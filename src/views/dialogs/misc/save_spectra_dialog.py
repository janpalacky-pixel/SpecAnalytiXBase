# src/views/dialogs/misc/save_spectra_dialog.py

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QGroupBox, QRadioButton, QCheckBox, QComboBox,
    QLabel, QPushButton, QButtonGroup, QMessageBox, QWidget,
)

from src.help.help_window import open_help_topic


class SaveOptionsDialog(QDialog):
    def __init__(self, parent=None, allow_snapshot=True):
        super().__init__(parent)
        self.setWindowTitle("Save Options")
        self._setup_ui()
        if not allow_snapshot:
            # Snapshot saves the ENTIRE application state, not a specific
            # spectra list — offering it here (e.g. when saving SVD
            # Interpolation's preview spectra) would silently save the
            # whole main workspace instead of what the user actually
            # asked to save, which is misleading, so it's just not an
            # option in this context.
            self.fmt_snapshot.setVisible(False)
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- file format ---------------------------------------------------
        fmt_group = QGroupBox("File Format")
        fmt_layout = QHBoxLayout()
        self.fmt_text     = QRadioButton("Text")
        self.fmt_excel    = QRadioButton("Excel")
        self.fmt_spc      = QRadioButton("GRAMS (.spc)")
        self.fmt_snapshot = QRadioButton("Snapshot")
        self.fmt_text.setChecked(True)
        for w in (self.fmt_text, self.fmt_excel, self.fmt_spc, self.fmt_snapshot):
            fmt_layout.addWidget(w)
        fmt_group.setLayout(fmt_layout)
        layout.addWidget(fmt_group)

        # --- save mode -----------------------------------------------------
        self.mode_group = QGroupBox("Save Mode")
        mode_layout = QHBoxLayout()
        self.mode_table      = QRadioButton("Save as Table")
        self.mode_individual = QRadioButton("Save Individual Files")
        self.mode_table.setChecked(True)
        for w in (self.mode_table, self.mode_individual):
            mode_layout.addWidget(w)
        self.mode_group.setLayout(mode_layout)
        layout.addWidget(self.mode_group)

        # --- x-scale -------------------------------------------------------
        self.scale_group = QGroupBox("X-scale")
        scale_layout = QHBoxLayout()
        self.use_common_scale = QCheckBox("Use common x-scale (all spectra must share the same grid)")
        scale_layout.addWidget(self.use_common_scale)
        self.scale_group.setLayout(scale_layout)
        layout.addWidget(self.scale_group)

        # Info label shown for GRAMS (.spc) — its "common x-scale" isn't a
        # user choice the way it is for Text/Excel: a single .spc file's
        # subfiles always share one x-axis by construction (see
        # spc_data_writer's module docstring), so the checkbox above gets
        # forced on and disabled for this format rather than offering a
        # combination the writer can't actually produce.
        self.spc_info = QLabel(
            "ℹ  GRAMS (.spc) files always share one x-axis across every "
            "spectrum in the file — this isn't optional for this format.\n"
            "   Spectra with different x-scales: use \"Save Individual "
            "Files\" instead, one .spc file per spectrum."
        )
        self.spc_info.setWordWrap(True)
        self.spc_info.setStyleSheet(
            "color: #7a5c00; background: #fff8dc; "
            "padding: 6px; border-radius: 4px; font-size: 9pt;"
        )
        self.spc_info.setVisible(False)
        layout.addWidget(self.spc_info)

        # Info label shown when individual scales are selected
        self.interlaced_info = QLabel(
            "ℹ  Individual-scale files use an interlaced layout (x₁, y₁, x₂, y₂ …).\n"
            "   To re-import them, enable \"Interlaced Format\" in Import Settings."
        )
        self.interlaced_info.setWordWrap(True)
        self.interlaced_info.setStyleSheet(
            "color: #7a5c00; background: #fff8dc; "
            "padding: 6px; border-radius: 4px; font-size: 9pt;"
        )
        self.interlaced_info.setVisible(False)
        layout.addWidget(self.interlaced_info)

        # --- layout (columns / rows) ----------------------------------------
        # Only meaningful with a common x-scale — Row layout needs one
        # shared X-axis to move into the header row; Individual-scale
        # files (interlaced) have no single shared axis, so this stays
        # column-only for that combination.
        self.layout_group = QGroupBox("Layout")
        layout_layout = QHBoxLayout()
        self.layout_columns = QRadioButton("Columns  (spectra in columns)")
        self.layout_rows    = QRadioButton("Rows  (spectra in rows)")
        self.layout_columns.setChecked(True)
        self.layout_columns.setToolTip(
            "Default. First column is the shared X-scale; every other "
            "column is one spectrum."
        )
        self.layout_rows.setToolTip(
            "First row is the shared X-scale; every other row is one "
            "spectrum. To re-import, select 'Row-oriented' layout in "
            "Import Settings — no other setting is needed."
        )
        self._layout_btn_group = QButtonGroup(self)
        for w in (self.layout_columns, self.layout_rows):
            self._layout_btn_group.addButton(w)
            layout_layout.addWidget(w)

        layout_layout.addStretch()
        self._layout_help_btn = QPushButton("?")
        self._layout_help_btn.setFixedWidth(24)
        self._layout_help_btn.setToolTip(
            "Why is this only available with 'Use common x-scale'?"
        )
        self._layout_help_btn.setStyleSheet(
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
        self._layout_help_btn.clicked.connect(self._show_layout_help)
        layout_layout.addWidget(self._layout_help_btn)

        self.layout_group.setLayout(layout_layout)
        layout.addWidget(self.layout_group)

        self.row_layout_info = QLabel(
            "ℹ  Rows layout: spectra become rows, sharing the X-scale in the header row.\n"
            "   To re-import, select \"Row-oriented\" in Import Settings — Layout."
        )
        self.row_layout_info.setWordWrap(True)
        self.row_layout_info.setStyleSheet(
            "color: #7a5c00; background: #fff8dc; "
            "padding: 6px; border-radius: 4px; font-size: 9pt;"
        )
        self.row_layout_info.setVisible(False)
        layout.addWidget(self.row_layout_info)

        # --- options -------------------------------------------------------
        opts_group = QGroupBox("Options")
        opts_layout = QVBoxLayout()

        self.use_labels = QCheckBox("Include column labels (header row)")
        opts_layout.addWidget(self.use_labels)

        sep_row = QHBoxLayout()
        sep_row.addWidget(QLabel("Value separator:"))
        self.value_separator = QComboBox()
        self.value_separator.addItems(["\t", ";", ",", " "])
        self.value_separator.setItemText(0, "tab")
        sep_row.addWidget(self.value_separator)
        opts_layout.addLayout(sep_row)

        dec_row = QHBoxLayout()
        dec_row.addWidget(QLabel("Decimal separator:"))
        self.decimal_separator = QComboBox()
        self.decimal_separator.addItems([".", ","])
        dec_row.addWidget(self.decimal_separator)
        opts_layout.addLayout(dec_row)

        # Snapshot info
        self.snapshot_info = QLabel(
            "Snapshot saves the complete application state including all "
            "operations, selections and plot settings."
        )
        self.snapshot_info.setWordWrap(True)
        self.snapshot_info.setStyleSheet("color: #555; font-style: italic; font-size: 9pt;")
        self.snapshot_info.setVisible(False)
        opts_layout.addWidget(self.snapshot_info)

        # Snapshot compression -- a few named presets rather than exposing
        # gzip's raw 1-9 level directly, which means nothing without
        # documentation. Wrapped in its own QWidget (not just a bare
        # QHBoxLayout) so the whole row can be shown/hidden as a unit via
        # setVisible() in _refresh(), the same way self.snapshot_info is --
        # a bare layout has no setVisible of its own.
        self.compression_row = QWidget()
        comp_row_layout = QHBoxLayout()
        comp_row_layout.setContentsMargins(0, 0, 0, 0)
        comp_row_layout.addWidget(QLabel("Compression:"))
        self.compression_level = QComboBox()
        self.compression_level.addItems(["Fast", "Balanced (default)", "Maximum"])
        self.compression_level.setCurrentIndex(1)  # Balanced -- matches
        # SaveManager.SNAPSHOT_GZIP_LEVEL's own default (gzip level 6)
        self.compression_level.setToolTip(
            "How hard to compress the .snapx file. Fast = quicker save, "
            "larger file. Maximum = smaller file, slower save (can be "
            "noticeably slower for a large workspace). Balanced is a good "
            "default for most sessions."
        )
        comp_row_layout.addWidget(self.compression_level)
        comp_row_layout.addStretch()
        self.compression_row.setLayout(comp_row_layout)
        self.compression_row.setVisible(False)
        opts_layout.addWidget(self.compression_row)

        opts_group.setLayout(opts_layout)
        layout.addWidget(opts_group)

        # --- buttons -------------------------------------------------------
        btn_layout = QHBoxLayout()
        self._help_btn = QPushButton("Help")
        self._help_btn.clicked.connect(self._show_help)
        btn_layout.addWidget(self._help_btn)
        btn_layout.addStretch()
        self.save_btn   = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")
        self.save_btn.setDefault(True)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self.fmt_text.toggled.connect(self._refresh)
        self.fmt_excel.toggled.connect(self._refresh)
        self.fmt_spc.toggled.connect(self._refresh)
        self.fmt_snapshot.toggled.connect(self._refresh)
        self.mode_table.toggled.connect(self._refresh)
        self.use_common_scale.toggled.connect(self._refresh)
        self.layout_columns.toggled.connect(self._refresh)
        self.layout_rows.toggled.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        """Enable / disable widgets depending on the current selections."""
        is_snapshot = self.fmt_snapshot.isChecked()
        is_text     = self.fmt_text.isChecked()
        is_spc      = self.fmt_spc.isChecked()
        is_table    = self.mode_table.isChecked()

        # GRAMS (.spc): a common x-scale isn't a choice, it's mandatory
        # for Table mode (one file, subfiles sharing one axis) — force the
        # checkbox on and lock it before reading is_common, rather than
        # letting the user uncheck something the writer can't honour.
        if is_spc and is_table:
            self.use_common_scale.setChecked(True)
        is_common = self.use_common_scale.isChecked()

        self.mode_group.setEnabled(not is_snapshot)
        self.scale_group.setEnabled(not is_snapshot and is_table and not is_spc)
        self.use_labels.setEnabled(not is_snapshot and not is_spc)
        self.value_separator.setEnabled(not is_snapshot and is_text)
        self.decimal_separator.setEnabled(not is_snapshot and is_text)
        self.snapshot_info.setVisible(is_snapshot)
        self.compression_row.setVisible(is_snapshot)
        self.spc_info.setVisible(is_spc and is_table)

        show_interlaced_hint = (
            is_text
            and is_table
            and not is_common
        )
        self.interlaced_info.setVisible(show_interlaced_hint)

        # Layout (Columns/Rows) is only meaningful for a table save with a
        # common x-scale in the pandas-based text/Excel writer — GRAMS
        # (.spc) is a binary format with its own fixed subfile layout, no
        # columns/rows choice applies. Individual-scale (interlaced) has
        # no single shared axis to put in a header row, and it's not
        # offered for Save Individual Files (each file is only one
        # spectrum already). Hidden entirely (not just greyed out) when
        # irrelevant, same pattern as the Import dialog's Layout-dependent
        # column pickers.
        self._layout_relevant = not is_snapshot and not is_spc and is_table and is_common
        self.layout_group.setVisible(self._layout_relevant)
        if not self._layout_relevant:
            self.layout_columns.setChecked(True)
        self.row_layout_info.setVisible(self._layout_relevant and self.layout_rows.isChecked())

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def _show_help(self):
        open_help_topic(self, 'save')

    def _show_layout_help(self):
        QMessageBox.information(
            self,
            "About Layout",
            "Layout (Columns/Rows) is only available when 'Use common "
            "x-scale' is checked.\n\n"
            "Rows layout needs one shared X-axis to move into the header "
            "row when spectra become rows. Individual x-scales (each "
            "spectrum on its own grid) has no single shared axis to use "
            "that way, so it stays column-only."
        )

    # ------------------------------------------------------------------
    # Settings extraction
    # ------------------------------------------------------------------

    # Display text -> gzip compresslevel. "Balanced" matches
    # SaveManager.SNAPSHOT_GZIP_LEVEL's own default (6) exactly, so
    # leaving this combo untouched behaves identically to before this
    # control existed.
    _COMPRESSION_PRESETS = {
        "Fast": 1,
        "Balanced (default)": 6,
        "Maximum": 9,
    }

    def get_settings(self) -> dict:
        sep_display = self.value_separator.currentText()
        sep_map = {'tab': '\t', ';': ';', ',': ',', ' ': ' '}
        value_sep = sep_map.get(sep_display, sep_display)

        return {
            'format': (
                'snapshot' if self.fmt_snapshot.isChecked() else
                'excel'    if self.fmt_excel.isChecked()    else
                'spc'      if self.fmt_spc.isChecked()      else
                'text'
            ),
            'mode':              'table' if self.mode_table.isChecked() else 'individual',
            'use_common_scale':  self.use_common_scale.isChecked(),
            'save_layout':       'rows' if (self._layout_relevant and self.layout_rows.isChecked()) else 'columns',
            'use_labels':        self.use_labels.isChecked(),
            'value_separator':   value_sep,
            'decimal_separator': self.decimal_separator.currentText(),
            'compression_level': self._COMPRESSION_PRESETS.get(
                self.compression_level.currentText(), 6),
        }
