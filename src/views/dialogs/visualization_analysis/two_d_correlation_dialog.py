# src/views/dialogs/visualization_analysis/two_d_correlation_dialog.py
"""
2D Correlation (2D-COS) dialog.

Left panel (scrollable)
    Settings        — reference spectrum, perturbation values, Run button
    Hetero 2D Correlation — optional cross-dataset mode (see below)
    Display options — equal aspect, noise threshold, linked zoom
    Compare runs    — A/B snapshots (store from current run, or save/load
                      to file for cross-session comparison) and their diff
    Help | Close

Right panel — QTabWidget
    Synchronous          — Phi(v1, v2) contour map, symmetric about the diagonal
    Asynchronous         — Psi(v1, v2) contour map, antisymmetric about the diagonal
    Dynamic spectra      — the mean/first-subtracted spectra actually correlated,
                           shown as an overlay so the maps can be sanity-checked
                           against the data that produced them
    Difference (A - B)   — A minus B, for whichever pair of stored snapshots
    Hetero Synchronous   — Phi_XY(v1, v2), cross-dataset, not necessarily square
    Hetero Asynchronous  — Psi_XY(v1, v2), cross-dataset, not necessarily square

Click either the Synchronous or Asynchronous map to read the exact
correlation values (and an automatic Noda's-rule interpretation) at that
point in the status line below the tabs.
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QComboBox, QPushButton, QLabel, QSpinBox, QCheckBox,
    QSizePolicy, QWidget, QTabWidget, QSplitter,
    QLineEdit, QDialogButtonBox, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QAbstractItemView, QShortcut, QApplication, QListWidget,
)
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from mpl_toolkits.axes_grid1 import make_axes_locatable

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import shorten_spectra_labels, make_shorten_names_checkbox
logger = get_logger(__name__)

_COLORS = [
    '#1f77b4', '#d62728', '#2ca02c', '#ff7f0e', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]


class TwoDCorrelationDialog(QDialog):

    def __init__(self, parent=None, controller=None, spectra=None):
        super().__init__(parent)
        self.setWindowTitle('2D Correlation (2D-COS)')
        self.setMinimumSize(1020, 620)
        self.resize(1280, 760)
        self.setModal(True)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        self.controller = controller
        self.spectra    = list(spectra or [])

        # Display-only "shorten names" map — driven by this dialog's OWN
        # checkBox_shorten_names (built in _build_ui, independent of the
        # main window's shared checkbox of the same name — see
        # label_shortening.make_shorten_names_checkbox). Off by default,
        # so this starts as an identity map; _on_shorten_names_toggled
        # recomputes it and refreshes every consumer once the checkbox
        # exists and is toggled. Selection in every list/combo populated
        # from self.spectra below is read back POSITIONALLY (list row /
        # combo index into self.spectra), never by matching the displayed
        # text back to a spectrum — so it's safe to bake the shortened
        # text directly into these widgets' items rather than needing the
        # main list's paint-only delegate trick. self.spectra itself is
        # never touched.
        self._display_labels = shorten_spectra_labels(self.spectra, False)
        # x_axis/synchronous/asynchronous/dynamic_spectra are owned by
        # self.controller.manager and refreshed from there after every
        # successful computation (see _on_computed) — see the same
        # "thin adapter" note in svd_analysis_dialog.py / nmf_dialog.py.
        self._mgr       = None
        self._perturbation_values = None   # optional, one real value per spectrum
        self._perturbation_label  = None
        self._snapshot_a = None   # {'x_axis','synchronous','asynchronous','desc'} or None
        self._snapshot_b = None
        self._syncing_zoom = False   # re-entrancy guard for linked zoom (see _on_sync_..._changed)

        self._build_ui()
        self._initial_run_pending = True

    def showEvent(self, event):
        super().showEvent(event)
        # Defensive: clear any override cursor(s) still active once this
        # dialog is actually on screen — see the identical fix (and full
        # explanation) in svd_analysis_dialog.py / cluster_analysis_dialog.py
        # / pca_scores_dialog.py / nmf_dialog.py's showEvent.
        from PyQt5.QtWidgets import QApplication
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

        if self._initial_run_pending:
            self._initial_run_pending = False
            from PyQt5.QtCore import QTimer
            # No manual QApplication.processEvents() here — see the
            # identical fix in the other visualization-analysis dialogs'
            # showEvent.
            QTimer.singleShot(50, self._run_analysis)

    def resizeEvent(self, event):
        """Redraw the currently visible tab's canvas after the window is
        resized. matplotlib's own resize-driven redraw keeps the plot
        itself fitting the new size, but our divider-based colorbar axes
        (see _contour_plot) is positioned relative to the main axes' box at
        the time it was last drawn — a plain resize alone doesn't reliably
        force that to recompute, which is why the maps only snapped to the
        correct proportions again after a full Run. Debounced with a short
        timer so a continuous window drag doesn't trigger a redraw on every
        single intermediate size."""
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

    def _make_info_button(self, title, text):
        """A small '?' button that pops up a short explanation on click —
        same orange-square style as the main window's own '?' buttons
        (e.g. next to Legend), for the longer explanations that used to
        sit as permanently-visible paragraphs cluttering this panel."""
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

    def _build_left(self):
        w = QWidget()
        w.setMinimumWidth(260)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        grp = QGroupBox('2D correlation settings')
        gl  = QVBoxLayout(grp)

        gl.addWidget(QLabel('Reference spectrum:'))
        self._ref_combo = QComboBox()
        self._ref_combo.addItems(['Average of all spectra', 'First spectrum', 'Specific spectrum\u2026'])
        self._ref_combo.setToolTip(
            'The dynamic spectra correlated below are each selected spectrum\n'
            'minus this reference. "Average" is the standard choice for most\n'
            '2D-COS work; "First spectrum" or "Specific spectrum" are useful\n'
            'when one of your spectra represents a genuine baseline/blank\n'
            'state (e.g. before a reaction starts) rather than an arbitrary\n'
            'member of the series.'
        )
        self._ref_combo.currentIndexChanged.connect(self._on_ref_mode_changed)
        gl.addWidget(self._ref_combo)

        self._ref_spectrum_combo = QComboBox()
        for s in self.spectra:
            full = s.get('label', '?')
            self._ref_spectrum_combo.addItem(self._display_labels.get(full, full))
        self._ref_spectrum_combo.setVisible(False)
        gl.addWidget(self._ref_spectrum_combo)

        self._perturbation_btn = QPushButton('Perturbation values\u2026')
        self._perturbation_btn.setToolTip(
            'Optionally enter the real perturbation value (temperature, time,\n'
            '...) for each spectrum. Used to sort spectra into the correct\n'
            'order and to detect/correct uneven spacing (see Help). If never\n'
            'set, spectra are assumed to already be in evenly-spaced order as\n'
            'selected — the classic 2D-COS assumption.'
        )
        self._perturbation_btn.clicked.connect(self._show_perturbation_dialog)
        gl.addWidget(self._perturbation_btn)
        self._perturbation_status = QLabel('Perturbation values: not set (using spectrum order)')
        self._perturbation_status.setStyleSheet('font-size:8pt; color:#555;')
        self._perturbation_status.setWordWrap(True)
        gl.addWidget(self._perturbation_status)
        self._resampling_details_btn = QPushButton('Resampling details\u2026')
        self._resampling_details_btn.setToolTip(
            'Shows exactly which original perturbation values were used and\n'
            'what synthetic evenly-spaced grid they were resampled onto.'
        )
        self._resampling_details_btn.clicked.connect(self._show_resampling_details)
        self._resampling_details_btn.setVisible(False)
        gl.addWidget(self._resampling_details_btn)

        self.run_btn = QPushButton('▶  Run 2D Correlation')
        self.run_btn.setStyleSheet(
            'QPushButton { background-color:#1976D2; color:white; '
            'font-weight:bold; padding:5px 16px; border-radius:4px; }'
            'QPushButton:hover { background-color:#1565C0; }'
        )
        self.run_btn.clicked.connect(self._run_analysis)
        gl.addWidget(self.run_btn)

        self._status_label = QLabel('')
        self._status_label.setStyleSheet('font-size:8pt; color:#555;')
        self._status_label.setWordWrap(True)
        gl.addWidget(self._status_label)
        layout.addWidget(grp)

        # ---- Hetero 2D correlation ----
        hetero_grp = QGroupBox('Hetero 2D Correlation')
        hl = QVBoxLayout(hetero_grp)
        hetero_header = QHBoxLayout()
        self._hetero_cb = QCheckBox('Enable hetero mode (correlate two datasets)')
        hetero_header.addWidget(self._hetero_cb)
        hetero_header.addWidget(self._make_info_button(
            'About Hetero 2D Correlation',
            'Standard 2D-COS correlates a dataset against itself. Hetero '
            '2D-COS instead correlates two DIFFERENT datasets\u2019 dynamic '
            'spectra directly against each other \u2014 e.g. IR bands against '
            'Raman bands measured at the same time points \u2014 producing one '
            'combined map.\n\n'
            'Select all spectra for BOTH datasets in the main window before '
            'opening this dialog, then split them between Dataset X and '
            'Dataset Y below (each list is selected independently). X and Y '
            'do NOT need the same x-axis, but do need the same number of '
            'spectra: the i-th selected spectrum in X is paired with the '
            'i-th selected spectrum in Y, in list order (same perturbation '
            'step \u2014 e.g. the same time point measured by two techniques).\n\n'
            'Select at least 3 spectra in each list. Perturbation values / '
            'automatic resampling aren\u2019t supported in hetero mode \u2014 both '
            'lists are assumed already evenly spaced and correctly ordered.'
        ))
        hl.addLayout(hetero_header)
        self._hetero_cb.stateChanged.connect(self._on_hetero_mode_changed)

        self._hetero_controls = QWidget()
        hc = QVBoxLayout(self._hetero_controls)
        hc.setContentsMargins(0, 0, 0, 0)

        lists_row = QHBoxLayout()
        x_col = QVBoxLayout()
        x_col.addWidget(QLabel('Dataset X:'))
        self._hetero_x_list = QListWidget()
        self._hetero_x_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for s in self.spectra:
            full = s.get('label', '?')
            self._hetero_x_list.addItem(self._display_labels.get(full, full))
        x_col.addWidget(self._hetero_x_list)
        self._hetero_ref_x_combo = QComboBox()
        self._hetero_ref_x_combo.addItems(['Average of X spectra', 'First X spectrum'])
        x_col.addWidget(self._hetero_ref_x_combo)
        lists_row.addLayout(x_col)

        y_col = QVBoxLayout()
        y_col.addWidget(QLabel('Dataset Y:'))
        self._hetero_y_list = QListWidget()
        self._hetero_y_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for s in self.spectra:
            full = s.get('label', '?')
            self._hetero_y_list.addItem(self._display_labels.get(full, full))
        y_col.addWidget(self._hetero_y_list)
        self._hetero_ref_y_combo = QComboBox()
        self._hetero_ref_y_combo.addItems(['Average of Y spectra', 'First Y spectrum'])
        y_col.addWidget(self._hetero_ref_y_combo)
        lists_row.addLayout(y_col)
        hc.addLayout(lists_row)

        self._hetero_controls.setVisible(False)
        hl.addWidget(self._hetero_controls)
        layout.addWidget(hetero_grp)

        # ---- Display options ----
        disp_grp = QGroupBox('Display options')
        dl = QVBoxLayout(disp_grp)

        self._equal_aspect_cb = QCheckBox('Equal aspect (\u03bd\u2081 = \u03bd\u2082 scale)')
        self._equal_aspect_cb.setChecked(False)
        self._equal_aspect_cb.setToolTip(
            'Forces both wavenumber axes to the same visual scale, so the\n'
            'diagonal is a true 45\u00b0 line \u2014 off by default because it makes\n'
            'the plot shrink to a sliver if you then zoom to a region that\n'
            'isn\u2019t itself square (which most rectangle-zooms aren\u2019t). Turn\n'
            'this on for the full, un-zoomed view if you want the symmetric\n'
            'look; turn it back off before zooming in on a specific region.'
        )
        self._equal_aspect_cb.stateChanged.connect(self._on_display_option_changed)
        dl.addWidget(self._equal_aspect_cb)

        thresh_row = QHBoxLayout()
        thresh_row.addWidget(QLabel('Noise threshold:'))
        self._noise_threshold_spin = QDoubleSpinBox()
        self._noise_threshold_spin.setRange(0.0, 95.0)
        self._noise_threshold_spin.setSuffix(' %')
        self._noise_threshold_spin.setSingleStep(1.0)
        self._noise_threshold_spin.setValue(0.0)
        self._noise_threshold_spin.setToolTip(
            'Hides correlation values smaller than this percentage of the\n'
            'map\u2019s own maximum \u2014 useful for the asynchronous map, which is\n'
            'often dominated by fine noise that obscures genuine cross peaks.\n'
            '0% shows everything (no filtering).'
        )
        self._noise_threshold_spin.valueChanged.connect(self._on_display_option_changed)
        thresh_row.addWidget(self._noise_threshold_spin)
        dl.addLayout(thresh_row)

        self._link_zoom_cb = QCheckBox('Link zoom (Synchronous \u21c4 Asynchronous)')
        self._link_zoom_cb.setChecked(True)
        self._link_zoom_cb.setToolTip(
            'Zooming or panning one of the two maps applies the same view\n'
            'to the other, so you\u2019re always comparing the same (\u03bd\u2081,\u03bd\u2082)\n'
            'region across both \u2014 useful since interpreting a cross peak\n'
            'means checking its sign in both maps at the same location.'
        )
        dl.addWidget(self._link_zoom_cb)

        # This dialog's OWN, independent Shorten Names toggle \u2014 not tied to
        # the main window's shared checkbox of the same name (see
        # make_shorten_names_checkbox docstring). Off by default.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)
        dl.addWidget(self.checkBox_shorten_names)

        layout.addWidget(disp_grp)

        # ---- Compare runs ----
        cmp_grp = QGroupBox('Compare runs')
        cl = QVBoxLayout(cmp_grp)
        cmp_header = QHBoxLayout()
        cmp_header.addWidget(QLabel('Compare snapshots:'))
        cmp_header.addStretch()
        cmp_header.addWidget(self._make_info_button(
            'About Compare Runs',
            '"Store as A" and "Store as B" each save a full snapshot of the '
            'CURRENT result \u2014 both the Synchronous and Asynchronous maps '
            'together, not one map per button. Use the dropdown below to '
            'choose which of the two you want to see the difference for.\n\n'
            'To see anything other than zero: click Store as A, then change '
            'a setting that actually affects the computation (reference '
            'spectrum, or perturbation values) and click Run again, then '
            'click Store as B. If A and B come from the same run, A \u2212 B is '
            'exactly zero everywhere \u2014 that\u2019s expected, not a bug.\n\n'
            'Save/Load to a file so A and B can come from entirely separate '
            'runs \u2014 e.g. select only heating-phase spectra, run, save as a '
            'file, then reopen this dialog with only cooling-phase spectra '
            'selected, run, and load both files here to compare.'
        ))
        cl.addLayout(cmp_header)
        row_a = QHBoxLayout()
        self._store_a_btn = QPushButton('Store as A')
        self._store_a_btn.setToolTip(
            'Saves the current Synchronous AND Asynchronous maps together as "A".')
        self._store_a_btn.clicked.connect(lambda: self._store_snapshot('a'))
        row_a.addWidget(self._store_a_btn)
        self._save_a_btn = QPushButton('Save A\u2026')
        self._save_a_btn.setToolTip('Save the currently stored A snapshot to a file.')
        self._save_a_btn.clicked.connect(lambda: self._save_snapshot_to_file('a'))
        self._save_a_btn.setEnabled(False)   # nothing to save until A holds something
        row_a.addWidget(self._save_a_btn)
        self._load_a_btn = QPushButton('Load A\u2026')
        self._load_a_btn.setToolTip('Load a previously saved snapshot into slot A.')
        self._load_a_btn.clicked.connect(lambda: self._load_snapshot_from_file('a'))
        row_a.addWidget(self._load_a_btn)
        cl.addLayout(row_a)

        row_b = QHBoxLayout()
        self._store_b_btn = QPushButton('Store as B')
        self._store_b_btn.setToolTip(
            'Saves the current Synchronous AND Asynchronous maps together as "B".\n'
            'Run the analysis again under different settings before clicking this,\n'
            'or A and B will be identical and their difference will be all zero.')
        self._store_b_btn.clicked.connect(lambda: self._store_snapshot('b'))
        row_b.addWidget(self._store_b_btn)
        self._save_b_btn = QPushButton('Save B\u2026')
        self._save_b_btn.setToolTip('Save the currently stored B snapshot to a file.')
        self._save_b_btn.clicked.connect(lambda: self._save_snapshot_to_file('b'))
        self._save_b_btn.setEnabled(False)   # nothing to save until B holds something
        row_b.addWidget(self._save_b_btn)
        self._load_b_btn = QPushButton('Load B\u2026')
        self._load_b_btn.setToolTip('Load a previously saved snapshot into slot B.')
        self._load_b_btn.clicked.connect(lambda: self._load_snapshot_from_file('b'))
        row_b.addWidget(self._load_b_btn)
        cl.addLayout(row_b)

        self._snapshot_status = QLabel('A: (not stored)\nB: (not stored)')
        self._snapshot_status.setStyleSheet('font-size:8pt; color:#555;')
        self._snapshot_status.setWordWrap(True)
        cl.addWidget(self._snapshot_status)
        self._diff_mode_combo = QComboBox()
        self._diff_mode_combo.addItems(['Synchronous difference', 'Asynchronous difference'])
        self._diff_mode_combo.setToolTip(
            'Which of A\u2019s two stored maps (Synchronous or Asynchronous) to\n'
            'subtract B\u2019s matching map from, in the Difference tab.')
        self._diff_mode_combo.currentIndexChanged.connect(self._refresh_difference)
        cl.addWidget(self._diff_mode_combo)
        layout.addWidget(cmp_grp)

        layout.addStretch(1)

        export_btn = QPushButton('Save…')
        export_btn.clicked.connect(self._show_save_dialog)
        layout.addWidget(export_btn)

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
            "QTabBar::tab { min-width: 150px; padding: 4px 12px; }"
        )

        self._tab_canvases = []
        for title, attr in [
            ('Synchronous',     '_sync_canvas'),
            ('Asynchronous',    '_async_canvas'),
            ('Dynamic spectra', '_dyn_canvas'),
            ('Difference (A \u2212 B)', '_diff_canvas'),
            ('Hetero Synchronous', '_hetero_sync_canvas'),
            ('Hetero Asynchronous', '_hetero_async_canvas'),
        ]:
            pw = QWidget()
            pl = QVBoxLayout(pw)
            pl.setContentsMargins(0, 0, 0, 0)
            canvas = _PlotCanvas(pw)
            setattr(self, attr, canvas)
            pl.addWidget(NavigationToolbar(canvas, pw))
            pl.addWidget(canvas)
            self._tabs.addTab(pw, title)
            self._tab_canvases.append(canvas)

        # A canvas sitting in a hidden (non-current) tab page doesn't get
        # its layout recalculated while the window is resized — Qt still
        # resizes the underlying widget, but matplotlib's own resize-driven
        # redraw only actually repaints visible widgets, so the divider-based
        # colorbar axes and tight_layout margins go stale until something
        # forces a fresh draw. That's why a resized tab only looked right
        # again after clicking Run (which redraws every canvas via
        # _contour_plot). Forcing one fresh redraw whenever a tab becomes
        # the current one fixes it immediately on switching tabs instead.
        self._tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self._tabs)

        self._readout_label = QLabel(
            'Click a point on the Synchronous or Asynchronous map to inspect its value.')
        self._readout_label.setStyleSheet('font-size:8pt; color:#555; padding:2px;')
        self._readout_label.setWordWrap(True)
        layout.addWidget(self._readout_label)

        # Linked zoom/pan between Synchronous and Asynchronous is wired up
        # in _refresh_synchronous/_refresh_asynchronous, not here — see the
        # comment there for why connecting the callbacks only once, at
        # dialog-build time, doesn't actually work.

        # Click-to-inspect: report the (v1, v2, intensity) at the clicked
        # point, plus an automatic Noda's-rule reading when both maps are
        # available — reading exact signs off a small color swatch is
        # error-prone; this gives the actual numbers instead.
        self._sync_canvas.mpl_connect('button_press_event', self._on_map_clicked)
        self._async_canvas.mpl_connect('button_press_event', self._on_map_clicked)

        return w

    # ------------------------------------------------------------------ #
    # Linked zoom                                                          #
    # ------------------------------------------------------------------ #

    def _on_sync_xlim_changed(self, ax):
        self._propagate_zoom(self._async_canvas.ax, xlim=ax.get_xlim())

    def _on_sync_ylim_changed(self, ax):
        self._propagate_zoom(self._async_canvas.ax, ylim=ax.get_ylim())

    def _on_async_xlim_changed(self, ax):
        self._propagate_zoom(self._sync_canvas.ax, xlim=ax.get_xlim())

    def _on_async_ylim_changed(self, ax):
        self._propagate_zoom(self._sync_canvas.ax, ylim=ax.get_ylim())

    def _propagate_zoom(self, target_ax, xlim=None, ylim=None):
        if self._syncing_zoom or not self._link_zoom_cb.isChecked():
            return
        self._syncing_zoom = True
        try:
            if xlim is not None:
                target_ax.set_xlim(xlim)
            if ylim is not None:
                target_ax.set_ylim(ylim)
            target_ax.figure.canvas.draw_idle()
        finally:
            self._syncing_zoom = False

    def _on_tab_changed(self, index):
        """Force a fresh tight_layout redraw for whichever tab just became
        visible — see the comment where this is connected, in _build_right,
        for why a canvas sitting in a hidden tab page can otherwise show
        stale geometry after a window resize."""
        if 0 <= index < len(self._tab_canvases):
            self._tab_canvases[index].draw_tight()

    # ------------------------------------------------------------------ #
    # Click-to-inspect                                                     #
    # ------------------------------------------------------------------ #

    def _on_map_clicked(self, event):
        if self._mgr is None or event.inaxes is None or event.xdata is None or event.ydata is None:
            return
        x = self._mgr.x_axis
        j = int(np.argmin(np.abs(x - event.xdata)))   # nearest index to v2 (x-axis)
        i = int(np.argmin(np.abs(x - event.ydata)))   # nearest index to v1 (y-axis)
        v1, v2 = x[i], x[j]

        sync_val = self._mgr.synchronous[i, j] if self._mgr.synchronous is not None else None
        async_val = self._mgr.asynchronous[i, j] if self._mgr.asynchronous is not None else None

        parts = [f'\u03bd\u2081={v1:.4g}, \u03bd\u2082={v2:.4g}']
        if sync_val is not None:
            parts.append(f'\u03a6={sync_val:.4g}')
        if async_val is not None:
            parts.append(f'\u03a8={async_val:.4g}')

        if i == j:
            parts.append('(on the diagonal \u2014 an autopeak, not a cross peak)')
        elif sync_val is not None and async_val is not None:
            # Noda's rule: same sign in both maps -> v1 changes before v2 as
            # the perturbation increases; opposite signs -> v1 changes after
            # v2. Assumes the synchronous autopeak at v1 is positive (the
            # normal case) and perturbation is increasing along the stored
            # spectrum order — both stated here rather than silently assumed.
            async_scale = float(np.max(np.abs(self._mgr.asynchronous))) or 1.0
            if abs(async_val) < 0.05 * async_scale:
                parts.append('\u2192 negligible asynchronous signal: bands change essentially simultaneously')
            elif (sync_val >= 0) == (async_val >= 0):
                parts.append('\u2192 by Noda\u2019s rule: \u03bd\u2081 changes before \u03bd\u2082 (increasing perturbation, positive \u03bd\u2081 autopeak assumed)')
            else:
                parts.append('\u2192 by Noda\u2019s rule: \u03bd\u2081 changes after \u03bd\u2082 (increasing perturbation, positive \u03bd\u2081 autopeak assumed)')

        self._readout_label.setText('  |  '.join(parts))

    # ------------------------------------------------------------------ #
    # Computation                                                          #
    # ------------------------------------------------------------------ #

    def _on_ref_mode_changed(self, *_):
        self._ref_spectrum_combo.setVisible(self._ref_combo.currentIndex() == 2)

    def _on_hetero_mode_changed(self, *_):
        enabled = self._hetero_cb.isChecked()
        self._hetero_controls.setVisible(enabled)
        # Homo-mode-only controls don't apply once hetero mode is active —
        # greyed out rather than hidden, so it's clear they still exist for
        # switching back rather than having disappeared.
        self._ref_combo.setEnabled(not enabled)
        self._ref_spectrum_combo.setEnabled(not enabled)
        self._perturbation_btn.setEnabled(not enabled)
        self.run_btn.setText(
            '\u25b6  Run Hetero 2D Correlation' if enabled else '\u25b6  Run 2D Correlation')

    def _show_perturbation_dialog(self):
        dlg = _PerturbationValuesDialog(
            self, self.spectra, self._perturbation_values, self._perturbation_label,
            display_labels=self._display_labels)
        if dlg.exec_() == QDialog.Accepted:
            self._perturbation_values = dlg.values
            self._perturbation_label = dlg.label
            if self._perturbation_values is None:
                self._perturbation_status.setText('Perturbation values: not set (using spectrum order)')
            else:
                label_part = f' ({self._perturbation_label})' if self._perturbation_label else ''
                self._perturbation_status.setText(
                    f'Perturbation values: set{label_part} \u2014 '
                    f'{min(self._perturbation_values):.4g} to {max(self._perturbation_values):.4g}')

    def _show_resampling_details(self):
        """Show exactly which original values were used and what synthetic
        uniform grid they were resampled onto — requested after the status
        line's one-line "resampled to uniform grid" note wasn't detailed
        enough to see what actually happened."""
        mgr = self._mgr
        if mgr is None or mgr.sorted_perturbation_values is None:
            QMessageBox.information(self, 'Resampling Details',
                                     'No perturbation values were used in the current result.')
            return
        lines = ['Spectrum\tOriginal value\tGrid value used\n' + '-' * 50]
        for label, orig, used in zip(mgr.spectrum_labels, mgr.sorted_perturbation_values,
                                      mgr.uniform_perturbation_values):
            lines.append(f'{self._display_labels.get(label, label)}\t{orig:.6g}\t{used:.6g}')
        if mgr.was_resampled:
            header = (
                'Your perturbation values were not evenly spaced (more than 2% off '
                'the mean spacing), so they were linearly resampled onto the '
                'synthetic, evenly-spaced grid shown below before computing either '
                'correlation map.\n\n'
            )
        else:
            header = (
                'Your perturbation values were already evenly spaced (within 2% of '
                'the mean spacing), so no resampling was needed — "Grid value used" '
                'is identical to "Original value" below.\n\n'
            )
        QMessageBox.information(self, 'Resampling Details', header + '\n'.join(lines))

    def _on_display_option_changed(self, *_):
        """Re-render everything that depends on display-only settings
        (equal aspect, noise threshold) — cheap (no recomputation needed),
        so this applies immediately rather than waiting for the next Run."""
        if self._mgr is not None:
            self._refresh_synchronous()
            self._refresh_asynchronous()
        self._refresh_difference()

    def _refresh_status_label(self):
        """Build/rebuild the '<n> spectra | <n> points | reference: ...'
        success-state status line from self._mgr — factored out of
        _on_computed so _on_shorten_names_toggled can rebuild it too
        (the reference spectrum's name may appear in it via _shortened())
        without duplicating the format string."""
        if self._mgr is None:
            return
        if self._mgr.reference_mode == 'mean':
            ref_desc = 'average'
        else:
            ref_desc = f'spectrum ‘{self._truncate_label(self._shortened(self._mgr.reference_label or "?"))}’'
        resample_note = '  |  resampled to uniform grid' if self._mgr.was_resampled else ''
        self._status_label.setText(
            f'{self._mgr.get_n_spectra()} spectra  |  '
            f'{self._mgr.get_n_points()} points  |  '
            f'reference: {ref_desc}{resample_note}'
        )

    def _on_shorten_names_toggled(self, _state=None):
        """Refresh everything this dialog's own Shorten Names checkbox
        affects. self._display_labels is a one-time-computed map (not a
        live paint-time lookup like the main spectra list's delegate), so
        every consumer built from it needs an explicit rebuild here:
        the Reference spectrum combo and both Hetero dataset lists (item
        text rebuilt in place, selection preserved by position since
        selection is always read back positionally into self.spectra —
        never by matching displayed text), the Dynamic spectra plot's
        legend (via _refresh_dynamic), and the status line's reference
        spectrum name (via _refresh_status_label). The Perturbation
        values / Resampling details popups read self._display_labels
        fresh each time they're opened, so they need no explicit refresh
        here — just an up-to-date map, which this provides."""
        enabled = self.checkBox_shorten_names.isChecked()
        self._display_labels = shorten_spectra_labels(self.spectra, enabled)

        prev_ref_idx = self._ref_spectrum_combo.currentIndex()
        self._ref_spectrum_combo.blockSignals(True)
        self._ref_spectrum_combo.clear()
        for s in self.spectra:
            full = s.get('label', '?')
            self._ref_spectrum_combo.addItem(self._display_labels.get(full, full))
        if 0 <= prev_ref_idx < self._ref_spectrum_combo.count():
            self._ref_spectrum_combo.setCurrentIndex(prev_ref_idx)
        self._ref_spectrum_combo.blockSignals(False)

        for list_widget in (self._hetero_x_list, self._hetero_y_list):
            selected_rows = {list_widget.row(item) for item in list_widget.selectedItems()}
            list_widget.blockSignals(True)
            list_widget.clear()
            for s in self.spectra:
                full = s.get('label', '?')
                list_widget.addItem(self._display_labels.get(full, full))
            for row in selected_rows:
                if 0 <= row < list_widget.count():
                    list_widget.item(row).setSelected(True)
            list_widget.blockSignals(False)

        self._refresh_dynamic()
        self._refresh_status_label()

    def _run_analysis(self, *_):
        if getattr(self, '_running', False):
            return  # already running — ignore a second trigger outright

        if self._hetero_cb.isChecked():
            self._run_hetero_analysis()
            return

        self._running = True
        self.run_btn.setEnabled(False)
        ref_idx = self._ref_combo.currentIndex()
        if ref_idx == 1:
            reference, reference_index = 'first', None
        elif ref_idx == 2:
            reference, reference_index = 'index', self._ref_spectrum_combo.currentIndex()
        else:
            reference, reference_index = 'mean', None

        self._status_label.setText('Running 2D correlation…')

        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        # A single progress dialog, not a staged one — the computation is
        # one matrix multiplication (see TwoDCorrelationManager.compute),
        # a single opaque step with no real intermediate checkpoints to
        # report, same situation as SVD Analysis's "Computing SVD…" dialog.
        self._progress = QProgressDialog('Computing 2D correlation…', None, 0, 0, self)
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setWindowTitle('2D Correlation')
        self._progress.setMinimumDuration(0)
        self._progress.setCancelButton(None)
        self._progress.show()
        # No manual QApplication.processEvents() here — see showEvent.

        self._worker = _ComputeWorker(
            lambda: self.controller.compute_analysis(
                self.spectra, reference=reference, reference_index=reference_index,
                perturbation_values=self._perturbation_values,
                perturbation_label=self._perturbation_label),
            self)
        self._worker.done.connect(self._on_computed)
        self._worker.start(QThread.LowPriority)

    def _run_hetero_analysis(self):
        # QListWidgetItem has no .row() method (unlike QTableWidgetItem) —
        # the row index has to be asked from the owning QListWidget instead.
        spectra_x = [self.spectra[i] for i in sorted(
            self._hetero_x_list.row(it) for it in self._hetero_x_list.selectedItems())]
        spectra_y = [self.spectra[i] for i in sorted(
            self._hetero_y_list.row(it) for it in self._hetero_y_list.selectedItems())]

        if len(spectra_x) < 3 or len(spectra_y) < 3:
            QMessageBox.warning(self, 'Insufficient Selection',
                                 'Select at least 3 spectra for Dataset X and at least '
                                 '3 for Dataset Y (each list is selected independently).')
            return
        if len(spectra_x) != len(spectra_y):
            QMessageBox.warning(
                self, 'Mismatched Selection',
                f'Dataset X has {len(spectra_x)} spectra selected and Dataset Y has '
                f'{len(spectra_y)} — hetero correlation needs the same number in each '
                '(one X spectrum paired with one Y spectrum per perturbation step).')
            return

        self._running = True
        self.run_btn.setEnabled(False)
        reference_x = 'first' if self._hetero_ref_x_combo.currentIndex() == 1 else 'mean'
        reference_y = 'first' if self._hetero_ref_y_combo.currentIndex() == 1 else 'mean'

        self._status_label.setText('Running hetero 2D correlation…')

        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        self._progress = QProgressDialog('Computing hetero 2D correlation…', None, 0, 0, self)
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setWindowTitle('2D Correlation')
        self._progress.setMinimumDuration(0)
        self._progress.setCancelButton(None)
        self._progress.show()

        self._worker = _ComputeWorker(
            lambda: self.controller.compute_hetero_analysis(
                spectra_x, spectra_y, reference_x=reference_x, reference_y=reference_y),
            self)
        self._worker.done.connect(self._on_hetero_computed)
        self._worker.start(QThread.LowPriority)

    def _on_computed(self):
        try:
            ok = self._worker.result
            thread_error = self._worker.error
            manager = self.controller.manager

            if thread_error is not None or not ok:
                specific = getattr(manager, 'last_error', None)
                message = str(thread_error) if thread_error is not None else (
                    specific or '2D correlation failed.'
                )
                QMessageBox.warning(self, '2D Correlation Failed', message)
                self._status_label.setText('⚠  Failed — see message above.')
                self._status_label.setStyleSheet('font-size:8pt; color:#C62828;')
                return

            self._mgr = manager
            self._refresh_status_label()
            self._status_label.setStyleSheet('font-size:8pt; color:#2E7D32;')
            self._resampling_details_btn.setVisible(self._mgr.perturbation_values is not None)
            self._refresh_all()
        finally:
            self._progress.close()
            self.run_btn.setEnabled(True)
            self._running = False
            from PyQt5.QtWidgets import QApplication
            QApplication.restoreOverrideCursor()

    def _on_hetero_computed(self):
        try:
            ok = self._worker.result
            thread_error = self._worker.error
            manager = self.controller.manager

            if thread_error is not None or not ok:
                specific = getattr(manager, 'last_error', None)
                message = str(thread_error) if thread_error is not None else (
                    specific or 'Hetero 2D correlation failed.'
                )
                QMessageBox.warning(self, 'Hetero 2D Correlation Failed', message)
                self._status_label.setText('⚠  Failed — see message above.')
                self._status_label.setStyleSheet('font-size:8pt; color:#C62828;')
                return

            self._mgr = manager
            self._status_label.setText(
                f'Hetero: {len(self._mgr.hetero_labels_x)} paired spectra  |  '
                f'X: {len(self._mgr.hetero_x_axis)} points  |  '
                f'Y: {len(self._mgr.hetero_y_axis)} points'
            )
            self._status_label.setStyleSheet('font-size:8pt; color:#2E7D32;')
            self._refresh_hetero_synchronous()
            self._refresh_hetero_asynchronous()
        finally:
            self._progress.close()
            self.run_btn.setEnabled(True)
            self._running = False
            from PyQt5.QtWidgets import QApplication
            QApplication.restoreOverrideCursor()

    def _refresh_all(self):
        self._refresh_synchronous()
        self._refresh_asynchronous()
        self._refresh_dynamic()
        self._refresh_difference()

    # ------------------------------------------------------------------ #
    # Plots                                                                #
    # ------------------------------------------------------------------ #

    def _contour_plot(self, canvas, x, matrix, title):
        """Shared rendering for the Synchronous/Asynchronous/Difference
        contour maps — a colormap symmetric about zero (so positive and
        negative correlation are visually distinct, the standard 2D-COS
        convention), with the diagonal marked for reference. Takes x
        explicitly (rather than always reading self._mgr.x_axis) since the
        Difference tab plots a comparison between two stored snapshots,
        not necessarily the current self._mgr."""
        ax = canvas.ax
        ax.clear()

        vmax = float(np.max(np.abs(matrix))) or 1.0

        # Noise threshold: zero out anything below the given percentage of
        # this map's own peak magnitude. Zero maps to pure white at the
        # center of the RdBu_r colormap, so this reads as "hidden" without
        # needing NaN/masked-array handling in contourf.
        threshold_frac = self._noise_threshold_spin.value() / 100.0
        if threshold_frac > 0:
            matrix = np.where(np.abs(matrix) < threshold_frac * vmax, 0.0, matrix)

        levels = np.linspace(-vmax, vmax, 21)
        cf = ax.contourf(x, x, matrix, levels=levels, cmap='RdBu_r', extend='both')
        ax.contour(x, x, matrix, levels=levels, colors='#00000022', linewidths=0.4)
        ax.plot([x.min(), x.max()], [x.min(), x.max()], color='#555', lw=0.7, ls='--', alpha=0.6)

        # fig.colorbar(cf, ax=ax) permanently shrinks ax to make room for
        # itself, and that shrink compounds on every redraw — that's fixed
        # below by never passing ax= at all. But reusing a single cax across
        # redraws (clearing it each time rather than recreating it) turned
        # out to have the same problem one level down: with extend='both',
        # each colorbar() call carves the triangular end-caps out of cax's
        # own box, and that shrink compounds too, even though cax is a
        # dedicated axes and ax itself stays untouched. The fix is the same
        # principle applied one level deeper: don't reuse cax across calls —
        # remove it and recreate it (with a fresh divider) every redraw, so
        # each call starts from ax's actual current box rather than from
        # whatever a previous extend='both' call left cax looking like.
        if getattr(canvas, '_cbar_ax', None) is not None:
            canvas._cbar_ax.remove()
        divider = make_axes_locatable(ax)
        canvas._cbar_ax = divider.append_axes('right', size='4%', pad=0.4)
        canvas.fig.colorbar(cf, cax=canvas._cbar_ax, label='Correlation intensity')

        ax.set_xlabel('Wavenumber \u03bd\u2082', fontsize=10)
        ax.set_ylabel('Wavenumber \u03bd\u2081', fontsize=10)
        ax.set_title(title, fontsize=11)
        # Equal aspect is opt-in (see the "Equal aspect" checkbox) rather
        # than always-on — adjustable='box' forces the axes box itself to
        # shrink to a sliver on any zoom whose x/y ranges aren't in the
        # same proportion, which is what almost any rectangle-zoom via the
        # navigation toolbar produces. Leaving it off by default fixed
        # that; this only re-enables it for users who want the symmetric
        # look on the full, un-zoomed view and are aware of the trade-off
        # (see the checkbox's tooltip).
        if self._equal_aspect_cb.isChecked():
            ax.set_aspect('equal', adjustable='box')
        else:
            ax.set_aspect('auto')
        canvas.draw_tight()

    def _refresh_synchronous(self, *_):
        if self._mgr is None or self._mgr.synchronous is None:
            return
        self._contour_plot(self._sync_canvas, self._mgr.x_axis, self._mgr.synchronous,
                            'Synchronous spectrum \u03a6(\u03bd\u2081,\u03bd\u2082)')
        self._reconnect_zoom_link(self._sync_canvas.ax,
                                   self._on_sync_xlim_changed, self._on_sync_ylim_changed)

    def _refresh_asynchronous(self, *_):
        if self._mgr is None or self._mgr.asynchronous is None:
            return
        self._contour_plot(self._async_canvas, self._mgr.x_axis, self._mgr.asynchronous,
                            'Asynchronous spectrum \u03a8(\u03bd\u2081,\u03bd\u2082)')
        self._reconnect_zoom_link(self._async_canvas.ax,
                                   self._on_async_xlim_changed, self._on_async_ylim_changed)

    def _reconnect_zoom_link(self, ax, xlim_handler, ylim_handler):
        """Re-wire the linked-zoom callbacks after a redraw.

        matplotlib's Axes.clear() (called at the top of _contour_plot on
        every redraw) replaces the axes' entire callback registry —
        `self.callbacks = cbook.CallbackRegistry(...)` — which silently
        disconnects anything connected via ax.callbacks.connect() before
        that point. Connecting these once, at dialog-build time (the
        original approach), meant linked zoom appeared to work in theory
        but was actually severed the moment the very first Run populated
        the plot, since that first _contour_plot() call already includes
        an ax.clear(). Reconnecting here, after every redraw, is the fix.
        """
        ax.callbacks.connect('xlim_changed', xlim_handler)
        ax.callbacks.connect('ylim_changed', ylim_handler)

    # ------------------------------------------------------------------ #
    # Hetero plots                                                         #
    # ------------------------------------------------------------------ #

    def _hetero_contour_plot(self, canvas, x_axis, y_axis, matrix, title):
        """Rendering for the Hetero Synchronous/Asynchronous maps — same
        colormap/colorbar/noise-threshold handling as _contour_plot, but
        the matrix isn't necessarily square (Dataset X and Y can have
        different numbers of wavenumber points and different axes
        entirely), so there's no diagonal line and the two axes are
        genuinely independent rather than "the same wavenumber, twice"."""
        ax = canvas.ax
        ax.clear()

        vmax = float(np.max(np.abs(matrix))) or 1.0
        threshold_frac = self._noise_threshold_spin.value() / 100.0
        if threshold_frac > 0:
            matrix = np.where(np.abs(matrix) < threshold_frac * vmax, 0.0, matrix)

        levels = np.linspace(-vmax, vmax, 21)
        cf = ax.contourf(y_axis, x_axis, matrix, levels=levels, cmap='RdBu_r', extend='both')
        ax.contour(y_axis, x_axis, matrix, levels=levels, colors='#00000022', linewidths=0.4)

        if getattr(canvas, '_cbar_ax', None) is not None:
            canvas._cbar_ax.remove()
        divider = make_axes_locatable(ax)
        canvas._cbar_ax = divider.append_axes('right', size='4%', pad=0.4)
        canvas.fig.colorbar(cf, cax=canvas._cbar_ax, label='Correlation intensity')

        ax.set_xlabel('Dataset Y wavenumber', fontsize=10)
        ax.set_ylabel('Dataset X wavenumber', fontsize=10)
        ax.set_title(title, fontsize=11)
        ax.set_aspect('auto')
        canvas.draw_tight()

    def _refresh_hetero_synchronous(self, *_):
        if self._mgr is None or self._mgr.hetero_synchronous is None:
            return
        self._hetero_contour_plot(
            self._hetero_sync_canvas, self._mgr.hetero_x_axis, self._mgr.hetero_y_axis,
            self._mgr.hetero_synchronous, 'Hetero synchronous spectrum \u03a6\u2093\u1d67(\u03bd\u2081,\u03bd\u2082)')

    def _refresh_hetero_asynchronous(self, *_):
        if self._mgr is None or self._mgr.hetero_asynchronous is None:
            return
        self._hetero_contour_plot(
            self._hetero_async_canvas, self._mgr.hetero_x_axis, self._mgr.hetero_y_axis,
            self._mgr.hetero_asynchronous, 'Hetero asynchronous spectrum \u03a8\u2093\u1d67(\u03bd\u2081,\u03bd\u2082)')

    # ------------------------------------------------------------------ #
    # Compare runs (A/B snapshots and their difference)                    #
    # ------------------------------------------------------------------ #

    def _store_snapshot(self, which):
        if self._mgr is None or self._mgr.synchronous is None:
            QMessageBox.warning(self, 'No results', 'Run 2D correlation first.')
            return
        snapshot = {
            'x_axis': self._mgr.x_axis.copy(),
            'synchronous': self._mgr.synchronous.copy(),
            'asynchronous': self._mgr.asynchronous.copy(),
            'desc': self._status_label.text() or '(no description)',
        }
        self._set_snapshot(which, snapshot)

    def _set_snapshot(self, which, snapshot):
        """Shared bookkeeping for both Store as A/B (from the current run)
        and Load A/B (from a file): assign the slot, refresh the status
        label, warn if A and B are now identical, and redraw the
        Difference tab."""
        if which == 'a':
            self._snapshot_a = snapshot
            self._save_a_btn.setEnabled(True)
        else:
            self._snapshot_b = snapshot
            self._save_b_btn.setEnabled(True)
        a_desc = self._snapshot_a['desc'] if self._snapshot_a else '(not stored)'
        b_desc = self._snapshot_b['desc'] if self._snapshot_b else '(not stored)'
        self._snapshot_status.setText(f'A: {a_desc}\nB: {b_desc}')

        if self._snapshot_a is not None and self._snapshot_b is not None:
            same_shape = (self._snapshot_a['synchronous'].shape == self._snapshot_b['synchronous'].shape)
            same_sync = same_shape and np.array_equal(self._snapshot_a['synchronous'], self._snapshot_b['synchronous'])
            same_async = same_shape and np.array_equal(self._snapshot_a['asynchronous'], self._snapshot_b['asynchronous'])
            if same_sync and same_async:
                QMessageBox.information(
                    self, 'A and B Are Identical',
                    'A and B currently hold the exact same result, so their '
                    'difference will be zero everywhere in the Difference tab. '
                    'To compare something meaningful, change a setting that '
                    'affects the computation (reference spectrum or perturbation '
                    'values), click Run again, then re-store A or B.')
        self._refresh_difference()

    def _save_snapshot_to_file(self, which):
        snapshot = self._snapshot_a if which == 'a' else self._snapshot_b
        if snapshot is None:
            QMessageBox.warning(self, 'Nothing to Save',
                                 f'Store a result as {which.upper()} first.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f'Save Snapshot {which.upper()}', f'2dcos_snapshot_{which}.npz',
            'Snapshot Files (*.npz);;All Files (*)')
        if not path:
            return
        ok = self.controller.save_snapshot(
            path, snapshot['x_axis'], snapshot['synchronous'], snapshot['asynchronous'],
            snapshot['desc'])
        if ok:
            QMessageBox.information(self, 'Saved', f'Snapshot {which.upper()} saved to:\n{path}')
        else:
            QMessageBox.warning(self, 'Save Failed', 'Could not save the snapshot file.')

    def _load_snapshot_from_file(self, which):
        path, _ = QFileDialog.getOpenFileName(
            self, f'Load Snapshot {which.upper()}', '', 'Snapshot Files (*.npz);;All Files (*)')
        if not path:
            return
        snapshot = self.controller.load_snapshot(path)
        if snapshot is None:
            QMessageBox.warning(self, 'Load Failed',
                                 'Could not read this file as a 2D correlation snapshot.')
            return
        self._set_snapshot(which, snapshot)

    def _refresh_difference(self, *_):
        canvas = self._diff_canvas
        if self._snapshot_a is None or self._snapshot_b is None:
            ax = canvas.ax
            ax.clear()
            ax.text(0.5, 0.5, 'Store a result as A and another as B to see their difference',
                    transform=ax.transAxes, ha='center', va='center', color='gray', wrap=True)
            ax.axis('off')
            canvas.draw_tight()
            return

        a, b = self._snapshot_a, self._snapshot_b
        if len(a['x_axis']) != len(b['x_axis']) or not np.allclose(a['x_axis'], b['x_axis']):
            ax = canvas.ax
            ax.clear()
            ax.text(0.5, 0.5, 'A and B have different x-axes and can\u2019t be compared',
                    transform=ax.transAxes, ha='center', va='center', color='#C62828', wrap=True)
            ax.axis('off')
            canvas.draw_tight()
            return

        if self._diff_mode_combo.currentIndex() == 1:
            diff = a['asynchronous'] - b['asynchronous']
            title = 'Asynchronous difference: A \u2212 B'
        else:
            diff = a['synchronous'] - b['synchronous']
            title = 'Synchronous difference: A \u2212 B'
        self._contour_plot(canvas, a['x_axis'], diff, title)

    def _shortened(self, label):
        """Look up *label*'s "shorten names" display text (see
        self._display_labels, built at dialog open time from
        self.spectra) — purely cosmetic, label itself is untouched.
        Falls back to *label* unchanged if it's not one of this dialog's
        spectra (e.g. 'average'/'?' placeholders)."""
        return self._display_labels.get(label, label)

    @staticmethod
    def _truncate_label(label, max_len=28):
        """Shorten a label for legend display without cutting mid-word
        illegibly. A plain label[-max_len:] slice (the previous approach)
        chopped off an arbitrary number of leading characters with no
        indication anything was removed — "Sample with header : 20C-back-ii"
        became "ith header : 20C-back-ii", which reads as a different,
        confusing label rather than a truncated one. If the label has a
        ':' separator (as these do), prefer showing just the part after
        it — usually the actual distinguishing identifier — with an
        ellipsis marking the cut; otherwise fall back to an ellipsis plus
        the tail characters, which at least signals truncation happened
        even if it lands mid-word."""
        if len(label) <= max_len:
            return label
        tail = label.rsplit(':', 1)[-1].strip()
        if 0 < len(tail) <= max_len - 1:
            return '\u2026' + tail
        return '\u2026' + label[-(max_len - 1):]

    def _refresh_dynamic(self, *_):
        if self._mgr is None or self._mgr.dynamic_spectra is None:
            return
        ax = self._dyn_canvas.ax
        ax.clear()
        x = self._mgr.x_axis
        dyn = self._mgr.dynamic_spectra
        n_spec = dyn.shape[0]
        for i in range(n_spec):
            color = _COLORS[i % len(_COLORS)]
            label = self._truncate_label(self._shortened(self._mgr.spectrum_labels[i]))
            ax.plot(x, dyn[i], color=color, lw=0.9, alpha=0.85,
                    label=label if n_spec <= 12 else None)
        ax.axhline(0, color='#999', lw=0.7, ls='--')
        ax.set_xlabel('x', fontsize=10)
        ax.set_ylabel('Intensity \u2212 reference', fontsize=10)
        if self._mgr.reference_mode == 'mean':
            ref_desc = 'average spectrum'
        else:
            ref_desc = f'spectrum \u2018{self._truncate_label(self._mgr.reference_label or "?")}\u2019'
        ax.set_title(f'Dynamic spectra ({n_spec} spectra, reference: {ref_desc})', fontsize=11)
        if n_spec <= 12:
            ax.legend(fontsize=7, loc='best', framealpha=0.7)
        ax.grid(True, linestyle='--', alpha=0.35)
        self._dyn_canvas.draw_tight()

    # ------------------------------------------------------------------ #
    # Export                                                               #
    # ------------------------------------------------------------------ #

    def _show_save_dialog(self):
        if self._mgr is None or self._mgr.synchronous is None:
            QMessageBox.warning(self, 'No results', 'Run 2D correlation first.')
            return
        dlg = _TwoDCorrelationSaveDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._execute_save(dlg.save_config)

    def _execute_save(self, config):
        """Build the save config and hand off to the controller — actual
        DataFrame construction and file writing lives in
        TwoDCorrelationManager, same split as every other
        visualization-analysis dialog."""
        file_path = config['file_path']
        try:
            if config['format'] == 'excel':
                success = self.controller.save_results_excel(
                    file_path,
                    include_synchronous=config['include_synchronous'],
                    include_asynchronous=config['include_asynchronous'],
                    include_dynamic=config['include_dynamic'],
                )
            else:
                success = self.controller.save_results_text({
                    'file_path': file_path,
                    'delimiter': config['delimiter'],
                    'precision': config['precision'],
                    'save_separate': config['save_separate'],
                    'include_synchronous': config['include_synchronous'],
                    'include_asynchronous': config['include_asynchronous'],
                    'include_dynamic': config['include_dynamic'],
                })

            if success:
                QMessageBox.information(self, 'Save Complete', f'Results saved to:\n{file_path}')
            else:
                QMessageBox.warning(self, 'Save Failed', 'Failed to save 2D correlation results.')
        except Exception as exc:
            QMessageBox.critical(self, 'Save Failed', str(exc))

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def _show_help(self):
        try:
            from src.help.two_d_correlation_help import (
                get_two_d_correlation_help_content, get_two_d_correlation_help_title)
            from src.help.help_window import show_help_window
            show_help_window(self, get_two_d_correlation_help_title(),
                              get_two_d_correlation_help_content())
        except Exception:
            QMessageBox.information(self, 'Help',
                                     'Help documentation is not available.')


# ======================================================================
# Perturbation values dialog
# ======================================================================

class _PerturbationValuesDialog(QDialog):
    """Lets the user enter the real perturbation value (temperature, time,
    ...) for each spectrum, either by typing them in or loading a text
    file with one number per line, in the same order as the spectra.
    These values are used only to (a) sort spectra into the correct
    perturbation order and (b) detect uneven spacing and resample onto a
    uniform grid if needed (see TwoDCorrelationManager.compute) — not
    required at all if the spectra are already known to be evenly spaced
    in the order they were selected."""

    def __init__(self, parent, spectra, existing_values=None, existing_label=None,
                 display_labels=None):
        super().__init__(parent)
        self.setWindowTitle('Perturbation Values')
        self.setModal(True)
        self.resize(520, 520)
        self.spectra = spectra
        self.values = None
        self.label = None
        # Display-only "shorten names" map (see label_shortening.py),
        # passed in from TwoDCorrelationDialog._display_labels — the
        # 'Spectrum' column is read-only and rows map to self.spectra
        # purely by position, so this never affects which value ends up
        # assigned to which spectrum.
        self._display_labels = display_labels or {}
        self._build_ui(existing_values, existing_label)

    def _build_ui(self, existing_values, existing_label):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            'Enter the real perturbation value for each spectrum below\n'
            '(e.g. actual temperature or time), or load them from a text\n'
            'file with one number per line, in the same order as the\n'
            'spectra shown. Leave blank / Cancel to use spectrum order\n'
            'instead (assumes even spacing). Select cells and use\n'
            'Ctrl+C / Ctrl+X / Ctrl+V / Delete to copy values in from a\n'
            'spreadsheet, the same as the Rename Spectra table.'
        ))

        label_row = QHBoxLayout()
        label_row.addWidget(QLabel('Axis label:'))
        self.label_edit = QLineEdit(existing_label or '')
        self.label_edit.setPlaceholderText('e.g. Temperature (\u00b0C)')
        label_row.addWidget(self.label_edit)
        layout.addLayout(label_row)

        self.table = QTableWidget(len(self.spectra), 2)
        self.table.setHorizontalHeaderLabels(['Spectrum', 'Value'])
        # Interactive + a sensible starting width for the Spectrum column;
        # Stretch for Value so it always gets the remaining space instead
        # of collapsing to near-zero width (ResizeToContents on an
        # initially-empty column has nothing to size against).
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.setColumnWidth(0, 180)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        # Extended/by-cell selection is what makes multi-cell copy/paste
        # meaningful — matches rename_spectra_dialog.py's New Label column.
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        for i, s in enumerate(self.spectra):
            full_label = s.get('label', '?')
            label_item = QTableWidgetItem(self._display_labels.get(full_label, full_label))
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, label_item)
            value_text = ''
            if existing_values is not None and i < len(existing_values):
                value_text = str(existing_values[i])
            self.table.setItem(i, 1, QTableWidgetItem(value_text))
        layout.addWidget(self.table)
        self._install_clipboard_shortcuts()

        btn_row = QHBoxLayout()
        load_btn = QPushButton('Load from file\u2026')
        load_btn.clicked.connect(self._load_from_file)
        btn_row.addWidget(load_btn)
        clear_btn = QPushButton('Clear all')
        clear_btn.clicked.connect(self._clear_values)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _install_clipboard_shortcuts(self):
        """Excel-style copy/cut/paste/delete for the Value column (column
        1) — same implementation as rename_spectra_dialog.py's New Label
        column. Paste accepts any text (numeric validation happens once,
        at OK, in _on_accept — not per-keystroke), so pasting from a
        spreadsheet column works the same as pasting from this table's
        own Ctrl+C output."""
        table = self.table

        def do_copy():
            value_items = sorted(
                (it for it in table.selectedItems() if it.column() == 1),
                key=lambda it: it.row()
            )
            if not value_items:
                return
            QApplication.clipboard().setText("\n".join(it.text() for it in value_items))
        QShortcut(QKeySequence.Copy, table).activated.connect(do_copy)

        def do_paste():
            text = QApplication.clipboard().text()
            if not text:
                return
            lines = [ln for ln in text.replace('\r', '').split('\n') if ln != '']
            selected_rows = sorted(it.row() for it in table.selectedItems())
            start_row = selected_rows[0] if selected_rows else max(table.currentRow(), 0)
            for i, line in enumerate(lines):
                row = start_row + i
                if row >= table.rowCount():
                    break
                # Spreadsheets paste multi-column selections tab-separated;
                # take the first token as the value.
                token = line.split('\t')[0].strip()
                table.setItem(row, 1, QTableWidgetItem(token))
        QShortcut(QKeySequence.Paste, table).activated.connect(do_paste)

        def do_delete():
            for it in table.selectedItems():
                if it.column() == 1:
                    it.setText("")
        QShortcut(QKeySequence.Delete, table).activated.connect(do_delete)

        def do_cut():
            do_copy()
            do_delete()
        QShortcut(QKeySequence.Cut, table).activated.connect(do_cut)

    def _load_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Load Perturbation Values', '', 'Text Files (*.txt);;All Files (*)')
        if not path:
            return
        try:
            with open(path, 'r') as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            values = [float(ln) for ln in lines]
        except Exception as exc:
            QMessageBox.warning(self, 'Load Failed', f'Could not read values:\n{exc}')
            return
        if len(values) != len(self.spectra):
            QMessageBox.warning(
                self, 'Wrong Number of Values',
                f'File has {len(values)} value(s) but there are {len(self.spectra)} '
                'spectra. Please provide exactly one value per spectrum.')
            return
        for i, v in enumerate(values):
            self.table.setItem(i, 1, QTableWidgetItem(str(v)))

    def _clear_values(self):
        for i in range(self.table.rowCount()):
            self.table.setItem(i, 1, QTableWidgetItem(''))

    def _on_accept(self):
        texts = [self.table.item(i, 1).text().strip() for i in range(self.table.rowCount())]
        if all(t == '' for t in texts):
            # Nothing entered — treat as "not using perturbation values".
            self.values = None
            self.label = None
            self.accept()
            return
        if any(t == '' for t in texts):
            QMessageBox.warning(self, 'Incomplete Values',
                                 'Please provide a value for every spectrum, or clear all of them.')
            return
        try:
            values = [float(t) for t in texts]
        except ValueError:
            QMessageBox.warning(self, 'Invalid Value', 'All values must be numbers.')
            return
        if len(set(values)) != len(values):
            QMessageBox.warning(self, 'Duplicate Values', 'Perturbation values must all be distinct.')
            return
        self.values = values
        self.label = self.label_edit.text().strip() or None
        self.accept()


class _TwoDCorrelationSaveDialog(QDialog):
    """Save dialog for 2D correlation results — same pattern as
    PCA/SVD/NMF's Save…: choose format, choose which categories to
    include, and (for text) delimiter/precision/combined-vs-separate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.save_config = {}
        self.setWindowTitle('Save 2D Correlation Results')
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
        self.include_sync_cb = QCheckBox('Synchronous')
        self.include_sync_cb.setChecked(True)
        include_layout.addWidget(self.include_sync_cb)
        self.include_async_cb = QCheckBox('Asynchronous')
        self.include_async_cb.setChecked(True)
        include_layout.addWidget(self.include_async_cb)
        self.include_dynamic_cb = QCheckBox('Dynamic spectra')
        self.include_dynamic_cb.setChecked(True)
        include_layout.addWidget(self.include_dynamic_cb)
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
            default_name = 'two_d_correlation_results.xlsx'
        else:
            file_filter = 'Text Files (*.txt);;CSV Files (*.csv);;All Files (*)'
            default_name = 'two_d_correlation_results.txt'
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save 2D Correlation Results', default_name, file_filter)
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
        if not (self.include_sync_cb.isChecked() or self.include_async_cb.isChecked()
                or self.include_dynamic_cb.isChecked()):
            QMessageBox.warning(self, 'Nothing to Save',
                                 'Select at least one of Synchronous, Asynchronous, or Dynamic spectra.')
            return
        self.save_config = {
            'file_path': self.path_edit.text(),
            'format': 'excel' if self.excel_radio.isChecked() else 'text',
            'include_synchronous': self.include_sync_cb.isChecked(),
            'include_asynchronous': self.include_async_cb.isChecked(),
            'include_dynamic': self.include_dynamic_cb.isChecked(),
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
        self._cbar_ax = None    # dedicated colorbar axes, created once and
                                 # reused by _contour_plot (see there for why)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fig.patch.set_facecolor('#ffffff')
        self.ax.set_facecolor('#ffffff')

    def leaveEvent(self, event):
        """Handle the mouse leaving the canvas.

        Deliberate override, not inherited behavior — applied from the
        start here, rather than after the fact: matplotlib's own
        FigureCanvasQT.leaveEvent() unconditionally calls
        QApplication.restoreOverrideCursor(), which assumes matplotlib
        itself is the only thing that ever pushes a global override
        cursor. This dialog pushes its own (see _run_analysis's progress
        cursor), so without this override, the mouse leaving the canvas
        while that cursor is active would pop it early and desync the
        cursor stack. See InteractiveSVDAnalysisCanvas.leaveEvent in
        svd_analysis_dialog.py for the full story.
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
