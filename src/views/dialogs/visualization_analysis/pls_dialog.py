# src/views/dialogs/visualization_analysis/pls_dialog.py
"""
PLS regression / PLS-DA dialog.

Layout mirrors ClusterAnalysisDialog's shape (control panel left, single
matplotlib canvas + a mode dropdown on the right, explicit "Run" button
rather than auto-recompute, background QThread so cross-validation
doesn't freeze the UI) with one addition unique to this tool: a
per-spectrum calibration-value table (same Excel-paste/spectrum_key/
Shorten-Names pattern as CDUnitConversionDialog's per-spectrum table,
trimmed to a single editable column) since PLS needs a known y-value per
calibration spectrum, which no other analysis tool in this app requires.

Read-only analysis — no Apply/Add-as-New, no Operations History entry
(see PLSController's docstring for why): nothing here is ever written
back to the spectra list.
"""

import numpy as np
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
from src.modules.visualization_analysis.pls_manager import MODE_REGRESSION, MODE_CLASSIFICATION

logger = get_logger(__name__)

COL_SPECTRUM = 0
COL_VALUE = 1


class _ComputeWorker(QThread):
    """Runs a single callable on a background thread — identical
    pattern to ClusterAnalysisDialog's/nmf_dialog.py's own copy (see
    those for the full rationale: a long blocking sklearn call on the
    GUI thread freezes the whole event loop, including the progress
    dialog's own ability to paint)."""
    done = pyqtSignal()
    progress = pyqtSignal(int, int, str)

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


class _PLSPlotCanvas(FigureCanvas):
    """One matplotlib Figure whose content is switched by
    self.visualization_mode — same single-canvas-plus-dropdown approach
    as ClusterAnalysisCanvas, rather than one canvas per tab."""

    VIEWS = ('cv_curve', 'scores', 'fit', 'coefficients')

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#f0f0f0')
        self.visualization_mode = 'cv_curve'

    def resizeEvent(self, event):
        # Same fix as IsosbesticPointDialog's canvas — see that file's
        # comment for the full explanation (tight_layout computed against
        # a provisional, not-yet-final canvas size on first draw).
        super().resizeEvent(event)
        if self._fig.get_axes():
            try:
                self._fig.tight_layout()
            except Exception:
                pass
            self.draw_idle()

    def plot(self, result):
        self._fig.clear()
        if result is None:
            ax = self._fig.add_subplot(111)
            ax.text(0.5, 0.5, 'Click "Run PLS" to fit a model.',
                     transform=ax.transAxes, ha='center', va='center',
                     color='#1976D2', fontsize=10)
            self.draw_idle()
            return

        mode = result['mode']
        view = self.visualization_mode
        if view == 'cv_curve':
            self._plot_cv_curve(result)
        elif view == 'scores':
            self._plot_scores(result)
        elif view == 'fit':
            self._plot_fit_or_confusion(result)
        elif view == 'coefficients':
            self._plot_coefficients(result)
        self.draw_idle()

    def _plot_cv_curve(self, result):
        ax = self._fig.add_subplot(111)
        comps = result['components_tried']
        scores = result['cv_scores']
        ax.plot(comps, scores, 'o-', color='#1565C0')
        chosen = result['chosen_n_components']
        chosen_idx = comps.index(chosen)
        ax.plot(chosen, scores[chosen_idx], 'o', color='#2E7D32', markersize=12,
                 label=f'Chosen: {chosen} components', zorder=5)
        ax.set_xlabel('Number of components (latent variables)')
        ylabel = 'RMSECV' if result['mode'] == MODE_REGRESSION else 'CV accuracy'
        ax.set_ylabel(ylabel)
        ax.set_title(f"Cross-validation ({result['cv_method']})")
        ax.grid(True, linestyle='--', alpha=0.4)
        ax.legend(fontsize=9)

    def _plot_scores(self, result):
        ax = self._fig.add_subplot(111)
        t = np.array(result['x_scores'])
        cal_idx = set(result['cal_indices'])
        preds = result['predictions']
        cal_positions = [i for i, p in enumerate(preds) if p['is_calibration']]

        if t.shape[1] < 2:
            ax.text(0.5, 0.5, 'Only 1 component — scores plot needs at least 2.',
                     transform=ax.transAxes, ha='center', va='center', color='#1976D2')
            return

        if result['mode'] == MODE_REGRESSION:
            actual = [preds[i]['actual'] for i in cal_positions]
            sc = ax.scatter(t[:, 0], t[:, 1], c=actual, cmap='viridis', s=50, edgecolor='k', linewidth=0.5)
            self._fig.colorbar(sc, ax=ax, label='Calibration value')
        else:
            class_labels = result['class_labels']
            colors = ['#1f77b4', '#d62728', '#2ca02c', '#ff7f0e', '#9467bd', '#8c564b', '#e377c2']
            for j, cls in enumerate(class_labels):
                idx = [k for k, i in enumerate(cal_positions) if preds[i]['actual_class'] == cls]
                ax.scatter(t[idx, 0], t[idx, 1], color=colors[j % len(colors)], s=50,
                           edgecolor='k', linewidth=0.5, label=cls)
            ax.legend(fontsize=9)

        ax.axhline(0, color='#999', lw=0.8)
        ax.axvline(0, color='#999', lw=0.8)
        ax.set_xlabel('Component 1 score')
        ax.set_ylabel('Component 2 score')
        ax.set_title('Calibration set scores')
        ax.grid(True, linestyle='--', alpha=0.3)

    def _plot_fit_or_confusion(self, result):
        ax = self._fig.add_subplot(111)
        if result['mode'] == MODE_REGRESSION:
            preds = [p for p in result['predictions'] if p['is_calibration']]
            actual = [p['actual'] for p in preds]
            predicted = [p['predicted'] for p in preds]
            ax.scatter(actual, predicted, color='#1565C0', s=45, edgecolor='k', linewidth=0.5)
            lims = [min(actual + predicted), max(actual + predicted)]
            pad = 0.05 * (lims[1] - lims[0] if lims[1] > lims[0] else 1)
            lims = [lims[0] - pad, lims[1] + pad]
            ax.plot(lims, lims, '--', color='#999', label='y = x')
            ax.set_xlim(lims); ax.set_ylim(lims)
            ax.set_xlabel('Actual (calibration)')
            ax.set_ylabel('Predicted')
            r2 = result['r2_calibration']
            ax.set_title(f"Actual vs Predicted — R² = {r2:.4f}" if r2 is not None else "Actual vs Predicted")
            ax.legend(fontsize=9)
            ax.grid(True, linestyle='--', alpha=0.3)
        else:
            cm = np.array(result['confusion_matrix'])
            labels = result['class_labels']
            im = ax.imshow(cm, cmap='Blues')
            ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, rotation=45, ha='right')
            ax.set_yticks(range(len(labels))); ax.set_yticklabels(labels)
            ax.set_xlabel('Predicted class')
            ax.set_ylabel('Actual class')
            acc = result['cal_accuracy']
            ax.set_title(f"Confusion matrix — accuracy = {acc:.1%}" if acc is not None else "Confusion matrix")
            vmax = cm.max() if cm.size else 1
            for i in range(cm.shape[0]):
                for j in range(cm.shape[1]):
                    color = 'white' if cm[i, j] > vmax / 2 else 'black'
                    ax.text(j, i, str(cm[i, j]), ha='center', va='center', color=color)
            self._fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    def _plot_coefficients(self, result):
        x = np.array(result['x_scale'])
        coef = np.array(result['coefficients'])
        vip = np.array(result['vip']) if result['vip'] is not None else None

        if vip is not None:
            ax1 = self._fig.add_subplot(211)
            ax2 = self._fig.add_subplot(212, sharex=ax1)
        else:
            ax1 = self._fig.add_subplot(111)
            ax2 = None

        # coef shape is (n_features, n_targets) or (n_targets, n_features)
        # depending on regression vs classification — plot each target's
        # coefficient curve.
        if coef.ndim == 2 and coef.shape[0] == len(x):
            series = coef.T
        elif coef.ndim == 2 and coef.shape[1] == len(x):
            series = coef
        else:
            series = coef.reshape(1, -1)

        labels = result['class_labels'] if result['mode'] == MODE_CLASSIFICATION else [None]
        for i, row in enumerate(series):
            label = labels[i] if labels and labels[i] else 'Coefficient'
            ax1.plot(x, row, lw=1.0, label=label)
        ax1.axhline(0, color='#999', lw=0.8)
        ax1.set_ylabel('Regression coefficient')
        ax1.set_title('Regression coefficients (original x-axis units)')
        ax1.grid(True, linestyle='--', alpha=0.3)
        if len(series) > 1:
            ax1.legend(fontsize=8)

        if ax2 is not None:
            ax2.plot(x, vip, color='#E65100', lw=1.0)
            ax2.axhline(1.0, color='#999', ls='--', lw=0.8, label='VIP = 1 (conventional threshold)')
            ax2.set_xlabel('X')
            ax2.set_ylabel('VIP score')
            ax2.grid(True, linestyle='--', alpha=0.3)
            ax2.legend(fontsize=8)
        else:
            ax1.set_xlabel('X')


class PLSDialog(QDialog):

    def __init__(self, parent=None, controller=None, spectra=None):
        super().__init__(parent)
        self.setWindowTitle('PLS / PLS-DA')
        self.setMinimumSize(1080, 720)
        self.resize(1320, 860)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self.controller = controller
        self.spectra = list(spectra or [])
        self._last_result = None
        self._worker = None
        self._progress = None

        self._build_ui()
        self._populate_table()

    def showEvent(self, event):
        super().showEvent(event)
        # Defensive: clear any override cursor(s) still active once this
        # dialog is actually on screen — e.g. a "please wait" cursor left
        # active by whoever opened this modal dialog (it won't get restored
        # by the caller until the dialog closes, since exec_() blocks). This
        # dialog is interactive as soon as it's shown, so nothing inherited
        # should still be forcing a busy look. Same fix as SVD Analysis and
        # Cluster Analysis dialogs.
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
        splitter.setSizes([400, 920])
        # A pane with setFixedWidth() can't actually be dragged by a
        # splitter — Qt can only ever place the handle at exactly that
        # width or, past some threshold, snap the whole pane to 0 (a
        # binary "there / not there" feel instead of a smooth resize).
        # setChildrenCollapsible(False) removes the snap-to-0 case
        # entirely; _build_left() below uses a minimum, not fixed, width
        # so there's now a real continuous range to drag across.
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet(
            'QSplitter::handle { background-color: #cfd8dc; } '
            'QSplitter::handle:hover { background-color: #90a4ae; }'
        )
        root.addWidget(splitter)

    def _build_left(self):
        w = QWidget()
        w.setMinimumWidth(320)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self._build_mode_group())
        layout.addWidget(self._build_table_group(), stretch=1)
        layout.addWidget(self._build_settings_group())

        self.run_btn = QPushButton('▶  Run PLS')
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
        self.regression_radio = QRadioButton('PLS Regression')
        self.classification_radio = QRadioButton('PLS-DA (Classification)')
        self.regression_radio.setChecked(True)
        btn_group = QButtonGroup(self)
        btn_group.addButton(self.regression_radio)
        btn_group.addButton(self.classification_radio)
        self.regression_radio.toggled.connect(self._on_mode_changed)
        layout.addWidget(self.regression_radio)
        layout.addWidget(self.classification_radio)
        return group

    def _build_table_group(self):
        group = QGroupBox('Calibration values')
        layout = QVBoxLayout(group)

        self._table_hint = QLabel(
            "Enter a known value for every CALIBRATION spectrum (the model is built "
            "from these). Leave a row blank to treat that spectrum as an UNKNOWN — "
            "the fitted model will predict it, but it won't influence the fit. "
            "Paste from a spreadsheet with Ctrl+V. Spectrum names are shortened to "
            "just the part that tells them apart — hover a row to see the full name."
        )
        self._table_hint.setWordWrap(True)
        self._table_hint.setStyleSheet('color: #666; font-size: 11px;')
        layout.addWidget(self._table_hint)

        # Display-only "shorten names" toggle — this dialog's own,
        # independent on/off state (see label_shortening.py's
        # make_shorten_names_checkbox), unrelated to the main window's
        # checkbox and always starting unchecked. Drives BOTH this
        # calibration table's Spectrum column and the results table's
        # (see _build_right) — both read the same _display_labels_map.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)
        layout.addWidget(self.checkBox_shorten_names)

        self.table = QTableWidget(len(self.spectra), 2)
        self.table.setHorizontalHeaderLabels(['Spectrum', 'Calibration value'])
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        # Spectrum column gets a wide, user-resizable default rather than
        # splitting 50/50 with the value column — spectrum names are
        # usually the longer of the two, especially before shortening
        # kicks in for a list too small (<2) or too uniform to shorten.
        header.setSectionResizeMode(COL_SPECTRUM, QHeaderView.Interactive)
        self.table.setColumnWidth(COL_SPECTRUM, 260)
        header.setSectionResizeMode(COL_VALUE, QHeaderView.Stretch)
        # When a name is too long for the column, elide from the LEFT
        # ("...cal_01") instead of the right ("pls_regression_prot...") —
        # for this app's "<file> : <name>" label convention the front is
        # almost always the least useful part to keep, and the tail is
        # what actually tells one row apart from another. Applies
        # regardless of the Shorten Names checkbox, so rows stay
        # identifiable even with it off.
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
        return group

    def _build_settings_group(self):
        group = QGroupBox('Model settings')
        layout = QVBoxLayout(group)

        comp_row = QHBoxLayout()
        self.auto_components_check = QCheckBox('Auto (cross-validated)')
        self.auto_components_check.setChecked(True)
        self.auto_components_check.toggled.connect(
            lambda checked: self.n_components_spin.setEnabled(not checked))
        comp_row.addWidget(self.auto_components_check)
        self.n_components_spin = QSpinBox()
        self.n_components_spin.setRange(1, 30)
        self.n_components_spin.setValue(3)
        self.n_components_spin.setEnabled(False)
        comp_row.addWidget(self.n_components_spin)
        layout.addLayout(comp_row)

        cv_row = QHBoxLayout()
        cv_row.addWidget(QLabel('CV folds (0 = leave-one-out):'))
        self.cv_folds_spin = QSpinBox()
        self.cv_folds_spin.setRange(0, 50)
        self.cv_folds_spin.setValue(0)
        cv_row.addWidget(self.cv_folds_spin)
        layout.addLayout(cv_row)

        self.autoscale_check = QCheckBox('Autoscale X (standardize each wavelength)')
        self.autoscale_check.setChecked(True)
        layout.addWidget(self.autoscale_check)

        return group

    def _build_right(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(4, 4, 4, 4)

        view_row = QHBoxLayout()
        view_row.addWidget(QLabel('View:'))
        self.view_combo = QComboBox()
        self.view_combo.addItem('Cross-validation curve', 'cv_curve')
        self.view_combo.addItem('Scores (component 1 vs 2)', 'scores')
        self.view_combo.addItem('Fit quality', 'fit')
        self.view_combo.addItem('Coefficients & VIP', 'coefficients')
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        view_row.addWidget(self.view_combo)
        view_row.addStretch()
        outer.addLayout(view_row)

        right_splitter = QSplitter(Qt.Vertical)
        # Default Qt handle is a near-invisible 1-pixel hairline on most
        # styles — technically draggable, but nobody can find it to grab.
        # Widen it and give it a visible color (darker on hover) so the
        # drag boundary between the plot and the results table is obvious.
        right_splitter.setHandleWidth(8)
        right_splitter.setChildrenCollapsible(False)
        right_splitter.setStyleSheet(
            'QSplitter::handle { background-color: #cfd8dc; } '
            'QSplitter::handle:hover { background-color: #90a4ae; }'
        )

        plot_widget = QWidget()
        pl = QVBoxLayout(plot_widget)
        pl.setContentsMargins(0, 0, 0, 0)
        self._canvas = _PLSPlotCanvas(plot_widget)
        pl.addWidget(NavigationToolbar(self._canvas, plot_widget))
        pl.addWidget(self._canvas)
        right_splitter.addWidget(plot_widget)

        results_widget = QWidget()
        rl = QVBoxLayout(results_widget)
        rl.setContentsMargins(0, 4, 0, 0)

        self._results_table = QTableWidget(0, 0)
        # Interactive (not Stretch) so the user can actually drag column
        # boundaries to resize them; Stretch mode locks every column to a
        # fixed proportional share and silently ignores resize attempts.
        # The last column still stretches to fill any leftover width, so
        # narrow tables don't leave a dead gap on the right.
        self._results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._results_table.horizontalHeader().setStretchLastSection(True)
        self._results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._results_table.setAlternatingRowColors(True)
        self._results_table.setSortingEnabled(True)
        # Same Shorten Names delegate as the calibration table on the left
        # (_display_labels_map) — this was previously only wired up on
        # self.table, so this results table's Spectrum column ignored the
        # checkbox entirely and always showed the full name.
        self._results_table.setItemDelegateForColumn(
            0, make_display_text_delegate(self._display_labels_map, parent=self._results_table))
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
        return w

    # ------------------------------------------------------------------
    # Shorten names (display-only) — this dialog's own independent
    # checkbox (see _build_table_group), no longer tied to the main
    # window's. Drives both self.table and self._results_table. If a
    # name is still too long for the column, it elides from the left
    # (see _build_table_group's setTextElideMode) so the distinguishing
    # tail stays visible, and the full name is always available as a
    # tooltip (see _populate_table).
    # ------------------------------------------------------------------
    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _on_shorten_names_toggled(self, _state):
        self.table.viewport().update()
        self._results_table.viewport().update()

    def _display_labels_map(self):
        if not self._shorten_names_enabled():
            return {}
        labels = [s.get('label', '') for s in self.spectra]
        if len(labels) < 2:
            return {}
        return compute_distinguishing_labels(labels)

    # ------------------------------------------------------------------
    # Calibration table
    # ------------------------------------------------------------------
    def _populate_table(self):
        self.table.setRowCount(len(self.spectra))
        for row, spec in enumerate(self.spectra):
            full_label = spec.get('label', '?')
            name_item = QTableWidgetItem(full_label)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            # Full label always available on hover, even though the cell
            # itself may be painted shortened (see _display_labels_map)
            # or truncated by column width.
            name_item.setToolTip(full_label)
            self.table.setItem(row, COL_SPECTRUM, name_item)
            self.table.setItem(row, COL_VALUE, QTableWidgetItem(""))

    def _on_mode_changed(self):
        is_regression = self.regression_radio.isChecked()
        header = 'Calibration value' if is_regression else 'Class label'
        self.table.setHorizontalHeaderLabels(['Spectrum', header])

    def _read_calibration(self):
        """Return {spectrum_key: raw_text} for every non-blank row —
        left as strings; PLSManager.compute_pls itself does the
        float()/str() interpretation appropriate to the chosen mode, and
        raises a clear ValueError if a regression value isn't numeric."""
        y_by_key = {}
        for row, spec in enumerate(self.spectra):
            item = self.table.item(row, COL_VALUE)
            text = item.text().strip() if item else ''
            if text:
                y_by_key[spectrum_key(spec)] = text
        return y_by_key

    def _install_clipboard_shortcuts(self):
        """Copy/Cut/Paste/Delete on the single editable column — same
        pattern as CDUnitConversionDialog's per-spectrum table, trimmed
        to one column (no multi-column block-paste ambiguity here)."""
        table = self.table

        def selected_value_items():
            return [it for it in table.selectedItems() if it.column() == COL_VALUE]

        def do_copy():
            items = selected_value_items()
            if not items:
                return
            rows = sorted(it.row() for it in items)
            text = "\n".join(table.item(r, COL_VALUE).text() if table.item(r, COL_VALUE) else "" for r in rows)
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
                # One value onto many selected cells — fill them all.
                for it in items:
                    it.setText(rows_text[0])
                return
            start_row = min(it.row() for it in items)
            for i, value in enumerate(rows_text):
                r = start_row + i
                if r >= table.rowCount():
                    break
                cell = table.item(r, COL_VALUE)
                if cell is None:
                    cell = QTableWidgetItem("")
                    table.setItem(r, COL_VALUE, cell)
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
        y_by_key = self._read_calibration()
        mode = MODE_REGRESSION if self.regression_radio.isChecked() else MODE_CLASSIFICATION
        n_components = None if self.auto_components_check.isChecked() else self.n_components_spin.value()
        cv_folds = None if self.cv_folds_spin.value() == 0 else self.cv_folds_spin.value()
        autoscale_x = self.autoscale_check.isChecked()

        self.run_btn.setEnabled(False)
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))

        self._progress = QProgressDialog('Fitting PLS model…', None, 0, 4, self)
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setWindowTitle('PLS / PLS-DA')
        self._progress.setMinimumDuration(0)
        self._progress.setCancelButton(None)
        self._progress.setValue(0)
        self._progress.show()

        self._worker = _ComputeWorker(None, self)
        self._worker._fn = lambda: self.controller.compute_pls(
            self.spectra, y_by_key, mode, n_components=n_components,
            autoscale_x=autoscale_x, cv_folds=cv_folds,
            progress_callback=self._worker.progress.emit,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_computed)
        self._worker.start(QThread.LowPriority)

    def _on_progress(self, step, total, label):
        if total != self._progress.maximum():
            self._progress.setMaximum(total)
        self._progress.setLabelText(label)
        self._progress.setValue(step)

    def _on_computed(self):
        QApplication.restoreOverrideCursor()
        self.run_btn.setEnabled(True)
        if self._progress is not None:
            self._progress.close()
            self._progress = None

        if self._worker.error is not None:
            QMessageBox.warning(self, 'Could Not Fit Model', str(self._worker.error))
            return

        self._last_result = self._worker.result
        self._update_summary()
        self._canvas.plot(self._last_result)
        self._populate_results_table()
        self._copy_btn.setEnabled(True)
        self._csv_btn.setEnabled(True)
        self._pdf_btn.setEnabled(True)

    def _update_summary(self):
        r = self._last_result
        n = r['chosen_n_components']
        if r['mode'] == MODE_REGRESSION:
            rmsecv = f"{r['rmsecv']:.4g}" if r['rmsecv'] is not None else 'n/a'
            text = (f"{n} components  •  RMSEC = {r['rmsec']:.4g}  •  RMSECV = {rmsecv}  •  "
                    f"R² = {r['r2_calibration']:.4f}")
        else:
            cv_acc = f"{r['cv_accuracy']:.1%}" if r['cv_accuracy'] is not None else 'n/a'
            text = (f"{n} components  •  Calibration accuracy = {r['cal_accuracy']:.1%}  •  "
                    f"CV accuracy = {cv_acc}")
        if r['n_prediction_only']:
            text += f"  •  {r['n_prediction_only']} unknown spectra predicted"
        self._summary_label.setText(text)

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------
    def _on_view_changed(self):
        self._canvas.visualization_mode = self.view_combo.currentData()
        self._canvas.plot(self._last_result)

    # ------------------------------------------------------------------
    # Results table
    # ------------------------------------------------------------------
    def _populate_results_table(self):
        r = self._last_result
        preds = r['predictions']
        table = self._results_table
        table.setSortingEnabled(False)

        if r['mode'] == MODE_REGRESSION:
            headers = ['Spectrum', 'Role', 'Actual', 'Predicted', 'Residual']
        else:
            headers = ['Spectrum', 'Role', 'Actual class', 'Predicted class', 'Correct?'] + \
                       [f'P({c})' for c in r['class_labels']]

        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(preds))

        def _item(val):
            it = QTableWidgetItem(val)
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return it

        for row, p in enumerate(preds):
            role = 'Calibration' if p['is_calibration'] else 'Prediction'
            table.setItem(row, 0, QTableWidgetItem(p['label']))
            table.setItem(row, 1, QTableWidgetItem(role))
            if r['mode'] == MODE_REGRESSION:
                actual = f"{p['actual']:.6g}" if p['actual'] is not None else ''
                table.setItem(row, 2, _item(actual))
                table.setItem(row, 3, _item(f"{p['predicted']:.6g}"))
                residual = f"{p['residual']:.4g}" if p['residual'] is not None else ''
                table.setItem(row, 4, _item(residual))
            else:
                table.setItem(row, 2, QTableWidgetItem(p['actual_class'] or ''))
                table.setItem(row, 3, QTableWidgetItem(p['predicted_class']))
                correct = ('Yes' if p['correct'] else 'No') if p['correct'] is not None else ''
                table.setItem(row, 4, QTableWidgetItem(correct))
                for j, cls in enumerate(r['class_labels']):
                    table.setItem(row, 5 + j, _item(f"{p['class_scores'][cls]:.3f}"))

        table.setSortingEnabled(True)
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
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export results', 'pls_results.csv', 'CSV files (*.csv);;All files (*)'
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(self._table_text(','))
        except OSError as exc:
            QMessageBox.warning(self, 'Export failed', str(exc))

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export PDF Report', 'pls_report.pdf',
                                              'PDF files (*.pdf)')
        if not path:
            return
        r = self._last_result
        mode_label = 'PLS Regression' if r['mode'] == MODE_REGRESSION else 'PLS-DA (classification)'
        n = r['chosen_n_components']
        meta = [f'Number of components: {n}']
        if r['mode'] == MODE_REGRESSION:
            rmsecv = f"{r['rmsecv']:.4g}" if r['rmsecv'] is not None else 'n/a'
            meta.append(f"RMSEC = {r['rmsec']:.4g}, RMSECV = {rmsecv}, R² = {r['r2_calibration']:.4f}")
        else:
            cv_acc = f"{r['cv_accuracy']:.1%}" if r['cv_accuracy'] is not None else 'n/a'
            meta.append(f"Calibration accuracy = {r['cal_accuracy']:.1%}, CV accuracy = {cv_acc}")
        if r['n_prediction_only']:
            meta.append(f"{r['n_prediction_only']} unknown spectra predicted")

        headers = [self._results_table.horizontalHeaderItem(c).text()
                   for c in range(self._results_table.columnCount())]
        rows = []
        for row in range(self._results_table.rowCount()):
            rows.append([self._results_table.item(row, c).text() if self._results_table.item(row, c) else ''
                        for c in range(self._results_table.columnCount())])
        labels = [s.get('label', '') for s in self.spectra]

        try:
            from src.modules.utils.pdf_report_utils import export_report_pdf
            export_report_pdf(path, mode_label, meta_lines=meta, figure=self._canvas._fig,
                              table_headers=headers, table_rows=rows, source_labels=labels)
        except Exception as exc:
            QMessageBox.warning(self, 'Export failed', str(exc))

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------
    def _show_help(self):
        try:
            from src.help.pls_help import get_pls_help_content, get_pls_help_title
            from src.help.help_window import show_help_window
            show_help_window(self, get_pls_help_title(), get_pls_help_content())
        except Exception:
            QMessageBox.information(self, 'Help', 'Help documentation is not available.')
