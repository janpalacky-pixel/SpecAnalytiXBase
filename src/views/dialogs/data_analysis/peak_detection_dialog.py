# src/views/dialogs/data_analysis/peak_detection_dialog.py
"""Right-click on the plot -> Detect Peaks: the settings of the peaks marked
on the plot. Apply marks them with the settings shown (the window stays
open); Close closes it. Reset to defaults, the orange "?" (what each setting
means) and Peak list… (every peak in a table, with these settings)."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                             QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout)

from src.modules.data_analysis import peak_list as pl
from src.views import icons
from src.views.dialogs.data_analysis.peak_settings_help import tooltip_of

# Everything as when nothing was changed (Reset to defaults)
DEFAULTS = {
    'threshold': pl.DEFAULTS['threshold'],
    'prominence': pl.DEFAULTS['prominence'],
    'distance': pl.DEFAULTS['distance'],
    'peak_mode': pl.DEFAULTS['mode'],
    'font_size': 10,
    'rotation': 0,
    'decimals': 2,
    'number_format': 'fixed',
    'format_type': 'x_only',
    'labels': 'band',
}
# Which peaks get their number written (see peak_settings_help.LABEL_HELP)
LABEL_MODES = [('band', "Once per band (above the highest peak)"), ('all', "On every peak"),
               ('current', "Only the current spectrum"), ('none', "None (dots only)")]
_FORMATS = ["fixed", "sci", "general", "mixed"]


class PeakDetectionDialog(QDialog):

    def __init__(self, parent=None, threshold=0.0, font_size=10, rotation=0, decimals=2,
                 format_type="x_only", number_format="fixed", show_labels=True, prominence=0.1,
                 distance=0.05, peak_mode="Positive", apply_callback=None, labels='band'):
        super().__init__(parent)
        self.setWindowTitle("Peak Detection Settings")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.apply_callback = apply_callback
        self.setup_ui(threshold, font_size, rotation, decimals, format_type, number_format,
                      show_labels, prominence, distance, peak_mode)
        self.labels_combo.setCurrentIndex(max(self.labels_combo.findData(labels), 0))

    def setup_ui(self, threshold, font_size, rotation, decimals, format_type, number_format,
                 show_labels, prominence, distance, peak_mode):
        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        intro = QLabel("Marks the peaks of the plotted spectra. Apply shows the result on the plot; "
                       "the window stays open.")
        intro.setWordWrap(True)
        top.addWidget(intro, 1)
        self.help_button = icons.help_button("What each setting means")
        self.help_button.clicked.connect(self.show_settings_help)
        top.addWidget(self.help_button, 0, Qt.AlignTop)
        outer.addLayout(top)

        layout = QFormLayout()
        self.threshold_input = QDoubleSpinBox(self)
        self.threshold_input.setRange(0.0, 1)
        self.threshold_input.setDecimals(4)
        self.threshold_input.setSingleStep(0.001)
        self.threshold_input.setValue(threshold)
        self.threshold_input.setToolTip(tooltip_of("Threshold (height)"))
        layout.addRow("Peak Detection Threshold:", self.threshold_input)

        self.prominence_input = QDoubleSpinBox(self)
        self.prominence_input.setRange(0.0, 1.0)
        self.prominence_input.setDecimals(4)
        self.prominence_input.setSingleStep(0.01)
        self.prominence_input.setValue(prominence)
        self.prominence_input.setToolTip(tooltip_of("Prominence"))
        layout.addRow("Prominence Threshold (Relative):", self.prominence_input)

        self.distance_input = QDoubleSpinBox(self)
        self.distance_input.setRange(0.0, 1.0)
        self.distance_input.setDecimals(4)
        self.distance_input.setSingleStep(0.01)
        self.distance_input.setValue(distance)
        self.distance_input.setToolTip(tooltip_of("Distance"))
        layout.addRow("Distance Threshold (Relative):", self.distance_input)

        self.peak_mode_combo = QComboBox(self)
        self.peak_mode_combo.addItems(["Positive", "Negative", "Both"])
        self.peak_mode_combo.setCurrentText(peak_mode)
        self.peak_mode_combo.setToolTip(tooltip_of("Peaks (mode)"))
        layout.addRow("Peak Detection Mode:", self.peak_mode_combo)

        self.labels_combo = QComboBox(self)
        for key, text in LABEL_MODES:
            self.labels_combo.addItem(text, key)
        self.labels_combo.setToolTip(tooltip_of("Labels"))
        layout.addRow("Labels:", self.labels_combo)

        self.font_size_input = QSpinBox(self)
        self.font_size_input.setRange(6, 20)
        self.font_size_input.setValue(font_size)
        self.font_size_input.setToolTip(tooltip_of("Font size"))
        layout.addRow("Peak Value Font Size:", self.font_size_input)

        self.rotation_input = QSpinBox(self)
        self.rotation_input.setRange(0, 360)
        self.rotation_input.setValue(rotation)
        self.rotation_input.setToolTip(tooltip_of("Text rotation"))
        layout.addRow("Text Rotation (degrees):", self.rotation_input)

        self.decimals_input = QSpinBox(self)
        self.decimals_input.setRange(0, 10)
        self.decimals_input.setValue(decimals)
        self.decimals_input.setToolTip(tooltip_of("Decimal places"))
        layout.addRow("Decimal Places:", self.decimals_input)

        self.number_format_combo = QComboBox(self)
        self.number_format_combo.addItems(["Fixed Point", "Scientific", "General", "Mixed (Auto)"])
        self.number_format_combo.setCurrentIndex(
            _FORMATS.index(number_format) if number_format in _FORMATS else 0)
        self.number_format_combo.setToolTip(tooltip_of("Number format"))
        layout.addRow("Number Format:", self.number_format_combo)

        self.format_type_combo = QComboBox(self)
        self.format_type_combo.addItems(["X and Y values", "X value only"])
        self.format_type_combo.setCurrentText("X and Y values" if format_type == "both"
                                              else "X value only")
        self.format_type_combo.setToolTip(tooltip_of("Display format"))
        layout.addRow("Display Format:", self.format_type_combo)
        outer.addLayout(layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        self.peak_list_button = QPushButton("Peak list…")
        self.peak_list_button.setToolTip("Every peak of the selected spectra in a table (position, "
                                         "height, width) and a plot of them, with these settings")
        self.peak_list_button.clicked.connect(self._show_peak_list)
        button_box.addButton(self.peak_list_button, QDialogButtonBox.ActionRole)
        self.reset_button = QPushButton("Reset to defaults")
        self.reset_button.setToolTip("Put every setting back to its default (the result is shown "
                                     "after Apply)")
        self.reset_button.clicked.connect(self.reset_defaults)
        button_box.addButton(self.reset_button, QDialogButtonBox.ResetRole)
        self.apply_button = button_box.button(QDialogButtonBox.Apply)
        self.apply_button.setToolTip("Mark the peaks on the plot with these settings")
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.apply)
        button_box.rejected.connect(self.reject)
        self.button_box = button_box
        outer.addWidget(button_box)

    def get_settings(self):
        return {
            'threshold': self.threshold_input.value(),
            'font_size': self.font_size_input.value(),
            'rotation': self.rotation_input.value(),
            'decimals': self.decimals_input.value(),
            'number_format': _FORMATS[self.number_format_combo.currentIndex()],
            'format_type': "both" if self.format_type_combo.currentText() == "X and Y values"
                           else "x_only",
            'prominence': self.prominence_input.value(),
            'distance': self.distance_input.value(),
            'peak_mode': self.peak_mode_combo.currentText(),
            'labels': self.labels_combo.currentData(),
        }

    def set_settings(self, s):
        self.threshold_input.setValue(s['threshold'])
        self.prominence_input.setValue(s['prominence'])
        self.distance_input.setValue(s['distance'])
        self.peak_mode_combo.setCurrentText(s['peak_mode'])
        self.font_size_input.setValue(s['font_size'])
        self.rotation_input.setValue(s['rotation'])
        self.decimals_input.setValue(s['decimals'])
        self.number_format_combo.setCurrentIndex(_FORMATS.index(s['number_format']))
        self.format_type_combo.setCurrentText("X and Y values" if s['format_type'] == "both"
                                              else "X value only")
        self.labels_combo.setCurrentIndex(max(self.labels_combo.findData(s.get('labels', 'band')), 0))

    def reset_defaults(self):
        self.set_settings(DEFAULTS)

    def apply(self):
        if self.apply_callback is not None:
            self.apply_callback(self.get_settings())

    def keyPressEvent(self, event):
        # Enter applies (and does not close the window)
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.apply()
            return
        super().keyPressEvent(event)

    def show_settings_help(self):
        from src.views.dialogs.data_analysis.peak_settings_help import PeakSettingsHelp
        self.settings_help = PeakSettingsHelp(self, labels=True)
        self.settings_help.show()
        return self.settings_help

    def _show_peak_list(self):
        """The peak list of the selected spectra with the settings shown here."""
        controller = getattr(self, 'peak_controller', None)     # set by PeakDetectionController
        if controller is None:
            return None
        s = self.get_settings()
        controller.peak_threshold, controller.peak_prominence = s['threshold'], s['prominence']
        controller.peak_distance, controller.peak_detection_mode = s['distance'], s['peak_mode']
        dialog = controller.show_peak_list()
        if dialog is not None:                       # settings changed in the list come back here
            self.threshold_input.setValue(controller.peak_threshold)
            self.prominence_input.setValue(controller.peak_prominence)
            self.distance_input.setValue(controller.peak_distance)
            self.peak_mode_combo.setCurrentText(controller.peak_detection_mode)
        return dialog
