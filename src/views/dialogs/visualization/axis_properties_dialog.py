
# src/views/dialogs/visualization/axis_properties_dialog.py
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, 
                           QSpinBox, QLabel, QPushButton, QFontComboBox, QLineEdit,
                           QGroupBox, QFormLayout)
from PyQt5.QtGui import QFont

class AxisPropertiesDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("Axis Properties")
        self.setModal(True)
        
        # Initialize settings
        self.settings = settings or {}
        
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        layout = QVBoxLayout()
        
        # X-Axis Group
        x_axis_group = QGroupBox("X-Axis")
        x_axis_layout = QFormLayout()
        
        # X-Axis Label
        self.x_label_edit = QLineEdit()
        x_axis_layout.addRow("Label:", self.x_label_edit)
        
        # X-Axis Label Font
        self.x_label_font_combo = QFontComboBox()
        x_axis_layout.addRow("Label Font:", self.x_label_font_combo)
        
        # X-Axis Label Font Size
        self.x_label_font_size = QSpinBox()
        self.x_label_font_size.setRange(6, 72)
        x_axis_layout.addRow("Label Font Size:", self.x_label_font_size)
        
        # X-Axis Tick Font
        self.x_tick_font_combo = QFontComboBox()
        x_axis_layout.addRow("Tick Font:", self.x_tick_font_combo)
        
        # X-Axis Tick Font Size
        self.x_tick_font_size = QSpinBox()
        self.x_tick_font_size.setRange(6, 72)
        x_axis_layout.addRow("Tick Font Size:", self.x_tick_font_size)
        
        x_axis_group.setLayout(x_axis_layout)
        layout.addWidget(x_axis_group)
        
        # Y-Axis Group
        y_axis_group = QGroupBox("Y-Axis")
        y_axis_layout = QFormLayout()
        
        # Y-Axis Label
        self.y_label_edit = QLineEdit()
        y_axis_layout.addRow("Label:", self.y_label_edit)
        
        # Y-Axis Label Font
        self.y_label_font_combo = QFontComboBox()
        y_axis_layout.addRow("Label Font:", self.y_label_font_combo)
        
        # Y-Axis Label Font Size
        self.y_label_font_size = QSpinBox()
        self.y_label_font_size.setRange(6, 72)
        y_axis_layout.addRow("Label Font Size:", self.y_label_font_size)
        
        # Y-Axis Tick Font
        self.y_tick_font_combo = QFontComboBox()
        y_axis_layout.addRow("Tick Font:", self.y_tick_font_combo)
        
        # Y-Axis Tick Font Size
        self.y_tick_font_size = QSpinBox()
        self.y_tick_font_size.setRange(6, 72)
        y_axis_layout.addRow("Tick Font Size:", self.y_tick_font_size)
        
        y_axis_group.setLayout(y_axis_layout)
        layout.addWidget(y_axis_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        reset_button = QPushButton("Reset to Default")
        
        button_layout.addWidget(reset_button)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # Connect signals
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        reset_button.clicked.connect(self.reset_to_default)
        
        self.setLayout(layout)

    def reset_to_default(self):
        """Reset all settings to default values."""
        self.settings = {
            'x_label': 'X-axis',
            'y_label': 'Y-axis',
            'x_label_font_family': 'Arial',
            'y_label_font_family': 'Arial',
            'x_label_font_size': 12,
            'y_label_font_size': 12,
            'x_tick_font_family': 'Arial',
            'y_tick_font_family': 'Arial',
            'x_tick_font_size': 10,
            'y_tick_font_size': 10,
        }
        self.load_settings()

    def load_settings(self):
        """Load current settings into the UI."""
        # X-Axis settings
        self.x_label_edit.setText(self.settings.get('x_label', 'X-axis'))
        self.x_label_font_combo.setCurrentFont(QFont(self.settings.get('x_label_font_family', 'Arial')))
        self.x_label_font_size.setValue(self.settings.get('x_label_font_size', 12))
        self.x_tick_font_combo.setCurrentFont(QFont(self.settings.get('x_tick_font_family', 'Arial')))
        self.x_tick_font_size.setValue(self.settings.get('x_tick_font_size', 10))
        
        # Y-Axis settings
        self.y_label_edit.setText(self.settings.get('y_label', 'Y-axis'))
        self.y_label_font_combo.setCurrentFont(QFont(self.settings.get('y_label_font_family', 'Arial')))
        self.y_label_font_size.setValue(self.settings.get('y_label_font_size', 12))
        self.y_tick_font_combo.setCurrentFont(QFont(self.settings.get('y_tick_font_family', 'Arial')))
        self.y_tick_font_size.setValue(self.settings.get('y_tick_font_size', 10))

    def get_settings(self):
        """Get the current settings from the dialog."""
        return {
            'x_label': self.x_label_edit.text(),
            'y_label': self.y_label_edit.text(),
            'x_label_font_family': self.x_label_font_combo.currentFont().family(),
            'y_label_font_family': self.y_label_font_combo.currentFont().family(),
            'x_label_font_size': self.x_label_font_size.value(),
            'y_label_font_size': self.y_label_font_size.value(),
            'x_tick_font_family': self.x_tick_font_combo.currentFont().family(),
            'y_tick_font_family': self.y_tick_font_combo.currentFont().family(),
            'x_tick_font_size': self.x_tick_font_size.value(),
            'y_tick_font_size': self.y_tick_font_size.value(),
        }