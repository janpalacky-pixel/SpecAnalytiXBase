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
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from src.modules.utils.app_logger import get_logger
from src.modules.visualization_analysis import group_statistics as gs
from src.modules.visualization_analysis import group_values as gv
from src.modules.visualization_analysis import group_tests as gt
from src.modules.visualization_analysis import group_spectra as gsp
from src.modules.visualization_analysis import dot_spread as ds
from src.views.dialogs.visualization_analysis.peak_fit_settings_dialog import (
    PeakFitSettingsDialog, load_settings as load_peak_fit_settings,
    save_settings as save_peak_fit_settings)
from src.views.dialogs.misc.fill_column_table import FillColumnTable
from src.modules.visualization.safe_layout import safe_tight_layout
from src.views.dialogs.misc.splitter_utils import no_collapse, scrollable_panel

logger = get_logger(__name__)

def _help_button(parent, title, text, tooltip):
    """Small orange '?' button (the app's context-help style) that shows
    `text` (rich text) in a message box."""
    btn = QPushButton('?')
    btn.setFixedSize(22, 22)
    btn.setAutoDefault(False)
    btn.setStyleSheet(
        'QPushButton { background-color:#F57C00; color:white; font-weight:bold; border:none; '
        'border-radius:4px; }'
        'QPushButton:hover { background-color:#E65100; }'
        'QPushButton:pressed { background-color:#BF360C; }')
    btn.setToolTip(tooltip)

    def show():
        box = QMessageBox(parent)
        box.setWindowTitle(title)
        box.setTextFormat(Qt.RichText)
        box.setText(text)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec_()
    btn.clicked.connect(show)
    return btn


_HELP_GROUPS = (
    "<h3>Groups and samples</h3>"
    "<p><b>Group</b>: what you compare (e.g. control / treated). A spectrum without a group is "
    "left out.</p>"
    "<p><b>Sample</b> (optional): which independent sample (specimen, culture, cuvette, map, "
    "cell, &hellip;) a spectrum comes from. Needed when several spectra come from one sample "
    "&mdash; they are not independent replicates (tick <i>One value per sample</i> in box 3) "
    "&mdash; and for the paired tests (the same sample name in both groups).</p>"
    "<p>Both columns work like a spreadsheet: type, drag the green square down, Ctrl+D, "
    "Ctrl+C / Ctrl+V (also from Excel), Delete, Ctrl+Z; right-click for more.</p>"
    "<p><b>Automatic:</b> if the data came from an Excel workbook with a sheet "
    "<i>Groups</i>, or a file <i>&lt;data file&gt;_groups.csv</i> lies next to the data file "
    "(columns: spectrum name, group, sample), the window fills both columns by itself when it "
    "opens with no groups set. <b>From table file&hellip;</b> loads such a table by hand.</p>"
    "<p><b>The buttons</b> &mdash; the same five for both columns (row <b>Group:</b> and row "
    "<b>Sample:</b>): <i>Set for selected rows&hellip;</i>, <i>From names&hellip;</i>, <i>From a "
    "property&hellip;</i> (a number stored with the spectra, Spectrum properties, e.g. pH: every "
    "value its own, or two split at a value), <i>From table file&hellip;</i>, <i>Clear</i>.</p>"
    "<p>A column made <i>From a property</i> or <i>From names</i> is <b>worked out again from "
    "the current values</b> each time the window opens (a changed or deleted property, an "
    "earlier state in the History, a renamed spectrum); the green line under the buttons says "
    "so. Edit the column yourself to keep it fixed.</p>")
_HELP_VALUE = (
    "<h3>Value per spectrum</h3>"
    "<p>The test compares <b>one number per spectrum</b>. The list has three parts:</p>"
    "<ul><li><b>One band</b> &mdash; a metric over one range (area, mean, maximum, peak "
    "position, FWHM, fitted peak values, &hellip;) or the intensity at x.</li>"
    "<li><b>Two bands</b> &mdash; a value from range A and one from range B, combined "
    "(A / B, log&#8322;(A/B), &hellip;). Ratios do not depend on the overall intensity "
    "(focus, concentration).</li>"
    "<li><b>Whole spectrum</b> &mdash; PCA score, SVD coefficient, correlation with or "
    "distance from a reference group; only for spectra with the same x-axis.</li></ul>"
    "<p>A spectrum that does not completely cover the range (or x) gets no value and is "
    "named in red. Help (bottom right) explains every value.</p>")
_HELP_TEST = (
    "<h3>Which test?</h3><ul>"
    "<li><b>Parametric</b> (default): compares means; Welch t-test, one-way ANOVA.</li>"
    "<li><b>Non-parametric</b>: compares ranks; robust to outliers and skewed values.</li>"
    "<li><b>Unequal spread</b>: Welch ANOVA + Games&ndash;Howell, when the groups clearly "
    "differ in spread (Brown&ndash;Forsythe check in the Test tab).</li>"
    "<li><b>Non-parametric + Dunn</b>: Kruskal&ndash;Wallis with its standard pairwise "
    "follow-up.</li>"
    "<li><b>Permutation test</b>: no distribution assumed; good for small groups.</li>"
    "<li><b>Paired</b>: the <i>same</i> samples in two groups (before / after), matched by "
    "the Sample column; finds small consistent changes that unpaired tests miss.</li></ul>"
    "<p>With three or more groups every pair is tested too (corrected p).</p>")
_HELP_REPLICATES = (
    "<h3>One value per sample</h3>"
    "<p>Many spectra of one sample (pixels of one map, temperatures of one melt, repeated "
    "scans of one cuvette) are <b>not independent</b>. Testing them as if they were makes "
    "the p-value far too small: 500 pixels of one map against 500 of another compares two "
    "maps, not two treatments.</p>"
    "<p>With this ticked, the spectra of each sample (Sample column) are averaged first, so "
    "the test uses one value per independent sample. When the Sample column gives several "
    "spectra of a group the same sample and this is not ticked, a red warning appears. With "
    "an empty Sample column nothing changes.</p>")
_HELP_SPECTRA = (
    "<h3>Spectra: where along x do the groups differ?</h3>"
    "<p>Instead of one value per spectrum, the groups are compared at <b>every point</b> of "
    "the spectrum. The upper plot shows the mean spectrum of each group with a band "
    "(mean &plusmn; SD, or the 95&nbsp;% CI of the mean); the lower plot the corrected "
    "p-value at each point (&minus;log<sub>10</sub>: higher = stronger). Regions where the "
    "groups differ significantly are shaded yellow.</p>"
    "<ul><li>First line: <b>PERMANOVA</b>, one overall test of the whole spectra (do the "
    "groups differ at all?).</li>"
    "<li><b>Test</b> and <b>One value per sample</b> are taken from box 3.</li>"
    "<li><b>Normalize</b>: spectra with different overall intensity should be normalized "
    "first. <i>Divide by the maximum in a band</i> that does not change (e.g. a reference "
    "band) is usually clearest; <i>Unit area</i> and <i>SNV</i> spread a change of one band "
    "over the whole spectrum.</li>"
    "<li><b>Correction</b>: hundreds of points are tested, so the p-values are corrected. "
    "<i>False discovery rate</i> (default): about 5&nbsp;% of the shaded points may be chance "
    "findings &mdash; read regions, not single points. <i>Holm</i> is stricter.</li>"
    "<li>Spectra on different x-axes are interpolated onto the points of the coarsest one.</li>"
    "</ul>")
_HELP_PLOT = (
    "<h3>Plot</h3><ul>"
    "<li><b>Box plot</b>: median, middle half of the values, every spectrum as a dot, the "
    "mean in orange.</li>"
    "<li><b>Violin plot</b>: the shape of each group (e.g. two clusters); unreliable with "
    "fewer than about 10 values.</li>"
    "<li><b>Points with mean &plusmn; 95 % CI</b>: the mean and the range in which the true "
    "mean probably lies &mdash; matches the t-test / ANOVA.</li></ul>"
    "<p><b>Dots</b>: the <i>height</i> of a dot is its value; its sideways position means "
    "nothing &mdash; it only keeps dots with similar values from covering each other. "
    "<i>Automatic</i> (default): a beeswarm when it fits, otherwise the density-scaled "
    "spread (many values, e.g. ROI regions of a map). <i>Random jitter</i>: a small "
    "random-looking shift, fixed for each spectrum. <i>Beeswarm</i>: dots side by side, "
    "none covers another, the width shows where the values crowd; very wide for hundreds "
    "of dots. <i>Density-scaled</i>: spread wider where many values lie close together, "
    "for any number of dots. Each choice always gives the same picture for the same data.</p>"
    "<p><b>Order of the groups</b>: the order of the group table the groups were read from "
    "(e.g. control, low dose, high dose), otherwise the order of the spectra list.</p>"
    "<p><b>Mark outliers</b> circles values outside 1.5 &times; the interquartile range; they "
    "are not removed. <b>Save plot&hellip;</b>: PNG, TIFF, SVG, PDF.</p>")
_HELP_RESULTS = (
    "<h3>Reading the Test tab</h3><ul>"
    "<li><b>p</b>: below 0.05 is usually read as a significant difference; it says nothing "
    "about how large the difference is.</li>"
    "<li><b>How large is the difference?</b>: the difference with its 95 % confidence "
    "interval, and the effect size (Hedges' g) with its interval.</li>"
    "<li><b>Checks of the test's assumptions</b>: bell shape and equal spread, with advice "
    "&mdash; information only.</li>"
    "<li><b>Possible outliers</b>: named, never removed.</li>"
    "<li><b>Results sentence</b>: ready for a paper &mdash; <i>Copy results "
    "sentence</i>.</li></ul>")

_DOT_AREA = 14          # scatter size of a dot (points^2)

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

BAND_TEXT = {'sd': "mean ± SD", 'ci': "mean ± 95 % CI"}
# light colours for the Sample column (one per sample name)
_SAMPLE_TINTS = ['#FFF3B0', '#D7EEFF', '#E8DAFF', '#DDF3D2', '#FFE0CC', '#F7D6EA',
                 '#D2F2EE', '#F0F0C4', '#E2E2FF', '#FFD9D9', '#E6EEF5', '#F2E2CF']


def _tint(colour, strength=0.28):
    """A light version of a plot colour for a table cell (text stays readable)."""
    c = QColor(colour)
    mix = lambda v: int(round(255 - (255 - v) * strength))
    return QColor(mix(c.red()), mix(c.green()), mix(c.blue())).name()
_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _exact_p(p, method=None):
    """' (p = 6.1 × 10⁻⁸)' when p is shown as '< 0.0001', so that tests can be
    told apart; for the permutation test the smallest possible p instead."""
    try:
        p = float(p)
    except (TypeError, ValueError):
        return ''
    if not np.isfinite(p) or p >= 1e-4:
        return ''
    if method == 'permutation':
        return f" (the smallest possible with {gt.N_PERMUTATIONS} permutations)"
    if p <= 0:
        return " (p < 10⁻³⁰⁰)"
    mant, exp = f"{p:.1e}".split('e')
    return f" (p = {mant} × 10{str(int(exp)).translate(_SUPERSCRIPT)})"
_GROUP_COLOURS = ['#1565C0', '#C62828', '#2E7D32', '#EF6C00', '#6A1B9A', '#00838F',
                  '#AD1457', '#5D4037', '#455A64', '#9E9D24']


class PropertyToGroupsDialog(QDialog):
    """Groups from a value stored with the spectra (Spectrum properties, or
    read from the file): every value its own group, or two groups split at
    a value. Shows how many spectra each group gets before OK."""

    def __init__(self, spectra, parent=None, what="Groups"):
        super().__init__(parent)
        from src.modules.visualization import color_by_value as cbv
        self.spectra = spectra
        self.setWindowTitle(f"{what} from a property")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        v = QVBoxLayout(self)
        intro = QLabel(f"{what} from a number stored with each spectrum (set in Spectrum "
                       "properties, or read from the file, e.g. temperature_C). They are worked "
                       "out again from the current values each time Group Statistics opens.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        form = QFormLayout()
        self.key_combo = QComboBox()
        self.key_combo.addItems(cbv.metadata_keys(spectra))
        form.addRow("Property:", self.key_combo)
        self.each_radio = QRadioButton("Each value is a group (e.g. pH 7, pH 7.4, pH 8)")
        self.split_radio = QRadioButton("Two groups, split at:")
        self.each_radio.setChecked(True)
        self.split_spin = QDoubleSpinBox()
        self.split_spin.setRange(-1e12, 1e12)
        self.split_spin.setDecimals(4)
        self.split_spin.setToolTip("Below this value one group, from this value on the other")
        split_row = QHBoxLayout()
        split_row.addWidget(self.split_radio)
        split_row.addWidget(self.split_spin, 1)
        v.addLayout(form)
        v.addWidget(self.each_radio)
        v.addLayout(split_row)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        v.addWidget(self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        v.addWidget(buttons)
        self.key_combo.currentIndexChanged.connect(self._key_changed)
        for w in (self.each_radio, self.split_radio):
            w.toggled.connect(self._update_preview)
        self.split_spin.valueChanged.connect(lambda *_: self.split_radio.setChecked(True))
        self.split_spin.valueChanged.connect(self._update_preview)
        self._key_changed()
        self.resize(460, self.sizeHint().height())

    def _key_changed(self, *_):
        """A new property: the split starts at the median of its values."""
        values = [gs.property_value(s, self.key_combo.currentText()) for s in self.spectra]
        values = [x for x in values if x is not None]
        self.split_spin.blockSignals(True)
        self.split_spin.setValue(float(np.median(values)) if values else 0.0)
        self.split_spin.blockSignals(False)
        self._update_preview()

    def recipe(self):
        """How the column is made (gs.column_from_recipe), or None."""
        key = self.key_combo.currentText()
        if not key:
            return None
        split = self.split_spin.value() if self.split_radio.isChecked() else None
        return {'kind': 'property', 'key': key, 'split': split}

    def groups(self):
        recipe = self.recipe()
        if recipe is None:
            return [gs.NO_GROUP] * len(self.spectra)
        return gs.column_from_recipe(recipe, self.spectra, [])

    def _update_preview(self, *_):
        groups = self.groups()
        counts = {}
        for g in groups:
            if g:
                counts[g] = counts.get(g, 0) + 1
        missing = sum(1 for g in groups if not g)
        if not self.key_combo.count():
            text = "The spectra have no stored numbers yet - set them in Spectrum properties."
        elif not counts:
            text = "No spectrum has this value."
        else:
            text = f"{len(counts)} group(s): " + ", ".join(f"{g} ({n})" for g, n in counts.items())
            if missing:
                text += f"; {missing} spectrum/spectra without a value (no group)"
            if len(counts) > 8:
                text += (". That is many groups - consider \"Two groups, split at\" "
                         "(e.g. for a temperature series).")
        self.preview.setText(text)
        self.ok_button.setEnabled(bool(counts))


class NamesToGroupsDialog(QDialog):
    """Groups from the spectrum names: 'contains' rules or a part of the name."""

    def __init__(self, labels, parent=None, title="Groups from spectrum names"):
        super().__init__(parent)
        self.setWindowTitle(title)
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
        # how to write the rules - always shown (a placeholder text in the box
        # would disappear as soon as the first rule is typed)
        self.rules_hint = QLabel(
            "One rule per line:  <b>text = group name</b>, e.g. <code>ctrl = Control</code>. "
            "Just the text: it becomes the group name. The first matching rule wins; "
            "upper/lower case is ignored.")
        self.rules_hint.setWordWrap(True)
        self.rules_hint.setStyleSheet("color:#666; margin-left:18px;")
        layout.addWidget(self.rules_hint)
        self.rules_edit = QPlainTextEdit()
        self.rules_edit.setPlaceholderText("ctrl = Control\ntreat = Treated")
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

    def recipe(self):
        """How the column is made (gs.column_from_recipe)."""
        if self.root_radio.isChecked():
            return {'kind': 'names', 'mode': 'root'}
        if self.contains_radio.isChecked():
            return {'kind': 'names', 'mode': 'contains',
                    'rules': [list(r) for r in self.rules()]}
        return {'kind': 'names', 'mode': 'part', 'separators': self.separators_edit.text() or '_',
                'part': self.part_spin.value()}

    def groups(self):
        return gs.column_from_recipe(self.recipe(), [{} for _ in self.labels], self.labels)

    def _update_preview(self, *_):
        groups = self.groups()
        counts = {}
        for g in groups:
            counts[g] = counts.get(g, 0) + 1
        named = [f"{g} ({n})" for g, n in counts.items() if g != gs.NO_GROUP]
        none = counts.get(gs.NO_GROUP, 0)
        if named:
            text = (f"{len(named)} group{'s' if len(named) != 1 else ''}: "
                    + ", ".join(named[:12]) + (" \u2026" if len(named) > 12 else ""))
            if none:
                text += f"; {none} spectr{'um' if none == 1 else 'a'} without a group"
        else:
            text = (f"No groups yet: {none} spectr{'um' if none == 1 else 'a'} without a group "
                    "\u2013 write the rules above, or choose another way.")
        self.preview.setText(text)


def repeated_samples_text(groups, samples, values=None, what="this test", order=None):
    """The warning for a sample name given to several spectra of ONE group,
    or '' if there is none. Says which names, what the program assumes and
    what to do -- not what happens to the p-value (that depends on the data).
    The same name in different groups is fine (it pairs them) and is said so
    when it occurs."""
    rep = gt.repeated_sample_names(groups, samples, values)
    if not rep:
        return ""
    rep = {g: rep[g] for g in gs.ordered_names(list(rep), order)}   # groups in plot order
    parts = []
    for g, names in rep.items():
        shown = ", ".join(f"{smp} ({n} spectra)" for smp, n in names[:3])
        if len(names) > 3:
            shown += f" and {len(names) - 3} more"
        parts.append(f"\u201c{g}\u201d: {shown}")
    one = len(rep) == 1 and len(next(iter(rep.values()))) == 1
    text = ("\u26a0 A sample name is used more than once within a group \u2014 "
            + "; ".join(parts) + ". Spectra with the same sample name in one group are taken as "
            + ("one sample measured more than once" if one else "measurements of one sample")
            + " (not independent replicates), but " + what + " counts every spectrum "
            "as a separate sample. If they are measurements of one sample, tick "
            "\u201cOne value per sample\u201d; if they are different samples, give them "
            "different sample names.")
    # a name in two groups (s7 before / s7 after) is not a problem: say so
    in_groups = {}
    for i, (g, smp) in enumerate(zip(groups, samples)):
        if g != gs.NO_GROUP and smp and (values is None or np.isfinite(values[i])):
            in_groups.setdefault(smp, [])
            if g not in in_groups[smp]:
                in_groups[smp].append(g)
    shared = [(smp, gr) for smp, gr in in_groups.items() if len(gr) > 1]
    if shared:
        smp, gr = shared[0]
        text += (f" (The same name in different groups, e.g. {smp} in \u201c{gr[0]}\u201d "
                 f"and \u201c{gr[1]}\u201d, is fine: it marks one sample measured in both "
                 "groups.)")
    return text


def paired_note(n_pairs, groups, samples, values, group_a, group_b):
    """'N pairs (Sample column).' plus what the paired test left out: sample
    names found in only one of the two groups, and spectra without a name."""
    only, no_name = gt.unpaired_samples(groups, samples, values, group_a, group_b)
    text = f"{n_pairs} pair{'s' if n_pairs != 1 else ''} (Sample column)."
    parts = []
    for g in (group_a, group_b):
        names = [smp for smp, grp in only.items() if grp == g]
        if names:
            shown = ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5
                                             else "")
            parts.append(f"{shown} (only in \u201c{g}\u201d)")
    if no_name:
        parts.append(f"{no_name} spectr{'um' if no_name == 1 else 'a'} without a sample name")
    if parts:
        text += (" Left out \u2014 no partner with the same sample name in the other group: "
                 + "; ".join(parts) + ".")
    return text


class GroupStatisticsDialog(QDialog):

    def __init__(self, spectra, parent=None, saved_groups=None, saved_settings=None,
                 source_note=None):
        # source_note (optional): where the groups came from when another
        # window opens this one with its groups (e.g. ROI regions of a 2D map);
        # shown under the table instead of looking for a group table file.
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
        # The groups / samples are remembered by the spectrum's identity
        # (metadata unique_id), not its name: a renamed spectrum keeps its
        # group, and the same file imported again starts without the old
        # groups (its own Groups sheet fills them in again). Spectra without
        # a unique_id (only possible outside the normal import) use the name.
        self.keys = [(s.get('metadata') or {}).get('unique_id') or lab
                     for s, lab in zip(self.spectra, self.labels)]
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
        # both sides in scroll areas: their contents need ~540 + ~930 px, more
        # than the window is wide, so the handle could hardly move (and
        # dragging further hid a side completely)
        splitter.addWidget(scrollable_panel(self._build_groups_panel(), 300))
        splitter.addWidget(scrollable_panel(self._build_right_panel(), 400))
        no_collapse(splitter)
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
        self._apply_recipes()         # columns from a property / the names: current values
        self._update_group_summary()
        if source_note:
            self.table_source.setText(source_note)
            self.table_source.setVisible(True)
        else:
            self._load_own_group_table()
        self._update_reference_choices()
        self.set_value_settings(dict(self.remembered_settings))
        j = self.plot_combo.findData(self.remembered_settings.get('plot'))
        if j >= 0:
            self.plot_combo.setCurrentIndex(j)
        j = self.dots_combo.findData(self.remembered_settings.get('dots'))
        if j >= 0:
            self.dots_combo.setCurrentIndex(j)
        j = self.test_combo.findData(self.remembered_settings.get('test'))
        if j >= 0:
            self.test_combo.setCurrentIndex(j)
        self._update_test_choices(opening=True)
        self._colour_table()
        self.per_sample_check.setChecked(bool(self.remembered_settings.get('per_sample')))
        self.outliers_check.setChecked(bool(self.remembered_settings.get('mark_outliers')))
        # Changing the test or 'One value per sample' recomputes what is shown
        # (the values themselves are reused, see _values_cache), so a result on
        # screen never belongs to another test.
        self._values_cache = None
        self.test_combo.currentIndexChanged.connect(self._recompute_shown)
        # results on screen that no longer match the groups / samples / value
        self._result_state = None
        for w in self.value_form.parentWidget().findChildren(QComboBox):
            w.currentIndexChanged.connect(self._check_outdated)
        for w in self.value_form.parentWidget().findChildren(QDoubleSpinBox):
            w.valueChanged.connect(self._check_outdated)
        for w in self.value_form.parentWidget().findChildren(QSpinBox):
            w.valueChanged.connect(self._check_outdated)
        for w in self.value_form.parentWidget().findChildren(QCheckBox):
            w.toggled.connect(self._check_outdated)
        self.per_sample_check.toggled.connect(self._recompute_shown)
        # No default button: Qt makes the first button ("Set group of selected
        # rows...") the dialog's default, so Enter in a table cell that is not
        # being edited, or in a number box, opened the Set group dialog.
        for btn in self.findChildren(QPushButton):
            btn.setAutoDefault(False)
            btn.setDefault(False)

    # ------------------------------------------------------------------ groups
    def _build_groups_panel(self):
        box = QGroupBox("1. Groups")
        lay = QVBoxLayout(box)
        # Spreadsheet-like Group column: fill handle, Ctrl+D, copy/paste,
        # Delete, Ctrl+Z (see fill_column_table.py)
        saved_samples = self.remembered_settings.setdefault('_samples', {})
        self.table = FillColumnTable(
            self.labels, [self.saved_groups.get(k, gs.NO_GROUP) for k in self.keys],
            headers=("Spectrum", "Group"),
            extra_columns=[("Sample (optional)", [saved_samples.get(k, '') for k in self.keys])])
        self.table.horizontalHeaderItem(2).setToolTip(
            "Optional: which independent sample (specimen, culture, cuvette, map, ...) a\n"
            "spectrum comes from. Spectra of one sample are not independent replicates:\n"
            "tick 'One value per sample' (box 3) to test sample means. The same sample\n"
            "name in two groups pairs them for the paired tests (before / after).")
        # Both columns: width adjustable by dragging the header border;
        # the Group column also takes any spare width at the right
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 110)
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

        # The same five ways for the Group and the Sample column, in two rows
        # (one column of the grid = one way): by hand for the selected rows,
        # from the names, from a stored value, from a table file, clear.
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        G, S = "Group", "Sample"
        rows = (
            (G, (("Set for selected rows\u2026", self.set_group_of_selected,
                  "Select rows (click, Shift+click, Ctrl+click), then give them a group"),
                 ("From names\u2026", self.groups_from_names,
                  "Groups from the spectrum names: a text they contain, or a part of the name"),
                 ("From a property\u2026", lambda: self.groups_from_property(),
                  "Groups from a number stored with the spectra (Spectrum properties, e.g. "
                  "pH): each value a group, or split at a value"),
                 ("From table file\u2026", self.groups_from_table_file,
                  "A CSV or Excel file with two columns: spectrum name, group (a third column: "
                  "the sample)"),
                 ("Clear all groups", lambda: self._set_groups([gs.NO_GROUP] * len(self.labels)),
                  "Remove the groups of all spectra (Ctrl+Z brings them back). To remove\n"
                  "only some, select their rows and press Delete (or right-click)."))),
            (S, (("Set for selected rows\u2026", self.set_sample_of_selected,
                  "Optional Sample column: which independent sample the selected spectra "
                  "come from"),
                 ("From names\u2026", self.samples_from_names,
                  "Sample column from the spectrum names (e.g. the file part of the name)"),
                 ("From a property\u2026", lambda: self.samples_from_property(),
                  "Sample column from a number stored with the spectra (e.g. a cuvette or "
                  "culture number set in Spectrum properties)"),
                 ("From table file\u2026", self.samples_from_table_file,
                  "A CSV or Excel file with two columns: spectrum name, sample (or three: "
                  "name, group, sample)"),
                 ("Clear all samples",
                  lambda: self.table.set_values([''] * len(self.labels), col=2),
                  "Remove the samples of all spectra (Ctrl+Z brings them back)"))),
        )
        self.column_buttons = {}
        for r, (what, entries) in enumerate(rows):
            label = QLabel(f"<b>{what}:</b>")
            grid.addWidget(label, r, 0)
            for c, (text, slot, tip) in enumerate(entries, start=1):
                b = QPushButton(text)
                b.setToolTip(tip)
                b.clicked.connect(lambda _checked=False, f=slot: f())
                grid.addWidget(b, r, c)
                self.column_buttons[(what, c)] = b
        grid.addWidget(_help_button(self, "Groups and samples", _HELP_GROUPS,
                                    "What the Group and Sample columns are, and how to fill "
                                    "them"), 0, 6)
        lay.addLayout(grid)
        # where the columns come from, when they are worked out again on opening
        self.recipe_note = QLabel()
        self.recipe_note.setWordWrap(True)
        self.recipe_note.setStyleSheet("color:#2E7D32;")
        self.recipe_note.setVisible(False)
        lay.addWidget(self.recipe_note)
        self.table_source = QLabel()
        self.table_source.setWordWrap(True)
        self.table_source.setStyleSheet("color:#2E7D32;")
        self.table_source.setVisible(False)
        lay.addWidget(self.table_source)
        self.group_summary = QLabel()
        self.group_summary.setWordWrap(True)
        lay.addWidget(self.group_summary)
        return box

    def groups(self):
        return [v.strip() for v in self.table.values()]

    def group_order(self):
        """The preferred order of the groups: the order of the group table
        they were read from (remembered for the session), else []."""
        return list(self.remembered_settings.get('group_order') or [])

    def _ordered(self, names):
        """names in the preferred order (group_order first, then the rest in
        order of first appearance)."""
        return gs.ordered_names(names, self.group_order())

    def _load_own_group_table(self):
        """If no group is set yet and the spectra's own data file has a group
        table (sheet 'Groups' in the workbook, or '<data file>_groups.csv'
        next to it), fill the Group / Sample columns from it (Ctrl+Z or
        Clear removes them)."""
        if any(self.groups()):
            return
        path = gs.find_group_table(self.spectra)
        if not path:
            return
        try:
            mapping, sample_map = gs.read_group_sample_table(path, labels=self.labels)
        except Exception:
            logger.exception("Reading the data file's group table failed")
            return
        groups = gs.groups_from_own_table(self.spectra, self.labels, path, mapping)
        if not any(groups):
            return
        # the groups keep the order of the table (e.g. control, low dose,
        # high dose), not of the spectra list (sorted by name: high before low)
        self.remembered_settings['group_order'] = gs.table_group_order(mapping)
        self._set_groups(groups)
        if sample_map:
            # same undo step as the groups: one Ctrl+Z removes both
            self.table.set_values(
                gs.groups_from_own_table(self.spectra, self.labels, path, sample_map),
                record_undo=False, col=2)
        where = (f"sheet \u201cGroups\u201d of {os.path.basename(path)}"
                 if path.lower().endswith(('.xlsx', '.xlsm'))
                 and not path.lower().endswith('_groups.xlsx') else os.path.basename(path))
        self.table_source.setText(
            f"Groups{' and samples' if sample_map else ''} filled in from the {where} "
            f"(Ctrl+Z or \u201cClear all groups\u201d removes them).")
        self.table_source.setVisible(True)
        self.loaded_group_table = path

    def samples(self):
        """The optional Sample column ('' = not given)."""
        return [v.strip() for v in self.table.values(2)]

    def set_sample_of_selected(self):
        rows = self.table.selected_rows()
        if not rows:
            QMessageBox.information(self, "Group Statistics",
                                    "Select one or more rows in the table first.")
            return
        names = [s for s in dict.fromkeys(self.samples()) if s]
        name, ok = QInputDialog.getItem(self, "Set sample", f"Sample for {len(rows)} spectra:",
                                        names or ["Sample 1"], 0, True)
        if ok:
            self.table.set_rows(rows, name.strip(), col=2)

    def samples_from_names(self):
        dlg = NamesToGroupsDialog(self.labels, self, title="Samples from spectrum names")
        if dlg.exec_() == QDialog.Accepted:
            self._fill_from_recipe('sample', dlg.recipe())

    def samples_from_property(self):
        dlg = PropertyToGroupsDialog(self.spectra, self, what="Samples")
        if dlg.exec_() == QDialog.Accepted and dlg.recipe() is not None:
            self._fill_from_recipe('sample', dlg.recipe())

    def samples_from_table_file(self):
        """The Sample column from a table file: spectrum name, sample (or
        name, group, sample: then the third column)."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Table of samples", "",
            "Tables (*.csv *.txt *.tsv *.xlsx *.xls);;All files (*)")
        if not path:
            return
        try:
            second, third = gs.read_group_sample_table(path, labels=self.labels)
        except Exception as exc:
            logger.exception("Reading the sample table failed")
            QMessageBox.warning(self, "Group Statistics", f"The table could not be read:\n{exc}")
            return
        mapping = third or second
        samples = gs.groups_from_table(self.labels, mapping)
        self.table.set_values(samples, col=2)
        found = sum(1 for v in samples if v)
        QMessageBox.information(self, "Group Statistics",
                                f"{found} of {len(samples)} spectra were found in the table "
                                f"(column {'3' if third else '2'}: the sample).")

    # -- columns worked out from a recipe ("From a property...", "From names...")
    _COLUMN = {'group': 1, 'sample': 2}

    def _fill_from_recipe(self, which, recipe):
        """Fill the Group or Sample column from the recipe now (one undo
        step) and remember the recipe, so the column is worked out again
        from the current values each time the window opens."""
        values = gs.column_from_recipe(recipe, self.spectra, self.labels)
        if values is None:
            return
        self.remembered_settings[f'{which}_recipe'] = recipe
        if which == 'group':
            self.remembered_settings['group_order'] = []     # order of the spectra list
        self._applying_recipe = True
        try:
            self.table.set_values(values, col=self._COLUMN[which])
        finally:
            self._applying_recipe = False
        self._update_recipe_note()

    def _apply_recipes(self):
        """On opening: the columns made by a recipe, from the current values
        (a changed or deleted property, an earlier state in the History, a
        renamed spectrum) - not the remembered, possibly stale ones."""
        changed = []
        for which in ('group', 'sample'):
            recipe = self.remembered_settings.get(f'{which}_recipe')
            values = gs.column_from_recipe(recipe, self.spectra, self.labels) if recipe else None
            if values is None:
                self.remembered_settings.pop(f'{which}_recipe', None)
                continue
            col = self._COLUMN[which]
            if [v.strip() for v in self.table.values(col)] != values:
                self._applying_recipe = True
                try:
                    self.table.set_values(values, record_undo=False, col=col)
                finally:
                    self._applying_recipe = False
                changed.append(which)
        self._update_recipe_note(updated=changed)

    def _forget_changed_recipes(self):
        """A column edited by hand (typed, pasted, set for rows, a table
        file, cleared) is no longer the recipe's: keep it as it is."""
        if getattr(self, '_applying_recipe', False):
            return
        for which in ('group', 'sample'):
            recipe = self.remembered_settings.get(f'{which}_recipe')
            if recipe is None:
                continue
            col = self._COLUMN[which]
            if [v.strip() for v in self.table.values(col)] != \
                    gs.column_from_recipe(recipe, self.spectra, self.labels):
                self.remembered_settings.pop(f'{which}_recipe', None)
        self._update_recipe_note()

    def _update_recipe_note(self, updated=()):
        note = getattr(self, 'recipe_note', None)
        if note is None:
            return
        parts = []
        for which, name in (('group', 'Groups'), ('sample', 'Samples')):
            recipe = self.remembered_settings.get(f'{which}_recipe')
            if recipe:
                parts.append(f"{name} from {gs.recipe_text(recipe)}"
                             + (" \u2013 updated from the current values" if which in updated
                                else ""))
        if parts:
            note.setText("; ".join(parts) + ". Worked out again from the current values each "
                         "time this window opens; edit the column yourself to keep it fixed.")
        note.setVisible(bool(parts))

    def _set_groups(self, groups):
        self.table.set_values(groups)          # one undo step; emits valuesChanged

    def _on_groups_changed(self):
        self._forget_changed_recipes()
        self._remember()
        self._update_group_summary()
        if hasattr(self, 'reference_combo'):
            self._update_reference_choices()
        if hasattr(self, 'test_combo'):
            self._update_test_choices()
        self._colour_table()
        self._check_outdated()

    def _paired_pairs(self):
        """Samples (Sample column) that appear in both groups -- only when
        there are exactly two groups."""
        groups, samples = self.groups(), self.samples()
        names = list(dict.fromkeys(g for g in groups if g))
        if len(names) != 2:
            return 0
        per = {}
        for g, smp in zip(groups, samples):
            if g and smp:
                per.setdefault(smp, set()).add(g)
        return sum(1 for gs_ in per.values() if len(gs_) == 2)

    def _update_test_choices(self, opening=False):
        """The paired tests need exactly two groups and at least 3 samples
        measured in both (the same name in the Sample column): grey them out
        otherwise, with the reason as tooltip. If one of them is chosen and
        there are more than two groups -- or the window opens with it
        remembered from other data -- switch to the parametric test and say
        so. (While the groups and samples are being typed, a chosen paired
        test is kept: Compute then says what is missing.)"""
        n = len({g for g in self.groups() if g})
        pairs = self._paired_pairs() if n == 2 else 0
        ok = n == 2 and pairs >= 3
        if n != 2:
            why = (f"A paired test compares exactly two groups; there are {n}.\n"
                   "Give only two groups (e.g. before / after) to use it.")
        else:
            why = ("A paired test needs the same samples measured in both groups:\n"
                   "the same name in the Sample column (e.g. s1 before / s1 after),\n"
                   f"at least 3 such samples; here {pairs}.")
        model = self.test_combo.model()
        for i in range(self.test_combo.count()):
            if self.test_combo.itemData(i) in gt.PAIRED:
                item = model.item(i)
                item.setEnabled(ok)
                item.setToolTip("" if ok else why)
        if not ok and self.test_combo.currentData() in gt.PAIRED and (n > 2 or (opening and n == 2)):
            # kept until a result shows it (compute() clears it); shown right
            # away too, also when nothing has been computed yet
            self.test_switched_note = (
                (f"The paired test compares exactly two groups (there are {n})"
                 if n > 2 else
                 f"The paired test needs at least 3 samples measured in both groups "
                 f"(the same name in the Sample column; here {pairs})")
                + ": switched to Parametric.")
            if hasattr(self, 'note'):
                self.note.setText(self.test_switched_note)
                self.note.setStyleSheet("color:#E65100;")
            self.test_combo.setCurrentIndex(self.test_combo.findData('parametric'))

    # ------------------------------------------------------------------ colours
    def group_colours(self):
        """{group: colour}: the same colour for a group in the table, the plot
        and the Spectra tab. A group keeps its colour while the window is open
        (a new group -- e.g. a typo -- gets the next free colour instead of
        shifting the colours of the others)."""
        order = self._ordered([g for g in self.groups() if g])
        assigned = self.__dict__.setdefault('_colour_assign', {})
        for g in order:
            if g not in assigned:
                used = {assigned[h] for h in order if h in assigned}
                free = [c for c in _GROUP_COLOURS if c not in used]
                assigned[g] = free[0] if free else _GROUP_COLOURS[len(assigned) % len(_GROUP_COLOURS)]
        return {g: assigned[g] for g in order}

    def _colour_table(self):
        """Group cells tinted with their group's plot colour; Sample cells with
        a light colour per sample (the same sample -- e.g. a pair -- the same
        colour). Signals blocked: a colour is not an edit (no undo step)."""
        t = self.table
        cmap = self.group_colours()
        samples = self.samples()
        smap = {smp: _SAMPLE_TINTS[i % len(_SAMPLE_TINTS)]
                for i, smp in enumerate(dict.fromkeys(x for x in samples if x))}
        empty = QBrush()
        t.blockSignals(True)
        try:
            for r, (g, smp) in enumerate(zip(self.groups(), samples)):
                it = t.item(r, 1)
                if it is not None:
                    it.setBackground(QBrush(QColor(_tint(cmap[g]))) if g in cmap else empty)
                it = t.item(r, 2)
                if it is not None:
                    it.setBackground(QBrush(QColor(smap[smp])) if smp in smap else empty)
        finally:
            t.blockSignals(False)
        t.viewport().update()

    def _table_menu(self, pos):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        rows = self.table.selected_rows()
        set_action = menu.addAction("Set group of selected rows…")
        fill_action = menu.addAction("Fill down (Ctrl+D)")
        menu.addSeparator()
        copy_action = menu.addAction("Copy (Ctrl+C)")
        paste_action = menu.addAction("Paste (Ctrl+V)")
        clear_action = menu.addAction(
            "Clear sample of selected rows (Delete)" if self.table.active_column() == 2
            else "Remove group of selected rows (Delete)")
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
                selection.select(model.index(r, 1), model.index(r, 1))   # Group cell
        mode = {'select': QItemSelectionModel.ClearAndSelect, 'add': QItemSelectionModel.Select,
                'remove': QItemSelectionModel.Deselect}.get(params.get('action', 'select'),
                                                            QItemSelectionModel.ClearAndSelect)
        self.table.selectionModel().select(selection, mode)

    def _remember(self):
        for key, g in zip(self.keys, self.groups()):
            if g:
                self.saved_groups[key] = g
            else:
                self.saved_groups.pop(key, None)
        saved_samples = self.remembered_settings.setdefault('_samples', {})
        for key, smp in zip(self.keys, self.samples()):
            if smp:
                saved_samples[key] = smp
            else:
                saved_samples.pop(key, None)

    def _group_names(self):
        return self._ordered([g for g in self.groups() if g])

    def _update_group_summary(self):
        groups = self.groups()
        counts = {}
        for g in groups:
            counts[g] = counts.get(g, 0) + 1
        cmap = self.group_colours() if hasattr(self, 'table') else {}
        named = [f"<b><span style='color:{cmap.get(g, '#000')}'>{html.escape(g)}</span></b> "
                 f"({counts[g]})" for g in self._ordered(list(counts)) if g != gs.NO_GROUP]
        none = counts.get(gs.NO_GROUP, 0)
        if not named:
            text = "No groups yet."
        else:
            text = f"{len(named)} group{'s' if len(named) != 1 else ''}: " + ", ".join(named)
        if none:
            text += f"<br>{none} spectr{'um' if none == 1 else 'a'} without a group (left out)."
        n_samples = len({smp for smp in self.samples() if smp})
        if n_samples:
            text += f"<br>{n_samples} sample{'s' if n_samples != 1 else ''} named."
        # 4) names that are probably meant to be the same group
        same = {}
        for g in counts:
            if g != gs.NO_GROUP:
                same.setdefault(" ".join(g.lower().split()), []).append(g)
        for names in same.values():
            if len(names) > 1:
                text += ("<br><span style='color:#B71C1C'>\u26a0 "
                         + " and ".join(f"\u201c{html.escape(n)}\u201d" for n in names)
                         + " differ only in upper/lower case or spaces \u2014 they count as "
                         + f"{len(names)} separate groups.</span>")
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
            recipe = dlg.recipe() if hasattr(dlg, 'recipe') else None
            if recipe is not None:
                self._fill_from_recipe('group', recipe)
            else:                                   # a window that only gives the groups
                self.remembered_settings['group_order'] = []
                self._set_groups(dlg.groups())

    def groups_from_property(self):
        dlg = PropertyToGroupsDialog(self.spectra, self)
        if dlg.exec_() == QDialog.Accepted and dlg.recipe() is not None:
            self._fill_from_recipe('group', dlg.recipe())

    def groups_from_table_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Table of groups", "",
            "Tables (*.csv *.txt *.tsv *.xlsx *.xls);;All files (*)")
        if not path:
            return
        try:
            mapping, sample_map = gs.read_group_sample_table(path, labels=self.labels)
        except Exception as exc:
            logger.exception("Reading the group table failed")
            QMessageBox.warning(self, "Group Statistics", f"The table could not be read:\n{exc}")
            return
        groups = gs.groups_from_table(self.labels, mapping)
        found = sum(1 for g in groups if g)
        self.remembered_settings['group_order'] = gs.table_group_order(mapping)
        self._set_groups(groups)
        if sample_map:
            self.table.set_values(gs.groups_from_table(self.labels, sample_map),
                                  record_undo=False, col=2)     # one undo step with the groups
        known = {l.strip().lower() for l in self.labels}
        unmatched = [name for name in mapping if name.strip().lower() not in known]
        text = f"{found} of {len(groups)} spectra were found in the table."
        if sample_map:
            text += " The Sample column was filled too."
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
        kind_row = QWidget()
        kr = QHBoxLayout(kind_row)
        kr.setContentsMargins(0, 0, 0, 0)
        kr.addWidget(self.kind_combo, 1)
        kr.addWidget(_help_button(self, "Value per spectrum", _HELP_VALUE,
                                  "What the value choices mean"))
        form.addRow("Value:", kind_row)
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
        for key, text in gt.METHODS.items():
            self.test_combo.addItem(text, key)
        self.test_combo.setToolTip(
            "Parametric: compares means (Welch t-test for two groups, one-way ANOVA for more).\n"
            "Non-parametric: compares ranks, robust to outliers and skewed values\n"
            "(Mann–Whitney U for two groups, Kruskal–Wallis for more).\n"
            "With three or more groups every pair is also tested (Holm-corrected p).\n"
            "Unequal spread: Welch ANOVA + Games–Howell pairs (groups with different spread);\n"
            "with two groups it is the Welch t-test.\n"
            "… + Dunn: Kruskal–Wallis with Dunn's pairwise test (its standard follow-up);\n"
            "with two groups it is the Mann–Whitney U test.\n"
            "Permutation test: no distribution assumed; good for small groups.\n"
            "Paired: the same samples in two groups (e.g. before / after), matched by the\n"
            "Sample column.")
        test_row = QHBoxLayout()
        test_row.addWidget(self.test_combo, 1)
        test_row.addWidget(_help_button(self, "Which test?", _HELP_TEST, "Which test to choose"))
        tl.addLayout(test_row)
        self.per_sample_check = QCheckBox("One value per sample (average its spectra)")
        self.per_sample_check.setToolTip(
            "Spectra of one sample (map, cuvette, culture, …) are not independent replicates;\n"
            "testing them as if they were makes p far too small. With this ticked, the spectra\n"
            "of each sample (Sample column) are averaged first, so the test uses one value per\n"
            "independent sample. Spectra without a sample count as their own sample.")
        sample_row = QHBoxLayout()
        sample_row.addWidget(self.per_sample_check, 1)
        sample_row.addWidget(_help_button(self, "One value per sample", _HELP_REPLICATES,
                                          "Why spectra of one sample are not independent"))
        tl.addLayout(sample_row)
        self.compute_btn = QPushButton("Compute")
        self.compute_btn.setStyleSheet("font-weight:bold;")
        self.compute_btn.clicked.connect(self.compute)
        self.compute_btn.setToolTip(
            "Compute the values and the test. Needed after changing the groups or the value;\n"
            "a change of the test or of 'One value per sample' recomputes by itself.")
        tl.addWidget(self.compute_btn)
        tl.addStretch(1)
        controls.addWidget(test_box, 2)
        lay.addLayout(controls)

        self.tabs = QTabWidget()
        # A minimum width for the tabs (it once left room for the open tab's
        # bold name; the open tab is no longer bold, see _apply_stylesheet)
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
        plot_row.addWidget(QLabel("Dots:"))
        self.dots_combo = QComboBox()
        for key in ds.MODES:
            self.dots_combo.addItem(ds.MODE_NAMES[key], key)
        self.dots_combo.setToolTip(
            "How the dots are spread sideways. The HEIGHT of a dot is its value; the sideways\n"
            "position means nothing, it only keeps dots with similar values apart.\n"
            "Automatic: a beeswarm when it fits, otherwise the density-scaled spread.\n"
            "Random jitter: a small random-looking shift, fixed for each spectrum.\n"
            "Beeswarm: side by side, no dot covers another (very wide for hundreds of dots).\n"
            "Density-scaled: wider where many values lie close together (any number of dots).")
        self.dots_combo.currentIndexChanged.connect(self._on_plot_type_changed)
        plot_row.addWidget(self.dots_combo)
        self.save_plot_btn = QPushButton("Save plot…")
        self.save_plot_btn.setToolTip("Save the plot as PNG, TIFF, SVG or PDF")
        self.save_plot_btn.setAutoDefault(False)
        self.save_plot_btn.setEnabled(False)
        self.save_plot_btn.clicked.connect(self.save_plot)
        plot_row.addWidget(self.save_plot_btn)
        self.outliers_check = QCheckBox("Mark outliers")
        self.outliers_check.setToolTip("Circle the values outside 1.5 × the interquartile range "
                                       "(Tukey's rule; they are not removed — the Test tab "
                                       "names them)")
        self.outliers_check.toggled.connect(self._on_plot_type_changed)
        plot_row.addWidget(self.outliers_check)
        plot_row.addWidget(_help_button(self, "Plot", _HELP_PLOT, "The plot types"))
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
        tests_tab = QWidget()
        tt = QVBoxLayout(tests_tab)
        tt.setContentsMargins(0, 0, 0, 0)
        tt.addWidget(self.tests_view, 1)
        copy_row = QHBoxLayout()
        self.copy_sentence_btn = QPushButton("Copy results sentence")
        self.copy_sentence_btn.setToolTip("Copy the sentence for a paper (test, statistic, p, "
                                          "effect size with confidence interval, n)")
        self.copy_sentence_btn.setEnabled(False)
        self.copy_sentence_btn.clicked.connect(self.copy_results_sentence)
        copy_row.addWidget(self.copy_sentence_btn)
        copy_row.addWidget(_help_button(self, "Reading the Test tab", _HELP_RESULTS,
                                        "How to read the results"))
        copy_row.addStretch(1)
        tt.addLayout(copy_row)
        self.tabs.addTab(tests_tab, "Test")
        self.values_table = QTableWidget(0, 4)
        self.values_table.setHorizontalHeaderLabels(["Spectrum", "Group", "Value", "Sample"])
        self.values_table.verticalHeader().setVisible(False)
        self.values_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabs.addTab(self.values_table, "Values")
        self._build_spectra_tab()
        lay.addWidget(self.tabs, 1)
        self.outdated_label = QLabel(
            "Groups, samples or the value changed since the last Compute \u2014 press Compute "
            "(or Compare spectra) to update the results.")
        self.outdated_label.setWordWrap(True)
        self.outdated_label.setStyleSheet("color:#E65100; font-style:italic;")
        self.outdated_label.setVisible(False)
        lay.addWidget(self.outdated_label)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color:#555;")
        lay.addWidget(self.note)
        self._update_value_widgets()
        return right

    # ------------------------------------------------------------------ spectra tab
    def _build_spectra_tab(self):
        """Tab 'Spectra': the groups compared at every point along x."""
        rs = self.remembered_settings
        tab = QWidget()
        tl = QVBoxLayout(tab)
        tl.setContentsMargins(4, 4, 4, 4)
        common = gsp.common_range(self.spectra)
        lo, hi = common if common else (0.0, 1.0)
        def small_spin(value):
            sp = self._spin(value, lo, hi)
            sp.setMaximumWidth(95)
            return sp
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Range:"))
        self.sp_from, self.sp_to = small_spin(lo), small_spin(hi)
        for w in (self.sp_from, QLabel("to"), self.sp_to):
            row1.addWidget(w)
        row1.addSpacing(10)
        row1.addWidget(QLabel("Correction:"))
        self.sp_corr_combo = QComboBox()
        for key, text in gsp.CORRECTIONS.items():
            self.sp_corr_combo.addItem(text, key)
        self.sp_corr_combo.setToolTip(
            "Hundreds of points are tested, so the p-values are corrected.\n"
            "FDR (false discovery rate, Benjamini–Hochberg): about 5 % of the shaded points\n"
            "may be chance findings.  Holm: strict — the chance of even one false point is 5 %.")
        row1.addWidget(self.sp_corr_combo)
        row1.addWidget(QLabel("Show:"))
        self.sp_show_combo = QComboBox()
        for key, text in gsp.BANDS.items():
            self.sp_show_combo.addItem(text, key)
        row1.addWidget(self.sp_show_combo)
        row1.addStretch(1)
        tl.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Normalize:"))
        self.sp_norm_combo = QComboBox()
        for key, text in gsp.NORMALIZATIONS.items():
            self.sp_norm_combo.addItem(text, key)
        self.sp_norm_combo.setToolTip(
            "None: the spectra as they are\n"
            "Divide by the maximum in a band: e.g. a reference band that does not change\n"
            "Unit area: each spectrum divided by its area over the compared range\n"
            "SNV: each spectrum (over the compared range) shifted to mean 0, scaled to SD 1")
        row2.addWidget(self.sp_norm_combo)
        band = rs.get('spectra_band') or (lo, hi)
        self.sp_band_from, self.sp_band_to = small_spin(band[0]), small_spin(band[1])
        self.sp_band_row = QWidget()
        br = QHBoxLayout(self.sp_band_row)
        br.setContentsMargins(0, 0, 0, 0)
        for w in (self.sp_band_from, QLabel("to"), self.sp_band_to):
            br.addWidget(w)
        row2.addWidget(self.sp_band_row)
        row2.addStretch(1)
        tl.addLayout(row2)
        row3 = QHBoxLayout()
        self.sp_compare_btn = QPushButton("Compare spectra")
        self.sp_compare_btn.setStyleSheet("font-weight:bold;")
        self.sp_compare_btn.setAutoDefault(False)
        self.sp_compare_btn.setToolTip("Compare the groups at every point (test and 'One value "
                                       "per sample' from box 3)")
        self.sp_compare_btn.clicked.connect(self.compute_spectra)
        row3.addWidget(self.sp_compare_btn)
        self.sp_save_btn = QPushButton("Save plot…")
        self.sp_save_btn.setAutoDefault(False)
        self.sp_save_btn.setEnabled(False)
        self.sp_save_btn.clicked.connect(self.save_spectra_plot)
        row3.addWidget(self.sp_save_btn)
        self.sp_export_btn = QPushButton("Export table…")
        self.sp_export_btn.setAutoDefault(False)
        self.sp_export_btn.setEnabled(False)
        self.sp_export_btn.setToolTip("x, mean, SD and n of each group, p and corrected p")
        self.sp_export_btn.clicked.connect(self.export_spectra_table)
        row3.addWidget(self.sp_export_btn)
        row3.addWidget(_help_button(self, "Spectra", _HELP_SPECTRA,
                                    "Comparing the groups along the whole spectrum"))
        row3.addStretch(1)
        tl.addLayout(row3)
        self.sp_note = QLabel("Compare the groups at every point of the spectrum: choose the "
                              "range and the normalization, then press Compare spectra." if common
                              else "The spectra have no x-range in common: no comparison along "
                              "the spectrum is possible.")
        self.sp_note.setWordWrap(True)
        self.sp_note.setStyleSheet("color:#555;")
        self.sp_note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.sp_note.setMinimumHeight(self.sp_note.fontMetrics().lineSpacing() * 2 + 6)
        tl.addWidget(self.sp_note)               # above the plot: always visible
        self.sp_figure = Figure(figsize=(6, 4))
        self.sp_canvas = FigureCanvas(self.sp_figure)
        self.sp_canvas.setMinimumHeight(260)
        tl.addWidget(self.sp_canvas, 1)
        for combo, key in ((self.sp_norm_combo, 'spectra_norm'),
                           (self.sp_corr_combo, 'spectra_correction'),
                           (self.sp_show_combo, 'spectra_show')):
            j = combo.findData(rs.get(key))
            if j >= 0:
                combo.setCurrentIndex(j)
        self.sp_norm_combo.currentIndexChanged.connect(self._update_spectra_widgets)
        self.sp_show_combo.currentIndexChanged.connect(self._draw_spectra)
        self._update_spectra_widgets()
        self.sp_compare_btn.setEnabled(common is not None)
        self.spectra_result = None
        # in a scroll area, so that this tab's controls do not make the whole
        # window taller (the other tabs need less height)
        from PyQt5.QtWidgets import QScrollArea, QFrame
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(tab)
        scroll.setMinimumHeight(60)
        self.tabs.addTab(scroll, "Spectra")

    def _update_spectra_widgets(self):
        self.sp_band_row.setVisible(self.sp_norm_combo.currentData() == 'band')

    def spectra_settings(self):
        return {'normalization': self.sp_norm_combo.currentData(),
                'band': (self.sp_band_from.value(), self.sp_band_to.value()),
                'rng': (self.sp_from.value(), self.sp_to.value()),
                'correction': self.sp_corr_combo.currentData()}

    def compute_spectra(self):
        """Compare the groups at every point (button 'Compare spectra')."""
        self._spectra_requested = True
        # the groups / samples the Spectra tab now shows (for the outdated hint)
        self._spectra_state = (tuple(self.groups()), tuple(self.samples()))
        st = self.spectra_settings()
        method = self.test_combo.currentData()
        per_sample = self.per_sample_check.isChecked()
        groups, samples = self.groups(), self.samples()
        self.remembered_settings.update({'spectra_norm': st['normalization'],
                                         'spectra_band': st['band'],
                                         'spectra_correction': st['correction'],
                                         'spectra_show': self.sp_show_combo.currentData()})
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = gsp.compare_spectra(self.spectra, groups, samples, method, per_sample,
                                    st['normalization'], st['band'], st['rng'],
                                    st['correction'], order=self.group_order())
            error = None
        except ValueError as exc:
            r, error = None, exc
        finally:
            QApplication.restoreOverrideCursor()
        if error is not None:
            self.spectra_result = None
            self.sp_figure.clear()
            self.sp_canvas.draw_idle()
            hint = (" Choose another test in box 3 \u2014 the tab is then recomputed by itself."
                    if self.test_combo.currentData() in gt.PAIRED else "")
            self.sp_note.setText(str(error) + hint)
            self.sp_note.setStyleSheet("color:#B71C1C;")
            self.sp_save_btn.setEnabled(False)
            self.sp_export_btn.setEnabled(False)
            self._check_outdated()
            return
        self.spectra_result = r
        notes = [t for t in (gsp.overall_text(r), gsp.ranges_text(r)) if t] + r['notes']
        warn = False
        if not per_sample and method not in gt.PAIRED and any(samples):
            text = repeated_samples_text(groups, samples, what="this comparison",
                                         order=self.group_order())
            if text:
                warn = True
                notes.append(text)
        if r['n_pairs'] is not None:
            two = self._ordered([g for g in groups if g != gs.NO_GROUP])
            notes.append(paired_note(r['n_pairs'], groups, samples, None, two[0], two[1])
                         if len(two) == 2 else f"{r['n_pairs']} pairs (Sample column).")
        self.sp_note.setText(" ".join(notes))
        self.sp_note.setStyleSheet("color:#B71C1C;" if warn else "color:#333;")
        self._draw_spectra()
        self.sp_save_btn.setEnabled(True)
        self._check_outdated()
        self.sp_export_btn.setEnabled(True)

    def _draw_spectra(self):
        r = self.spectra_result
        fig = self.sp_figure
        fig.clear()
        if r is None:
            self.sp_canvas.draw_idle()
            return
        ax1 = fig.add_subplot(211)
        ax2 = fig.add_subplot(212, sharex=ax1)
        x = r['x']
        show = self.sp_show_combo.currentData()
        cmap = self.group_colours()
        for i, g in enumerate(r['names']):
            c = cmap.get(g, _GROUP_COLOURS[i % len(_GROUP_COLOURS)])
            m = r['mean'][g]
            w = r['sd'][g] if show == 'sd' else r['ci'][g]
            ax1.plot(x, m, color=c, lw=1.4, label=f"{g} (n={r['n'][g]})")
            ax1.fill_between(x, m - w, m + w, color=c, alpha=0.18, lw=0)
        q = np.clip(np.asarray(r['q'], float), 1e-300, 1)
        ax2.plot(x, -np.log10(q), color='#333', lw=1)
        ax2.axhline(-np.log10(r['alpha']), color='#B71C1C', ls='--', lw=1)
        for a, b, k, _m in r['ranges']:
            half = (x[1] - x[0]) / 2 if len(x) > 1 else 0.5
            for ax in (ax1, ax2):
                ax.axvspan(a - half, b + half, color='#FFD54F', alpha=0.35, lw=0)
        corr = 'FDR q' if r['correction'] == 'fdr' else 'Holm p'
        ax1.set_title(f"{r['test']} at every point ({BAND_TEXT.get(show, show)}; yellow: "
                      f"{corr} < {r['alpha']:g})", fontsize=9)
        ylabel = {'none': "Intensity", 'band': "Intensity / band max",
                  'area': "Intensity / area", 'snv': "SNV"}.get(r['normalization'], "Intensity")
        ax1.set_ylabel(ylabel, fontsize=8)
        ax1.legend(fontsize=7, loc='best')
        ax2.set_ylabel(f"\u2212log\u2081\u2080({corr.split()[-1]})", fontsize=8)
        ax2.set_xlabel("x", fontsize=8)
        for ax in (ax1, ax2):
            ax.tick_params(labelsize=7)
        safe_tight_layout(fig)
        self.sp_canvas.draw_idle()

    def save_spectra_plot(self):
        path, chosen = QFileDialog.getSaveFileName(
            self, "Save plot", "group_spectra.png",
            "PNG image (*.png);;TIFF image (*.tif);;SVG vector graphics (*.svg);;PDF (*.pdf)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += {'PNG': '.png', 'TIFF': '.tif', 'SVG': '.svg', 'PDF': '.pdf'}.get(
                chosen.split()[0], '.png')
        try:
            self.sp_figure.savefig(path, dpi=300, bbox_inches='tight')
        except Exception as exc:
            logger.exception("Group statistics: saving the spectra plot failed")
            QMessageBox.warning(self, "Save plot", f"The plot could not be saved:\n{exc}")

    def export_spectra_table(self):
        if self.spectra_result is None:
            return
        path, chosen = QFileDialog.getSaveFileName(
            self, "Export table", "group_spectra.xlsx",
            "Excel workbook (*.xlsx);;CSV (*.csv)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += '.csv' if 'CSV' in chosen else '.xlsx'
        try:
            df = gsp.export_table(self.spectra_result)
            if path.lower().endswith('.csv'):
                df.to_csv(path, index=False)
            else:
                df.to_excel(path, index=False, sheet_name='Spectra comparison')
        except Exception as exc:
            logger.exception("Group statistics: exporting the spectra table failed")
            QMessageBox.warning(self, "Export table", f"The table could not be saved:\n{exc}")

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
        self._check_outdated()

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
        names = self._ordered([g for g in self.groups() if g])
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

    def keyPressEvent(self, event):
        """Ctrl+Z undoes the last change of the table also when the table does
        not have the focus -- e.g. right after pressing 'Clear' or 'Set group of
        selected rows...' (the button then has the focus). A text field or
        number box keeps its own Ctrl+Z (it handles the key before it gets here)."""
        from PyQt5.QtGui import QKeySequence
        if event.matches(QKeySequence.Undo):
            self.table.undo()
            event.accept()
            return
        super().keyPressEvent(event)

    def _current_state(self):
        return (tuple(self.groups()), tuple(self.samples()),
                repr(sorted(self.value_settings().items())), repr(self.fit_settings))

    def _check_outdated(self, *_):
        """Show 'changed - press Compute' (and an orange Compute button) while
        the results on screen belong to other groups, samples or value."""
        if not hasattr(self, 'outdated_label'):
            return
        stale = (self.comparison is not None and self._result_state is not None
                 and self._current_state() != self._result_state)
        # the Spectra tab depends on the groups and samples only (its own
        # settings are applied with Compare spectra)
        sp_state = getattr(self, '_spectra_state', None)
        sp_stale = (sp_state is not None
                    and (tuple(self.groups()), tuple(self.samples())) != sp_state)
        if stale:
            self.outdated_label.setText(
                "Groups, samples or the value changed since the last Compute \u2014 press "
                "Compute" + (" and Compare spectra" if sp_stale else " (or Compare spectra)")
                + " to update the results.")
        elif sp_stale:
            self.outdated_label.setText(
                "Groups or samples changed since the last Compare spectra \u2014 press "
                "Compare spectra (Spectra tab) to update it.")
        self.outdated_label.setVisible(stale or sp_stale)
        self.compute_btn.setStyleSheet(
            "font-weight:bold; background-color:#FFE0B2;" if stale else "font-weight:bold;")
        if hasattr(self, 'sp_compare_btn'):
            self.sp_compare_btn.setStyleSheet(
                "font-weight:bold; background-color:#FFE0B2;" if sp_stale
                else "font-weight:bold;")

    def _recompute_shown(self, *_):
        """Test or 'One value per sample' changed: recompute the results that
        are on screen (nothing happens before the first Compute)."""
        if self.comparison is not None:
            self.compute()
        # also when the last comparison failed (e.g. a paired test with three
        # groups): the new test may work, and the old message must not stay
        if getattr(self, '_spectra_requested', False):
            self.compute_spectra()

    def _cached_values(self, groups, v):
        """The values of the spectra for these value settings -- computed once
        and reused while only the test or the per-sample choice changes (a
        peak fit of thousands of spectra takes a while). Whole-spectrum values
        depend on the groups too, so they are part of the key there."""
        key = (repr(sorted(v.items())), repr(self.fit_settings),
               tuple(groups) if gv.is_whole_spectrum(v['kind']) else None)
        if self._values_cache is not None and self._values_cache[0] == key:
            return self._values_cache[1], self._values_cache[2]
        values, info = gv.compute_values(self.spectra, groups, v,
                                         fit_settings=self.fit_settings,
                                         mapper=self._fit_mapper)
        self._values_cache = (key, values, info)
        return values, info

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
            values, info = self._cached_values(groups, v)
        except Exception as exc:
            logger.exception("Group statistics: computing the values failed")
            QMessageBox.warning(self, "Group Statistics",
                                f"The values could not be computed:\n{exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        method = self.test_combo.currentData()
        per_sample = self.per_sample_check.isChecked()
        samples = self.samples()
        self.remembered_settings.update({'test': method, 'per_sample': per_sample})
        # what each value in the plot / test stands for (spectrum or sample)
        if per_sample:
            g_used, s_used, v_used = gt.sample_means(groups, samples, values)
            point_labels = [smp or '(single spectrum)' for smp in s_used]
        else:
            g_used, v_used = groups, list(values)
            point_labels = list(self.labels)
        data = gs.collect(g_used, v_used, self.group_order())
        self.data_labels = {}
        for g, lab, val in zip(g_used, point_labels, v_used):
            if g and np.isfinite(val):
                self.data_labels.setdefault(g, []).append(lab)
        paired = None
        if method in gt.PAIRED and len(data) == 2:
            a, b = list(data)
            paired = gt.paired_values(groups, samples, values, a, b)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = gt.compare_with(data, method, paired)
        finally:
            QApplication.restoreOverrideCursor()
        self.values, self.data, self.comparison = values, data, result
        missing = sum(1 for g, val in zip(groups, values) if g and not np.isfinite(val))
        notes = []
        switched = bool(getattr(self, 'test_switched_note', ''))
        if switched:
            notes.append(self.test_switched_note)
            self.test_switched_note = ''
        if result.get('test') is None:
            notes.append("No test was computed.")
        elif len(result.get('groups') or []) == 2 and method in ('welch_gh', 'dunn'):
            notes.append("With two groups this is the "
                         + ("Welch t-test (Games\u2013Howell" if method == 'welch_gh'
                            else "Mann\u2013Whitney U test (Dunn")
                         + " only adds the pairs when there are three or more groups).")
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
        if paired is not None and result.get('test') is not None:
            notes.append(paired_note(len(paired[0]), groups, samples, values, a, b))
        # Pseudoreplication -- only when the user filled the Sample column (the
        # new, optional feature): without it the window behaves exactly as before
        if per_sample:
            few = [(g, len(vv)) for g, vv in data.items() if len(vv) < 3]
            if few:
                notes.append("\u26a0 Few independent samples: " + ", ".join(
                    f"\u201c{g}\u201d {n}" for g, n in few) + " \u2014 the test has little "
                    "power; a non-significant result is not evidence of no difference.")
            self.replicate_warned = False
        else:
            text = (repeated_samples_text(groups, samples, values, order=self.group_order())
                    if any(samples) and method not in gt.PAIRED else "")
            if text:
                notes.append(text)
            self.replicate_warned = bool(text)
        self.note.setText(" ".join(notes))
        # Red whenever the test is not what was asked for: no test at all,
        # or a whole group left out (the test then compares fewer groups)
        self.left_out_groups = empty + [g for g in result.get('excluded', []) if g not in empty]
        self.note.setStyleSheet("color:#B71C1C;"
                                if result.get('test') is None or self.left_out_groups
                                or missing or any(n.startswith("\u26a0") for n in notes)
                                else "color:#E65100;" if switched   # the switch, as before Compute
                                else "color:#555;")
        self._show_box_plot()
        self._show_summary()
        self._show_tests()
        self._show_values(groups)
        self.export_btn.setEnabled(bool(data))
        self._result_state = self._current_state()
        self._check_outdated()
        self.copy_sentence_btn.setEnabled(bool(result.get('sentence')))

    def copy_results_sentence(self):
        text = (self.comparison or {}).get('sentence', '')
        if text:
            QApplication.clipboard().setText(text)

    def _on_plot_type_changed(self, *_):
        self.remembered_settings['plot'] = self.plot_combo.currentData()
        self.remembered_settings['dots'] = self.dots_combo.currentData()
        self.remembered_settings['mark_outliers'] = self.outliers_check.isChecked()
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
            cmap = self.group_colours()
            colours = [cmap.get(g, _GROUP_COLOURS[i % len(_GROUP_COLOURS)])
                       for i, g in enumerate(names)]
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
            # the dots are drawn on the centre line first and spread sideways
            # by _place_dots() once the y-axis limits are final (a beeswarm
            # needs the size of a dot in data units)
            mark = self.outliers_check.isChecked()
            any_marked = False
            layers = []
            labels_of = getattr(self, 'data_labels', None) or {}
            for p, g, v, colour in zip(positions, names, values, colours):
                dots = ax.scatter(np.full(len(v), p), v, s=_DOT_AREA, alpha=0.7,
                                  color=colour, zorder=3)
                ring, idx = None, []
                if mark:
                    idx = list(gt.outliers(v))
                    if idx:
                        any_marked = True
                        ring = ax.scatter(np.full(len(idx), p), v[idx], s=70,
                                          facecolors='none', edgecolors='#D50000',
                                          linewidths=1.4, zorder=7)
                # the key of every dot (spectrum or sample name): Random jitter
                # gives each its own fixed shift
                keys = list(labels_of.get(g, []))
                if len(keys) != len(v):
                    keys = [f"{g}\n{i}" for i in range(len(v))]
                layers.append((p, v, keys, dots, ring, idx))
            # half width of the spread: in the CI plot the mean and its bar
            # start 0.12 to the right of the centre
            self._dot_layers = (ax, layers, 0.1 if kind == 'ci' else 0.3)
            for p, v in zip(positions, values):
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
            if mark and any_marked:
                footnote = (footnote + " Red circles: outside 1.5 × the interquartile range "
                            "(possible outliers, not removed).").strip()
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
        elif r:
            # values and summary are shown, but no p-value: say why in the title
            import textwrap as _tw0
            reason = (r.get('note') or '').strip() or "see the note below the plot"
            ax.set_title(_tw0.fill("No test \u2014 " + reason, 110), fontsize=9,
                         color='#B71C1C')
        if footnote:
            import textwrap as _tw
            fig.text(0.01, 0.005, _tw.fill(footnote, 140), fontsize=7.5, color='#555555',
                     va='bottom')
            safe_tight_layout(fig, rect=(0, 0.05, 1, 1))
        else:
            safe_tight_layout(fig)
        if not names:
            self._dot_layers = None
        self._place_dots()
        self.canvas.draw_idle()
        self.save_plot_btn.setEnabled(bool(names))

    def _place_dots(self):
        """Spread the dots of every group sideways (Dots: Automatic / Random
        jitter / Beeswarm / Density-scaled, see dot_spread.py). Returns the
        set of methods used ('swarm', 'density', 'jitter')."""
        layers = getattr(self, '_dot_layers', None)
        if not layers:
            return set()
        ax, groups, half = layers
        dx, dy = ds.reference_dot_size(ax.get_ylim(), _DOT_AREA)
        mode = self.dots_combo.currentData()
        used = set()
        for p, v, keys, dots, ring, idx in groups:
            off, how = ds.offsets(mode, v, keys, dx, dy,
                                  min(0.12, half) if mode == 'jitter' else half)
            used.add(how)
            dots.set_offsets(np.column_stack([p + off, v]))
            if ring is not None:
                ring.set_offsets(np.column_stack([p + off[idx], v[idx]]))
        self.dots_used = used
        return used

    def _show_summary(self):
        rows = gs.describe(self.data)
        t = self.summary_table
        t.setRowCount(len(rows))
        for r, row in enumerate(rows):
            cells = [row['group'], str(row['n'])] + [f"{row[k]:.6g}" if np.isfinite(row[k]) else "–"
                                                       for k in ('mean', 'sd', 'median', 'min', 'max')]
            cmap = self.group_colours()
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if c == 0 and row['group'] in cmap:
                    item.setBackground(QBrush(QColor(_tint(cmap[row['group']]))))
                t.setItem(r, c, item)
        t.resizeColumnsToContents()

    def _tests_html(self):
        r = self.comparison
        if not r or not r['test']:
            return f"<p>{html.escape((r or {}).get('note', ''))}</p>"
        stat_line = f"Statistic = {r['statistic']:.4g}"
        df = r.get('df')
        if isinstance(df, tuple):
            stat_line += f" (df = {df[0]:.3g}, {df[1]:.3g})"
        elif df is not None and np.isfinite(df):
            stat_line += f" (df = {df:.3g})"
        effect = (f", {r['effect_name']} = {r['effect']:.3g}"
                  if r.get('effect_name') and np.isfinite(r.get('effect', np.nan)) else "")
        parts = [f"<h3>{html.escape(r['test'])}</h3>",
                f"<p>Value: {html.escape(self.value_label())}<br>"
                f"Groups: {html.escape(', '.join(r['groups']))}"
                + (f"<br>Pairs of samples: {r['n_pairs']}" if r.get('n_pairs') else "")
                + (" &mdash; one value per sample" if self.per_sample_check.isChecked() else "")
                + "</p>",
                f"<p>{stat_line}, <b>{html.escape(gs.p_text(r['p']))}</b>"
                f"{html.escape(_exact_p(r['p'], r.get('method')))}{effect}</p>"]
        if len(r['groups']) > 2 and r.get('pairs'):
            centre = "means" if r['parametric'] else "medians"
            adjusted_by = r.get('pairs_adjusted_by')
            with_ci = any('ci' in pr for pr in r['pairs'])
            head = (f"Pairs ({r['pair_test']}, p adjusted)" if adjusted_by
                    else f"Pairs ({r['pair_test']}, p Holm-corrected)")
            parts.append(f"<h4>{html.escape(head)}</h4>")
            parts.append("<table border='1' cellspacing='0' cellpadding='3'>"
                        f"<tr><th>Pair</th><th>Difference of {centre}</th>"
                        + ("<th>95 % CI</th>" if with_ci else "")
                        + "<th>p</th>"
                        f"<th>p ({'adjusted' if adjusted_by else 'Holm'})</th>"
                        f"<th>{r['pair_effect_name']}</th></tr>")
            for pr in r['pairs']:
                ci = (f"<td>{pr['ci'][0]:.4g} ; {pr['ci'][1]:.4g}</td>" if with_ci else "")
                parts.append(f"<tr><td>{html.escape(pr['a'])} – {html.escape(pr['b'])}</td>"
                            f"<td>{pr['difference']:.4g}</td>{ci}"
                            f"<td>{html.escape(gs.format_p(pr['p']))}</td>"
                            f"<td><b>{html.escape(gs.format_p(pr['p_holm']))}</b>"
                            f"{html.escape(_exact_p(pr['p_holm'], r.get('method')))}</td>"
                            f"<td>{pr['effect']:.3g}</td></tr>")
            parts.append("</table>")
        parts.append("<p style='color:#555'>p below 0.05 is usually read as a statistically "
                    "significant difference. The effect size says how large the difference is; "
                    "see Help.</p>")
        parts.extend(self._extra_html(r))
        return "".join(parts)

    def _extra_html(self, r):
        """Confidence intervals, assumption checks, outliers, results sentence."""
        parts = []
        ci, gci = r.get('ci'), r.get('g_ci')
        if (ci and np.isfinite(ci[1])) or (gci and np.isfinite(gci[1])):
            a, b = (r['groups'] + ['', ''])[:2]
            parts.append("<h4>How large is the difference?</h4><ul>")
            if ci and np.isfinite(ci[1]):
                what = ("mean of the differences (pairs)" if r.get('n_pairs')
                        else f"difference of means ({html.escape(a)} − {html.escape(b)})")
                parts.append(f"<li>{what}: <b>{ci[0]:.4g}</b>, 95 % confidence interval "
                             f"{ci[1]:.4g} to {ci[2]:.4g}</li>")
            if gci and np.isfinite(gci[1]):
                parts.append(f"<li>Hedges' g: <b>{gci[0]:.3g}</b>, 95 % confidence interval "
                             f"{gci[1]:.3g} to {gci[2]:.3g} (bootstrap)</li>")
            parts.append("</ul><p style='color:#555'>If the interval of the difference does "
                         "not include 0, the difference is significant at 5 %; its width shows "
                         "how precisely the difference is known.</p>")
        checks = r.get('checks')
        if checks:
            parts.append("<h4>Checks of the test's assumptions (information only)</h4>"
                         "<table border='1' cellspacing='0' cellpadding='3'>"
                         "<tr><th>Group</th><th>n</th><th>Bell-shaped? Shapiro–Wilk p</th></tr>")
            for g, n, p in checks['normality']:
                parts.append(f"<tr><td>{html.escape(g)}</td><td>{n}</td>"
                             f"<td>{html.escape(gs.format_p(p))}</td></tr>")
            parts.append("</table>")
            if np.isfinite(checks['equal_spread_p']):
                parts.append(f"<p>Same spread in all groups? Brown–Forsythe "
                             f"{html.escape(gs.p_text(checks['equal_spread_p']))}</p>")
            if checks['advice']:
                parts.append("<ul>" + "".join(f"<li>{html.escape(t)}</li>"
                                              for t in checks['advice']) + "</ul>")
            else:
                parts.append("<p style='color:#555'>No sign of a problem with the "
                             "assumptions.</p>")
        flagged = []
        for g, idx in (r.get('outliers') or {}).items():
            labels = getattr(self, 'data_labels', {}).get(g, [])
            names = [labels[i] for i in idx if i < len(labels)]
            if names:
                flagged.append(f"{html.escape(g)}: " + ", ".join(html.escape(n) for n in names))
        if flagged:
            parts.append("<h4>Possible outliers</h4><p>Outside 1.5 × the interquartile range "
                         "(not removed; check them, e.g. with Mark outliers in the plot): "
                         + "; ".join(flagged) + "</p>")
        if r.get('sentence'):
            parts.append("<h4>Results sentence</h4><p style='background:#F1F8E9; padding:6px;'>"
                         + html.escape(r['sentence']) + "</p>")
        return parts

    def _show_tests(self):
        self.tests_view.setHtml(self._tests_html())

    def _show_values(self, groups):
        t = self.values_table
        cmap = self.group_colours()
        t.setRowCount(len(self.labels))
        for r, (label, g, v, smp) in enumerate(zip(self.labels, groups, self.values,
                                                   self.samples())):
            for c, text in enumerate((label, g, f"{v:.6g}" if np.isfinite(v) else "–", smp)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if c == 1 and g in cmap:
                    item.setBackground(QBrush(QColor(_tint(cmap[g]))))
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
                           self.value_label(), samples=self.samples(), report=True)
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


def export_results(path, labels, groups, values, data, result, value_label, samples=None,
                   report=False):
    """Write the values, the summary and the tests to an Excel workbook
    (three sheets) or a CSV file (the tables one after another). With
    report=True (the window's Export) also a 'Report' sheet / table with the
    confidence intervals, assumption checks and the results sentence."""
    import pandas as pd
    values_df = pd.DataFrame({'Spectrum': labels, 'Group': groups, value_label: values})
    if samples is not None and any(samples):
        values_df['Sample'] = list(samples)
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
    report_rows = []
    ci, gci = result.get('ci'), result.get('g_ci')
    if ci and np.isfinite(ci[1]):
        report_rows += [('Difference of means', ci[0]), ('95 % CI low', ci[1]), ('95 % CI high', ci[2])]
    if gci and np.isfinite(gci[1]):
        report_rows += [("Hedges' g", gci[0]), ("Hedges' g 95 % CI low", gci[1]),
                   ("Hedges' g 95 % CI high", gci[2])]
    checks = result.get('checks') or {}
    for g, n, p in checks.get('normality', []):
        report_rows.append((f"Shapiro–Wilk p, {g} (n = {n})", p))
    if np.isfinite(checks.get('equal_spread_p', np.nan)):
        report_rows.append(("Brown–Forsythe p", checks['equal_spread_p']))
    for t in checks.get('advice', []):
        report_rows.append(("Advice", t))
    if result.get('sentence'):
        report_rows.append(("Results sentence", result['sentence']))
    report_df = (pd.DataFrame(report_rows, columns=['Item', 'Value'])
                 if report and report_rows else None)
    if path.lower().endswith('.csv'):
        with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
            for title, df in (('Values', values_df), ('Summary', summary_df), ('Tests', tests_df),
                              ('Report', report_df)):
                if df is None:
                    continue
                fh.write(f"{title}\n")
                df.to_csv(fh, index=False)
                fh.write("\n")
    else:
        with pd.ExcelWriter(path) as writer:
            values_df.to_excel(writer, sheet_name='Values', index=False)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            tests_df.to_excel(writer, sheet_name='Tests', index=False)
            if report_df is not None:
                report_df.to_excel(writer, sheet_name='Report', index=False)
