# src/views/dialogs/visualization_analysis/spectral_range_dialog.py

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup,
    QLineEdit, QSpinBox, QCheckBox, QDialogButtonBox,
    QAbstractItemView, QGroupBox, QComboBox, QSizePolicy,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QDoubleValidator

import matplotlib
matplotlib.use('Agg')
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)


def _evenly_spaced(spectra, n):
    if not spectra:
        return []
    total = len(spectra)
    if total <= n:
        return list(spectra)
    if n == 1:
        return [spectra[total // 2]]
    indices = [int(round(i * (total - 1) / (n - 1))) for i in range(n)]
    return [spectra[i] for i in indices]


_HELP_TEXT = """<html><head><style>
body { font-family: Arial, sans-serif; font-size: 12px; margin: 12px; line-height: 1.5; }
h2   { color: #1565C0; margin-top: 10px; }
h3   { color: #E65100; margin-top: 8px; margin-bottom: 2px; }
.tip { background:#E8F5E9; border-left:4px solid #2E7D32; padding:6px 10px; margin:6px 0; }
.kb  { font-family:monospace; background:#ececec; padding:1px 4px; border-radius:3px; }
</style></head><body>

<h2>Define Spectral Range — Quick Guide</h2>

<h3>Adding ranges</h3>
<ul>
  <li><b>Draw on plot:</b> make sure <b>✏ Draw ranges</b> is active (blue),
      then click and drag on the spectrum plot. Release to add the range.</li>
  <li><b>Type values:</b> enter From / To values and click <b>Add</b>.</li>
  <li>Both methods update the From / To fields so you can fine-tune after drawing.
      Drawn values are rounded to 4 decimal places.</li>
</ul>

<h3>Editing a range</h3>
<ul>
  <li>Click a range in the list — the From / To fields are populated with its values,
      and the <b>Add</b> button becomes <b>Update</b>.</li>
  <li>Edit the fields and click <b>Update</b> to change that range in place.</li>
  <li><b>Cancel edit</b>, right next to Update, deselects the range and goes back
      to adding a new one without changing anything.</li>
  <li>Adding or updating a range to values that exactly match another range
      already in the list is not allowed — the existing one is selected instead
      of creating a duplicate.</li>
</ul>

<h3>Removing ranges</h3>
<ul>
  <li>Click a range, or Ctrl/Shift-click several, then click <b>Remove</b> to
      delete just the selected one(s).</li>
  <li><b>Clear</b> removes every range at once.</li>
</ul>

<h3>Include vs Exclude</h3>
<ul>
  <li><b>Include:</b> only the listed ranges are used (blue shading).</li>
  <li><b>Exclude:</b> the listed ranges are removed; everything else is used
      (red shading). Useful for cutting out an interfering peak from a broad band.</li>
</ul>

<h3>Zoom / Pan vs Draw</h3>
<ul>
  <li>Toggle <b>✏ Draw ranges</b> off to use the toolbar zoom and pan tools freely.</li>
  <li>Toggle it back on to draw new ranges. Your zoom state is preserved.</li>
</ul>

<h3>Spectrum display</h3>
<ul>
  <li><b>Evenly spaced + Average (default):</b> shows a representative sample
      of spectra plus a black average line. Best for large datasets.</li>
  <li><b>Single spectrum:</b> select a specific spectrum from the dropdown.
      Evenly-spaced and average controls are greyed out — only the selected
      spectrum is shown. Useful when a specific spectrum has the band of
      interest and you want to define the range precisely.</li>
</ul>

<div class="tip">
  <b>Tip:</b> zoom into the region of interest first (Draw ranges off),
  then switch Draw ranges on and drag to mark the band precisely.
  The zoom is preserved when you switch modes.
</div>
</body></html>"""


class SpectralRangeDialog(QDialog):
    """
    Band range definition dialog for 2D spectral map / band ratio.

    Attributes after exec_():
        _ranges     : list of [lo, hi]
        _is_exclude : bool
    """

    def __init__(self, parent=None, all_spectra=None,
                 current_ranges=None, is_exclude=False,
                 band_label="Band", band_color='#1565C0'):
        super().__init__(parent)
        self.setWindowTitle(f"Define Spectral Range \u2014 {band_label}")
        self.setMinimumWidth(620)
        self.setMinimumHeight(580)
        self.resize(780, 680)
        # No WindowMinimizeButtonHint — this dialog is always modal (opened
        # via exec_()), so minimizing it would leave the whole app blocked
        # behind a taskbar entry with no visible sign anything is still
        # open — easy to mistake for a frozen app. Maximize stays available.
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)
        # Fix issue 4: prevent geometry changes on move by using fixed initial size hint
        self.setMaximumHeight(16777215)  # restore unlimited after first show

        self._all_spectra  = all_spectra or []
        self._ranges       = [list(r) for r in (current_ranges or [])]
        self._is_exclude   = is_exclude
        self._band_color   = band_color
        self._n_preview    = min(6, len(self._all_spectra))
        self._draw_mode    = True
        self._preview_drawn = False
        self._single_idx   = None   # index into _all_spectra for single spectrum view

        # When a range in self._list is selected, its bounds are loaded
        # into the From/To fields and this tracks which row is being
        # edited, so the "Add" button (relabeled "Update") updates that
        # entry in place instead of appending a duplicate. None means
        # "not currently editing an existing range" — same pattern as
        # normalization_dialog.py's region editing.
        self._editing_row = None

        self._n_timer = QTimer(self)
        self._n_timer.setSingleShot(True)
        self._n_timer.setInterval(400)
        self._n_timer.timeout.connect(self._refresh_preview)

        self._build_ui()
        self._refresh_list()
        self._refresh_preview()

    # ------------------------------------------------------------------ #
    # UI construction                                                       #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Spectral ranges groupbox (Mode + list + entry) ────────────────
        self._ranges_grp = QGroupBox("Spectral ranges")
        self._ranges_grp.setSizePolicy(
            __import__('PyQt5.QtWidgets', fromlist=['QSizePolicy']).QSizePolicy.Expanding,
            __import__('PyQt5.QtWidgets', fromlist=['QSizePolicy']).QSizePolicy.Expanding,
        )
        ranges_grp = self._ranges_grp
        ranges_lay = QVBoxLayout(ranges_grp)

        # Mode row + help button
        mode_row = QHBoxLayout()
        self._rb_include = QRadioButton("Include \u2014 use only the listed ranges")
        self._rb_exclude = QRadioButton("Exclude \u2014 remove the listed ranges")
        self._rb_include.setChecked(not self._is_exclude)
        self._rb_exclude.setChecked(self._is_exclude)
        bg = QButtonGroup(self)
        bg.addButton(self._rb_include)
        bg.addButton(self._rb_exclude)
        mode_row.addWidget(self._rb_include)
        mode_row.addWidget(self._rb_exclude)
        mode_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedWidth(32)
        help_btn.setFixedHeight(24)
        help_btn.setFlat(False)
        help_btn.setToolTip("Show help for this dialog")
        help_btn.setStyleSheet(
            "QPushButton { font-weight:bold; border-radius:11px; "
            "background:#1565C0; color:white; }"
            "QPushButton:hover { background:#1976D2; }"
        )
        help_btn.clicked.connect(self._show_help)
        mode_row.addWidget(help_btn)
        ranges_lay.addLayout(mode_row)

        # Range list — ExtendedSelection so Ctrl/Shift-click can select
        # several ranges at once for bulk removal (see _on_remove). Editing
        # a single range (populating From/To, switching Add -> Update)
        # only activates when EXACTLY one row is selected — see
        # _on_list_selection_changed.
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list.setSizePolicy(
            __import__('PyQt5.QtWidgets', fromlist=['QSizePolicy']).QSizePolicy.Expanding,
            __import__('PyQt5.QtWidgets', fromlist=['QSizePolicy']).QSizePolicy.Expanding,
        )
        self._list.itemSelectionChanged.connect(self._on_list_selection_changed)
        ranges_lay.addWidget(self._list, stretch=1)

        self._empty_hint = QLabel(
            "\u26a0  No ranges defined \u2014 please add at least one range."
        )
        self._empty_hint.setStyleSheet('color:#C62828; font-size:8pt; padding:4px;')
        self._empty_hint.setAlignment(Qt.AlignCenter)
        ranges_lay.addWidget(self._empty_hint)

        # Entry row
        entry_row = QHBoxLayout()
        entry_row.addWidget(QLabel("From:"))
        self._edit_from = QLineEdit()
        self._edit_from.setFixedWidth(90)
        self._edit_from.setValidator(QDoubleValidator(-1e9, 1e9, 6))
        self._edit_from.setPlaceholderText("x start")
        entry_row.addWidget(self._edit_from)
        entry_row.addWidget(QLabel("To:"))
        self._edit_to = QLineEdit()
        self._edit_to.setFixedWidth(90)
        self._edit_to.setValidator(QDoubleValidator(-1e9, 1e9, 6))
        self._edit_to.setPlaceholderText("x end")
        entry_row.addWidget(self._edit_to)
        # No setFixedWidth on _btn_add — its text toggles between "Add" and
        # "Update", and a fixed width sized for "Add" truncated "Update".
        # Letting it size itself to its own text avoids that regardless of
        # what the text says.
        self._btn_add = QPushButton("Add")
        self._btn_add.setToolTip(
            "Add the From / To values entered above as a new range.\n"
            "Drag on the plot to add ranges without using this button."
        )
        entry_row.addWidget(self._btn_add)
        # Cancel edit sits right next to Add/Update — while editing, this
        # is the button you actually reach for, not something at the far
        # end of the row past Remove/Clear.
        self._btn_cancel_edit = QPushButton("Cancel edit")
        self._btn_cancel_edit.setToolTip("Deselect the range and go back to adding a new one.")
        self._btn_cancel_edit.setVisible(False)
        entry_row.addWidget(self._btn_cancel_edit)
        self._btn_remove = QPushButton("Remove"); self._btn_remove.setFixedWidth(65)
        self._btn_remove.setToolTip(
            "Remove the selected range(s).\nCtrl/Shift-click ranges in the list to select more than one."
        )
        self._btn_clear  = QPushButton("Clear");  self._btn_clear.setFixedWidth(55)
        entry_row.addWidget(self._btn_remove)
        entry_row.addWidget(self._btn_clear)
        entry_row.addStretch()
        ranges_lay.addLayout(entry_row)
        root.addWidget(ranges_grp)

        # ── Preview ───────────────────────────────────────────────────
        preview_grp = QGroupBox("Preview")
        preview_grp.setSizePolicy(
            __import__('PyQt5.QtWidgets', fromlist=['QSizePolicy']).QSizePolicy.Expanding,
            __import__('PyQt5.QtWidgets', fromlist=['QSizePolicy']).QSizePolicy.Expanding,
        )
        preview_lay = QVBoxLayout(preview_grp)

        # Controls row 1: evenly spaced + average + draw toggle
        ctrl_row = QHBoxLayout()
        self._show_label = QLabel("Show")
        ctrl_row.addWidget(self._show_label)
        self._n_spin = QSpinBox()
        self._n_spin.setRange(1, max(1, len(self._all_spectra)))
        self._n_spin.setValue(self._n_preview)
        self._n_spin.setFixedWidth(55)
        ctrl_row.addWidget(self._n_spin)
        self._evenly_spaced_label = QLabel("evenly spaced")
        ctrl_row.addWidget(self._evenly_spaced_label)
        ctrl_row.addSpacing(10)
        self._avg_cb = QCheckBox("Average")
        self._avg_cb.setChecked(True)
        ctrl_row.addWidget(self._avg_cb)
        ctrl_row.addStretch()

        self._hide_ranges_cb = QCheckBox("Hide ranges info")
        self._hide_ranges_cb.setChecked(False)
        self._hide_ranges_cb.setToolTip(
            "Hide the Spectral ranges panel to give more space to the preview."
        )
        self._hide_ranges_cb.stateChanged.connect(self._on_hide_ranges_toggled)
        ctrl_row.addWidget(self._hide_ranges_cb)

        self._draw_btn = QPushButton("\u270f Draw ranges")
        self._draw_btn.setCheckable(True)
        self._draw_btn.setChecked(True)
        self._draw_btn.setFixedWidth(110)
        self._draw_btn.setToolTip(
            "When active: click and drag on the plot to add a range.\n"
            "Deactivate to use the toolbar zoom/pan tools freely."
        )
        self._draw_btn.setStyleSheet(
            "QPushButton:checked { background-color:#1976D2; color:white; "
            "font-weight:bold; border-radius:3px; }"
        )
        self._draw_btn.toggled.connect(self._on_draw_mode_toggled)
        ctrl_row.addWidget(self._draw_btn)
        preview_lay.addLayout(ctrl_row)

        # Controls row 2: single spectrum selector
        single_row = QHBoxLayout()
        single_row.addWidget(QLabel("Single spectrum:"))
        self._single_combo = QComboBox()
        self._single_combo.addItem("— none —")
        for s in self._all_spectra:
            self._single_combo.addItem(s['label'])
        self._single_combo.setMaximumWidth(300)
        self._single_combo.setToolTip(
            "Overlay a single spectrum on the preview in addition to "
            "the evenly spaced sample."
        )
        self._single_combo.currentIndexChanged.connect(self._on_single_changed)
        single_row.addWidget(self._single_combo)
        single_row.addStretch()
        preview_lay.addLayout(single_row)

        self._fig    = Figure(dpi=96, figsize=(7, 3))
        self._fig.subplots_adjust(left=0.08, right=0.98, top=0.92, bottom=0.12)
        self._ax     = self._fig.add_subplot(111)
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._canvas.setMinimumHeight(180)
        self._canvas.setSizePolicy(
            __import__('PyQt5.QtWidgets', fromlist=['QSizePolicy']).QSizePolicy.Expanding,
            __import__('PyQt5.QtWidgets', fromlist=['QSizePolicy']).QSizePolicy.Expanding,
        )
        self._toolbar = NavigationToolbar(self._canvas, preview_grp)
        preview_lay.addWidget(self._toolbar)
        preview_lay.addWidget(self._canvas)

        self._hint_label = QLabel(
            "Draw ranges: click and drag (blue\u202f=\u202finclude, red\u202f=\u202fexclude).  "
            "Disable Draw ranges to zoom/pan freely."
        )
        self._hint_label.setStyleSheet("font-size:8pt; color:#555;")
        self._hint_label.setWordWrap(False)
        self._hint_label.setSizePolicy(
            __import__('PyQt5.QtWidgets', fromlist=['QSizePolicy']).QSizePolicy.Preferred,
            __import__('PyQt5.QtWidgets', fromlist=['QSizePolicy']).QSizePolicy.Fixed,
        )
        preview_lay.addWidget(self._hint_label)
        root.addWidget(preview_grp)

        # ── OK / Cancel ───────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self._ok_btn = btns.button(QDialogButtonBox.Ok)
        root.addWidget(btns)

        # ── Connections ───────────────────────────────────────────────
        self._btn_add.clicked.connect(self._on_add)
        self._btn_remove.clicked.connect(self._on_remove)
        self._btn_clear.clicked.connect(self._on_clear)
        self._btn_cancel_edit.clicked.connect(self._cancel_edit)
        self._rb_include.toggled.connect(self._on_mode_toggled)
        self._rb_exclude.toggled.connect(self._on_mode_toggled)
        self._n_spin.valueChanged.connect(lambda _: self._n_timer.start())
        self._avg_cb.stateChanged.connect(lambda _: self._refresh_preview())

        # Drag-to-select
        self._drag_start = None
        self._drag_span  = None
        self._canvas.mpl_connect('button_press_event',   self._on_press)
        self._canvas.mpl_connect('motion_notify_event',  self._on_motion)
        self._canvas.mpl_connect('button_release_event', self._on_release)

        self._seed_fields()

    def _seed_fields(self):
        if not self._all_spectra:
            return
        xs = np.asarray(self._all_spectra[0]['x_scale'], dtype=float)
        if len(xs) < 2:
            return
        mid   = float((xs[0] + xs[-1]) / 2)
        delta = float(abs(xs[-1] - xs[0])) * 0.1
        self._edit_from.setText(f"{round(mid - delta, 1)}")
        self._edit_to.setText(f"{round(mid + delta, 1)}")

    # ------------------------------------------------------------------ #
    # Range management                                                      #
    # ------------------------------------------------------------------ #

    def _read_fields(self):
        try:
            lo = float(self._edit_from.text().replace(',', '.'))
            hi = float(self._edit_to.text().replace(',', '.'))
        except ValueError:
            return None
        if abs(hi - lo) < 1e-6:
            return None
        return min(lo, hi), max(lo, hi)

    def _find_duplicate_row(self, lo, hi, exclude_row=None):
        """Return the index of an existing range with the same (lo, hi)
        bounds (within floating-point tolerance), other than exclude_row —
        or None if there isn't one. Used to stop Add/Update/drag from
        ever creating an exact duplicate entry."""
        for i, (existing_lo, existing_hi) in enumerate(self._ranges):
            if i == exclude_row:
                continue
            if abs(existing_lo - lo) < 1e-9 and abs(existing_hi - hi) < 1e-9:
                return i
        return None

    def _on_add(self):
        pair = self._read_fields()
        if pair is None:
            return
        lo, hi = pair
        if self._editing_row is not None and 0 <= self._editing_row < len(self._ranges):
            dup = self._find_duplicate_row(lo, hi, exclude_row=self._editing_row)
            if dup is not None:
                # Updating to values that exactly match another existing
                # range would create a duplicate — select that range
                # instead of creating one.
                self._refresh_list(select_row=dup)
                return
            self._ranges[self._editing_row] = [lo, hi]
            self._ranges.sort(key=lambda r: r[0])
            # Sorting can move the just-updated entry to a different row —
            # find it again so it stays selected (sticky editing, so
            # further tweaks don't require reselecting).
            try:
                new_row = self._ranges.index([lo, hi])
            except ValueError:
                new_row = None
            self._refresh_list(select_row=new_row)
        else:
            dup = self._find_duplicate_row(lo, hi)
            if dup is not None:
                self._refresh_list(select_row=dup)
                return
            self._ranges.append([lo, hi])
            self._ranges.sort(key=lambda r: r[0])
            self._refresh_list()
        self._refresh_preview()

    def _on_remove(self):
        """Remove every currently-selected range — Ctrl/Shift-click in the
        list first to remove more than one at a time."""
        rows = sorted({self._list.row(it) for it in self._list.selectedItems()}, reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self._ranges):
                self._ranges.pop(row)
        self._refresh_list()
        self._refresh_preview()

    def _on_clear(self):
        self._ranges.clear()
        self._refresh_list()
        self._refresh_preview()

    def _cancel_edit(self):
        """Explicitly leave edit mode without removing or changing the
        selected range — used by the 'Cancel edit' button, since clicking
        empty space in the list does not reliably clear its selection."""
        self._list.clearSelection()
        self._exit_edit_mode()

    def _exit_edit_mode(self):
        self._editing_row = None
        self._btn_add.setText('Add')
        self._btn_add.setToolTip(
            "Add the From / To values entered above as a new range.\n"
            "Drag on the plot to add ranges without using this button."
        )
        self._btn_cancel_edit.setVisible(False)

    def _on_mode_toggled(self):
        self._is_exclude = self._rb_exclude.isChecked()
        self._refresh_preview()

    def _on_list_selection_changed(self):
        """Editing (populating From/To, switching Add -> Update) only
        activates when exactly one range is selected — with several
        selected (for bulk Remove, see _on_remove) there's no single
        range for From/To/Update to mean anything about."""
        selected = self._list.selectedItems()
        if len(selected) == 1:
            row = self._list.row(selected[0])
            if 0 <= row < len(self._ranges):
                lo, hi = self._ranges[row]
                # Values are stored already rounded (see _on_release), so
                # displaying them as-is (not re-rounded here) doesn't
                # coarsen anything on re-edit — it just shows what's
                # already stored.
                self._edit_from.setText(str(lo))
                self._edit_to.setText(str(hi))
                self._editing_row = row
                self._btn_add.setText('Update')
                self._btn_add.setToolTip(
                    'Update the selected range with the From / To values above.'
                )
                self._btn_cancel_edit.setVisible(True)
                return
        self._exit_edit_mode()

    def _on_single_changed(self, idx):
        # idx 0 = "— none —", idx 1+ = spectrum
        self._single_idx = idx - 1 if idx > 0 else None
        single_active = self._single_idx is not None
        # Disable and visually grey out evenly-spaced controls
        self._n_spin.setEnabled(not single_active)
        self._avg_cb.setEnabled(not single_active)
        grey   = "color: #aaa;"
        normal = ""
        self._n_spin.setStyleSheet(
            "QSpinBox { color: #aaa; background: #f0f0f0; }" if single_active else ""
        )
        self._show_label.setStyleSheet(grey if single_active else normal)
        self._evenly_spaced_label.setStyleSheet(grey if single_active else normal)
        self._avg_cb.setStyleSheet(grey if single_active else normal)
        self._refresh_preview()

    def _on_hide_ranges_toggled(self, state):
        hide = (state == Qt.Checked)
        self._ranges_grp.setVisible(not hide)
        self._hint_label.setVisible(not hide)

    def _on_draw_mode_toggled(self, checked):
        self._draw_mode = checked
        if checked:
            if hasattr(self._toolbar, 'mode') and self._toolbar.mode:
                if 'zoom' in str(self._toolbar.mode).lower():
                    self._toolbar.zoom()
                elif 'pan' in str(self._toolbar.mode).lower():
                    self._toolbar.pan()

    def _refresh_list(self, select_row=None):
        self._list.clear()
        for lo, hi in self._ranges:
            self._list.addItem(QListWidgetItem(f"  {lo:.1f}  \u2013  {hi:.1f}"))
        has_ranges = bool(self._ranges)
        self._list.setVisible(has_ranges)
        self._empty_hint.setVisible(not has_ranges)
        # Block OK only if opened with no ranges and none yet added
        if has_ranges:
            self._ranges_ever_added = True
            self._ok_btn.setEnabled(True)
        else:
            self._ok_btn.setEnabled(getattr(self, '_ranges_ever_added', False))
        if select_row is not None and 0 <= select_row < self._list.count():
            self._list.setCurrentRow(select_row)
        else:
            # QListWidget.clear() doesn't reliably re-emit
            # itemSelectionChanged, so explicitly drop out of edit mode
            # rather than relying on it.
            self._exit_edit_mode()

    # ------------------------------------------------------------------ #
    # Preview                                                              #
    # ------------------------------------------------------------------ #

    def _refresh_preview(self):
        n = self._n_spin.value()
        preview = _evenly_spaced(self._all_spectra, n)

        xlim = self._ax.get_xlim()
        ylim = self._ax.get_ylim()
        was_zoomed = self._preview_drawn

        self._ax.cla()
        mode_label = 'Exclude' if self._is_exclude else 'Include'
        shade_color = '#C62828' if self._is_exclude else self._band_color

        x_ref = None

        single_active = self._single_idx is not None

        if single_active and 0 <= self._single_idx < len(self._all_spectra):
            sp = self._all_spectra[self._single_idx]
            x  = np.asarray(sp['x_scale'], dtype=float)
            y  = np.asarray(sp['y_scale'], dtype=float)
            self._ax.plot(x, y, color='#1976D2', linewidth=1.2, alpha=0.9,
                          zorder=4, label=sp['label'])
            x_ref = x
        else:
            # Evenly spaced spectra
            for sp in preview:
                x = np.asarray(sp['x_scale'], dtype=float)
                y = np.asarray(sp['y_scale'], dtype=float)
                self._ax.plot(x, y, color='#999', linewidth=0.6, alpha=0.65)
                if x_ref is None:
                    x_ref = x

        # Average spectrum (only in evenly spaced mode)
        if not single_active and self._avg_cb.isChecked() and self._all_spectra:
            from src.modules.utils.spectra_validation import axes_match
            avg_x_ref = np.asarray(self._all_spectra[0]['x_scale'], dtype=float)
            # Only spectra that genuinely share avg_x_ref's axis go into the
            # average — previously this vstacked every selected spectrum's
            # y_scale unconditionally, wrapped only in a bare try/except.
            # That silently produces one of two wrong outcomes depending on
            # what's selected: if lengths differ, vstack raises and the
            # except swallows it (no average shown at all, not misleading,
            # but also no explanation why); if lengths happen to MATCH
            # while the actual x-values differ (e.g. two spectra with the
            # same point count on completely different ranges), vstack
            # succeeds and a fabricated "Average" line — drawn bold and
            # black, the same as the average of REAL matching data — gets
            # plotted with no indication anything was mixed.
            matching = [
                sp for sp in self._all_spectra
                if axes_match(avg_x_ref, np.asarray(sp['x_scale'], dtype=float))
            ]
            n_excluded = len(self._all_spectra) - len(matching)
            if matching:
                try:
                    all_y = np.vstack([
                        np.asarray(sp['y_scale'], dtype=float)
                        for sp in matching
                    ])
                    avg_y = np.mean(all_y, axis=0)
                    if x_ref is None:
                        x_ref = avg_x_ref
                    avg_label = 'Average' if n_excluded == 0 else f'Average ({len(matching)} matching-axis spectra)'
                    self._ax.plot(x_ref, avg_y, color='#111', linewidth=1.4,
                                  label=avg_label, zorder=5)
                    if n_excluded > 0:
                        self._ax.text(
                            0.5, 1.06,
                            f'\u26a0 {n_excluded} spectrum/spectra excluded from Average '
                            f'\u2014 different x-axis than the first spectrum',
                            transform=self._ax.transAxes, ha='center', fontsize=6.5,
                            color='#C62828')
                except Exception:
                    # The preview just shows no Average line -- log why.
                    logger.warning("Could not draw the Average in the range preview", exc_info=True)

        if single_active or self._avg_cb.isChecked():
            self._ax.legend(fontsize=7, loc='upper right', framealpha=0.7)

        # Shade ranges
        def _merge(ranges):
            if not ranges: return []
            s = sorted(ranges, key=lambda r: r[0])
            m = [list(s[0])]
            for lo, hi in s[1:]:
                if lo <= m[-1][1]:
                    m[-1][1] = max(m[-1][1], hi)
                else:
                    m.append([lo, hi])
            return m

        for lo, hi in _merge(self._ranges):
            self._ax.axvspan(lo, hi,
                             alpha=0.18 if self._is_exclude else 0.22,
                             color=shade_color, linewidth=0)

        single_info = self._single_idx is not None and 0 <= self._single_idx < len(self._all_spectra)
        total = len(self._all_spectra)
        self._ax.set_xlabel("x", fontsize=8)
        self._ax.tick_params(labelsize=7)
        if single_info:
            sp_name    = self._all_spectra[self._single_idx]["label"]
            right_part = f"spectrum: {sp_name}"
        else:
            right_part = f"{n} of {total} spectra shown"
        self._ax.set_title(
            f"{mode_label} \u2014 {len(self._ranges)} range(s)  |  "
            f"{right_part}", fontsize=8)
        if was_zoomed:
            self._ax.set_xlim(xlim)
            self._ax.set_ylim(ylim)

        self._preview_drawn = True
        self._canvas.draw_idle()

    # ------------------------------------------------------------------ #
    # Mouse drag                                                            #
    # ------------------------------------------------------------------ #

    def _on_press(self, event):
        if not self._draw_mode:
            return
        if event.inaxes != self._ax or event.button != 1:
            return
        self._drag_start = event.xdata
        if self._drag_span is not None:
            try: self._drag_span.remove()
            except Exception: pass
            self._drag_span = None

    def _on_motion(self, event):
        if not self._draw_mode:
            return
        if self._drag_start is None or event.inaxes != self._ax:
            return
        if event.xdata is None:
            return
        lo = min(self._drag_start, event.xdata)
        hi = max(self._drag_start, event.xdata)
        color = '#C62828' if self._is_exclude else self._band_color
        if self._drag_span is not None:
            try: self._drag_span.remove()
            except Exception: pass
        self._drag_span = self._ax.axvspan(
            lo, hi, alpha=0.35, color=color, linewidth=0)
        self._canvas.draw_idle()

    def _on_release(self, event):
        if not self._draw_mode:
            return
        if self._drag_start is None or event.button != 1:
            return
        if event.xdata is None or event.inaxes != self._ax:
            self._drag_start = None
            return
        # Rounded to 4 decimals — event.xdata is a raw pixel-to-data
        # coordinate transform and carries 15+ meaningless digits of
        # floating-point noise (e.g. 219.97286961758508) if stored as-is.
        # That noise used to leak straight into the From/To fields the
        # moment the range was reselected for editing.
        lo = round(min(self._drag_start, event.xdata), 4)
        hi = round(max(self._drag_start, event.xdata), 4)
        self._drag_start = None
        if abs(hi - lo) < 1e-6:
            return
        self._edit_from.setText(str(lo))
        self._edit_to.setText(str(hi))
        # Dragging always adds a brand-new range, never edits an existing
        # one in place — exit edit mode first so a stale _editing_row from
        # a previously selected range can't get silently overwritten.
        self._exit_edit_mode()
        if self._drag_span is not None:
            try: self._drag_span.remove()
            except Exception: pass
            self._drag_span = None
        dup = self._find_duplicate_row(lo, hi)
        if dup is None:
            self._ranges.append([lo, hi])
            self._ranges.sort(key=lambda r: r[0])
            self._refresh_list()
        else:
            self._refresh_list(select_row=dup)
        self._refresh_preview()

    # ------------------------------------------------------------------ #
    # Help                                                                  #
    # ------------------------------------------------------------------ #

    def _show_help(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Define Spectral Range — Help")
        dlg.resize(520, 480)
        lay = QVBoxLayout(dlg)
        tb = QTextBrowser()
        tb.setHtml(_HELP_TEXT)
        tb.setOpenExternalLinks(True)
        lay.addWidget(tb)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        dlg.exec_()

    # ------------------------------------------------------------------ #
    # Result                                                                #
    # ------------------------------------------------------------------ #

    def get_settings(self):
        return {
            'ranges':     [list(r) for r in self._ranges],
            'is_exclude': self._is_exclude,
        }
