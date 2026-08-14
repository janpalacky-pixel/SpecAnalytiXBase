
# src/views/dialogs/visualization/plot_properties_table_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QPushButton, QHBoxLayout)
from PyQt5.QtCore import Qt

class PlotPropertiesTableDialog(QDialog):
    """Dialog to display plot properties for multiple spectra in a table view."""
    
    def __init__(self, parent=None, spectrum_properties_manager=None, selected_spectra=None):
        super().__init__(parent)
        self.setWindowTitle("Plot Properties for Selected Spectra")
        self.setMinimumSize(600, 400)

        self.manager = spectrum_properties_manager
        # List of spectrum dicts, not labels — see
        # CustomPlotPropertiesManager's class docstring for why identity
        # (spectrum_key) rather than label text is used to look up and
        # store properties.
        self.selected_spectra = selected_spectra or []
        
        self.setup_ui()
        self.populate_table()
        
    def setup_ui(self):
        """Set up the dialog UI with a table and buttons."""
        layout = QVBoxLayout(self)
        
        # Create the table widget
        self.table = QTableWidget()
        self.table.setColumnCount(9)  # Number of property columns plus spectrum name
        self.table.setHorizontalHeaderLabels([
            "Spectrum", "Line Color", "Line Style", "Line Width", 
            "Marker", "Marker Size", "Edge Color", "Edge Width", "Face Color"
        ])
        
        # Set table properties
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        
        # Connect double-click signal
        self.table.itemDoubleClicked.connect(self.show_detailed_properties)
        
        layout.addWidget(self.table)
        
        # Buttons layout
        button_layout = QHBoxLayout()
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        
        self.details_button = QPushButton("Show Details")
        self.details_button.clicked.connect(self.show_selected_details)
        
        button_layout.addWidget(self.details_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
    
# Update the populate_table method in PlotPropertiesTableDialog class

    def populate_table(self):
        """Fill the table with data from selected spectra."""
        if not self.selected_spectra:
            return

        # Set row count based on number of selected spectra
        self.table.setRowCount(len(self.selected_spectra))

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
        
        # For each selected spectrum
        for row, spectrum in enumerate(self.selected_spectra):
            properties = self.manager.get_properties(spectrum)
            label = spectrum.get('label', 'Spectrum')

            # Spectrum name (first column) — the spectrum dict itself is
            # stashed as Qt.UserRole data so double-click / Show Details
            # can look properties back up by identity, not by re-parsing
            # this (possibly ambiguous, if two spectra share a label)
            # display text.
            name_item = QTableWidgetItem(label)
            name_item.setData(Qt.UserRole, spectrum)
            self.table.setItem(row, 0, name_item)
            
            # Line properties
            self.table.setItem(row, 1, QTableWidgetItem(properties['linecolor']))
            self.table.setItem(row, 2, QTableWidgetItem(properties['linestyle']))
            
            # Format floating point values to avoid precision issues
            line_width = '{:.1f}'.format(properties['linewidth'])
            self.table.setItem(row, 3, QTableWidgetItem(line_width))
            
            # Marker properties
            marker_name = marker_display_names.get(properties['marker'], properties['marker'])
            self.table.setItem(row, 4, QTableWidgetItem(marker_name))
            
            marker_size = '{:.1f}'.format(properties['markersize'])
            self.table.setItem(row, 5, QTableWidgetItem(marker_size))
            
            self.table.setItem(row, 6, QTableWidgetItem(properties['markeredgecolor']))
            
            edge_width = '{:.1f}'.format(properties['markeredgewidth'])
            self.table.setItem(row, 7, QTableWidgetItem(edge_width))
            
            self.table.setItem(row, 8, QTableWidgetItem(properties['markerfacecolor']))
    
    def show_selected_details(self):
        """Show detailed properties for the currently selected row."""
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            selected_row = selected_rows[0].row()
            spectrum = self.table.item(selected_row, 0).data(Qt.UserRole)
            self.show_detailed_properties_for_spectrum(spectrum)

    def show_detailed_properties(self, item):
        """Show detailed properties when a cell is double-clicked."""
        row = item.row()
        spectrum = self.table.item(row, 0).data(Qt.UserRole)
        self.show_detailed_properties_for_spectrum(spectrum)

    def show_detailed_properties_for_spectrum(self, spectrum):
        """Display detailed properties for a specific spectrum dict."""
        # Use the existing show_properties_info method
        self.manager.show_properties_info([spectrum])