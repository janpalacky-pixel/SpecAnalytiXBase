# src/views/dialogs/visualization_analysis/group_statistics_dialog.py
"""Analysis & Visualization -> Data Analysis -> Group Statistics.

1. Groups: every selected spectrum gets a group (table, editable), set by
   hand for selected rows, from the names (contains / part of the name) or
   from a table file.
2. Value: one number per spectrum (intensity at x, mean / area / maximum
   over a range, band ratio).
3. Compute: box plot with every value, summary per group, the test
   (Welch t / ANOVA or Mann-Whitney / Kruskal-Wallis, with Holm-corrected
   pairs and effect sizes), the values table; Export to CSV or Excel.
See src/modules/visualization_analysis/group_statistics.py.
"""

import html
import os

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from src.modules.utils.app_logger import get_logger
from src.modules.visualization_analysis import group_statistics as gs
from src.views.dialogs.misc.fill_column_table import FillColumnTable

logger = get_logger(__name__)

_GROUP_COLOURS = ['#1565C0', '#C62828', '#2E7D32', '#EF6C00', '#6A1B9A', '#00838F',
                  '#AD1457', '#5D4037', '#455A64', '#9E9D24']


class NamesToGroupsDialog(QDialog):
    """Groups from the spectrum names: 'contains' rules or a part of the name."""

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Groups from spectrum names")
        self.labels = list(labels)
        layout = QVBoxLayout(self)
        self.root_radio = QRadioButton("Common root name (as in Select / Rename)")
        self.root_radio.setToolTip(
            "Group = the name without its numbering, e.g.\n"
            "  Chlorella [r24_c14]  \u2192 Chlorella\n"
            "  CD_spectra_TBA : 0019 \u2192 CD_spectra_TBA\n"
            "  sample_012  \u2192 sample")
        self.contains_radio = QRadioButton("Name contains a text")
        self.part_radio = QRadioButton("A part of the name")
        modes = QButtonGroup(self)
        modes.addButton(self.root_radio)
        modes.addButton(self.contains_radio)
        modes.addButton(self.part_radio)
        self.root_radio.setChecked(True)

        layout.addWidget(self.root_radio)
        layout.addWidget(self.contains_radio)
        self.rules_edit = QPlainTextEdit()
        self.rules_edit.setPlaceholderText(
            "One rule per line:  text = group name\n"
            "e.g.\n  ctrl = Control\n  treat = Treated\n"
            "(or just the text: it becomes the group name). The first matching rule wins; "
            "upper/lower case is ignored.")
        self.rules_edit.setFixedHeight(110)
        layout.addWidget(self.rules_edit)

        layout.addWidget(self.part_radio)
        part_row = QHBoxLayout()
        part_row.addWidget(QLabel("Split the name at:"))
        self.separators_edit = QLineEdit("_")
        self.separators_edit.setMaximumWidth(60)
        self.separators_edit.setToolTip("One or more separator characters, e.g. _ or _- or a space")
        part_row.addWidget(self.separators_edit)
        part_row.addWidget(QLabel("and use part number:"))
        self.part_spin = QSpinBox()
        self.part_spin.setRange(-20, 20)
        self.part_spin.setValue(1)
        self.part_spin.setToolTip("1 = first part, 2 = second, ...; -1 = last part")
        part_row.addWidget(self.part_spin)
        part_row.addStretch(1)
        layout.addLayout(part_row)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("color:#555;")
        layout.addWidget(self.preview)
        for signal in (self.rules_edit.textChanged, self.separators_edit.textChanged,
                       self.part_spin.valueChanged, self.contains_radio.toggled,
                       self.root_radio.toggled):
            signal.connect(self._update_preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(480, 420)
        self._update_preview()

    def rules(self):
        rules = []
        for line in self.rules_edit.toPlainText().splitlines():
            if not line.strip():
                continue
            text, _, group = line.partition('=')
            rules.append((text.strip(), group.strip() or text.strip()))
        return rules

    def groups(self):
        if self.root_radio.isChecked():
            return gs.groups_from_root_name(self.labels)
        if self.contains_radio.isChecked():
            return gs.groups_from_contains(self.labels, self.rules())
        return gs.groups_from_part(self.labels, self.separators_edit.text() or '_',
                                   self.part_spin.value())

    def _update_preview(self, *_):
        groups = self.groups()
        counts = {}
        for g in groups:
            counts[g] = counts.get(g, 0) + 1
        named = [f"{g} ({n})" for g, n in counts.items() if g != gs.NO_GROUP]
        none = counts.get(gs.NO_GROUP, 0)
        text = f"{len(named)} groups: " + ", ".join(named[:12]) + (" …" if len(named) > 12 else "")
        if none:
            text += f"; {none} spectra without a group"
        self.preview.setText(text)


class GroupStatisticsDialog(QDialog):

    def __init__(self, spectra, parent=None, saved_groups=None):
        super().__init__(parent)
        self.setWindowTitle("Group Statistics")
        # Maximize button in the title bar (a plain QDialog has only the
        # close button). No minimize: the window is modal, and a minimized
        # modal window blocks the app while being out of sight, so the app
        # looks frozen (same rule as the other modal windows).
        self.setWindowFlags((self.windowFlags() | Qt.WindowMaximizeButtonHint)
                            & ~Qt.WindowMinimizeButtonHint)
        self.spectra = list(spectra)
        self.labels = [s.get('label', f'Spectrum {i + 1}') for i, s in enumerate(self.spectra)]
        self.saved_groups = saved_groups if saved_groups is not None else {}
        self.comparison = None      # (not "result": that would hide QDialog.result())
        self.values = None
        self.resize(1250, 780)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Compare groups of spectra (e.g. treated vs. control) on one value per spectrum: "
            "1. give the spectra their groups, 2. choose the value, 3. Compute.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_groups_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        layout.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.export_btn = QPushButton("Export…")
        self.export_btn.setToolTip("Save the values, the summary and the tests as CSV or Excel")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export)
        help_btn = QPushButton("Help")
        help_btn.clicked.connect(self.show_help)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(self.export_btn)
        bottom.addStretch(1)
        bottom.addWidget(help_btn)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)
        self._update_group_summary()

    # ------------------------------------------------------------------ groups
    def _build_groups_panel(self):
        box = QGroupBox("1. Groups")
        lay = QVBoxLayout(box)
        # Spreadsheet-like Group column: fill handle, Ctrl+D, copy/paste,
        # Delete, Ctrl+Z (see fill_column_table.py)
        self.table = FillColumnTable(
            self.labels, [self.saved_groups.get(l, gs.NO_GROUP) for l in self.labels],
            headers=("Spectrum", "Group"))
        # Both columns: width adjustable by dragging the header border;
        # the Group column also takes any spare width at the right
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(1, 120)
        self.table.valuesChanged.connect(self._on_groups_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.table.setToolTip(
            "Group column, like a spreadsheet:\n"
            "• type into a cell, or select cells and drag the small green square at the\n"
            "  bottom-right corner down: the value(s) are repeated into those rows\n"
            "• Ctrl+D fills the top selected value down; Ctrl+V pastes a column\n"
            "  (e.g. from Excel); one copied value pasted into several selected rows\n"
            "  fills them all; Delete clears; Ctrl+Z undoes\n"
            "• right-click for more")
        lay.addWidget(self.table, 1)

        row1 = QHBoxLayout()
        set_btn = QPushButton("Set group of selected rows…")
        set_btn.setToolTip("Select rows (click, Shift+click, Ctrl+click), then give them a group")
        set_btn.clicked.connect(self.set_group_of_selected)
        row1.addWidget(set_btn)
        lay.addLayout(row1)
        row2 = QHBoxLayout()
        names_btn = QPushButton("From names…")
        names_btn.setToolTip("Groups from the spectrum names: a text they contain, or a part of the name")
        names_btn.clicked.connect(self.groups_from_names)
        table_btn = QPushButton("From table file…")
        table_btn.setToolTip("A CSV or Excel file with two columns: spectrum name, group")
        table_btn.clicked.connect(self.groups_from_table_file)
        clear_btn = QPushButton("Clear")
        clear_btn.setToolTip("Remove all groups (Ctrl+Z brings them back)")
        clear_btn.clicked.connect(lambda: self._set_groups([gs.NO_GROUP] * len(self.labels)))
        row2.addWidget(names_btn)
        row2.addWidget(table_btn)
        row2.addWidget(clear_btn)
        lay.addLayout(row2)
        self.group_summary = QLabel()
        self.group_summary.setWordWrap(True)
        lay.addWidget(self.group_summary)
        return box

    def groups(self):
        return [v.strip() for v in self.table.values()]

    def _set_groups(self, groups):
        self.table.set_values(groups)          # one undo step; emits valuesChanged

    def _on_groups_changed(self):
        self._remember()
        self._update_group_summary()

    def _table_menu(self, pos):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        rows = self.table.selected_rows()
        set_action = menu.addAction("Set group of selected rows…")
        fill_action = menu.addAction("Fill down (Ctrl+D)")
        menu.addSeparator()
        copy_action = menu.addAction("Copy (Ctrl+C)")
        paste_action = menu.addAction("Paste (Ctrl+V)")
        clear_action = menu.addAction("Clear (Delete)")
        menu.addSeparator()
        select_action = menu.addAction("Select spectra…")
        undo_action = menu.addAction("Undo (Ctrl+Z)")
        for a in (set_action, fill_action, copy_action, clear_action):
            a.setEnabled(bool(rows))
        fill_action.setEnabled(len(rows) > 1)
        undo_action.setEnabled(bool(self.table._undo))
        chosen = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if chosen is set_action:
            self.set_group_of_selected()
        elif chosen is fill_action:
            self.table.fill_down()
        elif chosen is copy_action:
            self.table.copy_values()
        elif chosen is paste_action:
            self.table.paste_values()
        elif chosen is clear_action:
            self.table.clear_values()
        elif chosen is select_action:
            self.select_spectra()
        elif chosen is undo_action:
            self.table.undo()

    def select_spectra(self):
        """Select rows by name, range or step (the main window's Select
        Spectra dialog), e.g. to give every 3rd spectrum a group."""
        from src.views.dialogs.misc.spectra_selection_dialog import SpectraSelectionDialog
        dlg = SpectraSelectionDialog(parent=self, total_spectra=len(self.labels),
                                     title="Select spectra in the table", labels=self.labels)
        if dlg.exec_() != QDialog.Accepted:
            return
        params = dlg.get_selection_parameters() or {}
        from PyQt5.QtCore import QItemSelection, QItemSelectionModel
        model = self.table.model()
        selection = QItemSelection()
        for r in params.get('indices', []):
            if 0 <= r < self.table.rowCount():
                selection.select(model.index(r, 0), model.index(r, 1))
        mode = {'select': QItemSelectionModel.ClearAndSelect, 'add': QItemSelectionModel.Select,
                'remove': QItemSelectionModel.Deselect}.get(params.get('action', 'select'),
                                                            QItemSelectionModel.ClearAndSelect)
        self.table.selectionModel().select(selection, mode)

    def _remember(self):
        for label, g in zip(self.labels, self.groups()):
            if g:
                self.saved_groups[label] = g
            else:
                self.saved_groups.pop(label, None)

    def _group_names(self):
        seen = []
        for g in self.groups():
            if g and g not in seen:
                seen.append(g)
        return seen

    def _update_group_summary(self):
        groups = self.groups()
        counts = {}
        for g in groups:
            counts[g] = counts.get(g, 0) + 1
        named = [f"<b>{g}</b> ({n})" for g, n in counts.items() if g != gs.NO_GROUP]
        none = counts.get(gs.NO_GROUP, 0)
        if not named:
            text = "No groups yet."
        else:
            text = f"{len(named)} group{'s' if len(named) != 1 else ''}: " + ", ".join(named)
        if none:
            text += f"<br>{none} spectr{'um' if none == 1 else 'a'} without a group (left out)."
        self.group_summary.setText(text)

    def set_group_of_selected(self):
        rows = self.table.selected_rows()
        if not rows:
            QMessageBox.information(self, "Group Statistics",
                                    "Select one or more rows in the table first.")
            return
        name, ok = QInputDialog.getItem(self, "Set group", f"Group for {len(rows)} spectra:",
                                        self._group_names() or ["Group 1"], 0, True)
        if not ok:
            return
        self.table.set_rows(rows, name.strip())

    def groups_from_names(self):
        dlg = NamesToGroupsDialog(self.labels, self)
        if dlg.exec_() == QDialog.Accepted:
            self._set_groups(dlg.groups())

    def groups_from_table_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Table of groups", "",
            "Tables (*.csv *.txt *.tsv *.xlsx *.xls);;All files (*)")
        if not path:
            return
        try:
            mapping = gs.read_group_table(path)
        except Exception as exc:
            logger.exception("Reading the group table failed")
            QMessageBox.warning(self, "Group Statistics", f"The table could not be read:\n{exc}")
            return
        groups = gs.groups_from_table(self.labels, mapping)
        found = sum(1 for g in groups if g)
        self._set_groups(groups)
        QMessageBox.information(self, "Group Statistics",
                                f"{found} of {len(groups)} spectra were found in the table.")

    # ------------------------------------------------------------------ value + results
    def _build_right_panel(self):
        right = QWidget()
        lay = QVBoxLayout(right)
        lay.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()

        value_box = QGroupBox("2. Value per spectrum")
        form = QFormLayout(value_box)
        self.kind_combo = QComboBox()
        for key, text in gs.VALUE_KINDS.items():
            self.kind_combo.addItem(text, key)
        self.kind_combo.currentIndexChanged.connect(self._update_value_widgets)
        form.addRow("Value:", self.kind_combo)
        xmin, xmax = self._x_extent()
        self.has_common_range = self._common_range_exists()
        mid, quarter = (xmin + xmax) / 2, (xmax - xmin) / 8 or 1.0
        # Default ranges: one range (mean / area / maximum) = the whole
        # common x-range; band ratio = two neighbouring ranges either side
        # of the middle (A and B use the same "from" / "to" boxes as the
        # single range, so _update_value_widgets swaps between the two
        # defaults as long as the user has not typed a range himself)
        self._single_default = (xmin, xmax)
        self._ratio_default = (mid - quarter, mid)
        self.x_spin = self._spin(mid, xmin, xmax)
        self.x_row = QWidget()
        xr = QHBoxLayout(self.x_row)
        xr.setContentsMargins(0, 0, 0, 0)
        xr.addWidget(self.x_spin)
        xr.addStretch(1)
        form.addRow("x:", self.x_row)
        self.a_from, self.a_to = self._spin(mid - quarter, xmin, xmax), self._spin(mid, xmin, xmax)
        self.b_from, self.b_to = self._spin(mid, xmin, xmax), self._spin(mid + quarter, xmin, xmax)
        self.range_a_row = self._range_row(self.a_from, self.a_to)
        self.range_b_row = self._range_row(self.b_from, self.b_to)
        self.range_a_label = QLabel("Range:")
        self.range_b_label = QLabel("Range B:")
        form.addRow(self.range_a_label, self.range_a_row)
        form.addRow(self.range_b_label, self.range_b_row)
        self.no_common_range_label = QLabel(
            "\u26a0 The selected spectra have no x-range in common. Spectra that do not "
            "completely cover the chosen x or range get no value and are left out.")
        self.no_common_range_label.setWordWrap(True)
        self.no_common_range_label.setStyleSheet("color:#9A4A00;")
        self.no_common_range_label.setVisible(False)
        form.addRow(self.no_common_range_label)
        controls.addWidget(value_box, 3)

        test_box = QGroupBox("3. Test")
        tl = QVBoxLayout(test_box)
        self.test_combo = QComboBox()
        for key, text in gs.TESTS.items():
            self.test_combo.addItem(text, key)
        self.test_combo.setToolTip(
            "Parametric: compares means (Welch t-test for two groups, one-way ANOVA for more).\n"
            "Non-parametric: compares ranks, robust to outliers and skewed values\n"
            "(Mann–Whitney U for two groups, Kruskal–Wallis for more).\n"
            "With three or more groups every pair is also tested (Holm-corrected p).")
        tl.addWidget(self.test_combo)
        self.compute_btn = QPushButton("Compute")
        self.compute_btn.setStyleSheet("font-weight:bold;")
        self.compute_btn.clicked.connect(self.compute)
        tl.addWidget(self.compute_btn)
        tl.addStretch(1)
        controls.addWidget(test_box, 2)
        lay.addLayout(controls)

        self.tabs = QTabWidget()
        # The selected tab is drawn bold (application style) but Qt sizes
        # tabs for the normal font, so "Box plot" was cut off; a minimum
        # width leaves room for the bold text
        self.tabs.setStyleSheet("QTabBar::tab { min-width: 70px; }")
        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.figure)
        self.tabs.addTab(self.canvas, "Box plot")
        self.summary_table = QTableWidget(0, 7)
        self.summary_table.setHorizontalHeaderLabels(
            ["Group", "n", "Mean", "SD", "Median", "Min", "Max"])
        self.summary_table.verticalHeader().setVisible(False)
        self.tabs.addTab(self.summary_table, "Summary")
        self.tests_view = QTextBrowser()
        self.tabs.addTab(self.tests_view, "Test")
        self.values_table = QTableWidget(0, 3)
        self.values_table.setHorizontalHeaderLabels(["Spectrum", "Group", "Value"])
        self.values_table.verticalHeader().setVisible(False)
        self.values_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabs.addTab(self.values_table, "Values")
        lay.addWidget(self.tabs, 1)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color:#555;")
        lay.addWidget(self.note)
        self._update_value_widgets()
        return right

    @staticmethod
    def _spin(value, lo, hi):
        s = QDoubleSpinBox()
        span = max(abs(lo), abs(hi), 1.0)
        s.setRange(-10 * span, 10 * span)
        s.setDecimals(2)
        s.setValue(value)
        return s

    @staticmethod
    def _range_row(a, b):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(a)
        h.addWidget(QLabel("to"))
        h.addWidget(b)
        h.addStretch(1)
        return w

    @staticmethod
    def _extent_of(spectra):
        lows, highs = [], []
        for sp in spectra:
            x = np.asarray(sp.get('x_scale', []), dtype=float)
            x = x[np.isfinite(x)]
            if len(x):
                lows.append(x.min())
                highs.append(x.max())
        return (min(lows), max(highs)) if lows else (np.nan, np.nan)

    def _common_range_exists(self):
        lows, highs = [], []
        for sp in self.spectra:
            x = np.asarray(sp.get('x_scale', []), dtype=float)
            x = x[np.isfinite(x)]
            if len(x):
                lows.append(x.min())
                highs.append(x.max())
        return bool(lows) and min(highs) > max(lows)

    def _x_extent(self):
        lows, highs = [], []
        for s in self.spectra:
            x = np.asarray(s.get('x_scale', []), dtype=float)
            x = x[np.isfinite(x)]
            if len(x):
                lows.append(x.min())
                highs.append(x.max())
        if not lows:
            return 0.0, 1.0
        if min(highs) > max(lows):              # the part all spectra have
            return float(max(lows)), float(min(highs))
        return float(min(lows)), float(max(highs))   # none in common: everything (warned)

    def _update_value_widgets(self, *_):
        kind = self.kind_combo.currentData()
        # Swap the default range (only while it is still a default)
        current = (self.a_from.value(), self.a_to.value())
        wanted = self._ratio_default if kind == 'ratio' else self._single_default
        other = self._single_default if kind == 'ratio' else self._ratio_default
        if all(abs(c - o) < 1e-9 for c, o in zip(current, other)):
            self.a_from.setValue(wanted[0])
            self.a_to.setValue(wanted[1])
        self.no_common_range_label.setVisible(not self.has_common_range)
        self.x_row.setVisible(kind == 'intensity_at_x')
        self.x_row.parentWidget().layout().labelForField(self.x_row).setVisible(
            kind == 'intensity_at_x')
        ranged = kind in ('mean', 'area', 'max', 'ratio')
        self.range_a_row.setVisible(ranged)
        self.range_a_label.setVisible(ranged)
        self.range_a_label.setText("Range A:" if kind == 'ratio' else "Range:")
        self.range_b_row.setVisible(kind == 'ratio')
        self.range_b_label.setVisible(kind == 'ratio')

    def value_settings(self):
        return {'kind': self.kind_combo.currentData(), 'x0': self.x_spin.value(),
                'range_a': (self.a_from.value(), self.a_to.value()),
                'range_b': (self.b_from.value(), self.b_to.value())}

    def value_label(self):
        v = self.value_settings()
        k = v['kind']
        if k == 'intensity_at_x':
            return f"Intensity at {v['x0']:g}"
        a = f"{min(v['range_a']):g}–{max(v['range_a']):g}"
        if k == 'ratio':
            b = f"{min(v['range_b']):g}–{max(v['range_b']):g}"
            return f"Area {a} / area {b}"
        return {'mean': 'Mean', 'area': 'Area', 'max': 'Maximum'}[k] + f" over {a}"

    def compute(self):
        groups = self.groups()
        if len([g for g in set(groups) if g]) < 2:
            QMessageBox.warning(self, "Group Statistics",
                                "Give the spectra at least two different groups first "
                                "(column 'Group', or the buttons below the table).")
            return
        v = self.value_settings()
        values = gs.spectrum_values(self.spectra, v['kind'], x0=v['x0'],
                                    range_a=v['range_a'], range_b=v['range_b'])
        data = gs.collect(groups, values)
        parametric = self.test_combo.currentData() == 'parametric'
        result = gs.compare(data, parametric=parametric)
        self.values, self.data, self.comparison = values, data, result
        missing = sum(1 for g, val in zip(groups, values) if g and not np.isfinite(val))
        notes = []
        if result.get('test') is None:
            notes.append("No test was computed.")
        # A whole group without values: say which, and where its spectra are
        # (typical when the groups were measured over different x-ranges)
        empty = [g for g in dict.fromkeys(groups) if g and g not in data]
        for g in empty:
            members = [sp for sp, gg in zip(self.spectra, groups) if gg == g]
            lo, hi = self._extent_of(members)
            ra = f"{min(v['range_a']):g}\u2013{max(v['range_a']):g}"
            rb = f"{min(v['range_b']):g}\u2013{max(v['range_b']):g}"
            where = {'intensity_at_x': f"x = {v['x0']:g}",
                     'ratio': f"range A {ra} or range B {rb}"}.get(v['kind'],
                                                                  f"the range {ra}")
            notes.append(f"Group \u201c{g}\u201d ({len(members)} spectra) has no value and is "
                         f"not in the test: its spectra cover {lo:g}\u2013{hi:g}, outside "
                         f"{where}.")
        missing -= sum(1 for g in groups if g in empty)
        if missing:
            names = [lab for lab, g, val in zip(self.labels, groups, values)
                     if g and g not in empty and not np.isfinite(val)]
            notes.append(f"{missing} spectr{'um has' if missing == 1 else 'a have'} no value "
                         f"(the x or range is not completely inside them) and "
                         f"{'was' if missing == 1 else 'were'} left out: "
                         + ", ".join(names[:5]) + (" \u2026" if len(names) > 5 else "") + ".")
        if result['excluded']:
            notes.append("Left out of the test (fewer than 2 values): "
                         + ", ".join(result['excluded']) + ".")
        if result['note']:
            notes.append(result['note'])
        self.note.setText(" ".join(notes))
        # Red whenever the test is not what was asked for: no test at all,
        # or a whole group left out (the test then compares fewer groups)
        self.left_out_groups = empty + [g for g in result.get('excluded', []) if g not in empty]
        self.note.setStyleSheet("color:#B71C1C;"
                                if result.get('test') is None or self.left_out_groups
                                or missing else "color:#555;")
        self._show_box_plot()
        self._show_summary()
        self._show_tests()
        self._show_values(groups)
        self.export_btn.setEnabled(bool(data))

    def _show_box_plot(self):
        fig = self.figure
        fig.clear()
        ax = fig.add_subplot(111)
        names = list(self.data)
        values = [self.data[g] for g in names]
        if names:
            ax.boxplot(values, showfliers=False, widths=0.5,
                       medianprops={'color': 'black'})
            rng = np.random.default_rng(0)
            for i, v in enumerate(values, start=1):
                jitter = rng.uniform(-0.12, 0.12, len(v))
                ax.scatter(np.full(len(v), i) + jitter, v, s=14, alpha=0.7,
                           color=_GROUP_COLOURS[(i - 1) % len(_GROUP_COLOURS)], zorder=3)
                ax.plot([i - 0.25, i + 0.25], [np.mean(v)] * 2, color='#E65100', linewidth=1.5,
                        zorder=4)
            ax.set_xticks(range(1, len(names) + 1))
            ax.set_xticklabels([f"{g}\n(n={len(self.data[g])})" for g in names], fontsize=8)
        ax.set_ylabel(self.value_label(), fontsize=9)
        r = self.comparison
        if r and r['test']:
            left_out = getattr(self, 'left_out_groups', [])
            title = f"{r['test']}: {gs.p_text(r['p'])}"
            if left_out:
                title += ("\nnot in the test: group " if len(left_out) == 1
                          else "\nnot in the test: groups ") + ", ".join(left_out)
            ax.set_title(title, fontsize=9, color='#B71C1C' if left_out else 'black')
        fig.tight_layout()
        self.canvas.draw_idle()

    def _show_summary(self):
        rows = gs.describe(self.data)
        t = self.summary_table
        t.setRowCount(len(rows))
        for r, row in enumerate(rows):
            cells = [row['group'], str(row['n'])] + [f"{row[k]:.6g}" if np.isfinite(row[k]) else "–"
                                                       for k in ('mean', 'sd', 'median', 'min', 'max')]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                t.setItem(r, c, item)
        t.resizeColumnsToContents()

    def _tests_html(self):
        r = self.comparison
        if not r or not r['test']:
            return f"<p>{(r or {}).get('note', '')}</p>"
        parts = [f"<h3>{r['test']}</h3>",
                f"<p>Value: {html.escape(self.value_label())}<br>"
                f"Groups: {html.escape(', '.join(r['groups']))}</p>",
                f"<p>Statistic = {r['statistic']:.4g}, <b>{html.escape(gs.p_text(r['p']))}</b>, "
                f"{r['effect_name']} = {r['effect']:.3g}</p>"]
        if len(r['groups']) > 2:
            centre = "means" if r['parametric'] else "medians"
            parts.append(f"<h4>Pairs ({r['pair_test']}, p Holm-corrected)</h4>")
            parts.append("<table border='1' cellspacing='0' cellpadding='3'>"
                        f"<tr><th>Pair</th><th>Difference of {centre}</th><th>p</th>"
                        f"<th>p (Holm)</th><th>{r['pair_effect_name']}</th></tr>")
            for pr in r['pairs']:
                parts.append(f"<tr><td>{html.escape(pr['a'])} – {html.escape(pr['b'])}</td>"
                            f"<td>{pr['difference']:.4g}</td>"
                            f"<td>{html.escape(gs.format_p(pr['p']))}</td>"
                            f"<td><b>{html.escape(gs.format_p(pr['p_holm']))}</b></td>"
                            f"<td>{pr['effect']:.3g}</td></tr>")
            parts.append("</table>")
        parts.append("<p style='color:#555'>p below 0.05 is usually read as a statistically "
                    "significant difference. The effect size says how large the difference is; "
                    "see Help.</p>")
        return "".join(parts)

    def _show_tests(self):
        self.tests_view.setHtml(self._tests_html())

    def _show_values(self, groups):
        t = self.values_table
        t.setRowCount(len(self.labels))
        for r, (label, g, v) in enumerate(zip(self.labels, groups, self.values)):
            for c, text in enumerate((label, g, f"{v:.6g}" if np.isfinite(v) else "–")):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                t.setItem(r, c, item)

    # ------------------------------------------------------------------ export / help
    def export(self):
        if self.comparison is None:
            return
        path, chosen = QFileDialog.getSaveFileName(
            self, "Export group statistics", "group_statistics.xlsx",
            "Excel workbook (*.xlsx);;CSV (*.csv)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += '.csv' if 'CSV' in chosen else '.xlsx'
        try:
            export_results(path, self.labels, self.groups(), self.values, self.data, self.comparison,
                           self.value_label())
        except Exception as exc:
            logger.exception("Group statistics export failed")
            QMessageBox.warning(self, "Export failed", f"The file could not be written:\n{exc}")

    def show_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'group_statistics')


def export_results(path, labels, groups, values, data, result, value_label):
    """Write the values, the summary and the tests to an Excel workbook
    (three sheets) or a CSV file (the three tables one after another)."""
    import pandas as pd
    values_df = pd.DataFrame({'Spectrum': labels, 'Group': groups, value_label: values})
    summary_df = pd.DataFrame(gs.describe(data)).rename(columns={
        'group': 'Group', 'n': 'n', 'mean': 'Mean', 'sd': 'SD', 'median': 'Median',
        'min': 'Min', 'max': 'Max'})
    rows = [{'Comparison': 'All groups', 'Test': result['test'], 'Statistic': result['statistic'],
             'p': result['p'], 'p (Holm)': None, 'Effect size': result['effect_name'],
             'Effect': result['effect'], 'Difference': None}]
    for pr in result.get('pairs', []) if len(result.get('groups', [])) > 2 else []:
        rows.append({'Comparison': f"{pr['a']} – {pr['b']}", 'Test': result['pair_test'],
                     'Statistic': pr['statistic'], 'p': pr['p'], 'p (Holm)': pr['p_holm'],
                     'Effect size': result['pair_effect_name'], 'Effect': pr['effect'],
                     'Difference': pr['difference']})
    tests_df = pd.DataFrame(rows)
    if path.lower().endswith('.csv'):
        with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
            for title, df in (('Values', values_df), ('Summary', summary_df), ('Tests', tests_df)):
                fh.write(f"{title}\n")
                df.to_csv(fh, index=False)
                fh.write("\n")
    else:
        with pd.ExcelWriter(path) as writer:
            values_df.to_excel(writer, sheet_name='Values', index=False)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            tests_df.to_excel(writer, sheet_name='Tests', index=False)
