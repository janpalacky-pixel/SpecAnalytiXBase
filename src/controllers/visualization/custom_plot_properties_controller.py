
# src/controllers/visualization/custom_plot_properties_controller.py
from src.views.plot_only_mode import run_beside_plot  # windows beside the main plot
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
        """Plot Properties: one window with what the selected spectra have now,
        the new properties (Apply keeps the window open, OK applies and
        closes), Reset to defaults and Line colours..."""
        selected_spectra = self._get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(self.controller.view, "Warning", "Please select at least one spectrum.")
            return False

        multiple_selection = len(selected_spectra) > 1
        current_settings = self.manager.get_properties(selected_spectra[0]) if selected_spectra else self.manager.default_properties
        line_colours = getattr(self.controller, 'line_colours_controller', None)

        dialog = CustomPlotPropertiesDialog(
            self.controller.view,
            current_settings,
            multiple_selection,
            spectra=selected_spectra,
            manager=self.manager,
            apply_callback=lambda settings: self.apply_settings(selected_spectra, settings),
            reset_callback=lambda: self.reset_to_defaults(selected_spectra),
            line_colours_callback=line_colours.show_dialog if line_colours is not None else None,
        )
        self.dialog = dialog

        if run_beside_plot(dialog) == QDialog.Accepted:
            self.apply_settings(selected_spectra, dialog.get_settings())
            return True
        return False

    def apply_settings(self, selected_spectra, new_settings):
        """Give the spectra these properties and redraw."""
        colour_changed = any(
            self.manager.get_properties(s).get('linecolor') != new_settings.get('linecolor')
            for s in selected_spectra)
        for spectrum in selected_spectra:
            self.manager.spectrum_properties[spectrum_key(spectrum)] = dict(new_settings)
        # a new colour is seen only with "own colours" (Line colours)
        line_colours = getattr(self.controller, 'line_colours_controller', None)
        if colour_changed and line_colours is not None:
            line_colours.own_colour_set()
        # Update plot immediately after applying new settings
        if self.controller.interactive_mode_checkbox.isChecked():
            self.controller.plot_spectra()

    def reset_to_defaults(self, selected_spectra):
        """The spectra get the default properties again (no question: the
        window shows the result)."""
        for spectrum in selected_spectra:
            self.manager.spectrum_properties.pop(spectrum_key(spectrum), None)
        if self.controller.interactive_mode_checkbox.isChecked():
            self.controller.plot_spectra()

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