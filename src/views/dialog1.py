from PyQt5.QtWidgets import QDialog, QPushButton, QCheckBox
from PyQt5.QtCore import QRect, QMetaObject

class Dialog1(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface directly in Python code."""
        self.setObjectName("Dialog1")
        self.resize(769, 300)
        self.setWindowTitle("Dialog 1")
        
        # Push button for subdialog
        self.pushButton_subdialog = QPushButton(self)
        self.pushButton_subdialog.setGeometry(QRect(10, 10, 75, 23))
        self.pushButton_subdialog.setObjectName("pushButton_subdialog")
        self.pushButton_subdialog.setText("Open SubDialog")
        
        # Checkbox
        self.checkBox = QCheckBox(self)
        self.checkBox.setGeometry(QRect(10, 40, 91, 17))
        self.checkBox.setObjectName("checkBox")
        self.checkBox.setText("test_dialog_1")
        
        # Select button
        self.pushButton_select = QPushButton(self)
        self.pushButton_select.setGeometry(QRect(20, 70, 121, 23))
        self.pushButton_select.setObjectName("pushButton_select")
        self.pushButton_select.setText("pushButton_select")
        
        QMetaObject.connectSlotsByName(self)