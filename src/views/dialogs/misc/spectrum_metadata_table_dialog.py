
# src/views/dialogs/misc/spectrum_metadata_table_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
                            QHeaderView, QPushButton, QHBoxLayout)
# from PyQt5.QtCore import Qt
from src.views.dialogs.misc.spectrum_metadata_dialog import SpectrumMetadataDialog

class SpectrumMetadataTableDialog(QDialog):
    """Dialog to display a table of spectra with the ability to view detailed metadata."""
    
    def __init__(self, parent=None, spectra_data=None):
        super().__init__(parent)
        self.setWindowTitle("Spectrum Metadata Selection")
        self.setMinimumSize(600, 400)
        
        self.spectra_data = spectra_data or []
        
        self.setup_ui()
        self.populate_table()
        
    def setup_ui(self):
        """Set up the dialog UI with a table and buttons."""
        layout = QVBoxLayout(self)
        
        # Create the table widget
        self.table = QTableWidget()
        self.table.setColumnCount(2)  # Spectrum name and file path
        self.table.setHorizontalHeaderLabels(["Spectrum", "File Path"])
        
        # Set table properties
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        
        # Connect double-click signal
        self.table.itemDoubleClicked.connect(self.show_detailed_metadata)
        
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
    
    def populate_table(self):
        """Fill the table with data from selected spectra."""
        if not self.spectra_data:
            return
            
        # Set row count based on number of selected spectra
        self.table.setRowCount(len(self.spectra_data))
        
        # For each selected spectrum
        for row, spectrum in enumerate(self.spectra_data):
            # Spectrum name (first column)
            self.table.setItem(row, 0, QTableWidgetItem(spectrum['label']))
            
            # File path if available (second column)
            file_path = spectrum['metadata'].get('file_path', 'N/A')
            self.table.setItem(row, 1, QTableWidgetItem(file_path))
    
    def show_selected_details(self):
        """Show detailed metadata for the currently selected row."""
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            selected_row = selected_rows[0].row()
            spectrum = self.spectra_data[selected_row]
            self.show_spectrum_metadata(spectrum)
    
    def show_detailed_metadata(self, item):
        """Show detailed metadata when a cell is double-clicked."""
        row = item.row()
        spectrum = self.spectra_data[row]
        self.show_spectrum_metadata(spectrum)
    
    def show_spectrum_metadata(self, spectrum):
        """Display detailed metadata for a specific spectrum."""
        dialog = SpectrumMetadataDialog(
            parent=self,
            spectrum_label=spectrum['label'],
            metadata=spectrum['metadata']
        )
        dialog.exec_()