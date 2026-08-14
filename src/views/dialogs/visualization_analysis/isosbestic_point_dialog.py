# src/views/dialogs/visualization_analysis/isosbestic_point_dialog.py
"""
Isosbestic/Isodichroic Point Detection dialog.

Layout
------
Left panel (fixed 340 px)
    Spectra list — sort / select-all / clear
    Search range — x-min / x-max spinboxes, Reset to full range
    Sensitivity — minimum prominence (%) spinbox + '?' help button
    Max candidates shown — spinbox
    Help | OK | Cancel

Right panel
    Top    — plot: spectra overlay (top subplot) + std(x) curve (bottom
             subplot), both sharing the x-axis, with vertical markers at
             every detected candidate point
    Bottom — Results table (x, mean y, std, prominence, relative
             tightness) + Copy to clipboard / Export CSV

Read-only analysis — no Apply/Add-as-New (see IsosbesticPointController's
docstring for why): nothing here is ever written back to the spectra
list, so OK and Cancel behave identically except for which settings are
remembered for next time.
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton, QLabel,
    QDoubleSpinBox, QSpinBox, QListWidget, QSizePolicy, QSplitter,
    QWidget, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QApplication, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    make_shortened_name_delegate, make_shorten_names_checkbox, shorten_spectra_labels,
)
from src.modules.visualization_analysis.isosbestic_point_manager import (
    DEFAULT_MIN_PROMINENCE_PCT, DEFAULT_MIN_SIGNAL_PCT, DEFAULT_MAX_CANDIDATES,
)

logger = get_logger(__name__)

_COLORS = [
    '#1f77b4', '#d62728', '#2ca02c', '#ff7f0e',
    '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]
_MARKER_COLOR = '#2E7D32'


class IsosbesticPointDialog(QDialog):

    def __init__(self, parent=None, selected_spectra=None,
                 current_settings=None, controller=None):
        super().__init__(parent)
        self.setWindowTitle('Isosbestic / Isodichroic Point Detection')
        self.setMinimumSize(1020, 680)
        self.resize(1280, 820)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        # IsosbesticPointController, if given — see that class's docstring.
        self.controller = controller
        self.selected_spectra = list(selected_spectra or [])
        self._settings = dict(current_settings or {})
        self._last_result = None

        all_x = (
            np.asarray(self.selected_spectra[0]['x_scale'], dtype=float)
            if self.selected_spectra else np.array([0.0, 1.0])
        )
        self._full_x_min = float(np.min(all_x)) if len(all_x) else 0.0
        self._full_x_max = float(np.max(all_x)) if len(all_x) else 1.0

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._calculate)

        self.sort_ascending = True
        self._init_complete = False
        self._shown_once = False

        self._build_ui()
        self._populate_list()
        self._restore_settings(self._settings)
        self._init_complete = True
        self._select_all()

    def showEvent(self, event):
        super().showEvent(event)
        # The very first plot happens (via the 300ms debounce timer) while
        # the dialog is still being constructed, before Qt has settled the
        # splitters into their final on-screen sizes — so matplotlib's
        # tight_layout() computes subplot positions for a provisional,
        # too-small canvas size and the plot doesn't fill the available
        # area. Any later recompute (e.g. changing a search-range or
        # sensitivity control) re-runs tight_layout() against the by-then
        # correct final size and looks right — which is exactly what was
        # reported. Force one more recompute right after the dialog is
        # actually shown, once, so it fills the space from the start
        # without requiring the user to touch a control first.
        if not self._shown_once:
            self._shown_once = True
            QTimer.singleShot(0, self._calculate)

    # ------------------------------------------------------------------ #
    # UI                                                                    #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 940])
        root.addWidget(splitter)

    # ── Left panel ──────────────────────────────────────────────────────

    def _build_left(self):
        w = QWidget()
        w.setFixedWidth(340)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(self._build_range_group())
        layout.addWidget(self._build_sensitivity_group())

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

    def _build_range_group(self):
        group = QGroupBox('Search range')
        layout = QVBoxLayout(group)

        row = QHBoxLayout()
        row.addWidget(QLabel('X min:'))
        self._x_min_spin = QDoubleSpinBox()
        self._x_min_spin.setRange(-1e9, 1e9)
        self._x_min_spin.setDecimals(3)
        self._x_min_spin.setValue(self._full_x_min)
        self._x_min_spin.valueChanged.connect(self._schedule)
        row.addWidget(self._x_min_spin)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel('X max:'))
        self._x_max_spin = QDoubleSpinBox()
        self._x_max_spin.setRange(-1e9, 1e9)
        self._x_max_spin.setDecimals(3)
        self._x_max_spin.setValue(self._full_x_max)
        self._x_max_spin.valueChanged.connect(self._schedule)
        row2.addWidget(self._x_max_spin)
        layout.addLayout(row2)

        reset_btn = QPushButton('Reset to full range')
        reset_btn.setAutoDefault(False)
        reset_btn.clicked.connect(self._reset_range)
        layout.addWidget(reset_btn)
        return group

    def _build_sensitivity_group(self):
        group = QGroupBox('Detection sensitivity')
        layout = QVBoxLayout(group)

        row = QHBoxLayout()
        row.addWidget(QLabel('Minimum prominence:'))
        self._prominence_spin = QDoubleSpinBox()
        self._prominence_spin.setRange(0.1, 100.0)
        self._prominence_spin.setSuffix(' %')
        self._prominence_spin.setDecimals(1)
        self._prominence_spin.setValue(DEFAULT_MIN_PROMINENCE_PCT)
        self._prominence_spin.valueChanged.connect(self._schedule)
        row.addWidget(self._prominence_spin)
        prom_help = QPushButton('?')
        prom_help.setFixedWidth(24)
        prom_help.setAutoDefault(False)
        prom_help.setStyleSheet(
            'QPushButton { background-color: #F57C00; color: white; border: none; '
            'border-radius: 4px; font-weight: bold; padding: 2px; } '
            'QPushButton:hover { background-color: #E65100; }'
        )
        prom_help.clicked.connect(self._show_prominence_help)
        row.addWidget(prom_help)
        layout.addLayout(row)

        row_sig = QHBoxLayout()
        row_sig.addWidget(QLabel('Minimum signal level:'))
        self._signal_spin = QDoubleSpinBox()
        self._signal_spin.setRange(0.0, 100.0)
        self._signal_spin.setSuffix(' %')
        self._signal_spin.setDecimals(1)
        self._signal_spin.setValue(DEFAULT_MIN_SIGNAL_PCT)
        self._signal_spin.valueChanged.connect(self._schedule)
        row_sig.addWidget(self._signal_spin)
        signal_help = QPushButton('?')
        signal_help.setFixedWidth(24)
        signal_help.setAutoDefault(False)
        signal_help.setStyleSheet(
            'QPushButton { background-color: #F57C00; color: white; border: none; '
            'border-radius: 4px; font-weight: bold; padding: 2px; } '
            'QPushButton:hover { background-color: #E65100; }'
        )
        signal_help.clicked.connect(self._show_signal_help)
        row_sig.addWidget(signal_help)
        layout.addLayout(row_sig)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel('Max candidates shown:'))
        self._max_candidates_spin = QSpinBox()
        self._max_candidates_spin.setRange(1, 20)
        self._max_candidates_spin.setValue(DEFAULT_MAX_CANDIDATES)
        self._max_candidates_spin.valueChanged.connect(self._schedule)
        row2.addWidget(self._max_candidates_spin)
        layout.addLayout(row2)
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
        layout.addLayout(hdr)

        # Display-only "shorten names" toggle — this dialog's own,
        # independent on/off state (see label_shortening.py's
        # make_shorten_names_checkbox), unrelated to the main window's
        # checkbox and always starting unchecked.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _state: self._list.viewport().update())
        layout.addWidget(self.checkBox_shorten_names)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self._list.itemSelectionChanged.connect(self._schedule)
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
        outer = QVBoxLayout(w)
        outer.setContentsMargins(4, 4, 4, 4)

        right_splitter = QSplitter(Qt.Vertical)

        plot_widget = QWidget()
        pl = QVBoxLayout(plot_widget)
        pl.setContentsMargins(0, 0, 0, 0)
        self._canvas = _IsosbesticPlotCanvas(plot_widget)
        pl.addWidget(NavigationToolbar(self._canvas, plot_widget))
        pl.addWidget(self._canvas)
        right_splitter.addWidget(plot_widget)

        results_widget = QWidget()
        rl = QVBoxLayout(results_widget)
        rl.setContentsMargins(0, 4, 0, 0)

        self._status_label = QLabel('')
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            'background-color: #FFF8E1; padding: 6px; border-radius: 4px; '
            'color: #E65100;'
        )
        self._status_label.setVisible(False)
        rl.addWidget(self._status_label)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ['X', 'Mean Y', 'Std across spectra', 'Prominence', 'Relative tightness']
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        rl.addWidget(self._table, stretch=1)

        export_row = QHBoxLayout()
        export_row.addStretch()
        copy_btn = QPushButton('⧉  Copy to clipboard')
        copy_btn.clicked.connect(self._copy_table)
        export_row.addWidget(copy_btn)
        csv_btn = QPushButton('\U0001f4be  Export CSV…')
        csv_btn.clicked.connect(self._export_csv)
        export_row.addWidget(csv_btn)
        pdf_btn = QPushButton('\U0001f4c4  Export PDF…')
        pdf_btn.clicked.connect(self._export_pdf)
        export_row.addWidget(pdf_btn)
        rl.addLayout(export_row)

        right_splitter.addWidget(results_widget)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)
        outer.addWidget(right_splitter)
        return w

    # ------------------------------------------------------------------ #
    # Range / sensitivity                                                  #
    # ------------------------------------------------------------------ #

    def _reset_range(self):
        self._x_min_spin.blockSignals(True)
        self._x_max_spin.blockSignals(True)
        self._x_min_spin.setValue(self._full_x_min)
        self._x_max_spin.setValue(self._full_x_max)
        self._x_min_spin.blockSignals(False)
        self._x_max_spin.blockSignals(False)
        self._schedule()

    def _show_prominence_help(self):
        QMessageBox.information(
            self, 'Minimum Prominence — Help',
            "<html><body style='font-family: Arial, sans-serif; font-size: 12px;'>"
            "<p>At each x-value, this operation measures how much the selected "
            "spectra <b>disagree</b> with each other there (their standard "
            "deviation). A genuine isosbestic/isodichroic point is a "
            "wavelength where that disagreement drops to a clear, "
            "distinctive minimum — a dip that stands out from the general "
            "noise level, not just the single lowest point in an otherwise "
            "flat, noisy curve.</p>"
            "<p><b>Prominence</b> measures exactly that distinctiveness: how "
            "far the disagreement would have to rise, on its shallower side, "
            "before reaching a point that's just as disagreeing somewhere "
            "else in the search range. A shallow, noise-driven wiggle has "
            "low prominence; a real, clean crossing point — where the "
            "spectra collapse together tightly compared to how much they "
            "disagree everywhere else — has high prominence.</p>"
            "<p>The percentage here is relative to the full range of "
            "disagreement seen across the searched x-range. "
            "<b>Lower</b> it to see more, weaker candidates; <b>raise</b> it "
            "to see only the most convincing one(s).</p>"
            "</body></html>"
        )

    def _show_signal_help(self):
        QMessageBox.information(
            self, 'Minimum Signal Level — Help',
            "<html><body style='font-family: Arial, sans-serif; font-size: 12px;'>"
            "<p>Real spectra usually have long stretches of x-axis where "
            "<b>neither</b> component has any real signal — a flat baseline "
            "gap between separated bands, for example. Every selected "
            "spectrum agrees there too (they're all approximately zero), so "
            "that gap can look exactly like a tight, low-disagreement dip — "
            "sometimes an even SHARPER one than the real crossing, since it "
            "drops all the way to the same near-zero value on both sides. "
            "But that's not a real isosbestic/isodichroic point: nothing is "
            "actually happening there, there's no signal to agree about.</p>"
            "<p>This setting filters those out: a candidate is only kept if "
            "the mean signal at that point is at least this percentage of "
            "the largest mean signal anywhere in the searched range — i.e. "
            "there must be genuine, non-trivial signal from the "
            "interconverting species at the crossing, not just an empty "
            "region where everyone reads zero together.</p>"
            "<p><b>Lower</b> it if a real but weak crossing is being "
            "excluded; <b>raise</b> it if empty/baseline regions are still "
            "showing up as candidates.</p>"
            "</body></html>"
        )

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
        for i in range(self._list.count()):
            if self._list.item(i).text() in sel:
                self._list.item(i).setSelected(True)

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

    def _visible_spectra(self):
        sel = {item.text() for item in self._list.selectedItems()}
        return [s for s in self.selected_spectra if s['label'] in sel]

    # ------------------------------------------------------------------ #
    # Shorten names                                                        #
    # ------------------------------------------------------------------ #

    def _shorten_names_enabled(self) -> bool:
        return self.checkBox_shorten_names.isChecked()

    def _display_labels_map(self) -> dict:
        return shorten_spectra_labels(self.selected_spectra, self._shorten_names_enabled())

    # ------------------------------------------------------------------ #
    # Compute / render                                                     #
    # ------------------------------------------------------------------ #

    def _schedule(self, *_):
        if self._init_complete:
            self._timer.start()

    def _fallback_manager(self):
        """Only used if this dialog was constructed without an
        IsosbesticPointController (controller=None)."""
        if not hasattr(self, '_local_manager'):
            from src.modules.visualization_analysis.isosbestic_point_manager import IsosbesticPointManager
            self._local_manager = IsosbesticPointManager()
        return self._local_manager

    def _calculate(self):
        visible = self._visible_spectra()
        settings = self.get_settings()

        self._status_label.setVisible(False)

        if len(visible) < 2:
            self._table.setRowCount(0)
            self._canvas.plot([], None, [])
            self._status_label.setText('Select at least 2 spectra (3 or more recommended).')
            self._status_label.setStyleSheet(
                'background-color: #FFEBEE; padding: 6px; border-radius: 4px; color: #C62828;'
            )
            self._status_label.setVisible(True)
            return

        try:
            result = (
                self.controller.compute_results(visible, settings) if self.controller is not None
                else self._fallback_manager().compute_results(visible, settings)
            )
        except ValueError as exc:
            self._table.setRowCount(0)
            self._canvas.plot([], None, [])
            self._status_label.setText(str(exc))
            self._status_label.setStyleSheet(
                'background-color: #FFEBEE; padding: 6px; border-radius: 4px; color: #C62828;'
            )
            self._status_label.setVisible(True)
            return

        self._last_result = result
        if result.get('warning'):
            self._status_label.setText('⚠  ' + result['warning'])
            self._status_label.setStyleSheet(
                'background-color: #FFF8E1; padding: 6px; border-radius: 4px; color: #E65100;'
            )
            self._status_label.setVisible(True)

        self._populate_table(result['candidates'])
        self._canvas.plot(visible, result, self._display_labels_map())

    def _populate_table(self, candidates):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for c in candidates:
            row = self._table.rowCount()
            self._table.insertRow(row)

            def _item(val, fmt='{:.6g}'):
                item = QTableWidgetItem(fmt.format(val))
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                return item

            self._table.setItem(row, 0, _item(c['x']))
            self._table.setItem(row, 1, _item(c['mean_y']))
            self._table.setItem(row, 2, _item(c['std']))
            self._table.setItem(row, 3, _item(c['prominence']))
            self._table.setItem(row, 4, _item(c['relative_tightness'], '{:.4f}'))
        self._table.setSortingEnabled(True)

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
            self, 'Export results', 'isosbestic_point_results.csv',
            'CSV files (*.csv);;All files (*)'
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(self._table_text(','))
        except OSError as exc:
            QMessageBox.warning(self, 'Export failed', str(exc))

    def _export_pdf(self):
        if self._last_result is None or self._table.rowCount() == 0:
            QMessageBox.information(self, 'Nothing to Export',
                                    'No candidate isosbestic points to export yet.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export PDF Report', 'isosbestic_point_report.pdf',
                                              'PDF files (*.pdf)')
        if not path:
            return
        meta = [
            f"Search range: {self._x_min_spin.value():g} – {self._x_max_spin.value():g}",
            f"Minimum prominence: {self._prominence_spin.value():g}%",
            f"Minimum signal: {self._signal_spin.value():g}%",
            f"Max candidates shown: {self._max_candidates_spin.value()}",
            f"Candidates found: {self._table.rowCount()}",
        ]
        headers = [self._table.horizontalHeaderItem(c).text() for c in range(self._table.columnCount())]
        rows = []
        for r in range(self._table.rowCount()):
            rows.append([self._table.item(r, c).text() if self._table.item(r, c) else ''
                        for c in range(self._table.columnCount())])
        labels = [s.get('label', '') for s in self.selected_spectra]

        try:
            from src.modules.utils.pdf_report_utils import export_report_pdf
            export_report_pdf(path, 'Isosbestic / Isodichroic Point Detection', meta_lines=meta,
                              figure=self._canvas._fig, table_headers=headers, table_rows=rows,
                              source_labels=labels)
        except Exception as exc:
            QMessageBox.warning(self, 'Export failed', str(exc))

    # ------------------------------------------------------------------ #
    # Settings I/O                                                         #
    # ------------------------------------------------------------------ #

    def _restore_settings(self, s):
        if 'x_range' in s and s['x_range']:
            lo, hi = s['x_range']
            self._x_min_spin.setValue(lo)
            self._x_max_spin.setValue(hi)
        if 'min_prominence_pct' in s:
            self._prominence_spin.setValue(s['min_prominence_pct'])
        if 'min_signal_pct' in s:
            self._signal_spin.setValue(s['min_signal_pct'])
        if 'max_candidates' in s:
            self._max_candidates_spin.setValue(s['max_candidates'])

    def get_settings(self) -> dict:
        return {
            'x_range': (self._x_min_spin.value(), self._x_max_spin.value()),
            'min_prominence_pct': self._prominence_spin.value(),
            'min_signal_pct': self._signal_spin.value(),
            'max_candidates': self._max_candidates_spin.value(),
        }

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def _show_help(self):
        try:
            from src.help.isosbestic_point_help import (
                get_isosbestic_point_help_content, get_isosbestic_point_help_title)
            from src.help.help_window import show_help_window
            show_help_window(self, get_isosbestic_point_help_title(),
                             get_isosbestic_point_help_content())
        except Exception:
            QMessageBox.information(self, 'Help', 'Help documentation is not available.')


# ======================================================================
# Plot canvas
# ======================================================================

class _IsosbesticPlotCanvas(FigureCanvas):
    """Two stacked subplots sharing the x-axis: spectra overlay on top,
    cross-spectrum std(x) curve on the bottom, with vertical dashed
    markers at every detected candidate point in both."""

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        self._ax_spectra = self._fig.add_subplot(211)
        self._ax_std = self._fig.add_subplot(212, sharex=self._ax_spectra)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#f0f0f0')

    def resizeEvent(self, event):
        # Belt-and-braces fix for the plot not filling its space on first
        # display: Figure(tight_layout=True) only recomputes subplot
        # positions against the canvas's CURRENT pixel size at the moment
        # it draws, but the splitters this canvas lives in don't reach
        # their final on-screen sizes in a single step — Qt can resize
        # this widget more than once while settling the layout (an early
        # provisional size, then the real final one). Re-running
        # tight_layout() explicitly on every resize, not just relying on
        # the one-shot recompute after showEvent, means whichever resize
        # turns out to be the LAST one always leaves the plot correctly
        # laid out, regardless of how many intermediate sizes Qt passes
        # through first.
        super().resizeEvent(event)
        if self._fig.get_axes():
            try:
                self._fig.tight_layout()
            except Exception:
                pass
            self.draw_idle()

    def plot(self, spectra, result, display_labels=None):
        ax1, ax2 = self._ax_spectra, self._ax_std
        ax1.clear()
        ax2.clear()
        ax1.set_facecolor('#ffffff')
        ax2.set_facecolor('#ffffff')

        if not spectra:
            ax1.text(0.5, 0.5, 'Select spectra to see a preview here.',
                      transform=ax1.transAxes, ha='center', va='center',
                      color='#1976D2', fontsize=10)
            self.draw_idle()
            return

        dmap = display_labels or {}
        for i, s in enumerate(spectra):
            x = np.asarray(s.get('x_scale', []), dtype=float)
            y = np.asarray(s.get('y_scale', []), dtype=float)
            if not len(x):
                continue
            label = dmap.get(s.get('label', ''), s.get('label', f'S{i}'))
            ax1.plot(x, y, color=_COLORS[i % len(_COLORS)], lw=0.9,
                      alpha=0.75, label=label if len(spectra) <= 15 else None)

        if len(spectra) <= 15:
            ax1.legend(fontsize=6, loc='best', framealpha=0.6, ncol=max(1, len(spectra) // 8))

        ax1.set_ylabel('Intensity', fontsize=9)
        ax1.set_title(f'{len(spectra)} spectra', fontsize=10)
        ax1.grid(True, linestyle='--', alpha=0.35)

        if result is not None and len(result.get('x', [])):
            ax2.plot(result['x'], result['std_curve'], color='#546E7A', lw=1.2)
            ax2.fill_between(result['x'], 0, result['std_curve'],
                              color='#B0BEC5', alpha=0.3)
            for c in result.get('candidates', []):
                ax1.axvline(c['x'], color=_MARKER_COLOR, lw=1.4, ls='--', alpha=0.85, zorder=5)
                ax2.axvline(c['x'], color=_MARKER_COLOR, lw=1.4, ls='--', alpha=0.85, zorder=5)
                ax2.plot(c['x'], c['std'], 'o', color=_MARKER_COLOR, markersize=6, zorder=6)
                ax1.annotate(f"{c['x']:.4g}", xy=(c['x'], ax1.get_ylim()[1]),
                              fontsize=7, color=_MARKER_COLOR, ha='center', va='bottom',
                              xytext=(0, 2), textcoords='offset points')

        ax2.set_xlabel('X', fontsize=9)
        ax2.set_ylabel('Std across\nspectra', fontsize=9)
        ax2.grid(True, linestyle='--', alpha=0.35)

        self._fig.tight_layout()
        self.draw_idle()
