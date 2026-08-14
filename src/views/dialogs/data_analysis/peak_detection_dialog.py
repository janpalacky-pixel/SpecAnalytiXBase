
# src/views/dialogs/peak_detection_dialog.py
from PyQt5.QtWidgets import QDialog, QFormLayout, QDialogButtonBox, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton

class PeakDetectionDialog(QDialog):
    def __init__(self, parent=None, threshold=0.5, font_size=10, rotation=45, decimals=1, 
                 format_type="both", number_format="fixed", show_labels=True, prominence=0.1, 
                 distance=0.05, peak_mode="Positive"):
        super().__init__(parent)
        self.setWindowTitle("Peak Detection Settings")
        self.setup_ui(threshold, font_size, rotation, decimals, format_type, number_format, 
                      show_labels, prominence, distance, peak_mode)

    def setup_ui(self, threshold, font_size, rotation, decimals, format_type, number_format, 
                show_labels, prominence, distance, peak_mode):
        layout = QFormLayout(self)

        # Thresholds
        self.threshold_input = QDoubleSpinBox(self)
        self.threshold_input.setRange(0.0001, 1)
        self.threshold_input.setDecimals(4)
        self.threshold_input.setSingleStep(0.001)
        self.threshold_input.setValue(threshold)
        layout.addRow("Peak Detection Threshold:", self.threshold_input)

        self.prominence_input = QDoubleSpinBox(self)
        self.prominence_input.setRange(0.0, 1.0)
        self.prominence_input.setDecimals(4)
        self.prominence_input.setSingleStep(0.01)
        self.prominence_input.setValue(prominence)
        layout.addRow("Prominence Threshold (Relative):", self.prominence_input)

        self.distance_input = QDoubleSpinBox(self)
        self.distance_input.setRange(0.0, 1.0)
        self.distance_input.setDecimals(4)
        self.distance_input.setSingleStep(0.01)
        self.distance_input.setValue(distance)
        layout.addRow("Distance Threshold (Relative):", self.distance_input)

        # Peak detection mode
        self.peak_mode_combo = QComboBox(self)
        self.peak_mode_combo.addItems(["Positive", "Negative", "Both"])
        self.peak_mode_combo.setCurrentText(peak_mode)
        layout.addRow("Peak Detection Mode:", self.peak_mode_combo)

        # Other existing settings
        self.font_size_input = QSpinBox(self)
        self.font_size_input.setRange(6, 20)
        self.font_size_input.setValue(font_size)
        layout.addRow("Peak Value Font Size:", self.font_size_input)

        self.rotation_input = QSpinBox(self)
        self.rotation_input.setRange(0, 360)
        self.rotation_input.setValue(rotation)
        layout.addRow("Text Rotation (degrees):", self.rotation_input)

        self.decimals_input = QSpinBox(self)
        self.decimals_input.setRange(0, 10)
        self.decimals_input.setValue(decimals)
        layout.addRow("Decimal Places:", self.decimals_input)

        self.number_format_combo = QComboBox(self)
        self.number_format_combo.addItems(["Fixed Point", "Scientific", "General", "Mixed (Auto)"])
        format_map = {"fixed": 0, "sci": 1, "general": 2, "mixed": 3}
        self.number_format_combo.setCurrentIndex(format_map.get(number_format, 0))
        layout.addRow("Number Format:", self.number_format_combo)

        self.format_type_combo = QComboBox(self)
        self.format_type_combo.addItems(["X and Y values", "X value only"])
        self.format_type_combo.setCurrentText("X and Y values" if format_type == "both" else "X value only")
        layout.addRow("Display Format:", self.format_type_combo)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        help_button = QPushButton("Help")
        help_button.setToolTip("Show help for Peak Detection.")
        help_button.clicked.connect(self._show_help)
        button_box.addButton(help_button, QDialogButtonBox.HelpRole)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def get_settings(self):
        format_map = {0: "fixed", 1: "sci", 2: "general", 3: "mixed"}
        return {
            'threshold': self.threshold_input.value(),
            'font_size': self.font_size_input.value(),
            'rotation': self.rotation_input.value(),
            'decimals': self.decimals_input.value(),
            'number_format': format_map[self.number_format_combo.currentIndex()],
            'format_type': "both" if self.format_type_combo.currentText() == "X and Y values" else "x_only",
            'prominence': self.prominence_input.value(),
            'distance': self.distance_input.value(),
            'peak_mode': self.peak_mode_combo.currentText()
        }

    def _show_help(self):
        """Show the Peak Detection help window."""
        try:
            from src.help.peak_detection_help import (
                get_peak_detection_help_content, get_peak_detection_help_title)
            from src.help.help_window import show_help_window
            show_help_window(self, get_peak_detection_help_title(),
                             get_peak_detection_help_content())
        except Exception:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Help',
                                    'Help documentation is not available.')


