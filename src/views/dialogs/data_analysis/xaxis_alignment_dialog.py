# src/views/dialogs/data_analysis/xaxis_alignment_dialog.py
"""
X-Axis Alignment dialog — v4.

Left panel (fixed 340 px)
    • Spectra list — sort ▲/▼, Select all, Clear, Show legend
      Selection controls which spectra appear in Original / Aligned plots.
    • Alignment settings (reference, max shift, interpolation)
    • Optional x-range restriction
    • Help | Apply | Add as New | Close

Right panel — single view, no tabs
    Controls row:
        ▶ Run preview  |  ⚠ stale  |  progress
        Signal:  ○ Subplots  ○ Overlay
        ☑ Show spectra   ☑ Show table   ☑ Show shift plot

    Vertical QSplitter (setChildrenCollapsible False):
        TOP    Comparison canvas — Original / Aligned
                 (Subplots: two stacked plots sharing x-axis)
                 (Overlay:  original dashed, aligned solid, same axes)
        BOTTOM Stats bar + horizontal splitter (table | shift chart)
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QComboBox, QPushButton, QDoubleSpinBox, QSpinBox, QLabel, QCheckBox,
    QSizePolicy, QSplitter, QWidget, QListWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QButtonGroup, QRadioButton, QFileDialog, QApplication,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    make_shortened_name_delegate, compute_distinguishing_labels, shorten_spectra_labels,
    make_shorten_names_checkbox,
)

logger = get_logger(__name__)

_COLORS = [
    '#1f77b4', '#d62728', '#2ca02c', '#ff7f0e',
    '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]


# ──────────────────────────────────────────────────────────────────────
# Background worker
# ──────────────────────────────────────────────────────────────────────

class _AlignWorker(QThread):
    finished = pyqtSignal(list)
    error    = pyqtSignal(str)

    def __init__(self, manager, spectra, settings, parent=None):
        super().__init__(parent)
        self._manager  = manager
        self._spectra  = spectra
        self._settings = settings

    def run(self):
        try:
            self.finished.emit(self._manager.align_spectra(self._spectra, self._settings))
        except Exception as exc:
            self.error.emit(str(exc))


# ──────────────────────────────────────────────────────────────────────
# Main dialog
# ──────────────────────────────────────────────────────────────────────

class XAxisAlignmentDialog(QDialog):

    def __init__(self, parent=None, current_settings=None,
                 controller=None, selected_spectra=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle('X-Axis Alignment')
        self.setMinimumSize(1000, 620)
        self.resize(1300, 800)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        self.controller       = controller
        self.selected_spectra = list(selected_spectra or [])
        self._settings        = dict(current_settings or {})
        # Bound method (OperationsController.commit_xaxis_alignment) passed
        # in by whatever opened this dialog, so Apply / Add as New can
        # commit the result directly, without a separate Run step.
        self.commit_callback  = commit_callback
        # Pre-load cache before _build_ui so _on_settings_changed during
        # _populate_from_settings sees the stored hash and does not wipe the cache.
        self._aligned_spectra       = list(self._settings.get('_cached_aligned', []))
        self._preview_settings_hash = self._settings.get('_cached_hash', None)
        self._worker                = None

        self.sort_ascending           = True
        self._initialization_complete = False

        self._build_ui()
        self._populate_spectrum_list()
        self._populate_from_settings(self._settings)
        self._initialization_complete = True
        self._select_all()
        self._restore_cached_preview()

    # ──────────────────────────────────────────────────────────────────
    # Top-level layout
    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 960])
        root.addWidget(splitter)

    # ──────────────────────────────────────────────────────────────────
    # Left panel
    # ──────────────────────────────────────────────────────────────────

    def _build_left_panel(self):
        widget = QWidget()
        widget.setFixedWidth(340)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(self._build_spectra_group())
        layout.addWidget(self._build_settings_group())
        layout.addWidget(self._build_range_group())
        layout.addWidget(self._build_shift_plot_options_group())
        layout.addStretch()

        btn_row = QHBoxLayout()
        help_btn = QPushButton('Help')
        help_btn.setAutoDefault(False)
        help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(help_btn)

        btn_row.addStretch()

        # Apply / Add as New / Close commit directly via commit_callback —
        # there's no separate Run step in the main window for this
        # operation anymore (see OperationsController.commit_xaxis_alignment).
        self.apply_button = QPushButton('Apply')
        self.apply_button.setToolTip(
            'Replace the selected spectra with their aligned result.'
        )
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        btn_row.addWidget(self.apply_button)

        self.add_as_new_button = QPushButton('Add as New')
        self.add_as_new_button.setToolTip(
            'Keep the original spectra unchanged and add the aligned results '
            'to the list under new names.'
        )
        self.add_as_new_button.setAutoDefault(False)
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        btn_row.addWidget(self.add_as_new_button)

        self.close_button = QPushButton('Close')
        self.close_button.setAutoDefault(False)
        self.close_button.clicked.connect(self.reject)
        btn_row.addWidget(self.close_button)
        layout.addLayout(btn_row)
        return widget

    def _build_spectra_group(self):
        group = QGroupBox('Selected spectra')
        layout = QVBoxLayout(group)

        info = QLabel(
            '💡 Selection controls which spectra appear in the preview plots. '
            'Alignment is applied to all spectra loaded in the dialog.'
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
        # matching throughout this dialog reads, e.g. _visible_spectra)
        # is untouched by this paint-only delegate.
        self.spectra_list.setItemDelegate(
            make_shortened_name_delegate(self.spectra_list, self._shorten_names_enabled)
        )
        self.spectra_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.spectra_list)

        btn_row = QHBoxLayout()
        for label, slot in [('Select all', self._select_all), ('Clear', self._unselect_all)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        self.show_legend_cb = QCheckBox('Show legend')
        self.show_legend_cb.setChecked(False)
        self.show_legend_cb.stateChanged.connect(self._on_legend_changed)
        btn_row.addWidget(self.show_legend_cb)

        # This dialog's OWN, independent Shorten Names toggle — not tied to
        # the main window's shared checkbox of the same name (see
        # make_shorten_names_checkbox docstring). Off by default. Built
        # here (before _build_settings_group() runs) so it already exists
        # when that method's own _populate_reference_combo() call reads it.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)
        btn_row.addWidget(self.checkBox_shorten_names)

        layout.addLayout(btn_row)
        return group

    def _build_settings_group(self):
        group = QGroupBox('Alignment settings')
        form = QFormLayout(group)

        self.reference_combo = QComboBox()
        self._populate_reference_combo()
        self.reference_combo.currentIndexChanged.connect(self._on_settings_changed)
        form.addRow('Reference:', self.reference_combo)

        # The Reference dropdown is kept in sync with THIS dialog's own
        # Shorten Names checkbox via _on_shorten_names_toggled (connected
        # where that checkbox is built, in _build_spectra_group). A plain
        # paint-only delegate (make_shortened_name_delegate, used for the
        # spectra list above) doesn't fully work for a QComboBox: Qt only
        # routes an item delegate through the DROPDOWN list, never through
        # the closed box's own text — the part actually visible day to
        # day — so the item text itself has to be rebuilt instead. Safe to
        # do here (unlike the spectra list) because selection is read
        # purely via reference_combo.currentIndex() into
        # self.selected_spectra everywhere in this file, never by matching
        # displayed text.

        ref_note = QLabel(
            'The reference spectrum is returned unchanged.\n'
            'All other spectra are shifted to best match it.'
        )
        ref_note.setWordWrap(True)
        ref_note.setStyleSheet('color: grey; font-size: 10px;')
        form.addRow(ref_note)

        self.max_shift_spin = QDoubleSpinBox()
        self.max_shift_spin.setRange(0.01, 1000.0)
        self.max_shift_spin.setDecimals(2)
        self.max_shift_spin.setSingleStep(1.0)
        self.max_shift_spin.setValue(10.0)
        self.max_shift_spin.setToolTip(
            'Maximum shift searched in both directions.\n'
            'Set slightly larger than the largest expected drift.'
        )
        self.max_shift_spin.valueChanged.connect(self._on_settings_changed)
        form.addRow('Max shift (x-units):', self.max_shift_spin)

        self.interp_combo = QComboBox()
        self.interp_combo.addItems(['cubic', 'linear', 'quadratic'])
        self.interp_combo.setToolTip('"cubic" is smooth and most accurate for Raman spectra.')
        self.interp_combo.currentIndexChanged.connect(self._on_settings_changed)
        form.addRow('Interpolation:', self.interp_combo)
        return group

    def _build_range_group(self):
        self.range_group = QGroupBox('Restrict alignment to x-range (optional)')
        self.range_group.setCheckable(True)
        self.range_group.setChecked(False)
        self.range_group.toggled.connect(self._on_settings_changed)
        form = QFormLayout(self.range_group)

        x_min_def, x_max_def = self._data_range()

        self.x_min_spin = QDoubleSpinBox()
        self.x_min_spin.setRange(-1e6, 1e6)
        self.x_min_spin.setDecimals(1)
        self.x_min_spin.setValue(x_min_def if x_min_def is not None else 0.0)
        self.x_min_spin.valueChanged.connect(self._on_settings_changed)
        form.addRow('X min:', self.x_min_spin)

        self.x_max_spin = QDoubleSpinBox()
        self.x_max_spin.setRange(-1e6, 1e6)
        self.x_max_spin.setDecimals(1)
        self.x_max_spin.setValue(x_max_def if x_max_def is not None else 1000.0)
        self.x_max_spin.valueChanged.connect(self._on_settings_changed)
        form.addRow('X max:', self.x_max_spin)

        note = QLabel(
            'Restrict RMSD to this x-range.\n'
            'Useful when a clean, feature-rich spectral window is known.'
        )
        note.setWordWrap(True)
        note.setStyleSheet('color: grey; font-size: 10px;')
        form.addRow(note)
        return self.range_group

    def _build_shift_plot_options_group(self):
        """Label display options for the Shift plot tab — same widget set
        and convention as NMF/MCR-ALS's Concentrations display group and
        Cluster Analysis's dendrogram truncation controls. Only shown
        while the Shift plot tab is the active result tab (see
        _on_result_tab_changed)."""
        self._shift_plot_grp = group = QGroupBox('Shift plot display')
        layout = QVBoxLayout(group)

        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel('Label rotation:'))
        self._shift_rotation_combo = QComboBox()
        self._shift_rotation_combo.addItems(['90°', '45°', '0°'])
        self._shift_rotation_combo.setCurrentText('45°')
        self._shift_rotation_combo.setFixedWidth(60)
        self._shift_rotation_combo.currentTextChanged.connect(self._refresh_shift_plot)
        rot_row.addWidget(self._shift_rotation_combo)
        rot_row.addStretch()
        layout.addLayout(rot_row)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel('Label font size:'))
        self._shift_fontsize_combo = QComboBox()
        self._shift_fontsize_combo.addItems(['Auto', '3', '5', '7', '9', '11', '14'])
        self._shift_fontsize_combo.setCurrentText('Auto')
        self._shift_fontsize_combo.setFixedWidth(70)
        self._shift_fontsize_combo.setToolTip(
            'Auto shrinks labels as the number of spectra grows, so they\n'
            'stay legible without the plot becoming unreasonably wide.\n'
            'Choose an explicit size to override that.'
        )
        self._shift_fontsize_combo.currentTextChanged.connect(self._refresh_shift_plot)
        font_row.addWidget(self._shift_fontsize_combo)
        font_row.addStretch()
        layout.addLayout(font_row)

        trunc_row = QHBoxLayout()
        trunc_row.setContentsMargins(0, 0, 0, 0)
        trunc_row.setSpacing(4)
        self._shift_trunc_combo = QComboBox()
        self._shift_trunc_combo.addItems(['Full label', 'First N chars', 'Last N chars'])
        self._shift_trunc_combo.setCurrentText('Last N chars')
        self._shift_trunc_combo.setToolTip('How to display labels when they are too long')
        self._shift_trunc_combo.setFixedWidth(110)
        trunc_row.addWidget(self._shift_trunc_combo)
        n_label = QLabel('N:')
        n_label.setFixedWidth(20)
        trunc_row.addWidget(n_label)
        self._shift_trunc_n_spin = QSpinBox()
        self._shift_trunc_n_spin.setMinimum(1)
        self._shift_trunc_n_spin.setMaximum(200)
        self._shift_trunc_n_spin.setValue(18)
        self._shift_trunc_n_spin.setFixedWidth(55)
        self._shift_trunc_n_spin.setToolTip('Number of characters (N) to keep from each label')
        self._shift_trunc_n_spin.setKeyboardTracking(False)
        trunc_row.addWidget(self._shift_trunc_n_spin)
        trunc_row.addStretch()
        layout.addLayout(trunc_row)

        def _on_shift_trunc_changed():
            is_n_mode = self._shift_trunc_combo.currentText() != 'Full label'
            self._shift_trunc_n_spin.setEnabled(is_n_mode and not self._shift_use_index_cb.isChecked())
            self._refresh_shift_plot()

        self._shift_trunc_combo.currentTextChanged.connect(_on_shift_trunc_changed)
        self._shift_trunc_n_spin.valueChanged.connect(self._refresh_shift_plot)

        self._shift_use_index_cb = QCheckBox('Use spectrum index (1, 2, 3, ...) instead of labels')
        self._shift_use_index_cb.setChecked(False)
        self._shift_use_index_cb.setToolTip(
            'Show plain position numbers (1, 2, 3, ...) on the axis instead\n'
            'of spectrum labels — handy when labels are long or not\n'
            'meaningful for this view. Truncation above is disabled while\n'
            'this is checked, since there’s nothing left to truncate.'
        )

        def _on_shift_use_index_changed():
            use_index = self._shift_use_index_cb.isChecked()
            self._shift_trunc_combo.setEnabled(not use_index)
            is_n_mode = self._shift_trunc_combo.currentText() != 'Full label'
            self._shift_trunc_n_spin.setEnabled(not use_index and is_n_mode)
            self._refresh_shift_plot()

        self._shift_use_index_cb.stateChanged.connect(_on_shift_use_index_changed)
        layout.addWidget(self._shift_use_index_cb)

        group.setVisible(False)   # only relevant while the Shift plot tab is active
        return group

    # ──────────────────────────────────────────────────────────────────
    # Right panel
    # ──────────────────────────────────────────────────────────────────

    def _build_right_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        layout.addLayout(self._build_controls_row())

        # Tab widget: Spectra | Shift table | Shift plot
        from PyQt5.QtWidgets import QTabWidget
        self._tab_widget = QTabWidget()
        self._tab_widget.tabBar().setElideMode(Qt.ElideNone)
        self._tab_widget.setStyleSheet(
            "QTabBar::tab { min-width: 90px; padding: 4px 12px; }"
        )
        self._tab_widget.currentChanged.connect(self._on_result_tab_changed)

        # ── Tab 1: comparison canvas ──────────────────────────────────
        self._plot_panel = QWidget()
        pl = QVBoxLayout(self._plot_panel)
        pl.setContentsMargins(0, 0, 0, 0)
        self._align_canvas = _ComparisonCanvas(self._plot_panel)
        pl.addWidget(NavigationToolbar(self._align_canvas, self._plot_panel))
        pl.addWidget(self._align_canvas)
        self._tab_widget.addTab(self._plot_panel, 'Spectra')
        # Shift table and Shift plot tabs are added only after Run preview

        # ── Tab 2: shift table ────────────────────────────────────────
        self._table_widget = QWidget()
        tl = QVBoxLayout(self._table_widget)
        tl.setContentsMargins(4, 4, 4, 4)

        self._stats_label = QLabel('')
        self._stats_label.setStyleSheet(
            'background-color: #E8F5E9; padding: 6px; border-radius: 4px; '
            'font-family: monospace;'
        )
        self._stats_label.setWordWrap(True)
        tl.addWidget(self._stats_label)

        self._shift_table = QTableWidget(0, 4)
        self._shift_table.setHorizontalHeaderLabels(
            ['Spectrum', 'Shift (x-units)', 'Direction', 'Role']
        )
        self._shift_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3):
            self._shift_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeToContents
            )
        self._shift_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._shift_table.setAlternatingRowColors(True)
        self._shift_table.setSortingEnabled(True)
        tl.addWidget(self._shift_table)

        export_row = QHBoxLayout()
        export_row.addStretch()
        copy_btn = QPushButton('⧉  Copy to clipboard')
        copy_btn.setToolTip('Copy table as tab-separated text (paste into Excel, Calc, …)')
        copy_btn.clicked.connect(self._copy_table_to_clipboard)
        export_row.addWidget(copy_btn)
        export_csv_btn = QPushButton('💾  Export CSV…')
        export_csv_btn.setToolTip('Save the shift table as a CSV file')
        export_csv_btn.clicked.connect(self._export_table_csv)
        export_row.addWidget(export_csv_btn)
        tl.addLayout(export_row)

        # ── Tab 3: shift plot ─────────────────────────────────────────
        self._chart_widget = QWidget()
        cl = QVBoxLayout(self._chart_widget)
        cl.setContentsMargins(0, 0, 0, 0)
        self._shift_canvas = _ShiftPlotCanvas(self._chart_widget)
        cl.addWidget(NavigationToolbar(self._shift_canvas, self._chart_widget))
        cl.addWidget(self._shift_canvas)

        layout.addWidget(self._tab_widget)
        return widget


    def _build_controls_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        # Run preview
        self.run_preview_btn = QPushButton('▶  Run preview')
        self.run_preview_btn.setToolTip(
            'Compute alignment with the current settings.\n'
            'Does NOT apply — use OK for that.'
        )
        self.run_preview_btn.setStyleSheet(
            'QPushButton { background-color: #1976D2; color: white; '
            'font-weight: bold; padding: 5px 16px; border-radius: 4px; }'
            'QPushButton:hover { background-color: #1565C0; }'
            'QPushButton:disabled { background-color: #90A4AE; }'
        )
        self.run_preview_btn.clicked.connect(self._run_preview)
        row.addWidget(self.run_preview_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setMaximumWidth(140)
        row.addWidget(self._progress)

        self._stale_label = QLabel('⚠  Settings changed — re-run preview')
        self._stale_label.setStyleSheet('color: #E65100; font-style: italic;')
        self._stale_label.setVisible(False)
        row.addWidget(self._stale_label)

        sep = QLabel('|')
        sep.setStyleSheet('color: #ccc;')
        row.addWidget(sep)

        # View mode
        row.addWidget(QLabel('View:'))
        self._view_mode = QButtonGroup(self)
        for i, lbl in enumerate(['Subplots', 'Overlay']):
            rb = QRadioButton(lbl)
            rb.setChecked(i == 0)
            self._view_mode.addButton(rb, i)
            row.addWidget(rb)
        self._view_mode.buttonClicked.connect(self._on_view_mode_changed)

        row.addStretch()
        return row

    def _on_view_mode_changed(self, _=None):
        """Redraw comparison canvas with new mode if results are available."""
        if self._aligned_spectra and self._initialization_complete:
            self._redraw_comparison()

    # ──────────────────────────────────────────────────────────────────
    # Spectra-list helpers
    # ──────────────────────────────────────────────────────────────────

    def _populate_spectrum_list(self):
        self.spectra_list.blockSignals(True)
        self.spectra_list.clear()
        spectra = list(self.selected_spectra)
        if not self.sort_ascending:
            spectra = list(reversed(spectra))
        for s in spectra:
            self.spectra_list.addItem(s['label'])
        self.spectra_list.blockSignals(False)

    def _toggle_sort(self):
        self.sort_ascending = not self.sort_ascending
        self.sort_button.setText('▲' if self.sort_ascending else '▼')
        sel = {item.text() for item in self.spectra_list.selectedItems()}
        self._populate_spectrum_list()
        for i in range(self.spectra_list.count()):
            if self.spectra_list.item(i).text() in sel:
                self.spectra_list.item(i).setSelected(True)

    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _on_shorten_names_toggled(self, _state=None):
        """Refresh everything this dialog's own Shorten Names checkbox
        affects: the spectra list's paint-only delegate, the Reference
        combo's item text (rebuilt directly rather than painted — see the
        comment in _build_settings_group for why), and the Shift plot's
        x-axis tick labels."""
        self.spectra_list.viewport().update()
        self._populate_reference_combo()
        if hasattr(self, '_shift_trunc_combo'):
            self._refresh_shift_plot()

    def _populate_reference_combo(self, *_):
        """(Re)build the Reference dropdown's item text, honoring Shorten
        Names — see the comment where this is connected to the main
        window's checkbox in _build_settings_group for why item text is
        rebuilt directly instead of using a paint-only delegate.
        Preserves the current selection and never itself triggers
        _on_settings_changed (the combo's own currentIndexChanged handler
        stays connected for genuine reference changes only)."""
        display_map = shorten_spectra_labels(self.selected_spectra, self._shorten_names_enabled())
        prev_idx = self.reference_combo.currentIndex()
        self.reference_combo.blockSignals(True)
        self.reference_combo.clear()
        for s in self.selected_spectra:
            self.reference_combo.addItem(display_map.get(s['label'], s['label']))
        if 0 <= prev_idx < self.reference_combo.count():
            self.reference_combo.setCurrentIndex(prev_idx)
        self.reference_combo.blockSignals(False)

    def _on_result_tab_changed(self, idx):
        """Show the Shift plot display options only while that tab is
        actually the active one — same convention as NMF/MCR-ALS's
        _on_tab_changed for their left-panel display-options groups."""
        tab_text = self._tab_widget.tabText(idx)
        if hasattr(self, '_shift_plot_grp'):
            self._shift_plot_grp.setVisible(tab_text == 'Shift plot')

    # ──────────────────────────────────────────────────────────────────
    # Shift plot label display
    # ──────────────────────────────────────────────────────────────────

    def _shift_plot_entries(self):
        """(1-based position in self._aligned_spectra, label) for every
        non-reference spectrum, in the same order _ShiftPlotCanvas plots
        them — used to compute display labels before handing them to the
        canvas."""
        return [
            (i + 1, s['label'])
            for i, s in enumerate(self._aligned_spectra)
            if not s.get('xaxis_alignment_info', {}).get('is_reference', False)
        ]

    def _get_shift_plot_labels(self):
        """Shared label-formatting logic for the shift plot's x-axis:
        honors the main window's Shorten Names checkbox first, then
        optional First/Last-N-chars truncation on top — same convention
        as NMF/MCR-ALS's _get_display_labels. 'Use spectrum index' shows
        plain 1-based positions instead (matching the spectrum's row
        position, reference included, so numbering stays consistent with
        the Shift table)."""
        entries = self._shift_plot_entries()
        if not entries:
            return []
        if self._shift_use_index_cb.isChecked():
            return [str(pos) for pos, _ in entries]
        labels = [lbl for _, lbl in entries]
        if self._shorten_names_enabled():
            # Shorten against the FULL spectrum set (reference included),
            # not just the filtered non-reference subset above — the
            # distinguishing-substring computation depends on what else is
            # in the set, so shortening only the subset actually shown here
            # could pick different (and inconsistent) short names than the
            # main spectra list or any other view uses for the same
            # spectra. Same reasoning as NMF/MCR-ALS's _get_display_labels.
            all_labels = [s['label'] for s in self._aligned_spectra]
            short_map = compute_distinguishing_labels(all_labels)
            labels = [short_map.get(lbl, lbl) for lbl in labels]
        mode = self._shift_trunc_combo.currentText()
        n = self._shift_trunc_n_spin.value()
        if mode == 'First N chars':
            return [lbl[:n] for lbl in labels]
        elif mode == 'Last N chars':
            return [lbl[-n:] for lbl in labels]
        return labels

    def _refresh_shift_plot(self, *_):
        if not self._aligned_spectra:
            return
        labels = self._get_shift_plot_labels()
        rotation = int(self._shift_rotation_combo.currentText().replace('°', ''))
        fontsize_text = self._shift_fontsize_combo.currentText()
        if fontsize_text == 'Auto':
            n = len(labels) if labels else len(self._aligned_spectra)
            fontsize = 7 if n <= 40 else (5 if n <= 80 else 4)
        else:
            fontsize = int(fontsize_text)
        self._shift_canvas.plot_shifts(
            self._aligned_spectra, labels=labels, rotation=rotation, fontsize=fontsize)

    def _select_all(self):
        self.spectra_list.blockSignals(True)
        for i in range(self.spectra_list.count()):
            self.spectra_list.item(i).setSelected(True)
        self.spectra_list.blockSignals(False)
        if self._initialization_complete:
            self._on_selection_changed()

    def _unselect_all(self):
        self.spectra_list.blockSignals(True)
        for i in range(self.spectra_list.count()):
            self.spectra_list.item(i).setSelected(False)
        self.spectra_list.blockSignals(False)
        if self._initialization_complete:
            self._on_selection_changed()

    def _visible_spectra(self) -> list:
        """Return selected_spectra filtered to the current list selection."""
        sel = {item.text() for item in self.spectra_list.selectedItems()}
        visible = [s for s in self.selected_spectra if s['label'] in sel]
        return visible if visible else list(self.selected_spectra)

    def _on_selection_changed(self):
        if not self._initialization_complete:
            return
        if self._aligned_spectra:
            self._redraw_comparison()
        else:
            # No preview run yet — draw only the originals
            self._align_canvas.plot_originals_only(
                self._visible_spectra(),
                ref_label=self._current_ref_label(),
                legend_visible=self.show_legend_cb.isChecked(),
                overlay=(self._view_mode.checkedId() == 1),
            )

    def _on_legend_changed(self, state):
        if not self._initialization_complete:
            return
        if self._aligned_spectra:
            self._redraw_comparison()
        else:
            self._align_canvas.plot_originals_only(
                self._visible_spectra(),
                ref_label=self._current_ref_label(),
                legend_visible=(state == Qt.Checked),
                overlay=(self._view_mode.checkedId() == 1),
            )

    def _on_settings_changed(self, *_):
        if not self._initialization_complete:
            return
        current_hash = self._compute_settings_hash()
        if current_hash != self._preview_settings_hash:
            # Computation parameters changed — invalidate cached results
            self._aligned_spectra = []
            self._preview_settings_hash = None
            self._stale_label.setVisible(True)
            for widget in (self._table_widget, self._chart_widget):
                idx = self._tab_widget.indexOf(widget)
                if idx != -1:
                    self._tab_widget.removeTab(idx)
            # Show originals only (no cached results)
            self._align_canvas.plot_originals_only(
                self._visible_spectra(),
                ref_label=self._current_ref_label(),
                legend_visible=self.show_legend_cb.isChecked(),
                overlay=(self._view_mode.checkedId() == 1),
            )
        # If hash matches, cache is still valid — don't touch it

    def _compute_settings_hash(self) -> str:
        """Return a string that changes whenever computation parameters change."""
        s = self.get_settings()
        return (f"{s['reference_spectrum_index']}|{s['max_shift']:.4f}|"
                f"{s['interpolation_method']}|{s['x_range']}")

    def _redraw_comparison(self):
        """Redraw the comparison canvas from cached aligned results."""
        sel = {item.text() for item in self.spectra_list.selectedItems()}
        # Filter originals and aligned to the current selection
        visible_orig = [s for s in self.selected_spectra if s['label'] in sel] \
                       or list(self.selected_spectra)
        label_set    = {s['label'] for s in visible_orig}
        visible_aln  = [s for s in self._aligned_spectra if s['label'] in label_set]
        self._align_canvas.plot_comparison(
            visible_orig, visible_aln,
            ref_label=self._current_ref_label(),
            legend_visible=self.show_legend_cb.isChecked(),
            overlay=(self._view_mode.checkedId() == 1),
        )

    # ──────────────────────────────────────────────────────────────────
    # Populate from saved settings
    # ──────────────────────────────────────────────────────────────────

    def _populate_from_settings(self, settings):
        ref_idx = int(settings.get('reference_spectrum_index', 0))
        ref_idx = max(0, min(ref_idx, self.reference_combo.count() - 1))
        self.reference_combo.setCurrentIndex(ref_idx)
        self.max_shift_spin.setValue(float(settings.get('max_shift', 10.0)))
        method = settings.get('interpolation_method', 'cubic')
        idx = self.interp_combo.findText(method)
        if idx >= 0:
            self.interp_combo.setCurrentIndex(idx)
        x_range = settings.get('x_range')
        if x_range is not None:
            self.range_group.setChecked(True)
            self.x_min_spin.setValue(float(x_range[0]))
            self.x_max_spin.setValue(float(x_range[1]))


    # ──────────────────────────────────────────────────────────────────
    # Alignment preview
    # ──────────────────────────────────────────────────────────────────

    def _restore_cached_preview(self):
        """Re-populate canvases and tabs from pre-loaded cached results."""
        # _aligned_spectra and _preview_settings_hash were pre-loaded in __init__
        # from self._settings before UI was built; _on_settings_changed during
        # _populate_from_settings already verified the hash was still valid.
        if not self._aligned_spectra or not self._preview_settings_hash:
            return
        # Add result tabs
        if self._tab_widget.indexOf(self._table_widget) == -1:
            self._tab_widget.addTab(self._table_widget, 'Shift table')
        if self._tab_widget.indexOf(self._chart_widget) == -1:
            self._tab_widget.addTab(self._chart_widget, 'Shift plot')
        # Redraw everything
        self._redraw_comparison()
        self._populate_shift_table(self._aligned_spectra, self._current_ref_label())
        self._refresh_shift_plot()

    def _run_preview(self):
        from src.modules.data_analysis.xaxis_alignment_manager import XAxisAlignmentManager
        if len(self.selected_spectra) < 2:
            return
        self.run_preview_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._stale_label.setVisible(False)
        self._worker = _AlignWorker(
            XAxisAlignmentManager(), self.selected_spectra, self.get_settings(), self
        )
        self._worker.finished.connect(self._on_preview_done)
        self._worker.error.connect(self._on_preview_error)
        self._worker.start()

    def _on_preview_done(self, aligned):
        self._progress.setVisible(False)
        self.run_preview_btn.setEnabled(True)
        self._aligned_spectra = aligned
        self._preview_settings_hash = self._compute_settings_hash()
        self._stale_label.setVisible(False)

        # Add result tabs if not already present
        if self._tab_widget.indexOf(self._table_widget) == -1:
            self._tab_widget.addTab(self._table_widget, 'Shift table')
        if self._tab_widget.indexOf(self._chart_widget) == -1:
            self._tab_widget.addTab(self._chart_widget, 'Shift plot')

        self._redraw_comparison()
        self._populate_shift_table(aligned, self._current_ref_label())
        self._refresh_shift_plot()
        # Switch to Spectra tab so comparison is immediately visible
        idx = self._tab_widget.indexOf(self._plot_panel)
        if idx != -1:
            self._tab_widget.setCurrentIndex(idx)

    def _on_preview_error(self, msg):
        self._progress.setVisible(False)
        self.run_preview_btn.setEnabled(True)
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(self, 'Preview error', f'Alignment failed:\n{msg}')

    def _populate_shift_table(self, aligned, ref_label):
        self._shift_table.setSortingEnabled(False)
        self._shift_table.setRowCount(0)
        non_ref_shifts = []
        max_shift_allowed = self.max_shift_spin.value()
        bound_tol = max_shift_allowed * 0.99   # treat as bound-hit if within 1 %
        n_bound_hits = 0
        bound_bg = QColor('#FFF3E0')   # light orange background for bound rows

        for row_idx, s in enumerate(aligned):
            info   = s.get('xaxis_alignment_info', {})
            shift  = info.get('shift', 0.0)
            is_ref = info.get('is_reference', False)
            at_bound = (not is_ref) and (abs(shift) >= bound_tol)
            if at_bound:
                n_bound_hits += 1
            self._shift_table.insertRow(row_idx)

            name_item = QTableWidgetItem(s['label'])
            if at_bound:
                name_item.setBackground(bound_bg)
            self._shift_table.setItem(row_idx, 0, name_item)

            shift_text = f'{shift:+.5f}' if not is_ref else '0  (ref)'
            if at_bound:
                shift_text += '  ⚠'
            shift_item = QTableWidgetItem(shift_text)
            shift_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if at_bound:
                shift_item.setForeground(QColor('#E65100'))
                shift_item.setBackground(bound_bg)
                shift_item.setToolTip(
                    f'Shift reached the Max shift bound ({max_shift_allowed:.2f}).\n'
                    'The true shift may be larger. Increase Max shift and re-run.'
                )
            elif not is_ref:
                shift_item.setForeground(
                    QColor('#1565C0') if shift > 1e-6 else
                    QColor('#B71C1C') if shift < -1e-6 else
                    QColor('#000000')
                )
            self._shift_table.setItem(row_idx, 1, shift_item)

            dir_text = ('—' if is_ref else '→ right' if shift > 1e-6 else
                        '← left' if shift < -1e-6 else '≈ none')
            dir_item = QTableWidgetItem(dir_text)
            dir_item.setTextAlignment(Qt.AlignCenter)
            if at_bound:
                dir_item.setBackground(bound_bg)
            self._shift_table.setItem(row_idx, 2, dir_item)

            role_item = QTableWidgetItem('reference' if is_ref else 'aligned')
            role_item.setTextAlignment(Qt.AlignCenter)
            if is_ref:
                role_item.setForeground(QColor('#2E7D32'))
            if at_bound:
                role_item.setBackground(bound_bg)
            self._shift_table.setItem(row_idx, 3, role_item)

            if not is_ref:
                non_ref_shifts.append(shift)

        self._shift_table.setSortingEnabled(True)

        if non_ref_shifts:
            arr, abs_arr = np.array(non_ref_shifts), np.abs(np.array(non_ref_shifts))
            stats_text = (
                f'N aligned: {len(arr)}   |   '
                f'Mean |shift|: {np.mean(abs_arr):.4f}   |   '
                f'Max |shift|: {np.max(abs_arr):.4f}   |   '
                f'Std |shift|: {np.std(abs_arr):.4f}   |   '
                f'Min: {np.min(arr):+.4f}   Max: {np.max(arr):+.4f}'
            )
            if n_bound_hits:
                stats_text += (
                    f'     ⚠  {n_bound_hits} '
                    f'{"spectra" if n_bound_hits != 1 else "spectrum"} hit the Max shift bound '
                    f'— increase Max shift and re-run'
                )
                self._stats_label.setStyleSheet(
                    'background-color: #FFF3E0; padding: 6px; border-radius: 4px; '
                    'font-family: monospace; border: 1px solid #FF9800;'
                )
            else:
                self._stats_label.setStyleSheet(
                    'background-color: #E8F5E9; padding: 6px; border-radius: 4px; '
                    'font-family: monospace;'
                )
            self._stats_label.setText(stats_text)
        else:
            self._stats_label.setText('')
            self._stats_label.setStyleSheet(
                'background-color: #E8F5E9; padding: 6px; border-radius: 4px; '
                'font-family: monospace;'
            )

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    def _current_ref_label(self):
        idx = self.reference_combo.currentIndex()
        return self.selected_spectra[idx]['label'] \
               if 0 <= idx < len(self.selected_spectra) else None

    def _data_range(self):
        if not self.selected_spectra:
            return None, None
        x_mins, x_maxs = [], []
        for s in self.selected_spectra:
            x = s.get('x_scale', np.array([]))
            if len(x):
                x_mins.append(float(np.min(x)))
                x_maxs.append(float(np.max(x)))
        return (min(x_mins), max(x_maxs)) if x_mins else (None, None)

    def _show_help(self):
        try:
            from src.help.xaxis_alignment_help import (
                get_xaxis_alignment_help_content, get_xaxis_alignment_help_title)
            from src.help.help_window import show_help_window
            show_help_window(self, get_xaxis_alignment_help_title(),
                             get_xaxis_alignment_help_content())
        except Exception:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Help',
                                    'Help documentation is not available at this time.')

    # ──────────────────────────────────────────────────────────────────
    # Table export
    # ──────────────────────────────────────────────────────────────────

    def _table_as_text(self, sep='	') -> str:
        """Return the shift table as a delimited string (header + rows)."""
        headers = [
            self._shift_table.horizontalHeaderItem(c).text()
            for c in range(self._shift_table.columnCount())
        ]
        lines = [sep.join(headers)]
        for r in range(self._shift_table.rowCount()):
            row = []
            for c in range(self._shift_table.columnCount()):
                item = self._shift_table.item(r, c)
                row.append(item.text() if item else '')
            lines.append(sep.join(row))
        return '\n'.join(lines)

    def _copy_table_to_clipboard(self):
        QApplication.clipboard().setText(self._table_as_text(sep='\t'))

    def _export_table_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export shift table', 'xaxis_shifts.csv',
            'CSV files (*.csv);;All files (*)'
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(self._table_as_text(sep=','))
        except OSError as exc:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Export failed', str(exc))

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — commits directly via commit_callback. No
        separate Run step: feedback (success or failure) is shown right
        here next to the buttons that triggered it, instead of in a
        disconnected main-window message box.

        Re-runs the alignment with whatever settings are currently shown,
        whether or not Run preview was clicked first — Run preview exists
        purely so you can inspect the result before committing. The dialog
        closes itself once the commit succeeds.
        """
        from PyQt5.QtWidgets import QMessageBox

        if self.commit_callback is None:
            QMessageBox.critical(
                self, 'Not Available',
                'This dialog was opened without a way to apply changes. '
                'Please reopen it via Parameters.'
            )
            return

        if len(self.selected_spectra) < 2:
            QMessageBox.warning(
                self, 'Insufficient Spectra',
                'X-axis alignment requires at least 2 selected spectra.'
            )
            return

        # Strip the dialog's internal preview-cache keys (_cached_aligned /
        # _cached_hash) — they're large (full spectrum dicts with numpy
        # arrays) and only meaningful for re-populating this dialog, not
        # for the actual commit or the operations history record.
        settings = {k: v for k, v in self.get_settings().items()
                    if not k.startswith('_cached')}

        action = ('add the aligned result as new spectra' if add_as_new
                  else 'replace the selected spectra with their aligned result')
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
        x_range = None
        if self.range_group.isChecked():
            x_lo, x_hi = self.x_min_spin.value(), self.x_max_spin.value()
            if x_lo < x_hi:
                x_range = (x_lo, x_hi)
        settings = {
            'reference_spectrum_index': self.reference_combo.currentIndex(),
            'max_shift':                self.max_shift_spin.value(),
            'interpolation_method':     self.interp_combo.currentText(),
            'x_range':                  x_range,
        }
        # Persist cached preview results so they survive dialog re-open
        if self._aligned_spectra and self._preview_settings_hash:
            settings['_cached_aligned'] = self._aligned_spectra
            settings['_cached_hash']    = self._preview_settings_hash
        return settings


# ======================================================================
# Canvas helpers
# ======================================================================

def _plot_spectra_on_ax(ax, spectra_list, color_map, ref_label,
                        legend_visible, title=''):
    """Common helper: plot a list of spectra onto *ax*."""
    for s in spectra_list:
        x = np.asarray(s.get('x_scale', []), dtype=float)
        y = np.asarray(s.get('y_scale', []), dtype=float)
        if not len(x):
            continue
        is_ref = (s['label'] == ref_label or
                  s.get('xaxis_alignment_info', {}).get('is_reference', False))
        col = 'black' if is_ref else color_map.get(s['label'], '#888888')
        ax.plot(x, y, color=col, lw=2.0 if is_ref else 1.0, alpha=0.85,
                label=f'{s["label"]} (ref)' if is_ref else s['label'],
                zorder=5 if is_ref else 2)
    ax.set_ylabel('Intensity', fontsize=9)
    ax.grid(True, linestyle='--', alpha=0.4)
    if title:
        ax.set_title(title, fontsize=10)
    if legend_visible and len(spectra_list) > 1:
        ax.legend(loc='best', fontsize=7)


class _ComparisonCanvas(FigureCanvas):
    """
    Comparison canvas with two modes:
      Subplots — Original (top) / Aligned (bottom), shared x-axis
      Overlay  — Original (dashed) and Aligned (solid) on one axes, colour-coded
    Also supports drawing originals-only before a preview has been run.
    """

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#f0f0f0')

    def plot_originals_only(self, originals, ref_label=None,
                             legend_visible=False, overlay=False):
        """Show only the original spectra before a preview run."""
        self._fig.clear()
        if not originals:
            self.draw_idle()
            return
        ax = self._fig.add_subplot(111)
        ax.set_facecolor('#ffffff')
        color_map = {s['label']: _COLORS[i % len(_COLORS)]
                     for i, s in enumerate(originals)}
        _plot_spectra_on_ax(ax, originals, color_map, ref_label,
                            legend_visible, 'Spectra (run preview to align)')
        ax.set_xlabel('x', fontsize=9)
        self._fig.tight_layout()
        self.draw_idle()

    def plot_comparison(self, originals, aligned, ref_label=None,
                        legend_visible=False, overlay=False):
        self._fig.clear()
        if not originals:
            self.draw_idle()
            return

        color_map = {s['label']: _COLORS[i % len(_COLORS)]
                     for i, s in enumerate(originals)}
        n = len(originals)

        if overlay:
            ax = self._fig.add_subplot(111)
            ax.set_facecolor('#ffffff')
            # Originals: dashed
            for s in originals:
                x = np.asarray(s.get('x_scale', []), dtype=float)
                y = np.asarray(s.get('y_scale', []), dtype=float)
                if not len(x):
                    continue
                is_ref = (s['label'] == ref_label)
                col = 'black' if is_ref else color_map.get(s['label'], '#888')
                lbl = f'{s["label"]} orig' if legend_visible else '_nolegend_'
                ax.plot(x, y, color=col, lw=1.0, alpha=0.45,
                        linestyle='--', label=lbl, zorder=2)
            # Aligned: solid
            if aligned:
                for s in aligned:
                    x = np.asarray(s.get('x_scale', []), dtype=float)
                    y = np.asarray(s.get('y_scale', []), dtype=float)
                    if not len(x):
                        continue
                    is_ref = s.get('xaxis_alignment_info', {}).get('is_reference', False)
                    col = 'black' if is_ref else color_map.get(s['label'], '#888')
                    lbl = f'{s["label"]} aligned' if legend_visible else '_nolegend_'
                    ax.plot(x, y, color=col, lw=2.0 if is_ref else 1.5,
                            alpha=0.9, linestyle='-', label=lbl, zorder=5 if is_ref else 3)
            ax.set_xlabel('x', fontsize=9)
            ax.set_ylabel('Intensity', fontsize=9)
            ax.set_title(
                f'Original (dashed) vs Aligned (solid) — {n} spectra', fontsize=10
            )
            ax.grid(True, linestyle='--', alpha=0.4)
            if legend_visible and n > 1:
                ax.legend(loc='best', fontsize=7)

        else:  # Subplots
            ax_top = self._fig.add_subplot(211)
            ax_bot = self._fig.add_subplot(212, sharex=ax_top)
            for ax in (ax_top, ax_bot):
                ax.set_facecolor('#ffffff')
            _plot_spectra_on_ax(ax_top, originals, color_map, ref_label,
                                legend_visible, f'Original ({n} spectra)')
            if aligned:
                _plot_spectra_on_ax(ax_bot, aligned, color_map, ref_label,
                                    legend_visible, f'After alignment ({len(aligned)} spectra)')
            ax_bot.set_xlabel('x', fontsize=9)

        self._fig.tight_layout()
        self.draw_idle()


class _ShiftPlotCanvas(FigureCanvas):
    """Bar + scatter shift-per-spectrum chart."""

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        self._ax  = self._fig.add_subplot(111)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#f0f0f0')
        self._ax.set_facecolor('#ffffff')

    def plot_shifts(self, aligned, ref_label=None, labels=None, rotation=45, fontsize=8):
        """labels, rotation, fontsize: pre-computed display labels (already
        shortened/truncated/indexed as the caller's display options
        dictate — see XAxisAlignmentDialog._get_shift_plot_labels) and the
        rotation/font size to draw them with. labels=None falls back to
        the original fixed last-18-chars truncation, for any other caller
        that doesn't supply display options."""
        self._ax.clear()
        entries = [
            (i + 1, s['label'], float(s.get('xaxis_alignment_info', {}).get('shift', 0.0)))
            for i, s in enumerate(aligned)
            if not s.get('xaxis_alignment_info', {}).get('is_reference', False)
        ]
        if not entries:
            self._ax.text(0.5, 0.5, 'No shifts to display',
                          transform=self._ax.transAxes,
                          ha='center', va='center', color='grey')
            self.draw_idle()
            return

        raw_labels = [e[1] for e in entries]
        shifts = [e[2] for e in entries]
        arr    = np.array(shifts)

        bar_colors = ['#1565C0' if v >= 0 else '#B71C1C' for v in shifts]
        self._ax.bar(range(len(entries)), shifts, color=bar_colors,
                     alpha=0.7, edgecolor='white', linewidth=0.5)
        self._ax.scatter(range(len(entries)), shifts, color='black', s=40, zorder=5)
        self._ax.axhline(0, color='black', linewidth=0.8, linestyle='--')

        mean_s, std_s = float(np.mean(arr)), float(np.std(arr))
        self._ax.axhline(mean_s, color='#2E7D32', linewidth=1.2,
                         label=f'Mean = {mean_s:+.4f}')
        self._ax.axhspan(mean_s - std_s, mean_s + std_s,
                         color='#A5D6A7', alpha=0.25, label=f'±1 std = {std_s:.4f}')

        if labels is None:
            labels = [lbl if len(lbl) <= 20 else f'…{lbl[-18:]}' for lbl in raw_labels]
        ha = 'right' if rotation > 0 else 'center'
        self._ax.set_xticks(range(len(entries)))
        self._ax.set_xticklabels(labels, rotation=rotation, ha=ha, fontsize=fontsize)
        self._ax.set_xlabel('Spectrum', fontsize=9)
        self._ax.set_ylabel('Shift (x-units)', fontsize=9)
        self._ax.set_title('X-axis shift per spectrum', fontsize=10)
        self._ax.legend(fontsize=8, loc='best')
        self._ax.grid(True, axis='y', linestyle='--', alpha=0.4)
        self._fig.tight_layout()
        self.draw_idle()
