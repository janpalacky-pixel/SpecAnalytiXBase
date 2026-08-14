
# src/views/dialogs/visualization/constrained_layout_dialog.py
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton,
                             QDoubleSpinBox, QCheckBox, QDialogButtonBox, QLabel)

class ConstrainedLayoutDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("Layout Properties")
        self.setModal(True)
        
        # Initialize with default values or provided settings
        self.settings = settings or {}
        
        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Form layout for settings
        form_layout = QFormLayout()
        
        # Fixed padding settings
        self.w_pad_spin = QDoubleSpinBox()
        self.w_pad_spin.setRange(0.0, 2.0)
        self.w_pad_spin.setSingleStep(0.01)
        self.w_pad_spin.setDecimals(3)
        form_layout.addRow("Width Padding (inches):", self.w_pad_spin)
        
        self.h_pad_spin = QDoubleSpinBox()
        self.h_pad_spin.setRange(0.0, 2.0)
        self.h_pad_spin.setSingleStep(0.01)
        self.h_pad_spin.setDecimals(3)
        form_layout.addRow("Height Padding (inches):", self.h_pad_spin)
        
        # Subplot spacing settings
        self.wspace_spin = QDoubleSpinBox()
        self.wspace_spin.setRange(0.0, 1.0)
        self.wspace_spin.setSingleStep(0.01)
        self.wspace_spin.setDecimals(3)
        form_layout.addRow("Width Space (fraction):", self.wspace_spin)
        
        self.hspace_spin = QDoubleSpinBox()
        self.hspace_spin.setRange(0.0, 1.0)
        self.hspace_spin.setSingleStep(0.01)
        self.hspace_spin.setDecimals(3)
        form_layout.addRow("Height Space (fraction):", self.hspace_spin)
        
        # Adaptive padding settings
        self.adaptive_checkbox = QCheckBox("Use Adaptive Padding")
        self.adaptive_checkbox.stateChanged.connect(self.toggle_adaptive_settings)
        form_layout.addRow("", self.adaptive_checkbox)
        
        self.adaptive_factor_spin = QDoubleSpinBox()
        self.adaptive_factor_spin.setRange(0.0, 0.2)
        self.adaptive_factor_spin.setSingleStep(0.001)
        self.adaptive_factor_spin.setDecimals(3)
        form_layout.addRow("Adaptive Factor (%):", self.adaptive_factor_spin)
        
        layout.addLayout(form_layout)
        
        # Help text
        help_text = QLabel(
            "Width/Height Padding: Space around plot edges (inches)\n"
            "Width/Height Space: Space between subplots (fraction of subplot size)\n"
            "Adaptive Padding: Automatically adjust padding based on figure size\n"
            "Adaptive Factor: Percentage of figure size to use for padding"
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        
        # Buttons
        button_layout = QHBoxLayout()
        reset_button = QPushButton("Reset to Default")
        reset_button.clicked.connect(self.reset_to_default)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        button_layout.addWidget(reset_button)
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
    def load_settings(self):
        """Load current settings into the UI."""
        self.w_pad_spin.setValue(self.settings.get('w_pad', 0.03))
        self.h_pad_spin.setValue(self.settings.get('h_pad', 0.03))
        self.wspace_spin.setValue(self.settings.get('wspace', 0.01))
        self.hspace_spin.setValue(self.settings.get('hspace', 0.01))
        self.adaptive_checkbox.setChecked(self.settings.get('use_adaptive_padding', True))
        self.adaptive_factor_spin.setValue(self.settings.get('adaptive_factor', 0.01))
        
        # Update enabled state based on adaptive checkbox
        self.toggle_adaptive_settings()
        
    def toggle_adaptive_settings(self):
        """Toggle enabled state of adaptive settings based on checkbox."""
        is_adaptive = self.adaptive_checkbox.isChecked()
        self.adaptive_factor_spin.setEnabled(is_adaptive)
        
    def reset_to_default(self):
        """Reset all settings to default values."""
        self.settings = {
            'w_pad': 0.03,
            'h_pad': 0.03,
            'wspace': 0.01,
            'hspace': 0.01,
            'use_adaptive_padding': True,
            'adaptive_factor': 0.01
        }
        self.load_settings()
        
    def get_settings(self):
        """Get the current settings from the dialog."""
        return {
            'w_pad': self.w_pad_spin.value(),
            'h_pad': self.h_pad_spin.value(),
            'wspace': self.wspace_spin.value(),
            'hspace': self.hspace_spin.value(),
            'use_adaptive_padding': self.adaptive_checkbox.isChecked(),
            'adaptive_factor': self.adaptive_factor_spin.value()
        }