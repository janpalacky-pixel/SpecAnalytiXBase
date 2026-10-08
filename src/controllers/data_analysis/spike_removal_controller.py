# src/controllers/data_analysis/spike_removal_controller.py

import uuid
import numpy as np
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.spike_removal_manager import SpikeRemovalManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key
from src.modules.utils.progress_utils import notify_progress
from src.modules.utils.revision_tracking import revision_changed

logger = get_logger(__name__)


class SpikeRemovalController:
    """
    Controller for spike removal operations.
    Bridges the manager (algorithm) with the dialogs and the
    OperationsController pipeline.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager    = SpikeRemovalManager()
        # Compared against IncrementalOperationsManager.revision in
        # show_interactive_dialog() below, so a reopen only forgets a
        # spectrum's picked/detected spikes if an operation actually
        # changed that spectrum's data meanwhile -- see
        # revision_tracking.py.
        self._last_seen_revision = None

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as SVDBackgroundController.oc
        / BaselineCorrectionController.oc / CosmicRayController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from OperationsController.commit_spike_removal, #
    # unchanged in behavior, as part of giving every operation its own    #
    # dedicated controller instead of OperationsController holding all    #
    # of them directly. Internal references to OperationsController's own #
    # state now go through self.oc instead of self directly; src          #
    # (previously fetched via main_controller, since this method used to  #
    # live outside this class) is simply self now.                        #
    # ------------------------------------------------------------------ #

    def commit_spike_removal(self, settings, add_as_new, selected_spectra):
        """Commit the Spike removal operation directly, called by the
        dialog's own Apply / Add as New buttons rather than through the
        generic Run dispatch.

        Add as New uses suffix-style unique naming ('<label>_despiked',
        bumped on collision), matching the other refined operations.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra:
            return False, 'Please select one or more spectra to apply spike removal.'

        effective_spikes = settings.get('effective_spikes', {})
        total = sum(len(v) for v in effective_spikes.values())
        if total == 0:
            return False, (
                "No spikes are currently marked for removal.\n\n"
                "Use 'Re-detect all spectra' or mark spikes manually first."
            )

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "Spike Removal",
            f"Applying spike removal to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            try:
                processed_spectra = self.apply_interactive_removal(
                    settings, selected_spectra,
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
                )
            except Exception as exc:
                # The user only sees the one-line message; the log file gets the
                # full traceback, so a reported error can actually be diagnosed.
                logger.exception("Error applying spike removal")
                return False, f'Error applying spike removal: {exc}'

            if not processed_spectra:
                return False, 'Failed to apply spike removal.'

            # apply_interactive_removal() returns an entry for every selected
            # spectrum unconditionally — one with zero spikes marked comes
            # back with its y_scale completely unchanged. Only spectra that
            # actually had at least one spike removed are meaningfully
            # "processed"; keep the rest out of the result the same way
            # Manual Baseline and Interactive Subtraction do, so Add as New
            # doesn't duplicate untouched spectra under new names and
            # Operations History doesn't list every selected spectrum as
            # affected when most of them had nothing marked.
            processed_spectra = [
                s for s in processed_spectra
                if effective_spikes.get(s['label'])
            ]
            if not processed_spectra:
                return False, (
                    "None of the selected spectra had any spikes actually marked "
                    "for removal."
                )

            # Keep a reference under original labels before Add as New renames
            # them, for register_copy_operation() below.
            despiked_spectra = list(processed_spectra)

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in processed_spectra:
                    base_name = f"{spec['label']}_despiked"
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
                    renamed.append(spec)
                processed_spectra = renamed
                output_spectra = current_state + processed_spectra
            else:
                processed_labels = {s['label'] for s in processed_spectra}
                output_spectra = [s for s in current_state if s['label'] not in processed_labels]
                output_spectra.extend(processed_spectra)

            self.oc.operations_manager.apply_operation(
                # affected_spectra is processed_spectra (only the ones that
                # actually had spikes removed), not selected_spectra (the
                # full original selection) — same reasoning as Manual
                # Baseline: a spectrum with zero spikes marked passed through
                # apply_interactive_removal() completely unchanged and
                # shouldn't be reported as affected just for having been
                # selected.
                'Spike removal', settings, processed_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    despiked_spectra, processed_spectra,
                    operation_name='Spike removal',
                    pre_state=current_state,
                )

            # The removal has now been baked into the data — clear the
            # persisted detection state so stale spike markers don't reappear
            # next time this dialog is opened, mirroring the cleanup the other
            # refined operations do.
            self.manager.reset_all()
            self.oc.current_parameters.pop('Spike removal', None)

            if progress is not None:
                progress.setLabelText("Updating spectrum list\u2026")
                QApplication.processEvents()

            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

            highlight_ids = {
                spectrum_key(s) for s in (despiked_spectra if add_as_new else processed_spectra)
            }
            self.oc._rebuild_spectra_list_with_selection(highlight_ids)

            self.controller.selected_spectra = (
                despiked_spectra if add_as_new else processed_spectra
            )
            self.oc._redraw_after_operation(progress, "spike removal")
        finally:
            if progress is not None:
                progress.close()

        n = len(processed_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in processed_spectra)
            message = f'Added {n} new {noun}: {new_names}.'
        else:
            message = f'Removed {total} spike(s) across {n} {noun}.'
        return True, message

    # ------------------------------------------------------------------ #
    # Automatic removal                                                    #
    # ------------------------------------------------------------------ #

    def apply_automatic_removal(self, settings, spectra):
        """
        Apply automatic spike removal to spectra.

        Parameters
        ----------
        settings : dict  (threshold, half_window)
        spectra  : list of spectrum dicts (current state)

        Returns
        -------
        list of processed spectrum dicts
        """
        threshold   = settings.get('threshold', 7.0)
        half_window = settings.get('half_window', 2)

        processed = self.manager.apply_automatic_removal(
            spectra, threshold=threshold, half_window=half_window
        )

        summary = self.manager.get_summary(spectra)
        logger.info(
            "Automatic spike removal: %d spike(s) in %d/%d spectra",
            summary['total_spikes'],
            summary['spectra_with_spikes'],
            summary['total_spectra'],
        )
        return processed

    # ------------------------------------------------------------------ #
    # Interactive removal                                                   #
    # ------------------------------------------------------------------ #

    def show_interactive_dialog(self, spectra, current_settings=None, commit_callback=None):
        """
        Open the interactive spike removal dialog (modal).
        Restores previously defined spike selections if available.

        self.manager is a long-lived singleton whose auto_detected /
        manual_extra / rejected dicts are keyed by unique_id (see
        SpikeRemovalManager._key_for) so they survive a rename without
        being orphaned or, worse, silently picked up by an unrelated
        spectrum that later reuses an old label. The dialog itself stays
        label-based internally — it's modal, so no rename can happen
        mid-session — so this method is the seam that translates between
        the two: unique_id keys going in (saved_state), labels coming back
        out (_sync_manager below).

        *commit_callback*, if given, is passed straight through to the
        dialog (OperationsController.commit_spike_removal) so its own
        Apply / Add as New buttons can commit directly — there's no
        separate Run step for this operation any more.
        """
        from src.views.dialogs.data_analysis.spike_removal_interactive_dialog import (
            SpikeRemovalInteractiveDialog
        )

        # Prune settings left behind by spectra that no longer exist —
        # otherwise a newly imported spectrum that happens to reuse an old
        # label would inherit stale, unrelated spike markings (see
        # SpikeRemovalManager.prune_to_current_spectra docstring).
        self.manager.prune_to_current_spectra(self.controller.original_spectra)

        # If any operation ran since this dialog was last open (a
        # different spectrum's baseline correction, SNIP, an undo/redo,
        # ...), the spikes previously detected/picked for THESE spectra
        # may no longer correspond to their current data -- same
        # reasoning as BaselineCorrectionController.show_dialog. Only
        # clear the spectra actually being shown here, not the whole
        # manager (see _sync_manager's own comment on why a scoped clear
        # matters).
        should_reset, self._last_seen_revision = revision_changed(
            self.controller, self._last_seen_revision)
        if should_reset:
            for s in spectra:
                self.manager.reset_for_spectrum(self.manager._key_for(s))

        # Resolve the manager's unique_id keys back to each spectrum's
        # CURRENT label for the dialog, and restrict to spectra actually
        # in *this* selection — a key that doesn't match any spectrum here
        # (renamed away, or never belonged to this selection) is left out
        # rather than passed through under a guessed label.
        key_to_label = {self.manager._key_for(s): s['label'] for s in spectra}
        saved_state = {
            'auto_detected': {
                key_to_label[k]: v for k, v in self.manager.auto_detected.items()
                if k in key_to_label
            },
            'manual_extra': {
                key_to_label[k]: list(v) for k, v in self.manager.manual_extra.items()
                if k in key_to_label
            },
            'rejected': {
                key_to_label[k]: set(v) for k, v in self.manager.rejected.items()
                if k in key_to_label
            },
        }
        dialog = SpikeRemovalInteractiveDialog(
            parent=self.controller.view,
            spectra=spectra,
            controller=self.controller,
            current_settings=current_settings,
            saved_state=saved_state,
            commit_callback=commit_callback,
        )
        # Keep manager in sync whenever the dialog remembers its marking
        # (closeEvent emits this on every close that wasn't already
        # handled by a successful commit — see SpikeRemovalInteractiveDialog).
        def _sync_manager(settings):
            # Rebuild manager state for THIS session's spectra only, from
            # the effective spikes stored in settings.
            # settings['effective_spikes'] is keyed by label (the dialog's
            # own internal representation, built from this same *spectra*
            # list) — translate back to unique_id-based keys before
            # writing into the long-lived manager, so this state stays
            # correctly attached to its spectrum even if a rename happens
            # before the dialog is opened again.
            #
            # IMPORTANT: this used to call self.manager.reset_all(), which
            # wiped every spectrum's stored markings, not just the ones in
            # this dialog session — so e.g. opening spectrum B and closing
            # it would silently erase spectrum A's previously-saved manual
            # spikes too. Scope the reset to exactly the spectra that were
            # actually open here instead, leaving everything else
            # untouched.
            label_to_key = {s['label']: self.manager._key_for(s) for s in spectra}
            for s in spectra:
                self.manager.reset_for_spectrum(label_to_key[s['label']])
            for label, indices in settings.get('effective_spikes', {}).items():
                key = label_to_key.get(label, label)
                for idx in indices:
                    self.manager.add_manual_spike(key, idx)

        dialog.removal_applied.connect(_sync_manager)
        return dialog

    def apply_interactive_removal(self, settings, spectra, progress_callback=None):
        """
        Apply removal using the effective spike lists and per-spectrum
        half-window values stored in settings.

        This is a separate reimplementation from
        SpikeRemovalManager._remove_from_spectra rather than a call into
        it, because it needs per-spectrum half-window overrides
        (settings['half_window_map']) that _remove_from_spectra doesn't
        know about (it only has one manager-wide self.half_window) — so
        it can't just delegate there. This IS the method the real,
        interactive-dialog commit path (commit_spike_removal above) calls
        for every actual spike-removal run in the running app.

        Previously this reimplementation built new_spec['y_scale'] and
        nothing else — no metadata, no correction_history entry at all —
        while the OTHER, unused implementation
        (SpikeRemovalManager._remove_from_spectra, only ever reached via
        Batch Pipeline Replay) correctly wrote one. That's why Spike
        Removal's metadata looked empty for affected spectra: the code
        path that actually runs when you use the dialog was silently
        skipping it. Now writes the same style of correction_history
        entry Cosmic Ray Removal does — pixel index (1-based) AND x-scale
        value for each removed spike, only for spectra that actually had
        ≥1 spike removed.

        progress_callback: optional callable, invoked every 50 spectra
            during the loop below — see SNIPBaselineManager.apply_correction
            for the full reasoning; same hook/contract. None (the
            default) — no change from before.
        """
        effective_spikes = settings.get('effective_spikes', {})
        global_hw        = settings.get('half_window', 2)
        hw_map           = settings.get('half_window_map', {})

        from src.modules.data_analysis.spike_removal_manager import SpikeRemovalManager
        from src.modules.utils.correction_history import append_correction_history
        processed = []
        for i, spectrum in enumerate(spectra):
            notify_progress(progress_callback, i)
            label   = spectrum['label']
            indices = effective_spikes.get(label, [])
            hw      = hw_map.get(label, global_hw)
            new_y   = SpikeRemovalManager._interpolate_spikes(
                np.asarray(spectrum['y_scale'], dtype=float), indices, hw
            )
            new_spec = dict(spectrum)
            new_spec['y_scale'] = new_y
            if indices:
                # dict(spectrum) above is a SHALLOW copy — new_spec['metadata']
                # is still the exact same dict object as spectrum['metadata']
                # unless replaced with its own copy first (same shallow-copy
                # bug pattern fixed in CosmicRayManager.apply /
                # SpikeRemovalManager._remove_from_spectra).
                new_spec['metadata'] = dict(new_spec.get('metadata') or {})
                x_scale = np.asarray(spectrum['x_scale'], dtype=float)
                sorted_indices = sorted(indices)
                new_spec['metadata']['correction_history'] = append_correction_history(
                    spectrum.get('metadata'), 'Spike removal',
                    {
                        'spike_count': len(indices),
                        'half_window': hw,
                        # Same "pixel index + x-scale value" pairing Cosmic
                        # Ray Removal records — the raw index alone only
                        # makes sense if you also know the axis.
                        'spike_x_positions': [round(float(x_scale[idx]), 4) for idx in sorted_indices],
                        'spike_x_indices': [int(idx) + 1 for idx in sorted_indices],
                    }
                )
            processed.append(new_spec)

        total = sum(len(v) for v in effective_spikes.values())
        logger.info(
            "Interactive spike removal: %d spike(s) removed across %d spectra",
            total, len(spectra)
        )
        return processed
