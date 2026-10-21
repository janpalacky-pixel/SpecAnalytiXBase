# src/views/dialogs/misc/keyboard_shortcuts_dialog.py
"""Help -> Keyboard shortcuts...: every shortcut in one table
(src/modules/misc/keyboard_shortcuts.py, the same as in the User Guide)."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from src.modules.misc import keyboard_shortcuts as ks


class KeyboardShortcutsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(620, 640)
        layout = QVBoxLayout(self)
        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(False)
        table = ks.html_table().replace(
            '<table>', '<table border="1" cellspacing="0" cellpadding="5" width="100%">', 1)
        self.text.setHtml(
            '<style>.kbd { font-family: monospace; font-weight: bold; }</style>'
            '<p>On a Mac, Ctrl is the Cmd key.</p>' + table)
        layout.addWidget(self.text)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)


def show_keyboard_shortcuts(parent=None):
    dlg = KeyboardShortcutsDialog(parent)
    dlg.show()
    dlg.raise_()
    return dlg
