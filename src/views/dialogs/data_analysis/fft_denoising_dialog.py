# src/views/dialogs/data_analysis/fft_denoising_dialog.py
"""
FFT Denoising dialog — v3.

Layout
──────
Left panel (fixed 360 px)
    • Spectra list — sort ▲/▼, Select all, Clear, Show legend
      Selection drives ALL preview plots simultaneously.
    • Stop-bands — Quick cut (Cut low/Cut high, one click) plus a table of
      arbitrary [f_lo, f_hi] bands for anything more specific (e.g. a
      narrow spike). Everything removed shows up in this one table.
    • OK / Cancel / Help

Right panel — single view, no tabs
    Controls row:
        ◀ [N/M] ▶  spectrum name      (power-spectrum navigator)
        Signal view:  ○ Subplots  ○ Overlay
        Power view:   ○ Overlay   ○ Subplots
        ☐ Show power spectrum           (hides/shows the power panel)

    Vertical QSplitter:
        TOP  — power-spectrum panel  (collapsible via checkbox)
        BOT  — signal panel          (original vs denoised)

    Both panels update live on any filter or selection change (300 ms debounce).
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QDoubleSpinBox, QLabel, QCheckBox, QListWidget,
    QSizePolicy, QSplitter, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QButtonGroup, QRadioButton, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QTimer

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import make_shortened_name_delegate, make_shorten_names_checkbox

logger = get_logger(__name__)

_COLORS = [
    '#1f77b4', '#d62728', '#2ca02c', '#ff7f0e',
    '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]


class FFTDenoisingDialog(QDialog):

    def __init__(self, parent=None, current_settings=None,
                 controller=None, selected_spectra=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle('FFT Denoising')
        self.setMinimumSize(1020, 640)
        self.resize(1340, 820)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        self.controller       = controller
        self.selected_spectra = list(selected_spectra or [])
        self._settings        = dict(current_settings or {})
        self._stop_bands: list[tuple[float, float]] = []
        # When a row in _bands_table is selected, its bounds are loaded
        # into the F low/F high spinboxes and this tracks which row is
        # being edited, so "Add band" (relabeled "Update band") updates
        # that entry in place instead of appending a duplicate. None means
        # "not currently editing an existing band" — same pattern used by
        # normalization_dialog.py's region editing.
        self._editing_band_row = None
        # Bound method (OperationsController.commit_fft_denoising) passed
        # in by whatever opened this dialog, so Apply / Add as New can
        # commit the result directly, without a separate Run step.
        self.commit_callback  = commit_callback

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(300)
        self._update_timer.timeout.connect(self._refresh_all)

        self.sort_ascending           = True
        self._initialization_complete = False

        self._build_ui()
        self._populate_spectrum_list()
        self._populate_from_settings(self._settings)
        self._initialization_complete = True
        self._select_all()

    # ------------------------------------------------------------------
    # Top-level layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 980])
        root.addWidget(splitter)

    # ------------------------------------------------------------------
    # Left panel
    # ------------------------------------------------------------------

    def _build_left_panel(self):
        widget = QWidget()
        # setFixedWidth(360) used to sit here — it actively fights the
        # QSplitter above: dragging the handle can never actually resize
        # this panel since Qt won't violate a fixed width. A min/max range
        # lets the splitter actually resize it (same fix already applied
        # to Normalization, Band Ratio, Data Range, Cosmic Ray Removal,
        # X-axis Alignment, and Peak Fitting's dialogs).
        widget.setMinimumWidth(300)
        widget.setMaximumWidth(650)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Selected spectra gets the stretch factor, not a trailing
        # addStretch() — otherwise the extra vertical space collects as
        # empty gap between the Stop-bands group and the buttons below,
        # instead of letting the spectra list actually grow into it.
        layout.addWidget(self._build_spectra_group(), stretch=1)
        layout.addWidget(self._build_bands_group())

        btn_row = QHBoxLayout()
        help_btn = QPushButton('Help')
        help_btn.setAutoDefault(False)
        help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(help_btn)

        btn_row.addStretch()

        # Apply / Add as New commit directly via commit_callback — there's
        # no separate Run step in the main window for this operation
        # anymore (see OperationsController.commit_fft_denoising).
        self.apply_button = QPushButton('Apply')
        self.apply_button.setToolTip(
            'Replace the selected spectra with their denoised result.'
        )
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        btn_row.addWidget(self.apply_button)

        self.add_as_new_button = QPushButton('Add as New')
        self.add_as_new_button.setToolTip(
            'Keep the original spectra unchanged and add the denoised '
            'results to the list under new names.'
        )
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        btn_row.addWidget(self.add_as_new_button)

        self.close_button = QPushButton('Close')
        self.close_button.clicked.connect(self.reject)
        btn_row.addWidget(self.close_button)
        layout.addLayout(btn_row)
        return widget

    def _build_spectra_group(self):
        group = QGroupBox('Selected spectra')
        layout = QVBoxLayout(group)

        info = QLabel(
            '💡 Selection controls which spectra are shown in the preview. '
            'Denoising is applied to all spectra loaded in the dialog.'
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            'color: #1976D2; font-style: italic; padding: 5px; '
            'background-color: #E3F2FD; border-radius: 3px; margin: 2px;'
        )
        layout.addWidget(info)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel('Spectra:'))
        self.sort_button = QPushButton('▲')
        self.sort_button.setMaximumWidth(30)
        self.sort_button.setToolTip('Toggle sort order')
        self.sort_button.clicked.connect(self._toggle_sort)
        hdr.addWidget(self.sort_button)
        hdr.addStretch()
        layout.addLayout(hdr)

        self.spectra_list = QListWidget()
        self.spectra_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.spectra_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        # Display-only "shorten names" — item.text() (what selection
        # matching above reads: sel_labels = {item.text() for item in
        # ...selectedItems()}) is untouched by this paint-only delegate.
        self.spectra_list.setItemDelegate(
            make_shortened_name_delegate(self.spectra_list, self._shorten_names_enabled)
        )
        self.spectra_list.itemSelectionChanged.connect(self._on_list_selection_changed)
        layout.addWidget(self.spectra_list)

        btn_row = QHBoxLayout()
        for lbl, slot in [('Select all', self._select_all), ('Clear', self._unselect_all)]:
            b = QPushButton(lbl)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        self.show_legend_cb = QCheckBox('Show legend')
        self.show_legend_cb.setChecked(False)
        self.show_legend_cb.stateChanged.connect(self._schedule_update)
        btn_row.addWidget(self.show_legend_cb)
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)
        btn_row.addWidget(self.checkBox_shorten_names)
        layout.addLayout(btn_row)
        return group

    def _build_bands_group(self):
        group = QGroupBox('Stop-bands (frequencies to remove)')
        layout = QVBoxLayout(group)

        note = QLabel(
            'Zero out specific frequency intervals — a narrow spike visible '
            'in the power spectrum, or a whole low/high end of it. '
            '0 = DC / baseline,  1 = Nyquist / highest frequency.'
        )
        note.setWordWrap(True)
        note.setStyleSheet('color: grey; font-size: 10px;')
        layout.addWidget(note)

        # ---- Quick cut — one-click low-/high-frequency removal, without
        # a separate parallel "Frequency filter" mechanism: this just adds
        # a (0, x) or (x, 1) band to the same stop-bands list below, so
        # there's a single place that shows and controls everything that's
        # being removed. Low and high each get their own row rather than
        # sharing one — cramming label + spinbox + button twice into a
        # single row left "Cut high" truncated in the narrow left panel.
        quick_low_row = QHBoxLayout()
        quick_low_row.setSpacing(4)
        quick_low_row.addWidget(QLabel('Cut below:'))
        self._quick_low_spin = QDoubleSpinBox()
        self._quick_low_spin.setRange(0.0001, 99.9)
        self._quick_low_spin.setDecimals(2)
        self._quick_low_spin.setSingleStep(0.1)
        self._quick_low_spin.setValue(1.0)
        self._quick_low_spin.setSuffix(' %')
        self._quick_low_spin.setToolTip(
            'Percent of Nyquist below which everything is removed '
            '(removes slowly-varying baseline drift).'
        )
        quick_low_row.addWidget(self._quick_low_spin)
        btn_cut_low = QPushButton('Cut low')
        btn_cut_low.setToolTip('Add a stop-band from 0 up to this value.')
        btn_cut_low.clicked.connect(self._quick_cut_low)
        quick_low_row.addWidget(btn_cut_low)
        quick_low_row.addStretch()
        layout.addLayout(quick_low_row)

        quick_high_row = QHBoxLayout()
        quick_high_row.setSpacing(4)
        quick_high_row.addWidget(QLabel('Cut above:'))
        self._quick_high_spin = QDoubleSpinBox()
        self._quick_high_spin.setRange(0.0001, 99.9)
        self._quick_high_spin.setDecimals(2)
        self._quick_high_spin.setSingleStep(1.0)
        self._quick_high_spin.setValue(50.0)
        self._quick_high_spin.setSuffix(' %')
        self._quick_high_spin.setToolTip(
            'Percent of Nyquist above which everything is removed '
            '(removes HF electronic/shot noise).'
        )
        quick_high_row.addWidget(self._quick_high_spin)
        btn_cut_high = QPushButton('Cut high')
        btn_cut_high.setToolTip('Add a stop-band from this value up to Nyquist.')
        btn_cut_high.clicked.connect(self._quick_cut_high)
        quick_high_row.addWidget(btn_cut_high)
        quick_high_row.addStretch()
        layout.addLayout(quick_high_row)

        self._bands_table = QTableWidget(0, 2)
        self._bands_table.setHorizontalHeaderLabels(['F low (0–1)', 'F high (0–1)'])
        self._bands_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._bands_table.setMaximumHeight(100)
        self._bands_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._bands_table.setAlternatingRowColors(True)
        self._bands_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # ExtendedSelection so Ctrl/Shift-click can select several bands at
        # once for bulk removal (see _remove_band). Editing a single band
        # (populating F low/F high, switching Add -> Update) only
        # activates when exactly one row is selected — see
        # _on_band_row_selected.
        self._bands_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._bands_table.setToolTip(
            'Click a band to edit its values below.\nCtrl/Shift-click to select more than one for Remove.'
        )
        self._bands_table.itemSelectionChanged.connect(self._on_band_row_selected)
        layout.addWidget(self._bands_table)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        add_row.addWidget(QLabel('F low:'))
        self._band_lo_spin = QDoubleSpinBox()
        self._band_lo_spin.setRange(0.0, 0.998)
        self._band_lo_spin.setDecimals(3)
        self._band_lo_spin.setSingleStep(0.01)
        self._band_lo_spin.setValue(0.1)
        add_row.addWidget(self._band_lo_spin)
        add_row.addSpacing(8)
        add_row.addWidget(QLabel('F high:'))
        self._band_hi_spin = QDoubleSpinBox()
        self._band_hi_spin.setRange(0.001, 1.0)
        self._band_hi_spin.setDecimals(3)
        self._band_hi_spin.setSingleStep(0.01)
        self._band_hi_spin.setValue(0.2)
        add_row.addWidget(self._band_hi_spin)
        add_row.addStretch()
        layout.addLayout(add_row)

        btn_row = QHBoxLayout()
        self._add_band_btn = QPushButton('Add band')
        self._add_band_btn.setToolTip(
            'Add the F low / F high values above as a new stop-band.'
        )
        self._add_band_btn.clicked.connect(self._add_band)
        btn_row.addWidget(self._add_band_btn)
        # Cancel edit sits right next to Add/Update band — while editing,
        # this is the button you actually reach for, not something at the
        # far end of the row past Remove. Only shown while a band
        # is selected (i.e. while _add_band_btn reads "Update band").
        # QTableWidget does not reliably clear its selection when clicking
        # empty space below the rows, so an explicit way out of edit mode
        # is needed rather than relying on it.
        self._cancel_band_edit_btn = QPushButton('Cancel edit')
        self._cancel_band_edit_btn.setToolTip('Deselect the band and go back to adding a new one.')
        self._cancel_band_edit_btn.setVisible(False)
        self._cancel_band_edit_btn.clicked.connect(self._cancel_band_edit)
        btn_row.addWidget(self._cancel_band_edit_btn)
        rm_btn = QPushButton('Remove')
        rm_btn.setToolTip(
            'Remove the selected stop-band(s).\nCtrl/Shift-click rows in the table to select more than one.'
        )
        rm_btn.clicked.connect(self._remove_band)
        btn_row.addWidget(rm_btn)
        layout.addLayout(btn_row)
        return group

    # ------------------------------------------------------------------
    # Right panel — single view with vertical splitter
    # ------------------------------------------------------------------

    def _build_right_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        layout.addLayout(self._build_controls_row())

        # Vertical splitter: power (top) / signal (bottom)
        self._vsplit = QSplitter(Qt.Vertical)

        # ---- Power panel ----
        self._power_panel = QWidget()
        pp_layout = QVBoxLayout(self._power_panel)
        pp_layout.setContentsMargins(0, 0, 0, 0)
        self._power_canvas = _PowerCanvas(self._power_panel)
        pp_layout.addWidget(NavigationToolbar(self._power_canvas, self._power_panel))
        pp_layout.addWidget(self._power_canvas)
        self._vsplit.addWidget(self._power_panel)

        # ---- Signal panel ----
        self._signal_panel = QWidget()
        sp_layout = QVBoxLayout(self._signal_panel)
        sp_layout.setContentsMargins(0, 0, 0, 0)
        self._signal_canvas = _SignalCanvas(self._signal_panel)
        sp_layout.addWidget(NavigationToolbar(self._signal_canvas, self._signal_panel))
        sp_layout.addWidget(self._signal_canvas)
        self._vsplit.addWidget(self._signal_panel)

        self._vsplit.setSizes([320, 480])
        self._vsplit.setStretchFactor(0, 0)
        self._vsplit.setStretchFactor(1, 1)
        layout.addWidget(self._vsplit)
        return widget

    def _build_controls_row(self) -> QHBoxLayout:
        """Single toolbar row above the splitter."""
        row = QHBoxLayout()
        row.setSpacing(12)

        # Signal view mode
        row.addWidget(QLabel('Signal:'))
        self._signal_mode = QButtonGroup(self)
        for i, lbl in enumerate(['Subplots', 'Overlay']):
            rb = QRadioButton(lbl)
            rb.setChecked(i == 0)
            self._signal_mode.addButton(rb, i)
            row.addWidget(rb)
        self._signal_mode.buttonClicked.connect(self._schedule_update)

        sep1 = QLabel('|')
        sep1.setStyleSheet('color: #ccc;')
        row.addWidget(sep1)

        # Visibility checkboxes
        self._show_power_cb = QCheckBox('Show power spectra')
        self._show_power_cb.setChecked(True)
        self._show_power_cb.stateChanged.connect(self._on_panel_visibility_changed)
        row.addWidget(self._show_power_cb)

        self._show_signal_cb = QCheckBox('Show spectra')
        self._show_signal_cb.setChecked(True)
        self._show_signal_cb.stateChanged.connect(self._on_panel_visibility_changed)
        row.addWidget(self._show_signal_cb)

        row.addStretch()
        return row

    # ------------------------------------------------------------------
    # Panel visibility
    # ------------------------------------------------------------------

    def _on_panel_visibility_changed(self, _state=None):
        show_power  = self._show_power_cb.isChecked()
        show_signal = self._show_signal_cb.isChecked()
        self._power_panel.setVisible(show_power)
        self._signal_panel.setVisible(show_signal)
        # Restore a sensible split when both are visible
        if show_power and show_signal:
            total = self._vsplit.height()
            self._vsplit.setSizes([max(200, total // 3), max(300, total * 2 // 3)])
        if self._initialization_complete:
            self._schedule_update()

    # ------------------------------------------------------------------
    # Spectra-list helpers
    # ------------------------------------------------------------------

    def _populate_spectrum_list(self):
        self.spectra_list.blockSignals(True)
        self.spectra_list.clear()
        spectra = list(self.selected_spectra)
        if not self.sort_ascending:
            spectra = list(reversed(spectra))
        for s in spectra:
            self.spectra_list.addItem(s['label'])
        self.spectra_list.blockSignals(False)

    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _on_shorten_names_toggled(self, *_):
        self.spectra_list.viewport().update()
        self._schedule_update()

    def _display_labels_map(self):
        """{full_label: display_label} for self.selected_spectra — see
        label_shortening.py. Legend/title text only; denoised_map and
        every other lookup below stays keyed by full label."""
        if not self._shorten_names_enabled():
            return {}
        all_labels = [s.get('label', '') for s in self.selected_spectra]
        if len(all_labels) < 2:
            return {}
        from src.modules.utils.label_shortening import compute_distinguishing_labels
        return compute_distinguishing_labels(all_labels)

    def _toggle_sort(self):
        self.sort_ascending = not self.sort_ascending
        self.sort_button.setText('▲' if self.sort_ascending else '▼')
        sel = {item.text() for item in self.spectra_list.selectedItems()}
        self._populate_spectrum_list()
        for i in range(self.spectra_list.count()):
            if self.spectra_list.item(i).text() in sel:
                self.spectra_list.item(i).setSelected(True)

    def _select_all(self):
        self.spectra_list.blockSignals(True)
        for i in range(self.spectra_list.count()):
            self.spectra_list.item(i).setSelected(True)
        self.spectra_list.blockSignals(False)
        if self._initialization_complete:
            self._on_list_selection_changed()

    def _unselect_all(self):
        self.spectra_list.blockSignals(True)
        for i in range(self.spectra_list.count()):
            self.spectra_list.item(i).setSelected(False)
        self.spectra_list.blockSignals(False)
        if self._initialization_complete:
            self._on_list_selection_changed()

    def _on_list_selection_changed(self):
        if not self._initialization_complete:
            return
        self._schedule_update()

    # ------------------------------------------------------------------
    # Quick cut — one-click low-/high-frequency stop-bands
    # ------------------------------------------------------------------

    def _quick_cut_low(self):
        """Add a (0, x) stop-band from the Quick cut Low % spinbox —
        removes everything below x, same effect the old separate
        "Remove low frequencies" checkbox had, just expressed as a band."""
        f_hi = self._quick_low_spin.value() / 100.0
        self._quick_add_band(0.0, f_hi)

    def _quick_cut_high(self):
        """Add a (x, 1) stop-band from the Quick cut High % spinbox —
        removes everything above x."""
        f_lo = self._quick_high_spin.value() / 100.0
        self._quick_add_band(f_lo, 1.0)

    def _quick_add_band(self, f_lo, f_hi):
        """Shared by _quick_cut_low/_quick_cut_high: append (f_lo, f_hi) to
        the stop-bands list, or select it if it's already there — same
        duplicate-avoidance as manually typed bands via _add_band."""
        if f_lo >= f_hi:
            return
        dup = self._find_duplicate_band_row(f_lo, f_hi)
        if dup is not None:
            self._refresh_bands_table(select_row=dup)
            return
        self._stop_bands.append((f_lo, f_hi))
        self._refresh_bands_table()
        self._schedule_update()

    def _find_duplicate_band_row(self, f_lo, f_hi, exclude_row=None):
        """Return the index of an existing stop-band with the same (f_lo,
        f_hi) bounds (within floating-point tolerance), other than
        exclude_row — or None if there isn't one. Used to stop Add/Update
        from ever creating an exact duplicate entry."""
        for i, (existing_lo, existing_hi) in enumerate(self._stop_bands):
            if i == exclude_row:
                continue
            if abs(existing_lo - f_lo) < 1e-9 and abs(existing_hi - f_hi) < 1e-9:
                return i
        return None

    def _add_band(self):
        """Add the F low/F high values above as a new stop-band — or, if a
        band is currently selected in _bands_table (self._editing_band_row
        set by _on_band_row_selected), update that band in place instead.
        The button itself is relabeled "Update band" while editing, so
        this single slot covers both cases."""
        f_lo, f_hi = self._band_lo_spin.value(), self._band_hi_spin.value()
        if f_lo >= f_hi:
            return
        row = self._editing_band_row
        if row is not None and 0 <= row < len(self._stop_bands):
            dup = self._find_duplicate_band_row(f_lo, f_hi, exclude_row=row)
            if dup is not None:
                # Updating to values that exactly match another existing
                # band would create a duplicate — select that band instead
                # of creating one.
                self._refresh_bands_table(select_row=dup)
                return
            self._stop_bands[row] = (f_lo, f_hi)
            self._refresh_bands_table(select_row=row)
        else:
            dup = self._find_duplicate_band_row(f_lo, f_hi)
            if dup is not None:
                self._refresh_bands_table(select_row=dup)
                return
            self._stop_bands.append((f_lo, f_hi))
            self._refresh_bands_table()
        self._schedule_update()

    def _remove_band(self):
        """Remove every currently-selected stop-band — Ctrl/Shift-click in
        the table first to remove more than one at a time."""
        rows = sorted({idx.row() for idx in self._bands_table.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self._stop_bands):
                self._stop_bands.pop(row)
        self._refresh_bands_table()
        self._schedule_update()

    def _on_band_row_selected(self):
        """Populate the F low/F high spinboxes when a stop-band row is
        selected, and switch "Add band" into "Update band" mode (with a
        "Cancel edit" button appearing alongside it). Deselecting switches
        back to "Add band".

        Editing only activates when EXACTLY one row is selected — with
        several selected (for bulk Remove) there's no single band
        for F low/F high/Update to mean anything about. Uses
        selectionModel().selectedRows() rather than selectedItems(), since
        SelectRows behavior means selectedItems() returns one item per
        selected CELL (2 per row here), not one per row.
        """
        rows = self._bands_table.selectionModel().selectedRows()
        if len(rows) == 1:
            row = rows[0].row()
            if 0 <= row < len(self._stop_bands):
                f_lo, f_hi = self._stop_bands[row]
                self._band_lo_spin.setValue(f_lo)
                self._band_hi_spin.setValue(f_hi)
                self._editing_band_row = row
                self._add_band_btn.setText('Update band')
                self._add_band_btn.setToolTip(
                    'Update the selected stop-band with the F low / F high values above.'
                )
                self._cancel_band_edit_btn.setVisible(True)
                return
        self._exit_band_edit_mode()

    def _cancel_band_edit(self):
        """Explicitly leave edit mode without removing or changing the
        selected band — used by the 'Cancel edit' button, since clicking
        empty space in the table does not reliably clear its selection."""
        self._bands_table.clearSelection()
        self._exit_band_edit_mode()

    def _exit_band_edit_mode(self):
        self._editing_band_row = None
        self._add_band_btn.setText('Add band')
        self._add_band_btn.setToolTip(
            'Add the F low / F high values above as a new stop-band.'
        )
        self._cancel_band_edit_btn.setVisible(False)

    def _refresh_bands_table(self, select_row=None):
        self._bands_table.setRowCount(0)
        for f_lo, f_hi in self._stop_bands:
            r = self._bands_table.rowCount()
            self._bands_table.insertRow(r)
            self._bands_table.setItem(r, 0, QTableWidgetItem(f'{f_lo:.3f}'))
            self._bands_table.setItem(r, 1, QTableWidgetItem(f'{f_hi:.3f}'))
        if select_row is not None and 0 <= select_row < self._bands_table.rowCount():
            self._bands_table.selectRow(select_row)
        else:
            # setRowCount(0) doesn't reliably re-emit itemSelectionChanged,
            # so explicitly drop out of edit mode rather than relying on it.
            self._exit_band_edit_mode()

    # ------------------------------------------------------------------
    # Plot refresh
    # ------------------------------------------------------------------

    def _schedule_update(self, *_):
        if self._initialization_complete:
            self._update_timer.start()

    def _refresh_all(self):
        if not self.selected_spectra:
            return

        settings   = self.get_settings()
        legend_vis = self.show_legend_cb.isChecked()

        # Visible spectra = those selected in the list
        sel_labels = {item.text() for item in self.spectra_list.selectedItems()}
        visible    = [s for s in self.selected_spectra if s['label'] in sel_labels]
        if not visible:
            visible = [self.selected_spectra[0]]

        # Precompute denoised for all visible spectra
        denoised_map: dict[str, np.ndarray] = {}
        for s in visible:
            y = np.asarray(s.get('y_scale', []), dtype=float)
            if len(y) >= 4:
                denoised_map[s['label']] = self._quick_denoise(y, settings)

        display_map = self._display_labels_map()

        # ---- Power spectrum panel ------------------------------------
        if self._show_power_cb.isChecked():
            power_data = []
            for s in visible:
                y = np.asarray(s.get('y_scale', []), dtype=float)
                if len(y) >= 4:
                    from src.modules.data_analysis.fft_denoising_manager import FFTDenoisingManager
                    f, amp = FFTDenoisingManager().compute_power_spectrum(y)
                    power_data.append((f, amp, display_map.get(s['label'], s['label'])))
            self._power_canvas.plot_multi(power_data, settings, legend_vis)

        # ---- Signal panel -------------------------------------------
        if self._show_signal_cb.isChecked():
            signal_overlay = (self._signal_mode.checkedId() == 1)
            self._signal_canvas.plot_multi(
                visible, denoised_map,
                overlay=signal_overlay,
                legend_visible=legend_vis,
                display_labels=display_map,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _quick_denoise(self, y: np.ndarray, settings: dict) -> np.ndarray:
        from src.modules.data_analysis.fft_denoising_manager import FFTDenoisingManager
        m = FFTDenoisingManager()
        m.update_settings(settings)
        return m.preview_denoised(y)

    def _populate_from_settings(self, s):
        # Low/high cutoff are no longer separate controls — the Quick cut
        # buttons add the same shape of band directly to stop_bands now.
        # Settings saved before this change (older projects, Operations
        # History replay) may still carry low_cutoff/high_cutoff though,
        # so fold those into equivalent stop-bands here to preserve their
        # effect rather than silently dropping them.
        self._stop_bands = list(s.get('stop_bands', []))
        low = s.get('low_cutoff')
        if low is not None and float(low) > 0:
            self._stop_bands.append((0.0, float(low)))
        high = s.get('high_cutoff')
        if high is not None and float(high) < 1.0:
            self._stop_bands.append((float(high), 1.0))
        self._refresh_bands_table()

    def _show_help(self):
        try:
            from src.help.fft_denoising_help import (
                get_fft_denoising_help_content, get_fft_denoising_help_title)
            from src.help.help_window import show_help_window
            show_help_window(self, get_fft_denoising_help_title(),
                             get_fft_denoising_help_content())
        except Exception:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Help',
                                    'Help documentation is not available at this time.')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — commits directly via commit_callback. No
        separate Run step: feedback (success or failure) is shown right
        here next to the buttons that triggered it, instead of in a
        disconnected main-window message box. The dialog closes itself
        once the commit succeeds.
        """
        from PyQt5.QtWidgets import QMessageBox

        if self.commit_callback is None:
            QMessageBox.critical(
                self, 'Not Available',
                'This dialog was opened without a way to apply changes. '
                'Please reopen it via Parameters.'
            )
            return

        settings = self.get_settings()

        action = ('add the denoised result as new spectra' if add_as_new
                  else 'replace the selected spectra with their denoised result')
        confirm = QMessageBox.question(
            self, 'Confirm', f'{action[0].upper() + action[1:]}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(settings, add_as_new, list(self.selected_spectra))
        if success:
            QMessageBox.information(self, 'Done', message)
            self.accept()
        else:
            QMessageBox.warning(self, 'Could Not Apply', message)

    def get_settings(self) -> dict:
        # low_cutoff/high_cutoff are always None now — the Quick cut
        # buttons add their equivalent directly to stop_bands instead, so
        # there's a single mechanism for everything being removed. The
        # keys are still included since the manager's settings dict shape
        # expects them.
        return {
            'low_cutoff':  None,
            'high_cutoff': None,
            'stop_bands':  list(self._stop_bands),
            'window':      'none',
        }


# ======================================================================
# Canvas helpers
# ======================================================================

def _n_spectra_label(n: int) -> str:
    """Return '1 spectrum' or 'N spectra' — no grammar bug."""
    return f'{n} spectrum' if n == 1 else f'{n} spectra'


def _shade_filter_bands(ax, settings: dict):
    """Shade filtered regions on *ax*. Returns True if any bands were drawn."""
    bands = list(settings.get('stop_bands', []))
    low  = settings.get('low_cutoff')
    high = settings.get('high_cutoff')
    if low  is not None: bands.insert(0, (0.0, float(low)))
    if high is not None: bands.append((float(high), 1.0))
    first = True
    for f_lo, f_hi in bands:
        ax.axvspan(f_lo, f_hi, color='#EF9A9A', alpha=0.40,
                   label='Filtered' if first else '_nolegend_')
        first = False
    return bool(bands)


class _PowerCanvas(FigureCanvas):
    """Power spectrum canvas supporting both Overlay and Subplots modes."""

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#f0f0f0')

    def _common_ax_style(self, ax, title=''):
        ax.set_facecolor('#ffffff')
        ax.set_xlabel('Normalised frequency  (0 = DC,  1 = Nyquist)', fontsize=8)
        ax.set_ylabel('Amplitude', fontsize=8)
        ax.set_xlim(0, 1)
        ax.grid(True, linestyle='--', alpha=0.4)
        if title:
            ax.set_title(title, fontsize=9)

    def plot_multi(self, power_data: list, settings: dict, legend_visible: bool):
        """Overlay all spectra on a single axes."""
        self._fig.clear()
        if not power_data:
            self.draw_idle()
            return
        ax = self._fig.add_subplot(111)
        for i, (f, amp, label) in enumerate(power_data):
            ax.plot(f, amp, color=_COLORS[i % len(_COLORS)], lw=1.1,
                    label=label if legend_visible else '_nolegend_')
        has_bands = _shade_filter_bands(ax, settings)
        n = len(power_data)
        self._common_ax_style(
            ax, f'Power spectrum — {_n_spectra_label(n)} (overlay)'
        )
        if legend_visible or has_bands:
            ax.legend(fontsize=7, loc='upper right')
        self._fig.tight_layout()
        self.draw_idle()

    def plot_subplots(self, power_data: list, settings: dict, legend_visible: bool):
        """One subplot per spectrum, stacked vertically."""
        self._fig.clear()
        if not power_data:
            self.draw_idle()
            return
        n = len(power_data)
        axes = self._fig.subplots(n, 1, sharex=True)
        if n == 1:
            axes = [axes]
        for i, (ax, (f, amp, label)) in enumerate(zip(axes, power_data)):
            ax.plot(f, amp, color=_COLORS[i % len(_COLORS)], lw=1.1)
            _shade_filter_bands(ax, settings)
            short = label if len(label) <= 30 else f'…{label[-28:]}'
            ax.set_facecolor('#ffffff')
            ax.set_ylabel('Ampl.', fontsize=7)
            ax.set_title(short, fontsize=8, pad=2)
            ax.grid(True, linestyle='--', alpha=0.4)
        axes[-1].set_xlabel('Normalised frequency  (0 = DC,  1 = Nyquist)', fontsize=8)
        self._fig.suptitle(
            f'Power spectra — {_n_spectra_label(n)} (subplots)', fontsize=9, y=1.0
        )
        self._fig.tight_layout()
        self.draw_idle()


class _SignalCanvas(FigureCanvas):
    """Original vs denoised — Subplots or Overlay, any number of spectra."""

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#f0f0f0')

    def plot_multi(self, spectra_list, denoised_map,
                   overlay=False, legend_visible=False, display_labels=None):
        display_labels = display_labels or {}
        self._fig.clear()
        if not spectra_list:
            self.draw_idle()
            return

        n = len(spectra_list)

        if overlay:
            ax = self._fig.add_subplot(111)
            ax.set_facecolor('#ffffff')
            for i, s in enumerate(spectra_list):
                lbl = s['label']
                x   = np.asarray(s.get('x_scale', []), dtype=float)
                y   = np.asarray(s.get('y_scale', []), dtype=float)
                y_d = denoised_map.get(lbl)
                col = _COLORS[i % len(_COLORS)]
                disp = display_labels.get(lbl, lbl) if legend_visible else '_nolegend_'
                if len(x):
                    ax.plot(x, y,  color=col, lw=1.0, alpha=0.45,
                            linestyle='--', label=f'{disp} orig' if legend_visible else '_nolegend_')
                if y_d is not None and len(x):
                    ax.plot(x, y_d, color=col, lw=1.5, alpha=0.90,
                            linestyle='-', label=f'{disp} denoised' if legend_visible else '_nolegend_')
            ax.set_xlabel('x', fontsize=9)
            ax.set_ylabel('Intensity', fontsize=9)
            ax.set_title(
                f'Original (dashed) vs Denoised (solid) — {_n_spectra_label(n)}',
                fontsize=10
            )
            ax.grid(True, linestyle='--', alpha=0.4)
            if legend_visible:
                ax.legend(fontsize=7, loc='best')

        else:   # Subplots
            ax_top = self._fig.add_subplot(211)
            ax_bot = self._fig.add_subplot(212, sharex=ax_top)
            for ax in (ax_top, ax_bot):
                ax.set_facecolor('#ffffff')
            for i, s in enumerate(spectra_list):
                lbl = s['label']
                x   = np.asarray(s.get('x_scale', []), dtype=float)
                y   = np.asarray(s.get('y_scale', []), dtype=float)
                y_d = denoised_map.get(lbl)
                col  = _COLORS[i % len(_COLORS)]
                disp = display_labels.get(lbl, lbl) if legend_visible else '_nolegend_'
                if len(x):
                    ax_top.plot(x, y,  color=col, lw=1.0, alpha=0.85, label=disp)
                if y_d is not None and len(x):
                    ax_bot.plot(x, y_d, color=col, lw=1.0, alpha=0.85, label=disp)

            ax_top.set_title(f'Original — {_n_spectra_label(n)}',  fontsize=10)
            ax_bot.set_title(f'Denoised — {_n_spectra_label(n)}', fontsize=10)
            for ax in (ax_top, ax_bot):
                ax.set_ylabel('Intensity', fontsize=9)
                ax.grid(True, linestyle='--', alpha=0.4)
                if legend_visible:
                    ax.legend(fontsize=7, loc='best')
            ax_bot.set_xlabel('x', fontsize=9)

        self._fig.tight_layout()
        self.draw_idle()
