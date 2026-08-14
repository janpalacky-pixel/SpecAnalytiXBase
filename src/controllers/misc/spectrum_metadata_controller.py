
# src/controllers/misc/spectrum_metadata_controller.py

from PyQt5.QtWidgets import QMessageBox
from src.views.dialogs.misc.spectrum_metadata_dialog import SpectrumMetadataDialog
from src.views.dialogs.misc.spectrum_metadata_table_dialog import SpectrumMetadataTableDialog
from src.modules.misc.spectrum_metadata_manager import SpectrumMetadataManager

class SpectrumMetadataController:
    """Controller for handling spectrum metadata display operations."""
    
    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = SpectrumMetadataManager(main_controller)
    
    def show_metadata(self, selected_indices=None):
        """
        Show metadata for selected spectra.
        
        Args:
            selected_indices (list): Row indices (position in
                self.controller.original_spectra) of the spectra to show.
                If None, use currently selected items in the list widget.
                Was previously a list of LABEL strings — changed to
                indices because two spectra sharing a label (a real,
                reachable case elsewhere in this app) made the old
                label-based lookup silently merge both spectra's
                metadata together when only one was actually selected.
                See SpectrumMetadataManager.get_selected_spectra().
        """
        if selected_indices is None:
            selected_items = self.controller.spectra_list_widget.selectedItems()
            if not selected_items:
                QMessageBox.warning(self.controller.view, "Warning", 
                                   "Please select at least one spectrum.")
                return
            
            selected_indices = [
                self.controller.spectra_list_widget.row(item)
                for item in selected_items
            ]
        
        if not selected_indices:
            QMessageBox.warning(self.controller.view, "Warning", 
                               "Please select at least one spectrum.")
            return
        
        # Get spectrum data for the selected indices
        selected_spectra = self.manager.get_selected_spectra(selected_indices)
        
        if len(selected_spectra) == 1:
            # For a single spectrum, show detailed metadata dialog
            spectrum = selected_spectra[0]
            dialog = SpectrumMetadataDialog(
                parent=self.controller.view,
                spectrum_label=spectrum['label'],
                metadata=spectrum['metadata']
            )
            dialog.exec_()
        else:
            # For multiple spectra, show table dialog
            dialog = SpectrumMetadataTableDialog(
                parent=self.controller.view,
                spectra_data=selected_spectra
            )
            dialog.exec_()