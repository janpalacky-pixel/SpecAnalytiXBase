
from PyQt5.QtWidgets import QDialog, QCheckBox
from PyQt5.QtCore import QRect, QMetaObject

class Dialog2(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface directly in Python code."""
        self.setObjectName("Dialog2")
        self.resize(432, 71)
        self.setWindowTitle("Dialog 2")
        
        # Checkbox
        self.checkBox = QCheckBox(self)
        self.checkBox.setGeometry(QRect(10, 20, 91, 17))
        self.checkBox.setObjectName("checkBox")
        self.checkBox.setText("test_dialog_2")
        
        QMetaObject.connectSlotsByName(self)