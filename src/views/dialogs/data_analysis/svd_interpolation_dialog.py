# src/views/dialogs/data_analysis/svd_interpolation_dialog.py

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QComboBox, QRadioButton, QButtonGroup,
    QSpinBox, QDoubleSpinBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QWidget, QTabWidget, QMessageBox, QTextEdit,
    QSizePolicy, QFrame, QDialogButtonBox, QShortcut, QApplication,
    QCheckBox, QProgressDialog, QFileDialog, QScrollArea, QAbstractItemView,
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QKeySequence, QCursor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    make_shortened_name_delegate, make_shorten_names_checkbox,
    make_display_text_delegate, shorten_spectra_labels)

logger = get_logger(__name__)

_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
           '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']


class _ComputeWorker(QThread):
    """Runs a single callable on a background thread so a QProgressDialog
    can actually paint while it runs — same class/rationale as
    svd_analysis_dialog.py's and nmf_dialog.py's own copies: a long
    blocking call on the GUI thread freezes Qt's whole event loop,
    including the ability to paint or hide a progress dialog, for its
    entire duration. The callable must not touch any Qt widgets — only
    pure computation is safe to run here."""
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


def _make_help_button(tooltip, on_click):
    """Small orange '?' button that pops up detailed explanatory text —
    same look and role as svd_analysis_dialog.py's xaxis_help_btn, used
    here instead of permanently-visible paragraph labels so the panel
    stays compact; the explanation is a click away rather than always
    taking up space."""
    btn = QPushButton("?")
    btn.setFixedWidth(24)
    btn.setToolTip(tooltip)
    btn.setStyleSheet(
        "QPushButton {"
        "  background-color: #F57C00;"
        "  color: white;"
        "  border: none;"
        "  border-radius: 4px;"
        "  font-weight: bold;"
        "  padding: 2px;"
        "}"
        "QPushButton:hover { background-color: #E65100; }"
        "QPushButton:pressed { background-color: #BF360C; }"
    )
    btn.clicked.connect(on_click)
    return btn


# ======================================================================= #
#  CurvePointCanvas — click-to-add/remove editing, same interaction       #
#  pattern as BaselinePlotCanvas in baseline_correction_dialog.py, but    #
#  editing a coefficient-vs-parameter curve instead of a baseline shape. #
# ======================================================================= #

class CurvePointCanvas(FigureCanvas):
    point_added = pyqtSignal(float, float)
    point_removed = pyqtSignal(float, float)

    def __init__(self, parent=None, width=6, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, tight_layout=True)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)  # parented immediately — avoids the
                                 # unparented-widget flash bug (see
                                 # melting_curve_dialog.py's create_canvas_panel)

        self.edit_enabled = False
        self.setFocusPolicy(Qt.StrongFocus)
        self.mpl_connect('button_press_event', self._on_click)
        self.mpl_connect('motion_notify_event', self._on_mouse_move)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.updateGeometry()

    def _on_click(self, event):
        if not self.edit_enabled or event.inaxes != self.axes:
            return
        if event.xdata is None or event.ydata is None:
            return
        if event.button == 1:      # left click: add point
            self.point_added.emit(event.xdata, event.ydata)
        elif event.button == 3:    # right click: remove nearest point
            self.point_removed.emit(event.xdata, event.ydata)

    def _on_mouse_move(self, event):
        parent = self.parent()
        while parent is not None and not hasattr(parent, 'coordinates_label'):
            parent = parent.parent()
        if parent is not None:
            if event.inaxes:
                parent.coordinates_label.setText(
                    f"(parameter, coefficient) = ({event.xdata:.6g}, {event.ydata:.6g})")
            else:
                parent.coordinates_label.setText("")

    def plot(self, param_values, true_coeffs, points, curve_x, curve_y,
              param_label, title):
        """Redraws, preserving the current zoom/pan (axis limits) if the
        user has already set one — same convention as
        BaselinePlotCanvas.plot_spectrum, so zooming in to place a point
        precisely doesn't get undone by the very next point you add."""
        try:
            xlim, ylim = self.axes.get_xlim(), self.axes.get_ylim()
            had_limits = getattr(self, '_has_plotted_once', False)
        except Exception:
            had_limits = False

        self.axes.clear()
        if param_values is not None and true_coeffs is not None:
            self.axes.plot(param_values, true_coeffs, 'o', color='#888888',
                            ms=7, alpha=0.7, label='Measured (from SVD)')
        if curve_x is not None and curve_y is not None:
            self.axes.plot(curve_x, curve_y, '-', color='#d62728', lw=2,
                            label='Fitted curve', zorder=2)
        if points:
            px, py = zip(*points)
            self.axes.plot(px, py, 'o', color='#1f77b4', ms=9,
                            markeredgecolor='black', label='Manual points', zorder=3)
        self.axes.set_xlabel(param_label or 'Parameter value')
        self.axes.set_ylabel('Coefficient value')
        self.axes.set_title(title)
        self.axes.grid(True, linestyle='--', alpha=0.5)
        if param_values is not None or points:
            legend = self.axes.legend(loc='best', fontsize=8)
            if legend is not None:
                try:
                    legend.set_draggable(True)
                except AttributeError:
                    legend.draggable(True)

        if had_limits:
            self.axes.set_xlim(xlim)
            self.axes.set_ylim(ylim)
        else:
            self.axes.autoscale()
        self._has_plotted_once = True
        self.draw()

    def clear_plot(self, message='Apply parameter values, then check a\ncomponent on the left to edit its curve'):
        self.axes.clear()
        self.axes.set_xticks([])
        self.axes.set_yticks([])
        for spine in self.axes.spines.values():
            spine.set_visible(False)
        self.axes.text(0.5, 0.5, message, ha='center', va='center',
                        transform=self.axes.transAxes, color='#999999', fontsize=11)
        self._has_plotted_once = False
        self.draw()


class PreviewCanvas(FigureCanvas):
    def __init__(self, parent=None, width=6, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, tight_layout=True)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.updateGeometry()

    def plot(self, x_axis, source_to_plot, generated_to_plot, legend_limit,
             show_full_legend, progress=None, display_map=None):
        """Draws whatever subset the dialog has already decided to show
        (source_to_plot / generated_to_plot are pre-filtered lists — this
        canvas doesn't do any selection logic itself). Source and
        generated spectra each get their own individually-colored,
        individually-labeled legend entries (source lines dashed,
        generated lines solid, so the two groups stay visually distinct
        even sharing the same color cycle) — legend_limit caps each list
        independently, so a long generated run doesn't crowd out the
        source spectra's legend entries or vice versa.

        display_map, if given, is a {full_label: display_label} map (see
        label_shortening.shorten_spectra_labels) used for the legend text
        only — it never affects which spectra are plotted, just what
        their legend entries say.

        progress, if given, is a QProgressDialog with range (0, total
        lines) — updated periodically (not every single line, to avoid
        processEvents() overhead dominating the very thing it's meant to
        report on) since drawing many lines, not computing them, is what
        actually takes time for large previews.

        Returns True if either legend was truncated (more lines in that
        list than legend_limit and show_full_legend is False), so the
        caller can inform the user accordingly."""
        if display_map is None:
            display_map = {}
        self.axes.clear()
        count = 0
        update_every = 25

        src_limit = len(source_to_plot) if show_full_legend else legend_limit
        gen_limit = len(generated_to_plot) if show_full_legend else legend_limit
        truncated = (len(source_to_plot) > src_limit) or (len(generated_to_plot) > gen_limit)

        for i, s in enumerate(source_to_plot):
            color = _COLORS[i % len(_COLORS)]
            label = display_map.get(s['label'], s['label']) if i < src_limit else None
            self.axes.plot(s['x_scale'], s['y_scale'], color=color, lw=1,
                            linestyle='--', label=label, zorder=1)
            count += 1
            if progress is not None and count % update_every == 0:
                progress.setValue(count)
                QApplication.processEvents()

        for i, s in enumerate(generated_to_plot):
            color = _COLORS[i % len(_COLORS)]
            label = display_map.get(s['label'], s['label']) if i < gen_limit else None
            self.axes.plot(x_axis, s['y_scale'], color=color, lw=1.6,
                            label=label, zorder=2)
            count += 1
            if progress is not None and count % update_every == 0:
                progress.setValue(count)
                QApplication.processEvents()

        self.axes.set_xlabel('x')
        self.axes.set_ylabel('Intensity')
        self.axes.set_title('Generated spectra preview')
        self.axes.grid(True, linestyle='--', alpha=0.5)
        if source_to_plot or generated_to_plot:
            legend = self.axes.legend(loc='best', fontsize=7)
            if legend is not None:
                try:
                    legend.set_draggable(True)  # matplotlib >= 3.1
                except AttributeError:
                    legend.draggable(True)      # older matplotlib
        self.axes.autoscale()
        if progress is not None:
            progress.setValue(count)
        self.draw()
        return truncated

    def clear_plot(self):
        self.axes.clear()
        self.axes.set_xticks([])
        self.axes.set_yticks([])
        for spine in self.axes.spines.values():
            spine.set_visible(False)
        self.axes.text(0.5, 0.5, 'Click "Compute Preview" to see the generated spectra here',
                        ha='center', va='center', transform=self.axes.transAxes,
                        color='#999999', fontsize=11)
        self.draw()


# ======================================================================= #
#  _ComponentDiagnosticsDialog — "Guess # of components" (point 3)        #
# ======================================================================= #

class _ComponentDiagnosticsDialog(QDialog):
    """A much lighter version of SVD Analysis's own Diagnostics tab: a
    single switchable plot (component variance / singular values /
    residual error, each as bar or line, log or linear scale), so the
    user can judge visually how many components carry real signal.
    Deliberately does NOT state a specific suggested number — a plot
    lets the user judge for themselves rather than being told a number
    that may not fit their data's structure (see the discussion of
    Malinowski IND's failure mode in SVDInterpolationManager.
    compute_component_diagnostics)."""

    def __init__(self, parent, manager):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Guess # of Components")
        self.setMinimumSize(680, 560)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        layout = QVBoxLayout(self)

        note = QLabel(
            "Look for the \u2018elbow\u2019 \u2014 where the plot drops off "
            "sharply and then flattens out \u2014 as a rough guide to how many "
            "components carry real signal versus noise. This is a visual aid "
            "only; nothing here is picked for you.")
        note.setWordWrap(True)
        layout.addWidget(note)

        controls_row = QHBoxLayout()
        controls_row.addWidget(QLabel("Metric:"))
        self._metric_combo = QComboBox()
        self._metric_combo.addItems(
            ["Component variance", "Singular values", "Residual error"])
        self._metric_combo.currentIndexChanged.connect(self._redraw)
        controls_row.addWidget(self._metric_combo)

        controls_row.addSpacing(12)
        self._bar_radio = QRadioButton("Bar")
        self._bar_radio.setChecked(True)
        self._line_radio = QRadioButton("Line")
        style_group = QButtonGroup(self)
        style_group.addButton(self._bar_radio)
        style_group.addButton(self._line_radio)
        self._bar_radio.toggled.connect(self._redraw)
        controls_row.addWidget(self._bar_radio)
        controls_row.addWidget(self._line_radio)

        controls_row.addSpacing(12)
        self._log_cb = QCheckBox("Log scale")
        self._log_cb.setChecked(True)
        self._log_cb.toggled.connect(self._redraw)
        controls_row.addWidget(self._log_cb)
        controls_row.addStretch()
        layout.addLayout(controls_row)

        self._fig = Figure(figsize=(6, 4.5), tight_layout=True)
        self._ax1 = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        toolbar = NavigationToolbar(self._canvas, self)
        layout.addWidget(toolbar)
        layout.addWidget(self._canvas, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._redraw()

    def _current_series(self):
        """Returns (values, ylabel, title, show_cumulative) for whichever
        metric is currently selected. show_cumulative is only True for
        Component variance, where a cumulative-% overlay is meaningful."""
        metric = self._metric_combo.currentText()
        if metric == "Singular values":
            return self.manager.s, "Singular value", "Singular values", False
        if metric == "Residual error":
            re = self.manager.compute_residual_errors()
            return re, "Residual error RE(m)", "Residual error", False
        ev = self.manager.explained_variance
        return ev, "Explained variance (%)", "Component variance", True

    def _redraw(self, *_args):
        values, ylabel, title, show_cumulative = self._current_series()
        self._ax1.clear()
        if hasattr(self, '_ax2') and self._ax2 is not None:
            self._ax2.remove()
            self._ax2 = None

        n = 0 if values is None else len(values)
        n_show = min(n, 50)  # plenty to see the shape, avoids clutter
                              # when there are thousands of components.
        if n_show == 0:
            self._ax1.text(0.5, 0.5, 'No data available', ha='center', va='center',
                            transform=self._ax1.transAxes, color='#999999')
            self._canvas.draw()
            return

        x = np.arange(1, n_show + 1)
        y = np.asarray(values[:n_show], dtype=float)
        log_scale = self._log_cb.isChecked()
        y_plot = np.maximum(y, 1e-12) if log_scale else y  # log can't show 0/negative

        if self._bar_radio.isChecked():
            self._ax1.bar(x, y_plot, color='#1f77b4', alpha=0.75, label=ylabel)
        else:
            self._ax1.plot(x, y_plot, color='#1f77b4', marker='o', ms=4,
                            lw=1.5, label=ylabel)
        if log_scale:
            self._ax1.set_yscale('log')
        self._ax1.set_xlabel('Component')
        self._ax1.set_ylabel(ylabel + (' \u2014 log scale' if log_scale else ''))
        self._ax1.set_title(f'{title} (first {n_show} of {n})')
        self._ax1.grid(True, linestyle='--', alpha=0.4)

        if show_cumulative:
            ev = self.manager.explained_variance
            cum = np.cumsum(ev)[:n_show]
            self._ax2 = self._ax1.twinx()
            self._ax2.plot(x, cum, color='#d62728', marker='o', ms=3, lw=1.5,
                            label='Cumulative variance (%)')
            self._ax2.set_ylabel('Cumulative variance (%)')
            self._ax2.set_ylim(0, 105)
            lines1, labels1 = self._ax1.get_legend_handles_labels()
            lines2, labels2 = self._ax2.get_legend_handles_labels()
            self._ax1.legend(lines1 + lines2, labels1 + labels2,
                              loc='center right', fontsize=8)
        else:
            self._ax2 = None
            self._ax1.legend(loc='best', fontsize=8)

        self._canvas.draw()


# ======================================================================= #
#  SVDInterpolationDialog                                                  #
# ======================================================================= #

class SVDInterpolationDialog(QDialog):
    """
    Workflow:
      1. SVD is computed (in the background, with a progress dialog) from
         the spectra passed in (they've already been confirmed to share
         one x-axis by the controller).
      2. User enters/edits the parameter value for each spectrum (e.g. the
         temperature it was measured at) in the table on the left, either
         by hand or loaded from a file.
      3. User picks a component from the list and, with point editing
         switched On, clicks on its coefficient plot to place points
         describing how that coefficient varies with the parameter;
         Spline (default) or Polynomial connects them. Whichever
         components end up with a curve (>=2 points) are what get used —
         there's no separate "include this component" step. "Guess # of
         components" opens a small elbow-plot dialog to help judge how
         many are worth bothering with (a visual aid only — nothing is
         picked automatically).
      4. User enters target parameter values (typed, or from a
         start/end/step range) and, in the Preview tab, clicks Compute
         Preview to see the result WITHOUT adding anything yet. Add as
         New (bottom) evaluates every used component's curve at each
         target, reconstructs sum_k U[:,k]*s[k]*coeff_k(target), and adds
         the results to the main spectrum list via the controller.
    """

    def __init__(self, parent, controller, spectra):
        super().__init__(parent)
        self.setWindowTitle("SVD Interpolation — Create Spectra from Fitted Coefficients")
        self.setMinimumSize(1250, 800)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self.svd_controller = controller
        self.manager = controller.manager
        self.spectra = spectra
        self.source_labels = [s['label'] for s in spectra]

        self._active_component = None   # which component's curve is being edited
        self._last_generated = []
        self._svd_ready = False

        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        try:
            self._build_ui()
        finally:
            QApplication.restoreOverrideCursor()

        self._initial_compute_pending = True

    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _param_display_labels_map(self):
        """{full_label: display_label} for every spectrum in self.spectra
        — used by the parameter table's Spectrum-column delegate, which
        calls this on every paint so it always reflects the checkbox's
        current state."""
        return shorten_spectra_labels(self.spectra, self._shorten_names_enabled())

    def _on_shorten_names_toggled(self, _state=None):
        """Refresh everything this dialog's own Shorten Names checkbox
        affects: the two preview list delegates (paint-only, just needs a
        repaint), the parameter table's Spectrum column (also paint-only),
        and the preview plot's legend text (baked into matplotlib Text
        objects at draw time, so it needs an actual redraw, not just a
        repaint — only bother if a preview has already been generated)."""
        self._preview_source_list.viewport().update()
        self._preview_gen_list.viewport().update()
        self._param_table.viewport().update()
        if getattr(self, '_last_generated', None):
            self._redraw_preview()

    def showEvent(self, event):
        super().showEvent(event)
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        if self._initial_compute_pending:
            self._initial_compute_pending = False
            QTimer.singleShot(50, self._start_svd_computation)

    # ------------------------------------------------------------------
    # SVD computation (background thread + progress dialog) — point 6
    # ------------------------------------------------------------------
    def _start_svd_computation(self):
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        self._svd_progress = QProgressDialog('Computing SVD\u2026', None, 0, 0, self)
        self._svd_progress.setWindowModality(Qt.WindowModal)
        self._svd_progress.setWindowTitle('SVD Interpolation')
        self._svd_progress.setMinimumDuration(0)
        self._svd_progress.setCancelButton(None)
        self._svd_progress.show()
        # No processEvents() here — the computation runs on the worker
        # thread below, so this returns to Qt's real event loop almost
        # immediately, which paints the progress dialog on its own.
        self._svd_worker = _ComputeWorker(
            lambda: self.manager.compute_svd_from_spectra(self.spectra), self)
        self._svd_worker.done.connect(self._on_svd_computed)
        self._svd_worker.start(QThread.LowPriority)

    def _on_svd_computed(self):
        self._svd_progress.close()
        # .close() only hides it — being parented to self, Qt keeps the
        # native window alive until self closes or this is called
        # explicitly. Without it, every one of these accumulates as an
        # invisible-but-real window for the dialog's whole lifetime,
        # which shows up as ghost thumbnails when hovering the taskbar.
        self._svd_progress.deleteLater()
        try:
            if self._svd_worker.error is not None:
                QMessageBox.critical(self, "Error",
                                      f"Error computing SVD: {self._svd_worker.error}")
                self.reject()
                return
            if not self._svd_worker.result:
                QMessageBox.critical(self, "SVD Failed",
                                      "Could not compute SVD for the selected spectra.")
                self.reject()
                return

            self._svd_ready = True
            self._populate_parameter_table()
            self._populate_component_list()
            n_comp = self.manager.get_n_components()
            self._autofill_n_spin.setRange(1, max(1, n_comp))
            self._autofill_n_spin.setValue(min(5, n_comp) or 1)
            self.preview_canvas.clear_plot()
        finally:
            QApplication.restoreOverrideCursor()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        # ---------------- Left: settings ----------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(2, 2, 2, 2)
        left_layout.setSpacing(8)

        # Step 1 — parameter values
        param_grp = QGroupBox("1. Parameter values (e.g. temperature)")
        pv = QVBoxLayout(param_grp)
        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("Parameter name:"))
        self._param_label_edit = QLineEdit("Temperature")
        label_row.addWidget(self._param_label_edit, 1)

        # This dialog's own, independent "shorten names" toggle — feeds
        # the parameter table's Spectrum column below, the Preview tab's
        # source/generated list delegates, and the preview plot's legend
        # (see _on_shorten_names_toggled), so it lives here rather than
        # under any one of those individually.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)
        label_row.addWidget(self.checkBox_shorten_names)

        pv.addLayout(label_row)

        self._param_table = QTableWidget()
        self._param_table.setColumnCount(2)
        self._param_table.setHorizontalHeaderLabels(["Spectrum", "Parameter value"])
        self._param_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._param_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._param_table.setMinimumHeight(160)
        pv.addWidget(self._param_table, 1)
        self._install_table_clipboard_shortcuts(self._param_table)
        # Display-only "shorten names" for the Spectrum column — driven by
        # this dialog's own checkbox (built later, in the Preview tab; see
        # _param_display_labels_map). Paint-only delegate: item.text()
        # (what _populate_parameter_table sets and what clipboard copy
        # reads) always keeps the full original label.
        self._param_table.setItemDelegateForColumn(
            0, make_display_text_delegate(self._param_display_labels_map, parent=self._param_table))

        apply_row = QHBoxLayout()
        self._apply_params_btn = QPushButton("Apply parameter values")
        self._apply_params_btn.setToolTip(
            "Confirms the values above and refreshes every coefficient\n"
            "plot's x-axis to use them. Must be applied at least once\n"
            "before curves can be fit.")
        self._apply_params_btn.setStyleSheet(
            "QPushButton { background-color: #1565C0; color: white; "
            "font-weight: bold; padding: 5px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #0D47A1; }")
        self._apply_params_btn.clicked.connect(self._on_apply_parameters)
        apply_row.addWidget(self._apply_params_btn, 1)
        self._from_file_btn = QPushButton("From file")
        self._from_file_btn.setToolTip(
            "Load parameter values from a text file — one value per line,\n"
            "in the same order as the spectra above. A leading index\n"
            "column is tolerated; the last number on each line is used.")
        self._from_file_btn.clicked.connect(self._on_load_from_file)
        apply_row.addWidget(self._from_file_btn)
        pv.addLayout(apply_row)
        left_layout.addWidget(param_grp)

        # Step 2 — pick a component, shape its curve. No separate
        # "include this component" checklist: exactly like Manual
        # Baseline doesn't ask you to check off which spectra get
        # corrected — you just pick one and add points. Whichever
        # components end up with a curve (>=2 points) are used in the
        # reconstruction; components you never touch are automatically
        # left out, no separate step needed.
        comp_grp = QGroupBox("2. Components & curve fit")
        cv = QVBoxLayout(comp_grp)

        comp_header = QHBoxLayout()
        comp_header.addWidget(QLabel("Pick a component to edit:"))
        self._guess_components_btn = QPushButton("Guess # of components")
        self._guess_components_btn.setToolTip(
            "Opens a simplified diagnostic plot to help you judge how\n"
            "many components carry real signal — you decide, this\n"
            "doesn't pick a number for you.")
        self._guess_components_btn.clicked.connect(self._show_component_diagnostics_dialog)
        comp_header.addWidget(self._guess_components_btn)
        comp_header.addStretch()
        comp_header.addWidget(_make_help_button(
            "Help for Components & curve fit", self._show_components_help))
        cv.addLayout(comp_header)
        self._component_list = QListWidget()
        self._component_list.setMinimumHeight(140)
        self._component_list.currentRowChanged.connect(self._on_component_row_changed)
        cv.addWidget(self._component_list, 1)

        cv.addWidget(self._separator())

        poly_row = QHBoxLayout()
        self._poly_radio = QRadioButton("Polynomial")
        self._poly_order_spin = QSpinBox()
        self._poly_order_spin.setRange(1, 10)
        self._poly_order_spin.setValue(2)
        self._poly_order_spin.setPrefix("Degree: ")
        self._poly_order_spin.setVisible(False)
        self._poly_order_spin.valueChanged.connect(self._on_poly_order_changed)
        poly_row.addWidget(self._poly_radio)
        poly_row.addWidget(self._poly_order_spin, 1)
        cv.addLayout(poly_row)

        spline_row = QHBoxLayout()
        self._spline_radio = QRadioButton("Spline")
        self._spline_radio.setChecked(True)  # spline is the default fit type
        self._spline_smoothing_spin = QDoubleSpinBox()
        self._spline_smoothing_spin.setRange(0.0, 1e6)
        self._spline_smoothing_spin.setDecimals(4)
        self._spline_smoothing_spin.setValue(0.0)
        self._spline_smoothing_spin.setPrefix("Smoothing: ")
        self._spline_smoothing_spin.setToolTip(
            "How loosely the curve is allowed to deviate from your points,\n"
            "instead of passing through each one exactly.\n\n"
            "0 = interpolating spline: passes exactly through every point\n"
            "(can look wiggly if your points don't lie on a smooth trend).\n\n"
            "Larger values let the curve smooth over scatter in your points\n"
            "at the cost of missing them exactly — there's no universal\n"
            "'correct' number, since it depends on your points' scale and\n"
            "scatter. Try raising it gradually from 0 while watching the\n"
            "curve until it looks reasonable.")
        self._spline_smoothing_spin.valueChanged.connect(self._on_spline_smoothing_changed)
        spline_row.addWidget(self._spline_radio)
        spline_row.addWidget(self._spline_smoothing_spin, 1)
        cv.addLayout(spline_row)

        fit_group = QButtonGroup(self)
        fit_group.addButton(self._poly_radio)
        fit_group.addButton(self._spline_radio)
        self._poly_radio.toggled.connect(self._on_fit_type_changed)

        # Point-editing On/Off — same convention as Manual Baseline's
        # "Enable Baseline Correction" On/Off: editing and the navigation
        # toolbar's pan/zoom both want left-drag on the canvas, so only
        # one can be active at a time. Clear points shares this row to
        # save vertical space — safe to cram onto one row now that the
        # left panel is wrapped in a scroll area (this row simply wraps
        # narrower with a scrollbar instead of overlapping if it's ever
        # too tight, unlike before).
        cv.addWidget(self._separator())
        edit_row = QHBoxLayout()
        edit_row.addWidget(QLabel("Point editing:"))
        self._edit_mode_group = QButtonGroup(self)
        self._edit_on_btn = QRadioButton("On")
        self._edit_on_btn.setChecked(True)
        self._edit_on_btn.clicked.connect(self._enable_point_editing)
        self._edit_off_btn = QRadioButton("Off")
        self._edit_off_btn.clicked.connect(self._disable_point_editing)
        self._edit_mode_group.addButton(self._edit_on_btn)
        self._edit_mode_group.addButton(self._edit_off_btn)
        edit_row.addWidget(self._edit_on_btn)
        edit_row.addWidget(self._edit_off_btn)
        edit_row.addStretch()
        self._clear_points_btn = QPushButton("Clear points")
        self._clear_points_btn.clicked.connect(self._on_clear_points)
        edit_row.addWidget(self._clear_points_btn)
        edit_row.addWidget(_make_help_button(
            "Help for Point editing", self._show_point_editing_help))
        cv.addLayout(edit_row)

        autofill_row = QHBoxLayout()
        self._autofill_btn = QPushButton("Auto-fill current")
        self._autofill_btn.setToolTip(
            "Places a point at every measured (parameter, coefficient)\n"
            "pair for this component, and switches it to Spline with\n"
            "smoothing 0 — an exact fit through every measured point.\n"
            "For interpolating BETWEEN measured values this is usually\n"
            "excellent and much faster than clicking points by hand;\n"
            "you can still adjust points afterward, or clear them and\n"
            "start over manually. Extrapolating beyond the measured\n"
            "range is still just as much of a guess as with any\n"
            "hand-placed curve.")
        self._autofill_btn.clicked.connect(self._on_autofill_clicked)
        autofill_row.addWidget(self._autofill_btn)

        autofill_row.addWidget(QLabel("Auto fill first"))
        self._autofill_n_spin = QSpinBox()
        self._autofill_n_spin.setRange(1, 1)  # range widened once SVD is ready
        self._autofill_n_spin.setToolTip(
            "It's fine to include more components than seem strictly\n"
            "necessary — same reasoning as SVD Background's denoising\n"
            "(throwing out only the low-weight components): a component\n"
            "with negligible weight barely changes the reconstruction\n"
            "either way, so over-including doesn't really hurt, and can\n"
            "help the result carry the same general noise character as\n"
            "the original spectra.")
        autofill_row.addWidget(self._autofill_n_spin)
        self._autofill_bulk_btn = QPushButton("components")
        self._autofill_bulk_btn.setToolTip(
            "Applies Auto-fill current (left) to each of the first N\n"
            "components at once, instead of one at a time.")
        self._autofill_bulk_btn.clicked.connect(self._on_autofill_bulk_clicked)
        autofill_row.addWidget(self._autofill_bulk_btn)
        autofill_row.addStretch()
        cv.addLayout(autofill_row)

        left_layout.addWidget(comp_grp, 1)

        # Step 3 — target values. The actual preview/generate buttons
        # live in the Preview tab (see point 11 in the handoff) and at
        # the bottom of the dialog, not here — this group only defines
        # WHAT values to generate for.
        target_grp = QGroupBox("3. Target values")
        tv = QVBoxLayout(target_grp)
        target_header = QHBoxLayout()
        target_desc = QLabel("New parameter values (comma or newline separated), "
                              "e.g. 22, 37, 42:")
        target_desc.setWordWrap(True)
        target_header.addWidget(target_desc, 1)
        target_header.addWidget(_make_help_button(
            "Help for Target values", self._show_target_values_help))
        tv.addLayout(target_header)
        self._target_edit = QTextEdit()
        self._target_edit.setMinimumHeight(60)
        self._target_edit.textChanged.connect(self._invalidate_preview)
        tv.addWidget(self._target_edit, 1)

        range_row = QHBoxLayout()
        self._range_start_spin = QDoubleSpinBox()
        self._range_start_spin.setRange(-1e9, 1e9)
        self._range_start_spin.setDecimals(4)
        self._range_start_spin.setPrefix("start ")
        self._range_end_spin = QDoubleSpinBox()
        self._range_end_spin.setRange(-1e9, 1e9)
        self._range_end_spin.setDecimals(4)
        self._range_end_spin.setValue(10.0)
        self._range_end_spin.setPrefix("end ")
        self._range_step_spin = QDoubleSpinBox()
        self._range_step_spin.setRange(1e-6, 1e9)
        self._range_step_spin.setDecimals(4)
        self._range_step_spin.setValue(1.0)
        self._range_step_spin.setPrefix("step ")
        for w in (self._range_start_spin, self._range_end_spin, self._range_step_spin):
            range_row.addWidget(w)
        self._range_confirm_btn = QPushButton("Add")
        self._range_confirm_btn.setToolTip(
            "Appends every value from start to end (inclusive), stepping\n"
            "by step, to the target values above — on top of whatever's\n"
            "already there, not replacing it.")
        self._range_confirm_btn.clicked.connect(self._on_confirm_range_clicked)
        range_row.addWidget(self._range_confirm_btn)
        tv.addLayout(range_row)

        left_layout.addWidget(target_grp)

        # Buttons grouped together via QDialogButtonBox, same convention
        # as Manual Baseline's bottom row. Apply/Add as New now match
        # every other Spectra Processing operation's pair (Normalization,
        # Spike Removal, ...): Apply replaces the measured source spectra
        # with the interpolated result and closes the dialog; Add as New
        # keeps the sources untouched and appends the result under new
        # names. Add as New's own behavior (no confirmation prompt,
        # dialog stays open so more target values can be generated in
        # the same session) is unchanged from before Apply existed.
        button_box = QDialogButtonBox()

        self._help_btn = QPushButton("Help")
        self._help_btn.clicked.connect(self._show_help)
        button_box.addButton(self._help_btn, QDialogButtonBox.HelpRole)

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setToolTip(
            "Generates one new spectrum per target value, REMOVES the\n"
            "source spectra that fed the SVD basis from the main\n"
            "spectrum list, and adds the interpolated spectra in their\n"
            "place. Closes this dialog on success.")
        self._apply_btn.setStyleSheet(
            "QPushButton { background-color: #1565C0; color: white; "
            "font-weight: bold; padding: 5px 10px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #0D47A1; }")
        self._apply_btn.clicked.connect(self._on_apply_clicked)
        button_box.addButton(self._apply_btn, QDialogButtonBox.ActionRole)

        self._add_as_new_btn = QPushButton("Add as New")
        self._add_as_new_btn.setToolTip(
            "Generates one new spectrum per target value and adds them\n"
            "to the main spectrum list, alongside your original spectra\n"
            "(nothing existing is ever modified or replaced).")
        self._add_as_new_btn.setStyleSheet(
            "QPushButton { background-color: #2E7D32; color: white; "
            "font-weight: bold; padding: 5px 10px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #1B5E20; }")
        self._add_as_new_btn.clicked.connect(self._on_add_as_new_clicked)
        button_box.addButton(self._add_as_new_btn, QDialogButtonBox.ActionRole)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_box.addButton(close_btn, QDialogButtonBox.RejectRole)

        left_layout.addWidget(button_box)

        left.setMinimumWidth(480)
        left_scroll = QScrollArea()
        left_scroll.setWidget(left)
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(500)
        splitter.addWidget(left_scroll)

        # ---------------- Right: plots ----------------
        self._tabs = QTabWidget()
        self._tabs.setElideMode(Qt.ElideNone)
        self._tabs.setDocumentMode(True)
        # Belt-and-suspenders fix for tab-bar text clipping: explicit
        # padding via QSS (some native styles draw tab-edge decoration
        # that otherwise eats into unpadded text).
        self._tabs.setStyleSheet(
            "QTabBar::tab { padding: 6px 16px; min-width: 90px; }")

        curve_tab = QWidget()
        curve_tab_layout = QVBoxLayout(curve_tab)
        curve_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.curve_canvas = CurvePointCanvas(curve_tab)
        self.curve_canvas.point_added.connect(self._on_point_added)
        self.curve_canvas.point_removed.connect(self._on_point_removed)
        self._curve_toolbar = NavigationToolbar(self.curve_canvas, curve_tab)
        self.coordinates_label = QLabel("")
        self.coordinates_label.setStyleSheet("background-color: #f0f0f0; padding: 2px;")
        curve_tab_layout.addWidget(self._curve_toolbar)
        curve_tab_layout.addWidget(self.coordinates_label)
        self.curve_canvas.clear_plot()

        # Point 3 — optional subspectrum view for the currently-selected
        # component. Off by default (not usually needed for this
        # workflow's purpose), but a visibly noisy subspectrum can be a
        # sign the component isn't statistically relevant — consistent
        # with what the elbow plot (Guess # of components) would suggest,
        # and useful to sanity-check right next to the curve that would
        # actually use it for reconstruction.
        subspectrum_row = QHBoxLayout()
        self._show_subspectrum_cb = QCheckBox("Show subspectrum for this component")
        self._show_subspectrum_cb.setChecked(False)
        self._show_subspectrum_cb.setToolTip(
            "Shows the actual subspectrum (U column) for the currently\n"
            "selected component below. Not usually useful for this\n"
            "workflow — but a noisy-looking subspectrum can indicate\n"
            "the component isn't statistically relevant, consistent\n"
            "with the elbow plot.")
        self._show_subspectrum_cb.toggled.connect(self._on_show_subspectrum_toggled)
        subspectrum_row.addWidget(self._show_subspectrum_cb)
        subspectrum_row.addStretch()
        curve_tab_layout.addLayout(subspectrum_row)

        self._subspectrum_fig = Figure(figsize=(6, 2), tight_layout=True)
        self._subspectrum_ax = self._subspectrum_fig.add_subplot(111)
        self._subspectrum_canvas = FigureCanvas(self._subspectrum_fig)
        self._subspectrum_canvas.setVisible(False)

        # A splitter, not a fixed max-height, so the user can drag to
        # give the subspectrum more (or less) room instead of being
        # stuck with a small fixed strip.
        curve_splitter = QSplitter(Qt.Vertical)
        curve_splitter.addWidget(self.curve_canvas)
        curve_splitter.addWidget(self._subspectrum_canvas)
        curve_splitter.setStretchFactor(0, 3)
        curve_splitter.setStretchFactor(1, 1)
        curve_splitter.setSizes([600, 0])  # subspectrum starts collapsed (hidden anyway)
        curve_tab_layout.addWidget(curve_splitter, 1)
        self._curve_splitter = curve_splitter

        self._tabs.addTab(curve_tab, "  Coefficient curve  ")

        preview_tab = QWidget()
        preview_tab_layout = QVBoxLayout(preview_tab)
        preview_tab_layout.setContentsMargins(4, 4, 4, 4)

        preview_controls_row1 = QHBoxLayout()
        self._compute_preview_btn = QPushButton("Compute Preview")
        self._compute_preview_btn.setToolTip(
            "Computes the spectra for the current target values and\n"
            "shows them below — WITHOUT adding anything to the main\n"
            "spectrum list yet. Use Add as New (bottom of the dialog)\n"
            "once you're happy with the preview.")
        self._compute_preview_btn.clicked.connect(self._on_compute_preview_clicked)
        preview_controls_row1.addWidget(self._compute_preview_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.setToolTip(
            "Saves the currently computed spectra directly to a file\n"
            "(text, Excel, or individual files) — WITHOUT adding them\n"
            "to the main spectrum list. Saves exactly what's currently\n"
            "computed, regardless of which ones are checked/shown below.")
        self._save_btn.clicked.connect(self._on_save_clicked)
        preview_controls_row1.addWidget(self._save_btn)

        preview_controls_row1.addSpacing(16)
        preview_controls_row1.addWidget(QLabel("Legend limit:"))
        self._legend_limit_spin = QSpinBox()
        self._legend_limit_spin.setRange(1, 100000)
        self._legend_limit_spin.setValue(30)
        self._legend_limit_spin.setToolTip(
            "How many of the selected source spectra, and separately\n"
            "how many of the selected generated spectra, get their own\n"
            "legend entry (each list capped independently).")
        self._legend_limit_spin.valueChanged.connect(self._on_preview_display_changed)
        preview_controls_row1.addWidget(self._legend_limit_spin)
        self._show_full_legend_cb = QCheckBox("Show full legend")
        self._show_full_legend_cb.setToolTip(
            "Include every selected generated line in the legend,\n"
            "ignoring the limit above — can be slow if that's a lot\n"
            "of lines.")
        self._show_full_legend_cb.toggled.connect(self._on_preview_display_changed)
        preview_controls_row1.addWidget(self._show_full_legend_cb)

        preview_controls_row1.addStretch()
        preview_tab_layout.addLayout(preview_controls_row1)

        # Two independent multi-select lists (point 5) — pick any
        # combination of original and generated spectra to actually draw.
        lists_row = QHBoxLayout()

        source_col = QVBoxLayout()
        source_header = QHBoxLayout()
        source_header.addWidget(QLabel(f"Original spectra ({len(self.spectra)}):"))
        source_header.addStretch()
        source_all_btn = QPushButton("All")
        source_all_btn.setMinimumWidth(46)
        source_none_btn = QPushButton("None")
        source_none_btn.setMinimumWidth(58)
        source_header.addWidget(source_all_btn)
        source_header.addWidget(source_none_btn)
        source_col.addLayout(source_header)
        self._preview_source_list = QListWidget()
        self._preview_source_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._preview_source_list.setMaximumHeight(150)
        for s in self.spectra:
            self._preview_source_list.addItem(QListWidgetItem(s['label']))
        # Display-only "shorten names" — selection is positional (see
        # _redraw_preview's .row(it)), never by matching displayed text.
        self._preview_source_list.setItemDelegate(
            make_shortened_name_delegate(self._preview_source_list, self._shorten_names_enabled)
        )
        # Nothing selected by default (as if "None" were pressed) — the
        # user opts in to what they want to see, rather than the preview
        # starting from a potentially huge, slow-to-draw selection.
        self._preview_source_list.itemSelectionChanged.connect(self._on_preview_display_changed)
        source_all_btn.clicked.connect(self._preview_source_list.selectAll)
        source_none_btn.clicked.connect(self._preview_source_list.clearSelection)
        source_col.addWidget(self._preview_source_list)
        lists_row.addLayout(source_col)

        gen_col = QVBoxLayout()
        gen_header = QHBoxLayout()
        self._preview_gen_header_label = QLabel("Generated spectra (0):")
        gen_header.addWidget(self._preview_gen_header_label)
        gen_header.addStretch()
        gen_all_btn = QPushButton("All")
        gen_all_btn.setMinimumWidth(46)
        gen_none_btn = QPushButton("None")
        gen_none_btn.setMinimumWidth(58)
        gen_header.addWidget(gen_all_btn)
        gen_header.addWidget(gen_none_btn)
        gen_col.addLayout(gen_header)
        self._preview_gen_list = QListWidget()
        self._preview_gen_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._preview_gen_list.setMaximumHeight(150)
        # Display-only "shorten names" — same reasoning as
        # _preview_source_list above.
        self._preview_gen_list.setItemDelegate(
            make_shortened_name_delegate(self._preview_gen_list, self._shorten_names_enabled)
        )
        self._preview_gen_list.itemSelectionChanged.connect(self._on_preview_display_changed)
        gen_all_btn.clicked.connect(self._preview_gen_list.selectAll)
        gen_none_btn.clicked.connect(self._preview_gen_list.clearSelection)
        gen_col.addWidget(self._preview_gen_list)
        lists_row.addLayout(gen_col)

        preview_tab_layout.addLayout(lists_row)

        self.preview_canvas = PreviewCanvas(preview_tab)
        preview_toolbar = NavigationToolbar(self.preview_canvas, preview_tab)
        preview_tab_layout.addWidget(preview_toolbar)
        preview_tab_layout.addWidget(self.preview_canvas, 1)
        self._tabs.addTab(preview_tab, "  Preview  ")

        splitter.addWidget(self._tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([480, 900])

        self._enable_point_editing()

    @staticmethod
    def _separator():
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    @staticmethod
    def _install_table_clipboard_shortcuts(table):
        """Excel-style copy/cut/paste/delete for column 1 (Parameter
        value) — same pattern as rename_spectra_dialog.py's New Label
        column and svd_analysis_dialog.py's own parameter-value table."""

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

    def _show_components_help(self):
        QMessageBox.information(
            self, "Components & Curve Fit \u2014 Help",
            "<html><body style='font-family: Arial, sans-serif; font-size: 12px;'>"
            "<p>Select a component from the list, then add points below to define "
            "its curve. A <b>&#10003;</b> appears next to any component that already "
            "has one (&ge;2 points).</p>"
            "<p><b>Selection is implicit:</b> whichever components end up with a "
            "curve are the ones used in the reconstruction \u2014 components you "
            "never add points to are simply left out, exactly like Manual Baseline "
            "only corrects spectra you've actually placed points on.</p>"
            "<p>Points are remembered per component as you switch between them in "
            "the list, so you can freely go back and forth without losing anything."
            "</p>"
            "<p><b>Spline smoothing:</b> controls how loosely the curve is allowed "
            "to deviate from your points instead of passing through each one "
            "exactly. <b>0</b> = interpolating spline (passes exactly through "
            "every point, which can look wiggly if the points aren't on a smooth "
            "trend). Larger values let the curve smooth over scatter in your "
            "points at the cost of missing them exactly. There's no single "
            "'correct' value \u2014 it depends on your points' scale and scatter, "
            "so try raising it gradually from 0 while watching the curve.</p>"
            "<p><b>Guess # of components</b> opens a small separate diagnostic "
            "plot (variance / singular values / residual error) purely as a "
            "visual aid \u2014 nothing here picks a number for you.</p>"
            "<hr>"
            "<p><b>Auto-fill current / Auto fill first N</b> \u2014 places a point "
            "at every measured value and switches to an exact-fit spline. Worth "
            "understanding what this actually does: if you auto-fill EVERY "
            "component, the reconstruction at your measured parameter values "
            "will match the original spectra exactly \u2014 that's not a "
            "coincidence, it's just what SVD reconstruction means "
            "(&Sigma; U&middot;S&middot;V<sup>T</sup> reproduces the original data "
            "matrix exactly). So auto-fill's real value is entirely in the gaps "
            "<em>between</em> your measured values \u2014 that's the only place "
            "this tool actually does something a lookup table couldn't.</p>"
            "<p><b>About noise:</b> auto-fill reproduces each component's "
            "measured coefficients exactly, including any noise in them. For "
            "low-weight components this is usually harmless \u2014 often even "
            "desirable, since it lets the generated spectra carry the same "
            "general noise character as your real data rather than looking "
            "artificially clean. It only becomes a real problem if the noise "
            "has a genuine PATTERN and shows up in a statistically relevant "
            "(high-weight) component. Two ways to handle that: manually smooth "
            "just that component's curve (or place fewer, more deliberate "
            "points), or simply leave the outlier spectra out of the selection "
            "in the main window before running this tool at all.</p>"
            "<p><b>Extrapolation</b> beyond your measured parameter range is "
            "really the main case where manual point placement still matters "
            "\u2014 auto-fill has no opinion out there, a spline just continues "
            "on from its last segment. Manual points let you impose a trend you "
            "actually believe in, though it's inherently speculative either way "
            "and worth treating with some caution.</p>"
            "</body></html>")

    def _show_point_editing_help(self):
        QMessageBox.information(
            self, "Point Editing \u2014 Help",
            "<html><body style='font-family: Arial, sans-serif; font-size: 12px;'>"
            "<p><b>On:</b> left-click the plot to add a point, right-click to remove "
            "the nearest one. The zoom/pan toolbar above the plot is disabled while "
            "this is on, since both want left-click-drag on the canvas.</p>"
            "<p><b>Off:</b> use the toolbar to zoom, pan, or reset the view instead "
            "\u2014 clicking the plot won't add or remove points.</p>"
            "<p>Gray dots on the plot are the true, measured coefficients from the "
            "SVD \u2014 not editable, just a reference for placing your own points.</p>"
            "<p><b>Clear points</b> removes every point for the CURRENTLY SELECTED "
            "component only \u2014 other components' points are untouched.</p>"
            "</body></html>")

    def _show_target_values_help(self):
        QMessageBox.information(
            self, "Target Values \u2014 Help",
            "<html><body style='font-family: Arial, sans-serif; font-size: 12px;'>"
            "<p>These are the parameter values (e.g. temperatures) you want NEW, "
            "synthesized spectra for. Type them directly \u2014 comma or newline "
            "separated, e.g. <span style='font-family:monospace'>22, 37, 42</span> "
            "\u2014 or use the start / end / step fields below and click "
            "<b>Add</b> to append an evenly-spaced run instead (e.g. start 5, end "
            "90, step 5 \u2192 5, 10, 15, ... 90). Both can be combined \u2014 "
            "Add appends on top of whatever's already typed, it never replaces it."
            "</p>"
            "<p>Values outside the range of your measured parameter values are "
            "allowed (extrapolation) but get less trustworthy the further out "
            "they go \u2014 the curve is a guess beyond the data it was fit to.</p>"
            "</body></html>")

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------
    def _populate_parameter_table(self):
        labels = self.manager.spectrum_labels or []
        self._param_table.setRowCount(len(labels))
        for i, label in enumerate(labels):
            item = QTableWidgetItem(label)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self._param_table.setItem(i, 0, item)
            val_item = QTableWidgetItem(str(i + 1))  # sensible default: 1, 2, 3...
            self._param_table.setItem(i, 1, val_item)

    def _component_label(self, k):
        ev = self.manager.explained_variance
        pct = ev[k] if ev is not None else 0
        mark = '\u2713 ' if len(self.manager.get_curve_points(k)) >= 2 else '\u2003 '
        # 4 decimals, not 2 — with many spectra, a component can be
        # "100.00% / 0.00%" at 2 decimals while actually being 99.96% /
        # 0.038%, which matters when judging what's worth including.
        return f"{mark}Component {k + 1}  ({pct:.4f} % variance)"

    def _populate_component_list(self):
        n = self.manager.get_n_components()
        self._component_list.blockSignals(True)
        self._component_list.clear()
        for k in range(n):
            item = QListWidgetItem(self._component_label(k))
            item.setData(Qt.UserRole, k)
            self._component_list.addItem(item)
        self._component_list.blockSignals(False)
        if n > 0:
            self._component_list.setCurrentRow(0)

    def _refresh_component_list_labels(self):
        """Update the \u2713 marker after points change, without disturbing
        the current selection."""
        for i in range(self._component_list.count()):
            item = self._component_list.item(i)
            k = item.data(Qt.UserRole)
            item.setText(self._component_label(k))

    def _show_component_diagnostics_dialog(self):
        """Point 3 — a small, separate diagnostic popup with an elbow
        plot, opened on demand rather than always showing a specific
        suggested number in the main dialog (which read as more
        authoritative/prescriptive than intended — this is a rough visual
        aid, the user decides)."""
        if not self._svd_ready:
            return
        dlg = _ComponentDiagnosticsDialog(self, self.manager)
        dlg.exec_()

    def _components_with_curve(self):
        """Every component that currently has enough points to fit a
        curve — these are the ones used in reconstruction. No separate
        'include this component' step: presence of a curve IS the
        inclusion, same as Manual Baseline never asking which spectra to
        'include' — you just add points to the ones you want corrected."""
        n = self.manager.get_n_components()
        return [k for k in range(n) if len(self.manager.get_curve_points(k)) >= 2]

    # ------------------------------------------------------------------
    # Handlers — parameter values
    # ------------------------------------------------------------------
    def _on_apply_parameters(self):
        values = []
        for i in range(self._param_table.rowCount()):
            item = self._param_table.item(i, 1)
            try:
                values.append(float(item.text()))
            except (ValueError, AttributeError):
                QMessageBox.warning(self, "Invalid Value",
                                     f"Row {i + 1}: parameter value must be numeric.")
                return
        label = self._param_label_edit.text().strip() or None

        # Any curve points already placed (manually or via Auto-fill) are
        # tied to the OLD parameter values — changing them makes those
        # points stale: their x-positions no longer correspond to
        # anything real. Left in place, this is exactly what produced
        # old and new data appearing superimposed on the same plot after
        # re-applying different values. Confirm since it's destructive
        # across every component at once, not just the one being viewed.
        n_comp = self.manager.get_n_components()
        has_existing_points = any(
            len(self.manager.get_curve_points(k)) > 0 for k in range(n_comp))
        if has_existing_points:
            reply = QMessageBox.question(
                self, "Clear Existing Curve Points?",
                "Changing parameter values invalidates any curve points "
                "already placed — they were positioned against the OLD "
                "values, on every component that has any.\n\n"
                "Applying will clear ALL of them so old and new data can't "
                "end up mixed together. Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        if not self.manager.set_parameter_values(values, label=label):
            QMessageBox.warning(self, "Invalid Values",
                                 "Could not apply these parameter values.")
            return

        for k in range(n_comp):
            self.manager.clear_curve_points(k)
        self._refresh_component_list_labels()

        # New parameter values likely span a different range than before
        # — force the plot to re-fit to the new data instead of keeping
        # whatever zoom/framing was left over from the previous values,
        # which could make the new data look wrong, clipped, or blank.
        self.curve_canvas._has_plotted_once = False
        self._refresh_curve_plot()
        self._invalidate_preview()

    def _on_load_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Parameter Values", "", "Text files (*.txt *.csv *.dat);;All files (*)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = [ln.strip() for ln in f if ln.strip()]
        except Exception as e:
            QMessageBox.warning(self, "Load Failed", f"Could not read file: {e}")
            return

        values = []
        for ln in lines:
            # Tolerate a leading index column and other delimiters —
            # take the LAST number-looking token on the line.
            tokens = ln.replace(',', ' ').replace('\t', ' ').split()
            parsed = None
            for tok in reversed(tokens):
                try:
                    parsed = float(tok)
                    break
                except ValueError:
                    continue
            if parsed is None:
                QMessageBox.warning(self, "Load Failed",
                                     f"Could not parse a number from line: '{ln}'")
                return
            values.append(parsed)

        n_expected = self._param_table.rowCount()
        if len(values) != n_expected:
            QMessageBox.warning(
                self, "Count Mismatch",
                f"File has {len(values)} value(s), but there are {n_expected} "
                "spectra. Fix the file (or the selection) and try again.")
            return

        for i, v in enumerate(values):
            self._param_table.setItem(i, 1, QTableWidgetItem(f'{v:g}'))

    # ------------------------------------------------------------------
    # Handlers — components / curve editing
    # ------------------------------------------------------------------
    def _on_component_row_changed(self, row):
        if row < 0:
            self._active_component = None
            self.curve_canvas.clear_plot()
            self._refresh_subspectrum_plot()
            return
        item = self._component_list.item(row)
        k = item.data(Qt.UserRole)
        self._active_component = k
        fit_type = self.manager.get_fit_type(k)
        self._poly_radio.blockSignals(True)
        self._spline_radio.blockSignals(True)
        self._poly_radio.setChecked(fit_type != 'spline')
        self._spline_radio.setChecked(fit_type == 'spline')
        self._poly_radio.blockSignals(False)
        self._spline_radio.blockSignals(False)
        self._poly_order_spin.blockSignals(True)
        self._poly_order_spin.setValue(self.manager.get_poly_order(k))
        self._poly_order_spin.blockSignals(False)
        self._spline_smoothing_spin.blockSignals(True)
        self._spline_smoothing_spin.setValue(self.manager.get_spline_smoothing(k))
        self._spline_smoothing_spin.blockSignals(False)
        self._poly_order_spin.setVisible(fit_type != 'spline')
        self._spline_smoothing_spin.setVisible(fit_type == 'spline')
        self.curve_canvas._has_plotted_once = False
        self._refresh_curve_plot()
        self._refresh_subspectrum_plot()

    def _on_show_subspectrum_toggled(self, checked):
        self._subspectrum_canvas.setVisible(checked)
        if checked:
            # Was collapsed to 0 height while hidden — give it a
            # sensible split now rather than leaving it at 0.
            sizes = self._curve_splitter.sizes()
            if len(sizes) == 2 and sizes[1] == 0:
                total = sum(sizes) or 600
                self._curve_splitter.setSizes([int(total * 0.65), int(total * 0.35)])
            self._refresh_subspectrum_plot()

    def _refresh_subspectrum_plot(self):
        if not getattr(self, '_show_subspectrum_cb', None) or not self._show_subspectrum_cb.isChecked():
            return
        k = self._active_component
        self._subspectrum_ax.clear()
        if k is not None and self.manager.x_axis is not None:
            sub = self.manager.get_subspectrum(k)
            if sub is not None:
                self._subspectrum_ax.plot(self.manager.x_axis, sub, color='#555555', lw=1)
                self._subspectrum_ax.set_title(f'Subspectrum for Component {k + 1}', fontsize=9)
                self._subspectrum_ax.tick_params(labelsize=7)
                self._subspectrum_ax.grid(True, linestyle='--', alpha=0.4)
        else:
            self._subspectrum_ax.text(0.5, 0.5, 'No component selected', ha='center',
                                       va='center', transform=self._subspectrum_ax.transAxes,
                                       color='#999999', fontsize=9)
        self._subspectrum_canvas.draw()

    def _on_fit_type_changed(self, _checked):
        if self._active_component is None:
            return
        fit_type = 'polynomial' if self._poly_radio.isChecked() else 'spline'
        self.manager.set_fit_type(self._active_component, fit_type)
        self._poly_order_spin.setVisible(fit_type == 'polynomial')
        self._spline_smoothing_spin.setVisible(fit_type == 'spline')
        self._refresh_curve_plot()
        self._invalidate_preview()

    def _on_poly_order_changed(self, value):
        if self._active_component is not None:
            self.manager.set_poly_order(self._active_component, value)
            self._refresh_curve_plot()
            self._invalidate_preview()

    def _on_spline_smoothing_changed(self, value):
        if self._active_component is not None:
            self.manager.set_spline_smoothing(self._active_component, value)
            self._refresh_curve_plot()
            self._invalidate_preview()

    def _on_point_added(self, x, y):
        if self._active_component is None:
            return
        self.manager.add_curve_point(self._active_component, x, y)
        self._refresh_curve_plot()
        self._refresh_component_list_labels()
        self._invalidate_preview()

    def _on_point_removed(self, x, y):
        if self._active_component is None:
            return
        self.manager.remove_curve_point(self._active_component, x, y)
        self._refresh_curve_plot()
        self._refresh_component_list_labels()
        self._invalidate_preview()

    def _on_clear_points(self):
        if self._active_component is None:
            return
        self.manager.clear_curve_points(self._active_component)
        self._refresh_curve_plot()
        self._refresh_component_list_labels()
        self._invalidate_preview()

    def _on_autofill_clicked(self):
        """Point 7 — a point at every measured value, fit with an
        interpolating spline (smoothing 0), reproduces the measured
        coefficients almost exactly. For interpolating between measured
        values, this is usually all that's needed — skipping the manual
        click-a-few-points step entirely — discovered empirically to work
        very well in practice. Extrapolation beyond the measured range is
        unaffected by this shortcut; it's still a guess either way."""
        if self._active_component is None:
            return
        param_values = self.manager.get_parameter_values()
        if param_values is None:
            QMessageBox.warning(self, "Parameter Values Needed",
                                 "Click 'Apply parameter values' first.")
            return
        k = self._active_component
        true_coeffs = self.manager.get_coefficients(k)
        self.manager.clear_curve_points(k)
        for pv, tc in zip(param_values, true_coeffs):
            self.manager.add_curve_point(k, float(pv), float(tc))
        self.manager.set_fit_type(k, 'spline')
        self.manager.set_spline_smoothing(k, 0.0)

        self._poly_radio.blockSignals(True)
        self._spline_radio.blockSignals(True)
        self._spline_radio.setChecked(True)
        self._poly_radio.setChecked(False)
        self._poly_radio.blockSignals(False)
        self._spline_radio.blockSignals(False)
        self._poly_order_spin.setVisible(False)
        self._spline_smoothing_spin.blockSignals(True)
        self._spline_smoothing_spin.setValue(0.0)
        self._spline_smoothing_spin.blockSignals(False)
        self._spline_smoothing_spin.setVisible(True)

        self.curve_canvas._has_plotted_once = False
        self._refresh_curve_plot()
        self._refresh_component_list_labels()
        self._refresh_subspectrum_plot()
        self._invalidate_preview()

    def _on_autofill_bulk_clicked(self):
        """Same as _on_autofill_clicked, applied to the first N components
        at once. Deliberately allows N to exceed what 'Guess # of
        components' would suggest — per the user's own observation,
        over-including a low-weight component barely changes the
        reconstruction (its measured coefficients are close to flat/noisy
        either way), so there's little downside, and it can help the
        result carry the same general noise character as the original
        spectra — the same reasoning SVD Background's denoising already
        relies on elsewhere in this app."""
        if not self._svd_ready:
            return
        param_values = self.manager.get_parameter_values()
        if param_values is None:
            QMessageBox.warning(self, "Parameter Values Needed",
                                 "Click 'Apply parameter values' first.")
            return
        n = min(self._autofill_n_spin.value(), self.manager.get_n_components())
        for k in range(n):
            true_coeffs = self.manager.get_coefficients(k)
            self.manager.clear_curve_points(k)
            for pv, tc in zip(param_values, true_coeffs):
                self.manager.add_curve_point(k, float(pv), float(tc))
            self.manager.set_fit_type(k, 'spline')
            self.manager.set_spline_smoothing(k, 0.0)

        self._refresh_component_list_labels()
        # If the currently-displayed component was one of the ones just
        # filled, refresh its controls/plot to reflect the new state.
        row = self._component_list.currentRow()
        if self._active_component is not None and self._active_component < n:
            self.curve_canvas._has_plotted_once = False
            self._on_component_row_changed(row)
            self._refresh_subspectrum_plot()
        self._invalidate_preview()

    def _invalidate_preview(self):
        """Point 8 — any change to parameter values, curves, or target
        values makes the current preview stale; clear it rather than
        risk showing a plot that no longer matches the current settings.
        Press Compute Preview again to see the up-to-date result."""
        if not getattr(self, '_svd_ready', False) or not hasattr(self, 'preview_canvas'):
            return  # still under construction / SVD not ready yet
        if self._last_generated:
            self._last_generated = []
            self._preview_gen_list.clear()
            self._preview_gen_header_label.setText("Generated spectra (0):")
            self.preview_canvas.clear_plot()

    def _enable_point_editing(self):
        self.curve_canvas.edit_enabled = True
        if hasattr(self, '_curve_toolbar'):
            self._curve_toolbar.setEnabled(False)
            try:
                self._curve_toolbar.mode = ''
                if hasattr(self._curve_toolbar, '_active'):
                    self._curve_toolbar._active = None
            except Exception:
                pass

    def _disable_point_editing(self):
        self.curve_canvas.edit_enabled = False
        if hasattr(self, '_curve_toolbar'):
            self._curve_toolbar.setEnabled(True)

    def _refresh_curve_plot(self):
        k = self._active_component
        if k is None:
            return
        true_coeffs = self.manager.get_coefficients(k)
        param_values = self.manager.get_parameter_values()
        points = self.manager.get_curve_points(k)

        if param_values is None and not points:
            self.curve_canvas.clear_plot()
            return

        x_min = x_max = None
        span_values = list(param_values) if param_values is not None else []
        span_values += self._parse_target_values(silent=True) or []
        if span_values:
            x_min, x_max = min(span_values), max(span_values)

        curve_x, curve_y = self.manager.get_curve_for_plot(k, x_min=x_min, x_max=x_max)
        self.curve_canvas.plot(
            param_values, true_coeffs, points, curve_x, curve_y,
            self.manager.parameter_label, f"Component {k + 1} coefficient curve")

    # ------------------------------------------------------------------
    # Handlers — target values
    # ------------------------------------------------------------------
    def _parse_target_values(self, silent=False):
        text = self._target_edit.toPlainText().strip()
        if not text:
            return []
        parts = [p.strip() for chunk in text.splitlines() for p in chunk.split(',')]
        values = []
        for p in parts:
            if not p:
                continue
            try:
                values.append(float(p))
            except ValueError:
                if not silent:
                    QMessageBox.warning(self, "Invalid Target Value",
                                         f"'{p}' is not a valid number.")
                return None
        return values

    def _on_confirm_range_clicked(self):
        start = self._range_start_spin.value()
        end = self._range_end_spin.value()
        step = self._range_step_spin.value()
        if step <= 0:
            QMessageBox.warning(self, "Invalid Range", "Step must be greater than 0.")
            return
        if end < start:
            QMessageBox.warning(self, "Invalid Range", "End must be \u2265 start.")
            return
        n = int(round((end - start) / step)) + 1
        values = [start + i * step for i in range(n) if start + i * step <= end + step / 2]
        text = ', '.join(f'{v:g}' for v in values)
        current = self._target_edit.toPlainText().strip()
        self._target_edit.setPlainText(f"{current}, {text}" if current else text)

    # ------------------------------------------------------------------
    # Handlers — generation (background thread + progress dialog)
    # ------------------------------------------------------------------
    def _on_compute_preview_clicked(self):
        self._start_generation(commit_after=False)

    def _on_add_as_new_clicked(self):
        self._start_generation(commit_after=True, add_as_new=True)

    def _on_apply_clicked(self):
        """Apply — same destructive-replace confirmation every other
        operation's Apply button shows (Normalization, Spike Removal,
        ...) before actually removing anything from the spectrum list."""
        confirm = QMessageBox.question(
            self, "Confirm",
            "Replace the source spectra used for this interpolation with "
            "the newly generated spectra?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        self._start_generation(commit_after=True, add_as_new=False)

    def _on_save_clicked(self):
        """Point 5 (from the handoff) — save the currently generated
        spectra straight to a file via the app's existing Save dialog,
        without adding them to the main spectrum list. Uses whatever was
        last computed (Compute Preview or Add as New), not whatever's
        currently checked/shown in the Preview tab — the display
        selection is about what's drawn, not what you'd want saved."""
        if not self._last_generated:
            QMessageBox.warning(
                self, "Nothing to Save",
                "Nothing computed yet — set target values above and click "
                "Compute Preview first.")
            return
        save_controller = getattr(self.svd_controller.controller, 'save_controller', None)
        if save_controller is None:
            QMessageBox.warning(self, "Save Unavailable",
                                 "The application's save feature isn't available "
                                 "right now.")
            return
        save_controller.execute(spectra=self._last_generated)

    def _start_generation(self, commit_after, add_as_new=True):
        if not self._svd_ready:
            return
        if self.manager.get_parameter_values() is None:
            QMessageBox.warning(self, "Parameter Values Needed",
                                 "Click 'Apply parameter values' first.")
            return
        used = self._components_with_curve()
        if not used:
            QMessageBox.warning(
                self, "No Curves Defined",
                "None of the components have a curve yet — select a "
                "component on the left and add at least 2 points to it.")
            return
        targets = self._parse_target_values(silent=False)
        if targets is None:
            return
        if not targets:
            QMessageBox.warning(self, "No Target Values",
                                 "Enter at least one target parameter value, or "
                                 "use Add range.")
            return

        self._pending_used = used
        self._pending_targets = targets
        self._pending_commit_after = commit_after
        self._pending_add_as_new = add_as_new

        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        self._gen_progress = QProgressDialog('Reconstructing spectra\u2026', None, 0, 0, self)
        self._gen_progress.setWindowModality(Qt.WindowModal)
        self._gen_progress.setWindowTitle('SVD Interpolation')
        self._gen_progress.setMinimumDuration(0)
        self._gen_progress.setCancelButton(None)
        self._gen_progress.show()
        self._gen_worker = _ComputeWorker(
            lambda: self.manager.generate_spectra(used, targets), self)
        self._gen_worker.done.connect(self._on_generation_done)
        self._gen_worker.start(QThread.LowPriority)

    def _on_generation_done(self):
        self._gen_progress.close()
        self._gen_progress.deleteLater()
        try:
            if self._gen_worker.error is not None:
                QMessageBox.critical(self, "Error",
                                      f"Error generating spectra: {self._gen_worker.error}")
                return
            new_spectra, failed = self._gen_worker.result
            if not new_spectra:
                QMessageBox.warning(self, "Generation Failed",
                                     "No spectra could be generated.")
                return
            if failed:
                names = ', '.join(f"Component {k + 1}" for k in failed)
                QMessageBox.warning(
                    self, "Some Components Skipped",
                    f"{names} could not be fit and were left out of the "
                    "reconstruction.")

            self._last_generated = new_spectra
            self._tabs.setCurrentIndex(1)
            n = len(new_spectra)
            self._preview_gen_list.blockSignals(True)
            self._preview_gen_list.clear()
            for s in new_spectra:
                self._preview_gen_list.addItem(QListWidgetItem(s['label']))
            self._preview_gen_list.blockSignals(False)
            # Nothing selected by default (as if "None" were pressed) —
            # same reasoning as the source list: the user picks what to
            # actually see, rather than a fresh computation immediately
            # trying to draw everything.
            self._preview_source_list.clearSelection()
            self._preview_gen_header_label.setText(f"Generated spectra ({n}):")
            self._redraw_preview()

            if self._pending_commit_after:
                settings = {
                    'parameter_label': self.manager.parameter_label,
                    'selected_components': list(self._pending_used),
                    'target_values': list(self._pending_targets),
                    'fit_types': {k: self.manager.get_fit_type(k) for k in self._pending_used},
                }
                add_as_new = self._pending_add_as_new
                success, message = self.svd_controller.commit_generated_spectra(
                    new_spectra, self.source_labels, settings, add_as_new=add_as_new)
                if success:
                    # Both Apply and Add as New close the dialog on
                    # success — consistent with every other Spectra
                    # Processing operation's Apply/Add as New pair
                    # (Normalization, Spike Removal, ...). Use Compute
                    # Preview first to iterate on target values without
                    # committing/closing.
                    QMessageBox.information(self, "Done", message)
                    self.accept()
                    return
                else:
                    QMessageBox.warning(self, "Generation Failed", message)
        finally:
            QApplication.restoreOverrideCursor()

    # ------------------------------------------------------------------
    # Preview display (point 5 — selectable subsets; point 6 — progress
    # during the actually-slow part, which is plotting, not computing)
    # ------------------------------------------------------------------
    def _on_preview_display_changed(self, *_args):
        # Debounced: selecting several items (Ctrl/Shift-click, or the
        # All button) fires this once per item — redrawing synchronously
        # on every single one made multi-selecting feel frozen, since
        # each click blocked until its own redraw finished. Restarting a
        # short timer instead means only the LAST change in a quick burst
        # actually triggers a redraw.
        if not hasattr(self, '_preview_redraw_timer'):
            self._preview_redraw_timer = QTimer(self)
            self._preview_redraw_timer.setSingleShot(True)
            self._preview_redraw_timer.timeout.connect(self._redraw_preview)
        self._preview_redraw_timer.start(350)

    def _redraw_preview(self):
        if not self._last_generated:
            return
        source_indices = sorted({self._preview_source_list.row(it)
                                  for it in self._preview_source_list.selectedItems()})
        source_to_plot = [self.spectra[i] for i in source_indices]
        gen_indices = sorted({self._preview_gen_list.row(it)
                               for it in self._preview_gen_list.selectedItems()})
        generated_to_plot = [self._last_generated[i] for i in gen_indices]

        # Plotting hundreds/thousands of lines is the slow part here, NOT
        # the numeric generation — so the progress dialog belongs here,
        # not (only) around generate_spectra(). Only bother showing it
        # when there's enough to plot for it to matter.
        total = len(source_to_plot) + len(generated_to_plot)
        progress = None
        if total > 150:
            progress = QProgressDialog('Plotting preview\u2026', None, 0, total, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setWindowTitle('SVD Interpolation')
            progress.setMinimumDuration(0)
            progress.setCancelButton(None)
            progress.show()
            # Without this, the dialog doesn't actually get painted until
            # control returns to Qt's event loop — which, since the plot
            # loop below runs synchronously right after show(), wouldn't
            # happen until that loop's own periodic processEvents() calls
            # kick in. That's what caused the "looks frozen, then the bar
            # appears partway through" symptom: the window existed but
            # had never been drawn yet.
            QApplication.processEvents()

        display_map = shorten_spectra_labels(
            source_to_plot + generated_to_plot, self._shorten_names_enabled())

        try:
            truncated = self.preview_canvas.plot(
                self.manager.x_axis, source_to_plot, generated_to_plot,
                self._legend_limit_spin.value(), self._show_full_legend_cb.isChecked(),
                progress=progress, display_map=display_map)
        finally:
            if progress is not None:
                progress.close()
                progress.deleteLater()

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------
    def _show_help(self):
        try:
            from src.help.svd_interpolation_help import (
                get_svd_interpolation_help_content, get_svd_interpolation_help_title)
            from src.help.help_window import show_help_window
            show_help_window(self, get_svd_interpolation_help_title(),
                              get_svd_interpolation_help_content())
        except Exception as e:
            logger.error(f"Failed to show SVD Interpolation help: {e}")
            QMessageBox.information(self, "Help", "Help is not available right now.")
