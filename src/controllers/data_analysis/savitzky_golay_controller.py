
# src/controllers/data_analysis/savitzky_golay_controller.py
import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.savitzky_golay_manager import SavitzkyGolayManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key
logger = get_logger(__name__)

class SavitzkyGolayController:
    def __init__(self, main_controller):
        """
        Initialize the SavitzkyGolayController.
        
        Args:
            main_controller: Reference to MainController instance
        """
        self.controller = main_controller
        self.manager = SavitzkyGolayManager()
        self.last_selection_hash = None  # Track selection changes

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as SVDBackgroundController.oc
        / BaselineCorrectionController.oc / NormalizationController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from OperationsController.commit_sg_smoothing,  #
    # unchanged in behavior, as part of giving every operation its own    #
    # dedicated controller instead of OperationsController holding all    #
    # of them directly. Internal references to OperationsController's own #
    # state now go through self.oc instead of self directly; sg           #
    # (previously fetched via main_controller, since this method used to  #
    # live outside this class) is simply self now.                        #
    # ------------------------------------------------------------------ #

    def commit_sg_smoothing(self, settings, add_as_new, selected_spectra):
        """Commit the Savitzky-Golay smoothing operation directly, called
        by the dialog's own Apply / Add as New buttons rather than through
        the generic Run dispatch.

        Add as New uses suffix-style unique naming ('<label>_smoothed',
        bumped on collision), matching the other refined operations.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra:
            return False, 'Please select one or more spectra to apply the operation.'

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "SG-Smoothing",
            f"Applying Savitzky-Golay smoothing to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            try:
                processed_spectra = self.apply_sg_to_spectra(
                    settings, selected_spectra,
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
                )
            except Exception as exc:
                return False, f'Error applying Savitzky-Golay filter: {exc}'

            if not processed_spectra:
                return False, 'Failed to apply Savitzky-Golay filter to any of the selected spectra.'

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in processed_spectra:
                    base_name = f"{spec['label']}_smoothed"
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
                'SG-smoothing', settings, selected_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    selected_spectra, processed_spectra,
                    operation_name='SG-smoothing',
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

            self.oc._redraw_after_operation(progress, "Savitzky-Golay filtering")
        finally:
            if progress is not None:
                progress.close()

        n = len(processed_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in processed_spectra)
            message = f'Added {n} new {noun}: {new_names}.'
        else:
            message = f'Replaced {n} {noun} with the smoothed result.'
        return True, message

    def _get_selection_hash(self, spectra):
        """Create a hash to identify unique selections."""
        if not spectra:
            return None
        return ','.join(sorted(spectrum['label'] for spectrum in spectra))
    
    def apply_sg_to_spectra(self, settings, spectra=None, progress_callback=None):
        """
        Apply Savitzky-Golay filtering to spectra with given settings.
        
        Args:
            settings: Dictionary of Savitzky-Golay settings
            spectra: Optional list of spectra to process. If None, uses 
                     controller's selected spectra.
            progress_callback: optional callable, passed straight through
                to SavitzkyGolayManager.apply_sg_filter() — see that
                method's docstring. None (the default) — no change from
                before.
                     
        Returns:
            List of processed spectra
        """
        # Determine which spectra to process
        if spectra is None:
            # Original behavior - get selected spectra from spectrum_selector
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()
        else:
            # Use the provided spectra
            selected_spectra = spectra
        
        if not selected_spectra:
            return []
        
        # All spectra should have consistent x and y arrays by this point
        # but we'll check just to be safe
        valid_spectra = []
        for spectrum in selected_spectra:
            if (len(spectrum['x_scale']) > 0 and len(spectrum['y_scale']) > 0):
                # Create a deep copy to avoid modifying input
                spectrum_copy = {}
                for key, value in spectrum.items():
                    if key in ['x_scale', 'y_scale']:
                        if hasattr(value, 'copy'):
                            spectrum_copy[key] = value.copy()
                        else:
                            spectrum_copy[key] = value
                    elif key == 'metadata':
                        if hasattr(value, 'copy'):
                            spectrum_copy[key] = value.copy()
                        else:
                            spectrum_copy[key] = value
                    else:
                        spectrum_copy[key] = value
                        
                valid_spectra.append(spectrum_copy)
            else:
                logger.warning(f"Warning: Skipping empty spectrum '{spectrum['label']}' " f"(x: {len(spectrum['x_scale'])}, y: {len(spectrum['y_scale'])})")
        
        if not valid_spectra:
            logger.debug("No valid spectra for Savitzky-Golay filtering")
            return []
            
        # Apply SG filtering using the manager
        processed_spectra = self.manager.apply_sg_filter(valid_spectra, settings, progress_callback=progress_callback)
        
        return processed_spectra
    
    def update_settings(self, settings):
        """Update settings in the manager."""
        self.manager.update_settings(settings)