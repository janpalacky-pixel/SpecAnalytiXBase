
# src/modules/visualization/custom_plot_properties_manager.py
from PyQt5.QtWidgets import QMessageBox, QMenu
from src.views.dialogs.visualization.plot_properties_table_dialog import PlotPropertiesTableDialog
from src.modules.utils.spectrum_identity import spectrum_key

class CustomPlotPropertiesManager:
    """Manages custom plot properties for individual spectra.

    spectrum_properties is keyed by spectrum_key() (metadata['unique_id'],
    falling back to label only if no id exists) rather than by label —
    see developer_guide_help.py's "Golden Rule: Spectrum Identity". Labels
    are mutable display strings the user can rename at any time; keying
    by label meant a rename silently detached a spectrum from its custom
    color/style. All methods below therefore take spectrum dicts (or
    lists of them), not label strings.
    """
    def __init__(self, main_controller):
        self.controller = main_controller
        self.spectrum_properties = {}
        self.default_properties = {
            'linecolor': 'blue',
            'linestyle': '-',
            'linewidth': 1.0,
            'marker': 'None',
            'markersize': 6.0,
            'markeredgecolor': 'black',
            'markeredgewidth': 1.0,
            'markerfacecolor': 'black',
        }
        
    def show_properties_button_context_menu(self, pos):
        """Show context menu for plot properties button."""
        menu = QMenu()
        reset_action = menu.addAction("Reset")
        action = menu.exec_(pos)
        
        if action == reset_action:
            reply = QMessageBox.question(
                self.controller,
                "Reset Plot Properties",
                "Are you sure you want to reset the plot properties for all spectra to their default values?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.reset_all_properties()
                self.controller.plot_spectra()

    def get_properties(self, spectrum):
        """Get custom properties for a specific spectrum (a spectrum dict)."""
        return self.spectrum_properties.get(spectrum_key(spectrum), self.default_properties.copy())

    def reset_all_properties(self):
        """Reset all plot properties to default values."""
        self.spectrum_properties.clear()

    def reset_selected_properties(self, selected_spectra):
        """Reset plot properties for selected spectra (list of spectrum dicts) to default values."""
        if not selected_spectra:
            QMessageBox.warning(self.controller, "Warning", "Please select at least one spectrum.")
            return False

        reply = QMessageBox.question(
            self.controller,
            "Reset Plot Properties",
            f"Are you sure you want to reset the plot properties for {len(selected_spectra)} selected spectrum/spectra?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Remove only the selected spectra from the properties dictionary
            for spectrum in selected_spectra:
                key = spectrum_key(spectrum)
                if key in self.spectrum_properties:
                    del self.spectrum_properties[key]
            self.controller.plot_spectra()
            return True
        return False

    def show_properties_info(self, selected_spectra):
        """Display plot properties information for selected spectra (list of spectrum dicts)."""
        if not selected_spectra:
            QMessageBox.warning(self.controller, "Warning", "Please select at least one spectrum.")
            return

        if len(selected_spectra) > 1:
            QMessageBox.information(self.controller, "Info", "Please select only one spectrum to view its properties.")
            return

        spectrum = selected_spectra[0]
        spectrum_label = spectrum.get('label', 'Spectrum')
        properties = self.get_properties(spectrum)
        
        # Dictionary to translate marker symbols to user-friendly names
        marker_display_names = {
            'None': 'None',
            '.': 'Point (.)',
            'o': 'Circle (o)',
            's': 'Square (s)',
            '^': 'Triangle Up (^)',
            'v': 'Triangle Down (v)',
            '*': 'Star (*)',
            '+': 'Plus (+)',
            'x': 'Cross (x)'
        }     
        
        # Get the user-friendly marker name
        marker_name = marker_display_names.get(properties['marker'], properties['marker'])        

        # Format the properties information
        info = f"Plot Properties for: {spectrum_label}\n\n"
        info += "Line Properties:\n"
        info += f"• Color: {properties['linecolor']}\n"
        info += f"• Style: {properties['linestyle']}\n"
        info += f"• Width: {properties['linewidth']}\n\n"
        info += "Marker Properties:\n"
        info += f"• Type: {marker_name}\n"
        info += f"• Size: {properties['markersize']}\n"
        info += f"• Edge Color: {properties['markeredgecolor']}\n"
        info += f"• Edge Width: {properties['markeredgewidth']}\n"
        info += f"• Face Color: {properties['markerfacecolor']}\n"
        
        # Add note if using default properties
        if spectrum_key(spectrum) not in self.spectrum_properties:
            info += "\n(Using default properties)"

        QMessageBox.information(self.controller, "Plot Properties Info", info)

    def show_properties_table(self, selected_spectra):
        """Display plot properties for multiple selected spectra (list of spectrum dicts) in a table view."""
        if not selected_spectra:
            QMessageBox.warning(self.controller, "Warning", "Please select at least one spectrum.")
            return

        dialog = PlotPropertiesTableDialog(
            parent=self.controller,
            spectrum_properties_manager=self,
            selected_spectra=selected_spectra
        )
        
        dialog.exec_()        
        
        
        
        