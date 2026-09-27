# src/views/dialogs/visualization_analysis/nmf_dialog.py
"""
NMF (Non-negative Matrix Factorisation) dialog.

Left panel (fixed 300 px)
    Settings  — n_components, init method, max_iter
    Help | Close

Right panel — QTabWidget
    Components  — overlay of NMF spectral components (H rows)
    Scores      — bar chart or heatmap of W (abundances per spectrum)
    Reconstruction — overlay of original vs reconstructed spectra
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QComboBox, QPushButton, QLabel, QSpinBox, QCheckBox,
    QListWidget, QListWidgetItem, QSizePolicy, QSplitter, QWidget, QTabWidget,
    QLineEdit, QDialogButtonBox, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QScrollArea, QMenu, QAction,
    QTableWidget, QTableWidgetItem,
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


_COMP_NAME = 'NMF'

_COLORS = [
    '#1f77b4','#d62728','#2ca02c','#ff7f0e','#9467bd',
    '#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf',
]

# "Bootstrap Uncertainty..." always reports a 95% band -- same reasoning
# (and same named constant, rather than a literal 0.95) as MCR-ALS's own
# _BOOTSTRAP_CONFIDENCE_LEVEL in mcr_als_dialog.py.
_BOOTSTRAP_CONFIDENCE_LEVEL = 0.95


class NMFDialog(QDialog):

    def __init__(self, parent=None, controller=None, spectra=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle('Non-negative Matrix Factorisation (NMF)')
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
        # successful computation (see _on_nmf_computed / _run_nmf_best_of_n
        # / _compute_elbow_data) — the actual NMFManager instances now live
        # on the controller, not here. Every plot/export method below keeps
        # reading this same self._mgr attribute exactly as before.
        self._mgr      = None

        self._build_ui()
        self._apply_saved_settings()
        # Wire run-affecting controls to the stale-plot marker only after
        # building + restoring settings, so restoring saved settings during
        # construction doesn't blank the plots before the first run.
        # Max-iterations DOES change the sweeps (each trial's convergence
        # depth), so it invalidates them. The component count does NOT —
        # see _mark_results_stale_keep_sweeps.
        self._iter_spin.valueChanged.connect(self._mark_results_stale)
        self._n_spin.valueChanged.connect(self._mark_results_stale_keep_sweeps)
        self._init_combo.currentTextChanged.connect(self._mark_results_stale)
        self._n_spin.valueChanged.connect(self._rebuild_reference_rows)
        # _build_reference_group() built pickers using the DEFAULT component
        # count; _apply_saved_settings() may have restored a different one.
        self._rebuild_reference_rows()
        self._restore_saved_references()
        self._initial_run_pending = True
        self._elbow_cache_key = None
        self._elbow_cache_data = None
        self._fitq_cache_key = None
        self._fitq_cache_data = None

        # Hidden/testing-only ground-truth comparison state (see
        # _show_gt_context_menu). None until the user right-clicks and picks
        # a synthetic benchmark dataset. Never persisted anywhere outside
        # this dialog instance, so it can't leak between runs: this dialog
        # is freshly constructed every time NMF is opened (see
        # NMFController.handle_nmf), so simply not saving this anywhere else
        # is what makes it disappear the moment a new dataset is loaded or
        # the spectra selection changes in the main window and NMF is
        # reopened.
        self._gt = None
        self._gt_tab_widget = None
        self._gt_summary_label = None
        self._gt_report_table = None
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_gt_context_menu)

        self._on_tab_changed(self._tabs.currentIndex())

    def showEvent(self, event):
        super().showEvent(event)

        # Defensive: clear any override cursor(s) still active once this
        # dialog is actually on screen — e.g. a "please wait" cursor left
        # active by whoever opened this modal dialog (it won't get restored
        # by the caller until the dialog closes, since exec_() blocks). See
        # the identical fix in svd_analysis_dialog.py / cluster_analysis_dialog.py
        # / pca_scores_dialog.py's showEvent for the full explanation.
        from PyQt5.QtWidgets import QApplication
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

        if self._initial_run_pending:
            self._initial_run_pending = False
            from PyQt5.QtCore import QTimer
            # No manual QApplication.processEvents() here — see the
            # identical fix (and the reasoning behind it) in
            # svd_analysis_dialog.py, cluster_analysis_dialog.py, and
            # pca_scores_dialog.py's showEvent.
            QTimer.singleShot(50, self._run_nmf)

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left panel's controls (NMF settings, Reference spectra,
        # Concentrations/Reconstruction/Fit quality display options) can
        # add up to more vertical space than a shrunk window has to give —
        # a scroll area lets them stay full-size and readable (rather than
        # getting visually squashed/overlapping) with a scrollbar taking
        # up the slack instead. Matches the same pattern already used in
        # MCR-ALS's dialog.
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
        self._left_layout = layout   # kept for dynamic stretch adjustment — see _on_tab_changed

        grp = QGroupBox('NMF settings')
        gl  = QVBoxLayout(grp)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel('Components:'))
        self._n_spin = QSpinBox()
        self._n_spin.setKeyboardTracking(False)
        self._n_spin.setRange(2, min(20, len(self.spectra)))
        self._n_spin.setValue(min(2, len(self.spectra)))
        self._n_spin.setFixedWidth(60)
        self._n_spin.valueChanged.connect(self._on_settings_changed_for_elbow)
        r1.addWidget(self._n_spin)
        r1.addStretch()
        gl.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel('Initialisation:'))
        self._init_combo = QComboBox()
        self._init_combo.addItems(['nndsvda', 'nndsvd'])
        self._init_combo.currentIndexChanged.connect(self._on_settings_changed_for_elbow)
        self._init_combo.setToolTip(
            'nndsvda : NNDSVD with average fill (recommended)\n'
            'nndsvd  : NNDSVD (sparse components)\n\n'
            'Random initialisation isn\u2019t offered here — a single random\n'
            'attempt is unreliable on its own. Use "Run N times, keep best"\n'
            'below instead, which always uses multiple random restarts.'
        )
        r2.addWidget(self._init_combo)
        r2.addStretch()
        gl.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel('Max iterations:'))
        self._iter_spin = QSpinBox()
        self._iter_spin.setKeyboardTracking(False)
        self._iter_spin.setRange(100, 5000)
        self._iter_spin.setValue(500)
        self._iter_spin.setSingleStep(100)
        self._iter_spin.setFixedWidth(70)
        self._iter_spin.valueChanged.connect(self._on_settings_changed_for_elbow)
        r3.addWidget(self._iter_spin)
        r3.addStretch()
        gl.addLayout(r3)

        self._comp_offset_cb = QCheckBox('Offset components for clarity')
        self._comp_offset_cb.setChecked(True)
        self._comp_offset_cb.setToolTip(
            'Shifts each component vertically on the Components tab so\n'
            'overlapping curves are readable. Turn off to compare component\n'
            'shapes/intensities directly on the same baseline.'
        )
        self._comp_offset_cb.stateChanged.connect(self._refresh_components)
        gl.addWidget(self._comp_offset_cb)

        self._comp_normalize_cb = QCheckBox('Normalize each component to comparable scale')
        self._comp_normalize_cb.setChecked(True)
        self._comp_normalize_cb.setToolTip(
            'The raw absolute scale of H is arbitrary and can differ a lot\n'
            'between components (see Help) \u2014 a weak/degenerate component can\n'
            'end up on a much larger or smaller raw scale than the others,\n'
            'which visually swamps or hides genuinely important components\n'
            'when they all share one y-axis. Checking this rescales each\n'
            'component to the same peak height before plotting, so shapes\n'
            'are comparable regardless of raw magnitude. Turn off to see the\n'
            'actual raw relative scale between components.'
        )
        self._comp_normalize_cb.stateChanged.connect(self._refresh_components)
        gl.addWidget(self._comp_normalize_cb)

        self._comp_show_bootstrap_cb = QCheckBox('Show bootstrap confidence band')
        self._comp_show_bootstrap_cb.setChecked(True)
        self._comp_show_bootstrap_cb.setToolTip(
            'Shades each component with its bootstrap confidence band (see\n'
            '"Bootstrap Uncertainty…" below) once one has been computed for\n'
            'the currently loaded fit. Has no visible effect until then —\n'
            'this is a display toggle, not what triggers the computation.'
        )
        self._comp_show_bootstrap_cb.stateChanged.connect(self._refresh_components)
        gl.addWidget(self._comp_show_bootstrap_cb)

        self.run_btn = QPushButton('▶  Run NMF')
        self.run_btn.setStyleSheet(
            'QPushButton { background-color:#1976D2; color:white; '
            'font-weight:bold; padding:5px 16px; border-radius:4px; }'
            'QPushButton:hover { background-color:#1565C0; }'
        )
        self.run_btn.clicked.connect(self._run_nmf)
        gl.addWidget(self.run_btn)

        self._run_best_btn = QPushButton('Run N times, keep best…')
        self._run_best_btn.setToolTip(
            "Runs several random-seed restarts and keeps whichever finds the\n"
            "lowest lack-of-fit \u2014 the recommended way to check whether a\n"
            "result is reliable (see the \"X/N runs within 10% of best\" report\n"
            "afterward) rather than trusting a single deterministic run alone.\n"
            "Always uses random restarts internally, regardless of the\n"
            "Initialisation dropdown above."
        )
        self._run_best_btn.clicked.connect(self._run_nmf_best_of_n)
        gl.addWidget(self._run_best_btn)

        self._run_bootstrap_btn = QPushButton('Bootstrap Uncertainty…')
        self._run_bootstrap_btn.setToolTip(
            'Estimates how sensitive the CURRENTLY LOADED fit’s components\n'
            'and concentrations are to the actual noise in your data — a\n'
            'residual bootstrap, warm-started from this exact result, so it\n'
            'measures noise sensitivity specifically, not the separate\n'
            'rotational-ambiguity risk "Run N times, keep best" already\n'
            'checks (see Help for the distinction). Run NMF (or "Run N\n'
            'times, keep best") first — this refits around whatever result\n'
            'is currently loaded.'
        )
        self._run_bootstrap_btn.clicked.connect(self._prompt_and_run_bootstrap)
        gl.addWidget(self._run_bootstrap_btn)

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
        self.checkBox_shorten_names.stateChanged.connect(self._refresh_scores)
        self.checkBox_shorten_names.stateChanged.connect(self._rebuild_recon_list)
        self.checkBox_shorten_names.stateChanged.connect(self._refresh_reconstruction)
        self.checkBox_shorten_names.stateChanged.connect(self._refresh_fit_quality)
        layout.addWidget(self.checkBox_shorten_names)

        layout.addWidget(self._build_reference_group())

        # Component selector for reconstruction tab
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

        # Scores tab display options — same pattern (and same widget
        # behavior) as cluster_analysis_dialog's dendrogram options, and
        # identical to MCR-ALS's Concentrations display group.
        self._conc_grp = scores_grp = QGroupBox('Concentrations display')
        cl2 = QVBoxLayout(scores_grp)

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
        self._conc_view_combo.currentTextChanged.connect(self._refresh_scores)
        view_row.addWidget(self._conc_view_combo, 1)
        cl2.addLayout(view_row)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel('Plot type:'))
        self._scores_plot_type_combo = QComboBox()
        self._scores_plot_type_combo.addItems(['Grouped bars', 'Stacked bars', 'Lines'])
        self._scores_plot_type_combo.setCurrentText('Lines')
        self._scores_plot_type_combo.setToolTip(
            'Grouped bars: one bar per component per spectrum, side\n'
            'by side. Stacked bars: each spectrum\u2019s bars stacked into one,\n'
            'total height = sum of all components. Lines: one line per\n'
            'component across spectrum index \u2014 far more readable than bars\n'
            'once you have more than ~30-40 spectra (Lines is the default here).'
        )
        self._scores_plot_type_combo.currentTextChanged.connect(self._refresh_scores)
        type_row.addWidget(self._scores_plot_type_combo)
        cl2.addLayout(type_row)

        self._scores_normalize_cb = QCheckBox('Normalize to 100% per spectrum')
        self._scores_normalize_cb.setChecked(True)
        self._scores_normalize_cb.setToolTip(
            'The raw concentration scale is arbitrary — W @ H is unchanged\n'
            'by multiplying a component\u2019s concentration by k and dividing its\n'
            'spectrum by the same k, so W\u2019s absolute values have no inherent\n'
            'meaning on their own. Checking this rescales each spectrum\u2019s row\n'
            'of W to sum to 100% for DISPLAY only (e.g. "80% component 1,\n'
            '15% component 2, 5% component 3") — easier to read than the raw\n'
            'scale, but does not change the underlying fit or what gets\n'
            'saved/exported.\n\n'
            'Unlike MCR-ALS, this is a display-only approximation, not a\n'
            'genuine fitting constraint — NMF relies on scikit-learn\u2019s fixed\n'
            'algorithm, which doesn\u2019t support closure as part of the fit\n'
            'itself the way this app\u2019s own MCR-ALS implementation does.'
        )
        self._scores_normalize_cb.stateChanged.connect(self._refresh_scores)
        cl2.addWidget(self._scores_normalize_cb)

        self._scores_show_bootstrap_cb = QCheckBox('Show bootstrap confidence band')
        self._scores_show_bootstrap_cb.setChecked(True)
        self._scores_show_bootstrap_cb.setToolTip(
            'Adds error bars from the bootstrap confidence band (see\n'
            '"Bootstrap Uncertainty…" on the left) once one has been\n'
            'computed for the currently loaded fit. Only drawn for the\n'
            '"Lines" and "Grouped bars" plot types — a stacked bar’s\n'
            'segments do not have a single well-defined position to anchor\n'
            'an error bar to. Has no visible effect until a bootstrap has\n'
            'been run.'
        )
        self._scores_show_bootstrap_cb.stateChanged.connect(self._refresh_scores)
        cl2.addWidget(self._scores_show_bootstrap_cb)

        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel('Label rotation:'))
        self._scores_rotation_combo = QComboBox()
        self._scores_rotation_combo.addItems(['90°', '45°', '0°'])
        self._scores_rotation_combo.setCurrentText('45°')
        self._scores_rotation_combo.setFixedWidth(60)
        self._scores_rotation_combo.currentTextChanged.connect(self._refresh_scores)
        rot_row.addWidget(self._scores_rotation_combo)
        rot_row.addStretch()
        cl2.addLayout(rot_row)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel('Label font size:'))
        self._scores_fontsize_combo = QComboBox()
        self._scores_fontsize_combo.addItems(['Auto', '3', '5', '7', '9', '11', '14'])
        self._scores_fontsize_combo.setCurrentText('Auto')
        self._scores_fontsize_combo.setFixedWidth(70)
        self._scores_fontsize_combo.setToolTip(
            'Auto shrinks labels as the number of spectra grows, so they\n'
            'stay legible without the plot becoming unreasonably wide.\n'
            'Choose an explicit size to override that.'
        )
        self._scores_fontsize_combo.currentTextChanged.connect(self._refresh_scores)
        font_row.addWidget(self._scores_fontsize_combo)
        font_row.addStretch()
        cl2.addLayout(font_row)


        trunc_row = QHBoxLayout()
        trunc_row.setContentsMargins(0, 0, 0, 0)
        trunc_row.setSpacing(4)
        self._scores_trunc_combo = QComboBox()
        self._scores_trunc_combo.addItems(['Full label', 'First N chars', 'Last N chars'])
        self._scores_trunc_combo.setCurrentText('Last N chars')
        self._scores_trunc_combo.setToolTip('How to display labels when they are too long')
        self._scores_trunc_combo.setFixedWidth(110)
        trunc_row.addWidget(self._scores_trunc_combo)
        n_label = QLabel('N:')
        n_label.setFixedWidth(20)
        trunc_row.addWidget(n_label)
        self._scores_trunc_n_spin = QSpinBox()
        self._scores_trunc_n_spin.setMinimum(1)
        self._scores_trunc_n_spin.setMaximum(200)
        self._scores_trunc_n_spin.setValue(25)
        self._scores_trunc_n_spin.setFixedWidth(55)
        self._scores_trunc_n_spin.setToolTip('Number of characters (N) to keep from each label')
        self._scores_trunc_n_spin.setKeyboardTracking(False)
        trunc_row.addWidget(self._scores_trunc_n_spin)
        trunc_row.addStretch()
        cl2.addLayout(trunc_row)

        def _on_scores_trunc_changed():
            is_n_mode = self._scores_trunc_combo.currentText() != 'Full label'
            self._scores_trunc_n_spin.setEnabled(is_n_mode and not self._scores_use_index_cb.isChecked())
            self._refresh_scores()

        self._scores_trunc_combo.currentTextChanged.connect(_on_scores_trunc_changed)
        self._scores_trunc_n_spin.valueChanged.connect(self._refresh_scores)

        self._scores_use_index_cb = QCheckBox('Use spectrum index (1, 2, 3, ...) instead of labels')
        self._scores_use_index_cb.setChecked(False)
        self._scores_use_index_cb.setToolTip(
            'Show plain position numbers (1, 2, 3, ...) on the axis/table\n'
            'instead of spectrum labels — handy when labels are long or not\n'
            'meaningful for this view. Truncation below is disabled while\n'
            'this is checked, since there\u2019s nothing left to truncate.')

        def _on_scores_use_index_changed():
            use_index = self._scores_use_index_cb.isChecked()
            self._scores_trunc_combo.setEnabled(not use_index)
            is_n_mode = self._scores_trunc_combo.currentText() != 'Full label'
            self._scores_trunc_n_spin.setEnabled(not use_index and is_n_mode)
            self._refresh_scores()

        self._scores_use_index_cb.stateChanged.connect(_on_scores_use_index_changed)
        cl2.addWidget(self._scores_use_index_cb)

        layout.addWidget(scores_grp)

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
        self._elbow_max_spin.valueChanged.connect(self._on_settings_changed_for_elbow)
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

        # Negative values warning
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
        layout.addWidget(self._neg_warn)

        layout.addStretch(1)
        self._terminal_stretch_index = layout.count() - 1

        save_row = QHBoxLayout()
        send_to_main_btn = QPushButton('Send to main list\u2026')
        send_to_main_btn.setToolTip(
            'Add the resolved component spectra (H) as new spectra in the\n'
            'main spectrum list — the same idea as "Add new spectra from\n'
            'individual peaks" in Peak Fitting.'
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

    def _build_right(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tabs = QTabWidget()
        self._tabs.tabBar().setExpanding(False)
        self._tabs.setStyleSheet(
            "QTabBar::tab { min-width: 100px; padding: 4px 12px; }"
        )
        self._tabs.currentChanged.connect(self._on_tab_changed)

        for title, attr in [
            ('Components',     '_comp_canvas'),
            ('Concentrations', '_scores_canvas'),
            ('Reconstruction', '_recon_canvas'),
            ('Fit Quality',    '_fitq_canvas'),
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
        # The Elbow view now lives inside the Fit Quality tab (selected via
        # the "Show:" dropdown), sharing that tab's single canvas instead of
        # having its own tab. _refresh_elbow() draws here.
        self._elbow_canvas = self._fitq_canvas

        layout.addWidget(self._tabs)
        return w

    # ------------------------------------------------------------------ #
    # Ground-truth comparison (hidden/testing-only — right-click anywhere) #
    # ------------------------------------------------------------------ #
    # For validating/teaching this tool against the shipped synthetic
    # benchmark datasets, which come with known-TRUE pure components and
    # concentrations — never relevant for real data (real spectra have no
    # known-true decomposition to check against), which is why this isn't a
    # button on the Settings panel. See nmf_help.py's "Testing against
    # known ground truth" section.

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
        self._refresh_components()
        self._refresh_scores()
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
        if self._gt is None or self._mgr is None or self._mgr.H is None:
            return None
        try:
            return gtc.build_recovery_report(
                self._mgr.H, self._mgr.x_axis, self._mgr.W,
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
                'No result to compare yet — run NMF first.'
                if self._gt is not None else '')
            return

        rows = report['rows']
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            ['Fitted component', 'Best-matching TRUE component',
             'Spectral similarity', 'Concentration r', 'Concentration RMSE (%)'])
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(f'NMF {row["fitted_index"] + 1}'))
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
        """Dashed ground-truth pure-component curves on the Components tab,
        colour-matched to their best-matching fitted component so a
        component and its ground-truth partner are visually paired. Drawn
        with the same normalisation/offset treatment as the fitted curves
        so the two are directly comparable at a glance.

        A good NMF/MCR-ALS run can recover a component almost exactly, which
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
        if self._scores_normalize_cb.isChecked():
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
        used to make it invisible: Original is drawn opaque at zorder=4,
        so it simply painted over this thinner curve underneath it. Drawn
        above everything else (zorder=6, higher than the zorder=5 residual
        hatch) plus a white halo, this dotted curve now stays visible even
        when it sits exactly on top of Original — which is itself useful
        information (it tells you the "clean" dataset really is clean)."""
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
    # NMF computation                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _match_similarity(A, B):
        """Average best-matched absolute correlation between two sets of
        component rows (e.g. two different H matrices from two separate
        NMF runs) — used to judge whether two SOLUTIONS agree with each
        other structurally, the same one-to-one best-matching logic used
        elsewhere to compare a solution against known ground truth, just
        applied between two candidate solutions instead."""
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

    def _build_reference_group(self):
        """Optional reference-anchoring: assign a known component spectrum
        (from the spectra you selected) to one or more component slots, and
        optionally hold them fixed. Anchoring to what you already know is the
        single most effective way to break NMF's rotational ambiguity — the
        recovered components stop drifting to arbitrary rotations. Mirrors the
        MCR-ALS dialog's panel exactly, so the two tools behave the same."""
        self._ref_grp = grp = QGroupBox('Reference spectra (optional)')
        grp.setCheckable(True)
        grp.setChecked(False)
        grp.setToolTip(
            'Anchor component slots to KNOWN component spectra. Pick, for a\n'
            'component, one of the spectra you selected for this analysis\n'
            '(load your pure reference into the app and include it in the\n'
            'selection). This is the most powerful way to remove the\n'
            'rotational ambiguity — the recovered components stop drifting\n'
            'to arbitrary equally-good-fitting rotations. Measured against\n'
            'known ground truth on the 4-component Raman benchmarks, this\n'
            'took component recovery from ~0.6 to ~1.0 similarity.')
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
            'be fitted — usually not what you want: a previously-measured pure\n'
            'standard is not part of your experimental series, and including it\n'
            'changes the data being decomposed (and hence the result).\n\n'
            'Ticked (default): the chosen reference spectra are used ONLY as\n'
            'known component shapes and are REMOVED from the set of spectra that\n'
            'get fitted — so your concentration profiles cover just your series.\n\n'
            'Untick only if the reference genuinely is one of the samples in your\n'
            'series and you want it fitted too.')
        self._ref_external_cb.stateChanged.connect(self._on_external_refs_changed)
        v.addWidget(self._ref_external_cb)
        grp.toggled.connect(self._mark_results_stale)
        grp.toggled.connect(self._on_external_refs_changed)
        self._ref_fix_cb.stateChanged.connect(self._mark_results_stale)
        self._rebuild_reference_rows()
        return grp

    def _rebuild_reference_rows(self, *_):
        """One reference picker per component slot, synced to the current
        Components count."""
        from PyQt5.QtWidgets import QHBoxLayout
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

    def _reference_settings(self):
        """{component_index: (x, y)} from the pickers, or empty if off."""
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

    def _fit_spectra(self):
        """The spectra that actually get DECOMPOSED — every selected spectrum,
        minus any used as external reference standards (see the checkbox)."""
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
        optional and clamped to its control's own valid range, so an empty
        or partial saved dict leaves the defaults in place and a stale
        value can never crash the dialog. This makes the current_settings
        the controller fetches from last_op_settings actually take effect —
        previously it was stored and never read."""
        s = self._settings
        if not s:
            return
        try:
            if 'n_components' in s:
                v = int(s['n_components'])
                self._n_spin.setValue(max(self._n_spin.minimum(),
                                          min(self._n_spin.maximum(), v)))
            if 'max_iter' in s:
                v = int(s['max_iter'])
                self._iter_spin.setValue(max(self._iter_spin.minimum(),
                                             min(self._iter_spin.maximum(), v)))
            if s.get('init') in ('nndsvda', 'nndsvd'):
                self._init_combo.setCurrentText(s['init'])
        except (TypeError, ValueError):
            pass   # a malformed saved value just falls back to the defaults

    def _run_nmf_best_of_n(self):
        """Run NMF several times with different random seeds and keep
        whichever run is most representative of the near-best group —
        only useful for 'random' initialisation, which gives a different
        (but equally valid) result on every run."""
        if getattr(self, '_nmf_running', False):
            return
        from PyQt5.QtWidgets import QInputDialog
        n_runs, ok = QInputDialog.getInt(
            self, 'Run N times, keep best',
            'Number of runs (different random seeds):',
            value=getattr(self, '_last_n_runs', 10), min=2, max=100)
        if not ok:
            return
        self._last_n_runs = n_runs   # remembered and pre-filled next time
        if getattr(self, '_last_run_mode', None) != ('best_of_n', n_runs):
            self._elbow_cache_key = None
            self._fitq_cache_key = None
        self._last_run_mode = ('best_of_n', n_runs)
        self._nmf_running = True
        self._set_nmf_controls_enabled(False)

        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        n   = self._n_spin.value()
        itr = self._iter_spin.value()
        # Always random here, regardless of what the Initialisation
        # dropdown currently shows — this was a real bug: using
        # self._init_combo.currentText() meant that if a deterministic
        # init (nndsvd/nndsvda) was selected, every single trial ran
        # with the exact same fixed starting point and produced a
        # bit-for-bit identical result every time (random_state has no
        # effect on a deterministic init), making "N runs" silently
        # nothing of the sort — and making every run trivially "agree"
        # with itself, which is a false signal of reliability, not a
        # real one.
        init = 'random'

        progress = QProgressDialog(f'Run 1 of {n_runs}…', 'Cancel', 0, n_runs, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle('NMF')
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        refs, fix_refs = self._reference_settings()
        all_trials = []   # (lof, manager)
        m = None
        for i in range(n_runs):
            if progress.wasCanceled():
                break
            progress.setLabelText(f'Run {i + 1} of {n_runs}…')
            progress.setValue(i)
            QApplication.processEvents()
            m, ok = self.controller.compute_trial(
                self._fit_spectra(), n_components=n, init=init, max_iter=itr, random_state=i,
                references=refs, fix_references=fix_refs)
            if ok:
                all_trials.append((m.lof, m))
        progress.setValue(n_runs)

        try:
            if not all_trials:
                from PyQt5.QtWidgets import QMessageBox
                specific = getattr(m, 'last_error', None) if m is not None else None
                message = specific or 'All runs failed.'
                QMessageBox.warning(self, 'NMF Failed', message)
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
            # components. Confirmed directly on MCR-ALS with a known test
            # case (same underlying phenomenon applies to NMF): the
            # single lowest-LOF run scored worse against ground truth
            # than several runs with LOF only fractions of a percentage
            # point higher. Instead, take the pool of near-best runs and
            # keep whichever is most representative of that pool (highest
            # average structural agreement with the others in it).
            near_best_tol = 0.02   # within 2% of the best LOF
            pool = [(lof, mgr) for lof, mgr in all_trials if lof <= best_lof * (1 + near_best_tol)]

            if len(pool) == 1:
                best_mgr = pool[0][1]
                consensus = None
            else:
                agreement = []
                for i, (_, mgr_i) in enumerate(pool):
                    scores = [self._match_similarity(mgr_i.H, mgr_j.H)
                              for j, (_, mgr_j) in enumerate(pool) if j != i]
                    agreement.append(np.mean(scores))
                best_idx = int(np.argmax(agreement))
                best_mgr = pool[best_idx][1]
                consensus = agreement[best_idx]

            self.controller.adopt(best_mgr)
            self._mgr = self.controller.manager
            warnings = []
            if consensus is not None and consensus < 0.9:
                warnings.append(
                    'The near-best runs do not agree with each other structurally '
                    f'(only {consensus*100:.0f}% average agreement among {len(pool)} runs with '
                    'similarly low lack-of-fit). This is a real sign that this component count '
                    'is not uniquely determined by your data — different, equally-valid-looking '
                    'decompositions exist. Consider fewer components, or treat any single result '
                    '(including this one) with real caution.')
            # Same negative-values check as the plain Run NMF path — it was
            # previously only shown there, so a user who went straight to
            # "Run N times" on signed data never saw the warning that NMF is
            # clipping their negatives to zero.
            has_neg = any(
                np.any(np.asarray(s['y_scale'], dtype=float) < 0)
                for s in self._fit_spectra())
            if has_neg:
                warnings.append(
                    'Spectra contain negative values (e.g. CD data or '
                    'uncorrected baseline). NMF clips these to zero, '
                    'which distorts the decomposition. '
                    'Apply baseline correction first, or use PCA/SVD instead.')
            if self._mgr.x_range_mismatch_warning:
                warnings.append(self._mgr.x_range_mismatch_warning)
            if warnings:
                self._set_warning_text('\n\n⚠  '.join(warnings))
            else:
                self._neg_warn.setVisible(False)
            # How consistent were the random restarts? If most land near
            # the same best LOF, that's real evidence you're close to the
            # true (global) optimum rather than one lucky seed; if they're
            # scattered widely, the fit is poorly determined at this
            # component count regardless of which one you keep.
            n_ok = len(all_lofs)
            close_to_best = sum(1 for v in all_lofs if v <= best_lof * 1.10)
            status = (
                f'{n} components  |  lack of fit: {self._mgr.lof:.3g}%  |  '
                f'best of {n_runs} random runs  |  '
                f'{close_to_best}/{n_ok} runs within 10% of best'
            )
            if consensus is not None:
                status += f'  |  consensus among {len(pool)} near-best runs: {consensus*100:.0f}%'
            self._status_label.setText(status)
            self._status_label.setStyleSheet('font-size:8pt; color:#2E7D32;')
            self._refresh_all()
        finally:
            progress.close()
            self._set_nmf_controls_enabled(True)
            self._nmf_running = False
            QApplication.restoreOverrideCursor()

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
        """The subset of current control values worth remembering between
        dialog sessions — read by the controller after the dialog closes
        and stored in operations_controller.last_op_settings['NMF'], then
        handed back as current_settings next time and restored by
        _apply_saved_settings(). Keys match what _apply_saved_settings
        reads."""
        return dict(
            n_components=self._n_spin.value(),
            init=self._init_combo.currentText(),
            max_iter=self._iter_spin.value(),
            # Reference choices are stored as spectrum LABELS (not the arrays,
            # which are session objects); on reopen a saved label is restored
            # only if a spectrum with that label is actually present, so a
            # stale reference can never attach itself to the wrong data.
            ref_enabled=self._ref_grp.isChecked(),
            ref_labels=[c.currentText() for c in self._ref_combos],
            ref_ids=self._reference_ids(),
            ref_fixed=self._ref_fix_cb.isChecked(),
            ref_external=self._ref_external_cb.isChecked(),
        )

    def _run_nmf(self, *_):
        # Remember HOW this result was produced so the sweeps can reproduce it.
        if getattr(self, '_last_run_mode', None) != ('single', 1):
            self._elbow_cache_key = None
            self._fitq_cache_key = None
        self._last_run_mode = ('single', 1)

        if getattr(self, '_nmf_running', False):
            return  # already running — ignore a second trigger outright
        self._nmf_running = True
        self._set_nmf_controls_enabled(False)
        n    = self._n_spin.value()
        init = self._init_combo.currentText()
        itr  = self._iter_spin.value()

        self._status_label.setText('Running NMF…')

        # Warn if spectra contain significant negative values
        has_neg = any(
            np.any(np.asarray(s['y_scale'], dtype=float) < 0)
            for s in self._fit_spectra())

        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        # Determinate 2-stage progress bar instead of an indeterminate
        # "marquee" one — same fix, and the same reasoning, as Cluster
        # Analysis's Run Clustering button. The NMF fit itself is a single
        # opaque call into scikit-learn with no internal progress hooks, so
        # there's no way to animate continuously *during* it — but there
        # are two real, honest checkpoints either side of it: the fit
        # finishing, and the plots (which can themselves take a noticeable
        # moment to render for many spectra/components) finishing.
        self._nmf_progress = QProgressDialog('Running NMF fit…', None, 0, 2, self)
        self._nmf_progress.setWindowModality(Qt.WindowModal)
        self._nmf_progress.setWindowTitle('NMF')
        self._nmf_progress.setMinimumDuration(0)
        self._nmf_progress.setCancelButton(None)
        self._nmf_progress.setValue(0)
        self._nmf_progress.show()
        # No manual QApplication.processEvents() here — see showEvent.

        # Disabled at the very top of this method (before the progress
        # dialog is even created) so a rapid second click can't slip
        # through while the button was still technically enabled.

        refs, fix_refs = self._reference_settings()

        # self.controller.compute is pure computation (no Qt widget
        # access) — safe to run on the background thread. Its result now
        # lives on self.controller.manager rather than in a manager
        # instance created here.
        self._nmf_worker = _ComputeWorker(
            lambda: self.controller.compute(self._fit_spectra(), n_components=n, init=init, max_iter=itr,
                                            references=refs, fix_references=fix_refs),
            self)
        self._nmf_worker.done.connect(lambda: self._on_nmf_computed(has_neg, n))
        self._nmf_worker.start(QThread.LowPriority)

    def _set_nmf_controls_enabled(self, enabled):
        self.run_btn.setEnabled(enabled)
        self._run_best_btn.setEnabled(enabled)
        self._run_bootstrap_btn.setEnabled(enabled)

    def _prompt_and_run_bootstrap(self):
        """Ask how many bootstrap resamples to run, mirroring "Run N
        times, keep best"'s identical prompt pattern (and
        MCRALSDialog._prompt_and_run_bootstrap almost exactly). Requires
        an already-loaded, successful fit (self._mgr.H/.W/.X_nn all set)
        -- this refits AROUND that specific result to measure its noise
        sensitivity, it does not produce a new fit from scratch the way
        Run/Run-N-times do."""
        if getattr(self, '_nmf_running', False):
            return
        if self._mgr is None or self._mgr.H is None or self._mgr.X_nn is None:
            QMessageBox.information(
                self, 'Bootstrap Uncertainty',
                'Run NMF (or "Run N times, keep best") first —\n'
                'Bootstrap Uncertainty refits around whatever result is\n'
                'currently loaded; it doesn’t produce a new one on its own.')
            return
        # self._mgr can still hold a perfectly valid PRIOR fit while a
        # setting has since been changed without re-running (the red
        # "Settings changed" state) -- refitting around that stale result
        # would silently bootstrap the wrong thing, and _refresh_components/
        # _refresh_scores would then just show the stale placeholder
        # instead of the (successfully computed!) band, since
        # _results_stale is still True. Bug found in practice: confirm the
        # loaded result actually matches current settings before
        # refitting around it.
        if getattr(self, '_results_stale', False):
            QMessageBox.information(
                self, 'Bootstrap Uncertainty',
                'Settings have changed since the last run — press "Run\n'
                'NMF" (or "Run N times, keep best") first so the loaded\n'
                'result matches the current settings, then run Bootstrap\n'
                'Uncertainty around that.')
            return
        from PyQt5.QtWidgets import QInputDialog
        n_resamples, ok = QInputDialog.getInt(
            self, 'Bootstrap Uncertainty',
            'Number of bootstrap resamples:',
            value=getattr(self, '_last_n_bootstrap', 30), min=5, max=500)
        if not ok:
            return
        self._last_n_bootstrap = n_resamples   # remembered and pre-filled next time
        self._run_bootstrap_uncertainty(n_resamples)

    def _run_bootstrap_uncertainty(self, n_resamples):
        """Residual bootstrap, warm-started from self._mgr's own
        converged fit -- see NMFController.compute_bootstrap_uncertainty
        for the actual method, and the Developer Guide's "NMF Bootstrap
        Uncertainty" section for the full reasoning (including why every
        replicate is refit through the hand-written multiplicative-update
        loop regardless of which algorithm the reference fit itself used).
        Deliberately a plain sequential loop with a real, cancellable
        QProgressDialog -- the SAME pattern "Run N times, keep best" uses,
        mirroring MCRALSDialog._run_bootstrap_uncertainty."""
        if getattr(self, '_nmf_running', False):
            return
        self._nmf_running = True
        self._set_nmf_controls_enabled(False)

        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        n    = self._n_spin.value()
        init = self._init_combo.currentText()
        itr  = self._iter_spin.value()
        refs, fix_refs = self._reference_settings()

        progress = QProgressDialog(
            f'Bootstrap resample 1 of {n_resamples}…', 'Cancel', 0, n_resamples, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle('NMF')
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        def _on_progress(b, n_total):
            progress.setLabelText(f'Bootstrap resample {b + 1} of {n_total}…')
            progress.setValue(b)
            QApplication.processEvents()

        try:
            result = self.controller.compute_bootstrap_uncertainty(
                self._mgr, n_components=self._mgr.n_components,
                init=init, max_iter=itr,
                n_resamples=n_resamples,
                confidence_level=_BOOTSTRAP_CONFIDENCE_LEVEL,
                random_state=None,
                references=refs, fix_references=fix_refs,
                progress_callback=_on_progress,
                cancel_check=progress.wasCanceled)
            progress.setValue(n_resamples)

            if result is None:
                QMessageBox.warning(
                    self, 'Bootstrap Uncertainty',
                    self._mgr.last_error or 'All bootstrap resamples failed.')
                self._status_label.setText(
                    '⚠  Bootstrap uncertainty failed — see message above.')
                self._status_label.setStyleSheet('font-size:8pt; color:#C62828;')
                return

            pct = int(round(_BOOTSTRAP_CONFIDENCE_LEVEL * 100))
            msg = (f'Bootstrap uncertainty: {pct}% confidence band from '
                   f'{result["n_resamples_used"]}/{result["n_resamples_requested"]} '
                   f'resamples')
            if result['n_failed']:
                msg += f' ({result["n_failed"]} refit failed and were skipped)'
            self._status_label.setText(msg)
            self._status_label.setStyleSheet('font-size:8pt; color:#2E7D32;')
            self._refresh_components()
            self._refresh_scores()
        finally:
            self._set_nmf_controls_enabled(True)
            self._nmf_running = False
            QApplication.restoreOverrideCursor()

    def _on_nmf_computed(self, has_neg, n):
        try:
            ok = self._nmf_worker.result
            thread_error = self._nmf_worker.error
            mgr = self.controller.manager

            if thread_error is not None or not ok:
                from PyQt5.QtWidgets import QMessageBox
                specific = getattr(mgr, 'last_error', None)
                message = str(thread_error) if thread_error is not None else (
                    specific or
                    'NMF failed. Check that spectra have the same x-grid '
                    'and all values are finite.'
                )
                QMessageBox.warning(self, 'NMF Failed', message)
                self._status_label.setText('⚠  NMF failed — see message above.')
                self._status_label.setStyleSheet('font-size:8pt; color:#C62828;')
                return

            self._mgr = mgr
            self._nmf_progress.setLabelText('Rendering plots…')
            self._nmf_progress.setValue(1)

            warnings = []
            if has_neg:
                warnings.append(
                    'Spectra contain negative values (e.g. CD data or '
                    'uncorrected baseline). NMF clips these to zero, '
                    'which distorts the decomposition. '
                    'Apply baseline correction first, or use PCA/SVD instead.')
            if self._mgr.x_range_mismatch_warning:
                warnings.append(self._mgr.x_range_mismatch_warning)
            if warnings:
                self._set_warning_text('\n\n⚠  '.join(warnings))
            else:
                self._neg_warn.setVisible(False)

            converge_note = '' if self._mgr.converged else '  |  did not converge'
            self._status_label.setText(
                f'{n} components  |  '
                f'lack of fit: {self._mgr.lof:.3g}%  |  '
                f'{self._mgr.iterations_used} iterations{converge_note}'
            )
            self._status_label.setToolTip(
                'Lack of fit (LOF) = 100 \u00d7 sqrt(sum((X \u2212 WH)\u00b2) / sum(X\u00b2)).\n\n'
                'A percentage of the total signal magnitude left unexplained by\n'
                'the model — 0% would be a perfect fit. Same formula and meaning\n'
                'as MCR-ALS\'s own lack-of-fit, so the two are directly comparable.\n'
                'There\'s no universal "good" threshold; what matters is comparing\n'
                'this number across different component counts (see the Elbow tab)\n'
                'on the SAME dataset, and looking for where adding more components\n'
                'stops reducing it meaningfully.'
            )
            self._status_label.setStyleSheet('font-size:8pt; color:#2E7D32;')
            # Plotting for many spectra/components can itself take several
            # seconds (matplotlib rendering many lines/fills), which used
            # to happen AFTER the progress dialog had already closed —
            # closing it only now, in the finally block, means it stays
            # visible for the actual full wait, not just the model fit.
            self._refresh_all()
            self._nmf_progress.setValue(2)
        finally:
            self._nmf_progress.close()
            self._set_nmf_controls_enabled(True)
            self._nmf_running = False
            from PyQt5.QtWidgets import QApplication
            QApplication.restoreOverrideCursor()

    def _draw_stale(self, canvas):
        """Blank a result canvas with a clear 're-run' message so a stale
        plot is never mistaken for a result of the current settings."""
        ax = canvas.ax
        ax.clear()
        ax.text(0.5, 0.5, 'Settings changed —\npress \u201cRun NMF\u201d to update',
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
        """Called when a setting that changes the actual fit (components,
        initialisation, iterations) is edited without re-running. Blanks
        every result plot and drops the cached sweeps so the user never
        sees a plot that doesn't match the current settings."""
        if getattr(self, '_suppress_stale', False):
            return
        self._results_stale = True
        if invalidate_sweeps:
            self._elbow_cache_key = None
            self._elbow_cache_data = None
            self._fitq_cache_key = None
            self._fitq_cache_data = None
        for canvas in (self._comp_canvas, self._scores_canvas, self._recon_canvas,
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
        self._refresh_components()
        self._refresh_scores()
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
            self._refresh_fitq_current_run()
        elif watching_fitq:
            # You're actively looking at a "vs component count" view right
            # now — recompute immediately rather than showing a placeholder.
            self._refresh_fit_quality()
        # else: an expensive "vs component count" view that isn't visible —
        # leave it; it recomputes on its own next time you switch to it.

    def _on_tab_changed(self, idx):
        tab = self._tabs.tabText(idx)
        self._rc_grp.setVisible(tab == 'Reconstruction')
        self._conc_grp.setVisible(tab == 'Concentrations')
        self._fitq_grp.setVisible(tab == 'Fit Quality')
        # Give ALL extra vertical space to the Reconstruction spectrum
        # list when it's the visible tab, otherwise to the dead space
        # just above Send/Save instead — see the identical fix (and full
        # reasoning) in mcr_als_dialog.py's _on_tab_switched_refresh.
        rc_idx = self._left_layout.indexOf(self._rc_grp)
        is_recon = (tab == 'Reconstruction')
        self._left_layout.setStretch(rc_idx, 1 if is_recon else 0)
        self._left_layout.setStretch(self._terminal_stretch_index, 0 if is_recon else 1)
        if tab == 'Fit Quality':
            self._refresh_fit_quality()
            return
        if self._mgr is None:
            return
        if tab == 'Components':    self._refresh_components()
        elif tab == 'Concentrations': self._refresh_scores()
        elif tab == 'Reconstruction': self._refresh_reconstruction()

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

    def _on_settings_changed_for_elbow(self, *_):
        """'Max components to test' changed. The two 'vs component count'
        views are lazy (only computed when actually viewed); if one is the
        tab currently on screen, update it live. Doesn't depend on
        self._mgr (each runs its own independent sweep)."""
        tab = self._tabs.tabText(self._tabs.currentIndex())
        if tab == 'Fit Quality' and not self._fitq_mode_combo.currentText().startswith('Per spectrum'):
            self._refresh_fit_quality()

    # ------------------------------------------------------------------ #
    # Components plot                                                       #
    # ------------------------------------------------------------------ #

    def _refresh_components(self, *_):
        if getattr(self, '_results_stale', False):
            self._draw_stale(self._comp_canvas); return
        if self._mgr is None or self._mgr.H is None:
            return
        ax = self._comp_canvas.ax
        ax.clear()

        H = self._mgr.H          # (n_comp × n_wl)
        x = self._mgr.x_axis
        n = H.shape[0]
        use_offset = self._comp_offset_cb.isChecked()
        use_normalize = self._comp_normalize_cb.isChecked()

        if use_normalize:
            curves = []
            for k in range(n):
                peak = np.max(np.abs(H[k]))
                curves.append(H[k] / peak if peak > 0 else H[k])
        else:
            curves = [H[k] for k in range(n)]

        offset_step = (max(np.max(np.abs(c)) for c in curves) * 1.1 if n > 1 else 0.0) \
            if use_offset else 0.0

        # Bootstrap confidence band (see "Bootstrap Uncertainty..." and
        # NMFController.compute_bootstrap_uncertainty): drawn BEHIND each
        # component's own curve, in the SAME already-offset/normalized
        # display units the curve itself uses, so the shading visually
        # lines up with what's actually plotted rather than the raw H
        # scale. Mirrors MCRALSDialog._refresh_spectra's band exactly.
        br = self._mgr.bootstrap_result
        show_band = br is not None and self._comp_show_bootstrap_cb.isChecked()

        for k in range(n):
            color = _COLORS[k % len(_COLORS)]
            ev    = self._mgr.explained_variance[k]
            if show_band:
                lower_k = br['H_lower'][k]
                upper_k = br['H_upper'][k]
                if use_normalize:
                    peak = np.max(np.abs(H[k]))
                    if peak > 0:
                        lower_k = lower_k / peak
                        upper_k = upper_k / peak
                ax.fill_between(x, lower_k + k * offset_step, upper_k + k * offset_step,
                                color=color, alpha=0.20, linewidth=0, zorder=1)
            ax.plot(x, curves[k] + k * offset_step, color=color, lw=1.2, zorder=2,
                    label=f'NMF {k+1}  ({ev:.1f} %)')
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
        title = f'NMF spectral components ({n} components)'
        if show_band:
            pct = int(round(br['confidence_level'] * 100))
            title += f'  — shaded: {pct}% bootstrap CI (n={br["n_resamples_used"]})'
        ax.set_title(title, fontsize=11)
        ax.legend(fontsize=8, loc='best', framealpha=0.7)
        ax.grid(True, linestyle='--', alpha=0.35)
        self._comp_canvas.draw_tight()

    # ------------------------------------------------------------------ #
    # Scores (abundances) plot                                             #
    # ------------------------------------------------------------------ #

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
        if getattr(self, '_scores_use_index_cb', None) is not None and self._scores_use_index_cb.isChecked():
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

    def _refresh_scores(self, *_):
        if getattr(self, '_results_stale', False):
            self._draw_stale(self._scores_canvas); return
        if self._mgr is None or self._mgr.W is None:
            return

        # This can take a genuinely noticeable moment with many
        # spectra/components — up to n_spec * n_comp individual bar
        # patches plus tick-label layout, all in one matplotlib draw call.
        # It can't be threaded (matplotlib's draw() must run on the GUI
        # thread, since it touches the canvas widget directly) or split
        # into real stages (nothing is actually rendered to screen until
        # the single draw_tight() call at the end — a progress bar
        # ticking through the ax.bar() loop above it would have nothing
        # genuine to show, since none of that has painted anything yet).
        # A busy cursor is the honest amount of feedback for a single,
        # unsplittable, main-thread-only render — same reasoning as
        # ClusterAnalysisDialog.on_method_changed for its own
        # single-render views (Spectra, PCA 2D/3D).
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        try:
            ax = self._scores_canvas.ax
            ax.clear()

            W      = self._mgr.W      # (n_spec × n_comp)
            n_comp = W.shape[1]
            n_spec = W.shape[0]
            labels = self._get_display_labels(
                self._mgr.labels, self._scores_trunc_combo, self._scores_trunc_n_spin)

            if self._scores_normalize_cb.isChecked():
                row_sums = W.sum(axis=1, keepdims=True)
                row_sums[row_sums == 0] = 1.0   # avoid div-by-zero for an all-zero row
                W = 100.0 * W / row_sums
                y_label = 'Concentration (% of spectrum total)'
            else:
                y_label = 'Concentration (W)'

            # Table view: same numbers as the plot (incl. normalisation),
            # just readable directly. Switch the stacked widget's page and
            # skip the (pointless) plot draw.
            if self._conc_view_combo.currentText() == 'Table':
                self._populate_conc_table(
                    W, labels, self._scores_normalize_cb.isChecked())
                self._conc_stack.setCurrentIndex(1)
                return
            self._conc_stack.setCurrentIndex(0)

            plot_type = self._scores_plot_type_combo.currentText()
            x = np.arange(n_spec)

            # Bootstrap confidence band (see "Bootstrap Uncertainty..."):
            # drawn as error bars, in the SAME normalized-or-not units the
            # bars/lines above use. Only for Lines and Grouped bars -- a
            # stacked bar's segments don't have a single well-defined
            # position to anchor an error bar to, so it's deliberately
            # skipped there rather than drawn somewhere misleading.
            #
            # Note the normalization here reuses the REFERENCE fit's own
            # row sums (computed above), not each bootstrap replicate's
            # own row sum -- the same intentional display-only
            # simplification as MCRALSDialog._refresh_concentrations; see
            # the Developer Guide for the full caveat.
            br = self._mgr.bootstrap_result
            show_band = (br is not None and self._scores_show_bootstrap_cb.isChecked()
                        and plot_type in ('Lines', 'Grouped bars'))
            if show_band:
                W_lo, W_hi = br['W_lower'], br['W_upper']
                if self._scores_normalize_cb.isChecked():
                    W_lo = 100.0 * W_lo / row_sums
                    W_hi = 100.0 * W_hi / row_sums

            if plot_type == 'Lines':
                for k in range(n_comp):
                    color = _COLORS[k % len(_COLORS)]
                    ev = self._mgr.explained_variance[k]
                    if show_band:
                        yerr_lo = np.clip(W[:, k] - W_lo[:, k], 0, None)
                        yerr_hi = np.clip(W_hi[:, k] - W[:, k], 0, None)
                        ax.errorbar(x, W[:, k], yerr=[yerr_lo, yerr_hi], fmt='none',
                                    ecolor=color, alpha=0.5, capsize=2, zorder=1)
                    ax.plot(x, W[:, k], 'o-', color=color, ms=3, lw=1.2, zorder=2,
                            label=f'NMF {k+1}  ({ev:.1f} %)')
                tick_positions = x
            elif plot_type == 'Stacked bars':
                bottom = np.zeros(n_spec)
                for k in range(n_comp):
                    color = _COLORS[k % len(_COLORS)]
                    ev = self._mgr.explained_variance[k]
                    ax.bar(x, W[:, k], bottom=bottom, color=color, alpha=0.85,
                           label=f'NMF {k+1}  ({ev:.1f} %)')
                    bottom = bottom + W[:, k]
                tick_positions = x
            else:  # Grouped bars (default)
                bar_w = 0.8 / n_comp
                for k in range(n_comp):
                    color = _COLORS[k % len(_COLORS)]
                    ev    = self._mgr.explained_variance[k]
                    bar_x = x + k * bar_w
                    ax.bar(bar_x, W[:, k], width=bar_w, color=color,
                           alpha=0.75, label=f'NMF {k+1}  ({ev:.1f} %)')
                    if show_band:
                        yerr_lo = np.clip(W[:, k] - W_lo[:, k], 0, None)
                        yerr_hi = np.clip(W_hi[:, k] - W[:, k], 0, None)
                        ax.errorbar(bar_x, W[:, k], yerr=[yerr_lo, yerr_hi], fmt='none',
                                    ecolor='#333333', alpha=0.6, capsize=2, zorder=3)
                tick_positions = x + bar_w * (n_comp - 1) / 2

            if self._gt is not None:
                self._draw_gt_overlay_scores(ax, x)

            rotation = int(self._scores_rotation_combo.currentText().replace('\u00b0', ''))
            fontsize_text = self._scores_fontsize_combo.currentText()
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
            title = f'NMF concentration profiles  ({n_spec} spectra)'
            if show_band:
                pct = int(round(br['confidence_level'] * 100))
                title += f'  — error bars: {pct}% bootstrap CI (n={br["n_resamples_used"]})'
            ax.set_title(title, fontsize=11)
            ax.legend(fontsize=8, loc='best', framealpha=0.7)
            ax.grid(True, axis='y', linestyle='--', alpha=0.35)
            self._scores_canvas.draw_tight()
        finally:
            QApplication.restoreOverrideCursor()

    # ------------------------------------------------------------------ #
    # Reconstruction plot                                                  #
    # ------------------------------------------------------------------ #

    def _refresh_reconstruction(self, *_):
        if getattr(self, '_results_stale', False):
            self._draw_stale(self._recon_canvas); return
        if self._mgr is None or self._mgr.W is None:
            return
        idx = self._recon_list.currentRow()
        fitted = self._fit_spectra()
        if idx < 0 or idx >= len(fitted):
            return

        canvas = self._recon_canvas
        canvas.fig.clf()
        # Two stacked panels: the main comparison above, and a dedicated
        # residual sub-panel below at its own y-scale. Residuals are
        # typically much smaller than the original signal, so a plotted
        # residual curve on the SAME axes as the data would be visually
        # indistinguishable from zero — the hatch in the main panel shows
        # WHERE the residual sits relative to the data's own scale, and
        # this sub-panel shows what it actually looks like.
        ax, ax2 = canvas.fig.subplots(
            2, 1, sharex=True, gridspec_kw={'height_ratios': [3, 1], 'hspace': 0.08})
        canvas.ax = ax   # keep .ax pointing at the main panel, matching every other tab

        s      = fitted[idx]
        x      = self._mgr.x_axis
        y_orig = np.asarray(s['y_scale'], dtype=float)
        if len(y_orig) != len(x):
            _sx, _sy = _ascending_xy(s['x_scale'], y_orig)
            y_orig = np.interp(x, _sx, _sy)

        # Reconstruction: W[idx] @ H + offset. The manager subtracts a
        # constant (self._mgr.offset) before fitting, since NMF requires
        # non-negative input — without adding it back, the reconstruction
        # sits at the shifted scale while the original spectrum stays at
        # its real scale, making the residual look enormous even when the
        # fit itself is reasonable.
        y_recon = self._mgr.W[idx] @ self._mgr.H + self._mgr.offset

        ax.plot(x, y_orig,  color='#111', lw=1.4, label='Original', zorder=4)
        ax.plot(x, y_recon, color='#C62828', lw=1.0, ls='--',
                label='Reconstructed', zorder=3)
        if self._gt is not None:
            self._draw_gt_overlay_reconstruction(ax, x, s['label'])
        # Grey hatch, drawn on top of everything (zorder=5) — Residual's
        # old solid red fill was nearly the same colour as one of the
        # component fills below (#C62828 vs #d62728), so a dominant
        # component's fill visually swallowed the actual (correctly thin)
        # residual sliver underneath it. A hatch pattern in a colour that
        # doesn't appear anywhere else can't be confused with anything.
        if not self._recon_curves_only_cb.isChecked():
            ax.fill_between(x, y_orig, y_recon, facecolor='none', edgecolor='#555',
                            hatch='///', linewidth=0.0, label='Residual region', zorder=5)

        # Stacked component contributions — genuinely stacked on top of one
        # another (each starts where the previous ended), beginning from the
        # offset baseline, so the top of the stack lands exactly on the
        # reconstruction line (offset + sum_k W[idx,k]*H[k] = offset + W@H).
        # This matches the MCR-ALS Reconstruction tab and makes the additive
        # decomposition visible: the coloured bands literally add up to the
        # reconstructed spectrum. (They previously all started from the same
        # offset baseline and overlapped, so the bands did not sum to the
        # reconstruction and the tallest single component — not the total —
        # set the visible height.)
        if not self._recon_curves_only_cb.isChecked():
            bottom = np.full_like(x, self._mgr.offset, dtype=float)
            for k in range(self._mgr.n_components):
                contrib = self._mgr.W[idx, k] * self._mgr.H[k]
                # alpha 0.55 + solid edge so component k is the same colour
                # here as on the Components / Concentrations tabs.
                _c = _COLORS[k % len(_COLORS)]
                ax.fill_between(x, bottom, bottom + contrib,
                                alpha=0.55, color=_c,
                                edgecolor=_c, linewidth=0.8,
                                label=f'NMF {k+1} contribution', zorder=1)
                bottom = bottom + contrib

        ax.set_ylabel('Intensity', fontsize=10)
        ax.set_title(
            f'Reconstruction: {self._maybe_shorten(s["label"])[-40:]}', fontsize=10)
        ax.legend(fontsize=7, loc='best', framealpha=0.7,
                  ncol=max(1, (self._mgr.n_components + 2) // 3))
        ax.grid(True, linestyle='--', alpha=0.35)
        ax.tick_params(labelbottom=False)

        residual = y_orig - y_recon
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
        n_spec = mgr.W.shape[0]
        rel_residual = np.full(n_spec, np.nan)
        for i, s in enumerate(spectra):
            y = np.asarray(s['y_scale'], dtype=float)
            x = np.asarray(s['x_scale'], dtype=float)
            _sx, _sy = _ascending_xy(x, y)
            original = np.interp(x_ref, _sx, _sy) if len(y) != len(x_ref) else y
            reconstructed = mgr.W[i] @ mgr.H + mgr.offset
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
        if self._mgr is None or self._mgr.W is None:
            return
        ax = self._fitq_canvas.ax
        ax.clear()

        n_spec = self._mgr.W.shape[0]
        rel_residual = self._relative_residuals(self._mgr, self._fit_spectra())

        labels = [self._maybe_shorten(s['label'])[-25:] for s in self._fit_spectra()]
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
        reconstruction error can). Genuinely different information from
        the Elbow tab: reconstruction error is dominated by whichever
        spectra have the largest absolute residuals, while this reflects
        how the TYPICAL spectrum fits — the two can legitimately disagree,
        and that disagreement itself is informative (see Help).

        Only the point at your actual current component count (marked in
        green) is guaranteed to match the "Per spectrum" view's own
        reported median exactly — it reuses that real result directly.
        Every OTHER point is a separate trial run, which can genuinely
        differ from what a real "Run" at that count would show; this
        isn't a bug, see Help for why.
        """
        if not self.spectra or len(self.spectra) < 3:
            return
        n_max = min(self._elbow_max_spin.value(), len(self.spectra) - 1)
        init  = self._init_combo.currentText()
        itr   = self._iter_spin.value()
        cache_key = ('fitq', n_max, init, itr, len(self.spectra))

        if cache_key == self._fitq_cache_key and self._fitq_cache_data is not None:
            ns, medians = self._fitq_cache_data
        else:
            ns, medians = self._compute_fitq_vs_components_data(n_max, init, itr)
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

    def _compute_fitq_vs_components_data(self, n_max, init, itr):
        from PyQt5.QtWidgets import QApplication, QProgressDialog

        ns = list(range(2, n_max + 1))
        medians = []
        current_mgr_n = self._mgr.n_components if (self._mgr is not None and self._mgr.W is not None) else None

        progress = QProgressDialog('Computing median fit quality…', 'Cancel', 0, len(ns), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle('NMF')
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
            # For the component count the current run actually used, reuse
            # that real result directly rather than a fresh trial —
            # otherwise this point could disagree with the "Per spectrum"
            # view's own reported median at the same n, since a fresh
            # trial here uses a fixed random_state/settings that may not
            # match whatever the current run actually used.
            if n == current_mgr_n:
                medians.append(float(np.nanmedian(self._relative_residuals(self._mgr, self._fit_spectra()))))
                continue
            _lof, m = self._sweep_trial(n, init, itr, progress,
                                        'Computing median fit quality…')
            if progress.wasCanceled():
                progress.close()
                return None, None
            medians.append(
                float(np.nanmedian(self._relative_residuals(m, self._fit_spectra())))
                if m is not None else float('nan'))
        progress.setValue(len(ns))
        progress.close()
        return ns, medians

    # Below this lack-of-fit (%), a fit is exact for all practical purposes.
    _NEGLIGIBLE_LOF = 0.05

    def _finish_sweep_axes(self, ax, values, ylabel):
        """Guard the 'vs component count' plots against a misleading artefact:
        on (near-)noise-free data the fit is already EXACT at the correct
        component count, so every value is floating-point noise around zero
        (1e-9 % or smaller). Auto-scaling then stretches that dust across the
        whole axis, producing a dramatic zig-zag that looks like real structure.
        If every value is negligible, pin the y-axis and say so on the plot."""
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
        """Green dot marking the component count you currently have selected,
        plotted as a point ON the curve, using the curve's own value.

        It used to plot the LOADED RUN's own lack-of-fit, which floated off the
        curve whenever the run came from "Run N times, keep best" while the
        sweep did a single trial — two different computations shown on one axis
        as if comparable. The sweep now replays whatever your last Run did (see
        _sweep_trial), so the two agree; the dot sits on the curve and simply
        says "this is where your current component count lands"."""
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

    def _refresh_elbow(self, *_):
        """Lack-of-fit vs component count. The cache key includes the run mode,
        so switching between "Run NMF" and "Run N times, keep best" correctly
        recomputes the curve under the new conditions instead of showing a
        stale curve from the other mode."""
        if not self.spectra or len(self.spectra) < 3:
            return
        n_max = min(self._elbow_max_spin.value(), len(self.spectra) - 1)
        init = self._init_combo.currentText()
        itr = self._iter_spin.value()
        refs, fix_refs = self._reference_settings()
        cache_key = (n_max, init, itr, tuple(sorted(refs.keys())), fix_refs,
                     self._sweep_runs_spin.value())
        if self._elbow_cache_key == cache_key and self._elbow_cache_data is not None:
            ns, errors = self._elbow_cache_data
        else:
            ns, errors = self._compute_elbow_data(n_max, init, itr)
            if ns is None:
                return
            self._elbow_cache_key = cache_key
            self._elbow_cache_data = (ns, errors)

        ax = self._elbow_canvas.ax
        ax.clear()
        self._sweep_values = list(errors)
        ax.plot(ns, errors, 'o-', color='#1565C0', lw=1.5, markersize=5,
                label='Lack of fit at each component count')
        self._mark_current_run_point(ax, ns)
        ax.set_xlabel('Number of components', fontsize=10)
        ax.set_title('Elbow plot \u2014 choose n at the \u201celbow\u201d', fontsize=11)
        ax.set_xticks(ns)
        ax.grid(True, linestyle='--', alpha=0.35)
        self._finish_sweep_axes(ax, errors, 'Lack of fit (%)')
        self._elbow_canvas.draw_tight()

    def _sweep_trial(self, n, init, itr, progress=None, base_label=''):
        from PyQt5.QtWidgets import QApplication
        """Fit at component count *n* the SAME WAY your last Run did — a single
        run after "Run NMF", or N restarts keeping the best after "Run N times,
        keep best".

        The sweep used to always do ONE deterministic run, even when your loaded
        result came from best-of-N (which searches much harder). The curve and
        your result were then computed under different conditions and simply
        weren't comparable — which is what put the green dot off the curve.
        """
        # Effort comes from the sweeps' own "Restarts per component count"
        # control, not from the main Run's N (see the MCR-ALS note: mirroring a
        # 100-restart run at every count meant ~900 fits and took minutes).
        n_runs = self._sweep_runs_spin.value()
        refs, fix_refs = self._reference_settings()
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
                    self._fit_spectra(), n_components=n, init='random',
                    max_iter=itr, random_state=r,
                    references=refs, fix_references=fix_refs)
                if ok and m.lof < best_lof:
                    best_lof, best_m = m.lof, m
            if best_m is None:
                return float('nan'), None
            return best_lof, best_m
        m, ok = self.controller.compute_trial(
            self._fit_spectra(), n_components=n, init=init,
            max_iter=itr, random_state=42,
            references=refs, fix_references=fix_refs)
        return (m.lof if ok else float('nan')), (m if ok else None)

    def _compute_elbow_data(self, n_max, init, itr):
        """Lack-of-fit at every component count from 2..n_max, each computed the
        same way your last Run was (see _sweep_trial)."""
        from PyQt5.QtWidgets import QApplication, QProgressDialog

        ns = list(range(2, n_max + 1))
        errors = []

        progress = QProgressDialog('Computing elbow plot…', 'Cancel', 0, len(ns), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle('NMF')
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
            lof, _m = self._sweep_trial(n, init, itr, progress, 'Computing elbow plot…')
            if progress.wasCanceled():
                progress.close()
                return None, None
            errors.append(lof)
        progress.setValue(len(ns))
        progress.close()
        return ns, errors

    # ------------------------------------------------------------------ #
    # Export                                                              #
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
        if self._mgr is None or self._mgr.H is None:
            QMessageBox.warning(self, 'No results', 'Run NMF first.')
            return
        dlg = _ExportComponentsDialog(self, self._mgr.n_components, 'NMF')
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

    def _show_save_dialog(self):
        if self._mgr is None or self._mgr.H is None:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'No results', 'Run NMF first.')
            return
        dlg = _NMFSaveDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._execute_save(dlg.save_config)

    def _execute_save(self, config):
        """Build the save config and hand off to the controller — actual
        DataFrame construction and file writing now lives in NMFManager
        (save_results_excel/save_results_text), same split as SVD Analysis,
        Cluster Analysis, and PCA Scores & Loadings."""
        from PyQt5.QtWidgets import QMessageBox
        file_path = config['file_path']
        try:
            if config['format'] == 'excel':
                success = self.controller.save_results_excel(
                    file_path,
                    include_components=config['include_components'],
                    include_scores=config['include_scores'],
                    include_info=config['include_info'],
                )
            else:
                success = self.controller.save_results_text({
                    'file_path': file_path,
                    'delimiter': config['delimiter'],
                    'precision': config['precision'],
                    'save_separate': config['save_separate'],
                    'include_components': config['include_components'],
                    'include_scores': config['include_scores'],
                    'include_info': config['include_info'],
                })

            if success:
                QMessageBox.information(self, 'Save Complete', f'Results saved to:\n{file_path}')
            else:
                QMessageBox.warning(self, 'Save Failed', 'Failed to save NMF results.')
        except Exception as exc:
            QMessageBox.critical(self, 'Save Failed', str(exc))

    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def _show_help(self):
        try:
            from src.help.nmf_help import (
                get_nmf_help_content, get_nmf_help_title)
            from src.help.help_window import show_help_window
            show_help_window(self, get_nmf_help_title(),
                             get_nmf_help_content())
        except Exception:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Help',
                                    'Help documentation is not available.')


# ======================================================================
# Export components dialog
# ======================================================================

class _ExportComponentsDialog(QDialog):
    """Pick which resolved components to add as new spectra in the main
    spectrum list, and a base label to name them from — same idea as
    "Add new spectra from individual peaks" in Peak Fitting, but as an
    explicit post-hoc action rather than a pre-run checkbox, since this
    dialog can be re-run many times before the user decides a result is
    worth exporting."""

    def __init__(self, parent, n_components, default_base_label):
        super().__init__(parent)
        self.setWindowTitle('Export Components to Spectra List')
        self.setModal(True)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel('Select which resolved components to add as new spectra:'))
        self._checks = []
        for k in range(n_components):
            cb = QCheckBox(f'Component {k + 1}')
            cb.setChecked(True)
            layout.addWidget(cb)
            self._checks.append(cb)

        label_row = QHBoxLayout()
        label_row.addWidget(QLabel('Base label:'))
        self._label_edit = QLineEdit(default_base_label)
        self._label_edit.setToolTip(
            'Each exported spectrum is named "<base label>_NMF<n>",\n'
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
        return self._label_edit.text().strip() or 'Component'


# ======================================================================
# Reusable plot canvas
# ======================================================================

class _NMFSaveDialog(QDialog):
    """Save dialog for NMF results — same pattern as PCA/SVD's Save…:
    choose format, choose which categories to include, and (for text)
    delimiter/precision/combined-vs-separate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.save_config = {}
        self.setWindowTitle('Save NMF Results')
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
        self.include_components_cb = QCheckBox('Components')
        self.include_components_cb.setChecked(True)
        include_layout.addWidget(self.include_components_cb)
        self.include_scores_cb = QCheckBox('Concentrations')
        self.include_scores_cb.setChecked(True)
        include_layout.addWidget(self.include_scores_cb)
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
            default_name = 'nmf_results.xlsx'
        else:
            file_filter = 'Text Files (*.txt);;CSV Files (*.csv);;All Files (*)'
            default_name = 'nmf_results.txt'
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save NMF Results', default_name, file_filter)
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
        if not (self.include_components_cb.isChecked() or self.include_scores_cb.isChecked()
                or self.include_info_cb.isChecked()):
            QMessageBox.warning(self, 'Nothing to Save',
                                'Select at least one of Components, Scores, or Info.')
            return
        self.save_config = {
            'file_path': self.path_edit.text(),
            'format': 'excel' if self.excel_radio.isChecked() else 'text',
            'include_components': self.include_components_cb.isChecked(),
            'include_scores': self.include_scores_cb.isChecked(),
            'include_info': self.include_info_cb.isChecked(),
            'delimiter': self._get_delimiter(),
            'precision': self.precision_spin.value(),
            'save_separate': self.separate_files_radio.isChecked(),
        }
        self.accept()


class _ComputeWorker(QThread):
    """Runs a single callable on a background thread.

    A long blocking call on the GUI thread freezes Qt's entire event loop —
    including the ability to paint, show, or hide a progress dialog — for
    its whole duration. That's the actual reason the progress indicator
    behaved inconsistently (stuck on screen until an unrelated event forced
    a repaint, or vanishing early, depending on how the platform's
    'unresponsive window' handling happened to kick in for that particular
    run). Running the computation here instead keeps the GUI thread free to
    paint continuously throughout.

    The callable must not touch any Qt widgets — only pure computation
    (manager/controller methods that just crunch numbers) is safe to run
    here; anything that updates the UI must happen in the main-thread slot
    connected to `done`, after this thread finishes.
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
        self.fig = Figure(constrained_layout=True)
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
        QApplication.restoreOverrideCursor() — it assumes matplotlib itself
        is the only thing that ever pushes a global override cursor. That's
        not true here: this dialog pushes its own override cursors (Run
        NMF's progress cursor, Run N times' progress cursor, and
        _refresh_scores' busy cursor for the Scores tab). If the mouse
        happens to be over this canvas while any of those is active,
        matplotlib's leaveEvent pops it early and desyncs the cursor stack
        — visible as a "busy" cursor that lingers regardless of actual
        state and only clears the next time the mouse crosses this canvas
        again. Reimplement the same hover-leave notification without the
        blind cursor pop. (Same fix as the other three visualization
        dialogs' canvases — see InteractiveSVDAnalysisCanvas.leaveEvent in
        svd_analysis_dialog.py for the full story.)
        """
        if self.figure is not None:
            from matplotlib.backend_bases import LocationEvent
            LocationEvent("figure_leave_event", self, *self.mouseEventCoords(),
                          guiEvent=event)._process()

    def draw_tight(self):
        # constrained_layout (set at Figure construction) re-adjusts
        # automatically on every draw — no manual trigger needed, and
        # matplotlib advises against calling tight_layout() alongside it.
        self.draw_idle()
