# src/views/dialogs/misc/spectrum_properties_dialog.py
"""Right-click on the spectra list -> Spectrum properties...: a table with one
row per spectrum and one column per property (temperature, pH,
concentration, ...). Type the values, paste a column from Excel, fill them
from the names or as a series; Apply stores them (one step in the
Operations History, so Undo takes it back).
src/modules/misc/spectrum_properties.py."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog,
                             QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                             QHeaderView, QInputDialog, QLabel, QMessageBox, QPushButton,
                             QShortcut, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout)

from src.modules.misc import spectrum_properties as sp
from src.modules.visualization import color_by_value as cbv
from src.views import icons

_BAD = QColor('#ffcdd2')

HELP_HTML = """
<p><b>Spectrum properties</b> are numbers that belong to each spectrum: temperature, pH,
concentration, time, &hellip; They are used by <i>Line colours &rsaquo; Colours by value</i>,
the <i>Data table</i> (tab Values per spectrum, also in its formulas) and the plot of the
<i>Peak list</i>. Values read from the file (e.g. <code>temperature_C</code> of a JASCO
temperature scan) are shown too and can be corrected.</p>
<ul>
<li><b>Type</b> a value into a cell (a decimal comma is fine). An empty cell = no value.
<b>Delete</b> empties the selected cells.</li>
<li><b>Paste</b> (Ctrl+V) a column copied from Excel: it fills the cells from the current one
downward (several columns fill several properties).</li>
<li><b>Add property&hellip;</b>: a new column. Its name starts with a letter and has only letters,
digits and _ (e.g. <code>concentration_mM</code>), so it also works in formulas.</li>
<li><b>Fill from the names&hellip;</b>: e.g. 45 from <code>TBA_45C</code> &mdash; choose which number
of the name. <b>Fill a series&hellip;</b>: start and step, e.g. 20, 25, 30, &hellip; in the order of
the table (sort it first by clicking a heading if needed). Both fill the selected rows of the
current column, or all rows when none is selected.</li>
<li><b>Remove property</b> empties its whole column (removed on Apply).</li>
<li><b>Apply</b> stores the values. It is one step in the Operations History, so <b>Undo</b>
takes it back; snapshots keep the values.</li>
</ul>
"""


class SpectrumPropertiesDialog(QDialog):
    """apply_callback(spectra, values) -> (ok, message); values: one
    {key: value or None} per spectrum (in `spectra` order). The window keeps
    its own copies of the names and metadata (never changes the spectra)."""

    def __init__(self, parent, spectra, apply_callback=None):
        super().__init__(parent)
        self.spectra = [{'label': s.get('label', ''), 'metadata': dict(s.get('metadata') or {})}
                        for s in spectra]
        self.apply_callback = apply_callback
        n = len(self.spectra)
        self.setWindowTitle(f"Spectrum properties – {n} spectr{'um' if n == 1 else 'a'}")
        self.setWindowFlags((self.windowFlags() | Qt.WindowMaximizeButtonHint)
                            & ~Qt.WindowContextHelpButtonHint)
        self.resize(820, 560)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        intro = QLabel("Numbers that belong to each spectrum – temperature, pH, concentration, "
                       "time… They are used by Colours by value, the Data table and the Peak "
                       "list plot. Type, paste (Ctrl+V) or fill them; an empty cell = no value.")
        intro.setWordWrap(True)
        top.addWidget(intro, 1)
        self.help_button = icons.help_button("How to set the properties")
        self.help_button.clicked.connect(self.show_help)
        top.addWidget(self.help_button, 0, Qt.AlignTop)
        layout.addLayout(top)

        tools = QHBoxLayout()
        self.add_button = QPushButton("Add property…")
        self.add_button.clicked.connect(self.add_property)
        self.remove_button = QPushButton("Remove property")
        self.remove_button.setToolTip("Empty the whole current column (removed on Apply)")
        self.remove_button.clicked.connect(self.remove_property)
        self.name_button = QPushButton("Fill from the names…")
        self.name_button.setToolTip("A number written in the names, e.g. 45 from TBA_45C")
        self.name_button.clicked.connect(self.fill_from_names)
        self.series_button = QPushButton("Fill a series…")
        self.series_button.setToolTip("start, start + step, start + 2 step, … down the table")
        self.series_button.clicked.connect(self.fill_series)
        for b in (self.add_button, self.remove_button, self.name_button, self.series_button):
            b.setAutoDefault(False)
            tools.addWidget(b)
        tools.addStretch(1)
        layout.addLayout(tools)

        self.keys = sp.property_keys(self.spectra)
        self.table = QTableWidget(n, 1 + len(self.keys))
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.horizontalHeader().resizeSection(0, 340)
        self.table.setTextElideMode(Qt.ElideMiddle)          # start and end of long names
        for r, s in enumerate(self.spectra):
            name = QTableWidgetItem(str(s.get('label', '')))
            name.setFlags(name.flags() & ~Qt.ItemIsEditable)
            name.setData(Qt.UserRole, r)                     # its place in self.spectra
            self.table.setItem(r, 0, name)
        for key in self.keys:
            self._fill_column(self.keys.index(key) + 1, [sp.value_of(s, key) for s in self.spectra])
        self._set_headers()
        self.table.itemChanged.connect(self._changed)
        layout.addWidget(self.table, 1)
        QShortcut(QKeySequence.Paste, self.table, activated=self.paste)
        QShortcut(QKeySequence.Delete, self.table, activated=self.clear_cells)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        self.apply_button = self.buttons.button(QDialogButtonBox.Apply)
        self.apply_button.setToolTip("Store the values (one step in the Operations History)")
        self.apply_button.clicked.connect(self.apply)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)   # list order first
        self.table.setSortingEnabled(True)             # a click on a heading sorts by it
        self._changed()

    # -- the table
    def _set_headers(self):
        self.table.setHorizontalHeaderLabels(["Spectrum"] + self.keys)

    def _row_spectrum(self, row):
        return int(self.table.item(row, 0).data(Qt.UserRole))

    def _fill_column(self, col, values, rows=None):
        """values in self.spectra order (rows=None) or for the given table rows."""
        self.table.blockSignals(True)
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        try:
            if rows is None:
                where = {self._row_spectrum(r): r for r in range(self.table.rowCount())}
                pairs = [(where[i], v) for i, v in enumerate(values)]
            else:
                pairs = list(zip(rows, values))
            for r, v in pairs:
                item = QTableWidgetItem(sp.value_text(v))
                item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.table.setItem(r, col, item)
        finally:
            self.table.setSortingEnabled(sorting)
            self.table.blockSignals(False)
        self._changed()

    def values(self):
        """(values, problems): one {key: value or None} per spectrum; problems
        = cells that are not numbers."""
        values = [dict() for _ in self.spectra]
        problems = 0
        self.table.blockSignals(True)
        try:
            for r in range(self.table.rowCount()):
                i = self._row_spectrum(r)
                for c, key in enumerate(self.keys, 1):
                    item = self.table.item(r, c)
                    text = item.text() if item is not None else ''
                    try:
                        values[i][key] = sp.parse_value(text)
                        if item is not None:
                            item.setBackground(QBrush())
                    except ValueError:
                        problems += 1
                        values[i][key] = sp.value_of(self.spectra[i], key)
                        if item is not None:
                            item.setBackground(_BAD)
        finally:
            self.table.blockSignals(False)
        return values, problems

    def _changed(self, *_):
        if not hasattr(self, 'apply_button'):             # still being built
            return []
        values, problems = self.values()
        diff = sp.changes(self.spectra, values)
        self.apply_button.setEnabled(bool(diff) and not problems)
        if problems:
            self.summary.setText(f"{problems} cell(s) are not numbers (red) – correct or empty "
                                 "them.")
        elif diff:
            self.summary.setText(f"{len(diff)} value(s) changed – Apply stores them.")
        elif not self.keys:
            self.summary.setText("No properties yet – Add property… makes a column.")
        else:
            self.summary.setText("")
        return diff

    def _target_rows(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return rows or list(range(self.table.rowCount()))

    def _current_column(self):
        c = self.table.currentColumn()
        if c < 1 and self.keys:
            c = 1
        return c if c >= 1 else None

    # -- tools
    def add_property(self, name=None):
        if name is None:
            name, ok = QInputDialog.getItem(
                self, "Add property", "Name (letters, digits and _, e.g. concentration_mM):",
                [k for k in sp.SUGGESTED if k not in self.keys], 0, True)
            if not ok:
                return None
        name = (name or '').strip()
        problem = sp.check_name(name, self.spectra, self.keys)
        if problem:
            QMessageBox.warning(self, "Add property", problem)
            return None
        self.keys.append(name)
        col = self.table.columnCount()
        self.table.insertColumn(col)
        self._set_headers()
        self._fill_column(col, [None] * len(self.spectra))
        self.table.setCurrentCell(0, col)
        return name

    def remove_property(self):
        col = self._current_column()
        if col is None:
            return False
        key = self.keys[col - 1]
        answer = QMessageBox.question(
            self, "Remove property", f"Empty “{key}” for all {len(self.spectra)} spectra? "
            "(It is removed on Apply; Undo brings it back.)")
        if answer != QMessageBox.Yes:
            return False
        self._fill_column(col, [None] * len(self.spectra))
        return True

    def fill_from_names(self, number=None):
        col = self._current_column()
        if col is None:
            col = 1 if self.add_property() else None
            if col is None:
                return False
        rows = self._target_rows()
        spectra = [self.spectra[self._row_spectrum(r)] for r in rows]
        if number is None:
            choices = cbv.name_number_choices(spectra)
            example = str(spectra[0].get('label', '')) if spectra else ''
            texts = [t for _, t in choices]
            text, ok = QInputDialog.getItem(
                self, "Fill from the names",
                f"Which number of the name? (e.g. in “{example}”: "
                f"{', '.join(sp.value_text(v) for v in cbv.numbers_in(example)) or 'none'})",
                texts, 0, False)
            if not ok:
                return False
            number = choices[texts.index(text)][0]
        values = sp.from_name(spectra, number)
        self._fill_column(col, values, rows)
        missing = sum(v is None for v in values)
        if missing:
            self.summary.setText(self.summary.text() + f" {missing} name(s) have no such number.")
        return True

    def fill_series(self, start=None, step=None):
        col = self._current_column()
        if col is None:
            col = 1 if self.add_property() else None
            if col is None:
                return False
        rows = self._target_rows()
        if start is None:
            dlg = QDialog(self)
            dlg.setWindowTitle("Fill a series")
            form = QFormLayout(dlg)
            start_box, step_box = QDoubleSpinBox(), QDoubleSpinBox()
            for box, v in ((start_box, 0.0), (step_box, 1.0)):
                box.setRange(-1e12, 1e12)
                box.setDecimals(6)
                box.setValue(v)
            form.addRow("Start:", start_box)
            form.addRow("Step:", step_box)
            form.addRow(QLabel(f"{len(rows)} rows, from the top of the table down."))
            bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            bb.accepted.connect(dlg.accept)
            bb.rejected.connect(dlg.reject)
            form.addRow(bb)
            if not dlg.exec_():
                return False
            start, step = start_box.value(), step_box.value()
        self._fill_column(col, sp.series(len(rows), start, step), rows)
        return True

    def paste(self):
        text = QApplication.clipboard().text()
        if not text.strip():
            return 0
        lines = [line for line in text.replace('\r', '').split('\n')]
        while lines and not lines[-1].strip():
            lines.pop()
        r0 = max(self.table.currentRow(), 0)
        c0 = self._current_column()
        if c0 is None:
            return 0
        self.table.blockSignals(True)
        n = 0
        try:
            for dr, line in enumerate(lines):
                for dc, cell in enumerate(line.split('\t')):
                    r, c = r0 + dr, c0 + dc
                    if r < self.table.rowCount() and c < self.table.columnCount():
                        item = QTableWidgetItem(cell.strip())
                        item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                        self.table.setItem(r, c, item)
                        n += 1
        finally:
            self.table.blockSignals(False)
        self._changed()
        return n

    def clear_cells(self):
        self.table.blockSignals(True)
        try:
            for index in self.table.selectedIndexes():
                if index.column() >= 1:
                    self.table.setItem(index.row(), index.column(), QTableWidgetItem(''))
        finally:
            self.table.blockSignals(False)
        self._changed()

    # -- apply / close
    def apply(self):
        values, problems = self.values()
        if problems or self.apply_callback is None:
            return False
        ok, message = self.apply_callback(self.spectra, values)
        if ok:
            for s, v in zip(self.spectra, values):        # what is stored now
                sp.apply_to(s, v)
            self._changed()
        self.summary.setText(message)
        return ok

    def reject(self):
        if self.apply_button.isEnabled():
            answer = QMessageBox.question(
                self, "Spectrum properties", "Apply the changed values before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
            if answer == QMessageBox.Cancel:
                return
            if answer == QMessageBox.Yes and not self.apply():
                return
        super().reject()

    def show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Spectrum properties – help")
        dlg.resize(640, 460)
        v = QVBoxLayout(dlg)
        text = QTextBrowser()
        text.setHtml(HELP_HTML)
        v.addWidget(text)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.close)
        v.addWidget(bb)
        self.help_window = dlg
        dlg.show()
        return dlg
