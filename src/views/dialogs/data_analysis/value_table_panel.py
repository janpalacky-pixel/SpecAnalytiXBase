# src/views/dialogs/data_analysis/value_table_panel.py
"""The Data table's second tab, "Values per spectrum": one row per spectrum,
columns of values (Add value...), formula columns, copy / export, and a plot
of one column against another. The table is src/modules/data_analysis/value_table.py."""

import numpy as np
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt5.QtGui import QBrush, QColor, QKeySequence, QStandardItem
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                             QShortcut, QSpinBox, QTableView, QToolButton, QVBoxLayout, QWidget)

from src.modules.data_analysis.value_table import VALUE_SECTIONS, ValueTable
from src.modules.visualization_analysis import group_values as gv

_COLOURS = {'value': QColor('#E3F2FD'), 'band': QColor('#E3F2FD'), 'formula': QColor('#E8F5E9'),
            'metadata': QColor('#F2F4F7'), 'number': QColor('#F2F4F7')}


class ValueTableModel(QAbstractTableModel):

    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table
        self.header = None              # the view's heading: titles fitted to the column widths

    def _fit(self, text, section):
        if self.header is None:
            return text
        from PyQt5.QtGui import QFontMetrics
        width = max(self.header.sectionSize(section) - 12, 20)
        return QFontMetrics(self.header.font()).elidedText(text, Qt.ElideRight, width)

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
        v = self.table.value(index.row(), index.column())
        if role == Qt.DisplayRole:
            if isinstance(v, str):
                return v
            return f'{v:.6g}' if np.isfinite(v) else '—'
        if role == Qt.TextAlignmentRole and col.kind != 'name':
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.BackgroundRole and col.kind in _COLOURS:
            return QBrush(_COLOURS[col.kind])
        if role == Qt.ToolTipRole and col.kind == 'name':
            return v
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Vertical:
            return f'sp{section + 1}' if role == Qt.DisplayRole else None
        col = self.table.columns[section]
        if role == Qt.DisplayRole:
            return col.title if col.kind == 'name' else f'{col.name}\n{self._fit(col.title, section)}'
        if role == Qt.ToolTipRole:
            return (f'{col.name} = {col.formula}' if col.kind == 'formula'
                    else f'{col.name}: {col.title}')
        return None


class ValueChoiceDialog(QDialog):
    """Add value...: which value of every spectrum (as in Group Statistics)."""

    def __init__(self, parent, spectra):
        super().__init__(parent)
        self.setWindowTitle("Add a value per spectrum")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        xs = [np.asarray(s['x_scale'], float) for s in spectra if len(s['x_scale'])]
        lo = float(min(x.min() for x in xs)) if xs else 0.0
        hi = float(max(x.max() for x in xs)) if xs else 1.0
        layout = QVBoxLayout(self)
        intro = QLabel("The same values as in Group Statistics, computed for every selected "
                       "spectrum. A spectrum that does not cover the range gets no value (—).")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.kind = QComboBox()
        model = self.kind.model()
        for title, items in VALUE_SECTIONS:
            head = QStandardItem(title)
            head.setFlags(Qt.NoItemFlags)
            model.appendRow(head)
            for key, text in items:
                self.kind.addItem('   ' + text, key)
        self.kind.setCurrentIndex(self.kind.findData('area'))
        form.addRow("Value:", self.kind)

        def spin(value, decimals=3):
            box = QDoubleSpinBox()
            box.setRange(-1e9, 1e9)
            box.setDecimals(decimals)
            box.setValue(value)
            return box
        self.x0 = spin((lo + hi) / 2)
        self.x_mode = QComboBox()
        for k, t in gv.X_MODES.items():
            self.x_mode.addItem(t, k)
        self.halfwidth = spin(5.0)
        self.a_from, self.a_to = spin(lo), spin(hi)
        self.b_from, self.b_to = spin(lo), spin(hi)
        self.metric_a, self.metric_b = QComboBox(), QComboBox()
        for box in (self.metric_a, self.metric_b):
            box.addItems(gv.BAND_METRICS)
        self.operation = QComboBox()
        self.operation.addItems(gv.OPERATIONS)
        self.max_mode = QComboBox()
        for k, t in gv.MAX_MODES.items():
            self.max_mode.addItem(t, k)
        self.component = QSpinBox()
        self.component.setRange(1, 50)
        self.whole_range = QCheckBox("only within range A")

        def pair(a, b):
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(a)
            h.addWidget(QLabel("to"))
            h.addWidget(b)
            return w
        self.rows = {
            'x0': ("At x:", self.x0), 'x_mode': ("Taken as:", self.x_mode),
            'halfwidth': ("w:", self.halfwidth),
            'metric_a': ("Band A:", self.metric_a), 'range_a': ("Range:", pair(self.a_from, self.a_to)),
            'metric_b': ("Band B:", self.metric_b), 'range_b': ("Range B:", pair(self.b_from, self.b_to)),
            'operation': ("Combine:", self.operation), 'max_mode': ("Maximum as:", self.max_mode),
            'component': ("Component:", self.component), 'whole_range': ("", self.whole_range),
        }
        for label, w in self.rows.values():
            form.addRow(label, w)
        self.form = form
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for w in (self.kind, self.x_mode, self.metric_a, self.metric_b):
            w.currentIndexChanged.connect(self._show_rows)
        self.whole_range.toggled.connect(self._show_rows)
        self._show_rows()

    def _visible(self):
        s = self.settings()
        k = s['kind']
        show = set()
        if k == 'intensity_at_x':
            show |= {'x0', 'x_mode'} | ({'halfwidth'} if s['x_mode'] != 'point' else set())
        elif k in gv.ONE_BAND:
            show.add('range_a')
        elif k in gv.TWO_BANDS:
            show |= {'metric_a', 'range_a', 'metric_b', 'range_b', 'operation'}
        elif k in ('pca', 'svd'):
            show |= {'component', 'whole_range'} | ({'range_a'} if s['whole_use_range'] else set())
        if gv.uses_max_mode(s):
            show.add('max_mode')
        return show

    def _show_rows(self, *_):
        show = self._visible()
        label = self.form.labelForField(self.rows['range_a'][1])
        if label is not None:
            label.setText("Range A:" if 'range_b' in show else "Range:")
        for key, (_label, w) in self.rows.items():
            w.setVisible(key in show)
            label = self.form.labelForField(w)
            if label is not None:
                label.setVisible(key in show)
        self.adjustSize()

    def settings(self):
        return {
            'kind': self.kind.currentData() or 'area', 'x0': self.x0.value(),
            'x_mode': self.x_mode.currentData(), 'x_halfwidth': self.halfwidth.value(),
            'max_mode': self.max_mode.currentData(),
            'range_a': (self.a_from.value(), self.a_to.value()),
            'range_b': (self.b_from.value(), self.b_to.value()),
            'metric_a': self.metric_a.currentText(), 'metric_b': self.metric_b.currentText(),
            'operation': self.operation.currentText(), 'component': self.component.value(),
            'whole_use_range': self.whole_range.isChecked(),
        }


class ValuePlotDialog(QDialog):
    """One column against another (e.g. area against temperature)."""

    def __init__(self, parent, table, x_name, y_name):
        super().__init__(parent)
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
        from matplotlib.figure import Figure
        x, y, labels = table.xy(x_name, y_name)
        head = dict(zip([c.name for c in table.columns], table.header()[1:]))
        self.setWindowTitle(f"{y_name} against {x_name}")
        self.setWindowFlags((self.windowFlags() | Qt.WindowMaximizeButtonHint)
                            & ~Qt.WindowContextHelpButtonHint)
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        layout.addWidget(self.canvas, 1)
        ax = self.figure.add_subplot(111)
        order = np.argsort(x)
        ax.plot(x[order], y[order], '-', color='#9DB7DD', lw=1, zorder=1)
        ax.plot(x, y, 'o', color='#1F77B4', ms=5, zorder=2)
        ax.set_xlabel(head.get(x_name, x_name))
        ax.set_ylabel(head.get(y_name, y_name))
        ax.grid(alpha=0.3)
        n_all = table.n_rows
        note = QLabel(f"{len(x)} of {n_all} spectra have both values." if len(x) < n_all
                      else f"{len(x)} spectra.")
        layout.addWidget(note)
        self.figure.tight_layout()
        self.points = (x, y)


class ValueTablePanel(QWidget):

    def __init__(self, parent, spectra):
        super().__init__(parent)
        self.table = ValueTable.from_spectra(spectra)
        layout = QVBoxLayout(self)
        self.model = ValueTableModel(self.table, self)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.horizontalHeader().setDefaultSectionSize(120)
        self.view.horizontalHeader().resizeSection(0, 240)
        self.view.verticalHeader().setDefaultSectionSize(22)
        layout.addWidget(self.view, 1)
        QShortcut(QKeySequence.Copy, self.view, activated=self.copy_selection)
        self.model.header = self.view.horizontalHeader()
        self.view.horizontalHeader().sectionResized.connect(
            lambda section, *_: self.model.headerDataChanged.emit(Qt.Horizontal, section, section))

        row = QHBoxLayout()
        self.add_value_button = QPushButton("Add value…")
        self.add_value_button.setToolTip("A column of one value per spectrum: area or mean over a "
                                         "range, maximum, peak position, FWHM, fitted peak, "
                                         "intensity at x, two bands, PCA score …")
        self.add_value_button.clicked.connect(lambda: self.add_value())   # not clicked(False) as settings
        row.addWidget(self.add_value_button)
        row.addSpacing(12)
        row.addWidget(QLabel("New column ="))
        self.formula_edit = QLineEdit()
        self.formula_edit.setPlaceholderText("a formula of the columns, e.g. v1 / v2   or   v1 / temperature_C")
        self.formula_edit.returnPressed.connect(self.add_formula)
        row.addWidget(self.formula_edit, 3)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("optional name")
        self.name_edit.returnPressed.connect(self.add_formula)
        row.addWidget(self.name_edit, 1)
        self.add_formula_button = QPushButton("Add column")
        self.add_formula_button.clicked.connect(self.add_formula)
        row.addWidget(self.add_formula_button)
        layout.addLayout(row)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy")
        self.copy_button.setToolTip("Copy the selected cells (or the whole table) with the column "
                                    "names, e.g. into Excel")
        self.copy_button.clicked.connect(self.copy_selection)
        self.export_button = QPushButton("Export…")
        self.export_button.clicked.connect(self.export)
        self.remove_button = QPushButton("Remove column")
        self.remove_button.setToolTip("Remove the selected value or formula column(s)")
        self.remove_button.clicked.connect(self.remove_selected_columns)
        for b in (self.copy_button, self.export_button, self.remove_button):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(QLabel("Plot"))
        self.y_combo, self.x_combo = QComboBox(), QComboBox()
        buttons.addWidget(self.y_combo)
        buttons.addWidget(QLabel("against"))
        buttons.addWidget(self.x_combo)
        self.plot_button = QPushButton("Plot")
        self.plot_button.setToolTip("Plot one column against another, e.g. an area against the "
                                    "temperature")
        self.plot_button.clicked.connect(self.plot)
        buttons.addWidget(self.plot_button)
        layout.addLayout(buttons)
        for b in (self.copy_button, self.export_button, self.remove_button, self.plot_button,
                  self.add_value_button, self.add_formula_button):
            b.setAutoDefault(False)
        self._update()

    # -- helpers
    def _say(self, text, error=False):
        self.message.setText(text)
        self.message.setStyleSheet("color: #C62828;" if error else "color: #2E7D32;")

    def _update(self):
        names = [c.name for c in self.table.numeric_columns()]
        for box, prefer in ((self.x_combo, 0), (self.y_combo, -1)):
            keep = box.currentText()
            box.blockSignals(True)
            box.clear()
            box.addItems(names)
            if keep in names:
                box.setCurrentText(keep)
            elif names:
                box.setCurrentIndex(prefer % len(names))
            box.blockSignals(False)
        self.plot_button.setEnabled(len(names) >= 1)
        self.remove_button.setEnabled(any(c.kind in ('value', 'band', 'formula')
                                          for c in self.table.columns))

    # -- columns
    def add_value(self, settings=None):
        if settings is None:
            dlg = ValueChoiceDialog(self, self.table.spectra)
            if dlg.exec_() != QDialog.Accepted:
                return None
            settings = dlg.settings()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            col = self.table.add_value(settings)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            self._say(f"The value could not be computed: {exc}", error=True)
            return None
        QApplication.restoreOverrideCursor()
        self.model.refresh()
        missing = int((~np.isfinite(col.values)).sum())
        note = (f" {missing} spectr{'um has' if missing == 1 else 'a have'} no value (—)."
                if missing else "")
        notes = ' '.join(self.table.notes[-1:]) if missing == len(col.values) else ''
        self._say(f"Added {col.name}: {col.title}.{note} {notes}".strip(), error=bool(missing))
        self._update()
        self.y_combo.setCurrentText(col.name)          # ready to plot the new column
        return col

    def add_bands(self, value_name, bands):
        """The bands of the Peak list's Band table as columns b1, b2, ..."""
        added = self.table.add_bands(value_name, bands)
        self.model.refresh()
        self._update()
        if added:
            names = added[0].name if len(added) == 1 else f"{added[0].name}–{added[-1].name}"
            self._say(f"{names}: {value_name.split(' (')[0]} of each band from the Peak list "
                      f"({len(added)} band{'s' if len(added) != 1 else ''}; empty: no peak there). "
                      "Use them in formulas (e.g. b2 / b1) or plot them against a stored value.")
        return added

    def add_formula(self):
        try:
            cols = self.table.add_formulas(self.formula_edit.text(), self.name_edit.text())
        except ValueError as exc:
            self._say(str(exc), error=True)
            return None
        self.model.refresh()
        self._say("Added " + ', '.join(f"{c.name} = {c.formula}" for c in cols) + '.')
        self.formula_edit.clear()
        self.name_edit.clear()
        self._update()
        self.y_combo.setCurrentText(cols[-1].name)
        return cols[-1]

    def remove_selected_columns(self):
        names = [self.table.columns[c].name
                 for c in sorted({i.column() for i in self.view.selectionModel().selectedIndexes()})
                 if self.table.columns[c].kind in ('value', 'band', 'formula')]
        if not names:
            self._say("Select a cell of a value or band (blue) or formula (green) column to remove "
                      "it.",
                      error=True)
            return
        try:
            for name in reversed(names):
                self.table.remove_column(name)
        except ValueError as exc:
            self._say(str(exc), error=True)
        self.model.refresh()
        self._update()

    # -- copy, export, plot
    def copy_selection(self):
        indexes = self.view.selectionModel().selectedIndexes()
        if indexes:
            rows = sorted({i.row() for i in indexes})
            cols = sorted({i.column() for i in indexes})
        else:
            rows, cols = None, None
        QApplication.clipboard().setText(self.table.rows_as_text(rows, cols))
        self._say("Copied (with the column names).")

    def export(self):
        path, chosen = QFileDialog.getSaveFileName(
            self, "Export the values per spectrum", "values_per_spectrum.xlsx",
            "Excel (*.xlsx);;CSV (*.csv);;Text, tab-separated (*.txt)")
        if not path:
            return None
        if '.' not in path.replace('\\', '/').split('/')[-1]:
            path += {'CSV': '.csv', 'Text': '.txt'}.get(chosen.split(' ')[0], '.xlsx')
        try:
            self.table.export(path)
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"The table could not be saved:\n\n{exc}")
            return None
        self._say(f"Saved: {path}")
        return path

    def plot(self):
        x_name, y_name = self.x_combo.currentText(), self.y_combo.currentText()
        try:
            dlg = ValuePlotDialog(self, self.table, x_name, y_name)
        except ValueError as exc:
            self._say(str(exc), error=True)
            return None
        if not len(dlg.points[0]):
            self._say(f"No spectrum has both {x_name} and {y_name}.", error=True)
            return None
        self.plot_dialog = dlg
        dlg.show()
        return dlg
