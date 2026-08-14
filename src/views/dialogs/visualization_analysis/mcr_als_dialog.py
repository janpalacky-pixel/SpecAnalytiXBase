# src/views/dialogs/visualization_analysis/mcr_als_dialog.py
"""
MCR-ALS (Multivariate Curve Resolution - Alternating Least Squares) dialog.

Mirrors nmf_dialog.py's shape closely — MCR-ALS and NMF solve a related
problem (X ~= C @ ST / X ~= W @ H, both non-negative by default) but via
different algorithms (explicit NNLS-constrained alternating least squares
here, vs. NMF's multiplicative-update algorithm), which is why MCR-ALS
supports turning non-negativity off independently for either factor while
NMF does not.
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QComboBox, QPushButton, QLabel, QSpinBox, QCheckBox,
    QSizePolicy, QWidget, QTabWidget, QSplitter,
    QLineEdit, QDialogButtonBox, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QDoubleSpinBox, QListWidget, QListWidgetItem,
    QScrollArea, QMenu, QAction, QTableWidget, QTableWidgetItem,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.patheffects as mpl_path_effects

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import compute_distinguishing_labels, make_shorten_names_checkbox
from src.modules.visualization_analysis import ground_truth_comparison as gtc
from src.views.dialogs.misc.ground_truth_picker_dialog import pick_ground_truth_dataset
logger = get_logger(__name__)


def _ascending_xy(x, y):
    """Return (x, y) sorted by ascending x.

    np.interp() REQUIRES ascending x; given descending x it silently returns
    nonsense rather than raising. Descending x is common in practice (Raman files
    are frequently stored in descending wavenumber order), and the standard and
    row-oriented importers deliberately preserve the file's row order — so nothing
    upstream guarantees it. Sorting is a pure reordering (each y stays with its own
    x), so it cannot change a legitimate result; it only removes a way to get a
    silently wrong one.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size > 1 and np.any(np.diff(x) < 0):
        order = np.argsort(x, kind='stable')
        return x[order], y[order]
    return x, y


_COMP_NAME = 'MCR'

_COLORS = [
    '#1f77b4', '#d62728', '#2ca02c', '#ff7f0e', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]


class MCRALSDialog(QDialog):

    def __init__(self, parent=None, controller=None, spectra=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle('MCR-ALS (Multivariate Curve Resolution)')
        self.setMinimumSize(1020, 620)
        self.resize(1280, 760)
        self.setModal(True)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        self.controller = controller
        self.spectra   = list(spectra or [])
        self._settings = dict(current_settings or {})
        # self._mgr is refreshed from self.controller.manager after every
        # successful computation — the actual MCRALSManager instances live
        # on the controller, not here (see nmf_dialog.py for the same
        # "thin adapter" pattern).
        self._mgr      = None

        self._build_ui()
        self._apply_saved_settings()
        # _build_reference_group() built one reference picker per component
        # using the DEFAULT component count; _apply_saved_settings() may have
        # just restored a different count (e.g. 4). Rebuild the pickers now so
        # a reopened dialog shows the right number of them, not the default 2.
        self._rebuild_reference_rows()
        self._restore_saved_references()
        # Only now (after building + restoring settings) wire the
        # run-affecting controls to the stale-plot marker, so restoring
        # saved settings during construction doesn't blank the plots
        # before the first run has even happened.
        # Max-iterations DOES change the sweeps (each trial's convergence
        # depth), so it invalidates them. The component count does NOT —
        # see _mark_results_stale_keep_sweeps.
        self._iter_spin.valueChanged.connect(self._mark_results_stale)
        self._n_spin.valueChanged.connect(self._mark_results_stale_keep_sweeps)
        for _cb in (self._c_nonneg_cb, self._st_nonneg_cb, self._closure_cb):
            _cb.stateChanged.connect(self._mark_results_stale)
        # keep one reference-picker per component as the count changes
        self._n_spin.valueChanged.connect(self._rebuild_reference_rows)
        self._initial_run_pending = True
        self._elbow_cache_key = None
        self._elbow_cache_data = None
        self._fitq_cache_key = None
        self._fitq_cache_data = None

        # Hidden/testing-only ground-truth comparison state (see
        # _show_gt_context_menu). None until the user right-clicks and picks
        # a synthetic benchmark dataset. Never persisted anywhere outside
        # this dialog instance, so it can't leak between runs: this dialog
        # is freshly constructed every time MCR-ALS is opened (mirrors
        # nmf_dialog.py's identical reasoning), so simply not saving this
        # anywhere else is what makes it disappear the moment a new dataset
        # is loaded or the spectra selection changes in the main window and
        # MCR-ALS is reopened.
        self._gt = None
        self._gt_tab_widget = None
        self._gt_summary_label = None
        self._gt_report_table = None
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_gt_context_menu)

        self._on_tab_switched_refresh(self._tabs.currentIndex())

    def showEvent(self, event):
        super().showEvent(event)
        from PyQt5.QtWidgets import QApplication
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

        if self._initial_run_pending:
            self._initial_run_pending = False
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(50, self._run_mcr_als)

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.NoFrame)
        left_scroll.setWidget(self._build_left())
        splitter.addWidget(left_scroll)

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
        self._left_layout = layout   # kept for dynamic stretch adjustment — see _on_tab_switched_refresh

        grp = QGroupBox('MCR-ALS settings')
        gl = QVBoxLayout(grp)

        n_row = QHBoxLayout()
        n_row.addWidget(QLabel('Components:'))
        self._n_spin = QSpinBox()
        self._n_spin.setKeyboardTracking(False)
        self._n_spin.setRange(2, max(2, min(20, len(self.spectra))))
        self._n_spin.setValue(min(2, self._n_spin.maximum()))
        n_row.addWidget(self._n_spin)
        gl.addLayout(n_row)

        # Initialisation dropdown removed — 'random' used to be offered
        # here too, but selecting it and clicking the plain Run button was
        # exactly the "single random attempt" footgun explicitly warned
        # against (a lone random start is unreliable; only meaningful
        # through multiple restarts). Removing it left only one
        # deterministic choice ('svd'), making a dropdown pointless.
        # Run MCR-ALS always uses svd; "Run N times, keep best" (below) is
        # the dedicated, unconditionally-available path for random
        # restarts, decoupled from any dropdown state.

        iter_row = QHBoxLayout()
        iter_row.addWidget(QLabel('Max iterations:'))
        self._iter_spin = QSpinBox()
        self._iter_spin.setKeyboardTracking(False)
        self._iter_spin.setRange(10, 2000)
        self._iter_spin.setValue(100)
        iter_row.addWidget(self._iter_spin)
        gl.addLayout(iter_row)

        constraints_header = QHBoxLayout()
        constraints_header.addWidget(QLabel('Constraints:'))
        constraints_header.addStretch()
        constraints_header.addWidget(self._make_info_button(
            'About MCR-ALS Constraints',
            'Non-negativity is applied independently to the concentration '
            'profiles (C) and/or the pure spectra (ST) via NNLS at every '
            'iteration \u2014 turn either off if you specifically expect that '
            'factor to have genuinely negative values (e.g. CD spectra as a '
            'pure component). Turning both off reduces MCR-ALS to plain '
            'alternating least squares with no constraint at all.\n\n'
            'Behind the scenes, each component\u2019s ST row is also rescaled to '
            'unit norm every iteration, with the compensating scale factor '
            'pushed into C \u2014 this always happens automatically (not a '
            'user setting), since C @ ST is mathematically unaffected by '
            'C *= k, ST /= k for any k, and without pinning that down the '
            'two factors could drift to arbitrarily large or small scales '
            'over many iterations. It has no effect on the fit itself '
            '(same reconstruction either way), only on keeping the raw '
            'numbers well-behaved.'
        ))
        gl.addLayout(constraints_header)
        self._c_nonneg_cb = QCheckBox('Non-negative concentrations (C)')
        self._c_nonneg_cb.setChecked(True)
        gl.addWidget(self._c_nonneg_cb)
        self._st_nonneg_cb = QCheckBox('Non-negative spectra (ST)')
        self._st_nonneg_cb.setChecked(True)
        gl.addWidget(self._st_nonneg_cb)
        self._closure_cb = QCheckBox('Closure (concentrations sum to 100% per spectrum)')
        self._closure_cb.setChecked(False)
        self._closure_cb.setToolTip(
            'A genuine constraint applied DURING the fit \u2014 every spectrum\u2019s\n'
            'concentration row is forced to sum to 1 at every iteration, and\n'
            'the pure spectra adapt to that constraint through the fit itself,\n'
            'so the result is self-consistent (not just relabeled afterward).\n'
            'This is the only way to get directly, physically interpretable\n'
            'relative composition (e.g. "80% component 1, 15% component 2,\n'
            '5% component 3") without an external calibration standard \u2014 the\n'
            'raw, unconstrained scale of C has no physical meaning on its own.\n\n'
            'Off by default: this is a REAL constraint that changes what the\n'
            'fit can find, not a cosmetic option. If your system does not\n'
            'actually have closure (total concentration genuinely constant\n'
            'across your series), turning this on can make the TRUE solution\n'
            'mathematically unreachable, not just harder to find \u2014 confirmed\n'
            'directly: a benchmark whose true concentrations vary from 1.0 to\n'
            '~2.0 across the series never recovered the correct answer with\n'
            'closure on, in any of many random restarts, while routinely\n'
            'recovering it with closure off. Only turn this on if you have a\n'
            'specific, justified reason to believe total concentration is\n'
            'genuinely constant for your data.'
        )
        gl.addWidget(self._closure_cb)
        # "Normalize spectra each iteration" used to be a user-facing
        # checkbox here. Removed: it's purely internal numerical
        # bookkeeping (keeps C and ST from drifting to arbitrary scales
        # during iteration — see Help) with zero effect on the actual fit
        # (same reconstruction, same lack-of-fit either way), so exposing
        # it as a toggle implied a meaningful scientific choice that
        # doesn't actually exist. Always on now.

        self._spectra_offset_cb = QCheckBox('Offset components for clarity')
        self._spectra_offset_cb.setChecked(True)
        self._spectra_offset_cb.setToolTip(
            'Shifts each component vertically on the Pure Spectra tab so\n'
            'overlapping curves are readable. Turn off to compare component\n'
            'shapes/intensities directly on the same baseline.'
        )
        self._spectra_offset_cb.stateChanged.connect(self._refresh_spectra)
        gl.addWidget(self._spectra_offset_cb)

        self._spectra_normalize_cb = QCheckBox('Normalize each component to comparable scale')
        self._spectra_normalize_cb.setChecked(True)
        self._spectra_normalize_cb.setToolTip(
            'The raw absolute scale of ST is arbitrary and can differ a lot\n'
            'between components (see Help) \u2014 a weak/degenerate component can\n'
            'end up on a much larger or smaller raw scale than the others,\n'
            'which visually swamps or hides genuinely important components\n'
            'when they all share one y-axis. Checking this rescales each\n'
            'component to the same peak height before plotting, so shapes\n'
            'are comparable regardless of raw magnitude. Turn off to see the\n'
            'actual raw relative scale between components.'
        )
        self._spectra_normalize_cb.stateChanged.connect(self._refresh_spectra)
        gl.addWidget(self._spectra_normalize_cb)

        self.run_btn = QPushButton('\u25b6  Run MCR-ALS')
        self.run_btn.setStyleSheet(
            'QPushButton { background-color:#1976D2; color:white; '
            'font-weight:bold; padding:5px 16px; border-radius:4px; }'
            'QPushButton:hover { background-color:#1565C0; }'
        )
        self.run_btn.clicked.connect(self._run_mcr_als)
        gl.addWidget(self.run_btn)

        self._run_best_btn = QPushButton('Run N times, keep best\u2026')
        self._run_best_btn.setToolTip(
            'Runs several random-seed restarts and keeps whichever finds the\n'
            'lowest lack-of-fit \u2014 the recommended way to check whether a\n'
            'result is reliable (see the "X/N runs within 10% of best" report\n'
            'afterward) rather than trusting a single deterministic run alone.'
        )
        self._run_best_btn.clicked.connect(self._prompt_and_run_best_of_n)
        gl.addWidget(self._run_best_btn)

        # The warnings are valuable but were rendered as a large block of red
        # text that dominated the left panel and pushed the real controls out
        # of view. Collapsed to one compact button instead: it shows how many
        # warnings there are, and clicking it opens the full text in a dialog
        # (see _set_warning_text / _show_warning_details).
        self._neg_warn = QPushButton('')
        self._neg_warn.setStyleSheet(
            'text-align:left; background:#FFF8E1; color:#E65100; padding:6px; '
            'border:1px solid #FFCC80; border-radius:3px; font-size:8pt;')
        self._neg_warn.setToolTip('Click to see the full warning text.')
        self._neg_warn.clicked.connect(self._show_warning_details)
        self._neg_warn.setVisible(False)
        gl.addWidget(self._neg_warn)

        self._status_label = QLabel('')
        self._status_label.setStyleSheet('font-size:8pt; color:#555;')
        self._status_label.setWordWrap(True)
        gl.addWidget(self._status_label)
        layout.addWidget(grp)

        # Shorten Names — governs spectrum-label display across every tab
        # that shows one (Concentrations x-axis, Reconstruction spectrum
        # list/title, Fit Quality bar chart). Deliberately placed here,
        # OUTSIDE the three tab-conditional groups below (_rc_grp/_conc_grp/
        # _fitq_grp, each shown only while its own tab is active) — it used
        # to live inside _conc_grp, which meant it was invisible (and
        # un-toggleable) whenever you were looking at Reconstruction or Fit
        # Quality, despite already affecting both of those tabs. A single
        # checkbox with dialog-wide effect needs to stay reachable no matter
        # which tab you're on.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._refresh_concentrations)
        self.checkBox_shorten_names.stateChanged.connect(self._rebuild_recon_list)
        self.checkBox_shorten_names.stateChanged.connect(self._refresh_reconstruction)
        self.checkBox_shorten_names.stateChanged.connect(self._refresh_fit_quality)
        layout.addWidget(self.checkBox_shorten_names)

        layout.addWidget(self._build_reference_group())

        # Spectrum selector for the Reconstruction tab — without this, the
        # Reconstruction tab always showed spectrum 0 with no way to look
        # at any other spectrum's fit.
        self._rc_grp = rc_grp = QGroupBox('Reconstruction preview')
        rl = QVBoxLayout(rc_grp)
        rl.addWidget(QLabel('Select spectrum:'))
        self._recon_list = QListWidget()
        for s in self.spectra:
            item = QListWidgetItem(s['label'])
            item.setData(Qt.UserRole, s['label'])
            self._recon_list.addItem(item)
        if self.spectra:
            self._recon_list.setCurrentRow(0)
        self._recon_list.currentRowChanged.connect(self._refresh_reconstruction)
        rl.addWidget(self._recon_list, 1)
        self._recon_curves_only_cb = QCheckBox('Show only Original + Reconstructed')
        self._recon_curves_only_cb.setChecked(False)
        self._recon_curves_only_cb.setToolTip(
            'When checked, the Reconstruction tab shows only the black Original\n'
            'and the red dashed Reconstructed curve — hiding the coloured\n'
            'per-component contribution bands and the residual shading. Useful\n'
            'for a clean overlay of how well the model matches the data,\n'
            'without the stacked component fills.')
        self._recon_curves_only_cb.stateChanged.connect(self._refresh_reconstruction)
        rl.addWidget(self._recon_curves_only_cb)
        layout.addWidget(rc_grp, 1)

        # Concentrations tab display options — same pattern (and same
        # widget behavior) as cluster_analysis_dialog's dendrogram options.
        self._conc_grp = conc_grp = QGroupBox('Concentrations display')
        cl2 = QVBoxLayout(conc_grp)

        view_row = QHBoxLayout()
        view_row.addWidget(QLabel('Show:'))
        self._conc_view_combo = QComboBox()
        self._conc_view_combo.addItems(['Plot', 'Table'])
        self._conc_view_combo.setToolTip(
            'Plot: the concentration profiles as curves/bars.\n'
            'Table: exactly the same numbers in a readable grid — reading\n'
            'precise values off a chart is fiddly, so the table gives you the\n'
            'per-spectrum, per-component values directly (and honours the\n'
            '"Normalize to 100% per spectrum" option below, so you can read\n'
            'the interpretable percentages straight off).')
        self._conc_view_combo.currentTextChanged.connect(self._refresh_concentrations)
        view_row.addWidget(self._conc_view_combo, 1)
        cl2.addLayout(view_row)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel('Plot type:'))
        self._conc_plot_type_combo = QComboBox()
        self._conc_plot_type_combo.addItems(['Grouped bars', 'Stacked bars', 'Lines'])
        self._conc_plot_type_combo.setCurrentText('Lines')
        self._conc_plot_type_combo.setToolTip(
            'Grouped bars: one bar per component per spectrum, side\n'
            'by side. Stacked bars: each spectrum\u2019s bars stacked into one,\n'
            'total height = sum of all components. Lines: one line per\n'
            'component across spectrum index \u2014 far more readable than bars\n'
            'once you have more than ~30-40 spectra (Lines is the default here).'
        )
        self._conc_plot_type_combo.currentTextChanged.connect(self._refresh_concentrations)
        type_row.addWidget(self._conc_plot_type_combo)
        cl2.addLayout(type_row)

        self._conc_normalize_cb = QCheckBox('Normalize to 100% per spectrum')
        self._conc_normalize_cb.setChecked(True)
        self._conc_normalize_cb.setToolTip(
            'If "Closure" is enabled in the settings above, C already sums\n'
            'to 100% per spectrum as a genuine result of the fit itself \u2014\n'
            'this checkbox is then a no-op (dividing by 1 changes nothing).\n\n'
            'If Closure is OFF, the raw concentration scale is arbitrary \u2014\n'
            'C @ ST is unchanged by multiplying a component\u2019s concentration\n'
            'by k and dividing its spectrum by the same k. Checking this\n'
            'rescales each spectrum\u2019s row of C to sum to 100% for DISPLAY\n'
            'only (e.g. "80% component 1, 15% component 2, 5% component 3") \u2014\n'
            'note this does NOT correspond to a self-consistent fit the way\n'
            'true Closure does; it does not change the underlying fit or\n'
            'what gets saved/exported.'
        )
        self._conc_normalize_cb.stateChanged.connect(self._refresh_concentrations)
        cl2.addWidget(self._conc_normalize_cb)

        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel('Label rotation:'))
        self._conc_rotation_combo = QComboBox()
        self._conc_rotation_combo.addItems(['90°', '45°', '0°'])
        self._conc_rotation_combo.setCurrentText('45°')
        self._conc_rotation_combo.setFixedWidth(60)
        self._conc_rotation_combo.currentTextChanged.connect(self._refresh_concentrations)
        rot_row.addWidget(self._conc_rotation_combo)
        rot_row.addStretch()
        cl2.addLayout(rot_row)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel('Label font size:'))
        self._conc_fontsize_combo = QComboBox()
        self._conc_fontsize_combo.addItems(['Auto', '3', '5', '7', '9', '11', '14'])
        self._conc_fontsize_combo.setCurrentText('Auto')
        self._conc_fontsize_combo.setFixedWidth(70)
        self._conc_fontsize_combo.setToolTip(
            'Auto shrinks labels as the number of spectra grows, so they\n'
            'stay legible without the plot becoming unreasonably wide.\n'
            'Choose an explicit size to override that.'
        )
        self._conc_fontsize_combo.currentTextChanged.connect(self._refresh_concentrations)
        font_row.addWidget(self._conc_fontsize_combo)
        font_row.addStretch()
        cl2.addLayout(font_row)


        trunc_row = QHBoxLayout()
        trunc_row.setContentsMargins(0, 0, 0, 0)
        trunc_row.setSpacing(4)
        self._conc_trunc_combo = QComboBox()
        self._conc_trunc_combo.addItems(['Full label', 'First N chars', 'Last N chars'])
        self._conc_trunc_combo.setCurrentText('Last N chars')
        self._conc_trunc_combo.setToolTip('How to display labels when they are too long')
        self._conc_trunc_combo.setFixedWidth(110)
        trunc_row.addWidget(self._conc_trunc_combo)
        n_label = QLabel('N:')
        n_label.setFixedWidth(20)
        trunc_row.addWidget(n_label)
        self._conc_trunc_n_spin = QSpinBox()
        self._conc_trunc_n_spin.setMinimum(1)
        self._conc_trunc_n_spin.setMaximum(200)
        self._conc_trunc_n_spin.setValue(25)
        self._conc_trunc_n_spin.setFixedWidth(55)
        self._conc_trunc_n_spin.setToolTip('Number of characters (N) to keep from each label')
        self._conc_trunc_n_spin.setKeyboardTracking(False)
        trunc_row.addWidget(self._conc_trunc_n_spin)
        trunc_row.addStretch()
        cl2.addLayout(trunc_row)

        def _on_conc_trunc_changed():
            is_n_mode = self._conc_trunc_combo.currentText() != 'Full label'
            self._conc_trunc_n_spin.setEnabled(is_n_mode and not self._conc_use_index_cb.isChecked())
            self._refresh_concentrations()

        self._conc_trunc_combo.currentTextChanged.connect(_on_conc_trunc_changed)
        self._conc_trunc_n_spin.valueChanged.connect(self._refresh_concentrations)

        self._conc_use_index_cb = QCheckBox('Use spectrum index (1, 2, 3, ...) instead of labels')
        self._conc_use_index_cb.setChecked(False)
        self._conc_use_index_cb.setToolTip(
            'Show plain position numbers (1, 2, 3, ...) on the axis/table\n'
            'instead of spectrum labels — handy when labels are long or not\n'
            'meaningful for this view. Truncation below is disabled while\n'
            'this is checked, since there\u2019s nothing left to truncate.')

        def _on_conc_use_index_changed():
            use_index = self._conc_use_index_cb.isChecked()
            self._conc_trunc_combo.setEnabled(not use_index)
            is_n_mode = self._conc_trunc_combo.currentText() != 'Full label'
            self._conc_trunc_n_spin.setEnabled(not use_index and is_n_mode)
            self._refresh_concentrations()

        self._conc_use_index_cb.stateChanged.connect(_on_conc_use_index_changed)
        cl2.addWidget(self._conc_use_index_cb)

        layout.addWidget(conc_grp)

        self._fitq_grp = fitq_grp = QGroupBox('Fit Quality / Elbow display')
        fitq_layout = QVBoxLayout(fitq_grp)
        fitq_layout.addWidget(QLabel('Show:'))
        self._fitq_mode_combo = QComboBox()
        self._fitq_mode_combo.addItems([
            'Per spectrum (current run)',
            'Elbow: lack of fit vs component count',
            'Median residual vs component count',
        ])
        self._fitq_mode_combo.setToolTip(
            'Per spectrum: for the run you just computed, shows every\n'
            'spectrum\u2019s own error size, as a % of that spectrum\u2019s own total\n'
            'signal ("relative" = relative to that spectrum\u2019s own scale, so\n'
            'faint and bright spectra are compared fairly).\n\n'
            'Elbow: re-runs at every component count from 2 up to "Max\n'
            'components to test" and plots the aggregate lack-of-fit (%).\n'
            'Look for the "elbow" where adding components stops helping.\n\n'
            'Median residual vs component count: same sweep, but tracks the\n'
            'MIDDLE (median) of the per-spectrum error percentages instead\n'
            'of the aggregate lack-of-fit. The two "vs component count"\n'
            'views can legitimately disagree \u2014 see Help for what that means.'
        )
        self._fitq_mode_combo.currentTextChanged.connect(self._on_fitq_mode_changed)
        fitq_layout.addWidget(self._fitq_mode_combo)

        self._elbow_max_row_w = QWidget()
        elbow_max_row = QHBoxLayout(self._elbow_max_row_w)
        elbow_max_row.setContentsMargins(0, 0, 0, 0)
        elbow_max_row.addWidget(QLabel('Max components to test:'))
        self._elbow_max_spin = QSpinBox()
        self._elbow_max_spin.setKeyboardTracking(False)
        self._elbow_max_spin.setRange(3, max(3, min(30, len(self.spectra) - 1)))
        self._elbow_max_spin.setValue(min(10, self._elbow_max_spin.maximum()))
        self._elbow_max_spin.setToolTip(
            'Both "vs component count" views (Elbow and Median residual)\n'
            'test every component count from 2 up to this number \u2014 independent\n'
            'of the main "Components" setting above, which only controls what a\n'
            'normal Run actually uses. (Ignored by the "Per spectrum" view.)'
        )
        self._elbow_max_spin.valueChanged.connect(self._on_elbow_max_changed)
        elbow_max_row.addWidget(self._elbow_max_spin)
        fitq_layout.addWidget(self._elbow_max_row_w)

        self._sweep_runs_row_w = QWidget()
        sweep_runs_row = QHBoxLayout(self._sweep_runs_row_w)
        sweep_runs_row.setContentsMargins(0, 0, 0, 0)
        sweep_runs_row.addWidget(QLabel('Restarts per component count:'))
        self._sweep_runs_spin = QSpinBox()
        # Without this, QSpinBox emits valueChanged on EVERY keystroke: typing
        # "11" fires at "1" first, kicking off a full (slow) recomputation
        # before you have finished typing. keyboardTracking(False) makes it emit
        # only when editing is actually finished (Enter / focus lost) or when the
        # up/down arrows are used.
        self._sweep_runs_spin.setKeyboardTracking(False)
        self._sweep_runs_spin.setRange(1, 100)
        self._sweep_runs_spin.setValue(5)
        self._sweep_runs_spin.setToolTip(
            'How hard the two "vs component count" views try at EACH component\n'
            'count.\n\n'
            '1  = a single run per count (fastest).\n'
            '5  = five random restarts per count, keeping the best (default).\n\n'
            'This is deliberately SEPARATE from the "Run N times, keep best"\n'
            'count. These plots exist to help you pick the number of components,\n'
            'and a handful of restarts is ample for that — whereas mirroring a\n'
            '100-restart run at every count means ~900 fits, which takes minutes.\n'
            'Raise it if the curve looks unstable; lower it to 1 if you just want\n'
            'a quick look.')
        self._sweep_runs_spin.valueChanged.connect(self._on_sweep_runs_changed)
        sweep_runs_row.addWidget(self._sweep_runs_spin)
        fitq_layout.addWidget(self._sweep_runs_row_w)
        self._sync_elbow_max_enabled()

        layout.addWidget(fitq_grp)

        layout.addStretch(1)
        self._terminal_stretch_index = layout.count() - 1

        save_row = QHBoxLayout()
        send_to_main_btn = QPushButton('Send to main list\u2026')
        send_to_main_btn.setToolTip(
            'Add the resolved pure-component spectra (ST) as new spectra in\n'
            'the main spectrum list — the same idea as Peak Fitting\u2019s\n'
            '"Add new spectra from individual peaks".'
        )
        send_to_main_btn.clicked.connect(self._show_export_components_dialog)
        save_row.addWidget(send_to_main_btn)

        export_btn = QPushButton('Save…')
        export_btn.clicked.connect(self._show_save_dialog)
        save_row.addWidget(export_btn)
        layout.addLayout(save_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        help_btn = QPushButton('Help')
        help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(help_btn)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        return w

    def _make_info_button(self, title, text):
        """Small orange '?' button — same style used throughout the rest
        of the app (e.g. the main window's Legend '?')."""
        btn = QPushButton('?')
        btn.setFixedSize(28, 28)
        btn.setStyleSheet(
            'QPushButton { background-color:#F57C00; color:white; '
            'font-weight:bold; font-size:11pt; border:none; border-radius:4px; }'
            'QPushButton:hover { background-color:#EF6C00; }'
        )
        btn.setToolTip('About this section')
        btn.clicked.connect(lambda: QMessageBox.information(self, title, text))
        return btn

    def _build_right(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tabs = QTabWidget()
        self._tabs.tabBar().setExpanding(False)
        self._tabs.setStyleSheet(
            "QTabBar::tab { min-width: 110px; padding: 4px 12px; }"
        )
        self._tab_canvases = []

        for title, attr in [
            ('Pure Spectra',    '_spectra_canvas'),
            ('Concentrations',  '_conc_canvas'),
            ('Reconstruction',  '_recon_canvas'),
            ('Fit Quality',     '_fitq_canvas'),
        ]:
            pw = QWidget()
            pl = QVBoxLayout(pw)
            pl.setContentsMargins(0, 0, 0, 0)
            canvas = _PlotCanvas(pw)
            setattr(self, attr, canvas)
            pl.addWidget(NavigationToolbar(canvas, pw))
            pl.addWidget(canvas)
            if title == 'Concentrations':
                # This tab can show either the plot or a readable table of
                # the same numbers (reading exact values off a chart is
                # fiddly) — a QStackedWidget holds both; the "Show:" combo
                # in the Concentrations display group switches between them.
                from PyQt5.QtWidgets import QStackedWidget, QTableWidget
                self._conc_stack = QStackedWidget()
                self._conc_stack.addWidget(pw)               # page 0: plot
                self._conc_table = QTableWidget()
                self._conc_table.setAlternatingRowColors(True)
                self._conc_stack.addWidget(self._conc_table)  # page 1: table
                self._tabs.addTab(self._conc_stack, title)
            else:
                self._tabs.addTab(pw, title)
            self._tab_canvases.append(canvas)
        # The Elbow view now lives inside the Fit Quality tab (selected via
        # the "Show:" dropdown), so it shares that tab's single canvas
        # instead of having its own tab. _refresh_elbow() draws here.
        self._elbow_canvas = self._fitq_canvas

        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.currentChanged.connect(self._on_tab_switched_refresh)
        layout.addWidget(self._tabs)
        return w

    def _on_tab_changed(self, index):
        if 0 <= index < len(self._tab_canvases):
            self._tab_canvases[index].draw_tight()

    def _on_tab_switched_refresh(self, index):
        tab = self._tabs.tabText(index)
        self._rc_grp.setVisible(tab == 'Reconstruction')
        self._conc_grp.setVisible(tab == 'Concentrations')
        self._fitq_grp.setVisible(tab == 'Fit Quality')
        # Give ALL extra vertical space to the Reconstruction spectrum
        # list when it's the visible tab (a long spectrum list benefits
        # from the room); otherwise send it to the dead space just above
        # Send/Save instead, so every other settings group stays compact.
        # Only one of these two should ever be non-zero at a time — if
        # both were non-zero simultaneously, Qt would split the extra
        # space between them rather than giving it all to the listbox.
        rc_idx = self._left_layout.indexOf(self._rc_grp)
        is_recon = (tab == 'Reconstruction')
        self._left_layout.setStretch(rc_idx, 1 if is_recon else 0)
        self._left_layout.setStretch(self._terminal_stretch_index, 0 if is_recon else 1)
        if tab == 'Fit Quality':
            self._refresh_fit_quality()

    def _on_fitq_mode_changed(self, *_):
        self._sync_elbow_max_enabled()
        self._refresh_fit_quality()

    def _on_sweep_runs_changed(self, *_):
        """Changing how hard the sweeps try invalidates their cached curves."""
        self._elbow_cache_key = None
        self._fitq_cache_key = None
        tab = self._tabs.tabText(self._tabs.currentIndex())
        if tab == 'Fit Quality' and not self._fitq_mode_combo.currentText().startswith('Per spectrum'):
            self._refresh_fit_quality()

    def _sync_elbow_max_enabled(self):
        """'Max components to test' only affects the two 'vs component
        count' views, so grey it out for the per-spectrum view rather than
        leaving a control that silently does nothing."""
        per_spectrum = self._fitq_mode_combo.currentText().startswith('Per spectrum')
        self._elbow_max_row_w.setEnabled(not per_spectrum)
        self._sweep_runs_row_w.setEnabled(not per_spectrum)

    def _on_elbow_max_changed(self, *_):
        """The cache keys for both the Elbow and the Median-residual trend
        already include this value, so they'll recompute correctly next
        time either is viewed regardless — this just refreshes immediately
        if you're already looking at one of them right now."""
        tab = self._tabs.tabText(self._tabs.currentIndex())
        if tab == 'Fit Quality' and not self._fitq_mode_combo.currentText().startswith('Per spectrum'):
            self._refresh_fit_quality()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        from PyQt5.QtCore import QTimer
        if not hasattr(self, '_resize_redraw_timer'):
            self._resize_redraw_timer = QTimer(self)
            self._resize_redraw_timer.setSingleShot(True)
            self._resize_redraw_timer.timeout.connect(self._redraw_current_tab)
        self._resize_redraw_timer.start(150)

    def _redraw_current_tab(self):
        idx = self._tabs.currentIndex()
        if 0 <= idx < len(self._tab_canvases):
            self._tab_canvases[idx].draw_tight()

    # ------------------------------------------------------------------ #
    # Ground-truth comparison (hidden/testing-only — right-click anywhere) #
    # ------------------------------------------------------------------ #
    # For validating/teaching this tool against the shipped synthetic
    # benchmark datasets, which come with known-TRUE pure components and
    # concentrations — never relevant for real data (real spectra have no
    # known-true decomposition to check against), which is why this isn't a
    # button on the Settings panel. See mcr_als_help.py's "Testing against
    # known ground truth" section. Mirrors nmf_dialog.py's identical
    # feature — see that file for more detailed comments.

    def _show_gt_context_menu(self, pos):
        menu = QMenu(self)
        if self._gt is not None:
            label_action = QAction(f'Ground truth: {self._gt.filename}', self)
            label_action.setEnabled(False)
            menu.addAction(label_action)
            menu.addSeparator()
            change_action = QAction('Change ground-truth dataset…', self)
            change_action.triggered.connect(self._pick_ground_truth_dataset)
            menu.addAction(change_action)
            clear_action = QAction('Clear ground-truth comparison', self)
            clear_action.triggered.connect(self._clear_ground_truth)
            menu.addAction(clear_action)
        else:
            compare_action = QAction('Compare with ground truth (testing)…', self)
            compare_action.triggered.connect(self._pick_ground_truth_dataset)
            menu.addAction(compare_action)
        menu.exec_(self.mapToGlobal(pos))

    def _pick_ground_truth_dataset(self):
        filepath = pick_ground_truth_dataset(self)
        if not filepath:
            return
        try:
            truth = gtc.load_ground_truth(filepath)
        except Exception as e:
            logger.exception('Failed to load ground-truth dataset: %s', filepath)
            QMessageBox.critical(
                self, 'Could not load ground truth',
                f"Couldn't read pure components/concentrations from "
                f"this file:\n\n{e}")
            return
        self._gt = truth
        self._ensure_gt_tab()
        self._refresh_all_after_gt_change()

    def _clear_ground_truth(self):
        self._gt = None
        self._remove_gt_tab()
        self._refresh_all_after_gt_change()

    def _refresh_all_after_gt_change(self):
        """Redraw every tab that has a ground-truth overlay, plus the
        report tab if one is showing. Cheap even for a from-scratch match
        (components/spectra here are small — tens of points, not millions),
        so recomputing on every redraw instead of caching+invalidating is
        the simpler, harder-to-get-wrong choice."""
        self._refresh_spectra()
        self._refresh_concentrations()
        self._refresh_reconstruction()
        self._refresh_gt_report_tab()

    def _ensure_gt_tab(self):
        if getattr(self, '_gt_tab_widget', None) is not None:
            return
        pw = QWidget()
        pl = QVBoxLayout(pw)
        summary = QLabel('')
        summary.setWordWrap(True)
        summary.setStyleSheet('padding: 4px;')
        pl.addWidget(summary)
        table = QTableWidget()
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        pl.addWidget(table)
        self._gt_tab_widget = pw
        self._gt_summary_label = summary
        self._gt_report_table = table
        self._tabs.addTab(pw, 'Ground Truth')
        self._tabs.setCurrentWidget(pw)

    def _remove_gt_tab(self):
        if getattr(self, '_gt_tab_widget', None) is None:
            return
        idx = self._tabs.indexOf(self._gt_tab_widget)
        if idx >= 0:
            self._tabs.removeTab(idx)
        self._gt_tab_widget = None
        self._gt_summary_label = None
        self._gt_report_table = None

    def _gt_current_report(self):
        """The ground-truth recovery report for the CURRENT fit, or None if
        there's no ground truth loaded / nothing has been run yet."""
        if self._gt is None or self._mgr is None or self._mgr.ST is None:
            return None
        try:
            return gtc.build_recovery_report(
                self._mgr.ST, self._mgr.x_axis, self._mgr.C,
                [s['label'] for s in self._fit_spectra()], self._gt)
        except Exception:
            logger.exception('Ground-truth recovery report failed')
            return None

    def _refresh_gt_report_tab(self):
        if getattr(self, '_gt_report_table', None) is None:
            return
        report = self._gt_current_report()
        table = self._gt_report_table
        if report is None:
            table.clear()
            table.setRowCount(0)
            table.setColumnCount(0)
            self._gt_summary_label.setText(
                'No result to compare yet — run MCR-ALS first.'
                if self._gt is not None else '')
            return

        rows = report['rows']
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            ['Fitted component', 'Best-matching TRUE component',
             'Spectral similarity', 'Concentration r', 'Concentration RMSE (%)'])
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(f'MCR {row["fitted_index"] + 1}'))
            truth_txt = row['truth_label'] if row['truth_label'] is not None else '(unmatched)'
            table.setItem(i, 1, QTableWidgetItem(truth_txt))
            table.setItem(i, 2, QTableWidgetItem(f'{row["spectral_similarity"]:.3f}'))
            r = row['conc_correlation']
            table.setItem(i, 3, QTableWidgetItem('-' if np.isnan(r) else f'{r:.3f}'))
            rmse = row['conc_rmse_pct']
            table.setItem(i, 4, QTableWidgetItem('-' if np.isnan(rmse) else f'{rmse:.2f}'))
        table.resizeColumnsToContents()

        lof_txt = f'{self._mgr.lof:.3g}%' if self._mgr is not None else 'n/a'
        summary_lines = [
            f"<b>Source:</b> {report['source_filename']}",
            f"<b>Overall recovery score</b> (mean matched spectral similarity): "
            f"{report['mean_spectral_similarity']:.3f} — 1.0 is a perfect "
            f"match to the true components.",
            f"<b>Current run's lack of fit</b> (fit-to-DATA, from the status "
            f"line): {lof_txt} — this is a different measurement from "
            f"the recovery score above and the two can legitimately "
            f"disagree: a low lack-of-fit does NOT guarantee a high "
            f"recovery score. That gap is the whole point of this tool "
            f"(see the Help page's “Read this first” section).",
            f"<b>Concentration r vs. RMSE</b> — these measure two different "
            f"things and can disagree with each other too. r (correlation) "
            f"is scale/offset-independent: it only checks whether the "
            f"fitted and TRUE profiles rise and fall together across your "
            f"spectra, so it stays high even if the fitted values are "
            f"shifted or rescaled from the truth (or, in a closed system, "
            f"even for a poorly-separated component whose profile happens "
            f"to still trend opposite the other component, as it must). "
            f"RMSE is the actual point-by-point disagreement in percentage "
            f"points, after both are normalised to 100% per spectrum — a "
            f"high r together with a high RMSE means \"right trend, wrong "
            f"absolute split\", which is the concentration-side symptom of "
            f"the same non-uniqueness problem discussed above and in the "
            f"Help page.",
        ]
        if report['n_conc_rows_matched'] < report['n_conc_rows_total']:
            summary_lines.append(
                f"<b>Warning:</b> only {report['n_conc_rows_matched']} of "
                f"{report['n_conc_rows_total']} fitted spectra have a "
                f"matching label in this ground-truth file's Concentrations "
                f"sheet — concentration columns above may be based on "
                f"very few points, or show ‘-’ entirely. This "
                f"usually means the wrong benchmark file was picked for "
                f"your current spectra selection.")
        self._gt_summary_label.setText('<br>'.join(summary_lines))

    def _draw_gt_overlay_components(self, ax, x, offset_step, use_normalize):
        """Dashed ground-truth pure-component curves on the Pure Spectra
        tab, colour-matched to their best-matching fitted component so a
        component and its ground-truth partner are visually paired. Drawn
        with the same normalisation/offset treatment as the fitted curves
        so the two are directly comparable at a glance.

        A good MCR-ALS/NMF run can recover a component almost exactly, which
        means this dashed curve can sit nearly on top of the solid fitted
        curve underneath it — and a dashed line drawn in the SAME colour as
        an identically-shaped solid line right behind it is invisible: the
        solid colour simply fills in every gap in the dash pattern. A thin
        white halo (path_effects.Stroke) around the dashed line breaks that
        up by punching a light-coloured outline through the solid line
        wherever the dash is drawn, so the dash pattern stays visible even
        when the two curves coincide almost exactly. Sparse open-circle
        markers (white fill, coloured edge) are added on top for the same
        reason as the Concentrations tab's 'x' markers: with several sharp,
        criss-crossing bands (typical of Raman/ROA-type spectra) a dash
        pattern alone can still be hard to trace by eye against a
        same-coloured solid curve that crosses it repeatedly — a handful of
        unmistakably GT-only markers give the eye fixed points to follow the
        curve from, independent of how much dashing happens to be visible
        at any one spot."""
        report = self._gt_current_report()
        if report is None:
            return
        truth_on_x = gtc.interpolate_truth_components(x, self._gt)
        n_pts = len(x)
        markevery = max(1, n_pts // 16)
        for row in report['rows']:
            truth_idx = row['truth_index']
            if truth_idx is None:
                continue
            k = row['fitted_index']
            curve = truth_on_x[truth_idx]
            if use_normalize:
                peak = np.max(np.abs(curve))
                curve = curve / peak if peak > 0 else curve
            color = _COLORS[k % len(_COLORS)]
            line, = ax.plot(
                x, curve + k * offset_step, color=color, lw=1.6, ls=(0, (4, 2.5)),
                alpha=0.95, zorder=5, solid_capstyle='butt',
                marker='o', markevery=markevery, ms=5.5,
                markerfacecolor='white', markeredgecolor=color, markeredgewidth=1.3,
                label=f'GT: {row["truth_label"]}  (sim={row["spectral_similarity"]:.2f})')
            line.set_path_effects([
                mpl_path_effects.Stroke(linewidth=3.2, foreground='white'),
                mpl_path_effects.Normal(),
            ])

    def _draw_gt_overlay_scores(self, ax, x_positions):
        """Ground-truth concentration profiles on the Concentrations tab —
        same colour as the matched fitted component, dotted line with an
        'x' marker so it reads clearly against Lines, Stacked bars, or
        Grouped bars alike regardless of which plot type is selected."""
        report = self._gt_current_report()
        if report is None:
            return
        fitted_labels = [s['label'] for s in self._fit_spectra()]
        row_for_fitted, _ = gtc.align_concentration_rows(fitted_labels, self._gt)
        truth_conc = self._gt.concentrations
        if self._conc_normalize_cb.isChecked():
            truth_conc = gtc.normalize_rows_to_100(truth_conc)
        for row in report['rows']:
            truth_idx = row['truth_index']
            if truth_idx is None:
                continue
            k = row['fitted_index']
            y = np.full(len(fitted_labels), np.nan)
            for i, r in enumerate(row_for_fitted):
                if r is not None:
                    y[i] = truth_conc[r, truth_idx]
            color = _COLORS[k % len(_COLORS)]
            ax.plot(x_positions, y, color=color, ls=':', marker='x', ms=5, lw=1.3,
                    alpha=0.9, label=f'GT: {row["truth_label"]}')

    def _draw_gt_overlay_reconstruction(self, ax, x, spectrum_label):
        """The TRUE, noise-free generative curve for the spectrum currently
        shown on the Reconstruction tab (ground truth's concentrations for
        this exact spectrum, dotted with its own pure components) — a
        genuinely different comparison from Original/Reconstructed: it
        shows how close your fit gets to the real underlying signal, not
        just to the (possibly noisy) measurement.

        On a CLEAN benchmark dataset (no noise added), this TRUE curve is
        numerically almost identical to the "Original" measurement — which
        can make a lower-zorder line invisible underneath an opaque one
        drawn later. Drawn at a high zorder (6, above the residual hatch
        and component-contribution fills) plus a white halo, this dotted
        curve stays visible even when it sits exactly on top of Original —
        which is itself useful information (it tells you the "clean"
        dataset really is clean)."""
        if self._gt is None:
            return
        row_for_fitted, _ = gtc.align_concentration_rows([spectrum_label], self._gt)
        truth_idx = row_for_fitted[0]
        if truth_idx is None:
            return
        truth_on_x = gtc.interpolate_truth_components(x, self._gt)
        y_true = self._gt.concentrations[truth_idx] @ truth_on_x
        line, = ax.plot(x, y_true, color='#2E7D32', lw=1.4, ls=(0, (3, 2)),
                         alpha=0.95, label='TRUE (noise-free)', zorder=6)
        line.set_path_effects([
            mpl_path_effects.Stroke(linewidth=3.0, foreground='white'),
            mpl_path_effects.Normal(),
        ])

    # ------------------------------------------------------------------ #
    # Computation                                                          #
    # ------------------------------------------------------------------ #


    def _restore_saved_references(self):
        """Re-apply the saved reference-anchoring choices, once the pickers
        exist and have been rebuilt to the restored component count. A saved
        label is applied ONLY if a spectrum with that label is present in the
        current selection — otherwise it is silently skipped, so reopening the
        dialog on a different dataset can't attach a stale reference to the
        wrong spectrum. Also resyncs the Reconstruction list, since external
        references change which spectra are actually fitted."""
        s = self._settings or {}
        if not s:
            return
        try:
            by_label = {sp.get('label') for sp in self.spectra}
            id_to_label = {}
            for sp in self.spectra:
                uid = (sp.get('metadata') or {}).get('unique_id')
                if uid:
                    id_to_label[uid] = sp.get('label')
            labels = s.get('ref_labels') or []
            ids = s.get('ref_ids') or []
            for k, combo in enumerate(self._ref_combos):
                lbl = labels[k] if k < len(labels) else ''
                uid = ids[k] if k < len(ids) else ''
                target = None
                if uid and uid in id_to_label:
                    # Same spectrum, even if it has since been renamed.
                    target = id_to_label[uid]
                elif uid:
                    # We know which spectrum this was, and it is NOT here any
                    # more. Do NOT fall back to the label: a different spectrum
                    # may have been imported under the same name, and silently
                    # anchoring to it would be far worse than simply forgetting
                    # the reference.
                    target = None
                elif lbl and lbl != '(none)' and lbl in by_label:
                    # No id was stored (older saved settings) — label match is
                    # the best we can do.
                    target = lbl
                if target:
                    combo.blockSignals(True)
                    combo.setCurrentText(target)
                    combo.blockSignals(False)
            if 'ref_fixed' in s:
                self._ref_fix_cb.setChecked(bool(s['ref_fixed']))
            if 'ref_external' in s:
                self._ref_external_cb.setChecked(bool(s['ref_external']))
            if 'ref_enabled' in s:
                self._ref_grp.setChecked(bool(s['ref_enabled']))
            self._rebuild_recon_list()
        except (TypeError, ValueError, AttributeError):
            pass

    def _apply_saved_settings(self):
        """Restore the controls to the last-used settings for this dialog,
        if the app passed any in (current_settings). Every field is
        optional and clamped to its control's own valid range, so an
        empty or partial saved dict simply leaves the defaults in place
        and a stale/out-of-range value can never crash the dialog. This
        is what makes the current_settings the controller fetches from
        last_op_settings actually take effect — previously it was stored
        and never read."""
        s = self._settings
        if not s:
            return
        try:
            if 'n_components' in s:
                v = int(s['n_components'])
                self._n_spin.setValue(max(self._n_spin.minimum(),
                                          min(self._n_spin.maximum(), v)))
            if 'max_iterations' in s:
                v = int(s['max_iterations'])
                self._iter_spin.setValue(max(self._iter_spin.minimum(),
                                             min(self._iter_spin.maximum(), v)))
            if 'c_nonneg' in s:
                self._c_nonneg_cb.setChecked(bool(s['c_nonneg']))
            if 'st_nonneg' in s:
                self._st_nonneg_cb.setChecked(bool(s['st_nonneg']))
            if 'closure' in s:
                self._closure_cb.setChecked(bool(s['closure']))
        except (TypeError, ValueError):
            pass   # a malformed saved value just falls back to the defaults

    def _build_reference_group(self):
        """Optional reference-anchoring: assign a known pure spectrum (from
        the spectra you selected) to one or more component slots, and
        optionally hold them fixed. Anchoring to what you already know is
        the single most effective way to break MCR's rotational ambiguity —
        the resolved components stop drifting to arbitrary rotations."""
        self._ref_grp = grp = QGroupBox('Reference spectra (optional)')
        grp.setCheckable(True)
        grp.setChecked(False)
        grp.setToolTip(
            'Anchor component slots to KNOWN pure spectra. Pick, for a\n'
            'component, one of the spectra you selected for this analysis\n'
            '(load your pure reference into the app and include it in the\n'
            'selection). This is the most powerful way to remove the\n'
            'rotational ambiguity — the resolved components stop drifting\n'
            'to arbitrary equally-good-fitting rotations. Most effective\n'
            'for non-negative data; for signed (CD) data use it together\n'
            'with "Run N times, keep best".')
        v = QVBoxLayout(grp)
        self._ref_rows_container = QWidget()
        self._ref_rows_layout = QVBoxLayout(self._ref_rows_container)
        self._ref_rows_layout.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self._ref_rows_container)
        self._ref_combos = []
        self._ref_fix_cb = QCheckBox('Hold references fixed (else use only as starting guess)')
        self._ref_fix_cb.setChecked(True)
        self._ref_fix_cb.setToolTip(
            'Fixed: the referenced component is held exactly equal to the\n'
            'known spectrum throughout the fit (strongest anchoring).\n'
            'Unfixed: the reference is only the starting guess and is then\n'
            'free to adapt (gentler — useful if your reference is close but\n'
            'not identical to the true component).')
        v.addWidget(self._ref_fix_cb)
        self._ref_external_cb = QCheckBox('References are external (exclude them from the fitted data)')
        self._ref_external_cb.setChecked(True)
        self._ref_external_cb.setToolTip(
            'A reference is picked from the spectra you selected, so by default\n'
            'that pure spectrum would ALSO be treated as one of the mixtures to\n'
            'be fitted — which is usually not what you want: a previously-measured\n'
            'pure standard is not part of your experimental series, and including\n'
            'it changes the data being decomposed (and hence the result).\n\n'
            'Ticked (default): the chosen reference spectra are used ONLY as known\n'
            'component shapes and are REMOVED from the set of spectra that get\n'
            'fitted — so your concentration profiles cover just your real series.\n\n'
            'Untick only if the reference genuinely is one of the samples in your\n'
            'series (e.g. the first spectrum of a melting curve really is the pure\n'
            'duplex) and you want it fitted too.')
        self._ref_external_cb.stateChanged.connect(self._on_external_refs_changed)
        v.addWidget(self._ref_external_cb)
        # anchoring changes the fit → mark results stale when toggled/edited
        grp.toggled.connect(self._mark_results_stale)
        grp.toggled.connect(self._on_external_refs_changed)
        self._ref_fix_cb.stateChanged.connect(self._mark_results_stale)
        self._rebuild_reference_rows()
        return grp

    def _rebuild_reference_rows(self, *_):
        """Sync one reference picker per component slot to the current
        Components count."""
        from PyQt5.QtWidgets import QComboBox, QHBoxLayout
        # remember prior choices by slot so changing the count doesn't wipe them
        prior = [c.currentText() for c in getattr(self, '_ref_combos', [])]
        while self._ref_rows_layout.count():
            item = self._ref_rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._ref_combos = []
        labels = ['(none)'] + [s.get('label', f'Spectrum {i+1}')
                               for i, s in enumerate(self.spectra)]
        for k in range(self._n_spin.value()):
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(QLabel(f'Component {k+1}:'))
            combo = QComboBox()
            combo.addItems(labels)
            if k < len(prior) and prior[k] in labels:
                combo.setCurrentText(prior[k])
            combo.currentTextChanged.connect(self._mark_results_stale)
            # Changing WHICH spectrum is a reference changes which spectra
            # are fitted (when references are external), so the
            # Reconstruction tab's spectrum list has to follow — otherwise
            # it keeps offering the pure standards that are no longer part
            # of the fitted data.
            combo.currentTextChanged.connect(self._on_external_refs_changed)
            hl.addWidget(combo, 1)
            self._ref_rows_layout.addWidget(row)
            self._ref_combos.append(combo)

    def _fit_spectra(self):
        """The spectra that actually get DECOMPOSED. Normally that's every
        selected spectrum. But when "References are external" is on, the
        spectra chosen as reference standards are excluded — a
        previously-measured pure standard is a known component shape, not one
        of the mixtures in your experimental series, and leaving it in the
        fitted data would change what's being decomposed (an extra, nearly
        pure row in D pulls the fit toward it)."""
        refs, _ = self._reference_settings()
        if not refs or not getattr(self, '_ref_external_cb', None) \
                or not self._ref_external_cb.isChecked():
            return list(self.spectra)
        ref_labels = set()
        for combo in self._ref_combos:
            t = combo.currentText()
            if t and t != '(none)':
                ref_labels.add(t)
        return [s for s in self.spectra if s.get('label') not in ref_labels]

    def _on_external_refs_changed(self, *_):
        """Excluding/including reference spectra changes which spectra are
        fitted, so the reconstruction list must follow, and results go stale."""
        self._rebuild_recon_list()
        self._mark_results_stale()

    def _rebuild_recon_list(self, *_):
        """Keep the Reconstruction tab's spectrum selector in sync with the
        spectra actually being fitted (and also called when the Shorten
        Names checkbox is toggled, to redraw the item text).

        The previously-selected spectrum is tracked by its real (never
        shortened) label, stored in each item's Qt.UserRole, rather than by
        its displayed text — otherwise toggling Shorten Names would change
        every item's text and the "find the previously-selected item by
        matching its text" lookup would fail, silently resetting the
        selection to row 0."""
        if not hasattr(self, '_recon_list'):
            return
        prev_item = self._recon_list.currentItem()
        prev_label = prev_item.data(Qt.UserRole) if prev_item else None
        self._recon_list.blockSignals(True)
        self._recon_list.clear()
        for s in self._fit_spectra():
            item = QListWidgetItem(self._maybe_shorten(s['label']))
            item.setData(Qt.UserRole, s['label'])
            self._recon_list.addItem(item)
        if self._recon_list.count():
            idx = 0
            if prev_label:
                for i in range(self._recon_list.count()):
                    if self._recon_list.item(i).data(Qt.UserRole) == prev_label:
                        idx = i
                        break
            self._recon_list.setCurrentRow(idx)
        self._recon_list.blockSignals(False)

    def _reference_settings(self):
        """Build the references dict {component_index: (x, y)} from the
        pickers, or empty if reference anchoring is off / nothing chosen."""
        if not getattr(self, '_ref_grp', None) or not self._ref_grp.isChecked():
            return {}, False
        refs = {}
        for k, combo in enumerate(self._ref_combos):
            txt = combo.currentText()
            if txt and txt != '(none)':
                for s in self.spectra:
                    if s.get('label') == txt:
                        refs[k] = (np.asarray(s['x_scale'], float),
                                   np.asarray(s['y_scale'], float))
                        break
        return refs, self._ref_fix_cb.isChecked()

    def _current_settings(self):
        refs, fix_refs = self._reference_settings()
        return dict(
            n_components=self._n_spin.value(),
            init='svd',   # the only deterministic option now that random is
                          # only reachable via "Run N times, keep best"
            max_iterations=self._iter_spin.value(),
            c_nonneg=self._c_nonneg_cb.isChecked(),
            st_nonneg=self._st_nonneg_cb.isChecked(),
            normalize_spectra=True,   # see removal note above — always on now
            closure=self._closure_cb.isChecked(),
            references=refs,
            fix_references=fix_refs,
        )

    def _reference_ids(self):
        """Stable identity for each reference choice: the app gives every
        spectrum a metadata['unique_id'] (see spectrum_manager.Spectrum and
        operations_controller, which take pains to keep it unique even across
        copies and renames). Persisting that alongside the label closes the
        one real hole in label-only matching: delete a spectrum, import a
        different one that happens to reuse the same label, and a label-only
        match would silently re-attach the old reference to the new,
        unrelated data. Matching on unique_id first makes that impossible."""
        ids = []
        for combo in self._ref_combos:
            txt = combo.currentText()
            uid = ''
            if txt and txt != '(none)':
                for sp in self.spectra:
                    if sp.get('label') == txt:
                        uid = (sp.get('metadata') or {}).get('unique_id', '') or ''
                        break
            ids.append(uid)
        return ids

    def _persist_settings(self):
        """The current control values worth remembering between dialog
        sessions — read by the controller after the dialog closes and
        stored in operations_controller.last_op_settings['MCR-ALS'], then
        handed back as current_settings next time and restored by
        _apply_saved_settings(). Reuses _current_settings(); the extra
        internal keys (init, normalize_spectra) are simply ignored on
        restore.

        The reference choices are stored as spectrum LABELS (not the arrays
        themselves, which are session objects): on reopen, a saved label is
        only restored if a spectrum with that label is actually present in
        the new selection, so a stale reference can never silently attach
        itself to the wrong data."""
        s = self._current_settings()
        s.pop('references', None)
        s.pop('fix_references', None)
        s['ref_enabled'] = self._ref_grp.isChecked()
        s['ref_labels'] = [c.currentText() for c in self._ref_combos]
        s['ref_ids'] = self._reference_ids()
        s['ref_fixed'] = self._ref_fix_cb.isChecked()
        s['ref_external'] = self._ref_external_cb.isChecked()
        return s

    def _set_mcr_controls_enabled(self, enabled):
        self.run_btn.setEnabled(enabled)
        self._run_best_btn.setEnabled(enabled)

    def _run_mcr_als(self, *_):
        # Remember HOW this result was produced, so the Elbow / Median sweeps
        # can reproduce the same computation at every component count (see
        # _sweep_trial). Also invalidate the sweeps: a curve computed in the
        # other mode is no longer comparable with this result.
        if getattr(self, '_last_run_mode', None) != ('single', 1):
            self._elbow_cache_key = None
            self._fitq_cache_key = None
        self._last_run_mode = ('single', 1)

        if getattr(self, '_mcr_running', False):
            return  # already running — ignore a second trigger outright
        self._mcr_running = True
        self._set_mcr_controls_enabled(False)
        s = self._current_settings()

        self._status_label.setText('Running MCR-ALS…')

        has_neg = any(
            np.any(np.asarray(sp['y_scale'], dtype=float) < 0)
            for sp in self._fit_spectra())

        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        # Determinate 2-stage progress bar (fit done / plots rendered) —
        # same fix, same reasoning, as NMF's Run NMF button: the ALS fit
        # itself is one opaque call with no real intermediate checkpoints
        # to report, but the fit finishing and the plots finishing are two
        # honest, real boundaries either side of it.
        self._mcr_progress = QProgressDialog('Running MCR-ALS fit…', None, 0, 2, self)
        self._mcr_progress.setWindowModality(Qt.WindowModal)
        self._mcr_progress.setWindowTitle('MCR-ALS')
        self._mcr_progress.setMinimumDuration(0)
        self._mcr_progress.setCancelButton(None)
        self._mcr_progress.setValue(0)
        self._mcr_progress.show()

        self._mcr_worker = _ComputeWorker(
            lambda: self.controller.compute(self._fit_spectra(), **s), self)
        self._mcr_worker.done.connect(lambda: self._on_mcr_computed(has_neg))
        self._mcr_worker.start(QThread.LowPriority)

    def _on_mcr_computed(self, has_neg):
        try:
            ok = self._mcr_worker.result
            thread_error = self._mcr_worker.error
            mgr = self.controller.manager

            if thread_error is not None or not ok:
                specific = getattr(mgr, 'last_error', None)
                message = str(thread_error) if thread_error is not None else (
                    specific or
                    'MCR-ALS failed. Check that spectra have the same x-grid '
                    'and all values are finite.'
                )
                QMessageBox.warning(self, 'MCR-ALS Failed', message)
                self._status_label.setText('⚠  MCR-ALS failed — see message above.')
                self._status_label.setStyleSheet('font-size:8pt; color:#C62828;')
                return

            self._mgr = mgr
            self._mcr_progress.setLabelText('Rendering plots…')
            self._mcr_progress.setValue(1)

            warnings = []
            if has_neg and (self._c_nonneg_cb.isChecked() or self._st_nonneg_cb.isChecked()):
                warnings.append(
                    'Spectra contain negative values (e.g. CD data or '
                    'uncorrected baseline), but non-negativity is enabled for '
                    'C and/or ST. This will distort the fit unless the '
                    'negative-valued factor genuinely should be constrained '
                    'non-negative regardless. Consider unchecking the '
                    'relevant constraint, or applying baseline correction first.')
            if self._mgr.x_range_mismatch_warning:
                warnings.append(self._mgr.x_range_mismatch_warning)
            if not self._mgr.converged:
                warnings.append(
                    f'Did not converge within {self._iter_spin.value()} iterations '
                    '— consider increasing Max iterations.')
            if warnings:
                self._set_warning_text('\n\n⚠  '.join(warnings))
            else:
                self._neg_warn.setVisible(False)

            self._status_label.setText(
                f'{self._n_spin.value()} components  |  '
                f'lack of fit: {self._mgr.lof:.3g}%  |  '
                f'{self._mgr.iterations_used} iterations'
                f'{" (converged)" if self._mgr.converged else ""}'
            )
            self._status_label.setToolTip(
                'Lack of fit (LOF) = 100 \u00d7 sqrt(sum((D \u2212 C\u00b7ST)\u00b2) / sum(D\u00b2)).\n\n'
                'A percentage of the total signal magnitude left unexplained by\n'
                'the model — 0% would be a perfect fit. There\'s no universal\n'
                '"good" threshold; what matters is comparing this number across\n'
                'different component counts (see the Elbow tab) on the SAME\n'
                'dataset, and looking for where adding more components stops\n'
                'reducing it meaningfully.'
            )
            self._status_label.setStyleSheet('font-size:8pt; color:#2E7D32;')
            self._refresh_all()
        finally:
            self._mcr_progress.setValue(2)
            self._mcr_progress.close()
            self._set_mcr_controls_enabled(True)
            self._mcr_running = False
            from PyQt5.QtWidgets import QApplication
            QApplication.restoreOverrideCursor()

    def _prompt_and_run_best_of_n(self):
        """Ask how many random-seed runs to try, matching NMF's identical
        "Run N times, keep best" prompt (default 10, 2-100) rather than a
        hardcoded count."""
        if getattr(self, '_mcr_running', False):
            return
        from PyQt5.QtWidgets import QInputDialog
        n_runs, ok = QInputDialog.getInt(
            self, 'Run N times, keep best',
            'Number of runs (different random seeds):',
            value=getattr(self, '_last_n_runs', 10), min=2, max=100)
        if not ok:
            return
        self._last_n_runs = n_runs   # remembered and pre-filled next time
        self._run_mcr_als_best_of_n(n_runs)

    @staticmethod
    def _match_similarity(A, B):
        """Average best-matched absolute correlation between two sets of
        component rows (e.g. two different ST matrices from two separate
        MCR-ALS runs) — used to judge whether two SOLUTIONS agree with
        each other structurally, the same one-to-one best-matching logic
        used elsewhere in this file to compare a solution against known
        ground truth, just applied between two candidate solutions
        instead."""
        n = A.shape[0]
        used = set()
        total = 0.0
        for k in range(n):
            best_j, best_c = None, -2
            for j in range(n):
                if j in used:
                    continue
                length = min(A.shape[1], B.shape[1])
                c = np.corrcoef(A[k, :length], B[j, :length])[0, 1]
                if np.isnan(c):
                    c = 0.0
                if abs(c) > best_c:
                    best_c, best_j = abs(c), j
            used.add(best_j)
            total += best_c
        return total / n

    def _run_mcr_als_best_of_n(self, n_runs):
        if getattr(self, '_last_run_mode', None) != ('best_of_n', n_runs):
            self._elbow_cache_key = None
            self._fitq_cache_key = None
        self._last_run_mode = ('best_of_n', n_runs)

        if getattr(self, '_mcr_running', False):
            return
        self._mcr_running = True
        self._set_mcr_controls_enabled(False)

        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        s = self._current_settings()

        progress = QProgressDialog(f'Run 1 of {n_runs}…', 'Cancel', 0, n_runs, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle('MCR-ALS')
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        all_trials = []   # (lof, manager)
        m = None
        for i in range(n_runs):
            if progress.wasCanceled():
                break
            progress.setLabelText(f'Run {i + 1} of {n_runs}…')
            progress.setValue(i)
            QApplication.processEvents()
            m, ok = self.controller.compute_trial(
                self._fit_spectra(), n_components=s['n_components'], init='random',
                max_iterations=s['max_iterations'], tol=0.01,
                c_nonneg=s['c_nonneg'], st_nonneg=s['st_nonneg'],
                normalize_spectra=s['normalize_spectra'], closure=s['closure'],
                random_state=i,
                references=s.get('references'), fix_references=s.get('fix_references', False))
            if ok:
                all_trials.append((m.lof, m))
        progress.setValue(n_runs)

        try:
            if not all_trials:
                specific = getattr(m, 'last_error', None) if m is not None else None
                QMessageBox.warning(self, 'MCR-ALS Failed', specific or 'All runs failed.')
                self._status_label.setText('⚠  All runs failed — see message above.')
                self._status_label.setStyleSheet('font-size:8pt; color:#C62828;')
                return

            all_lofs = [t[0] for t in all_trials]
            best_lof = min(all_lofs)

            # Don't just keep the single lowest-LOF run: with a genuinely
            # noisy fit, the absolute best LOF can belong to a solution
            # that happens to fit THIS noise realization marginally
            # better than several other, essentially-as-good solutions —
            # while representing a different (wrong) rotation of the
            # components. Confirmed directly: across 100 real restarts on
            # a known test case, the single lowest-LOF run scored 0.997
            # correlation against ground truth, while several runs with
            # LOF only ~0.001-0.003 percentage points higher scored a
            # perfect 1.000. Instead, take the pool of near-best runs and
            # keep whichever is most representative of that pool (highest
            # average structural agreement with the others in it) — the
            # consensus answer, not whichever run got marginally lucky
            # with the noise.
            near_best_tol = 0.02   # within 2% of the best LOF
            pool = [(lof, mgr) for lof, mgr in all_trials if lof <= best_lof * (1 + near_best_tol)]

            if len(pool) == 1:
                best_mgr = pool[0][1]
                consensus = None
            else:
                agreement = []
                for i, (_, mgr_i) in enumerate(pool):
                    scores = [self._match_similarity(mgr_i.ST, mgr_j.ST)
                              for j, (_, mgr_j) in enumerate(pool) if j != i]
                    agreement.append(np.mean(scores))
                best_idx = int(np.argmax(agreement))
                best_mgr = pool[best_idx][1]
                consensus = agreement[best_idx]

            self.controller.adopt(best_mgr)
            self._mgr = self.controller.manager
            # How consistent were the random restarts? If most of them
            # land near the same best LOF, that's real evidence you're
            # close to the true (global) optimum rather than one lucky
            # seed; if they're scattered widely, the fit is poorly
            # determined at this component count regardless of which one
            # you keep — see Help for what to do about that.
            n_ok = len(all_lofs)
            close_to_best = sum(1 for v in all_lofs if v <= best_lof * 1.10)
            status = (
                f'{self._n_spin.value()} components  |  '
                f'lack of fit: {self._mgr.lof:.3g}%  |  best of {n_runs} random runs  |  '
                f'{close_to_best}/{n_ok} runs within 10% of best'
            )
            if consensus is not None:
                status += f'  |  consensus among {len(pool)} near-best runs: {consensus*100:.0f}%'
            self._status_label.setText(status)
            self._status_label.setStyleSheet('font-size:8pt; color:#2E7D32;')

            warnings = []
            if consensus is not None and consensus < 0.9:
                warnings.append(
                    'The near-best runs do not agree with each other structurally '
                    f'(only {consensus*100:.0f}% average agreement among {len(pool)} runs with '
                    'similarly low lack-of-fit). This is a real sign that this component count '
                    'is not uniquely determined by your data — different, equally-valid-looking '
                    'decompositions exist. Consider fewer components, or treat any single result '
                    '(including this one) with real caution.')
            # Same negative-values check as the plain Run MCR-ALS path — it
            # was previously only shown there, so a user who went straight to
            # "Run N times" on signed data (CD, uncorrected baseline) never
            # saw the warning that non-negativity is distorting the fit.
            has_neg = any(
                np.any(np.asarray(sp['y_scale'], dtype=float) < 0)
                for sp in self._fit_spectra())
            if has_neg and (self._c_nonneg_cb.isChecked() or self._st_nonneg_cb.isChecked()):
                warnings.append(
                    'Spectra contain negative values (e.g. CD data or '
                    'uncorrected baseline), but non-negativity is enabled for '
                    'C and/or ST. This will distort the fit unless the '
                    'negative-valued factor genuinely should be constrained '
                    'non-negative regardless. Consider unchecking the '
                    'relevant constraint, or applying baseline correction first.')
            if self._mgr.x_range_mismatch_warning:
                warnings.append(self._mgr.x_range_mismatch_warning)
            if warnings:
                self._set_warning_text('\n\n⚠  '.join(warnings))
            else:
                self._neg_warn.setVisible(False)
            self._refresh_all()
        finally:
            self._set_mcr_controls_enabled(True)
            self._mcr_running = False
            QApplication.restoreOverrideCursor()

    def _draw_stale(self, canvas):
        """Blank a result canvas with a clear 'you changed the settings,
        the plot no longer matches — re-run' message, so a stale plot is
        never mistaken for a result of the current settings."""
        ax = canvas.ax
        ax.clear()
        ax.text(0.5, 0.5, 'Settings changed —\npress \u201cRun MCR-ALS\u201d to update',
                ha='center', va='center', fontsize=11, color='#B71C1C',
                transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        canvas.draw_tight()

    def _mark_results_stale_keep_sweeps(self, *_):
        """The COMPONENT COUNT changed. That makes the loaded result stale (the
        Pure Spectra / Concentrations / Reconstruction tabs no longer match the
        settings), but it does NOT invalidate the Elbow or Median sweeps: those
        re-run the analysis at EVERY component count from 2 to the maximum, so
        their curves are independent of which single count you happen to have
        selected. Blanking them here just forced a needless (and slow)
        recomputation. The only thing that changes on those plots is where the
        red 'Current n' line sits."""
        self._mark_results_stale(invalidate_sweeps=False)

    def _mark_results_stale(self, *_, invalidate_sweeps=True):
        """Called whenever a setting that changes the actual fit (components,
        iterations, constraints) is edited without re-running. Invalidates
        the cached component-count sweeps and blanks every result plot so
        the user is never looking at a plot that doesn't correspond to the
        current settings."""
        if getattr(self, '_suppress_stale', False):
            return
        self._results_stale = True
        if invalidate_sweeps:
            self._elbow_cache_key = None
            self._elbow_cache_data = None
            self._fitq_cache_key = None
            self._fitq_cache_data = None
        for canvas in (self._spectra_canvas, self._conc_canvas, self._recon_canvas,
                       self._recon_canvas):
            self._draw_stale(canvas)
        # The Fit Quality canvas is only blanked when it is showing the
        # per-spectrum view (which genuinely depends on the loaded run).
        # The two 'vs component count' sweeps stay valid unless a setting
        # that actually affects them changed, so they are simply redrawn
        # (moving the 'Current n' line) rather than blanked.
        if self._fitq_mode_combo.currentText().startswith('Per spectrum'):
            self._draw_stale(self._fitq_canvas)
        elif not invalidate_sweeps:
            self._refresh_fit_quality()
        else:
            self._draw_stale(self._fitq_canvas)

    def _refresh_all(self):
        self._results_stale = False
        self._refresh_spectra()
        self._refresh_concentrations()
        self._refresh_reconstruction()
        # Ground-truth comparison (testing/didactic feature, hidden behind
        # the right-click context menu): the overlay curves on the three
        # tabs above are already redrawn by the calls just above (each of
        # those methods checks self._gt itself); this call additionally
        # refreshes the dynamic "Ground Truth" report tab so its numbers
        # reflect THIS run, not whatever was loaded when ground truth was
        # first picked.
        if self._gt is not None:
            self._refresh_gt_report_tab()
        # Invalidate the cached trend first — it was computed against
        # whatever settings/result existed before this run.
        # NOTE: the Elbow / Median sweep caches are deliberately NOT cleared
        # here. Pressing Run (or "Run N times") does not change any setting the
        # sweeps depend on — they re-run the analysis at every component count
        # from their own settings — so a cached sweep is still perfectly valid
        # after a Run. Clearing it forced a full (slow) recomputation of the
        # whole sweep every single time you pressed Run while the Fit Quality
        # tab was open, which is what made Run feel so slow from that tab. The
        # caches ARE cleared by _mark_results_stale when a setting that really
        # does affect them changes (max-iterations, constraints, references).
        watching_fitq = (self._tabs.tabText(self._tabs.currentIndex()) == 'Fit Quality')
        mode = self._fitq_mode_combo.currentText()
        if mode.startswith('Per spectrum'):
            # Cheap — always safe to refresh after every run.
            self._refresh_fitq_current_run()
        elif watching_fitq:
            # You're actively looking at a "vs component count" view right
            # now — recompute immediately rather than showing a placeholder
            # you'd have to leave and come back to clear.
            self._refresh_fit_quality()
        # else: an expensive "vs component count" view that isn't visible —
        # leave it; it recomputes on its own next time you switch to it.

    # ------------------------------------------------------------------ #
    # Plots                                                                #
    # ------------------------------------------------------------------ #

    def _refresh_spectra(self, *_):
        if getattr(self, '_results_stale', False):
            self._draw_stale(self._spectra_canvas); return
        if self._mgr is None or self._mgr.ST is None:
            return
        ax = self._spectra_canvas.ax
        ax.clear()
        x = self._mgr.x_axis
        n_comp = self._mgr.ST.shape[0]
        use_offset = self._spectra_offset_cb.isChecked()
        use_normalize = self._spectra_normalize_cb.isChecked()

        if use_normalize:
            curves = []
            for k in range(n_comp):
                peak = np.max(np.abs(self._mgr.ST[k]))
                curves.append(self._mgr.ST[k] / peak if peak > 0 else self._mgr.ST[k])
        else:
            curves = [self._mgr.ST[k] for k in range(n_comp)]

        offset_step = (max(np.max(np.abs(c)) for c in curves) * 1.15 if n_comp > 1 else 0.0) \
            if use_offset else 0.0
        for k in range(n_comp):
            color = _COLORS[k % len(_COLORS)]
            ev = self._mgr.explained_variance[k]
            ax.plot(x, curves[k] + k * offset_step, color=color, lw=1.2,
                    label=f'MCR {k+1}  ({ev:.1f} %)')
            if use_offset:
                ax.axhline(k * offset_step, color=color, lw=0.4, ls=':', alpha=0.5)

        if self._gt is not None:
            self._draw_gt_overlay_components(ax, x, offset_step, use_normalize)

        ax.set_xlabel('x', fontsize=10)
        ylabel = 'Intensity'
        if use_normalize:
            ylabel += ' (normalized)'
        if use_offset:
            ylabel += ' (offset)'
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(f'MCR-ALS pure component spectra ({n_comp} components)', fontsize=11)
        ax.legend(fontsize=8, loc='best', framealpha=0.7)
        ax.grid(True, linestyle='--', alpha=0.35)
        self._spectra_canvas.draw_tight()

    def _maybe_shorten(self, label):
        """Apply this dialog's Shorten Names checkbox (if checked) to a
        single spectrum label — same distinguishing-shortening logic the
        Concentrations tab uses via _get_display_labels, but for the
        Reconstruction tab's spectrum-selector list/title and the Fit
        Quality tab's bar-chart labels, which pick one label at a time
        rather than a whole list. Shortening is still computed against
        the FULL spectrum list (what's "distinguishing" depends on the
        whole group, not the one label being displayed)."""
        if not self.checkBox_shorten_names.isChecked():
            return label
        short_map = compute_distinguishing_labels([s['label'] for s in self.spectra])
        return short_map.get(label, label)

    def _get_display_labels(self, labels, trunc_combo, trunc_n_spin):
        """Shared label-truncation logic driven by a "Full label / First N
        chars / Last N chars" combo + N spinbox — same convention as
        cluster_analysis_dialog's dendrogram truncation controls.

        When "Use spectrum index" is checked, plain 1-based position
        numbers are returned instead — truncation doesn't apply then.

        Honors this dialog's own "shorten names" checkbox
        (self.checkBox_shorten_names) first, same order as
        cluster_analysis_dialog: shorten, THEN apply the First/Last-N-chars
        truncation on top of the (possibly already-shortened) text."""
        if getattr(self, '_conc_use_index_cb', None) is not None and self._conc_use_index_cb.isChecked():
            return [str(i + 1) for i in range(len(labels))]
        labels = list(labels)
        if self.checkBox_shorten_names.isChecked():
            short_map = compute_distinguishing_labels(labels)
            labels = [short_map.get(lbl, lbl) for lbl in labels]
        mode = trunc_combo.currentText()
        n = trunc_n_spin.value()
        if mode == 'First N chars':
            return [lbl[:n] for lbl in labels]
        elif mode == 'Last N chars':
            return [lbl[-n:] for lbl in labels]
        return list(labels)


    def _populate_conc_table(self, C, labels, normalized):
        """Fill the Concentrations tab's table page with exactly the numbers
        the plot is showing (including the 100%-normalisation if enabled), so
        precise values can be read off directly instead of eyeballed."""
        from PyQt5.QtWidgets import QTableWidgetItem
        n_spec, n_comp = C.shape
        t = self._conc_table
        t.clear()
        t.setRowCount(n_spec)
        t.setColumnCount(n_comp + 1)
        unit = ' (%)' if normalized else ''
        t.setHorizontalHeaderLabels(
            ['Spectrum'] + [f'{_COMP_NAME} {k+1}{unit}' for k in range(n_comp)])
        for i in range(n_spec):
            t.setItem(i, 0, QTableWidgetItem(str(labels[i])))
            for k in range(n_comp):
                val = float(C[i, k])
                item = QTableWidgetItem(f'{val:.2f}' if normalized else f'{val:.4g}')
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(i, k + 1, item)
        t.resizeColumnsToContents()

    def _refresh_concentrations(self, *_):
        if getattr(self, '_results_stale', False):
            self._draw_stale(self._conc_canvas); return
        if self._mgr is None or self._mgr.C is None:
            return

        # Same reasoning as ClusterAnalysisDialog.on_method_changed and
        # NMFDialog's own Scores tab: this is a single, unsplittable
        # matplotlib draw call on the GUI thread — nothing genuinely
        # progresses until the one final render, so a busy cursor is the
        # honest amount of feedback here, not a progress bar.
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        try:
            ax = self._conc_canvas.ax
            ax.clear()

            C = self._mgr.C
            n_comp = C.shape[1]
            n_spec = C.shape[0]
            labels = self._get_display_labels(
                self._mgr.labels, self._conc_trunc_combo, self._conc_trunc_n_spin)

            if self._conc_normalize_cb.isChecked():
                row_sums = C.sum(axis=1, keepdims=True)
                row_sums[row_sums == 0] = 1.0   # avoid div-by-zero for an all-zero row
                C = 100.0 * C / row_sums
                y_label = 'Concentration (% of spectrum total)'
            else:
                y_label = 'Concentration (C)'

            # Table view: same numbers as the plot (incl. normalisation),
            # just readable directly. Switch the stacked widget's page and
            # skip the (pointless) plot draw.
            if self._conc_view_combo.currentText() == 'Table':
                self._populate_conc_table(
                    C, labels, self._conc_normalize_cb.isChecked())
                self._conc_stack.setCurrentIndex(1)
                return
            self._conc_stack.setCurrentIndex(0)

            plot_type = self._conc_plot_type_combo.currentText()
            x = np.arange(n_spec)

            if plot_type == 'Lines':
                for k in range(n_comp):
                    color = _COLORS[k % len(_COLORS)]
                    ev = self._mgr.explained_variance[k]
                    ax.plot(x, C[:, k], 'o-', color=color, ms=3, lw=1.2,
                            label=f'MCR {k+1}  ({ev:.1f} %)')
                tick_positions = x
            elif plot_type == 'Stacked bars':
                bottom = np.zeros(n_spec)
                for k in range(n_comp):
                    color = _COLORS[k % len(_COLORS)]
                    ev = self._mgr.explained_variance[k]
                    ax.bar(x, C[:, k], bottom=bottom, color=color, alpha=0.85,
                           label=f'MCR {k+1}  ({ev:.1f} %)')
                    bottom = bottom + C[:, k]
                tick_positions = x
            else:  # Grouped bars (default)
                bar_w = 0.8 / n_comp
                for k in range(n_comp):
                    color = _COLORS[k % len(_COLORS)]
                    ev = self._mgr.explained_variance[k]
                    ax.bar(x + k * bar_w, C[:, k], width=bar_w, color=color,
                           alpha=0.75, label=f'MCR {k+1}  ({ev:.1f} %)')
                tick_positions = x + bar_w * (n_comp - 1) / 2

            if self._gt is not None:
                self._draw_gt_overlay_scores(ax, x)

            rotation = int(self._conc_rotation_combo.currentText().replace('\u00b0', ''))
            fontsize_text = self._conc_fontsize_combo.currentText()
            if fontsize_text == 'Auto':
                label_fontsize = 7 if n_spec <= 40 else (5 if n_spec <= 80 else 4)
            else:
                label_fontsize = int(fontsize_text)
            ha = 'right' if rotation > 0 else 'center'

            if n_spec <= 40 or fontsize_text != 'Auto':
                ax.set_xticks(tick_positions)
                ax.set_xticklabels(labels, rotation=rotation, ha=ha, fontsize=label_fontsize)
            else:
                step = max(1, n_spec // 20)
                ticks = list(range(0, n_spec, step))
                ax.set_xticks(tick_positions[ticks])
                ax.set_xticklabels([labels[t] for t in ticks], rotation=rotation,
                                    ha=ha, fontsize=label_fontsize)

            ax.set_ylabel(y_label, fontsize=10)
            ax.set_title(f'MCR-ALS concentration profiles  ({n_spec} spectra)', fontsize=11)
            ax.legend(fontsize=8, loc='best', framealpha=0.7)
            ax.grid(True, axis='y', linestyle='--', alpha=0.35)
            self._conc_canvas.draw_tight()
        finally:
            QApplication.restoreOverrideCursor()

    @staticmethod
    def _truncate_label(label, max_len=25):
        if len(label) <= max_len:
            return label
        tail = label.rsplit(':', 1)[-1].strip()
        if 0 < len(tail) <= max_len - 1:
            return '\u2026' + tail
        return '\u2026' + label[-(max_len - 1):]

    def _refresh_reconstruction(self, *_):
        if getattr(self, '_results_stale', False):
            self._draw_stale(self._recon_canvas); return
        if self._mgr is None or self._mgr.C is None:
            return
        canvas = self._recon_canvas
        canvas.fig.clf()
        # Two stacked panels: the main comparison above, and a dedicated
        # residual sub-panel below at its own y-scale. Residuals are
        # typically much smaller than the original signal, so a plotted
        # residual curve on the SAME axes as the data would be visually
        # indistinguishable from zero — the hatched region in the main
        # panel shows WHERE the residual sits relative to the data's own
        # scale, and this sub-panel shows what it actually looks like.
        ax1, ax2 = canvas.fig.subplots(
            2, 1, sharex=True, gridspec_kw={'height_ratios': [3, 1], 'hspace': 0.08})
        canvas.ax = ax1   # keep .ax pointing at the main panel, matching every other tab

        idx = self._recon_list.currentRow()
        if idx < 0:
            idx = 0
        idx = max(0, min(idx, self._mgr.C.shape[0] - 1))
        x = self._mgr.x_axis
        original = None
        for s in self.spectra:
            if s.get('label') == self._mgr.labels[idx]:
                y = np.asarray(s['y_scale'], dtype=float)
                _sx, _sy = _ascending_xy(s['x_scale'], y)
                original = np.interp(x, _sx, _sy) \
                    if len(y) != len(x) else y
                break
        reconstructed = self._mgr.C[idx, :] @ self._mgr.ST

        ax1.plot(x, original, color='black', lw=1.2, label='Original')
        ax1.plot(x, reconstructed, color='red', ls='--', lw=1.2, label='Reconstructed (C\u00b7ST)')
        if self._gt is not None:
            self._draw_gt_overlay_reconstruction(ax1, x, self._mgr.labels[idx])
        curves_only = self._recon_curves_only_cb.isChecked()
        if not curves_only:
            bottom = np.zeros_like(x)
            for k in range(self._mgr.ST.shape[0]):
                contrib = self._mgr.C[idx, k] * self._mgr.ST[k]
                color = _COLORS[k % len(_COLORS)]
                # alpha 0.55 + a solid edge in the SAME colour as the
                # Pure Spectra / Concentrations tabs use for this component,
                # so component k reads as the same colour everywhere (a light
                # 0.35-alpha red otherwise looked "pink" next to the solid red
                # line used for the same component on the other tabs).
                ax1.fill_between(x, bottom, bottom + contrib, color=color, alpha=0.55,
                                  edgecolor=color, linewidth=0.8,
                                  label=f'MCR {k+1} contribution')
                bottom = bottom + contrib
        residual = original - reconstructed
        if not curves_only:
            ax1.fill_between(x, reconstructed, reconstructed + residual, hatch='///',
                              facecolor='none', edgecolor='gray', alpha=0.5, label='Residual region')

        ax1.set_ylabel('Intensity', fontsize=10)
        ax1.set_title(f'Reconstruction: {self._maybe_shorten(self._mgr.labels[idx])}', fontsize=11)
        ax1.legend(fontsize=7, loc='best', framealpha=0.7)
        ax1.grid(True, linestyle='--', alpha=0.35)
        ax1.tick_params(labelbottom=False)

        ax2.plot(x, residual, color='#555', lw=1.0)
        ax2.axhline(0, color='black', lw=0.6, ls='-')
        ax2.set_xlabel('x', fontsize=10)
        ax2.set_ylabel('Residual', fontsize=9)
        ax2.grid(True, linestyle='--', alpha=0.35)

        canvas.draw_tight()

    def _relative_residuals(self, mgr, spectra):
        """Per-spectrum relative residual (%) for a given (already-computed)
        manager — shared by the current-run bar chart and the
        median-vs-component-count trend, so both use exactly the same
        definition of "fit quality"."""
        x_ref = mgr.x_axis
        n_spec = mgr.C.shape[0]
        rel_residual = np.full(n_spec, np.nan)
        for i in range(n_spec):
            original = None
            for s in spectra:
                if s.get('label') == mgr.labels[i]:
                    y = np.asarray(s['y_scale'], dtype=float)
                    x = np.asarray(s['x_scale'], dtype=float)
                    _sx, _sy = _ascending_xy(x, y)
                    original = np.interp(x_ref, _sx, _sy) if len(y) != len(x_ref) else y
                    break
            if original is None:
                continue
            reconstructed = mgr.C[i, :] @ mgr.ST
            denom = np.linalg.norm(original)
            rel_residual[i] = 100.0 * np.linalg.norm(original - reconstructed) / denom \
                if denom > 0 else 0.0
        return rel_residual

    def _refresh_fit_quality(self, *_):
        mode = self._fitq_mode_combo.currentText()
        # Only the per-spectrum view depends on the loaded run, so only it goes
        # stale. The two 'vs component count' sweeps are independent of the
        # selected component count and remain valid.
        if getattr(self, '_results_stale', False) and mode.startswith('Per spectrum'):
            self._draw_stale(self._fitq_canvas)
            return
        if mode.startswith('Elbow'):
            self._refresh_elbow()
        elif mode.startswith('Median'):
            self._refresh_fitq_vs_components()
        else:
            self._refresh_fitq_current_run()

    def _refresh_fitq_current_run(self):
        """One glance at every spectrum's fit at once — a bar chart of
        each spectrum's relative residual (%), rather than having to click
        through the Reconstruction tab one spectrum at a time to notice
        that one of them fits much worse than the rest."""
        if self._mgr is None or self._mgr.C is None:
            return
        ax = self._fitq_canvas.ax
        ax.clear()

        n_spec = self._mgr.C.shape[0]
        rel_residual = self._relative_residuals(self._mgr, self._fit_spectra())

        labels = [self._truncate_label(self._maybe_shorten(lbl)) for lbl in self._mgr.labels]
        median = float(np.nanmedian(rel_residual))
        # Flag spectra fitting notably worse than the rest — a visual aid,
        # not a formal statistical test: anything more than double the
        # median (and itself above 1%, so tiny numbers near-zero don't all
        # get flagged just because they're not exactly equal) is marked.
        threshold = max(median * 2.0, 1.0)
        colors = ['#C62828' if (r > threshold) else '#1976D2' for r in rel_residual]

        x_pos = np.arange(n_spec)
        ax.bar(x_pos, rel_residual, color=colors)
        ax.axhline(median, color='gray', ls='--', lw=1,
                   label=f'Median ({median:.3g}%)')
        if n_spec <= 40:
            ax.set_xticks(x_pos)
            ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=7)
        else:
            step = max(1, n_spec // 20)
            ticks = list(range(0, n_spec, step))
            ax.set_xticks(ticks)
            ax.set_xticklabels([labels[t] for t in ticks], rotation=45, ha='right', fontsize=7)

        ax.set_ylabel('Relative residual (%)', fontsize=10)
        ax.set_title('Fit quality across all spectra', fontsize=11)
        ax.legend(fontsize=8, loc='best', framealpha=0.7)
        ax.grid(True, axis='y', linestyle='--', alpha=0.35)
        self._fitq_canvas.draw_tight()

    def _refresh_fitq_vs_components(self):
        """Median relative residual vs component count — the SAME
        per-spectrum metric the current-run bar chart uses (median, so a
        few badly-fit spectra don't dominate it the way the Elbow tab's
        aggregate lack-of-fit can). Genuinely different information from
        the Elbow tab: lack-of-fit is dominated by whichever spectra have
        the largest absolute residuals, while this reflects how the
        TYPICAL spectrum fits — the two can legitimately disagree, and
        that disagreement itself is informative (see the Help topic).

        Only the point at your actual current component count (marked in
        green) is guaranteed to match the "Per spectrum" view's own
        reported median exactly — it reuses that real result directly.
        Every OTHER point is a separate trial run with early stopping
        deliberately disabled (forced to the full iteration budget), since
        comparing fairly across different component counts requires each
        one to be pushed equally far — the same fix applied to the Elbow
        tab. Your actual settings may use early stopping, so those other
        points can genuinely differ from what a real "Run" at that count
        would show; this isn't a bug, it's an unavoidable trade-off
        between "fair comparison across counts" and "exactly matches your
        current settings" — see Help.
        """
        if not self.spectra or len(self.spectra) < 3:
            return
        n_max = min(self._elbow_max_spin.value(), len(self.spectra) - 1)
        s = self._current_settings()
        cache_key = ('fitq', n_max, s['init'], s['max_iterations'], s['c_nonneg'],
                     s['st_nonneg'], s['normalize_spectra'], s['closure'],
                     self._sweep_runs_spin.value())
        if self._fitq_cache_key == cache_key and self._fitq_cache_data is not None:
            ns, medians = self._fitq_cache_data
        else:
            ns, medians = self._compute_fitq_vs_components_data(n_max, s)
            if ns is None:
                return
            self._fitq_cache_key = cache_key
            self._fitq_cache_data = (ns, medians)

        ax = self._fitq_canvas.ax
        ax.clear()
        # Same two-entry legend as the Elbow view.
        self._sweep_values = list(medians)
        ax.plot(ns, medians, 'o-', color='#1565C0', lw=1.5, markersize=5,
                label='Median residual at each component count')
        ax.set_xlabel('Number of components', fontsize=10)
        ax.set_title('Median fit quality vs. component count', fontsize=11)
        ax.set_xticks(ns)
        ax.grid(True, linestyle='--', alpha=0.35)
        self._finish_sweep_axes(ax, medians, 'Median relative residual (%)')
        self._mark_current_run_point(ax, ns)
        self._fitq_canvas.draw_tight()

    def _compute_fitq_vs_components_data(self, n_max, s):
        from PyQt5.QtWidgets import QApplication, QProgressDialog

        ns = list(range(2, n_max + 1))
        medians = []
        current_mgr_n = self._mgr.n_components if (self._mgr is not None and self._mgr.C is not None) else None

        progress = QProgressDialog('Computing median fit quality…', 'Cancel', 0, len(ns), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle('MCR-ALS')
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        for i, n in enumerate(ns):
            if progress.wasCanceled():
                progress.close()
                return None, None
            progress.setLabelText(f'Computing median fit quality… ({n} components)')
            progress.setValue(i)
            QApplication.processEvents()
            # For the component count you're actually currently set to, use
            # the real, already-computed current run directly rather than
            # a fresh trial — otherwise this point could disagree with the
            # "Per spectrum" view's own reported median at the same n,
            # since a fresh trial here deliberately forces full iterations
            # for a fair cross-count comparison (see below), which the
            # current run may not have used.
            if n == current_mgr_n:
                medians.append(float(np.nanmedian(self._relative_residuals(self._mgr, self._fit_spectra()))))
                continue
            _lof, m = self._sweep_trial(n, s, progress, 'Computing median fit quality…')
            if progress.wasCanceled():
                progress.close()
                return None, None
            if m is not None:
                medians.append(float(np.nanmedian(self._relative_residuals(m, self._fit_spectra()))))
            else:
                medians.append(float('nan'))
        progress.setValue(len(ns))
        progress.close()
        return ns, medians

    # ------------------------------------------------------------------ #
    # Elbow                                                                #
    # ------------------------------------------------------------------ #


    # Below this lack-of-fit (%), a fit is exact for all practical purposes.
    # Noise-free synthetic data hits ~1e-9 % or lower at the correct component
    # count, i.e. machine precision.
    _NEGLIGIBLE_LOF = 0.05

    def _finish_sweep_axes(self, ax, values, ylabel):
        """Guard the 'vs component count' plots against a genuinely misleading
        artefact: when the data is (near-)noise-free, the fit is already EXACT
        at the correct component count, so every value on the curve is
        floating-point noise around zero (1e-9 % or smaller). Matplotlib then
        autoscales that dust to fill the whole axis, producing a dramatic
        zig-zag that looks like real structure — users reasonably read the
        wiggles as "5 components is worse than 4", when in truth every point is
        zero to numerical precision and the differences are meaningless.

        So: if every value is below the negligible threshold, pin the y-axis to
        a fixed sensible range (which flattens the curve onto zero, where it
        belongs) and say so on the plot."""
        vals = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
        if vals.size and float(np.nanmax(np.abs(vals))) < self._NEGLIGIBLE_LOF:
            ax.set_ylim(-0.01, max(0.1, self._NEGLIGIBLE_LOF * 2))
            ax.text(0.5, 0.55,
                    'Every fit here is essentially EXACT\n'
                    f'(all values < {self._NEGLIGIBLE_LOF:g} %, i.e. zero to numerical precision).\n'
                    'The smallest component count shown already reproduces the data.\n'
                    'Any wiggle you would see on an auto-scaled axis is floating-point\n'
                    'noise, not real structure — do not read an "elbow" into it.',
                    transform=ax.transAxes, ha='center', va='center',
                    fontsize=9, color='#2E7D32',
                    bbox=dict(boxstyle='round', facecolor='#E8F5E9',
                              edgecolor='#A5D6A7'))
        else:
            ax.set_ylim(bottom=0)
        ax.set_ylabel(ylabel, fontsize=10)


    def _mark_current_run_point(self, ax, ns, _unused=None):
        """Green dot marking the component count you currently have selected —
        plotted as a point ON the curve, using the curve's own value.

        It used to plot the LOADED RUN's own lack-of-fit instead. That was
        subtly wrong and looked like a plotting bug: the sweep computes one
        deterministic trial per component count, whereas your loaded run may
        have come from "Run N times, keep best", which searches much harder and
        so lands on a different (usually better) value. The dot then floated
        off the curve. The two numbers were never comparable — they were
        computed under different conditions — so showing them on the same axis
        as if they were invited exactly the wrong conclusion.

        The dot now simply says "this is where your current component count sits
        on this curve", which is the only claim the sweep can honestly support.
        Your run's actual lack-of-fit is reported in the status line, where it
        can't be mistaken for a point on this curve."""
        if not ns:
            return
        try:
            n_cur = self._n_spin.value()
        except Exception:
            return
        if n_cur not in ns:
            return
        v = self._sweep_values[ns.index(n_cur)] if getattr(self, '_sweep_values', None) else None
        if v is None or not np.isfinite(v):
            return
        ax.plot(n_cur, v, 'o', color='#2E7D32', ms=10, zorder=3,
                label=f'Current setting (n={n_cur})')
        ax.legend(fontsize=8, loc='best')

    def _mark_current_n(self, ax):
        """The red dashed vertical line used to be drawn here. It has been
        removed: it marked the same component count the green dot already
        marks, so it was pure duplication and added a third legend entry for
        no information."""
        return


    def _refresh_elbow(self):
        if not self.spectra or len(self.spectra) < 3:
            return
        n_max = min(self._elbow_max_spin.value(), len(self.spectra) - 1)
        s = self._current_settings()
        cache_key = (n_max, s['init'], s['max_iterations'], s['c_nonneg'],
                     s['st_nonneg'], s['normalize_spectra'], s['closure'],
                     self._sweep_runs_spin.value())
        if self._elbow_cache_key == cache_key and self._elbow_cache_data is not None:
            ns, lofs = self._elbow_cache_data
        else:
            ns, lofs = self._compute_elbow_data(n_max, s)
            if ns is None:
                return
            self._elbow_cache_key = cache_key
            self._elbow_cache_data = (ns, lofs)

        ax = self._elbow_canvas.ax
        ax.clear()
        # Two-entry legend, matching the 'Median residual' view: the curve,
        # and a dot for the component count you currently have selected.
        self._sweep_values = list(lofs)
        ax.plot(ns, lofs, 'o-', color='#1565C0', lw=1.5, markersize=5,
                label='Lack of fit at each component count')
        self._mark_current_run_point(ax, ns)
        ax.set_xlabel('Number of components', fontsize=10)
        # Same title, axes, colours and current-n marker as the NMF elbow, so
        # the two tools' elbow plots are directly comparable.
        ax.set_title('Elbow plot \u2014 choose n at the \u201celbow\u201d', fontsize=11)
        ax.set_xticks(ns)
        ax.grid(True, linestyle='--', alpha=0.35)
        self._finish_sweep_axes(ax, lofs, 'Lack of fit (%)')
        self._elbow_canvas.draw_tight()


    def _sweep_trial(self, n, s, progress=None, base_label=''):
        from PyQt5.QtWidgets import QApplication
        """Fit at component count *n* the SAME WAY your last Run did.

        Previously every point on the sweep was ONE deterministic run, even when
        your loaded result came from "Run N times, keep best" — which searches
        much harder. The curve and your result were then computed under
        different conditions and simply weren't comparable (this is what put the
        green dot off the curve). Now the sweep replays whatever you last did:

          * after "Run MCR-ALS"        -> one run per component count (fast)
          * after "Run N times, keep best" -> N restarts per count, keep the
            best, exactly as the button does.

        Returns the lack-of-fit and the fitted manager (or (nan, None)).
        """
        # The sweeps' effort is set by their own "Restarts per component count"
        # control, NOT by the main Run's N. Mirroring a 100-restart run at every
        # component count meant ~900 fits and took minutes; these plots only need
        # to be good enough to pick a component count.
        n_runs = self._sweep_runs_spin.value()
        common = dict(
            n_components=n,
            # Use EXACTLY the settings the real Run uses — same iteration budget,
            # same convergence tolerance.
            #
            # This previously forced tol=0.0 ("never stop early") on the theory
            # that every component count should be pushed to the same depth for a
            # fair comparison. That was a bad trade: it made every restart grind
            # through the full iteration budget (~100 iterations) when the real
            # Run converges in ~10, so each sweep point cost ~10x what the
            # equivalent Run costs. With 100 restarts x 9 component counts that
            # turned a ~6 s job into ~60 s PER COMPONENT COUNT — minutes for one
            # plot. The fairness it bought is not needed here anyway: the
            # restarts themselves (best-of-N) already guard against a single run
            # stopping at a bad spot, which was the real worry.
            max_iterations=s['max_iterations'], tol=s.get('tol', 0.01),
            c_nonneg=s['c_nonneg'], st_nonneg=s['st_nonneg'],
            normalize_spectra=s['normalize_spectra'], closure=s['closure'],
            references=s.get('references'),
            fix_references=s.get('fix_references', False),
        )
        if n_runs > 1:
            best_lof, best_m = float('inf'), None
            for r in range(int(n_runs)):
                if progress is not None and progress.wasCanceled():
                    return float('nan'), None
                if progress is not None:
                    progress.setLabelText(
                        f'{base_label} ({n} components, run {r + 1}/{n_runs})')
                    QApplication.processEvents()
                m, ok = self.controller.compute_trial(
                    self._fit_spectra(), init='random', random_state=r, **common)
                if ok and m.lof < best_lof:
                    best_lof, best_m = m.lof, m
            if best_m is None:
                return float('nan'), None
            return best_lof, best_m
        m, ok = self.controller.compute_trial(
            self._fit_spectra(), init=s['init'], random_state=42, **common)
        return (m.lof if ok else float('nan')), (m if ok else None)

    def _compute_elbow_data(self, n_max, s):
        from PyQt5.QtWidgets import QApplication, QProgressDialog

        ns = list(range(2, n_max + 1))
        lofs = []

        progress = QProgressDialog('Computing elbow plot…', 'Cancel', 0, len(ns), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle('MCR-ALS')
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        for i, n in enumerate(ns):
            if progress.wasCanceled():
                progress.close()
                return None, None
            progress.setLabelText(f'Computing elbow plot… ({n} components)')
            progress.setValue(i)
            QApplication.processEvents()
            lof, _m = self._sweep_trial(n, s, progress, 'Computing elbow plot…')
            if progress.wasCanceled():
                progress.close()
                return None, None
            lofs.append(lof)
        progress.setValue(len(ns))
        progress.close()
        return ns, lofs

    # ------------------------------------------------------------------ #
    # Export components to spectra list                                    #
    # ------------------------------------------------------------------ #

    def _set_warning_text(self, text):
        """Warnings used to be rendered as a large block of red text in the
        left panel, which pushed the actual controls off-screen and made the
        panel feel like a wall of text. The information is genuinely valuable,
        so it isn't discarded — it's collapsed to a single compact warning
        BUTTON. The button states how many warnings there are; clicking it
        opens the full text in a scrollable dialog."""
        self._warning_text = text
        n = text.count('\u26a0') + 1 if text else 0
        label = ('\u26a0  1 warning — click for details' if n <= 1
                 else f'\u26a0  {n} warnings — click for details')
        self._neg_warn.setText(label)
        self._neg_warn.setVisible(True)

    def _clear_warning_text(self):
        self._warning_text = ''
        self._neg_warn.setVisible(False)

    def _show_warning_details(self):
        """Full warning text, in a scrollable dialog — triggered by the
        compact warning button."""
        text = getattr(self, '_warning_text', '')
        if not text:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle('Warnings')
        box.setText('The last run produced the following warning(s):')
        box.setDetailedText(text)
        box.setInformativeText(text)
        box.exec_()

    def _show_export_components_dialog(self):
        if self._mgr is None or self._mgr.ST is None:
            QMessageBox.warning(self, 'No results', 'Run MCR-ALS first.')
            return
        dlg = _ExportComponentsDialog(self, self._mgr.n_components, 'MCR-ALS')
        if dlg.exec_() == QDialog.Accepted:
            indices = dlg.selected_indices()
            if not indices:
                QMessageBox.warning(self, 'Nothing Selected',
                                     'Select at least one component to export.')
                return
            count = self.controller.export_components_to_main_list(
                dlg.base_label(), self.spectra, which=indices)
            QMessageBox.information(self, 'Exported',
                                     f'{count} spectrum(s) added to the main spectrum list.')

    # ------------------------------------------------------------------ #
    # Save                                                                 #
    # ------------------------------------------------------------------ #

    def _show_save_dialog(self):
        if self._mgr is None or self._mgr.ST is None:
            QMessageBox.warning(self, 'No results', 'Run MCR-ALS first.')
            return
        dlg = _MCRSaveDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._execute_save(dlg.save_config)

    def _execute_save(self, config):
        from PyQt5.QtWidgets import QMessageBox
        file_path = config['file_path']
        try:
            if config['format'] == 'excel':
                success = self.controller.save_results_excel(
                    file_path,
                    include_spectra=config['include_spectra'],
                    include_concentrations=config['include_concentrations'],
                    include_info=config['include_info'],
                )
            else:
                success = self.controller.save_results_text({
                    'file_path': file_path,
                    'delimiter': config['delimiter'],
                    'precision': config['precision'],
                    'save_separate': config['save_separate'],
                    'include_spectra': config['include_spectra'],
                    'include_concentrations': config['include_concentrations'],
                    'include_info': config['include_info'],
                })

            if success:
                QMessageBox.information(self, 'Save Complete', f'Results saved to:\n{file_path}')
            else:
                QMessageBox.warning(self, 'Save Failed', 'Failed to save MCR-ALS results.')
        except Exception as exc:
            QMessageBox.critical(self, 'Save Failed', str(exc))

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def _show_help(self):
        try:
            from src.help.mcr_als_help import get_mcr_als_help_content, get_mcr_als_help_title
            from src.help.help_window import show_help_window
            show_help_window(self, get_mcr_als_help_title(), get_mcr_als_help_content())
        except Exception:
            QMessageBox.information(self, 'Help', 'Help documentation is not available.')


# ======================================================================
# Export components dialog
# ======================================================================

class _ExportComponentsDialog(QDialog):
    """Pick which resolved pure spectra to add as new spectra in the main
    spectrum list, and a base label to name them from — same idea as Peak
    Fitting's "Add new spectra from individual peaks", but as an explicit
    post-hoc action rather than a pre-run checkbox, since this dialog can
    be re-run many times before the user decides a result is worth
    exporting.

    Labelled "Pure spectrum N" throughout, matching this dialog's own
    "Pure Spectra" tab/Save… naming — NOT "Component N", which is what the
    otherwise-identical NMF dialog uses for the same concept. That
    difference is deliberate (each method's own literature uses different
    vocabulary — chemometrics calls these "pure spectra", NMF/ML calls
    them "components"), so it should stay consistent within THIS dialog's
    own vocabulary rather than borrowing NMF's."""

    def __init__(self, parent, n_components, default_base_label):
        super().__init__(parent)
        self.setWindowTitle('Export Pure Spectra to Spectra List')
        self.setModal(True)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel('Select which resolved pure spectra to add as new spectra:'))
        self._checks = []
        for k in range(n_components):
            cb = QCheckBox(f'Pure spectrum {k + 1}')
            cb.setChecked(True)
            layout.addWidget(cb)
            self._checks.append(cb)

        label_row = QHBoxLayout()
        label_row.addWidget(QLabel('Base label:'))
        self._label_edit = QLineEdit(default_base_label)
        self._label_edit.setToolTip(
            'Each exported spectrum is named "<base label>_MCR<n>",\n'
            'with a numeric suffix added automatically if that name already exists.'
        )
        label_row.addWidget(self._label_edit)
        layout.addLayout(label_row)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def selected_indices(self):
        return [k for k, cb in enumerate(self._checks) if cb.isChecked()]

    def base_label(self):
        return self._label_edit.text().strip() or 'Pure spectrum'


# ======================================================================
# Save dialog
# ======================================================================

class _MCRSaveDialog(QDialog):
    """Save dialog for MCR-ALS results — same pattern as NMF/PCA/SVD's
    Save…: choose format, choose which categories to include, and (for
    text) delimiter/precision/combined-vs-separate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.save_config = {}
        self.setWindowTitle('Save MCR-ALS Results')
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
        self.include_spectra_cb = QCheckBox('Pure Spectra')
        self.include_spectra_cb.setChecked(True)
        include_layout.addWidget(self.include_spectra_cb)
        self.include_conc_cb = QCheckBox('Concentrations')
        self.include_conc_cb.setChecked(True)
        include_layout.addWidget(self.include_conc_cb)
        self.include_info_cb = QCheckBox('Info')
        self.include_info_cb.setChecked(True)
        include_layout.addWidget(self.include_info_cb)
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
            default_name = 'mcr_als_results.xlsx'
        else:
            file_filter = 'Text Files (*.txt);;CSV Files (*.csv);;All Files (*)'
            default_name = 'mcr_als_results.txt'
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save MCR-ALS Results', default_name, file_filter)
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
        if not (self.include_spectra_cb.isChecked() or self.include_conc_cb.isChecked()
                or self.include_info_cb.isChecked()):
            QMessageBox.warning(self, 'Nothing to Save',
                                 'Select at least one of Pure Spectra, Concentrations, or Info.')
            return
        self.save_config = {
            'file_path': self.path_edit.text(),
            'format': 'excel' if self.excel_radio.isChecked() else 'text',
            'include_spectra': self.include_spectra_cb.isChecked(),
            'include_concentrations': self.include_conc_cb.isChecked(),
            'include_info': self.include_info_cb.isChecked(),
            'delimiter': self._get_delimiter(),
            'precision': self.precision_spin.value(),
            'save_separate': self.separate_files_radio.isChecked(),
        }
        self.accept()


class _ComputeWorker(QThread):
    """Runs a single callable on a background thread — see nmf_dialog.py
    for the full rationale."""
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
        self.fig = Figure(constrained_layout=True)
        self.ax  = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fig.patch.set_facecolor('#ffffff')
        self.ax.set_facecolor('#ffffff')

    def leaveEvent(self, event):
        """Deliberate override — see InteractiveSVDAnalysisCanvas.leaveEvent
        in svd_analysis_dialog.py for the full story. Applied from the
        start here, since every visualization-analysis dialog needs it."""
        if self.figure is not None:
            from matplotlib.backend_bases import LocationEvent
            LocationEvent("figure_leave_event", self, *self.mouseEventCoords(),
                          guiEvent=event)._process()

    def draw_tight(self):
        # constrained_layout (set at Figure construction) re-adjusts
        # automatically on every draw — no manual trigger needed, and
        # matplotlib advises against calling tight_layout() alongside it.
        self.draw_idle()
