# src/views/dialogs/visualization_analysis/kinetics_fitting_dialog.py
"""
Kinetics Fitting dialog.

Layout mirrors PLSDialog's shape (control panel left, single matplotlib
canvas + a mode dropdown on the right, explicit "Run" button rather than
auto-recompute, background QThread so a slow global-analysis fit doesn't
freeze the UI) with one addition unique to this tool: a per-spectrum TIME
table (same auto-guess-from-label / editable / paste pattern as
MeltingCurveDialog's temps_table, trimmed to a single editable column and
reusing PLSDialog's simpler single-column clipboard-shortcut approach)
since every spectrum needs a known time value, the same way PLS needs a
known calibration value per spectrum.

Two modes, one shared time table:
    - Single wavelength: extract one (time, signal) trace at a chosen
      x-position and fit a sum of 1-4 exponentials to it.
    - Global analysis: fit ONE shared set of rate constants across every
      wavelength of the whole selected series at once (variable
      projection -- see KineticsManager's docstring), producing
      Decay-Associated Spectra (DAS).

Read-only analysis -- no Apply/Add-as-New, no Operations History entry
(see KineticsController's docstring for why): nothing here is ever
written back to the spectra list.

Built with the lessons learned from PLSDialog's own bug-fix history
applied from the start, rather than after the fact:
    - showEvent drains any wait-cursor left active by the caller (see
      PLSDialog.showEvent's comment for the full explanation).
    - Table columns use Interactive resize + resizeColumnsToContents(),
      never Stretch (which silently blocks all manual column resizing).
    - Splitter panes use setMinimumWidth (never setFixedWidth, which
      makes a splitter unable to do anything but snap between that exact
      size and 0) plus setChildrenCollapsible(False) and a widened,
      visibly-styled handle.
    - The Shorten Names delegate is wired up on every table that shows
      spectrum names, not just the input table.
"""

import numpy as np
import re
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton, QLabel,
    QDoubleSpinBox, QSpinBox, QCheckBox, QRadioButton, QButtonGroup,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSplitter, QWidget, QSizePolicy, QFileDialog, QApplication, QMessageBox,
    QShortcut, QProgressDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QKeySequence, QCursor

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    compute_distinguishing_labels, make_display_text_delegate, make_shorten_names_checkbox,
)
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)

COL_SPECTRUM = 0
COL_TIME = 1

MODE_SINGLE = 'single'
MODE_GLOBAL = 'global'

# Matches every signed/unsigned float or int found in a spectrum label --
# same regex as MeltingCurveDialog's own _NUMBER_RE, used only to seed a
# reasonable starting guess for each spectrum's time value; never trusted
# as the final value.
_NUMBER_RE = re.compile(r'-?\d+\.?\d*')


class _ComputeWorker(QThread):
    """Runs a single callable on a background thread -- identical pattern
    to PLSDialog's/ClusterAnalysisDialog's own copy."""
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


class _KineticsPlotCanvas(FigureCanvas):
    """One matplotlib Figure whose content is switched by
    self.visualization_mode -- same single-canvas-plus-dropdown approach
    as PLSDialog's _PLSPlotCanvas."""

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#f0f0f0')
        self.visualization_mode = 'trace'

    def resizeEvent(self, event):
        # Same fix as PLSDialog's/IsosbesticPointDialog's canvas -- see
        # those files' comments for the full explanation (tight_layout
        # computed against a provisional, not-yet-final canvas size on
        # first draw).
        super().resizeEvent(event)
        if self._fig.get_axes():
            try:
                self._fig.tight_layout()
            except Exception:
                pass
            self.draw_idle()

    def plot(self, mode, result, preview_wavelength=None):
        self._fig.clear()
        if result is None:
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5, 'Click "Run Fit" to fit a model.',
                     transform=ax.transAxes, ha='center', va='center',
                     color='#1976D2', fontsize=10)
            self.draw_idle()
            return

        view = self.visualization_mode
        if mode == MODE_SINGLE:
            if view == 'components':
                self._plot_single_components(result)
            else:
                self._plot_single_trace(result)
        else:
            if view == 'das':
                self._plot_das(result)
            else:
                self._plot_global_trace(result, preview_wavelength)
        self.draw_idle()

    # -- Single wavelength views -----------------------------------
    def _plot_single_trace(self, result):
        ax1 = self._fig.add_subplot(211)
        ax2 = self._fig.add_subplot(212, sharex=ax1)
        t = result['t']
        y = result['y']
        y_fit = result['fit']['y_fit']
        ax1.scatter(t, y, s=18, color='#1565C0', label='Data', zorder=3)
        ax1.plot(t, y_fit, color='#E65100', linewidth=1.8, label='Fit')
        ax1.set_ylabel('Signal')
        ax1.legend(fontsize=8)
        ax1.set_title('Kinetic trace + fit')

        residual = y - y_fit
        ax2.axhline(0, color='#999', linewidth=0.8)
        ax2.scatter(t, residual, s=14, color='#C62828')
        ax2.set_xlabel('Time')
        ax2.set_ylabel('Residual')

    def _plot_single_components(self, result):
        ax = self._fig.add_subplot(111)
        t = result['t']
        y = result['y']
        fit = result['fit']
        ax.scatter(t, y, s=18, color='#1565C0', label='Data', zorder=3, alpha=0.6)
        ax.plot(t, fit['y_fit'], color='#212121', linewidth=1.8, label='Total fit')
        comps = fit['components']
        colors = ['#E65100', '#2E7D32', '#6A1B9A', '#00838F']
        for i, (comp_curve, comp_p) in enumerate(zip(comps['components'], comps['params'])):
            tau = comp_p['tau']
            ax.plot(t, comp_curve + comps['y_inf'], linestyle='--', linewidth=1.4,
                    color=colors[i % len(colors)],
                    label=f"Component {i + 1} (τ={tau:.3g})")
        ax.axhline(comps['y_inf'], color='#777', linewidth=0.8, linestyle=':',
                   label=f"Offset (y∞={comps['y_inf']:.3g})")
        ax.set_xlabel('Time')
        ax.set_ylabel('Signal')
        ax.legend(fontsize=8)
        ax.set_title('Individual exponential components')

    # -- Global analysis views ---------------------------------------
    def _plot_global_trace(self, result, preview_wavelength):
        ax1 = self._fig.add_subplot(211)
        ax2 = self._fig.add_subplot(212, sharex=ax1)
        t = result['times']
        wl = result['x_wavelengths']
        if preview_wavelength is None:
            preview_wavelength = wl[len(wl) // 2]
        idx = int(np.argmin(np.abs(wl - preview_wavelength)))

        data_col = result['D'][:, idx]
        fit_col = result['D_fit'][:, idx]
        ax1.scatter(t, data_col, s=18, color='#1565C0', label='Data', zorder=3)
        ax1.plot(t, fit_col, color='#E65100', linewidth=1.8, label='Fit')
        ax1.set_ylabel('Signal')
        ax1.legend(fontsize=8)
        ax1.set_title(f'Kinetic trace + fit at X = {wl[idx]:.4g} (global fit)')

        residual = data_col - fit_col
        ax2.axhline(0, color='#999', linewidth=0.8)
        ax2.scatter(t, residual, s=14, color='#C62828')
        ax2.set_xlabel('Time')
        ax2.set_ylabel('Residual')

    def _plot_das(self, result):
        ax = self._fig.add_subplot(111)
        wl = result['x_wavelengths']
        colors = ['#E65100', '#2E7D32', '#6A1B9A', '#00838F']
        for i, (amp_row, k) in enumerate(zip(result['amplitudes'], result['rates'])):
            tau = 1.0 / k if k != 0 else float('inf')
            ax.plot(wl, amp_row, color=colors[i % len(colors)], linewidth=1.6,
                    label=f"Component {i + 1} (τ={tau:.3g})")
        if result.get('offset_spectrum') is not None:
            ax.plot(wl, result['offset_spectrum'], color='#777', linewidth=1.4,
                    linestyle=':', label='Offset (y∞)')
        ax.axhline(0, color='#bbb', linewidth=0.7)
        ax.set_xlabel('X (wavelength)')
        ax.set_ylabel('Amplitude')
        ax.legend(fontsize=8)
        ax.set_title('Decay-Associated Spectra (DAS)')


class KineticsFittingDialog(QDialog):

    def __init__(self, parent=None, controller=None, spectra=None):
        super().__init__(parent)
        self.setWindowTitle('Kinetics Fitting')
        self.setMinimumSize(1080, 720)
        self.resize(1320, 860)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self.controller = controller
        self.spectra = list(spectra or [])
        self._last_result = None
        self._last_mode = None
        self._worker = None
        self._progress = None
        self._original_times = {}

        self._build_ui()
        self._populate_time_table()

    def showEvent(self, event):
        super().showEvent(event)
        # Defensive: clear any override cursor(s) still active once this
        # dialog is actually on screen -- see PLSDialog.showEvent for the
        # full explanation. Same fix, applied from the start this time.
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
        splitter.setSizes([420, 900])
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet(
            'QSplitter::handle { background-color: #cfd8dc; } '
            'QSplitter::handle:hover { background-color: #90a4ae; }'
        )
        root.addWidget(splitter)

    def _build_left(self):
        w = QWidget()
        w.setMinimumWidth(340)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self._build_mode_group())
        layout.addWidget(self._build_table_group(), stretch=1)
        layout.addWidget(self._build_settings_group())

        self.run_btn = QPushButton('▶  Run Fit')
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

    def _build_mode_group(self):
        group = QGroupBox('Mode')
        layout = QHBoxLayout(group)
        self.single_radio = QRadioButton('Single wavelength')
        self.global_radio = QRadioButton('Global analysis')
        self.single_radio.setChecked(True)
        btn_group = QButtonGroup(self)
        btn_group.addButton(self.single_radio)
        btn_group.addButton(self.global_radio)
        self.single_radio.toggled.connect(self._on_mode_changed)
        layout.addWidget(self.single_radio)
        layout.addWidget(self.global_radio)
        return group

    def _build_table_group(self):
        group = QGroupBox('Time values')
        layout = QVBoxLayout(group)

        self._table_hint = QLabel(
            "One time value per spectrum, needed either way (which wavelength you "
            "fit doesn't matter for this). Values are guessed from spectrum names and "
            "are always editable -- double-click a cell, or select a column of values "
            "in a spreadsheet and paste here with Ctrl+V."
        )
        self._table_hint.setWordWrap(True)
        self._table_hint.setStyleSheet('color: #666; font-size: 11px;')
        layout.addWidget(self._table_hint)

        # Display-only "shorten names" toggle — this dialog's own,
        # independent on/off state (see label_shortening.py's
        # make_shorten_names_checkbox), unrelated to the main window's
        # checkbox and always starting unchecked.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _state: self.table.viewport().update())
        layout.addWidget(self.checkBox_shorten_names)

        self.table = QTableWidget(len(self.spectra), 2)
        self.table.setHorizontalHeaderLabels(['Spectrum', 'Time'])
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_SPECTRUM, QHeaderView.Interactive)
        self.table.setColumnWidth(COL_SPECTRUM, 220)
        header.setSectionResizeMode(COL_TIME, QHeaderView.Stretch)
        self.table.setTextElideMode(Qt.ElideLeft)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.table.setItemDelegateForColumn(
            COL_SPECTRUM, make_display_text_delegate(self._display_labels_map, parent=self.table))
        self._install_clipboard_shortcuts()

        layout.addWidget(self.table, 1)

        revert_row = QHBoxLayout()
        revert_row.addStretch()
        revert_btn = QPushButton('Revert to auto-detected times')
        revert_btn.setAutoDefault(False)
        revert_btn.clicked.connect(self._revert_times)
        revert_row.addWidget(revert_btn)
        layout.addLayout(revert_row)

        return group

    def _build_settings_group(self):
        group = QGroupBox('Model settings')
        layout = QVBoxLayout(group)

        wl_row = QHBoxLayout()
        self._wavelength_label = QLabel('Extraction X:')
        wl_row.addWidget(self._wavelength_label)
        self.wavelength_spin = QDoubleSpinBox()
        x_all = self.spectra[0]['x_scale'] if self.spectra else [0.0, 1.0]
        x_min, x_max = float(np.min(x_all)), float(np.max(x_all))
        self.wavelength_spin.setRange(x_min, x_max)
        self.wavelength_spin.setDecimals(4)
        self.wavelength_spin.setValue(self._default_wavelength(x_min, x_max))
        wl_row.addWidget(self.wavelength_spin)
        layout.addLayout(wl_row)

        window_row = QHBoxLayout()
        self._window_label = QLabel('Averaging window (± X, 0 = none):')
        window_row.addWidget(self._window_label)
        self.window_spin = QDoubleSpinBox()
        self.window_spin.setRange(0.0, max((x_max - x_min), 1.0))
        self.window_spin.setDecimals(4)
        self.window_spin.setValue(0.0)
        window_row.addWidget(self.window_spin)
        layout.addLayout(window_row)

        comp_row = QHBoxLayout()
        comp_row.addWidget(QLabel('Number of components:'))
        self.n_components_spin = QSpinBox()
        self.n_components_spin.setRange(1, 4)
        self.n_components_spin.setValue(1)
        comp_row.addWidget(self.n_components_spin)
        layout.addLayout(comp_row)

        return group

    def _default_wavelength(self, x_min, x_max):
        """Default the extraction/preview X to whichever point has the
        largest standard deviation ACROSS the selected spectra -- the
        most informative single point to start with for a kinetic trace,
        since a point where every spectrum has nearly the same value
        carries almost no kinetic information at all."""
        if len(self.spectra) < 2:
            return (x_min + x_max) / 2.0
        try:
            ys = np.array([s['y_scale'] for s in self.spectra], dtype=float)
            x = np.asarray(self.spectra[0]['x_scale'], dtype=float)
            std = np.std(ys, axis=0)
            return float(x[np.argmax(std)])
        except Exception:
            return (x_min + x_max) / 2.0

    def _build_right(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(4, 4, 4, 4)

        view_row = QHBoxLayout()
        view_row.addWidget(QLabel('View:'))
        self.view_combo = QComboBox()
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        view_row.addWidget(self.view_combo)
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
        self._canvas = _KineticsPlotCanvas(plot_widget)
        pl.addWidget(NavigationToolbar(self._canvas, plot_widget))
        pl.addWidget(self._canvas)
        right_splitter.addWidget(plot_widget)

        results_widget = QWidget()
        rl = QVBoxLayout(results_widget)
        rl.setContentsMargins(0, 4, 0, 0)

        self._results_table = QTableWidget(0, 0)
        self._results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._results_table.horizontalHeader().setStretchLastSection(True)
        self._results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._results_table.setAlternatingRowColors(True)
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
        self._rebuild_view_combo()
        return w

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------
    def _on_mode_changed(self):
        is_single = self.single_radio.isChecked()
        self._wavelength_label.setText('Extraction X:' if is_single else 'Preview X (fit already uses every X):')
        self._window_label.setVisible(is_single)
        self.window_spin.setVisible(is_single)
        self._rebuild_view_combo()

    def _rebuild_view_combo(self):
        self.view_combo.blockSignals(True)
        self.view_combo.clear()
        if self.single_radio.isChecked():
            self.view_combo.addItem('Kinetic trace + fit', 'trace')
            self.view_combo.addItem('Individual components', 'components')
        else:
            self.view_combo.addItem('Kinetic trace + fit (one X)', 'trace')
            self.view_combo.addItem('Decay-Associated Spectra (DAS)', 'das')
        self.view_combo.blockSignals(False)
        self._canvas.visualization_mode = self.view_combo.currentData()

    # ------------------------------------------------------------------
    # Shorten names (display-only) — this dialog's own independent
    # checkbox (see _build_table_group), no longer tied to the main
    # window's.
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
    # Time table
    # ------------------------------------------------------------------
    def _guess_time(self, spec, fallback_index):
        """Seed a starting time guess from the LAST number found in the
        spectrum's label (trailing numbers are more often a per-spectrum
        index/time than a leading one that's part of a shared sample
        name), falling back to existing 'time' metadata, then to the
        spectrum's position in the selection order. Always user-editable
        afterwards -- this is only a starting point."""
        label = spec.get('label', '')
        numbers = _NUMBER_RE.findall(label)
        if numbers:
            try:
                return float(numbers[-1])
            except ValueError:
                pass
        existing_time = (spec.get('metadata') or {}).get('time')
        if existing_time is not None:
            try:
                return float(existing_time)
            except (TypeError, ValueError):
                pass
        return float(fallback_index)

    def _populate_time_table(self):
        self.table.setRowCount(len(self.spectra))
        self._original_times = {}
        for row, spec in enumerate(self.spectra):
            full_label = spec.get('label', '?')
            name_item = QTableWidgetItem(full_label)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            name_item.setToolTip(full_label)
            self.table.setItem(row, COL_SPECTRUM, name_item)

            guess = self._guess_time(spec, row)
            self.table.setItem(row, COL_TIME, QTableWidgetItem(f"{guess:g}"))
            self._original_times[spectrum_key(spec)] = guess
        self.table.resizeColumnsToContents()

    def _revert_times(self):
        for row, spec in enumerate(self.spectra):
            key = spectrum_key(spec)
            if key in self._original_times:
                self.table.item(row, COL_TIME).setText(f"{self._original_times[key]:g}")

    def _read_times(self):
        """Return (times, ok) -- times is a list aligned with self.spectra
        (same order), ok is False (with a warning already shown) if any
        row is blank or not parseable as a number -- unlike PLS's
        calibration table, a blank/unknown row has no meaning here, every
        spectrum needs a real time value to be part of the series at
        all."""
        times = []
        for row, spec in enumerate(self.spectra):
            item = self.table.item(row, COL_TIME)
            text = item.text().strip() if item else ''
            if not text:
                QMessageBox.warning(
                    self, 'Missing Time Value',
                    f"Row {row + 1} ({spec.get('label', '?')}) has no time value. "
                    "Every selected spectrum needs one.")
                return None, False
            try:
                times.append(float(text))
            except ValueError:
                QMessageBox.warning(
                    self, 'Invalid Time Value',
                    f"Row {row + 1} ({spec.get('label', '?')}): '{text}' is not a number.")
                return None, False
        return times, True

    def _install_clipboard_shortcuts(self):
        """Copy/Cut/Paste/Delete on the single editable column -- same
        pattern as PLSDialog's calibration table."""
        table = self.table

        def selected_value_items():
            return [it for it in table.selectedItems() if it.column() == COL_TIME]

        def do_copy():
            items = selected_value_items()
            if not items:
                return
            rows = sorted(it.row() for it in items)
            text = "\n".join(table.item(r, COL_TIME).text() if table.item(r, COL_TIME) else "" for r in rows)
            QApplication.clipboard().setText(text)

        def do_delete():
            for it in selected_value_items():
                it.setText("")

        def do_cut():
            do_copy()
            do_delete()

        def do_paste():
            text = QApplication.clipboard().text()
            if not text:
                return
            rows_text = [ln for ln in text.replace('\r', '').split('\n') if ln != '']
            if not rows_text:
                return
            items = selected_value_items()
            if not items:
                return
            if len(rows_text) == 1 and len(items) > 1:
                for it in items:
                    it.setText(rows_text[0])
                return
            start_row = min(it.row() for it in items)
            for i, value in enumerate(rows_text):
                r = start_row + i
                if r >= table.rowCount():
                    break
                cell = table.item(r, COL_TIME)
                if cell is None:
                    cell = QTableWidgetItem("")
                    table.setItem(r, COL_TIME, cell)
                cell.setText(value.split('\t')[0])

        for seq, fn in [(QKeySequence.Copy, do_copy), (QKeySequence.Cut, do_cut),
                         (QKeySequence.Paste, do_paste), (QKeySequence.Delete, do_delete)]:
            sc = QShortcut(seq, table)
            sc.setContext(Qt.WidgetShortcut)
            sc.activated.connect(fn)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def _run_analysis(self):
        times, ok = self._read_times()
        if not ok:
            return

        n_components = self.n_components_spin.value()
        mode = MODE_SINGLE if self.single_radio.isChecked() else MODE_GLOBAL

        self.run_btn.setEnabled(False)
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))

        self._progress = QProgressDialog('Fitting kinetic model…', None, 0, 0, self)
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setWindowTitle('Kinetics Fitting')
        self._progress.setMinimumDuration(0)
        self._progress.setCancelButton(None)
        self._progress.show()

        if mode == MODE_SINGLE:
            x_value = self.wavelength_spin.value()
            window = self.window_spin.value()

            def _fn():
                y_values, out_of_range = self.controller.extract_curve(self.spectra, x_value, window=window)
                t_arr = np.asarray(times, dtype=float)
                order = np.argsort(t_arr)
                t_sorted = t_arr[order]
                y_sorted = y_values[order]
                fit = self.controller.fit_single_wavelength(t_sorted, y_sorted, n_components)
                if fit is None:
                    raise RuntimeError(
                        "The fit did not converge. Try a different number of "
                        "components, or check the time values / extraction X.")
                return {'t': t_sorted, 'y': y_sorted, 'fit': fit,
                        'out_of_range': out_of_range, 'x_value': x_value}
        else:
            def _fn():
                result = self.controller.fit_global(self.spectra, times, n_components)
                if result is None:
                    raise RuntimeError(
                        "The global fit did not converge. Try a different number "
                        "of components, or check the time values.")
                return result

        self._worker = _ComputeWorker(_fn, self)
        self._worker.done.connect(lambda: self._on_computed(mode))
        self._worker.start(QThread.LowPriority)

    def _on_computed(self, mode):
        QApplication.restoreOverrideCursor()
        self.run_btn.setEnabled(True)
        if self._progress is not None:
            self._progress.close()
            self._progress = None

        if self._worker.error is not None:
            QMessageBox.warning(self, 'Could Not Fit Model', str(self._worker.error))
            return

        self._last_result = self._worker.result
        self._last_mode = mode
        self._update_summary()
        preview_x = self.wavelength_spin.value() if mode == MODE_GLOBAL else None
        self._canvas.plot(mode, self._last_result, preview_wavelength=preview_x)
        self._populate_results_table()
        self._copy_btn.setEnabled(True)
        self._csv_btn.setEnabled(True)
        self._pdf_btn.setEnabled(True)

        if mode == MODE_SINGLE:
            oor = self._last_result.get('out_of_range') or []
            if oor:
                QMessageBox.information(
                    self, 'Extraction X Outside Range',
                    f"{len(oor)} of {len(self.spectra)} spectra don't actually cover "
                    f"X = {self._last_result['x_value']:g} — their value was "
                    "extrapolated from the nearest edge point instead of interpolated. "
                    "The fit still ran, but treat it with extra caution.")

    def _update_summary(self):
        r = self._last_result
        n = self.n_components_spin.value()
        q = r['fit']['quality'] if self._last_mode == MODE_SINGLE else r['quality']
        text = (f"{n} component{'s' if n != 1 else ''}"
                f"{' (shared)' if self._last_mode == MODE_GLOBAL else ''}  •  "
                f"R² = {q['r_squared']:.4f}  •  RMSD = {q['rmsd']:.4g}")
        self._summary_label.setText(text)

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------
    def _on_view_changed(self):
        self._canvas.visualization_mode = self.view_combo.currentData()
        preview_x = self.wavelength_spin.value() if self._last_mode == MODE_GLOBAL else None
        self._canvas.plot(self._last_mode, self._last_result, preview_wavelength=preview_x)

    # ------------------------------------------------------------------
    # Results table -- component parameters (compact, always exportable),
    # not a full curve/DAS dump -- same design choice as MeltingCurve /
    # PeakFitting showing component params in a table and full curves via
    # the plot instead.
    # ------------------------------------------------------------------
    def _populate_results_table(self):
        r = self._last_result
        table = self._results_table
        headers = (['Component', 'Rate constant (k)', 'k error', 'Tau (1/k)', 'tau error', 'Amplitude', 'amp. error']
                   if self._last_mode == MODE_SINGLE else
                   ['Component', 'Rate constant (k)', 'k error', 'Tau (1/k)', 'tau error'])
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        def _item(val):
            it = QTableWidgetItem(val)
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return it

        if self._last_mode == MODE_SINGLE:
            comps = r['fit']['components']
            rows = comps['params']
            table.setRowCount(len(rows) + 1)
            for i, p in enumerate(rows):
                table.setItem(i, 0, QTableWidgetItem(f"Component {i + 1}"))
                table.setItem(i, 1, _item(f"{p['rate']:.6g}"))
                table.setItem(i, 2, _item(f"{p.get('rate_err'):.4g}" if p.get('rate_err') is not None else ''))
                table.setItem(i, 3, _item(f"{p['tau']:.6g}"))
                table.setItem(i, 4, _item(f"{p.get('tau_err'):.4g}" if p.get('tau_err') is not None else ''))
                table.setItem(i, 5, _item(f"{p['amplitude']:.6g}"))
                table.setItem(i, 6, _item(f"{p.get('amplitude_err'):.4g}" if p.get('amplitude_err') is not None else ''))
            last = len(rows)
            table.setItem(last, 0, QTableWidgetItem('Offset (y∞)'))
            table.setItem(last, 1, _item(''))
            table.setItem(last, 2, _item(''))
            table.setItem(last, 3, _item(''))
            table.setItem(last, 4, _item(''))
            table.setItem(last, 5, _item(f"{comps['y_inf']:.6g}"))
            err = comps.get('y_inf_err')
            table.setItem(last, 6, _item(f"{err:.4g}" if err is not None else ''))
        else:
            table.setRowCount(len(r['rates']))
            rates_err = r.get('rates_err')
            for i, k in enumerate(r['rates']):
                table.setItem(i, 0, QTableWidgetItem(f"Component {i + 1}"))
                table.setItem(i, 1, _item(f"{k:.6g}"))
                err = rates_err[i] if rates_err is not None else None
                table.setItem(i, 2, _item(f"{err:.4g}" if err is not None else ''))
                table.setItem(i, 3, _item(f"{r['tau'][i]:.6g}"))
                tau_err = (err / k ** 2) if (err is not None and k != 0) else None
                table.setItem(i, 4, _item(f"{tau_err:.4g}" if tau_err is not None else ''))

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
        path, _ = QFileDialog.getSaveFileName(self, 'Export Results', 'kinetics_fit_results.csv',
                                              'CSV files (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(self._table_text(','))
        except Exception as e:
            QMessageBox.warning(self, 'Export Failed', str(e))

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export PDF Report', 'kinetics_fit_report.pdf',
                                              'PDF files (*.pdf)')
        if not path:
            return
        mode_label = 'Single wavelength' if self._last_mode == MODE_SINGLE else 'Global analysis'
        n = self.n_components_spin.value()
        meta = [f'Mode: {mode_label}', f'Number of components: {n}']
        if self._last_mode == MODE_SINGLE:
            meta.append(f'Extraction X: {self.wavelength_spin.value():g}')
            if self.window_spin.value():
                meta.append(f'Averaging window: ±{self.window_spin.value():g}')
        else:
            meta.append(f'Preview X: {self.wavelength_spin.value():g}')
        q = self._last_result['fit']['quality'] if self._last_mode == MODE_SINGLE else self._last_result['quality']
        meta.append(f"R² = {q['r_squared']:.4f}, RMSD = {q['rmsd']:.4g}")

        headers = [self._results_table.horizontalHeaderItem(c).text()
                   for c in range(self._results_table.columnCount())]
        rows = []
        for r in range(self._results_table.rowCount()):
            rows.append([self._results_table.item(r, c).text() if self._results_table.item(r, c) else ''
                        for c in range(self._results_table.columnCount())])
        labels = [s.get('label', '') for s in self.spectra]

        try:
            from src.modules.utils.pdf_report_utils import export_report_pdf
            export_report_pdf(path, f'Kinetics Fitting — {mode_label}', meta_lines=meta,
                              figure=self._canvas._fig, table_headers=headers, table_rows=rows,
                              source_labels=labels)
        except Exception as e:
            QMessageBox.warning(self, 'Export Failed', str(e))

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------
    def _show_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'kinetics_fitting')
