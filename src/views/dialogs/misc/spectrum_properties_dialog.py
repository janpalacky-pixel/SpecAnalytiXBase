# src/views/dialogs/misc/spectrum_properties_dialog.py
"""Right-click on the spectra list -> Spectrum properties...: a table with one
row per spectrum and one column per property (temperature, pH,
concentration, ...). Type the values, paste a column from Excel, fill them
from the names, as a series or from a table file; Apply stores them (one step in the
Operations History, so Undo takes it back).
src/modules/misc/spectrum_properties.py."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog,
                             QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                             QHBoxLayout,
                             QHeaderView, QInputDialog, QLabel, QListWidget,
                             QMessageBox, QPushButton,
                             QShortcut, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout)

from src.modules.misc import spectrum_properties as sp
from src.modules.visualization import color_by_value as cbv
from src.views import icons

_BAD = QColor('#ffcdd2')

HELP_HTML = """
<p><b>Spectrum properties</b> are numbers that belong to each spectrum: temperature, pH,
concentration, time, &hellip; They are used by <i>Line colours &rsaquo; Colours by value</i>,
the <i>Data table</i> (tab Values per spectrum, also in its formulas), the plot of the
<i>Peak list</i>, <i>Melting Curve Analysis</i> (X from) and <i>Group Statistics</i> (groups From a
property). Values read from the file (e.g. <code>temperature_C</code> of a JASCO
temperature scan) are shown too and can be corrected.</p>
<ul>
<li><b>Type</b> a value into a cell (a decimal comma is fine). An empty cell = no value.
<b>Delete</b> empties the selected cells.</li>
<li><b>Paste</b> (Ctrl+V) a column copied from Excel: it fills the cells from the current one
downward (several columns fill several properties).</li>
<li><b>Add property&hellip;</b>: a new column. Type its name (completed from the suggestions), pick
it with the &#9662; arrow of the field, or click it in the list (double-click adds it). It starts with
a letter and has only letters, digits and _ (e.g. <code>concentration_mM</code>), so it also works
in formulas.</li>
<li><b>Fill from the names&hellip;</b>: e.g. 45 from <code>TBA_45C</code> &mdash; choose which number
of the name. <b>Fill a series&hellip;</b>: start and step, e.g. 20, 25, 30, &hellip; in the order of
the table (sort it first by clicking a heading if needed). Both fill the selected rows of the
current column, or all rows when none is selected.</li>
<li><b>Fill from a file&hellip;</b>: a table in Excel, CSV or TXT &mdash; the spectrum names in
the first column, then one column per property with its name in the first row, e.g.
<pre>spectrum     pH    temperature_C
control_01   7.4   25
control_02   7.4   30</pre>
Each spectrum is looked for under its names in this order: its <b>full name</b> as in the
list (<code>day1 : control_01</code>), its <b>original name</b> (before a rename), then its
<b>short name</b> &mdash; the part after &ldquo; : &rdquo;, the column name in the data file
(<code>control_01</code>). Case, spaces and punctuation do not matter (<code>Control 01</code> =
<code>control_01</code>). When it is not clear, nothing is filled and the window says why: a name
that is in the table twice, or a short name that fits several spectra (<code>control_01</code>
when the list holds <code>day1 : control_01</code> and <code>day2 : control_01</code> &mdash; write
the full names in the table then). A new property gets a column (a heading like
<i>Temperature (&deg;C)</i> becomes <code>Temperature_C</code>); only the spectra in the table and
the cells with a number change: a cell that is not a number (e.g. <i>n.d.</i>) and a column of
text (e.g. notes) are left out. Excel: the sheet <i>Properties</i> if there is one, else the first
sheet.<br>
A window says what was filled and, line by line, what was not used and why.<br>
<b>Example:</b> load <i>Help &rsaquo; Test datasets &rsaquo; Synthetic &rsaquo; Group Statistics
&rsaquo; three treatment groups</i>, select all, open this window and fill it from the example
table: <a href="example:save">save a copy of the example table&hellip;</a> &middot;
<a href="example:open">open it</a> (Excel; also as <a href="example:save-csv">CSV&hellip;</a>).
The example contains on purpose a row <i>ghost_99</i> (no such spectrum), a cell <i>n.d.</i> (not a
number) and a text column <i>note</i>, to show what is left out.</li>
<li><b>Sort</b>: click a heading (values as numbers, empty cells last; names naturally).</li>
<li><b>Remove property</b> empties its whole column (removed on Apply).</li>
<li><b>Apply</b> stores the values. It is one step in the Operations History, so <b>Undo</b>
takes it back; snapshots keep the values.</li>
</ul>
"""


def _natural_key(text):
    """'raman_2' before 'raman_10': the numbers in a text compared as numbers."""
    import re
    return [(0, float(part), '') if part[:1].isdigit() else (1, 0.0, part.lower())
            for part in re.split(r'(\d+(?:\.\d+)?)', str(text)) if part]


class _NameItem(QTableWidgetItem):
    """A spectrum name; sorts naturally (raman_2 before raman_10)."""

    def __lt__(self, other):
        return _natural_key(self.text()) < _natural_key(other.text())


class _ValueItem(QTableWidgetItem):
    """A value cell; sorts by the number (2 before 10), empty or not-a-number
    cells after the numbers."""

    def __lt__(self, other):
        def key(item):
            try:
                v = sp.parse_value(item.text())
            except ValueError:
                v = None
            return (0, v) if v is not None else (1, 0.0)
        return key(self) < key(other)


class AddPropertyDialog(QDialog):
    """The name of a new property, three ways: type it (a suggestion is
    completed while typing), pick it with the arrow of the field, or click it
    in the list below (a double-click adds it at once). Add is possible only
    for a good name; what is wrong is said at once below the field (no
    message box afterwards)."""

    def __init__(self, parent, suggestions, check):
        super().__init__(parent)
        self.check = check                  # name -> None, or why it cannot be used
        self.setWindowTitle("Add property")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        v = QVBoxLayout(self)
        intro = QLabel("A property is one number for each spectrum (e.g. its temperature, pH or "
                       "concentration). Type a name (it is completed from the suggestions), pick one "
                       "with the arrow, or click one in the list:")
        intro.setWordWrap(True)
        v.addWidget(intro)
        form = QFormLayout()
        self.name_box = QComboBox()
        self.name_box.setEditable(True)
        self.name_box.setInsertPolicy(QComboBox.NoInsert)
        self.name_box.addItems(suggestions)
        self.name_box.setCurrentIndex(-1)            # empty at the start
        self.name_edit = self.name_box.lineEdit()    # completes the suggestions while typing
        self.name_edit.setPlaceholderText("type a name, or pick one with the arrow")
        form.addRow("Name:", self.name_box)
        # the suggestions as a visible list (a drop-down arrow is easy to miss)
        self.suggestion_list = QListWidget()
        self.suggestion_list.addItems(suggestions)
        self.suggestion_list.setMaximumHeight(130)
        self.suggestion_list.setToolTip("Click: put the name into the field. Double-click: add it.")
        self.suggestion_list.itemClicked.connect(lambda item: self.name_box.setEditText(item.text()))
        self.suggestion_list.itemDoubleClicked.connect(
            lambda item: (self.name_box.setEditText(item.text()), self.accept()))
        form.addRow("Suggestions:", self.suggestion_list)
        v.addLayout(form)
        rule = QLabel("Letters, digits and _ only (no spaces), starting with a letter – so the "
                      "name also works in the formulas of the Data table.")
        rule.setWordWrap(True)
        rule.setStyleSheet("color: grey;")
        v.addWidget(rule)
        self.problem = QLabel("")
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet("color: #C62828;")
        v.addWidget(self.problem)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = self.buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Add")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        v.addWidget(self.buttons)
        self.name_box.editTextChanged.connect(self._check)
        self._check()
        self.resize(460, self.sizeHint().height())
        self.name_box.setFocus()

    def name(self):
        return self.name_box.currentText().strip()

    def _check(self, *_):
        """Add only for a good name; the reason shown at once (not for an
        empty field - there is nothing wrong yet)."""
        problem = self.check(self.name())
        empty = not self.name()
        self.ok_button.setEnabled(not problem)
        self.problem.setText("" if empty else (problem or ""))
        return problem

    def accept(self):
        if not self._check():
            super().accept()


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
                       "time… They are used by Colours by value, the Data table, the Peak list plot, "
                       "Melting Curve Analysis and Group Statistics. Type, paste (Ctrl+V) or fill "
                       "them; an empty cell = no value.")
        intro.setWordWrap(True)
        top.addWidget(intro, 1)
        self.help_button = icons.help_button("How to set the properties")
        self.help_button.clicked.connect(self.show_help)
        top.addWidget(self.help_button, 0, Qt.AlignTop)
        layout.addLayout(top)

        tools = QHBoxLayout()
        self.add_button = QPushButton("Add property…")
        self.add_button.clicked.connect(lambda: self.add_property())   # not clicked(False) as an argument
        self.remove_button = QPushButton("Remove property")
        self.remove_button.setToolTip("Empty the whole current column (removed on Apply)")
        self.remove_button.clicked.connect(self.remove_property)
        self.name_button = QPushButton("Fill from the names…")
        self.name_button.setToolTip("A number written in the names, e.g. 45 from TBA_45C")
        self.name_button.clicked.connect(lambda: self.fill_from_names())   # not clicked(False) as an argument
        self.series_button = QPushButton("Fill a series…")
        self.series_button.setToolTip("start, start + step, start + 2 step, … down the table")
        self.series_button.clicked.connect(lambda: self.fill_series())   # not clicked(False) as an argument
        self.file_button = QPushButton("Fill from a file…")
        self.file_button.setToolTip("A table (Excel, CSV, TXT): the spectrum names in the first "
                                    "column, then one column per property with its name in the "
                                    "first row")
        self.file_button.clicked.connect(lambda: self.fill_from_file())   # not clicked(False) as an argument
        for b in (self.add_button, self.remove_button, self.name_button, self.series_button,
                  self.file_button):
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
            name = _NameItem(str(s.get('label', '')))
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
                item = _ValueItem(sp.value_text(v))
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
            self.summary.setText("No properties yet. Start with Add property… (e.g. pH): it "
                                 "makes a column; then type the values, paste them from Excel "
                                 "or use Fill from the names… / Fill a series…, and Apply. "
                                 "Fill from a file… reads a whole table (names + properties).")
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
        """A new empty column. Without a name the Add property window asks
        for it (the button must call it without arguments: clicked(False)
        would arrive as the name)."""
        if name is None:
            dlg = AddPropertyDialog(self, [k for k in sp.SUGGESTED if k not in self.keys],
                                    lambda n: sp.check_name(n, self.spectra, self.keys))
            if dlg.exec_() != QDialog.Accepted:
                return None
            name = dlg.name()
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
        self.table.clearSelection()     # the new column is current; Fill… fills all its rows
        self.summary.setText(f"Added “{name}”: type its values into the column, paste them "
                             "(Ctrl+V) or use Fill from the names… / Fill a series…; then Apply.")
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
        """Fill the current column (selected rows, or all) with a number from
        the spectrum names; without `number` it asks which one (last, first, ...)."""
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

    def fill_from_file(self, path=None):
        """Fill properties from a table file: the spectrum names in the first
        column, one column per property (its name in the first row). New
        properties get a column; only the spectra found in the table and
        the cells with a number change. Nothing is stored until Apply.
        Returns the result of sp.from_table (None if cancelled or unreadable)."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Fill from a file", "", sp.TABLE_FILTER)
            if not path:
                return None
        try:
            header, rows = sp.read_table(path)
        except Exception as exc:
            QMessageBox.warning(self, "Fill from a file", f"The table could not be read:\n{exc}")
            return None
        result = sp.from_table(self.spectra, header, rows)
        where = {self._row_spectrum(r): r for r in range(self.table.rowCount())}
        for key in result['keys']:
            if key not in self.keys:
                self.keys.append(key)
                col = self.table.columnCount()
                self.table.insertColumn(col)
                self._set_headers()
                self._fill_column(col, [None] * len(self.spectra))
            col = self.keys.index(key) + 1
            pairs = [(where[i], v) for i, v in enumerate(result['values'][key]) if v is not None]
            if pairs:
                self._fill_column(col, [v for _, v in pairs], [r for r, _ in pairs])
        report = sp.table_report(result)
        diff = self._changed()
        if result['keys']:
            change = (f"{len(diff)} value(s) will change \u2013 Apply stores them."
                      if diff else "Nothing changed: the values are already there.")
            report += "\n" + change
            self.summary.setText(f"From the file: {result['found']} of {len(self.spectra)} "
                                 f"spectra. {change}")
        else:
            self.summary.setText(report.split('\n')[0])
        if result['keys']:
            QMessageBox.information(self, "Fill from a file", report)
        else:
            QMessageBox.warning(self, "Fill from a file", report)
        return result

    def paste(self):
        """Ctrl+V: a block copied from Excel fills the cells from the current
        one down (and right, for several columns)."""
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
                        item = _ValueItem(cell.strip())
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
                    self.table.setItem(index.row(), index.column(), _ValueItem(''))
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

    EXAMPLE = 'resources/test_data/examples/treatment_properties'

    def example_link(self, link, target=None):
        """The links of the help: example:save / example:save-csv - a copy of
        the example table where the user wants it; example:open - open it
        (Excel). Returns the path saved or opened (None if cancelled)."""
        import os
        import shutil
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        from src.modules.utils.resource_path import resource_path
        ext = '.csv' if link == 'example:save-csv' else '.xlsx'
        source = resource_path(self.EXAMPLE + ext)
        if link == 'example:open':
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(source)))
            return source
        if link not in ('example:save', 'example:save-csv'):
            return None
        if target is None:
            target, _ = QFileDialog.getSaveFileName(
                self, "Save a copy of the example table", os.path.basename(source),
                "CSV (*.csv)" if ext == '.csv' else "Excel (*.xlsx)")
            if not target:
                return None
        try:
            shutil.copyfile(source, target)
        except OSError as exc:
            QMessageBox.warning(self, "Example table", f"It could not be saved:\n{exc}")
            return None
        return target

    def show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Spectrum properties – help")
        dlg.resize(640, 460)
        v = QVBoxLayout(dlg)
        text = QTextBrowser()
        text.setOpenLinks(False)                     # the example links are handled here
        text.anchorClicked.connect(lambda url: self.example_link(url.toString()))
        text.setHtml(HELP_HTML)
        v.addWidget(text)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.close)
        v.addWidget(bb)
        self.help_window = dlg
        dlg.show()
        return dlg
