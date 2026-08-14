# src/controllers/data_analysis/fft_denoising_controller.py

import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.fft_denoising_manager import FFTDenoisingManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)


class FFTDenoisingController:
    """Thin controller between OperationsController and FFTDenoisingManager."""

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager    = FFTDenoisingManager()

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as SVDBackgroundController.oc
        / BaselineCorrectionController.oc / SavitzkyGolayController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from OperationsController.commit_fft_denoising, #
    # unchanged in behavior, as part of giving every operation its own    #
    # dedicated controller instead of OperationsController holding all    #
    # of them directly. Internal references to OperationsController's own #
    # state now go through self.oc instead of self directly; fdc          #
    # (previously fetched via main_controller, since this method used to  #
    # live outside this class) is simply self now.                        #
    # ------------------------------------------------------------------ #

    def commit_fft_denoising(self, settings, add_as_new, selected_spectra):
        """Commit the FFT Denoising operation directly, called by the
        dialog's own Apply / Add as New buttons rather than through the
        generic Run dispatch.

        Add as New uses suffix-style unique naming ('<label>_denoised',
        bumped on collision), matching the other refined operations.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra:
            return False, 'Please select one or more spectra to apply FFT denoising.'

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "FFT Denoising",
            f"Applying FFT denoising to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            try:
                processed_spectra = self.apply_denoising_to_spectra(
                    settings, selected_spectra,
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
                )
            except Exception as exc:
                return False, f'Error applying FFT denoising: {exc}'

            if not processed_spectra:
                return False, 'Failed to apply FFT denoising to any of the selected spectra.'

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in processed_spectra:
                    base_name = f"{spec['label']}_denoised"
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
                'FFT Denoising', settings, selected_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    selected_spectra, processed_spectra,
                    operation_name='FFT Denoising',
                    pre_state=current_state,
                )

            if progress is not None:
                progress.setLabelText("Updating spectrum list\u2026")
                QApplication.processEvents()

            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

            highlight_ids = {
                spectrum_key(s) for s in (selected_spectra if add_as_new else processed_spectra)
            }
            self.oc._rebuild_spectra_list_with_selection(highlight_ids)

            self.controller.selected_spectra = (
                selected_spectra if add_as_new else processed_spectra
            )
            if progress is not None:
                progress.setLabelText("Redrawing plot\u2026")
                QApplication.processEvents()
            try:
                self.controller.plot_spectra(
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None
                )
            except Exception as exc:
                logger.error(f"Error plotting after FFT denoising: {exc}")
        finally:
            if progress is not None:
                progress.close()

        n = len(processed_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in processed_spectra)
            message = f'Added {n} new {noun}: {new_names}.'
        else:
            message = f'Replaced {n} {noun} with the denoised result.'
        # A spectrum that failed to denoise (unexpected numerical issue)
        # is left unchanged by denoise_spectra() rather than dropped or
        # corrupted, but that was previously invisible outside the log.
        if getattr(self.manager, 'failed_labels', None):
            fn = len(self.manager.failed_labels)
            fnoun = 'spectrum' if fn == 1 else 'spectra'
            failed_names = self.oc._format_names_for_message(self.manager.failed_labels)
            message += (f'\n\u26a0 Could not denoise {fn} {fnoun} (left unchanged): '
                        f'{failed_names}.')
        return True, message

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------

    def show_dialog(self, selected_spectra=None, commit_callback=None, current_settings=None):
        """Open the FFT Denoising dialog.

        *current_settings*, if given, takes priority over the manager's
        committed state for pre-population — settings tweaked in the
        dialog but never committed (the user just clicked Close) would
        otherwise be forgotten the next time the dialog opens, since the
        manager only updates when Apply / Add as New actually runs (see
        OperationsController.commit_fft_denoising). Falls back to the
        manager's state when no cache is available yet (e.g. the very
        first open).

        *commit_callback*, if given, is passed straight through to the
        dialog (OperationsController.commit_fft_denoising) so its own
        Apply / Add as New buttons can commit directly — there's no
        separate Run step for this operation any more. Since Apply / Add
        as New no longer map to QDialog's accept/reject, this method
        always returns whatever get_settings() reports once the dialog
        closes, regardless of how it closed, so the caller can remember
        what was last shown even if nothing was committed.
        """
        from src.views.dialogs.data_analysis.fft_denoising_dialog import FFTDenoisingDialog
        from PyQt5.QtWidgets import QMessageBox

        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                'No spectra selected',
                'Please select one or more spectra for FFT denoising.'
            )
            return None

        if not current_settings:
            current_settings = {
                'stop_bands':  list(self.manager.stop_bands),
                'low_cutoff':  self.manager.low_cutoff,
                'high_cutoff': self.manager.high_cutoff,
                'window':      self.manager.window,
            }

        dialog = FFTDenoisingDialog(
            parent=self.controller.view,
            current_settings=current_settings,
            controller=self.controller,
            selected_spectra=selected_spectra,
            commit_callback=commit_callback,
        )

        dialog.exec_()
        return dialog.get_settings()

    def show_parameters_dialog(self):
        selected = self.controller.spectrum_selector.get_selected_spectra()
        return self.show_dialog(selected) is not None

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply_denoising_to_spectra(self, settings, spectra=None, progress_callback=None):
        if spectra is None:
            spectra = self.controller.spectrum_selector.get_selected_spectra()
        if not spectra:
            return []

        valid = [s for s in spectra
                 if len(s.get('x_scale', [])) > 3 and len(s.get('y_scale', [])) > 3]
        if not valid:
            return []

        return self.manager.denoise_spectra(valid, settings, progress_callback=progress_callback)

    def update_settings(self, settings):
        self.manager.update_settings(settings)
