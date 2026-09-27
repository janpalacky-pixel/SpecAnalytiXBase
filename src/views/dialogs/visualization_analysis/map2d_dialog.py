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

import traceback

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QSpinBox, QDoubleSpinBox, QLabel, QPushButton, QSizePolicy,
    QSplitter, QWidget, QMessageBox, QCheckBox,
    QComboBox, QRadioButton, QButtonGroup, QFrame,
    QScrollArea, QListWidget, QListWidgetItem, QDialogButtonBox,
    QFileDialog, QAbstractSpinBox, QSlider,
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

# Same 95% default as the standalone NMF Analysis / MCR-ALS tools'
# own Bootstrap Uncertainty (_BOOTSTRAP_CONFIDENCE_LEVEL in
# nmf_dialog.py / mcr_als_dialog.py) -- kept as its own module-level
# constant here rather than importing theirs, since this dialog
# already keeps its NMF/MCR-ALS map logic independent of those
# dialogs' UI (only the underlying Manager/Controller classes are
# shared -- see Map2DManager.compute_bootstrap_uncertainty).
_MAP_BOOTSTRAP_CONFIDENCE_LEVEL = 0.95


def _disable_wheel_scrolling(root):
    """Make every spinbox/combobox/slider under root ignore mouse-wheel
    events, so scrolling over the control panel always scrolls the
    panel rather than silently changing whatever value the cursor
    happens to be sitting on (Qt's default is to respond to the wheel
    even without focus or a click) — same fix as
    melting_curve_dialog.py's _disable_wheel_scrolling."""
    for widget in root.findChildren((QAbstractSpinBox, QComboBox, QSlider)):
        widget.wheelEvent = lambda event: event.ignore()


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
        # Reference-spectra pixel markers (NMF/MCR-ALS) — {component_index:
        # (row, col)}, numbered circles kept separate from the plain
        # crosshair (see mark_pixel) since several can be shown at once.
        # update_map() clears the axes on every full redraw, so it
        # re-applies these from this stored dict rather than relying on
        # callers to remember to redraw them.
        self._ref_pixel_by_component = {}
        self._ref_marker_artists = []
        self._ref_markers_visible = True
        # Miniature spectrum preview shown while picking a reference
        # (see set_ref_picking_active) — a small floating Qt widget with
        # its own tiny matplotlib canvas, positioned next to the cursor
        # by _on_hover. Built lazily on first use.
        self._ref_picking_active = False
        # Called (with no arguments) after every full redraw that clears
        # the axes (_draw_stale/update_map) — set by the dialog to
        # _redraw_roi_patches so ROI region outlines survive a mode
        # switch or any other full redraw instead of silently vanishing
        # (their underlying data in self._roi_regions was never touched;
        # only their matplotlib artists were destroyed by ax.cla(), the
        # same class of bug as the hover-tooltip staleness above).
        self._post_redraw_hook = None
        self._mini_preview_widget = None
        self._mini_preview_ax = None
        self._mini_preview_canvas = None
        self._mini_preview_last_sp_idx = None
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
            self._hide_mini_spectrum_preview()
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
            self._hide_mini_spectrum_preview()
            return

        sp_idx = row * n_cols + col
        if sp_idx >= len(self._hover_spectra):
            return

        label   = self._hover_spectra[sp_idx].get('label', f'#{sp_idx}')
        val     = self._hover_map_data[row, col]
        text    = f"Row {row + 1}, Col {col + 1}\n{label}\nValue: {val:.4g}"

        if self._ref_picking_active:
            self._show_mini_spectrum_preview(sp_idx, event)
        else:
            self._hide_mini_spectrum_preview()

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
    # Reference-picking hover preview (see set_ref_picking_active,
    # called by the dialog whenever a "Pick on map…" button is
    # armed/disarmed).
    def set_ref_picking_active(self, active):
        self._ref_picking_active = active
        if not active:
            self._hide_mini_spectrum_preview()

    def _hide_mini_spectrum_preview(self):
        if self._mini_preview_widget is not None:
            self._mini_preview_widget.hide()
        self._mini_preview_last_sp_idx = None

    def _show_mini_spectrum_preview(self, sp_idx, event):
        if self._mini_preview_widget is None:
            self._mini_preview_widget = QWidget(self)
            self._mini_preview_widget.setFixedSize(150, 100)
            self._mini_preview_widget.setStyleSheet(
                "background-color: white; border: 1px solid #888;")
            self._mini_preview_widget.setAttribute(Qt.WA_TransparentForMouseEvents)
            v = QVBoxLayout(self._mini_preview_widget)
            v.setContentsMargins(2, 2, 2, 2)
            mini_fig = Figure(figsize=(1.5, 1.0), dpi=100)
            self._mini_preview_canvas = FigureCanvas(mini_fig)
            self._mini_preview_ax = mini_fig.add_subplot(111)
            v.addWidget(self._mini_preview_canvas)

        if sp_idx != self._mini_preview_last_sp_idx:
            self._mini_preview_last_sp_idx = sp_idx
            sp = self._hover_spectra[sp_idx]
            x  = np.asarray(sp.get('x_scale', []), dtype=float)
            y  = np.asarray(sp.get('y_scale', []), dtype=float)
            self._mini_preview_ax.clear()
            self._mini_preview_ax.plot(x, y, color='#1565C0', linewidth=1)
            self._mini_preview_ax.set_xticks([])
            self._mini_preview_ax.set_yticks([])
            self._mini_preview_ax.set_title(
                sp.get('label', f'#{sp_idx}'), fontsize=6)
            self._mini_preview_canvas.draw_idle()

        # event.x/event.y are matplotlib canvas pixel coords, y measured
        # from the BOTTOM of the canvas — flip to Qt widget coords (y
        # from the top) and nudge away from the cursor.
        qt_x = int(event.x) + 16
        qt_y = int(self.height() - event.y) + 16
        qt_x = max(0, min(qt_x, self.width() - self._mini_preview_widget.width() - 2))
        qt_y = max(0, min(qt_y, self.height() - self._mini_preview_widget.height() - 2))
        self._mini_preview_widget.move(qt_x, qt_y)
        self._mini_preview_widget.show()
        self._mini_preview_widget.raise_()

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
        if self._post_redraw_hook is not None:
            self._post_redraw_hook()
        self.draw_idle()

    def set_post_redraw_hook(self, fn):
        """Register a callable to run after every full redraw that clears
        the axes (_draw_stale/update_map), right before the final
        draw_idle(). Used by the dialog to re-attach ROI region patches
        (see the comment on self._post_redraw_hook above)."""
        self._post_redraw_hook = fn

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
        # ax.cla() removes the hover-tooltip annotation from the axes'
        # artist list without notifying us — the Python object referenced
        # by self._tooltip survives, but it is now orphaned (no longer in
        # ax.texts, .axes no longer points at this ax) and will never be
        # rendered again no matter how many times set_visible(True) is
        # called on it. Reset the reference so enable_hover() (called
        # right after every full redraw) recreates it fresh, attached to
        # the axes that will actually be drawn.
        self._tooltip = None

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
        self._draw_ref_markers()
        if self._post_redraw_hook is not None:
            self._post_redraw_hook()
        self.draw_idle()

    # ------------------------------------------------------------------
    # Reference-spectra pixel markers (set_ref_pixel/clear_ref_pixels are
    # the public API the dialog uses; _draw_ref_markers does the actual
    # matplotlib work and is also called by update_map() since a full
    # redraw (ax.cla()) would otherwise silently drop these).
    def set_ref_pixel(self, component_index, row_col):
        """row_col: (row, col) tuple, or None to clear that component's marker."""
        if row_col is None:
            self._ref_pixel_by_component.pop(component_index, None)
        else:
            self._ref_pixel_by_component[component_index] = row_col
        self._draw_ref_markers()

    def clear_ref_pixels(self):
        self._ref_pixel_by_component = {}
        self._draw_ref_markers()

    def set_ref_markers_visible(self, visible):
        self._ref_markers_visible = visible
        self._draw_ref_markers()

    def _draw_ref_markers(self):
        for art in self._ref_marker_artists:
            try:
                art.remove()
            except Exception:
                pass
        self._ref_marker_artists = []
        if self._ref_markers_visible:
            for component_index, (row, col) in self._ref_pixel_by_component.items():
                marker, = self.ax.plot(
                    col, row, 'o', markersize=13, markerfacecolor='none',
                    markeredgecolor='#FFEB3B', markeredgewidth=2.2,
                    zorder=9, clip_on=True)
                txt = self.ax.text(
                    col, row, str(component_index + 1),
                    color='#FFEB3B', fontsize=7.5, fontweight='bold',
                    ha='center', va='center', zorder=10, clip_on=True)
                self._ref_marker_artists.append(marker)
                self._ref_marker_artists.append(txt)
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
    # RGB overlay mode (see _build_rgb_panel / _compose_rgb_overlay)
    _RGB_KIND_LABELS = {'svd': 'SVD', 'pca': 'PCA', 'nmf': 'NMF', 'mcr': 'MCR-ALS'}
    _RGB_CHANNEL_NAMES = ('Red', 'Green', 'Blue')
    _RGB_CHANNEL_COLORS = ('#C62828', '#2E7D32', '#1565C0')

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
        self._pca_ranges         = []   # PCA mode — independent from SVD's own range
        self._pca_is_exclude     = False
        self._nmf_ranges         = []   # NMF mode — independent from SVD's own range
        self._nmf_is_exclude     = False
        self._mcr_ranges         = []   # MCR-ALS mode — independent from the other two
        self._mcr_is_exclude     = False
        self._cluster_ranges     = []   # Cluster mode
        self._cluster_is_exclude = False
        # Arithmetic Band B
        self._arith_b = dict(ranges=[], is_exclude=False, x_min=None, x_max=None)

        # SVD / PCA inversion tracking — separate sets, since they're
        # separate decompositions with independent sign ambiguity.
        self._svd_inverted = set()
        self._pca_inverted = set()

        # Last computed map data (for re-render without recompute)
        self._last_map_data           = None
        # RGB overlay mode: the full (n_rows, n_cols, 3) composed
        # image (for the panel's "Export as PNG…" button and for
        # showing real per-channel values on click) — kept separate
        # from _last_map_data, which in RGB mode holds a grayscale
        # mean-of-channels proxy purely so the generic map/ROI/hover
        # machinery keeps working unchanged (see the developer guide).
        self._rgb_overlay_array       = None
        # Per-kind "the cached fit no longer matches the current
        # settings" flag. Switching modes alone never sets this — only
        # a change that would actually produce a different fit does
        # (range reconfigured, NMF/MCR-ALS component count changed,
        # references changed with auto-recompute off). _on_mode_changed
        # uses this to decide whether re-entering a decomp mode can just
        # redraw the already-cached component (cheap) or must show the
        # "press Update Map" placeholder (a stale fit would otherwise
        # display silently as if it were current). Cleared right after
        # each successful fit in _compute_map.
        self._decomp_needs_refit = {'svd': False, 'pca': False,
                                     'nmf': False, 'mcr': False}
        # Which decomposition kind ('svd'/'pca') produced it, if any —
        # lets _export_map add the unit-normalized-coefficient note only
        # when it's actually relevant (not for intensity/arithmetic/cluster
        # maps, which have no such ambiguity).
        self._last_map_kind           = None
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

        # Reference-spectra anchoring (NMF/MCR-ALS): {component_index:
        # (row, col)} picked by clicking the map, plus which component
        # (if any) is currently "armed" waiting for that click.
        self._ref_pixel_by_component = {}
        self._ref_picking_component  = None

        self._build_ui()
        self._connect_signals()
        _disable_wheel_scrolling(self)

        # Convenience: MAT/WITec map imports (and similar) record each
        # pixel's map_n_rows/map_n_cols in metadata['import_parameters']
        # — every spectrum in such a map carries the same values, so
        # checking the first spectrum is enough. When present and
        # consistent with the number of spectra actually loaded here,
        # skip having to look up/enter the dimensions by hand: pre-fill
        # them and let the existing dims-changed path draw the map right
        # away (only in "fast" modes — Intensity/Arithmetic/Cluster — the
        # same as if the user had typed correct dims in manually). A
        # text-format map import (e.g. Raman_2D_map_85x55.txt) has no
        # such metadata, so this correctly falls through to the existing
        # manual Suggest… flow for those.
        detected_dims = self._detect_map_dimensions_from_metadata()
        if detected_dims is not None:
            n_rows, n_cols = detected_dims
            self._rows_spin.setValue(n_rows)
            self._cols_spin.setValue(n_cols)

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

    def _make_info_button(self, title, text):
        """Small orange '?' button — same style used throughout the rest
        of the app (e.g. the standalone NMF Analysis / MCR-ALS dialogs'
        section-header info buttons). Sized/styled to match the reference
        row's "X" clear button (24x24, no explicit font-size) rather than
        the smaller 20x20 tried earlier — that size swallowed the glyph
        entirely under the native Windows button style."""
        btn = QPushButton('?')
        btn.setFixedSize(24, 24)
        btn.setStyleSheet(
            'QPushButton { background-color:#F57C00; color:white; '
            'font-weight:bold; border:none; border-radius:4px; }'
            'QPushButton:hover { background-color:#EF6C00; }')
        btn.setToolTip('About this section')
        btn.clicked.connect(lambda: QMessageBox.information(self, title, text))
        return btn

    @staticmethod
    def _style_pick_button(btn, active):
        """Recolor/relabel a reference row's "Pick on map…" button so
        the armed (picking) state is visually obvious rather than relying
        only on its checked/sunken look, which is easy to miss."""
        if active:
            btn.setText("Click the map…")
            btn.setToolTip(
                "Picking mode is on — click a pixel on the map to use its "
                "spectrum as this component's reference, or press this "
                "button again to cancel.")
            btn.setStyleSheet(
                "QPushButton { background-color:#2E7D32; color:white; "
                "font-weight:bold; }"
                "QPushButton:hover { background-color:#1B5E20; }")
        else:
            btn.setText("Pick on map…")
            btn.setToolTip(
                "Click, then click a pixel on the map to use its spectrum "
                "as this component's reference.")
            btn.setStyleSheet("")

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
        # ROI region outlines must survive every full map redraw
        # (mode switch, Update Map, cmap/aspect change, ...) — see
        # _redraw_roi_patches for why this can't just be "leave the
        # patches alone".
        self._map_canvas.set_post_redraw_hook(self._redraw_roi_patches)
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
        self._btn_compute.setToolTip(
            "(Re)compute the map with the current settings.\n"
            "For NMF/MCR-ALS, this is a single, fast, deterministic\n"
            "fit — see \"Run N times, keep best…\" above for a slower,\n"
            "more robust alternative that tries several random\n"
            "starting points instead of just one.")
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
        self._btn_autofill.setAutoDefault(False)
        self._btn_autofill.setDefault(False)
        self._btn_autofill.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._btn_autofill.setToolTip(
            "Show all valid (rows × cols) factor pairs and auto-fill the most square option."
        )
        row.addWidget(self._btn_autofill)
        row.addStretch()
        row.addWidget(self._make_info_button(
            "About Map Dimensions",
            "Rows × Cols must equal the total number of selected spectra — "
            "spectra are placed row-by-row (C order).\n\n"
            "If every selected spectrum carries the map's own row/col size "
            "(true for MAT/WITec map imports), this is filled in "
            "automatically as soon as the dialog opens. A plain "
            "text/column-format map import doesn't carry this information, "
            "so it falls back to manual entry — type the values directly, "
            "or use Suggest… to pick from the valid (rows, cols) factor "
            "pairs of the spectrum count."))
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
        radio_row1 = QHBoxLayout()
        radio_row2 = QHBoxLayout()
        self._radio_intensity = QRadioButton("Intensity metric")
        self._radio_svd       = QRadioButton("SVD")
        self._radio_pca       = QRadioButton("PCA")
        self._radio_nmf       = QRadioButton("NMF")
        self._radio_mcr       = QRadioButton("MCR-ALS")
        self._radio_arith     = QRadioButton("Map arithmetic")
        self._radio_cluster   = QRadioButton("Cluster overlay")
        self._radio_rgb       = QRadioButton("RGB overlay")
        self._radio_intensity.setChecked(True)
        # Disabled until at least one of SVD/PCA/NMF/MCR-ALS has been
        # computed at least once — RGB overlay has nothing to combine
        # before then. Re-enabled in _update_rgb_radio_enabled(), called
        # after every successful decomposition compute.
        self._radio_rgb.setEnabled(False)
        self._radio_rgb.setToolTip(
            "Compute at least one SVD, PCA, NMF or MCR-ALS map first —\n"
            "RGB overlay combines up to three of their component maps\n"
            "into one false-color composite image.")
        self._radio_group = QButtonGroup(self)
        self._radio_group.addButton(self._radio_intensity, 0)
        self._radio_group.addButton(self._radio_svd,       1)
        self._radio_group.addButton(self._radio_arith,     2)
        self._radio_group.addButton(self._radio_cluster,   3)
        self._radio_group.addButton(self._radio_nmf,       4)
        self._radio_group.addButton(self._radio_mcr,       5)
        self._radio_group.addButton(self._radio_pca,       6)
        self._radio_group.addButton(self._radio_rgb,       7)
        radio_row1.addWidget(self._radio_intensity)
        radio_row1.addWidget(self._radio_svd)
        radio_row1.addWidget(self._radio_pca)
        radio_row1.addWidget(self._radio_nmf)
        radio_row1.addStretch()
        radio_row2.addWidget(self._radio_mcr)
        radio_row2.addWidget(self._radio_arith)
        radio_row2.addWidget(self._radio_cluster)
        radio_row2.addWidget(self._radio_rgb)
        radio_row2.addStretch()
        radio_row2.addWidget(self._make_info_button(
            "About Map Type",
            "Intensity metric: colours each pixel by a band metric (integral, "
            "mean, peak, etc.) computed on that pixel's own spectrum.\n\n"
            "SVD / PCA / NMF / MCR-ALS: four spatial decomposition modes. SVD "
            "and PCA each get every component from one fast, exact fit (PCA "
            "additionally mean-centers the data first, the standard PCA "
            "convention); NMF and MCR-ALS need the number of components "
            "chosen first, then Update Map fits and shows component 1. All "
            "four colour each pixel by one component's per-pixel score.\n\n"
            "Map arithmetic: combines two independently configured bands "
            "(A and B) pixel-wise — ratio, difference, sum or product.\n\n"
            "Cluster overlay: runs k-means directly on the map spectra and "
            "colours each pixel by its cluster assignment.\n\n"
            "RGB overlay: assign up to three already-computed SVD/PCA/NMF/"
            "MCR-ALS component maps to the Red/Green/Blue channels of one "
            "composite image — available once at least one of those has "
            "been computed."))
        lay.addLayout(radio_row1)
        lay.addLayout(radio_row2)

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
        # Only shown in Intensity metric mode (not Arithmetic, which
        # shares this same combo/panel but names its two bands
        # differently) — the metric options need more room to explain
        # than a tooltip, in particular that 'Intensity at x' is a
        # single interpolated point rather than an average over a
        # range like every other option here.
        self._metric_help_btn = self._make_info_button(
            "About the Metric options",
            "Every option here computes one scalar value per spectrum from the\npixels within the configured Band range — except 'Intensity at x',\nwhich is different (see below).\n\nIntegral: area under the range-filtered spectrum (trapezoidal rule).\nMean: average y-value over the range.\nVariance: spread of y-values within the range.\nPeak intensity: maximum y-value in the range.\nPeak position: x-value at the intensity maximum in the range.\nFWHM: full width at half maximum of the dominant peak in the range.\nBaseline-corrected integral: area above the chord connecting the\nrange endpoints.\n\nIntensity at x: linearly interpolates the full spectrum at one exact\nx-value — a single point, not an average over a range or its\nneighboring points. Because it reads only that one point, it is more\nsensitive to noise at that exact position than the range-based\nmetrics above. If you want noise averaged out, use Mean (or\nIntegral) over a narrow range centered on your feature instead.")
        metric_row.addWidget(self._metric_help_btn)
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

        # ── Decomposition sub-panel (SVD / NMF / MCR-ALS) ────────────
        # One shared panel for all three — SVD gets every component "for
        # free" from a single fast np.linalg.svd call and just needs a
        # component index afterward, but NMF and MCR-ALS are iterative
        # fits that require choosing how many components to resolve
        # BEFORE fitting, hence the extra "Components" spinner sharing
        # the Component/Label row below (hidden for SVD, which has no
        # equivalent setting).
        self._svd_panel = QWidget()
        svlay = QVBoxLayout(self._svd_panel)
        svlay.setContentsMargins(0, 0, 0, 0)
        svlay.setSpacing(4)


        # ── NMF-only fit settings: initialisation + max iterations ──
        self._nmf_settings_row_widget = QWidget()
        nmf_row = QHBoxLayout(self._nmf_settings_row_widget)
        nmf_row.setContentsMargins(0, 0, 0, 0)
        nmf_row.setSpacing(4)
        lbl_nmf_init = QLabel("Init.:")
        lbl_nmf_init.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        nmf_row.addWidget(lbl_nmf_init)
        self._nmf_init_combo = QComboBox()
        self._nmf_init_combo.addItems(['nndsvda', 'nndsvd'])
        self._nmf_init_combo.setToolTip(
            "nndsvda : NNDSVD with average fill (recommended)\n"
            "nndsvd  : NNDSVD, zeros left as zeros\n"
            "Same options as the standalone NMF Analysis tool. Ignored "
            "when 'Run N times, keep best…' is used — that always runs "
            "with random initialisation instead.")
        nmf_row.addWidget(self._nmf_init_combo)
        lbl_nmf_iter = QLabel("Max iter.:")
        lbl_nmf_iter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        nmf_row.addWidget(lbl_nmf_iter)
        self._nmf_maxiter_spin = QSpinBox()
        self._nmf_maxiter_spin.setKeyboardTracking(False)
        self._nmf_maxiter_spin.setRange(50, 5000)
        self._nmf_maxiter_spin.setSingleStep(50)
        self._nmf_maxiter_spin.setValue(500)
        self._nmf_maxiter_spin.setFixedWidth(70)
        nmf_row.addWidget(self._nmf_maxiter_spin)
        nmf_row.addStretch()
        self._nmf_settings_row_widget.setVisible(False)
        svlay.addWidget(self._nmf_settings_row_widget)

        # ── MCR-ALS-only fit settings: max iterations + constraints ──
        self._mcr_settings_widget = QWidget()
        mcr_v = QVBoxLayout(self._mcr_settings_widget)
        mcr_v.setContentsMargins(0, 0, 0, 0)
        mcr_v.setSpacing(2)
        mcr_iter_row = QHBoxLayout()
        mcr_iter_row.setSpacing(4)
        lbl_mcr_iter = QLabel("Max iter.:")
        lbl_mcr_iter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        mcr_iter_row.addWidget(lbl_mcr_iter)
        self._mcr_maxiter_spin = QSpinBox()
        self._mcr_maxiter_spin.setKeyboardTracking(False)
        self._mcr_maxiter_spin.setRange(10, 2000)
        self._mcr_maxiter_spin.setSingleStep(10)
        self._mcr_maxiter_spin.setValue(100)
        self._mcr_maxiter_spin.setFixedWidth(70)
        mcr_iter_row.addWidget(self._mcr_maxiter_spin)
        mcr_iter_row.addStretch()
        mcr_v.addLayout(mcr_iter_row)
        mcr_constraints_row = QHBoxLayout()
        mcr_constraints_row.setSpacing(6)
        self._mcr_c_nonneg_cb = QCheckBox("Non-neg. C")
        self._mcr_c_nonneg_cb.setChecked(True)
        self._mcr_c_nonneg_cb.setToolTip("Non-negative concentrations (C).")
        mcr_constraints_row.addWidget(self._mcr_c_nonneg_cb)
        self._mcr_st_nonneg_cb = QCheckBox("Non-neg. ST")
        self._mcr_st_nonneg_cb.setChecked(True)
        self._mcr_st_nonneg_cb.setToolTip("Non-negative pure spectra (ST).")
        mcr_constraints_row.addWidget(self._mcr_st_nonneg_cb)
        self._mcr_closure_cb = QCheckBox("Closure")
        self._mcr_closure_cb.setChecked(False)
        self._mcr_closure_cb.setToolTip(
            "Concentrations sum to 100% per spectrum. Only turn this on if "
            "your system genuinely has closure (total concentration "
            "constant across the map) — same caveat as the standalone "
            "MCR-ALS tool.")
        mcr_constraints_row.addWidget(self._mcr_closure_cb)
        mcr_constraints_row.addStretch()
        mcr_v.addLayout(mcr_constraints_row)
        self._mcr_settings_widget.setVisible(False)
        svlay.addWidget(self._mcr_settings_widget)

        comp_label_row = QHBoxLayout()
        comp_label_row.setSpacing(4)
        self._decomp_n_label = QLabel("Components to fit:")
        self._decomp_n_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        comp_label_row.addWidget(self._decomp_n_label)
        self._decomp_n_spin = QSpinBox()
        self._decomp_n_spin.setKeyboardTracking(False)
        self._decomp_n_spin.setRange(2, max(2, min(20, self.n_spectra)))
        self._decomp_n_spin.setValue(min(2, self._decomp_n_spin.maximum()))
        self._decomp_n_spin.setFixedWidth(60)
        self._decomp_n_spin.setToolTip(
            "How many components to resolve — chosen before fitting, "
            "unlike SVD (which yields every component from one fit and "
            "only needs a component index afterward). Same range/default "
            "convention as the standalone NMF Analysis / MCR-ALS tools.")
        comp_label_row.addWidget(self._decomp_n_spin)
        self._decomp_n_label.setVisible(False)
        self._decomp_n_spin.setVisible(False)
        # Deliberately worded differently from "Components to fit" above
        # (rather than both just saying "Component[s]") — one sets how
        # many to fit, this one picks which already-fitted one to browse;
        # same word for both was confusing them together.
        lbl_comp = QLabel("Browse component:")
        lbl_comp.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        comp_label_row.addWidget(lbl_comp)
        self._component_combo = QComboBox()
        self._component_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._component_combo.setMinimumWidth(80)
        self._component_combo.setMaximumWidth(200)
        self._component_combo.setToolTip(
            "Choose the component whose per-pixel score is displayed as "
            "map values (V-coefficients for SVD, abundances for NMF/"
            "MCR-ALS).")
        comp_label_row.addWidget(self._component_combo)
        self._comp_label_label = QLabel("Label:")
        self._comp_label_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        comp_label_row.addWidget(self._comp_label_label)
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

        # ── NMF/MCR-ALS only: robustness re-run + fit status ──────────
        decomp_btn_row = QHBoxLayout()
        self._btn_decomp_run_n = QPushButton("Run N times, keep best…")
        self._btn_decomp_run_n.setToolTip(
            "Like Update Map below, this (re)computes the map — but\n"
            "instead of one deterministic fit, it runs the fit several\n"
            "times with different random starting points and keeps\n"
            "whichever run best represents the near-best group — same\n"
            "robustness check as the standalone NMF Analysis / MCR-ALS\n"
            "tools.\n"
            "Only useful for a fit that isn't already fully\n"
            "deterministic; may take a while on a large map since every\n"
            "run refits every pixel.")
        self._btn_decomp_run_n.setVisible(False)
        decomp_btn_row.addWidget(self._btn_decomp_run_n)

        self._btn_run_bootstrap_map = QPushButton("Bootstrap Uncertainty…")
        self._btn_run_bootstrap_map.setToolTip(
            "Quantifies how much the CURRENTLY LOADED result would\n"
            "wobble under a different noise draw of the same data — a\n"
            "different question from \"Run N times, keep best…\" above\n"
            "(which instead checks for the wrong local optimum /\n"
            "rotational ambiguity). Same residual bootstrap, warm-\n"
            "started from this exact result, as the standalone NMF\n"
            "Analysis / MCR-ALS tools' own Bootstrap Uncertainty button\n"
            "— see their help pages for the full explanation.\n"
            "Requires a fit already loaded and up to date (press\n"
            "\"Update Map\" / \"Run N times, keep best…\" first if\n"
            "settings changed since).")
        self._btn_run_bootstrap_map.setVisible(False)
        decomp_btn_row.addWidget(self._btn_run_bootstrap_map)
        svlay.addLayout(decomp_btn_row)

        self._decomp_run_n_caption = QLabel(
            "\"Run N times\": slower, more thorough alternative to Update "
            "Map below — tries several random starts and keeps the most "
            "consistent result.  \"Bootstrap Uncertainty\": quantifies how "
            "much the currently loaded result would wobble under different "
            "noise, once loaded.")
        self._decomp_run_n_caption.setWordWrap(True)
        self._decomp_run_n_caption.setStyleSheet("font-size:8pt; color:#555;")
        self._decomp_run_n_caption.setVisible(False)
        svlay.addWidget(self._decomp_run_n_caption)

        bootstrap_cb_row = QHBoxLayout()
        self._show_bootstrap_band_cb = QCheckBox(
            "Show bootstrap confidence band on component plot")
        self._show_bootstrap_band_cb.setChecked(True)
        self._show_bootstrap_band_cb.setToolTip(
            "Shades the component's own spectral-shape overlay (on the\n"
            "clicked-pixel spectrum panel below) with its bootstrap\n"
            "confidence band. Has no visible effect until Bootstrap\n"
            "Uncertainty has actually been run.")
        self._show_bootstrap_band_cb.setVisible(False)
        bootstrap_cb_row.addWidget(self._show_bootstrap_band_cb)

        self._show_uncertainty_map_cb = QCheckBox(
            "Show as uncertainty map (band width per pixel)")
        self._show_uncertainty_map_cb.setEnabled(False)
        self._show_uncertainty_map_cb.setToolTip(
            "Replaces the map above with the WIDTH of the bootstrap\n"
            "confidence band at each pixel, instead of the component's\n"
            "score/concentration itself — bright = noise-sensitive\n"
            "there, dark = solid. Enabled once Bootstrap Uncertainty\n"
            "has been run for the currently loaded fit.")
        self._show_uncertainty_map_cb.setVisible(False)
        bootstrap_cb_row.addWidget(self._show_uncertainty_map_cb)
        svlay.addLayout(bootstrap_cb_row)

        self._bootstrap_status_label = QLabel("")
        self._bootstrap_status_label.setStyleSheet("font-size:8pt; color:#2E7D32;")
        self._bootstrap_status_label.setWordWrap(True)
        self._bootstrap_status_label.setVisible(False)
        svlay.addWidget(self._bootstrap_status_label)

        self._decomp_status_label = QLabel("")
        self._decomp_status_label.setStyleSheet("font-size:8pt; color:#2E7D32;")
        self._decomp_status_label.setWordWrap(True)
        self._decomp_status_label.setVisible(False)
        svlay.addWidget(self._decomp_status_label)

        # ── NMF/MCR-ALS only: optional reference-spectra anchoring ────
        self._ref_grp = QGroupBox("Reference spectra (optional)")
        self._ref_grp.setCheckable(True)
        self._ref_grp.setChecked(False)
        self._ref_grp.setToolTip(
            "Anchor a component slot to a KNOWN component spectrum — pick it "
            "by clicking its pixel on the map, the same way as inspecting a "
            "spectrum. The most effective way to remove NMF/MCR-ALS's "
            "rotational ambiguity. Unlike the standalone NMF Analysis / "
            "MCR-ALS tools, a chosen reference stays part of the fitted "
            "data here — removing it would leave fewer spectra than "
            "Rows × Cols pixels, breaking the map's fixed grid.")
        self._ref_grp.toggled.connect(self._on_ref_grp_toggled)
        ref_v = QVBoxLayout(self._ref_grp)
        self._ref_rows_container = QWidget()
        self._ref_rows_layout = QVBoxLayout(self._ref_rows_container)
        self._ref_rows_layout.setContentsMargins(0, 0, 0, 0)
        ref_v.addWidget(self._ref_rows_container)
        self._ref_pick_rows = []   # [{'pick_btn':, 'status_label':, 'clear_btn':}]
        self._ref_fix_cb = QCheckBox("Hold references fixed (else use only as starting guess)")
        self._ref_fix_cb.setChecked(True)
        self._ref_fix_cb.setToolTip(
            "Fixed: the referenced component is held exactly equal to the "
            "known spectrum throughout the fit (strongest anchoring).\n"
            "Unfixed: the reference is only the starting guess and is then "
            "free to adapt.")
        ref_fix_row = QHBoxLayout()
        ref_fix_row.addWidget(self._ref_fix_cb)
        ref_fix_row.addStretch()
        ref_fix_row.addWidget(self._make_info_button(
            "About Reference Spectra",
            "Anchor a component slot to a KNOWN component spectrum — the "
            "most effective way to remove NMF/MCR-ALS's rotational "
            "ambiguity.\n\n"
            "Press “Pick on map…” for a component, then click that "
            "pixel on the map — the same click-a-pixel gesture used "
            "everywhere else in this dialog. The picked pixel is marked "
            "with a numbered circle; View shows its spectrum, and the red "
            "X clears it.\n\n"
            "Hold references fixed: checked pins the component to the "
            "reference exactly throughout the fit; unchecked uses it only "
            "as a starting guess, free to adapt.\n\n"
            "Unlike the standalone NMF Analysis / MCR-ALS tools, a chosen "
            "reference always stays part of the fitted data here — "
            "removing it would leave fewer spectra than Rows × Cols "
            "pixels, breaking the map's fixed grid."))
        ref_v.addLayout(ref_fix_row)
        self._ref_autorecompute_cb = QCheckBox(
            "Auto-recompute when references change")
        self._ref_autorecompute_cb.setChecked(False)
        self._ref_autorecompute_cb.setToolTip(
            "Off (default): picking, clearing, or fixing a reference\n"
            "just flags the map as stale until you next press Update\n"
            "Map — nothing recomputes on every click.\n"
            "On: the same changes recompute the map immediately. Can\n"
            "be slow to leave on for a large map, since every change\n"
            "refits every pixel.")
        ref_v.addWidget(self._ref_autorecompute_cb)
        self._ref_stale_warning_label = QLabel("")
        self._ref_stale_warning_label.setWordWrap(True)
        self._ref_stale_warning_label.setStyleSheet(
            "font-size:8pt; color:#E65100; font-weight:bold;")
        self._ref_stale_warning_label.setVisible(False)
        ref_v.addWidget(self._ref_stale_warning_label)
        self._ref_grp.setVisible(False)
        svlay.addWidget(self._ref_grp)

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

        # ── RGB overlay sub-panel ─────────────────────────────────────
        # Assign up to three already-computed component maps (any mix
        # of SVD/PCA/NMF/MCR-ALS) to R/G/B and compose one false-color
        # image. Unlike SVD/PCA/NMF/MCR-ALS's own sub-panel, this one
        # doesn't drive a fit — it only reads whatever those four
        # decompositions already have cached (see _compose_rgb_overlay).
        self._rgb_panel = QWidget()
        rgblay = QVBoxLayout(self._rgb_panel)
        rgblay.setContentsMargins(0, 0, 0, 0)
        rgblay.setSpacing(4)

        self._rgb_channel_widgets = []  # one dict per R/G/B, in that order
        for ch_idx, (name, color) in enumerate(
                zip(self._RGB_CHANNEL_NAMES, self._RGB_CHANNEL_COLORS)):
            box = QGroupBox(name)
            box.setStyleSheet(
                f"QGroupBox {{ font-weight: bold; color: {color}; }}")
            blay = QVBoxLayout(box)
            blay.setSpacing(3)

            cb_enable = QCheckBox("Enable")
            blay.addWidget(cb_enable)

            row1 = QHBoxLayout()
            row1.addWidget(QLabel("Source:"))
            kind_combo = QComboBox()
            for k in ('svd', 'pca', 'nmf', 'mcr'):
                kind_combo.addItem(self._RGB_KIND_LABELS[k], k)
            row1.addWidget(kind_combo, stretch=1)
            blay.addLayout(row1)

            row2 = QHBoxLayout()
            row2.addWidget(QLabel("Component:"))
            comp_combo = QComboBox()
            row2.addWidget(comp_combo, stretch=1)
            blay.addLayout(row2)

            rgblay.addWidget(box)

            self._rgb_channel_widgets.append({
                'enable': cb_enable, 'kind': kind_combo, 'comp': comp_combo,
            })
            self._refresh_rgb_component_combo(ch_idx)

            cb_enable.stateChanged.connect(self._on_rgb_panel_changed)
            kind_combo.currentIndexChanged.connect(
                lambda _i, c=ch_idx: self._on_rgb_channel_kind_changed(c))
            comp_combo.currentIndexChanged.connect(self._on_rgb_panel_changed)

        pct_row = QHBoxLayout()
        pct_row.addWidget(QLabel("Low %:"))
        self._rgb_lo_pct_spin = QDoubleSpinBox()
        self._rgb_lo_pct_spin.setRange(0.0, 49.0)
        self._rgb_lo_pct_spin.setValue(0.0)
        self._rgb_lo_pct_spin.setDecimals(1)
        self._rgb_lo_pct_spin.valueChanged.connect(self._on_rgb_panel_changed)
        pct_row.addWidget(self._rgb_lo_pct_spin)
        pct_row.addWidget(QLabel("High %:"))
        self._rgb_hi_pct_spin = QDoubleSpinBox()
        self._rgb_hi_pct_spin.setRange(51.0, 100.0)
        self._rgb_hi_pct_spin.setValue(100.0)
        self._rgb_hi_pct_spin.setDecimals(1)
        self._rgb_hi_pct_spin.valueChanged.connect(self._on_rgb_panel_changed)
        pct_row.addWidget(self._rgb_hi_pct_spin)
        rgblay.addLayout(pct_row)
        rgb_note = QLabel(
            "This one % setting is shared by all channels, but is "
            "computed from each channel's OWN values — so the actual "
            "cutoffs usually differ per channel. Purely for this "
            "preview/export; never changes your fit's real values. "
            "0% / 100% = full min–max, no clipping.")
        rgb_note.setWordWrap(True)
        rgb_note.setStyleSheet("font-size:8pt; color:#555;")
        rgblay.addWidget(rgb_note)

        self._rgb_export_btn = QPushButton("Export as PNG…")
        self._rgb_export_btn.setToolTip(
            "Save the current composite at native resolution (one image\n"
            "pixel per map pixel) — independent of the on-screen Equal\n"
            "aspect / Colormap / Interpolation display options above,\n"
            "which never affect the exported file.")
        self._rgb_export_btn.clicked.connect(self._export_rgb_overlay_png)
        rgblay.addWidget(self._rgb_export_btn)

        lay.addWidget(self._rgb_panel)
        self._rgb_panel.setVisible(False)

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
        grid.addWidget(self._make_info_button(
            "About Display Options",
            "Colormap / Interpolation: purely cosmetic — how the same "
            "underlying map values are rendered, no effect on the "
            "computed data.\n\n"
            "Equal aspect ratio: shows each pixel square (rows : cols "
            "physical proportions) rather than stretched to fill the "
            "panel.\n\n"
            "Colorbar range (below): clip the displayed colour range by "
            "percentile, independent of the actual data range."),
            0, 2, alignment=Qt.AlignRight)

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
            "Overlay the component's own spectral shape (orange dashed) on\n"
            "the clicked-pixel spectrum.")
        hdr.addWidget(self._show_svd_cb)

        self._svd_full_range_cb = QCheckBox("Full spectrum")
        self._svd_full_range_cb.setChecked(False)
        self._svd_full_range_cb.setToolTip(
            "Checked: show the full spectrum, with the fit range shaded.\n"
            "Unchecked (default): show the spectrum clipped to the fit\n"
            "range so it matches the component x-axis exactly.")
        hdr.addWidget(self._svd_full_range_cb)

        # Reconstructed-spectrum overlay, on the SAME row as the checkboxes
        # above rather than a row of its own — now that the title label no
        # longer repeats the component name/EV% (see _update_subspectrum_in_panel),
        # there's room. Its own explicit "how many components" spinbox is
        # deliberately NOT tied to the Component dropdown above (which just
        # browses one component's own map/shape at a time) or, for
        # NMF/MCR-ALS, to the Components spinner in the Map Type panel
        # (which sets how many to *fit* and only takes effect after "Update
        # Map" — this spinbox works on whatever is already fitted, right
        # away).
        self._show_reconstructed_cb = QCheckBox("Show reconstr. spectrum using")
        self._show_reconstructed_cb.setChecked(False)
        self._show_reconstructed_cb.setToolTip(
            "Overlay the spectrum rebuilt from the first N fitted components\n"
            "(N set by the spinbox to the right) on the same axis as the\n"
            "clicked-pixel spectrum, since it's in the same intensity units\n"
            "(green dashed). Active in SVD, PCA, NMF, and MCR-ALS modes.")
        hdr.addWidget(self._show_reconstructed_cb)

        self._recon_n_spin = QSpinBox()
        self._recon_n_spin.setRange(1, 1)
        self._recon_n_spin.setValue(1)
        self._recon_n_spin.setEnabled(False)
        self._recon_n_spin.setToolTip(
            "How many already-fitted components to sum into the\n"
            "reconstruction above (its range tracks how many components\n"
            "are actually fitted for the active mode). Defaults to using\n"
            "every fitted component until you dial it down.")
        hdr.addWidget(self._recon_n_spin)
        self._recon_n_user_set = False

        self._recon_n_suffix_label = QLabel("comp.")
        hdr.addWidget(self._recon_n_suffix_label)

        vlay.addLayout(hdr)

        # All five of the widgets above are decomposition-only (SVD, PCA,
        # NMF, MCR-ALS) — hidden explicitly right here rather than relying
        # solely on _on_mode_changed, which only runs on an actual radio
        # click: the dialog opens with Intensity checked programmatically
        # (no click, so no buttonClicked signal), so without this they'd
        # sit visible-but-meaningless in Intensity/Arithmetic/Cluster mode
        # until the user happened to click a mode radio once.
        self._show_svd_cb.setVisible(False)
        self._svd_full_range_cb.setVisible(False)
        self._show_reconstructed_cb.setVisible(False)
        self._recon_n_spin.setVisible(False)
        self._recon_n_suffix_label.setVisible(False)

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
        self._show_reconstructed_cb.stateChanged.connect(self._on_show_reconstructed_changed)
        self._recon_n_spin.valueChanged.connect(self._on_recon_n_spin_changed)
        self._component_combo.currentIndexChanged.connect(
            self._on_component_changed)
        self._comp_label_combo.currentIndexChanged.connect(
            self._refresh_component_combo_labels)
        self._btn_invert.clicked.connect(self._invert_component)
        self._btn_multi_map.clicked.connect(self._show_multi_map)
        self._btn_diagnostics.clicked.connect(self._show_diagnostics)
        self._btn_decomp_run_n.clicked.connect(self._run_decomp_best_of_n)
        self._btn_run_bootstrap_map.clicked.connect(self._prompt_and_run_bootstrap_map)
        self._show_bootstrap_band_cb.stateChanged.connect(self._draw_twin_subspectrum)
        self._show_uncertainty_map_cb.stateChanged.connect(self._on_show_uncertainty_map_changed)
        self._decomp_n_spin.valueChanged.connect(self._on_decomp_n_changed)
        self._ref_fix_cb.toggled.connect(self._on_reference_settings_changed)
        # NMF's Init./Max iter., and MCR-ALS's Max iter./Non-neg. C/
        # Non-neg. ST/Closure, change the fit itself exactly like a
        # component-count or range change does -- wire them to the
        # same stale-marking path (_on_fit_settings_changed) so a
        # mode switch away and back never silently redraws an old
        # fit computed under different settings.
        self._nmf_init_combo.currentIndexChanged.connect(
            lambda *_: self._on_fit_settings_changed('nmf'))
        self._nmf_maxiter_spin.valueChanged.connect(
            lambda *_: self._on_fit_settings_changed('nmf'))
        self._mcr_maxiter_spin.valueChanged.connect(
            lambda *_: self._on_fit_settings_changed('mcr'))
        self._mcr_c_nonneg_cb.toggled.connect(
            lambda *_: self._on_fit_settings_changed('mcr'))
        self._mcr_st_nonneg_cb.toggled.connect(
            lambda *_: self._on_fit_settings_changed('mcr'))
        self._mcr_closure_cb.toggled.connect(
            lambda *_: self._on_fit_settings_changed('mcr'))
        self._ref_autorecompute_cb.toggled.connect(self._on_ref_autorecompute_toggled)
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

    def _decomp_kind(self):
        """
        'svd' / 'pca' / 'nmf' / 'mcr' if one of the four decomposition
        radios is checked, else None. The single place that knows which
        radio maps to which kind string — everything else (Map2DManager's
        unified get_component_*(kind, ...) accessors included) works off
        this string instead of re-checking radios itself.
        """
        if self._radio_svd.isChecked():
            return 'svd'
        if self._radio_pca.isChecked():
            return 'pca'
        if self._radio_nmf.isChecked():
            return 'nmf'
        if self._radio_mcr.isChecked():
            return 'mcr'
        return None

    def _is_decomp_mode(self):
        """True for any of SVD / NMF / MCR-ALS — the three modes that
        share the decomposition panel, fit-then-browse-by-index workflow,
        and (for NMF/MCR-ALS) an explicit component count chosen before
        fitting."""
        return self._decomp_kind() is not None

    def _active_range_state(self):
        """Return (ranges, is_exclude) for the currently active mode."""
        if self._radio_svd.isChecked():
            return self._svd_ranges, self._svd_is_exclude
        elif self._radio_pca.isChecked():
            return self._pca_ranges, self._pca_is_exclude
        elif self._radio_nmf.isChecked():
            return self._nmf_ranges, self._nmf_is_exclude
        elif self._radio_mcr.isChecked():
            return self._mcr_ranges, self._mcr_is_exclude
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
        elif self._radio_pca.isChecked():
            self._pca_ranges     = ranges
            self._pca_is_exclude = is_exclude
        elif self._radio_nmf.isChecked():
            self._nmf_ranges     = ranges
            self._nmf_is_exclude = is_exclude
        elif self._radio_mcr.isChecked():
            self._mcr_ranges     = ranges
            self._mcr_is_exclude = is_exclude
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
        is_pca     = self._radio_pca.isChecked()
        is_nmf     = self._radio_nmf.isChecked()
        is_mcr     = self._radio_mcr.isChecked()
        is_decomp  = is_svd or is_pca or is_nmf or is_mcr
        is_arith   = self._radio_arith.isChecked()
        is_int     = self._radio_intensity.isChecked()
        is_cluster = self._radio_cluster.isChecked()
        is_rgb     = self._radio_rgb.isChecked()

        # A reference pick armed in NMF/MCR-ALS mode doesn't carry meaning
        # in any other mode — disarm it so a leftover "click a pixel to
        # set Component N's reference" hint can't linger after switching.
        if self._ref_picking_component is not None:
            self._ref_picking_component = None
            for rw in self._ref_pick_rows:
                rw['pick_btn'].setChecked(False)
                self._style_pick_button(rw['pick_btn'], False)
            self._click_info_label.setText("Click a pixel to inspect its spectrum.")
            self._map_canvas.set_ref_picking_active(False)

        # Clear SVD twin axis when leaving SVD mode (NMF/MCR-ALS use the
        # same overlay machinery — see _draw_twin_subspectrum — so this
        # only needs to fire when leaving the decomposition modes entirely)
        if not is_decomp:
            self._clear_twin_axis()
            self._clear_reconstructed_overlay()

        # Metric panel and band config visible for intensity and arithmetic only
        self._metric_panel.setVisible(is_int or is_arith)
        # Only in Intensity mode, not Arithmetic — see the button's
        # construction comment for why.
        self._metric_help_btn.setVisible(is_int)
        self._update_x_val_visibility()
        # Band A panel: visible for all modes except cluster/decomposition hides metric
        self._band_a_panel.setVisible(is_int or is_arith or is_decomp or is_cluster)
        # In arithmetic mode, _arith_panel has its own Band A button — hide the one in _band_a_panel
        self._btn_configure_ranges.setVisible(not is_arith and not is_rgb)
        self._ranges_summary_label.setVisible(not is_arith and not is_rgb)
        self._intensity_panel.setVisible(False)
        self._svd_panel.setVisible(is_decomp)
        # Components-to-fit row only applies to NMF/MCR-ALS — SVD gets
        # every component from one fit and has no such setting.
        self._decomp_n_label.setVisible(is_nmf or is_mcr)
        self._decomp_n_spin.setVisible(is_nmf or is_mcr)
        # Fit-control rows: each algorithm's own settings, SVD has none
        # (it's a single deterministic np.linalg.svd call).
        self._nmf_settings_row_widget.setVisible(is_nmf)
        self._mcr_settings_widget.setVisible(is_mcr)
        # Robustness re-run, fit-quality status, and reference-spectra
        # anchoring: meaningful for NMF/MCR-ALS's iterative fits, not for
        # SVD's single deterministic decomposition.
        self._btn_decomp_run_n.setVisible(is_nmf or is_mcr)
        self._decomp_run_n_caption.setVisible(is_nmf or is_mcr)
        self._decomp_status_label.setVisible(is_nmf or is_mcr)
        self._btn_run_bootstrap_map.setVisible(is_nmf or is_mcr)
        self._show_bootstrap_band_cb.setVisible(is_nmf or is_mcr)
        self._show_uncertainty_map_cb.setVisible(is_nmf or is_mcr)
        self._ref_grp.setVisible(is_nmf or is_mcr)
        if is_nmf or is_mcr:
            self._rebuild_reference_rows()
        # "Label:" dropdown (σ / residual error) only means anything for
        # SVD — NMF/MCR-ALS just always show explained variance.
        self._comp_label_label.setVisible(is_svd)
        self._comp_label_combo.setVisible(is_svd)
        # Sign inversion isn't offered for NMF/MCR-ALS: both are
        # constrained non-negative, so a component can't come out
        # "upside down" the way an SVD component sometimes does — and
        # the multi-component grid / diagnostics views aren't wired up
        # for them yet either (hide, don't grey out, same convention as
        # the JWS/SPE-only controls in the Import dialog).
        self._btn_invert.setVisible(is_svd or is_pca)
        self._btn_multi_map.setVisible(is_svd or is_pca)
        self._btn_diagnostics.setVisible(is_svd)
        self._arith_panel.setVisible(is_arith)
        self._cluster_panel.setVisible(is_cluster)
        self._rgb_panel.setVisible(is_rgb)
        self._update_ranges_summary()  # show the active mode's range

        # Colorbar range controls only make sense for continuous, single-
        # scalar maps — not for cluster's discrete labels or RGB overlay's
        # literal composite (no colormap/colorbar involved either way).
        clim_visible = not is_cluster and not is_rgb
        self._clim_auto_cb.setVisible(clim_visible)
        self._clim_min_spin.setVisible(clim_visible)
        self._clim_max_spin.setVisible(clim_visible)
        # find and hide/show the Low%/High% labels too
        for lbl in self._clim_pct_labels:
            lbl.setVisible(clim_visible)

        # Spectrum panel checkboxes. "Full spectrum" (clipped-vs-full main
        # plot view) and "Show <kind> component" (the twin-axis overlay) both
        # apply to all three decomposition modes — the checkbox is relabelled
        # to name whichever kind is active so it never reads "Show SVD
        # component" while looking at an NMF or MCR-ALS map.
        self._show_bands_cb.setVisible(is_int or is_arith or is_cluster)
        if is_decomp:
            kind_label = {'svd': 'SVD', 'pca': 'PCA', 'nmf': 'NMF', 'mcr': 'MCR-ALS'}[self._decomp_kind()]
            self._show_svd_cb.setText(f"Show {kind_label} component")
            self._show_svd_cb.setToolTip(
                f"Overlay the {kind_label} component's own spectral shape\n"
                "(orange dashed) on the clicked-pixel spectrum.")
            self._svd_full_range_cb.setToolTip(
                f"Checked: show the full spectrum, with the {kind_label} range\n"
                "shaded.\n"
                f"Unchecked (default): show the spectrum clipped to the\n"
                f"{kind_label} range so it matches the component x-axis exactly.")
        self._show_svd_cb.setVisible(is_decomp)
        self._svd_full_range_cb.setVisible(is_decomp)
        self._show_reconstructed_cb.setVisible(is_decomp)
        self._recon_n_spin.setVisible(is_decomp)
        self._recon_n_suffix_label.setVisible(is_decomp)


        self._invalidate_map()

        if is_decomp:
            kind = self._decomp_kind()
            kind_label = {'svd': 'SVD', 'pca': 'PCA', 'nmf': 'NMF', 'mcr': 'MCR-ALS'}[kind]
            # Switching modes alone should never force an expensive
            # re-fit: if this kind is already computed AND nothing that
            # would invalidate that fit (range, component count,
            # references — see _decomp_needs_refit) has changed since,
            # just redraw it from the existing cache. Only fall back to
            # the "press Update Map" placeholder when there's genuinely
            # nothing valid to show yet.
            restored = False
            if (self.controller.get_n_components(kind) > 0
                    and not self._decomp_needs_refit.get(kind, False)):
                restored = self._redraw_cached_decomp_map(kind)
            if not restored:
                # Decomposition modes: clear the spectrum panel — only show after Update Map
                self._spectrum_title_label.setText(f"Press 'Update Map' to compute {kind_label}")
                self._spectrum_canvas.ax.cla()
                self._spectrum_canvas.draw_idle()
                self._recon_n_user_set = False
                self._recon_n_spin.blockSignals(True)
                self._recon_n_spin.setMaximum(1)
                self._recon_n_spin.setValue(1)
                self._recon_n_spin.blockSignals(False)
                # Undo any "Components changed — press Update Map" staleness
                # left over from a previous visit to NMF/MCR-ALS mode.
                self._component_combo.setEnabled(True)
                self._decomp_status_label.setStyleSheet(
                    "font-size:8pt; color:#2E7D32;")
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
        elif is_rgb:
            # Refresh every channel's Component list on entry — a kind
            # computed while some OTHER mode was active (the only way
            # to compute one, since RGB overlay doesn't fit anything
            # itself) would otherwise leave that channel's combo empty
            # until the user happened to touch its Source dropdown.
            for _ch_idx in range(3):
                # Only repopulate a channel whose Component combo is
                # out of sync with its Source kind's real count (the
                # empty-combo case this exists for). Repopulating
                # unconditionally on every mode entry would blow away
                # the user's actual selection each time they merely
                # switch away and back — _refresh_rgb_component_combo
                # always resets to Component 1, which is correct right
                # after a genuine kind change but wrong here.
                _w = self._rgb_channel_widgets[_ch_idx]
                _kind = _w['kind'].currentData()
                _real_n = self.controller.get_n_components(_kind) if _kind else 0
                if _w['comp'].count() != _real_n:
                    self._refresh_rgb_component_combo(_ch_idx)
            self._act_export_map.setEnabled(False)
            # Explicitly cleared rather than left at whatever it held
            # before this mode switch — _invalidate_map() (called just
            # above, for every mode) doesn't touch this attribute, so
            # without resetting it here, a failed or skipped auto-build
            # below would leave a stale array in place and the "nothing
            # to show yet" check further down would wrongly think this
            # switch already redrew something.
            self._rgb_overlay_array = None
            # Unlike SVD/NMF/MCR-ALS, composing this mode never redoes
            # anyone else's fit — it only reads whatever those already
            # computed, so there's no expensive-recompute reason to
            # require an explicit button press here. If at least one
            # channel is already configured from a previous visit,
            # show it immediately (quiet — nothing typed yet, so no
            # "nothing enabled" popup); otherwise fall back to the
            # placeholder, since a fresh dialog's channels all start
            # disabled and there's no reasonable default assignment to
            # jump straight to.
            if any(w['enable'].isChecked() for w in self._rgb_channel_widgets):
                self._compute_rgb_overlay_map(quiet=True)
            if self._rgb_overlay_array is None:
                self._spectrum_title_label.setText(
                    "Press 'Update Map' to build the RGB overlay")
                self._spectrum_canvas.ax.cla()
                self._spectrum_canvas.draw_idle()

    def _update_x_val_visibility(self):
        """Show/hide x-value spinboxes and configure buttons based on metric and mode."""
        is_x_metric = self._metric_combo.currentText() == "Intensity at x"
        is_arith    = self._radio_arith.isChecked()
        is_decomp   = self._is_decomp_mode()
        is_cluster  = self._radio_cluster.isChecked()
        is_rgb      = self._radio_rgb.isChecked()

        # x-value row only for "Intensity at x" in non-decomposition/cluster/RGB modes
        self._x_val_row.setVisible(
            is_x_metric and not is_decomp and not is_cluster and not is_rgb)
        self._x_val_label.setText("x₁ (Band A):" if is_arith else "x:")
        self._x_val2_label.setVisible(is_arith and is_x_metric)
        self._x_val2_spin.setVisible(is_arith and is_x_metric)

        # Configure band button: always shown in decomposition/cluster mode,
        # never for RGB overlay (it has no spectral range of its own — it
        # only reads other modes' already-computed component maps)
        show_configure = (is_decomp or is_cluster or not is_x_metric) and not is_rgb
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
        if is_decomp:
            kind_label = {'svd': 'SVD', 'pca': 'PCA', 'nmf': 'NMF', 'mcr': 'MCR-ALS'}[self._decomp_kind()]
            self._btn_configure_ranges.setText(f"Configure {kind_label} range…")
            self._band_a_header.setText(f"{kind_label} computation range")
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
        # A dimensions change is the ONE thing that actually invalidates
        # existing ROI regions: their bounds are row/col INDICES into the
        # current n_rows × n_cols grid, so reshaping that grid (even to a
        # still-valid product, e.g. 25×25 → 5×125) can leave old bounds
        # pointing at the wrong pixels or entirely out of range. Nothing
        # else that goes through _invalidate_map() (mode switch, changing
        # a decomposition's range/component count/references, ...) changes
        # n_rows/n_cols, so only this handler clears ROIs — see
        # _invalidate_map for the mode-switch case this used to also do.
        self._clear_all_rois()
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
        """Clear the displayed map and show a 'recompute needed' message.

        Does NOT clear ROI regions — a region's (row, col) bounds stay
        meaningful regardless of which map type is showing or being
        recomputed, as long as the grid dimensions themselves haven't
        changed (see _on_dims_changed, the one place that DOES need to
        clear them). Callers of this method include a plain mode switch
        (SVD → NMF, Intensity → RGB overlay, ...), which is exactly the
        case ROI regions should survive.

        Also resets "Show as uncertainty map" -- bug found in practice:
        without this, changing a fit setting (component count, Init./Max
        iter., ...) while that checkbox was checked left the OLD
        bootstrap band-width heatmap fully drawn on screen, right
        alongside the red "Settings changed" warning, since nothing
        else ever re-checks staleness once that checkbox's own redraw
        path (_on_show_uncertainty_map_changed) has already run. Every
        staleness trigger in this dialog funnels through this one
        method, so resetting it here (rather than in each of those
        callers separately) closes all of them at once. Unchecking
        rather than leaving it checked-but-stale also means the
        checkbox's own redraw path is never re-entered here: with
        self._last_map_data already cleared to None just above,
        _on_show_uncertainty_map_changed's "unchecked" branch is a
        no-op, so the black "Settings changed" placeholder this method
        just drew is left alone."""
        self._last_map_data = None
        self._last_map_kind = None
        self._map_canvas.disable_hover()
        self._map_canvas._draw_stale()
        self._ref_stale_warning_label.setVisible(False)
        show_umap_cb = getattr(self, '_show_uncertainty_map_cb', None)
        if show_umap_cb is not None:
            if show_umap_cb.isChecked():
                show_umap_cb.setChecked(False)
            show_umap_cb.setEnabled(False)
        bootstrap_label = getattr(self, '_bootstrap_status_label', None)
        if bootstrap_label is not None:
            bootstrap_label.setVisible(False)

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

    def _detect_map_dimensions_from_metadata(self):
        """Return (n_rows, n_cols) read from the first spectrum's
        metadata['import_parameters'], if present and consistent with the
        number of spectra actually loaded here (a mixed selection drawn
        from more than one map, or a stale/edited value, would make the
        product not match) — else None."""
        if not self.spectra:
            return None
        params = self.spectra[0].get('metadata', {}).get('import_parameters', {}) or {}
        n_rows = params.get('map_n_rows')
        n_cols = params.get('map_n_cols')
        if not n_rows or not n_cols:
            return None
        if n_rows * n_cols != self.n_spectra:
            return None
        return n_rows, n_cols

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
        self._last_map_kind = None

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
        # See the matching comment in _MapCanvas.update_map: cla()
        # orphans the existing hover-tooltip annotation.
        self._map_canvas._tooltip = None
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
        self._redraw_roi_patches()
        self._map_canvas.draw()

    # ── RGB overlay mode ─────────────────────────────────────────────

    def _update_rgb_radio_enabled(self):
        """Call after every successful SVD/PCA/NMF/MCR-ALS compute:
        RGB overlay becomes selectable once at least one of them has
        at least one component. It's never disabled again afterward —
        a kind's cache is only ever replaced, not cleared to empty
        once populated (see Map2DManager)."""
        available = [k for k in ('svd', 'pca', 'nmf', 'mcr')
                     if self.controller.get_n_components(k) > 0]
        if available and not self._radio_rgb.isEnabled():
            self._radio_rgb.setEnabled(True)
            self._radio_rgb.setToolTip(
                "Assign up to three computed component maps to R/G/B.")

    def _refresh_rgb_component_combo(self, ch_idx):
        """Repopulate one RGB channel's Component dropdown for whichever
        kind is currently selected in that channel's Source combo. A
        kind with zero components (not computed yet) simply leaves the
        combo empty — the channel then contributes black, same as a
        disabled channel (see _rgb_channel_array)."""
        widgets = self._rgb_channel_widgets[ch_idx]
        kind = widgets['kind'].currentData()
        n = self.controller.get_n_components(kind) if kind else 0
        combo = widgets['comp']
        combo.blockSignals(True)
        combo.clear()
        for i in range(n):
            combo.addItem(f"Component {i + 1}")
        combo.setCurrentIndex(0 if n else -1)
        combo.blockSignals(False)

    def _on_rgb_channel_kind_changed(self, ch_idx):
        self._refresh_rgb_component_combo(ch_idx)
        self._on_rgb_panel_changed()

    def _on_rgb_panel_changed(self):
        """Any RGB panel control changed (Enable checkbox, Source kind,
        Component, or the Low%/High% stretch spinboxes) — recompute and
        redraw immediately. Unlike SVD/PCA/NMF/MCR-ALS, composing an RGB
        overlay from already-computed decompositions is cheap, so there
        is no "first build requires the explicit button press" gate
        here: even the very first Enable checkbox toggle (before
        anything has ever been drawn, i.e. _rgb_overlay_array is still
        None) should show the map right away, not silently wait for a
        Compute Map press that the user was told they don't need."""
        if not self._radio_rgb.isChecked():
            return
        self._compute_rgb_overlay_map()

    def _rgb_channel_array(self, ch_idx, n_rows, n_cols):
        """Return this channel's raw (n_rows, n_cols) map, or None if
        disabled / nothing valid selected / shape mismatch (e.g. the
        dimensions spinboxes changed since that kind was computed).

        Bug found in practice (same family as _on_component_changed's):
        the RGB overlay's per-channel "Source kind" picks whichever
        decomposition (SVD/PCA/NMF/MCR-ALS) is asked for, independent
        of which mode's radio button is currently active -- so a kind
        that went stale while some OTHER mode was on screen (a range or
        fit-setting change nobody re-fit yet) was still read straight
        from its persisted manager here, with no staleness check at
        all, silently compositing a channel from an outdated fit."""
        widgets = self._rgb_channel_widgets[ch_idx]
        if not widgets['enable'].isChecked():
            return None
        kind = widgets['kind'].currentData()
        comp_idx = widgets['comp'].currentIndex()
        if kind is None or comp_idx < 0:
            return None
        if self._decomp_needs_refit.get(kind, False):
            return None
        coeffs = self.controller.get_component_coefficients(kind, comp_idx)
        if coeffs is None:
            return None
        try:
            return np.asarray(coeffs, dtype=float).reshape(n_rows, n_cols)
        except ValueError:
            return None

    def _rgb_normalize_channel(self, arr, n_rows, n_cols):
        """Percentile-stretch one channel's map to [0, 1] using the
        shared Low%/High% setting, computed from THIS channel's own
        values — same percentage, different absolute cutoff per
        channel. Returns all-zero for a disabled/missing/all-NaN
        channel, so a partially-configured overlay never raises."""
        out = np.zeros((n_rows, n_cols), dtype=float)
        if arr is None:
            return out
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return out
        lo_pct = self._rgb_lo_pct_spin.value()
        hi_pct = self._rgb_hi_pct_spin.value()
        lo = float(np.percentile(finite, lo_pct))
        hi = float(np.percentile(finite, hi_pct))
        if hi <= lo:
            hi = lo + 1e-12
        out = (arr - lo) / (hi - lo)
        out = np.nan_to_num(out, nan=0.0, posinf=1.0, neginf=0.0)
        return np.clip(out, 0.0, 1.0)

    def _compose_rgb_overlay(self, n_rows, n_cols):
        rgb = np.zeros((n_rows, n_cols, 3), dtype=float)
        for ch_idx in range(3):
            rgb[:, :, ch_idx] = self._rgb_normalize_channel(
                self._rgb_channel_array(ch_idx, n_rows, n_cols), n_rows, n_cols)
        return rgb

    def _rgb_channel_summary(self):
        parts = []
        for ch_idx, name in enumerate(self._RGB_CHANNEL_NAMES):
            widgets = self._rgb_channel_widgets[ch_idx]
            if not widgets['enable'].isChecked():
                parts.append(f"{name[0]}: off")
                continue
            kind = widgets['kind'].currentData()
            comp_idx = widgets['comp'].currentIndex()
            kind_lbl = self._RGB_KIND_LABELS.get(kind, str(kind))
            parts.append(f"{name[0]}: {kind_lbl} C{comp_idx + 1}")
        return "  ".join(parts)

    def _compute_rgb_overlay_map(self, quiet=False):
        """'Compute Map' handler for RGB overlay mode — also re-invoked
        live by _on_rgb_panel_changed after the first build, and
        automatically by _on_mode_changed when re-entering RGB overlay
        mode with at least one channel already configured (composing
        from already-computed decompositions is cheap, unlike an
        SVD/PCA/NMF/MCR-ALS refit, so there's no reason to require an
        explicit button press the way those do). *quiet* suppresses the
        two informational/warning popups below for that automatic path
        — they exist to explain an unexpected result to someone who
        just pressed a button, not to interrupt a silent mode switch
        with a dialog before the user has done anything at all."""
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()
        if not self.controller.validate_dimensions(
                self.n_spectra, n_rows, n_cols):
            if not quiet:
                QMessageBox.warning(
                    self, "Invalid Dimensions",
                    f"Rows × Cols must equal the number of spectra.\n"
                    f"{n_rows} × {n_cols} = {n_rows * n_cols}  ≠  "
                    f"{self.n_spectra}")
            return
        if not any(w['enable'].isChecked() for w in self._rgb_channel_widgets):
            if not quiet:
                QMessageBox.information(
                    self, "Nothing to show",
                    "Enable at least one of R / G / B in the RGB overlay "
                    "panel first.")
            return

        # Everything from here on (including the "all enabled channels
        # are empty" check just below) is wrapped in try/except: an
        # uncaught exception raised from inside a Qt slot invoked by a
        # real button click (as opposed to a direct call from a test
        # script) is swallowed by PyQt's default handling in a running
        # application — it prints a traceback to stderr/console
        # (invisible if nothing is watching the terminal) and otherwise
        # leaves the GUI exactly as it was, which looks indistinguishable
        # from "the button did nothing". Surface it as an explicit error
        # dialog instead, so a failure here is never silent.
        try:
            # An enabled channel with no usable data (empty Component
            # combo, a kind that hasn't actually been computed, or a
            # stale selection left over from before the map dimensions
            # changed) contributes silent all-zero — see
            # _rgb_channel_array. Composing anyway is correct for a
            # deliberate red/green-only overlay, but if EVERY enabled
            # channel is like this the result is a solid black image
            # with no obvious explanation, which reads as "nothing
            # happened". Catch that specific case here and say so,
            # rather than drawing a blank composite silently.
            empty_enabled = [
                name for ch_idx, name in enumerate(self._RGB_CHANNEL_NAMES)
                if self._rgb_channel_widgets[ch_idx]['enable'].isChecked()
                and self._rgb_channel_array(ch_idx, n_rows, n_cols) is None
            ]
            enabled_count = sum(
                1 for w in self._rgb_channel_widgets if w['enable'].isChecked())
            if empty_enabled and len(empty_enabled) == enabled_count:
                if not quiet:
                    QMessageBox.warning(
                        self, "No data for enabled channel(s)",
                        "Enabled but showing nothing: " + ", ".join(empty_enabled) +
                        ".\n\nEach channel's Source kind must actually have "
                        "been computed (switch to that mode and press Update "
                        "Map/Compute Map first), and its Component dropdown "
                        "must have a component selected. This would otherwise "
                        "silently compose an all-black image.")
                return

            rgb = self._compose_rgb_overlay(n_rows, n_cols)
            self._rgb_overlay_array = rgb
            # A real (n_rows, n_cols) scalar stand-in — the mean of the
            # three displayed channels — so the generic map/ROI/hover
            # machinery (which all key off _last_map_data being a real,
            # finite 2-D array) keeps working unchanged. See the developer
            # guide's RGB overlay section for why CSV export and ROI
            # comparison stats are deliberately disabled rather than
            # exposed against this proxy.
            self._last_map_data = rgb.mean(axis=2)
            self._last_map_kind = None

            self._draw_rgb_overlay_map(
                rgb,
                title=f"RGB overlay: {self._rgb_channel_summary()}  "
                      f"({n_rows} × {n_cols})")
            self._show_range_spectrum_in_panel()
            self._on_map_computed()
            # Not applicable to a 3-channel composite — use the panel's
            # own "Export as PNG…" button instead.
            self._act_export_map.setEnabled(False)
        except Exception as exc:
            traceback.print_exc()
            self._rgb_overlay_array = None
            QMessageBox.critical(
                self, "RGB overlay failed",
                "Building the RGB overlay raised an error:\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                "Full details were printed to the console/terminal.")

    def _draw_rgb_overlay_map(self, rgb, title="RGB overlay"):
        """Render the composed R/G/B image. No colorbar — the pixel
        colors ARE the data, not a colormap-encoded scalar, so unlike
        every other mode's map there is nothing for a colorbar to
        show."""
        interp = self._interp_combo.currentText()
        equal_aspect = self._equal_aspect_cb.isChecked()

        self._map_canvas.ax.cla()
        # See the matching comment in _MapCanvas.update_map: cla()
        # orphans the existing hover-tooltip annotation, so drop the
        # reference here too and let enable_hover() (called by
        # _on_map_computed right after this method returns) recreate it
        # attached to the freshly-cleared axes.
        self._map_canvas._tooltip = None
        if self._map_canvas._cbar_ax is not None:
            try:
                self._map_canvas._cbar_ax.remove()
            except Exception:
                pass
            self._map_canvas._cbar_ax = None

        im = self._map_canvas.ax.imshow(
            rgb, origin='upper',
            aspect='equal' if equal_aspect else 'auto',
            interpolation=interp)
        self._map_canvas._im = im

        self._map_canvas.ax.set_title(title, fontsize=9)
        self._map_canvas.ax.set_xlabel("Column index", fontsize=8)
        self._map_canvas.ax.set_ylabel("Row index",    fontsize=8)
        self._map_canvas.fig.tight_layout()
        self._redraw_roi_patches()
        self._map_canvas.draw()

    def _export_rgb_overlay_png(self):
        if not any(w['enable'].isChecked() for w in self._rgb_channel_widgets):
            QMessageBox.warning(
                self, "Nothing to export",
                "Enable at least one of R / G / B first.")
            return
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()
        rgb = self._compose_rgb_overlay(n_rows, n_cols)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export RGB Overlay", "", "PNG image (*.png)")
        if not path:
            return
        if not path.lower().endswith('.png'):
            path += '.png'
        try:
            # RGB float array in [0, 1] — matplotlib writes it as-is,
            # no cmap/norm involved (those only apply to scalar data);
            # native n_rows × n_cols resolution, independent of
            # whatever "Equal aspect" the on-screen preview is using.
            plt.imsave(path, rgb, origin='upper')
            QMessageBox.information(
                self, "Export",
                f"RGB overlay saved to:\n{path}\n\n{self._rgb_channel_summary()}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

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
            if self._is_decomp_mode():
                band_color = '#E65100'     # orange — matches the decomposition twin axis
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
                    if not self._is_decomp_mode():
                        self._compute_map()
                    else:
                        # SVD/NMF/MCR-ALS are all fit-then-browse — same
                        # reason SVD alone used to be singled out here:
                        # changing the range invalidates a fit that's
                        # potentially expensive to redo, so it's not
                        # done automatically the way the fast metric
                        # modes' ranges are.
                        self._invalidate_map()
                        self._decomp_needs_refit[self._decomp_kind()] = True
                        # Same disabling _on_decomp_n_changed/
                        # _on_fit_settings_changed already do -- this
                        # used to be the one staleness-setter that
                        # skipped it, which is exactly what let
                        # _on_component_changed redraw the OLD map (see
                        # its own docstring). Kept even though that
                        # method now guards itself directly, so the
                        # combo's own enabled-state doesn't keep lying
                        # about whether it's safe to touch.
                        self._component_combo.setEnabled(False)
                        kind_label = {'svd': 'SVD', 'pca': 'PCA', 'nmf': 'NMF', 'mcr': 'MCR-ALS'}[self._decomp_kind()]
                        self._spectrum_title_label.setText(
                            f"{kind_label} range changed — press 'Update Map' to recompute")
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
            self._last_map_kind = None
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
            self._last_map_kind = None
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

        elif self._radio_rgb.isChecked():
            self._compute_rgb_overlay_map()

        else:  # SVD / NMF / MCR-ALS mode
            kind = self._decomp_kind()
            comp_idx = max(0, self._component_combo.currentIndex())
            dec_inc, dec_is_excl = self._active_range_state()
            dec_inc_ranges = [] if dec_is_excl else dec_inc
            dec_exc_ranges = dec_inc if dec_is_excl else []

            if kind == 'svd':
                map_data = self.controller.compute_svd_map(
                    self.spectra, n_rows, n_cols,
                    component_index=comp_idx,
                    x_min=None, x_max=None,
                    include_ranges=dec_inc_ranges, exclude_ranges=dec_exc_ranges,
                )
                fail_msg = (
                    "Failed to compute SVD map.\n"
                    "Ensure all spectra have the same number of data points "
                    "in the selected range (use Linearization in Data Range "
                    "if needed).")
            elif kind == 'pca':
                map_data = self.controller.compute_pca_map(
                    self.spectra, n_rows, n_cols,
                    component_index=comp_idx,
                    x_min=None, x_max=None,
                    include_ranges=dec_inc_ranges, exclude_ranges=dec_exc_ranges,
                )
                fail_msg = (
                    "Failed to compute PCA map.\n"
                    "Ensure all spectra have the same number of data points "
                    "in the selected range (use Linearization in Data Range "
                    "if needed).")
            elif kind == 'nmf':
                refs, fix_refs = self._reference_settings()
                map_data = self.controller.compute_nmf_map(
                    self.spectra, n_rows, n_cols,
                    n_components=self._decomp_n_spin.value(),
                    component_index=comp_idx,
                    x_min=None, x_max=None,
                    include_ranges=dec_inc_ranges, exclude_ranges=dec_exc_ranges,
                    init=self._nmf_init_combo.currentText(),
                    max_iter=self._nmf_maxiter_spin.value(),
                    references=refs, fix_references=fix_refs,
                )
                specific = self.controller.manager.get_last_decomp_error('nmf')
                fail_msg = "Failed to compute NMF map." + (
                    f"\n\n{specific}" if specific else
                    "\nEnsure all spectra have the same number of data "
                    "points in the selected range.")
            else:  # 'mcr'
                refs, fix_refs = self._reference_settings()
                map_data = self.controller.compute_mcr_map(
                    self.spectra, n_rows, n_cols,
                    n_components=self._decomp_n_spin.value(),
                    component_index=comp_idx,
                    x_min=None, x_max=None,
                    include_ranges=dec_inc_ranges, exclude_ranges=dec_exc_ranges,
                    max_iterations=self._mcr_maxiter_spin.value(),
                    c_nonneg=self._mcr_c_nonneg_cb.isChecked(),
                    st_nonneg=self._mcr_st_nonneg_cb.isChecked(),
                    closure=self._mcr_closure_cb.isChecked(),
                    references=refs, fix_references=fix_refs,
                )
                specific = self.controller.manager.get_last_decomp_error('mcr')
                fail_msg = "Failed to compute MCR-ALS map." + (
                    f"\n\n{specific}" if specific else
                    "\nEnsure all spectra have the same number of data "
                    "points in the selected range.")

            if map_data is None:
                QMessageBox.critical(self, "Error", fail_msg)
                return
            self._last_map_data = map_data
            self._last_map_kind = kind if kind in ('svd', 'pca') else None
            self._decomp_needs_refit[kind] = False
            self._ref_stale_warning_label.setVisible(False)
            if kind == 'svd':
                self._svd_inverted.clear()
            elif kind == 'pca':
                self._pca_inverted.clear()
            self._refresh_component_combo(keep_index=comp_idx)
            self._update_rgb_radio_enabled()
            # Invert / Multi-map now also apply to PCA (same sign
            # ambiguity as SVD, unlike NMF/MCR-ALS's non-negativity
            # constraint — see _on_mode_changed, which already hides
            # them for NMF/MCR-ALS). Diagnostics stays SVD-only: its
            # residual-error/Malinowski-IND adapter (_SVDDiagAdapter)
            # isn't generalized to read PCA's arrays. Either way these
            # only actually enable once the fit has something to show.
            self._btn_invert.setEnabled(kind in ('svd', 'pca'))
            self._btn_multi_map.setEnabled(kind in ('svd', 'pca'))
            self._btn_diagnostics.setEnabled(kind == 'svd')
            ev_arr = self.controller.get_component_explained_variance(kind)
            ev     = (ev_arr[comp_idx]
                      if ev_arr is not None and comp_idx < len(ev_arr)
                      else 0.0)
            kind_title = {'svd': 'SVD coeff.', 'pca': 'PCA coeff.', 'nmf': 'NMF', 'mcr': 'MCR-ALS'}[kind]
            title  = (f"{kind_title} map – component {comp_idx + 1}  "
                      f"(EV={ev:.2f}%)  ({n_rows} × {n_cols})")
            self._map_canvas.update_map(
                map_data,
                cmap=self._cmap_combo.currentText(),
                interpolation=self._interp_combo.currentText(),
                title=title,
                equal_aspect=self._equal_aspect_cb.isChecked(),
            )
            # Freshly (re)fit — the panel below is about to fall back to
            # its default spectrum-0 preview, so a previous click's pixel
            # is no longer what's being shown; drop it rather than let
            # the reconstruction overlay keep referencing it.
            self._last_clicked_pixel = None
            self._update_subspectrum_in_panel(comp_idx)
            self._update_decomp_status_label(kind)
            self._sync_uncertainty_map_toggle(kind)
            self._on_map_computed()

        self._map_canvas.setFocus()

    # ── NMF/MCR-ALS: reference-spectra anchoring ────────────────────────

    def _on_fit_settings_changed(self, kind):
        """NMF's Init./Max iter., or MCR-ALS's Max iter./Non-neg. C/
        Non-neg. ST/Closure, changed while that kind is the active
        Map Type.

        These settings feed the fit exactly the way the component
        count and the range do (see _on_decomp_n_changed and
        _configure_ranges) -- changing any of them makes the
        currently-shown map/spectrum describe a fit that no longer
        matches the controls on screen. Treat it the same way: mark
        this kind stale so switching Map Type away and back redraws
        from cache ONLY while nothing invalidating has changed, and
        otherwise asks for 'Update Map' instead of silently keeping
        (and mislabeling) the old fit.

        Bug found in practice (same shape as the one Bootstrap
        Uncertainty's "Show as uncertainty map" checkbox had): this
        handler updated the spectrum panel's TITLE to the red warning
        but never actually cleared the plot underneath, unlike
        _on_decomp_n_changed's identical case just below -- so the old
        component's dashed twin-axis overlay, and its shaded bootstrap
        confidence band if "Show bootstrap confidence band on component
        plot" was checked, stayed fully drawn and unlabeled-as-stale
        right under a title that said otherwise. Now clears the same
        way _on_decomp_n_changed already does.
        """
        if self._decomp_kind() != kind:
            # Widgets for the other kind are hidden while it isn't
            # active, but guard anyway in case a signal still fires
            # programmatically.
            return
        kind_label = {'nmf': 'NMF', 'mcr': 'MCR-ALS'}[kind]
        self._invalidate_map()
        self._decomp_needs_refit[kind] = True
        self._component_combo.setEnabled(False)
        self._decomp_status_label.setStyleSheet(
            "font-size:8pt; color:#B71C1C; font-weight:bold;")
        self._decomp_status_label.setText(
            f"Fit settings changed \u2014 press 'Update Map' to refit {kind_label}")
        self._decomp_status_label.setVisible(True)
        self._spectrum_title_label.setText(
            f"{kind_label} fit settings changed \u2014 press 'Update Map' to refit")
        self._spectrum_canvas.ax.cla()
        self._spectrum_canvas.draw_idle()
        self._clear_twin_axis()
        self._clear_reconstructed_overlay()

    def _on_decomp_n_changed(self, *_):
        """'Components' spinner (how many to fit next) changed.

        The Component dropdown, its EV%s, and the Lack-of-fit/iterations
        status line all still describe the OLD fit until 'Update Map' is
        pressed — so rather than leaving a mismatched count on screen
        with no explanation (e.g. "Components: 6" next to a dropdown
        still only listing C1-C4 from a 4-component fit), mark the map
        and the whole spectrum panel stale, exactly like a range change
        does for NMF/MCR-ALS (see _configure_ranges).
        """
        self._rebuild_reference_rows()
        kind = self._decomp_kind()
        if kind not in ('nmf', 'mcr'):
            return
        kind_label = {'nmf': 'NMF', 'mcr': 'MCR-ALS'}[kind]
        self._invalidate_map()
        self._decomp_needs_refit[kind] = True
        self._component_combo.setEnabled(False)
        self._decomp_status_label.setStyleSheet(
            "font-size:8pt; color:#B71C1C; font-weight:bold;")
        self._decomp_status_label.setText(
            f"Components changed to {self._decomp_n_spin.value()} — "
            f"press 'Update Map' to refit {kind_label}")
        self._decomp_status_label.setVisible(True)
        self._spectrum_title_label.setText(
            f"{kind_label} components changed — press 'Update Map' to refit")
        self._spectrum_canvas.ax.cla()
        self._spectrum_canvas.draw_idle()
        self._clear_twin_axis()
        self._clear_reconstructed_overlay()

    def _rebuild_reference_rows(self, *_):
        """One reference row per component slot, synced to the current
        Components count. Each row picks its reference by clicking a
        pixel on the map (see _on_pick_ref_clicked / _on_map_click) rather
        than from a dropdown — with a map's own spectra numbering in the
        thousands, a "select from this list" combo doesn't scale the way
        it does for the standalone NMF Analysis / MCR-ALS tools' much
        shorter spectrum lists."""
        n = self._decomp_n_spin.value()
        # Drop any picked pixels beyond the new component count, and
        # disarm picking if it was armed for a slot that no longer exists.
        for k in list(self._ref_pixel_by_component):
            if k >= n:
                del self._ref_pixel_by_component[k]
        if self._ref_picking_component is not None and self._ref_picking_component >= n:
            self._ref_picking_component = None
        while self._ref_rows_layout.count():
            item = self._ref_rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._ref_pick_rows = []
        n_cols = self._cols_spin.value()
        for k in range(n):
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(4)
            hl.addWidget(QLabel(f"Component {k + 1}:"))
            pick_btn = QPushButton("Pick on map…")
            pick_btn.setCheckable(True)
            pick_btn.setToolTip(
                "Click, then click a pixel on the map to use its spectrum "
                "as this component's reference.")
            pick_btn.clicked.connect(lambda _checked, ci=k: self._on_pick_ref_clicked(ci))
            self._style_pick_button(pick_btn, False)
            hl.addWidget(pick_btn)
            status_label = QLabel()
            status_label.setStyleSheet("font-size:8pt; color:#444;")
            status_label.setWordWrap(True)
            hl.addWidget(status_label, 1)
            view_btn = QPushButton("View")
            view_btn.setEnabled(False)
            view_btn.setToolTip("Show this reference's spectrum.")
            view_btn.clicked.connect(lambda _checked, ci=k: self._on_view_ref_clicked(ci))
            hl.addWidget(view_btn)
            clear_btn = QPushButton("X")
            clear_btn.setFixedSize(24, 24)
            clear_btn.setStyleSheet(
                "QPushButton { background-color:#C62828; color:white; "
                "font-weight:bold; border:none; border-radius:4px; }"
                "QPushButton:hover { background-color:#B71C1C; }")
            clear_btn.setToolTip("Clear this component's reference.")
            clear_btn.clicked.connect(lambda _checked, ci=k: self._on_clear_ref_clicked(ci))
            hl.addWidget(clear_btn)
            self._ref_rows_layout.addWidget(row)
            self._ref_pick_rows.append(dict(pick_btn=pick_btn,
                                             status_label=status_label,
                                             view_btn=view_btn,
                                             clear_btn=clear_btn))
            self._update_ref_row_status(k, n_cols)
        self._sync_ref_markers()

    def _update_ref_row_status(self, component_index, n_cols=None):
        """Refresh one reference row's status label (and the View
        button's enabled state) from self._ref_pixel_by_component —
        called after a pick, a clear, or a rebuild."""
        if component_index >= len(self._ref_pick_rows):
            return
        row_widgets = self._ref_pick_rows[component_index]
        pixel = self._ref_pixel_by_component.get(component_index)
        if pixel is None:
            row_widgets['status_label'].setText("(none)")
            row_widgets['view_btn'].setEnabled(False)
            return
        row, col = pixel
        if n_cols is None:
            n_cols = self._cols_spin.value()
        sp_idx = row * n_cols + col
        label = (self.spectra[sp_idx].get('label', f'r{row}_c{col}')
                 if 0 <= sp_idx < self.n_spectra else f'r{row}_c{col}')
        row_widgets['status_label'].setText(
            f"row {row + 1}, col {col + 1}  —  {label}")
        row_widgets['view_btn'].setEnabled(0 <= sp_idx < self.n_spectra)

    def _sync_ref_markers(self):
        """Push self._ref_pixel_by_component onto the map canvas as the
        numbered markers, and drop any marker whose component slot no
        longer has a row (after Components count shrinks)."""
        self._map_canvas.clear_ref_pixels()
        for k, pixel in self._ref_pixel_by_component.items():
            self._map_canvas.set_ref_pixel(k, pixel)
        self._map_canvas.set_ref_markers_visible(self._ref_grp.isChecked())

    def _on_pick_ref_clicked(self, component_index):
        """Toggle picking mode for one component's reference row —
        clicking the map afterward (see _on_map_click) assigns that
        pixel's spectrum as the reference. While armed, hovering the map
        also shows a miniature preview of the spectrum under the cursor
        (see _MapCanvas.set_ref_picking_active)."""
        row_widgets = self._ref_pick_rows[component_index] if component_index < len(self._ref_pick_rows) else None
        if self._ref_picking_component == component_index:
            # Clicked its own already-armed button again — cancel.
            self._ref_picking_component = None
            if row_widgets is not None:
                row_widgets['pick_btn'].setChecked(False)
                self._style_pick_button(row_widgets['pick_btn'], False)
            self._click_info_label.setText("Click a pixel to inspect its spectrum.")
            self._map_canvas.set_ref_picking_active(False)
            return
        # Arm this one, disarm/uncheck any other row's button.
        self._ref_picking_component = component_index
        for i, rw in enumerate(self._ref_pick_rows):
            armed = (i == component_index)
            rw['pick_btn'].setChecked(armed)
            self._style_pick_button(rw['pick_btn'], armed)
        self._click_info_label.setText(
            f"Click a pixel on the map to set it as Component "
            f"{component_index + 1}'s reference spectrum.")
        self._map_canvas.set_ref_picking_active(True)

    def _on_clear_ref_clicked(self, component_index):
        self._ref_pixel_by_component.pop(component_index, None)
        self._update_ref_row_status(component_index)
        self._map_canvas.set_ref_pixel(component_index, None)
        self._on_reference_settings_changed()

    def _on_view_ref_clicked(self, component_index):
        """Pop up a small plot of the spectrum currently anchoring this
        component slot."""
        pixel = self._ref_pixel_by_component.get(component_index)
        if pixel is None:
            return
        row, col = pixel
        n_cols = self._cols_spin.value()
        sp_idx = row * n_cols + col
        if not (0 <= sp_idx < self.n_spectra):
            return
        sp = self.spectra[sp_idx]
        label = sp.get('label', f'r{row}_c{col}')

        popup = QDialog(self)
        popup.setWindowTitle(f"Component {component_index + 1} reference — {label}")
        v = QVBoxLayout(popup)
        fig = Figure(figsize=(5, 3.2), tight_layout=True)
        canvas = FigureCanvas(fig)
        ax = fig.add_subplot(111)
        ax.plot(np.asarray(sp['x_scale'], dtype=float),
                np.asarray(sp['y_scale'], dtype=float),
                color='#1565C0', linewidth=1.2)
        ax.set_title(label, fontsize=9)
        ax.set_xlabel(sp.get('x_unit', 'x'), fontsize=8)
        ax.set_ylabel("Intensity", fontsize=8)
        v.addWidget(canvas)
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(popup.reject)
        btn_box.accepted.connect(popup.accept)
        v.addWidget(btn_box)
        popup.resize(480, 380)
        popup.exec_()

    def _on_ref_autorecompute_toggled(self, checked):
        """Checking "Auto-recompute when references change" while
        the stale-reference warning is showing recomputes right away
        instead of leaving both visible at once — they're mutually
        exclusive: once every future change recomputes immediately,
        there's nothing left to warn about."""
        if checked and self._ref_stale_warning_label.isVisible():
            self._compute_map()

    def _on_reference_settings_changed(self):
        """Called after a reference pick/clear, the "Hold references
        fixed" checkbox, or the Reference spectra group's own on/off
        switch changes something _reference_settings() would now return
        differently. Off by default, this just flags the currently
        displayed map as stale (without hiding it — recomputing every
        pixel on every click would be disruptive); with "Auto-recompute
        when references change" on, it recomputes right away instead."""
        if self._decomp_kind() not in ('nmf', 'mcr'):
            return
        if self._last_map_data is None:
            return
        if self._ref_autorecompute_cb.isChecked():
            self._compute_map()
            return
        self._decomp_needs_refit[self._decomp_kind()] = True
        self._ref_stale_warning_label.setText(
            "References changed — press ‘Update Map’ to apply.")
        self._ref_stale_warning_label.setVisible(True)

    def _on_ref_grp_toggled(self, checked):
        self._map_canvas.set_ref_markers_visible(checked)
        self._on_reference_settings_changed()

    def _reference_settings(self):
        """{component_index: (x, y)} from the picked pixels, or empty if
        the Reference spectra group is off."""
        if not self._ref_grp.isChecked():
            return {}, False
        refs = {}
        n_cols = self._cols_spin.value()
        n = self._decomp_n_spin.value()
        for k, (row, col) in self._ref_pixel_by_component.items():
            if k >= n:
                continue
            sp_idx = row * n_cols + col
            if 0 <= sp_idx < self.n_spectra:
                s = self.spectra[sp_idx]
                refs[k] = (np.asarray(s['x_scale'], dtype=float),
                           np.asarray(s['y_scale'], dtype=float))
        return refs, self._ref_fix_cb.isChecked()

    # ── NMF/MCR-ALS: fit-quality status + robustness re-run ─────────────

    def _update_decomp_status_label(self, kind):
        """Show lack-of-fit / iterations (and, after a best-of-n run,
        the consensus info) for NMF/MCR-ALS — SVD has no equivalent
        concept (it's an exact, non-iterative decomposition)."""
        # A fresh fit is in hand — undo the red "Components changed —
        # press Update Map" styling _on_decomp_n_changed may have set.
        self._decomp_status_label.setStyleSheet(
            "font-size:8pt; color:#2E7D32;")
        if kind not in ('nmf', 'mcr'):
            self._decomp_status_label.setText("")
            return
        lof = self.controller.get_component_lof(kind)
        iterations, converged = self.controller.get_component_iterations(kind)
        parts = []
        if lof is not None:
            parts.append(f"Lack of fit: {lof:.3f}%")
        if iterations is not None:
            conv_str = "" if converged else " (not converged)"
            parts.append(f"{iterations} iterations{conv_str}")
        run_info = self.controller.get_last_run_info(kind)
        if run_info is not None:
            n_runs, pool_size, consensus = run_info
            if consensus is not None:
                parts.append(f"best of {n_runs} runs ({consensus * 100:.0f}% "
                             f"consensus among {pool_size} near-best)")
            else:
                parts.append(f"best of {n_runs} runs")
        self._decomp_status_label.setText("  |  ".join(parts))

    # ── NMF/MCR-ALS: Bootstrap Uncertainty ──────────────────────────────

    def _prompt_and_run_bootstrap_map(self):
        """Ask how many bootstrap resamples to run, mirroring
        NMFDialog._prompt_and_run_bootstrap / MCRALSDialog's identical
        pattern almost exactly. Requires an already-loaded, successful,
        non-stale fit for the active kind -- this refits AROUND that
        specific result to measure its noise sensitivity, it does not
        produce a new fit from scratch the way Update Map / Run N times
        do."""
        kind = self._decomp_kind()
        if kind not in ('nmf', 'mcr'):
            return
        if self.controller.get_component_lof(kind) is None:
            QMessageBox.information(
                self, 'Bootstrap Uncertainty',
                'Compute a map ("Update Map", or "Run N times, keep '
                'best…") first \u2014 Bootstrap Uncertainty refits around '
                'whatever result is currently loaded; it does not '
                'produce a new one on its own.')
            return
        # Same bug class fixed in the standalone NMF/MCR-ALS dialogs
        # (see nmf_manager.py/mcr_als_manager.py's bootstrap_result reset
        # and nmf_dialog.py/mcr_als_dialog.py's _prompt_and_run_bootstrap):
        # a setting changed without re-running (_decomp_needs_refit) must
        # not be silently bootstrapped as if it still matched the loaded
        # fit.
        if self._decomp_needs_refit.get(kind, False):
            QMessageBox.information(
                self, 'Bootstrap Uncertainty',
                'Settings have changed since the last run \u2014 press '
                '"Update Map" (or "Run N times, keep best…") first so '
                'the loaded result matches the current settings, then '
                'run Bootstrap Uncertainty around that.')
            return
        from PyQt5.QtWidgets import QInputDialog
        n_resamples, ok = QInputDialog.getInt(
            self, 'Bootstrap Uncertainty',
            'Number of bootstrap resamples:',
            value=getattr(self, '_last_n_bootstrap_map', 30), min=5, max=500)
        if not ok:
            return
        self._last_n_bootstrap_map = n_resamples
        self._run_bootstrap_uncertainty_map(kind, n_resamples)

    def _run_bootstrap_uncertainty_map(self, kind, n_resamples):
        """Residual bootstrap, warm-started from the map's own converged
        fit for *kind* -- see Map2DManager.compute_bootstrap_uncertainty
        for the actual method (delegated straight to NMFController /
        MCRALSController.compute_bootstrap_uncertainty against this
        map's own persisted manager). Deliberately a plain sequential
        loop with a real, cancellable QProgressDialog, mirroring the
        standalone NMF/MCR-ALS dialogs' _run_bootstrap_uncertainty --
        unlike _run_decomp_best_of_n's simpler wait-cursor-only pattern,
        a bootstrap run refits *n_resamples* times over, easily the
        slowest single action available in this dialog, so cancel
        support earns its keep here."""
        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))

        refs, fix_refs = self._reference_settings()
        kwargs = dict(
            n_components=self._decomp_n_spin.value(),
            n_resamples=n_resamples,
            confidence_level=_MAP_BOOTSTRAP_CONFIDENCE_LEVEL,
            random_state=None,
            references=refs, fix_references=fix_refs,
        )
        if kind == 'nmf':
            kwargs.update(init=self._nmf_init_combo.currentText(),
                          max_iter=self._nmf_maxiter_spin.value())
        else:
            kwargs.update(max_iterations=self._mcr_maxiter_spin.value(),
                          tol=0.01,
                          c_nonneg=self._mcr_c_nonneg_cb.isChecked(),
                          st_nonneg=self._mcr_st_nonneg_cb.isChecked(),
                          normalize_spectra=True,
                          closure=self._mcr_closure_cb.isChecked())

        progress = QProgressDialog(
            f'Bootstrap resample 1 of {n_resamples}\u2026', 'Cancel', 0,
            n_resamples, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle('2D Map')
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        def _on_progress(b, n_total):
            progress.setLabelText(f'Bootstrap resample {b + 1} of {n_total}\u2026')
            progress.setValue(b)
            QApplication.processEvents()

        try:
            result = self.controller.compute_bootstrap_uncertainty(
                kind, progress_callback=_on_progress,
                cancel_check=progress.wasCanceled, **kwargs)
            progress.setValue(n_resamples)

            if result is None:
                err = self.controller.get_last_decomp_error(kind)
                QMessageBox.warning(
                    self, 'Bootstrap Uncertainty',
                    err or 'All bootstrap resamples failed.')
                self._bootstrap_status_label.setText(
                    '\u26a0  Bootstrap uncertainty failed \u2014 see message above.')
                self._bootstrap_status_label.setStyleSheet(
                    'font-size:8pt; color:#C62828;')
                self._bootstrap_status_label.setVisible(True)
                return

            pct = int(round(_MAP_BOOTSTRAP_CONFIDENCE_LEVEL * 100))
            msg = (f'Bootstrap uncertainty: {pct}% confidence band from '
                   f'{result["n_resamples_used"]}/'
                   f'{result["n_resamples_requested"]} resamples')
            if result['n_failed']:
                msg += f' ({result["n_failed"]} refit failed and were skipped)'
            self._bootstrap_status_label.setText(msg)
            self._bootstrap_status_label.setStyleSheet(
                'font-size:8pt; color:#2E7D32;')
            self._bootstrap_status_label.setVisible(True)
            self._draw_twin_subspectrum()
            self._sync_uncertainty_map_toggle(kind)
        finally:
            QApplication.restoreOverrideCursor()

    def _sync_uncertainty_map_toggle(self, kind):
        """Enable/reset "Show as uncertainty map" to match whether a
        bootstrap result currently exists for *kind* -- called after
        every map redraw (fresh fit, best-of-n, component switch, or a
        cached mode-switch redraw) so the toggle never claims to show an
        uncertainty view for a fit it doesn't actually match. If it was
        already checked and a matching result still exists (e.g. the
        user just switched which component is being browsed), redraws
        it for the new component instead of silently reverting to the
        point-estimate map without saying so."""
        has_bootstrap = (kind in ('nmf', 'mcr')
                         and self.controller.get_bootstrap_result(kind) is not None)
        self._show_uncertainty_map_cb.setEnabled(has_bootstrap)
        if not has_bootstrap:
            self._bootstrap_status_label.setVisible(False)
            if self._show_uncertainty_map_cb.isChecked():
                self._show_uncertainty_map_cb.blockSignals(True)
                self._show_uncertainty_map_cb.setChecked(False)
                self._show_uncertainty_map_cb.blockSignals(False)
        elif self._show_uncertainty_map_cb.isChecked():
            self._on_show_uncertainty_map_changed()

    def _on_show_uncertainty_map_changed(self):
        """Swap the map canvas between the point-estimate map
        (self._last_map_data) and the bootstrap band-WIDTH map for the
        active component (Map2DManager.get_component_uncertainty_map) --
        a heatmap of how noise-sensitive each pixel's score/
        concentration is, not a second measurement of anything new."""
        kind = self._decomp_kind()
        if kind not in ('nmf', 'mcr'):
            return
        comp_idx = max(0, self._component_combo.currentIndex())
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()
        kind_title = {'nmf': 'NMF', 'mcr': 'MCR-ALS'}[kind]

        if self._show_uncertainty_map_cb.isChecked():
            umap = self.controller.get_component_uncertainty_map(
                kind, comp_idx, n_rows, n_cols)
            if umap is None:
                self._show_uncertainty_map_cb.blockSignals(True)
                self._show_uncertainty_map_cb.setChecked(False)
                self._show_uncertainty_map_cb.blockSignals(False)
                return
            title = (f"{kind_title} component {comp_idx + 1} \u2014 bootstrap "
                     f"uncertainty (95% CI width)  ({n_rows} \u00d7 {n_cols})")
            self._map_canvas.update_map(
                umap,
                cmap=self._cmap_combo.currentText(),
                interpolation=self._interp_combo.currentText(),
                title=title,
                equal_aspect=self._equal_aspect_cb.isChecked(),
            )
        elif self._last_map_data is not None:
            ev_arr = self.controller.get_component_explained_variance(kind)
            ev     = (ev_arr[comp_idx]
                      if ev_arr is not None and comp_idx < len(ev_arr)
                      else 0.0)
            title  = (f"{kind_title} map \u2013 component {comp_idx + 1}  "
                      f"(EV={ev:.2f}%)  ({n_rows} \u00d7 {n_cols})")
            self._map_canvas.update_map(
                self._last_map_data,
                cmap=self._cmap_combo.currentText(),
                interpolation=self._interp_combo.currentText(),
                title=title,
                equal_aspect=self._equal_aspect_cb.isChecked(),
            )

    def _run_decomp_best_of_n(self):
        """Run the active NMF/MCR-ALS fit several times with different
        random seeds and keep whichever run best represents the near-best
        group — same policy as the standalone tools' own button of the
        same name (see Map2DManager._pick_best_of_n). Every trial refits
        every pixel in the map, so this can take a while on a large map;
        there's no live progress/cancel here (unlike the standalone
        dialogs) — just a wait cursor — to keep this addition simple."""
        kind = self._decomp_kind()
        if kind not in ('nmf', 'mcr'):
            return
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()
        if not self.controller.validate_dimensions(self.n_spectra, n_rows, n_cols):
            QMessageBox.warning(
                self, "Invalid Dimensions",
                f"Rows × Cols must equal the number of spectra.\n"
                f"{n_rows} × {n_cols} = {n_rows * n_cols}  ≠  {self.n_spectra}")
            return

        from PyQt5.QtWidgets import QInputDialog
        n_runs, ok = QInputDialog.getInt(
            self, "Run N times, keep best",
            "Number of runs (different random seeds):",
            value=getattr(self, '_last_map_n_runs', 10), min=2, max=50)
        if not ok:
            return
        self._last_map_n_runs = n_runs

        comp_idx = max(0, self._component_combo.currentIndex())
        dec_inc, dec_is_excl = self._active_range_state()
        dec_inc_ranges = [] if dec_is_excl else dec_inc
        dec_exc_ranges = dec_inc if dec_is_excl else []
        refs, fix_refs = self._reference_settings()

        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        try:
            if kind == 'nmf':
                map_data = self.controller.compute_nmf_map(
                    self.spectra, n_rows, n_cols,
                    n_components=self._decomp_n_spin.value(),
                    component_index=comp_idx,
                    x_min=None, x_max=None,
                    include_ranges=dec_inc_ranges, exclude_ranges=dec_exc_ranges,
                    max_iter=self._nmf_maxiter_spin.value(),
                    n_runs=n_runs, references=refs, fix_references=fix_refs,
                )
                fail_msg = ("All NMF runs failed.\n\n"
                            + (self.controller.manager.get_last_decomp_error('nmf') or ""))
            else:
                map_data = self.controller.compute_mcr_map(
                    self.spectra, n_rows, n_cols,
                    n_components=self._decomp_n_spin.value(),
                    component_index=comp_idx,
                    x_min=None, x_max=None,
                    include_ranges=dec_inc_ranges, exclude_ranges=dec_exc_ranges,
                    max_iterations=self._mcr_maxiter_spin.value(),
                    c_nonneg=self._mcr_c_nonneg_cb.isChecked(),
                    st_nonneg=self._mcr_st_nonneg_cb.isChecked(),
                    closure=self._mcr_closure_cb.isChecked(),
                    n_runs=n_runs, references=refs, fix_references=fix_refs,
                )
                fail_msg = "All MCR-ALS runs failed."
        finally:
            QApplication.restoreOverrideCursor()

        if map_data is None:
            QMessageBox.critical(self, "Error", fail_msg)
            return

        self._last_map_data = map_data
        # Bug found in practice: unlike _compute_map's decomp branch
        # (which clears this right after its own successful fit), this
        # method never did -- so choosing "Run N times, keep best"
        # instead of "Update Map" right after changing a setting left
        # _decomp_needs_refit[kind] stuck True even though the result
        # now on screen is a completely fresh, current fit. Harmless by
        # itself (it only makes things OVER-cautious, never wrong), but
        # it wrongly blocked Bootstrap Uncertainty/the multi-map window/
        # SVD diagnostics with a "press Update Map first" message for a
        # fit that was, in fact, already up to date.
        self._decomp_needs_refit[kind] = False
        self._ref_stale_warning_label.setVisible(False)
        self._refresh_component_combo(keep_index=comp_idx)
        self._update_rgb_radio_enabled()
        ev_arr = self.controller.get_component_explained_variance(kind)
        ev     = (ev_arr[comp_idx]
                  if ev_arr is not None and comp_idx < len(ev_arr) else 0.0)
        kind_title = {'nmf': 'NMF', 'mcr': 'MCR-ALS'}[kind]
        title  = (f"{kind_title} map – component {comp_idx + 1}  "
                  f"(EV={ev:.2f}%)  ({n_rows} × {n_cols})")
        self._map_canvas.update_map(
            map_data,
            cmap=self._cmap_combo.currentText(),
            interpolation=self._interp_combo.currentText(),
            title=title,
            equal_aspect=self._equal_aspect_cb.isChecked(),
        )
        # Same reasoning as _compute_map's decomp branch: a fresh best-of-n
        # refit falls back to the default spectrum-0 preview below, so
        # drop any previous click rather than leave the reconstruction
        # overlay pointing at a pixel from before this refit.
        self._last_clicked_pixel = None
        self._update_subspectrum_in_panel(comp_idx)
        self._update_decomp_status_label(kind)
        self._sync_uncertainty_map_toggle(kind)
        self._on_map_computed()
        self._map_canvas.setFocus()

    # ── SVD component combo ─────────────────────────────────────────────

    def _refresh_component_combo(self, keep_index=0):
        """Repopulate the component dropdown after computing the active
        decomposition.

        Bug found in practice: this is also reached from
        _refresh_component_combo_labels (the EV% <-> sigma label
        selector), which fires while the Map Type radio and everything
        else stays exactly as it was -- including a fit marked stale.
        Rebuilding the dropdown's items always re-read the CURRENT
        (possibly stale) manager's component count/EV values -- not
        wrong to show (it's the same cached fit every other stale-aware
        widget is refusing to act on, not different data), but this
        method's unconditional setEnabled(True) at the end used to
        re-enable the Component combo even while
        _decomp_needs_refit[kind] was True, undoing whichever staleness
        setter had just disabled it (_on_decomp_n_changed/
        _on_fit_settings_changed/_configure_ranges_inner). _on_component_
        changed's own guard means selecting a component through it while
        stale is a safe no-op either way, but the widget shouldn't LOOK
        interactive when it isn't. Kept disabled here too whenever this
        kind is stale."""
        kind = self._decomp_kind()
        if kind is None:
            return
        n      = self.controller.get_n_components(kind)
        ev_arr = self.controller.get_component_explained_variance(kind)
        mgr    = self.controller.manager
        # The σ / residual-error label choices only mean anything for
        # SVD (NMF/MCR-ALS have no singular values, and no residual-error
        # adapter) — for the other two kinds, always show explained
        # variance regardless of what the (hidden, for them) combo says.
        mode   = self._comp_label_combo.currentText() if kind == 'svd' else "Explained var.(%)"

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
        self._component_combo.setEnabled(not self._decomp_needs_refit.get(kind, False))
        self._refresh_recon_n_spin()

    def _redraw_cached_decomp_map(self, kind):
        """Redraw component 1 of an ALREADY-fitted decomposition straight
        from Map2DManager's cache (get_component_coefficients) — no
        refit. Used by _on_mode_changed when switching back into a
        decomp mode whose fit is still valid (already computed, and
        nothing that would invalidate it has changed since — see
        _decomp_needs_refit); mode switching alone should never trigger
        an expensive re-fit. Returns True if it drew something, False
        if there was nothing valid to show (the caller falls back to
        the normal 'press Update Map' placeholder in that case)."""
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()
        if not self.controller.validate_dimensions(
                self.n_spectra, n_rows, n_cols):
            return False
        self._refresh_component_combo(keep_index=0)
        comp_idx = max(0, self._component_combo.currentIndex())
        coeffs = self.controller.get_component_coefficients(kind, comp_idx)
        if coeffs is None:
            return False
        try:
            map_data = np.asarray(coeffs, dtype=float).reshape(n_rows, n_cols)
        except ValueError:
            return False

        self._last_map_data = map_data
        self._last_map_kind = kind if kind in ('svd', 'pca') else None
        self._btn_invert.setEnabled(kind in ('svd', 'pca'))
        self._btn_multi_map.setEnabled(kind in ('svd', 'pca'))
        self._btn_diagnostics.setEnabled(kind == 'svd')
        ev_arr = self.controller.get_component_explained_variance(kind)
        ev     = (ev_arr[comp_idx]
                  if ev_arr is not None and comp_idx < len(ev_arr)
                  else 0.0)
        kind_title = {'svd': 'SVD coeff.', 'pca': 'PCA coeff.', 'nmf': 'NMF', 'mcr': 'MCR-ALS'}[kind]
        title  = (f"{kind_title} map – component {comp_idx + 1}  "
                  f"(EV={ev:.2f}%)  ({n_rows} × {n_cols})")
        self._map_canvas.update_map(
            map_data,
            cmap=self._cmap_combo.currentText(),
            interpolation=self._interp_combo.currentText(),
            title=title,
            equal_aspect=self._equal_aspect_cb.isChecked(),
        )
        self._last_clicked_pixel = None
        self._update_subspectrum_in_panel(comp_idx)
        self._update_decomp_status_label(kind)
        self._sync_uncertainty_map_toggle(kind)
        self._on_map_computed()
        return True

    def _refresh_recon_n_spin(self):
        """Keep the reconstruction spinbox's range in sync with how many
        components are actually fitted for the active kind.

        Defaults to the full component count until the user explicitly
        dials it down (self._recon_n_user_set) — after that, their choice
        is preserved across refreshes (switching the σ/EV/RE label combo,
        re-running NMF/MCR-ALS, etc.) as long as it's still in range.
        """
        kind = self._decomp_kind()
        if kind is None:
            return
        n_total = self.controller.get_n_components(kind)
        if n_total <= 0:
            return
        self._recon_n_spin.blockSignals(True)
        self._recon_n_spin.setMaximum(n_total)
        if not self._recon_n_user_set or self._recon_n_spin.value() > n_total:
            self._recon_n_spin.setValue(n_total)
        self._recon_n_spin.blockSignals(False)

    def _on_recon_n_spin_changed(self, _value):
        """User picked a specific N — remember that and refresh the overlay."""
        self._recon_n_user_set = True
        if self._show_reconstructed_cb.isChecked() and self._is_decomp_mode():
            self._draw_reconstructed_overlay()

    def _refresh_component_combo_labels(self):
        """Called when the user switches EV% ↔ σ label selector."""
        kind = self._decomp_kind()
        if kind is None or self.controller.get_n_components(kind) == 0:
            return
        current = self._component_combo.currentIndex()
        self._refresh_component_combo(keep_index=max(0, current))

    def _on_component_changed(self, index):
        """Switch displayed component without recomputing the fit.

        Bug found in practice, and the most serious of this whole
        family: unlike _draw_twin_subspectrum/_update_subspectrum_in_
        panel/_draw_reconstructed_overlay (all guarded against
        _decomp_needs_refit directly, because they're each reachable
        through a checkbox/spinbox that stays enabled while stale),
        this method redraws the MAP CANVAS itself -- not just a
        spectrum-panel overlay -- and had no guard of its own at all.
        It happened to be safe only because _on_decomp_n_changed and
        _on_fit_settings_changed both disable self._component_combo
        while stale, so a direct click couldn't reach it. But
        _configure_ranges_inner (changing the spectral range for
        SVD/PCA/NMF/MCR-ALS) sets _decomp_needs_refit too and does NOT
        disable the combo -- so switching which component to browse
        right after changing the range silently redrew the OLD map
        (self.controller.get_component_coefficients(kind, index) reads
        straight from the persisted per-kind manager, which a range
        change never touches until 'Update Map' is pressed), overwriting
        the correct black "stale" placeholder _invalidate_map() had just
        drawn, with no warning at all. Guarding here directly -- the same
        defense-in-depth already applied to the other three -- means
        this is safe regardless of which caller does or doesn't disable
        the combo, rather than depending on every future staleness
        trigger remembering to do so.
        """
        kind = self._decomp_kind()
        if kind is None or index < 0 or self.controller.get_n_components(kind) == 0:
            return
        if self._decomp_needs_refit.get(kind, False):
            return
        coeffs = self.controller.get_component_coefficients(kind, index)
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
        self._last_map_kind = kind if kind in ('svd', 'pca') else None
        ev_arr = self.controller.get_component_explained_variance(kind)
        ev     = (ev_arr[index]
                  if ev_arr is not None and index < len(ev_arr) else 0.0)
        kind_title = {'svd': 'SVD coeff.', 'pca': 'PCA coeff.', 'nmf': 'NMF', 'mcr': 'MCR-ALS'}[kind]
        title  = (f"{kind_title} map – component {index + 1}  "
                  f"(EV={ev:.2f}%)  ({n_rows} × {n_cols})")
        self._map_canvas.update_map(
            map_data,
            cmap=self._cmap_combo.currentText(),
            interpolation=self._interp_combo.currentText(),
            title=title,
            equal_aspect=self._equal_aspect_cb.isChecked(),
        )
        self._sync_uncertainty_map_toggle(kind)

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
        """Flip sign of the active decomposition's subspectrum/
        coefficients for the current component, then redraw. Works for
        SVD and PCA (both have a genuine sign ambiguity); a no-op for
        NMF/MCR-ALS, which the button is hidden for anyway (see
        _on_mode_changed) since their non-negativity constraint rules
        this out.
        """
        index = self._component_combo.currentIndex()
        if index < 0:
            return
        kind = self._decomp_kind()
        if not self.controller.invert_component(kind, index):
            return
        inverted_set = {'svd': self._svd_inverted,
                        'pca': self._pca_inverted}.get(kind)
        if inverted_set is not None:
            if index in inverted_set:
                inverted_set.discard(index)
            else:
                inverted_set.add(index)

        # Redraw map
        self._on_component_changed(index)

        # Refresh spectrum panel for clicked pixel (or reference if none clicked)
        if self._last_clicked_pixel is not None and kind in ('svd', 'pca'):
            row, col = self._last_clicked_pixel
            n_cols = self._cols_spin.value()
            sp_idx = row * n_cols + col
            if 0 <= sp_idx < self.n_spectra:
                self._update_subspectrum_in_panel(
                    index, clicked_sp=self.spectra[sp_idx])
            else:
                self._update_subspectrum_in_panel(index)

    def _show_diagnostics(self):
        """Open SVDDiagnosticsDialog reused from svd_analysis_dialog.

        Same staleness gap fixed in _show_multi_map just above (this
        button is also enabled purely by kind == 'svd', regardless of
        _decomp_needs_refit)."""
        if self.controller.get_n_svd_components() == 0:
            QMessageBox.information(self, "No SVD",
                                    "Compute an SVD map first.")
            return
        if self._decomp_needs_refit.get('svd', False):
            QMessageBox.information(
                self, "No SVD",
                "Settings have changed since the last run — press "
                "'Update Map' first so this shows the current fit.")
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
        """Open the multi-component map grid window — works for SVD or
        PCA (whichever is active); the button is hidden for NMF/MCR-ALS
        (see _on_mode_changed).

        Bug found in practice (same family as _on_component_changed's
        and the RGB overlay's): this button stays enabled purely based
        on kind in ('svd', 'pca') (see _on_mode_changed/_compute_map),
        with no staleness check -- so a range change (which sets
        _decomp_needs_refit for SVD/PCA too, see _configure_ranges_inner)
        left it clickable, opening a grid of every component's map read
        straight from the stale, pre-range-change fit."""
        kind = self._decomp_kind()
        if kind not in ('svd', 'pca'):
            return
        if self.controller.get_n_components(kind) == 0:
            kind_label = {'svd': 'SVD', 'pca': 'PCA'}[kind]
            QMessageBox.information(self, f"No {kind_label}",
                                    f"Compute a {kind_label} map first.")
            return
        if self._decomp_needs_refit.get(kind, False):
            kind_label = {'svd': 'SVD', 'pca': 'PCA'}[kind]
            QMessageBox.information(
                self, f"No {kind_label}",
                "Settings have changed since the last run — press "
                "'Update Map' first so this shows the current fit.")
            return
        n_rows = self._rows_spin.value()
        n_cols = self._cols_spin.value()
        if not self.controller.validate_dimensions(
                self.n_spectra, n_rows, n_cols):
            QMessageBox.warning(self, "Invalid Dimensions",
                                "Set valid map dimensions first.")
            return
        # The σ/residual-error label modes are SVD-diagnostics-specific
        # (_SVDDiagAdapter isn't generalized to PCA) — same guard already
        # used elsewhere (_refresh_component_combo) so a label mode picked
        # while in SVD mode doesn't leak into a PCA multi-map window.
        label_mode = (self._comp_label_combo.currentText()
                      if kind == 'svd' else "Explained var.(%)")
        dlg = _MultiMapDialog(
            parent=self,
            controller=self.controller,
            kind=kind,
            n_rows=n_rows,
            n_cols=n_cols,
            cmap=self._cmap_combo.currentText(),
            label_mode=label_mode,
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
        Skipped for cluster maps (fixed discrete colormap) and RGB overlay
        (literal composite, no colormap/colorbar at all)."""
        if self._map_canvas._im is None or self._last_map_data is None:
            return
        if self._radio_cluster.isChecked() or self._radio_rgb.isChecked():
            return
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
        elif self._radio_rgb.isChecked() and self._rgb_overlay_array is not None:
            # RGB overlay ignores Colormap (literal composite, no cmap
            # applies) but Interpolation still does — redraw with it.
            self._draw_rgb_overlay_map(
                self._rgb_overlay_array,
                title=f"RGB overlay: {self._rgb_channel_summary()}  "
                      f"({self._rows_spin.value()} × {self._cols_spin.value()})")
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
        elif self._radio_rgb.isChecked() and self._rgb_overlay_array is not None:
            self._draw_rgb_overlay_map(
                self._rgb_overlay_array,
                title=f"RGB overlay: {self._rgb_channel_summary()}  "
                      f"({self._rows_spin.value()} × {self._cols_spin.value()})")
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
                self._last_map_kind = None
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
        """Dispatch map clicks to reference picking, line-profile mode, or
        spectrum inspection."""
        if event.inaxes is not self._map_canvas.ax:
            return
        if event.xdata is None or event.ydata is None:
            return

        # ── Reference-spectrum picking (NMF/MCR-ALS) ────────────────────
        if self._ref_picking_component is not None:
            n_rows = self._rows_spin.value()
            n_cols = self._cols_spin.value()
            col = int(round(event.xdata))
            row = int(round(event.ydata))
            if not (0 <= row < n_rows and 0 <= col < n_cols):
                return
            component_index = self._ref_picking_component
            self._ref_pixel_by_component[component_index] = (row, col)
            self._update_ref_row_status(component_index, n_cols)
            self._map_canvas.set_ref_pixel(component_index, (row, col))
            self._on_reference_settings_changed()
            if component_index < len(self._ref_pick_rows):
                pick_btn = self._ref_pick_rows[component_index]['pick_btn']
                pick_btn.setChecked(False)
                self._style_pick_button(pick_btn, False)
            self._ref_picking_component = None
            self._click_info_label.setText("Click a pixel to inspect its spectrum.")
            self._map_canvas.set_ref_picking_active(False)
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
                    f"Line mode: P1 set at row={row + 1}, col={col + 1}.  "
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

        if self._radio_rgb.isChecked() and self._rgb_overlay_array is not None:
            r_, g_, b_ = self._rgb_overlay_array[row, col]
            self._click_info_label.setText(
                f"Row {row + 1}, Col {col + 1}  →  spectrum: {label}  "
                f"(R={r_:.3f} G={g_:.3f} B={b_:.3f}, display-scaled 0–1)")
        else:
            self._click_info_label.setText(
                f"Row {row + 1}, Col {col + 1}  →  spectrum: {label}  "
                f"(map value: {map_val:.5g})")

        if self._right_splitter.sizes()[1] == 0:
            return

        x = np.asarray(sp.get('original_x_scale', sp['x_scale']), dtype=float)
        y = np.asarray(sp.get('original_y_scale', sp['y_scale']), dtype=float)

        if self._is_decomp_mode():
            comp_idx = max(0, self._component_combo.currentIndex())
            self._update_subspectrum_in_panel(comp_idx, clicked_sp=sp)
        elif self._radio_rgb.isChecked():
            pos = f"Row {row + 1}, Col {col + 1}"
            self._spectrum_title_label.setText(
                f"{label}  [{pos}]  [{self._rgb_channel_summary()}]")
            self._spectrum_canvas.update_spectrum(
                x, y,
                title=f"{label}  ({pos})",
                xlabel="Wavenumber / x",
                ylabel="Intensity",
                color='#1565C0',
            )
        elif self._radio_cluster.isChecked():
            cluster_id = int(round(map_val))
            pos = f"Row {row + 1}, Col {col + 1}"
            self._spectrum_title_label.setText(
                f"{label}  [{pos}]  [Cluster {cluster_id}]")
            self._spectrum_canvas.update_spectrum(
                x, y,
                title=f"{label}  ({pos})  (Cluster {cluster_id})",
                xlabel="Wavenumber / x",
                ylabel="Intensity",
                color='#1565C0',
            )
            self._draw_range_bands(x)
        else:
            mode = self._metric_combo.currentText()
            pos = f"Row {row + 1}, Col {col + 1}"
            self._spectrum_title_label.setText(
                f"{label}  [{pos}]  [{mode} = {map_val:.4g}]")
            self._spectrum_canvas.update_spectrum(
                x, y,
                title=f"{label}  ({pos})  ({mode} = {map_val:.4g})",
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
        """Toggle component subspectrum overlay instantly (SVD/NMF/MCR-ALS)."""
        if self._show_svd_cb.isChecked():
            if self._is_decomp_mode() and self._last_clicked_pixel is not None:
                self._draw_twin_subspectrum()
        else:
            self._clear_twin_axis()

    def _draw_twin_subspectrum(self):
        """Add/refresh the twin-axis subspectrum overlay — only if checkbox is on.

        Works for any decomposition kind (SVD, NMF, MCR-ALS): each has its
        own get_component_subspectrum(kind, idx) via the unified accessor,
        so there's nothing SVD-specific left here.

        For NMF/MCR-ALS, if a Bootstrap Uncertainty result already exists
        for the active fit and "Show bootstrap confidence band on
        component plot" is checked, also shades this twin curve with its
        bootstrap band (get_component_subspectrum_band) -- the same
        quantity nmf_dialog.py/mcr_als_dialog.py shade on their own
        Components tab, just drawn on the twin axis here instead of a
        dedicated one.

        Also guards against staleness directly (same reasoning as
        _update_subspectrum_in_panel's own guard): this method is wired
        straight to "Show bootstrap confidence band on component plot"'s
        checkbox, a SEPARATE entry point that bypasses
        _update_subspectrum_in_panel entirely, so that method's guard
        alone would not have covered this one.
        """
        kind = self._decomp_kind()
        if kind is None:
            self._clear_twin_axis()
            return
        if not self._show_svd_cb.isChecked():
            self._clear_twin_axis()
            return
        if self._decomp_needs_refit.get(kind, False):
            return
        comp_idx = self._component_combo.currentIndex()
        sx, sy = self.controller.get_component_subspectrum(kind, comp_idx)
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
        if kind in ('nmf', 'mcr') and self._show_bootstrap_band_cb.isChecked():
            lo, hi = self.controller.get_component_subspectrum_band(kind, comp_idx)
            if lo is not None and hi is not None and len(lo) == len(sx):
                twin.fill_between(sx, lo, hi, color='#E65100', alpha=0.18,
                                   linewidth=0, zorder=1)
        twin.plot(sx, sy, color='#E65100', linewidth=0.9,
                  linestyle='--', alpha=0.8, zorder=2)
        twin.set_ylabel("Component amplitude", fontsize=7, color='#E65100')
        twin.tick_params(axis='y', labelcolor='#E65100', labelsize=6)
        self._spectrum_canvas._twin_ax = twin
        self._spectrum_canvas.fig.tight_layout()
        self._spectrum_canvas.draw_idle()

    def _clear_reconstructed_overlay(self):
        """Remove the reconstructed-spectrum overlay from the spectrum canvas."""
        canvas = self._spectrum_canvas
        if hasattr(canvas, '_recon_line') and canvas._recon_line is not None:
            try:
                canvas._recon_line.remove()
            except Exception:
                pass
            canvas._recon_line = None
            legend = canvas.ax.get_legend()
            if legend is not None:
                try:
                    legend.remove()
                except Exception:
                    pass
            canvas.draw_idle()

    def _on_show_reconstructed_changed(self):
        """Toggle the reconstructed-spectrum overlay instantly (SVD/PCA/NMF/MCR-ALS)."""
        checked = self._show_reconstructed_cb.isChecked()
        self._recon_n_spin.setEnabled(checked)
        self._recon_n_suffix_label.setEnabled(checked)
        if checked:
            if self._is_decomp_mode():
                self._draw_reconstructed_overlay()
        else:
            self._clear_reconstructed_overlay()

    def _draw_reconstructed_overlay(self):
        """Add/refresh the reconstructed-spectrum overlay — only if checkbox
        is on AND a pixel has actually been clicked.

        Unlike a component's own subspectrum (a different physical
        quantity, hence the twin axis in _draw_twin_subspectrum), a
        reconstruction built from N components is in the same intensity
        units as the clicked-pixel spectrum, so it's plotted as a second
        line directly on the primary axis rather than on a twin axis.

        N comes from its own spinbox (self._recon_n_spin) — deliberately
        independent of which single component the Component dropdown is
        browsing. Deliberately does NOT fall back to spectrum index 0
        before any pixel has been clicked (unlike the raw component
        overlay, which previews spectrum 0) — a reconstruction claims to
        approximate a specific pixel's spectrum, and showing one with no
        Row/Col shown for it looked like a stale/wrong result.

        Bug found in practice (same hole as _draw_twin_subspectrum's,
        fixed the same way): this is a THIRD separate entry point
        (alongside the checkbox and _update_subspectrum_in_panel) that
        redraws straight from the current fit data with no staleness
        check of its own -- self._recon_n_spin's valueChanged
        (_on_recon_n_spin_changed) calls straight into this method, so
        after a settings change nudging that spinbox redrew the OLD
        reconstruction line right under the "Settings changed" warning,
        exactly like the twin-axis overlay did before its own fix. Same
        guard, same reasoning: _update_subspectrum_in_panel's own guard
        doesn't cover this because this method has its own direct
        callers that bypass it entirely.
        """
        kind = self._decomp_kind()
        if kind is None or self._last_clicked_pixel is None:
            self._clear_reconstructed_overlay()
            return
        if not self._show_reconstructed_cb.isChecked():
            self._clear_reconstructed_overlay()
            return
        if self._decomp_needs_refit.get(kind, False):
            self._clear_reconstructed_overlay()
            return
        n_cols = self._cols_spin.value()
        row, col = self._last_clicked_pixel
        sp_idx = row * n_cols + col
        if not (0 <= sp_idx < self.n_spectra):
            self._clear_reconstructed_overlay()
            return
        n_components = self._recon_n_spin.value()
        rx, ry = self.controller.get_reconstructed_spectrum(
            kind, sp_idx, n_components)
        if rx is None or ry is None:
            return
        ax = self._spectrum_canvas.ax
        # Remove previous reconstruction line cleanly
        if hasattr(self._spectrum_canvas, '_recon_line') and \
                self._spectrum_canvas._recon_line is not None:
            try:
                self._spectrum_canvas._recon_line.remove()
            except Exception:
                pass
            self._spectrum_canvas._recon_line = None
        line, = ax.plot(rx, ry, color='#2E7D32', linewidth=1.1,
                        linestyle='--', alpha=0.85,
                        label=f"Reconstructed ({n_components} comp.)")
        self._spectrum_canvas._recon_line = line
        ax.legend(handles=[line], fontsize=6, loc='upper right', framealpha=0.7)
        self._spectrum_canvas.fig.tight_layout()
        self._spectrum_canvas.draw_idle()

    # ── Spectrum / subspectrum panel helpers ────────────────────────────

    def _show_range_spectrum_in_panel(self):
        """After compute or mode switch: show first spectrum with range band shading."""
        if self._right_splitter.sizes()[1] == 0 or not self.spectra:
            return
        # Clear any SVD twin axis / reconstruction overlay from a previous mode
        self._clear_twin_axis()
        self._clear_reconstructed_overlay()

        sp    = self.spectra[0]
        x     = np.asarray(sp.get('original_x_scale', sp['x_scale']), dtype=float)
        y     = np.asarray(sp.get('original_y_scale', sp['y_scale']), dtype=float)
        label = sp.get('label', 'Spectrum 1')

        if self._radio_cluster.isChecked():
            k = self._cluster_k_spin.value()
            method = self._cluster_method_combo.currentText()
            title_plot = f"Cluster preview: {label}  [k={k}, {method}]"
            panel_title = "Click a pixel to see its spectrum and cluster assignment"
        elif self._is_decomp_mode():
            kind_label  = {'svd': 'SVD', 'pca': 'PCA', 'nmf': 'NMF', 'mcr': 'MCR-ALS'}[self._decomp_kind()]
            title_plot  = f"{kind_label} range preview: {label}"
            panel_title = f"Click a pixel — showing: {label}"
        elif self._radio_rgb.isChecked():
            title_plot  = f"RGB overlay preview: {label}"
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

        # Skip if unchecked. In decomposition mode, only draw when "Full
        # spectrum" is checked.
        if not self._show_bands_cb.isChecked():
            self._spectrum_canvas.draw_idle()
            return
        if self._is_decomp_mode():
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
        elif self._is_decomp_mode():
            dec_ranges, dec_is_excl = self._active_range_state()
            _draw_band(None, None,
                       _merge_ranges(dec_ranges),
                       dec_is_excl,
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
        """Toggle between full-spectrum and component-range-only display."""
        if self._is_decomp_mode():
            comp_idx = max(0, self._component_combo.currentIndex())
            self._update_subspectrum_in_panel(comp_idx)

    def _update_subspectrum_in_panel(self, comp_idx, clicked_sp=None):
        """Show spectrum in lower-right panel for SVD/NMF/MCR-ALS mode.

        clicked_sp : spectrum dict to display (defaults to self.spectra[0])

        Bug found in practice (same root cause as _on_fit_settings_changed's
        missing clear, and the uncertainty-map checkbox's missing reset --
        see _invalidate_map): _on_svd_display_changed (the "Full spectrum"
        checkbox) calls straight into this method with no staleness check
        of its own, and this method reads the CURRENT component data
        (get_component_subspectrum) regardless of whether a setting has
        changed since the last fit -- so toggling "Full spectrum" (or any
        future caller of this method) after a settings change silently
        redrew the full old spectrum + old twin overlay right underneath
        the still-correct "Settings changed" warning above it, exactly
        undoing _on_decomp_n_changed's/_on_fit_settings_changed's
        ax.cla()/_clear_twin_axis() call. The standalone NMF/MCR-ALS
        dialogs never had this hole because THEIR redraw functions
        (_refresh_components/_refresh_scores) each check staleness at
        their own top before drawing anything real -- this mirrors that
        same defense-in-depth pattern here, in the one shared method
        every "redraw the spectrum panel for NMF/MCR-ALS" path funnels
        through, rather than patching each caller separately (there may
        be callers not yet audited for this).
        """
        if self._right_splitter.sizes()[1] == 0 or not self.spectra:
            return

        kind = self._decomp_kind()
        if kind is None:
            return
        if self._decomp_needs_refit.get(kind, False):
            return

        sp     = clicked_sp if clicked_sp is not None else self.spectra[0]
        x_full = np.asarray(sp.get('original_x_scale', sp['x_scale']),
                             dtype=float)
        y_full = np.asarray(sp.get('original_y_scale', sp['y_scale']),
                             dtype=float)

        # The component name and its EV% are already shown just above, in
        # the Map Type panel's Browse-component dropdown — repeating them
        # here, in both this label AND the plot's own title, was pure
        # duplication. The one thing this panel alone tells you is which
        # pixel is being shown, so that's all its title states now.
        if clicked_sp is not None and self._last_clicked_pixel is not None:
            # Row/Col of the clicked pixel — shown explicitly rather than
            # relying on it being decodable from the spectrum's own label
            # (only true for WITec MAT imports; not for other formats).
            r, c = self._last_clicked_pixel
            title = f"Row {r + 1}, Col {c + 1}"
        else:
            title = "Click a pixel to see its spectrum"
        self._spectrum_title_label.setText(title)

        show_full = self._svd_full_range_cb.isChecked()

        if show_full:
            # Full spectrum + shaded band region + twin-axis component
            self._spectrum_canvas.update_spectrum(
                x_full, y_full,
                title=title,
                xlabel="Wavenumber / x",
                ylabel="Intensity",
                color='#1565C0',
            )
            # Shade the band region using _draw_range_bands, which reads
            # the active mode's ranges via _active_range_state()
            self._draw_range_bands(x_full)
        else:
            # Clipped spectrum — x-axis matches the fitted component exactly
            x_comp, _y_comp = self.controller.get_component_subspectrum(kind, comp_idx)
            if x_comp is not None:
                # Interpolate the full spectrum onto the component's x-axis
                if x_full[0] > x_full[-1]:
                    y_clipped = np.interp(x_comp, x_full[::-1], y_full[::-1])
                else:
                    y_clipped = np.interp(x_comp, x_full, y_full)
                x_svd = x_comp
            else:
                x_svd, y_clipped = x_full, y_full
            self._spectrum_canvas.update_spectrum(
                x_svd, y_clipped,
                title=title,
                xlabel="Wavenumber / x",
                ylabel="Intensity",
                color='#1565C0',
            )

        # Overlay component subspectrum if checkbox is checked
        if self._show_svd_cb.isChecked():
            self._draw_twin_subspectrum()

        # Overlay reconstructed spectrum if checkbox is checked
        if self._show_reconstructed_cb.isChecked():
            self._draw_reconstructed_overlay()

        self._set_spectrum_panel_visible(True)

    # ── Feature 1: Export map ───────────────────────────────────────────

    def _export_map(self):
        """Export the current map array as CSV or Excel. Not applicable
        in RGB overlay mode (a 3-channel composite, not one scalar per
        pixel) — use the RGB overlay panel's own "Export as PNG…"
        button instead (this action is disabled while that mode is
        active, but guard here too in case it's ever invoked another
        way)."""
        if self._radio_rgb.isChecked():
            QMessageBox.information(
                self, "Not applicable",
                "RGB overlay is a 3-channel composite, not a single "
                "map value per pixel — use the RGB overlay panel's own "
                "\"Export as PNG…\" button instead.")
            return
        if self._last_map_data is None:
            QMessageBox.information(self, "No map", "Compute a map first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Map", "",
            "CSV file (*.csv);;Excel file (*.xlsx)"
        )
        if not path:
            return
        # For SVD/PCA coefficient maps, flag the normalization convention —
        # these values are unit-normalized (not multiplied by the singular
        # value), same as the standalone PCA Scores & Loadings tool's own
        # "Scores". Unlike that tool, this map has no separate Variance
        # sheet/section carrying its singular values, so instead of just
        # pointing elsewhere (the standalone tool runs its own independent
        # SVD/PCA over whatever spectra it currently has loaded, which
        # generally won't match this map's own range-filtered subset), we
        # look up and print this exact component's own sigma directly, so
        # the conversion factor is self-contained and always correct.
        note = None
        if self._last_map_kind in ('svd', 'pca'):
            kind_label = 'SVD' if self._last_map_kind == 'svd' else 'PCA'
            comp_idx = max(0, self._component_combo.currentIndex())
            mgr = self.controller.manager
            sigma_arr = mgr._s if self._last_map_kind == 'svd' else mgr._pca_s
            sigma = (sigma_arr[comp_idx]
                      if sigma_arr is not None and comp_idx < len(sigma_arr)
                      else None)
            if sigma is not None:
                note = (f"Note: these {kind_label} coefficient values (component "
                        f"{comp_idx + 1}) are unit-normalized, not multiplied by "
                        f"the singular value. This component's sigma = {sigma:.6g} "
                        "— multiply every value in this map by that number to get "
                        "a scikit-learn/Jolliffe-convention (sigma-scaled) score.")
            else:
                note = (f"Note: these {kind_label} coefficient values are "
                        "unit-normalized, not multiplied by the singular value.")
        try:
            if path.endswith('.xlsx'):
                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Map"
                start_row = 1
                if note:
                    ws.cell(row=1, column=1).value = note
                    start_row = 2
                for r, row in enumerate(self._last_map_data.tolist(), start=start_row):
                    for c, value in enumerate(row, start=1):
                        ws.cell(row=r, column=c).value = value
                wb.save(path)
            else:
                if not path.endswith('.csv'):
                    path += '.csv'
                header = note if note else ''
                np.savetxt(path, self._last_map_data, delimiter=',', header=header)
            QMessageBox.information(self, "Export", f"Map saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))
    # ── Feature 2: ROI selection ────────────────────────────────────────

    def _update_roi_count(self):
        """Update 'View ROI spectra' with count and mode, keep cancel buttons clean."""
        n_drawn = len(self._all_roi_labels())
        if self._roi_exclude_mode:
            n_view = self.n_spectra - n_drawn
        else:
            n_view = n_drawn

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
        # Stats available when ≥2 regions and a map exists — not for RGB
        # overlay, which has three channel values per pixel, not one.
        self._act_roi_stats.setEnabled(
            n_regions >= 2 and self._last_map_data is not None
            and not self._radio_rgb.isChecked())

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

    def _redraw_roi_patches(self):
        """Re-create every ROI region's matplotlib artist on the CURRENT
        axes, and point self._roi_regions' 'patch' entries at the new
        ones. Registered as the map canvas's post-redraw hook (see
        _MapCanvas.set_post_redraw_hook) so it runs after every full
        redraw that clears the axes — mode switch, Update Map, cmap/
        interpolation/aspect changes, the "Settings changed" placeholder,
        all of them call ax.cla() somewhere, which silently orphans every
        existing patch/line the exact same way it orphans the hover
        tooltip (see the matching comment in _MapCanvas.update_map): the
        Python object in reg['patch'] survives, but it's no longer part
        of the axes' artist list and will never be drawn again no matter
        what. self._roi_regions' own data (bounds, labels, spectra) is
        untouched by any of this — only the visual artists need rebuilding.

        The 'lasso' case has no separate vertex store in the region dict,
        so its vertices are read off the existing (orphaned but still
        readable) PathPatch before building its replacement.
        """
        if not self._roi_regions:
            return
        from matplotlib.patches import Rectangle, Ellipse, PathPatch
        from matplotlib.path import Path as MPath
        import matplotlib.lines as mlines

        ax = self._map_canvas.ax
        for reg in self._roi_regions:
            kind = reg['type']
            if kind == 'rect':
                row0, row1, col0, col1 = reg['bounds']
                artist = Rectangle(
                    (col0 - 0.5, row0 - 0.5),
                    col1 - col0 + 1, row1 - row0 + 1,
                    linewidth=1.5, edgecolor='white', facecolor='none',
                    linestyle='--', zorder=5,
                )
                ax.add_patch(artist)
            elif kind == 'ellipse':
                artist = Ellipse(
                    (reg['cx'], reg['cy']),
                    width=2 * reg['a'], height=2 * reg['b'],
                    linewidth=1.5, edgecolor='white', facecolor='none',
                    linestyle='--', zorder=5,
                )
                ax.add_patch(artist)
            elif kind == 'lasso':
                verts = reg['patch'].get_path().vertices
                artist = PathPatch(
                    MPath(verts),
                    linewidth=1.5, edgecolor='white', facecolor='none',
                    linestyle='--', zorder=5,
                )
                ax.add_patch(artist)
            elif kind == 'line':
                r0, r1, c0, c1 = reg['bounds']
                artist = mlines.Line2D(
                    [c0, c1], [r0, r1],
                    color='white', linewidth=1.8,
                    linestyle='-', marker='o',
                    markersize=4, zorder=6,
                )
                ax.add_line(artist)
            else:
                continue

            reg['patch'] = artist
            # _on_roi_selected / _on_ellipse_roi_selected mutate the
            # LAST-drawn region's patch in place when the user drags its
            # resize handles right after drawing it — keep those
            # references pointing at the fresh artist too, or a resize
            # right after a mode switch would silently edit an orphaned
            # patch nobody can see.
            if self._last_rect_region is reg:
                self._last_rect_patch = artist
            if self._last_ellipse_region is reg:
                self._last_ellipse_patch = artist

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

        if self._radio_rgb.isChecked() and self._rgb_overlay_array is not None:
            # Literal composite — redraw via the same helper as everywhere
            # else in RGB mode, not the generic scalar+cmap path below.
            self._draw_rgb_overlay_map(
                self._rgb_overlay_array,
                title=f"RGB overlay: {self._rgb_channel_summary()}  "
                      f"({self._rows_spin.value()} × {self._cols_spin.value()})")
        elif self._last_map_data is not None:
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
        """Show a comparison table of map value statistics per ROI region.
        Not available in RGB overlay mode (three channel values per
        pixel, not one) — the action is disabled in that mode already,
        but guard here too."""
        if self._radio_rgb.isChecked():
            QMessageBox.information(
                self, "Not applicable",
                "RGB overlay has three channel values per pixel, not one "
                "map value — compare individual components via the "
                "single-component map view instead.")
            return
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

    # ------------------------------------------------------------------ #
    # QDialog cleanup                                                      #
    # ------------------------------------------------------------------ #

    def keyPressEvent(self, event):
        """Enter/Return never triggers a button click in this dialog.

        QDialog's own base implementation reacts to Return/Enter by
        clicking whichever button Qt considers "the" default — every
        QPushButton is autoDefault=True unless told otherwise, and with
        none of this dialog's many buttons explicitly exempted, Qt was
        free to pick any one of them. Disabling autoDefault on a single
        button (e.g. "Suggest…") only made Qt fall through to the next
        eligible one (e.g. the "?" info button) — the bug wasn't about
        which button was nearby, it was this dialog-wide default-button
        mechanism itself. This dialog is a persistent tool panel, not a
        simple form with one obvious "submit" action, so Return/Enter
        should never fire a button on its own no matter which widget has
        focus — intercepting it here, before QDialog's base class gets
        to act on it, is the one place that reliably covers every
        widget and every button at once.
        """
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            return
        super().keyPressEvent(event)

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

    def __init__(self, parent, controller, n_rows, n_cols, kind='svd',
                 cmap='viridis', label_mode='Explained var.(%)'):
        super().__init__(parent)
        self.controller = controller
        self.kind       = kind
        self.n_rows     = n_rows
        self.n_cols     = n_cols
        self.cmap       = cmap
        self.label_mode = label_mode
        self.n_total    = controller.get_n_components(kind)

        kind_title = {'svd': 'SVD', 'pca': 'PCA'}.get(kind, kind.upper())
        self.setWindowTitle(f"{kind_title} Multi-Component Map")
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
        _disable_wheel_scrolling(self)
        # Tick first 3 components (no draw yet — showEvent handles that)
        for i in range(min(3, self.n_total)):
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

        ev_arr = self.controller.get_component_explained_variance(self.kind)
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
        ev_arr = self.controller.get_component_explained_variance(self.kind)
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
        """Invert the highlighted component — same action as the main
        dialog's own Invert button (works for SVD or PCA, whichever kind
        this window was opened for; see Map2DManager.invert_component)."""
        idx = self._highlighted
        if not self.controller.invert_component(self.kind, idx):
            return
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
        ev_arr  = self.controller.get_component_explained_variance(self.kind)

        self._fig.clear()

        if not indices:
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5, "No components selected.\nTick one or more components on the left.",
                    ha='center', va='center', transform=ax.transAxes, fontsize=10,
                    color='#555')
            ax.set_axis_off()
            self._canvas.draw_idle()
            return

        if self.controller.get_n_components(self.kind) == 0:
            kind_label = {'svd': 'SVD', 'pca': 'PCA'}.get(self.kind, self.kind.upper())
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5, f"No {kind_label} data available",
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

            _sx, u_col_raw = self.controller.get_component_subspectrum(self.kind, comp_idx)
            v_row_raw      = self.controller.get_component_coefficients(self.kind, comp_idx)
            if u_col_raw is None or v_row_raw is None:
                ax_map.text(0.5, 0.5, "no data", ha='center', va='center',
                            transform=ax_map.transAxes)
                ax_spec.set_axis_off()
                continue
            u_col = np.asarray(u_col_raw).copy()
            v_row = np.asarray(v_row_raw).copy()

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
            x_ax = _sx
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
