# src/views/dialogs/visualization_analysis/band_ratio_dialog.py
"""
Band Ratio / Peak Area Calculator dialog — v2.

Follows the 2D-map arithmetic panel pattern.  Each band is defined using
the same SpectralRangeDialog (include/exclude sub-ranges), making the band
definition fully consistent with the 2D map feature.

Layout
------
Left panel (fixed 360 px)
    Band A  — Configure Band A…  | summary | metric combo
    Band B  — ☑ Enable | Configure Band B… | summary | metric combo
    Operation — A only / B only / A/B / A-B / A+B
    Spectra list (sort / select-all / clear)
    Help | OK | Cancel

Right panel — QTabWidget
    Preview  — overlay of selected spectra; Band A shaded blue,
               Band B shaded orange; masked regions highlighted
    Results  — ▶ Calculate | stats bar | table | Copy | Export CSV
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QComboBox, QPushButton, QLabel, QCheckBox, QSpinBox, QDoubleSpinBox,
    QListWidget, QSizePolicy, QSplitter, QWidget, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QApplication,
)
from PyQt5.QtCore import Qt, QTimer, QItemSelection, QItemSelectionModel
from PyQt5.QtGui import QColor

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    make_shortened_name_delegate, make_display_text_delegate, shorten_spectra_labels,
    make_shorten_names_checkbox,
)

logger = get_logger(__name__)

_COLOR_A = '#1565C0'
_COLOR_B = '#C62828'
_COLORS  = [
    '#1f77b4','#d62728','#2ca02c','#ff7f0e',
    '#9467bd','#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf',
]


class BandRatioDialog(QDialog):

    def __init__(self, parent=None, selected_spectra=None,
                 current_settings=None, controller=None):
        super().__init__(parent)
        self.setWindowTitle('Band Ratio / Peak Area Calculator')
        self.setMinimumSize(1020, 640)
        self.resize(1280, 780)
        # No WindowMinimizeButtonHint — this dialog is always modal (opened
        # via exec_()), so minimizing it would leave the whole app blocked
        # behind a taskbar entry with no visible sign anything is still
        # open — easy to mistake for a frozen app. Maximize stays available.
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        # BandRatioController, if given — see that class's docstring for
        # why this replaced this dialog creating its own throwaway
        # BandRatioManager() inline on every Calculate click. None is
        # still accepted (falls back to a local manager in _calculate())
        # so any caller not yet updated to pass one doesn't break.
        #
        # Deliberately the LAST parameter here, not inserted after
        # `parent` — an existing caller using positional arguments (e.g.
        # BandRatioDialog(parent, my_spectra, my_settings)) must keep
        # working unchanged. Putting a new parameter in the middle of an
        # existing constructor's positional order is exactly the kind of
        # change that silently reassigns an existing caller's real
        # arguments to the wrong parameter — confirmed: that's exactly
        # what happened here the first time, which is why the spectra
        # list came back empty.
        self.controller = controller

        self.selected_spectra = list(selected_spectra or [])
        self._settings        = dict(current_settings or {})
        self._results         = []

        # Band state dicts — mirrors SpectralRangeDialog return value
        self._band_a = self._settings.get('band_a',
                       {'ranges': [], 'is_exclude': False, 'metric': 'Baseline-corrected integral'})
        self._band_b = self._settings.get('band_b', None)
        # Pre-compute x-scale for default x_pos spinbox values
        self._xs_default = (
            np.asarray(self.selected_spectra[0]['x_scale'], dtype=float)
            if self.selected_spectra else np.array([0.0])
        )

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._refresh_preview)

        self.sort_ascending = True
        self._init_complete = False

        self._build_ui()
        self._populate_list()
        self._restore_settings(self._settings)
        self._init_complete = True
        self._select_all()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 920])
        root.addWidget(splitter)

    # ── Left panel ──────────────────────────────────────────────────────

    def _build_left(self):
        w = QWidget()
        # setFixedWidth(360) used to sit here — it actively fights the
        # QSplitter above: dragging the handle can never actually resize
        # this panel since Qt won't violate a fixed width. A min/max range
        # lets the splitter actually resize it (same fix already applied
        # to Normalization, Cosmic Ray Removal, X-axis Alignment, and Peak
        # Fitting's dialogs).
        w.setMinimumWidth(300)
        w.setMaximumWidth(650)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(self._build_band_a_group())
        layout.addWidget(self._build_band_b_group())
        layout.addWidget(self._build_operation_group())

        spectra_group = self._build_spectra_group()
        spectra_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout.addWidget(spectra_group)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        help_btn = QPushButton('Help')
        help_btn.setAutoDefault(False)
        help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(help_btn)
        ok_btn = QPushButton('OK')
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        return w

    def _build_band_a_group(self):
        group = QGroupBox('Band A')
        group.setStyleSheet(f'QGroupBox::title {{ color: {_COLOR_A}; font-weight: bold; }}')
        layout = QVBoxLayout(group)

        btn_row = QHBoxLayout()
        self._btn_configure_a = QPushButton('Configure Band A…')
        self._btn_configure_a.clicked.connect(self._configure_band_a)
        btn_row.addWidget(self._btn_configure_a)
        layout.addLayout(btn_row)

        self._summary_a = QLabel('\u26a0  No range defined — click Configure Band A')
        self._summary_a.setWordWrap(True)
        self._summary_a.setStyleSheet('font-size:8pt; color:#C62828;')
        layout.addWidget(self._summary_a)

        metric_row = QHBoxLayout()
        metric_row.addWidget(QLabel('Metric:'))
        self._metric_a = QComboBox()
        self._metric_a.addItems([
            'Baseline-corrected integral', 'Integral', 'Mean',
            'Peak intensity', 'Peak position', 'Variance',
            'Intensity at x',
        ])
        self._metric_a.setToolTip(
            'Baseline-corrected integral: area above the drop-line baseline\n'
            'Integral: raw area under the curve (trapz)\n'
            'Mean: average intensity in the band\n'
            'Peak intensity: maximum y in the band\n'
            'Peak position: x at maximum y\n'
            'Variance: spread of intensities'
        )
        self._metric_a.currentIndexChanged.connect(self._on_metric_a_changed)
        metric_row.addWidget(self._metric_a)
        metric_row.addStretch()
        layout.addLayout(metric_row)

        xrow_a = QHBoxLayout()
        xrow_a.addWidget(QLabel('x position:'))
        self._x_pos_a = QDoubleSpinBox()
        self._x_pos_a.setRange(-1e9, 1e9)
        self._x_pos_a.setDecimals(2)
        _x_a_default = float(self._xs_default[len(self._xs_default)//3]) if len(self._xs_default) else 0.0
        self._x_pos_a.setValue(_x_a_default)
        self._x_pos_a.valueChanged.connect(self._schedule)
        xrow_a.addWidget(self._x_pos_a)
        xrow_a.addStretch()
        self._x_row_a = QWidget()
        self._x_row_a.setLayout(xrow_a)
        self._x_row_a.setVisible(False)
        layout.addWidget(self._x_row_a)
        return group

    def _build_band_b_group(self):
        group = QGroupBox('Band B')
        group.setStyleSheet(f'QGroupBox::title {{ color: {_COLOR_B}; font-weight: bold; }}')
        layout = QVBoxLayout(group)

        self._btn_configure_b = QPushButton('Configure Band B…')
        self._btn_configure_b.clicked.connect(self._configure_band_b)
        layout.addWidget(self._btn_configure_b)

        self._summary_b = QLabel('No ranges — full spectrum')
        self._summary_b.setWordWrap(True)
        self._summary_b.setStyleSheet(f'font-size:8pt; color:{_COLOR_B};')
        layout.addWidget(self._summary_b)

        metric_row = QHBoxLayout()
        metric_row.addWidget(QLabel('Metric:'))
        self._metric_b = QComboBox()
        self._metric_b.addItems([
            'Baseline-corrected integral', 'Integral', 'Mean',
            'Peak intensity', 'Peak position', 'Variance',
            'Intensity at x',
        ])
        self._metric_b.currentIndexChanged.connect(self._on_metric_b_changed)
        metric_row.addWidget(self._metric_b)
        metric_row.addStretch()
        layout.addLayout(metric_row)

        xrow_b = QHBoxLayout()
        xrow_b.addWidget(QLabel('x position:'))
        self._x_pos_b = QDoubleSpinBox()
        self._x_pos_b.setRange(-1e9, 1e9)
        self._x_pos_b.setDecimals(2)
        _x_b_default = float(self._xs_default[2*len(self._xs_default)//3]) if len(self._xs_default) else 0.0
        self._x_pos_b.setValue(_x_b_default)
        self._x_pos_b.valueChanged.connect(self._schedule)
        xrow_b.addWidget(self._x_pos_b)
        xrow_b.addStretch()
        self._x_row_b = QWidget()
        self._x_row_b.setLayout(xrow_b)
        self._x_row_b.setVisible(False)
        layout.addWidget(self._x_row_b)

        group.setVisible(False)
        self._band_b_group = group
        return group

    def _build_operation_group(self):
        group = QGroupBox('Operation')
        layout = QHBoxLayout(group)
        layout.addWidget(QLabel('Result:'))
        self._op_combo = QComboBox()
        self._op_combo.addItems(['A only', 'A / B', 'A - B', 'A + B'])
        self._op_combo.setToolTip(
            'A only  : just the Band A value\n'
            'A / B   : ratio (Band A divided by Band B)\n'
            'A - B   : difference\n'
            'A + B   : sum'
        )
        self._op_combo.currentIndexChanged.connect(self._on_operation_changed)
        layout.addWidget(self._op_combo)
        layout.addStretch()
        return group

    def _build_spectra_group(self):
        group = QGroupBox('Selected spectra')
        layout = QVBoxLayout(group)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel('Spectra:'))
        self._sort_btn = QPushButton('▲')
        self._sort_btn.setMaximumWidth(28)
        self._sort_btn.clicked.connect(self._toggle_sort)
        hdr.addWidget(self._sort_btn)
        hdr.addStretch()
        # Own, independent "Shorten names" toggle for this dialog — feeds
        # both self._list's delegate and the Results table's column-0
        # delegate (both ultimately read _shorten_names_enabled(), below).
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)
        hdr.addWidget(self.checkBox_shorten_names)
        layout.addLayout(hdr)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self._list.itemSelectionChanged.connect(self._schedule)
        # Paint-only — item.text() stays the full label, since
        # _visible_spectra() matches selected items back to
        # self.selected_spectra by that exact text.
        self._list.setItemDelegate(
            make_shortened_name_delegate(self._list, self._shorten_names_enabled))
        layout.addWidget(self._list, stretch=1)

        btn_row = QHBoxLayout()
        for lbl, slot in [('Select all', self._select_all),
                           ('Clear', self._clear_selection)]:
            b = QPushButton(lbl)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        layout.addLayout(btn_row)
        return group

    # ── Right panel ─────────────────────────────────────────────────────

    def _build_right(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tabs = QTabWidget()
        self._tabs.tabBar().setExpanding(False)
        self._tabs.setStyleSheet("QTabBar::tab { min-width: 70px; padding: 4px 12px; }")

        # Preview tab
        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(4, 4, 4, 4)
        pl.setSpacing(4)
        # Show spectral ranges checkbox
        prev_ctrl = QHBoxLayout()
        self._show_ranges_cb = QCheckBox("Show spectral ranges")
        self._show_ranges_cb.setChecked(True)
        self._show_ranges_cb.setToolTip(
            "Uncheck to hide the Spectral ranges groupbox and give "
            "more space to the preview plot."
        )
        self._show_ranges_cb.stateChanged.connect(self._on_show_ranges_toggled)
        prev_ctrl.addWidget(self._show_ranges_cb)
        self._show_legend_cb = QCheckBox("Show legend")
        self._show_legend_cb.setChecked(False)
        self._show_legend_cb.setToolTip("Show spectrum labels in the preview plot")
        self._show_legend_cb.stateChanged.connect(self._schedule)
        prev_ctrl.addWidget(self._show_legend_cb)
        prev_ctrl.addStretch()
        pl.addLayout(prev_ctrl)
        self._preview_canvas = _PreviewCanvas(pw)
        pl.addWidget(NavigationToolbar(self._preview_canvas, pw))
        pl.addWidget(self._preview_canvas)
        self._tabs.addTab(pw, 'Preview')

        # Results tab
        rw = QWidget()
        rl = QVBoxLayout(rw)
        rl.setContentsMargins(4, 4, 4, 4)
        rl.setSpacing(6)

        self._stats_label = QLabel('')
        self._stats_label.setStyleSheet(
            'background-color: #E8F5E9; padding: 6px; border-radius: 4px; '
            'font-family: monospace;'
        )
        self._stats_label.setWordWrap(True)
        rl.addWidget(self._stats_label)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ['Spectrum', 'Value A', 'Value B', 'Result']
        )
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            self._table.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        # Paint-only — cell text (read by _table_text() for Copy/Export
        # CSV) stays the full label regardless of what's painted here.
        self._table.setItemDelegateForColumn(
            0, make_display_text_delegate(self._display_labels_map, parent=self._table))
        rl.addWidget(self._table)

        export_row = QHBoxLayout()
        export_row.addStretch()
        copy_btn = QPushButton('\u29c9  Copy to clipboard')
        copy_btn.clicked.connect(self._copy_table)
        export_row.addWidget(copy_btn)
        csv_btn = QPushButton('\U0001f4be  Export CSV\u2026')
        csv_btn.clicked.connect(self._export_csv)
        export_row.addWidget(csv_btn)
        pdf_btn = QPushButton('\U0001f4c4  Export PDF\u2026')
        pdf_btn.clicked.connect(self._export_pdf)
        export_row.addWidget(pdf_btn)
        rl.addLayout(export_row)

        self._tabs.addTab(rw, 'Results')

        # ── Plots tab ──────────────────────────────────────────────────
        pw2 = QWidget()
        pl2 = QVBoxLayout(pw2)
        pl2.setContentsMargins(4, 4, 4, 4)
        pl2.setSpacing(4)
        # Plot controls
        plot_ctrl = QHBoxLayout()
        plot_ctrl.addWidget(QLabel("Plot type:"))
        self._plot_type_combo = QComboBox()
        self._plot_type_combo.addItems(["Bar", "Line", "Scatter", "Bar + Line"])
        self._plot_type_combo.currentIndexChanged.connect(self._refresh_plots)
        plot_ctrl.addWidget(self._plot_type_combo)
        plot_ctrl.addSpacing(12)
        plot_ctrl.addWidget(QLabel("Label rotation:"))
        self._label_rotation_combo = QComboBox()
        self._label_rotation_combo.addItems(["0°", "45°", "90°"])
        self._label_rotation_combo.setCurrentIndex(1)
        self._label_rotation_combo.currentIndexChanged.connect(self._refresh_plots)
        plot_ctrl.addWidget(self._label_rotation_combo)
        plot_ctrl.addSpacing(12)
        plot_ctrl.addWidget(QLabel("Show last N chars:"))
        self._label_chars_spin = QSpinBox()
        self._label_chars_spin.setRange(0, 200)
        self._label_chars_spin.setValue(0)
        self._label_chars_spin.setSpecialValueText("all")
        self._label_chars_spin.setFixedWidth(60)
        self._label_chars_spin.setToolTip(
            "0 = show full label. N > 0 = show only the last N characters."
        )
        self._label_chars_spin.valueChanged.connect(self._refresh_plots)
        plot_ctrl.addWidget(self._label_chars_spin)
        plot_ctrl.addStretch()
        pl2.addLayout(plot_ctrl)
        self._plots_canvas = _ResultsPlotsCanvas(pw2)
        pl2.addWidget(NavigationToolbar(self._plots_canvas, pw2))
        pl2.addWidget(self._plots_canvas)
        self._tabs.addTab(pw2, 'Plots')

        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)
        return w

    # ------------------------------------------------------------------ #
    # Band configuration via SpectralRangeDialog                             #
    # ------------------------------------------------------------------ #

    def _configure_band_a(self):
        from src.views.dialogs.visualization_analysis.spectral_range_dialog import SpectralRangeDialog
        dlg = SpectralRangeDialog(
            parent=self,
            all_spectra=self.selected_spectra,
            current_ranges=self._band_a.get('ranges', []),
            is_exclude=self._band_a.get('is_exclude', False),
            band_label='Band A',
            band_color=_COLOR_A,
        )
        if dlg.exec_():
            self._band_a['ranges']     = [list(r) for r in dlg._ranges]
            self._band_a['is_exclude'] = bool(dlg._is_exclude)
            self._update_summary_a()
            self._schedule()

    def _configure_band_b(self):
        from src.views.dialogs.visualization_analysis.spectral_range_dialog import SpectralRangeDialog
        band_b = self._band_b or {'ranges': [], 'is_exclude': False,
                                  'metric': 'Baseline-corrected integral'}
        dlg = SpectralRangeDialog(
            parent=self,
            all_spectra=self.selected_spectra,
            current_ranges=band_b.get('ranges', []),
            is_exclude=band_b.get('is_exclude', False),
            band_label='Band B',
            band_color=_COLOR_B,
        )
        if dlg.exec_():
            if self._band_b is None:
                self._band_b = {}
            self._band_b['ranges']     = [list(r) for r in dlg._ranges]
            self._band_b['is_exclude'] = bool(dlg._is_exclude)
            self._update_summary_b()
            self._schedule()

    def _on_metric_a_changed(self, *_):
        is_x = self._metric_a.currentText() == 'Intensity at x'
        self._btn_configure_a.setVisible(not is_x)
        self._summary_a.setVisible(not is_x)
        self._x_row_a.setVisible(is_x)
        self._schedule()

    def _on_metric_b_changed(self, *_):
        is_x = self._metric_b.currentText() == 'Intensity at x'
        self._btn_configure_b.setVisible(not is_x)
        self._summary_b.setVisible(not is_x)
        self._x_row_b.setVisible(is_x)
        self._schedule()

    def _update_summary_a(self):
        ranges = self._band_a.get('ranges', [])
        excl   = self._band_a.get('is_exclude', False)
        if not ranges:
            self._summary_a.setStyleSheet('font-size:8pt; color:#C62828;')
            self._summary_a.setText('\u26a0  No range defined — click Configure Band A')
        else:
            self._summary_a.setStyleSheet(f'font-size:8pt; color:{_COLOR_A};')
            self._summary_a.setText(self._format_summary(ranges, excl))

    def _update_summary_b(self):
        if self._band_b is None:
            self._summary_b.setStyleSheet(f'font-size:8pt; color:#C62828;')
            self._summary_b.setText('\u26a0  No range defined — click Configure Band B')
            return
        ranges = self._band_b.get('ranges', [])
        excl   = self._band_b.get('is_exclude', False)
        if not ranges:
            self._summary_b.setStyleSheet('font-size:8pt; color:#C62828;')
            self._summary_b.setText('\u26a0  No range defined — click Configure Band B')
        else:
            self._summary_b.setStyleSheet(f'font-size:8pt; color:{_COLOR_B};')
            self._summary_b.setText(self._format_summary(ranges, excl))

    @staticmethod
    def _format_summary(ranges, is_exclude):
        mode  = 'Exclude' if is_exclude else 'Include'
        parts = [f'[{lo:.1f}, {hi:.1f}]' for lo, hi in ranges]
        return f'{mode}: {", ".join(parts)}'

    # ------------------------------------------------------------------ #
    # Operation / band-B toggle                                            #
    # ------------------------------------------------------------------ #

    def _on_show_ranges_toggled(self, state):
        """Toggle the Band A/B groupboxes to give more space to preview."""
        from PyQt5.QtWidgets import QGroupBox
        visible = (state == Qt.Checked)
        # Find Band A and Band B groupboxes in the left panel
        for gb in self.findChildren(QGroupBox):
            if gb.title() in ("Band A", "Band B"):
                gb.setVisible(visible)

    def _refresh_plots(self, *_):
        """Refresh only the plots tab without recalculating results."""
        if self._results:
            self._plots_canvas.plot(
                self._results, self.get_settings(),
                plot_type=self._plot_type_combo.currentText(),
                label_rotation=int(self._label_rotation_combo.currentText().replace("°", "")),
                label_chars=self._label_chars_spin.value(),
                display_labels=self._display_labels_map(),
            )

    def _on_operation_changed(self, *_):
        needs_b = self._op_combo.currentText() != 'A only'
        self._band_b_group.setVisible(needs_b)
        if needs_b and self._band_b is None:
            self._band_b = {'ranges': [], 'is_exclude': False,
                            'metric': 'Baseline-corrected integral'}
        self._schedule()

    # ------------------------------------------------------------------ #
    # Spectra list                                                         #
    # ------------------------------------------------------------------ #

    def _populate_list(self):
        self._list.blockSignals(True)
        self._list.clear()
        spectra = list(self.selected_spectra)
        if not self.sort_ascending:
            spectra = list(reversed(spectra))
        for s in spectra:
            self._list.addItem(s['label'])
        self._list.blockSignals(False)

    def _toggle_sort(self):
        self.sort_ascending = not self.sort_ascending
        self._sort_btn.setText('▲' if self.sort_ascending else '▼')
        sel = {item.text() for item in self._list.selectedItems()}
        self._populate_list()
        rows_to_select = [i for i in range(self._list.count()) if self._list.item(i).text() in sel]
        self._batch_select_rows(rows_to_select)

    def _select_all(self):
        self._list.blockSignals(True)
        self._list.selectAll()
        self._list.blockSignals(False)
        if self._init_complete:
            self._schedule()

    def _clear_selection(self):
        self._list.blockSignals(True)
        self._list.clearSelection()
        self._list.blockSignals(False)
        if self._init_complete:
            self._schedule()

    def _batch_select_rows(self, rows_to_select):
        """Select exactly the given rows as one atomic operation, not one
        item.setSelected() call per row — see this method's callers'
        comment for why that matters at scale."""
        if not rows_to_select:
            return
        model = self._list.model()
        selection = QItemSelection()
        for row in rows_to_select:
            idx = model.index(row, 0)
            selection.select(idx, idx)
        self._list.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)

    def _visible_spectra(self):
        sel = {item.text() for item in self._list.selectedItems()}
        return [s for s in self.selected_spectra if s['label'] in sel]

    # ------------------------------------------------------------------ #
    # Shorten names (this dialog's own checkBox_shorten_names)            #
    # ------------------------------------------------------------------ #

    def _shorten_names_enabled(self) -> bool:
        """True when this dialog's own 'shorten names' checkbox is
        checked — independent of the main window's setting."""
        return self.checkBox_shorten_names.isChecked()

    def _display_labels_map(self) -> dict:
        """{full_label: display_label} for self.selected_spectra, honoring
        the shorten-names checkbox — identity map when disabled. Display
        only; never used for lookup/identity (see label_shortening.py)."""
        return shorten_spectra_labels(self.selected_spectra, self._shorten_names_enabled())

    def _on_shorten_names_toggled(self, *_):
        # Both consumers are paint-only delegates (make_shortened_name_delegate
        # for self._list, make_display_text_delegate for self._table column 0)
        # — an explicit viewport().update() just avoids waiting on the next
        # unrelated repaint for the new state to become visible.
        self._list.viewport().update()
        self._table.viewport().update()

    # ------------------------------------------------------------------ #
    # Preview                                                              #
    # ------------------------------------------------------------------ #

    def _schedule(self, *_):
        if self._init_complete:
            self._timer.start()

    def _refresh_preview(self):
        settings = self.get_settings()
        visible  = self._visible_spectra()
        show_legend = self._show_legend_cb.isChecked()
        self._preview_canvas.plot(visible, settings, show_legend=show_legend,
                                   display_labels=self._display_labels_map())
        # Also refresh results/plots if those tabs are currently visible
        current_tab = self._tabs.tabText(self._tabs.currentIndex())
        if current_tab in ('Results', 'Plots') and visible:
            self._calculate()

    # ------------------------------------------------------------------ #
    # Results                                                              #
    # ------------------------------------------------------------------ #

    def _on_tab_changed(self, idx):
        if not self._init_complete:
            return
        tab = self._tabs.tabText(idx)
        if tab in ('Results', 'Plots'):
            self._calculate()

    def _fallback_manager(self):
        """Only used if this dialog was constructed without a
        BandRatioController (controller=None) — kept for backward
        compatibility with any caller not yet updated to pass one.
        Every current, updated call site provides a real controller, so
        this path is not expected to run in practice."""
        if not hasattr(self, '_local_manager'):
            from src.modules.visualization_analysis.band_ratio_manager import BandRatioManager
            self._local_manager = BandRatioManager()
        return self._local_manager

    def _calculate(self):
        settings = self.get_settings()
        visible  = self._visible_spectra()
        if not visible:
            return

        def _band_ready(band_def):
            if not band_def:
                return False
            if band_def.get('metric') == 'Intensity at x':
                return True
            return bool(band_def.get('ranges'))

        if not _band_ready(settings.get('band_a')):
            self._stats_label.setText(
                '\u26a0  Configure Band A before calculating.'
            )
            self._stats_label.setStyleSheet(
                'background-color: #FFEBEE; padding: 6px; border-radius: 4px; '
                'font-family: monospace; color: #C62828;'
            )
            self._table.setRowCount(0)
            self._plots_canvas.plot([], settings)
            return

        op = settings.get('operation', 'A only')
        if op != 'A only' and not _band_ready(settings.get('band_b')):
            self._stats_label.setText(
                f'\u26a0  Configure Band B before calculating {op}.'
            )
            self._stats_label.setStyleSheet(
                'background-color: #FFEBEE; padding: 6px; border-radius: 4px; '
                'font-family: monospace; color: #C62828;'
            )
            self._table.setRowCount(0)
            self._plots_canvas.plot([], settings)
            return

        self._stats_label.setStyleSheet(
            'background-color: #E8F5E9; padding: 6px; border-radius: 4px; '
            'font-family: monospace;'
        )
        self._results = (
            self.controller.compute_results(visible, settings) if self.controller is not None
            else self._fallback_manager().compute_results(visible, settings)
        )
        self._populate_table(self._results, settings)
        self._plots_canvas.plot(
            self._results, settings,
            plot_type=self._plot_type_combo.currentText(),
            label_rotation=int(self._label_rotation_combo.currentText().replace("°", "")),
            label_chars=self._label_chars_spin.value(),
            display_labels=self._display_labels_map(),
        )

    def _populate_table(self, results, settings):
        op = settings.get('operation', 'A only')
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        vals_a, vals_b, vals_r = [], [], []
        for r in results:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(r['label']))

            def _item(val, color=None):
                txt = f'{val:.6g}' if val is not None and not (isinstance(val, float) and np.isnan(val)) else '—'
                item = QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if color and val is not None:
                    item.setForeground(QColor(color))
                return item

            self._table.setItem(row, 1, _item(r['value_a'], _COLOR_A))
            self._table.setItem(row, 2, _item(r['value_b'], _COLOR_B))
            self._table.setItem(row, 3, _item(r['result']))

            if r['value_a'] is not None: vals_a.append(r['value_a'])
            if r['value_b'] is not None: vals_b.append(r['value_b'])
            if r['result']  is not None and not np.isnan(r['result']): vals_r.append(r['result'])

        self._table.setSortingEnabled(True)

        # Update column header; hide Result column when it duplicates Value A/B
        op_label = {'A only': 'A', 'A / B': 'A / B', 'A - B': 'A − B', 'A + B': 'A + B'}
        self._table.setHorizontalHeaderLabels(
            ['Spectrum', 'Value A', 'Value B', op_label.get(op, 'Result')]
        )
        # Result column is redundant when op is A only or B only
        hide_result = op in ('A only',)
        self._table.setColumnHidden(3, hide_result)
        # Value B column is redundant when op is A only
        self._table.setColumnHidden(2, op == 'A only')

        def _stat(arr, lbl):
            if not arr: return ''
            a = np.array(arr)
            return (f'{lbl}: mean={np.mean(a):.4g}  '
                    f'std={np.std(a, ddof=1 if len(a)>1 else 0):.4g}  '
                    f'min={np.min(a):.4g}  max={np.max(a):.4g}')

        stats = _stat(vals_a, 'A')
        if vals_b:
            if stats: stats += '     '
            stats += _stat(vals_b, 'B')
        if vals_r and op != 'A only':
            if stats: stats += '     '
            stats += _stat(vals_r, op)
        self._stats_label.setText(stats)

    # ------------------------------------------------------------------ #
    # Export                                                               #
    # ------------------------------------------------------------------ #

    def _table_text(self, sep='\t'):
        headers = [self._table.horizontalHeaderItem(c).text()
                   for c in range(self._table.columnCount())]
        lines = [sep.join(headers)]
        for r in range(self._table.rowCount()):
            row = []
            for c in range(self._table.columnCount()):
                item = self._table.item(r, c)
                row.append(item.text() if item else '')
            lines.append(sep.join(row))
        return '\n'.join(lines)

    def _copy_table(self):
        QApplication.clipboard().setText(self._table_text('\t'))

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export results', 'band_ratio_results.csv',
            'CSV files (*.csv);;All files (*)'
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(self._table_text(','))
        except OSError as exc:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Export failed', str(exc))

    def _export_pdf(self):
        from PyQt5.QtWidgets import QMessageBox
        if not self._results:
            QMessageBox.information(self, 'Nothing to Export', 'No results to export yet.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export PDF Report', 'band_ratio_report.pdf',
                                              'PDF files (*.pdf)')
        if not path:
            return
        settings = self.get_settings()
        band_a, band_b = settings.get('band_a') or {}, settings.get('band_b') or {}
        meta = [f"Operation: {settings.get('operation', 'A only')}",
                f"Band A metric: {band_a.get('metric', '')}"]
        if band_b:
            meta.append(f"Band B metric: {band_b.get('metric', '')}")

        headers = [self._table.horizontalHeaderItem(c).text() for c in range(self._table.columnCount())
                  if not self._table.isColumnHidden(c)]
        rows = []
        for r in range(self._table.rowCount()):
            rows.append([self._table.item(r, c).text() if self._table.item(r, c) else ''
                        for c in range(self._table.columnCount()) if not self._table.isColumnHidden(c)])
        labels = [s.get('label', '') for s in self.selected_spectra]

        try:
            from src.modules.utils.pdf_report_utils import export_report_pdf
            export_report_pdf(path, 'Band Ratio / Peak Area Calculator', meta_lines=meta,
                              figure=self._plots_canvas._fig, table_headers=headers, table_rows=rows,
                              source_labels=labels)
        except Exception as exc:
            QMessageBox.warning(self, 'Export failed', str(exc))

    # ------------------------------------------------------------------ #
    # Settings I/O                                                         #
    # ------------------------------------------------------------------ #

    def _restore_settings(self, s):
        if 'band_a' in s:
            self._band_a = dict(s['band_a'])
            self._update_summary_a()
            m = self._band_a.get('metric', 'Baseline-corrected integral')
            idx = self._metric_a.findText(m)
            if idx >= 0: self._metric_a.setCurrentIndex(idx)
        if s.get('band_b') is not None:
            self._band_b = dict(s['band_b'])
            self._update_summary_b()
            m = self._band_b.get('metric', 'Baseline-corrected integral')
            idx = self._metric_b.findText(m)
            if idx >= 0: self._metric_b.setCurrentIndex(idx)
        if 'operation' in s:
            idx = self._op_combo.findText(s['operation'])
            if idx >= 0: self._op_combo.setCurrentIndex(idx)

    def get_settings(self) -> dict:
        band_a = dict(self._band_a)
        band_a['metric'] = self._metric_a.currentText()
        if band_a['metric'] == 'Intensity at x':
            band_a['x_pos'] = self._x_pos_a.value()

        band_b = None
        if self._op_combo.currentText() != 'A only' and self._band_b is not None:
            band_b = dict(self._band_b)
            band_b['metric'] = self._metric_b.currentText()
            if band_b['metric'] == 'Intensity at x':
                band_b['x_pos'] = self._x_pos_b.value()

        return {
            'band_a':    band_a,
            'band_b':    band_b,
            'operation': self._op_combo.currentText(),
        }

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def _show_help(self):
        try:
            from src.help.band_ratio_help import (
                get_band_ratio_help_content, get_band_ratio_help_title)
            from src.help.help_window import show_help_window
            show_help_window(self, get_band_ratio_help_title(),
                             get_band_ratio_help_content())
        except Exception:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Help',
                                    'Help documentation is not available.')


# ======================================================================
# Preview canvas
# ======================================================================

class _PreviewCanvas(FigureCanvas):
    """Overlay of selected spectra with shaded band regions."""

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        self._ax  = self._fig.add_subplot(111)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#f0f0f0')
        self._ax.set_facecolor('#ffffff')
        # Tracks the "N spectra excluded from Mean/SD" warning text (see
        # plot() below) so it can be removed on the next call — text added
        # via self._fig.text() is NOT cleared by ax.clear() (that only
        # clears the axes, not artists added directly to the figure).
        self._warning_text = None

    def plot(self, spectra, settings, show_legend=False, display_labels=None):
        ax = self._ax
        ax.clear()
        ax.set_facecolor('#ffffff')

        # Remove any warning text left over from a previous render before
        # doing anything else — including before the early "no spectra"
        # return below, so an empty selection doesn't leave a stale
        # warning on screen either. Without this, calling plot() again
        # added a brand new text artist every time n_excluded > 0 without
        # ever removing the previous one, so: (a) the warning never went
        # away even after a later selection no longer needed it (nothing
        # ever called .remove() on it), and (b) each redraw where it WAS
        # still needed stacked another overlapping copy on top of the
        # last, since matplotlib doesn't deduplicate figure-level text —
        # exactly the "chaos" of overlapping red text in repeated renders.
        if self._warning_text is not None:
            try:
                self._warning_text.remove()
            except Exception:
                pass
            self._warning_text = None

        if not spectra:
            self.draw_idle()
            return

        from src.modules.visualization_analysis.band_ratio_manager import BandRatioManager
        from src.modules.utils.spectra_validation import axes_match
        mgr = BandRatioManager()
        n   = len(spectra)

        # ── Three-tier rendering based on dataset size ────────────────
        # Tier 1  ≤ 30   : plot all spectra individually
        # Tier 2  31–200 : mean ± SD band + ~20 evenly spaced faded lines
        # Tier 3  > 200  : mean ± SD band only (fastest)

        TIER2_SAMPLE = 20   # number of individual lines shown in tier 2

        # Always compute mean ± SD for tiers 2 & 3; also use mean as
        # the reference spectrum for band shading in ALL tiers (including
        # tier 1 — this is not just a large-dataset concern).
        #
        # Which spectra go into that mean/SD must be decided by whether
        # they actually share x_ref's x-axis (axes_match), not merely
        # whether they have the same NUMBER of points. Two spectra can
        # have identical length while covering completely different
        # ranges (e.g. 0-100 vs 200-300) — Band Ratio's real per-spectrum
        # results are unaffected by this (each spectrum's band value is
        # computed from its own x/y independently, correctly), but this
        # preview's "Mean (n=...)" trace and the value ANNOTATED on the
        # shaded band are both computed from this aggregate — silently
        # averaging point i of one spectrum with point i of an
        # unrelated-range spectrum would show a fabricated number with no
        # indication anything was mixed.
        x_ref = np.asarray(spectra[0].get('x_scale', []), dtype=float)
        y_mat = np.vstack([
            np.asarray(s.get('y_scale', []), dtype=float)
            for s in spectra
            if axes_match(x_ref, np.asarray(s.get('x_scale', []), dtype=float))
        ])
        n_excluded = n - len(y_mat)
        y_mean = np.mean(y_mat, axis=0)
        y_sd   = np.std(y_mat, axis=0, ddof=1) if len(y_mat) > 1 else np.zeros_like(y_mean)

        if n <= 30:
            # Tier 1 — all individual spectra
            for i, s in enumerate(spectra):
                x = np.asarray(s.get('x_scale', []), dtype=float)
                y = np.asarray(s.get('y_scale', []), dtype=float)
                if not len(x): continue
                ax.plot(x, y, color=_COLORS[i % len(_COLORS)],
                        lw=0.9, alpha=0.55, zorder=2)
        else:
            # Tier 2 / 3 — mean ± SD shaded band
            ax.fill_between(x_ref, y_mean - y_sd, y_mean + y_sd,
                            color='#B0BEC5', alpha=0.35, zorder=2,
                            label='\u00b11 SD')
            ax.plot(x_ref, y_mean, color='#546E7A', lw=1.4,
                    zorder=3, label=f'Mean (n={n})')

            if n <= 200:
                # Tier 2 — also show a sample of individual spectra
                step = max(1, n // TIER2_SAMPLE)
                sample = spectra[::step]
                for s in sample:
                    x = np.asarray(s.get('x_scale', []), dtype=float)
                    y = np.asarray(s.get('y_scale', []), dtype=float)
                    if not len(x): continue
                    ax.plot(x, y, color='#888', lw=0.6,
                            alpha=0.25, zorder=1)

            ax.legend(fontsize=8, loc='best', framealpha=0.7)

        # Use mean spectrum as the representative for band shading
        y_r = y_mean

        def _shade(band_def, color, label):
            if band_def is None: return
            ranges     = band_def.get('ranges', [])
            is_exclude = band_def.get('is_exclude', False)
            metric     = band_def.get('metric', 'Baseline-corrected integral')

            # Intensity at x: show as dashed vertical line + point marker
            if metric == 'Intensity at x':
                x_pos = band_def.get('x_pos', 0.0)
                # Find nearest y value on mean spectrum
                if len(x_ref) > 0:
                    idx = int(np.argmin(np.abs(x_ref - x_pos)))
                    y_val = float(y_r[idx])
                    ax.axvline(x_pos, color=color, lw=1.8, ls='--',
                               alpha=0.85, zorder=5)
                    ax.plot(x_ref[idx], y_val, 'o', color=color,
                            markersize=7, zorder=6)
                    n_spec = len(spectra)
                    note = f' (mean, n={n_spec})' if n_spec > 1 else ''
                    ax.annotate(
                        f'{label}={y_val:.3g}{note}',
                        xy=(x_ref[idx], y_val),
                        fontsize=8, color=color, ha='left',
                        xytext=(6, 0), textcoords='offset points'
                    )
                return

            # Do not shade if no ranges are defined — avoids misleading full-spectrum shading
            if not ranges:
                return

            include = [] if is_exclude else ranges
            exclude = ranges if is_exclude else []
            x_seg, y_seg = mgr._apply_range_filter(x_ref, y_r, include, exclude)

            if len(x_seg) < 2: return

            # Split x_seg into contiguous sub-segments (gaps > 2 × median step)
            # so fill_between does not bridge excluded regions
            dx = np.diff(x_seg)
            if len(dx) > 0:
                median_step = np.median(np.abs(dx))
                gap_mask = np.abs(dx) > 3 * median_step
                split_at = np.where(gap_mask)[0] + 1
            else:
                split_at = []
            segments_x = np.split(x_seg, split_at)
            segments_y = np.split(y_seg, split_at)

            for sx, sy in zip(segments_x, segments_y):
                if len(sx) < 2: continue
                if metric == 'Baseline-corrected integral':
                    x0, y0 = sx[0], sy[0]
                    x1, y1 = sx[-1], sy[-1]
                    slope = (y1 - y0) / (x1 - x0) if x1 != x0 else 0.0
                    baseline = y0 + slope * (sx - x0)
                    ax.fill_between(sx, baseline, sy, color=color,
                                    alpha=0.45, zorder=5,
                                    edgecolor=color, linewidth=0)
                    ax.plot(sx, baseline, color=color,
                            lw=1.5, ls='--', alpha=0.9, zorder=6)
                else:
                    ax.fill_between(sx, 0, sy, color=color,
                                    alpha=0.40, zorder=5)

            # Vertical markers at included segment boundaries
            for sx in segments_x:
                if len(sx) < 2: continue
                ax.axvline(sx[0],  color=color, lw=0.8, ls=':', alpha=0.5)
                ax.axvline(sx[-1], color=color, lw=0.8, ls=':', alpha=0.5)

            # Compute and show value on first segment
            value = mgr._compute_metric(x_seg, y_seg, metric)
            if value is not None and not np.isnan(value):
                mid_x = x_seg[len(x_seg) // 2]
                n_spec = len(spectra)
                note = f' (mean, n={n_spec})' if n_spec > 1 else ''
                ax.annotate(f'{label}={value:.3g}{note}',
                            xy=(mid_x, np.max(y_seg)),
                            fontsize=8, color=color, ha='center',
                            xytext=(0, 6), textcoords='offset points')

        band_a = settings.get('band_a')
        band_b = settings.get('band_b')
        _shade(band_a, _COLOR_A, 'A')
        _shade(band_b, _COLOR_B, 'B')

        if show_legend and n <= 30:
            # Add per-spectrum legend (only sensible for small datasets)
            dmap = display_labels or {}
            handles = [ax.lines[i] for i in range(min(n, len(ax.lines)))]
            labels  = [dmap.get(s.get("label", f"S{i}"), s.get("label", f"S{i}"))
                       for i, s in enumerate(spectra)]
            ax.legend(handles[:len(labels)], labels,
                      fontsize=6, loc="best", framealpha=0.6,
                      ncol=max(1, n // 15))
        ax.set_xlabel('x', fontsize=9)
        ax.set_ylabel('Intensity', fontsize=9)
        _n = len(spectra)
        ax.set_title(f'Band preview — {_n} {"spectrum" if _n == 1 else "spectra"}', fontsize=10)
        if n_excluded > 0:
            self._warning_text = self._fig.text(
                0.5, 0.002,
                f'\u26a0 {n_excluded} spectrum/spectra excluded from the Mean/SD '
                f'trace above — different x-axis than the first selected spectrum. '
                f'Each spectrum\'s own Band A/B RESULT is still computed correctly '
                f'from its own data regardless of this.',
                ha='center', fontsize=7, color='#C62828')
        ax.grid(True, linestyle='--', alpha=0.35)
        self._fig.tight_layout()
        self.draw_idle()

# ======================================================================
# Results Plots Canvas
# ======================================================================

class _ResultsPlotsCanvas(FigureCanvas):
    """
    Bar/scatter plots of Value A, Value B, and Result across spectra.
    Shows one subplot per active value column.
    """

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#ffffff')

    def plot(self, results, settings,
             plot_type="Bar", label_rotation=45, label_chars=0, display_labels=None):
        self._fig.clear()

        if not results:
            self.draw_idle()
            return

        op        = settings.get('operation', 'A only')
        has_b     = any(r['value_b'] is not None for r in results)
        has_r     = op != 'A only'
        op_labels = {'A only': 'A', 'A / B': 'A / B',
                     'A - B': 'A − B', 'A + B': 'A + B'}
        result_label = op_labels.get(op, 'Result')

        # Build list of (values, label, color) to plot
        series = []
        vals_a = [r['value_a'] for r in results]
        if any(v is not None for v in vals_a):
            series.append((vals_a, 'Value A', _COLOR_A))
        if has_b:
            vals_b = [r['value_b'] for r in results]
            if any(v is not None for v in vals_b):
                series.append((vals_b, 'Value B', _COLOR_B))
        if has_r:
            vals_r = [r['result'] for r in results]
            if any(v is not None and not (isinstance(v, float) and np.isnan(v))
                   for v in vals_r):
                series.append((vals_r, result_label, '#2E7D32'))

        n_plots = len(series)
        if n_plots == 0:
            self.draw_idle()
            return

        dmap = display_labels or {}
        labels = [dmap.get(r['label'], r['label']) for r in results]
        x      = np.arange(len(labels))

        axes = self._fig.subplots(n_plots, 1, sharex=True)
        if n_plots == 1:
            axes = [axes]

        for ax, (vals, title, color) in zip(axes, series):
            ax.set_facecolor('#ffffff')
            y = np.array([v if v is not None and not
                          (isinstance(v, float) and np.isnan(v))
                          else np.nan for v in vals])
            if plot_type in ("Bar", "Bar + Line"):
                ax.bar(x, y, color=color, alpha=0.70, width=0.6)
            if plot_type in ("Line", "Bar + Line", "Scatter"):
                mk = "o" if plot_type == "Scatter" else "o"
                ls = "-" if plot_type != "Scatter" else "None"
                ax.plot(x, y, color=color, lw=1.2 if plot_type != "Scatter" else 0,
                        marker=mk, markersize=5 if plot_type == "Scatter" else 4,
                        ls=ls, alpha=0.9)
            ax.axhline(0, color='#888', lw=0.6, ls='--')
            ax.set_ylabel(title, fontsize=9, color=color)
            ax.tick_params(labelsize=8)
            ax.grid(True, axis='y', linestyle='--', alpha=0.4)
            # Mean line
            valid = y[~np.isnan(y)]
            if len(valid):
                ax.axhline(np.mean(valid), color=color, lw=1.0,
                           ls=':', alpha=0.7,
                           label=f'mean={np.mean(valid):.4g}')
                ax.legend(fontsize=7, loc='upper right', framealpha=0.7)

        # X tick labels
        ax_bottom = axes[-1]
        def _fmt(lbl):
            return lbl[-label_chars:] if label_chars > 0 else lbl
        ha = "right" if label_rotation > 0 else "center"
        if len(labels) <= 60:
            ax_bottom.set_xticks(x)
            ax_bottom.set_xticklabels([_fmt(l) for l in labels],
                                      rotation=label_rotation, ha=ha, fontsize=7)
        else:
            step = max(1, len(labels) // 30)
            ax_bottom.set_xticks(x[::step])
            ax_bottom.set_xticklabels(
                [_fmt(labels[i]) for i in range(0, len(labels), step)],
                rotation=label_rotation, ha=ha, fontsize=7)

        self._fig.tight_layout()
        self.draw_idle()
