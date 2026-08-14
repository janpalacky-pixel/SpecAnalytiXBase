# src/views/dialogs/visualization_analysis/reference_matching_dialog.py
"""
Reference Library Matching dialog.

Left panel (fixed 340 px)
    Library groupbox  — load files button + summary label
    Settings groupbox — metric, top N, normalization
    Spectra list      — select query spectra
    Help | OK | Cancel

Right panel — QTabWidget
    Preview   — query spectrum + top-N reference overlays
    Results   — table (query label, rank, reference label, score,
                overlap %) + Copy / Export CSV/PDF
    Plots     — per-query bar/line/scatter charts
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QComboBox, QPushButton, QLabel, QSpinBox,
    QListWidget, QSizePolicy, QSplitter, QWidget, QTabWidget,
    QTableView, QHeaderView,
    QFileDialog, QApplication, QListWidgetItem, QStyledItemDelegate,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QStandardItemModel, QStandardItem

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key
from src.modules.utils.label_shortening import (
    make_shortened_name_delegate, make_display_text_delegate,
    compute_distinguishing_labels, make_shorten_names_checkbox,
)
logger = get_logger(__name__)

_MATCH_COLORS = ['#E65100','#1565C0','#2E7D32','#6A1B9A','#00838F']


class ReferenceMatchingDialog(QDialog):

    def __init__(self, parent=None, selected_spectra=None,
                 current_settings=None, all_spectra=None, main_controller=None):
        super().__init__(parent)
        self.setWindowTitle('Reference Library Matching')
        self.setMinimumSize(1060, 640)
        self.resize(1300, 780)
        # No WindowMinimizeButtonHint — this dialog is always modal (opened
        # via exec_()), so minimizing it would leave the whole app blocked
        # behind a taskbar entry with no visible sign anything is still
        # open — easy to mistake for a frozen app. Maximize stays available.
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        # main_controller — kept for callers/backward compatibility, but no
        # longer used for "shorten names": this dialog now has its own,
        # independent checkBox_shorten_names (see _build_spectra_group /
        # _shorten_names_enabled below) instead of reading the main
        # window's shared checkbox.
        self._main_controller = main_controller

        self.selected_spectra  = list(selected_spectra or [])
        self.all_spectra       = list(all_spectra or selected_spectra or [])
        self._settings         = dict(current_settings or {})
        self._results          = []
        self._preview_idx      = 0
        self._file_library     = []  # cached file-based library

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._refresh_all)

        self._init_complete = False
        self._build_ui()
        self._populate_list()
        self._restore_settings(self._settings)
        self._init_complete = True
        # Only apply a default selection on first open — if settings already
        # restored a selection, keep it. Defaults to just the first query
        # spectrum (see _select_first_only) rather than selecting every
        # spectrum at once.
        if not self._settings.get('query_selected'):
            self._select_first_only()

    # ------------------------------------------------------------------ #
    # Shorten names (display-only) — this dialog's own checkbox           #
    # ------------------------------------------------------------------ #

    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _on_shorten_names_toggled(self, *_):
        # All four consumers are paint-only delegates fed by
        # _shorten_names_enabled()/_display_labels_map() above — an
        # explicit viewport().update() on each just avoids waiting on the
        # next unrelated repaint for the new state to become visible.
        self._ref_list_widget.viewport().update()
        self._list.viewport().update()
        self._table.viewport().update()

    def _display_labels_map(self):
        """{full_label: display_label} for every one of self.selected_spectra
        — see _display_label's docstring for the same enabled/disabled and
        fallback behavior, just returning the whole map at once for
        plot-call sites that need it repeatedly per redraw."""
        if not self._shorten_names_enabled():
            return {}
        all_labels = [s.get('label', '') for s in self.selected_spectra]
        if len(all_labels) < 2:
            return {}
        return compute_distinguishing_labels(all_labels)

    def _display_label(self, label):
        """Shorten *label* for display right now (a one-off snapshot, for
        table cells / plot text rather than a live-updating list) — NOT
        cached, and computed only across self.selected_spectra's labels,
        matching what the query/reference lists themselves group by.
        Falls back to *label* unchanged when disabled or label isn't one
        of self.selected_spectra's."""
        return self._display_labels_map().get(label, label)

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 960])
        root.addWidget(splitter)

    # ── Left panel ──────────────────────────────────────────────────────

    def _build_left(self):
        w = QWidget()
        # setFixedWidth() on a panel INSIDE a QSplitter locks that panel's
        # width, defeating the splitter's own drag-to-resize handle for it
        # — the same setFixedWidth-fights-QSplitter pattern found and
        # fixed repeatedly elsewhere in this audit. setMinimumWidth still
        # keeps the panel from collapsing to nothing, while
        # splitter.setSizes([340, 960]) (see _build_ui) still controls the
        # actual STARTING width — the user can just resize afterward.
        w.setMinimumWidth(280)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        lib_grp = self._build_library_group()
        layout.addWidget(lib_grp)
        layout.addWidget(self._build_settings_group())

        spectra_grp = self._build_spectra_group()
        spectra_grp.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout.addWidget(spectra_grp)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        help_btn = QPushButton('Help')
        help_btn.setAutoDefault(False)
        help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(help_btn)
        ok_btn = QPushButton('Close')
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._save_and_close)

        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)
        return w

    def _build_library_group(self):
        from PyQt5.QtWidgets import QButtonGroup, QRadioButton
        group = QGroupBox('Reference library')
        layout = QVBoxLayout(group)

        # Mode radio buttons
        mode_row = QHBoxLayout()
        self._lib_mode_grp = QButtonGroup(self)
        self._rb_internal = QRadioButton('From loaded spectra')
        self._rb_external = QRadioButton('From file(s)')
        self._rb_internal.setChecked(True)
        self._lib_mode_grp.addButton(self._rb_internal, 0)
        self._lib_mode_grp.addButton(self._rb_external, 1)
        mode_row.addWidget(self._rb_internal)
        mode_row.addWidget(self._rb_external)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Internal: pick references from all loaded spectra
        self._internal_widget = QWidget()
        int_lay = QVBoxLayout(self._internal_widget)
        int_lay.setContentsMargins(0, 0, 0, 0)
        self._ref_list_widget = QListWidget()
        self._ref_list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self._ref_list_widget.setMinimumHeight(80)
        self._ref_list_widget.setMaximumHeight(200)
        for s in self.selected_spectra:
            item = QListWidgetItem(s['label'])
            # Identity, not label text, is what selection restore/matching
            # keys off of — see _visible_spectra, get_settings and
            # _restore_settings below.
            item.setData(Qt.UserRole, spectrum_key(s))
            self._ref_list_widget.addItem(item)
        # Display-only "shorten names" — safe here because selection is
        # read back via Qt.UserRole above, never by matching this list's
        # displayed text (see make_shortened_name_delegate's docstring).
        self._ref_list_widget.setItemDelegate(
            make_shortened_name_delegate(self._ref_list_widget, self._shorten_names_enabled)
        )
        self._ref_list_widget.itemSelectionChanged.connect(self._on_library_changed)
        int_lay.addWidget(self._ref_list_widget)

        int_btn_row = QHBoxLayout()
        sel_all_int_btn = QPushButton("Select all")
        sel_all_int_btn.clicked.connect(self._select_all_int_refs)
        clear_int_btn = QPushButton("Clear")
        clear_int_btn.clicked.connect(self._clear_int_refs)
        int_btn_row.addWidget(sel_all_int_btn)
        int_btn_row.addWidget(clear_int_btn)
        int_lay.addLayout(int_btn_row)
        layout.addWidget(self._internal_widget)

        # External: load from file
        self._external_widget = QWidget()
        ext_lay = QVBoxLayout(self._external_widget)
        ext_lay.setContentsMargins(0, 0, 0, 0)
        load_btn = QPushButton('Load library file(s)\u2026')
        load_btn.clicked.connect(self._load_library)
        ext_lay.addWidget(load_btn)
        self._lib_summary = QLabel('No library loaded')
        self._lib_summary.setStyleSheet('font-size:8pt; color:#555;')
        self._lib_summary.setWordWrap(True)
        ext_lay.addWidget(self._lib_summary)
        # List showing loaded reference spectra
        self._file_ref_list = QListWidget()
        self._file_ref_list.setSelectionMode(QListWidget.ExtendedSelection)
        self._file_ref_list.setMinimumHeight(80)
        self._file_ref_list.setMaximumHeight(200)
        self._file_ref_list.itemSelectionChanged.connect(self._schedule)
        ext_lay.addWidget(self._file_ref_list)

        # Select all / Clear for file library
        file_btn_row = QHBoxLayout()
        sel_all_file_btn = QPushButton("Select all")
        sel_all_file_btn.clicked.connect(self._select_all_file_refs)
        clear_file_btn = QPushButton("Clear")
        clear_file_btn.clicked.connect(self._clear_file_refs)
        file_btn_row.addWidget(sel_all_file_btn)
        file_btn_row.addWidget(clear_file_btn)
        ext_lay.addLayout(file_btn_row)
        self._external_widget.setVisible(False)
        layout.addWidget(self._external_widget)

        self._rb_internal.toggled.connect(self._on_lib_mode_changed)
        self._rb_external.toggled.connect(self._on_lib_mode_changed)
        # Set initial visibility explicitly
        self._internal_widget.setVisible(True)
        self._external_widget.setVisible(False)
        return group

    def _build_settings_group(self):
        group = QGroupBox('Matching settings')
        layout = QVBoxLayout(group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel('Metric:'))
        self._metric_combo = QComboBox()
        self._metric_combo.addItems(['cosine', 'pearson', 'euclidean'])
        self._metric_combo.setToolTip(
            'cosine    — scale-invariant dot product (recommended)\n'
            'pearson   — linear correlation coefficient\n'
            'euclidean — 1 / (1 + distance), sensitive to intensity scale'
        )
        self._metric_combo.currentIndexChanged.connect(self._on_metric_changed)
        row1.addWidget(self._metric_combo)
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel('Top N matches:'))
        self._topn_spin = QSpinBox()
        self._topn_spin.setRange(1, 20)
        self._topn_spin.setValue(5)
        self._topn_spin.setFixedWidth(55)
        self._topn_spin.valueChanged.connect(self._schedule)
        row2.addWidget(self._topn_spin)
        row2.addStretch()
        layout.addLayout(row2)

        self._norm_row = QWidget()
        norm_inner = QHBoxLayout(self._norm_row)
        norm_inner.setContentsMargins(0, 0, 0, 0)
        norm_inner.addWidget(QLabel('Pre-normalise:'))
        self._norm_combo = QComboBox()
        self._norm_combo.addItems(['none', 'vector', 'max peak', 'unit area'])
        self._norm_combo.setToolTip(
            'Relevant for euclidean metric only.\n'
            'none      — use spectra as-is\n'
            'vector    — divide by L2 norm\n'
            'max peak  — scale to maximum intensity = 1\n'
            'unit area — scale so total area = 1'
        )
        self._norm_combo.currentIndexChanged.connect(self._schedule)
        norm_inner.addWidget(self._norm_combo)
        norm_inner.addStretch()
        layout.addWidget(self._norm_row)
        self._norm_row.setVisible(False)  # hidden for cosine/pearson

        row4 = QHBoxLayout()
        row4.addWidget(QLabel('Min overlap %:'))
        from PyQt5.QtWidgets import QDoubleSpinBox
        self._overlap_spin = QDoubleSpinBox()
        self._overlap_spin.setRange(1.0, 100.0)
        self._overlap_spin.setDecimals(0)
        self._overlap_spin.setValue(50.0)
        self._overlap_spin.setFixedWidth(65)
        self._overlap_spin.setToolTip(
            'Minimum x-axis overlap (%) between query and reference\n'
            'required for a match to be considered reliable.\n'
            'Matches below this threshold are shown in grey with NaN score.'
        )
        self._overlap_spin.valueChanged.connect(self._schedule)
        row4.addWidget(self._overlap_spin)
        row4.addStretch()
        layout.addLayout(row4)
        return group

    def _build_spectra_group(self):
        group = QGroupBox('Query spectra')
        layout = QVBoxLayout(group)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel('Click: select & preview  |  Shift: extend  |  Ctrl: toggle'))
        hdr.addStretch()
        help_btn = QPushButton('?')
        help_btn.setFixedSize(18, 18)
        help_btn.setStyleSheet(
            'QPushButton { border-radius:9px; background:#1565C0; color:white; '
            'font-weight:bold; font-size:10px; padding:0px; }'
            'QPushButton:hover { background:#0D47A1; }'
        )
        help_btn.setToolTip(
            'Click any spectrum to select it and preview its top matches.\n'
            'Select several to see one subplot per spectrum in Preview\n'
            '(up to Max subplots below).\n'
            'All selected (blue) spectra are included in Results and Plots.\n'
            'Use Shift+click to extend selection, Ctrl+click to toggle.\n'
            'Select all / Clear for bulk selection.'
        )
        help_btn.clicked.connect(self._show_query_help)
        hdr.addWidget(help_btn)
        layout.addLayout(hdr)

        # Own, independent "Shorten names" toggle for this dialog — feeds
        # ALL FOUR display consumers: self._ref_list_widget and self._list
        # (both via make_shortened_name_delegate/_shorten_names_enabled),
        # plus the Results table's columns 0 and 2 (both via
        # make_display_text_delegate/_display_labels_map, which itself
        # calls _shorten_names_enabled). One checkbox, one flag, shared by
        # every consumer — see _shorten_names_enabled / _display_labels_map
        # above.
        shorten_row = QHBoxLayout()
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)
        shorten_row.addWidget(self.checkBox_shorten_names)
        shorten_row.addStretch()
        layout.addLayout(shorten_row)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        # Display-only "shorten names" — safe here because selection is
        # read back via Qt.UserRole (see _visible_spectra), never by
        # matching this list's displayed text.
        self._list.setItemDelegate(
            make_shortened_name_delegate(self._list, self._shorten_names_enabled)
        )
        layout.addWidget(self._list, stretch=1)

        btn_row = QHBoxLayout()
        for lbl, slot in [('Select all', self._select_all),
                           ('Clear', self._clear_selection)]:
            b = QPushButton(lbl)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        subplots_row = QHBoxLayout()
        subplots_row.addWidget(QLabel('Max subplots (Preview):'))
        self._preview_max_subplots_spin = QSpinBox()
        self._preview_max_subplots_spin.setRange(1, 20)
        self._preview_max_subplots_spin.setValue(4)
        self._preview_max_subplots_spin.setToolTip(
            'When more than one query spectrum is selected, the Preview '
            'tab shows one subplot per query (its own top matches), up to '
            'this many at once — raise it to see more selected spectra '
            'together, lower it to keep the plot area from getting '
            'crowded. Does not affect the Results table, which always '
            'lists every selected query.'
        )
        self._preview_max_subplots_spin.setKeyboardTracking(False)
        self._preview_max_subplots_spin.valueChanged.connect(self._schedule)
        subplots_row.addWidget(self._preview_max_subplots_spin)
        subplots_row.addStretch()
        layout.addLayout(subplots_row)

        return group

    # ── Right panel ─────────────────────────────────────────────────────

    def _build_right(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tabs = QTabWidget()
        self._tabs.tabBar().setExpanding(False)
        self._tabs.setStyleSheet(
            "QTabBar::tab { min-width: 70px; padding: 4px 12px; }"
        )

        # Preview tab
        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(0, 0, 0, 0)
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

        # QTableView + QStandardItemModel, NOT QTableWidget — kept as a
        # cleaner Qt Model/View design. Not itself related to the crash;
        # see the comment on setItemDelegateForColumn() below for that.
        self._table_model = QStandardItemModel(0, 5, self)
        self._table_model.setHorizontalHeaderLabels(
            ['Query spectrum', 'Rank', 'Reference', 'Score', 'Overlap %']
        )
        self._table = QTableView()
        self._table.setModel(self._table_model)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for c in (1, 3, 4):
            self._table.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeToContents)
        self._table.setEditTriggers(QTableView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        # Display-only "shorten names" — paint-only delegate, so the
        # QStandardItem's text() (what Copy/Export CSV actually reads,
        # see _table_text) always keeps the full/original label
        # regardless of what's shown on screen. self._display_labels_map()
        # is built from self.selected_spectra's labels only — a lookup
        # miss (e.g. column 2 "Reference" names when the library is an
        # external file, unrelated to self.selected_spectra) safely
        # passes the label through unchanged rather than shortening it
        # incorrectly, since .get(text, text) never rewrites a key it
        # doesn't recognize. In the common "From loaded spectra" library
        # mode, references ARE drawn from self.selected_spectra, so this
        # correctly shortens column 2 too in that case.
        #
        # parent=self._table is THE FIX for the real crash this dialog had
        # ("app just closes" / Windows "access violation" / Linux SIGSEGV
        # every time the Results table got real rows). Root-caused via a
        # from-scratch, fork-isolated reproduction of the actual dialog
        # class (build it, select spectra, populate the table, process
        # events — repeated 20 times per variant, in a fresh subprocess
        # each time so a segfault couldn't kill the test run): without an
        # explicit parent (or a kept Python reference), the
        # _DisplayTextDelegate object returned by make_display_text_delegate
        # has NOTHING keeping it alive in Python — setItemDelegateForColumn()
        # does NOT take ownership of it (this is documented Qt behaviour,
        # and make_shortened_name_delegate's own docstring already warns
        # about it). The delegate is garbage-collected right after this
        # call returns; the table still points at it internally. The next
        # time the table repaints (e.g. via app.processEvents() after
        # setRowCount()/appendRow()), Qt calls into the now-freed object
        # and the process segfaults. Reproduced 20/20 trials without
        # parent=self._table, 0/20 with it — same harness, only this one
        # line different. (An earlier, wrong theory blamed the table
        # being a sibling QTabWidget tab of a matplotlib canvas — see the
        # comment at the top of this method for why that was disproven.)
        self._table.setItemDelegateForColumn(
            0, make_display_text_delegate(self._display_labels_map, parent=self._table))
        self._table.setItemDelegateForColumn(
            2, make_display_text_delegate(self._display_labels_map, parent=self._table))
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

        # ── Plots tab ──────────────────────────────────────────────
        plw = QWidget()
        pll = QVBoxLayout(plw)
        pll.setContentsMargins(4, 4, 4, 4)
        pll.setSpacing(4)
        # Plot controls row
        pc_row = QHBoxLayout()
        pc_row.addWidget(QLabel("Max subplots:"))
        from PyQt5.QtWidgets import QSpinBox as _QSB
        self._max_subplots_spin = _QSB()
        self._max_subplots_spin.setRange(1, 100)
        self._max_subplots_spin.setValue(5)
        self._max_subplots_spin.setFixedWidth(55)
        self._max_subplots_spin.setToolTip("Maximum number of query spectra to show as subplots")
        # Without this, typing e.g. "100" fires _refresh_plots on every
        # intermediate digit (1, 10, 100) — each one a full matplotlib
        # replot with up to that many subplots. Same missing-keyboard-
        # tracking pattern found and fixed elsewhere in this audit (e.g.
        # SG-Smoothing's window-length spinbox); _preview_max_subplots_spin
        # a few dozen lines below already gets this right, just not
        # applied here consistently.
        self._max_subplots_spin.setKeyboardTracking(False)
        self._max_subplots_spin.valueChanged.connect(self._refresh_plots)
        pc_row.addWidget(self._max_subplots_spin)
        pc_row.addSpacing(12)
        pc_row.addWidget(QLabel("Plot type:"))
        self._plot_type_combo = QComboBox()
        self._plot_type_combo.addItems(["Bar", "Line", "Scatter", "Bar + Line"])
        self._plot_type_combo.currentIndexChanged.connect(self._refresh_plots)
        pc_row.addWidget(self._plot_type_combo)
        pc_row.addSpacing(12)
        pc_row.addWidget(QLabel("Label rotation:"))
        self._label_rot_combo = QComboBox()
        self._label_rot_combo.addItems(["0°", "30°", "45°", "90°"])
        self._label_rot_combo.setCurrentIndex(2)
        self._label_rot_combo.currentIndexChanged.connect(self._refresh_plots)
        pc_row.addWidget(self._label_rot_combo)
        pc_row.addSpacing(12)
        pc_row.addWidget(QLabel("Last N chars:"))
        from PyQt5.QtWidgets import QSpinBox as _QSB2
        self._label_chars_spin = _QSB2()
        self._label_chars_spin.setRange(0, 200)
        self._label_chars_spin.setValue(0)
        self._label_chars_spin.setSpecialValueText("all")
        self._label_chars_spin.setFixedWidth(60)
        # Same missing-keyboard-tracking issue as _max_subplots_spin above.
        self._label_chars_spin.setKeyboardTracking(False)
        self._label_chars_spin.valueChanged.connect(self._refresh_plots)
        pc_row.addWidget(self._label_chars_spin)
        pc_row.addSpacing(12)
        pc_row.addWidget(QLabel('Bar colours:'))
        self._palette_combo = QComboBox()
        self._palette_combo.addItems([
            'default', 'tab10', 'Set1', 'Set2', 'Set3',
            'coolwarm', 'viridis', 'plasma', 'RdYlGn', 'spectral'
        ])
        self._palette_combo.setToolTip(
            'Colour palette for ranked matches.\n'
            '"default": fixed 5-colour sequence (orange, blue, green, purple, teal)\n'
            'Other options: matplotlib colormaps sampled for top-N colours'
        )
        self._palette_combo.currentIndexChanged.connect(self._refresh_plots)
        pc_row.addWidget(self._palette_combo)
        pc_row.addSpacing(12)
        pc_row.addWidget(QLabel('Y min:'))
        from PyQt5.QtWidgets import QDoubleSpinBox as _QDSB
        self._y_bottom_spin = _QDSB()
        self._y_bottom_spin.setRange(-1.0, 1.0)
        self._y_bottom_spin.setDecimals(4)
        self._y_bottom_spin.setSingleStep(0.01)
        self._y_bottom_spin.setValue(0.9)
        self._y_bottom_spin.setFixedWidth(80)
        self._y_bottom_spin.setToolTip('Minimum y-axis value for score plots')
        # Same missing-keyboard-tracking issue as _max_subplots_spin above.
        self._y_bottom_spin.setKeyboardTracking(False)
        self._y_bottom_spin.valueChanged.connect(self._refresh_plots)
        pc_row.addWidget(self._y_bottom_spin)
        pc_row.addSpacing(6)
        pc_row.addWidget(QLabel('Y max:'))
        self._y_top_spin = _QDSB()
        self._y_top_spin.setRange(-1.0, 1.0)
        self._y_top_spin.setDecimals(4)
        self._y_top_spin.setSingleStep(0.001)
        self._y_top_spin.setValue(1.0)
        self._y_top_spin.setFixedWidth(80)
        self._y_top_spin.setToolTip('Maximum y-axis value for score plots')
        # Same missing-keyboard-tracking issue as _max_subplots_spin above.
        self._y_top_spin.setKeyboardTracking(False)
        self._y_top_spin.valueChanged.connect(self._refresh_plots)
        pc_row.addWidget(self._y_top_spin)
        pc_row.addStretch()
        pll.addLayout(pc_row)
        self._scores_canvas = _ScoresCanvas(plw)
        pll.addWidget(NavigationToolbar(self._scores_canvas, plw))
        pll.addWidget(self._scores_canvas)
        self._tabs.addTab(plw, 'Plots')

        self._tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self._tabs)
        return w

    # ------------------------------------------------------------------ #
    # Library loading                                                      #
    # ------------------------------------------------------------------ #

    def _on_metric_changed(self, *_):
        """Show pre-normalise only for euclidean metric."""
        is_euclidean = self._metric_combo.currentText() == 'euclidean'
        self._norm_row.setVisible(is_euclidean)
        self._schedule()

    def _select_all_int_refs(self):
        self._ref_list_widget.blockSignals(True)
        for i in range(self._ref_list_widget.count()):
            self._ref_list_widget.item(i).setSelected(True)
        self._ref_list_widget.blockSignals(False)
        self._on_library_changed()

    def _clear_int_refs(self):
        self._ref_list_widget.blockSignals(True)
        for i in range(self._ref_list_widget.count()):
            self._ref_list_widget.item(i).setSelected(False)
        self._ref_list_widget.blockSignals(False)
        self._on_library_changed()

    def _select_all_file_refs(self):
        self._file_ref_list.blockSignals(True)
        for i in range(self._file_ref_list.count()):
            self._file_ref_list.item(i).setSelected(True)
        self._file_ref_list.blockSignals(False)
        self._schedule()

    def _clear_file_refs(self):
        self._file_ref_list.blockSignals(True)
        for i in range(self._file_ref_list.count()):
            self._file_ref_list.item(i).setSelected(False)
        self._file_ref_list.blockSignals(False)
        self._schedule()

    def _on_lib_mode_changed(self):
        internal = self._rb_internal.isChecked()
        self._internal_widget.setVisible(internal)
        self._external_widget.setVisible(not internal)
        # Clear results if switching to external with no library loaded
        if not internal and not self._file_library:
            self._results = []
            self._table_model.setRowCount(0)
            self._stats_label.setText('')
            self._scores_canvas.plot([], {})
            self._preview_canvas.plot({}, [])
        self._schedule()

    def _on_library_changed(self):
        n = len(self._ref_list_widget.selectedItems())
        # hint label removed
        self._schedule()

    def _load_library(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Load reference library',
            self._settings.get('library_dir', ''),
            'Spectral files (*.csv *.txt *.dat *.xlsx *.xls);;All files (*)'
        )
        if not paths:
            return
        import numpy as np
        from src.modules.visualization_analysis.reference_matching_manager import (
            ReferenceMatchingManager
        )
        mgr = ReferenceMatchingManager()
        try:
            n = mgr.load_library(paths)
            # Cache the loaded library so it persists across mode switches
            self._file_library = list(mgr._library)
            self._settings['library_paths'] = paths
            self._settings['library_dir']   = str(
                __import__('pathlib').Path(paths[0]).parent
            )
            self._lib_summary.setText(
                f'{n} reference spectra loaded from '
                f'{len(paths)} file(s).'
            )
            self._lib_summary.setStyleSheet('font-size:8pt; color:#2E7D32;')
            self._file_ref_list.clear()
            for entry in self._file_library:
                item = QListWidgetItem(entry['label'])
                self._file_ref_list.addItem(item)
                item.setSelected(True)
            self._schedule()
        except Exception as exc:
            self._lib_summary.setText(f'\u26a0  {exc}')
            self._lib_summary.setStyleSheet('font-size:8pt; color:#C62828;')

    # ------------------------------------------------------------------ #
    # Spectra list                                                         #
    # ------------------------------------------------------------------ #

    def _populate_list(self):
        self._list.blockSignals(True)
        self._list.clear()
        for s in self.selected_spectra:
            item = QListWidgetItem(s['label'])
            item.setData(Qt.UserRole, spectrum_key(s))
            self._list.addItem(item)
        self._list.blockSignals(False)
        if self.selected_spectra:
            self._list.setCurrentRow(0)
            self._highlight_nav_item(0)

    def _show_query_help(self):
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self, 'Query spectra — how selection works',
            '<b>Preview (click any spectrum):</b><br>'
            'Clicking a spectrum selects it and shows its top matches in the '
            '<b>Preview</b> tab.<br><br>'
            '<b>Previewing more than one at once:</b><br>'
            'If more than one spectrum is selected (blue-highlighted), the '
            'Preview tab shows one subplot per selected spectrum — each with '
            'its own top matches — instead of just a single one, up to the '
            '<b>Max subplots</b> limit below the spectra list. If more '
            'spectra are selected than that limit allows, the plot shows a '
            'note (\u201cShowing N of M\u201d) rather than silently leaving '
            'the rest out with no indication. Raise Max subplots to see '
            'more at once, or lower it if the plot area feels crowded — it '
            'only affects this preview, never the Results table, which '
            'always lists every selected query regardless of this setting.<br><br>'
            '<b>Results &amp; Plots (selected spectra):</b><br>'
            'All <b>blue-highlighted</b> spectra are matched against the reference '
            'library and appear in the <b>Results</b> table and <b>Plots</b> tab. '
            'Use <b>Select all</b> to include all spectra, or manually build a '
            'subset using Shift+click (extend) and Ctrl+click (toggle).<br><br>'
            '<b>Summary:</b><br>'
            '\u2022 Click = select one + preview<br>'
            '\u2022 Shift+click = extend selection<br>'
            '\u2022 Ctrl+click = toggle individual spectrum<br>'
            '\u2022 Select all / Clear = bulk selection for Results and Preview<br>'
            '\u2022 Max subplots = how many selected spectra the Preview shows at once'
        )

    def _on_item_clicked(self, item):
        # preview_idx itself is kept consistent by _sync_preview_idx(),
        # called from _on_selection_changed below — itemSelectionChanged
        # fires for this click too (and, unlike itemClicked, also for
        # keyboard-driven selection changes), so there's no need to
        # duplicate that logic here. This handler now only needs to make
        # sure a plain click (which doesn't always change the selection,
        # e.g. clicking the already-sole-selected item) still triggers a
        # refresh.
        if self._init_complete:
            self._schedule()

    def _sync_preview_idx(self):
        """Keep _preview_idx pointing at a row that is actually selected
        right now.

        Uses QListWidget's own currentRow() — which Qt keeps correct for
        every selection-changing interaction, mouse or keyboard — rather
        than a value maintained by hand from itemClicked alone.
        itemClicked only fires for mouse clicks, so a selection built or
        changed via the keyboard (arrow keys to move, Shift+Arrow to
        extend a range, Ctrl+Space to toggle the current item) never
        touched _preview_idx before this: it stayed frozen at whatever it
        was initialized to (row 0) or last set to by a mouse click, no
        matter what the visibly-highlighted selection became afterward —
        exactly the "Query" spectrum in the preview not matching what's
        actually selected in the Query spectra list.

        currentRow() alone isn't quite enough by itself, though: for a
        Ctrl+click/Ctrl+Space that TOGGLES the current item OFF,
        currentRow() still reports that now-deselected row. So this
        checks it's actually selected before adopting it, and otherwise
        falls back to any other currently-selected row — the same
        validation previously applied only inside the click handler, now
        applied uniformly for every kind of selection change.
        """
        row = self._list.currentRow()
        if row >= 0 and self._list.item(row).isSelected():
            self._preview_idx = row
            return
        # currentRow() isn't usable right now (nothing is "current", or
        # the current row isn't selected). If _preview_idx already points
        # at a row that's still selected, leave it alone — an unrelated
        # selection change elsewhere in the list shouldn't disturb an
        # already-valid preview. Otherwise, fall back to any other
        # currently-selected row, or to nothing if none remain.
        #
        # This must run whenever the above is true, INCLUDING when
        # _preview_idx is already None — an earlier version of this
        # fix only searched for a fallback when _preview_idx held some
        # specific stale value, so a selection built up from a None
        # starting point (e.g. right after Clear, then selecting new
        # rows one at a time without ever moving "current" along with
        # them) never found the newly-selected rows at all and stayed
        # stuck on None.
        if (self._preview_idx is not None
                and self._preview_idx < self._list.count()
                and self._list.item(self._preview_idx).isSelected()):
            return
        selected_rows = [i for i in range(self._list.count())
                         if self._list.item(i).isSelected()]
        self._preview_idx = selected_rows[-1] if selected_rows else None

    def _on_selection_changed(self):
        self._sync_preview_idx()
        self._highlight_nav_item(self._preview_idx)
        if self._init_complete:
            self._schedule()



    def _on_list_row_changed(self, row):
        # Only used for programmatic row changes (populate_list, etc.)
        pass

    def _highlight_nav_item(self, row):
        pass

    def _update_nav(self):
        pass  # Navigator arrows removed — no-op kept for compatibility

    def _prev(self):
        pass

    def _next(self):
        pass

    def _select_all(self):
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setSelected(True)
        self._list.blockSignals(False)
        self._sync_preview_idx()
        if self._preview_idx is None and self._list.count() > 0:
            self._preview_idx = 0   # everything just got selected
        if self._init_complete:
            self._schedule()

    def _select_first_only(self):
        """Select just the first query spectrum — used only as the
        dialog's own opening default (see __init__), instead of
        _select_all(). Selecting every spectrum by default made the very
        first computation run against the whole list at once, which is
        rarely what's wanted when the dialog has just been opened and
        settings haven't been chosen yet; starting from one spectrum lets
        the very first Preview render quickly and gives an obvious
        "add more with Shift/Ctrl+click, or Select all" starting point.
        Not used for Clear/re-selection elsewhere — those already have
        their own explicit meaning."""
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setSelected(i == 0)
        self._list.blockSignals(False)
        self._sync_preview_idx()
        if self._preview_idx is None and self._list.count() > 0:
            self._preview_idx = 0
        if self._init_complete:
            self._schedule()

    def _clear_selection(self):
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setSelected(False)
        self._list.blockSignals(False)
        # Nothing is selected anymore — the preview must not keep showing
        # whatever was last previewed.
        self._preview_idx = None
        if self._init_complete:
            self._schedule()

    def _visible_spectra(self):
        sel = {item.data(Qt.UserRole) for item in self._list.selectedItems()}
        return [s for s in self.selected_spectra if spectrum_key(s) in sel]

    # ------------------------------------------------------------------ #
    # Preview                                                              #
    # ------------------------------------------------------------------ #

    def _schedule(self, *_):
        if self._init_complete:
            self._timer.start()

    def _refresh_all(self, *_):
        """Recompute results first — the single source of truth for the
        Results tab AND, now, for the multi-query Preview grid below —
        then refresh whatever's currently visible."""
        # Wrapped for the same reason as _on_tab_changed below: this runs
        # from a QTimer.timeout signal, so an uncaught exception here has
        # no dialog-level catch above it and would otherwise surface as
        # the dialog appearing to freeze/crash rather than a readable
        # message.
        try:
            self._compute_results()
            self._refresh_preview()
            if self._results:
                self._refresh_plots()
        except Exception as exc:
            logger.exception("Reference Matching: failed to refresh")
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, 'Could not update',
                f'An error occurred while updating the matches:\n\n{exc}\n\n'
                'Please check your spectra selection and settings, and see '
                'the log for details.'
            )

    def _refresh_preview(self):
        visible = self._visible_spectra()

        if len(visible) > 1:
            # More than one query spectrum selected — show one subplot per
            # query (up to Max subplots), instead of silently showing only
            # a single one with no indication the rest of the selection
            # was being ignored. Reuses self._results (just computed by
            # _refresh_all above) rather than a second identical call to
            # mgr.match() — this is exactly the same computation the
            # Results tab already needed.
            max_n = self._preview_max_subplots_spin.value()
            label_to_spectrum = {s['label']: s for s in self.selected_spectra}
            pairs = []
            for res in self._results[:max_n]:
                sp = label_to_spectrum.get(res['label'])
                if sp is not None:
                    pairs.append((sp, res['matches']))
            settings = self.get_settings()
            self._preview_canvas.plot_multi(
                pairs, len(visible), max_n,
                normalization=settings.get('normalization', 'none'),
                display_labels=self._display_labels_map())
            self._update_nav()
            return

        # Zero or one query spectrum selected — unchanged single-spectrum view.
        if self._preview_idx is None or not self.selected_spectra:
            self._preview_canvas.show_no_selection()
            self._update_nav()
            return
        idx = max(0, min(self._preview_idx, len(self.selected_spectra) - 1))
        if idx >= len(self.selected_spectra):
            return
        s        = self.selected_spectra[idx]
        settings = self.get_settings()

        mgr = self._build_manager()
        if mgr is None:
            return

        results = mgr.match([s], settings)
        if results:
            self._preview_canvas.plot(s, results[0]['matches'],
                normalization=settings.get('normalization', 'none'),
                display_labels=self._display_labels_map())
        self._update_nav()

    # ------------------------------------------------------------------ #
    # Manager factory                                                      #
    # ------------------------------------------------------------------ #

    def _build_manager(self):
        """Build and return a loaded ReferenceMatchingManager, or None."""
        import numpy as np
        from src.modules.visualization_analysis.reference_matching_manager import (
            ReferenceMatchingManager
        )
        mgr = ReferenceMatchingManager()
        if self._rb_internal.isChecked():
            sel_ids = {item.data(Qt.UserRole)
                       for item in self._ref_list_widget.selectedItems()}
            ref_spectra = [s for s in self.selected_spectra
                           if spectrum_key(s) in sel_ids]
            if not ref_spectra:
                return None
            mgr._library = [
                {
                    'label': s['label'],
                    'x':     np.asarray(s['x_scale'], dtype=float),
                    'y':     np.asarray(s['y_scale'], dtype=float),
                    # Lets the manager detect and skip a spectrum being
                    # matched against itself when it's selected as both a
                    # query and a reference — by actual identity, not by
                    # label (see ReferenceMatchingManager._key_for). Only
                    # set here, in internal mode, where we genuinely know
                    # this library entry IS one of the app's own spectra;
                    # file-loaded entries never get this, so a coincidental
                    # label match with an external file is never excluded.
                    'source_key': (s.get('metadata') or {}).get('unique_id') or s['label'],
                }
                for s in ref_spectra
            ]
            mgr.library_path = ['<internal>']
            return mgr
        else:
            # Use cached library, filtered by selection if any items selected
            if self._file_library:
                sel = {self._file_ref_list.item(i).text()
                       for i in range(self._file_ref_list.count())
                       if self._file_ref_list.item(i).isSelected()}
                # If nothing selected, use all
                lib = [e for e in self._file_library if e['label'] in sel] \
                      if sel else list(self._file_library)
                if not lib:
                    return None
                mgr._library = lib
                mgr.library_path = self._settings.get('library_paths', ['<cached>'])
                return mgr
            paths = self._settings.get('library_paths')
            if not paths:
                return None
            try:
                mgr.load_library(paths)
                self._file_library = list(mgr._library)  # cache for future
                return mgr
            except Exception:
                return None

    # ------------------------------------------------------------------ #
    # Results                                                              #
    # ------------------------------------------------------------------ #

    def _refresh_plots(self, *_):
        """Refresh only the Plots tab without recomputing results."""
        if self._results:
            self._scores_canvas.plot(
                self._results,
                self.get_settings(),
                max_subplots=self._max_subplots_spin.value(),
                plot_type=self._plot_type_combo.currentText(),
                label_rotation=int(self._label_rot_combo.currentText().replace("°", "")),
                label_chars=self._label_chars_spin.value(),
                y_bottom=self._y_bottom_spin.value(),
                y_top=self._y_top_spin.value(),
                palette=self._palette_combo.currentText(),
                display_labels=self._display_labels_map(),
            )

    def _on_tab_changed(self, idx):
        if self._init_complete and self._tabs.tabText(idx) in ('Results', 'Plots'):
            # Wrapped in try/except: an uncaught exception raised here
            # propagates out of a Qt signal handler with no dialog-level
            # catch anywhere above it, which surfaces to the user as the
            # whole dialog (or app) appearing to "crash" rather than a
            # readable error message. A real crash of exactly this kind
            # was found and fixed at its root cause (see
            # label_shortening.py's _shorten_label_group — an empty
            # spectrum label could raise IndexError inside
            # compute_distinguishing_labels, called from here via
            # _compute_results -> _display_labels_map). This guard is a
            # second line of defense so any OTHER not-yet-found edge
            # case fails as a message box instead of silently taking the
            # dialog down.
            try:
                self._compute_results()
            except Exception as exc:
                logger.exception("Reference Matching: failed to compute results "
                                 "on tab switch")
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, 'Could not update results',
                    f'An error occurred while computing match results:\n\n{exc}\n\n'
                    'This tab may show stale or incomplete data. Please check your '
                    'spectra selection and settings, and see the log for details.'
                )

    def _compute_results(self):
        visible = self._visible_spectra()
        if not visible:
            return

        mgr = self._build_manager()
        if mgr is None:
            self._stats_label.setText('\u26a0  No reference library defined.')
            self._stats_label.setStyleSheet(
                'background-color:#FFEBEE; padding:6px; border-radius:4px; '
                'font-family:monospace; color:#C62828;'
            )
            return

        settings = self.get_settings()
        self._results = mgr.match(visible, settings)
        self._populate_table(self._results)
        self._scores_canvas.plot(
            self._results, settings,
            max_subplots=self._max_subplots_spin.value(),
            plot_type=self._plot_type_combo.currentText(),
            label_rotation=int(self._label_rot_combo.currentText().replace("°", "")),
            label_chars=self._label_chars_spin.value(),
            y_bottom=self._y_bottom_spin.value(),
            y_top=self._y_top_spin.value(),
            display_labels=self._display_labels_map(),
        )

    def _populate_table(self, results):
        # Populated through self._table_model (QStandardItemModel) via
        # appendRow(), NOT QTableWidget's insertRow()/setItem() — kept as
        # a cleaner Model/View population path. The crash this table used
        # to hit on every repaint after getting real rows was actually a
        # dangling item delegate (see the setItemDelegateForColumn() /
        # parent=self._table comment in _build_right()), unrelated to how
        # rows are populated here.
        self._table.setSortingEnabled(False)
        self._table_model.setRowCount(0)

        for res in results:
            for rank, match in enumerate(res['matches'], start=1):
                reliable = match.get('reliable', True)
                grey     = QColor('#aaa')

                def _item(text, align=None, color=None):
                    it = QStandardItem(text)
                    it.setEditable(False)
                    if align: it.setTextAlignment(align)
                    if color: it.setForeground(color)
                    elif not reliable: it.setForeground(grey)
                    return it

                rank_color = QColor('#2E7D32') if (rank == 1 and reliable) else None
                sc = match['score']
                score_txt = f"{sc:.4f}" if not (
                    isinstance(sc, float) and sc != sc) else '—'
                # Negative = anti-correlated → show in red
                if isinstance(sc, float) and sc < 0:
                    sc_color = QColor('#C62828')
                elif rank == 1 and reliable:
                    sc_color = QColor('#2E7D32')
                else:
                    sc_color = None
                ov_txt = f"{match['overlap_pct']:.0f} %" if 'overlap_pct' in match else '—'
                ov_color = QColor('#C62828') if not reliable else None

                row_items = [
                    _item(res['label']),
                    _item(str(rank), Qt.AlignCenter, rank_color),
                    _item(match['ref_label']),
                    _item(score_txt, Qt.AlignRight | Qt.AlignVCenter, sc_color),
                    _item(ov_txt, Qt.AlignCenter, ov_color),
                ]
                self._table_model.appendRow(row_items)

        self._table.setSortingEnabled(True)

        n_q = len(results)
        metric = self.get_settings().get('metric', 'cosine')
        if self._rb_internal.isChecked():
            lib_info = f"from loaded spectra ({len(self._ref_list_widget.selectedItems())} references)"
        else:
            paths = self._settings.get("library_paths", ["?"])
            lib_info = paths[0] if paths else "?"
        text = (f'{n_q} spectra matched  |  metric: {metric}  |  '
               f'library: {lib_info}')

        # A query with an empty matches list here always means every
        # currently-selected reference IS that same query spectrum — see
        # _PreviewCanvas.plot's matching note for the full explanation.
        # Surfaced here too since the Results table itself would
        # otherwise just silently have no rows for that spectrum, with
        # no visible explanation of why.
        empty_labels = [r['label'] for r in results if not r['matches']]
        if empty_labels:
            names = ', '.join(empty_labels[:3])
            if len(empty_labels) > 3:
                names += f', +{len(empty_labels) - 3} more'
            text += (f'  |  ⚠ no matches for: {names} (a spectrum is never '
                    'matched against itself — select a different reference)')
            self._stats_label.setStyleSheet(
                'background-color:#FFF3E0; padding:6px; border-radius:4px; '
                'font-family:monospace;'
            )
        else:
            self._stats_label.setStyleSheet(
                'background-color:#E8F5E9; padding:6px; border-radius:4px; '
                'font-family:monospace;'
            )
        self._stats_label.setText(text)

    # ------------------------------------------------------------------ #
    # Export                                                               #
    # ------------------------------------------------------------------ #

    def _table_text(self, sep='\t'):
        model = self._table_model
        headers = [model.horizontalHeaderItem(c).text()
                   for c in range(model.columnCount())]
        lines = [sep.join(headers)]
        for r in range(model.rowCount()):
            row = []
            for c in range(model.columnCount()):
                item = model.item(r, c)
                row.append(item.text() if item else '')
            lines.append(sep.join(row))
        return '\n'.join(lines)

    def _copy_table(self):
        QApplication.clipboard().setText(self._table_text('\t'))

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export results', 'reference_matching_results.csv',
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
            QMessageBox.information(self, 'Nothing to Export', 'No match results to export yet.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export PDF Report', 'reference_matching_report.pdf',
                                              'PDF files (*.pdf)')
        if not path:
            return
        settings = self.get_settings()
        meta = [
            f"Metric: {settings.get('metric', '')}",
            f"Normalization: {settings.get('normalization', '')}",
            f"Top N matches: {settings.get('top_n', '')}",
            f"Minimum overlap: {settings.get('min_overlap_pct', '')}%",
            f"Library: {'External file' if settings.get('lib_mode') == 'external' else 'Internal spectra'}",
        ]
        model = self._table_model
        headers = [model.horizontalHeaderItem(c).text() for c in range(model.columnCount())]
        rows = []
        for r in range(model.rowCount()):
            rows.append([model.item(r, c).text() if model.item(r, c) else ''
                        for c in range(model.columnCount())])
        labels = [s.get('label', '') for s in self.selected_spectra]

        try:
            from src.modules.utils.pdf_report_utils import export_report_pdf
            export_report_pdf(path, 'Reference Library Matching', meta_lines=meta,
                              figure=self._scores_canvas._fig, table_headers=headers, table_rows=rows,
                              source_labels=labels)
        except Exception as exc:
            QMessageBox.warning(self, 'Export failed', str(exc))

    # ------------------------------------------------------------------ #
    # Settings I/O                                                         #
    # ------------------------------------------------------------------ #

    def _restore_settings(self, s):
        if 'metric' in s:
            idx = self._metric_combo.findText(s['metric'])
            if idx >= 0: self._metric_combo.setCurrentIndex(idx)
        if 'top_n' in s:
            self._topn_spin.setValue(int(s['top_n']))
        if 'normalization' in s:
            idx = self._norm_combo.findText(s['normalization'])
            if idx >= 0: self._norm_combo.setCurrentIndex(idx)
        if 'min_overlap_pct' in s:
            self._overlap_spin.setValue(float(s['min_overlap_pct']))
        if 'preview_max_subplots' in s:
            self._preview_max_subplots_spin.setValue(int(s['preview_max_subplots']))

        # Restore library mode (must be done before restoring file library)
        if s.get('lib_mode') == 'external':
            self._rb_external.setChecked(True)
        else:
            self._rb_internal.setChecked(True)

        # Restore file library if paths are saved
        if s.get('library_paths'):
            paths = s['library_paths']
            from src.modules.visualization_analysis.reference_matching_manager import (
                ReferenceMatchingManager)
            try:
                _mgr = ReferenceMatchingManager()
                n = _mgr.load_library(paths)
                self._file_library = list(_mgr._library)
                self._lib_summary.setText(
                    f'{n} reference spectra auto-loaded from {len(paths)} file(s).')
                self._lib_summary.setStyleSheet('font-size:8pt; color:#2E7D32;')
                self._file_ref_list.clear()
                self._file_ref_list.blockSignals(True)
                for entry in self._file_library:
                    item = QListWidgetItem(entry['label'])
                    self._file_ref_list.addItem(item)
                saved_sel = set(s.get('file_ref_selected', []))
                for i in range(self._file_ref_list.count()):
                    it = self._file_ref_list.item(i)
                    # If no saved selection, select all; otherwise restore saved
                    it.setSelected(it.text() in saved_sel if saved_sel else True)
                self._file_ref_list.blockSignals(False)
            except Exception:
                self._lib_summary.setText(
                    f'Last session: {len(paths)} file(s) — click Load to refresh.')
                self._lib_summary.setStyleSheet('font-size:8pt; color:#E65100;')

        # Restore reference list selection (internal mode). Saved sets are
        # keyed by spectrum_key() (unique_id) so a rename between saving
        # and restoring the dialog doesn't break the match — see
        # get_settings below. item.text() is also checked, for backward
        # compatibility with sessions saved before this fix, where
        # ref_selected/query_selected held plain label text.
        if s.get('ref_selected'):
            sel = set(s['ref_selected'])
            self._ref_list_widget.blockSignals(True)
            for i in range(self._ref_list_widget.count()):
                item = self._ref_list_widget.item(i)
                item.setSelected(item.data(Qt.UserRole) in sel or item.text() in sel)
            self._ref_list_widget.blockSignals(False)
            self._on_library_changed()

        # Restore query spectra selection
        if s.get('query_selected'):
            sel = set(s['query_selected'])
            self._list.blockSignals(True)
            for i in range(self._list.count()):
                item = self._list.item(i)
                item.setSelected(item.data(Qt.UserRole) in sel or item.text() in sel)
            self._list.blockSignals(False)

    def get_settings(self) -> dict:
        s = dict(self._settings)
        s['metric']          = self._metric_combo.currentText()
        s['top_n']           = self._topn_spin.value()
        s['normalization']   = self._norm_combo.currentText()
        s['min_overlap_pct'] = self._overlap_spin.value()
        s['preview_max_subplots'] = self._preview_max_subplots_spin.value()
        s['lib_mode']        = 'external' if self._rb_external.isChecked() else 'internal'
        # Save reference library selection (internal mode) — keyed by
        # unique_id (Qt.UserRole), not label text, so a later rename
        # doesn't detach the saved selection from its spectrum. See
        # CustomPlotPropertiesManager's class docstring / the Golden Rule
        # in developer_guide_help.py for the same pattern elsewhere.
        s['ref_selected']    = [item.data(Qt.UserRole)
                                 for item in self._ref_list_widget.selectedItems()]
        # Save file reference list selection
        s['file_ref_selected'] = [self._file_ref_list.item(i).text()
                                   for i in range(self._file_ref_list.count())
                                   if self._file_ref_list.item(i).isSelected()]
        # Save query spectra selection — unique_id, same reasoning as
        # ref_selected above.
        s['query_selected']  = [self._list.item(i).data(Qt.UserRole)
                                 for i in range(self._list.count())
                                 if self._list.item(i).isSelected()]
        return s

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def _save_and_close(self):
        """Save current settings and close with Accepted so caller persists them."""
        self.accept()

    def closeEvent(self, event):
        """Always save settings when dialog is closed (including X button)."""
        self.accept()
        event.accept()

    def _show_help(self):
        try:
            from src.help.reference_matching_help import (
                get_reference_matching_help_content,
                get_reference_matching_help_title,
            )
            from src.help.help_window import show_help_window
            show_help_window(self, get_reference_matching_help_title(),
                             get_reference_matching_help_content())
        except Exception:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Help',
                                    'Help documentation is not available.')


# ======================================================================
# Preview canvas
# ======================================================================

_COLORS = ['#1f77b4','#d62728','#2ca02c','#ff7f0e','#9467bd']


class _PreviewCanvas(FigureCanvas):
    """Query spectrum vs top-N reference matches."""

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        self._ax  = self._fig.add_subplot(111)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#ffffff')
        self._ax.set_facecolor('#ffffff')

    def _ensure_single_axes(self):
        """Rebuild a single axes if the figure isn't already in that exact
        state. A previous call may have been plot_multi(), which calls
        self._fig.clear() and builds a fresh grid of axes — that destroys
        the original self._ax object entirely, leaving it a stale
        reference no longer attached to this figure. Drawing onto a
        detached axes doesn't raise an error, but nothing visibly
        changes: the figure silently keeps showing whatever plot_multi()
        last drew, while the caller quietly "succeeds" drawing onto an
        axes nobody can see. Used by both plot() and show_no_selection()
        so this can't be forgotten in one and not the other."""
        if len(self._fig.axes) != 1 or self._ax not in self._fig.axes:
            self._fig.clear()
            self._ax = self._fig.add_subplot(111)
            self._ax.set_facecolor('#ffffff')

    def show_no_selection(self):
        """Empty state for when no query spectrum is currently selected
        in the Query spectra list — used instead of continuing to show
        whatever was last previewed, which could be a spectrum that's no
        longer part of the selection at all (see _on_item_clicked)."""
        self._ensure_single_axes()
        ax = self._ax
        ax.clear()
        ax.set_facecolor('#ffffff')
        ax.text(0.5, 0.5, 'No query spectrum selected.\nClick a spectrum '
                'in the Query spectra list to preview it.',
                ha='center', va='center', transform=ax.transAxes,
                fontsize=10, color='#666')
        ax.set_xticks([])
        ax.set_yticks([])
        self.draw_idle()

    @staticmethod
    def _draw_query_and_matches(ax, query_spectrum, matches, normalization, display_labels=None):
        """Draw one query spectrum plus its top-N match overlays onto
        *ax*. Shared by plot() (single query) and plot_multi() (grid, one
        subplot per query) so this logic — including the "never draw
        fabricated overlap data" rule — lives in exactly one place rather
        than being duplicated per rendering mode.

        display_labels: optional {full_label: display_label} map (see
        label_shortening.py) — legend text only, mirrors the main
        window's "shorten names" checkbox. query_spectrum/matches
        themselves are untouched."""
        display_labels = display_labels or {}
        ax.set_facecolor('#ffffff')
        x = np.asarray(query_spectrum.get('x_scale', []), dtype=float)
        y = np.asarray(query_spectrum.get('y_scale', []), dtype=float)
        if not len(x):
            return

        from src.modules.visualization_analysis.reference_matching_manager import (
            ReferenceMatchingManager)
        mgr_cls = ReferenceMatchingManager
        y_plot = mgr_cls._normalize(x, y, normalization)
        query_label = query_spectrum.get("label", "?")
        query_label = display_labels.get(query_label, query_label)
        ax.plot(x, y_plot, color='#111', lw=1.2, alpha=0.9, zorder=5,
                label=f'Query: {query_label}')

        for i, match in enumerate(matches):
            x_ov = match.get('x_overlap')
            y_ref_ov = match.get('y_ref_overlap')
            if x_ov is None or y_ref_ov is None or len(x_ov) < 2:
                # No genuine overlap to show — see plot()'s original note:
                # never draw fabricated flat-extrapolated data here.
                continue
            color = _MATCH_COLORS[i % len(_MATCH_COLORS)]
            score = match['score']
            score_txt = f'{score:.3f}' if not (isinstance(score, float) and score != score) else '\u2014'
            y_ref_plot = mgr_cls._normalize(x_ov, y_ref_ov, normalization)
            ref_label = match["ref_label"]
            ref_label = display_labels.get(ref_label, ref_label)
            ax.plot(x_ov, y_ref_plot, color=color, lw=0.9, alpha=0.75,
                    ls='--', zorder=4,
                    label=f'#{i+1} {ref_label}  ({score_txt})')

    def plot(self, query_spectrum, matches, normalization='none', display_labels=None):
        self._ensure_single_axes()
        ax = self._ax
        ax.clear()
        self._draw_query_and_matches(ax, query_spectrum, matches, normalization, display_labels)
        ax.set_xlabel('x', fontsize=9)
        ax.set_ylabel('Intensity', fontsize=9)
        ax.set_title(f'Top {len(matches)} matches', fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.35)
        ax.legend(fontsize=7, loc='best', framealpha=0.7)
        if not matches:
            # The only way this dialog's manager ever returns an empty
            # matches list for a query that actually HAS a library to
            # compare against (a missing library entirely is caught
            # earlier, in _build_manager/_compute_results, with its own
            # "No reference library defined" message) is that every
            # currently-selected reference IS this same query spectrum —
            # matching a spectrum against itself is always excluded (see
            # ReferenceMatchingManager.match's source_key check), since a
            # spectrum trivially "matches" itself perfectly and that
            # isn't a meaningful comparison. Spelling this out here
            # avoids a bare, unexplained "Top 0 matches" title with an
            # otherwise-empty plot.
            ax.text(0.5, 0.06,
                    'No matches: every selected reference is this same spectrum.\n'
                    'A spectrum is never matched against itself — select at least\n'
                    'one different reference spectrum.',
                    ha='center', va='bottom', transform=ax.transAxes,
                    fontsize=8, color='#C62828',
                    bbox=dict(boxstyle='round', facecolor='#FFEBEE', edgecolor='#C62828', alpha=0.9))
        self._fig.tight_layout()
        self.draw_idle()

    def plot_multi(self, pairs, n_total, max_subplots, normalization='none', display_labels=None):
        """One subplot per query spectrum — used when more than one query
        spectrum is selected in the Query spectra list. Previously the
        Preview tab only ever showed a single query (whichever was last
        clicked/current), silently ignoring the rest of the selection with
        no indication anything was being left out — confusing when the
        Results tab clearly shows every selected query has its own row.

        Args:
            pairs: list of (query_spectrum, matches) tuples, already
                limited by the caller to at most max_subplots entries —
                this method only draws what it's given.
            n_total: how many query spectra are ACTUALLY selected right
                now (before the max_subplots cap) — used only to word the
                "showing N of M" note when the cap is active.
            max_subplots: the configured cap — used only for that note.
        """
        self._fig.clear()
        if not pairs:
            self.draw_idle()
            return

        n = len(pairs)
        axes = self._fig.subplots(n, 1, sharex=True, squeeze=False)

        for i, (query_spectrum, matches) in enumerate(pairs):
            ax = axes[i][0]
            self._draw_query_and_matches(ax, query_spectrum, matches, normalization, display_labels)
            ax.set_ylabel('Intensity', fontsize=7)
            ax.tick_params(labelsize=7)
            ax.grid(True, linestyle='--', alpha=0.3)
            ax.legend(fontsize=6, loc='upper right', framealpha=0.7)

        axes[-1][0].set_xlabel('x', fontsize=8)

        if n_total > max_subplots:
            self._fig.suptitle(
                f'Showing {max_subplots} of {n_total} selected query spectra '
                f'\u2014 increase Max subplots (Query spectra panel) to see the rest.',
                fontsize=8, color='#C62828')
        else:
            self._fig.suptitle(f'{n_total} query spectra', fontsize=8, color='#555')

        try:
            self._fig.tight_layout(rect=[0, 0, 1, 0.96])
        except Exception:
            pass
        self.draw_idle()

def _get_match_color(rank_idx, top_n, palette='default'):
    """Return colour for rank rank_idx (0-based) given top_n total matches."""
    if palette == 'default':
        return _MATCH_COLORS[rank_idx % len(_MATCH_COLORS)]
    import matplotlib.pyplot as plt
    try:
        cmap = plt.get_cmap(palette)
        n = max(top_n, 1)
        t = rank_idx / n if n > 1 else 0.5
        rgba = cmap(t)
        return '#{:02x}{:02x}{:02x}'.format(
            int(rgba[0]*255), int(rgba[1]*255), int(rgba[2]*255))
    except Exception:
        return _MATCH_COLORS[rank_idx % len(_MATCH_COLORS)]


# ======================================================================
# Scores plot canvas
# ======================================================================

class _ScoresCanvas(FigureCanvas):
    """
    Bar chart: for each query spectrum show top-N match scores.
    One subplot per query spectrum (up to 20; truncated for performance).
    """

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#ffffff')

    def plot(self, results, settings, max_subplots=5,
             plot_type='Bar', label_rotation=45, label_chars=0,
             y_bottom=0.9, y_top=1.0, palette='default', display_labels=None):
        """display_labels: optional {full_label: display_label} map (see
        label_shortening.py) — applied ONLY to subplot titles and x-axis
        tick text below, never to all_ref_labels/ref_idx, which stay
        full-label-keyed since matches are looked up against them by
        m['ref_label'] (full)."""
        display_labels = display_labels or {}
        self._fig.clear()

        if not results:
            self.draw_idle()
            return

        shown   = results[:max_subplots]
        n_subs  = len(shown)
        if n_subs == 0:
            self.draw_idle()
            return

        def _fmt(lbl):
            return lbl[-label_chars:] if label_chars > 0 else lbl

        ha = 'right' if label_rotation > 0 else 'center'

        # Build union of all reference labels across shown queries (shared x-axis)
        all_ref_labels = []
        seen = set()
        for res in shown:
            for m in res['matches']:
                lbl = m['ref_label']
                if lbl not in seen:
                    all_ref_labels.append(lbl)
                    seen.add(lbl)

        x_pos   = np.arange(len(all_ref_labels))
        ref_idx = {lbl: i for i, lbl in enumerate(all_ref_labels)}
        top_n   = int(settings.get('top_n', 5))

        axes = self._fig.subplots(n_subs, 1, sharex=True, squeeze=False)

        for i, res in enumerate(shown):
            ax = axes[i][0]
            ax.set_facecolor('#ffffff')
            matches    = [m for m in res['matches'] if m.get('reliable', True)]
            scores     = np.full(len(all_ref_labels), np.nan)
            colors_arr = ['#cccccc'] * len(all_ref_labels)
            for j, m in enumerate(matches):
                idx_r = ref_idx.get(m['ref_label'], -1)
                if idx_r >= 0:
                    sc = m['score']
                    scores[idx_r] = sc if not (isinstance(sc, float) and sc != sc) else np.nan
                    colors_arr[idx_r] = _get_match_color(j, top_n, palette)

            # Plot NaN as a short grey bar (y_bottom + small delta) to be visible
            delta = max(0.005, (y_top - y_bottom) * 0.05)
            scores_plot = np.where(np.isnan(scores), y_bottom + delta, scores)
            colors_plot = [('#bbbbbb' if np.isnan(scores[k]) else colors_arr[k])
                           for k in range(len(scores))]

            if plot_type in ('Bar', 'Bar + Line'):
                ax.bar(x_pos, scores_plot, color=colors_plot, alpha=0.72, width=0.6)
            if plot_type in ('Line', 'Bar + Line', 'Scatter'):
                mk = 'o'
                ls = '-' if plot_type != 'Scatter' else 'None'
                lw = 1.2 if plot_type != 'Scatter' else 0
                valid = ~np.isnan(scores)
                ax.plot(x_pos[valid], scores_plot[valid], color='#333', lw=lw,
                        marker=mk, markersize=4, ls=ls, alpha=0.85)

            valid_scores = scores[~np.isnan(scores)]
            y_max = float(np.max(valid_scores)) if len(valid_scores) else 1.0
            ax.set_ylim(y_bottom, y_top)
            ax.set_ylabel('Score', fontsize=7)
            res_label = display_labels.get(res['label'], res['label'])
            ax.set_title(res_label, fontsize=8, loc='left', pad=2)
            ax.grid(True, axis='y', linestyle='--', alpha=0.35)
            ax.tick_params(labelsize=7)

        # X-axis labels only on the bottom subplot (shared x-axis)
        ax_bottom = axes[-1][0]
        ax_bottom.set_xticks(x_pos)
        ax_bottom.set_xticklabels(
            [_fmt(display_labels.get(l, l)) for l in all_ref_labels],
            rotation=label_rotation, ha=ha, fontsize=7)



        if len(results) > max_subplots:
            self._fig.text(0.5, 0.002,
                f'Showing {n_subs} of {len(results)} query spectra '
                f'— increase Max subplots to see more',
                ha='center', fontsize=7, color='#888')

        self._fig.tight_layout()
        self.draw_idle()