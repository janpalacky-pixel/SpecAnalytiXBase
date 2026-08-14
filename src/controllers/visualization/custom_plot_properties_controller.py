
# src/controllers/visualization/custom_plot_properties_controller.py
from PyQt5.QtWidgets import QMessageBox, QDialog
from PyQt5.QtCore import Qt
from src.views.dialogs.visualization.custom_plot_properties_dialog import CustomPlotPropertiesDialog
from src.modules.utils.spectrum_identity import spectrum_key

class CustomPlotPropertiesController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = self.controller.custom_plot_properties_manager

    def _get_selected_spectra(self):
        """Resolve the list widget's current selection to actual spectrum
        dicts by identity (Qt.UserRole unique_id), not by label text —
        see CustomPlotPropertiesManager's class docstring."""
        selected_ids = {
            item.data(Qt.UserRole) for item in self.controller.spectra_list_widget.selectedItems()
        }
        return [
            spectrum for spectrum in self.controller.original_spectra
            if spectrum_key(spectrum) in selected_ids
        ]

    def show_dialog(self):
        """Show the custom plot properties dialog for selected spectra."""
        selected_spectra = self._get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(self.controller.view, "Warning", "Please select at least one spectrum.")
            return False

        multiple_selection = len(selected_spectra) > 1
        current_settings = self.manager.get_properties(selected_spectra[0]) if selected_spectra else self.manager.default_properties

        dialog = CustomPlotPropertiesDialog(
            self.controller.view,
            current_settings,
            multiple_selection
        )

        if dialog.exec_() == QDialog.Accepted:
            new_settings = dialog.get_settings()
            for spectrum in selected_spectra:
                self.manager.spectrum_properties[spectrum_key(spectrum)] = new_settings.copy()

            # Update plot immediately after applying new settings
            if self.controller.interactive_mode_checkbox.isChecked():
                self.controller.plot_spectra()
            return True
        return False

    def show_properties_info(self, selected_spectra):
        """Display plot properties information for selected spectra (list of spectrum dicts)."""
        self.manager.show_properties_info(selected_spectra)

    def reset_selected_properties(self, selected_spectra):
        """Reset plot properties for selected spectra (list of spectrum dicts) to default values."""
        return self.manager.reset_selected_properties(selected_spectra)
        
    def reset_all_properties(self):
        """Reset all plot properties to default values."""
        self.manager.reset_all_properties()
        self.controller.plot_spectra()
        
    def show_context_menu(self, pos):
        """Show context menu for plot properties button."""
        self.manager.show_properties_button_context_menu(pos)