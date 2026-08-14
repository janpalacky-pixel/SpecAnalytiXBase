
# src/views/dialogs/visualization/legend_properties_dialog.py
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, 
                           QSpinBox, QLabel, QPushButton, QFontComboBox, QComboBox)
from PyQt5.QtGui import QFont

class LegendPropertiesDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("Legend Properties")
        self.setModal(True)
        
        # Initialize default values or use provided settings
        self.settings = settings or {}
        
        # Define available legend positions
        self.legend_positions = [
            'upper right',
            'upper left',
            'lower left',
            'lower right',
            'right',
            'center left',
            'center right',
            'lower center',
            'upper center',
            'center'
        ]        

        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Visibility checkbox
        self.visible_cb = QCheckBox("Show Legend")
        layout.addWidget(self.visible_cb)
        
        # Position selection
        position_layout = QHBoxLayout()
        position_layout.addWidget(QLabel("Position:"))
        self.position_combo = QComboBox()
        self.position_combo.addItems(self.legend_positions)
        position_layout.addWidget(self.position_combo)
        layout.addLayout(position_layout)        
        
        # Movable checkbox
        self.movable_cb = QCheckBox("Movable Legend")
        layout.addWidget(self.movable_cb)
        
        # Font settings
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Font:"))
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont('Arial'))
        font_layout.addWidget(self.font_combo)
        
        font_size_layout = QHBoxLayout()
        font_size_layout.addWidget(QLabel("Font Size:"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 72)
        font_size_layout.addWidget(self.font_size_spin)
        
        layout.addLayout(font_layout)
        layout.addLayout(font_size_layout)
        
        # Maximum items settings
        self.show_all_cb = QCheckBox("Show All Legend Items")
        layout.addWidget(self.show_all_cb)
        
        max_items_layout = QHBoxLayout()
        max_items_layout.addWidget(QLabel("Maximum Legend Items:"))
        self.max_items_spin = QSpinBox()
        self.max_items_spin.setRange(1, 100)
        max_items_layout.addWidget(self.max_items_spin)
        layout.addLayout(max_items_layout)
        
        # Legend columns setting
        columns_layout = QHBoxLayout()
        columns_layout.addWidget(QLabel("Number of Columns:"))
        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(1, 10)  # Adjust the range of columns as needed
        columns_layout.addWidget(self.columns_spin)
        layout.addLayout(columns_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        reset_button = QPushButton("Reset to Default")  # New reset button
        
        # Add all buttons to the layout
        button_layout.addWidget(reset_button)  # Add reset button first
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # Connect signals
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        reset_button.clicked.connect(self.reset_to_default)  # Connect reset button
        self.show_all_cb.stateChanged.connect(self.toggle_max_items)
                
        self.setLayout(layout)

    def reset_to_default(self):
        """Reset all settings to default values."""
        # Tell the parent (controller) to reset settings
        self.settings = {
            'movable': True,
            'max_items': 20,
            'show_all_items': False,
            'font_size': 10,
            'font_family': 'Arial',
            'visible': False,
            'position': 'upper right',
            'outside_plot': False,
            'use_pagination': False,
            'columns': 1,
        }
        self.load_settings()   

    def toggle_max_items(self, state):
        """Enable/disable max items spinbox based on 'Show All' checkbox."""
        self.max_items_spin.setEnabled(not bool(state))

    def load_settings(self):
        """Load current settings into the UI."""
        self.visible_cb.setChecked(self.settings.get('visible', False))
        self.movable_cb.setChecked(self.settings.get('movable', True))
        self.show_all_cb.setChecked(self.settings.get('show_all_items', False))
        self.max_items_spin.setValue(self.settings.get('max_items', 20))
        self.max_items_spin.setEnabled(not self.settings.get('show_all_items', False))
        self.font_size_spin.setValue(self.settings.get('font_size', 10))
        self.font_combo.setCurrentFont(QFont(self.settings.get('font_family', 'Arial')))
        self.position_combo.setCurrentText(self.settings.get('position', 'upper right'))
        self.columns_spin.setValue(self.settings.get('columns', 1))
        
    def get_settings(self):
        """Get the current settings from the dialog."""
        return {
            'visible': self.visible_cb.isChecked(),
            'movable': self.movable_cb.isChecked(),
            'max_items': self.max_items_spin.value(),
            'show_all_items': self.show_all_cb.isChecked(),
            'font_size': self.font_size_spin.value(),
            'font_family': self.font_combo.currentFont().family(),
            'position': self.position_combo.currentText(),
            'columns': self.columns_spin.value(),
            # Preserving other settings that might not be in the UI
            'outside_plot': self.settings.get('outside_plot', False),
            'use_pagination': self.settings.get('use_pagination', False),
        }
