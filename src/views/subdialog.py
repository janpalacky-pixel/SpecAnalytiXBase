
from PyQt5.QtWidgets import QDialog, QCheckBox, QPushButton
from PyQt5.QtCore import QRect, QMetaObject

class SubDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface directly in Python code."""
        self.setObjectName("SubDialog")
        self.resize(206, 141)
        self.setWindowTitle("SubDialog")
        
        # Checkbox
        self.checkBox = QCheckBox(self)
        self.checkBox.setGeometry(QRect(10, 20, 101, 17))
        self.checkBox.setObjectName("checkBox")
        self.checkBox.setText("test_dialog_sub")
        
        # Test button
        self.test_button_pushButton = QPushButton(self)
        self.test_button_pushButton.setGeometry(QRect(10, 60, 75, 23))
        self.test_button_pushButton.setObjectName("test_button_pushButton")
        self.test_button_pushButton.setText("test-button")
        
        QMetaObject.connectSlotsByName(self)