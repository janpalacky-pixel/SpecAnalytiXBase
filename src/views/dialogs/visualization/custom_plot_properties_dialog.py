
# src/views/dialogs/visualization/custom_plot_properties_dialog.py
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                           QComboBox, QDoubleSpinBox, QDialogButtonBox, 
                           QPushButton, QColorDialog)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

class CustomPlotPropertiesDialog(QDialog):
    def __init__(self, parent=None, current_settings=None, multiple_selection=False):
        super().__init__(parent)
        self.setWindowTitle("Custom Plot Properties")
        self.multiple_selection = multiple_selection
        
        # Define default settings
        self.default_settings = {
            'linecolor': 'blue',
            'linestyle': '-',
            'linewidth': 1.0,
            'marker': 'None',
            'markersize': 6.0,
            'markeredgecolor': 'black',
            'markeredgewidth': 1.0,
            'markerfacecolor': 'black',
        }    
        
        # Extended color list
        self.standard_colors = [
            'blue', 'red', 'green', 'yellow', 'orange', 'purple', 'black',
            'cyan', 'magenta', 'brown', 'pink', 'gray', 'olive', 'navy',
            'teal', 'maroon', 'lime', 'indigo', 'violet', 'crimson'
        ]
        
        # Use provided settings or defaults
        self.current_settings = current_settings or self.default_settings.copy()
        
        # Color dialog instance
        self.color_dialog = QColorDialog(self)
        self.color_dialog.setOption(QColorDialog.DontUseNativeDialog)
        self.color_dialog.setWindowTitle("Select Color")
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Line properties
        line_group = QVBoxLayout()
        
        # Line color with button
        line_color_layout = QHBoxLayout()
        line_color_layout.addWidget(QLabel("Line Color:"))
        self.line_color_combo = QComboBox()
        self.line_color_combo.addItems(self.standard_colors)
        self.line_color_combo.setCurrentText(self.current_settings['linecolor'])
        line_color_layout.addWidget(self.line_color_combo)
        
        self.line_color_button = QPushButton("Custom...")
        self.line_color_button.clicked.connect(lambda: self.pick_color(self.line_color_combo))
        line_color_layout.addWidget(self.line_color_button)
        line_group.addLayout(line_color_layout)
        
        # Line style
        line_style_layout = QHBoxLayout()
        line_style_layout.addWidget(QLabel("Line Style:"))
        self.line_style_combo = QComboBox()
        self.line_style_combo.addItems(['-', '--', ':', '-.'])
        self.line_style_combo.setCurrentText(self.current_settings['linestyle'])
        line_style_layout.addWidget(self.line_style_combo)
        line_group.addLayout(line_style_layout)
        
        # Line width
        line_width_layout = QHBoxLayout()
        line_width_layout.addWidget(QLabel("Line Width:"))
        self.line_width_spin = QDoubleSpinBox()
        self.line_width_spin.setRange(0.1, 10.0)
        self.line_width_spin.setSingleStep(0.1)
        self.line_width_spin.setValue(self.current_settings['linewidth'])
        line_width_layout.addWidget(self.line_width_spin)
        line_group.addLayout(line_width_layout)
        
        # Marker properties
        marker_group = QVBoxLayout()
        
        # Marker style
        marker_style_layout = QHBoxLayout()
        marker_style_layout.addWidget(QLabel("Marker:"))
        self.marker_combo = QComboBox()
        
       # Define user-friendly marker options with their corresponding matplotlib symbols
        marker_options = [
            ('None', 'None'),
            ('Point (.)', '.'),
            ('Circle (o)', 'o'),
            ('Square (s)', 's'),
            ('Triangle Up (^)', '^'),
            ('Triangle Down (v)', 'v'),
            ('Star (*)', '*'),
            ('Plus (+)', '+'),
            ('Cross (x)', 'x')
        ]        
        
        # Store the mapping for later reference
        self.marker_display_to_value = {display: value for display, value in marker_options}
        self.marker_value_to_display = {value: display for display, value in marker_options}     
        
        # Add the user-friendly options to the combo box
        for display, _ in marker_options:
            self.marker_combo.addItem(display)

        # Set current value based on settings
        current_marker = self.current_settings['marker']
        if current_marker in self.marker_value_to_display:
            self.marker_combo.setCurrentText(self.marker_value_to_display[current_marker])        

        marker_style_layout.addWidget(self.marker_combo)
        marker_group.addLayout(marker_style_layout)
        
        # Marker size
        marker_size_layout = QHBoxLayout()
        marker_size_layout.addWidget(QLabel("Marker Size:"))
        self.marker_size_spin = QDoubleSpinBox()
        self.marker_size_spin.setRange(1.0, 20.0)
        self.marker_size_spin.setSingleStep(0.5)
        self.marker_size_spin.setValue(self.current_settings['markersize'])
        marker_size_layout.addWidget(self.marker_size_spin)
        marker_group.addLayout(marker_size_layout)
        
        # Edge color with button
        edge_color_layout = QHBoxLayout()
        edge_color_layout.addWidget(QLabel("Edge Color:"))
        self.edge_color_combo = QComboBox()
        self.edge_color_combo.addItems(self.standard_colors + ['none'])
        self.edge_color_combo.setCurrentText(self.current_settings['markeredgecolor'])
        edge_color_layout.addWidget(self.edge_color_combo)
        
        self.edge_color_button = QPushButton("Custom...")
        self.edge_color_button.clicked.connect(lambda: self.pick_color(self.edge_color_combo))
        edge_color_layout.addWidget(self.edge_color_button)
        marker_group.addLayout(edge_color_layout)
        
        # Face color with button
        face_color_layout = QHBoxLayout()
        face_color_layout.addWidget(QLabel("Face Color:"))
        self.face_color_combo = QComboBox()
        self.face_color_combo.addItems(self.standard_colors + ['none'])
        self.face_color_combo.setCurrentText(self.current_settings['markerfacecolor'])
        face_color_layout.addWidget(self.face_color_combo)
        
        self.face_color_button = QPushButton("Custom...")
        self.face_color_button.clicked.connect(lambda: self.pick_color(self.face_color_combo))
        face_color_layout.addWidget(self.face_color_button)
        marker_group.addLayout(face_color_layout)
        
        # Edge width
        edge_width_layout = QHBoxLayout()
        edge_width_layout.addWidget(QLabel("Edge Width:"))
        self.edge_width_spin = QDoubleSpinBox()
        self.edge_width_spin.setRange(0.1, 5.0)
        self.edge_width_spin.setSingleStep(0.1)
        self.edge_width_spin.setValue(self.current_settings['markeredgewidth'])
        edge_width_layout.addWidget(self.edge_width_spin)
        marker_group.addLayout(edge_width_layout)

        # Add groups to main layout
        layout.addLayout(line_group)
        layout.addLayout(marker_group)
        
        # Add Set Default button
        default_button = QPushButton("Set Default")
        default_button.clicked.connect(self.set_default_values)
        layout.addWidget(default_button)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def pick_color(self, combo_box):
        """Handle color picking with a dedicated button."""
        current_color = combo_box.currentText()
        if current_color != 'none':
            self.color_dialog.setCurrentColor(QColor(current_color))
        
        if self.color_dialog.exec_() == QColorDialog.Accepted:
            color = self.color_dialog.selectedColor()
            hex_color = color.name()
            
            # Add the color to the combo box if it's not already there
            if combo_box.findText(hex_color) == -1:
                combo_box.insertItem(0, hex_color)
            combo_box.setCurrentText(hex_color)
    
    def set_default_values(self):
        """Reset all values to defaults."""
        self.line_color_combo.setCurrentText(self.default_settings['linecolor'])
        self.line_style_combo.setCurrentText(self.default_settings['linestyle'])
        self.line_width_spin.setValue(self.default_settings['linewidth'])
        self.marker_combo.setCurrentText(self.default_settings['marker'])

        # Set the marker using the display text
        default_marker = self.default_settings['marker']
        if default_marker in self.marker_value_to_display:
            self.marker_combo.setCurrentText(self.marker_value_to_display[default_marker])        
        
        self.marker_size_spin.setValue(self.default_settings['markersize'])
        self.edge_color_combo.setCurrentText(self.default_settings['markeredgecolor'])
        self.edge_width_spin.setValue(self.default_settings['markeredgewidth'])
        self.face_color_combo.setCurrentText(self.default_settings['markerfacecolor'])
    
    def get_settings(self):
        """Return the current custom plot property settings."""
        
        display_text = self.marker_combo.currentText()
        marker_value = self.marker_display_to_value.get(display_text, 'None')        
        
        return {
            'linecolor': self.line_color_combo.currentText(),
            'linestyle': self.line_style_combo.currentText(),
            'linewidth': self.line_width_spin.value(),
            'marker': marker_value,  # Use the matplotlib symbol value
            'markersize': self.marker_size_spin.value(),
            'markeredgecolor': self.edge_color_combo.currentText(),
            'markeredgewidth': self.edge_width_spin.value(),
            'markerfacecolor': self.face_color_combo.currentText(),
        }
