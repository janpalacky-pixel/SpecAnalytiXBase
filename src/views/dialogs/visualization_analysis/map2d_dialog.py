# src/views/dialogs/visualization_analysis/map2d_dialog.py
"""
2-D Spectral Map dialog  –  v2
==============================

Layout
------
Horizontal QSplitter:
  LEFT  : map canvas (matplotlib imshow) + navigation toolbar
  RIGHT : QScrollArea containing all controls, with a second QSplitter
          splitting controls (top) from the spectrum/subspectrum panel (bottom).

Controls (top-to-bottom in the scroll area)
  ┌─ Map Dimensions ───────────────────────────────────────────────┐
  │  Total spectra: N   Rows: [spin]  ×  Cols: [spin]             │
  │  hint label             [Suggest dimensions…]                  │
  └────────────────────────────────────────────────────────────────┘
  ┌─ Spectral Ranges ──────────────────────────────────────────────┐
  │  [Configure Ranges…]   summary label                          │
  │  ☑ Show range preview                                         │
  │  ┄┄ (range preview canvas – collapsible) ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
  └────────────────────────────────────────────────────────────────┘
  ┌─ Map Type ─────────────────────────────────────────────────────┐
  │  ◉ Intensity metric   ○ SVD coefficients                      │
  │  [intensity sub-panel: Metric combo]                          │
  │  [SVD sub-panel: Component combo, EV label,                   │
  │                  Invert btn, Diagnostics btn]                  │
  └────────────────────────────────────────────────────────────────┘
  ┌─ Display Options ──────────────────────────────────────────────┐
  │  Colormap: [combo]   Interpolation: [combo]                   │
  └────────────────────────────────────────────────────────────────┘
  [Compute Map]  [Close]
  ┄┄ (spectrum/subspectrum panel – collapsible) ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄

Interactive click: clicking a pixel in the map shows that spectrum.
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QSpinBox, QDoubleSpinBox, QLabel, QPushButton, QSizePolicy,
    QSplitter, QWidget, QMessageBox, QCheckBox,
    QComboBox, QRadioButton, QButtonGroup, QFrame,
    QScrollArea, QListWidget, QListWidgetItem, QDialogButtonBox,
    QFileDialog,
)
from PyQt5.QtCore import Qt, QTimer
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match, describe_axis_mismatch
from src.views.dialogs.visualization_analysis.roi_spectra_dialogs import (
    _RemoveROIDialog, _ROISpectraDialog,
)

logger = get_logger(__name__)


def _evenly_spaced_spectra(spectra, n=6):
    """Return n evenly spaced spectra from the list for preview purposes.

    Deterministic, zero computation, guarantees spatial diversity across
    the map regardless of how many spectra there are.
    """
    if not spectra:
        return []
    total = len(spectra)
    if total <= n:
        return list(spectra)
    indices = [int(round(i * (total - 1) / (n - 1))) for i in range(n)]
    return [spectra[i] for i in indices]


# ══════════════════════════════════════════════════════════════════════════════
# Canvas helpers
# ══════════════════════════════════════════════════════════════════════════════

class _MapCanvas(FigureCanvas):
    """Left-side canvas that holds the 2-D map imshow."""

    def __init__(self, parent=None):
        self.fig = Figure(tight_layout=False)
        self.ax  = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._cbar_ax   = None
        self._im        = None
        self._crosshair = None
        # Hover tooltip annotation (hidden until mouse enters a valid pixel)
        self._tooltip   = None
        self._hover_cid = None   # connection id for motion_notify_event
        self._draw_empty()

    # ------------------------------------------------------------------
    # Tooltip helpers
    # ------------------------------------------------------------------
    def _make_tooltip(self):
        """Create the annotation box used for hover tooltips."""
        ann = self.ax.annotate(
            "", xy=(0, 0), xytext=(12, 12),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.35", fc="#FFFFF0",
                      ec="#888", alpha=0.88, lw=0.8),
            fontsize=7.5,
            zorder=20,
        )
        ann.set_visible(False)
        return ann

    def enable_hover(self, map_data, spectra, n_cols):
        """Attach a motion-notify callback that shows pixel info on hover.

        Parameters
        ----------
        map_data : 2-D numpy array  (n_rows × n_cols)
        spectra  : flat list of spectrum dicts (same order as the map)
        n_cols   : number of map columns
        """
        self._hover_map_data = map_data
        self._hover_spectra  = spectra
        self._hover_n_cols   = n_cols

        # Create tooltip annotation now that axes exist
        if self._tooltip is None:
            self._tooltip = self._make_tooltip()
        else:
            self._tooltip.set_visible(False)

        # Disconnect previous callback if any
        if self._hover_cid is not None:
            try:
                self.mpl_disconnect(self._hover_cid)
            except Exception:
                pass
        self._hover_cid = self.mpl_connect(
            'motion_notify_event', self._on_hover)

    def disable_hover(self):
        if self._hover_cid is not None:
            try:
                self.mpl_disconnect(self._hover_cid)
            except Exception:
                pass
            self._hover_cid = None
        if self._tooltip is not None:
            self._tooltip.set_visible(False)
            self.draw_idle()

    def _on_hover(self, event):
        if event.inaxes is not self.ax:
            if self._tooltip and self._tooltip.get_visible():
                self._tooltip.set_visible(False)
                self.draw_idle()
            return
        if self._im is None:
            return

        col = int(round(event.xdata)) if event.xdata is not None else -1
        row = int(round(event.ydata)) if event.ydata is not None else -1
        n_rows, n_cols = self._hover_map_data.shape
        if not (0 <= row < n_rows and 0 <= col < n_cols):
            if self._tooltip and self._tooltip.get_visible():
                self._tooltip.set_visible(False)
                self.draw_idle()
            return

        sp_idx = row * n_cols + col
        if sp_idx >= len(self._hover_spectra):
            return

        label   = self._hover_spectra[sp_idx].get('label', f'#{sp_idx}')
        val     = self._hover_map_data[row, col]
        text    = f"Row {row}, Col {col}\n{label}\nValue: {val:.4g}"

        if self._tooltip is None:
            self._tooltip = self._make_tooltip()

        self._tooltip.set_text(text)
        self._tooltip.xy = (col, row)

        # Compute offset in display coords so we can avoid the colorbar axes.
        # Strategy: try right-side offset first; if it would overlap the colorbar
        # (or the figure boundary), flip to the left side.
        fig        = self.fig
        ax         = self.ax
        renderer   = fig.canvas.get_renderer()

        # Display coords of the data point
        disp_pt    = ax.transData.transform((col, row))
        fig_width_px, fig_height_px = fig.get_size_inches() * fig.dpi

        # Colorbar axes right edge in display coords (if present)
        cbar_left_px = fig_width_px  # default: whole figure width
        if hasattr(self, '_cbar_ax') and self._cbar_ax is not None:
            try:
                cbar_bbox = self._cbar_ax.get_window_extent(renderer)
                cbar_left_px = cbar_bbox.x0
            except Exception:
                pass

        # Tooltip box approximate width in pixels (3 lines × ~8 chars → ~70 px)
        tooltip_w_px = 120
        tooltip_h_px = 48

        # Try right-side offset; flip left if box would hit the colorbar or edge
        ox_px = disp_pt[0] + 14 + tooltip_w_px
        if ox_px > cbar_left_px - 4:
            # Place to the left of the cursor
            ox = -(tooltip_w_px + 6)
        else:
            ox = 14

        # Try top offset; flip down if box would go above figure
        oy_px = disp_pt[1] + 14 + tooltip_h_px
        if oy_px > fig_height_px - 4:
            oy = -(tooltip_h_px + 6)
        else:
            oy = 14

        self._tooltip.xyann = (ox, oy)
        self._tooltip.set_visible(True)
        self.draw_idle()

    # ------------------------------------------------------------------
    def _draw_empty(self):
        self.fig.subplots_adjust(left=0.08, right=0.88, top=0.93, bottom=0.08)
        self.ax.set_facecolor('#1a1a2e')
        self.ax.set_title("No map computed yet", color='#888', fontsize=9)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.draw_idle()

    def _draw_stale(self):
        """Show a black canvas with a prompt to recompute after settings change."""
        if self._cbar_ax is not None:
            try:
                self._cbar_ax.remove()
            except Exception:
                pass
            self._cbar_ax = None
        self._im        = None
        self._crosshair = None
        self.fig.subplots_adjust(left=0.08, right=0.88, top=0.93, bottom=0.08)
        self.ax.cla()
        self.ax.set_facecolor('#1a1a2e')
        self.ax.set_title("Settings changed — click  Update Map  to recompute",
                          color='#FF8C00', fontsize=9)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.draw_idle()

    # ------------------------------------------------------------------
    def update_map(self, data, cmap='viridis', interpolation='nearest', title='',
                   xlabel='Column index', ylabel='Row index', equal_aspect=False):
        """Full redraw – called when new map data is available."""
        # Remove old colorbar axes if present
        if self._cbar_ax is not None:
            self._cbar_ax.remove()
            self._cbar_ax = None
        self._im        = None
        self._crosshair = None

        self.fig.subplots_adjust(left=0.08, right=0.85, top=0.93, bottom=0.08)
        self.ax.cla()

        aspect = 'equal' if equal_aspect else 'auto'
        self._im = self.ax.imshow(
            data, cmap=cmap, interpolation=interpolation,
            origin='upper', aspect=aspect,
        )
        # Create colorbar in a fixed-width axes to prevent imshow from shrinking
        from mpl_toolkits.axes_grid1 import make_axes_locatable
        divider      = make_axes_locatable(self.ax)
        self._cbar_ax = divider.append_axes("right", size="5%", pad=0.05)
        self.fig.colorbar(self._im, cax=self._cbar_ax)

        self.ax.set_title(title, fontsize=9)
        self.ax.set_xlabel(xlabel, fontsize=8)
        self.ax.set_ylabel(ylabel, fontsize=8)
        self.draw_idle()

    # ------------------------------------------------------------------
    def update_cmap_interp(self, cmap, interpolation, equal_aspect=False):
        """Lightweight redraw – colormap / interpolation / aspect change only."""
        if self._im is None:
            return
        self._im.set_cmap(cmap)
        self._im.set_interpolation(interpolation)
        self.ax.set_aspect('equal' if equal_aspect else 'auto')
        if self._cbar_ax is not None:
            self._cbar_ax.cla()
            self.fig.colorbar(self._im, cax=self._cbar_ax)
        self.draw_idle()

    # ------------------------------------------------------------------
    def mark_pixel(self, row, col):
        """Draw / move the crosshair marker at (col, row)."""
        if self._crosshair is not None:
            try:
                self._crosshair.remove()
            except Exception:
                pass
        self._crosshair, = self.ax.plot(
            col, row, 'w+', markersize=10, markeredgewidth=1.5,
            zorder=10, clip_on=True,
        )
        self.draw_idle()


class _SpectrumCanvas(FigureCanvas):
    """Shared canvas for the range-preview spectrum and the clicked-point spectrum."""

    def __init__(self, height_inches=2.2, parent=None):
        self.fig = Figure(figsize=(5, height_inches), tight_layout=True)
        self.ax  = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._draw_empty()

    def _draw_empty(self, msg=""):
        self.ax.cla()
        self.ax.set_facecolor('#f9f9f9')
        self.ax.text(0.5, 0.5, msg or "No spectrum shown",
                     ha='center', va='center', transform=self.ax.transAxes,
                     color='#888', fontsize=9)
        self.ax.set_xticks([]); self.ax.set_yticks([])
        self.draw_idle()

    def update_spectrum(self, x, y, title='',
                        xlabel='Wavenumber / x', ylabel='Intensity',
                        color='#1565C0',
                        ranges=None, is_exclude=False,
                        x_min=None, x_max=None):
        self.ax.cla()
        self.ax.plot(x, y, color=color, linewidth=0.9)
        self.ax.set_title(title, fontsize=9)
        self.ax.set_xlabel(xlabel, fontsize=8)
        self.ax.set_ylabel(ylabel, fontsize=8)
        self.ax.tick_params(labelsize=7)
        self.fig.tight_layout()
        # Use draw() not draw_idle() so the canvas is fully rendered before
        # _draw_range_bands adds patches on top.
        self.draw()


# ══════════════════════════════════════════════════════════════════════════════
# Adapter so SVDDiagnosticsDialog can work with Map2DManager
# ══════════════════════════════════════════════════════════════════════════════

class _SVDDiagAdapter:
    """
    Thin shim that wraps Map2DController to expose the same interface that
    SVDDiagnosticsDialog expects from an SVDAnalysisController.
    """

    class _ManagerProxy:
        """Proxies the attributes SVDDiagnosticsDialog reads from manager."""
        def __init__(self, mgr):
            self._m = mgr

        @property
        def explained_variance(self):
            return self._m._explained_variance

        @property
        def s(self):
            return self._m._s

        @property
        def U(self):
            return self._m._U

    def __init__(self, map2d_controller):
        self._ctrl   = map2d_controller
        self.manager = self._ManagerProxy(map2d_controller.manager)

    def get_svd_components_info(self):
        mgr = self._ctrl.manager
        if mgr._U is None:
            return None
        return {
            'n_components': mgr._U.shape[1],
            'n_datapoints': mgr._U.shape[0],
            'explained_variance': mgr._explained_variance,
            'total_variance_first_5': (
                float(np.sum(mgr._explained_variance[:5]))
                if mgr._explained_variance is not None else 0
            ),
        }

    def get_analysis_summary(self):
        mgr = self._ctrl.manager
        if mgr._U is None:
            return {'status': 'No SVD computed', 'n_spectra': 0}
        return {
            'status': 'SVD computed',
            'n_subspectra':  mgr._U.shape[1],
            'n_datapoints':  mgr._U.shape[0],
            'n_spectra':     mgr._Vt.shape[1] if mgr._Vt is not None else 0,
            'explained_variance_first_5': (
                mgr._explained_variance[:5].tolist()
                if mgr._explained_variance is not None else []
            ),
            'spectrum_labels': [],
            'inverted_subspectra': [],
        }

    def calculate_residual_errors(self):
        """Mirror SVDAnalysisManager.calculate_residual_errors logic."""
        mgr = self._ctrl.manager
        if mgr._s is None or mgr._U is None:
            return None
        s  = mgr._s
        num_of_spectra    = mgr._U.shape[1]
        num_of_spec_points = mgr._U.shape[0]
        if num_of_spectra == 1:
            return np.array([0])
        PCA_eigen = s ** 2
        num_of_scores = len(s)
        E = np.zeros(num_of_scores - 1)
        for m in range(num_of_scores - 1):
            expr_1 = np.sum(PCA_eigen) - np.sum(PCA_eigen[:m + 1])
            denom  = (num_of_spec_points - m - 1) * (num_of_spectra - m - 1)
            E[m]   = np.sqrt(expr_1 / denom) if denom > 0 else 0.0
        return E


# ══════════════════════════════════════════════════════════════════════════════
# Main dialog
# ══════════════════════════════════════════════════════════════════════════════

class Map2DDialog(QDialog):
    """
    2-D spectral map dialog.

    Parameters
    ----------
    parent     : parent QWidget
    controller : Map2DController
    spectra    : list of spectrum dicts (x_scale, y_scale, label)
    """

    COLORMAPS = [
        'viridis', 'plasma', 'inferno', 'magma', 'cividis',
        'hot', 'cool', 'coolwarm', 'RdBu_r', 'seismic',
        'jet', 'rainbow', 'turbo', 'gray', 'bone',
    ]
    INTERPOLATIONS = ['nearest', 'bilinear', 'bicubic', 'lanczos', 'spline16']

    def __init__(self, parent, controller, spectra):
        super().__init__(parent)
        self.controller = controller
        self.spectra    = spectra
        self.n_spectra  = len(spectra)

        # Range state — one independent set per mode
        self._ranges     = []       # Intensity mode
        self._is_exclude = False
        self._x_min      = None
        self._x_max      = None
        self._arith_a_ranges     = []   # Arithmetic Band A (independent from intensity)
        self._arith_a_is_exclude = False
        self._svd_ranges         = []   # SVD mode
        self._svd_is_exclude     = False
        self._cluster_ranges     = []   # Cluster mode
        self._cluster_is_exclude = False
        # Arithmetic Band B
        self._arith_b = dict(ranges=[], is_exclude=False, x_min=None, x_max=None)

        # SVD inversion tracking
        self._svd_inverted = set()

        # Last computed map data (for re-render without recompute)
        self._last_map_data           = None
        self._last_cluster_labels     = None
        self._last_cluster_X          = None
        self._last_cluster_spectra_y  = None
        self._roi_active          = False
        self._ellipse_roi_active  = False
        self._ellipse_selector    = None
        self._roi_selector        = None
        self._lasso_selector = None
        self._line_roi_active = False    # line profile mode
        self._line_p1        = None      # first click point (col, row)
        self._remove_roi_active = False
        # Single source of truth for ROI regions.
        # Each entry: {'type':'rect'|'lasso', 'bounds':(r0,r1,c0,c1)|None,
        #              'labels': list[str], 'spectra': list[dict], 'patch': artist}
        self._roi_regions = []
        # Tracks the region+patch most recently created by the *current*
        # activation of the rect/ellipse selector, so that resizing or
        # moving it via its handles after release (the interactive
        # editing the selector deliberately supports) updates that same
        # region in place instead of silently appending a duplicate —
        # matplotlib's RectangleSelector/EllipseSelector re-fires the
        # same callback on every handle-drag release, not just on a
        # brand-new rectangle. Reset to None whenever a fresh selector
        # is (re)activated, so a truly new rectangle after that point is
        # correctly treated as new.
        self._last_rect_region  = None
        self._last_rect_patch   = None
        self._last_ellipse_region = None
        self._last_ellipse_patch  = None
        self._last_clicked_pixel = None   # (row, col) for redraw after invert

        self._build_ui()
        self._connect_signals()
        self._update_dimension_hint()
        self._update_ranges_summary()
        self._update_x_val_visibility()
        self._band_a_header.setText("Band")
        # Initialise checkbox visibility to match default mode (Intensity)
        self._show_bands_cb.setVisible(True)
        self._show_svd_cb.setVisible(False)
        self._svd_full_range_cb.setVisible(False)
        # Colorbar controls visible by default (cluster mode hides them)
        self._clim_auto_cb.setVisible(True)
        self._clim_min_spin.setVisible(True)
        self._clim_max_spin.setVisible(True)
        for lbl in self._clim_pct_labels:
            lbl.setVisible(True)
        # Debounce timer for "Intensity at x" spinbox
        self._x_val_timer = QTimer(self)
        self._x_val_timer.setSingleShot(True)
        self._x_val_timer.setInterval(600)   # ms after last keystroke
        self._x_val_timer.timeout.connect(self._recompute_if_x_val_mode)

        # Prevent Enter key in x-val spinboxes from triggering the dialog's
        # default button (which opens the "Valid map dimensions" dialog)
        for spin in (self._x_val_spin, self._x_val2_spin):
            spin.installEventFilter(self)
        # Seed x_val spinboxes with midpoint of spectra x-range (block signals — no recompute yet)
        try:
            xs = self.spectra[0].get('original_x_scale',
                                     self.spectra[0]['x_scale'])
            mid = float((xs[0] + xs[-1]) / 2)
            for spin in (self._x_val_spin, self._x_val2_spin):
                spin.blockSignals(True)
                spin.setValue(mid)
                spin.blockSignals(False)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Top-level UI construction                                            #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        self.setWindowTitle("2D Spectral Map")
        self.setMinimumSize(950, 600)
        self.resize(1200, 700)
        self.setModal(True)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        # Outer horizontal splitter: map  |  controls+panels
        self._outer_splitter = QSplitter(Qt.Horizontal)
        self._outer_splitter.setChildrenCollapsible(True)

        # ── LEFT: map canvas ─────────────────────────────────────────
        left_widget = QWidget()
        left_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        left_widget.customContextMenuRequested.connect(
            self._show_right_panel_menu)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(2, 2, 2, 2)
        self._map_canvas  = _MapCanvas(left_widget)
        self._map_toolbar = NavigationToolbar(self._map_canvas, left_widget)
        left_layout.addWidget(self._map_toolbar)
        left_layout.addWidget(self._map_canvas, stretch=1)

        # Coordinate + spectrum label shown below map
        self._click_info_label = QLabel("Click a pixel to inspect its spectrum")
        self._click_info_label.setStyleSheet(
            "font-size:8pt; color:#555; padding:2px 6px;")
        left_layout.addWidget(self._click_info_label)

        # Right-click hint anchored to bottom-right of the map area
        right_click_hint = QLabel("right-click map → show/hide panel")
        right_click_hint.setAlignment(Qt.AlignRight)
        right_click_hint.setStyleSheet("font-size:7pt; color:#bbb; padding:0 4px;")
        left_layout.addWidget(right_click_hint)

        self._outer_splitter.addWidget(left_widget)

        # ── RIGHT: inner vertical splitter (controls + spectrum panel)
        self._right_splitter = QSplitter(Qt.Vertical)
        self._right_splitter.setChildrenCollapsible(True)

        # Controls in a scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ctrl_widget = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_widget)
        ctrl_layout.setContentsMargins(4, 4, 4, 4)
        ctrl_layout.setSpacing(5)

        ctrl_layout.addWidget(self._build_dimensions_group())
        ctrl_layout.addWidget(self._build_maptype_group())
        ctrl_layout.addWidget(self._build_display_group())
        ctrl_layout.addStretch()

        ctrl_widget.setMinimumWidth(300)
        scroll.setWidget(ctrl_widget)
        self._right_splitter.addWidget(scroll)

        # Spectrum / subspectrum panel (bottom of right side)
        self._spectrum_panel = self._build_spectrum_panel()
        self._right_splitter.addWidget(self._spectrum_panel)
        self._right_splitter.setSizes([420, 260])

        # Right column = splitter on top + fixed button bar at bottom
        right_col = QWidget()
        right_col_layout = QVBoxLayout(right_col)
        right_col_layout.setContentsMargins(0, 0, 0, 0)
        right_col_layout.setSpacing(0)
        right_col_layout.addWidget(self._right_splitter, stretch=1)

        # Fixed bottom bar — structured into dropdown menus to reduce crowding
        btn_bar = QWidget()
        btn_bar.setStyleSheet(
            "QWidget { background:#F0F0F0; border-top: 1px solid #C8CDD6; }"
        )
        btn_bar_layout = QHBoxLayout(btn_bar)
        btn_bar_layout.setContentsMargins(8, 6, 8, 6)
        btn_bar_layout.setSpacing(6)

        from PyQt5.QtWidgets import QToolButton, QMenu

        # ── Update Map (standalone prominent button) ──────────────────
        self._btn_compute = QPushButton("Update Map")
        self._btn_compute.setStyleSheet(
            "QPushButton{background:#2E7D32;color:white;font-weight:bold;"
            "border-radius:4px;padding:5px 14px; border:none;}"
            "QPushButton:hover{background:#1B5E20;}"
        )
        btn_bar_layout.addWidget(self._btn_compute)

        # ── ROI dropdown ──────────────────────────────────────────────
        roi_btn = QToolButton()
        roi_btn.setText("ROI ▾")
        roi_btn.setToolTip("Region of Interest tools")
        roi_btn.setPopupMode(QToolButton.InstantPopup)
        roi_menu = QMenu(roi_btn)

        self._act_add_roi = roi_menu.addAction("Add ROI rectangle…")
        self._act_add_roi.setEnabled(False)
        self._act_add_roi.setToolTip(
            "Draw rectangles on the map to select regions.\n"
            "Selector stays active — draw multiple in one session.")

        self._act_add_ellipse_roi = roi_menu.addAction("Add ROI ellipse…")
        self._act_add_ellipse_roi.setEnabled(False)
        self._act_add_ellipse_roi.setToolTip(
            "Draw ellipses on the map to select circular or elliptical features.\n"
            "Selector stays active — draw multiple in one session.")

        self._act_paint_roi = roi_menu.addAction("Paint ROI lasso…")
        self._act_paint_roi.setEnabled(False)
        self._act_paint_roi.setToolTip(
            "Draw a freehand lasso to select any non-rectangular region.\n"
            "All pixels inside the lasso path are added to the ROI.")

        self._act_line_roi = roi_menu.addAction("Add ROI line profile…")
        self._act_line_roi.setEnabled(False)
        self._act_line_roi.setToolTip(
            "Click two points on the map to define a line.\n"
            "All pixels along the line (Bresenham) are added to the ROI\n"
            "and shown in the ROI viewer in spatial order along the line.")

        roi_menu.addSeparator()

        self._act_view_roi = roi_menu.addAction("View ROI spectra…  (0)")
        self._act_view_roi.setEnabled(False)

        self._act_roi_stats = roi_menu.addAction("ROI comparison statistics…")
        self._act_roi_stats.setEnabled(False)
        self._act_roi_stats.setToolTip(
            "Show a table of mean ± std of the map value for each ROI region.\n"
            "Requires at least two regions and a computed map.")

        self._act_roi_mode = roi_menu.addAction("Mode: Include  ◯")
        self._act_roi_mode.setEnabled(False)
        self._roi_exclude_mode = False

        roi_menu.addSeparator()

        self._act_remove_roi = roi_menu.addAction("View / Remove ROI regions…")
        self._act_remove_roi.setEnabled(False)
        self._act_remove_roi.setToolTip(
            "List all drawn ROI regions. Click a row to highlight it\n"
            "on the map (yellow) — useful just to identify which region\n"
            "is which. Select one or more and click 'Remove selected'\n"
            "to delete them, or Cancel to close without changes.")

        self._act_clear_roi = roi_menu.addAction("Clear all ROIs")
        self._act_clear_roi.setEnabled(False)

        roi_btn.setMenu(roi_menu)
        btn_bar_layout.addWidget(roi_btn)
        self._roi_menu_btn = roi_btn   # keep reference

        # ── Export dropdown ───────────────────────────────────────────
        exp_btn = QToolButton()
        exp_btn.setText("Export ▾")
        exp_btn.setPopupMode(QToolButton.InstantPopup)
        exp_menu = QMenu(exp_btn)

        self._act_export_map = exp_menu.addAction("Export map (CSV/Excel)…")
        self._act_export_map.setEnabled(False)

        exp_btn.setMenu(exp_menu)
        btn_bar_layout.addWidget(exp_btn)

        # ── Session dropdown ──────────────────────────────────────────
        ses_btn = QToolButton()
        ses_btn.setText("Session ▾")
        ses_btn.setPopupMode(QToolButton.InstantPopup)
        ses_menu = QMenu(ses_btn)

        self._act_save_session = ses_menu.addAction("Save session…")
        self._act_save_session.setEnabled(False)
        self._act_load_session = ses_menu.addAction("Load session…")

        ses_btn.setMenu(ses_menu)
        btn_bar_layout.addWidget(ses_btn)

        btn_bar_layout.addStretch()
        btn_help = QPushButton("Help")
        btn_help.clicked.connect(self._show_help)
        btn_bar_layout.addWidget(btn_help)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_bar_layout.addWidget(btn_close)
        right_col_layout.addWidget(btn_bar)

        self._outer_splitter.addWidget(right_col)
        self._outer_splitter.setSizes([750, 430])

        root.addWidget(self._outer_splitter)

    # ── group builders ──────────────────────────────────────────────────

    def _show_help(self):
        """Open the 2D Map help dialog."""
        try:
            from src.help.map2d_help import (
                get_map2d_help_title,
                get_map2d_help_content,
            )
            from src.help.help_window import show_help_window
            show_help_window(
                self,
                get_map2d_help_title(),
                get_map2d_help_content(),
            )
        except Exception as exc:
            logger.error("Failed to open help: %s", exc, exc_info=True)
            QMessageBox.information(self, "Help",
                                    "Help content could not be loaded.")

    def _build_dimensions_group(self):
        grp = QGroupBox("Map Dimensions")
        lay = QVBoxLayout(grp)
        lay.setSpacing(4)

        self._n_spectra_label = QLabel(f"Total spectra: {self.n_spectra}")
        self._n_spectra_label.setStyleSheet("font-weight:bold;")
        lay.addWidget(self._n_spectra_label)

        row = QHBoxLayout()
        row.setSpacing(4)
        lbl_rows = QLabel("Rows (Y):")
        lbl_rows.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        row.addWidget(lbl_rows)
        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(1, max(self.n_spectra, 1))
        self._rows_spin.setValue(1)
        self._rows_spin.setKeyboardTracking(False)
        self._rows_spin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self._rows_spin.setToolTip("Number of rows (Y) of the 2D map")
        row.addWidget(self._rows_spin)
        lbl_x = QLabel("× Cols (X):")
        lbl_x.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        row.addWidget(lbl_x)
        self._cols_spin = QSpinBox()
        self._cols_spin.setRange(1, max(self.n_spectra, 1))
        self._cols_spin.setValue(1)
        self._cols_spin.setKeyboardTracking(False)
        self._cols_spin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self._cols_spin.setToolTip("Number of columns (X) of the 2D map")
        row.addWidget(self._cols_spin)
        # Suggest dimensions on the same row
        self._btn_autofill = QPushButton("Suggest…")
        self._btn_autofill.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._btn_autofill.setToolTip(
            "Show all valid (rows × cols) factor pairs and auto-fill the most square option."
        )
        row.addWidget(self._btn_autofill)
        row.addStretch()
        lay.addLayout(row)

        self._dim_hint_label = QLabel("")
        self._dim_hint_label.setWordWrap(True)
        self._dim_hint_label.setStyleSheet("font-size:8pt;")
        lay.addWidget(self._dim_hint_label)

        return grp

    @staticmethod
    def _make_band_label(text, color):
        lbl = QLabel(f"<b>{text}</b>")
        lbl.setStyleSheet(f"color:{color}; font-size:8pt;")
        return lbl

    def _build_maptype_group(self):
        grp = QGroupBox("Map Type")
        lay = QVBoxLayout(grp)

        # ── Radio buttons ────────────────────────────────────────────
        radio_row = QHBoxLayout()
        self._radio_intensity = QRadioButton("Intensity metric")
        self._radio_svd       = QRadioButton("SVD coefficients")
        self._radio_arith     = QRadioButton("Map arithmetic")
        self._radio_cluster   = QRadioButton("Cluster overlay")
        self._radio_intensity.setChecked(True)
        self._radio_group = QButtonGroup(self)
        self._radio_group.addButton(self._radio_intensity, 0)
        self._radio_group.addButton(self._radio_svd,       1)
        self._radio_group.addButton(self._radio_arith,     2)
        self._radio_group.addButton(self._radio_cluster,   3)
        radio_row.addWidget(self._radio_intensity)
        radio_row.addWidget(self._radio_svd)
        radio_row.addWidget(self._radio_arith)
        radio_row.addWidget(self._radio_cluster)
        radio_row.addStretch()
        lay.addLayout(radio_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        # ── Shared metric panel (Intensity + Arithmetic) ─────────────
        self._metric_panel = QWidget()
        mlay = QVBoxLayout(self._metric_panel)
        mlay.setContentsMargins(0, 0, 0, 0)
        mlay.setSpacing(4)

        metric_row = QHBoxLayout()
        metric_row.addWidget(QLabel("Metric:"))
        self._metric_combo = QComboBox()
        self._metric_combo.addItems([
            "Integral", "Mean", "Variance",
            "Peak intensity", "Peak position", "FWHM",
            "Baseline-corrected integral", "Intensity at x",
        ])
        self._metric_combo.setToolTip(
            "Integral                    : area under the curve (trapz)\n"
            "Mean                        : average intensity in the range\n"
            "Variance                    : spread of intensities\n"
            "Peak intensity              : maximum y-value in the range\n"
            "Peak position               : x-value at the intensity maximum\n"
            "FWHM                        : full width at half maximum of the dominant peak\n"
            "Baseline-corrected integral : area above the chord connecting the range endpoints\n"
            "Intensity at x              : interpolated intensity at a user-specified x-value"
        )
        metric_row.addWidget(self._metric_combo)
        metric_row.addStretch()
        mlay.addLayout(metric_row)

        # x-value row — shown only for "Intensity at x"
        self._x_val_row = QWidget()
        xrow = QHBoxLayout(self._x_val_row)
        xrow.setContentsMargins(0, 0, 0, 0)
        xrow.setSpacing(4)
        self._x_val_label = QLabel("x:")
        self._x_val_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self._x_val_spin = QDoubleSpinBox()
        self._x_val_spin.setRange(-1e9, 1e9)
        self._x_val_spin.setDecimals(2)
        self._x_val_spin.setValue(0.0)
        self._x_val_spin.setToolTip("x-value for Band A (or the only band in Intensity mode)")
        xrow.addWidget(self._x_val_label)
        xrow.addWidget(self._x_val_spin)
        self._x_val2_label = QLabel("x₂ (Band B):")
        self._x_val2_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self._x_val2_spin = QDoubleSpinBox()
        self._x_val2_spin.setRange(-1e9, 1e9)
        self._x_val2_spin.setDecimals(2)
        self._x_val2_spin.setValue(0.0)
        self._x_val2_spin.setToolTip("x-value for Band B (Arithmetic mode only)")
        xrow.addWidget(self._x_val2_label)
        xrow.addWidget(self._x_val2_spin)
        xrow.addStretch()
        self._x_val_row.setVisible(False)
        mlay.addWidget(self._x_val_row)
        lay.addWidget(self._metric_panel)

        # ── Band A (visible for Intensity + Arithmetic) ──────────────
        self._band_a_panel = QWidget()
        alay_a = QVBoxLayout(self._band_a_panel)
        alay_a.setContentsMargins(0, 2, 0, 2)
        alay_a.setSpacing(2)
        # header label kept as a non-visible placeholder so _update_x_val_visibility
        # can still call setText() without AttributeError
        self._band_a_header = QLabel()
        self._band_a_header.setVisible(False)
        self._btn_configure_ranges = QPushButton("Configure Band A…")
        self._btn_configure_ranges.setToolTip(
            "Define include/exclude spectral ranges and x-min/x-max clip for Band A.")
        alay_a.addWidget(self._btn_configure_ranges)
        self._ranges_summary_label = QLabel("No range — full spectrum")
        self._ranges_summary_label.setWordWrap(True)
        self._ranges_summary_label.setStyleSheet("font-size:8pt; color:#444;")
        alay_a.addWidget(self._ranges_summary_label)
        lay.addWidget(self._band_a_panel)

        # ── Intensity-only placeholder (empty — Band A above covers it) ─
        self._intensity_panel = QWidget()
        lay.addWidget(self._intensity_panel)

        # ── SVD sub-panel ────────────────────────────────────────────
        self._svd_panel = QWidget()
        svlay = QVBoxLayout(self._svd_panel)
        svlay.setContentsMargins(0, 0, 0, 0)
        svlay.setSpacing(4)
        comp_label_row = QHBoxLayout()
        comp_label_row.setSpacing(4)
        lbl_comp = QLabel("Component:")
        lbl_comp.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        comp_label_row.addWidget(lbl_comp)
        self._component_combo = QComboBox()
        self._component_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._component_combo.setMinimumWidth(80)
        self._component_combo.setMaximumWidth(200)
        self._component_combo.setToolTip(
            "Choose SVD component whose V-coefficients are displayed as map values.")
        comp_label_row.addWidget(self._component_combo)
        lbl_label = QLabel("Label:")
        lbl_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        comp_label_row.addWidget(lbl_label)
        self._comp_label_combo = QComboBox()
        self._comp_label_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._comp_label_combo.addItems(["Explained var.(%)", "Singular value σ", "Residual error"])
        comp_label_row.addWidget(self._comp_label_combo)
        comp_label_row.addStretch()
        svlay.addLayout(comp_label_row)
        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(4)
        self._btn_invert = QPushButton("Invert")
        self._btn_invert.setEnabled(False)
        btn_row2.addWidget(self._btn_invert)
        self._btn_multi_map = QPushButton("Multi-map…")
        self._btn_multi_map.setEnabled(False)
        btn_row2.addWidget(self._btn_multi_map)
        self._btn_diagnostics = QPushButton("Diagnostics…")
        self._btn_diagnostics.setEnabled(False)
        btn_row2.addWidget(self._btn_diagnostics)
        btn_row2.addStretch()
        svlay.addLayout(btn_row2)
        lay.addWidget(self._svd_panel)
        self._svd_panel.setVisible(False)

        # ── Arithmetic sub-panel (Band A + Band B on one row + operation) ──
        self._arith_panel = QWidget()
        alay = QVBoxLayout(self._arith_panel)
        alay.setContentsMargins(0, 0, 0, 0)
        alay.setSpacing(4)

        # Band A and Band B buttons on the same row
        bands_row = QHBoxLayout()
        bands_row.setSpacing(6)
        self._btn_arith_range_a = QPushButton("Configure Band A…")
        self._btn_arith_range_a.setToolTip(
            "Define include/exclude spectral ranges for Band A.")
        bands_row.addWidget(self._btn_arith_range_a, 1)
        self._btn_arith_range_b = QPushButton("Configure Band B…")
        self._btn_arith_range_b.setToolTip(
            "Define include/exclude spectral ranges for Band B.")
        bands_row.addWidget(self._btn_arith_range_b, 1)
        alay.addLayout(bands_row)

        # Summary labels row (A left, B right)
        summary_row = QHBoxLayout()
        summary_row.setSpacing(6)
        self._arith_range_a_summary = QLabel("A: full spectrum")
        self._arith_range_a_summary.setStyleSheet("font-size:8pt; color:#1565C0;")
        self._arith_range_a_summary.setWordWrap(True)
        summary_row.addWidget(self._arith_range_a_summary, 1)
        self._arith_range_b_label = QLabel("B: full spectrum")
        self._arith_range_b_label.setStyleSheet("font-size:8pt; color:#C62828;")
        self._arith_range_b_label.setWordWrap(True)
        summary_row.addWidget(self._arith_range_b_label, 1)
        alay.addLayout(summary_row)

        # Operation dropdown below both bands
        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("Operation:"))
        self._arith_op_combo = QComboBox()
        self._arith_op_combo.addItems(["A / B", "A - B", "A + B", "A × B"])
        self._arith_op_combo.setToolTip(
            "A / B : ratio map\nA - B : difference map\n"
            "A + B : sum map\nA × B : product map")
        op_row.addWidget(self._arith_op_combo)
        op_row.addStretch()
        alay.addLayout(op_row)

        lay.addWidget(self._arith_panel)
        self._arith_panel.setVisible(False)

        # ── Cluster overlay sub-panel (embedded K-means) ─────────────
        self._cluster_panel = QWidget()
        clay = QVBoxLayout(self._cluster_panel)
        clay.setContentsMargins(0, 0, 0, 4)
        clay.setSpacing(4)

        # Method + k row
        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("Method:"))
        self._cluster_method_combo = QComboBox()
        self._cluster_method_combo.addItems([
            "K-means",
            "MiniBatch K-means",
        ])
        self._cluster_method_combo.setToolTip(
            "K-means: standard algorithm, accurate, suitable for up to ~5 000 spectra.\n"
            "MiniBatch K-means: faster approximation, recommended for very large maps.")
        method_row.addWidget(self._cluster_method_combo)
        method_row.addSpacing(8)
        method_row.addWidget(QLabel("k (clusters):"))
        self._cluster_k_spin = QSpinBox()
        self._cluster_k_spin.setRange(2, 20)
        self._cluster_k_spin.setValue(4)
        self._cluster_k_spin.setFixedWidth(55)
        self._cluster_k_spin.setToolTip(
            "Number of clusters.  Start with a small value (3–5) and increase\n"
            "if the map shows too little spatial variation.")
        method_row.addWidget(self._cluster_k_spin)
        method_row.addStretch()
        clay.addLayout(method_row)

        # Range note
        self._cluster_range_note = QLabel(
            "Clustering uses the Band A spectral range above.")
        self._cluster_range_note.setStyleSheet("font-size:8pt; color:#555;")
        self._cluster_range_note.setWordWrap(True)
        clay.addWidget(self._cluster_range_note)

        # Status label
        self._cluster_status_label = QLabel("")
        self._cluster_status_label.setWordWrap(True)
        self._cluster_status_label.setStyleSheet("font-size:8pt; color:#555;")
        clay.addWidget(self._cluster_status_label)

        # Averages button (enabled after clustering)
        self._btn_cluster_avg = QPushButton("Show cluster averages…")
        self._btn_cluster_avg.setToolTip(
            "Show the mean spectrum of each cluster and export them to the main list.")
        self._btn_cluster_avg.setEnabled(False)
        clay.addWidget(self._btn_cluster_avg)

        lay.addWidget(self._cluster_panel)
        self._cluster_panel.setVisible(False)

        return grp

    def _build_display_group(self):
        from PyQt5.QtWidgets import QGridLayout, QDoubleSpinBox
        grp = QGroupBox("Display Options")
        grid = QGridLayout(grp)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        grid.addWidget(QLabel("Colormap:"), 0, 0)
        self._cmap_combo = QComboBox()
        self._cmap_combo.addItems(self.COLORMAPS)
        self._cmap_combo.setCurrentText("viridis")
        grid.addWidget(self._cmap_combo, 0, 1)

        grid.addWidget(QLabel("Interpolation:"), 1, 0)
        self._interp_combo = QComboBox()
        self._interp_combo.addItems(self.INTERPOLATIONS)
        self._interp_combo.setCurrentText("nearest")
        grid.addWidget(self._interp_combo, 1, 1)

        self._equal_aspect_cb = QCheckBox("Equal aspect ratio (rows : cols)")
        self._equal_aspect_cb.setChecked(False)
        self._equal_aspect_cb.setToolTip(
            "When checked, the map image is displayed with equal pixel spacing\n"
            "on both axes, so each pixel appears square in the plot.\n"
            "Uncheck for non-square maps where you want the image to fill the panel."
        )
        grid.addWidget(self._equal_aspect_cb, 2, 0, 1, 2)

        # ── Colorbar range (Feature 3) ──────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        grid.addWidget(sep, 3, 0, 1, 2)

        self._clim_auto_cb = QCheckBox("Auto colorbar range")
        self._clim_auto_cb.setChecked(True)
        self._clim_auto_cb.setToolTip(
            "When checked, colorbar min/max are set from the full data range.\n"
            "Uncheck to clip by percentile — useful to suppress outlier pixels.")
        grid.addWidget(self._clim_auto_cb, 4, 0, 1, 2)

        clim_row = QHBoxLayout()
        clim_row.setSpacing(4)
        _lbl_lo = QLabel("Low %:")
        clim_row.addWidget(_lbl_lo)
        self._clim_min_spin = QDoubleSpinBox()
        self._clim_min_spin.setRange(0.0, 99.9)
        self._clim_min_spin.setDecimals(1)
        self._clim_min_spin.setSingleStep(0.5)
        self._clim_min_spin.setValue(2.0)
        self._clim_min_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._clim_min_spin.setEnabled(False)
        self._clim_min_spin.setToolTip(
            "Clip the bottom N% of map values (e.g. 2 = clip bottom 2%).\n"
            "Useful when a few very dark pixels dominate the colorbar.")
        clim_row.addWidget(self._clim_min_spin)
        _lbl_hi = QLabel("High %:")
        clim_row.addWidget(_lbl_hi)
        self._clim_max_spin = QDoubleSpinBox()
        self._clim_max_spin.setRange(0.1, 100.0)
        self._clim_max_spin.setDecimals(1)
        self._clim_max_spin.setSingleStep(0.5)
        self._clim_max_spin.setValue(98.0)
        self._clim_max_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._clim_max_spin.setEnabled(False)
        self._clim_max_spin.setToolTip(
            "Clip the top N% of map values (e.g. 98 = clip top 2%).\n"
            "Useful when a few very bright pixels dominate the colorbar.")
        clim_row.addWidget(self._clim_max_spin)

        clim_widget = QWidget()
        clim_widget.setLayout(clim_row)
        grid.addWidget(clim_widget, 5, 0, 1, 2)
        self._clim_pct_labels = [_lbl_lo, _lbl_hi]

        grid.setColumnStretch(1, 1)
        return grp

    def _build_spectrum_panel(self):
        """Bottom-right panel: clicked-spectrum / subspectrum display.

        Right-click anywhere on the map (left side) or on this panel
        to show/hide the entire right control column via the outer splitter.
        """
        container = QWidget()
        container.setContextMenuPolicy(Qt.CustomContextMenu)
        container.customContextMenuRequested.connect(
            self._show_right_panel_menu)
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(4, 2, 4, 2)
        vlay.setSpacing(2)

        hdr = QHBoxLayout()
        self._spectrum_title_label = QLabel("Spectrum / subspectrum panel")
        self._spectrum_title_label.setStyleSheet(
            "font-weight:bold; font-size:8pt; color:#1A237E;")
        hdr.addWidget(self._spectrum_title_label)
        hdr.addStretch()
        self._show_bands_cb = QCheckBox("Show range bands")
        self._show_bands_cb.setChecked(True)
        self._show_bands_cb.setToolTip(
            "Overlay shaded band region(s) on the spectrum below.\n"
            "Intensity mode: one blue band.\n"
            "Arithmetic mode: Band A in blue, Band B in red.")
        hdr.addWidget(self._show_bands_cb)

        self._show_svd_cb = QCheckBox("Show SVD component")
        self._show_svd_cb.setChecked(True)
        self._show_svd_cb.setToolTip(
            "Overlay the SVD subspectrum (orange dashed) on the clicked-pixel spectrum.\n"
            "Only active in SVD coefficients mode.")
        hdr.addWidget(self._show_svd_cb)

        self._svd_full_range_cb = QCheckBox("Full spectrum")
        self._svd_full_range_cb.setChecked(False)
        self._svd_full_range_cb.setToolTip(
            "Checked: show the full spectrum with SVD band region shaded and\n"
            "component overlaid on a twin axis within that region.\n"
            "Unchecked (default): show the spectrum clipped to the SVD range\n"
            "so it matches the component x-axis exactly.")
        hdr.addWidget(self._svd_full_range_cb)
        vlay.addLayout(hdr)

        self._spectrum_canvas  = _SpectrumCanvas(height_inches=2.4)
        self._spectrum_toolbar = NavigationToolbar(
            self._spectrum_canvas, container)
        vlay.addWidget(self._spectrum_toolbar)
        vlay.addWidget(self._spectrum_canvas, stretch=1)
        return container

    # ------------------------------------------------------------------ #
    # Signal connections                                                   #
    # ------------------------------------------------------------------ #

    def _connect_signals(self):
        self._radio_group.buttonClicked.connect(self._on_mode_changed)
        self._rows_spin.valueChanged.connect(self._on_dims_changed)
        self._cols_spin.valueChanged.connect(self._on_dims_changed)
        self._btn_autofill.clicked.connect(self._show_factor_pairs)
        self._btn_configure_ranges.clicked.connect(self._configure_ranges)
        self._btn_compute.clicked.connect(self._compute_map)
        self._metric_combo.currentIndexChanged.connect(self._on_metric_changed)
        self._x_val_spin.valueChanged.connect(self._on_x_val_changed)
        self._x_val2_spin.valueChanged.connect(self._on_x_val_changed)
        self._show_bands_cb.stateChanged.connect(self._on_show_bands_changed)
        self._show_svd_cb.stateChanged.connect(self._on_show_svd_changed)
        self._svd_full_range_cb.stateChanged.connect(self._on_svd_display_changed)
        self._component_combo.currentIndexChanged.connect(
            self._on_component_changed)
        self._comp_label_combo.currentIndexChanged.connect(
            self._refresh_component_combo_labels)
        self._btn_invert.clicked.connect(self._invert_component)
        self._btn_multi_map.clicked.connect(self._show_multi_map)
        self._btn_diagnostics.clicked.connect(self._show_diagnostics)
        self._cmap_combo.currentTextChanged.connect(
            self._on_cmap_interp_changed)
        self._interp_combo.currentTextChanged.connect(
            self._on_cmap_interp_changed)
        self._equal_aspect_cb.stateChanged.connect(
            self._on_aspect_changed)
        # Feature 3: colorbar range
        self._clim_auto_cb.stateChanged.connect(self._on_clim_auto_changed)
        self._clim_min_spin.valueChanged.connect(self._on_clim_manual_changed)
        self._clim_max_spin.valueChanged.connect(self._on_clim_manual_changed)
        # Feature 1: export
        self._act_export_map.triggered.connect(self._export_map)
        # Feature 2: ROI
        self._act_add_roi.triggered.connect(self._toggle_roi)
        self._act_add_ellipse_roi.triggered.connect(self._toggle_ellipse_roi)
        self._act_paint_roi.triggered.connect(self._toggle_lasso)
        self._act_line_roi.triggered.connect(self._toggle_line_roi)
        self._act_clear_roi.triggered.connect(self._clear_all_rois)
        self._act_view_roi.triggered.connect(self._open_roi_viewer)
        self._act_roi_stats.triggered.connect(self._show_roi_statistics)
        self._act_roi_mode.triggered.connect(self._toggle_roi_mode)
        self._act_remove_roi.triggered.connect(self._activate_remove_roi)
        self._act_save_session.triggered.connect(self._save_session)
        self._act_load_session.triggered.connect(self._load_session)
        # Feature 5: save/load session
        self._act_save_session.triggered.connect(self._save_session)
        self._act_load_session.triggered.connect(self._load_session)
        self._btn_arith_range_a.clicked.connect(
            lambda: self._configure_arith_band('a'))
        self._btn_arith_range_b.clicked.connect(
            lambda: self._configure_arith_band('b'))
        self._arith_op_combo.currentIndexChanged.connect(self._invalidate_map)
        self._cluster_k_spin.valueChanged.connect(self._invalidate_map)
        self._cluster_method_combo.currentIndexChanged.connect(self._invalidate_map)
        self._btn_cluster_avg.clicked.connect(self._show_cluster_averages)
        # Map click
        self._map_canvas.mpl_connect('button_press_event',
                                     self._on_map_click)

    # ------------------------------------------------------------------ #
    # Slot implementations                                                 #
    # ------------------------------------------------------------------ #

    def eventFilter(self, obj, event):
        """Consume Enter/Return key on x-value spinboxes so it doesn't
        activate the dialog's default button."""
        from PyQt5.QtCore import QEvent
        if obj in (self._x_val_spin, self._x_val2_spin):
            if event.type() == QEvent.KeyPress:
                from PyQt5.QtCore import Qt as _Qt
                if event.key() in (
                        _Qt.Key_Return, _Qt.Key_Enter):
                    # Fire the debounce timer immediately instead
                    self._x_val_timer.stop()
                    self._recompute_if_x_val_mode()
                    return True   # consume the event
        return super().eventFilter(obj, event)

    def _active_range_state(self):
        """Return (ranges, is_exclude) for the currently active mode."""
        if self._radio_svd.isChecked():
            return self._svd_ranges, self._svd_is_exclude
        elif self._radio_cluster.isChecked():
            return self._cluster_ranges, self._cluster_is_exclude
        elif self._radio_arith.isChecked():
            return self._arith_a_ranges, self._arith_a_is_exclude
        else:  # intensity
            return self._ranges, self._is_exclude

    def _set_active_range_state(self, ranges, is_exclude):
        """Write (ranges, is_exclude) to the currently active mode's state."""
        if self._radio_svd.isChecked():
            self._svd_ranges     = ranges
            self._svd_is_exclude = is_exclude
        elif self._radio_cluster.isChecked():
            self._cluster_ranges     = ranges
            self._cluster_is_exclude = is_exclude
        elif self._radio_arith.isChecked():
            self._arith_a_ranges     = ranges
            self._arith_a_is_exclude = is_exclude
        else:
            self._ranges     = ranges
            self._is_exclude = is_exclude

    def _on_mode_changed(self, _btn):
        is_svd     = self._radio_svd.isChecked()
        is_arith   = self._radio_arith.isChecked()
        is_int     = self._radio_intensity.isChecked()
        is_cluster = self._radio_cluster.isChecked()

        # Clear SVD twin axis when leaving SVD mode
        if not is_svd:
            self._clear_twin_axis()

        # Metric panel and band config visible for intensity and arithmetic only
        self._metric_panel.setVisible(is_int or is_arith)
        self._update_x_val_visibility()
        # Band A panel: visible for all modes except cluster/SVD hides metric
        self._band_a_panel.setVisible(is_int or is_arith or is_svd or is_cluster)
        # In arithmetic mode, _arith_panel has its own Band A button — hide the one in _band_a_panel
        self._btn_configure_ranges.setVisible(not is_arith)
        self._ranges_summary_label.setVisible(not is_arith)
        self._intensity_panel.setVisible(False)
        self._svd_panel.setVisible(is_svd)
        self._arith_panel.setVisible(is_arith)
        self._cluster_panel.setVisible(is_cluster)
        self._update_ranges_summary()  # show the active mode's range

        # Colorbar range controls only make sense for continuous maps
        clim_visible = not is_cluster
        self._clim_auto_cb.setVisible(clim_visible)
        self._clim_min_spin.setVisible(clim_visible)
        self._clim_max_spin.setVisible(clim_visible)
        # find and hide/show the Low%/High% labels too
        for lbl in self._clim_pct_labels:
            lbl.setVisible(clim_visible)

        # Spectrum panel checkboxes: show only when relevant
        self._show_bands_cb.setVisible(is_int or is_arith or is_cluster)
        self._show_svd_cb.setVisible(is_svd)
        self._svd_full_range_cb.setVisible(is_svd)


        # Remember whether a previous map existed before invalidating
        had_map = self._last_map_data is not None
        self._invalidate_map()

        if is_svd:
            # SVD: clear the spectrum panel — only show after Update Map
            self._spectrum_title_label.setText("Press 'Update Map' to compute SVD")
            self._spectrum_canvas.ax.cla()
            self._spectrum_canvas.draw_idle()
        elif is_int or is_arith or is_cluster:
            # Always recompute for fast modes when dims are valid —
            # regardless of whether a previous map existed (covers jumping from SVD)
            n_rows = self._rows_spin.value()
            n_cols = self._cols_spin.value()
            dims_ok = (n_rows > 0 and n_cols > 0
                       and n_rows * n_cols == self.n_spectra)
            if dims_ok:
                self._compute_map()
            else:
                self._show_range_spectrum_in_panel()

    def _update_x_val_visibility(self):
        """Show/hide x-value spinboxes and configure buttons based on metric and mode."""
        is_x_metric = self._metric_combo.currentText() == "Intensity at x"
        is_arith    = self._radio_arith.isChecked()
        is_svd      = self._radio_svd.isChecked()
        is_cluster  = self._radio_cluster.isChecked()

        # x-value row only for "Intensity at x" in non-SVD/cluster modes
        self._x_val_row.setVisible(is_x_metric and not is_svd and not is_cluster)
        self._x_val_label.setText("x₁ (Band A):" if is_arith else "x:")
        self._x_val2_label.setVisible(is_arith and is_x_metric)
        self._x_val2_spin.setVisible(is_arith and is_x_metric)

        # Configure band button: always shown in SVD/cluster mode
        show_configure = is_svd or is_cluster or not is_x_metric
        self._btn_configure_ranges.setVisible(show_configure)
        self._ranges_summary_label.setVisible(show_configure)

        # Band B configure: only for arithmetic
        if hasattr(self, '_btn_arith_range_b'):
            show_b = is_arith and not is_x_metric
            self._btn_arith_range_a.setVisible(is_arith)
            self._btn_arith_range_b.setVisible(show_b)
            self._arith_range_a_summary.setVisible(is_arith)
            self._arith_range_b_label.setVisible(show_b)

        # Labels per mode
        if is_svd:
            self._btn_configure_ranges.setText("Configure SVD range…")
            self._band_a_header.setText("SVD computation range")
        elif is_cluster:
            self._btn_configure_ranges.setText("Configure clustering range…")
            self._band_a_header.setText("Clustering range")
        elif is_arith and not is_x_metric:
            self._btn_configure_ranges.setText("Configure Band A…")
            self._band_a_header.setText("Band A")
        elif not is_x_metric:
            self._btn_configure_ranges.setText("Configure Band…")
            self._band_a_header.setText("Band")

    def _on_metric_changed(self):
        self._update_x_val_visibility()
        if (self._radio_intensity.isChecked() or self._radio_arith.isChecked()) \
                and self._last_map_data is not None:
            self._compute_map()
        else:
            self._invalidate_map()

    def _on_x_val_changed(self):
        """x-value spinbox changed — debounce so recompute fires after typing stops."""
        self._x_val_timer.start()   # restart the 600 ms countdown on every change

    def _recompute_if_x_val_mode(self):
        """Called by the debounce timer — recompute when metric is Intensity at x."""
        if self._metric_combo.currentText() == "Intensity at x" \
                and (self._radio_intensity.isChecked()
                     or self._radio_arith.isChecked()):
            # Only recompute if dimensions are valid — avoids the dimension
            # warning dialog firing silently on every keystroke
            n_rows = self._rows_spin.value()
            n_cols = self._cols_spin.value()
            if self.controller.validate_dimensions(self.n_spectra, n_rows, n_cols):
                self._compute_map()

    def _on_dims_changed(self):
        """Called when rows or cols spinbox changes — update hint and optionally recompute."""
        self._update_dimension_hint()
        n_rows  = self._rows_spin.value()
        n_cols  = self._cols_spin.value()
        is_fast = (self._radio_intensity.isChecked()
                   or self._radio_arith.isChecked()
                   or self._radio_cluster.isChecked())
        dims_ok = (n_rows > 0 and n_cols > 0
                   and n_rows * n_cols == self.n_spectra)
        if is_fast and dims_ok:
            self._compute_map()
        else:
            self._invalidate_map()

    def _invalidate_map(self):
        """Clear the displayed map and show a 'recompute needed' message."""
        self._last_map_data = None
        self._map_canvas.disable_hover()
        self._clear_all_rois()
        self._map_canvas._draw_stale()

    # ── Dimensions ──────────────────────────────────────────────────────

    def _update_dimension_hint(self):
        r, c    = self._rows_spin.value(), self._cols_spin.value()
        product = r * c
        if product == self.n_spectra:
            self._dim_hint_label.setText(
                f"✓  {r} × {c} = {product}  (valid)")
            self._dim_hint_label.setStyleSheet(
                "font-size:8pt; color:#2E7D32; font-weight:bold;")
        else:
            diff = product - self.n_spectra
            sign = "+" if diff > 0 else ""
            self._dim_hint_label.setText(
                f"✗  {r} × {c} = {product}  "
                f"(need {self.n_spectra}, off by {sign}{diff})")
            self._dim_hint_label.setStyleSheet(
                "font-size:8pt; color:#C62828;")

    def _show_factor_pairs(self):
        pairs = self.controller.get_factor_pairs(self.n_spectra)
        if not pairs:
            QMessageBox.information(self, "Factor pairs",
                                    "No valid integer dimensions found.")
            return

        # Build a small dialog with a selectable list
        dlg = QDialog(self)
        dlg.setWindowTitle("Valid map dimensions")
        dlg.setMinimumWidth(280)
        lay = QVBoxLayout(dlg)

        lay.addWidget(QLabel(
            f"Valid (rows × cols) pairs for <b>{self.n_spectra}</b> spectra.<br>"
            f"Double-click or select and press OK to apply:"))

        lst = QListWidget()
        best_idx = 0
        best_ratio = float('inf')
        for i, (a, b) in enumerate(pairs):
            lst.addItem(QListWidgetItem(f"{a} × {b} = {self.n_spectra}"))
            ratio = abs(a / b - 1)
            if ratio < best_ratio:
                best_ratio = ratio
                best_idx   = i
        lst.setCurrentRow(best_idx)
        lst.itemDoubleClicked.connect(lambda _: dlg.accept())
        lay.addWidget(lst)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() == QDialog.Accepted:
            row = lst.currentRow()
            if row >= 0:
                a, b = pairs[row]
                self._rows_spin.setValue(a)
                self._cols_spin.setValue(b)

    # ── Spectral ranges ─────────────────────────────────────────────────

    def _compute_cluster_map(self, n_rows, n_cols):
        """Run K-means / MiniBatch K-means on the map spectra and display result."""
        from sklearn.cluster import KMeans, MiniBatchKMeans
        from sklearn.preprocessing import StandardScaler

        k      = self._cluster_k_spin.value()
        method = self._cluster_method_combo.currentText()

        self._cluster_status_label.setText("Computing clusters…")
        self._cluster_status_label.setStyleSheet("font-size:8pt; color:#555;")

        # Build data matrix using Band A range (same as intensity/SVD)
        inc = [] if self._cluster_is_exclude else self._cluster_ranges
        exc = self._cluster_ranges if self._cluster_is_exclude else []
        mgr = self.controller.manager

        filtered_y = []
        filtered_x = None
        reference_sp = None
        for sp in self.spectra:
            x = np.asarray(sp.get('original_x_scale', sp['x_scale']), dtype=float)
            y = np.asarray(sp.get('original_y_scale', sp['y_scale']), dtype=float)
            xf, yf = mgr._apply_range_filter(x, y, None, None, inc, exc)
            if filtered_x is None:
                filtered_x = xf
                reference_sp = sp
            elif len(xf) == len(filtered_x) and not axes_match(xf, filtered_x):
                # Same length, but NOT the same x-axis — the length-only
                # check below wouldn't catch this. Clustering compares
                # spectra point-by-point across the whole batch, so this
                # needs the same "share a common x-axis" guarantee every
                # other combines-spectra operation in this app requires.
                # Verified directly: two same-length, x-offset spectra
                # combined silently before this check existed.
                QMessageBox.warning(
                    self, "Mismatched x-axis",
                    f"Cannot cluster — spectra don't share a common x-axis.\n\n"
                    f"{describe_axis_mismatch(reference_sp, sp, 'clustering')}"
                )
                self._cluster_status_label.setText("")
                return
            filtered_y.append(yf)

        # Check consistent lengths
        lengths = {len(y) for y in filtered_y}
        if len(lengths) > 1:
            QMessageBox.warning(
                self, "Incompatible spectra",
                f"Spectra have different lengths after filtering "
                f"({lengths}).\nApply the same Data Range preprocessing first.")
            self._cluster_status_label.setText("")
            return

        try:
            X = np.vstack(filtered_y)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            self._cluster_status_label.setText("")
            return

        # Standardise (zero mean, unit variance per wavenumber)
        X = StandardScaler().fit_transform(X)

        try:
            if method == "MiniBatch K-means":
                model = MiniBatchKMeans(n_clusters=k, random_state=42,
                                        n_init=3)
            else:
                model = KMeans(n_clusters=k, random_state=42, n_init=10)
            label_array = model.fit_predict(X).astype(int)
        except Exception as exc:
            QMessageBox.critical(self, "Clustering failed", str(exc))
            self._cluster_status_label.setText("")
            return

        self._last_cluster_labels = label_array   # store for fast redraw
        self._last_cluster_X      = X             # standardised matrix for diagnostics
        self._last_cluster_spectra_y = np.vstack(filtered_y)  # raw (unstandardised)
        map_data = label_array.reshape(n_rows, n_cols)
        self._last_map_data = map_data.astype(float)

        self._cluster_status_label.setText(
            f"✓  {k} clusters  ({method})  |  "
            f"{n_rows * n_cols} spectra")
        self._cluster_status_label.setStyleSheet("font-size:8pt; color:#2E7D32;")
        self._btn_cluster_avg.setEnabled(True)

        self._draw_cluster_map(map_data, k, n_rows, n_cols,
                               title=f"{method}  k={k}  ({n_rows}×{n_cols})")
        self._show_range_spectrum_in_panel()
        self._on_map_computed()

    def _draw_cluster_map(self, map_data, k, n_rows, n_cols, title="Cluster overlay"):
        """Render the cluster label map with a discrete colormap."""
        import matplotlib.colors as mcolors
        base_cmap    = plt.cm.get_cmap('tab10', k)
        norm         = mcolors.BoundaryNorm(
            boundaries=np.arange(-0.5, k + 0.5, 1), ncolors=k)
        interp       = self._interp_combo.currentText()
        equal_aspect = self._equal_aspect_cb.isChecked()

        self._map_canvas.ax.cla()
        if self._map_canvas._cbar_ax is not None:
            try:
                self._map_canvas._cbar_ax.remove()
            except Exception:
                pass
            self._map_canvas._cbar_ax = None

        im = self._map_canvas.ax.imshow(
            map_data, cmap=base_cmap, norm=norm,
            origin='upper',
            aspect='equal' if equal_aspect else 'auto',
            interpolation=interp)

        from mpl_toolkits.axes_grid1 import make_axes_locatable
        divider = make_axes_locatable(self._map_canvas.ax)
        cbar_ax = divider.append_axes("right", size="5%", pad=0.05)
        cbar    = self._map_canvas.fig.colorbar(
            im, cax=cbar_ax, ticks=np.arange(k))
        cbar.set_ticklabels([f"C{i}" for i in range(k)])
        self._map_canvas._cbar_ax = cbar_ax
        self._map_canvas._im      = im

        self._map_canvas.ax.set_title(title, fontsize=9)
        self._map_canvas.ax.set_xlabel("Column index", fontsize=8)
        self._map_canvas.ax.set_ylabel("Row index",    fontsize=8)
        self._map_canvas.fig.tight_layout()
        self._map_canvas.draw()

    def _show_cluster_averages(self):
        """Show mean spectrum per cluster and offer export to main list."""
        if self._last_cluster_labels is None or self._last_cluster_spectra_y is None:
            return

        labels = self._last_cluster_labels
        Y      = self._last_cluster_spectra_y   # raw (unstandardised)
        k      = self._cluster_k_spin.value()

        # Get x-axis from first spectrum (filtered to cluster range)
        sp0    = self.spectra[0]
        x_full = np.asarray(sp0.get('original_x_scale', sp0['x_scale']),
                             dtype=float)
        inc = [] if self._cluster_is_exclude else self._cluster_ranges
        exc = self._cluster_ranges if self._cluster_is_exclude else []
        mgr = self.controller.manager
        x_cl, _ = mgr._apply_range_filter(x_full,
                                           np.zeros_like(x_full),
                                           None, None, inc, exc)

        # Compute per-cluster mean spectra
        avgs = {}
        counts = {}
        for ci in range(k):
            mask = labels == ci
            counts[ci] = int(mask.sum())
            if counts[ci] > 0:
                avgs[ci] = Y[mask].mean(axis=0)

        # --- small dialog ------------------------------------------------
        dlg = QDialog(self)
        dlg.setWindowTitle("Cluster average spectra")
        dlg.setMinimumWidth(620)
        dlg.setMinimumHeight(420)
        root = QVBoxLayout(dlg)

        # Plot
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
        fig = Figure(figsize=(6, 3), tight_layout=True)
        ax  = fig.add_subplot(111)
        cmap_tab = plt.cm.get_cmap('tab10', k)
        for ci in range(k):
            if ci in avgs:
                col = cmap_tab(ci)
                ax.plot(x_cl, avgs[ci],
                        color=col, linewidth=1.2,
                        label=f"C{ci}  (n={counts[ci]})")
        ax.set_xlabel("x", fontsize=8)
        ax.set_ylabel("Mean intensity", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.legend(fontsize=7, loc='best')
        ax.set_title("Mean spectrum per cluster", fontsize=9)
        canvas = FigureCanvasQTAgg(fig)
        canvas.setMinimumHeight(220)
        root.addWidget(canvas)

        # Export button
        btn_export = QPushButton(
            "Export cluster averages to main spectrum list")
        btn_export.setToolTip(
            "Adds one average spectrum per cluster to the main list,\n"
            "labelled 'Cluster_0_avg', 'Cluster_1_avg', etc.")

        def _do_export():
            import copy as _copy
            new_spectra = []
            for ci in range(k):
                if ci not in avgs:
                    continue
                lbl = f"Cluster_{ci}_avg"
                new_spectra.append({
                    'x_scale': x_cl.copy(),
                    'y_scale': avgs[ci].copy(),
                    'label':   lbl,
                    'metadata': {
                        'source': f'Cluster {ci} average from 2D Map',
                        'n_members': counts[ci],
                    },
                })
            n = self.controller.send_spectra_to_main_list(
                new_spectra, label_prefix="Cluster_avg", source_spectra=self.spectra)
            QMessageBox.information(
                dlg, "Done",
                f"{n} cluster average spectra added to the main list.")

        btn_export.clicked.connect(_do_export)
        root.addWidget(btn_export)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        root.addWidget(btns)
        dlg.exec_()

    def _configure_ranges(self):
        """Open spectral range dialog for the main map ranges."""
        self._btn_configure_ranges.setEnabled(False)
        try:
            self._configure_ranges_inner()
        finally:
            QTimer.singleShot(300, lambda: self._btn_configure_ranges.setEnabled(True))

    def _configure_ranges_inner(self):
        """Open the simple band range dialog for the current mode's range."""
        try:
            from src.views.dialogs.visualization_analysis.spectral_range_dialog \
                import SpectralRangeDialog
            band_label = self._btn_configure_ranges.text().replace("…", "").strip()
            cur_ranges, cur_is_exclude = self._active_range_state()
            # Colour matches the range band shown in the spectrum panel
            if self._radio_svd.isChecked():
                band_color = '#E65100'     # orange — matches SVD twin axis
            elif self._radio_cluster.isChecked():
                band_color = '#6A1B9A'     # purple
            else:
                band_color = '#1565C0'     # blue (intensity)
            dlg = SpectralRangeDialog(
                parent=self,
                all_spectra=self.spectra,
                current_ranges=list(cur_ranges),
                is_exclude=cur_is_exclude,
                band_label=band_label,
                band_color=band_color,
            )
            if dlg.exec_() == QDialog.Accepted:
                s = dlg.get_settings()
                if s is not None:
                    self._set_active_range_state(s['ranges'], s['is_exclude'])
                    self._x_min = None
                    self._x_max = None
                    self._update_ranges_summary()
                    if not self._radio_svd.isChecked():
                        self._compute_map()
                    else:
                        self._invalidate_map()
                        # Clear spectrum panel — must press Update Map
                        self._spectrum_title_label.setText(
                            "SVD range changed — press 'Update Map' to recompute")
                        self._spectrum_canvas.ax.cla()
                        self._spectrum_canvas.draw_idle()
        except Exception as exc:
            logger.error("Map2DDialog: range dialog failed: %s", exc,
                         exc_info=True)
            QMessageBox.warning(self, "Error",
                                f"Could not open range dialog:\n{exc}")

    def _configure_arith_band(self, band='b'):
        """Open the simple band range dialog for Band A or Band B."""
        btn = self._btn_arith_range_a if band == 'a' else self._btn_arith_range_b
        btn.setEnabled(False)
        try:
            self._configure_arith_band_inner(band)
        finally:
            _btn = btn
            QTimer.singleShot(300, lambda: _btn.setEnabled(True))

    def _configure_arith_band_inner(self, band):
        # Band A uses flat state (_arith_a_ranges/_arith_a_is_exclude),
        # Band B uses dict state (_arith_b)
        if band == 'a':
            cur_ranges    = self._arith_a_ranges
            cur_is_excl   = self._arith_a_is_exclude
        else:
            cur_ranges    = self._arith_b['ranges']
            cur_is_excl   = self._arith_b['is_exclude']
        try:
            from src.views.dialogs.visualization_analysis.spectral_range_dialog \
                import SpectralRangeDialog
            dlg = SpectralRangeDialog(
                parent=self,
                all_spectra=self.spectra,
                current_ranges=list(cur_ranges),
                is_exclude=cur_is_excl,
                band_label=f"Band {'A' if band == 'a' else 'B'}",
                band_color='#1565C0' if band == 'a' else '#C62828',
            )
            if dlg.exec_() == QDialog.Accepted:
                s = dlg.get_settings()
                if s is not None:
                    if band == 'a':
                        self._arith_a_ranges     = s['ranges']
                        self._arith_a_is_exclude = s['is_exclude']
                    else:
                        self._arith_b['ranges']     = s['ranges']
                        self._arith_b['is_exclude'] = s['is_exclude']
                        self._arith_b['x_min']      = None
                        self._arith_b['x_max']      = None
                    self._update_arith_band_label(band)
                    self._compute_map()
        except Exception as exc:
            logger.error("Arithmetic band config failed: %s", exc,
                         exc_info=True)
            QMessageBox.warning(self, "Error", str(exc))

    def _update_arith_band_label(self, band):
        if band == 'a':
            ranges     = self._arith_a_ranges
            is_exclude = self._arith_a_is_exclude
            lbl        = self._arith_range_a_summary
            prefix     = "A: "
        else:
            ranges     = self._arith_b['ranges']
            is_exclude = self._arith_b['is_exclude']
            lbl        = self._arith_range_b_label
            prefix     = "B: "
        if ranges:
            mode  = "Excl" if is_exclude else "Incl"
            pairs = ", ".join(f"[{s:.0f}–{e:.0f}]" for s, e in ranges)
            lbl.setText(f"{prefix}{mode}: {pairs}")
            color = "#1565C0" if band == 'a' else "#C62828"
            lbl.setStyleSheet(f"font-size:8pt; color:{color};")
        else:
            lbl.setText(f"{prefix}full spectrum")
            lbl.setStyleSheet("font-size:8pt; color:#444;")

    def _update_ranges_summary(self):
        ranges, is_exclude = self._active_range_state()
        if ranges:
            mode  = "Exclude" if is_exclude else "Include"
            pairs = ", ".join(f"[{s:.1f}–{e:.1f}]" for s, e in ranges)
            self._ranges_summary_label.setText(f"{mode}: {pairs}")
            self._ranges_summary_label.setStyleSheet(
                "font-size:8pt; color:#1A237E;")
        else:
            self._ranges_summary_label.setText("No range — full spectrum used")
            self._ranges_summary_label.setStyleSheet(
                "font-size:8pt; color:#555;")

    # ── Map computation ─────────────────────────────────────────────────

    def _compute_map(self):
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()

        if not self.controller.validate_dimensions(
                self.n_spectra, n_rows, n_cols):
            QMessageBox.warning(
                self, "Invalid Dimensions",
                f"Rows × Cols must equal the number of spectra.\n"
                f"{n_rows} × {n_cols} = {n_rows * n_cols}  ≠  "
                f"{self.n_spectra}")
            return

        inc = [] if self._is_exclude else self._ranges
        exc = self._ranges if self._is_exclude else []

        if self._radio_intensity.isChecked():
            metric   = self._metric_combo.currentText()
            x_val    = (self._x_val_spin.value()
                        if metric == "Intensity at x" else None)
            map_data = self.controller.compute_intensity_map(
                self.spectra, n_rows, n_cols,
                metric=metric,
                x_min=self._x_min, x_max=self._x_max,
                include_ranges=inc, exclude_ranges=exc,
                x_val=x_val,
            )
            if map_data is None:
                QMessageBox.critical(self, "Error",
                                     "Failed to compute intensity map.")
                return
            self._last_map_data = map_data
            title = f"{metric} map  ({n_rows} × {n_cols})"
            self._map_canvas.update_map(
                map_data,
                cmap=self._cmap_combo.currentText(),
                interpolation=self._interp_combo.currentText(),
                title=title,
                equal_aspect=self._equal_aspect_cb.isChecked(),
            )
            # Reset spectrum panel to range preview
            self._show_range_spectrum_in_panel()
            self._on_map_computed()

        elif self._radio_arith.isChecked():
            op      = self._arith_op_combo.currentText()
            metric  = self._metric_combo.currentText()
            # Band A uses its own independent range state
            inc_a   = [] if self._arith_a_is_exclude else self._arith_a_ranges
            exc_a   = self._arith_a_ranges if self._arith_a_is_exclude else []
            sb      = self._arith_b
            inc_b   = [] if sb['is_exclude'] else sb['ranges']
            exc_b   = sb['ranges'] if sb['is_exclude'] else []
            x_val_a = self._x_val_spin.value()  if metric == "Intensity at x" else None
            x_val_b = self._x_val2_spin.value() if metric == "Intensity at x" else None
            map_data = self.controller.compute_arithmetic_map(
                self.spectra, n_rows, n_cols,
                metric_a=metric, metric_b=metric,
                x_min_a=self._x_min,  x_max_a=self._x_max,
                include_ranges_a=inc_a, exclude_ranges_a=exc_a,
                x_val_a=x_val_a,
                x_min_b=sb['x_min'], x_max_b=sb['x_max'],
                include_ranges_b=inc_b, exclude_ranges_b=exc_b,
                x_val_b=x_val_b,
                operation=op,
            )
            if map_data is None:
                QMessageBox.critical(self, "Error",
                                     "Failed to compute arithmetic map.\n"
                                     "Check that both bands have valid ranges.")
                return
            self._last_map_data = map_data
            title = f"Arithmetic {op}  ({n_rows} × {n_cols})"
            self._map_canvas.update_map(
                map_data,
                cmap=self._cmap_combo.currentText(),
                interpolation=self._interp_combo.currentText(),
                title=title,
                equal_aspect=self._equal_aspect_cb.isChecked(),
            )
            self._show_range_spectrum_in_panel()
            self._on_map_computed()

        elif self._radio_cluster.isChecked():
            self._compute_cluster_map(n_rows, n_cols)

        else:  # SVD mode
            comp_idx = max(0, self._component_combo.currentIndex())
            svd_inc = [] if self._svd_is_exclude else self._svd_ranges
            svd_exc = self._svd_ranges if self._svd_is_exclude else []
            map_data = self.controller.compute_svd_map(
                self.spectra, n_rows, n_cols,
                component_index=comp_idx,
                x_min=None, x_max=None,
                include_ranges=svd_inc, exclude_ranges=svd_exc,
            )
            if map_data is None:
                QMessageBox.critical(
                    self, "Error",
                    "Failed to compute SVD map.\n"
                    "Ensure all spectra have the same number of data points "
                    "in the selected range (use Linearization in Data Range "
                    "if needed).")
                return
            self._last_map_data = map_data
            self._svd_inverted.clear()
            self._refresh_component_combo(keep_index=comp_idx)
            self._btn_invert.setEnabled(True)
            self._btn_multi_map.setEnabled(True)
            self._btn_diagnostics.setEnabled(True)
            ev_arr = self.controller.get_explained_variance()
            ev     = (ev_arr[comp_idx]
                      if ev_arr is not None and comp_idx < len(ev_arr)
                      else 0.0)
            title  = (f"SVD coeff. map – component {comp_idx + 1}  "
                      f"(EV={ev:.2f}%)  ({n_rows} × {n_cols})")
            self._map_canvas.update_map(
                map_data,
                cmap=self._cmap_combo.currentText(),
                interpolation=self._interp_combo.currentText(),
                title=title,
                equal_aspect=self._equal_aspect_cb.isChecked(),
            )
            self._update_subspectrum_in_panel(comp_idx)
            self._on_map_computed()

        self._map_canvas.setFocus()

    # ── SVD component combo ─────────────────────────────────────────────

    def _refresh_component_combo(self, keep_index=0):
        """Repopulate the component dropdown after computing SVD."""
        n      = self.controller.get_n_svd_components()
        ev_arr = self.controller.get_explained_variance()
        mgr    = self.controller.manager
        mode   = self._comp_label_combo.currentText()

        # Pre-compute residual errors if needed (only once per refresh)
        re_arr = None
        if mode == "Residual error":
            adapter = _SVDDiagAdapter(self.controller)
            re_arr  = adapter.calculate_residual_errors()

        self._component_combo.blockSignals(True)
        self._component_combo.clear()
        for i in range(n):
            if mode == "Singular value σ":
                sv  = mgr._s[i] if (mgr._s is not None and i < len(mgr._s)) else 0.0
                lbl = f"C{i + 1}  (σ={sv:.4g})"
            elif mode == "Residual error":
                re  = (re_arr[i] if re_arr is not None and i < len(re_arr)
                       else 0.0)
                lbl = f"C{i + 1}  (RE={re:.4g})"
            else:  # "Explained var.(%)"
                ev  = (ev_arr[i]
                       if ev_arr is not None and i < len(ev_arr) else 0.0)
                lbl = f"C{i + 1}  (EV={ev:.3f}%)"
            self._component_combo.addItem(lbl)
        idx = min(keep_index, max(0, n - 1))
        self._component_combo.setCurrentIndex(idx)
        self._component_combo.blockSignals(False)

    def _refresh_component_combo_labels(self):
        """Called when the user switches EV% ↔ σ label selector."""
        if self.controller.get_n_svd_components() == 0:
            return
        current = self._component_combo.currentIndex()
        self._refresh_component_combo(keep_index=max(0, current))

    def _on_component_changed(self, index):
        """Switch displayed component without recomputing SVD."""
        if index < 0 or self.controller.get_n_svd_components() == 0:
            return
        coeffs = self.controller.get_coefficients(index)
        if coeffs is None:
            return
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()
        if not self.controller.validate_dimensions(
                self.n_spectra, n_rows, n_cols):
            return
        try:
            map_data = coeffs.reshape(n_rows, n_cols)
        except ValueError:
            return

        self._last_map_data = map_data
        ev_arr = self.controller.get_explained_variance()
        ev     = (ev_arr[index]
                  if ev_arr is not None and index < len(ev_arr) else 0.0)
        title  = (f"SVD coeff. map – component {index + 1}  "
                  f"(EV={ev:.2f}%)  ({n_rows} × {n_cols})")
        self._map_canvas.update_map(
            map_data,
            cmap=self._cmap_combo.currentText(),
            interpolation=self._interp_combo.currentText(),
            title=title,
            equal_aspect=self._equal_aspect_cb.isChecked(),
        )

        # If a pixel was clicked, refresh using its spectrum; otherwise show reference.
        if self._last_clicked_pixel is not None:
            row, col = self._last_clicked_pixel
            sp_idx = row * n_cols + col
            if 0 <= sp_idx < self.n_spectra:
                self._update_subspectrum_in_panel(
                    index, clicked_sp=self.spectra[sp_idx])
                return
        self._update_subspectrum_in_panel(index)

    def _invert_component(self):
        """Flip sign of U[:,k] and Vt[k,:] then redraw."""
        index = self._component_combo.currentIndex()
        if index < 0:
            return
        mgr = self.controller.manager
        if mgr._U is None or index >= mgr._U.shape[1]:
            return
        mgr._U[:, index]  *= -1
        mgr._Vt[index, :] *= -1
        if index in self._svd_inverted:
            self._svd_inverted.discard(index)
        else:
            self._svd_inverted.add(index)

        # Redraw map
        self._on_component_changed(index)

        # Refresh spectrum panel for clicked pixel (or reference if none clicked)
        if self._last_clicked_pixel is not None and self._radio_svd.isChecked():
            row, col = self._last_clicked_pixel
            n_rows = self._rows_spin.value()
            n_cols = self._cols_spin.value()
            sp_idx = row * n_cols + col
            if 0 <= sp_idx < self.n_spectra:
                self._update_subspectrum_in_panel(
                    index, clicked_sp=self.spectra[sp_idx])
            else:
                self._update_subspectrum_in_panel(index)

    def _show_diagnostics(self):
        """Open SVDDiagnosticsDialog reused from svd_analysis_dialog."""
        if self.controller.get_n_svd_components() == 0:
            QMessageBox.information(self, "No SVD",
                                    "Compute an SVD map first.")
            return
        try:
            from src.views.dialogs.visualization_analysis.svd_analysis_dialog \
                import SVDDiagnosticsDialog
            adapter = _SVDDiagAdapter(self.controller)
            dlg     = SVDDiagnosticsDialog(parent=self, controller=adapter)
            dlg.show()
        except Exception as exc:
            logger.error("Map2DDialog: diagnostics failed: %s", exc,
                         exc_info=True)
            QMessageBox.warning(self, "Error",
                                f"Could not open diagnostics:\n{exc}")

    def _show_multi_map(self):
        """Open the multi-component map grid window."""
        if self.controller.get_n_svd_components() == 0:
            QMessageBox.information(self, "No SVD",
                                    "Compute an SVD map first.")
            return
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()
        if not self.controller.validate_dimensions(
                self.n_spectra, n_rows, n_cols):
            QMessageBox.warning(self, "Invalid Dimensions",
                                "Set valid map dimensions first.")
            return
        dlg = _MultiMapDialog(
            parent=self,
            controller=self.controller,
            n_rows=n_rows,
            n_cols=n_cols,
            cmap=self._cmap_combo.currentText(),
            label_mode=self._comp_label_combo.currentText(),
        )
        dlg.exec_()

    # ── Display options ─────────────────────────────────────────────────

    def _on_clim_auto_changed(self, state):
        """Toggle manual colorbar range spinboxes."""
        manual = not bool(state)
        self._clim_min_spin.setEnabled(manual)
        self._clim_max_spin.setEnabled(manual)
        if self._last_map_data is not None:
            self._apply_clim()

    def _on_clim_manual_changed(self):
        if self._last_map_data is None or self._clim_auto_cb.isChecked():
            return
        self._apply_clim()

    def _apply_clim(self):
        """Apply colorbar range — either auto (full range) or percentile clip.
        Skipped for cluster maps which use a fixed discrete colormap."""
        if self._map_canvas._im is None or self._last_map_data is None:
            return
        if self._radio_cluster.isChecked():
            return  # cluster maps use fixed discrete norm, clim not applicable
        valid = self._last_map_data[np.isfinite(self._last_map_data)]
        if valid.size == 0:
            return
        if self._clim_auto_cb.isChecked():
            vmin = float(valid.min())
            vmax = float(valid.max())
        else:
            lo_pct = self._clim_min_spin.value()
            hi_pct = self._clim_max_spin.value()
            if lo_pct >= hi_pct:
                return   # invalid range, skip
            vmin = float(np.percentile(valid, lo_pct))
            vmax = float(np.percentile(valid, hi_pct))
        self._map_canvas._im.set_clim(vmin, vmax)
        if self._map_canvas._cbar_ax is not None:
            self._map_canvas._cbar_ax.cla()
            self._map_canvas.fig.colorbar(
                self._map_canvas._im, cax=self._map_canvas._cbar_ax)
        self._map_canvas.draw_idle()

    def _on_cmap_interp_changed(self):
        if self._last_map_data is None:
            return
        if self._radio_cluster.isChecked() and self._last_cluster_labels is not None:
            # Cluster map uses fixed discrete colormap — just redraw with stored labels
            n_rows = self._rows_spin.value()
            n_cols = self._cols_spin.value()
            k      = self._cluster_k_spin.value()
            map_data = self._last_cluster_labels.reshape(n_rows, n_cols)
            self._draw_cluster_map(map_data, k, n_rows, n_cols)
        else:
            self._map_canvas.update_cmap_interp(
                self._cmap_combo.currentText(),
                self._interp_combo.currentText(),
                equal_aspect=self._equal_aspect_cb.isChecked(),
            )

    def _on_aspect_changed(self):
        if self._last_map_data is None:
            return
        if self._radio_cluster.isChecked() and self._last_cluster_labels is not None:
            n_rows = self._rows_spin.value()
            n_cols = self._cols_spin.value()
            k      = self._cluster_k_spin.value()
            map_data = self._last_cluster_labels.reshape(n_rows, n_cols)
            self._draw_cluster_map(map_data, k, n_rows, n_cols)
        else:
            self._map_canvas.update_cmap_interp(
                self._cmap_combo.currentText(),
                self._interp_combo.currentText(),
                equal_aspect=self._equal_aspect_cb.isChecked(),
            )

    def _on_map_computed(self):
        """Called after every successful map computation to enable feature buttons
        and seed the colorbar range spinboxes with the data's actual min/max."""
        self._act_export_map.setEnabled(True)
        self._act_add_roi.setEnabled(True)
        self._act_add_ellipse_roi.setEnabled(True)
        self._act_paint_roi.setEnabled(True)
        self._act_line_roi.setEnabled(True)
        self._act_clear_roi.setEnabled(True)
        self._act_remove_roi.setEnabled(True)
        self._act_roi_mode.setEnabled(True)
        self._act_save_session.setEnabled(True)
        if self._last_map_data is not None:
            valid = self._last_map_data[np.isfinite(self._last_map_data)]
            if valid.size == 0:
                # All-NaN map — warn the user rather than crashing
                metric = self._metric_combo.currentText()
                if metric == "Intensity at x":
                    x_val = self._x_val_spin.value()
                    QMessageBox.warning(
                        self, "No valid map data",
                        f"All pixels returned NaN for '{metric}' at x = {x_val:.2f}.\n\n"
                        f"The x-value is likely outside the spectral range of your data.\n"
                        f"Check the x-axis limits and adjust the x-value spinbox.")
                else:
                    QMessageBox.warning(
                        self, "No valid map data",
                        f"All pixels returned NaN for metric '{metric}'.\n"
                        f"Check the spectral range configuration.")
                self._last_map_data = None
                return
            # Enable hover tooltip
            self._map_canvas.enable_hover(
                self._last_map_data,
                self.spectra,
                self._cols_spin.value(),
            )

    def _show_right_panel_menu(self, pos):
        """Context menu (right-click on map or spectrum panel) to show/hide
        the entire right control column."""
        from PyQt5.QtWidgets import QMenu
        menu   = QMenu(self)
        sizes  = self._outer_splitter.sizes()
        hidden = sizes[1] == 0
        action = menu.addAction("Show controls panel" if hidden
                                else "Hide controls panel")
        chosen = menu.exec_(self.sender().mapToGlobal(pos))
        if chosen == action:
            self._set_right_panel_visible(hidden)  # hidden→show, shown→hide

    def _set_right_panel_visible(self, visible):
        """Collapse or restore the entire right control column."""
        total = sum(self._outer_splitter.sizes())
        if visible:
            self._outer_splitter.setSizes([int(total * 0.62), int(total * 0.38)])
        else:
            self._outer_splitter.setSizes([total, 0])

    # kept as alias so existing internal calls still work
    def _set_spectrum_panel_visible(self, visible):
        """Show or collapse the spectrum sub-panel inside the right splitter."""
        if visible:
            sizes = self._right_splitter.sizes()
            total = sum(sizes)
            self._right_splitter.setSizes([int(total * 0.58), int(total * 0.42)])
        else:
            sizes = self._right_splitter.sizes()
            total = sum(sizes)
            self._right_splitter.setSizes([total, 0])

    # ── Interactive click ───────────────────────────────────────────────

    def _toggle_line_roi(self):
        """Toggle line profile mode on/off."""
        if self._last_map_data is None:
            return
        if self._line_roi_active:
            self._cancel_line_roi()
        else:
            self._deactivate_all_tools()   # mutual exclusion
            self._line_roi_active = True
            self._line_p1 = None
            self._act_line_roi.setText("Cancel ROI line profile")
            self._click_info_label.setText(
                "Line mode: click the START point on the map.")

    def _cancel_line_roi(self):
        self._line_roi_active = False
        self._line_p1 = None
        self._act_line_roi.setText("Add ROI line profile…")
        self._click_info_label.setText("Click a pixel to inspect its spectrum.")

    @staticmethod
    def _bresenham(r0, c0, r1, c1):
        """Return list of (row, col) pixel coordinates along the line from
        (r0,c0) to (r1,c1) using Bresenham's algorithm."""
        pixels = []
        dr = abs(r1 - r0); dc = abs(c1 - c0)
        sr = 1 if r0 < r1 else -1
        sc = 1 if c0 < c1 else -1
        err = dr - dc
        r, c = r0, c0
        while True:
            pixels.append((r, c))
            if r == r1 and c == c1:
                break
            e2 = 2 * err
            if e2 > -dc:
                err -= dc; r += sr
            if e2 <  dr:
                err += dr; c += sc
        return pixels

    def _on_map_click(self, event):
        """Dispatch map clicks to line-profile mode or spectrum inspection."""
        if event.inaxes is not self._map_canvas.ax:
            return
        if event.xdata is None or event.ydata is None:
            return

        # ── Line profile mode ──────────────────────────────────────────
        if self._line_roi_active:
            col = int(round(event.xdata))
            row = int(round(event.ydata))
            n_rows = self._rows_spin.value()
            n_cols = self._cols_spin.value()
            col = max(0, min(col, n_cols - 1))
            row = max(0, min(row, n_rows - 1))

            if self._line_p1 is None:
                self._line_p1 = (row, col)
                self._map_canvas.mark_pixel(row, col)
                self._act_line_roi.setText("Cancel line profile")
                self._click_info_label.setText(
                    f"Line mode: P1 set at row={row}, col={col}.  "
                    f"Now click the END point.")
            else:
                r0, c0 = self._line_p1
                r1, c1 = row, col
                pixels = self._bresenham(r0, c0, r1, c1)

                new_spectra, new_labels = [], []
                for r, c in pixels:
                    idx = r * n_cols + c
                    if idx < self.n_spectra:
                        new_spectra.append(self.spectra[idx])
                        new_labels.append(
                            self.spectra[idx].get('label', f'[{r},{c}]'))

                if new_spectra:
                    import matplotlib.lines as mlines
                    line_artist = mlines.Line2D(
                        [c0, c1], [r0, r1],
                        color='white', linewidth=1.8,
                        linestyle='-', marker='o',
                        markersize=4, zorder=6,
                    )
                    self._map_canvas.ax.add_line(line_artist)
                    self._map_canvas.draw_idle()
                    self._roi_regions.append({
                        'type':    'line',
                        'bounds':  (r0, r1, c0, c1),
                        'labels':  new_labels,
                        'spectra': new_spectra,
                        'patch':   line_artist,
                    })
                    self._update_roi_count()
                    self._click_info_label.setText(
                        f"Line: {len(new_spectra)} spectra  "
                        f"({r0},{c0})→({r1},{c1}).  "
                        f"Click again for another line or Cancel.")
                else:
                    self._click_info_label.setText("No spectra on that line.")

                self._line_p1 = None
                self._act_line_roi.setText("Cancel line profile")
            return

        # ── Normal spectrum inspection ─────────────────────────────────
        if self._last_map_data is None:
            return
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()
        if not self.controller.validate_dimensions(
                self.n_spectra, n_rows, n_cols):
            return

        col = int(round(event.xdata))
        row = int(round(event.ydata))
        if not (0 <= row < n_rows and 0 <= col < n_cols):
            return

        # Spectrum index in the flat list
        sp_idx = row * n_cols + col
        if sp_idx >= self.n_spectra:
            return

        self._map_canvas.mark_pixel(row, col)
        self._last_clicked_pixel = (row, col)

        sp    = self.spectra[sp_idx]
        label = sp.get('label', f'Spectrum {sp_idx + 1}')
        map_val = self._last_map_data[row, col]

        self._click_info_label.setText(
            f"Row {row}, Col {col}  →  spectrum: {label}  "
            f"(map value: {map_val:.5g})")

        if self._right_splitter.sizes()[1] == 0:
            return

        x = np.asarray(sp.get('original_x_scale', sp['x_scale']), dtype=float)
        y = np.asarray(sp.get('original_y_scale', sp['y_scale']), dtype=float)

        if self._radio_svd.isChecked():
            comp_idx = max(0, self._component_combo.currentIndex())
            self._update_subspectrum_in_panel(comp_idx, clicked_sp=sp)
        elif self._radio_cluster.isChecked():
            cluster_id = int(round(map_val))
            self._spectrum_title_label.setText(
                f"{label}  [Cluster {cluster_id}]")
            self._spectrum_canvas.update_spectrum(
                x, y,
                title=f"{label}  (Cluster {cluster_id})",
                xlabel="Wavenumber / x",
                ylabel="Intensity",
                color='#1565C0',
            )
            self._draw_range_bands(x)
        else:
            mode = self._metric_combo.currentText()
            self._spectrum_title_label.setText(
                f"{label}  [{mode} = {map_val:.4g}]")
            self._spectrum_canvas.update_spectrum(
                x, y,
                title=f"{label}  ({mode} = {map_val:.4g})",
                xlabel="Wavenumber / x",
                ylabel="Intensity",
                color='#1565C0',
                ranges=self._ranges,
                is_exclude=self._is_exclude,
                x_min=self._x_min,
                x_max=self._x_max,
            )
            self._draw_range_bands(x)
        self._set_spectrum_panel_visible(True)

    def _clear_twin_axis(self):
        """Remove the SVD twin-axis overlay from the spectrum canvas."""
        if hasattr(self._spectrum_canvas, '_twin_ax') and \
                self._spectrum_canvas._twin_ax is not None:
            try:
                self._spectrum_canvas._twin_ax.remove()
            except Exception:
                pass
            self._spectrum_canvas._twin_ax = None
            self._spectrum_canvas.draw_idle()

    def _on_show_svd_changed(self):
        """Toggle SVD subspectrum overlay instantly."""
        if self._show_svd_cb.isChecked():
            if self._radio_svd.isChecked() and self._last_clicked_pixel is not None:
                self._draw_twin_subspectrum()
        else:
            self._clear_twin_axis()

    def _draw_twin_subspectrum(self):
        """Add/refresh the twin-axis subspectrum overlay — only if checkbox is on."""
        if not self._show_svd_cb.isChecked():
            self._clear_twin_axis()
            return
        comp_idx = self._component_combo.currentIndex()
        sx, sy = self.controller.get_subspectrum(comp_idx)
        if sx is None or sy is None:
            return
        ax = self._spectrum_canvas.ax
        # Remove previous twin cleanly
        if hasattr(self._spectrum_canvas, '_twin_ax') and \
                self._spectrum_canvas._twin_ax is not None:
            try:
                self._spectrum_canvas._twin_ax.remove()
            except Exception:
                pass
            self._spectrum_canvas._twin_ax = None
        twin = ax.twinx()
        twin.plot(sx, sy, color='#E65100', linewidth=0.9,
                  linestyle='--', alpha=0.8)
        twin.set_ylabel("U amplitude", fontsize=7, color='#E65100')
        twin.tick_params(axis='y', labelcolor='#E65100', labelsize=6)
        self._spectrum_canvas._twin_ax = twin
        self._spectrum_canvas.fig.tight_layout()
        self._spectrum_canvas.draw_idle()

    # ── Spectrum / subspectrum panel helpers ────────────────────────────

    def _show_range_spectrum_in_panel(self):
        """After compute or mode switch: show first spectrum with range band shading."""
        if self._right_splitter.sizes()[1] == 0 or not self.spectra:
            return
        # Clear any SVD twin axis from a previous mode
        self._clear_twin_axis()

        sp    = self.spectra[0]
        x     = np.asarray(sp.get('original_x_scale', sp['x_scale']), dtype=float)
        y     = np.asarray(sp.get('original_y_scale', sp['y_scale']), dtype=float)
        label = sp.get('label', 'Spectrum 1')

        if self._radio_cluster.isChecked():
            k = self._cluster_k_spin.value()
            method = self._cluster_method_combo.currentText()
            title_plot = f"Cluster preview: {label}  [k={k}, {method}]"
            panel_title = f"Click a pixel to see its spectrum and cluster assignment"
        elif self._radio_svd.isChecked():
            title_plot  = f"SVD range preview: {label}"
            panel_title = f"Click a pixel — showing: {label}"
        else:
            metric      = self._metric_combo.currentText()
            title_plot  = f"Range preview: {label}  [{metric}]"
            panel_title = f"Click a pixel — showing: {label}"

        self._spectrum_title_label.setText(panel_title)
        self._spectrum_canvas.update_spectrum(x, y, title=title_plot)
        self._draw_range_bands(x)
        self._set_spectrum_panel_visible(True)

    def _draw_range_bands(self, x=None):
        """Overlay shaded band region(s) on the spectrum canvas.

        Always removes existing band patches first so unchecking the checkbox
        correctly clears them. Vertical edge lines are intentionally omitted —
        the shaded span is sufficient and lines caused y-axis rescaling.
        """
        ax = self._spectrum_canvas.ax

        # Always remove existing band patches first (handles the uncheck case)
        for patch in list(ax.patches):
            if getattr(patch, '_range_band', False):
                patch.remove()

        # Skip if unchecked. In SVD mode, only draw when "Full spectrum" is checked.
        if not self._show_bands_cb.isChecked():
            self._spectrum_canvas.draw_idle()
            return
        if self._radio_svd.isChecked():
            if not self._svd_full_range_cb.isChecked():
                self._spectrum_canvas.draw_idle()
                return

        if x is None or len(x) == 0:
            self._spectrum_canvas.draw_idle()
            return

        x_full_min, x_full_max = float(x.min()), float(x.max())

        def _merge_ranges(ranges):
            """Merge overlapping/adjacent ranges into their union."""
            if not ranges:
                return []
            s = sorted(ranges, key=lambda r: r[0])
            m = [list(s[0])]
            for lo, hi in s[1:]:
                if lo <= m[-1][1]:
                    m[-1][1] = max(m[-1][1], hi)
                else:
                    m.append([lo, hi])
            return m

        def _draw_band(x_min, x_max, ranges, is_exclude, color, alpha=0.15):
            lo = x_min if x_min is not None else x_full_min
            hi = x_max if x_max is not None else x_full_max
            lo = max(lo, x_full_min)
            hi = min(hi, x_full_max)
            if lo >= hi:
                return
            if ranges:
                if not is_exclude:
                    # Include: shade only the specified sub-ranges
                    for (r0, r1) in ranges:
                        r0c, r1c = max(r0, lo), min(r1, hi)
                        if r0c < r1c:
                            span = ax.axvspan(r0c, r1c, alpha=alpha,
                                              color=color, linewidth=0,
                                              zorder=0)
                            span._range_band = True
                else:
                    # Exclude: shade the full range, then use hatched overlay
                    # on excluded sub-ranges to mark them as removed.
                    # Draw base shade across the kept regions by shading full
                    # range then marking excluded zones with dense hatching.
                    span = ax.axvspan(lo, hi, alpha=alpha,
                                      color=color, linewidth=0, zorder=0)
                    span._range_band = True
                    for (r0, r1) in ranges:
                        r0c, r1c = max(r0, lo), min(r1, hi)
                        if r0c < r1c:
                            # Mark excluded zone with hatching over white
                            excl = ax.axvspan(r0c, r1c, alpha=0.55,
                                              facecolor='white',
                                              edgecolor=color,
                                              hatch='////',
                                              linewidth=0, zorder=1)
                            excl._range_band = True
            else:
                # No sub-ranges: shade entire clip region
                span = ax.axvspan(lo, hi, alpha=alpha,
                                  color=color, linewidth=0, zorder=0)
                span._range_band = True

        if self._radio_intensity.isChecked():
            _draw_band(self._x_min, self._x_max,
                       _merge_ranges(self._ranges), self._is_exclude,
                       color='#1565C0')
        elif self._radio_arith.isChecked():
            _draw_band(None, None,
                       _merge_ranges(self._arith_a_ranges),
                       self._arith_a_is_exclude,
                       color='#1565C0', alpha=0.22)
            sb = self._arith_b
            _draw_band(sb['x_min'], sb['x_max'],
                       _merge_ranges(sb['ranges']),
                       sb['is_exclude'],
                       color='#C62828', alpha=0.22)
        elif self._radio_cluster.isChecked():
            _draw_band(None, None,
                       _merge_ranges(self._cluster_ranges),
                       self._cluster_is_exclude,
                       color='#6A1B9A', alpha=0.15)
        elif self._radio_svd.isChecked():
            _draw_band(None, None,
                       _merge_ranges(self._svd_ranges),
                       self._svd_is_exclude,
                       color='#E65100', alpha=0.15)

        self._spectrum_canvas.draw_idle()

    def _on_show_bands_changed(self):
        """Redraw range bands when checkbox is toggled."""
        if not self.spectra:
            return
        # Get x from first spectrum as reference
        sp = self.spectra[0]
        x  = np.asarray(sp.get('original_x_scale', sp['x_scale']), dtype=float)
        self._draw_range_bands(x)

    def _on_svd_display_changed(self):
        """Toggle between full-spectrum and SVD-range-only display."""
        if self._radio_svd.isChecked():
            comp_idx = max(0, self._component_combo.currentIndex())
            self._update_subspectrum_in_panel(comp_idx)

    def _update_subspectrum_in_panel(self, comp_idx, clicked_sp=None):
        """Show spectrum in lower-right panel for SVD mode.

        clicked_sp : spectrum dict to display (defaults to self.spectra[0])
        """
        if self._right_splitter.sizes()[1] == 0 or not self.spectra:
            return

        sp     = clicked_sp if clicked_sp is not None else self.spectra[0]
        x_full = np.asarray(sp.get('original_x_scale', sp['x_scale']),
                             dtype=float)
        y_full = np.asarray(sp.get('original_y_scale', sp['y_scale']),
                             dtype=float)

        ev_arr = self.controller.get_explained_variance()
        ev     = (ev_arr[comp_idx]
                  if ev_arr is not None and comp_idx < len(ev_arr) else 0.0)
        title  = f"SVD component {comp_idx + 1}  (EV = {ev:.3f}%)"
        self._spectrum_title_label.setText(
            f"{title}  — click a pixel to see its spectrum")

        show_full = self._svd_full_range_cb.isChecked()

        if show_full:
            # Full spectrum + shaded SVD band region + twin-axis component
            self._spectrum_canvas.update_spectrum(
                x_full, y_full,
                title=title,
                xlabel="Wavenumber / x",
                ylabel="Intensity",
                color='#1565C0',
            )
            # Shade the SVD band region using _draw_range_bands which
            # correctly reads self._svd_ranges / self._svd_is_exclude
            self._draw_range_bands(x_full)
        else:
            # Clipped spectrum — x-axis matches SVD component exactly
            mgr = self.controller.manager
            if mgr._svd_x_axis is not None:
                x_svd = mgr._svd_x_axis
                # Interpolate the full spectrum onto the SVD x-axis
                if x_full[0] > x_full[-1]:
                    y_clipped = np.interp(x_svd, x_full[::-1], y_full[::-1])
                else:
                    y_clipped = np.interp(x_svd, x_full, y_full)
            else:
                x_svd, y_clipped = x_full, y_full
            self._spectrum_canvas.update_spectrum(
                x_svd, y_clipped,
                title=title,
                xlabel="Wavenumber / x",
                ylabel="Intensity",
                color='#1565C0',
            )

        # Overlay SVD component if checkbox is checked
        if self._show_svd_cb.isChecked():
            self._draw_twin_subspectrum()

        self._set_spectrum_panel_visible(True)

    # ── Feature 1: Export map ───────────────────────────────────────────

    def _export_map(self):
        """Export the current map array as CSV or Excel."""
        if self._last_map_data is None:
            QMessageBox.information(self, "No map", "Compute a map first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Map", "",
            "CSV file (*.csv);;Excel file (*.xlsx)"
        )
        if not path:
            return
        try:
            if path.endswith('.xlsx'):
                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Map"
                for row in self._last_map_data.tolist():
                    ws.append(row)
                wb.save(path)
            else:
                if not path.endswith('.csv'):
                    path += '.csv'
                np.savetxt(path, self._last_map_data, delimiter=',')
            QMessageBox.information(self, "Export", f"Map saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    # ── Feature 2: ROI selection ────────────────────────────────────────

    def _update_roi_count(self):
        """Update 'View ROI spectra' with count and mode, keep cancel buttons clean."""
        n_drawn = len(self._all_roi_labels())
        if self._roi_exclude_mode:
            n_view = self.n_spectra - n_drawn
            mode_str = f"excl. {n_drawn}"
        else:
            n_view = n_drawn
            mode_str = f"sel. {n_drawn}"

        if n_drawn > 0:
            if self._roi_exclude_mode:
                label = f"{n_view} | excl. {n_drawn}"
            else:
                label = str(n_view)
            self._act_view_roi.setText(f"View ROI spectra…  ({label})")
            self._act_view_roi.setEnabled(True)
        else:
            self._act_view_roi.setText("View ROI spectra…  (0)")
            self._act_view_roi.setEnabled(False)

        # Cancel buttons show only their action — no counts
        n_regions = len(self._roi_regions)
        if n_regions == 0:
            self._act_add_roi.setText("Add ROI rectangle…")
        # Stats available when ≥2 regions and a map exists
        self._act_roi_stats.setEnabled(
            n_regions >= 2 and self._last_map_data is not None)

    def _all_roi_labels(self):
        """Return deduplicated flat label list across all regions."""
        seen, out = set(), []
        for reg in self._roi_regions:
            for lbl in reg['labels']:
                if lbl not in seen:
                    seen.add(lbl)
                    out.append(lbl)
        return out

    def _all_roi_spectra(self):
        """Return deduplicated flat spectra list across all regions."""
        seen, out = set(), []
        for reg in self._roi_regions:
            for sp in reg['spectra']:
                lbl = sp.get('label', '')
                if lbl not in seen:
                    seen.add(lbl)
                    out.append(sp)
        return out

    def _toggle_roi(self):
        if self._last_map_data is None:
            return
        if self._roi_active:
            self._deactivate_roi()
        else:
            self._activate_roi()
    def _deactivate_all_tools(self):
        """Cancel all ROI drawing tools — ensures strict mutual exclusion."""
        if self._roi_active:
            self._deactivate_roi()
        if self._ellipse_roi_active:
            self._deactivate_ellipse_roi()
        if self._lasso_selector is not None:
            try:
                self._lasso_selector.set_active(False)
            except Exception:
                pass
            self._lasso_selector = None
            self._act_paint_roi.setText("Paint ROI lasso…")
        if self._line_roi_active:
            self._cancel_line_roi()

    def _activate_roi(self):
        self._remove_roi_active = False
        self._act_remove_roi.setText("View / Remove ROI regions…")
        self._deactivate_all_tools()   # mutual exclusion
        from matplotlib.widgets import RectangleSelector
        self._roi_active = True
        self._act_add_roi.setText("Cancel ROI rectangle")
        self._roi_selector = RectangleSelector(
            self._map_canvas.ax,
            self._on_roi_selected,
            useblit=True, button=[1],
            minspanx=0, minspany=0,
            spancoords='data', interactive=True,
        )
        self._last_rect_region = None
        self._last_rect_patch  = None
        self._map_canvas.draw_idle()

    def _deactivate_roi(self):
        self._roi_active = False
        self._act_add_roi.setText("Add ROI rectangle…")
        if self._roi_selector is not None:
            self._roi_selector.set_active(False)
            self._roi_selector = None
        self._map_canvas.draw_idle()
        self._update_roi_count()

    def _toggle_ellipse_roi(self):
        if self._last_map_data is None:
            return
        if self._ellipse_roi_active:
            self._deactivate_ellipse_roi()
        else:
            self._activate_ellipse_roi()

    def _activate_ellipse_roi(self):
        self._remove_roi_active = False
        self._act_remove_roi.setText("View / Remove ROI regions…")
        self._deactivate_all_tools()
        from matplotlib.widgets import EllipseSelector
        self._ellipse_roi_active = True
        self._act_add_ellipse_roi.setText("Cancel ROI ellipse")
        self._ellipse_selector = EllipseSelector(
            self._map_canvas.ax,
            self._on_ellipse_selected,
            useblit=True, button=[1],
            minspanx=0, minspany=0,
            spancoords='data', interactive=True,
        )
        self._last_ellipse_region = None
        self._last_ellipse_patch  = None
        self._map_canvas.draw_idle()

    def _deactivate_ellipse_roi(self):
        self._ellipse_roi_active = False
        self._act_add_ellipse_roi.setText("Add ROI ellipse…")
        if self._ellipse_selector is not None:
            try:
                self._ellipse_selector.set_active(False)
            except Exception:
                pass
            self._ellipse_selector = None
        self._map_canvas.draw_idle()
        self._update_roi_count()

    def _on_ellipse_selected(self, eclick, erelease):
        """Called both for a brand-new ellipse AND for resizing/moving an
        already-drawn one via its handles after release — same reasoning
        as _on_roi_selected's is_adjustment check above."""
        import numpy as np
        is_adjustment = (
            self._last_ellipse_region is not None
            and getattr(self._ellipse_selector, '_active_handle', None) is not None
        )

        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()

        # Ellipse centre and semi-axes in data (pixel) coordinates
        x0, x1 = sorted([eclick.xdata, erelease.xdata])
        y0, y1 = sorted([eclick.ydata,  erelease.ydata])
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        a = (x1 - x0) / 2   # semi-axis along x (columns)
        b = (y1 - y0) / 2   # semi-axis along y (rows)

        if a < 0.5 or b < 0.5:
            return   # too small

        new_spectra, new_labels = [], []
        for r in range(n_rows):
            for c in range(n_cols):
                # Point-in-ellipse test
                if a > 0 and b > 0:
                    if ((c - cx) / a) ** 2 + ((r - cy) / b) ** 2 <= 1.0:
                        idx = r * n_cols + c
                        if idx < self.n_spectra:
                            new_spectra.append(self.spectra[idx])
                            new_labels.append(
                                self.spectra[idx].get('label', f'[{r},{c}]'))

        if not new_spectra:
            return

        if is_adjustment:
            region = self._last_ellipse_region
            region['bounds'] = (y0, y1, x0, x1)
            region['cx'], region['cy'], region['a'], region['b'] = cx, cy, a, b
            region['labels']  = new_labels
            region['spectra'] = new_spectra
            patch = self._last_ellipse_patch
            patch.set_center((cx, cy))
            patch.set_width(2 * a)
            patch.set_height(2 * b)
            self._map_canvas.draw_idle()
            self._update_roi_count()
            return

        # Draw ellipse patch on the map
        from matplotlib.patches import Ellipse
        ell = Ellipse(
            (cx, cy), width=2 * a, height=2 * b,
            linewidth=1.5, edgecolor='white', facecolor='none',
            linestyle='--', zorder=5,
        )
        self._map_canvas.ax.add_patch(ell)
        self._map_canvas.draw_idle()

        new_region = {
            'type':    'ellipse',
            'bounds':  (y0, y1, x0, x1),   # (row_min, row_max, col_min, col_max)
            'cx': cx, 'cy': cy, 'a': a, 'b': b,
            'labels':  new_labels,
            'spectra': new_spectra,
            'patch':   ell,
        }
        self._roi_regions.append(new_region)
        self._last_ellipse_region = new_region
        self._last_ellipse_patch  = ell

        self._act_add_ellipse_roi.setText("Cancel ROI ellipse")
        self._update_roi_count()

    def _toggle_lasso(self):
        """Toggle lasso selector on/off — mirrors _toggle_roi pattern."""
        if self._last_map_data is None:
            return
        if self._lasso_selector is not None:
            # Cancel lasso
            try:
                self._lasso_selector.set_active(False)
            except Exception:
                pass
            self._lasso_selector = None
            self._act_paint_roi.setText("Paint ROI lasso…")
            self._map_canvas.draw_idle()
            self._update_roi_count()
        else:
            self._activate_lasso()

    def _on_roi_selected(self, eclick, erelease):
        """Called both when the user finishes drawing a brand-new ROI
        rectangle AND when they resize/move an already-drawn one via its
        handles after release (matplotlib re-fires this same callback on
        every handle-drag release, not only on a fresh drag — see
        _active_handle check below).
        """
        # matplotlib sets _active_handle to a corner/edge code or 'C'
        # (move) when this release event came from dragging a handle on
        # the ALREADY-drawn rectangle; it's None when it came from
        # starting a brand-new drag elsewhere. This is exactly the
        # distinction we need: adjust the same region vs. create a new
        # one. (Private attribute, but stable across recent matplotlib
        # versions; falls back to "treat as new" if it's ever absent.)
        is_adjustment = (
            self._last_rect_region is not None
            and getattr(self._roi_selector, '_active_handle', None) is not None
        )

        col0 = int(round(min(eclick.xdata, erelease.xdata)))
        col1 = int(round(max(eclick.xdata, erelease.xdata)))
        row0 = int(round(min(eclick.ydata, erelease.ydata)))
        row1 = int(round(max(eclick.ydata, erelease.ydata)))
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()
        col0 = max(0, min(col0, n_cols - 1))
        col1 = max(0, min(col1, n_cols - 1))
        row0 = max(0, min(row0, n_rows - 1))
        row1 = max(0, min(row1, n_rows - 1))

        new_spectra, new_labels = [], []
        for r in range(row0, row1 + 1):
            for c in range(col0, col1 + 1):
                idx = r * n_cols + c
                if idx < self.n_spectra:
                    new_spectra.append(self.spectra[idx])
                    new_labels.append(self.spectra[idx].get('label', f'[{r},{c}]'))

        if not new_spectra:
            return

        if is_adjustment:
            # Update the region and its patch in place — this is what
            # makes "grab a handle to fix up the rectangle after
            # releasing" behave as an edit, instead of silently piling
            # up an extra near-duplicate region every time it's nudged.
            region = self._last_rect_region
            region['bounds']  = (row0, row1, col0, col1)
            region['labels']  = new_labels
            region['spectra'] = new_spectra
            patch = self._last_rect_patch
            patch.set_xy((col0 - 0.5, row0 - 0.5))
            patch.set_width(col1 - col0 + 1)
            patch.set_height(row1 - row0 + 1)
            self._map_canvas.draw_idle()
            self._update_roi_count()
            return

        from matplotlib.patches import Rectangle
        rect = Rectangle(
            (col0 - 0.5, row0 - 0.5),
            col1 - col0 + 1, row1 - row0 + 1,
            linewidth=1.5, edgecolor='white', facecolor='none',
            linestyle='--', zorder=5,
        )
        self._map_canvas.ax.add_patch(rect)
        self._map_canvas.draw_idle()

        new_region = {
            'type': 'rect',
            'bounds': (row0, row1, col0, col1),
            'labels': new_labels,
            'spectra': new_spectra,
            'patch': rect,
        }
        self._roi_regions.append(new_region)
        self._last_rect_region = new_region
        self._last_rect_patch  = rect

        self._act_add_roi.setText("Cancel ROI rectangle…")
        self._update_roi_count()

    def _activate_lasso(self):
        """Freehand lasso selector for non-rectangular ROI."""
        if self._last_map_data is None:
            return
        self._remove_roi_active = False
        self._act_remove_roi.setText("View / Remove ROI regions…")
        self._deactivate_all_tools()   # mutual exclusion
        from matplotlib.widgets import LassoSelector
        self._act_paint_roi.setText("Cancel lasso")
        self._lasso_selector = LassoSelector(
            self._map_canvas.ax,
            self._on_lasso_selected,
            useblit=True, button=[1],
        )
        self._map_canvas.draw_idle()

    def _on_lasso_selected(self, verts):
        """Collect pixels inside the lasso path. Lasso stays active for more selections."""
        from matplotlib.path import Path
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()
        path   = Path(verts)

        new_spectra, new_labels = [], []
        for r in range(n_rows):
            for c in range(n_cols):
                if path.contains_point((c, r)):
                    idx = r * n_cols + c
                    if idx < self.n_spectra:
                        new_spectra.append(self.spectra[idx])
                        new_labels.append(
                            self.spectra[idx].get('label', f'[{r},{c}]'))

        if not new_spectra:
            return

        from matplotlib.patches import PathPatch
        from matplotlib.path import Path as MPath
        closed_verts = list(verts) + [verts[0]]
        lasso_patch = PathPatch(
            MPath(closed_verts),
            linewidth=1.5, edgecolor='white', facecolor='none',
            linestyle='--', zorder=5,
        )
        self._map_canvas.ax.add_patch(lasso_patch)
        self._map_canvas.draw_idle()

        self._roi_regions.append({
            'type': 'lasso',
            'bounds': None,
            'labels': new_labels,
            'spectra': new_spectra,
            'patch': lasso_patch,
        })

        self._update_roi_count()

    def _activate_remove_roi(self):
        """Show dialog with multi-select list; remove all selected regions at once."""
        if not self._roi_regions:
            QMessageBox.information(self, "No ROIs", "No ROI regions to remove.")
            return
        dlg = _RemoveROIDialog(
            parent=self,
            regions=self._roi_regions,
            map_canvas=self._map_canvas,
        )
        if dlg.exec_() == QDialog.Accepted and dlg.selected_indices:
            # Remove in reverse order so indices stay valid
            for idx in sorted(dlg.selected_indices, reverse=True):
                self._remove_roi_by_index(idx)
            # Restore remaining patches
            for reg in self._roi_regions:
                try:
                    reg['patch'].set_edgecolor('white')
                    reg['patch'].set_linewidth(1.5)
                except Exception:
                    pass
            self._map_canvas.draw_idle()
            # If no regions remain, reset add-roi button text (Point 3)
            if not self._roi_regions:
                self._act_add_roi.setText("Add ROI rectangle…")

    def _remove_roi_by_index(self, hit_idx):
        """Remove the ROI region at hit_idx."""
        reg = self._roi_regions[hit_idx]
        try:
            reg['patch'].remove()
        except Exception:
            pass
        del self._roi_regions[hit_idx]
        self._click_info_label.setText(
            f"Region removed. {len(self._all_roi_labels())} spectra in selection.")
        self._update_roi_count()
        # If no regions remain, use full clear to ensure canvas is clean
        if not self._roi_regions:
            self._act_add_roi.setText("Add ROI rectangle…")
            self._clear_all_rois()
        else:
            self._map_canvas.draw()

    def _clear_all_rois(self):
        """Remove all ROI regions and reset."""
        if self._lasso_selector is not None:
            try:
                self._lasso_selector.set_active(False)
            except Exception:
                pass
            self._lasso_selector = None
            self._act_paint_roi.setText("Paint ROI lasso…")

        if self._line_roi_active:
            self._cancel_line_roi()

        if self._roi_selector is not None:
            try:
                self._roi_selector.set_active(False)
                self._roi_selector.set_visible(False)
            except Exception:
                pass
            self._roi_selector = None
        self._roi_active = False

        if self._ellipse_selector is not None:
            try:
                self._ellipse_selector.set_active(False)
            except Exception:
                pass
            self._ellipse_selector = None
        self._ellipse_roi_active = False
        self._act_add_ellipse_roi.setText("Add ROI ellipse…")

        # Remove all patches
        for reg in self._roi_regions:
            try:
                reg['patch'].remove()
            except Exception:
                pass
        self._roi_regions.clear()

        self._act_add_roi.setText("Add ROI rectangle…")
        self._act_remove_roi.setEnabled(False)

        # Full redraw to clear ghost handles
        self._map_canvas.ax.cla()
        # Reset tooltip — ax.cla() destroys the annotation artist
        self._map_canvas._tooltip = None

        if self._last_map_data is not None:
            from mpl_toolkits.axes_grid1 import make_axes_locatable
            aspect = 'equal' if self._equal_aspect_cb.isChecked() else 'auto'
            self._map_canvas._im = self._map_canvas.ax.imshow(
                self._last_map_data,
                cmap=self._cmap_combo.currentText(),
                interpolation=self._interp_combo.currentText(),
                origin='upper', aspect=aspect,
            )
            if self._map_canvas._cbar_ax is not None:
                try:
                    self._map_canvas._cbar_ax.remove()
                except Exception:
                    pass
            divider = make_axes_locatable(self._map_canvas.ax)
            self._map_canvas._cbar_ax = divider.append_axes("right", size="5%", pad=0.05)
            self._map_canvas.fig.colorbar(
                self._map_canvas._im, cax=self._map_canvas._cbar_ax)
            if not self._clim_auto_cb.isChecked():
                self._map_canvas._im.set_clim(
                    self._clim_min_spin.value(), self._clim_max_spin.value())
            self._map_canvas.ax.set_xlabel("Column index", fontsize=8)
            self._map_canvas.ax.set_ylabel("Row index", fontsize=8)
            # Re-enable hover tooltip on the fresh axes
            self._map_canvas.enable_hover(
                self._last_map_data, self.spectra, self._cols_spin.value())
        self._map_canvas.draw_idle()
        self._update_roi_count()
        # Re-enable ROI drawing tools — the map is still there
        if self._last_map_data is not None:
            self._act_add_roi.setEnabled(True)
            self._act_paint_roi.setEnabled(True)
            self._act_line_roi.setEnabled(True)
            self._act_remove_roi.setEnabled(True)

    def _toggle_roi_mode(self):
        """Toggle between Include and Exclude ROI mode."""
        self._roi_exclude_mode = not self._roi_exclude_mode
        if self._roi_exclude_mode:
            self._act_roi_mode.setText("Mode: Exclude  ●")
        else:
            self._act_roi_mode.setText("Mode: Include  ◯")
        # Update all counts immediately to reflect the new mode
        self._update_roi_count()

    def _show_roi_statistics(self):
        """Show a comparison table of map value statistics per ROI region."""
        if self._last_map_data is None or len(self._roi_regions) < 2:
            return

        n_cols   = self._cols_spin.value()
        map_data = self._last_map_data
        metric   = (self._metric_combo.currentText()
                    if self._radio_intensity.isChecked() else
                    self._arith_op_combo.currentText()
                    if self._radio_arith.isChecked() else
                    "Map value")

        # Compute stats per region
        # Build label → pixel index map once
        label_to_idx = {sp.get('label', ''): i
                        for i, sp in enumerate(self.spectra)}

        rows = []
        for i, reg in enumerate(self._roi_regions):
            vals = []
            for lbl in reg['labels']:
                idx = label_to_idx.get(lbl)
                if idx is None:
                    continue
                r, c = divmod(idx, n_cols)
                if 0 <= r < map_data.shape[0] and \
                   0 <= c < map_data.shape[1]:
                    v = map_data[r, c]
                    if np.isfinite(v):
                        vals.append(float(v))
            if vals:
                vals = np.asarray(vals)
                rows.append({
                    'Region': f"Region {i+1} ({reg['type']})",
                    'N pixels': len(vals),
                    'Mean': float(vals.mean()),
                    'Std': float(vals.std()),
                    'Min': float(vals.min()),
                    'Median': float(np.median(vals)),
                    'Max': float(vals.max()),
                })

        if not rows:
            QMessageBox.information(self, "No data",
                                    "No valid map values found in the ROI regions.")
            return

        # Build dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("ROI comparison statistics")
        dlg.setMinimumWidth(640)
        lay = QVBoxLayout(dlg)

        lay.addWidget(QLabel(
            f"<b>Metric:</b> {metric}  |  "
            f"<b>{len(rows)}</b> regions"))

        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        cols = ['Region', 'N pixels', 'Mean', 'Std', 'Min', 'Median', 'Max']
        tbl = QTableWidget(len(rows), len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c_, col in enumerate(cols[1:], 1):
            tbl.horizontalHeader().setSectionResizeMode(c_, QHeaderView.ResizeToContents)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setAlternatingRowColors(True)

        for r_, row in enumerate(rows):
            for c_, col in enumerate(cols):
                val = row[col]
                text = val if isinstance(val, str) else (
                    str(int(val)) if col == 'N pixels' else f"{val:.4g}")
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignLeft | Qt.AlignVCenter if c_ == 0
                    else Qt.AlignRight | Qt.AlignVCenter)
                tbl.setItem(r_, c_, item)

        lay.addWidget(tbl)

        # Export button
        btn_row = QHBoxLayout()
        btn_export = QPushButton("Export as CSV…")
        def _export():
            from PyQt5.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(
                dlg, "Save statistics", "roi_statistics.csv",
                "CSV files (*.csv)")
            if path:
                import csv
                with open(path, 'w', newline='') as f:
                    w = csv.DictWriter(f, fieldnames=cols)
                    w.writeheader()
                    w.writerows(rows)
        btn_export.clicked.connect(_export)
        btn_row.addWidget(btn_export)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        dlg.exec_()

    def _open_roi_viewer(self):
        """Open the ROI spectra viewer."""
        if not self._roi_regions:
            QMessageBox.information(self, "ROI", "No spectra selected yet.\n"
                                    "Draw rectangles or lasso regions on the map first.")
            return

        all_spectra = self._all_roi_spectra()
        all_labels  = self._all_roi_labels()

        if self._roi_exclude_mode:
            incl_set    = set(all_labels)
            view_spectra = [sp for sp in self.spectra
                            if sp.get('label', '') not in incl_set]
            view_labels  = [sp.get('label', '') for sp in view_spectra]
            mode_str = "Exclude"
        else:
            view_spectra = all_spectra
            view_labels  = all_labels
            mode_str = "Include"

        if not view_spectra:
            QMessageBox.information(self, "ROI",
                                    "No spectra remain after applying the exclusion.")
            return

        n_rects  = sum(1 for r in self._roi_regions if r['type'] == 'rect')
        n_lassos = sum(1 for r in self._roi_regions if r['type'] == 'lasso')
        n_lines  = sum(1 for r in self._roi_regions if r['type'] == 'line')
        parts = []
        if n_rects:  parts.append(f"{n_rects} rect{'s' if n_rects > 1 else ''}")
        if n_lassos: parts.append(f"{n_lassos} lasso{'s' if n_lassos > 1 else ''}")
        if n_lines:  parts.append(f"{n_lines} line{'s' if n_lines > 1 else ''}")
        region_str = ", ".join(parts) if parts else "no regions"
        title = f"ROI [{mode_str}]  {region_str}  ({len(view_spectra)} spectra)"

        # Collect line profile data for EVERY line region (not just the
        # first one drawn), tagged with a 1-based line_id, so the viewer
        # can tell multiple line profiles apart instead of silently
        # dropping every line after the first. Only meaningful in
        # Include mode, where view_spectra/view_labels line up with
        # view_labels below.
        line_map_values = None
        line_positions  = None
        line_ids        = None
        line_regions    = [r for r in self._roi_regions if r['type'] == 'line']
        if line_regions and not self._roi_exclude_mode:
            n_cols = self._cols_spin.value()
            # label -> (line_id, position along that line, map value).
            # First-seen wins if a spectrum happens to sit on more than
            # one line, matching the dedup rule _all_roi_spectra() uses.
            line_data = {}
            for line_id, lr in enumerate(line_regions, start=1):
                r0, r1, c0, c1 = lr['bounds']
                pixels = self._bresenham(r0, c0, r1, c1)
                for pos, (r, c) in enumerate(pixels):
                    idx = r * n_cols + c
                    if idx < self.n_spectra and self._last_map_data is not None:
                        lbl = self.spectra[idx].get('label', f'[{r},{c}]')
                        if lbl not in line_data:
                            line_data[lbl] = (
                                line_id, pos, float(self._last_map_data[r, c]))
            if line_data:
                line_ids        = [line_data[lbl][0] if lbl in line_data else None
                                    for lbl in view_labels]
                line_positions  = [line_data[lbl][1] if lbl in line_data else None
                                    for lbl in view_labels]
                line_map_values = [line_data[lbl][2] if lbl in line_data else None
                                    for lbl in view_labels]

        dlg = _ROISpectraDialog(
            parent=self,
            spectra=view_spectra,
            labels=view_labels,
            ranges=self._ranges,
            is_exclude=self._is_exclude,
            x_min=self._x_min,
            x_max=self._x_max,
            title=title,
            line_map_values=line_map_values,
            line_positions=line_positions,
            line_ids=line_ids,
            map2d_controller=self.controller,
        )
        dlg.exec_()

    # ── Feature 5: Save / load session ─────────────────────────────────

    def _save_session(self):
        import json
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Session", "", "JSON session (*.json)")
        if not path:
            return
        if not path.endswith('.json'):
            path += '.json'
        mgr = self.controller.manager
        session = {
            'n_rows':        self._rows_spin.value(),
            'n_cols':        self._cols_spin.value(),
            'map_mode':      'svd' if self._radio_svd.isChecked() else 'intensity',
            'metric':        self._metric_combo.currentText(),
            'cmap':          self._cmap_combo.currentText(),
            'interpolation': self._interp_combo.currentText(),
            'equal_aspect':  self._equal_aspect_cb.isChecked(),
            'clim_auto':     self._clim_auto_cb.isChecked(),
            'clim_min':      self._clim_min_spin.value(),
            'clim_max':      self._clim_max_spin.value(),
            'label_mode':    (self._comp_label_combo.currentText()
                              if hasattr(self, '_comp_label_combo') else ''),
            'svd_component': self._component_combo.currentIndex(),
            'ranges':        self._ranges,
            'is_exclude':    self._is_exclude,
            'x_min':         self._x_min,
            'x_max':         self._x_max,
            'svd_U':  mgr._U.tolist()  if mgr._U  is not None else None,
            'svd_s':  mgr._s.tolist()  if mgr._s  is not None else None,
            'svd_Vt': mgr._Vt.tolist() if mgr._Vt is not None else None,
            'svd_x':  (mgr._svd_x_axis.tolist()
                       if mgr._svd_x_axis is not None else None),
        }
        try:
            with open(path, 'w') as f:
                json.dump(session, f)
            QMessageBox.information(self, "Session saved",
                                    f"Session saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    def _load_session(self):
        import json
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Session", "", "JSON session (*.json)")
        if not path:
            return
        try:
            with open(path) as f:
                s = json.load(f)
            # Dimensions
            self._rows_spin.blockSignals(True)
            self._cols_spin.blockSignals(True)
            self._rows_spin.setValue(s.get('n_rows', 1))
            self._cols_spin.setValue(s.get('n_cols', 1))
            self._rows_spin.blockSignals(False)
            self._cols_spin.blockSignals(False)
            self._update_dimension_hint()
            # Ranges
            self._ranges     = s.get('ranges', [])
            self._is_exclude = s.get('is_exclude', False)
            self._x_min      = s.get('x_min')
            self._x_max      = s.get('x_max')
            self._update_ranges_summary()
            # Display
            if s.get('cmap') in self.COLORMAPS:
                self._cmap_combo.setCurrentText(s['cmap'])
            if s.get('interpolation') in self.INTERPOLATIONS:
                self._interp_combo.setCurrentText(s['interpolation'])
            self._equal_aspect_cb.setChecked(s.get('equal_aspect', False))
            self._clim_auto_cb.setChecked(s.get('clim_auto', True))
            if not s.get('clim_auto', True):
                self._clim_min_spin.setValue(s.get('clim_min', 0))
                self._clim_max_spin.setValue(s.get('clim_max', 1))
            # Map mode
            if s.get('map_mode') == 'svd':
                self._radio_svd.setChecked(True)
            else:
                self._radio_intensity.setChecked(True)
            self._on_mode_changed(None)
            idx = self._metric_combo.findText(s.get('metric', 'Integral'))
            if idx >= 0:
                self._metric_combo.setCurrentIndex(idx)
            # Restore SVD arrays
            mgr = self.controller.manager
            if s.get('svd_U') is not None:
                mgr._U   = np.array(s['svd_U'])
                mgr._s   = np.array(s['svd_s'])
                mgr._Vt  = np.array(s['svd_Vt'])
                mgr._svd_x_axis = (np.array(s['svd_x'])
                                   if s.get('svd_x') else None)
                mgr._explained_variance = (
                    mgr._s ** 2 / np.sum(mgr._s ** 2) * 100)
                if s.get('map_mode') == 'svd':
                    self._refresh_component_combo(
                        keep_index=s.get('svd_component', 0))
                    self._btn_invert.setEnabled(True)
                    self._btn_multi_map.setEnabled(True)
                    self._btn_diagnostics.setEnabled(True)
            self._invalidate_map()
            QMessageBox.information(
                self, "Session loaded",
                "Settings restored. Click Update Map to recompute.")
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))

    # ------------------------------------------------------------------ #
    # QDialog cleanup                                                      #
    # ------------------------------------------------------------------ #

    def closeEvent(self, event):
        try:
            plt.close(self._map_canvas.fig)
            plt.close(self._spectrum_canvas.fig)
        except Exception:
            pass
        super().closeEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
# ROI spectra viewer
# ══════════════════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════════════════
# Multi-component map grid window
# ══════════════════════════════════════════════════════════════════════════════

class _MultiMapDialog(QDialog):
    """
    Grid window showing selected SVD component maps side-by-side with
    their corresponding subspectra.

    Layout  (matplotlib figure, n_selected rows × 2 cols)
    ──────────────────────────────────────────────────────
    Row k:  [ 2D map of component k ]  [ subspectrum U[:,k] ]

    Left control panel
    ──────────────────
    • Scrollable list of components, each row has:
        [☑ Show]  [↕ Invert]  Component N  (EV=x.xxx%)
    • Clear selection button
    • Colormap selector
    • Plot button + Close button
    """

    def __init__(self, parent, controller, n_rows, n_cols,
                 cmap='viridis', label_mode='Explained var.(%)'):
        super().__init__(parent)
        self.controller = controller
        self.n_rows     = n_rows
        self.n_cols     = n_cols
        self.cmap       = cmap
        self.label_mode = label_mode
        self.n_total    = controller.get_n_svd_components()

        self.setWindowTitle("SVD Multi-Component Map")
        self.setModal(True)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.resize(1200, 700)

        # Debounce timer so resize doesn't trigger a redraw on every pixel
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._plot_all)

        self._build_ui()
        # Tick first 4 components (no draw yet — showEvent handles that)
        for i in range(min(4, self.n_total)):
            self._show_checks[i].blockSignals(True)
            self._show_checks[i].setChecked(True)
            self._show_checks[i].blockSignals(False)

    def showEvent(self, event):
        """Draw after the window is fully laid out and sized."""
        super().showEvent(event)
        # Use a zero-delay timer so Qt finishes painting before we draw
        QTimer.singleShot(0, self._plot_all)

    def resizeEvent(self, event):
        """Debounce resize: redraw 150 ms after the user stops resizing."""
        super().resizeEvent(event)
        self._resize_timer.start(150)

    # ------------------------------------------------------------------ #

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        # ── Left control panel ────────────────────────────────────────
        ctrl = QWidget()
        ctrl.setFixedWidth(230)
        clay = QVBoxLayout(ctrl)
        clay.setSpacing(4)

        clay.addWidget(QLabel("<b>Select components to plot:</b>"))

        # Clear selection + single Invert button — same pattern as SVD analysis
        sel_row = QHBoxLayout()
        btn_none = QPushButton("Clear selection")
        btn_none.setToolTip("Uncheck all components")
        btn_none.clicked.connect(self._unselect_all)
        sel_row.addWidget(btn_none)
        self._btn_invert = QPushButton("Invert")
        self._btn_invert.setToolTip(
            "Flip the sign of the highlighted (blue) component.\n"
            "Click a row to select it, then press Invert."
        )
        self._btn_invert.clicked.connect(self._invert_highlighted)
        sel_row.addWidget(self._btn_invert)
        sel_row.addStretch()
        clay.addLayout(sel_row)

        # Scrollable component list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setSpacing(2)
        list_layout.setContentsMargins(2, 2, 2, 2)

        ev_arr = self.controller.get_explained_variance()
        # Pre-compute residual errors once if needed (avoids repeated computation)
        _re_arr = None
        if self.label_mode == "Residual error":
            _re_arr = _SVDDiagAdapter(self.controller).calculate_residual_errors()
        mgr = self.controller.manager

        self._show_checks = []
        self._row_widgets = []
        self._highlighted = 0

        for i in range(self.n_total):
            # Build label according to chosen mode
            if self.label_mode == "Singular value σ":
                sv  = (mgr._s[i] if mgr._s is not None and i < len(mgr._s) else 0.0)
                lbl_text = f"C{i + 1}  (σ={sv:.4g})"
            elif self.label_mode == "Residual error":
                re  = (_re_arr[i] if _re_arr is not None and i < len(_re_arr) else 0.0)
                lbl_text = f"C{i + 1}  (RE={re:.4g})"
            else:
                ev  = (ev_arr[i] if ev_arr is not None and i < len(ev_arr) else 0.0)
                lbl_text = f"C{i + 1}  (EV={ev:.3f}%)"

            row_w = QWidget()
            row_w.setAutoFillBackground(True)
            row_w.setCursor(Qt.PointingHandCursor)
            row = QHBoxLayout(row_w)
            row.setSpacing(4)
            row.setContentsMargins(2, 1, 2, 1)

            cb_show = QCheckBox()
            cb_show.setChecked(False)
            cb_show.setToolTip(f"Include component {i + 1} in the grid plot")
            cb_show.stateChanged.connect(self._on_selection_changed)
            row.addWidget(cb_show)
            self._show_checks.append(cb_show)

            lbl = QLabel(lbl_text)
            lbl.setStyleSheet("font-size:8pt;")
            row.addWidget(lbl, stretch=1)

            row_w.mousePressEvent = lambda _ev, idx=i: self._highlight_row(idx)
            list_layout.addWidget(row_w)
            self._row_widgets.append(row_w)

        list_layout.addStretch()
        scroll.setWidget(list_widget)
        clay.addWidget(scroll, stretch=1)

        # Highlight first row by default
        self._highlight_row(0)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        clay.addWidget(sep)

        clay.addWidget(QLabel("<b>Colormap:</b>"))
        self._cmap_combo = QComboBox()
        self._cmap_combo.addItems([
            'viridis', 'plasma', 'inferno', 'magma', 'cividis',
            'hot', 'coolwarm', 'RdBu_r', 'seismic', 'jet',
        ])
        self._cmap_combo.setCurrentText(self.cmap)
        self._cmap_combo.currentTextChanged.connect(self._plot_all)
        clay.addWidget(self._cmap_combo)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        clay.addWidget(btn_close)

        outer.addWidget(ctrl)

        # ── Right: matplotlib grid canvas + toolbar ───────────────────
        right = QWidget()
        rlay  = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)

        self._fig    = Figure(tight_layout=True)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding,
                                   QSizePolicy.Expanding)
        self._toolbar = NavigationToolbar(self._canvas, right)

        rlay.addWidget(self._toolbar)
        rlay.addWidget(self._canvas, stretch=1)
        outer.addWidget(right, stretch=1)

    # ------------------------------------------------------------------ #

    def _comp_label(self, idx):
        """Return the metric string for component idx using the chosen label_mode."""
        mgr    = self.controller.manager
        ev_arr = self.controller.get_explained_variance()
        mode   = self.label_mode

        if mode == "Singular value σ":
            sv = (mgr._s[idx] if mgr._s is not None and idx < len(mgr._s)
                  else 0.0)
            return f"C{idx + 1}  (σ={sv:.4g})"
        elif mode == "Residual error":
            adapter = _SVDDiagAdapter(self.controller)
            re_arr  = adapter.calculate_residual_errors()
            re = (re_arr[idx] if re_arr is not None and idx < len(re_arr)
                  else 0.0)
            return f"C{idx + 1}  (RE={re:.4g})"
        else:  # "Explained var.(%)"
            ev = (ev_arr[idx] if ev_arr is not None and idx < len(ev_arr)
                  else 0.0)
            return f"C{idx + 1}  (EV={ev:.3f}%)"

    def _highlight_row(self, idx):
        """Highlight the clicked row and remember it for Invert."""
        for i, rw in enumerate(self._row_widgets):
            rw.setStyleSheet(
                "QWidget { background:#D0E4F7; }" if i == idx
                else "QWidget { background:transparent; }"
            )
        self._highlighted = idx

    def _invert_highlighted(self):
        """Invert the highlighted component — same action as SVD analysis Invert."""
        idx = self._highlighted
        mgr = self.controller.manager
        if mgr._U is None or mgr._Vt is None:
            return
        if idx >= mgr._U.shape[1]:
            return
        mgr._U[:, idx]  *= -1
        mgr._Vt[idx, :] *= -1
        self._plot_all()

    def _unselect_all(self):
        for cb in self._show_checks:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._plot_all()

    def _on_selection_changed(self):
        self._plot_all()

    def _get_selected_indices(self):
        return [i for i, cb in enumerate(self._show_checks) if cb.isChecked()]

    def _plot_all(self):
        """Redraw the grid for the currently selected components."""
        indices = self._get_selected_indices()
        cmap    = self._cmap_combo.currentText()
        mgr     = self.controller.manager
        ev_arr  = self.controller.get_explained_variance()

        self._fig.clear()

        if not indices:
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5, "No components selected.\nTick one or more components on the left.",
                    ha='center', va='center', transform=ax.transAxes, fontsize=10,
                    color='#555')
            ax.set_axis_off()
            self._canvas.draw_idle()
            return

        if mgr._U is None or mgr._Vt is None:
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5, "No SVD data available",
                    ha='center', va='center', transform=ax.transAxes)
            self._canvas.draw_idle()
            return

        n = len(indices)
        # Grid: n rows × 2 cols  (map | subspectrum)
        axes = self._fig.subplots(n, 2, squeeze=False)

        # Pre-compute residual errors once if needed
        _re_arr = None
        if self.label_mode == "Residual error":
            _re_arr = _SVDDiagAdapter(self.controller).calculate_residual_errors()

        for row_k, comp_idx in enumerate(indices):
            ax_map  = axes[row_k][0]
            ax_spec = axes[row_k][1]

            u_col = mgr._U[:, comp_idx].copy()
            v_row = mgr._Vt[comp_idx, :].copy()

            # Build metric label for titles
            if self.label_mode == "Singular value σ":
                sv       = (mgr._s[comp_idx] if mgr._s is not None else 0.0)
                met_str  = f"σ={sv:.4g}"
            elif self.label_mode == "Residual error":
                re       = (_re_arr[comp_idx]
                            if _re_arr is not None and comp_idx < len(_re_arr)
                            else 0.0)
                met_str  = f"RE={re:.4g}"
            else:
                ev       = (ev_arr[comp_idx]
                            if ev_arr is not None and comp_idx < len(ev_arr)
                            else 0.0)
                met_str  = f"EV={ev:.3f}%"

            # ── Left: 2D coefficient map ──────────────────────────────
            try:
                map_data = v_row.reshape(self.n_rows, self.n_cols)
            except ValueError:
                ax_map.text(0.5, 0.5, "reshape error",
                            ha='center', va='center',
                            transform=ax_map.transAxes)
                ax_spec.set_axis_off()
                continue

            im = ax_map.imshow(map_data, cmap=cmap, aspect='auto',
                               origin='upper', interpolation='nearest')
            self._fig.colorbar(im, ax=ax_map, fraction=0.046, pad=0.04)
            ax_map.set_title(f"Map {comp_idx + 1}  ({met_str})", fontsize=8)
            ax_map.set_xlabel("Col", fontsize=7)
            ax_map.set_ylabel("Row", fontsize=7)
            ax_map.tick_params(labelsize=6)

            # ── Right: corresponding subspectrum U[:,k] ───────────────
            x_ax = mgr._svd_x_axis
            if x_ax is not None and len(x_ax) == len(u_col):
                ax_spec.plot(x_ax, u_col, linewidth=0.8, color='#E65100')
                ax_spec.set_xlabel("Wavenumber / x", fontsize=7)
            else:
                ax_spec.plot(u_col, linewidth=0.8, color='#E65100')
                ax_spec.set_xlabel("Index", fontsize=7)
            ax_spec.set_title(f"Subspectrum {comp_idx + 1}  ({met_str})",
                              fontsize=8)
            ax_spec.set_ylabel("U amplitude", fontsize=7)
            ax_spec.tick_params(labelsize=6)

        self._fig.tight_layout()
        self._canvas.draw_idle()

    # ------------------------------------------------------------------ #

    def closeEvent(self, event):
        try:
            plt.close(self._fig)
        except Exception:
            pass
        super().closeEvent(event)

