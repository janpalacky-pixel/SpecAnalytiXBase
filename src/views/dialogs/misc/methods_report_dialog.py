# src/views/dialogs/misc/methods_report_dialog.py
"""File -> Methods report for publication: shows the report built by
src/modules/misc/methods_report.py -- text, parameter table, references,
all three editable -- and copies or saves the parts the user ticks, as
Word (.docx), HTML, Markdown or plain text.

Edits survive closing the window: they are kept in *draft_store* (a dict
owned by the main window, so for the rest of the session) together with
the generated draft they were made on. Reopened on the same processing,
the edited version is shown; if the processing has changed since, the user
chooses between the edited version and a fresh draft."""

import os

from PyQt5.QtCore import QMimeData, Qt
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextEdit, QVBoxLayout)

from src.modules.misc.methods_report import (
    ExportContent, MethodsReport, TABLE_HEADER, default_file_name)

_FILTERS = (("Word document (*.docx)", '.docx'), ("HTML (*.html)", '.html'),
            ("Markdown (*.md)", '.md'), ("Text (*.txt)", '.txt'))


def _preferences():
    try:
        from src.modules.misc.session_files import Preferences
        return Preferences()
    except Exception:
        return None


class MethodsReportDialog(QDialog):

    def __init__(self, report: MethodsReport, parent=None, start_dir: str = '',
                 draft_store=None):
        super().__init__(parent)
        self.report = report
        self._store = draft_store if draft_store is not None else {}
        self._start_dir = start_dir
        self.saved_path = None
        self.setWindowTitle("Methods report for publication")
        self.resize(860, 640)
        layout = QVBoxLayout(self)

        note = QLabel(
            "A draft of the Methods text for the processing behind the spectra shown now "
            "(Operations History up to the active step). Treat it as a template: check it, "
            "and edit the text, the parameter table and the references as you need. "
            "Click Help for details.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        layout.addWidget(note)

        # Shown when an earlier edited version is displayed (see _restore_draft).
        self.draft_label = QLabel("")
        self.draft_label.setWordWrap(True)
        self.draft_label.setStyleSheet(
            "color:#1b5e20; background:#e8f5e9; padding:3px 6px; border-radius:3px;")
        self.draft_label.setVisible(False)
        layout.addWidget(self.draft_label)

        self.tabs = QTabWidget()
        # Without this, Windows cuts the tab titles short (same fix as in
        # the Normalization and Cosmic ray dialogs).
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.setStyleSheet("QTabBar::tab { min-width: 150px; padding: 4px 12px; }")

        self.text_edit = QTextEdit()
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setPlainText(report.text)
        self.tabs.addTab(self.text_edit, "Text")
        self.tabs.setTabToolTip(0, "The Methods paragraph. Edit it freely.")

        rows = report.table_rows()
        self.table = QTableWidget(len(rows), len(TABLE_HEADER))
        self.table.setHorizontalHeaderLabels(list(TABLE_HEADER))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed
                                   | QTableWidget.AnyKeyPressed)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(r, c, item)
        header = self.table.horizontalHeader()
        for c in range(len(TABLE_HEADER) - 1):
            header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        n = len(report.steps)
        self.tabs.addTab(self.table, f"Parameters ({n} step{'' if n == 1 else 's'})")
        self.tabs.setTabToolTip(1, "Every step with its settings. Double-click a cell to edit it.")

        self.refs_edit = QTextEdit()
        self.refs_edit.setAcceptRichText(False)
        self.refs_edit.setPlainText("\n\n".join(report.numbered_references()))
        self.tabs.addTab(self.refs_edit, f"References ({len(report.references)})")
        self.tabs.setTabToolTip(2, "One reference per paragraph (separated by an empty line). "
                                   "Edit them to match your journal's citation style if needed.")
        layout.addWidget(self.tabs, stretch=1)

        # Which optional parts go into Copy / Save (the text always does).
        include_row = QHBoxLayout()
        include_row.addWidget(QLabel("Copy and save the text together with:"))
        prefs = _preferences()
        self.include_table_cb = QCheckBox("Parameter table")
        self.include_refs_cb = QCheckBox("References")
        for cb, key in ((self.include_table_cb, 'methods_report_include_table'),
                        (self.include_refs_cb, 'methods_report_include_references')):
            cb.setChecked(bool(prefs.get(key, True)) if prefs else True)
            cb.toggled.connect(lambda on, k=key: self._remember(k, on))
            include_row.addWidget(cb)
        include_row.addStretch(1)
        layout.addLayout(include_row)

        buttons = QHBoxLayout()
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setToolTip("Copy the text and the ticked parts. Pasted into Word, the "
                                 "table stays a table.")
        self.copy_btn.clicked.connect(self.copy)
        self.save_btn = QPushButton("Save…")
        self.save_btn.setToolTip("Save the text and the ticked parts as a Word document, HTML, "
                                 "Markdown or plain text.")
        self.save_btn.clicked.connect(self.save)
        self.reset_btn = QPushButton("Restore generated draft")
        self.reset_btn.setToolTip("Discard your edits in all three tabs and show the automatically "
                                  "generated version again.")
        self.reset_btn.clicked.connect(self.restore_generated)
        self.help_btn = QPushButton("Help")
        self.help_btn.clicked.connect(self.show_help)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(self.copy_btn)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.reset_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.help_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self._generated = self._current_parts()
        self._restore_draft()

    # ------------------------------------------------------------------
    # Keeping edits between openings
    # ------------------------------------------------------------------
    def _current_parts(self):
        return (self.text_edit.toPlainText(), tuple(self._table_rows()),
                self.refs_edit.toPlainText())

    def _show_parts(self, parts):
        text, rows, refs = parts
        self.text_edit.setPlainText(text)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(r, c, item)
        self.refs_edit.setPlainText(refs)

    def _restore_draft(self):
        draft = self._store.get('draft')
        if not draft:
            return
        if draft['generated'] != self._generated:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("Methods report")
            box.setText("You edited this report earlier, but the processing has changed since "
                        "then (steps added, removed or changed, or other data loaded).")
            box.setInformativeText("Keep my edited version: show your earlier text, table and "
                                   "references (they describe the earlier processing).\n"
                                   "New draft: generate the report for the current processing.")
            keep = box.addButton("Keep my edited version", QMessageBox.AcceptRole)
            box.addButton("New draft", QMessageBox.RejectRole)
            box.exec_()
            if box.clickedButton() is not keep:
                self._store.pop('draft', None)
                return
        self._show_parts(draft['edited'])
        self.draft_label.setText(
            "Your earlier edits are shown. \"Restore generated draft\" brings back the "
            "automatically generated version.")
        self.draft_label.setVisible(True)

    def _remember_draft(self):
        current = self._current_parts()
        if current == self._generated:
            self._store.pop('draft', None)
        else:
            self._store['draft'] = {'generated': self._generated, 'edited': current}

    def restore_generated(self):
        if self._current_parts() != self._generated:
            answer = QMessageBox.question(
                self, "Restore generated draft",
                "Discard your edits in the Text, Parameters and References tabs?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self._show_parts(self._generated)
        self._store.pop('draft', None)
        self.draft_label.setVisible(False)

    def done(self, result):
        # Closing the window in any way (Close, Esc, the X) keeps the edits.
        self._remember_draft()
        super().done(result)

    # ------------------------------------------------------------------
    @staticmethod
    def _remember(key, on):
        prefs = _preferences()
        if prefs is not None:
            prefs.set(key, bool(on))

    def _table_rows(self):
        rows = []
        for r in range(self.table.rowCount()):
            rows.append(tuple((self.table.item(r, c).text() if self.table.item(r, c) else '')
                              for c in range(self.table.columnCount())))
        return rows

    def _references(self):
        text = self.refs_edit.toPlainText().replace('\r\n', '\n')
        return [' '.join(p.split()) for p in text.split('\n\n') if p.strip()]

    def content(self) -> ExportContent:
        """Everything as currently edited, with the ticked parts."""
        return ExportContent(
            text=self.text_edit.toPlainText().strip(),
            table_rows=self._table_rows(),
            references=self._references(),
            include_table=self.include_table_cb.isChecked(),
            include_references=self.include_refs_cb.isChecked())

    def copy(self):
        content = self.content()
        mime = QMimeData()
        mime.setText(content.as_plain_text())
        mime.setHtml(content.as_html())
        QApplication.clipboard().setMimeData(mime)

    def save(self):
        filters = ';;'.join(f for f, _ in _FILTERS)
        path, chosen = QFileDialog.getSaveFileName(
            self, "Save Methods report",
            os.path.join(self._start_dir or os.path.expanduser('~'), default_file_name() + '.docx'),
            filters)
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += dict(_FILTERS).get(chosen, '.docx')
        try:
            self.content().save(path)
        except OSError as exc:
            QMessageBox.warning(self, "Could not save",
                                f"The report could not be saved:\n{exc}\n\n"
                                "If the file is open in Word, close it and try again.")
            return
        self.saved_path = path

    def show_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'methods_report')
