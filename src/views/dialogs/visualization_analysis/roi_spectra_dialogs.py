# src/views/dialogs/visualization_analysis/roi_spectra_dialogs.py
"""
ROI region management + spectra viewer dialogs for the 2-D Spectral Map.
==========================================================================

Split out of map2d_dialog.py (which was growing past ~5000 lines and
mixing several unrelated concerns) purely to improve readability —
no behavior changes. These two dialogs are entirely self-contained:
they only receive plain data (spectra dicts, labels, region dicts) via
their constructors and never reach back into Map2DDialog internals, so
extracting them carries no coupling risk.

Contains
--------
_RemoveROIDialog  : lists all accumulated ROI regions, highlights the
                     selected one(s) on the map, and removes them.
_ROISpectraDialog : the "View ROI spectra" viewer — Overlay / Grid /
                     Waterfall / Heatmap / Difference / Line profile
                     modes for whatever spectra are inside the
                     accumulated ROI region(s).

Both are still "private" (leading underscore) — imported and used only
by Map2DDialog in map2d_dialog.py, not part of the public API of this
package.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QComboBox, QRadioButton, QButtonGroup,
    QSpinBox, QDoubleSpinBox, QFrame, QWidget, QMessageBox, QFileDialog,
    QSizePolicy,
)
from PyQt5.QtCore import Qt
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import numpy as np

from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match

logger = get_logger(__name__)


class _RemoveROIDialog(QDialog):
    """
    Modal dialog listing all ROI regions with multi-selection.
    Clicking a row highlights the corresponding patch on the map in yellow.
    Multiple regions can be selected and removed at once.
    """

    def __init__(self, parent, regions, map_canvas):
        super().__init__(parent)
        self.regions         = regions
        self.map_canvas      = map_canvas
        self.selected_indices = []
        self.setWindowTitle("View / Remove ROI Regions")
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setMinimumWidth(440)
        self._build_ui()
        self._restore_all()

    def _build_ui(self):
        from PyQt5.QtWidgets import QDialogButtonBox
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Select one or more regions to remove.\n"
            "Click a row to highlight it on the map (yellow border).\n"
            "Hold Ctrl or Shift to select multiple regions."
        ))

        self._lst = QListWidget()
        self._lst.setSelectionMode(QListWidget.ExtendedSelection)
        # Same "count lines only, in order" numbering _open_roi_viewer()
        # uses to build Line 1 / Line 2 / ... — precomputed here so line
        # rows can show it, keeping this list's Region numbering (which
        # counts every region type) cross-referenceable with the spectra
        # viewer's Line numbering (which counts lines only).
        line_number_by_index = {}
        _line_counter = 0
        for i, reg in enumerate(self.regions):
            if reg['type'] == 'line':
                _line_counter += 1
                line_number_by_index[i] = _line_counter

        for i, reg in enumerate(self.regions):
            n = len(reg['labels'])
            if reg['type'] == 'rect':
                r0, r1, c0, c1 = reg['bounds']
                text = (f"Region {i+1}: rectangle  "
                        f"rows {r0}–{r1}, cols {c0}–{c1}  ({n} spectra)")
            elif reg['type'] == 'ellipse':
                cx, cy = reg.get('cx', 0), reg.get('cy', 0)
                a,  b  = reg.get('a',  0), reg.get('b',  0)
                text = (f"Region {i+1}: ellipse  "
                        f"centre ({cx:.1f},{cy:.1f})  "
                        f"axes {a:.1f}×{b:.1f}  ({n} spectra)")
            elif reg['type'] == 'line':
                r0, r1, c0, c1 = reg['bounds']
                text = (f"Region {i+1}: line  "
                        f"({r0},{c0})→({r1},{c1})  ({n} spectra)  "
                        f"(Line {line_number_by_index[i]})")
            else:
                text = f"Region {i+1}: lasso  ({n} spectra)"
            self._lst.addItem(text)

        self._lst.itemSelectionChanged.connect(self._on_selection_changed)
        lay.addWidget(self._lst)

        btns = QDialogButtonBox()
        self._btn_remove = btns.addButton("Remove selected", QDialogButtonBox.AcceptRole)
        btns.addButton("Cancel", QDialogButtonBox.RejectRole)
        self._btn_remove.setEnabled(False)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self._on_reject)
        lay.addWidget(btns)

    def _on_selection_changed(self):
        """Highlight selected patches yellow, restore unselected ones."""
        selected_rows = {self._lst.row(item) for item in self._lst.selectedItems()}
        for i, reg in enumerate(self.regions):
            try:
                if reg['type'] == 'line':
                    # Line2D uses set_color / set_linewidth (no edgecolor)
                    if i in selected_rows:
                        reg['patch'].set_color('#FFD600')
                        reg['patch'].set_linewidth(3.5)
                        reg['patch'].set_markersize(7)
                    else:
                        reg['patch'].set_color('white')
                        reg['patch'].set_linewidth(1.8)
                        reg['patch'].set_markersize(4)
                else:
                    if i in selected_rows:
                        reg['patch'].set_edgecolor('#FFD600')
                        reg['patch'].set_linewidth(2.5)
                    else:
                        reg['patch'].set_edgecolor('white')
                        reg['patch'].set_linewidth(1.5)
            except Exception:
                pass
        self.map_canvas.draw_idle()
        self._btn_remove.setEnabled(bool(selected_rows))

    def _restore_all(self):
        for reg in self.regions:
            try:
                if reg['type'] == 'line':
                    reg['patch'].set_color('white')
                    reg['patch'].set_linewidth(1.8)
                    reg['patch'].set_markersize(4)
                else:
                    reg['patch'].set_edgecolor('white')
                    reg['patch'].set_linewidth(1.5)
            except Exception:
                pass
        self.map_canvas.draw_idle()

    def _on_accept(self):
        self.selected_indices = sorted(
            {self._lst.row(item) for item in self._lst.selectedItems()})
        self._restore_all()
        self.accept()

    def _on_reject(self):
        self._restore_all()
        self.reject()
        self.reject()

    def closeEvent(self, event):
        self._restore_all()
        super().closeEvent(event)


class _ROISpectraDialog(QDialog):
    """Shows spectra from one or more accumulated ROI rectangles.

    Left panel controls: multi-select list, Select All / Unselect All,
    View mode (Overlay | Grid | Waterfall | Heatmap | Difference |
    Line profile), Average / variance options, Export, Close.
    Grid and Waterfall modes are capped (see 'Max spectra to plot' spin
    box in the dialog itself) to avoid unreadable or slow plots.
    """

    DEFAULT_MAX_PLOT_SPECTRA = 30   # fallback used only the very first time
                                     # this dialog is ever opened this session
    _last_display_limit = None      # remembers the value across dialog
                                     # re-opens within the same app session
                                     # (not saved to disk / across restarts)

    def __init__(self, parent, spectra, labels, ranges, is_exclude,
                 x_min, x_max, title="ROI spectra",
                 line_map_values=None, line_positions=None,
                 line_ids=None, map2d_controller=None):
        """
        Parameters
        ----------
        line_map_values  : list of float, optional (None entries allowed
            for spectra that aren't part of any line region)
        line_positions   : list of int, optional (position along that
            spectrum's own line — see line_ids)
        line_ids         : list of int, optional — 1-based id of which
            drawn line each spectrum belongs to (None if not on a line).
            Lets the viewer tell two or more line profiles apart instead
            of merging them into one meaningless sequence.
        map2d_controller : Map2DController, optional — needed for Send to main list
        """
        super().__init__(parent)
        self.spectra          = spectra
        self.labels           = labels
        self.ranges           = ranges
        self.is_exclude       = is_exclude
        self.x_min            = x_min
        self.x_max            = x_max
        self.line_map_values  = line_map_values
        self.line_positions   = line_positions
        self.line_ids         = line_ids
        self.has_line         = bool(line_map_values)
        self.n_lines          = len({lid for lid in (line_ids or []) if lid is not None})
        self.map2d_controller = map2d_controller
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.resize(1050, 600)
        self._build_ui()
        self._select_all_items()
        # Auto-select Line profile mode if this is a line region
        if self.has_line:
            self._mode_combo.setCurrentText("Line profile")
            self._on_view_mode_changed(self._mode_combo.currentText())
        self._plot()

    # ------------------------------------------------------------------ #

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        # ── Left control panel ────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(220)
        ll = QVBoxLayout(left)
        ll.setSpacing(5)

        ll.addWidget(QLabel("<b>Spectra in ROI:</b>"))

        sel_row = QHBoxLayout()
        btn_all  = QPushButton("Select All")
        btn_none = QPushButton("Unselect All")
        btn_all.clicked.connect(self._select_all_items)
        btn_none.clicked.connect(self._unselect_all_items)
        sel_row.addWidget(btn_all)
        sel_row.addWidget(btn_none)
        ll.addLayout(sel_row)

        self._lst = QListWidget()
        # Tag each entry with which drawn line it belongs to whenever
        # more than one line profile is present, so the list itself
        # (not just the plot) tells them apart — e.g. "L1: [3,4]".
        if self.n_lines > 1 and self.line_ids is not None:
            display_labels = [
                f"L{lid}: {lbl}" if lid is not None else lbl
                for lbl, lid in zip(self.labels, self.line_ids)
            ]
        else:
            display_labels = self.labels
        self._lst.addItems(display_labels)
        for i in range(self._lst.count()):
            item = self._lst.item(i)
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
        self._lst.setSelectionMode(QListWidget.ExtendedSelection)
        self._lst.selectAll()
        self._lst.itemSelectionChanged.connect(self._plot)
        self._lst.currentRowChanged.connect(self._on_highlight)
        ll.addWidget(self._lst, stretch=1)

        # ── Display limit (meaning depends on view mode — see help) ────
        # User-adjustable in the dialog itself, rather than a fixed
        # class attribute. Grid/Waterfall: caps how many spectra are
        # actually drawn (too many subplots/stacked traces is unreadable
        # and slow). Overlay/Difference: those modes handle any number
        # of spectra fine, but a legend with hundreds of entries doesn't
        # — so it caps legend entries only, not the spectra themselves.
        # Heatmap ignores it entirely (row count isn't a readability
        # problem the same way).
        max_row = QHBoxLayout()
        max_row.addWidget(QLabel("Display limit:"))
        self._max_plot_spin = QSpinBox()
        self._max_plot_spin.setRange(1, 9999)
        self._max_plot_spin.setValue(
            type(self)._last_display_limit
            if type(self)._last_display_limit is not None
            else self.DEFAULT_MAX_PLOT_SPECTRA)
        self._max_plot_spin.setToolTip(
            "Grid / Waterfall: max spectra actually plotted.\n"
            "Overlay / Difference: max legend entries shown\n"
            "(all spectra are still plotted).\n"
            "Heatmap: not used.\n"
            "Remembered for the rest of this session.\n"
            "Click the ? button for details.")
        self._max_plot_spin.valueChanged.connect(self._on_display_limit_changed)
        max_row.addWidget(self._max_plot_spin)

        # Small ? button — same visual style as the main window's
        # orange plot-controls help button.
        self._display_limit_help_button = QPushButton("?")
        self._display_limit_help_button.setFixedWidth(22)
        self._display_limit_help_button.setToolTip(
            "What does 'Display limit' do in each view mode?")
        self._display_limit_help_button.setStyleSheet(
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
        self._display_limit_help_button.clicked.connect(
            self._show_display_limit_help)
        max_row.addWidget(self._display_limit_help_button)
        ll.addLayout(max_row)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        ll.addWidget(sep1)

        # ── View mode ─────────────────────────────────────────────────
        ll.addWidget(QLabel("<b>View mode:</b>"))
        self._mode_combo = QComboBox()
        self._mode_items = ["Overlay", "Grid", "Waterfall", "Heatmap", "Difference"]
        if self.has_line:
            self._mode_items.append("Line profile")
        self._mode_combo.addItems(self._mode_items)
        self._mode_combo.setToolTip(
            "Overlay    — all spectra on one axes\n"
            "Grid       — one subplot per spectrum\n"
            "Waterfall  — spectra stacked with a vertical offset\n"
            "Heatmap    — spectra as image rows (intensity = colour)\n"
            "Difference — each spectrum minus a chosen reference\n"
            "Line profile — map value & spectra along a drawn line\n"
            "               (only available for line ROI regions)")
        self._mode_combo.currentTextChanged.connect(self._on_view_mode_changed)
        ll.addWidget(self._mode_combo)

        # ── Grid axis-link options (Grid mode only) ────────────────────
        self._grid_opts = QWidget()
        go_lay = QVBoxLayout(self._grid_opts)
        go_lay.setContentsMargins(0, 0, 0, 0)
        go_lay.setSpacing(3)
        from PyQt5.QtWidgets import QGridLayout as _GL
        grd = _GL()
        grd.setSpacing(4)
        # x-axes are always identical for map spectra — only offer y-axis linking
        grd.addWidget(QLabel("Link y:"), 0, 0)
        self._link_y_combo = QComboBox()
        self._link_y_combo.addItems(["none", "all", "row", "col"])
        self._link_y_combo.setCurrentText("none")
        self._link_y_combo.setToolTip(
            "Link y-axes across subplots:\n"
            "all — same y-scale for all\n"
            "row — same y-scale within each row\n"
            "col — same y-scale within each column"
        )
        self._link_y_combo.currentIndexChanged.connect(self._plot)
        grd.addWidget(self._link_y_combo, 0, 1)
        go_lay.addLayout(grd)
        self._grid_opts.setVisible(False)
        ll.addWidget(self._grid_opts)

        # ── Waterfall options (Waterfall mode only) ────────────────────
        self._waterfall_opts = QWidget()
        wf_lay = QHBoxLayout(self._waterfall_opts)
        wf_lay.setContentsMargins(0, 0, 0, 0)
        wf_lay.addWidget(QLabel("Offset:"))
        self._waterfall_offset_spin = QDoubleSpinBox()
        self._waterfall_offset_spin.setRange(0.0, 1e9)
        self._waterfall_offset_spin.setDecimals(4)
        self._waterfall_offset_spin.setSpecialValueText("auto")
        self._waterfall_offset_spin.setValue(0.0)
        self._waterfall_offset_spin.setSingleStep(0.01)
        self._waterfall_offset_spin.setToolTip(
            "Vertical spacing between stacked spectra.\n"
            "0 = auto (based on typical peak-to-peak range).")
        self._waterfall_offset_spin.valueChanged.connect(self._plot)
        wf_lay.addWidget(self._waterfall_offset_spin)
        self._waterfall_opts.setVisible(False)
        ll.addWidget(self._waterfall_opts)

        # ── Heatmap options (Heatmap mode only) ────────────────────────
        self._heatmap_opts = QWidget()
        hm_lay = QHBoxLayout(self._heatmap_opts)
        hm_lay.setContentsMargins(0, 0, 0, 0)
        hm_lay.addWidget(QLabel("Colormap:"))
        self._heatmap_cmap_combo = QComboBox()
        self._heatmap_cmap_combo.addItems(
            ["viridis", "plasma", "inferno", "magma", "coolwarm", "jet"])
        self._heatmap_cmap_combo.currentIndexChanged.connect(self._plot)
        hm_lay.addWidget(self._heatmap_cmap_combo)
        self._heatmap_opts.setVisible(False)
        ll.addWidget(self._heatmap_opts)

        # ── Difference options (Difference mode only) ──────────────────
        self._diff_opts = QWidget()
        df_lay = QVBoxLayout(self._diff_opts)
        df_lay.setContentsMargins(0, 0, 0, 0)
        df_lay.addWidget(QLabel("Reference:"))
        self._diff_ref_combo = QComboBox()
        self._diff_ref_combo.currentIndexChanged.connect(self._plot)
        df_lay.addWidget(self._diff_ref_combo)
        self._diff_opts.setVisible(False)
        ll.addWidget(self._diff_opts)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        ll.addWidget(sep2)

        # ── Average / variance options ────────────────────────────────
        ll.addWidget(QLabel("<b>Average / variance:</b>"))
        self._avg_none_rb  = QRadioButton("None")
        self._avg_only_rb  = QRadioButton("Average")
        self._avg_sigma_rb = QRadioButton("Average ± N·σ")
        self._avg_none_rb.setChecked(True)
        avg_grp = QButtonGroup(self)
        for rb in (self._avg_none_rb, self._avg_only_rb, self._avg_sigma_rb):
            avg_grp.addButton(rb)
            ll.addWidget(rb)
        avg_grp.buttonClicked.connect(self._on_avg_changed)

        sig_row = QHBoxLayout()
        sig_row.addWidget(QLabel("σ :"))
        self._sigma_spin = QSpinBox()
        self._sigma_spin.setRange(1, 5)
        self._sigma_spin.setValue(3)
        self._sigma_spin.setEnabled(False)
        self._sigma_spin.valueChanged.connect(self._plot)
        sig_row.addWidget(self._sigma_spin)
        sig_row.addStretch()
        ll.addLayout(sig_row)

        sep3 = QFrame(); sep3.setFrameShape(QFrame.HLine)
        ll.addWidget(sep3)

        # ── Export + Close ────────────────────────────────────────────
        btn_export = QPushButton("Export selected…")
        btn_export.clicked.connect(self._export)
        ll.addWidget(btn_export)

        btn_send = QPushButton("Send to main list…")
        btn_send.setToolTip(
            "Add the selected spectra (or their average) to the main\n"
            "spectrum list, making them available for all processing operations."
        )
        btn_send.clicked.connect(self._send_to_main_list)
        ll.addWidget(btn_send)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        ll.addWidget(btn_close)

        outer.addWidget(left)

        # ── Right: matplotlib ─────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self._fig    = Figure(tight_layout=True)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._toolbar = NavigationToolbar(self._canvas, right)
        rl.addWidget(self._toolbar)
        rl.addWidget(self._canvas, stretch=1)
        outer.addWidget(right, stretch=1)
        self._axes  = []
        self._lines = []

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _selected_row_indices(self):
        # Sorted: .selectedItems() reflects click/selection order, not
        # necessarily list order — every caller here (grid layout, line
        # profile positions, CSV export) expects ascending row order, the
        # same guarantee the old checkbox-based iteration always gave for
        # free by walking range(count()) in order.
        return sorted(self._lst.row(item) for item in self._lst.selectedItems())

    def _select_all_items(self):
        self._lst.blockSignals(True)
        self._lst.selectAll()
        self._lst.blockSignals(False)
        self._plot()

    def _unselect_all_items(self):
        self._lst.blockSignals(True)
        self._lst.clearSelection()
        self._lst.blockSignals(False)
        self._plot()

    def _on_view_mode_changed(self, mode_text=None):
        mode = mode_text if mode_text else self._mode_combo.currentText()
        is_grid  = (mode == "Grid")
        is_wf    = (mode == "Waterfall")
        is_hm    = (mode == "Heatmap")
        is_diff  = (mode == "Difference")
        self._grid_opts.setVisible(is_grid)
        self._waterfall_opts.setVisible(is_wf)
        self._heatmap_opts.setVisible(is_hm)
        self._diff_opts.setVisible(is_diff)
        if is_diff:
            self._refresh_diff_ref_combo()
        # avg/variance overlay is only wired up in Overlay mode (Grid,
        # Waterfall, Heatmap, Difference have their own semantics) —
        # matches the enabled state Overlay/Grid already had.
        avg_relevant = mode in ("Overlay", "Grid")
        self._avg_none_rb.setEnabled(avg_relevant)
        self._avg_only_rb.setEnabled(avg_relevant)
        self._avg_sigma_rb.setEnabled(avg_relevant)
        self._sigma_spin.setEnabled(
            avg_relevant and self._avg_sigma_rb.isChecked())
        self._plot()

    def _on_display_limit_changed(self, value):
        """Remember the Display limit for the rest of this session, so
        reopening the ROI viewer later doesn't reset it back to the
        default."""
        type(self)._last_display_limit = value
        self._plot()

    def _refresh_diff_ref_combo(self):
        """Keep the Difference-mode reference list in sync with the
        currently selected spectra (only meaningful choices are shown).

        If the spectrum that was the reference gets unselected (e.g. via
        Unselect All, or by removing it from the ROI list), it's no
        longer a valid choice, so this falls back to the first remaining
        selected spectrum. That fallback is safe — it always lands on a
        valid choice — but happens silently, and someone glancing at the
        plot without reading the combo box could still think they're
        comparing against their original pick. _plot_difference() flags
        this in the plot title when it happens (see
        self._diff_ref_auto_switched below)."""
        indices = self._selected_row_indices()
        current = self._diff_ref_combo.currentText()
        self._diff_ref_combo.blockSignals(True)
        self._diff_ref_combo.clear()
        self._diff_ref_combo.addItems([self.labels[i] for i in indices])
        idx = self._diff_ref_combo.findText(current)
        self._diff_ref_auto_switched = bool(current) and idx < 0
        self._diff_ref_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._diff_ref_combo.blockSignals(False)

    def _on_avg_changed(self, _btn):
        self._sigma_spin.setEnabled(self._avg_sigma_rb.isChecked())
        self._plot()

    def _cap_for_plot(self, sel_spectra, orig_indices, colors, mode_name):
        """Shared cap+warning for modes that get slow/unreadable with too
        many spectra (Grid, Waterfall). Truncates to the user-adjustable
        'Display limit' value and warns rather than silently dropping
        spectra."""
        cap = self._max_plot_spin.value()
        n = len(sel_spectra)
        if n > cap:
            from PyQt5.QtWidgets import QMessageBox as _QMB
            _QMB.warning(
                self, f"{mode_name} limit",
                f"{mode_name} mode is limited to {cap} spectra to avoid "
                f"performance/readability issues.\n"
                f"Only the first {cap} selected spectra will be plotted.\n\n"
                f"You can raise this using the 'Display limit' box on the "
                f"left (click its ? button for details)."
            )
            sel_spectra  = sel_spectra[:cap]
            orig_indices = orig_indices[:cap]
            colors       = colors[:cap]
        return sel_spectra, orig_indices, colors

    def _add_legend(self, ax, lines, labels, max_entries=None):
        """Shared legend helper. Skips the legend (with a small note
        instead) once there are too many entries to be readable, using
        the same 'Display limit' value as Grid/Waterfall's spectra cap
        so the threshold is one thing the user controls in one place."""
        if not lines:
            return
        if max_entries is None:
            max_entries = self._max_plot_spin.value()
        if len(lines) > max_entries:
            ax.text(0.99, 0.99,
                    f"Legend hidden ({len(lines)} spectra > {max_entries})",
                    ha='right', va='top', transform=ax.transAxes,
                    fontsize=6, color='#888')
            return
        ax.legend(lines, labels, fontsize=6, loc='best',
                  framealpha=0.85, ncol=1 if len(lines) <= 15 else 2)

    def _show_display_limit_help(self):
        """Focused popup explaining only 'Display limit' — its effect
        genuinely differs by mode, so a single tooltip line isn't
        enough, but it shouldn't send the person into the full Map2D
        help document either; this button should only ever be about
        this one control."""
        QMessageBox.information(
            self, "Display limit — what it does per mode",
            "<b>Grid</b> and <b>Waterfall</b>:<br>"
            "Caps how many of the selected spectra are actually plotted. "
            "Too many subplots or stacked traces become unreadable and "
            "slow to draw, so extra spectra beyond the limit are simply "
            "not drawn (a warning tells you when this happens).<br><br>"
            "<b>Overlay</b> and <b>Difference</b>:<br>"
            "All selected spectra are always plotted — that's not a "
            "problem for these modes, just possibly slower. Only the "
            "<i>legend</i> is capped, since a legend with hundreds of "
            "entries is unreadable and slow on its own. Above the "
            "limit, the legend is replaced with a small note instead.<br><br>"
            "<b>Heatmap</b>:<br>"
            "Not used — row count isn't a readability problem the same "
            "way (a heatmap with many rows is still just a heatmap)."
        )

    # ------------------------------------------------------------------ #
    # Plotting                                                             #
    # ------------------------------------------------------------------ #

    def _plot(self, *_):
        indices = self._selected_row_indices()
        self._fig.clear()
        self._axes  = []
        self._lines = []

        if not indices:
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5, "No spectra selected",
                    ha='center', va='center', transform=ax.transAxes, color='#888')
            ax.set_axis_off()
            self._canvas.draw_idle()
            return

        sel_spectra = [self.spectra[i] for i in indices]
        colors = plt.cm.tab20(np.linspace(0, 1, max(len(sel_spectra), 1)))

        mode = self._mode_combo.currentText()
        if mode == "Overlay":
            self._plot_overlay(sel_spectra, colors, indices)
        elif mode == "Grid":
            self._plot_grid(sel_spectra, colors, indices)
        elif mode == "Waterfall":
            self._plot_waterfall(sel_spectra, colors, indices)
        elif mode == "Heatmap":
            self._plot_heatmap(sel_spectra, indices)
        elif mode == "Difference":
            self._plot_difference(sel_spectra, colors, indices)
        elif mode == "Line profile":
            self._plot_line_profile(sel_spectra, indices)

        self._canvas.draw_idle()

    def _shading_kwargs(self, ax):
        """Draw range shading and clip lines on an axes."""
        if self.ranges:
            for s, e in self.ranges:
                lo, hi = min(s, e), max(s, e)
                face = '#FF000012' if self.is_exclude else '#00AA0012'
                ax.axvspan(lo, hi, color=face)
        if self.x_min is not None:
            ax.axvline(self.x_min, color='#E65100', lw=0.7, ls='--')
        if self.x_max is not None:
            ax.axvline(self.x_max, color='#E65100', lw=0.7, ls='--')

    def _avg_variance_overlay(self, ax, sel_spectra):
        """Add average (and optional variance band) to axes."""
        if self._avg_none_rb.isChecked():
            return
        y_all, x_ref = [], None
        skipped = []
        for sp in sel_spectra:
            x = np.asarray(sp.get('original_x_scale', sp['x_scale']), float)
            y = np.asarray(sp.get('original_y_scale', sp['y_scale']), float)
            if x_ref is None:
                x_ref = x
            elif len(x) == len(x_ref) and not axes_match(x, x_ref):
                # Same length but NOT the same x-axis — averaging these
                # together would silently combine unrelated wavenumber
                # positions and attribute the result to x_ref's own axis.
                # A plain shape mismatch (different length) still falls
                # through to the vstack below and is caught by its
                # ValueError, same as before; this catches the same-length
                # case that check couldn't.
                skipped.append(sp.get('label', '?'))
                continue
            y_all.append(y)
        if skipped:
            logger.warning(
                "Average/variance overlay: excluded %d spectrum(s) with a "
                "mismatched x-axis: %s", len(skipped), skipped)
        if not y_all or x_ref is None:
            return
        try:
            mat = np.vstack(y_all)
        except ValueError:
            return
        avg = np.mean(mat, axis=0)
        std = np.std(mat, axis=0)
        ax.plot(x_ref, avg, color='black', linewidth=1.4,
                label='Average', zorder=10)
        if self._avg_sigma_rb.isChecked():
            n_sig = self._sigma_spin.value()
            ax.fill_between(x_ref, avg - n_sig * std, avg + n_sig * std,
                            color='#808080', alpha=0.25,
                            label=f'±{n_sig}σ', zorder=9)
        ax.legend(fontsize=7)

    def _plot_line_profile(self, sel_spectra, orig_indices):
        """Feature 2: two-panel line profile plot.

        Top panel   : map value vs position along the line.
        Bottom panel: all selected spectra as a waterfall / overlay,
                      coloured by position (cold → warm = start → end).
        """
        self._axes  = []
        self._lines = []

        if not self.has_line or self.line_map_values is None:
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5,
                    "Line profile data not available.\n"
                    "Open this viewer from a line region\n"
                    "(drawn with 'Draw line profile').",
                    ha='center', va='center', transform=ax.transAxes,
                    fontsize=9, color='#555')
            ax.set_axis_off()
            self._canvas.draw_idle()
            return

        # Keep only the selected spectra that actually sit on a line
        # (orig_indices index into self.spectra / self.line_map_values /
        # self.line_ids — arrays may contain None for spectra pulled in
        # from a rect/lasso region rather than a line).
        triples = [
            (self.line_ids[i], self.line_positions[i], self.line_map_values[i], sp)
            for i, sp in zip(orig_indices, sel_spectra)
            if i < len(self.line_map_values) and self.line_map_values[i] is not None
        ]

        if not triples:
            self._canvas.draw_idle()
            return

        # Distinct base colour per line (tab10), so two or more line
        # profiles are never mistaken for one another.
        distinct_line_ids = sorted({t[0] for t in triples if t[0] is not None})
        base_colours = {lid: plt.cm.tab10(k % 10)
                         for k, lid in enumerate(distinct_line_ids)}
        multi_line = len(distinct_line_ids) > 1

        # ── Top: map value profile ────────────────────────────────────
        ax_top = self._fig.add_subplot(211)
        for lid in distinct_line_ids:
            group = sorted([t for t in triples if t[0] == lid], key=lambda t: t[1])
            positions = [g[1] for g in group]
            map_vals  = [g[2] for g in group]
            colour = base_colours[lid]
            label = f"Line {lid}" if multi_line else None
            ax_top.plot(positions, map_vals, color=colour, linewidth=1.2,
                        zorder=2, label=label)
            ax_top.scatter(positions, map_vals, color=colour, s=20, zorder=3,
                           edgecolors='none')
        ax_top.set_xlabel("Position along line (pixels)", fontsize=8)
        ax_top.set_ylabel("Map value", fontsize=8)
        title = "Map value profile along line"
        if multi_line:
            title += "s"
            ax_top.legend(fontsize=7)
        ax_top.set_title(title, fontsize=9)
        ax_top.tick_params(labelsize=7)
        ax_top.grid(True, linewidth=0.4, alpha=0.5)
        self._axes.append(ax_top)

        # ── Bottom: spectra coloured by line, shaded by position ──────
        ax_bot = self._fig.add_subplot(212)
        for lid in distinct_line_ids:
            group = sorted([t for t in triples if t[0] == lid], key=lambda t: t[1])
            n = len(group)
            base = np.array(base_colours[lid])
            for k, (_, pos, _, sp) in enumerate(group):
                # Shade from light to full base colour along the line's
                # own position order, keeping each line's hue distinct.
                shade = 0.35 + 0.65 * (k / max(n - 1, 1))
                colour = tuple(np.clip(base[:3] * shade + (1 - shade), 0, 1)) + (base[3],)
                x = np.asarray(sp.get('original_x_scale', sp['x_scale']), float)
                y = np.asarray(sp.get('original_y_scale', sp['y_scale']), float)
                label = f"Line {lid}" if (multi_line and k == 0) else None
                ln, = ax_bot.plot(x, y, color=colour, linewidth=0.7,
                                  alpha=0.85, label=label)
                self._lines.append(ln)
        if multi_line:
            ax_bot.legend(fontsize=7)

        sp_list = [t[3] for t in triples]
        self._avg_variance_overlay(ax_bot, sp_list)
        self._shading_kwargs(ax_bot)
        ax_bot.set_xlabel("Wavenumber / x", fontsize=8)
        ax_bot.set_ylabel("Intensity", fontsize=8)
        if multi_line:
            ax_bot.set_title(
                f"Spectra along {len(distinct_line_ids)} lines  "
                f"({len(triples)} spectra total)", fontsize=9)
        else:
            ax_bot.set_title(
                f"Spectra along line  (light=start → full colour=end, "
                f"{len(triples)} spectra)", fontsize=9)
        ax_bot.tick_params(labelsize=7)

        self._axes.append(ax_bot)
        self._fig.tight_layout()

    def _plot_overlay(self, sel_spectra, colors, orig_indices):
        ax = self._fig.add_subplot(111)
        self._axes = [ax]
        lines, labels = [], []
        for i, (sp, color) in enumerate(zip(sel_spectra, colors)):
            x = np.asarray(sp.get('original_x_scale', sp['x_scale']), float)
            y = np.asarray(sp.get('original_y_scale', sp['y_scale']), float)
            ln, = ax.plot(x, y, color=color, linewidth=0.7, alpha=0.7)
            lines.append(ln)
            labels.append(self.labels[orig_indices[i]])
        self._avg_variance_overlay(ax, sel_spectra)
        self._add_legend(ax, lines, labels)
        self._shading_kwargs(ax)
        ax.set_xlabel("Wavenumber / x", fontsize=8)
        ax.set_ylabel("Intensity", fontsize=8)
        ax.set_title(f"{len(sel_spectra)} spectra (overlay)", fontsize=9)
        self._lines = lines

    def _plot_grid(self, sel_spectra, colors, orig_indices):
        sel_spectra, orig_indices, colors = self._cap_for_plot(
            sel_spectra, orig_indices, colors, "Grid")
        n = len(sel_spectra)

        ncols = max(1, int(np.ceil(np.sqrt(n))))
        nrows = max(1, int(np.ceil(n / ncols)))
        axes = self._fig.subplots(nrows, ncols, squeeze=False)
        self._axes = []
        link_y = self._link_y_combo.currentText()

        for k, (sp, color) in enumerate(zip(sel_spectra, colors)):
            r, c = divmod(k, ncols)
            ax   = axes[r][c]
            self._axes.append(ax)
            x = np.asarray(sp.get('original_x_scale', sp['x_scale']), float)
            y = np.asarray(sp.get('original_y_scale', sp['y_scale']), float)
            ax.plot(x, y, color=color, linewidth=0.8)
            # Issue 4: avg/variance meaningless for a single spectrum — skip in grid
            self._shading_kwargs(ax)
            lbl = self.labels[orig_indices[k]]
            ax.set_title(lbl, fontsize=6)
            ax.tick_params(labelsize=5)

        # Hide unused subplots. Must divide by ncols here, matching the
        # plotting loop above — dividing by n (the spectra count) instead
        # computed the WRONG (row, col) for any grid with leftover empty
        # cells, hiding an already-populated cell (whichever one happened
        # to land on the same divmod result) instead of the genuinely
        # empty one. Confirmed reachable for n=3 (hid the 3rd spectrum,
        # itself already plotted at (1,0), while the real empty cell
        # (1,1) was never hidden) and n=5 (hid the 4th spectrum at (1,0)
        # instead of the real empty cell at (1,2)) — n=4 has zero
        # leftover cells for THIS grid shape, so the loop body never ran
        # and the bug was invisible there.
        for k in range(n, nrows * ncols):
            r, c = divmod(k, ncols if ncols else 1)
            try:
                axes[r][c].set_visible(False)
            except Exception:
                pass

        # Axis linking
        self._apply_axis_linking(axes, nrows, ncols, link_y)
        self._fig.tight_layout()

    def _apply_axis_linking(self, axes, nrows, ncols, link_y):
        """Link y-axes according to the combo selection.
        x-axes are not linked — map spectra always share the same x-scale."""
        def _link_group(ax_list, xy):
            if not ax_list:
                return
            ref = ax_list[0]
            for ax in ax_list[1:]:
                if xy == 'x':
                    ax.sharex(ref)
                else:
                    ax.sharey(ref)

        if link_y == 'all':
            _link_group([a for row in axes for a in row if a.get_visible()], 'y')
        elif link_y == 'row':
            for row in axes:
                _link_group([a for a in row if a.get_visible()], 'y')
        elif link_y == 'col':
            for ci in range(ncols):
                _link_group([axes[ri][ci] for ri in range(nrows)
                             if axes[ri][ci].get_visible()], 'y')

    # ------------------------------------------------------------------ #

    def _plot_waterfall(self, sel_spectra, colors, orig_indices):
        """Spectra stacked with a vertical offset, in list order."""
        ax = self._fig.add_subplot(111)
        self._axes = [ax]

        sel_spectra, orig_indices, colors = self._cap_for_plot(
            sel_spectra, orig_indices, colors, "Waterfall")
        lines, labels = [], []

        ys = [np.asarray(sp.get('original_y_scale', sp['y_scale']), float)
              for sp in sel_spectra]

        offset = self._waterfall_offset_spin.value()
        if offset <= 0.0:
            # auto: a fraction of the typical peak-to-peak range, so
            # traces are separated but still overlap slightly (easier
            # to compare shapes than fully non-overlapping stacks).
            ranges = [y.max() - y.min() for y in ys if y.size]
            offset = 0.6 * float(np.median(ranges)) if ranges else 1.0
            if offset <= 0.0:
                offset = 1.0

        for i, (sp, y, color) in enumerate(zip(sel_spectra, ys, colors)):
            x = np.asarray(sp.get('original_x_scale', sp['x_scale']), float)
            baseline = i * offset
            ln, = ax.plot(x, y + baseline, color=color, linewidth=0.8)
            lines.append(ln)
            labels.append(self.labels[orig_indices[i]])

        self._add_legend(ax, lines, labels)
        self._shading_kwargs(ax)
        ax.set_xlabel("Wavenumber / x", fontsize=8)
        ax.set_ylabel(f"Intensity  (offset {offset:.4g}/trace)", fontsize=8)
        ax.set_title(f"{len(sel_spectra)} spectra (waterfall)", fontsize=9)
        ax.tick_params(labelsize=7)
        self._lines = lines

    def _plot_heatmap(self, sel_spectra, orig_indices):
        """Spectra as image rows: y = spectrum, x = wavenumber, colour = intensity."""
        ax = self._fig.add_subplot(111)
        self._axes = [ax]
        self._lines = []

        if not sel_spectra:
            return

        x_ref = np.asarray(
            sel_spectra[0].get('original_x_scale', sel_spectra[0]['x_scale']), float)
        mismatched = [
            sp.get('label', '?') for sp in sel_spectra[1:]
            if len(np.asarray(sp.get('original_x_scale', sp['x_scale']), float)) == len(x_ref)
            and not axes_match(
                np.asarray(sp.get('original_x_scale', sp['x_scale']), float), x_ref)
        ]
        if mismatched:
            # Same refuse-and-name-them convention as Average/Export/
            # SVD/Cluster elsewhere in the app — combining spectra onto
            # one shared axis is exactly the kind of thing that should
            # never happen silently, even via interpolation.
            QMessageBox.warning(
                self, "Cannot build heatmap",
                f"Spectra don't share a common x-axis (mismatched: "
                f"{', '.join(mismatched[:5])}"
                f"{'…' if len(mismatched) > 5 else ''}).\n"
                "Use Data Range to put them on a common axis first, then "
                "try again."
            )
            ax.text(0.5, 0.5, "Mismatched x-axis — see warning.",
                    ha='center', va='center', transform=ax.transAxes, color='#888')
            ax.set_axis_off()
            return

        rows = [np.asarray(sp.get('original_y_scale', sp['y_scale']), float)
                for sp in sel_spectra]
        if not rows:
            return

        mat = np.vstack(rows)
        cmap = self._heatmap_cmap_combo.currentText()
        extent = [x_ref[0], x_ref[-1], len(rows) - 0.5, -0.5] if x_ref.size else None
        im = ax.imshow(mat, aspect='auto', cmap=cmap, extent=extent,
                        interpolation='nearest')
        cb = self._fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
        cb.set_label("Intensity", fontsize=7)
        cb.ax.tick_params(labelsize=6)

        labels = [self.labels[i] for i in orig_indices[:len(rows)]]
        # Evenly-spaced y-tick indices, capped at max_ticks and always
        # including the first and last row. The previous floor-division
        # step (len // max_ticks) stayed at 1 for any n up to 2*max_ticks
        # - 1, so e.g. 59 spectra still showed all 59 labels; this
        # spans the full range evenly instead, so the true label count
        # never exceeds max_ticks regardless of n, with no such gap.
        max_ticks = 30
        n_labels = len(labels)
        if n_labels <= max_ticks:
            tick_idx = list(range(n_labels))
        else:
            tick_idx = sorted(set(
                int(round(i)) for i in
                np.linspace(0, n_labels - 1, max_ticks)))
        ax.set_yticks(tick_idx)
        ax.set_yticklabels([labels[i] for i in tick_idx], fontsize=6)
        ax.set_xlabel("Wavenumber / x", fontsize=8)
        ax.set_title(f"{len(rows)} spectra (heatmap)", fontsize=9)
        ax.tick_params(labelsize=7)

    def _plot_difference(self, sel_spectra, colors, orig_indices):
        """Each selected spectrum minus a chosen reference spectrum."""
        ax = self._fig.add_subplot(111)
        self._axes = [ax]
        lines = []

        self._refresh_diff_ref_combo()
        ref_label = self._diff_ref_combo.currentText()
        if not ref_label:
            ax.text(0.5, 0.5, "No reference spectrum available.",
                    ha='center', va='center', transform=ax.transAxes, color='#888')
            ax.set_axis_off()
            return

        ref_idx = self.labels.index(ref_label) if ref_label in self.labels else None
        if ref_idx is None:
            return
        ref_sp = self.spectra[ref_idx]
        x_ref = np.asarray(ref_sp.get('original_x_scale', ref_sp['x_scale']), float)
        y_ref = np.asarray(ref_sp.get('original_y_scale', ref_sp['y_scale']), float)

        mismatched = [
            sp.get('label', '?') for sp in sel_spectra
            if sp is not ref_sp
            and len(np.asarray(sp.get('original_x_scale', sp['x_scale']), float)) == len(x_ref)
            and not axes_match(
                np.asarray(sp.get('original_x_scale', sp['x_scale']), float), x_ref)
        ]
        if mismatched:
            # Same refuse-and-name-them convention as Average/Export/
            # SVD/Cluster elsewhere in the app, rather than silently
            # interpolating spectra onto the reference's axis before
            # subtracting them.
            QMessageBox.warning(
                self, "Cannot compute differences",
                f"Spectra don't share a common x-axis with the reference "
                f"'{ref_label}' (mismatched: {', '.join(mismatched[:5])}"
                f"{'…' if len(mismatched) > 5 else ''}).\n"
                "Use Data Range to put them on a common axis first, then "
                "try again."
            )
            ax.text(0.5, 0.5, "Mismatched x-axis — see warning.",
                    ha='center', va='center', transform=ax.transAxes, color='#888')
            ax.set_axis_off()
            return

        labels = []

        for sp, color, oi in zip(sel_spectra, colors, orig_indices):
            if sp is ref_sp:
                continue
            y = np.asarray(sp.get('original_y_scale', sp['y_scale']), float)
            ln, = ax.plot(x_ref, y - y_ref, color=color,
                          linewidth=0.7, alpha=0.8)
            lines.append(ln)
            labels.append(self.labels[oi])

        self._add_legend(ax, lines, labels)
        ax.axhline(0, color='#333', linewidth=0.8, linestyle='--')
        self._shading_kwargs(ax)
        ax.set_xlabel("Wavenumber / x", fontsize=8)
        ax.set_ylabel("Intensity difference", fontsize=8)
        title = f"{len(lines)} spectra minus '{ref_label}'"
        if getattr(self, '_diff_ref_auto_switched', False):
            title += "  — reference auto-switched (previous choice no longer selected)"
        ax.set_title(title, fontsize=9)
        ax.tick_params(labelsize=7)
        self._lines = lines

    # ------------------------------------------------------------------ #

    def _on_highlight(self, row):
        """Bold-highlight a spectrum in overlay mode."""
        if not self._axes or not self._lines:
            return
        for i, line in enumerate(self._lines):
            line.set_linewidth(2.0 if i == row else 0.7)
            line.set_alpha(1.0 if i == row else 0.35)
        self._canvas.draw_idle()

    def _send_to_main_list(self):
        """Send selected spectra (or their average) to the main spectrum list."""
        if self.map2d_controller is None:
            QMessageBox.warning(self, "Not available",
                                "No connection to the main spectrum list.")
            return
        indices = self._selected_row_indices()
        if not indices:
            QMessageBox.information(self, "Nothing selected",
                                    "Select at least one spectrum in the list.")
            return

        sel_spectra = [self.spectra[i] for i in indices]

        # Ask the user what to send
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QRadioButton, \
            QButtonGroup, QLineEdit, QDialogButtonBox, QLabel as _QLabel

        dlg = QDialog(self)
        dlg.setWindowTitle("Send to main list")
        lay = QVBoxLayout(dlg)

        lay.addWidget(_QLabel(
            f"<b>{len(sel_spectra)}</b> spectra selected.<br>"
            "What would you like to send to the main spectrum list?"
        ))

        rb_all = QRadioButton(
            f"All {len(sel_spectra)} spectra individually")
        rb_avg = QRadioButton("Average of the selected spectra")
        rb_all.setChecked(True)
        grp = QButtonGroup(dlg)
        grp.addButton(rb_all)
        grp.addButton(rb_avg)
        lay.addWidget(rb_all)
        lay.addWidget(rb_avg)

        lay.addWidget(_QLabel("Label / prefix for new spectra:"))
        name_edit = QLineEdit("ROI")
        lay.addWidget(name_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted:
            return

        prefix = name_edit.text().strip() or "ROI"

        if rb_avg.isChecked():
            # Build average spectrum
            import numpy as _np
            x_ref = _np.asarray(
                sel_spectra[0].get('original_x_scale',
                                   sel_spectra[0]['x_scale']),
                dtype=float)
            mismatched = [
                sp.get('label', '?') for sp in sel_spectra[1:]
                if len(_np.asarray(sp.get('original_x_scale', sp['x_scale']), dtype=float)) == len(x_ref)
                and not axes_match(
                    _np.asarray(sp.get('original_x_scale', sp['x_scale']), dtype=float), x_ref)
            ]
            if mismatched:
                QMessageBox.warning(
                    self, "Cannot average",
                    f"Spectra don't share a common x-axis (mismatched: "
                    f"{', '.join(mismatched[:5])}"
                    f"{'…' if len(mismatched) > 5 else ''}).\n"
                    "Send them individually instead, or use Data Range to "
                    "put them on a common axis first."
                )
                return
            try:
                y_mat = _np.vstack([
                    _np.asarray(sp.get('original_y_scale', sp['y_scale']),
                                dtype=float)
                    for sp in sel_spectra])
                y_avg = _np.mean(y_mat, axis=0)
            except ValueError:
                QMessageBox.warning(
                    self, "Cannot average",
                    "Spectra have different lengths — cannot compute average.\n"
                    "Send them individually instead.")
                return
            avg_sp = {
                'x_scale': x_ref,
                'y_scale': y_avg,
                'label':   prefix,
                'metadata': {'source': f'Average of {len(sel_spectra)} ROI spectra'},
            }
            to_send = [avg_sp]
        else:
            # Tag each spectrum with the prefix. A cheap shallow copy is
            # enough here — just to set a new label without mutating the
            # original — since send_spectra_to_main_list() already does
            # its own proper, independent copy of everything it actually
            # stores; copy.deepcopy()'ing here too was pure duplicated
            # work, immediately thrown away and redone.
            to_send = []
            for sp in sel_spectra:
                new_sp = dict(sp)
                # Replace label prefix if the original label differs
                new_sp['label'] = prefix + '_' + sp.get('label', 'sp')
                to_send.append(new_sp)

        n = self.map2d_controller.send_spectra_to_main_list(
            to_send, label_prefix=prefix, source_spectra=self.spectra)
        QMessageBox.information(
            self, "Done",
            f"{n} spectrum/spectra added to the main list.\n"
            f"They are now available for all processing operations.")

    def _export(self):
        """Export selected spectra to CSV."""
        indices = self._selected_row_indices()
        if not indices:
            QMessageBox.information(self, "Export", "No spectra selected.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export ROI spectra", "", "CSV file (*.csv)")
        if not path:
            return
        if not path.endswith('.csv'):
            path += '.csv'
        try:
            rows = []
            header_written = False
            for i in indices:
                sp = self.spectra[i]
                x  = np.asarray(sp.get('original_x_scale', sp['x_scale']), float)
                y  = np.asarray(sp.get('original_y_scale', sp['y_scale']), float)
                if not header_written:
                    rows.append(['x'] + [self.labels[j] for j in indices])
                    header_written = True
                rows.append(np.concatenate([[x[0]], y[:1]]))  # placeholder
            # Build full matrix: rows = x-points, cols = spectra
            x_ref = np.asarray(
                self.spectra[indices[0]].get(
                    'original_x_scale', self.spectra[indices[0]]['x_scale']), float)
            mismatched = []
            for i in indices[1:]:
                xi = np.asarray(self.spectra[i].get(
                    'original_x_scale', self.spectra[i]['x_scale']), float)
                if len(xi) == len(x_ref) and not axes_match(xi, x_ref):
                    mismatched.append(self.labels[i])
            if mismatched:
                QMessageBox.warning(
                    self, "Cannot export",
                    f"Spectra don't share a common x-axis (mismatched: "
                    f"{', '.join(mismatched[:5])}"
                    f"{'…' if len(mismatched) > 5 else ''}).\n"
                    "A single shared 'x' column would mislabel their actual "
                    "wavenumber positions. Export them individually instead, "
                    "or use Data Range to put them on a common axis first."
                )
                return
            mat = np.column_stack([
                np.asarray(self.spectra[i].get(
                    'original_y_scale', self.spectra[i]['y_scale']), float)
                for i in indices])
            header = 'x,' + ','.join(self.labels[i] for i in indices)
            data   = np.column_stack([x_ref, mat])
            np.savetxt(path, data, delimiter=',', header=header, comments='')
            QMessageBox.information(self, "Export",
                                    f"Saved {len(indices)} spectra to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def closeEvent(self, event):
        try:
            plt.close(self._fig)
        except Exception:
            pass
        super().closeEvent(event)
