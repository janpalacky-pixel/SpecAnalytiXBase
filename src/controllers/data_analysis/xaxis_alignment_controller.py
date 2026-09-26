# src/controllers/data_analysis/xaxis_alignment_controller.py
"""
Controller for the x-axis alignment (x-shift correction) operation.

Follows the same pattern as NormalizationController:
  • show_dialog()             – open the parameter dialog, persist settings
  • apply_alignment_to_spectra() – delegate computation to the manager
  • update_settings()          – forward settings to the manager
"""

import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.xaxis_alignment_manager import XAxisAlignmentManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)


class XAxisAlignmentController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = XAxisAlignmentManager()
        self._last_settings = {}   # persists full settings dict including cache
        # Labels of any spectra skipped on the most recent
        # apply_alignment_to_spectra() call (too few points to align) — see
        # that method. Exposed so the commit path can warn the user, rather
        # than a skipped spectrum silently vanishing from the result with
        # only a log line (invisible in the running app) to explain why.
        self.last_skipped_labels = []

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as SVDBackgroundController.oc
        / BaselineCorrectionController.oc / FFTDenoisingController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from OperationsController.commit_xaxis_alignment, #
    # unchanged in behavior, as part of giving every operation its own    #
    # dedicated controller instead of OperationsController holding all    #
    # of them directly. Internal references to OperationsController's own #
    # state now go through self.oc instead of self directly; xac          #
    # (previously fetched via main_controller, since this method used to  #
    # live outside this class) is simply self now.                        #
    # ------------------------------------------------------------------ #

    def commit_xaxis_alignment(self, settings, add_as_new, selected_spectra):
        """Commit the X-axis alignment operation directly, called by the
        dialog's own Apply / Add as New buttons rather than through the
        generic Run dispatch. Add as New uses suffix-style unique naming
        ('<label>_aligned', bumped on collision), matching Data range,
        Normalization, and Interactive Subtraction.

        Re-runs the alignment from *settings* every time, regardless of
        whether the dialog's own Run preview was used first — Run preview
        is purely there so the user can inspect the result before
        committing, the same way the old Run-button workflow always
        recomputed rather than trusting a stale preview.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra or len(selected_spectra) < 2:
            return False, 'X-axis alignment requires at least 2 selected spectra.'

        ref_idx = settings.get('reference_spectrum_index', 0)
        if ref_idx >= len(selected_spectra):
            return False, (
                f'The stored reference index ({ref_idx}) exceeds the number of '
                f'selected spectra ({len(selected_spectra)}).\n'
                'Please choose a new reference spectrum.'
            )

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "X-axis Alignment",
            f"Applying x-axis alignment to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            try:
                aligned_spectra = self.apply_alignment_to_spectra(
                    settings, selected_spectra,
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
                )
            except RuntimeError as exc:
                return False, str(exc)
            except Exception as exc:
                logger.exception('Unexpected error in x-axis alignment')
                return False, f'An unexpected error occurred: {exc}'

            if not aligned_spectra:
                return False, (
                    'No spectra were returned after alignment.\n'
                    'Check that the selected spectra overlap and share compatible x-scales.'
                )

            # apply_alignment_to_spectra() silently drops any selected spectrum
            # with fewer than 4 points — it isn't even passed through
            # unchanged, just excluded entirely. Keep a reference to which
            # selected spectra actually made it into aligned_spectra, under
            # their original labels, so they (and only they) get reported as
            # affected/copied/highlighted below — the same reasoning as the
            # Manual Baseline and Spike Removal fixes, just for a much rarer
            # trigger.
            aligned_input_labels = {s['label'] for s in aligned_spectra}
            aligned_input_spectra = [s for s in selected_spectra if s['label'] in aligned_input_labels]

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                # Suffix-style unique naming, matching the Data range,
                # Normalization, and Interactive Subtraction commits — never
                # reuse the source label, since "add as new" appends alongside
                # the untouched original.
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in aligned_spectra:
                    base_name = f"{spec['label']}_aligned"
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
                aligned_spectra = renamed
                output_spectra = current_state + aligned_spectra
            else:
                aligned_labels = {s['label'] for s in aligned_spectra}
                output_spectra = [s for s in current_state if s['label'] not in aligned_labels]
                output_spectra.extend(aligned_spectra)

            self.oc.operations_manager.apply_operation(
                'X-axis alignment', settings, aligned_input_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    aligned_input_spectra, aligned_spectra,
                    operation_name='X-axis alignment',
                    pre_state=current_state,
                )

            if progress is not None:
                progress.setLabelText("Updating spectrum list\u2026")
                QApplication.processEvents()

            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

            highlight_ids = {
                spectrum_key(s) for s in (aligned_input_spectra if add_as_new else aligned_spectra)
            }
            self.oc._rebuild_spectra_list_with_selection(highlight_ids)

            self.controller.selected_spectra = (
                aligned_input_spectra if add_as_new else aligned_spectra
            )
            self.oc._redraw_after_operation(progress, "x-axis alignment")
        finally:
            if progress is not None:
                progress.close()

        n = len(aligned_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in aligned_spectra)
            message = f'Added {n} new {noun}: {new_names}.'
        else:
            message = f'Replaced {n} {noun} with the aligned result.'
        # apply_alignment_to_spectra() silently leaves any spectrum with
        # fewer than 4 points out of aligned_spectra entirely (see the
        # comment above aligned_input_labels) — the count above was
        # already correctly excluding them, but nothing told the user WHY
        # fewer spectra came back than were selected. Same fix as
        # commit_automated_baseline / commit_snip_baseline.
        if getattr(self, 'last_skipped_labels', None):
            sn = len(self.last_skipped_labels)
            snoun = 'spectrum' if sn == 1 else 'spectra'
            skipped_names = self.oc._format_names_for_message(self.last_skipped_labels)
            message += (f'\n\u26a0 {sn} {snoun} skipped (too few data points): '
                        f'{skipped_names}.')
        return True, message

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------

    def get_default_range(self):
        selected = self.controller.spectrum_selector.get_selected_spectra()
        return self.manager.get_default_range(selected)

    def show_dialog(self, selected_spectra=None, commit_callback=None):
        """Open the alignment dialog and return the settings dict, or None if cancelled.

        Settings are always pre-populated from whatever was last shown for
        this exact spectra selection (self._last_settings), even if it was
        never committed — Apply / Add as New no longer map to QDialog's
        accept(), so without this, settings tweaked but not Applied would be
        forgotten the next time the dialog opens.

        *commit_callback*, if given, is passed straight through to the
        dialog (OperationsController.commit_xaxis_alignment) so its own
        Apply / Add as New buttons can commit directly — there's no
        separate Run step for this operation any more.
        """
        from src.views.dialogs.data_analysis.xaxis_alignment_dialog import XAxisAlignmentDialog
        from PyQt5.QtWidgets import QMessageBox

        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                'No spectra selected',
                'Please select two or more spectra for x-axis alignment.'
            )
            return None

        if len(selected_spectra) < 2:
            QMessageBox.warning(
                self.controller.view,
                'Insufficient spectra',
                'X-axis alignment requires at least 2 spectra.\n'
                'Please select at least 2 spectra.'
            )
            return None

        # Use full persisted settings (includes _cached_aligned / _cached_hash)
        # but only if the spectra selection is identical to the last time
        # the dialog was shown. Keyed by unique_id (see
        # XAxisAlignmentManager._key_for), not label, so a rename alone
        # doesn't look like "a different selection" and discard a still-valid
        # preview cache, and so a re-imported spectrum that happens to reuse
        # an old label can't be mistaken for the spectrum that cache belongs to.
        current_keys = [self.manager._key_for(s) for s in selected_spectra]
        if (self._last_settings and
                self._last_settings.get('_cached_keys') == current_keys):
            current_settings = dict(self._last_settings)
        else:
            # Different selection — carry over computation params but drop
            # the preview cache (it was computed for a different set of
            # spectra and would mislead here).
            base = self._last_settings or {}

            # reference_spectrum_index is a POSITION in the selection list,
            # not a stable identity — reusing the raw number against a
            # different selection can silently point at an unrelated
            # spectrum (different spectra, or the same ones reordered).
            # Resolve it by identity instead: find where the spectrum that
            # was actually chosen as reference last time now sits in
            # *this* selection, and use that. If it isn't part of this
            # selection at all, fall back to the first spectrum rather than
            # keep a number that no longer means anything.
            ref_key = base.get('_cached_reference_key')
            new_ref_idx = 0
            if ref_key is not None:
                for i, s in enumerate(selected_spectra):
                    if self.manager._key_for(s) == ref_key:
                        new_ref_idx = i
                        break
                else:
                    logger.debug(
                        "X-axis alignment: previous reference spectrum is not "
                        "part of the current selection; defaulting reference "
                        "to the first spectrum."
                    )

            current_settings = {
                'reference_spectrum_index': new_ref_idx,
                'max_shift':                base.get('max_shift',
                    getattr(self.manager, 'max_shift', 10.0)),
                'interpolation_method':     base.get('interpolation_method',
                    getattr(self.manager, 'interpolation_method', 'cubic')),
                'x_range':                  base.get('x_range',
                    getattr(self.manager, 'x_range', None)),
            }

        dialog = XAxisAlignmentDialog(
            parent=self.controller.view,
            current_settings=current_settings,
            controller=self.controller,
            selected_spectra=selected_spectra,
            commit_callback=commit_callback,
        )

        # Apply / Add as New commit directly via commit_callback (see
        # XAxisAlignmentDialog._on_commit_clicked) instead of going through
        # QDialog's accept(). Close maps to reject(). Either way, just run
        # the dialog and remember whatever it was last showing — including
        # its preview cache — so reopening for the same selection starts
        # from where the user left off, applied or not.
        dialog.exec_()
        settings = dialog.get_settings()
        settings['_cached_keys'] = current_keys
        # Remember WHICH spectrum (by identity) is the reference, not just
        # its position, so a future reopen with a different/reordered
        # selection can still find it correctly — see resolution logic above.
        ref_idx = settings.get('reference_spectrum_index', 0)
        if 0 <= ref_idx < len(selected_spectra):
            settings['_cached_reference_key'] = self.manager._key_for(selected_spectra[ref_idx])
        self._last_settings = dict(settings)
        return settings

    def show_parameters_dialog(self):
        """Convenience wrapper used by OperationsController.
        Returns True if the dialog was accepted."""
        selected = self.controller.spectrum_selector.get_selected_spectra()
        return self.show_dialog(selected) is not None

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply_alignment_to_spectra(self, settings, spectra=None, progress_callback=None):
        """Align *spectra* with *settings* and return the result list.

        If *spectra* is None the currently selected spectra are used.

        progress_callback: optional callable, passed straight through to
        XAxisAlignmentManager.align_spectra() — see that method's own
        docstring. None (the default) — no change from before.
        """
        if spectra is None:
            spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not spectra:
            return []

        # settings['reference_spectrum_index'] is a POSITION in *spectra* as
        # given — but the filtering loop below can remove spectra from the
        # middle of the list (too few points to align), which silently
        # shifts every later index down. Resolve which spectrum is actually
        # meant to be the reference by IDENTITY first, before any filtering
        # touches the list, then find its new position afterward — reusing
        # the raw index across the filtering step let it silently point at
        # a completely different spectrum whenever anything ahead of the
        # reference got dropped (confirmed directly: the intended reference
        # ended up being shifted like an ordinary spectrum, while an
        # unrelated spectrum was silently treated as the reference instead,
        # with no error or warning).
        self.last_skipped_labels = []
        orig_ref_idx = int(settings.get('reference_spectrum_index', 0))
        ref_key = None
        if 0 <= orig_ref_idx < len(spectra):
            ref_key = self.manager._key_for(spectra[orig_ref_idx])

        valid = []
        for s in spectra:
            if len(s.get('x_scale', [])) < 4 or len(s.get('y_scale', [])) < 4:
                logger.warning(
                    "Skipping spectrum '%s': too few data points for alignment.",
                    s.get('label', '?')
                )
                self.last_skipped_labels.append(s.get('label', '?'))
                continue
            valid.append(s)

        if len(valid) < 2:
            logger.debug('Fewer than 2 valid spectra for alignment.')
            return []

        settings = dict(settings)
        new_ref_idx = 0
        if ref_key is not None:
            for i, s in enumerate(valid):
                if self.manager._key_for(s) == ref_key:
                    new_ref_idx = i
                    break
            else:
                logger.warning(
                    "X-axis alignment: the selected reference spectrum had "
                    "too few points and was excluded; defaulting the "
                    "reference to the first remaining spectrum instead."
                )
        settings['reference_spectrum_index'] = new_ref_idx

        return self.manager.align_spectra(valid, settings, progress_callback=progress_callback)

    def update_settings(self, settings):
        self.manager.update_settings(settings)
