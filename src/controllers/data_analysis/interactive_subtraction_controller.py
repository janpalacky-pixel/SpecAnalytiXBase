# src/controllers/data_analysis/interactive_subtraction_controller.py
import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.interactive_subtraction_manager import InteractiveSubtractionManager
from src.modules.utils.spectra_validation import validate_common_x_axis
from src.modules.utils.progress_utils import notify_progress
from src.modules.utils.spectrum_identity import spectrum_key
from src.modules.utils.revision_tracking import revision_changed
import numpy as np


class InteractiveSubtractionController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = InteractiveSubtractionManager()
        self._last_selection_hash = None
        # Compared against IncrementalOperationsManager.revision in
        # show_dialog() below -- _check_and_clear_on_selection_change only
        # catches a DIFFERENT selection being made; it has no way to know
        # that some OTHER operation (SNIP Baseline, say) changed the very
        # data a stored factor was picked against, for spectra that are
        # still selected. See revision_tracking.py.
        self._last_seen_revision = None

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as SVDBackgroundController.oc
        / BaselineCorrectionController.oc / XAxisAlignmentController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from                                            #
    # OperationsController.commit_interactive_subtraction, unchanged in   #
    # behavior, as part of giving every operation its own dedicated       #
    # controller instead of OperationsController holding all of them      #
    # directly. Internal references to OperationsController's own state   #
    # now go through self.oc instead of self directly; isc (previously    #
    # fetched via main_controller, since this method used to live outside #
    # this class) is simply self now.                                     #
    # ------------------------------------------------------------------ #

    def commit_interactive_subtraction(self, stored_factors, add_as_new, selected_spectra):
        """Commit interactive subtraction directly, called by the dialog's
        own Apply / Add as New buttons rather than through the generic
        Run dispatch — this operation no longer goes through
        run_operation's confirmation prompt or current_parameters at all,
        since the dialog now owns deciding when there's something valid
        to commit.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback rather than a separate, disconnected message
        box appearing in the main window.
        """
        if not selected_spectra:
            return False, 'No spectra selected in the main window.'

        settings = {'stored_factors': dict(stored_factors)}

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "Interactive Subtraction",
            f"Applying interactive subtraction to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            try:
                all_spectra, affected_labels = self.apply_subtraction_to_spectra(
                    settings, selected_spectra,
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
                )
                if not affected_labels:
                    return False, (
                        "No stored subtraction factors match the currently selected "
                        "spectra in the main window. Use 'Show info' to check what "
                        "has been committed via Update."
                    )
            except Exception as e:
                return False, f'Error applying interactive subtraction: {e}'

            affected_set = set(affected_labels)
            source_spectra = [s for s in selected_spectra if s['label'] in affected_set]
            processed_spectra = [s for s in all_spectra if s['label'] in affected_set]

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                # Give each result a NEW, unique label rather than reusing the
                # source spectrum's label — reusing it (as a previous version
                # of this code did) meant two spectra ended up sharing one
                # label, since "add as new" appends alongside the untouched
                # original rather than replacing it. Matches the Spectral
                # Calculator's own collision-avoidance approach.
                all_labels = {s['label'] for s in current_state}
                renamed_processed = []
                for spec in processed_spectra:
                    base_name = f"{spec['label']}_subtracted"
                    new_name = base_name
                    suffix = 1
                    while new_name in all_labels:
                        new_name = f'{base_name}_{suffix}'
                        suffix += 1
                    all_labels.add(new_name)
                    spec = dict(spec)
                    spec['label'] = new_name
                    # Give the new copy its own identity. Without this it
                    # silently shares the source spectrum's unique_id (dict(spec)
                    # is a shallow copy, and metadata is the SAME dict object as
                    # the source's unless replaced here) — meaning selecting the
                    # ORIGINAL by label later would also sweep in this copy via
                    # the ID-based matching fallback in
                    # _get_current_state_for_selected_spectra(), silently
                    # re-processing spectra that were never actually selected.
                    spec['metadata'] = dict(spec.get('metadata') or {})
                    spec['metadata']['unique_id'] = str(uuid.uuid4())
                    renamed_processed.append(spec)
                processed_spectra = renamed_processed
                output_spectra = current_state + processed_spectra
            else:
                # Replace: only the spectra that were actually subtracted are
                # swapped out for their results — everything else in the
                # current state (including unaffected selected spectra) is
                # left exactly as it was. Labels are unchanged here, which is
                # correct for a true in-place replace.
                output_spectra = [s for s in current_state if s['label'] not in affected_set]
                output_spectra.extend(processed_spectra)

            self.oc.operations_manager.apply_operation(
                "Interactive subtraction",
                settings,
                source_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                # Mirror the Spectral Calculator / Combine Spectra history
                # bookkeeping: remove the replace-style record apply_operation
                # just added, and register a proper "(add as new)" copy
                # record instead, so only one history entry appears.
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    source_spectra, processed_spectra,
                    operation_name="Interactive subtraction",
                    pre_state=current_state,
                )

            if progress is not None:
                progress.setLabelText("Updating spectrum list\u2026")
                QApplication.processEvents()

            # Controlled UI update — full list rebuild, same as every other
            # operation's commit path.
            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

            highlight_ids = {
                spectrum_key(s) for s in (source_spectra if add_as_new else processed_spectra)
            }
            self.oc._rebuild_spectra_list_with_selection(highlight_ids)

            self.controller.selected_spectra = (
                source_spectra if add_as_new else processed_spectra
            )
            self.oc._redraw_after_operation(progress, "interactive subtraction")
        finally:
            if progress is not None:
                progress.close()

        n = len(processed_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in processed_spectra)
            message = f'Added {n} new {noun}: {new_names}.'
        else:
            message = f'Replaced {n} {noun} with the subtraction result.'
        return True, message

    # ------------------------------------------------------------------
    # Selection tracking — clear stored factors when selection changes
    # ------------------------------------------------------------------
    def _get_selection_hash(self, spectra):
        """Identify a selection by the spectra themselves, not their
        labels — so a rename doesn't look like 'the selection changed'
        and wipe stored_factors for every spectrum in it, just because one
        of them got renamed."""
        if not spectra:
            return None
        return ','.join(sorted(self.manager._key_for(s) for s in spectra))

    def _check_and_clear_on_selection_change(self, selected_spectra):
        """Clear stored factors (and any file-loaded subtrahends) when the
        main-window selection changes, so reopening the dialog for a
        different set of spectra starts clean instead of showing
        'Show info' results left over from a previous, unrelated
        selection. A factor is only meaningful in the context of the
        selection it was created for.
        """
        h = self._get_selection_hash(selected_spectra)
        if self._last_selection_hash is not None and h != self._last_selection_hash:
            self.manager.stored_factors = {}
            self.manager.file_subtrahends = []
        self._last_selection_hash = h

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------
    def show_dialog(self, selected_spectra=None, commit_callback=None):
        """Show the interactive subtraction dialog.

        Passes the manager's persisted stored_factors so that closing and
        reopening the dialog for the *same* selection restores previous work.
        Factors are cleared automatically when the selection changes.

        commit_callback, if given, is passed straight through to the
        dialog so its own Apply / Add as New buttons can commit results
        directly — see OperationsController.commit_interactive_subtraction.
        """
        from src.views.dialogs.data_analysis.interactive_subtraction_dialog import InteractiveSubtractionDialog

        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra or len(selected_spectra) < 2:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self.controller.view,
                'Insufficient Spectra',
                'Please select at least two spectra for interactive subtraction.'
            )
            return None

        # Subtraction is point-by-point: minuend[i] - factor * subtrahend[i].
        # That is only meaningful if both spectra are sampled at the same x, so
        # refuse BEFORE the dialog is built — an empty/misleading dialog is worse
        # than no dialog. (The manager used to quietly reconcile mismatched axes
        # itself; that is the same silent-repair trap that produced real bugs
        # elsewhere in this codebase. Harmonising axes belongs to the Data Range
        # operation, where the user can see what it did.)
        if not validate_common_x_axis(selected_spectra, self.controller.view,
                                      'Interactive Subtraction'):
            return None

        # Clear factors if selection changed since last open
        self._check_and_clear_on_selection_change(selected_spectra)

        # Clear factors if any operation ran meanwhile, even for the SAME
        # selection -- a factor picked for a (minuend, subtrahend) pair no
        # longer means anything once either spectrum's own data changed.
        should_reset, self._last_seen_revision = revision_changed(
            self.controller, self._last_seen_revision)
        if should_reset:
            self.manager.stored_factors = {}

        # Prune settings left behind by spectra that no longer exist —
        # otherwise a newly imported spectrum that happens to reuse an old
        # label would inherit stale, unrelated stored factors (see
        # InteractiveSubtractionManager.prune_to_current_spectra docstring).
        self.manager.prune_to_current_spectra(self.controller.original_spectra)

        dialog = InteractiveSubtractionDialog(
            parent=self.controller.view,
            selected_spectra=selected_spectra,
            controller=self.controller,
            stored_factors=dict(self.manager.stored_factors),  # pass current state
            file_subtrahends=list(self.manager.file_subtrahends),  # pass current state
            commit_callback=commit_callback,
        )

        # Keep manager in sync when the dialog stores/clears factors or
        # loads a new subtrahend from a file.
        dialog.factors_updated.connect(self._on_factors_updated)
        dialog.file_subtrahends_updated.connect(self._on_file_subtrahends_updated)

        dialog.show()
        return dialog

    def _on_factors_updated(self, factors: dict):
        """Receive updated stored_factors from the dialog and persist in manager."""
        self.manager.stored_factors = factors

    def _on_file_subtrahends_updated(self, file_subtrahends: list):
        """Receive updated file_subtrahends from the dialog and persist in
        manager — kept local to this controller/session, never added to
        the main spectrum list."""
        self.manager.file_subtrahends = file_subtrahends

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------
    def apply_subtraction_to_spectra(self, settings, spectra=None, progress_callback=None):
        """Apply interactive subtraction using every stored
        (minuend_key, subtrahend_key) -> factor triple — exactly what
        the dialog's "Show info" displays — rather than whichever
        radio/list selection happened to be active in the dialog when OK
        was clicked. This also means only the spectra that actually have
        a stored factor are touched; everything else passes through
        completely unmodified.

        Keys are unique_id-based (see InteractiveSubtractionManager._key_for),
        not label-based, so a spectrum renamed between storing a factor and
        applying it is still resolved correctly.

        Each minuend has exactly ONE stored subtrahend at a time — this is
        a one-to-one "subtract spectrum X from spectrum Y" relationship,
        not several to be combined. The dialog's own Update button (see
        InteractiveSubtractionDialog.on_update_clicked) enforces this by
        replacing any existing entry for a minuend rather than adding
        alongside it, so stored_factors should never actually contain more
        than one entry per minuend by the time this runs. If it ever does
        anyway (e.g. settings loaded from before that fix was in place),
        whichever entry is encountered last for that minuend is the one
        that's applied — silently combining them would assume a chained,
        cumulative-subtraction intent that doesn't match how this feature
        is meant to be used.

        Returns the full list of spectra (modified minuends + everything
        else unchanged), plus, as a second value, the list of CURRENT
        labels that were actually subtracted — needed so the caller can
        register the operation against only the spectra actually affected,
        the same way the Spectral Calculator and Combine Spectra report
        their affected-spectra count, instead of the entire selection.

        progress_callback: optional callable, invoked every 50 processed
            (minuend, subtrahend) factors below — see
            SNIPBaselineManager.apply_correction for the full reasoning;
            same hook/contract. None (the default) — no change from
            before.
        """
        if spectra is None:
            spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not spectra:
            return [], []

        stored_factors = settings.get('stored_factors') or {}
        if not stored_factors:
            return [], []

        by_key = {self.manager._key_for(s): s for s in spectra}
        # File-loaded subtrahends live only on the manager, not in the
        # main-window spectra list — add them to the lookup so a stored
        # factor that references one resolves correctly. File subtrahends
        # are given a real unique_id at import time (see the dialog's
        # on_import_subtrahend_clicked), specifically so _key_for() never
        # falls back to a label here — a label collision with an unrelated
        # main-window spectrum would otherwise make setdefault() silently
        # keep the WRONG spectrum under this key, and a stored factor meant
        # for the file subtrahend would get applied against a completely
        # different spectrum with no error.
        for s in self.manager.file_subtrahends:
            by_key.setdefault(self.manager._key_for(s), s)
        result_spectra = list(spectra)  # default: everything passes through unchanged
        affected_labels = []

        for i, ((minuend_key, subtrahend_key), factor) in enumerate(stored_factors.items()):
            notify_progress(progress_callback, i)
            minuend = by_key.get(minuend_key)
            subtrahend = by_key.get(subtrahend_key)
            if minuend is None or subtrahend is None:
                # One of the two spectra from this stored triple is no
                # longer present in the current state (e.g. removed since
                # the triple was stored) — skip it rather than guess,
                # matching the dialog's own restore logic.
                continue

            # subtract_one raises AxisMismatchError (a ValueError subclass)
            # if the two spectra don't share an x-axis. The dialog refuses
            # to ever store such a pair in stored_factors in the first
            # place, so this should be unreachable in practice — but it's
            # left to propagate rather than caught-and-ignored here, as a
            # hard backstop rather than a silent skip. The current (and
            # only) caller, OperationsController.commit_interactive_subtraction,
            # already wraps this call in a try/except and surfaces the
            # message to the user.
            updated = self.manager.subtract_one(minuend, subtrahend, factor)
            idx = next(i for i, s in enumerate(result_spectra)
                       if self.manager._key_for(s) == minuend_key)
            result_spectra[idx] = updated
            affected_labels.append(minuend['label'])

        return result_spectra, affected_labels

    def update_settings(self, settings):
        self.manager.update_settings(settings)
