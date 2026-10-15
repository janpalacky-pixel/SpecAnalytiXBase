# src/views/dialogs/visualization_analysis/group_statistics_dialog.py
"""Analysis & Visualization -> Data Analysis -> Group Statistics.

1. Groups: every selected spectrum gets a group (table, editable), set by
   hand for selected rows, from the names (contains / part of the name) or
   from a table file.
2. Value: one number per spectrum (intensity at x, mean / area / maximum
   over a range, band ratio).
3. Compute: box / violin / mean ± CI plot with every value (Save plot…),
   summary per group, the test
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
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from src.modules.utils.app_logger import get_logger
from src.modules.visualization_analysis import group_statistics as gs
from src.modules.visualization_analysis import group_values as gv
from src.views.dialogs.visualization_analysis.peak_fit_settings_dialog import (
    PeakFitSettingsDialog, load_settings as load_peak_fit_settings,
    save_settings as save_peak_fit_settings)
from src.views.dialogs.misc.fill_column_table import FillColumnTable

logger = get_logger(__name__)

_PLOT_TYPES = {
    'box': "Box plot",
    'violin': "Violin plot",
    'ci': "Points with mean ± 95 % CI",
}

# One line under the value choice: what the chosen value is
_VALUE_HINTS = {
    'intensity_at_x': "The spectrum's intensity at one x-value.",
    'area': "Area under the spectrum from exactly the start to exactly the end of the range.",
    'bc_area': "Area above the straight line joining the spectrum at the two range edges "
               "(the band without a sloping background).",
    'mean': "Average height of the spectrum over the range (area / width).",
    'max': "Highest intensity in the range.",
    'peak_position': "x-position of the highest point (or parabola top) in the range — "
                     "compares band shifts.",
    'fwhm': "Width of the dominant band at half its height.",
    'variance': "Spread of the intensities within the range.",
    'fit_center': "Centre of a peak fitted to the range (between measured points, little "
                  "affected by noise).",
    'fit_fwhm': "Width (FWHM) of a peak fitted to the range.",
    'fit_height': "Height of a peak fitted to the range, above the fitted background.",
    'fit_area': "Area of a peak fitted to the range, without the fitted background.",
    'fit_r2': "How well one peak plus background describes the range (1 = perfect).",
    'ratio': "A value from band A and one from band B, combined — e.g. area A / area B, "
             "independent of the overall intensity.",
    'pca': "Score of each spectrum on a principal component of the selected spectra "
           "(mean-centred): do the groups differ along a main direction of variation? "
           "The sign of a component is arbitrary.",
    'svd': "Coefficient of each spectrum on an SVD component (not mean-centred; "
           "component 1 mostly follows the overall intensity).",
    'corr_ref': "Pearson correlation of each spectrum with the mean spectrum of the "
                "reference group (1 = the same shape).",
    'dist_ref': "Root-mean-square difference between each spectrum and the mean spectrum "
                "of the reference group (0 = identical).",
}

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
            "  sample_012  \u2192 sample\n"
            "  CD_melt_1 : CD [mdeg] T=45.00C \u2192 CD_melt_1")
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
        help_button = QPushButton("Help")
        help_button.setToolTip("What this window does, with examples")
        help_button.setAutoDefault(False)
        help_button.clicked.connect(self.show_help)
        buttons.addButton(help_button, QDialogButtonBox.HelpRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(480, 420)
        self._update_preview()

    HELP_TEXT = (
        "<h3>Groups from spectrum names</h3>"
        "<p>Gives every spectrum in the table a group, worked out from its name, so you "
        "do not have to type the groups by hand. The line at the bottom previews the "
        "groups and how many spectra each gets; <b>OK</b> writes them into the Group "
        "column (you can still edit them there, and Ctrl+Z undoes it).</p>"
        "<p><b>Common root name</b> (one click) &mdash; the name without its numbering, "
        "the same rule as <i>Select spectra</i> and <i>Rename</i> use:<br>"
        "&nbsp;&nbsp;<code>Chlorella [r24_c14]</code> &rarr; <code>Chlorella</code><br>"
        "&nbsp;&nbsp;<code>CD_spectra_TBA : 0019</code> &rarr; <code>CD_spectra_TBA</code><br>"
        "&nbsp;&nbsp;<code>sample_012</code> &rarr; <code>sample</code><br>"
        "&nbsp;&nbsp;<code>CD_melt_1 : CD [mdeg] T=45.00C</code> &rarr; <code>CD_melt_1</code> "
        "(the file part before \u201c : \u201d)<br>"
        "Best for spectra from several files or maps.</p>"
        "<p><b>Name contains a text</b> &mdash; one rule per line, "
        "<code>text = group</code>:<br>"
        "&nbsp;&nbsp;<code>ctrl = Control</code><br>"
        "&nbsp;&nbsp;<code>treat = Treated</code><br>"
        "A spectrum whose name contains <i>ctrl</i> gets the group <i>Control</i>. The first "
        "matching rule wins, upper/lower case does not matter, and a line with only a "
        "text (e.g. <code>ctrl</code>) uses the text itself as the group.</p>"
        "<p><b>A part of the name</b> &mdash; the name is cut at the separator "
        "character(s) and one piece is used:<br>"
        "&nbsp;&nbsp;<code>cellA_day3_01</code>, separator <code>_</code>, part 2 "
        "&rarr; <code>day3</code><br>"
        "&nbsp;&nbsp;<code>Raman_DNA : sp001</code>, separator <code>:</code>, part 1 "
        "&rarr; <code>Raman_DNA</code><br>"
        "Part &minus;1 is the last piece. Several characters in the box are all "
        "separators (e.g. <code>_-</code>).</p>"
        "<p>A spectrum that gets no group (no rule matches, or the name has too few "
        "pieces) is left out of the statistics.</p>")

    def show_help(self):
        box = QMessageBox(self)
        box.setWindowTitle("Help \u2013 Groups from spectrum names")
        box.setTextFormat(Qt.RichText)
        box.setText(self.HELP_TEXT)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec_()

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

    def __init__(self, spectra, parent=None, saved_groups=None, saved_settings=None):
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
        # value settings remembered for the session (by the controller)
        self.remembered_settings = saved_settings if saved_settings is not None else {}
        from src.modules.visualization_analysis.peak_fit_map import PeakFitMapper
        self._fit_mapper = PeakFitMapper()          # keeps fits, e.g. for A and B
        self.resize(1250, 820)

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
        self._update_reference_choices()
        self.set_value_settings(dict(self.remembered_settings))
        j = self.plot_combo.findData(self.remembered_settings.get('plot'))
        if j >= 0:
            self.plot_combo.setCurrentIndex(j)

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
        if hasattr(self, 'reference_combo'):
            self._update_reference_choices()

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
            mapping = gs.read_group_table(path, labels=self.labels)
        except Exception as exc:
            logger.exception("Reading the group table failed")
            QMessageBox.warning(self, "Group Statistics", f"The table could not be read:\n{exc}")
            return
        groups = gs.groups_from_table(self.labels, mapping)
        found = sum(1 for g in groups if g)
        self._set_groups(groups)
        known = {l.strip().lower() for l in self.labels}
        unmatched = [name for name in mapping if name.strip().lower() not in known]
        text = f"{found} of {len(groups)} spectra were found in the table."
        if unmatched:
            text += (f"\n\n{len(unmatched)} name(s) in the table match no spectrum here, "
                     f"e.g.:\n" + "\n".join(unmatched[:5]))
        QMessageBox.information(self, "Group Statistics", text)

    # ------------------------------------------------------------------ value + results
    def _build_right_panel(self):
        right = QWidget()
        lay = QVBoxLayout(right)
        lay.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()

        value_box = QGroupBox("2. Value per spectrum")
        form = QFormLayout(value_box)
        self.value_form = form
        self.same_axis = gv.same_x_axis(self.spectra)
        self.kind_combo = QComboBox()
        self.kind_combo.setMaxVisibleItems(25)
        self._fill_kind_combo()
        self.kind_combo.currentIndexChanged.connect(self._update_value_widgets)
        form.addRow("Value:", self.kind_combo)
        xmin, xmax = self._x_extent()
        self.has_common_range = self._common_range_exists()
        mid, quarter = (xmin + xmax) / 2, (xmax - xmin) / 8 or 1.0
        # Default ranges: one range (one band, whole spectrum) = the whole
        # common x-range; two bands = two neighbouring ranges either side
        # of the middle (A and B use the same "from" / "to" boxes as the
        # single range, so _update_value_widgets swaps between the two
        # defaults as long as the user has not typed a range himself)
        self._single_default = (xmin, xmax)
        self._ratio_default = (mid - quarter, mid)

        # x (Intensity at x): point / average / fit over x +- w
        self.x_spin = self._spin(mid, xmin, xmax)
        self.x_mode_combo = QComboBox()
        for key, text in gv.X_MODES.items():
            self.x_mode_combo.addItem(text, key)
        self.x_mode_combo.setToolTip(
            "The interpolated point: the spectrum read at exactly x (one noisy point can\n"
            "decide the value).\n"
            "Average over x ± w: the mean height of the spectrum from x − w to x + w.\n"
            "Polynomial fitted over x ± w: a parabola fitted to the points from x − w to\n"
            "x + w and read at x (smooths the noise, keeps the shape).")
        self.w_label = QLabel("w:")
        self.w_spin = self._spin(max((xmax - xmin) / 100, 0.01), 0.0, xmax - xmin)
        self.w_spin.setMinimum(0.0)
        self.w_spin.setToolTip("Half-width of the window around x (x-axis units)")
        self.x_row = QWidget()
        xr = QHBoxLayout(self.x_row)
        xr.setContentsMargins(0, 0, 0, 0)
        xr.addWidget(self.x_spin)
        xr.addWidget(QLabel("value:"))
        xr.addWidget(self.x_mode_combo)
        xr.addWidget(self.w_label)
        xr.addWidget(self.w_spin)
        xr.addStretch(1)
        form.addRow("x:", self.x_row)
        self.x_mode_combo.currentIndexChanged.connect(self._update_value_widgets)

        # Peak intensity / position: highest point or parabola top
        self.max_mode_combo = QComboBox()
        for key, text in gv.MAX_MODES.items():
            self.max_mode_combo.addItem(text, key)
        self.max_mode_combo.setToolTip(
            "The highest point: the largest measured value (a noise spike can win; the\n"
            "position can only be a measured x).\n"
            "Top of a parabola: a parabola through the highest points of the band (noise\n"
            "matters less; the position can lie between measured points).")
        self.max_row = QWidget()
        mr = QHBoxLayout(self.max_row)
        mr.setContentsMargins(0, 0, 0, 0)
        mr.addWidget(self.max_mode_combo)
        mr.addStretch(1)
        form.addRow("Peak top:", self.max_row)

        # whole spectrum: only within a range?
        self.whole_range_check = QCheckBox("Use only the range below (otherwise the whole spectrum)")
        self.whole_range_check.toggled.connect(self._update_value_widgets)
        form.addRow(self.whole_range_check)

        # ranges (+ the metric of each band for two bands)
        self.a_from, self.a_to = self._spin(mid - quarter, xmin, xmax), self._spin(mid, xmin, xmax)
        self.b_from, self.b_to = self._spin(mid, xmin, xmax), self._spin(mid + quarter, xmin, xmax)
        self.metric_a_combo, self.metric_b_combo = QComboBox(), QComboBox()
        for combo, default in ((self.metric_a_combo, 'Integral'),
                               (self.metric_b_combo, 'Integral')):
            combo.addItems(gv.BAND_METRICS)
            combo.setCurrentText(default)
            combo.setToolTip("What is taken from this band (the same metrics as in the 2D Map)")
            combo.currentIndexChanged.connect(self._update_value_widgets)
        self.range_a_row = self._range_row(self.a_from, self.a_to, self.metric_a_combo)
        self.range_b_row = self._range_row(self.b_from, self.b_to, self.metric_b_combo)
        self.range_a_label = QLabel("Range:")
        self.range_b_label = QLabel("Range B:")
        form.addRow(self.range_a_label, self.range_a_row)
        form.addRow(self.range_b_label, self.range_b_row)
        self.operation_combo = QComboBox()
        self.operation_combo.addItems(gv.OPERATIONS)
        self.operation_combo.setToolTip(
            "A / B: ratio (independent of the overall intensity)\n"
            "A − B, A + B, A × B: difference, sum, product\n"
            "(A − B) / (A + B): normalised difference, always between −1 and 1\n"
            "log₂(A / B): log ratio; doubling = +1, halving = −1 (symmetric)")
        self.operation_row = QWidget()
        orow = QHBoxLayout(self.operation_row)
        orow.setContentsMargins(0, 0, 0, 0)
        orow.addWidget(self.operation_combo)
        orow.addStretch(1)
        form.addRow("Combine:", self.operation_row)

        # whole spectrum: component / reference group
        self.component_spin = QSpinBox()
        self.component_spin.setRange(1, 20)
        self.component_spin.setToolTip("1 = the direction of the largest variation, 2 = the next, …")
        self.component_row = QWidget()
        crow = QHBoxLayout(self.component_row)
        crow.setContentsMargins(0, 0, 0, 0)
        crow.addWidget(self.component_spin)
        crow.addStretch(1)
        form.addRow("Component:", self.component_row)
        self.reference_combo = QComboBox()
        self.reference_combo.setToolTip(
            "Each spectrum is compared with the mean spectrum of this group; a spectrum\n"
            "of the group itself with the mean of the group's other spectra.")
        self.reference_row = QWidget()
        rrow = QHBoxLayout(self.reference_row)
        rrow.setContentsMargins(0, 0, 0, 0)
        rrow.addWidget(self.reference_combo)
        rrow.addStretch(1)
        form.addRow("Reference group:", self.reference_row)

        # peak fit settings (fitted metrics)
        self.fit_settings = load_peak_fit_settings()
        self.fit_button = QPushButton("Fit settings…")
        self.fit_button.setToolTip("Peak shape, background and rejection rules of the fit "
                                   "(the same settings as the 2D Map's peak-fit maps)")
        self.fit_button.setAutoDefault(False)
        self.fit_button.clicked.connect(self.edit_fit_settings)
        self.fit_summary = QLabel()
        self.fit_summary.setStyleSheet("color:#555;")
        self.fit_row = QWidget()
        frow = QHBoxLayout(self.fit_row)
        frow.setContentsMargins(0, 0, 0, 0)
        frow.addWidget(self.fit_button)
        frow.addWidget(self.fit_summary)
        frow.addStretch(1)
        form.addRow("Peak fit:", self.fit_row)
        self._update_fit_summary()

        self.no_common_range_label = QLabel(
            "\u26a0 The selected spectra have no x-range in common. Spectra that do not "
            "completely cover the chosen x or range get no value and are left out.")
        self.no_common_range_label.setWordWrap(True)
        self.no_common_range_label.setStyleSheet("color:#9A4A00;")
        self.no_common_range_label.setVisible(False)
        form.addRow(self.no_common_range_label)
        self.value_hint = QLabel()
        self.value_hint.setWordWrap(True)
        self.value_hint.setStyleSheet("color:#555;")
        form.addRow(self.value_hint)
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
        plot_tab = QWidget()
        pl = QVBoxLayout(plot_tab)
        pl.setContentsMargins(4, 4, 4, 4)
        plot_row = QHBoxLayout()
        plot_row.addWidget(QLabel("Plot:"))
        self.plot_combo = QComboBox()
        for key, text in _PLOT_TYPES.items():
            self.plot_combo.addItem(text, key)
        self.plot_combo.setToolTip(
            "Box plot: median, middle half of the values (box), every spectrum as a dot, the\n"
            "mean in orange.\n"
            "Violin plot: the shape of each group's values (e.g. two clusters), with every\n"
            "spectrum, the median and the mean; unreliable for groups with fewer than 10 values.\n"
            "Points with mean ± 95 % CI: every spectrum, the mean and its 95 % confidence\n"
            "interval — the plot that matches the t-test / ANOVA.")
        self.plot_combo.currentIndexChanged.connect(self._on_plot_type_changed)
        plot_row.addWidget(self.plot_combo)
        self.save_plot_btn = QPushButton("Save plot…")
        self.save_plot_btn.setToolTip("Save the plot as PNG, TIFF, SVG or PDF")
        self.save_plot_btn.setAutoDefault(False)
        self.save_plot_btn.setEnabled(False)
        self.save_plot_btn.clicked.connect(self.save_plot)
        plot_row.addWidget(self.save_plot_btn)
        plot_row.addStretch(1)
        pl.addLayout(plot_row)
        pl.addWidget(self.canvas, 1)
        self.tabs.addTab(plot_tab, "Plot")
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
    def _range_row(a, b, metric_combo=None):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(a)
        h.addWidget(QLabel("to"))
        h.addWidget(b)
        if metric_combo is not None:
            h.addWidget(metric_combo)
        h.addStretch(1)
        return w

    def _fill_kind_combo(self):
        """The value choices in three sections (headers are not selectable);
        whole-spectrum values are greyed out unless all spectra share one
        x-axis."""
        from PyQt5.QtGui import QFont
        model = self.kind_combo.model()
        first = None
        for header, items in gv.VALUE_SECTIONS:
            self.kind_combo.addItem(header)
            head = model.item(self.kind_combo.count() - 1)
            head.setEnabled(False)
            font = QFont(head.font())
            font.setBold(True)
            head.setFont(font)
            for key, text in items:
                self.kind_combo.addItem(text, key)
                item = model.item(self.kind_combo.count() - 1)
                if gv.is_whole_spectrum(key) and not self.same_axis:
                    item.setEnabled(False)
                    item.setToolTip("Needs spectra with the same x-axis; the selected "
                                    "spectra have different x-axes.")
                if first is None:
                    first = self.kind_combo.count() - 1
        self.kind_combo.setCurrentIndex(first)

    def _update_fit_summary(self):
        s = self.fit_settings
        self.fit_summary.setText(f"{s['shape']}, background {s['baseline'].lower()}")

    def edit_fit_settings(self):
        dlg = PeakFitSettingsDialog(
            self.fit_settings, self,
            intro="For every spectrum, one peak plus a background is fitted to the points "
                  "of the range (the same fit as the 2D Map's peak-fit maps). Choose a range "
                  "that contains one band and some background on both sides.")
        if dlg.exec_() != QDialog.Accepted:
            return
        self.fit_settings = dlg.settings()
        save_peak_fit_settings(self.fit_settings)
        self._update_fit_summary()

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
        if kind is None:            # a section header (cannot normally be chosen)
            return
        two = kind in gv.TWO_BANDS
        whole = gv.is_whole_spectrum(kind)
        one_band = kind in gv.ONE_BAND and kind != 'intensity_at_x'
        # Swap the default range (only while it is still a default)
        current = (self.a_from.value(), self.a_to.value())
        wanted = self._ratio_default if two else self._single_default
        other = self._single_default if two else self._ratio_default
        if all(abs(c - o) < 1e-9 for c, o in zip(current, other)):
            self.a_from.setValue(wanted[0])
            self.a_to.setValue(wanted[1])
        settings = self.value_settings()
        self.no_common_range_label.setVisible(not self.has_common_range and not whole)

        def show(row, visible):
            row.setVisible(visible)
            label = self.value_form.labelForField(row)
            if label is not None:
                label.setVisible(visible)

        show(self.x_row, kind == 'intensity_at_x')
        averaged = self.x_mode_combo.currentData() != 'point'
        self.w_label.setVisible(averaged)
        self.w_spin.setVisible(averaged)
        show(self.max_row, gv.uses_max_mode(settings))
        self.whole_range_check.setVisible(whole)
        range_a = one_band or two or (whole and self.whole_range_check.isChecked())
        self.range_a_row.setVisible(range_a)
        self.range_a_label.setVisible(range_a)
        self.range_a_label.setText("Range A:" if two else "Range:")
        self.range_b_row.setVisible(two)
        self.range_b_label.setVisible(two)
        self.metric_a_combo.setVisible(two)
        self.metric_b_combo.setVisible(two)
        show(self.operation_row, two)
        show(self.component_row, kind in ('pca', 'svd'))
        show(self.reference_row, kind in ('corr_ref', 'dist_ref'))
        show(self.fit_row, gv.uses_fit(settings))
        self.value_hint.setText(_VALUE_HINTS.get(kind, ''))

    def _update_reference_choices(self):
        current = self.reference_combo.currentText()
        names = [g for g in dict.fromkeys(self.groups()) if g]
        self.reference_combo.blockSignals(True)
        self.reference_combo.clear()
        self.reference_combo.addItems(names)
        if current in names:
            self.reference_combo.setCurrentText(current)
        self.reference_combo.blockSignals(False)

    def value_settings(self):
        return {'kind': self.kind_combo.currentData(), 'x0': self.x_spin.value(),
                'x_mode': self.x_mode_combo.currentData(), 'x_halfwidth': self.w_spin.value(),
                'max_mode': self.max_mode_combo.currentData(),
                'range_a': (self.a_from.value(), self.a_to.value()),
                'range_b': (self.b_from.value(), self.b_to.value()),
                'metric_a': self.metric_a_combo.currentText(),
                'metric_b': self.metric_b_combo.currentText(),
                'operation': self.operation_combo.currentText(),
                'component': self.component_spin.value(),
                'reference_group': self.reference_combo.currentText(),
                'whole_use_range': self.whole_range_check.isChecked()}

    def set_value_settings(self, v):
        """Restore remembered settings (the same session, e.g. reopening)."""
        if not v:
            return
        i = self.kind_combo.findData(v.get('kind'))
        if i >= 0 and self.kind_combo.model().item(i).isEnabled():
            self.kind_combo.setCurrentIndex(i)
        for combo, key in ((self.x_mode_combo, 'x_mode'), (self.max_mode_combo, 'max_mode')):
            j = combo.findData(v.get(key))
            if j >= 0:
                combo.setCurrentIndex(j)
        for spin, key in ((self.x_spin, 'x0'), (self.w_spin, 'x_halfwidth')):
            if v.get(key) is not None:
                spin.setValue(float(v[key]))
        for (lo, hi), key in (((self.a_from, self.a_to), 'range_a'),
                              ((self.b_from, self.b_to), 'range_b')):
            if v.get(key):
                lo.setValue(float(v[key][0]))
                hi.setValue(float(v[key][1]))
        for combo, key in ((self.metric_a_combo, 'metric_a'), (self.metric_b_combo, 'metric_b'),
                           (self.operation_combo, 'operation')):
            if v.get(key) and combo.findText(v[key]) >= 0:
                combo.setCurrentText(v[key])
        self.component_spin.setValue(int(v.get('component', 1)))
        self.whole_range_check.setChecked(bool(v.get('whole_use_range')))
        if v.get('reference_group') and self.reference_combo.findText(v['reference_group']) >= 0:
            self.reference_combo.setCurrentText(v['reference_group'])
        self._update_value_widgets()

    def value_label(self):
        return gv.value_label(self.value_settings())

    def _where_text(self, v):
        """Where the value is taken from, for messages."""
        ra = f"{min(v['range_a']):g}\u2013{max(v['range_a']):g}"
        rb = f"{min(v['range_b']):g}\u2013{max(v['range_b']):g}"
        if v['kind'] == 'intensity_at_x':
            if v['x_mode'] == 'point':
                return f"x = {v['x0']:g}"
            return f"x = {v['x0']:g} \u00b1 {v['x_halfwidth']:g}"
        if v['kind'] in gv.TWO_BANDS:
            return f"range A {ra} or range B {rb}"
        return f"the range {ra}"

    def compute(self):
        groups = self.groups()
        if len([g for g in set(groups) if g]) < 2:
            QMessageBox.warning(self, "Group Statistics",
                                "Give the spectra at least two different groups first "
                                "(column 'Group', or the buttons below the table).")
            return
        v = self.value_settings()
        if gv.is_whole_spectrum(v['kind']) and v['kind'] in ('corr_ref', 'dist_ref') \
                and not v['reference_group']:
            QMessageBox.warning(self, "Group Statistics", "Choose the reference group first.")
            return
        self.remembered_settings.update(v)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            values, info = gv.compute_values(self.spectra, groups, v,
                                             fit_settings=self.fit_settings,
                                             mapper=self._fit_mapper)
        except Exception as exc:
            logger.exception("Group statistics: computing the values failed")
            QMessageBox.warning(self, "Group Statistics",
                                f"The values could not be computed:\n{exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        data = gs.collect(groups, values)
        parametric = self.test_combo.currentData() == 'parametric'
        result = gs.compare(data, parametric=parametric)
        self.values, self.data, self.comparison = values, data, result
        missing = sum(1 for g, val in zip(groups, values) if g and not np.isfinite(val))
        notes = []
        if result.get('test') is None:
            notes.append("No test was computed.")
        if info.get('note'):
            notes.append(info['note'])
        if info.get('explained') is not None and np.isfinite(info['explained']):
            notes.append(f"Component {v['component']} describes "
                         f"{info['explained']:.1f} % of the variation.")
        whole = gv.is_whole_spectrum(v['kind'])
        reasons = []
        if not whole:
            reasons.append("the x or range is not completely inside them")
        if gv.uses_fit(v):
            reasons.append("the peak fit was rejected")
        if v['kind'] in gv.TWO_BANDS and v['operation'] in ('A / B', 'log₂(A / B)',
                                                            '(A − B) / (A + B)'):
            reasons.append("the combination is undefined, e.g. division by zero")
        if v['kind'] in ('corr_ref', 'dist_ref'):
            reasons.append("a reference group of one spectrum has no other spectra to "
                           "compare with")
        reason = " or ".join(reasons) if reasons else "it could not be computed"
        # A whole group without values: say which, and where its spectra are
        # (typical when the groups were measured over different x-ranges)
        empty = [g for g in dict.fromkeys(groups) if g and g not in data]
        for g in empty:
            members = [sp for sp, gg in zip(self.spectra, groups) if gg == g]
            lo, hi = self._extent_of(members)
            if whole or info.get('note'):
                notes.append(f"Group \u201c{g}\u201d ({len(members)} spectra) has no value "
                             f"and is not in the test.")
                continue
            notes.append(f"Group \u201c{g}\u201d ({len(members)} spectra) has no value and is "
                         f"not in the test: its spectra cover {lo:g}\u2013{hi:g}"
                         + (f", outside {self._where_text(v)}" if not gv.uses_fit(v) else
                            f" ({reason})") + ".")
        missing -= sum(1 for g in groups if g in empty)
        if missing:
            names = [lab for lab, g, val in zip(self.labels, groups, values)
                     if g and g not in empty and not np.isfinite(val)]
            notes.append(f"{missing} spectr{'um has' if missing == 1 else 'a have'} no value "
                         f"({reason}) and "
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

    def _on_plot_type_changed(self, *_):
        self.remembered_settings['plot'] = self.plot_combo.currentData()
        if getattr(self, 'data', None) is not None:
            self._show_box_plot()

    def save_plot(self):
        path, chosen = QFileDialog.getSaveFileName(
            self, "Save plot", "group_statistics.png",
            "PNG image (*.png);;TIFF image (*.tif);;SVG vector graphics (*.svg);;PDF (*.pdf)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += {'PNG': '.png', 'TIFF': '.tif', 'SVG': '.svg', 'PDF': '.pdf'}.get(
                chosen.split()[0], '.png')
        try:
            self.figure.savefig(path, dpi=300, bbox_inches='tight')
        except Exception as exc:
            logger.exception("Group statistics: saving the plot failed")
            QMessageBox.warning(self, "Save plot", f"The plot could not be saved:\n{exc}")

    def _show_box_plot(self):
        """Draw the chosen plot type (box / violin / points with mean ± 95 % CI)."""
        fig = self.figure
        fig.clear()
        ax = fig.add_subplot(111)
        names = list(self.data)
        values = [np.asarray(self.data[g], dtype=float) for g in names]
        kind = self.plot_combo.currentData()
        footnote = ''
        if names:
            colours = [_GROUP_COLOURS[i % len(_GROUP_COLOURS)] for i in range(len(names))]
            positions = list(range(1, len(names) + 1))
            if kind == 'box':
                ax.boxplot(values, showfliers=False, widths=0.5,
                           medianprops={'color': 'black'})
            elif kind == 'violin':
                drawable = [(p, v) for p, v in zip(positions, values)
                            if len(v) >= 2 and np.ptp(v) > 0]
                if drawable:
                    parts = ax.violinplot([v for _, v in drawable],
                                          positions=[p for p, _ in drawable], widths=0.7,
                                          showextrema=False)
                    for body, (p, _) in zip(parts['bodies'], drawable):
                        body.set_facecolor(colours[p - 1])
                        body.set_edgecolor(colours[p - 1])
                        body.set_alpha(0.25)
                for p, v in zip(positions, values):
                    ax.plot([p - 0.18, p + 0.18], [np.median(v)] * 2, color='black',
                            linewidth=1.5, zorder=4)
                few = [g for g, v in zip(names, values) if len(v) < 10]
                if few:
                    footnote = ("Fewer than 10 values in " + ", ".join(few)
                                + ": the violin shape is unreliable there.")
            rng = np.random.default_rng(0)
            for p, v, colour in zip(positions, values, colours):
                jitter = rng.uniform(-0.12, 0.12, len(v))
                ax.scatter(np.full(len(v), p) + jitter, v, s=14, alpha=0.7,
                           color=colour, zorder=3)
                mean = float(np.mean(v))
                if kind == 'ci':
                    if len(v) >= 2:
                        from scipy import stats as _stats
                        half = (_stats.t.ppf(0.975, len(v) - 1) * np.std(v, ddof=1)
                                / np.sqrt(len(v)))
                        ax.errorbar(p + 0.25, mean, yerr=half, fmt='none', ecolor='black',
                                    elinewidth=1.3, capsize=5, zorder=5)
                    ax.plot([p + 0.12, p + 0.38], [mean] * 2, color='#E65100', linewidth=2,
                            zorder=6)
                else:
                    ax.plot([p - 0.25, p + 0.25], [mean] * 2, color='#E65100', linewidth=1.5,
                            zorder=4)
            if kind == 'ci':
                footnote = ("Orange: mean; black bar: 95 % confidence interval of the mean "
                            "(t distribution).")
            elif kind == 'violin':
                footnote = ("Black: median; orange: mean. " + footnote).strip()
            ax.set_xticks(positions)
            ax.set_xticklabels([f"{g}\n(n={len(self.data[g])})" for g in names], fontsize=8)
            ax.set_xlim(0.4, len(names) + 0.6)
        import textwrap
        ax.set_ylabel(textwrap.fill(self.value_label(), 48), fontsize=9)
        r = self.comparison
        if r and r['test']:
            left_out = getattr(self, 'left_out_groups', [])
            title = f"{r['test']}: {gs.p_text(r['p'])}"
            if left_out:
                title += ("\nnot in the test: group " if len(left_out) == 1
                          else "\nnot in the test: groups ") + ", ".join(left_out)
            ax.set_title(title, fontsize=9, color='#B71C1C' if left_out else 'black')
        if footnote:
            import textwrap as _tw
            fig.text(0.01, 0.005, _tw.fill(footnote, 140), fontsize=7.5, color='#555555',
                     va='bottom')
            fig.tight_layout(rect=(0, 0.05, 1, 1))
        else:
            fig.tight_layout()
        self.canvas.draw_idle()
        self.save_plot_btn.setEnabled(bool(names))

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

    def done(self, r):
        try:
            self.remembered_settings.update(self.value_settings())
        except Exception:
            logger.exception("Group statistics: remembering the settings failed")
        super().done(r)

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
