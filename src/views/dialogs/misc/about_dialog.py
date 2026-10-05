# src/views/dialogs/misc/about_dialog.py

from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QLabel,
                             QPlainTextEdit, QPushButton, QVBoxLayout)
from PyQt5.QtGui import QFont, QFontDatabase

from src.modules.utils.about_info import get_about_info, format_about_text


class AboutDialog(QDialog):
    """Help > About: which version/build and which library versions this
    copy of the application is running on, with a button to copy it all for
    a bug report."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About SpecAnalytiXBase")
        self.setMinimumWidth(480)

        self._info = get_about_info()
        version = dict(self._info).get("Version", "")

        layout = QVBoxLayout(self)

        title = QLabel("SpecAnalytiXBase  %s" % version)
        title_font = QFont(title.font())
        title_font.setPointSize(title_font.pointSize() + 4)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        subtitle = QLabel(
            "Free, open-source software (GPL-3.0). See Help › License.")
        layout.addWidget(subtitle)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.details.setPlainText(format_about_text(self._info))
        self.details.setMinimumHeight(240)
        layout.addWidget(self.details)

        buttons = QDialogButtonBox()
        self.copy_button = QPushButton("Copy to clipboard")
        self.copy_button.setToolTip(
            "Copy this information, e.g. to paste into a bug report.")
        self.copy_button.clicked.connect(self.copy_to_clipboard)
        buttons.addButton(self.copy_button, QDialogButtonBox.ActionRole)
        buttons.addButton(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.details.toPlainText())
