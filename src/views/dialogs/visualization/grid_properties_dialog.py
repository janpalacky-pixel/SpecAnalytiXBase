
# src/views/dialogs/visualization/grid_properties_dialog.py
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, 
                           QDoubleSpinBox, QLabel, QPushButton, QComboBox)

class GridPropertiesDialog(QDialog):
    # Line style choices
    _line_styles = [
        ('-', 'Solid'),
        ('--', 'Dashed'),
        (':', 'Dotted'),
        ('-.', 'Dash-dot')
    ]
    
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("Grid Properties")
        self.setModal(True)
        
        # Initialize default values or use provided settings
        self.settings = settings or {}
        
        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Major Grid Section
        layout.addWidget(QLabel("Major Grid"))
        
        # Major grid visibility
        self.major_visible_cb = QCheckBox("Show Major Grid")
        layout.addWidget(self.major_visible_cb)
        
        # Major grid width
        major_width_layout = QHBoxLayout()
        major_width_layout.addWidget(QLabel("Width:"))
        self.major_width_spin = QDoubleSpinBox()
        self.major_width_spin.setRange(0.1, 5.0)
        self.major_width_spin.setSingleStep(0.1)
        major_width_layout.addWidget(self.major_width_spin)
        layout.addLayout(major_width_layout)
        
        # Major grid style
        major_style_layout = QHBoxLayout()
        major_style_layout.addWidget(QLabel("Style:"))
        self.major_style_combo = QComboBox()
        for style, name in self._line_styles:
            self.major_style_combo.addItem(name, style)
        major_style_layout.addWidget(self.major_style_combo)
        layout.addLayout(major_style_layout)
        
        # Major grid color
        major_color_layout = QHBoxLayout()
        major_color_layout.addWidget(QLabel("Color:"))
        self.major_color_combo = QComboBox()
        self.add_color_options(self.major_color_combo)
        major_color_layout.addWidget(self.major_color_combo)
        layout.addLayout(major_color_layout)
        
        # Minor Grid Section
        layout.addWidget(QLabel("\nMinor Grid"))
        
        # Minor grid visibility
        self.minor_visible_cb = QCheckBox("Show Minor Grid")
        layout.addWidget(self.minor_visible_cb)
        
        # Minor grid width
        minor_width_layout = QHBoxLayout()
        minor_width_layout.addWidget(QLabel("Width:"))
        self.minor_width_spin = QDoubleSpinBox()
        self.minor_width_spin.setRange(0.1, 5.0)
        self.minor_width_spin.setSingleStep(0.1)
        minor_width_layout.addWidget(self.minor_width_spin)
        layout.addLayout(minor_width_layout)
        
        # Minor grid style
        minor_style_layout = QHBoxLayout()
        minor_style_layout.addWidget(QLabel("Style:"))
        self.minor_style_combo = QComboBox()
        for style, name in self._line_styles:
            self.minor_style_combo.addItem(name, style)
        minor_style_layout.addWidget(self.minor_style_combo)
        layout.addLayout(minor_style_layout)
        
        # Minor grid color
        minor_color_layout = QHBoxLayout()
        minor_color_layout.addWidget(QLabel("Color:"))
        self.minor_color_combo = QComboBox()
        self.add_color_options(self.minor_color_combo)
        minor_color_layout.addWidget(self.minor_color_combo)
        layout.addLayout(minor_color_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        reset_button = QPushButton("Reset to Default")
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        button_layout.addWidget(reset_button)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # Connect signals
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        reset_button.clicked.connect(self.reset_to_default)
        
        self.setLayout(layout)

    def add_color_options(self, combo):
        """Add color options to a combo box."""
        colors = [
            ('#000000', 'Black'),
            ('#808080', 'Gray'),
            ('#CCCCCC', 'Light Gray'),
            ('#E5E5E5', 'Very Light Gray')
        ]
        for color_code, color_name in colors:
            combo.addItem(color_name, color_code)
    
    def reset_to_default(self):
        """Reset all settings to default values."""
        self.settings = {
            'major_grid_visible': True,
            'minor_grid_visible': False,
            'major_grid_width': 0.8,
            'minor_grid_width': 0.5,
            'major_grid_color': '#CCCCCC',
            'minor_grid_color': '#E5E5E5',
            'major_grid_style': '-',
            'minor_grid_style': ':'
        }
        self.load_settings()
        
    def load_settings(self):
        """Load current settings into the UI."""
        # Major grid settings
        self.major_visible_cb.setChecked(self.settings.get('major_grid_visible', True))
        self.major_width_spin.setValue(self.settings.get('major_grid_width', 0.8))
        
        # Set major grid style
        major_style = self.settings.get('major_grid_style', '-')
        major_style_index = next((i for i, (style, _) in enumerate(self._line_styles) 
                               if style == major_style), 0)
        self.major_style_combo.setCurrentIndex(major_style_index)
        
        # Set major grid color
        major_color = self.settings.get('major_grid_color', '#CCCCCC')
        major_color_index = self.major_color_combo.findData(major_color)
        if major_color_index >= 0:
            self.major_color_combo.setCurrentIndex(major_color_index)
        
        # Minor grid settings
        self.minor_visible_cb.setChecked(self.settings.get('minor_grid_visible', False))
        self.minor_width_spin.setValue(self.settings.get('minor_grid_width', 0.5))
        
        # Set minor grid style
        minor_style = self.settings.get('minor_grid_style', ':')
        minor_style_index = next((i for i, (style, _) in enumerate(self._line_styles) 
                               if style == minor_style), 0)
        self.minor_style_combo.setCurrentIndex(minor_style_index)
        
        # Set minor grid color
        minor_color = self.settings.get('minor_grid_color', '#E5E5E5')
        minor_color_index = self.minor_color_combo.findData(minor_color)
        if minor_color_index >= 0:
            self.minor_color_combo.setCurrentIndex(minor_color_index)
        
    def get_settings(self):
        """Get the current settings from the dialog."""
        return {
            'major_grid_visible': self.major_visible_cb.isChecked(),
            'minor_grid_visible': self.minor_visible_cb.isChecked(),
            'major_grid_width': self.major_width_spin.value(),
            'minor_grid_width': self.minor_width_spin.value(),
            'major_grid_color': self.major_color_combo.currentData(),
            'minor_grid_color': self.minor_color_combo.currentData(),
            'major_grid_style': self.major_style_combo.currentData(),
            'minor_grid_style': self.minor_style_combo.currentData()
        }