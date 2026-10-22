
# src/views/dialogs/visualization/custom_plot_properties_dialog.py
"""Plot Properties (the button below the spectra list, or right-click on the
list): one window for the line colour, style, width and markers of the
selected spectra - a table of what they have now, the settings to give them
(Apply / OK), Reset to defaults, and Line colours... (the colours are used
when Line colours is "own colours")."""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                           QComboBox, QDoubleSpinBox, QDialogButtonBox,
                           QPushButton, QColorDialog, QGroupBox, QHeaderView,
                           QTableWidget, QTableWidgetItem)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon, QPixmap

MARKER_NAMES = {'None': 'None', '.': 'Point (.)', 'o': 'Circle (o)', 's': 'Square (s)',
                '^': 'Triangle Up (^)', 'v': 'Triangle Down (v)', '*': 'Star (*)',
                '+': 'Plus (+)', 'x': 'Cross (x)'}
STYLE_NAMES = {'-': 'solid', '--': 'dashed', ':': 'dotted', '-.': 'dash-dot'}


class CustomPlotPropertiesDialog(QDialog):
    """spectra + manager: the table of their current properties.
    apply_callback(settings): Apply (the window stays open; OK applies too,
    through the controller). reset_callback(): Reset to defaults.
    line_colours_callback(): the Line colours window."""

    def __init__(self, parent=None, current_settings=None, multiple_selection=False,
                 spectra=None, manager=None, apply_callback=None, reset_callback=None,
                 line_colours_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Plot Properties")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.multiple_selection = multiple_selection
        self.spectra = list(spectra or [])
        self.manager = manager
        self.apply_callback = apply_callback
        self.reset_callback = reset_callback
        self.line_colours_callback = line_colours_callback
        
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
        n = len(self.spectra)
        if self.manager is not None and n:
            intro = QLabel(f"The line colour, style and markers of the {n} selected "
                           f"spectr{'um' if n == 1 else 'a'}: what they have now, and below what to "
                           "give them.")
            intro.setWordWrap(True)
            layout.addWidget(intro)
            self.table = QTableWidget(0, 6)
            self.table.setHorizontalHeaderLabels(
                ["Spectrum", "Line colour", "Line style", "Width", "Marker", "Set"])
            self.table.verticalHeader().setVisible(False)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionMode(QTableWidget.NoSelection)
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            for c in range(1, 6):
                self.table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
            self.table.setMinimumHeight(130)
            layout.addWidget(self.table, 1)
            self.refresh_table()
        else:
            self.table = None

        edit_box = QGroupBox("New properties" + (" for all of them" if n > 1 else ""))
        edit_layout = QVBoxLayout(edit_box)
        layout.addWidget(edit_box)
        outer_layout, layout = layout, edit_layout

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
        layout = outer_layout

        note = QHBoxLayout()
        note_label = QLabel("The line colour is used when Line colours is \u201cown colours\u201d "
                            "(it switches to it by itself when you change the colour).")
        note_label.setWordWrap(True)
        note.addWidget(note_label, 1)
        self.line_colours_button = QPushButton("Line colours\u2026")
        self.line_colours_button.setToolTip("Automatic colours, own colours or colours by value")
        self.line_colours_button.clicked.connect(self._line_colours)
        self.line_colours_button.setEnabled(self.line_colours_callback is not None)
        note.addWidget(self.line_colours_button)
        layout.addLayout(note)

        self.status = QLabel("")
        layout.addWidget(self.status)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Apply | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        self.reset_button = QPushButton("Reset to defaults")
        self.reset_button.setToolTip("The selected spectra get the default properties again "
                                     "(blue solid line, width 1, no markers)")
        self.reset_button.clicked.connect(self.reset_defaults)
        buttons.addButton(self.reset_button, QDialogButtonBox.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.apply_button = buttons.button(QDialogButtonBox.Apply)
        self.apply_button.setToolTip("Give the selected spectra these properties (the window "
                                     "stays open)")
        self.apply_button.clicked.connect(self.apply)
        self.apply_button.setEnabled(self.apply_callback is not None)
        self.button_box = buttons
        layout.addWidget(buttons)

    # -- the table of what the spectra have now
    @staticmethod
    def _swatch(colour):
        pix = QPixmap(14, 14)
        try:
            pix.fill(QColor(colour) if colour != 'none' else QColor(0, 0, 0, 0))
        except Exception:
            pix.fill(QColor(0, 0, 0, 0))
        return QIcon(pix)

    def refresh_table(self):
        if self.table is None or self.manager is None:
            return
        from src.modules.utils.spectrum_identity import spectrum_key
        own = getattr(self.manager, 'spectrum_properties', {})
        self.table.setRowCount(len(self.spectra))
        for r, s in enumerate(self.spectra):
            p = self.manager.get_properties(s)
            colour = QTableWidgetItem(str(p['linecolor']))
            colour.setIcon(self._swatch(p['linecolor']))
            cells = [QTableWidgetItem(str(s.get('label', ''))), colour,
                     QTableWidgetItem(STYLE_NAMES.get(p['linestyle'], str(p['linestyle']))),
                     QTableWidgetItem(f"{p['linewidth']:.1f}"),
                     QTableWidgetItem(MARKER_NAMES.get(p['marker'], str(p['marker']))),
                     QTableWidgetItem("own" if spectrum_key(s) in own else "default")]
            for c, item in enumerate(cells):
                self.table.setItem(r, c, item)

    # -- actions
    def apply(self):
        if self.apply_callback is None:
            return False
        self.apply_callback(self.get_settings())
        self.refresh_table()
        self.status.setText("Applied.")
        return True

    def reset_defaults(self):
        self.set_default_values()
        if self.reset_callback is not None:
            self.reset_callback()
            self.refresh_table()
            self.status.setText("The selected spectra have the default properties again.")

    def _line_colours(self):
        if self.line_colours_callback is not None:
            self.line_colours_callback()
    
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
