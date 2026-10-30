# src/views/dialogs/data_analysis/data_table_dialog.py
"""Analysis & Visualization -> Data Analysis -> Data table (also a button
under the menu bar): the selected spectra as a spreadsheet, with columns
calculated from formulas that can be added as new spectra. The table logic is
in src/modules/data_analysis/data_table.py; adding the spectra in
src/controllers/data_analysis/data_table_controller.py."""

import numpy as np
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt5.QtGui import QBrush, QColor, QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QDialog, QFileDialog, QHBoxLayout,
                             QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QShortcut,
                             QTableView, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from src.modules.data_analysis.data_table import FUNCTION_HELP, DataTable

_FORMULA_BG = QColor('#E8F5E9')
_X_BG = QColor('#F2F4F7')
_COPY_ASK_ABOVE = 2_000_000          # cells; bigger copies take a while and a lot of memory


class DataTableModel(QAbstractTableModel):
    """The table, read on demand: only the cells on screen are formatted, so
    thousands of spectra open at once."""

    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table
        self.header = None              # the view's heading: names are fitted to its widths

    def _fit(self, text, section):
        """The spectrum name as wide as its column allows; a long one keeps
        its end (spectra of one file differ at the end: '... : 0001')."""
        if self.header is None:
            return text
        from PyQt5.QtGui import QFontMetrics
        width = max(self.header.sectionSize(section) - 12, 20)
        return QFontMetrics(self.header.font()).elidedText(text, Qt.ElideLeft, width)

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.table.n_rows

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.table.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        col = self.table.columns[index.column()]
        if role == Qt.DisplayRole:
            v = self.table.value(index.row(), index.column())
            if v is None:
                return ''
            return f'{v:.6g}' if v == v and abs(v) != float('inf') else '—'
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.BackgroundRole:
            if col.kind == 'formula':
                return QBrush(_FORMULA_BG)
            if col.kind == 'x':
                return QBrush(_X_BG)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Vertical:
            return section + 1 if role == Qt.DisplayRole else None
        col = self.table.columns[section]
        if role == Qt.DisplayRole:
            if col.kind == 'x':
                return col.name
            return f'{col.name}\n{self._fit(col.title, section)}'
        if role == Qt.ToolTipRole:
            if col.kind == 'formula':
                return f'{col.name} = {col.formula}\nNew spectrum name: {col.title}'
            return f'{col.name}: {col.title}'
        return None


class DataTableDialog(QDialog):

    def __init__(self, parent, spectra, commit_callback=None, value_callback=None):
        super().__init__(parent)
        self.table = DataTable.from_spectra(spectra)
        self.commit_callback = commit_callback
        # Values per spectrum > As new spectrum: value_callback(spectrum, sources);
        # by default the one of the controller that adds the formula columns
        if value_callback is None:
            value_callback = getattr(getattr(commit_callback, '__self__', None),
                                     'add_value_spectrum', None)
        self.value_callback = value_callback
        # the columns of the last Data table are made again (and remembered
        # when this one closes): DataTableController.remembered, shared by
        # every way of opening the Data table (menu, Peak list, Peak Fitting,
        # Spectral Calculator)
        owner = getattr(commit_callback, '__self__', None)
        self.memory_owner = owner if hasattr(owner, 'remembered') else None
        n = len(self.table.spectrum_columns())
        self.setWindowTitle(f"Data table – {n} spectr{'um' if n == 1 else 'a'}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(960, 640)
        layout = QVBoxLayout(self)
        # what each tab is for is said at the top of the tab itself (with an
        # orange "?" for more)
        outer = layout
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { min-width: 170px; padding: 6px 14px; }")
        outer.addWidget(self.tabs, 1)
        page = QWidget()
        layout = QVBoxLayout(page)
        self.tabs.addTab(page, "Points (one row per x)")
        # which tab is for what - the tab names alone are easy to overlook
        top = QHBoxLayout()
        self.points_guide = QLabel(
            "This tab shows the spectra themselves (x, then sp1, sp2, …) – calculate new spectra "
            "point by point, e.g. sp1 − sp2. One number per spectrum: tab <b>Values per "
            "spectrum</b>.")
        self.points_guide.setWordWrap(True)
        self.points_guide.setStyleSheet("color: #555;")
        top.addWidget(self.points_guide, 1)
        from src.help.data_table_quick_help import quick_help_button
        self.quick_help_button = quick_help_button('points', self.show_quick_help)
        top.addWidget(self.quick_help_button, 0, Qt.AlignTop)
        layout.addLayout(top)

        if not self.table.shared_x:
            note = QLabel(
                "The selected spectra have different x-axes: each has its own x column, and "
                "formulas are not available (their points do not line up row by row). To use "
                "formulas, bring them onto one x-axis first: Spectra processing › Data range "
                "with ‘Apply linearization’.")
            note.setWordWrap(True)
            note.setStyleSheet("color: #B45309;")
            layout.addWidget(note)
            self.axes_note = note

        self.model = DataTableModel(self.table, self)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.horizontalHeader().setDefaultSectionSize(116)
        self.view.verticalHeader().setDefaultSectionSize(22)
        self.view.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.horizontalHeader().customContextMenuRequested.connect(self._header_menu)
        self.model.header = self.view.horizontalHeader()
        self.view.horizontalHeader().sectionResized.connect(
            lambda section, *_: self.model.headerDataChanged.emit(Qt.Horizontal, section, section))
        layout.addWidget(self.view, 1)
        QShortcut(QKeySequence.Copy, self.view, activated=self.copy_selection)

        row = QHBoxLayout()
        row.addWidget(QLabel("New column ="))
        self.formula_edit = QLineEdit()
        self.formula_edit.setPlaceholderText(
            "a formula, e.g. sp1 / sp2   — several at once: separate them with commas")
        self.formula_edit.returnPressed.connect(self.add_column)
        row.addWidget(self.formula_edit, 3)
        row.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("optional: the new spectrum's name")
        self.name_edit.returnPressed.connect(self.add_column)
        row.addWidget(self.name_edit, 2)
        self.add_button = QPushButton("Add column")
        self.add_button.setToolTip("Calculate the formula and show it as a new (green) column")
        self.add_button.clicked.connect(self.add_column)
        row.addWidget(self.add_button)
        self.functions_button = QToolButton()
        self.functions_button.setText("Functions")
        self.functions_button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.functions_button)
        for example, text in FUNCTION_HELP:
            act = menu.addAction(f"{example}    — {text}")
            act.triggered.connect(lambda _c=False, e=example: self._insert(e))
        self.functions_button.setMenu(menu)
        row.addWidget(self.functions_button)
        layout.addLayout(row)
        for w in (self.formula_edit, self.name_edit, self.add_button, self.functions_button):
            w.setEnabled(self.table.shared_x)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy")
        self.copy_button.setToolTip("Copy the selected cells (or the whole table when nothing is "
                                    "selected) with their column names, e.g. into Excel")
        self.copy_button.clicked.connect(self.copy_selection)
        self.export_button = QPushButton("Export…")
        self.export_button.setToolTip("Save the whole table as Excel or CSV")
        self.export_button.clicked.connect(self.export)
        self.remove_button = QPushButton("Remove column")
        self.remove_button.setToolTip("Remove the selected formula column(s)")
        self.remove_button.clicked.connect(self.remove_selected_columns)
        self.add_spectra_button = QPushButton("Add formula columns as new spectra")
        self.add_spectra_button.setToolTip(
            "Each formula column becomes a new spectrum in the spectra list (one step in the "
            "Operations History, so Undo removes them again)")
        self.add_spectra_button.clicked.connect(self.add_as_spectra)
        close = QPushButton("Close")
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        for b in (self.copy_button, self.export_button, self.remove_button):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(self.add_spectra_button)
        layout.addLayout(buttons)

        from src.views.dialogs.data_analysis.value_table_panel import ValueTablePanel
        self.values = ValueTablePanel(self, spectra, add_spectrum=self.value_callback)
        self.tabs.addTab(self.values, "Values per spectrum")
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        outer.addLayout(bottom)
        for b in (self.copy_button, self.export_button, self.remove_button, self.add_spectra_button,
                  self.add_button):
            b.setAutoDefault(False)
        self._update_buttons()
        self._make_remembered_columns()

    # ------------------------------------------------- remembered columns
    def _labels(self):
        return [str(c.title) for c in self.table.spectrum_columns()]

    def _make_remembered_columns(self):
        """The columns of the last Data table: the formulas of Points when the
        same spectra are open (sp1, sp2, ... mean the same spectra), and the
        columns of Values per spectrum always (they are made per spectrum)."""
        memory = getattr(self.memory_owner, 'remembered', None)
        if not isinstance(memory, dict):
            return
        points = memory.get('points') or []
        if points and self.table.shared_x and memory.get('labels') == self._labels():
            made, failed = [], []
            for formula, title in points:
                try:
                    made += self.table.add_formulas(formula, title)
                except ValueError:
                    failed.append(formula)
            if made or failed:
                self.model.refresh()
                self._update_buttons()
                text = ("From the last time (the same spectra): "
                        + ', '.join(f"{c.name} = {c.formula}" for c in made) + "." if made else "")
                if failed:
                    text += " Not made again: " + ', '.join(failed) + "."
                self._say(text.strip(), error=bool(failed) and not made)
        self.values.replay(memory.get('values'))

    def remember(self):
        """What this Data table has added, for the next one."""
        if self.memory_owner is None:
            return
        # formulas already added as new spectra are done: not made again
        done = getattr(self, 'formulas_added_as_spectra', False)
        self.memory_owner.remembered = {
            'labels': self._labels(),
            'points': [] if done else [(c.formula, '' if c.title == c.formula else c.title)
                                       for c in self.table.formula_columns()],
            'values': self.values.table.recipes(),
        }

    def done(self, result):
        self.remember()
        super().done(result)

    def show_quick_help(self, key='points', run=True):
        from src.help.data_table_quick_help import show_quick_help
        return show_quick_help(self, key, run)

    # ------------------------------------------------------------- formulas
    def _insert(self, text):
        self.formula_edit.insert(text)
        self.formula_edit.setFocus()

    def _say(self, text, error=False):
        self.message.setText(text)
        self.message.setStyleSheet("color: #C62828;" if error else "color: #2E7D32;")

    def add_column(self):
        formula = self.formula_edit.text().strip()
        try:
            cols = self.table.add_formulas(formula, self.name_edit.text())
        except ValueError as exc:
            self._say(str(exc), error=True)
            return None
        self.model.refresh()
        self.view.scrollTo(self.model.index(0, len(self.table.columns) - 1))
        notes = []
        for c in cols:
            bad = int((~np.isfinite(c.values)).sum())
            if bad:
                notes.append(f"{c.name} has no number at {bad} of {len(c.values)} points (e.g. "
                             "log10 or sqrt of a negative value, or division by zero), shown as —; "
                             "it can be added as a spectrum only when every point has a number.")
        added = ', '.join(f"{c.name} = {c.formula}" for c in cols)
        self._say(f"Added {added}." + (' ' + ' '.join(notes) if notes else ''), error=bool(notes))
        col = cols[-1]
        self.formula_edit.clear()
        self.name_edit.clear()
        self._update_buttons()
        return col

    def _selected_columns(self):
        return sorted({i.column() for i in self.view.selectionModel().selectedIndexes()})

    def remove_selected_columns(self):
        names = [self.table.columns[c].name for c in self._selected_columns()
                 if self.table.columns[c].kind == 'formula']
        if not names:
            self._say("Select a cell of a formula (green) column to remove it.", error=True)
            return
        try:
            for name in reversed(names):
                self.table.remove_column(name)
        except ValueError as exc:
            self._say(str(exc), error=True)
        self.model.refresh()
        self._update_buttons()

    def _header_menu(self, pos):
        section = self.view.horizontalHeader().logicalIndexAt(pos)
        if section < 0:
            return
        col = self.table.columns[section]
        menu = QMenu(self)
        copy = menu.addAction(f"Copy column {col.name}")
        remove = menu.addAction(f"Remove {col.name}") if col.kind == 'formula' else None
        chosen = menu.exec_(self.view.horizontalHeader().mapToGlobal(pos))
        if chosen is copy:
            QApplication.clipboard().setText(self.table.rows_as_text(cols=[section]))
            self._say(f"Column {col.name} copied.")
        elif remove is not None and chosen is remove:
            try:
                self.table.remove_column(col.name)
            except ValueError as exc:
                self._say(str(exc), error=True)
            self.model.refresh()
            self._update_buttons()

    def _update_buttons(self):
        self.add_spectra_button.setEnabled(bool(self.table.formula_columns()))
        self.remove_button.setEnabled(bool(self.table.formula_columns()))

    # ---------------------------------------------------------- copy, export
    def copy_selection(self):
        indexes = self.view.selectionModel().selectedIndexes()
        if indexes:
            rows = sorted({i.row() for i in indexes})
            cols = sorted({i.column() for i in indexes})
        else:
            rows, cols = range(self.table.n_rows), range(len(self.table.columns))
        cells = len(rows) * len(cols)
        if cells > _COPY_ASK_ABOVE and QMessageBox.question(
                self, "Copy a large table?",
                f"{cells:,} cells — this takes a while and Excel may not take them all. "
                "Copy anyway? (Export… saves the whole table as a file.)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        QApplication.clipboard().setText(self.table.rows_as_text(rows, cols))
        self._say(f"Copied {len(rows)} rows × {len(cols)} columns (with the column names).")

    def export(self):
        filters = "Excel (*.xlsx);;CSV (*.csv);;Text, tab-separated (*.txt)"
        path, chosen = QFileDialog.getSaveFileName(self, "Export the data table", "data_table.xlsx",
                                                   filters)
        if not path:
            return None
        if '.' not in path.split('/')[-1].split('\\')[-1]:
            path += {'CSV': '.csv', 'Text': '.txt'}.get(chosen.split(' ')[0], '.xlsx')
        try:
            self.table.export(path)
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"The table could not be saved:\n\n{exc}")
            return None
        self._say(f"Saved: {path}")
        return path

    # ----------------------------------------------------------- new spectra
    def add_as_spectra(self):
        try:
            spectra = self.table.new_spectra()
        except ValueError as exc:
            self._say(str(exc), error=True)
            return False
        if self.commit_callback is None:
            return False
        ok, text = self.commit_callback(self.table, spectra)
        if not ok:
            self._say(text, error=True)
            return False
        self.formulas_added_as_spectra = True
        self.accept()
        return True

    def show_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'user_guide', 'data-table')
