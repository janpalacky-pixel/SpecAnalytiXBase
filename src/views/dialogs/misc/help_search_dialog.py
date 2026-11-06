# src/views/dialogs/misc/help_search_dialog.py
"""Help › Search the help… (F1): a word in all help pages at once; a hit
opens its page at that section in the browser."""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)


class HelpSearchDialog(QDialog):
    def __init__(self, parent=None, open_topic=None):
        super().__init__(parent)
        self.setWindowTitle("Search the help")
        self.resize(760, 520)
        self._open_topic = open_topic
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Find:"))
        self.field = QLineEdit()
        self.field.setPlaceholderText("a word or a few words, e.g. legend, 600 dpi, isosbestic")
        self.field.setClearButtonEnabled(True)
        self.field.setToolTip(
            "Find: the help sections that contain every word typed here (in all\n"
            "help pages at once). Double-click a result (or Enter) to open it.")
        row.addWidget(self.field, 1)
        layout.addLayout(row)
        self.count_label = QLabel(" ")
        self.count_label.setStyleSheet("color: #555;")
        layout.addWidget(self.count_label)
        self.results = QListWidget()
        self.results.setWordWrap(True)
        self.results.setAlternatingRowColors(True)
        self.results.itemActivated.connect(self._open_item)
        layout.addWidget(self.results, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.open_button = QPushButton("Open")
        self.open_button.setToolTip("Open: the chosen section of the help in the browser.")
        self.open_button.clicked.connect(lambda: self._open_item(self.results.currentItem()))
        close = QPushButton("Close")
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        buttons.addWidget(self.open_button)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.find)
        self.field.textChanged.connect(lambda *_: self._timer.start())
        self.field.returnPressed.connect(self._enter)

    def find(self, text=None):
        """Show the sections that contain every word of the field."""
        from src.help import help_search
        text = self.field.text() if text is None else text
        self.results.clear()
        if not text.strip():
            self.count_label.setText(" ")
            return []
        if help_search._index is None:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                help_search.index()                   # every page read once
            finally:
                QApplication.restoreOverrideCursor()
        found = help_search.search(text)
        for hit in found:
            where = hit['title'] + (f"  ›  {hit['heading']}" if hit['heading'] else '')
            item = QListWidgetItem(f"{where}\n    {hit['snippet']}")
            item.setData(Qt.UserRole, (hit['key'], hit['anchor']))
            item.setToolTip(where)
            self.results.addItem(item)
        self.count_label.setText(
            f"{len(found)} section{'s' if len(found) != 1 else ''} found"
            + (" (the best 60)" if len(found) == 60 else "") if found else "Nothing found.")
        if found:
            self.results.setCurrentRow(0)
        return found

    def _enter(self):
        self._timer.stop()
        found = self.find()
        if found and self.results.currentItem() is not None:
            self._open_item(self.results.currentItem())

    def _open_item(self, item):
        if item is None:
            return
        key, anchor = item.data(Qt.UserRole)
        if self._open_topic is not None:
            self._open_topic(key, anchor)
        else:
            from src.help.help_window import open_help_topic
            open_help_topic(self, key, anchor)
