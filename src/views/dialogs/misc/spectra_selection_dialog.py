
# src/views/dialogs/misc/spectra_selection_dialog.py
from PyQt5.QtWidgets import (QDialog, QSpinBox, QVBoxLayout, QHBoxLayout, 
                           QLabel, QDialogButtonBox, QPushButton)

class SpectraSelectionDialog(QDialog):
    """
    A reusable dialog for selecting spectra by range with various options.
    Can be used for both spectrum selector and rename operations.
    """
    def __init__(self, parent=None, total_spectra=0, title="Select Spectra"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.total_spectra = total_spectra
        self.selection_result = {
            'start': 0,
            'end': total_spectra - 1 if total_spectra > 0 else 0,
            'step': 1,
            'action': None  # Will be set based on which button is clicked
        }
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout()
        
        # Add spin boxes for start, end indices, and step
        start_layout = QHBoxLayout()
        start_layout.addWidget(QLabel("Start:"))
        self.start_spinbox = QSpinBox()
        self.start_spinbox.setMinimum(1)
        self.start_spinbox.setMaximum(self.total_spectra if self.total_spectra > 0 else 1)
        start_layout.addWidget(self.start_spinbox)
        
        end_layout = QHBoxLayout()
        end_layout.addWidget(QLabel("End:"))
        self.end_spinbox = QSpinBox()
        self.end_spinbox.setMinimum(1)
        self.end_spinbox.setMaximum(self.total_spectra if self.total_spectra > 0 else 1)
        self.end_spinbox.setValue(self.total_spectra if self.total_spectra > 0 else 1)
        end_layout.addWidget(self.end_spinbox)
        
        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("Step:"))
        self.step_spinbox = QSpinBox()
        self.step_spinbox.setMinimum(1)
        self.step_spinbox.setMaximum(self.total_spectra if self.total_spectra > 0 else 1)
        step_layout.addWidget(self.step_spinbox)
        
        # Add all layouts to main layout
        layout.addLayout(start_layout)
        layout.addLayout(end_layout)
        layout.addLayout(step_layout)
        
        # Add selection buttons
        button_layout = QHBoxLayout()
        
        # Select button
        self.select_button = QPushButton("Select")
        self.select_button.clicked.connect(lambda: self.handle_button_click("select"))
        button_layout.addWidget(self.select_button)
        
        # Add button
        self.add_button = QPushButton("Add to Selection")
        self.add_button.clicked.connect(lambda: self.handle_button_click("add"))
        button_layout.addWidget(self.add_button)
        
        # Remove button
        self.remove_button = QPushButton("Remove from Selection")
        self.remove_button.clicked.connect(lambda: self.handle_button_click("remove"))
        button_layout.addWidget(self.remove_button)
        
        layout.addLayout(button_layout)
        
        # Add standard OK and Cancel buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        
        self.setLayout(layout)
        
    def handle_button_click(self, action):
        """Handle clicks on the selection action buttons."""
        self.selection_result.update({
            'start': self.start_spinbox.value() - 1,  # Convert to 0-based index
            'end': self.end_spinbox.value() - 1,      # Convert to 0-based index
            'step': self.step_spinbox.value(),
            'action': action
        })
        self.accept()
        
    def get_selection_parameters(self):
        """Return the selection parameters."""
        return self.selection_result