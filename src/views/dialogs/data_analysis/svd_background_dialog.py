# src/views/dialogs/data_analysis/svd_background_dialog.py

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QRadioButton, QSpinBox, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QDialogButtonBox,
    QSplitter, QWidget, QMessageBox, QCheckBox,
    QButtonGroup, QSizePolicy, QMenu, QAction,
    QAbstractItemView, QTableWidget, QTableWidgetItem,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from src.help.svd_background_help import (
    get_svd_background_help_content,
    get_svd_background_help_title,
)
from src.help.help_window import show_help_window
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)


# ======================================================================= #
#  SVDSingularValuesWindow                                                  #
# ======================================================================= #

class SVDSingularValuesWindow(QDialog):
    """Display SVD singular values and / or residual errors."""

    def __init__(self, parent=None, svd_controller=None, show_type="both"):
        super().__init__(parent)
        self.svd_controller = svd_controller
        self.show_type      = show_type
        self.use_log_scale  = True

        titles = {
            "singular": "SVD Singular Values",
            "residual": "SVD Residual Errors",
        }
        self.setWindowTitle(titles.get(show_type, "SVD Singular Values and Residual Errors"))
        self.setModal(False)
        self.resize(800, 600)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )

        self._setup_ui()
        self.plot_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale:"))
        self.scale_group  = QButtonGroup()
        self.linear_radio = QRadioButton("Linear")
        self.linear_radio.clicked.connect(self._on_scale_changed)
        self.scale_group.addButton(self.linear_radio)
        scale_layout.addWidget(self.linear_radio)
        self.log_radio = QRadioButton("Logarithmic")
        self.log_radio.setChecked(True)
        self.log_radio.clicked.connect(self._on_scale_changed)
        self.scale_group.addButton(self.log_radio)
        scale_layout.addWidget(self.log_radio)
        scale_layout.addStretch()
        layout.addLayout(scale_layout)

        self.figure = Figure(figsize=(10, 8))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        layout.addWidget(NavigationToolbar(self.canvas, self))

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_scale_changed(self):
        self.use_log_scale = self.log_radio.isChecked()
        self.plot_data()

    def _calculate_residual_errors(self):
        if not self.svd_controller or self.svd_controller.manager.s is None:
            return None
        s = self.svd_controller.manager.s
        U = self.svd_controller.manager.U
        if U is None:
            return None
        n_spectra = U.shape[1]
        n_points  = U.shape[0]
        if n_spectra == 1:
            return np.array([0])
        eigen = s ** 2
        n     = len(s)
        E     = np.zeros(n - 1)
        for m in range(n - 1):
            num = np.sum(eigen) - np.sum(eigen[:m + 1])
            den = (n_points - m - 1) * (n_spectra - m - 1)
            E[m] = np.sqrt(num / den) if den > 0 else 0
        return E

    def plot_data(self):
        if not self.svd_controller:
            return
        try:
            self.figure.clear()
            plot = self.use_log_scale and (lambda ax, x, y, **kw: ax.semilogy(x, y, **kw)) \
                                      or (lambda ax, x, y, **kw: ax.plot(x, y, **kw))

            def _singular(ax):
                s = self.svd_controller.manager.s
                if s is None:
                    return
                idx = np.arange(1, len(s) + 1)
                plot(ax, idx, s, color='blue', marker='o', markersize=6, linewidth=2)
                ax.set_ylabel('Singular Value' + (' (log)' if self.use_log_scale else ''))
                ax.set_title('Singular Values')
                ax.set_xlabel('Component')
                ax.grid(True, alpha=0.3)

            def _residual(ax):
                E = self._calculate_residual_errors()
                if E is None or len(E) == 0:
                    return
                idx = np.arange(1, len(E) + 1)
                plot(ax, idx, E, color='red', marker='o', markersize=6, linewidth=2)
                ax.set_ylabel('Residual Error' + (' (log)' if self.use_log_scale else ''))
                ax.set_title('Residual Errors')
                ax.set_xlabel('Component')
                ax.grid(True, alpha=0.3)

            if self.show_type == "both":
                _singular(self.figure.add_subplot(211))
                _residual(self.figure.add_subplot(212))
            elif self.show_type == "singular":
                _singular(self.figure.add_subplot(111))
            else:
                _residual(self.figure.add_subplot(111))

            self.figure.tight_layout()
            self.canvas.draw()
        except Exception as exc:
            logger.error(f"Error plotting SVD data: {exc}")


# ======================================================================= #
#  SVDPreviewWindow                                                         #
# ======================================================================= #

class SVDPreviewWindow(QDialog):
    """Show original vs reconstructed spectra side-by-side."""

    def __init__(self, parent=None, svd_controller=None, settings=None, original_spectra=None):
        super().__init__(parent)
        self.svd_controller   = svd_controller
        self.settings         = settings or {}
        self.original_spectra = original_spectra or []

        self.setWindowTitle("SVD Reconstruction Preview")
        self.setModal(False)
        self.resize(1200, 800)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )

        self._setup_ui()
        self.plot_comparison()

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ── Left panel ──────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(220)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(6, 6, 6, 6)
        lv.setSpacing(8)

        bc   = self.settings.get('baseline_corrections', {})
        n_bc = sum(1 for d in bc.values() if len(d.get('points', [])) >= 2)
        info = QLabel(
            f"<b>Reconstruction Preview:</b><br>"
            f"Mode: {self.settings.get('correction_mode', 'unknown')}<br>"
            f"Baseline corrections: {n_bc} subspectra with ≥2 points"
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background:#f0f0f0; padding:8px; border:1px solid #ccc; border-radius:4px;"
        )
        lv.addWidget(info)
        lv.addWidget(QLabel("<b>Select spectra to show:</b>"))

        btn_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all)
        btn_row.addWidget(self.select_all_btn)
        self.unselect_all_btn = QPushButton("Unselect All")
        self.unselect_all_btn.clicked.connect(self._unselect_all)
        btn_row.addWidget(self.unselect_all_btn)
        lv.addLayout(btn_row)

        self.spectra_list = QListWidget()
        self.spectra_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.spectra_list.itemSelectionChanged.connect(self.plot_comparison)
        lv.addWidget(self.spectra_list, stretch=1)
        self._populate_list()

        self.link_axes_cb = QCheckBox("Link X-axes")
        self.link_axes_cb.setChecked(True)
        self.link_axes_cb.stateChanged.connect(self.plot_comparison)
        lv.addWidget(self.link_axes_cb)

        self.hide_legend_cb = QCheckBox("Hide Legend")
        self.hide_legend_cb.setChecked(True)
        self.hide_legend_cb.stateChanged.connect(self.plot_comparison)
        lv.addWidget(self.hide_legend_cb)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        lv.addWidget(close_btn)
        root.addWidget(left)

        # ── Right panel ─────────────────────────────────────────────
        right  = QWidget()
        rv     = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(2)
        self.figure = Figure(figsize=(12, 10))
        self.canvas = FigureCanvas(self.figure)
        rv.addWidget(self.canvas, stretch=1)
        rv.addWidget(NavigationToolbar(self.canvas, self))
        root.addWidget(right, stretch=1)

    def _populate_list(self):
        self.spectra_list.clear()
        self.spectra_list.blockSignals(True)
        try:
            for i, sp in enumerate(self.original_spectra):
                item = QListWidgetItem(f"{i + 1}. {sp.get('label', f'Spectrum {i+1}')}")
                item.setFlags(item.flags() | Qt.ItemIsSelectable)
                self.spectra_list.addItem(item)
                if i < 5:
                    item.setSelected(True)
        finally:
            self.spectra_list.blockSignals(False)

    def _select_all(self):
        self.spectra_list.selectAll()

    def _unselect_all(self):
        self.spectra_list.clearSelection()

    def _selected_indices(self):
        return [
            i for i in range(self.spectra_list.count())
            if self.spectra_list.item(i).isSelected()
        ]

    def plot_comparison(self):
        if not self.svd_controller or not self.original_spectra:
            return
        try:
            reconstructed = self.svd_controller.manager.reconstruct_spectra(self.original_spectra)
            self.figure.clear()

            ax1 = self.figure.add_subplot(211)
            ax2 = (self.figure.add_subplot(212, sharex=ax1)
                   if self.link_axes_cb.isChecked()
                   else self.figure.add_subplot(212))

            indices = self._selected_indices()
            if not indices:
                for ax, msg in ((ax1, "No spectra selected"),
                                (ax2, "Please select spectra to display")):
                    ax.text(0.5, 0.5, msg, transform=ax.transAxes,
                            ha='center', va='center', fontsize=14)
            else:
                colors = plt.cm.tab10(np.linspace(0, 1, len(indices)))
                show_legend = not self.hide_legend_cb.isChecked()

                for plot_i, sp_i in enumerate(indices):
                    lbl = self.original_spectra[sp_i].get('label', f'Spectrum {sp_i+1}')
                    ax1.plot(self.original_spectra[sp_i]['x_scale'],
                             self.original_spectra[sp_i]['y_scale'],
                             color=colors[plot_i], label=lbl, linewidth=1)
                    ax2.plot(reconstructed[sp_i]['x_scale'],
                             reconstructed[sp_i]['y_scale'],
                             color=colors[plot_i], label=lbl, linewidth=1)

                for ax, title in ((ax1, f'Original Spectra ({len(indices)} selected)'),
                                  (ax2, f'Reconstructed Spectra ({len(indices)} selected)')):
                    ax.set_title(title)
                    ax.set_ylabel('Intensity')
                    ax.grid(True, alpha=0.3)
                    if show_legend:
                        ax.legend()
                ax2.set_xlabel('Wavenumber')

            self.figure.tight_layout()
            self.canvas.draw()
        except Exception as exc:
            logger.error(f"Error plotting preview: {exc}")


# ======================================================================= #
#  SVDDiagnosticsDialog                                                     #
# ======================================================================= #

class SVDDiagnosticsDialog(QDialog):
    """One row per spectrum, showing the same correction diagnostics that
    end up in metadata['svd_correction'] after Apply — visible here live,
    without needing to Apply first and then dig into a spectrum's own
    metadata to check whether the correction did something reasonable."""

    _COLUMNS = [
        ("Label",                             "label"),
        ("Subspectra Used for Reconstruction", "subspectra_used_for_reconstruction"),
        ("Baseline Corrected Subspectra",     "baseline_corrected_subspectra"),
        ("Original Mean",                     "original_mean"),
        ("Corrected Mean",                    "corrected_mean"),
        ("Max Absolute Change",               "max_absolute_change"),
        ("Relative Mean Change",              "relative_mean_change"),
    ]

    def __init__(self, parent, spectra):
        super().__init__(parent)
        self.setWindowTitle("SVD Correction Diagnostics")
        self.resize(760, 420)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Computed live from the current settings (mode, selected "
            "components, baseline corrections) — nothing has been applied. "
            "These are the same values that will be recorded in each "
            "spectrum's metadata['svd_correction'] if you click Apply now."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        table = QTableWidget()
        table.setColumnCount(len(self._COLUMNS))
        table.setHorizontalHeaderLabels([c[0] for c in self._COLUMNS])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setRowCount(len(spectra))

        for row, spectrum in enumerate(spectra):
            # reconstruct_spectra() returns the ORIGINAL spectrum unchanged
            # (no 'svd_correction' key at all) if reconstruction wasn't
            # possible for it — show that plainly rather than blank cells
            # that look like a formatting bug.
            info_dict = (spectrum.get('metadata') or {}).get('svd_correction')
            for col, (header, key) in enumerate(self._COLUMNS):
                if key == "label":
                    text = spectrum.get('label', '?')
                elif info_dict is None:
                    text = "(not corrected)"
                else:
                    value = info_dict.get(key)
                    if isinstance(value, float):
                        text = f"{value:.4g}"
                    elif isinstance(value, list):
                        text = str(value)
                    else:
                        text = "" if value is None else str(value)
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, col, item)

        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)


# ======================================================================= #
#  InteractiveSVDCanvas                                                     #
# ======================================================================= #

class InteractiveSVDCanvas(FigureCanvas):
    """Matplotlib canvas with interactive baseline-point editing."""

    baseline_updated = pyqtSignal(int)

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(12, 8))
        super().__init__(self.fig)
        self.setParent(parent)

        self.ax_subspectra   = self.fig.add_subplot(211)
        self.ax_coefficients = self.fig.add_subplot(212)
        self.fig.tight_layout(pad=3.0)

        self.svd_controller      = None
        self.current_subspectrum = 0
        self.baseline_mode       = False
        self.viewing_corrected   = False
        self.show_coefficients   = True
        self.axis_limits         = {}        # saved per-subspectrum zoom state

        self.setFocusPolicy(Qt.StrongFocus)
        self.mpl_connect('button_press_event', self._on_click)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # -- Context menu --------------------------------------------------- #

    def _show_context_menu(self, pos):
        """Show the context menu unless right-click just removed a baseline point."""
        if getattr(self, '_suppress_context_menu', False):
            self._suppress_context_menu = False
            return

        menu = QMenu(self)

        coeff_label  = "Hide Coefficients Plot" if self.show_coefficients else "Show Coefficients Plot"
        coeff_action = QAction(coeff_label, self)
        coeff_action.triggered.connect(self.toggle_coefficients_plot)
        menu.addAction(coeff_action)
        menu.addSeparator()

        # Walk up to find the parent SVDBackgroundDialog
        parent = self.parentWidget()
        while parent and not isinstance(parent, SVDBackgroundDialog):
            parent = parent.parentWidget()

        if parent and hasattr(parent, 'toggle_controls_visibility'):
            visible = getattr(parent, 'controls_visible', True)
            text    = "Show Only SVD Results" if visible else "Show Controls"
            toggle  = QAction(text, self)
            toggle.triggered.connect(
                lambda checked, p=parent, v=visible: p.toggle_controls_visibility(not v)
            )
            menu.addAction(toggle)

        menu.exec_(self.mapToGlobal(pos))

    # -- Public helpers -------------------------------------------------- #

    def set_svd_controller(self, controller):
        self.svd_controller = controller

    def toggle_coefficients_plot(self):
        self.show_coefficients = not self.show_coefficients
        self.plot_subspectrum(self.current_subspectrum, show_baseline=True)

    def enable_baseline_mode(self):
        self.baseline_mode = True
        self.setFocus()

    def disable_baseline_mode(self):
        self.baseline_mode = False

    # -- Plot methods ---------------------------------------------------- #

    def plot_subspectrum(self, index, show_baseline=True):
        """Plot subspectrum *index* (original or corrected view)."""
        if not self.svd_controller:
            return

        # Save current zoom before changing subspectrum
        if (self.baseline_mode
                and self.current_subspectrum != index
                and hasattr(self.ax_subspectra, 'get_xlim')):
            self.axis_limits[self.current_subspectrum] = {
                'xlim': self.ax_subspectra.get_xlim(),
                'ylim': self.ax_subspectra.get_ylim(),
            }

        self.current_subspectrum = index
        self.fig.clear()

        if self.show_coefficients:
            self.ax_subspectra   = self.fig.add_subplot(211)
            self.ax_coefficients = self.fig.add_subplot(212)
        else:
            self.ax_subspectra   = self.fig.add_subplot(111)
            self.ax_coefficients = None

        x, y = self.svd_controller.get_subspectrum_data(index, corrected=self.viewing_corrected)
        if x is None:
            return

        color = 'green' if self.viewing_corrected else 'blue'
        label = 'Corrected' if self.viewing_corrected else 'Original Subspectrum'
        self.ax_subspectra.plot(x, y, color=color, linewidth=1, label=label)

        # Baseline points and curve — shown in BOTH original and corrected
        # view (previously original-view only; confirmed real complaint —
        # seeing where the baseline was placed relative to the CORRECTED
        # result, e.g. to check the correction actually flattened it out,
        # is exactly the comparison this restriction was blocking). Purely
        # a display change — the points/curve are still defined in the
        # ORIGINAL subspectrum's coordinate space and are simply drawn as
        # an overlay here; see _on_click below for why adding NEW points
        # still needs to happen in original view specifically.
        if show_baseline:
            pts = self.svd_controller.manager.get_baseline_points(index)
            if pts:
                bx, by = zip(*pts)
                self.ax_subspectra.plot(bx, by, 'ro', markersize=8, label='Baseline points')
                if len(pts) >= 2:
                    cfg   = self.svd_controller.manager.get_baseline_settings(index)
                    curve = self.svd_controller.manager._calculate_baseline(
                        pts, cfg['type'], cfg['order']
                    )
                    if curve is not None:
                        self.ax_subspectra.plot(x, curve, 'r-', linewidth=2, label='Baseline curve')

        variance = 0.0
        if (self.svd_controller.manager.explained_variance is not None
                and index < len(self.svd_controller.manager.explained_variance)):
            variance = self.svd_controller.manager.explained_variance[index]

        title = f"Subspectrum {index + 1} ({variance:.3f}% variance)"
        if self.viewing_corrected:
            title += " — Corrected"
            # Baseline points/curve are now shown here too (see above),
            # but ADDING new points still only works in Original view —
            # a click here would land in the CORRECTED y-scale, not the
            # original one baseline points are actually defined against,
            # silently producing a garbage point. Previously this
            # restriction was invisible (clicking just did nothing);
            # this makes it visible instead of leaving the user guessing
            # why nothing happened.
            if getattr(self, 'baseline_mode', False):
                title += "  (switch to Original view to add/edit points)"
        self.ax_subspectra.set_title(title)
        self.ax_subspectra.grid(True, alpha=0.3)
        self.ax_subspectra.legend()

        if self.show_coefficients and self.ax_coefficients is not None:
            coeff = self.svd_controller.get_coefficients(index)
            if coeff is not None:
                self.ax_coefficients.plot(coeff, 'o-', markersize=4)
                self.ax_coefficients.set_title(f"Coefficients for Subspectrum {index + 1}")
                self.ax_coefficients.grid(True, alpha=0.3)

        self.fig.tight_layout(pad=3.0)
        self.draw()
        self._restore_or_autoscale(index)

    def plot_subspectrum_both(self, index):
        """Overlay original and baseline-corrected subspectrum."""
        if not self.svd_controller:
            return

        if (self.baseline_mode
                and self.current_subspectrum != index
                and hasattr(self.ax_subspectra, 'get_xlim')):
            self.axis_limits[self.current_subspectrum] = {
                'xlim': self.ax_subspectra.get_xlim(),
                'ylim': self.ax_subspectra.get_ylim(),
            }

        self.current_subspectrum = index
        self.fig.clear()

        if self.show_coefficients:
            self.ax_subspectra   = self.fig.add_subplot(211)
            self.ax_coefficients = self.fig.add_subplot(212)
        else:
            self.ax_subspectra   = self.fig.add_subplot(111)
            self.ax_coefficients = None

        x,  y_orig = self.svd_controller.get_subspectrum_data(index, corrected=False)
        xc, y_corr = self.svd_controller.get_subspectrum_data(index, corrected=True)
        if x is None:
            return

        self.ax_subspectra.plot(x, y_orig, color='blue', linewidth=1, label='Original', alpha=0.7)
        if xc is not None and y_corr is not None and not np.array_equal(y_orig, y_corr):
            self.ax_subspectra.plot(xc, y_corr, color='red', linewidth=1, label='Corrected', alpha=0.7)

        pts = self.svd_controller.manager.get_baseline_points(index)
        if pts:
            bx, by = zip(*pts)
            self.ax_subspectra.plot(bx, by, 'go', markersize=8, alpha=0.7,
                                    markeredgecolor='black', linestyle='', label='Baseline points')
            if len(pts) >= 2:
                cfg   = self.svd_controller.manager.get_baseline_settings(index)
                curve = self.svd_controller.manager._calculate_baseline(
                    pts, cfg['type'], cfg['order']
                )
                if curve is not None:
                    self.ax_subspectra.plot(x, curve, 'g--', linewidth=2, alpha=0.8,
                                            label='Baseline curve')

        variance = 0.0
        if (self.svd_controller.manager.explained_variance is not None
                and index < len(self.svd_controller.manager.explained_variance)):
            variance = self.svd_controller.manager.explained_variance[index]

        self.ax_subspectra.set_title(
            f"Subspectrum {index + 1} ({variance:.3f}% variance) — Both Views"
        )
        self.ax_subspectra.grid(True, alpha=0.3)
        self.ax_subspectra.legend()

        if self.show_coefficients and self.ax_coefficients is not None:
            coeff = self.svd_controller.get_coefficients(index)
            if coeff is not None:
                self.ax_coefficients.plot(coeff, 'o-', markersize=4)
                self.ax_coefficients.set_title(f"Coefficients for Subspectrum {index + 1}")
                self.ax_coefficients.grid(True, alpha=0.3)

        self.fig.tight_layout(pad=3.0)
        self.draw()
        self._restore_or_autoscale(index)

    # -- Axis scaling ---------------------------------------------------- #

    def _restore_or_autoscale(self, index):
        if self.baseline_mode and index in self.axis_limits:
            lim = self.axis_limits[index]
            self.ax_subspectra.set_xlim(lim['xlim'])
            self.ax_subspectra.set_ylim(lim['ylim'])
            self.draw()
        else:
            QTimer.singleShot(50, self._delayed_autoscale)

    def _delayed_autoscale(self):
        try:
            self.ax_subspectra.relim()
            self.ax_subspectra.autoscale()
            self.axis_limits[self.current_subspectrum] = {
                'xlim': self.ax_subspectra.get_xlim(),
                'ylim': self.ax_subspectra.get_ylim(),
            }
            self.draw()
        except Exception as exc:
            logger.error(f"Autoscale error: {exc}")

    # -- Mouse click handler --------------------------------------------- #

    def _on_click(self, event):
        if not self.baseline_mode or not self.svd_controller:
            return
        if event.inaxes != self.ax_subspectra:
            return
        if event.xdata is None or event.ydata is None:
            return
        if self.viewing_corrected:
            # Baseline points are defined in the ORIGINAL subspectrum's
            # y-scale — a click here would be interpreted in the
            # CORRECTED y-scale instead (different values, since
            # baseline subtraction already happened), silently creating
            # a garbage point that doesn't mean what it looks like it
            # means. Blocked here; see plot_subspectrum's title hint for
            # where the user actually finds out why, instead of the
            # click just silently doing nothing.
            return

        cx, cy = event.xdata, event.ydata

        # Freeze axis limits on every interaction
        xlim = self.ax_subspectra.get_xlim()
        ylim = self.ax_subspectra.get_ylim()
        self.axis_limits[self.current_subspectrum] = {'xlim': xlim, 'ylim': ylim}

        from PyQt5.QtWidgets import QApplication
        modifiers = QApplication.keyboardModifiers()

        if event.button == 1 and (modifiers & Qt.ShiftModifier):
            # Shift+Left-click: remove nearest point
            pts = self.svd_controller.manager.get_baseline_points(self.current_subspectrum)
            if pts:
                self.svd_controller.remove_baseline_point(self.current_subspectrum, cx, cy)
                self.plot_subspectrum(self.current_subspectrum, show_baseline=True)
                self.baseline_updated.emit(self.current_subspectrum)

        elif event.button == 1:
            # Left-click: add point
            self.svd_controller.add_baseline_point(self.current_subspectrum, cx, cy)
            self.plot_subspectrum(self.current_subspectrum, show_baseline=True)
            self.baseline_updated.emit(self.current_subspectrum)

        elif event.button == 3:
            # Right-click: remove nearby point, or show context menu if none nearby
            pts   = self.svd_controller.manager.get_baseline_points(self.current_subspectrum)
            x_tol = 0.02 * (xlim[1] - xlim[0])
            y_tol = 0.05 * (ylim[1] - ylim[0])
            found = False
            if pts:
                for px, py in pts:
                    if abs(cx - px) < x_tol and abs(cy - py) < y_tol:
                        self.svd_controller.remove_baseline_point(
                            self.current_subspectrum, cx, cy
                        )
                        self.plot_subspectrum(self.current_subspectrum, show_baseline=True)
                        self.baseline_updated.emit(self.current_subspectrum)
                        found = True
                        break
            self._suppress_context_menu = found


# ======================================================================= #
#  SVDBackgroundDialog                                                      #
# ======================================================================= #

class SVDBackgroundDialog(QDialog):
    """Main dialog for interactive SVD background correction."""

    # Stylesheet constants shared across control groups
    _TOGGLE_STYLE = """
        QPushButton {
            border: 1px solid #aaa; border-radius: 4px;
            padding: 4px 8px; background-color: #f0f0f0; color: #222;
        }
        QPushButton:checked {
            background-color: #2979ff; color: white;
            border: 1px solid #1a56cc; font-weight: bold;
        }
        QPushButton:hover:!checked {
            background-color: #dce8ff; border: 1px solid #2979ff;
        }
        QPushButton:disabled {
            background-color: #e8e8e8; color: #aaa; border: 1px solid #ccc;
        }
    """
    _CLEAR_STYLE = """
        QPushButton {
            border: 1px solid #aaa; border-radius: 4px;
            padding: 4px 8px; background-color: #f0f0f0; color: #222;
        }
        QPushButton:hover:enabled {
            background-color: #ffe0e0; border: 1px solid #cc3333; color: #cc3333;
        }
        QPushButton:disabled {
            background-color: #e8e8e8; color: #aaa; border: 1px solid #ccc;
        }
    """
    _HINT_STYLE = (
        "color: #1976D2; font-style: italic; padding: 5px;"
        " background-color: #E3F2FD; border-radius: 3px; margin: 2px;"
    )

    def __init__(self, parent=None, current_settings=None, controller=None,
                 selected_spectra=None, commit_callback=None):
        super().__init__(parent)
        self.controller              = controller
        self.current_settings        = current_settings or {}
        self.svd_controller          = None
        self.current_reconstruction_mode = "all_subspectra"
        self.controls_visible        = True
        # Fixed snapshot of the spectra to correct, taken when the dialog
        # opened — safe because this dialog is modal, so the main window's
        # selection can't change underneath it while it's open.
        self.selected_spectra        = list(selected_spectra or [])
        # Bound method (OperationsController.commit_svd_background) passed
        # in by whatever opened this dialog, so Apply / Add as New can
        # commit the result directly, without a separate Run step.
        self.commit_callback         = commit_callback

        self.setWindowTitle("SVD Background Correction")
        self.setModal(True)
        self.resize(1400, 900)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )

        self.setup_ui()

        if self.controller:
            self._initialise_data()    # Phase 1: compute SVD, populate components
            self._restore_settings()   # Phase 2: apply previously saved settings
            self._finalise_ui()        # Phase 3: final adjustments

    # ------------------------------------------------------------------ #
    # Initialisation phases                                                #
    # ------------------------------------------------------------------ #

    def _initialise_data(self):
        self.initialize_svd()

    def _restore_settings(self):
        self.load_current_settings()

    def _finalise_ui(self):
        if hasattr(self, 'toolbar'):
            self.toolbar.setEnabled(False)
            self.canvas.setCursor(Qt.ArrowCursor)

    # ------------------------------------------------------------------ #
    # UI construction                                                       #
    # ------------------------------------------------------------------ #

    def setup_ui(self):
        layout   = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        splitter.addWidget(self._create_control_panel())
        splitter.addWidget(self._create_canvas_panel())
        splitter.setSizes([400, 1000])

    def _hint(self, text):
        """Return a styled hint QLabel."""
        lbl = QLabel(text)
        lbl.setStyleSheet(self._HINT_STYLE)
        lbl.setWordWrap(True)
        return lbl

    def _create_control_panel(self):
        widget = QWidget()
        widget.setFixedWidth(400)
        layout = QVBoxLayout(widget)

        # ── Subspectrum Navigation ──────────────────────────────────
        nav_group  = QGroupBox("Subspectrum Navigation")
        nav_layout = QVBoxLayout(nav_group)
        nav_row    = QHBoxLayout()

        self.prev_btn = QPushButton("Previous")
        self.prev_btn.clicked.connect(self.prev_subspectrum)
        self.prev_btn.setEnabled(False)
        nav_row.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.next_subspectrum)
        self.next_btn.setEnabled(False)
        nav_row.addWidget(self.next_btn)

        nav_row.addWidget(QLabel("Jump to:"))
        self.subspectrum_spin = QSpinBox()
        self.subspectrum_spin.setMinimum(1)
        self.subspectrum_spin.setMaximum(1)
        self.subspectrum_spin.setKeyboardTracking(False)
        self.subspectrum_spin.valueChanged.connect(self.change_subspectrum)
        self.subspectrum_spin.setEnabled(False)
        nav_row.addWidget(self.subspectrum_spin)

        self.invert_btn = QPushButton("Invert")
        self.invert_btn.clicked.connect(self.invert_subspectrum)
        self.invert_btn.setEnabled(False)
        nav_row.addWidget(self.invert_btn)

        nav_layout.addLayout(nav_row)
        nav_layout.addWidget(self._hint(
            "💡 Navigate subspectra from SVD decomposition. Apply individual baseline "
            "corrections as needed. Reconstruction uses chosen subspectra."
        ))
        nav_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(nav_group)

        # ── Baseline Correction ─────────────────────────────────────
        baseline_group  = QGroupBox("Baseline Correction")
        baseline_layout = QVBoxLayout(baseline_group)

        # Enable sub-group
        enable_group  = QGroupBox("Enable Baseline Correction")
        enable_layout = QVBoxLayout(enable_group)
        radio_row     = QHBoxLayout()
        self.baseline_mode_group = QButtonGroup()

        self.baseline_on_btn = QRadioButton("On")
        self.baseline_on_btn.setChecked(True)
        self.baseline_on_btn.clicked.connect(self.enable_baseline_mode)
        self.baseline_mode_group.addButton(self.baseline_on_btn)
        radio_row.addWidget(self.baseline_on_btn)

        self.baseline_off_btn = QRadioButton("Off")
        self.baseline_off_btn.clicked.connect(self.disable_baseline_mode)
        self.baseline_mode_group.addButton(self.baseline_off_btn)
        radio_row.addWidget(self.baseline_off_btn)

        enable_layout.addLayout(radio_row)
        enable_layout.addWidget(self._hint(
            "💡 Left-click: Add point | Right-click or Shift+Left-click: Remove point. "
            "Navigator toolbar is disabled during baseline correction."
        ))
        baseline_layout.addWidget(enable_group)

        # View Mode sub-group
        view_group  = QGroupBox("View Mode")
        view_layout = QVBoxLayout(view_group)
        view_layout.addWidget(self._hint(
            "💡 Select view mode for visualization. Press buttons again to rescale. "
            "Axis limits remain fixed during baseline editing."
        ))
        view_row = QHBoxLayout()
        self.view_original_btn = QPushButton("Original")
        self.view_original_btn.setCheckable(True)
        self.view_original_btn.setChecked(True)
        self.view_original_btn.clicked.connect(self.view_original)
        view_row.addWidget(self.view_original_btn)
        self.view_corrected_btn = QPushButton("Corrected")
        self.view_corrected_btn.setCheckable(True)
        self.view_corrected_btn.clicked.connect(self.view_corrected)
        view_row.addWidget(self.view_corrected_btn)
        self.view_both_btn = QPushButton("Both")
        self.view_both_btn.setCheckable(True)
        self.view_both_btn.clicked.connect(self.view_both)
        view_row.addWidget(self.view_both_btn)
        view_layout.addLayout(view_row)
        view_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        baseline_layout.addWidget(view_group)

        # Baseline Fitting sub-group
        fit_group  = QGroupBox("Baseline Fitting")
        fit_layout = QVBoxLayout(fit_group)
        fit_row    = QHBoxLayout()
        self.baseline_spline_btn = QPushButton("Spline")
        self.baseline_spline_btn.setCheckable(True)
        self.baseline_spline_btn.setChecked(True)
        self.baseline_spline_btn.clicked.connect(self.set_baseline_spline)
        fit_row.addWidget(self.baseline_spline_btn)
        self.baseline_poly_btn = QPushButton("Poly")
        self.baseline_poly_btn.setCheckable(True)
        self.baseline_poly_btn.clicked.connect(self.set_baseline_poly)
        fit_row.addWidget(self.baseline_poly_btn)
        fit_row.addWidget(QLabel("Polynomial Order:"))
        self.poly_order_spin = QSpinBox()
        self.poly_order_spin.setMinimum(1)
        self.poly_order_spin.setMaximum(10)
        self.poly_order_spin.setValue(3)
        self.poly_order_spin.setEnabled(False)
        self.poly_order_spin.setKeyboardTracking(False)
        self.poly_order_spin.valueChanged.connect(self.update_baseline_settings)
        fit_row.addWidget(self.poly_order_spin)
        fit_layout.addLayout(fit_row)
        fit_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        baseline_layout.addWidget(fit_group)

        # Clear Baselines sub-group
        clear_group  = QGroupBox("Clear Baselines")
        clear_layout = QHBoxLayout(clear_group)
        self.clear_current_btn = QPushButton("Current")
        self.clear_current_btn.clicked.connect(self.clear_current_baseline)
        self.clear_current_btn.setEnabled(False)
        clear_layout.addWidget(self.clear_current_btn)
        self.clear_all_btn = QPushButton("All")
        self.clear_all_btn.clicked.connect(self.clear_all_baselines)
        self.clear_all_btn.setEnabled(False)
        clear_layout.addWidget(self.clear_all_btn)
        baseline_layout.addWidget(clear_group)

        baseline_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(baseline_group)

        # ── Reconstruction Mode ─────────────────────────────────────
        recon_group  = QGroupBox("Reconstruction Mode")
        recon_layout = QVBoxLayout(recon_group)

        mode_row = QHBoxLayout()
        self.all_mode_btn = QPushButton("All")
        self.all_mode_btn.setCheckable(True)
        self.all_mode_btn.setChecked(True)
        self.all_mode_btn.clicked.connect(lambda: self.set_mode_and_update_list("all_subspectra"))
        mode_row.addWidget(self.all_mode_btn)

        self.corrected_mode_btn = QPushButton("Only corr.")
        self.corrected_mode_btn.setCheckable(True)
        self.corrected_mode_btn.clicked.connect(lambda: self.set_mode_and_update_list("corrected_only"))
        mode_row.addWidget(self.corrected_mode_btn)

        first_n_row = QHBoxLayout()
        self.first_n_mode_btn = QPushButton("First N comp.")
        self.first_n_mode_btn.setCheckable(True)
        self.first_n_mode_btn.clicked.connect(lambda: self.set_mode_and_update_list("first_n"))
        first_n_row.addWidget(self.first_n_mode_btn)
        self.max_components_spin = QSpinBox()
        self.max_components_spin.setMinimum(1)
        self.max_components_spin.setMaximum(100)
        self.max_components_spin.setValue(10)
        self.max_components_spin.setMaximumWidth(60)
        self.max_components_spin.setKeyboardTracking(False)
        self.max_components_spin.valueChanged.connect(self.on_max_components_changed)
        first_n_row.addWidget(self.max_components_spin)
        first_n_row.addStretch()
        mode_row.addLayout(first_n_row)

        help_mode_btn = QPushButton("Help")
        help_mode_btn.setMaximumWidth(50)
        help_mode_btn.clicked.connect(self.show_reconstruction_help)
        mode_row.addWidget(help_mode_btn)
        recon_layout.addLayout(mode_row)

        recon_layout.addWidget(QLabel("Selected Components:"))
        self.components_list = QListWidget()
        self.components_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.components_list.itemChanged.connect(self.on_component_selection_changed)
        self.components_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.components_list.customContextMenuRequested.connect(self._show_components_context_menu)
        recon_layout.addWidget(self.components_list)

        recon_button_row = QHBoxLayout()
        self.preview_btn = QPushButton("Preview Reconstruction")
        self.preview_btn.clicked.connect(self.preview_reconstruction)
        self.preview_btn.setEnabled(False)
        self.preview_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        recon_button_row.addWidget(self.preview_btn)

        self.diagnostics_btn = QPushButton("Diagnostics...")
        self.diagnostics_btn.setToolTip(
            "Show, per spectrum, the same correction diagnostics recorded "
            "in metadata['svd_correction'] after Apply — original/corrected "
            "mean, relative mean change, etc. — computed live from the "
            "current settings without applying anything."
        )
        self.diagnostics_btn.clicked.connect(self.show_diagnostics_table)
        self.diagnostics_btn.setEnabled(False)
        self.diagnostics_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        recon_button_row.addWidget(self.diagnostics_btn)

        recon_layout.addLayout(recon_button_row)

        recon_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout.addWidget(recon_group)

        # ── Buttons ─────────────────────────────────────────────────
        self.button_box = QDialogButtonBox()

        self.help_button = QPushButton("Help")
        self.help_button.clicked.connect(self.show_help)
        self.button_box.addButton(self.help_button, QDialogButtonBox.HelpRole)

        # Apply / Add as New commit directly via commit_callback — there's
        # no separate Run step in the main window for this operation
        # anymore (see OperationsController.commit_svd_background). Both
        # start disabled until compute_svd() succeeds, like preview_btn and
        # the navigation buttons above.
        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip(
            "Replace the selected spectra with their SVD-corrected result."
        )
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        self.button_box.addButton(self.apply_button, QDialogButtonBox.ActionRole)

        self.add_as_new_button = QPushButton("Add as New")
        self.add_as_new_button.setToolTip(
            "Keep the original spectra unchanged and add the SVD-corrected "
            "results to the list under new names."
        )
        self.add_as_new_button.setEnabled(False)
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        self.button_box.addButton(self.add_as_new_button, QDialogButtonBox.ActionRole)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        self.button_box.addButton(self.close_button, QDialogButtonBox.RejectRole)

        self.button_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.button_box)

        # Stretch factors
        layout.setStretchFactor(nav_group,      0)
        layout.setStretchFactor(baseline_group, 0)
        layout.setStretchFactor(recon_group,    1)
        layout.setStretchFactor(self.button_box, 0)

        # Apply styles to toggle / clear buttons
        for btn in (
            self.view_original_btn, self.view_corrected_btn, self.view_both_btn,
            self.baseline_spline_btn, self.baseline_poly_btn,
            self.all_mode_btn, self.corrected_mode_btn, self.first_n_mode_btn,
        ):
            btn.setStyleSheet(self._TOGGLE_STYLE)

        for btn in (self.clear_current_btn, self.clear_all_btn):
            btn.setStyleSheet(self._CLEAR_STYLE)

        return widget

    def _create_canvas_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.canvas = InteractiveSVDCanvas()
        self.canvas.baseline_updated.connect(self.on_baseline_updated)
        self.toolbar = NavigationToolbar(self.canvas, widget)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        return widget

    # ------------------------------------------------------------------ #
    # SVD initialisation                                                   #
    # ------------------------------------------------------------------ #

    def initialize_svd(self):
        if not self.controller:
            return
        selected = self.selected_spectra
        if not selected:
            QMessageBox.warning(self, "No Spectra",
                                "Please select spectra before opening SVD correction.")
            return
        if not hasattr(self.controller, 'svd_background_controller'):
            from src.controllers.data_analysis.svd_background_controller import SVDBackgroundController
            self.controller.svd_background_controller = SVDBackgroundController(self.controller)
        self.svd_controller = self.controller.svd_background_controller
        self.canvas.set_svd_controller(self.svd_controller)
        self.compute_svd()

    def compute_svd(self):
        if not self.controller or not self.svd_controller:
            return
        selected = self.selected_spectra
        if not selected:
            QMessageBox.warning(self, "No Spectra", "Please select spectra to compute SVD.")
            return
        try:
            if not self.svd_controller.manager.compute_svd_from_spectra(selected):
                QMessageBox.warning(self, "SVD Error",
                                    "Failed to compute SVD. Ensure all spectra have identical x-axes.")
                return
            info = self.svd_controller.get_svd_components_info()
            if not info:
                QMessageBox.warning(self, "SVD Error", "Failed to get SVD component information.")
                return

            self.subspectrum_spin.setMaximum(info['n_components'])
            for btn in (self.subspectrum_spin, self.prev_btn, self.next_btn,
                        self.invert_btn, self.baseline_on_btn, self.baseline_off_btn,
                        self.clear_current_btn, self.clear_all_btn, self.preview_btn,
                        self.diagnostics_btn, self.apply_button, self.add_as_new_button):
                btn.setEnabled(True)

            self.populate_components_list(info['n_components'])
            self.subspectrum_spin.setValue(1)
            self.canvas.plot_subspectrum(0)
            self.canvas.enable_baseline_mode()
            self.canvas.setFocus()
            self.auto_apply_settings()
            self.update_button_states()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Error computing SVD: {exc}")

    def load_current_settings(self):
        """Apply previously saved settings on top of the freshly computed SVD."""
        if not self.current_settings:
            return

        # Remember the requested mode — applied AFTER baseline corrections so
        # that 'corrected_only' is not rejected for having no corrections yet.
        mode = self.current_settings.get('correction_mode', 'all_subspectra')
        if mode == 'first_n':
            self.max_components_spin.setValue(self.current_settings.get('max_components', 10))

        # Restore inversions FIRST (before baseline corrections, because
        # baseline coordinates are defined on the inverted subspectrum).
        for idx in self.current_settings.get('inverted_subspectra', []):
            if idx < self.svd_controller.manager.U.shape[1]:
                self.svd_controller.manager.inverted_subspectra.add(idx)
                self.svd_controller.manager.U[:, idx]  *= -1
                self.svd_controller.manager.Vt[idx, :] *= -1
                if self.svd_controller.manager.corrected_U is not None:
                    self.svd_controller.manager.corrected_U[:, idx] = \
                        self.svd_controller.manager.U[:, idx]

        # Restore baseline corrections
        for key, data in self.current_settings.get('baseline_corrections', {}).items():
            idx        = int(key)
            points     = data.get('points', [])
            fit_type   = data.get('fit_type', 'spline')
            poly_order = data.get('poly_order', 3)
            if len(points) >= 2:
                try:
                    self.svd_controller.manager.set_baseline_correction(
                        idx, points, fit_type, poly_order
                    )
                except Exception as exc:
                    logger.error(f"Failed to restore baseline for subspectrum {idx}: {exc}")

        # Restore reconstruction mode (now that corrections are in place)
        if mode in ('all_subspectra', 'corrected_only', 'first_n'):
            self.set_mode_and_update_list(mode)
        elif mode == 'selected':
            self.all_mode_btn.setChecked(False)
            self.corrected_mode_btn.setChecked(False)
            self.first_n_mode_btn.setChecked(False)
            self.current_reconstruction_mode = 'selected'
            selected_components = self.current_settings.get('selected_subspectra', [])
            self.components_list.blockSignals(True)
            try:
                for i in range(self.components_list.count()):
                    self.components_list.item(i).setCheckState(Qt.Unchecked)
                for idx in selected_components:
                    if idx < self.components_list.count():
                        self.components_list.item(idx).setCheckState(Qt.Checked)
            finally:
                self.components_list.blockSignals(False)
        else:
            self.set_mode_and_update_list('all_subspectra')

        # Refresh the plot and the fit-type UI for the current subspectrum
        current_index = self.subspectrum_spin.value() - 1
        if self.view_both_btn.isChecked():
            self.canvas.plot_subspectrum_both(current_index)
        else:
            self.canvas.plot_subspectrum(current_index)

        self.update_svd_manager()
        # Refresh fit type buttons / poly-order spinbox now that settings are loaded
        self.change_subspectrum(self.subspectrum_spin.value())

    # ------------------------------------------------------------------ #
    # Navigation                                                           #
    # ------------------------------------------------------------------ #

    def prev_subspectrum(self):
        v = self.subspectrum_spin.value()
        if v > 1:
            self.subspectrum_spin.setValue(v - 1)

    def next_subspectrum(self):
        v = self.subspectrum_spin.value()
        if v < self.subspectrum_spin.maximum():
            self.subspectrum_spin.setValue(v + 1)

    def change_subspectrum(self, value):
        """Navigate to subspectrum *value* and refresh the fit-type UI."""
        index = value - 1
        self.canvas.plot_subspectrum(index)
        if self.svd_controller:
            cfg        = self.svd_controller.manager.get_baseline_settings(index)
            fit_type   = cfg.get('type', 'spline')
            poly_order = cfg.get('order', 3)
            self.poly_order_spin.blockSignals(True)
            if fit_type == 'spline':
                self.baseline_spline_btn.setChecked(True)
                self.baseline_poly_btn.setChecked(False)
                self.poly_order_spin.setEnabled(False)
            else:
                self.baseline_spline_btn.setChecked(False)
                self.baseline_poly_btn.setChecked(True)
                self.poly_order_spin.setEnabled(True)
            self.poly_order_spin.setValue(poly_order)
            self.poly_order_spin.blockSignals(False)

    # ------------------------------------------------------------------ #
    # View mode                                                            #
    # ------------------------------------------------------------------ #

    def _set_view(self, mode):
        """Switch between 'original', 'corrected', and 'both'."""
        self.view_original_btn.setChecked(mode == 'original')
        self.view_corrected_btn.setChecked(mode == 'corrected')
        self.view_both_btn.setChecked(mode == 'both')
        self.canvas.viewing_corrected = (mode == 'corrected')
        idx = self.subspectrum_spin.value() - 1
        # Clear stored limits so the view rescales on switch
        self.canvas.axis_limits.pop(idx, None)
        if mode == 'both':
            self.canvas.plot_subspectrum_both(idx)
        else:
            self.canvas.plot_subspectrum(idx)

    def view_original(self):
        self._set_view('original')

    def view_corrected(self):
        self._set_view('corrected')

    def view_both(self):
        self._set_view('both')

    # ------------------------------------------------------------------ #
    # Baseline fitting                                                     #
    # ------------------------------------------------------------------ #

    def set_baseline_spline(self):
        self.baseline_spline_btn.setChecked(True)
        self.baseline_poly_btn.setChecked(False)
        self.poly_order_spin.setEnabled(False)
        self.update_baseline_settings()

    def set_baseline_poly(self):
        self.baseline_spline_btn.setChecked(False)
        self.baseline_poly_btn.setChecked(True)
        self.poly_order_spin.setEnabled(True)
        self.update_baseline_settings()

    def update_baseline_settings(self):
        if not self.svd_controller:
            return
        idx        = self.subspectrum_spin.value() - 1
        fit_type   = 'spline' if self.baseline_spline_btn.isChecked() else 'poly'
        poly_order = self.poly_order_spin.value()
        self.svd_controller.set_baseline_settings(idx, fit_type, poly_order)
        self.canvas.plot_subspectrum(idx)
        self.auto_apply_settings()

    def enable_baseline_mode(self):
        self.canvas.enable_baseline_mode()
        self.clear_current_btn.setEnabled(True)
        self.clear_all_btn.setEnabled(True)
        if hasattr(self, 'toolbar'):
            self.toolbar.setEnabled(False)
            try:
                self.toolbar.mode = ''
                if hasattr(self.toolbar, '_active'):
                    self.toolbar._active = None
                self.canvas.setCursor(Qt.ArrowCursor)
                self.toolbar._update_buttons_checked()
            except Exception as exc:
                logger.error(f"Toolbar reset failed: {exc}")
                self.canvas.setCursor(Qt.ArrowCursor)
        self.canvas.setFocus()

    def disable_baseline_mode(self):
        self.canvas.disable_baseline_mode()
        if hasattr(self, 'toolbar'):
            self.toolbar.setEnabled(True)

    # ------------------------------------------------------------------ #
    # Clear baselines                                                      #
    # ------------------------------------------------------------------ #

    def clear_current_baseline(self):
        if not self.svd_controller:
            return
        idx = self.subspectrum_spin.value() - 1
        self.svd_controller.clear_baseline(idx)
        self.canvas.plot_subspectrum(idx)
        if (self.current_reconstruction_mode == "corrected_only"
                and len(self.svd_controller.manager.baseline_corrections) == 0):
            QMessageBox.information(self, "No Corrections Remaining",
                                    "No baseline corrections remain. Switching to 'All' mode.")
            self.set_mode_and_update_list("all_subspectra")
        self.auto_apply_settings(permanent=False)
        self.update_button_states()

    def clear_all_baselines(self):
        if not self.svd_controller:
            return
        reply = QMessageBox.question(
            self, "Clear All Baselines",
            "Are you sure you want to clear all baseline corrections?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for idx in list(self.svd_controller.manager.baseline_corrections):
            self.svd_controller.clear_baseline(idx)
        self.canvas.plot_subspectrum(self.subspectrum_spin.value() - 1)
        if self.current_reconstruction_mode == "corrected_only":
            QMessageBox.information(self, "No Corrections Remaining",
                                    "All corrections cleared. Switching to 'All' mode.")
            self.set_mode_and_update_list("all_subspectra")
        self.auto_apply_settings(permanent=False)
        self.update_button_states()
        QMessageBox.information(self, "Cleared", "All baseline corrections have been cleared.")

    # ------------------------------------------------------------------ #
    # Reconstruction mode                                                  #
    # ------------------------------------------------------------------ #

    def set_mode_and_update_list(self, mode):
        """Set reconstruction mode and update the component list."""
        self.all_mode_btn.setChecked(False)
        self.corrected_mode_btn.setChecked(False)
        self.first_n_mode_btn.setChecked(False)

        if (mode == "corrected_only"
                and len(self.svd_controller.manager.baseline_corrections) == 0):
            QMessageBox.information(
                self, "No Corrections",
                "No baseline corrections applied yet. Add corrections to subspectra first."
            )
            # Restore previous button
            self.all_mode_btn.setChecked(
                self.current_reconstruction_mode == "all_subspectra"
            )
            self.first_n_mode_btn.setChecked(
                self.current_reconstruction_mode == "first_n"
            )
            return

        self.all_mode_btn.setChecked(mode == "all_subspectra")
        self.corrected_mode_btn.setChecked(mode == "corrected_only")
        self.first_n_mode_btn.setChecked(mode == "first_n")
        self.current_reconstruction_mode = mode

        self._update_component_selection(mode)
        self.auto_apply_settings(permanent=False)

    def _update_component_selection(self, mode):
        """Check / uncheck components list items to match *mode*."""
        if not self.svd_controller or self.components_list.count() == 0:
            return
        self.components_list.blockSignals(True)
        try:
            if mode == "all_subspectra":
                for i in range(self.components_list.count()):
                    self.components_list.item(i).setCheckState(Qt.Checked)
            elif mode == "corrected_only":
                corrected = set(self.svd_controller.manager.baseline_corrections)
                for i in range(self.components_list.count()):
                    state = Qt.Checked if i in corrected else Qt.Unchecked
                    self.components_list.item(i).setCheckState(state)
            elif mode == "first_n":
                n = self.max_components_spin.value()
                for i in range(self.components_list.count()):
                    self.components_list.item(i).setCheckState(
                        Qt.Checked if i < n else Qt.Unchecked
                    )
        finally:
            self.components_list.blockSignals(False)

    # Keep the old name as an alias for backward compatibility
    def update_component_selection_based_on_mode_name(self, mode_name):
        self._update_component_selection(mode_name)

    def on_max_components_changed(self, value):
        if self.first_n_mode_btn.isChecked():
            self._update_component_selection("first_n")
            self.auto_apply_settings()

    def on_component_selection_changed(self, item):
        selected = sum(
            1 for i in range(self.components_list.count())
            if self.components_list.item(i).checkState() == Qt.Checked
        )
        if selected == 0:
            item.setCheckState(Qt.Checked)
            QMessageBox.warning(self, "Selection Required",
                                "At least one component must be selected.")
            return
        # Manual selection — deactivate all preset-mode buttons
        self.all_mode_btn.setChecked(False)
        self.corrected_mode_btn.setChecked(False)
        self.first_n_mode_btn.setChecked(False)
        self.current_reconstruction_mode = "selected"
        self.auto_apply_settings(permanent=False)
        self.update_svd_manager()
        self.update_button_states()

    # ------------------------------------------------------------------ #
    # Invert subspectrum                                                   #
    # ------------------------------------------------------------------ #

    def invert_subspectrum(self):
        if not self.svd_controller:
            return
        idx = self.subspectrum_spin.value() - 1
        if idx in self.svd_controller.manager.baseline_corrections:
            reply = QMessageBox.question(
                self, "Clear Baseline Corrections",
                f"Subspectrum {idx + 1} has baseline corrections.\n\n"
                "Inverting will clear them to avoid coordinate conflicts.\n\n"
                "Do you want to continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return
        self.canvas.axis_limits.pop(idx, None)
        self.svd_controller.manager.invert_subspectrum(idx)
        self.update_svd_manager()
        if self.view_both_btn.isChecked():
            self.canvas.plot_subspectrum_both(idx)
        else:
            self.canvas.plot_subspectrum(idx)
        self.auto_apply_settings(permanent=False)
        self.update_button_states()

    # ------------------------------------------------------------------ #
    # Preview                                                              #
    # ------------------------------------------------------------------ #

    def preview_reconstruction(self):
        if not self.svd_controller or self.svd_controller.manager.corrected_U is None:
            QMessageBox.warning(self, "Error", "No SVD data available.")
            return
        preview = SVDPreviewWindow(
            self,
            self.svd_controller,
            self.get_settings(),
            self.selected_spectra,
        )
        preview.show()

    def show_diagnostics_table(self):
        """Show, per spectrum, the same correction diagnostics that end up
        in metadata['svd_correction'] after Apply — computed live from the
        current dialog settings via the SAME reconstruct_spectra() call
        SVDPreviewWindow.plot_comparison() already uses, rather than a
        second copy of that logic. Nothing is applied or committed;
        reconstruct_spectra() is a pure computation over the manager's
        current in-session state (mode, selected components, baseline
        corrections), which the rest of this dialog already keeps live-
        synced as you interact with it — the same assumption
        SVDPreviewWindow already relies on."""
        if not self.svd_controller or self.svd_controller.manager.corrected_U is None:
            QMessageBox.warning(self, "Error", "No SVD data available.")
            return
        if not self.selected_spectra:
            QMessageBox.warning(self, "No Spectra", "No spectra to show diagnostics for.")
            return

        reconstructed = self.svd_controller.manager.reconstruct_spectra(self.selected_spectra)
        dlg = SVDDiagnosticsDialog(self, reconstructed)
        dlg.exec_()

    # ------------------------------------------------------------------ #
    # Populate components list                                             #
    # ------------------------------------------------------------------ #

    def populate_components_list(self, n_components):
        self.components_list.clear()
        s  = self.svd_controller.manager.s if self.svd_controller else None
        ev = self.svd_controller.manager.explained_variance if self.svd_controller else None
        E  = self._calculate_residual_errors()

        for i in range(min(n_components, 20)):
            variance = ev[i] if ev is not None and i < len(ev) else 0.0
            text     = f"Component {i + 1} ({variance:.3f}%)"
            if s is not None and i < len(s):
                text += f", S={s[i]:.3e}"
            if E is not None and i < len(E):
                text += f", E={E[i]:.3e}"
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.components_list.addItem(item)

    def _calculate_residual_errors(self):
        if not self.svd_controller or self.svd_controller.manager.s is None:
            return None
        s         = self.svd_controller.manager.s
        U         = self.svd_controller.manager.U
        if U is None:
            return None
        n_spectra = U.shape[1]
        n_points  = U.shape[0]
        if n_spectra == 1:
            return np.array([0])
        eigen = s ** 2
        n     = len(s)
        E     = np.zeros(n - 1)
        for m in range(n - 1):
            num  = np.sum(eigen) - np.sum(eigen[:m + 1])
            den  = (n_points - m - 1) * (n_spectra - m - 1)
            E[m] = np.sqrt(num / den) if den > 0 else 0
        return E

    def get_selected_components(self):
        return [
            i for i in range(self.components_list.count())
            if self.components_list.item(i).checkState() == Qt.Checked
        ]

    # ------------------------------------------------------------------ #
    # Settings                                                             #
    # ------------------------------------------------------------------ #

    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — commits directly via commit_callback. No
        separate Run step: feedback (success or failure) is shown right
        here next to the buttons that triggered it, instead of in a
        disconnected main-window message box. The dialog closes itself
        once the commit succeeds.
        """
        if self.commit_callback is None:
            QMessageBox.critical(
                self, "Not Available",
                "This dialog was opened without a way to apply changes. "
                "Please reopen it via Parameters."
            )
            return

        settings = self.get_settings()
        if not settings:
            QMessageBox.warning(
                self, "No Settings",
                "Could not read the current settings from the dialog."
            )
            return

        action = ("add the SVD-corrected result as new spectra" if add_as_new
                  else "replace the selected spectra with their SVD-corrected result")
        confirm = QMessageBox.question(
            self, "Confirm", f"{action[0].upper() + action[1:]}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(settings, add_as_new, list(self.selected_spectra))
        if success:
            QMessageBox.information(self, "Done", message)
            # Use close() rather than accept() so closeEvent still fires —
            # that's what persists the (now-cleared) settings into
            # current_parameters for next time, the same way clicking
            # Close normally does.
            self.close()
        else:
            QMessageBox.warning(self, "Could Not Apply", message)

    def get_settings(self):
        if not self.svd_controller:
            return None
        settings = {
            'correction_mode':    getattr(self, 'current_reconstruction_mode', 'all_subspectra'),
            'selected_subspectra': self.get_selected_components(),
            'baseline_corrections': {
                idx: {
                    'points':     pts,
                    'fit_type':   self.svd_controller.manager.get_baseline_settings(idx)['type'],
                    'poly_order': self.svd_controller.manager.get_baseline_settings(idx)['order'],
                }
                for idx, pts in self.svd_controller.manager.baseline_points.items()
            },
            'inverted_subspectra': list(self.svd_controller.manager.inverted_subspectra),
        }
        if settings['correction_mode'] == 'first_n':
            settings['max_components'] = self.max_components_spin.value()
        return settings

    def auto_apply_settings(self, permanent=False):
        if not self.controller:
            return
        settings = self.get_settings()
        if not settings:
            return
        if self.svd_controller and self.svd_controller.manager:
            self.svd_controller.manager.correction_mode = settings['correction_mode']
            if 'max_components' in settings:
                self.svd_controller.manager.max_components = settings['max_components']
            if 'selected_subspectra' in settings:
                self.svd_controller.manager.set_selected_subspectra(settings['selected_subspectra'])
        if permanent and hasattr(self.controller, 'operations_controller'):
            self.controller.operations_controller.current_parameters["SVD background"] = settings
            selected = self.selected_spectra
            self.controller.operations_controller.last_selection_hash = ','.join(
                sorted(sp['label'] for sp in selected)
            )

    def update_svd_manager(self):
        """Push current dialog state into the SVD manager (for live preview)."""
        if not self.svd_controller or not self.svd_controller.manager:
            return
        settings = self.get_settings()
        if not settings:
            return
        self.svd_controller.manager.correction_mode = settings['correction_mode']
        if 'max_components' in settings:
            self.svd_controller.manager.max_components = settings['max_components']
        if 'selected_subspectra' in settings:
            self.svd_controller.manager.set_selected_subspectra(settings['selected_subspectra'])

    def update_button_states(self):
        if not self.svd_controller:
            return
        # corrected_only button is always enabled; the warning is shown on click
        self.corrected_mode_btn.setEnabled(True)

    # ------------------------------------------------------------------ #
    # Baseline updated signal handler                                      #
    # ------------------------------------------------------------------ #

    def on_baseline_updated(self, subspectrum_index):
        if self.view_both_btn.isChecked():
            self.canvas.plot_subspectrum_both(subspectrum_index)
        if self.current_reconstruction_mode == "corrected_only":
            self._update_component_selection("corrected_only")
        self.auto_apply_settings(permanent=False)
        self.update_button_states()

    # ------------------------------------------------------------------ #
    # Context menus                                                        #
    # ------------------------------------------------------------------ #

    def _show_components_context_menu(self, pos):
        menu = QMenu(self)
        for label, plot_type in (
            ("View Singular Values",                  "singular"),
            ("View Residual Errors",                  "residual"),
            ("View Singular Values and Residual Errors", "both"),
        ):
            action = QAction(label, self)
            action.triggered.connect(lambda checked, t=plot_type: self._show_svd_plot(t))
            menu.addAction(action)
        menu.exec_(self.components_list.mapToGlobal(pos))

    def _show_svd_plot(self, plot_type):
        if not self.svd_controller:
            QMessageBox.warning(self, "Error", "No SVD data available.")
            return
        SVDSingularValuesWindow(self, self.svd_controller, plot_type).show()

    def toggle_controls_visibility(self, visible):
        self.controls_visible = visible
        splitter = self.layout().itemAt(0).widget()
        if isinstance(splitter, QSplitter) and splitter.count() >= 2:
            splitter.widget(0).setVisible(visible)
            splitter.setSizes([400 if visible else 0, 1000])
        self.update()

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def show_help(self):
        show_help_window(self, get_svd_background_help_title(),
                         get_svd_background_help_content())

    def show_reconstruction_help(self):
        from src.help.svd_reconstruction_help import (
            get_svd_reconstruction_help_content,
            get_svd_reconstruction_help_title,
        )
        show_help_window(self, get_svd_reconstruction_help_title(),
                         get_svd_reconstruction_help_content())

    # ------------------------------------------------------------------ #
    # Close                                                                #
    # ------------------------------------------------------------------ #

    def closeEvent(self, event):
        """Save settings when the dialog is closed by any means."""
        self.auto_apply_settings(permanent=True)
        super().closeEvent(event)
