# src/views/dialogs/visualization_analysis/pca_scores_dialog.py
"""
PCA / SVD Scores & Loadings dialog.

Reuses the SVD already computed by SVDBackgroundManager.
The data matrix is (n_wavelengths × n_spectra), so:
    U   : (n_wl × n_comp)   — loadings (spectral components)
    s   : (n_comp,)          — singular values
    Vt  : (n_comp × n_spec)  — scores (spectrum coordinates)

Layout
------
Left panel (fixed 300 px)
    SVD settings  — n_components spinbox, recompute button
    Scores tab    — PC_x / PC_y(/PC_z) selectors, colour-by combo, 3D toggle
                    (hidden unless the Scores tab is active)
    Loadings tab  — which PCs to show, overlay checkbox
                    (hidden unless the Loadings tab is active)
    Help | Close

Right panel — QTabWidget
    Scores   — scatter plot (PC_a vs PC_b, optionally 3D with PC_c)
    Loadings — overlay of selected PC loadings vs wavenumber
    Variance — scree plot (explained variance per component) plus a
               table of eigenvalues, explained/cumulative variance, and
               residual error (Malinowski's IND function, same formula
               used by SVD Background's diagnostics)
"""

import csv
import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QComboBox, QPushButton, QLabel, QSpinBox, QCheckBox,
    QListWidget, QSizePolicy, QSplitter, QWidget, QTabWidget,
    QDoubleSpinBox, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QLineEdit, QDialogButtonBox,
    QRadioButton, QButtonGroup,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib import cm as _cm
from mpl_toolkits.axes_grid1 import make_axes_locatable
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — registers the '3d' projection

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

_COLORS = [
    '#1f77b4','#d62728','#2ca02c','#ff7f0e','#9467bd',
    '#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf',
]

# Confidence level used for Bootstrap Uncertainty -- same convention as
# NMFDialog/MCRALSDialog's own _BOOTSTRAP_CONFIDENCE_LEVEL.
_BOOTSTRAP_CONFIDENCE_LEVEL = 0.95


class PcaScoresDialog(QDialog):

    # Shared metric catalog, used for axis labels, the Loadings component
    # list, and the Variance tab's Single/Compare/Overview plots — naming
    # matches SVD Analysis's own METRICS dict exactly, so the same word
    # means the same thing in both dialogs.
    _METRICS = {
        'Singular values (\u03c3)': {
            'log': True, 'color': '#1565C0',
            'tooltip': (
                '\u03c3\u1d62 = square root of the variance explained by component i.\n'
                'Look for a kink where the steep drop flattens \u2014 that marks the signal-to-noise boundary.\n\n'
                'Formula: X = U \u00d7 diag(\u03c3) \u00d7 V\u1d40'
            ),
        },
        'Eigenvalue (\u03c3\u00b2)': {
            'log': True, 'color': '#0D47A1',
            'tooltip': (
                'Eigenvalue = \u03c3\u1d62\u00b2 \u2014 the absolute amount of variance component i\n'
                'accounts for, before converting to a percentage (Explained variance).\n\n'
                'For raw, unnormalized spectral intensities, eigenvalues commonly reach\n'
                '1e8\u20131e16 or beyond \u2014 this is expected, not a sign of a problem. Eigenvalue\n'
                'scales with the square of the data\'s absolute intensity scale, so it carries\n'
                'no inherent "normal" range; only its relative size across components matters.'
            ),
        },
        'Explained variance (%)': {
            'log': False, 'color': '#1976D2',
            'tooltip': (
                'EV_i = \u03c3\u1d62\u00b2 / \u03a3\u03c3\u2c7c\u00b2 \u00d7 100%\n\n'
                'The fraction of total spectral variance explained by each\n'
                'individual component. Component 1 always has the largest value.\n'
                'Components beyond the signal-to-noise boundary typically each\n'
                'contribute < 1% and collectively form a flat tail.'
            ),
        },
        'Cumulative explained var. (%)': {
            'log': False, 'color': '#2E7D32',
            'tooltip': (
                'Cum_EV(N) = \u03a3\u1d62\u208c\u2081\u1d3a EV_i\n\n'
                'Running total of variance explained when using the first N components.'
            ),
        },
        'Cumulative unexplained var. (%)': {
            'log': False, 'color': '#C62828',
            'tooltip': (
                'Unexpl(N) = 100% \u2212 Cum_EV(N)\n\n'
                'The fraction of total variance NOT captured by the first N components.'
            ),
        },
        'Residual error E(m)': {
            'log': True, 'color': '#E65100',
            'tooltip': (
                'E(m) = \u221a[ \u03a3\u1d62\u208e\u2098 \u03c3\u1d62\u00b2 / ((n_pts \u2212 m \u2212 1)(n_sp \u2212 m \u2212 1)) ]\n\n'
                'Root-mean-square residual normalised by degrees of freedom.\n'
                'Monotonically decreasing for typical spectral data (n_pts >> n_sp).\n'
                'Look for the elbow \u2014 the point where the rate of decrease visibly flattens.\n\n'
                'Log scale is recommended for finding the elbow: on a linear scale the\n'
                'first components dominate the axis and compress the rest into a narrow\n'
                'band, making the elbow invisible.\n\n'
                'Note: has no true minimum for spectroscopic data.'
            ),
        },
        'Malinowski IND': {
            'log': True, 'color': '#6A1B9A',
            'tooltip': (
                'IND(m) = E(m) / (n_sp \u2212 m)\u00b2\n\n'
                'Normalizing E(m) this way makes IND turn back upward once you\'ve\n'
                'retained more components than there are real factors, giving it\n'
                'an actual minimum \u2014 the statistically suggested cutoff.\n\n'
                'Most reliable when n_pts >> n_sp; for large or near-square\n'
                'datasets the minimum can be unreliable.'
            ),
        },
    }

    # Genuine interpretation guidance for specific metric pairs, keyed by
    # frozenset of the two metric names above — ported directly from SVD
    # Analysis's Diagnostics tab, since both dialogs decompose spectra via
    # the same underlying SVD and share the exact same seven metrics, so
    # the guidance carries over verbatim. Without this, "What does this
    # comparison mean?" could only paste each metric's own definition
    # one after another, which just repeats what Single metric mode
    # already explains rather than saying anything about the *relationship*
    # between the two curves. Pairs not listed here (mostly anything
    # involving Eigenvalue, which is just \u03c3\u00b2 and therefore mirrors
    # whatever Singular values already shows) fall back to a generic
    # explanation in _get_variance_compare_help_text.
    _COMPARE_HELP = {
        frozenset(['Singular values (\u03c3)', 'Residual error E(m)']): (
            "Singular values (\u03c3) vs Residual error E(m)\n\n"
            "\u2022 Both curves decrease as the component number increases.\n"
            "\u2022 In the \u03c3 curve: if it drops steeply for the first few components and then "
            "flattens suddenly, that flat region is the noise. "
            "The component where the steep drop ends is the boundary.\n"
            "\u2022 Check the E curve at the same component number: E should also show a change "
            "in slope there \u2014 decreasing faster before and more slowly after. "
            "If both curves show a change at the same N, that confirms N is optimal.\n"
            "\u2022 If \u03c3 flattens early but E keeps dropping noticeably, the two metrics "
            "disagree \u2014 E is still detecting residual variance that \u03c3 alone would miss. "
            "Check the IND curve for a more reliable criterion."
        ),
        frozenset(['Singular values (\u03c3)', 'Malinowski IND']): (
            "Singular values (\u03c3) vs Malinowski IND\n\n"
            "This is the most informative comparison for finding the optimal N "
            "\u2014 when IND is reliable (see caveat below).\n\n"
            "\u2022 In the \u03c3 curve: look for where it transitions from steep to flat. "
            "That transition marks the signal-to-noise boundary.\n"
            "\u2022 In the IND curve: unlike \u03c3 and E which always decrease, IND has a "
            "genuine minimum \u2014 it decreases at first, reaches a lowest point, then "
            "rises again. The component at the minimum is the statistically optimal N.\n"
            "\u2022 The component where \u03c3 flattens should coincide with the IND minimum. "
            "If they agree, the result is robust.\n"
            "\u2022 After the IND minimum, IND rises because the degrees-of-freedom "
            "denominator (n_sp \u2212 m)\u00b2 shrinks faster than the residual variance \u2014 "
            "adding those components is statistically unjustified even if \u03c3 is not zero.\n"
            "\u2022 Components before the IND minimum with visibly larger \u03c3 values are real signal. "
            "Components after the minimum with nearly flat \u03c3 are noise.\n\n"
            "IND RELIABILITY CAVEAT:\n"
            "IND was developed for small datasets where n_pts >> n_sp (ratio > 10).\n"
            "When n_pts/n_sp < 5 (nearly square matrix), the denominator (n_sp \u2212 m)\u00b2 "
            "shrinks too slowly and the IND minimum shifts to a falsely high N.\n"
            "In those cases: rely on the \u03c3 kink and visual inspection of the Scores/Loadings tabs."
        ),
        frozenset(['Residual error E(m)', 'Malinowski IND']): (
            "Residual error E(m) vs Malinowski IND\n\n"
            "Both metrics are derived from the same residual variance, but IND "
            "divides by (n_sp \u2212 m)\u00b2 while E divides by the full degrees of freedom.\n\n"
            "\u2022 E always decreases \u2014 the curve never turns upward.\n"
            "\u2022 IND decreases at first, reaches a minimum, then rises. "
            "The minimum is the statistically optimal N.\n"
            "\u2022 Look at where E starts flattening \u2014 the rate of decrease slows visibly. "
            "Compare that component to the IND minimum. If they coincide, the result is robust.\n"
            "\u2022 If E still drops noticeably after the IND minimum, the two criteria "
            "disagree \u2014 IND says stop, but E says there is still residual variance "
            "worth capturing. Inspect those components visually to decide.\n\n"
            "IND reliability: works best when n_pts >> n_sp. "
            "If n_pts/n_sp < 5, the IND minimum may be unreliable."
        ),
        frozenset(['Cumulative explained var. (%)', 'Malinowski IND']): (
            "Cumulative explained variance (%) vs Malinowski IND\n\n"
            "\u2022 Cumulative explained variance is a running total that rises from 0% toward "
            "100% as more components are added. It rises steeply for real-signal components "
            "and flattens for noise components.\n"
            "\u2022 IND has a genuine minimum at the statistically optimal N. "
            "Find that N in the IND curve, then read off the corresponding cumulative "
            "explained value to see how much cumulative variance that N represents.\n"
            "\u2022 If the IND minimum falls where cumulative explained has already flattened "
            "near 95\u201399%, the statistical and variance criteria agree.\n"
            "\u2022 If the IND minimum occurs where cumulative explained is still rising steeply "
            "and has not yet reached 90%, IND may be too conservative \u2014 consider retaining "
            "additional components on scientific grounds.\n\n"
            "IND reliability: works best when n_pts >> n_sp. "
            "If n_pts/n_sp < 5, the IND minimum may be unreliable \u2014 rely on the "
            "cumulative-explained elbow instead."
        ),
        frozenset(['Singular values (\u03c3)', 'Explained variance (%)']): (
            "Singular values (\u03c3) vs Explained variance per component (%)\n\n"
            "These two metrics are mathematically related: EV_i = \u03c3\u1d62\u00b2 / \u03a3\u03c3\u2c7c\u00b2 \u00d7 100%.\n"
            "Comparing them reveals the same information on two different scales.\n\n"
            "\u2022 The two curves will show nearly identical shapes \u2014 they cannot "
            "disagree because one is a direct transformation of the other.\n"
            "\u2022 Use this view to calibrate your intuition: see how a given \u03c3 value "
            "corresponds to a % of explained variance for the same component."
        ),
        frozenset(['Singular values (\u03c3)', 'Cumulative explained var. (%)']): (
            "Singular values (\u03c3) vs Cumulative explained variance (%)\n\n"
            "\u2022 \u03c3 measures each component's individual contribution; cumulative explained "
            "variance shows the running total. Together they answer: 'how much do I gain "
            "by adding one more?'\n"
            "\u2022 Each jump upward in the cumulative curve equals the variance explained by "
            "that component, which is proportional to \u03c3\u1d62\u00b2. A component with large \u03c3 "
            "causes a large visible jump; a component with small \u03c3 barely moves the curve.\n"
            "\u2022 Look for the component where \u03c3 drops sharply AND the cumulative curve "
            "flattens. That double signal confirms the noise boundary.\n"
            "\u2022 The kink in \u03c3 and the elbow in the cumulative curve should coincide at the "
            "optimal N."
        ),
        frozenset(['Singular values (\u03c3)', 'Cumulative unexplained var. (%)']): (
            "Singular values (\u03c3) vs Cumulative unexplained variance (%)\n\n"
            "\u2022 Unexplained variance = 100% \u2212 cumulative explained variance.\n"
            "\u2022 As more components are retained, both \u03c3 and unexplained variance decrease.\n"
            "\u2022 Look for a component where \u03c3 shows a sudden large drop AND unexplained "
            "variance shows a corresponding sudden large downward jump. Both happening "
            "at the same component number confirms that component carries real signal.\n"
            "\u2022 After that component, \u03c3 values typically become much smaller and decrease "
            "only gradually \u2014 and unexplained variance flattens and barely changes "
            "from one component to the next. That flat region is noise.\n"
            "\u2022 The component where \u03c3 transitions from steep to flat, and unexplained "
            "variance stops dropping noticeably, is the optimal N."
        ),
        frozenset(['Explained variance (%)', 'Residual error E(m)']): (
            "Explained variance per component (%) vs Residual error E(m)\n\n"
            "\u2022 Explained variance shows each component's individual share of total "
            "variance. E shows the total reconstruction error when that component and "
            "all higher ones are excluded \u2014 it decreases as more components are retained.\n"
            "\u2022 The first few components typically have visibly taller bars, AND the E "
            "curve drops steeply at the same components. Those are real signal.\n"
            "\u2022 When the bars become so small they are barely visible above zero, but E "
            "is still dropping noticeably, it means many small components together still "
            "carry meaningful variance \u2014 consider keeping more than the IND minimum suggests.\n"
            "\u2022 When both the bars are barely visible AND E has flattened and barely "
            "changes from one component to the next, those components are noise."
        ),
        frozenset(['Explained variance (%)', 'Malinowski IND']): (
            "Explained variance per component (%) vs Malinowski IND\n\n"
            "\u2022 Explained variance measures individual contribution; IND measures "
            "statistical justification for including each additional component.\n"
            "\u2022 The component at the IND minimum should have a noticeably larger bar "
            "than the components after it. If it's similar for N and N+1, IND may be "
            "identifying the wrong boundary.\n"
            "\u2022 Components with explained variance > 1% but rising IND are borderline \u2014 "
            "examine them visually before deciding to include or exclude.\n"
            "\u2022 The component where explained variance drops sharply should align with "
            "the IND minimum.\n\n"
            "IND reliability: works best when n_pts >> n_sp. "
            "If n_pts/n_sp < 5, the IND minimum may be unreliable."
        ),
        frozenset(['Explained variance (%)', 'Cumulative explained var. (%)']): (
            "Explained variance per component (%) vs Cumulative explained variance (%)\n\n"
            "\u2022 Explained variance is a bar chart showing each component's individual "
            "share. Tall bars = real signal. Bars barely visible above zero = noise.\n"
            "\u2022 Cumulative explained variance is a running total rising from 0% toward "
            "100%. It rises steeply when the bars are tall, and flattens when they are tiny.\n"
            "\u2022 The component where the bars transition from tall to barely visible is "
            "the same component where the cumulative curve flattens. "
            "That is the signal-to-noise boundary."
        ),
        frozenset(['Explained variance (%)', 'Cumulative unexplained var. (%)']): (
            "Explained variance per component (%) vs Cumulative unexplained variance (%)\n\n"
            "\u2022 Each component reduces the unexplained variance by exactly its own share.\n"
            "\u2022 The unexplained curve is therefore a mirror of the cumulative explained "
            "curve \u2014 a smooth monotone descent with no additional diagnostic value.\n"
            "\u2022 The bar chart and the unexplained descending line show the same "
            "information from complementary angles, making it easy to see which "
            "components make a meaningful dent in the total unexplained variance."
        ),
        frozenset(['Cumulative explained var. (%)', 'Residual error E(m)']): (
            "Cumulative explained variance (%) vs Residual error E(m)\n\n"
            "\u2022 Both measure 'how much is left unexplained', but on different scales.\n"
            "\u2022 Cumulative explained variance is normalised to 100% (fraction of total "
            "variance). E(m) is normalised by degrees of freedom \u2014 it depends on the "
            "actual magnitudes.\n"
            "\u2022 A component that increases cumulative explained variance substantially "
            "and also reduces E substantially is unambiguously real signal.\n"
            "\u2022 Divergence between the two (one plateaus but the other still drops) "
            "indicates that the degree-of-freedom correction in E is doing significant "
            "work \u2014 worth checking that the data matrix is not rank-deficient."
        ),
        frozenset(['Cumulative explained var. (%)', 'Cumulative unexplained var. (%)']): (
            "Cumulative explained variance (%) vs Cumulative unexplained variance (%)\n\n"
            "\u2022 These two metrics always sum to 100%, so one curve is always a "
            "perfect mirror of the other. There is no diagnostic information in this "
            "comparison.\n\n"
            "\u2022 Compare either of them against Residual error E(m) or Malinowski IND "
            "for a more informative view."
        ),
        frozenset(['Cumulative unexplained var. (%)', 'Residual error E(m)']): (
            "Cumulative unexplained variance (%) vs Residual error E(m)\n\n"
            "\u2022 Both decrease as more components are retained, but at different rates.\n"
            "\u2022 Unexplained variance is normalised to the total variance (scale-free). "
            "E(m) is in absolute units (intensity\u00b2/degree-of-freedom).\n"
            "\u2022 If they decrease at the same rate, the data has uniform noise and the "
            "variance-based and error-based criteria will agree.\n"
            "\u2022 If E drops faster than unexplained variance in the early components, "
            "the leading components have above-average noise \u2014 check for outlier spectra.\n"
            "\u2022 If unexplained variance drops faster in the early components, the leading "
            "components are very clean and the noise is concentrated in the tail."
        ),
        frozenset(['Cumulative unexplained var. (%)', 'Malinowski IND']): (
            "Cumulative unexplained variance (%) vs Malinowski IND\n\n"
            "\u2022 Unexplained variance shows what fraction of total information is still "
            "missing; IND shows whether including more components is statistically justified.\n"
            "\u2022 The IND minimum at N means: including component N+1 causes more "
            "statistical penalty than benefit. The unexplained variance at that N "
            "tells you the practical cost \u2014 how much information you are leaving out.\n"
            "\u2022 If unexplained variance at the IND minimum is still large (> 10%), "
            "you may want to override the IND criterion and include more components "
            "on scientific grounds.\n"
            "\u2022 This is the most useful comparison for deciding whether to follow IND "
            "strictly or keep additional components for scientific reasons.\n\n"
            "IND reliability: works best when n_pts >> n_sp. "
            "If n_pts/n_sp < 5, the IND minimum may be unreliable \u2014 the unexplained "
            "variance elbow is then a more reliable guide."
        ),
    }

    def __init__(self, parent=None, controller=None, spectra=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle('PCA / SVD — Scores & Loadings')
        self.setMinimumSize(1000, 620)
        self.resize(1280, 760)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        self.controller    = controller
        self.spectra       = list(spectra or [])
        self._settings     = dict(current_settings or {})
        # U/s/Vt/x_axis/expl_var/residual_err/malinowski_ind are no longer
        # computed here — they're owned by self.controller.manager
        # (PcaScoresManager). These attributes are refreshed from there
        # after every successful computation (see _on_pca_svd_computed) and
        # simply read from here everywhere else in this file, so none of
        # the many plotting/export call sites below needed to change.
        self._U            = None   # loadings  (n_wl × n_comp)
        self._s            = None   # singular values
        self._Vt           = None   # scores    (n_comp × n_spec)
        self._x_axis       = None
        self._labels       = [s['label'] for s in self.spectra]
        self._expl_var     = None
        self._residual_err = None
        self._malinowski_ind = None
        self._scores_is_3d = None   # tracks current axes projection so we
                                     # only rebuild the axes when it changes
        self._scores_cbar_ax = None
        self._scores_colorbar = None
        self._scores_3d_orig_pos = None
        self._last_n_bootstrap = 30   # remembered resample count, pre-filled next time

        self._build_ui()
        self._restore_settings()
        self._initial_compute_pending = True

    def get_settings(self) -> dict:
        """Return the dialog's current settings, so the caller can
        remember them for next time this exact selection is reopened
        (see PcaScoresController._on_dialog_destroyed). Mirrors the same
        save-on-close pattern used by Data Range / Baseline Correction /
        FFT Denoising — captured regardless of how the dialog was
        closed, not gated behind an explicit "Save" action."""
        return {
            'n_components':      self._n_comp_spin.value(),
            'mean_center':       self._mean_center_cb.isChecked(),
            'pc_label_metric':   self._pc_label_metric_combo.currentText(),
            'pc_label_format':   self._pc_label_format_combo.currentText(),
            'pc_label_decimals': self._pc_label_decimals_spin.value(),
            'pc_x':              self._pc_x_spin.value(),
            'pc_y':              self._pc_y_spin.value(),
            'pc_z':              self._pc_z_spin.value(),
            'scores_3d':         self._scores_3d_cb.isChecked(),
            'color_by':          self._color_combo.currentText(),
            'show_labels':       self._show_labels_cb.isChecked(),
            'offset_loadings':   self._load_offset_cb.isChecked(),
            'variance_mode':     self._variance_mode_combo.currentText(),
            'variance_single':   self._variance_single_combo.currentText(),
            'variance_x':        self._variance_x_combo.currentText(),
            'variance_y':        self._variance_y_combo.currentText(),
            'variance_log':      self._variance_log_cb.isChecked(),
        }

    def _restore_settings(self):
        """Apply self._settings (from a previous session — the caller
        only passes this in when it was last shown for this exact
        selection, see main_controller._show_pca_scores_dialog) to the
        widgets just built, before the first SVD computation runs, so a
        restored component count etc. takes effect immediately rather
        than needing a manual recompute."""
        s = self._settings
        if not s:
            return

        if 'n_components' in s:
            # Clamp to whatever range is valid for the CURRENT selection
            # — spin box bounds depend on len(spectra) and point count,
            # which a previous session may have had different values for.
            n = max(self._n_comp_spin.minimum(),
                    min(int(s['n_components']), self._n_comp_spin.maximum()))
            self._n_comp_spin.setValue(n)

        if 'mean_center' in s:
            # blockSignals: setChecked() would otherwise fire stateChanged
            # -> _compute_svd() immediately, duplicating the single
            # showEvent-scheduled initial compute that already picks up
            # whatever this checkbox ends up set to (_initial_compute_pending).
            self._mean_center_cb.blockSignals(True)
            self._mean_center_cb.setChecked(bool(s['mean_center']))
            self._mean_center_cb.blockSignals(False)

        for combo, key in (
            (self._pc_label_metric_combo, 'pc_label_metric'),
            (self._pc_label_format_combo, 'pc_label_format'),
            (self._variance_mode_combo,   'variance_mode'),
            (self._variance_single_combo, 'variance_single'),
            (self._variance_x_combo,      'variance_x'),
            (self._variance_y_combo,      'variance_y'),
        ):
            if key in s:
                idx = combo.findText(s[key])
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        if 'pc_label_decimals' in s:
            self._pc_label_decimals_spin.setValue(int(s['pc_label_decimals']))

        for spin, key in (
            (self._pc_x_spin, 'pc_x'),
            (self._pc_y_spin, 'pc_y'),
            (self._pc_z_spin, 'pc_z'),
        ):
            if key in s:
                spin.setValue(max(spin.minimum(), min(int(s[key]), spin.maximum())))

        if s.get('scores_3d'):
            self._scores_3d_cb.setChecked(True)   # triggers _on_3d_toggled

        if 'color_by' in s:
            # The combo only offers 'index' and 'T² (Hotelling)' at build
            # time — PC-based entries ('PC1', 'PC2', ...) get added
            # dynamically once the first SVD computation knows how many
            # components exist. Restoring a PC-based choice from a
            # previous session isn't possible yet at this point, so it
            # falls back to the default ('index') rather than silently
            # doing nothing.
            idx = self._color_combo.findText(s['color_by'])
            if idx >= 0:
                self._color_combo.setCurrentIndex(idx)

        if 'show_labels' in s:
            self._show_labels_cb.setChecked(bool(s['show_labels']))

        if 'offset_loadings' in s:
            self._load_offset_cb.setChecked(bool(s['offset_loadings']))

        if 'variance_log' in s:
            self._variance_log_cb.setChecked(bool(s['variance_log']))

    def showEvent(self, event):
        super().showEvent(event)
        # _compute_svd() (and the plot rendering it triggers) used to run
        # directly from __init__, before this dialog had its final
        # on-screen geometry — tight_layout()/the canvas's sizing got
        # computed against whatever placeholder size existed at that
        # moment, not the real window size. That's why the plot only
        # filled the window correctly after something else (changing a
        # setting, switching tabs) forced a fresh redraw. Deferring to
        # showEvent, with events flushed and a short real delay first,
        # reliably runs it after layout has actually settled (same fix
        # used for the Cosmic Ray Detection heatmap).

        # Defensive: clear any override cursor(s) still active once this
        # dialog is actually on screen — e.g. a "please wait" cursor left
        # active by whoever opened this dialog. This dialog isn't modal, so
        # that cursor is usually cleared by the caller almost immediately
        # after show() returns — but clearing it here too costs nothing and
        # keeps this dialog consistent with svd_analysis_dialog.py and
        # cluster_analysis_dialog.py, which needed this defensively for the
        # same underlying cursor-stack issue (see _PlotCanvas.leaveEvent).
        from PyQt5.QtWidgets import QApplication
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

        if self._initial_compute_pending:
            self._initial_compute_pending = False
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtCore import QTimer
            QApplication.processEvents()
            QTimer.singleShot(50, self._compute_svd)

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 980])
        root.addWidget(splitter)

    def _build_left(self):
        w = QWidget()
        w.setMinimumWidth(260)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # SVD settings
        svd_grp = QGroupBox('SVD settings')
        sg = QVBoxLayout(svd_grp)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel('Max components:'))
        self._n_comp_spin = QSpinBox()
        self._n_comp_spin.setRange(2, min(50, len(self.spectra),
                                          len(self.spectra[0]['x_scale'])
                                          if self.spectra else 50))
        self._n_comp_spin.setValue(min(10, len(self.spectra)))
        self._n_comp_spin.setFixedWidth(60)
        r1.addWidget(self._n_comp_spin)
        r1.addStretch()
        sg.addLayout(r1)
        self._mean_center_cb = QCheckBox('Mean-center spectra before SVD')
        self._mean_center_cb.setChecked(True)
        self._mean_center_cb.setToolTip(
            "Standard PCA convention: subtract the mean spectrum (the "
            "average of every selected spectrum) before decomposing, so "
            "the components describe how spectra differ from each other "
            "rather than being dominated by whatever signal level they "
            "all share. Checked by default here since this dialog is "
            "framed as PCA; SVD Analysis defaults this off to match its "
            "traditional raw-SVD convention. Toggling recomputes "
            "instantly."
        )
        # stateChanged passes the new Qt.CheckState int through — _compute_svd
        # takes no arguments, so a plain lambda discards it rather than
        # letting PyQt pass it straight through (which would raise a
        # TypeError: _compute_svd() takes 1 positional argument but 2 were given).
        self._mean_center_cb.stateChanged.connect(lambda _checked: self._compute_svd())
        sg.addWidget(self._mean_center_cb)
        self._recompute_btn = QPushButton('Recompute SVD')
        self._recompute_btn.clicked.connect(self._compute_svd)
        sg.addWidget(self._recompute_btn)
        self._run_bootstrap_btn = QPushButton('Bootstrap Uncertainty…')
        self._run_bootstrap_btn.setToolTip(
            'Estimates how sensitive the CURRENTLY LOADED SVD’s loadings\n'
            'and scores are to the actual noise in your data — a residual\n'
            'bootstrap around this exact result. Every replicate is\n'
            'sign-aligned back to this result first (the same ambiguity\n'
            'the axis Invert controls in SVD Analysis exist to fix by\n'
            'hand), so the band reflects noise sensitivity only, not\n'
            'sign flips. Runs automatically around whichever SVD is\n'
            'currently loaded above.'
        )
        self._run_bootstrap_btn.clicked.connect(self._prompt_and_run_bootstrap)
        sg.addWidget(self._run_bootstrap_btn)
        layout.addWidget(svd_grp)

        # Metric display — always visible (not tied to whichever tab is
        # active), since the chosen metric drives labels in more than one
        # place: Scores axis labels and the Loadings component list both
        # read from this same choice.
        metric_grp = QGroupBox('Metric display')
        mg = QVBoxLayout(metric_grp)
        metric_row = QHBoxLayout()
        metric_label = QLabel('Metric:')
        metric_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        metric_row.addWidget(metric_label)
        self._pc_label_metric_combo = QComboBox()
        self._pc_label_metric_combo.addItems(list(self._METRICS.keys()))
        self._pc_label_metric_combo.setCurrentText('Explained variance (%)')
        self._pc_label_metric_combo.setToolTip(
            'Which number appears next to each PC: in Scores axis labels\n'
            'and in the Loadings component list.'
        )
        self._pc_label_metric_combo.currentIndexChanged.connect(self._refresh_scores)
        self._pc_label_metric_combo.currentIndexChanged.connect(self._refresh_loadings_list_labels)
        metric_row.addWidget(self._pc_label_metric_combo)
        mg.addLayout(metric_row)

        fmt_row = QHBoxLayout()
        fmt_label = QLabel('Format:')
        fmt_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        fmt_row.addWidget(fmt_label)
        self._pc_label_format_combo = QComboBox()
        self._pc_label_format_combo.addItems(['Fixed', 'Scientific'])
        self._pc_label_format_combo.currentIndexChanged.connect(self._refresh_scores)
        self._pc_label_format_combo.currentIndexChanged.connect(self._refresh_loadings_list_labels)
        fmt_row.addWidget(self._pc_label_format_combo)
        decimals_label = QLabel('Decimals:')
        decimals_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        fmt_row.addWidget(decimals_label)
        self._pc_label_decimals_spin = QSpinBox()
        self._pc_label_decimals_spin.setRange(0, 6)
        self._pc_label_decimals_spin.setValue(3)
        self._pc_label_decimals_spin.setFixedWidth(45)
        self._pc_label_decimals_spin.setKeyboardTracking(False)
        self._pc_label_decimals_spin.valueChanged.connect(self._refresh_scores)
        self._pc_label_decimals_spin.valueChanged.connect(self._refresh_loadings_list_labels)
        fmt_row.addWidget(self._pc_label_decimals_spin)
        mg.addLayout(fmt_row)
        layout.addWidget(metric_grp)

        # Scores settings
        scores_grp = QGroupBox('Scores plot')
        self._scores_grp = scores_grp
        sg2 = QVBoxLayout(scores_grp)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel('X axis (PC):'))
        self._pc_x_spin = QSpinBox()
        self._pc_x_spin.setRange(1, 10)
        self._pc_x_spin.setValue(1)
        self._pc_x_spin.setFixedWidth(50)
        self._pc_x_spin.setKeyboardTracking(False)
        self._pc_x_spin.valueChanged.connect(self._refresh_scores)
        r2.addWidget(self._pc_x_spin)
        r2.addStretch()
        sg2.addLayout(r2)
        r3 = QHBoxLayout()
        r3.addWidget(QLabel('Y axis (PC):'))
        self._pc_y_spin = QSpinBox()
        self._pc_y_spin.setRange(1, 10)
        self._pc_y_spin.setValue(2)
        self._pc_y_spin.setFixedWidth(50)
        self._pc_y_spin.setKeyboardTracking(False)
        self._pc_y_spin.valueChanged.connect(self._refresh_scores)
        r3.addWidget(self._pc_y_spin)
        r3.addStretch()
        sg2.addLayout(r3)

        self._scores_3d_cb = QCheckBox('3D plot (adds a Z axis)')
        self._scores_3d_cb.setToolTip(
            'Plot three components at once instead of two — sometimes\n'
            'reveals separation between groups that overlap in any single\n'
            '2D projection.'
        )
        self._scores_3d_cb.stateChanged.connect(self._on_3d_toggled)
        sg2.addWidget(self._scores_3d_cb)

        self._z_row = QHBoxLayout()
        self._z_row.addWidget(QLabel('Z axis (PC):'))
        self._pc_z_spin = QSpinBox()
        self._pc_z_spin.setRange(1, 10)
        self._pc_z_spin.setValue(3)
        self._pc_z_spin.setFixedWidth(50)
        self._pc_z_spin.setKeyboardTracking(False)
        self._pc_z_spin.valueChanged.connect(self._refresh_scores)
        self._z_row.addWidget(self._pc_z_spin)
        self._z_row.addStretch()
        sg2.addLayout(self._z_row)
        self._set_z_row_visible(False)

        r4 = QHBoxLayout()
        r4.addWidget(QLabel('Colour by:'))
        self._color_combo = QComboBox()
        self._color_combo.addItems(['index', 'T\u00b2 (Hotelling)'])
        self._color_combo.setToolTip(
            'index: colour each spectrum by its position in the list\n'
            'PC1, PC2, ...: colour by score on that component (the list is\n'
            'rebuilt after each SVD computation to match how many components\n'
            'actually exist)\n'
            'T\u00b2 (Hotelling): colour by Hotelling\'s T\u00b2 statistic — a\n'
            'standard PCA outlier metric combining all plotted components;\n'
            'high values flag spectra that are unusual relative to the rest'
        )
        self._color_combo.currentIndexChanged.connect(self._refresh_scores)
        r4.addWidget(self._color_combo)
        r4.addStretch()
        sg2.addLayout(r4)
        self._show_labels_cb = QCheckBox('Show labels')
        self._show_labels_cb.setChecked(False)
        self._show_labels_cb.stateChanged.connect(self._refresh_scores)
        sg2.addWidget(self._show_labels_cb)
        self._scores_show_bootstrap_cb = QCheckBox('Show bootstrap confidence band')
        self._scores_show_bootstrap_cb.setChecked(True)
        self._scores_show_bootstrap_cb.setToolTip(
            'Error bars from Bootstrap Uncertainty (2D scatter only —\n'
            'a 3D scatter has no single well-defined line to draw them\n'
            'along). Only shown once Bootstrap Uncertainty has been run.'
        )
        self._scores_show_bootstrap_cb.stateChanged.connect(self._refresh_scores)
        sg2.addWidget(self._scores_show_bootstrap_cb)

        layout.addWidget(scores_grp)

        # Loadings settings
        load_grp = QGroupBox('Loadings plot')
        self._load_grp = load_grp
        lg = QVBoxLayout(load_grp)
        load_label_row = QHBoxLayout()
        load_label_row.addWidget(QLabel('Select components to show:'))
        load_label_row.addStretch()
        load_help_btn = QPushButton('?')
        load_help_btn.setFixedSize(28, 22)
        load_help_btn.setToolTip('How to select multiple components')
        load_help_btn.clicked.connect(self._show_loadings_selection_help)
        load_label_row.addWidget(load_help_btn)
        lg.addLayout(load_label_row)
        self._load_list = QListWidget()
        self._load_list.setSelectionMode(QListWidget.ExtendedSelection)
        lg.addWidget(self._load_list, 1)
        self._load_offset_cb = QCheckBox('Offset loadings for clarity')
        self._load_offset_cb.setChecked(True)
        self._load_offset_cb.stateChanged.connect(self._refresh_loadings)
        lg.addWidget(self._load_offset_cb)
        self._load_show_bootstrap_cb = QCheckBox('Show bootstrap confidence band')
        self._load_show_bootstrap_cb.setChecked(True)
        self._load_show_bootstrap_cb.setToolTip(
            'Shaded band from Bootstrap Uncertainty, drawn behind each\n'
            'selected loading in the same offset units the curve itself\n'
            'uses. Only shown once Bootstrap Uncertainty has been run.'
        )
        self._load_show_bootstrap_cb.stateChanged.connect(self._refresh_loadings)
        lg.addWidget(self._load_show_bootstrap_cb)
        layout.addWidget(load_grp, 1)
        # Scores tab is active by default (index 0) — hide the Loadings
        # settings until the user actually switches to that tab.
        load_grp.setVisible(False)

        layout.addStretch()

        btn_row = QHBoxLayout()
        self._save_btn = QPushButton('Save…')
        self._save_btn.setToolTip(
            'Save Scores, Loadings, and/or Variance metrics to Excel or text/CSV'
        )
        self._save_btn.clicked.connect(self._show_save_dialog)
        btn_row.addWidget(self._save_btn)
        btn_row.addStretch()
        help_btn = QPushButton('Help')
        help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(help_btn)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        return w

    def _build_right(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tabs = QTabWidget()
        self._tabs.tabBar().setExpanding(False)
        self._tabs.setStyleSheet(
            "QTabBar::tab { min-width: 80px; padding: 4px 12px; }"
        )
        self._tabs.currentChanged.connect(self._on_tab_changed)

        for title, canvas_attr in [
            ('Scores',   '_scores_canvas'),
            ('Loadings', '_loadings_canvas'),
        ]:
            pw = QWidget()
            pl = QVBoxLayout(pw)
            pl.setContentsMargins(0, 0, 0, 0)
            canvas = _PlotCanvas(pw)
            setattr(self, canvas_attr, canvas)
            pl.addWidget(NavigationToolbar(canvas, pw))
            pl.addWidget(canvas)
            self._tabs.addTab(pw, title)

        # Variance tab — metrics presentation modeled directly on SVD
        # Analysis's Diagnostics tab: Single/Compare/Overview view modes,
        # log scale, a per-metric explanation, and a full-window table
        # button, instead of a single fixed plot+table split. Uses the
        # shared self._METRICS catalog defined at class level.

        var_pw = QWidget()
        var_pl = QVBoxLayout(var_pw)
        var_pl.setContentsMargins(0, 0, 0, 0)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel('View:'))
        self._variance_mode_combo = QComboBox()
        self._variance_mode_combo.addItems(['Single metric', 'Compare two metrics', 'Overview (all)'])
        self._variance_mode_combo.currentIndexChanged.connect(self._on_variance_mode_changed)
        mode_row.addWidget(self._variance_mode_combo)

        self._variance_single_wrap = QWidget()
        single_row = QHBoxLayout(self._variance_single_wrap)
        single_row.setContentsMargins(0, 0, 0, 0)
        single_metric_label = QLabel('Metric:')
        single_metric_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        single_row.addWidget(single_metric_label)
        self._variance_single_combo = QComboBox()
        self._variance_single_combo.addItems(list(self._METRICS.keys()))
        self._variance_single_combo.setCurrentText('Explained variance (%)')
        self._variance_single_combo.currentIndexChanged.connect(self._on_variance_single_metric_changed)
        single_row.addWidget(self._variance_single_combo)
        mode_row.addWidget(self._variance_single_wrap)

        self._variance_compare_wrap = QWidget()
        compare_row = QHBoxLayout(self._variance_compare_wrap)
        compare_row.setContentsMargins(0, 0, 0, 0)
        x_label = QLabel('X:')
        x_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        compare_row.addWidget(x_label)
        self._variance_x_combo = QComboBox()
        self._variance_x_combo.addItems(list(self._METRICS.keys()))
        self._variance_x_combo.currentIndexChanged.connect(self._on_variance_x_metric_changed)
        compare_row.addWidget(self._variance_x_combo)
        self._variance_x_log_cb = QCheckBox('Log X')
        self._variance_x_log_cb.stateChanged.connect(self._refresh_variance)
        compare_row.addWidget(self._variance_x_log_cb)
        y_label = QLabel('Y:')
        y_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        compare_row.addWidget(y_label)
        self._variance_y_combo = QComboBox()
        self._variance_y_combo.addItems(list(self._METRICS.keys()))
        self._variance_y_combo.setCurrentText('Residual error E(m)')
        self._variance_y_combo.currentIndexChanged.connect(self._on_variance_y_metric_changed)
        compare_row.addWidget(self._variance_y_combo)
        self._variance_y_log_cb = QCheckBox('Log Y')
        self._variance_y_log_cb.stateChanged.connect(self._refresh_variance)
        compare_row.addWidget(self._variance_y_log_cb)
        mode_row.addWidget(self._variance_compare_wrap)
        self._variance_compare_wrap.setVisible(False)

        # Initialise the compare-mode log checkboxes to each metric's own
        # default (blocking signals so this doesn't trigger a redraw before
        # self._variance_canvas exists yet) — same approach as the Single
        # metric combo further down, and as SVD Analysis's Diagnostics tab.
        x_meta = self._METRICS[self._variance_x_combo.currentText()]
        y_meta = self._METRICS[self._variance_y_combo.currentText()]
        self._variance_x_log_cb.blockSignals(True)
        self._variance_x_log_cb.setChecked(x_meta['log'])
        self._variance_x_log_cb.blockSignals(False)
        self._variance_y_log_cb.blockSignals(True)
        self._variance_y_log_cb.setChecked(y_meta['log'])
        self._variance_y_log_cb.blockSignals(False)

        mode_row.addStretch()
        var_pl.addLayout(mode_row)

        opt_row = QHBoxLayout()
        self._variance_log_cb = QCheckBox('Log scale')
        self._variance_log_cb.setToolTip(
            'Several metrics span orders of magnitude \u2014 a log scale makes\n'
            'the elbow/cutoff point far easier to see than a linear scale.\n'
            'Resets to the metric\'s own default whenever you change metric.'
        )
        self._variance_log_cb.stateChanged.connect(self._refresh_variance)
        # Match the log checkbox to 'Explained variance (%)''s own default
        # (linear) — kept explicit rather than relying on QCheckBox's
        # implicit unchecked default, so this stays correct if the initial
        # metric above ever changes.
        self._variance_log_cb.setChecked(
            self._METRICS[self._variance_single_combo.currentText()]['log'])
        opt_row.addWidget(self._variance_log_cb)

        self._variance_overview_log_cb = QCheckBox('Log scale (overview)')
        self._variance_overview_log_cb.setChecked(False)
        self._variance_overview_log_cb.setToolTip(
            'Force log scale on all seven panels in the Overview.\n'
            'When unchecked, each panel uses its own metric\'s default scale\n'
            '(\u03c3, Eigenvalue, E, IND \u2192 log; variance metrics \u2192 linear).'
        )
        self._variance_overview_log_cb.setVisible(False)
        self._variance_overview_log_cb.stateChanged.connect(self._refresh_variance)
        opt_row.addWidget(self._variance_overview_log_cb)

        opt_row.addStretch()
        self._variance_info_btn = QPushButton('\u2139  What does this metric mean?')
        self._variance_info_btn.clicked.connect(self._show_variance_metric_info)
        opt_row.addWidget(self._variance_info_btn)
        var_table_btn = QPushButton('Show all metrics (table)\u2026')
        var_table_btn.clicked.connect(self._show_variance_metrics_table)
        opt_row.addWidget(var_table_btn)
        var_pl.addLayout(opt_row)

        self._variance_canvas = _PlotCanvas(var_pw)
        var_pl.addWidget(NavigationToolbar(self._variance_canvas, var_pw))
        var_pl.addWidget(self._variance_canvas)

        self._tabs.addTab(var_pw, 'Diagnostics')

        layout.addWidget(self._tabs)
        return w

    # ------------------------------------------------------------------ #
    # SVD computation                                                      #
    # ------------------------------------------------------------------ #

    def _compute_svd(self):
        if not self.spectra:
            return
        if getattr(self, '_pca_svd_running', False):
            return  # already running — ignore a second trigger outright
        self._pca_svd_running = True
        self._set_pca_controls_enabled(False)

        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        self._pca_progress = QProgressDialog('Computing SVD…', None, 0, 0, self)
        self._pca_progress.setWindowModality(Qt.WindowModal)
        self._pca_progress.setWindowTitle('PCA / SVD')
        self._pca_progress.setMinimumDuration(0)
        self._pca_progress.setCancelButton(None)
        self._pca_progress.show()
        # No manual QApplication.processEvents() here — see the identical
        # fix (and the reasoning behind it) in svd_analysis_dialog.py and
        # cluster_analysis_dialog.py's showEvent/run_clustering.

        n_requested = self._n_comp_spin.value()
        mean_center = self._mean_center_cb.isChecked()

        # self.controller.compute_svd_analysis is pure computation (no Qt
        # widget access) — safe to run on the background thread. Its
        # result now lives on self.controller.manager rather than in a
        # dict passed back through the worker.
        self._svd_worker = _ComputeWorker(
            lambda: self.controller.compute_svd_analysis(self.spectra, n_requested, mean_center=mean_center), self)
        self._svd_worker.done.connect(self._on_pca_svd_computed)
        self._svd_worker.start(QThread.LowPriority)

    def _on_pca_svd_computed(self):
        try:
            if self._svd_worker.error is not None:
                logger.warning("PcaScoresDialog: SVD computation raised: %s", self._svd_worker.error)
                QMessageBox.critical(
                    self, "SVD Computation Failed",
                    f"An unexpected error occurred:\n\n{self._svd_worker.error}"
                )
                return
            success = self._svd_worker.result
            if not success:
                logger.warning("PcaScoresDialog: SVD computation failed")
                # Previously this returned silently — no message box, only
                # a log entry invisible to anyone not watching the log
                # file. The progress dialog still closed and the button
                # re-enabled (the finally block below always runs), so
                # nothing visibly hung, but there was also nothing telling
                # the user their click didn't produce a result, or why.
                message = getattr(self.controller.manager, 'last_error', None) or (
                    "SVD computation failed for an unknown reason. See the "
                    "application log for details."
                )
                QMessageBox.warning(self, "SVD Computation Failed", message)
                return

            # Pull the freshly computed state from the manager. Everywhere
            # else in this file keeps reading these same self._U / self._s
            # / etc. attributes exactly as before — only where they get
            # filled in has changed.
            manager = self.controller.manager
            self._U               = manager.U               # (n_wl × n)
            self._s               = manager.s                # (n,)
            self._Vt              = manager.Vt               # (n × n_spec)
            self._x_axis          = manager.x_axis
            self._expl_var        = manager.explained_variance
            self._residual_err    = manager.residual_err
            self._malinowski_ind  = manager.malinowski_ind
            n = len(self._s)

            # Update spinbox ranges
            for spin in (self._pc_x_spin, self._pc_y_spin, self._pc_z_spin):
                spin.setMaximum(n)
            if n < 3 and self._scores_3d_cb.isChecked():
                self._scores_3d_cb.setChecked(False)  # triggers _on_3d_toggled

            # Colour by — repopulate with every PC actually available (was
            # hardcoded to PC3/PC4/PC5 regardless of n, which made no sense
            # for fewer than 5 or more than 5 components)
            prev_color = self._color_combo.currentText()
            self._color_combo.blockSignals(True)
            self._color_combo.clear()
            self._color_combo.addItems(
                ['index'] + [f'PC{i+1}' for i in range(n)] + ['T\u00b2 (Hotelling)'])
            if prev_color in [self._color_combo.itemText(i) for i in range(self._color_combo.count())]:
                self._color_combo.setCurrentText(prev_color)
            self._color_combo.blockSignals(False)

            # Update loadings list
            self._load_list.blockSignals(True)
            self._load_list.clear()
            for i in range(n):
                self._load_list.addItem(
                    f'PC{i+1}  ({self._pc_axis_label(i)})')
            for i in range(min(3, n)):
                self._load_list.item(i).setSelected(True)
            self._load_list.blockSignals(False)
            self._load_list.itemSelectionChanged.connect(self._refresh_loadings)

            # Plotting (Scores/Loadings/Variance) can itself take a while
            # for many spectra/components — closing the progress dialog
            # only in the finally block below means it stays visible for
            # that too, not just the underlying SVD computation.
            self._refresh_all()
        finally:
            self._pca_progress.close()
            self._set_pca_controls_enabled(True)
            self._pca_svd_running = False
            from PyQt5.QtWidgets import QApplication
            QApplication.restoreOverrideCursor()

    def _set_pca_controls_enabled(self, enabled):
        """Shared enable/disable for everything that starts a background
        computation on self.controller.manager -- recomputing the SVD and
        running Bootstrap Uncertainty must not be allowed to overlap,
        since both replace/reset the same manager state. Mirrors
        NMFDialog._set_nmf_controls_enabled."""
        self._recompute_btn.setEnabled(enabled)
        self._n_comp_spin.setEnabled(enabled)
        self._mean_center_cb.setEnabled(enabled)
        self._run_bootstrap_btn.setEnabled(enabled)

    def _prompt_and_run_bootstrap(self):
        """Ask how many bootstrap resamples to run, mirroring
        NMFDialog._prompt_and_run_bootstrap. Requires an already-computed
        SVD (self._U/self._Vt and the manager's own data_matrix all set)
        -- this refits AROUND that specific result to measure its noise
        sensitivity, it does not produce a new SVD on its own. Unlike
        SVDAnalysisDialog's version, there is no separate signal/noise
        n_components choice to make here: this manager already fixed how
        many components count as signal at compute time (the "Max
        components" spinbox above), so PcaScoresController.
        compute_bootstrap_uncertainty always covers exactly those."""
        if getattr(self, '_pca_svd_running', False):
            return
        manager = self.controller.manager
        if (self._U is None or self._Vt is None
                or manager is None or manager.data_matrix is None):
            QMessageBox.information(
                self, 'Bootstrap Uncertainty',
                'Compute an SVD first — Bootstrap Uncertainty refits\n'
                'around whatever result is currently loaded above; it\n'
                'doesn\u2019t produce one on its own.')
            return
        from PyQt5.QtWidgets import QInputDialog
        n_resamples, ok = QInputDialog.getInt(
            self, 'Bootstrap Uncertainty',
            'Number of bootstrap resamples:',
            value=self._last_n_bootstrap, min=5, max=500)
        if not ok:
            return
        self._last_n_bootstrap = n_resamples   # remembered and pre-filled next time
        self._run_bootstrap_uncertainty(n_resamples)

    def _run_bootstrap_uncertainty(self, n_resamples):
        """Residual bootstrap around self.controller.manager's own
        decomposition, with every replicate sign-aligned back to it --
        see PcaScoresController.compute_bootstrap_uncertainty for the
        method itself, and the Developer Guide's "SVD Analysis / PCA
        Bootstrap Uncertainty" section for the full reasoning (the sign
        ambiguity it corrects for is the same one SVD Analysis's own
        Invert controls exist to fix by hand). Deliberately a plain
        sequential loop with a real, cancellable QProgressDialog, the
        same pattern NMFDialog._run_bootstrap_uncertainty uses."""
        if getattr(self, '_pca_svd_running', False):
            return
        self._pca_svd_running = True
        self._set_pca_controls_enabled(False)

        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))

        manager = self.controller.manager

        progress = QProgressDialog(
            f'Bootstrap resample 1 of {n_resamples}\u2026', 'Cancel', 0, n_resamples, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle('PCA / SVD')
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        def _on_progress(b, n_total):
            progress.setLabelText(f'Bootstrap resample {b + 1} of {n_total}\u2026')
            progress.setValue(b)
            QApplication.processEvents()

        try:
            result = self.controller.compute_bootstrap_uncertainty(
                manager, n_resamples=n_resamples,
                confidence_level=_BOOTSTRAP_CONFIDENCE_LEVEL,
                random_state=None,
                progress_callback=_on_progress,
                cancel_check=progress.wasCanceled)
            progress.setValue(n_resamples)

            if result is None:
                QMessageBox.warning(
                    self, 'Bootstrap Uncertainty',
                    manager.last_error or 'All bootstrap resamples failed.')
                return

            pct = int(round(_BOOTSTRAP_CONFIDENCE_LEVEL * 100))
            msg = (f'Bootstrap uncertainty: {pct}% confidence band from '
                   f'{result["n_resamples_used"]}/{result["n_resamples_requested"]} '
                   f'resamples')
            if result['n_failed']:
                msg += f' ({result["n_failed"]} refit failed and were skipped)'
            QMessageBox.information(self, 'Bootstrap Uncertainty', msg)
            self._refresh_scores()
            self._refresh_loadings()
        finally:
            self._set_pca_controls_enabled(True)
            self._pca_svd_running = False
            QApplication.restoreOverrideCursor()

    def _refresh_all(self):
        self._refresh_scores()
        self._refresh_loadings()
        self._refresh_variance()

    def _on_tab_changed(self, idx):
        tab = self._tabs.tabText(idx)
        self._scores_grp.setVisible(tab == 'Scores')
        self._load_grp.setVisible(tab == 'Loadings')
        if tab == 'Scores':
            self._refresh_scores()
        elif tab == 'Loadings':
            self._refresh_loadings()
        elif tab == 'Diagnostics':
            self._refresh_variance()

    def _set_z_row_visible(self, visible):
        for i in range(self._z_row.count()):
            w = self._z_row.itemAt(i).widget()
            if w is not None:
                w.setVisible(visible)

    def _on_3d_toggled(self, *_):
        is_3d = self._scores_3d_cb.isChecked()
        self._set_z_row_visible(is_3d)
        self._refresh_scores()

    def _show_loadings_selection_help(self):
        QMessageBox.information(
            self, 'Selecting components',
            'Click a component to select just that one.\n\n'
            'Ctrl+click to add or remove individual components from the '
            'selection without losing the rest.\n\n'
            'Shift+click to select every component between the last-clicked '
            'one and the one you just clicked.\n\n'
            'All currently selected components are plotted together in the '
            'Loadings tab.'
        )

    def _format_pc_number(self, value):
        """Format a single number per the Axis label format/Decimals controls."""
        decimals = self._pc_label_decimals_spin.value()
        if self._pc_label_format_combo.currentText().startswith('Scientific'):
            return f'{value:.{decimals}e}'
        return f'{value:.{decimals}f}'

    def _pc_axis_label(self, pc_index):
        """Build the '(value)' part of a PC axis label using whichever
        metric and format are currently selected in Metric / Format /
        Decimals — defaults to explained variance, but a component with a
        vanishingly small share can otherwise round to 0.0% and look
        broken even though the real number is fine.
        """
        metric = self._pc_label_metric_combo.currentText()
        values = self._get_metric_values(metric)
        value = values[pc_index] if pc_index < len(values) else 0.0
        formatted = self._format_pc_number(value)
        return f'{formatted} %' if '%' in metric else formatted

    def _refresh_loadings_list_labels(self, *_):
        """Rebuild the Loadings component list's displayed text (which
        reflects the chosen Metric/Format/Decimals) without disturbing
        which components are currently selected."""
        if self._expl_var is None:
            return
        n = len(self._expl_var)
        selected_indices = {i for i in range(self._load_list.count())
                            if self._load_list.item(i).isSelected()}
        self._load_list.blockSignals(True)
        self._load_list.clear()
        for i in range(n):
            self._load_list.addItem(f'PC{i+1}  ({self._pc_axis_label(i)})')
        for i in selected_indices:
            if i < self._load_list.count():
                self._load_list.item(i).setSelected(True)
        self._load_list.blockSignals(False)
        self._refresh_loadings()

    # ------------------------------------------------------------------ #
    # Scores plot                                                          #
    # ------------------------------------------------------------------ #

    def _refresh_scores(self, *_):
        if self._Vt is None:
            return

        n = self._Vt.shape[0]
        is_3d = self._scores_3d_cb.isChecked() and n >= 3

        # matplotlib requires the 3D projection to be set when the axes is
        # created — it can't be toggled on an existing 2D axes. Only
        # rebuild when actually switching, not on every refresh.
        if is_3d != self._scores_is_3d:
            self._scores_canvas.fig.clf()
            if is_3d:
                self._scores_canvas.ax = self._scores_canvas.fig.add_subplot(111, projection='3d')
                # The figure was constructed with tight_layout=True, which
                # auto-applies layout adjustments on every draw — entirely
                # independent of whether draw_tight() or draw_idle() is
                # called explicitly. That auto-adjustment is what kept
                # overriding the fixed positions below, every single
                # refresh. Disabling it for 3D (matplotlib version
                # dependent API, hence the try/except) is what actually
                # makes the fixed positions stick.
                try:
                    self._scores_canvas.fig.set_layout_engine(None)
                except AttributeError:
                    self._scores_canvas.fig.set_tight_layout(False)
                # Fixed position, set once and never auto-adjusted —
                # leaves a reserved strip on the right for an optional
                # colorbar. make_axes_locatable (used for the 2D case)
                # doesn't support 3D axes, and capturing/restoring
                # get_position() turned out not to work either — 3D axes
                # apparently shrink via some other internal state that
                # isn't fully reflected there. A fixed-position colorbar
                # axes sidesteps the problem entirely: fig.colorbar()
                # never gets to auto-manage anything, because cax= tells
                # it exactly where to draw, every single time.
                self._scores_canvas.ax.set_position([0.05, 0.08, 0.78, 0.86])
                self._scores_cbar_ax = self._scores_canvas.fig.add_axes([0.86, 0.15, 0.025, 0.7])
                self._scores_cbar_ax.set_visible(False)
            else:
                self._scores_canvas.ax = self._scores_canvas.fig.add_subplot(111)
                self._scores_cbar_ax = None
                try:
                    self._scores_canvas.fig.set_layout_engine('tight')
                except AttributeError:
                    self._scores_canvas.fig.set_tight_layout(True)
            self._scores_colorbar = None
            self._scores_is_3d = is_3d

        ax = self._scores_canvas.ax
        ax.clear()

        pc_x = min(self._pc_x_spin.value() - 1, n - 1)
        pc_y = min(self._pc_y_spin.value() - 1, n - 1)
        xs = self._Vt[pc_x, :]
        ys = self._Vt[pc_y, :]
        n_spec = len(xs)

        if is_3d:
            pc_z = min(self._pc_z_spin.value() - 1, n - 1)
            zs = self._Vt[pc_z, :]
        else:
            pc_z = None

        # Bootstrap confidence band (see "Bootstrap Uncertainty..." above
        # and PcaScoresController.compute_bootstrap_uncertainty): drawn as
        # per-spectrum error bars on both axes, behind the scatter points.
        # 2D only -- a 3D scatter has no single well-defined line to draw
        # an error bar along, so it's deliberately skipped there rather
        # than drawn somewhere misleading (same reasoning NMFDialog uses
        # to skip Stacked bars).
        br = self.controller.manager.bootstrap_result
        show_band = (not is_3d and br is not None
                     and self._scores_show_bootstrap_cb.isChecked()
                     and pc_x < br['Vt_lower'].shape[0]
                     and pc_y < br['Vt_lower'].shape[0])

        # Colour by
        color_by = self._color_combo.currentText()
        cmap, c_values, c_label = None, None, None
        if color_by == 'index':
            cmap, c_values, c_label = 'viridis', np.arange(n_spec), 'Spectrum index'
        elif color_by.startswith('T'):
            pcs_used = [pc_x, pc_y] + ([pc_z] if pc_z is not None else [])
            c_values = self.controller.hotelling_t2(pcs_used)
            cmap, c_label = 'magma', "T\u00b2 (Hotelling)"
        else:
            pc_c = int(color_by.replace('PC', '')) - 1
            if pc_c < n:
                cmap, c_values, c_label = 'coolwarm', self._Vt[pc_c, :], f'Score on {color_by}'

        if show_band:
            x_lo = np.clip(xs - br['Vt_lower'][pc_x, :], 0, None)
            x_hi = np.clip(br['Vt_upper'][pc_x, :] - xs, 0, None)
            y_lo = np.clip(ys - br['Vt_lower'][pc_y, :], 0, None)
            y_hi = np.clip(br['Vt_upper'][pc_y, :] - ys, 0, None)
            ax.errorbar(xs, ys, xerr=[x_lo, x_hi], yerr=[y_lo, y_hi],
                        fmt='none', ecolor='#999999', alpha=0.5, capsize=2, zorder=1)

        if c_values is not None:
            if is_3d:
                sc = ax.scatter(xs, ys, zs, c=c_values, cmap=cmap, s=35, alpha=0.85)
                self._scores_cbar_ax.set_visible(True)
                self._scores_cbar_ax.clear()
                self._scores_colorbar = self._scores_canvas.fig.colorbar(
                    sc, cax=self._scores_cbar_ax, label=c_label)
            else:
                sc = ax.scatter(xs, ys, c=c_values, cmap=cmap, s=40, alpha=0.85, zorder=3)
                # fig.colorbar(ax=ax) permanently shrinks ax to make room
                # for itself, and that shrink compounds on every redraw —
                # a dedicated axes, created once and reused, avoids this.
                if self._scores_cbar_ax is None:
                    divider = make_axes_locatable(ax)
                    self._scores_cbar_ax = divider.append_axes('right', size='3%', pad=0.3)
                else:
                    self._scores_cbar_ax.clear()
                self._scores_colorbar = self._scores_canvas.fig.colorbar(
                    sc, cax=self._scores_cbar_ax, label=c_label)
        else:
            if is_3d:
                self._scores_cbar_ax.set_visible(False)
                ax.scatter(xs, ys, zs, color='#1565C0', s=35, alpha=0.85)
            else:
                ax.scatter(xs, ys, color='#1565C0', s=40, alpha=0.85)

        # Labels
        if self._show_labels_cb.isChecked():
            for i in range(n_spec):
                lbl = self._labels[i] if i < len(self._labels) else str(i + 1)
                if is_3d:
                    ax.text(xs[i], ys[i], zs[i], lbl[-20:], fontsize=6, alpha=0.7)
                else:
                    ax.annotate(lbl[-20:], (xs[i], ys[i]), fontsize=6,
                                xytext=(3, 3), textcoords='offset points', alpha=0.7)

        ax.set_xlabel(f'PC{pc_x+1}  ({self._pc_axis_label(pc_x)})', fontsize=10)
        ax.set_ylabel(f'PC{pc_y+1}  ({self._pc_axis_label(pc_y)})', fontsize=10)

        if is_3d:
            ax.set_zlabel(f'PC{pc_z+1}  ({self._pc_axis_label(pc_z)})', fontsize=10)
            ax.set_title(f'Scores: PC{pc_x+1} vs PC{pc_y+1} vs PC{pc_z+1}  '
                         f'({n_spec} spectra)', fontsize=11)
            # tight_layout() is unreliable with 3D axes and would override
            # the explicit fixed positions set above — which is exactly
            # what was reintroducing the shrinking bug. Drawing directly
            # skips it entirely for the 3D case.
            self._scores_canvas.draw_idle()
        else:
            # axhline(0)/axvline(0) below are full-width/height reference
            # lines that matplotlib's autoscale takes into account by
            # default — stretching the visible range out to the origin
            # even when no actual data point is anywhere near it. Fixing
            # the limits to the real data range (with a small margin)
            # first means the lines just extend across that fixed range
            # instead of expanding it; if the data doesn't naturally pass
            # near zero, the lines simply won't be visible, which is fine.
            if show_band:
                # Widen the fixed range to the error bars too, not just
                # the point estimates -- otherwise a band can be clipped
                # right at the axes edge, which looks like a rendering
                # bug rather than the actual (wider) uncertainty.
                x_min = float(min(xs.min(), (xs - x_lo).min()))
                x_max = float(max(xs.max(), (xs + x_hi).max()))
                y_min = float(min(ys.min(), (ys - y_lo).min()))
                y_max = float(max(ys.max(), (ys + y_hi).max()))
            else:
                x_min, x_max = float(xs.min()), float(xs.max())
                y_min, y_max = float(ys.min()), float(ys.max())
            x_pad = (x_max - x_min) * 0.05 or 0.01
            y_pad = (y_max - y_min) * 0.05 or 0.01
            ax.set_xlim(x_min - x_pad, x_max + x_pad)
            ax.set_ylim(y_min - y_pad, y_max + y_pad)
            ax.axhline(0, color='#999', lw=0.6, ls='--')
            ax.axvline(0, color='#999', lw=0.6, ls='--')
            title = f'Scores: PC{pc_x+1} vs PC{pc_y+1}  ({n_spec} spectra)'
            if show_band:
                pct = int(round(br['confidence_level'] * 100))
                title += f'  — bars: {pct}% bootstrap CI (n={br["n_resamples_used"]})'
            ax.set_title(title, fontsize=11)
            ax.grid(True, linestyle='--', alpha=0.35)
            self._scores_canvas.draw_tight()

    # ------------------------------------------------------------------ #
    # Loadings plot                                                        #
    # ------------------------------------------------------------------ #

    def _refresh_loadings(self, *_):
        if self._U is None:
            return
        ax = self._loadings_canvas.ax
        ax.clear()

        sel_rows = [self._load_list.row(item)
                    for item in self._load_list.selectedItems()]
        if not sel_rows:
            self._loadings_canvas.draw_tight()
            return

        offset_step = 0.0
        if self._load_offset_cb.isChecked():
            max_amp = max(float(np.ptp(self._U[:, r])) for r in sel_rows)
            offset_step = max_amp * 1.1

        # Bootstrap confidence band (see "Bootstrap Uncertainty..." above
        # and PcaScoresController.compute_bootstrap_uncertainty): drawn
        # BEHIND each loading's own curve, in the same offset units the
        # curve itself uses -- mirrors NMFDialog._refresh_components's
        # band exactly.
        br = self.controller.manager.bootstrap_result
        show_band = (br is not None and self._load_show_bootstrap_cb.isChecked()
                     and br['U_lower'].shape[1] > max(sel_rows))

        for k, r in enumerate(sel_rows):
            loading = self._U[:, r]
            offset  = k * offset_step
            color   = _COLORS[r % len(_COLORS)]
            if show_band:
                ax.fill_between(self._x_axis, br['U_lower'][:, r] + offset,
                                br['U_upper'][:, r] + offset,
                                color=color, alpha=0.20, linewidth=0, zorder=1)
            ax.plot(self._x_axis, loading + offset, color=color,
                    lw=1.0, zorder=2, label=f'PC{r+1}  ({self._pc_axis_label(r)})')
            if self._load_offset_cb.isChecked():
                ax.axhline(offset, color=color, lw=0.4, ls=':', alpha=0.5)

        ax.set_xlim(float(self._x_axis.min()), float(self._x_axis.max()))
        ax.set_xlabel('x', fontsize=10)
        ax.set_ylabel('Loading' + (' (offset)' if self._load_offset_cb.isChecked()
                                    else ''), fontsize=10)
        title = 'Loadings (spectral components)'
        if show_band:
            pct = int(round(br['confidence_level'] * 100))
            title += f'  — shaded: {pct}% bootstrap CI (n={br["n_resamples_used"]})'
        ax.set_title(title, fontsize=11)
        ax.legend(fontsize=8, loc='best', framealpha=0.7)
        ax.grid(True, linestyle='--', alpha=0.35)
        self._loadings_canvas.draw_tight()

    # ------------------------------------------------------------------ #
    # Variance (scree) plot                                                #
    # ------------------------------------------------------------------ #

    def _on_variance_mode_changed(self, *_):
        mode = self._variance_mode_combo.currentText()
        self._variance_single_wrap.setVisible(mode == 'Single metric')
        self._variance_compare_wrap.setVisible(mode == 'Compare two metrics')
        self._variance_log_cb.setVisible(mode == 'Single metric')
        self._variance_overview_log_cb.setVisible(mode == 'Overview (all)')
        self._variance_info_btn.setText(
            '\u2139  What does this comparison mean?' if mode == 'Compare two metrics'
            else '\u2139  What does this metric mean?')
        self._variance_info_btn.setEnabled(mode != 'Overview (all)')
        self._refresh_variance()

    def _on_variance_single_metric_changed(self, *_):
        """Reset the log checkbox to the newly selected metric's own
        default. Without this, the checkbox keeps whatever state the
        previous metric left it in, so — combined with the old
        `log_scale or meta['log']` bug this replaces — unchecking it had
        no visible effect for any metric whose own default is log scale
        (Singular values, Eigenvalue, Residual error, Malinowski IND):
        meta['log'] being True meant the checkbox could never turn log
        scale *off*, only turn it on for the metrics that default to linear."""
        meta = self._METRICS[self._variance_single_combo.currentText()]
        self._variance_log_cb.blockSignals(True)
        self._variance_log_cb.setChecked(meta['log'])
        self._variance_log_cb.blockSignals(False)
        self._refresh_variance()

    def _on_variance_x_metric_changed(self, *_):
        """Sync the X log checkbox to the new metric's default, and nudge Y
        to a different metric if they'd otherwise match (comparing a metric
        against itself isn't useful)."""
        if self._variance_x_combo.currentIndex() == self._variance_y_combo.currentIndex():
            next_idx = (self._variance_y_combo.currentIndex() + 1) % self._variance_y_combo.count()
            self._variance_y_combo.blockSignals(True)
            self._variance_y_combo.setCurrentIndex(next_idx)
            self._variance_y_combo.blockSignals(False)
        meta = self._METRICS[self._variance_x_combo.currentText()]
        self._variance_x_log_cb.blockSignals(True)
        self._variance_x_log_cb.setChecked(meta['log'])
        self._variance_x_log_cb.blockSignals(False)
        self._refresh_variance()

    def _on_variance_y_metric_changed(self, *_):
        """Mirror of _on_variance_x_metric_changed for the Y side."""
        if self._variance_x_combo.currentIndex() == self._variance_y_combo.currentIndex():
            next_idx = (self._variance_x_combo.currentIndex() + 1) % self._variance_x_combo.count()
            self._variance_x_combo.blockSignals(True)
            self._variance_x_combo.setCurrentIndex(next_idx)
            self._variance_x_combo.blockSignals(False)
        meta = self._METRICS[self._variance_y_combo.currentText()]
        self._variance_y_log_cb.blockSignals(True)
        self._variance_y_log_cb.setChecked(meta['log'])
        self._variance_y_log_cb.blockSignals(False)
        self._refresh_variance()

    def _get_metric_values(self, metric_name):
        """Return the per-component array for any of the seven metrics in
        self._METRICS (colors/tooltips stay here since they're presentation
        concerns; the actual derived arrays are owned by
        self.controller.manager, same split as SVD Analysis's Diagnostics
        tab vs. SVDAnalysisManager)."""
        return self.controller.get_metric_values(metric_name)

    def _get_variance_compare_help_text(self):
        """Real interpretation guidance for the current X/Y pair — see
        _COMPARE_HELP. Falls back to a generic explanation of how to read
        two side-by-side component plots for any pair not specifically
        covered there (mostly anything paired with Eigenvalue, which is
        just \u03c3\u00b2 and therefore mirrors Singular values)."""
        x_name = self._variance_x_combo.currentText()
        y_name = self._variance_y_combo.currentText()
        pair = frozenset([x_name, y_name])
        if pair in self._COMPARE_HELP:
            return self._COMPARE_HELP[pair]
        return (
            f"{x_name} vs {y_name}\n\n"
            "Both metrics are plotted side by side against component number.\n\n"
            "Look for features that align between the two plots:\n"
            "\u2022 Kinks, elbows, or sudden changes that occur at the same component N\n"
            "  in both panels confirm that N is a real signal-to-noise boundary.\n"
            "\u2022 A dashed vertical line marks the Malinowski IND minimum on both panels\n"
            "  so you can see how that criterion relates to each metric visually.\n"
            "\u2022 If the two metrics show different features at different N values,\n"
            "  inspect the corresponding components in the Scores/Loadings tabs directly."
        )

    def _show_variance_metric_info(self):
        mode = self._variance_mode_combo.currentText()
        if mode == 'Single metric':
            name = self._variance_single_combo.currentText()
            tooltip = self._METRICS[name]['tooltip'].replace('\n', '<br>')
            QMessageBox.information(self, f'{name} \u2014 what does this mean?', tooltip)
        elif mode == 'Compare two metrics':
            text = self._get_variance_compare_help_text().replace('\n', '<br>')
            QMessageBox.information(self, 'About this comparison', text)

    def _plot_variance_metric(self, ax, name, use_log):
        """Draw a single metric against component number on the given axes.
        Shared by Single metric mode and each panel of Compare two metrics,
        so both modes render identically apart from being one axes vs. two."""
        meta = self._METRICS[name]
        n = len(self._expl_var)
        pcs = np.arange(1, n + 1)
        values = self._get_metric_values(name)
        if name == 'Explained variance (%)':
            ax.bar(pcs, values, color=meta['color'], alpha=0.8)
        else:
            ax.plot(pcs, values, 'o-', color=meta['color'])
        if use_log:
            ax.set_yscale('log')
        ax.set_xlabel('Principal component', fontsize=10)
        ax.set_ylabel(name, fontsize=10)
        ax.set_title(name, fontsize=11)
        ax.set_xticks(pcs)
        ax.grid(True, linestyle='--', alpha=0.35)

    def _refresh_variance(self, *_):
        if self._expl_var is None:
            return
        n = len(self._expl_var)
        pcs = np.arange(1, n + 1)
        mode = self._variance_mode_combo.currentText()
        fig = self._variance_canvas.fig
        fig.clf()

        ind_values = self._get_metric_values('Malinowski IND')
        ind_min_n = None
        if ind_values.size and not np.all(np.isnan(ind_values)):
            ind_min_n = int(np.nanargmin(ind_values)) + 1

        if mode == 'Single metric':
            ax = fig.add_subplot(111)
            name = self._variance_single_combo.currentText()
            # Use the checkbox's own state directly — not `checkbox or
            # meta['log']`, which used to make unchecking it a no-op for
            # every metric whose default is already log scale.
            self._plot_variance_metric(ax, name, self._variance_log_cb.isChecked())

        elif mode == 'Compare two metrics':
            # Two subplots side by side against component number — same
            # layout as SVD Analysis's Diagnostics tab — rather than a
            # single scatter of metric X against metric Y. A scatter mixes
            # two different units on one pair of axes and answers a
            # different question ("how correlated are these two metrics'
            # values") than what this view is meant for: seeing whether two
            # metrics agree on *where* (which component number) the
            # signal-to-noise boundary falls, which needs both plotted
            # against the same shared x-axis (component number).
            x_name = self._variance_x_combo.currentText()
            y_name = self._variance_y_combo.currentText()
            ax1 = fig.add_subplot(1, 2, 1)
            ax2 = fig.add_subplot(1, 2, 2)
            self._plot_variance_metric(ax1, x_name, self._variance_x_log_cb.isChecked())
            self._plot_variance_metric(ax2, y_name, self._variance_y_log_cb.isChecked())
            if ind_min_n is not None:
                for ax in (ax1, ax2):
                    ax.axvline(ind_min_n, color='purple', ls=':', lw=1.2, alpha=0.7,
                               label=f'IND min (N={ind_min_n})')
                    ax.legend(fontsize=7)

        else:  # Overview (all)
            force_log = self._variance_overview_log_cb.isChecked()
            for i, (name, meta) in enumerate(self._METRICS.items()):
                ax = fig.add_subplot(2, 4, i + 1)
                values = self._get_metric_values(name)
                if name == 'Explained variance (%)':
                    ax.bar(pcs, values, color=meta['color'], alpha=0.8)
                else:
                    ax.plot(pcs, values, 'o-', color=meta['color'], markersize=3)
                if force_log or meta['log']:
                    ax.set_yscale('log')
                ax.set_title(name, fontsize=9)
                ax.tick_params(labelsize=7)
                ax.grid(True, linestyle='--', alpha=0.3)

        self._variance_canvas.draw_tight()

    def _show_variance_metrics_table(self):
        """All six metrics, for every component, as a single table in a
        larger window — same data as Export Variance, but for on-screen
        scanning. Mirrors SVD Analysis's equivalent button."""
        if self._expl_var is None:
            return
        n = len(self._expl_var)
        pcs = np.arange(1, n + 1)
        columns = [('Component', pcs, '{:d}')]
        for name in self._METRICS:
            fmt = '{:.6g}' if name in ('Singular values (\u03c3)', 'Eigenvalue (\u03c3\u00b2)',
                                       'Residual error E(m)', 'Malinowski IND') else '{:.4f}'
            columns.append((name, self._get_metric_values(name), fmt))

        dlg = QDialog(self)
        dlg.setWindowTitle('All PCA/SVD Metrics')
        dlg.setModal(True)
        dlg.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint)
        dlg.resize(1000, 700)
        vbox = QVBoxLayout(dlg)

        table = QTableWidget(n, len(columns))
        table.setHorizontalHeaderLabels([c[0] for c in columns])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        for col_idx, (_, values, fmt) in enumerate(columns):
            for row_idx in range(n):
                val = values[row_idx] if row_idx < len(values) else np.nan
                text = '\u2014' if (isinstance(val, float) and np.isnan(val)) else fmt.format(val)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row_idx, col_idx, item)
        vbox.addWidget(table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        export_btn = QPushButton('Export…')
        export_btn.clicked.connect(self._export_variance)
        btn_row.addWidget(export_btn)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        vbox.addLayout(btn_row)

        dlg.exec_()

    # ------------------------------------------------------------------ #
    # Export                                                              #
    # ------------------------------------------------------------------ #

    def _export_variance(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Variance', 'pca_variance.csv', 'CSV Files (*.csv)')
        if not path:
            return
        try:
            cumvar = np.cumsum(self._expl_var)
            singular_values = self._s if self._s is not None else np.zeros(len(self._expl_var))
            eigenvalues = self._s ** 2 if self._s is not None else np.zeros(len(self._expl_var))
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(
                    ['Component', 'Singular values (sigma)', 'Eigenvalue (sigma^2)',
                     'Explained variance (%)', 'Cumulative explained var. (%)',
                     'Residual error E(m)', 'Malinowski IND'])
                for i, (ev, cv) in enumerate(zip(self._expl_var, cumvar)):
                    res = (f'{self._residual_err[i]:.6g}'
                           if self._residual_err is not None and i < len(self._residual_err)
                           else '')
                    ind = (f'{self._malinowski_ind[i]:.6g}'
                           if self._malinowski_ind is not None and i < len(self._malinowski_ind)
                              and not np.isnan(self._malinowski_ind[i])
                           else '')
                    writer.writerow(
                        [f'PC{i+1}', f'{singular_values[i]:.6g}', f'{eigenvalues[i]:.6g}',
                         f'{ev:.4f}', f'{cv:.4f}', res, ind])
            QMessageBox.information(
                self, 'Export Complete', f'Variance data exported to:\n{path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Export Failed', str(exc))

    def _show_save_dialog(self):
        """Open the unified Save dialog — same pattern as SVD Analysis's
        Save…: choose format, choose which categories to include, then
        write one Excel workbook or one/several text files."""
        if self._Vt is None:
            QMessageBox.warning(self, 'No Data', 'Compute SVD before saving.')
            return
        dlg = _PcaSaveDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._execute_save(dlg.save_config)

    def _execute_save(self, config):
        """Build the save config and hand off to the controller — actual
        DataFrame construction and file writing now lives in
        PcaScoresManager (save_results_excel/save_results_text), same split
        as SVD Analysis and Cluster Analysis."""
        file_path = config['file_path']
        try:
            if config['format'] == 'excel':
                success = self.controller.save_results_excel(
                    file_path, self._labels,
                    include_scores=config['include_scores'],
                    include_loadings=config['include_loadings'],
                    include_variance=config['include_variance'],
                )
            else:
                success = self.controller.save_results_text({
                    'file_path': file_path,
                    'labels': self._labels,
                    'delimiter': config['delimiter'],
                    'precision': config['precision'],
                    'save_separate': config['save_separate'],
                    'include_scores': config['include_scores'],
                    'include_loadings': config['include_loadings'],
                    'include_variance': config['include_variance'],
                })

            if success:
                QMessageBox.information(self, 'Save Complete', f'Results saved to:\n{file_path}')
            else:
                QMessageBox.warning(self, 'Save Failed', 'Failed to save PCA/SVD results.')
        except Exception as exc:
            QMessageBox.critical(self, 'Save Failed', str(exc))

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def _show_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'pca_scores')


# ======================================================================
# Reusable plot canvas
# ======================================================================

class _PcaSaveDialog(QDialog):
    """Save dialog for PCA/SVD Scores & Loadings — same pattern as SVD
    Analysis's Save…: choose format, choose which categories to include,
    and (for text) delimiter/precision/combined-vs-separate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.save_config = {}
        self.setWindowTitle('Save PCA/SVD Results')
        self.setModal(True)
        self.resize(480, 420)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        format_group = QGroupBox('File Format')
        format_layout = QVBoxLayout(format_group)
        self._format_buttons = QButtonGroup()
        self.excel_radio = QRadioButton('Excel (.xlsx)')
        self.excel_radio.setChecked(True)
        self._format_buttons.addButton(self.excel_radio)
        format_layout.addWidget(self.excel_radio)
        self.text_radio = QRadioButton('Text/CSV')
        self._format_buttons.addButton(self.text_radio)
        format_layout.addWidget(self.text_radio)
        layout.addWidget(format_group)

        self.text_options_group = QGroupBox('Text Format Options')
        text_layout = QVBoxLayout(self.text_options_group)
        delim_row = QHBoxLayout()
        delim_row.addWidget(QLabel('Delimiter:'))
        self.delimiter_combo = QComboBox()
        self.delimiter_combo.addItems(['Tab (\\t)', 'Comma (,)', 'Semicolon (;)', 'Space ( )'])
        delim_row.addWidget(self.delimiter_combo)
        text_layout.addLayout(delim_row)
        prec_row = QHBoxLayout()
        prec_row.addWidget(QLabel('Decimal Precision:'))
        self.precision_spin = QSpinBox()
        self.precision_spin.setRange(1, 15)
        self.precision_spin.setValue(6)
        prec_row.addWidget(self.precision_spin)
        text_layout.addLayout(prec_row)
        self.single_file_radio = QRadioButton('Save all data in one file')
        self.single_file_radio.setChecked(True)
        text_layout.addWidget(self.single_file_radio)
        self.separate_files_radio = QRadioButton('Save data in separate files')
        text_layout.addWidget(self.separate_files_radio)
        self.text_options_group.setEnabled(False)
        layout.addWidget(self.text_options_group)
        self.excel_radio.toggled.connect(lambda checked: self.text_options_group.setEnabled(not checked))

        include_group = QGroupBox('Include')
        include_layout = QHBoxLayout(include_group)
        self.include_scores_cb = QCheckBox('Scores')
        self.include_scores_cb.setChecked(True)
        include_layout.addWidget(self.include_scores_cb)
        self.include_loadings_cb = QCheckBox('Loadings')
        self.include_loadings_cb.setChecked(True)
        include_layout.addWidget(self.include_loadings_cb)
        self.include_variance_cb = QCheckBox('Variance (metrics)')
        self.include_variance_cb.setChecked(True)
        include_layout.addWidget(self.include_variance_cb)
        layout.addWidget(include_group)

        path_group = QGroupBox('Output File')
        path_layout = QVBoxLayout(path_group)
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText('Select output file…')
        path_row.addWidget(self.path_edit)
        browse_btn = QPushButton('Browse…')
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)
        path_layout.addLayout(path_row)
        layout.addWidget(path_group)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _browse(self):
        if self.excel_radio.isChecked():
            file_filter = 'Excel Files (*.xlsx);;All Files (*)'
            default_name = 'pca_scores_results.xlsx'
        else:
            file_filter = 'Text Files (*.txt);;CSV Files (*.csv);;All Files (*)'
            default_name = 'pca_scores_results.txt'
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save PCA/SVD Results', default_name, file_filter)
        if file_path:
            self.path_edit.setText(file_path)

    def _get_delimiter(self):
        text = self.delimiter_combo.currentText()
        if 'Tab' in text:
            return '\t'
        elif 'Comma' in text:
            return ','
        elif 'Semicolon' in text:
            return ';'
        elif 'Space' in text:
            return ' '
        return '\t'

    def _on_accept(self):
        if not self.path_edit.text():
            QMessageBox.warning(self, 'No File Selected', 'Please select an output file.')
            return
        if not (self.include_scores_cb.isChecked() or self.include_loadings_cb.isChecked()
                or self.include_variance_cb.isChecked()):
            QMessageBox.warning(self, 'Nothing to Save',
                                'Select at least one of Scores, Loadings, or Variance.')
            return
        self.save_config = {
            'file_path': self.path_edit.text(),
            'format': 'excel' if self.excel_radio.isChecked() else 'text',
            'include_scores': self.include_scores_cb.isChecked(),
            'include_loadings': self.include_loadings_cb.isChecked(),
            'include_variance': self.include_variance_cb.isChecked(),
            'delimiter': self._get_delimiter(),
            'precision': self.precision_spin.value(),
            'save_separate': self.separate_files_radio.isChecked(),
        }
        self.accept()


class _ComputeWorker(QThread):
    """Runs a single callable on a background thread — see the equivalent
    class in nmf_dialog.py for the full rationale: a long blocking call on
    the GUI thread freezes Qt's entire event loop, including the ability
    to paint, show, or hide a progress dialog, for its whole duration.
    The callable must not touch any Qt widgets — only pure computation is
    safe to run here.
    """
    done = pyqtSignal()

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self._fn()
        except Exception as exc:
            self.error = exc
        self.done.emit()


class _PlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(tight_layout=True)
        self.ax  = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fig.patch.set_facecolor('#ffffff')
        self.ax.set_facecolor('#ffffff')

    def leaveEvent(self, event):
        """Handle the mouse leaving the canvas.

        Deliberate override, not inherited behavior. matplotlib's own
        FigureCanvasQT.leaveEvent() unconditionally calls
        QApplication.restoreOverrideCursor() — it assumes matplotlib itself is
        the only thing that ever pushes a global override cursor. That's not
        true here: this dialog pushes its own override cursors (see
        PcaScoresDialog.__init__/showEvent and _compute_svd's progress
        cursor). This dialog isn't modal, so in practice the window where
        this could produce a visibly stuck cursor is much shorter-lived than
        in a modal dialog shown via exec_() — but it's the same latent bug,
        so it gets the same fix as InteractiveSVDAnalysisCanvas in
        svd_analysis_dialog.py and ClusterAnalysisCanvas in
        cluster_analysis_dialog.py: reimplement the same hover-leave
        notification without the blind cursor pop.
        """
        if self.figure is not None:
            from matplotlib.backend_bases import LocationEvent
            LocationEvent("figure_leave_event", self, *self.mouseEventCoords(),
                          guiEvent=event)._process()

    def draw_tight(self):
        try:
            self.fig.tight_layout()
        except Exception:
            pass
        self.draw_idle()
