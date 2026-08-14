# src/views/dialogs/visualization_analysis/qc_outlier_dialog.py
"""
QC / Outlier Detection dialog.

Layout mirrors KineticsFittingDialog's/PLSDialog's shape (control panel
left, single matplotlib canvas + a view dropdown on the right, explicit
"Run" button, background QThread so a slow PCA fit on a large batch
doesn't freeze the UI) but is simpler than either: there's no per-spectrum
input table (QC needs nothing from the user per spectrum, unlike PLS's
calibration values or Kinetics' time values) -- just a handful of model
settings that apply to the whole batch at once.

Fits a PCA model to the selected batch and flags spectra whose Hotelling
T^2 (unusual pattern, within the model) or Q-residual (doesn't fit the
model at all) exceeds its statistical control limit -- see
QCOutlierManager's docstring for the full explanation of both metrics.

Read-only analysis -- no Apply/Add-as-New, no Operations History entry
(same as PLS / Kinetics Fitting / Isosbestic Point Detection): nothing
here is ever written back to the spectra list.

Built with the lessons learned from PLSDialog's/KineticsFittingDialog's
own bug-fix history applied from the start:
    - showEvent drains any wait-cursor left active by the caller.
    - Table columns use Interactive resize + resizeColumnsToContents(),
      never Stretch.
    - Splitter panes use setMinimumWidth (never setFixedWidth) plus
      setChildrenCollapsible(False) and a widened, visibly-styled handle.
    - The Shorten Names delegate is wired up on the results table.
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton, QLabel,
    QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QSplitter, QWidget,
    QSizePolicy, QFileDialog, QApplication, QMessageBox, QProgressDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QCursor

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    compute_distinguishing_labels, make_display_text_delegate, make_shorten_names_checkbox,
)

logger = get_logger(__name__)

COL_SPECTRUM = 0
COL_T2 = 1
COL_Q = 2
COL_FLAG = 3

_CONFIDENCE_OPTIONS = [('90%', 0.10), ('95%', 0.05), ('99%', 0.01)]


class _ComputeWorker(QThread):
    """Runs a single callable on a background thread -- identical pattern
    to every other analysis dialog's own copy."""
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


class _QCPlotCanvas(FigureCanvas):
    """One matplotlib Figure whose content is switched by
    self.visualization_mode -- same single-canvas-plus-dropdown approach
    as PLSDialog's/KineticsFittingDialog's own plot canvas."""

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#f0f0f0')
        self.visualization_mode = 'distance'

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fig.get_axes():
            try:
                self._fig.tight_layout()
            except Exception:
                pass
            self.draw_idle()

    def plot(self, mgr, mode, labels_map=None, selected_index=None):
        self._fig.clear()
        if mgr is None or mgr.t2 is None:
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5, 'Click "Run QC Check" to fit the model.',
                     transform=ax.transAxes, ha='center', va='center',
                     color='#1976D2', fontsize=10)
            self.draw_idle()
            return

        if mode == 'scores':
            self._plot_scores(mgr, labels_map, selected_index)
        elif mode == 'residual':
            self._plot_residual(mgr, selected_index)
        else:
            self._plot_distance(mgr, labels_map, selected_index)
        self.draw_idle()

    def plot_full_spectrum(self, mgr, selected_index, labels_map=None):
        """"Full spectrum" row-click mode (see QCOutlierDialog's "On row
        click" selector next to View): a single, plain plot of one
        spectrum's full ORIGINAL curve — no model overlay, no residual
        panel, nothing but "here is what this spectrum actually looks
        like." Deliberately simpler than the existing 'Residual spectrum'
        view (which is model vs. original vs. residual, three curves
        across two panels) — this is for when all you want is a quick,
        direct look at one flagged (or unflagged) spectrum's shape,
        without a second dropdown trip to Residual spectrum and back.
        """
        self._fig.clear()
        if selected_index is None or mgr is None or mgr.x_axis is None:
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5, 'Select a spectrum in the results table below.',
                     transform=ax.transAxes, ha='center', va='center',
                     color='#1976D2', fontsize=10)
            self.draw_idle()
            return
        ax = self._fig.add_subplot(111)
        self._plot_full_spectrum_on_ax(mgr, selected_index, labels_map, ax)
        self.draw_idle()

    def plot_split(self, mgr, mode, selected_index, labels_map=None):
        """"Both (split view)" row-click mode: the current View plot
        (Distance plot / PCA scores / Residual spectrum) on the left,
        the selected spectrum's plain full-original-curve plot on the
        right — side by side, so you don't have to choose between
        seeing where a point sits and seeing what its spectrum actually
        looks like. Falls back to the plain single-panel plot() when
        there's no row selected yet (nothing to put on the right side).
        """
        self._fig.clear()
        if mgr is None or mgr.t2 is None:
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5, 'Click "Run QC Check" to fit the model.',
                     transform=ax.transAxes, ha='center', va='center',
                     color='#1976D2', fontsize=10)
            self.draw_idle()
            return
        if selected_index is None:
            if mode == 'scores':
                self._plot_scores(mgr, labels_map, None)
            elif mode == 'residual':
                self._plot_residual(mgr, None)
            else:
                self._plot_distance(mgr, labels_map, None)
            self.draw_idle()
            return

        gs = self._fig.add_gridspec(1, 2, width_ratios=[1, 1], wspace=0.35)
        if mode == 'scores':
            left_ax = self._fig.add_subplot(gs[0, 0])
            self._plot_scores(mgr, labels_map, selected_index, ax=left_ax)
        elif mode == 'residual':
            left_gs = gs[0, 0].subgridspec(2, 1)
            ax1 = self._fig.add_subplot(left_gs[0, 0])
            ax2 = self._fig.add_subplot(left_gs[1, 0], sharex=ax1)
            self._plot_residual(mgr, selected_index, ax1=ax1, ax2=ax2)
        else:
            left_ax = self._fig.add_subplot(gs[0, 0])
            self._plot_distance(mgr, labels_map, selected_index, ax=left_ax)

        right_ax = self._fig.add_subplot(gs[0, 1])
        self._plot_full_spectrum_on_ax(mgr, selected_index, labels_map, right_ax)
        self.draw_idle()

    def _plot_full_spectrum_on_ax(self, mgr, selected_index, labels_map, ax):
        """Shared by plot_full_spectrum (standalone) and plot_split (right
        panel) — draws the selected spectrum's plain original curve onto
        whatever axes it's given. original = recon + residual is exactly
        the same identity _plot_residual already relies on (residual =
        Xc - X_hat, recon = mean + X_hat, so recon + residual = mean + Xc
        = X, the true original values)."""
        recon, residual = mgr.reconstruction(selected_index)
        original = recon + residual
        label = self._display(mgr.labels[selected_index], labels_map)
        flagged = bool(mgr.t2_flag[selected_index] or mgr.q_flag[selected_index])
        color = '#C62828' if flagged else '#1565C0'
        ax.plot(mgr.x_axis, original, color=color, linewidth=1.3)
        reason = mgr.flag_reason(selected_index)
        title = f"{label}  —  {reason if reason else 'OK'}"
        ax.set_title(title, fontsize=10, color=color)
        ax.set_xlabel('X')
        ax.set_ylabel('Signal')
        ax.grid(True, linestyle='--', alpha=0.3)

    def _display(self, label, labels_map):
        return (labels_map or {}).get(label, label)

    def _highlight_selected(self, ax, x, y, label):
        """Draw a bold ring around the currently-selected table row's
        point, on top of whatever else is plotted (OK/Flagged points,
        control-limit lines) — an open ring rather than a filled dot so
        it's never mistaken for another filled-circle "OK" point, and a
        distinct saturated blue ('#2962FF') so it reads clearly against
        both the OK points' blue and the Flagged points' red. Shared by
        _plot_distance and _plot_scores so the same visual language means
        "this is the row selected below" in either view."""
        ax.scatter([x], [y], s=170, facecolors='none', edgecolors='#2962FF',
                   linewidths=2.4, zorder=6, label='Selected (table row)')
        ax.annotate(label, (x, y), fontsize=8, fontweight='bold', color='#2962FF',
                   xytext=(6, -11), textcoords='offset points', zorder=6)

    def _plot_distance(self, mgr, labels_map, selected_index=None, ax=None):
        if ax is None:
            ax = self._fig.add_subplot(111)
        flagged = mgr.t2_flag | mgr.q_flag
        ax.scatter(mgr.t2[~flagged], mgr.q[~flagged], s=28, color='#1565C0',
                   label='OK', zorder=3)
        if np.any(flagged):
            ax.scatter(mgr.t2[flagged], mgr.q[flagged], s=40, color='#C62828',
                       marker='^', label='Flagged', zorder=4)
            for i in np.where(flagged)[0]:
                ax.annotate(self._display(mgr.labels[i], labels_map),
                           (mgr.t2[i], mgr.q[i]), fontsize=7, color='#C62828',
                           xytext=(4, 4), textcoords='offset points')
        if mgr.t2_limit is not None:
            ax.axvline(mgr.t2_limit, color='#E65100', linestyle='--', linewidth=1.2,
                      label=f"T² limit ({(1 - mgr.alpha) * 100:.0f}%)")
        if mgr.q_limit:
            ax.axhline(mgr.q_limit, color='#6A1B9A', linestyle='--', linewidth=1.2,
                      label=f"Q limit ({(1 - mgr.alpha) * 100:.0f}%)")
        if selected_index is not None:
            self._highlight_selected(ax, mgr.t2[selected_index], mgr.q[selected_index],
                                     self._display(mgr.labels[selected_index], labels_map))
        ax.set_xlabel("Hotelling T² (unusual pattern)")
        ax.set_ylabel("Q-residual / SPE (doesn't fit the model)")
        ax.set_title('Distance plot')
        ax.legend(fontsize=8)

    def _plot_scores(self, mgr, labels_map, selected_index=None, ax=None):
        if ax is None:
            ax = self._fig.add_subplot(111)
        flagged = mgr.t2_flag | mgr.q_flag
        if mgr.n_components >= 2:
            x, y = mgr.scores[:, 0], mgr.scores[:, 1]
            xlabel, ylabel = (f"PC1 ({mgr.explained_variance[0]:.1f}%)",
                             f"PC2 ({mgr.explained_variance[1]:.1f}%)")
        else:
            x, y = mgr.scores[:, 0], np.arange(len(mgr.scores))
            xlabel, ylabel = f"PC1 ({mgr.explained_variance[0]:.1f}%)", "Spectrum order"
        ax.scatter(x[~flagged], y[~flagged], s=28, color='#1565C0', label='OK', zorder=3)
        if np.any(flagged):
            ax.scatter(x[flagged], y[flagged], s=40, color='#C62828', marker='^',
                      label='Flagged', zorder=4)
            for i in np.where(flagged)[0]:
                ax.annotate(self._display(mgr.labels[i], labels_map), (x[i], y[i]),
                           fontsize=7, color='#C62828', xytext=(4, 4), textcoords='offset points')
        if selected_index is not None:
            self._highlight_selected(ax, x[selected_index], y[selected_index],
                                     self._display(mgr.labels[selected_index], labels_map))
        ax.axhline(0, color='#bbb', linewidth=0.7)
        ax.axvline(0, color='#bbb', linewidth=0.7)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title('PCA scores')
        ax.legend(fontsize=8)

    def _plot_residual(self, mgr, selected_index, ax1=None, ax2=None):
        if selected_index is None:
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5, 'Select a spectrum in the results table below.',
                     transform=ax.transAxes, ha='center', va='center',
                     color='#1976D2', fontsize=10)
            return
        recon, residual = mgr.reconstruction(selected_index)
        if ax1 is None:
            ax1 = self._fig.add_subplot(211)
        if ax2 is None:
            ax2 = self._fig.add_subplot(212, sharex=ax1)
        original = recon + residual
        ax1.plot(mgr.x_axis, original, color='#1565C0', linewidth=1.4, label='Original')
        ax1.plot(mgr.x_axis, recon, color='#E65100', linewidth=1.4, linestyle='--',
                label=f'Model ({mgr.n_components} comp.)')
        ax1.set_ylabel('Signal')
        ax1.legend(fontsize=8)
        ax1.set_title(f"{mgr.labels[selected_index]} — original vs. model")

        ax2.axhline(0, color='#999', linewidth=0.8)
        ax2.plot(mgr.x_axis, residual, color='#C62828', linewidth=1.2)
        ax2.set_xlabel('X')
        ax2.set_ylabel('Residual')


class QCOutlierDialog(QDialog):

    def __init__(self, parent=None, controller=None, spectra=None):
        super().__init__(parent)
        self.setWindowTitle('QC / Outlier Detection')
        self.setMinimumSize(1080, 720)
        self.resize(1320, 860)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self.controller = controller
        self.spectra = list(spectra or [])
        self._worker = None
        self._progress = None
        self._display_order = []   # results-table row -> index into self.spectra

        self._build_ui()

    def showEvent(self, event):
        super().showEvent(event)
        from PyQt5.QtWidgets import QApplication
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 940])
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet(
            'QSplitter::handle { background-color: #cfd8dc; } '
            'QSplitter::handle:hover { background-color: #90a4ae; }'
        )
        root.addWidget(splitter)

    def _build_left(self):
        w = QWidget()
        w.setMinimumWidth(320)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        info = QLabel(f"Checking {len(self.spectra)} selected spectra against "
                       f"each other as one batch.")
        info.setWordWrap(True)
        info.setStyleSheet('color: #555;')
        layout.addWidget(info)

        layout.addWidget(self._build_settings_group())
        layout.addStretch(1)

        self.run_btn = QPushButton('▶  Run QC Check')
        self.run_btn.setStyleSheet(
            'QPushButton { background-color: #2E7D32; color: white; font-weight: bold; '
            'padding: 8px; border-radius: 4px; } QPushButton:hover { background-color: #1B5E20; }'
        )
        self.run_btn.clicked.connect(self._run_analysis)
        layout.addWidget(self.run_btn)

        self._summary_label = QLabel('')
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet(
            'background-color: #E3F2FD; padding: 6px; border-radius: 4px; color: #1565C0;'
        )
        layout.addWidget(self._summary_label)

        btn_row = QHBoxLayout()
        help_btn = QPushButton('Help')
        help_btn.setAutoDefault(False)
        help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(help_btn)
        btn_row.addStretch()
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        return w

    def _build_settings_group(self):
        group = QGroupBox('Model settings')
        layout = QVBoxLayout(group)

        self.auto_components_check = QCheckBox('Auto-select components (by variance explained)')
        self.auto_components_check.setChecked(True)
        self.auto_components_check.toggled.connect(self._on_auto_toggled)
        layout.addWidget(self.auto_components_check)

        variance_row = QHBoxLayout()
        variance_row.addWidget(QLabel('Variance threshold:'))
        self.variance_spin = QSpinBox()
        self.variance_spin.setRange(50, 99)
        self.variance_spin.setValue(95)
        self.variance_spin.setSuffix('%')
        variance_row.addWidget(self.variance_spin)
        layout.addLayout(variance_row)

        comp_row = QHBoxLayout()
        comp_row.addWidget(QLabel('Number of components:'))
        max_k = max(1, min(len(self.spectra) - 2, 20))
        self.n_components_spin = QSpinBox()
        self.n_components_spin.setRange(1, max_k)
        self.n_components_spin.setValue(min(2, max_k))
        self.n_components_spin.setEnabled(False)
        comp_row.addWidget(self.n_components_spin)
        layout.addLayout(comp_row)

        conf_row = QHBoxLayout()
        conf_row.addWidget(QLabel('Confidence level:'))
        self.confidence_combo = QComboBox()
        for text, _alpha in _CONFIDENCE_OPTIONS:
            self.confidence_combo.addItem(text)
        self.confidence_combo.setCurrentIndex(1)   # 95%
        conf_row.addWidget(self.confidence_combo)
        layout.addLayout(conf_row)

        return group

    def _on_auto_toggled(self, checked):
        self.variance_spin.setEnabled(checked)
        self.n_components_spin.setEnabled(not checked)

    def _build_right(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(4, 4, 4, 4)

        view_row = QHBoxLayout()
        view_row.addWidget(QLabel('View:'))
        self.view_combo = QComboBox()
        self.view_combo.addItem('Distance plot (T² vs Q)', 'distance')
        self.view_combo.addItem('PCA scores', 'scores')
        self.view_combo.addItem('Residual spectrum (selected row)', 'residual')
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        view_row.addWidget(self.view_combo)
        view_row.addSpacing(16)
        view_row.addWidget(QLabel('On row click:'))
        self.row_click_combo = QComboBox()
        self.row_click_combo.addItem('Highlight point', 'highlight')
        self.row_click_combo.addItem('Full spectrum', 'spectrum')
        self.row_click_combo.addItem('Both (split view)', 'both')
        self.row_click_combo.setToolTip(
            "What clicking a row in the results table below does to the plot:\n\n"
            "Highlight point (default): just highlights that point on the\n"
            "Distance plot / PCA scores view (or still drives Residual\n"
            "spectrum, if that's the current View) — nothing else changes.\n\n"
            "Full spectrum: replaces whatever's shown here with that\n"
            "spectrum's full original curve — a quick, direct look, simpler\n"
            "than switching View to 'Residual spectrum' (which also overlays\n"
            "the model fit and a residual panel).\n\n"
            "Both (split view): the current View plot on the left, that\n"
            "spectrum's full original curve on the right, side by side.")
        self.row_click_combo.currentIndexChanged.connect(self._refresh_canvas)
        view_row.addWidget(self.row_click_combo)
        view_row.addStretch()
        outer.addLayout(view_row)

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.setHandleWidth(8)
        right_splitter.setChildrenCollapsible(False)
        right_splitter.setStyleSheet(
            'QSplitter::handle { background-color: #cfd8dc; } '
            'QSplitter::handle:hover { background-color: #90a4ae; }'
        )

        plot_widget = QWidget()
        pl = QVBoxLayout(plot_widget)
        pl.setContentsMargins(0, 0, 0, 0)
        self._canvas = _QCPlotCanvas(plot_widget)
        pl.addWidget(NavigationToolbar(self._canvas, plot_widget))
        pl.addWidget(self._canvas)
        right_splitter.addWidget(plot_widget)

        results_widget = QWidget()
        rl = QVBoxLayout(results_widget)
        rl.setContentsMargins(0, 4, 0, 0)

        # Display-only "shorten names" toggle — this dialog's own,
        # independent on/off state (see label_shortening.py's
        # make_shorten_names_checkbox), unrelated to the main window's
        # checkbox and always starting unchecked.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _state: self._results_table.viewport().update())
        rl.addWidget(self.checkBox_shorten_names)

        self._results_table = QTableWidget(0, 4)
        self._results_table.setHorizontalHeaderLabels(['Spectrum', 'T²', 'Q (SPE)', 'Flag'])
        self._results_table.verticalHeader().setVisible(False)
        header = self._results_table.horizontalHeader()
        header.setSectionResizeMode(COL_SPECTRUM, QHeaderView.Interactive)
        self._results_table.setColumnWidth(COL_SPECTRUM, 220)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self._results_table.setTextElideMode(Qt.ElideLeft)
        self._results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._results_table.setAlternatingRowColors(True)
        self._results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._results_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._results_table.itemSelectionChanged.connect(self._on_row_selected)
        self._results_table.setItemDelegateForColumn(
            COL_SPECTRUM, make_display_text_delegate(self._display_labels_map, parent=self._results_table))
        rl.addWidget(self._results_table, stretch=1)

        export_row = QHBoxLayout()
        export_row.addStretch()
        self._copy_btn = QPushButton('⧉  Copy to clipboard')
        self._copy_btn.setEnabled(False)
        self._copy_btn.clicked.connect(self._copy_table)
        export_row.addWidget(self._copy_btn)
        self._csv_btn = QPushButton('\U0001f4be  Export CSV…')
        self._csv_btn.setEnabled(False)
        self._csv_btn.clicked.connect(self._export_csv)
        export_row.addWidget(self._csv_btn)
        self._pdf_btn = QPushButton('\U0001f4c4  Export PDF…')
        self._pdf_btn.setEnabled(False)
        self._pdf_btn.clicked.connect(self._export_pdf)
        export_row.addWidget(self._pdf_btn)
        rl.addLayout(export_row)

        right_splitter.addWidget(results_widget)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)
        outer.addWidget(right_splitter)
        return w

    # ------------------------------------------------------------------
    # Shorten names (display-only) — this dialog's own independent
    # checkbox (see _build_right), no longer tied to the main window's.
    # ------------------------------------------------------------------
    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _display_labels_map(self):
        if not self._shorten_names_enabled():
            return {}
        labels = [s.get('label', '') for s in self.spectra]
        if len(labels) < 2:
            return {}
        return compute_distinguishing_labels(labels)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def _run_analysis(self):
        n_components = None if self.auto_components_check.isChecked() else self.n_components_spin.value()
        variance_threshold = self.variance_spin.value() / 100.0
        alpha = _CONFIDENCE_OPTIONS[self.confidence_combo.currentIndex()][1]

        self.run_btn.setEnabled(False)
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))

        self._progress = QProgressDialog('Fitting PCA model and checking for outliers…', None, 0, 0, self)
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setWindowTitle('QC / Outlier Detection')
        self._progress.setMinimumDuration(0)
        self._progress.setCancelButton(None)
        self._progress.show()

        def _fn():
            ok, err = self.controller.compute_qc(
                self.spectra, n_components=n_components,
                variance_threshold=variance_threshold, alpha=alpha)
            if not ok:
                raise RuntimeError(err or "QC computation failed.")
            return True

        self._worker = _ComputeWorker(_fn, self)
        self._worker.done.connect(self._on_computed)
        self._worker.start(QThread.LowPriority)

    def _on_computed(self):
        QApplication.restoreOverrideCursor()
        self.run_btn.setEnabled(True)
        if self._progress is not None:
            self._progress.close()
            self._progress = None

        if self._worker.error is not None:
            QMessageBox.warning(self, 'Could Not Run QC Check', str(self._worker.error))
            return

        self._update_summary()
        self._populate_results_table()
        self._refresh_canvas()
        self._copy_btn.setEnabled(True)
        self._csv_btn.setEnabled(True)
        self._pdf_btn.setEnabled(True)

    def _update_summary(self):
        mgr = self.controller.manager
        n_flagged = int(np.sum(mgr.t2_flag | mgr.q_flag))
        text = (f"{mgr.n_components} component{'s' if mgr.n_components != 1 else ''} "
                f"({np.sum(mgr.explained_variance):.1f}% variance)  •  "
                f"{n_flagged} of {mgr.n_spectra} spectra flagged  •  "
                f"{(1 - mgr.alpha) * 100:.0f}% confidence")
        self._summary_label.setText(text)

    # ------------------------------------------------------------------
    # View switching / row selection
    # ------------------------------------------------------------------
    def _refresh_canvas(self):
        """Single shared entry point for anything that should update the
        plot: the View dropdown changing, a results-table row being
        selected, or the "On row click" selector changing. Centralizing
        this means all three always agree on what should currently be on
        screen, instead of each handler separately re-deciding it (which
        is how the old _on_row_selected only ever redrew for the
        'residual' View, silently doing nothing for Distance plot / PCA
        scores — exactly the gap Full spectrum / Both / point-
        highlighting needed closed)."""
        if self.controller.manager is None or self.controller.manager.t2 is None:
            return
        idx = self._current_selected_index()
        mode = self.view_combo.currentData()
        self._canvas.visualization_mode = mode
        row_click_mode = self.row_click_combo.currentData()
        labels_map = self._display_labels_map()
        if row_click_mode == 'spectrum' and idx is not None:
            self._canvas.plot_full_spectrum(self.controller.manager, idx,
                                            labels_map=labels_map)
        elif row_click_mode == 'both' and idx is not None:
            self._canvas.plot_split(self.controller.manager, mode, idx,
                                    labels_map=labels_map)
        else:
            self._canvas.plot(self.controller.manager, mode,
                              labels_map=labels_map, selected_index=idx)

    def _on_view_changed(self):
        self._refresh_canvas()

    def _on_row_selected(self):
        self._refresh_canvas()

    def _current_selected_index(self):
        rows = self._results_table.selectionModel().selectedRows() if self._results_table.selectionModel() else []
        if not rows:
            return None
        table_row = rows[0].row()
        if table_row < len(self._display_order):
            return self._display_order[table_row]
        return None

    # ------------------------------------------------------------------
    # Results table -- worst-first (largest T²/limit or Q/limit ratio),
    # so the spectra most worth looking at are always at the top rather
    # than buried in whatever order they happened to be selected.
    # ------------------------------------------------------------------
    def _populate_results_table(self):
        mgr = self.controller.manager
        t2_ratio = mgr.t2 / mgr.t2_limit if mgr.t2_limit else np.zeros_like(mgr.t2)
        q_ratio = mgr.q / mgr.q_limit if mgr.q_limit else np.zeros_like(mgr.q)
        severity = np.maximum(t2_ratio, q_ratio)
        order = np.argsort(-severity)
        self._display_order = list(order)

        table = self._results_table
        table.setRowCount(len(order))
        for row, idx in enumerate(order):
            name_item = QTableWidgetItem(mgr.labels[idx])
            name_item.setToolTip(mgr.labels[idx])
            table.setItem(row, COL_SPECTRUM, name_item)

            t2_item = QTableWidgetItem(f"{mgr.t2[idx]:.4g}")
            t2_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if mgr.t2_flag[idx]:
                t2_item.setForeground(Qt.red)
            table.setItem(row, COL_T2, t2_item)

            q_item = QTableWidgetItem(f"{mgr.q[idx]:.4g}")
            q_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if mgr.q_flag[idx]:
                q_item.setForeground(Qt.red)
            table.setItem(row, COL_Q, q_item)

            reason = mgr.flag_reason(idx)
            flag_item = QTableWidgetItem(reason if reason else 'OK')
            if reason:
                flag_item.setForeground(Qt.red)
            table.setItem(row, COL_FLAG, flag_item)

        table.resizeColumnsToContents()

    def _table_text(self, sep='\t'):
        headers = [self._results_table.horizontalHeaderItem(c).text()
                   for c in range(self._results_table.columnCount())]
        lines = [sep.join(headers)]
        for r in range(self._results_table.rowCount()):
            row = []
            for c in range(self._results_table.columnCount()):
                item = self._results_table.item(r, c)
                row.append(item.text() if item else '')
            lines.append(sep.join(row))
        return '\n'.join(lines)

    def _copy_table(self):
        QApplication.clipboard().setText(self._table_text('\t'))

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export Results', 'qc_outlier_results.csv',
                                              'CSV files (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(self._table_text(','))
        except Exception as e:
            QMessageBox.warning(self, 'Export Failed', str(e))

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export PDF Report', 'qc_outlier_report.pdf',
                                              'PDF files (*.pdf)')
        if not path:
            return
        mgr = self.controller.manager
        n_flagged = int(np.sum(mgr.t2_flag | mgr.q_flag))
        meta = [
            f"Components: {mgr.n_components} ({np.sum(mgr.explained_variance):.1f}% variance)",
            f"Confidence level: {(1 - mgr.alpha) * 100:.0f}%",
            f"Flagged: {n_flagged} of {mgr.n_spectra} spectra",
        ]
        headers = ['Spectrum', 'T²', 'Q (SPE)', 'Flag']
        rows = []
        for r in range(self._results_table.rowCount()):
            rows.append([self._results_table.item(r, c).text() if self._results_table.item(r, c) else ''
                        for c in range(4)])
        labels = [s.get('label', '') for s in self.spectra]

        try:
            from src.modules.utils.pdf_report_utils import export_report_pdf
            export_report_pdf(path, 'QC / Outlier Detection', meta_lines=meta,
                              figure=self._canvas._fig, table_headers=headers, table_rows=rows,
                              source_labels=labels)
        except Exception as e:
            QMessageBox.warning(self, 'Export Failed', str(e))

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------
    def _show_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'qc_outlier')
