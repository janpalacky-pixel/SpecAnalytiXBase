# src/controllers/data_analysis/resolution_enhancement_controller.py

import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.resolution_enhancement_manager import ResolutionEnhancementManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)


class ResolutionEnhancementController:
    """
    Controller for spectral resolution enhancement (Wiener deconvolution).

    Bridges ResolutionEnhancementManager (the algorithm) with the dialog
    and the OperationsController commit pipeline — mirrors
    CosmicRayController's role. Before this class existed, both
    ResolutionEnhancementDialog's live preview and
    OperationsController.commit_resolution_enhancement independently
    created their own fresh ResolutionEnhancementManager() instance
    inline, with no shared state and no per-spectrum failure tracking
    reaching the commit path at all.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = ResolutionEnhancementManager()

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as SVDBackgroundController.oc
        / BaselineCorrectionController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from                                            #
    # OperationsController.commit_resolution_enhancement, unchanged in    #
    # behavior, as part of giving every operation its own dedicated       #
    # controller instead of OperationsController holding all of them      #
    # directly. Internal references to OperationsController's own state   #
    # now go through self.oc instead of self directly; rec (previously    #
    # fetched via main_controller, since this method used to live outside #
    # this class) is simply self now.                                     #
    # ------------------------------------------------------------------ #

    def commit_resolution_enhancement(self, settings, add_as_new, selected_spectra):
        """Commit the Resolution enhancement operation directly, called by
        the dialog's own Apply / Add as New buttons rather than through the
        generic Run dispatch.

        Add as New uses suffix-style unique naming ('<label>_enhanced',
        bumped on collision), matching the other refined operations.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra:
            return False, 'Please select one or more spectra to apply resolution enhancement.'

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "Resolution Enhancement",
            f"Applying resolution enhancement to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            processed_spectra, error = self.apply_enhancement_to_spectra(
                settings, selected_spectra,
                progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
            )
            if error is not None:
                return False, f'Error applying resolution enhancement: {error}'

            if not processed_spectra:
                return False, 'Failed to apply resolution enhancement.'

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in processed_spectra:
                    base_name = f"{spec['label']}_enhanced"
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
                'Resolution enhancement', settings, selected_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    selected_spectra, processed_spectra,
                    operation_name='Resolution enhancement',
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
                logger.error(f"Error plotting after resolution enhancement: {exc}")
        finally:
            if progress is not None:
                progress.close()

        n = len(processed_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in processed_spectra)
            message = f'Added {n} new {noun}: {new_names}.'
        else:
            message = f'Replaced {n} {noun} with the resolution-enhanced result.'
        # A spectrum too degenerate to deconvolve (too few points, or a
        # non-finite result) is left unchanged rather than corrupted or
        # aborting the whole batch — see ResolutionEnhancementManager.enhance.
        # Surface that here so it isn't silently invisible to the user.
        if getattr(self.manager, 'failed_labels', None):
            fn = len(self.manager.failed_labels)
            fnoun = 'spectrum' if fn == 1 else 'spectra'
            failed_names = self.oc._format_names_for_message(self.manager.failed_labels)
            message += (f'\n\u26a0 Could not enhance {fn} {fnoun} (left unchanged): '
                        f'{failed_names}.')
        return True, message

    # ------------------------------------------------------------------ #
    # Dialog                                                               #
    # ------------------------------------------------------------------ #

    def show_dialog(self, selected_spectra=None, commit_callback=None, current_settings=None):
        """Open the resolution enhancement dialog."""
        from src.views.dialogs.data_analysis.resolution_enhancement_dialog import (
            ResolutionEnhancementDialog)
        from PyQt5.QtWidgets import QMessageBox

        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                'No spectra selected',
                'Please select one or more spectra for resolution enhancement.'
            )
            return None

        dialog = ResolutionEnhancementDialog(
            parent=self.controller.view,
            spectra=selected_spectra,
            current_settings=current_settings,
            controller=self,
            commit_callback=commit_callback,
        )
        dialog.exec_()
        return dialog.get_settings()

    def preview(self, x, y, irf_sigma, snr):
        """Pure preview computation for a single spectrum (used by the
        dialog's live preview) — routed through the shared manager
        instance rather than a throwaway one, for consistency, though
        this particular computation is stateless either way."""
        return self.manager.preview(x, y, irf_sigma, snr)

    # ------------------------------------------------------------------ #
    # Apply                                                                #
    # ------------------------------------------------------------------ #

    def apply_enhancement_to_spectra(self, settings, spectra=None, progress_callback=None):
        """Enhance *spectra* with *settings* and return the result list.

        Returns (processed_spectra, error_message). error_message is None
        on success; processed_spectra is None on failure. Never raises —
        OperationsController.commit_resolution_enhancement turns this
        straight into its own (success, message) return value.

        progress_callback: optional callable, passed straight through to
        ResolutionEnhancementManager.enhance() — see that method's own
        docstring. None (the default) — no change from before.
        """
        if spectra is None:
            spectra = self.controller.spectrum_selector.get_selected_spectra()
        if not spectra:
            return None, 'No spectra to process.'

        try:
            processed = self.manager.enhance(
                spectra, irf_sigma=settings['irf_sigma'], snr=settings['snr'],
                progress_callback=progress_callback,
            )
        except Exception as exc:
            logger.exception('Unexpected error in resolution enhancement')
            return None, f'An unexpected error occurred: {exc}'
        return processed, None

    def update_settings(self, settings):
        if 'irf_sigma' in settings:
            self.manager.irf_sigma = settings['irf_sigma']
        if 'snr' in settings:
            self.manager.snr = settings['snr']
