# src/views/dialogs/misc/import_dialog.py
#
# Combined import dialog: settings + live file preview in one place.
#
# Flow
# ----
# 1. ImportController calls ImportDialog.get_file_paths_and_settings()
#    which opens the OS file-picker first.
# 2. If the user selected files, the dialog opens with auto-detected
#    settings pre-filled and a preview of the first file.
# 3. Changing any control reruns the preview immediately.
# 4. The user clicks "Import" (accept) or "Cancel" (reject).
# 5. ImportController reads dialog.get_settings() and proceeds.

import os
import re
from typing import Optional, List

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QComboBox, QSpinBox,
    QCheckBox, QPushButton, QTableWidget, QTableWidgetItem,
    QFileDialog, QSizePolicy, QHeaderView,
    QRadioButton, QButtonGroup, QListWidget, QListWidgetItem,
    QMessageBox, QInputDialog, QWidget,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from src.help.help_window import open_help_topic
from src.modules.misc.import_profile_manager import ImportProfileManager


# ---------------------------------------------------------------------------
# Helpers (pure functions, no Qt dependency)
# ---------------------------------------------------------------------------

def _read_sample(filepath: str, n_lines: int = 8, sheet_name: Optional[str] = None) -> list:
    """
    Read up to *n_lines* non-blank lines from *filepath*.
    For Excel files, reads rows from *sheet_name* (or the auto-selected
    sheet if None) instead.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.xlsx', '.xls', '.xlsm'):
        return _read_excel_sample(filepath, n_lines, sheet_name)

    lines = []
    for encoding in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            with open(filepath, 'r', encoding=encoding) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        if line.startswith('\ufeff'):
                            line = line[1:]
                        lines.append(line)
                        if len(lines) >= n_lines:
                            break
            break
        except UnicodeDecodeError:
            continue
    return lines


def _list_excel_sheets(filepath: str) -> list:
    """Return the list of sheet names in an Excel workbook, or [] on failure."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        names = list(wb.sheetnames)
        wb.close()
        return names
    except Exception:
        return []


def _read_excel_sample(filepath: str, n_lines: int = 8, sheet_name: Optional[str] = None) -> list:
    """Read up to *n_lines* rows from an Excel file as tab-separated strings."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        if sheet_name and sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
        elif 'spectra' in wb.sheetnames:
            ws = wb['spectra']
        else:
            ws = wb.active
        lines = []
        for row in ws.iter_rows(values_only=True):
            tokens = []
            for cell in row:
                if cell is None:
                    tokens.append('')
                elif isinstance(cell, float):
                    tokens.append(repr(cell))
                elif isinstance(cell, int):
                    tokens.append(str(cell))
                else:
                    tokens.append(str(cell).strip())
            while tokens and tokens[-1] == '':
                tokens.pop()
            if tokens:
                lines.append('\t'.join(tokens))
                if len(lines) >= n_lines:
                    break
        wb.close()
        return lines
    except Exception:
        return []


def _split_line(line: str, delimiter: str) -> list:
    if delimiter == r'\s+':
        return [t for t in line.split() if t]
    return [t.strip() for t in line.split(delimiter)]


def _autodetect_delimiter(lines: list) -> str:
    """Same logic as table_data_converter._detect_delimiter."""
    if not lines:
        return r'\s+'
    non_empty = [l for l in lines if l.strip()]

    # Tab: check column-count consistency, and require a real majority of
    # lines to actually contain a tab (see table_data_converter._detect_delimiter
    # for why: a single stray tab character shouldn't hijack detection).
    tab_counts = [len(l.split('\t')) for l in non_empty]
    lines_with_tab = sum(1 for c in tab_counts if c > 1)
    if (tab_counts and max(tab_counts) > 1 and len(set(tab_counts)) <= 2
            and lines_with_tab >= max(1, len(non_empty) * 0.5)):
        return '\t'

    def _consistent(d):
        counts = [l.count(d) for l in non_empty]
        return bool(counts) and max(counts) > 0 and len(set(counts)) <= 2

    for d in (';', '|'):
        if _consistent(d):
            return d

    # Comma: only if not decimal
    if non_empty and non_empty[0].count(',') > 0:
        dec_comma = sum(len(re.findall(r'\d,\d', l)) for l in non_empty)
        del_comma = sum(l.count(',') for l in non_empty) - dec_comma
        if _consistent(',') and del_comma > dec_comma:
            return ','

    # Whitespace
    first_n = len(non_empty[0].split()) if non_empty else 0
    if first_n > 1 and all(
        len(l.split()) == first_n for l in non_empty[:5] if l.strip()
    ):
        return r'\s+'

    return ','


def _autodetect_decimal(lines: list, delimiter: str) -> str:
    dots = commas = 0
    for line in lines[:10]:
        for part in _split_line(line, delimiter)[:10]:
            if re.search(r'\d\.\d', part):
                dots += 1
            if re.search(r'\d,\d', part):
                commas += 1
    return ',' if commas > dots else '.'


def _autodetect_header(lines: list, delimiter: str, decimal: str, threshold: float = 0.5) -> bool:
    if not lines:
        return False
    parts = _split_line(lines[0], delimiter)
    non_numeric = 0
    for p in parts:
        p = p.strip()
        if not p:
            continue
        try:
            test = re.sub(r'(\d),(\d)', r'\1.\2', p) if decimal == ',' else p
            float(test)
        except ValueError:
            non_numeric += 1
    return len(parts) > 0 and non_numeric >= len(parts) * threshold


# Display name ↔ internal value maps
_DELIM_TO_DISPLAY = {'\t': 'tab', ';': ';', ',': ',', '|': '|', r'\s+': 'space'}
_DISPLAY_TO_DELIM = {v: k for k, v in _DELIM_TO_DISPLAY.items()}
_DISPLAY_TO_DELIM['Auto'] = None


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class ImportDialog(QDialog):
    """
    Combined import-settings + preview dialog.

    Usage
    -----
        accepted, file_paths, settings = ImportDialog.run(parent, default_settings)
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, parent, file_paths: list, default_settings: dict):
        super().__init__(parent)
        self.setWindowTitle("Import Spectra")
        self.setMinimumWidth(680)
        self.setMinimumHeight(560)

        self._file_paths = file_paths          # already chosen by the OS picker
        self._default_settings = default_settings
        self._sample_lines = []                # raw lines from current file
        self._preview_file_index = 0

        # Per-file settings cache: {file_index: settings_dict}. Each file
        # remembers its own Layout/separator/column choices independently,
        # so flipping between files while reviewing a multi-file batch
        # never loses or overwrites another file's configuration. Populated
        # lazily — a file gets an entry the first time it's previewed.
        self._file_settings: dict = {}
        # Per-SHEET settings for a multi-sheet Excel import:
        #   {(file_index, sheet_name): settings_dict}
        # Sheets of one workbook are genuinely different tables — different
        # columns to exclude, possibly a different layout or header row — so they
        # each need their own settings, not one shared set.
        self._sheet_settings: dict = {}
        # Which sheet's settings the controls are currently showing/editing
        # (only meaningful while "Import several sheets" is ticked).
        # True while a sheet switch is in progress — see _on_sheet_list_selection.
        self._switching_sheet: bool = False
        # Per-SHEET settings for multi-sheet import, keyed by
        # (file_index, sheet_name). Different sheets are usually different
        # tables, so each keeps its own exclusions/layout/header row.
        self._sheet_settings: dict = {}
        self._current_multi_sheet = None

        # Named, disk-persisted settings profiles — survive across
        # sessions, unlike everything above (which only lasts this dialog).
        self._profile_manager = ImportProfileManager()

        # Safe defaults — overwritten immediately by _load_first_file()
        self._detected_delimiter  = '\t'
        self._detected_decimal    = '.'
        self._detected_header     = False

        self._build_ui()
        self._load_first_file()                # auto-detect + populate preview

    # ------------------------------------------------------------------
    # Class-level convenience
    # ------------------------------------------------------------------

    @classmethod
    def run(cls, parent, default_settings: dict, file_paths: Optional[list] = None) -> tuple:
        """
        Show the dialog for *file_paths*, or — if not given — open the OS
        file-picker first to obtain them (the normal File → Import path).
        Passing file_paths directly skips the picker entirely; used for
        drag-and-drop import, where the files are already known.

        Returns
        -------
        (accepted: bool, file_paths: list, settings_list: list[dict])
        settings_list has one entry per file_paths, in the same order —
        each file may have different settings if the user customized it
        individually while previewing.
        """
        if file_paths is None:
            file_paths, _ = QFileDialog.getOpenFileNames(
                parent,
                "Select Spectra Files",
                "",
                "All supported files (*.txt *.csv *.dat *.xlsx *.xls *.xlsm *.spe *.spc *.jws);;"
                "Text Files (*.txt *.csv *.dat);;"
                "Excel Files (*.xlsx *.xls *.xlsm);;"
                "SPE Files (*.spe);;"
                "SPC Files (*.spc);;"
                "JWS Files (*.jws);;"
                "All Files (*.*)",
            )
        if not file_paths:
            return False, [], []

        dlg = cls(parent, file_paths, default_settings)
        accepted = dlg.exec_() == QDialog.Accepted
        return accepted, file_paths, dlg.get_all_settings()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        n = len(self._file_paths)

        # Prominent "which file am I configuring right now" label — always
        # visible, single or multi-file, so it's unambiguous which file's
        # settings the controls below are currently showing/editing. The
        # "X of N" count already makes a separate "N files selected" label
        # redundant, so there isn't one.
        self._current_file_label = QLabel("")
        self._current_file_label.setWordWrap(True)
        self._current_file_label.setStyleSheet(
            "font-weight:bold; font-size:10pt; padding:2px 4px;"
        )
        root.addWidget(self._current_file_label)

        # Quick per-file actions, plus file-to-file navigation, all on one
        # row to save vertical space. Reset is always shown (even for a
        # single file, undoing manual tweaks is still useful); Apply and
        # the ◀ ▶ navigation arrows only appear when there's more than
        # one file.
        actions_row = QHBoxLayout()
        self._reset_auto_btn = QPushButton("Reset to Auto-detected")
        self._reset_auto_btn.setToolTip(
            "Discard any manual changes made to this file and re-run "
            "auto-detection fresh, as if it had never been previewed."
        )
        self._reset_auto_btn.clicked.connect(self._reset_current_file_to_auto)
        actions_row.addWidget(self._reset_auto_btn)

        if n > 1:
            self._apply_all_btn = QPushButton("Apply to All Other Files")
            self._apply_all_btn.setToolTip(
                "Copy this file's settings — Layout, separators, header, "
                "column pickers, everything — to every other file in this "
                "batch. Useful when many files share the same non-default "
                "format. Asks for confirmation first."
            )
            self._apply_all_btn.clicked.connect(self._apply_settings_to_all_files)
            actions_row.addWidget(self._apply_all_btn)

        actions_row.addStretch()

        if n > 1:
            self._prev_btn = QPushButton("◀")
            self._next_btn = QPushButton("▶")
            self._prev_btn.setFixedWidth(28)
            self._next_btn.setFixedWidth(28)
            self._prev_btn.clicked.connect(self._prev_file)
            self._next_btn.clicked.connect(self._next_file)
            actions_row.addWidget(self._prev_btn)
            actions_row.addWidget(self._next_btn)

        root.addLayout(actions_row)

        # Named, disk-persisted profiles — a full settings snapshot saved
        # under a name and reusable across files and application sessions,
        # for a recurring instrument export format you import repeatedly.
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Import profile:"))
        self._profile_combo = QComboBox()
        self._profile_combo.setToolTip(
            "Select a saved profile to apply its full settings — Layout, "
            "separators, header, every column picker — to the currently "
            "previewed file."
        )
        self._profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        profile_row.addWidget(self._profile_combo, stretch=1)

        self._save_profile_btn = QPushButton("Save Current as Profile…")
        self._save_profile_btn.setToolTip(
            "Save the currently-displayed file's settings under a name, "
            "so you can reapply them later — even in a future session."
        )
        self._save_profile_btn.clicked.connect(self._save_current_as_profile)
        profile_row.addWidget(self._save_profile_btn)

        self._delete_profile_btn = QPushButton("Delete")
        self._delete_profile_btn.setToolTip("Delete the selected profile.")
        self._delete_profile_btn.clicked.connect(self._delete_selected_profile)
        profile_row.addWidget(self._delete_profile_btn)

        root.addLayout(profile_row)
        self._populate_profile_combo()

        if n > 1:
            # Full file list — every selected file, one per row, so nothing
            # is ever hidden behind a "+N more" truncation. Click any row
            # to jump preview straight to that file. The currently-shown
            # file's row is kept selected/highlighted as you navigate via
            # the ◀ ▶ buttons too, so the list and the preview never
            # disagree about which file is active.
            self._file_list_widget = QListWidget()
            self._file_list_widget.setMaximumHeight(110)
            for p in self._file_paths:
                self._file_list_widget.addItem(os.path.basename(p))
            self._file_list_widget.currentRowChanged.connect(self._on_file_list_row_changed)
            root.addWidget(self._file_list_widget)

        # --- settings row -------------------------------------------------
        settings_row = QHBoxLayout()

        # Separators group
        self._sep_group = QGroupBox("Separators")
        sep_layout = QGridLayout()
        sep_layout.setVerticalSpacing(4)

        self._sheet_label = QLabel("Sheet:")
        self._sheet_label.setToolTip(
            "Excel files only. Which worksheet to read.\n\n"
            "Auto prefers a sheet named 'spectra' (the sheet this "
            "app's own Save function writes), otherwise the first sheet."
        )
        sep_layout.addWidget(self._sheet_label, 0, 0)

        # --- sheet picker + multi-sheet import ----------------------------
        # Everything sheet-related lives in ONE cell, laid out top-to-bottom:
        #
        #     [x] Import several sheets      <- always visible (Excel only)
        #     ( single-sheet dropdown )      <- when the box is unticked
        #     [ checkable list of sheets ]   <- when the box is ticked
        #
        # Earlier attempts put the checkbox in its own grid column (which left a
        # wide empty gap to the right) and then stacked the dropdown and the list
        # in a QStackedWidget (which always reserves room for the TALLER page, so
        # the unticked state showed a big empty box where the dropdown should be
        # — and the dropdown was hidden inside it anyway). A plain vertical box
        # with two mutually-exclusive widgets has neither problem: the cell is
        # exactly as tall as whatever is actually showing.
        self._sheet_box = QWidget()
        _sheet_v = QVBoxLayout(self._sheet_box)
        _sheet_v.setContentsMargins(0, 0, 0, 0)
        _sheet_v.setSpacing(4)

        self._multi_sheet_cb = QCheckBox("Import several sheets")
        self._multi_sheet_cb.setToolTip(
            "Excel files only.\n\n"
            "Off (default): read the single sheet chosen below.\n\n"
            "On: read every sheet you tick, in one import. Each sheet is read\n"
            "with the same settings, and its spectra are labelled\n"
            "'<file> [<sheet>] : <column>' so identically-named columns in\n"
            "different sheets stay distinct."
        )
        _sheet_v.addWidget(self._multi_sheet_cb)

        self._sheet_combo = QComboBox()
        self._sheet_combo.addItem("Auto (spectra / first sheet)")
        self._sheet_combo.setToolTip(self._sheet_label.toolTip())
        _sheet_v.addWidget(self._sheet_combo)

        self._sheet_list = QListWidget()
        self._sheet_list.setMaximumHeight(96)
        self._sheet_list.setSelectionMode(QListWidget.SingleSelection)
        self._sheet_list.setToolTip(self._multi_sheet_cb.toolTip())
        self._sheet_list.setVisible(False)
        _sheet_v.addWidget(self._sheet_list)

        # Click a sheet to configure it (see _on_sheet_list_selection); this
        # button instead broadcasts the sheet currently being configured to
        # every other sheet in the workbook, for the case where they
        # genuinely do share one non-default layout — the deliberate,
        # explicit counterpart to sheets otherwise defaulting back to Auto
        # on their own (see _apply_autodetect's reset_separators docstring).
        self._apply_all_sheets_btn = QPushButton("Apply to All Sheets")
        self._apply_all_sheets_btn.setToolTip(
            "Copy the sheet currently being configured — Layout, "
            "separators, header, column pickers, everything — to every "
            "other sheet in this workbook. Useful when several sheets "
            "share the same non-default format. Asks for confirmation "
            "first."
        )
        self._apply_all_sheets_btn.clicked.connect(self._apply_settings_to_all_sheets)
        self._apply_all_sheets_btn.setVisible(False)
        _sheet_v.addWidget(self._apply_all_sheets_btn)

        self._sheet_edit_label = QLabel("")
        self._sheet_edit_label.setStyleSheet(
            "color:#0D47A1; font-weight:bold; font-size:8pt; padding:1px;")
        self._sheet_edit_label.setVisible(False)
        _sheet_v.addWidget(self._sheet_edit_label)

        sep_layout.addWidget(self._sheet_box, 0, 1)
        self._sheet_label.setVisible(False)
        self._sheet_box.setVisible(False)

        sep_layout.addWidget(QLabel("Value separator:"), 1, 0)
        self._delim_combo = QComboBox()
        self._delim_combo.addItems(['Auto', 'tab', ';', ',', '|', 'space'])
        self._delim_combo.setToolTip("Character that separates columns in the file.")
        sep_layout.addWidget(self._delim_combo, 1, 1)

        sep_layout.addWidget(QLabel("Decimal separator:"), 2, 0)
        self._decimal_combo = QComboBox()
        self._decimal_combo.addItems(['Auto', '.', ','])
        self._decimal_combo.setToolTip("Character used as decimal point in numbers.")
        sep_layout.addWidget(self._decimal_combo, 2, 1)

        sep_layout.addWidget(QLabel("Header row:"), 3, 0)
        self._header_combo = QComboBox()
        self._header_combo.addItems(['Auto', 'No header', 'Row 1'])
        self._header_combo.setToolTip(
            "Which row is the header — the row holding the column names.\n\n"
            "Auto      : detect it (assumes the table starts at the first row).\n"
            "No header : there are no column names; names are generated.\n"
            "Row N     : row N is the header. Everything ABOVE it is discarded.\n\n"
            "Use 'Row N' when the file has preamble above the real table — an\n"
            "instrument banner, a title, a blank line, units on their own line.\n"
            "'Row 1' is the same as the old 'Yes'.\n\n"
            "In Row-oriented layout there is no header ROW (the spectrum names\n"
            "come from a label COLUMN — see Label column). There, 'Row N' means\n"
            "'the table starts at row N', i.e. row N is the shared X-scale row,\n"
            "and anything above it is discarded.")
        sep_layout.addWidget(self._header_combo, 3, 1)

        hdr_thresh_label = QLabel("Header threshold:")
        hdr_thresh_label.setToolTip(
            "Only used when Header row is set to Auto.\n\n"
            "The candidate header line is split into tokens. If at least "
            "this percentage of tokens fail to parse as a number, the line "
            "is classified as a header; otherwise it's treated as data.\n\n"
            "Lower it if a real header is being missed because a few of its "
            "tokens happen to look numeric. Raise it if a data line is being "
            "mistaken for a header because it contains a few text values."
        )
        sep_layout.addWidget(hdr_thresh_label, 4, 0)
        self._header_threshold_spin = QSpinBox()
        self._header_threshold_spin.setRange(1, 100)
        self._header_threshold_spin.setValue(50)
        self._header_threshold_spin.setSuffix(" %")
        self._header_threshold_spin.setToolTip(hdr_thresh_label.toolTip())
        # Without this, typing a new threshold fires _on_settings_changed
        # -> _refresh_preview() (a full re-parse of the sample lines and
        # preview table rebuild) on every intermediate digit, not just the
        # final value. Same missing-keyboard-tracking pattern found and
        # fixed elsewhere in this audit (e.g. SG-Smoothing's window-length
        # spinbox, several spinboxes in reference_matching_dialog.py).
        self._header_threshold_spin.setKeyboardTracking(False)
        sep_layout.addWidget(self._header_threshold_spin, 4, 1)

        self._sep_group.setLayout(sep_layout)
        settings_row.addWidget(self._sep_group)

        # General group
        self._gen_group = QGroupBox("General")
        gen_layout = QGridLayout()
        gen_layout.setVerticalSpacing(4)

        layout_label = QLabel("Layout:")
        gen_layout.addWidget(layout_label, 0, 0)

        self._layout_standard   = QRadioButton("Standard  (spectra in columns)")
        self._layout_interlaced = QRadioButton("Interlaced  (x₁,y₁,x₂,y₂,…)")
        self._layout_row        = QRadioButton("Row-oriented  (spectra in rows)")
        self._layout_standard.setChecked(True)

        self._layout_interlaced.setToolTip(
            "Enable when each spectrum has its own x-column:\n"
            "columns alternate x, y, x, y, …"
        )
        self._layout_row.setToolTip(
            "Enable when each spectrum occupies a row instead of a column:\n"
            "row 0 is the shared x-scale; an optional first column\n"
            "provides spectrum labels for the remaining rows."
        )

        self._layout_group = QButtonGroup(self)
        for w in (self._layout_standard, self._layout_interlaced, self._layout_row):
            self._layout_group.addButton(w)

        gen_layout.addWidget(self._layout_standard,   1, 0, 1, 2)
        gen_layout.addWidget(self._layout_interlaced, 2, 0, 1, 2)
        gen_layout.addWidget(self._layout_row,         3, 0, 1, 2)

        label_col_label = QLabel("Label column:")
        label_col_label.setToolTip(
            "Row-oriented only. Which column of the raw file to use as the "
            "spectrum-label source, instead of the default first column.\n\n"
            "Shown as 'Column N: <first value>' so columns with duplicate "
            "or missing names can still be told apart by their index."
        )
        self._label_col_label = label_col_label
        gen_layout.addWidget(label_col_label, 4, 0)
        self._label_column_combo = QComboBox()
        self._label_column_combo.addItem("Auto (first column)")
        self._label_column_combo.setToolTip(label_col_label.toolTip())
        gen_layout.addWidget(self._label_column_combo, 4, 1)

        x_col_label = QLabel("X-scale column:")
        x_col_label.setToolTip(
            "Standard layout only. Which column of the file to use as the "
            "shared X-scale, instead of the default first column.\n\n"
            "Shown as 'Column N: <first value>' so columns with duplicate "
            "or missing names can still be told apart by their index.\n\n"
            "Note: every remaining column is treated as a spectrum. Use "
            "'Exclude columns' below for any other metadata columns that "
            "shouldn't become spectra."
        )
        self._x_col_label = x_col_label
        gen_layout.addWidget(x_col_label, 5, 0)
        self._x_scale_column_combo = QComboBox()
        self._x_scale_column_combo.addItem("Auto (first column)")
        self._x_scale_column_combo.setToolTip(x_col_label.toolTip())
        gen_layout.addWidget(self._x_scale_column_combo, 5, 1)

        exclude_col_label = QLabel("Exclude columns:")
        exclude_col_label.setToolTip(
            "Standard layout only. Tick any columns that are neither the "
            "X-scale nor a real spectrum — an ID number, sample type, "
            "timestamp, etc. — to drop them entirely before importing.\n\n"
            "Unlike picking a different X-scale column alone, excluded "
            "columns are removed rather than becoming bogus spectra.\n\n"
            "A column can't be both the X-scale column and excluded."
        )
        self._exclude_col_label = exclude_col_label
        gen_layout.addWidget(exclude_col_label, 6, 0, Qt.AlignTop)
        self._exclude_columns_list = QListWidget()
        self._exclude_columns_list.setToolTip(exclude_col_label.toolTip())
        self._exclude_columns_list.setMaximumHeight(90)
        self._exclude_columns_list.setSelectionMode(QListWidget.NoSelection)
        gen_layout.addWidget(self._exclude_columns_list, 6, 1)

        # --- X-axis conveniences -------------------------------------------
        self._index_x_cb = QCheckBox("Use row number (1, 2, 3, …) as the X axis")
        self._index_x_cb.setToolTip(
            "For tables that have no meaningful numeric X axis at all — a table\n"
            "of concentration profiles, say, whose only non-numeric column is a\n"
            "sample name.\n\n"
            "Excluding that name column does NOT solve it: the first remaining\n"
            "column would then be eaten as the X-scale, silently costing you a\n"
            "real data column. Tick this and a synthetic X axis (1, 2, 3, …) is\n"
            "used instead, so EVERY remaining column stays a spectrum.\n\n"
            "Row-oriented layout: the X-scale normally comes from the first data\n"
            "ROW. With this ticked there is no such row — every row is a spectrum\n"
            "and the X axis becomes the point number.\n\n"
            "Cannot be combined with an explicit X-scale column (there is no X\n"
            "column to pick)."
        )
        self._index_x_cb.toggled.connect(self._on_index_x_toggled)
        gen_layout.addWidget(self._index_x_cb, 7, 0, 1, 2)


        gen_layout.addWidget(QLabel("Analyze rows:"), 9, 0)
        self._analyze_spin = QSpinBox()
        self._analyze_spin.setRange(1, 200)
        self._analyze_spin.setToolTip("Rows examined for auto-detection heuristics.")
        gen_layout.addWidget(self._analyze_spin, 9, 1)

        self._gen_group.setLayout(gen_layout)
        settings_row.addWidget(self._gen_group)

        # Initial visibility matches the default layout (Standard, checked
        # above) — Label column is Row-oriented-only, so start hidden.
        self._label_col_label.setVisible(False)
        self._label_column_combo.setVisible(False)

        root.addLayout(settings_row)

        # --- Zero padding (auto-generated spectrum numbering) --------------
        # Lives outside the General group (unlike the other text/Excel-only
        # controls above) because it also applies to multi-frame SPE and
        # multi-subfile SPC files — both build auto-numbered labels like
        # "sample : 0002" the same way text/Excel imports do (see
        # read_spe_data/read_spc_data's own zero_padding parameter). Only
        # JWS never uses it: its per-file spectra are channel-named
        # (CD/HT/Absorbance), never auto-numbered — see _load_file, which
        # hides this row specifically for JWS.
        self._padding_row = QWidget()
        padding_row_layout = QHBoxLayout(self._padding_row)
        padding_row_layout.setContentsMargins(0, 0, 0, 0)
        padding_row_layout.addWidget(QLabel("Zero padding:"))
        self._padding_spin = QSpinBox()
        self._padding_spin.setRange(1, 10)
        self._padding_spin.setToolTip(
            "Digit width for auto-generated spectrum numbers (e.g. 4 → "
            "\"0001\", \"0002\", … instead of \"1\", \"2\", …) — wider "
            "than the largest number needed keeps alphabetical sorting of "
            "spectrum labels in the correct numeric order."
        )
        padding_row_layout.addWidget(self._padding_spin)
        padding_row_layout.addStretch()
        root.addWidget(self._padding_row)

        # --- detection summary line ---------------------------------------
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(
            "color:#444; font-size:9pt; padding:2px 4px;"
            "background:#f9f9f9; border-radius:3px;"
        )
        root.addWidget(self._summary_label)

        # --- SPE calibration choice (legacy WinSpec files only) -----------
        # Hidden entirely except when the currently-previewed file is a
        # legacy WinSpec .spe with a valid x-axis calibration — see
        # _load_spe_preview, which is the only place that shows/enables/
        # relabels this. LightField files and legacy files with no
        # calibration recorded never show it at all, same "hide, don't
        # grey out, when a control has no possible effect" convention
        # used for Layout-dependent column pickers elsewhere in this
        # dialog.
        self._spe_calib_cb = QCheckBox("Use calibrated x-axis")
        self._spe_calib_cb.setVisible(False)
        self._spe_calib_cb.toggled.connect(self._on_spe_calibration_toggled)
        root.addWidget(self._spe_calib_cb)

        # --- JWS channel selection (JASCO CD spectrometer files) ----------
        # Hidden entirely except when the currently-previewed file is a
        # .jws — see _load_jws_preview, the only place that populates and
        # shows it. A .jws file can carry several co-recorded channels
        # (commonly CD, and optionally HT and/or Absorbance sharing the
        # same wavelength axis — see jasco_jws_reader.py's module
        # docstring), and unlike SPE/SPC frames these are NOT all imported
        # unconditionally: each row lets the user tick which channel(s)
        # become spectra. Type is this reader's own value-range-based
        # guess (there is no channel-type string recorded in the file
        # itself) shown as an editable combo box rather than trusted
        # silently.
        self._jws_channels_group = QGroupBox("Channels to import")
        jws_layout = QVBoxLayout()
        self._jws_channels_table = QTableWidget(0, 3)
        self._jws_channels_table.setHorizontalHeaderLabels(["Include", "Type", "Range"])
        self._jws_channels_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._jws_channels_table.horizontalHeader().setStretchLastSection(True)
        self._jws_channels_table.verticalHeader().setVisible(False)
        self._jws_channels_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._jws_channels_table.setSelectionMode(QTableWidget.NoSelection)
        self._jws_channels_table.setMaximumHeight(140)
        self._jws_channels_table.itemChanged.connect(self._on_jws_channel_setting_changed)
        jws_layout.addWidget(self._jws_channels_table)
        self._jws_channels_group.setLayout(jws_layout)
        self._jws_channels_group.setVisible(False)
        root.addWidget(self._jws_channels_group)

        # --- preview table ------------------------------------------------
        preview_group = QGroupBox("Preview  (first file)")
        preview_layout = QVBoxLayout()

        self._preview_table = QTableWidget()
        self._preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._preview_table.setSelectionMode(QTableWidget.NoSelection)
        self._preview_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self._preview_table.setAlternatingRowColors(True)
        mono = QFont("Courier New", 9)
        self._preview_table.setFont(mono)
        self._preview_table.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        preview_layout.addWidget(self._preview_table)
        preview_group.setLayout(preview_layout)
        root.addWidget(preview_group, stretch=1)

        # --- buttons ------------------------------------------------------
        btn_layout = QHBoxLayout()
        self._help_btn = QPushButton("Help")
        self._help_btn.clicked.connect(self._show_help)
        btn_layout.addWidget(self._help_btn)
        btn_layout.addStretch()
        self._import_btn = QPushButton("Import")
        self._import_btn.setDefault(True)
        self._cancel_btn = QPushButton("Cancel")
        self._import_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._import_btn)
        btn_layout.addWidget(self._cancel_btn)
        root.addLayout(btn_layout)

        # --- signals ------------------------------------------------------
        self._sheet_combo.currentIndexChanged.connect(self._on_sheet_changed)
        # BUG FIX: these two connections were missing entirely, so ticking
        # "Import several sheets" did nothing at all — the combo never turned
        # into the checkable list, and ticking sheets never refreshed anything.
        self._multi_sheet_cb.toggled.connect(self._on_multi_sheet_toggled)
        self._sheet_list.itemChanged.connect(self._on_sheet_list_changed)
        # Selecting (highlighting) a sheet — as opposed to ticking it — chooses
        # which sheet's settings the panel below is editing.
        self._sheet_list.currentRowChanged.connect(self._on_sheet_list_selection)
        self._delim_combo.currentTextChanged.connect(self._on_delimiter_changed)
        self._decimal_combo.currentTextChanged.connect(self._on_settings_changed)
        self._header_combo.currentTextChanged.connect(self._on_settings_changed)
        self._header_threshold_spin.valueChanged.connect(self._on_settings_changed)
        self._label_column_combo.currentIndexChanged.connect(self._on_settings_changed)
        self._x_scale_column_combo.currentIndexChanged.connect(self._on_settings_changed)
        self._exclude_columns_list.itemChanged.connect(self._on_settings_changed)
        self._layout_standard.toggled.connect(self._on_layout_changed)
        self._layout_interlaced.toggled.connect(self._on_layout_changed)
        self._layout_row.toggled.connect(self._on_layout_changed)
        self._padding_spin.valueChanged.connect(self._on_settings_changed)
        self._analyze_spin.valueChanged.connect(self._on_analyze_rows_changed)

    # ------------------------------------------------------------------
    # File loading and navigation
    # ------------------------------------------------------------------

    def _load_first_file(self):
        self._has_loaded_once = False
        self._load_file(self._preview_file_index)

    def _load_file(self, index: int):
        """
        Show file *index* in the preview/settings panel.

        If this file was already previewed earlier in this dialog session,
        its exact previous settings are restored (whatever the user last
        configured for it) instead of re-running auto-detection — so
        flipping between files while reviewing a batch never loses edits.
        The very first time a file is shown, settings are auto-detected
        fresh from `self._default_settings` as before.
        """
        # Snapshot whatever the outgoing file's widgets currently show,
        # before we switch — captures any edit made without navigating
        # away via the list/arrows (e.g. the user tweaks a setting then
        # clicks Import directly).
        if self._has_loaded_once:
            self._capture_current_file_settings()

        self._preview_file_index = index
        filepath = self._file_paths[index]
        n = len(self._file_paths)

        # The profile dropdown only reflects a profile just applied to
        # THIS file's settings — switching files makes that stale.
        self._profile_combo.blockSignals(True)
        self._profile_combo.setCurrentIndex(0)
        self._profile_combo.blockSignals(False)

        self._current_file_label.setText(
            f"Now configuring file {index + 1} of {n}:  {os.path.basename(filepath)}"
        )
        if hasattr(self, '_file_list_widget'):
            self._file_list_widget.blockSignals(True)
            self._file_list_widget.setCurrentRow(index)
            self._file_list_widget.blockSignals(False)

        file_ext = os.path.splitext(filepath)[1].lower()
        is_spe = file_ext == '.spe'
        is_spc = file_ext == '.spc'
        is_jws = file_ext == '.jws'
        is_binary = is_spe or is_spc or is_jws

        # SPE/SPC/JWS files (raw camera frames / GRAMS spectra / JASCO CD
        # channels) have almost no configurable import settings — no
        # delimiter, decimal, header, Layout, column pickers, or Sheet.
        # Hide every text/Excel-oriented settings group and show a
        # dedicated info/preview instead, rather than letting the
        # text/Excel-oriented logic below try to make sense of binary
        # data. Zero padding is the one exception (see _padding_row below)
        # since multi-frame SPE / multi-subfile SPC files auto-number
        # their spectra the same way text/Excel imports do.
        self._sep_group.setVisible(not is_binary)
        self._gen_group.setVisible(not is_binary)
        # Zero padding applies to every format except JWS, whose per-file
        # spectra are channel-named (CD/HT/Absorbance) rather than
        # auto-numbered.
        self._padding_row.setVisible(not is_jws)
        # Reset both binary-format-specific controls up front — each is
        # only ever turned back on by its own _load_*_preview when it's
        # actually relevant for the file now on screen, so navigating away
        # from e.g. a JWS file to a text file doesn't leave the channel
        # table stuck on screen.
        self._spe_calib_cb.setVisible(False)
        self._jws_channels_group.setVisible(False)
        if is_binary:
            self._sheet_label.setVisible(False)
            self._sheet_combo.setVisible(False)
            if is_spe or is_spc:
                # Restore this file's own previously-saved zero-padding
                # width before generating its preview, the same way
                # _load_spe_preview restores spe_use_calibration below —
                # otherwise switching between binary files would leak
                # whichever file's padding the spinbox last happened to
                # show.
                saved = self._file_settings.get(index, {})
                self._padding_spin.blockSignals(True)
                self._padding_spin.setValue(saved.get('zero_padding', 4))
                self._padding_spin.blockSignals(False)
            if is_spe:
                self._load_spe_preview(filepath)
            elif is_spc:
                self._load_spc_preview(filepath)
            else:
                self._load_jws_preview(filepath)
            if index not in self._file_settings:
                self._capture_current_file_settings()
            self._has_loaded_once = True
            return

        is_excel = file_ext in ('.xlsx', '.xls', '.xlsm')

        # Sheet picker: only meaningful for Excel files. Populated with
        # this specific file's actual sheet names before any sample data
        # is read, since which sheet is selected determines what the
        # preview shows in the first place. If this file was already
        # customized earlier in the session, its saved sheet choice is
        # restored here too.
        self._sheet_label.setVisible(is_excel)
        self._multi_sheet_cb.setVisible(is_excel)
        saved_settings = self._file_settings.get(index)
        target_sheet = saved_settings.get('sheet_name') if saved_settings else None
        saved_multi = (saved_settings or {}).get('sheet_names') or []
        if is_excel:
            sheets = _list_excel_sheets(filepath)
            self._sheet_combo.blockSignals(True)
            self._sheet_combo.clear()
            self._sheet_combo.addItem("Auto (spectra / first sheet)")
            for sheet in sheets:
                self._sheet_combo.addItem(sheet)
            if target_sheet:
                found_idx = self._sheet_combo.findText(target_sheet)
                self._sheet_combo.setCurrentIndex(found_idx if found_idx >= 0 else 0)
            else:
                self._sheet_combo.setCurrentIndex(0)
            self._sheet_combo.blockSignals(False)

            # Mirror the same sheets into the checkable multi-select list used
            # by "Import several sheets".
            #
            # NOT while a sheet switch is in progress: rebuilding the list resets
            # its selection, which re-fires currentRowChanged and re-enters the
            # switch handler — which then pointed the edited sheet back at the one we
            # were leaving and wrote the freshly-reset widget defaults over its
            # real settings. The list contents cannot have changed anyway (same
            # file, same workbook), so there is simply nothing to rebuild here.
            if not self._switching_sheet:
                self._sheet_list.blockSignals(True)
                self._sheet_list.clear()
                for sheet in sheets:
                    item = QListWidgetItem(sheet)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(
                        Qt.Checked if sheet in saved_multi else Qt.Unchecked)
                    self._sheet_list.addItem(item)
                self._sheet_list.blockSignals(False)

            self._multi_sheet_cb.blockSignals(True)
            self._multi_sheet_cb.setChecked(bool(saved_multi))
            self._multi_sheet_cb.blockSignals(False)

        multi_on = is_excel and self._multi_sheet_cb.isChecked()
        self._sheet_box.setVisible(is_excel)
        self._sheet_combo.setVisible(is_excel and not multi_on)
        self._sheet_list.setVisible(multi_on)
        self._update_apply_all_sheets_visibility()

        self._sample_lines = _read_sample(
            filepath,
            n_lines=8,   # preview shows up to 8 rows; auto-detection uses analyze_rows separately
            sheet_name=self._current_sheet_name() if is_excel else None,
        )

        # For Excel files, separator controls are not meaningful
        for w in (self._delim_combo, self._decimal_combo):
            w.setEnabled(not is_excel)
        if is_excel:
            self._summary_label.setText(
                "Excel file — delimiter and decimal separator are read natively from the workbook."
            )
            self._summary_label.setStyleSheet(
                "color:#7a5c00; background:#fff8dc; padding:2px 4px; border-radius:3px;"
            )
        else:
            self._summary_label.setStyleSheet(
                "color:#444; font-size:9pt; padding:2px 4px;"
                "background:#f9f9f9; border-radius:3px;"
            )

        if index in self._file_settings:
            self._apply_saved_settings(self._file_settings[index], self._sample_lines)
        else:
            self._apply_autodetect(self._sample_lines)
            self._populate_label_column_combo()
            self._populate_x_scale_column_combo()
            self._populate_exclude_columns_list()
            self._capture_current_file_settings()

        self._has_loaded_once = True
        self._refresh_preview()

    def _load_spe_preview(self, filepath: str, use_calibration: Optional[bool] = None):
        """
        Show a lightweight preview for an SPE file (LightField 3.x or
        legacy WinSpec 2.x — read_spe_data auto-detects which) — no
        settings apply beyond the calibration choice below, so this
        replaces the usual settings-driven preview with a short summary
        and a look at the first few frames. Errors (e.g. an unsupported
        2D/multi-ROI acquisition) are shown the same way a bad delimiter
        guess would be — in the summary line, not a popup, so browsing a
        multi-file batch isn't interrupted.

        use_calibration: which axis to preview. None (the default, used
        when a file is first opened/switched to) resolves automatically:
        this file's previously-saved choice if it has one, otherwise the
        pixel axis (see the default below for why). Passed explicitly by
        _on_spe_calibration_toggled when the user flips the checkbox for
        the file currently on screen.
        """
        index = self._preview_file_index
        if use_calibration is None:
            saved = self._file_settings.get(index, {})
            # No saved choice yet for this file: default to the pixel
            # axis. Calibration isn't available at all for a large class
            # of real files (LightField/new-format SPE has no calibration
            # support here — see spe_data_converter), and even where it
            # is available (legacy WinSpec), it's whatever axis the
            # instrument software happened to record — commonly
            # wavelength (nm), not the derived unit (e.g. Raman shift)
            # someone actually wants to work in. Pixel-index is the one
            # axis every SPE file can always produce, so it's the safer
            # default; calibrated is still one click away whenever a
            # specific file's calibration is exactly what's wanted.
            use_calibration = saved.get('spe_use_calibration', False)

        try:
            from src.modules.data_io.spe_data_converter import read_spe_data
            spectra = read_spe_data(
                filepath, zero_padding=self._padding_spin.value(),
                use_calibration=use_calibration)
        except Exception as e:
            self._summary_label.setText(f"Could not read SPE file: {e}")
            self._summary_label.setStyleSheet(
                "color:#8a0000; background:#fff0f0; padding:2px 4px;"
                "border-radius:3px; font-weight:bold;"
            )
            self._preview_table.setRowCount(0)
            self._preview_table.setColumnCount(0)
            self._spe_calib_cb.setVisible(False)
            return

        n_frames = len(spectra)
        width = len(spectra[0]['x_scale']) if spectra else 0
        file_type = spectra[0]['metadata']['file_type'] if spectra else 'spe'
        is_legacy = file_type == 'spe_winspec_legacy'
        format_label = "WinSpec legacy" if is_legacy else "LightField"

        params = spectra[0]['metadata']['import_parameters'] if spectra else {}
        calibration_available = bool(params.get('calibration_available', False))
        x_axis_calibrated = bool(params.get('x_axis_calibrated', False))
        unit_label = params.get('calibration_unit_label', '') or ''

        # The checkbox only ever appears when it could actually change
        # something for THIS file — LightField files (calibration not
        # currently supported for that format — see spe_data_converter)
        # and legacy files with no recorded calibration never show it,
        # same "hide, don't grey out, a control with no possible effect"
        # convention used for Layout-dependent column pickers elsewhere
        # in this dialog.
        self._spe_calib_cb.blockSignals(True)
        if is_legacy and calibration_available:
            label = f"Use calibrated x-axis ({unit_label})" if unit_label else "Use calibrated x-axis"
            self._spe_calib_cb.setText(label)
            self._spe_calib_cb.setChecked(x_axis_calibrated)
            self._spe_calib_cb.setToolTip(
                "This file carries a real x-axis calibration recorded by "
                "WinSpec at acquisition time. Checked: import spectra "
                "with that calibrated axis. Unchecked: import with the "
                "raw pixel index instead (this app's long-standing "
                "default)."
            )
            self._spe_calib_cb.setVisible(True)
        else:
            self._spe_calib_cb.setChecked(False)
            self._spe_calib_cb.setVisible(False)
        self._spe_calib_cb.blockSignals(False)

        if x_axis_calibrated:
            axis_desc = f"a calibrated x-axis ({unit_label})" if unit_label else "a calibrated x-axis"
        else:
            axis_desc = f"an uncalibrated pixel-index x-axis (0–{max(width - 1, 0)})"
        self._summary_label.setText(
            f"SPE file ({format_label}) — {n_frames} frame{'s' if n_frames != 1 else ''} "
            f"detected, {width} pixels each. Will import as {n_frames} "
            f"spectra with {axis_desc}."
        )
        self._summary_label.setStyleSheet(
            "color:#7a5c00; background:#fff8dc; padding:2px 4px; border-radius:3px;"
        )

        # Same visual language as the text-file preview: cyan = the axis
        # column — pixel index or, when calibrated, the real physical
        # axis — rather than a shared x-scale read from delimited text.
        # Rows are pixels/points (first 8, matching the usual cap);
        # columns are the first few frames.
        preview_frames = spectra[:5]
        n_rows = min(8, width)
        self._preview_table.setRowCount(n_rows)
        self._preview_table.setColumnCount(1 + len(preview_frames))
        axis_header = unit_label if (x_axis_calibrated and unit_label) else (
            'x-axis' if x_axis_calibrated else 'pixel'
        )
        self._preview_table.setHorizontalHeaderLabels(
            [axis_header] + [f"frame {i + 1}" for i in range(len(preview_frames))]
        )
        for r in range(n_rows):
            axis_value = preview_frames[0]['x_scale'][r]
            axis_text = f"{axis_value:.3f}" if x_axis_calibrated else str(int(axis_value))
            idx_item = QTableWidgetItem(axis_text)
            idx_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            idx_item.setBackground(Qt.GlobalColor.cyan)
            idx_item.setForeground(Qt.GlobalColor.darkBlue)
            self._preview_table.setItem(r, 0, idx_item)
            for c, sp in enumerate(preview_frames):
                val_item = QTableWidgetItem(f"{sp['y_scale'][r]:.1f}")
                val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._preview_table.setItem(r, c + 1, val_item)

    def _on_spe_calibration_toggled(self, checked: bool):
        """User flipped the 'Use calibrated x-axis' checkbox for the SPE
        file currently on screen — reload its preview under the new
        choice and persist it, the same way any other per-file setting
        change does."""
        filepath = self._file_paths[self._preview_file_index]
        self._load_spe_preview(filepath, use_calibration=checked)
        self._capture_current_file_settings()

    def _load_spc_preview(self, filepath: str):
        """
        Show a lightweight preview for a GRAMS/Thermo SPC file (old or
        new format — read_spc_data auto-detects which) — same treatment
        as the SPE preview above: no configurable settings, just a
        summary and a look at the first few subfiles. Unlike SPE, SPC
        carries a real, calibrated x-axis (wavenumber, nm, etc. — see
        x_label) rather than a raw pixel index, and usually has just one
        subfile rather than many frames.
        """
        try:
            from src.modules.data_io.spc_data_converter import read_spc_data
            spectra = read_spc_data(filepath, zero_padding=self._padding_spin.value())
        except Exception as e:
            self._summary_label.setText(f"Could not read SPC file: {e}")
            self._summary_label.setStyleSheet(
                "color:#8a0000; background:#fff0f0; padding:2px 4px;"
                "border-radius:3px; font-weight:bold;"
            )
            self._preview_table.setRowCount(0)
            self._preview_table.setColumnCount(0)
            return

        n_sub = len(spectra)
        n_points = len(spectra[0]['x_scale']) if spectra else 0
        params = spectra[0]['metadata']['import_parameters'] if spectra else {}
        format_label = "old" if params.get('spc_format', '').startswith('old') else "new"
        x_label = params.get('x_label', 'x')
        y_label = params.get('y_label', 'y')
        self._summary_label.setText(
            f"SPC file ({format_label} format) — {n_sub} subfile{'s' if n_sub != 1 else ''} "
            f"detected, {n_points} points each. X axis: {x_label}. Y axis: {y_label}."
        )
        self._summary_label.setStyleSheet(
            "color:#7a5c00; background:#fff8dc; padding:2px 4px; border-radius:3px;"
        )

        # Same visual language as the SPE preview: cyan = the axis
        # column, here the file's own calibrated x-axis. Rows are points
        # (first 8, matching the usual cap); columns are the first few
        # subfiles.
        preview_subs = spectra[:5]
        n_rows = min(8, n_points)
        self._preview_table.setRowCount(n_rows)
        self._preview_table.setColumnCount(1 + len(preview_subs))
        self._preview_table.setHorizontalHeaderLabels(
            [x_label] + [f"subfile {i + 1}" for i in range(len(preview_subs))]
        )
        for r in range(n_rows):
            idx_item = QTableWidgetItem(f"{preview_subs[0]['x_scale'][r]:.4g}")
            idx_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            idx_item.setBackground(Qt.GlobalColor.cyan)
            idx_item.setForeground(Qt.GlobalColor.darkBlue)
            self._preview_table.setItem(r, 0, idx_item)
            for c, sp in enumerate(preview_subs):
                val_item = QTableWidgetItem(f"{sp['y_scale'][r]:.4g}")
                val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._preview_table.setItem(r, c + 1, val_item)

    # Channel-type combo text <-> jasco_jws_reader's internal type codes.
    _JWS_TYPE_TO_COMBO_TEXT = {
        'CD': 'CD [mdeg]', 'HT': 'HT [V]', 'Abs': 'Absorbance [AU]', 'Signal': 'Signal',
    }
    _JWS_COMBO_TEXT_TO_TYPE = {v: k for k, v in _JWS_TYPE_TO_COMBO_TEXT.items()}

    def _load_jws_preview(self, filepath: str):
        """
        Show the channel-selection table for a JASCO .jws file. Unlike
        SPE/SPC, a .jws file's spectra are NOT all imported unconditionally
        — each co-recorded channel (CD, and optionally HT and/or
        Absorbance — see jasco_jws_reader.py's module docstring) becomes
        its own spectrum only if ticked here, since e.g. a CD-only user
        importing a file that also carries HT wouldn't want a spurious
        "HT [V]" spectrum cluttering their list. All channels are ticked
        by default.

        Channel TYPE is this reader's own value-range-based guess (.jws
        does not record a channel-type string anywhere recoverable — see
        the module docstring) and is deliberately an editable combo box
        rather than trusted silently: pick the correct type here if the
        guess looks wrong for a given file.
        """
        index = self._preview_file_index
        saved = self._file_settings.get(index, {})
        saved_selected = saved.get('jws_selected_channels')
        saved_overrides = saved.get('jws_channel_type_overrides') or {}

        try:
            from src.modules.data_io.jasco_jws_reader import probe_jws_channels
            probe = probe_jws_channels(filepath)
        except Exception as e:
            self._summary_label.setText(f"Could not read JWS file: {e}")
            self._summary_label.setStyleSheet(
                "color:#8a0000; background:#fff0f0; padding:2px 4px;"
                "border-radius:3px; font-weight:bold;"
            )
            self._jws_channels_table.setRowCount(0)
            self._jws_channels_group.setVisible(False)
            self._preview_table.setRowCount(0)
            self._preview_table.setColumnCount(0)
            return

        channels = probe['channels']
        self._summary_label.setText(
            f"JASCO .jws file — {len(channels)} channel{'s' if len(channels) != 1 else ''} "
            f"found, {probe['n_points']} points each, x-axis {probe['x_start']:.2f} to "
            f"{probe['x_end']:.2f}. Tick which channel(s) to import below."
        )
        self._summary_label.setStyleSheet(
            "color:#7a5c00; background:#fff8dc; padding:2px 4px; border-radius:3px;"
        )

        self._jws_channels_group.setVisible(True)
        self._jws_channels_table.blockSignals(True)
        self._jws_channels_table.setRowCount(len(channels))
        for row, ch in enumerate(channels):
            # Row index == channel index by construction (probe returns
            # channels in order 0..n-1) — relied on by
            # _current_jws_selected_channels/_current_jws_channel_type_overrides.
            include_item = QTableWidgetItem(f"Channel {ch['index'] + 1}")
            include_item.setFlags((include_item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            default_checked = saved_selected is None or ch['index'] in saved_selected
            include_item.setCheckState(Qt.Checked if default_checked else Qt.Unchecked)
            self._jws_channels_table.setItem(row, 0, include_item)

            combo = QComboBox()
            combo.addItems(['CD [mdeg]', 'HT [V]', 'Absorbance [AU]', 'Signal'])
            chosen_type = saved_overrides.get(ch['index'], ch['type'])
            combo.setCurrentText(self._JWS_TYPE_TO_COMBO_TEXT.get(chosen_type, ch['display']))
            combo.currentIndexChanged.connect(self._on_jws_channel_setting_changed)
            self._jws_channels_table.setCellWidget(row, 1, combo)

            range_item = QTableWidgetItem(f"{ch['y_min']:.3g} to {ch['y_max']:.3g}")
            range_item.setFlags(range_item.flags() & ~Qt.ItemIsEditable)
            range_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._jws_channels_table.setItem(row, 2, range_item)
        self._jws_channels_table.blockSignals(False)

        self._preview_table.setRowCount(0)
        self._preview_table.setColumnCount(0)

    def _on_jws_channel_setting_changed(self, *_args):
        """User ticked/unticked a channel or changed its guessed type for
        the JWS file currently on screen — persist immediately, the same
        way the SPE calibration checkbox does."""
        self._capture_current_file_settings()

    def _current_jws_selected_channels(self) -> Optional[list]:
        """None when the channel table isn't currently showing a JWS
        file's channels — callers then fall back to 'import every
        channel', matching read_jws_data's own default."""
        if self._jws_channels_table.rowCount() == 0:
            return None
        selected = []
        for row in range(self._jws_channels_table.rowCount()):
            item = self._jws_channels_table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                selected.append(row)  # row == channel index, see _load_jws_preview
        return selected

    def _current_jws_channel_type_overrides(self) -> dict:
        overrides = {}
        for row in range(self._jws_channels_table.rowCount()):
            combo = self._jws_channels_table.cellWidget(row, 1)
            if combo is not None:
                overrides[row] = self._JWS_COMBO_TEXT_TO_TYPE.get(combo.currentText(), 'Signal')
        return overrides

    def _header_setting(self):
        """Translate the Header-row combo into (header, header_row).

        'Auto'      -> (None, None)   detect; table starts at row 0
        'No header' -> (False, None)  no column names anywhere
        'Row N'     -> (True, N-1)    row N is the header; rows above discarded
        """
        text = self._header_combo.currentText()
        if text == 'Auto':
            return None, None
        if text in ('No header', 'No'):
            return False, None
        if text.startswith('Row '):
            try:
                return True, int(text.split()[1]) - 1
            except (IndexError, ValueError):
                return True, 0
        # legacy value from a saved profile
        return (text == 'Yes'), (0 if text == 'Yes' else None)

    def _populate_header_row_combo(self):
        """Offer one 'Row N' entry per line of the sample, so a header that is
        not the first line can actually be chosen."""
        current = self._header_combo.currentText()
        # Save/restore whatever blocked state the caller already had, rather
        # than forcing blockSignals(False) at the end — Qt's blockSignals()
        # doesn't nest, so a caller that already had this combo blocked (e.g.
        # _apply_saved_settings, mid-restore) would otherwise get it silently
        # UNBLOCKED here, letting a later setCurrentText() in that caller fire
        # a premature _on_settings_changed() before the rest of the restore
        # has finished.
        was_blocked = self._header_combo.signalsBlocked()
        self._header_combo.blockSignals(True)
        self._header_combo.clear()
        self._header_combo.addItems(['Auto', 'No header'])
        for i in range(max(1, len(self._sample_lines))):
            self._header_combo.addItem(f'Row {i + 1}')
        idx = self._header_combo.findText(current)
        self._header_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._header_combo.blockSignals(was_blocked)

    def _current_sheet_name(self) -> Optional[str]:
        """The sheet the preview and the settings panel currently refer to.

        In multi-sheet mode that is the sheet SELECTED (highlighted) in the list
        — the one being configured — not the combo, which is hidden.
        """
        if self._multi_sheet_cb.isChecked() and self._current_multi_sheet:
            return self._current_multi_sheet
        idx = self._sheet_combo.currentIndex()
        return None if idx <= 0 else self._sheet_combo.currentText()

    def _current_sheet_names(self) -> Optional[list]:
        """The ticked sheets when "Import several sheets" is on, else None.

        None means "single-sheet behaviour" — the importer then falls back to
        sheet_name exactly as before, so nothing changes for existing users or
        for non-Excel files.
        """
        # Deliberately NOT gated on isVisible(): a widget reports itself
        # invisible until the dialog is actually shown, which made this return
        # None even with sheets ticked. The checkbox is only ever checkable for
        # Excel files (it is hidden and left unchecked otherwise), so its state
        # alone is the right test.
        if not self._multi_sheet_cb.isChecked():
            return None
        names = [self._sheet_list.item(i).text()
                 for i in range(self._sheet_list.count())
                 if self._sheet_list.item(i).checkState() == Qt.Checked]
        return names or None

    def _on_sheet_list_changed(self, *_):
        """A sheet was ticked/unticked in the multi-sheet list."""
        self._on_settings_changed()


    def _capture_current_sheet_settings(self):
        """Snapshot the live widgets into the sheet currently being configured."""
        if self._current_multi_sheet:
            self._sheet_settings[(self._preview_file_index,
                                  self._current_multi_sheet)] = self._plain_settings()

    def _on_sheet_list_selection(self, row):
        """A different sheet was selected for configuration. Save the settings of
        the one we're leaving, re-read the sample from the new sheet, and restore
        that sheet's own settings (or start it from the current ones)."""
        if row < 0 or not self._multi_sheet_cb.isChecked():
            return
        item = self._sheet_list.item(row)
        if item is None:
            return
        new_sheet = item.text()
        if new_sheet == self._current_multi_sheet:
            return
        self._capture_current_sheet_settings()
        self._current_multi_sheet = new_sheet

        # Guard against re-entrancy: rebuilding the widgets below fires the usual
        # "settings changed" signals, and the sheet list would be repopulated,
        # resetting its selection and re-entering this handler — which then wrote
        # the freshly-reset widget defaults back over the settings just captured
        # for the sheet being left.
        self._switching_sheet = True
        try:
            filepath = self._file_paths[self._preview_file_index]
            self._sample_lines = _read_sample(
                filepath, n_lines=8, sheet_name=new_sheet)

            saved = self._sheet_settings.get((self._preview_file_index, new_sheet))
            if saved:
                self._apply_saved_settings(saved, self._sample_lines)
            else:
                # A sheet we've never clicked into before — genuinely
                # re-detect from Auto rather than silently inheriting
                # whatever the previous sheet had manually set (see
                # _apply_autodetect's reset_separators docstring).
                self._apply_autodetect(self._sample_lines, reset_separators=True)

            # The column pickers must list THIS sheet's columns — otherwise you
            # would be ticking "exclude column 3" against the previous sheet's
            # column names. (This was the missing piece: sheets are different
            # tables, so their columns differ.)
            self._populate_header_row_combo()
            if self._layout_row.isChecked():
                self._populate_label_column_combo()
            elif self._layout_standard.isChecked():
                self._populate_x_scale_column_combo()
                self._populate_exclude_columns_list()

            # Repopulating clears the tick marks, so re-apply the saved choices.
            if saved:
                self._restore_column_choices(saved)
        finally:
            self._switching_sheet = False

        self._on_settings_changed()

    def _on_index_x_toggled(self, *_):
        """index_x replaces the X axis with the row number, so there is no X
        column left to choose — grey the picker out (and reset it) rather than
        letting the user set two contradictory things and get an error on
        import."""
        on = self._index_x_cb.isChecked()
        self._x_scale_column_combo.setEnabled(not on)
        self._x_col_label.setEnabled(not on)
        if on:
            self._x_scale_column_combo.setCurrentIndex(0)   # back to Auto
        self._on_settings_changed()


    def _restore_column_choices(self, settings: dict):
        """Re-tick exclude-columns / re-select x-scale & label columns after the
        pickers have been rebuilt for a different sheet."""
        excl = settings.get('exclude_columns') or []
        self._exclude_columns_list.blockSignals(True)
        for i in range(self._exclude_columns_list.count()):
            self._exclude_columns_list.item(i).setCheckState(
                Qt.Checked if i in excl else Qt.Unchecked)
        self._exclude_columns_list.blockSignals(False)
        for combo, key in ((self._x_scale_column_combo, 'x_scale_column'),
                           (self._label_column_combo, 'label_column')):
            val = settings.get(key)
            combo.blockSignals(True)
            combo.setCurrentIndex(0 if val is None else min(val + 1, combo.count() - 1))
            combo.blockSignals(False)

    def _update_apply_all_sheets_visibility(self):
        """Show 'Apply to All Sheets' only when it could plausibly do
        something — multi-sheet mode on, and more than one sheet exists."""
        self._apply_all_sheets_btn.setVisible(
            self._multi_sheet_cb.isChecked() and self._sheet_list.count() > 1
        )

    def _on_multi_sheet_toggled(self, *_):
        """Swap the single-sheet combo for the checkable list (and back)."""
        on = self._multi_sheet_cb.isChecked()
        self._sheet_combo.setVisible(not on)
        self._sheet_list.setVisible(on)
        self._update_apply_all_sheets_visibility()
        if on:
            # Seed the ticks from the sheet currently chosen in the combo, so
            # turning the option on doesn't silently discard that choice.
            current = self._current_sheet_name()
            any_checked = False
            for i in range(self._sheet_list.count()):
                item = self._sheet_list.item(i)
                match = (current is not None and item.text() == current)
                item.setCheckState(Qt.Checked if match else Qt.Unchecked)
                any_checked = any_checked or match
            if not any_checked and self._sheet_list.count():
                self._sheet_list.item(0).setCheckState(Qt.Checked)
            if self._sheet_list.count() and self._sheet_list.currentRow() < 0:
                self._sheet_list.setCurrentRow(0)
                self._current_multi_sheet = self._sheet_list.item(0).text()
        else:
            self._current_multi_sheet = None
        self._on_settings_changed()

    def _on_sheet_changed(self, *_):
        """Sheet picker changed — re-read the sample from the newly
        selected sheet and refresh everything that depends on file
        content (column pickers, header detection, preview)."""
        filepath = self._file_paths[self._preview_file_index]
        self._sample_lines = _read_sample(
            filepath, n_lines=8, sheet_name=self._current_sheet_name()
        )
        self._populate_header_row_combo()
        if self._layout_row.isChecked():
            self._populate_label_column_combo()
        elif self._layout_standard.isChecked():
            self._populate_x_scale_column_combo()
            self._populate_exclude_columns_list()
        self._on_settings_changed()

    def _capture_current_file_settings(self):
        """Snapshot the currently-displayed file's live widget state into the
        per-file cache, so it survives navigating away and back.

        When "Import several sheets" is ticked, the very same widget state is
        ALSO snapshotted against the sheet currently being edited — that is what
        lets each worksheet keep its own exclude-columns / layout / header row.
        """
        self._file_settings[self._preview_file_index] = self.get_settings()

    def _apply_saved_settings(self, settings: dict, lines: list):
        """
        Restore a previously-captured per-file settings dict into the
        widgets — used when navigating back to a file the user already
        customized. Mirrors _apply_autodetect, but pulls widget values
        from *settings* instead of self._default_settings.
        """
        delim = _autodetect_delimiter(lines)
        decimal = _autodetect_decimal(lines, delim)
        threshold = settings.get('header_threshold', 0.5)
        header = _autodetect_header(lines, delim, decimal, threshold)

        widgets = (self._delim_combo, self._decimal_combo, self._header_combo,
                   self._header_threshold_spin, self._layout_standard,
                   self._layout_interlaced, self._layout_row,
                   self._padding_spin, self._analyze_spin,
                   self._index_x_cb)
        for w in widgets:
            w.blockSignals(True)

        # The X-axis conveniences are per-file (and, for a multi-sheet import,
        # per-sheet) choices like any other, so they must be restored along with
        # everything else — otherwise navigating to another file and back would
        # silently drop them.
        self._index_x_cb.setChecked(bool(settings.get('index_x', False)))

        stored_delim = settings.get('delimiter')
        self._delim_combo.setCurrentText(
            'Auto' if stored_delim is None else _DELIM_TO_DISPLAY.get(stored_delim, stored_delim)
        )
        self._detected_delimiter = delim

        stored_dec = settings.get('decimal_separator')
        self._decimal_combo.setCurrentText('Auto' if stored_dec is None else stored_dec)
        self._detected_decimal = decimal

        # Rebuild the 'Row N' entries for THIS file/sheet's sample BEFORE
        # trying to select one — otherwise a saved "Row N" (or "No header")
        # choice can't be found in the combo's still-stale item list (left
        # over from whichever sheet was previously being configured) and
        # setCurrentText() below silently fails to apply, leaving the
        # combo showing whatever it happened to already display. This was
        # the actual bug behind "Header row resets to Auto when switching
        # sheets": the old code below only ever tried 'Yes'/'No', neither
        # of which has been a real combo item since Header Row grew its
        # 'Row N' options — every restore of an explicit choice failed.
        self._populate_header_row_combo()
        stored_hdr = settings.get('header')
        stored_hdr_row = settings.get('header_row')
        if stored_hdr is None:
            self._header_combo.setCurrentText('Auto')
        elif stored_hdr is False:
            self._header_combo.setCurrentText('No header')
        elif stored_hdr_row is not None:
            self._header_combo.setCurrentText(f'Row {stored_hdr_row + 1}')
        else:
            # header=True with no specific row recorded — same as 'Row 1'.
            self._header_combo.setCurrentText('Row 1')
        self._detected_header = header

        self._header_threshold_spin.setValue(int(round(threshold * 100)))

        if settings.get('row_oriented'):
            self._layout_row.setChecked(True)
        elif settings.get('interlaced_format'):
            self._layout_interlaced.setChecked(True)
        else:
            self._layout_standard.setChecked(True)
        self._apply_layout_visibility()

        self._padding_spin.setValue(settings.get('zero_padding', 4))
        self._analyze_spin.setValue(settings.get('analyze_rows', 20))

        for w in widgets:
            w.blockSignals(False)

        # Column pickers must be repopulated from THIS file's tokens
        # (using the delimiter just restored above) before their saved
        # index/checks can be re-applied.
        self._populate_label_column_combo()
        self._populate_x_scale_column_combo()
        self._populate_exclude_columns_list()

        label_col = settings.get('label_column')
        self._label_column_combo.blockSignals(True)
        idx = 0 if label_col is None else label_col + 1
        if idx < self._label_column_combo.count():
            self._label_column_combo.setCurrentIndex(idx)
        self._label_column_combo.blockSignals(False)

        x_col = settings.get('x_scale_column')
        self._x_scale_column_combo.blockSignals(True)
        idx = 0 if x_col is None else x_col + 1
        if idx < self._x_scale_column_combo.count():
            self._x_scale_column_combo.setCurrentIndex(idx)
        self._x_scale_column_combo.blockSignals(False)

        exclude_cols = set(settings.get('exclude_columns') or [])
        self._exclude_columns_list.blockSignals(True)
        for i in range(self._exclude_columns_list.count()):
            item = self._exclude_columns_list.item(i)
            item.setCheckState(Qt.Checked if i in exclude_cols else Qt.Unchecked)
        self._exclude_columns_list.blockSignals(False)

        self._update_summary()

    def get_all_settings(self) -> List[dict]:
        """
        Return one resolved settings dict per selected file, in the same
        order as file_paths. Each entry reflects whatever that specific
        file was configured with while it was being previewed — files
        never visited keep whatever _apply_autodetect produced for them
        on first (and only) load.
        """
        self._capture_current_file_settings()
        return [self._file_settings.get(i, self.get_settings())
                for i in range(len(self._file_paths))]



    def _populate_profile_combo(self):
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        self._profile_combo.addItem("— Select a saved profile —")
        for name in self._profile_manager.list_profiles():
            self._profile_combo.addItem(name)
        self._profile_combo.setCurrentIndex(0)
        self._profile_combo.blockSignals(False)

    def _on_profile_selected(self, index: int):
        if index <= 0:
            return
        name = self._profile_combo.currentText()
        try:
            settings = self._profile_manager.load_profile(name)
        except KeyError:
            return
        self._apply_profile(settings)
        # Deliberately leave the dropdown showing the applied profile's
        # name (rather than resetting to the placeholder) as visible
        # confirmation that it actually applied. Note this is still a
        # one-shot copy, not an ongoing link — further edits to the
        # settings below do not get saved back into the profile.

    def _apply_profile(self, settings: dict):
        """
        Apply a saved profile's settings to the currently-displayed file.

        Handles the Sheet picker separately first — _apply_saved_settings
        deliberately doesn't touch it (a *file's* sheet restoration
        already happens in _load_file before that call runs) — since
        sheet_name is workbook-specific and this profile may have been
        saved from a different Excel file than the one currently open.
        Same silent-fallback-to-Auto behavior as elsewhere applies if the
        saved name doesn't match a sheet in this file.
        """
        if self._sheet_combo.isVisible():
            target_sheet = settings.get('sheet_name')
            self._sheet_combo.blockSignals(True)
            if target_sheet:
                found_idx = self._sheet_combo.findText(target_sheet)
                self._sheet_combo.setCurrentIndex(found_idx if found_idx >= 0 else 0)
            else:
                self._sheet_combo.setCurrentIndex(0)
            self._sheet_combo.blockSignals(False)
            filepath = self._file_paths[self._preview_file_index]
            self._sample_lines = _read_sample(
                filepath, n_lines=8, sheet_name=self._current_sheet_name()
            )

        self._apply_saved_settings(settings, self._sample_lines)
        self._capture_current_file_settings()
        self._refresh_preview()

    def _save_current_as_profile(self):
        name, ok = QInputDialog.getText(self, "Save Import Profile", "Profile name:")
        if not ok or not name.strip():
            return
        name = name.strip()

        if name in self._profile_manager.list_profiles():
            reply = QMessageBox.question(
                self, "Overwrite Profile",
                f'A profile named "{name}" already exists. Overwrite it?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        try:
            self._profile_manager.save_profile(name, self.get_settings())
        except (ValueError, RuntimeError) as e:
            QMessageBox.critical(self, "Save Failed", str(e))
            return

        self._populate_profile_combo()
        QMessageBox.information(self, "Saved", f'Profile "{name}" saved.')

    def _delete_selected_profile(self):
        idx = self._profile_combo.currentIndex()
        if idx <= 0:
            QMessageBox.information(self, "Delete Profile", "Select a profile to delete first.")
            return
        name = self._profile_combo.currentText()
        reply = QMessageBox.question(
            self, "Delete Profile",
            f'Delete the profile "{name}"? This cannot be undone.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._profile_manager.delete_profile(name)
        self._populate_profile_combo()

    def _reset_current_file_to_auto(self):
        """
        Discard this file's cached/customized settings and re-run
        auto-detection fresh — exactly the same code path a never-before-
        seen file goes through in _load_file, just triggered manually
        for a file that's already been (possibly) customized. Includes
        the Sheet picker (Excel files) — resetting to Auto re-reads the
        sample from the auto-selected sheet, not whichever sheet happened
        to be manually chosen before.
        """
        self._file_settings.pop(self._preview_file_index, None)

        # _apply_autodetect deliberately *preserves* whatever the
        # delimiter/decimal/header combos already show — that's what lets
        # a manual override carry forward as a convenience default for
        # the next *new* file. That's exactly backwards for a reset of
        # THIS file, so force them back to Auto here first.
        for combo in (self._delim_combo, self._decimal_combo, self._header_combo):
            combo.blockSignals(True)
            combo.setCurrentText('Auto')
            combo.blockSignals(False)

        if self._sheet_combo.isVisible():
            self._sheet_combo.blockSignals(True)
            self._sheet_combo.setCurrentIndex(0)
            self._sheet_combo.blockSignals(False)
            filepath = self._file_paths[self._preview_file_index]
            self._sample_lines = _read_sample(filepath, n_lines=8, sheet_name=None)

        self._apply_autodetect(self._sample_lines)
        self._populate_label_column_combo()
        self._populate_x_scale_column_combo()
        self._populate_exclude_columns_list()
        self._capture_current_file_settings()
        self._refresh_preview()

    def _apply_settings_to_all_files(self):
        """
        Copy the currently-displayed file's resolved settings onto every
        OTHER file in the batch — including files not yet previewed
        (which would otherwise get their own independent auto-detection)
        and files already customized differently (which get overwritten).
        Confirms first since the second case is destructive.

        Column-index settings (label_column, x_scale_column,
        exclude_columns) are copied verbatim. This is exactly right when
        every file shares the same column layout — the main use case —
        but if a target file has fewer columns, an index that's now out
        of range simply falls back to Auto when that file is next
        previewed (_apply_saved_settings already guards this), or, if
        never previewed again, surfaces as a clear per-file "out of
        range" import error rather than a silent misread.

        sheet_name behaves differently, by the underlying reader's
        existing design (not something introduced here): if the named
        sheet doesn't exist in a target Excel file, it silently falls
        back to auto-selection (spectra / first sheet) rather than
        raising — so a sheet name that doesn't apply to every file in the
        batch won't cause a visible error, just a possibly-unexpected
        sheet choice for that one file. Worth a quick check if your batch
        mixes Excel files with different sheet names.
        """
        n = len(self._file_paths)
        if n <= 1:
            return

        current_settings = self.get_settings()
        other_count = n - 1

        reply = QMessageBox.question(
            self,
            "Apply to All Other Files",
            f"Apply the current settings to all {other_count} other "
            f"file{'s' if other_count != 1 else ''} in this batch?\n\n"
            "This will overwrite any settings you've already customized "
            "individually for other files. Files not yet previewed will "
            "also start from these settings instead of their own "
            "auto-detection.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for i in range(n):
            if i == self._preview_file_index:
                continue
            self._file_settings[i] = dict(current_settings)

        QMessageBox.information(
            self,
            "Applied",
            f"Settings applied to {other_count} other "
            f"file{'s' if other_count != 1 else ''}."
        )

    def _apply_settings_to_all_sheets(self):
        """
        Copy the sheet currently being configured onto every OTHER sheet in
        this workbook — the explicit, opt-in counterpart to sheets otherwise
        defaulting back to Auto on their own (see _apply_autodetect's
        reset_separators docstring). Applies to every sheet listed, not just
        ticked ones, so a sheet you tick on later already has sensible
        settings waiting instead of starting from its own auto-detection.

        Mirrors _apply_settings_to_all_files: column-index settings are
        copied verbatim (right when sheets share a column layout, and
        harmlessly falls back to Auto for a target sheet with fewer columns
        — see that method's docstring), and confirmation is required since
        this overwrites any settings already customized per-sheet.
        """
        n = self._sheet_list.count()
        if n <= 1:
            return

        source_sheet = self._current_multi_sheet
        if not source_sheet:
            return

        # Capture the live widget state as this sheet's own settings first,
        # so what gets copied is exactly what's on screen right now.
        self._capture_current_sheet_settings()
        current_settings = dict(self._sheet_settings[(self._preview_file_index, source_sheet)])

        other_count = n - 1
        reply = QMessageBox.question(
            self,
            "Apply to All Sheets",
            f"Apply the settings for ‘{source_sheet}’ to all "
            f"{other_count} other sheet{'s' if other_count != 1 else ''} "
            f"in this workbook?\n\n"
            "This will overwrite any settings you've already customized "
            "individually for other sheets. Sheets not yet configured will "
            "also start from these settings instead of their own "
            "auto-detection.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for i in range(n):
            sheet_name = self._sheet_list.item(i).text()
            if sheet_name == source_sheet:
                continue
            target_settings = dict(current_settings)
            target_settings['sheet_name'] = sheet_name
            self._sheet_settings[(self._preview_file_index, sheet_name)] = target_settings

        QMessageBox.information(
            self,
            "Applied",
            f"Settings applied to {other_count} other "
            f"sheet{'s' if other_count != 1 else ''}."
        )

    def _on_file_list_row_changed(self, row: int):
        if row >= 0 and row != self._preview_file_index:
            self._load_file(row)

    def _prev_file(self):
        if self._preview_file_index > 0:
            self._load_file(self._preview_file_index - 1)

    def _next_file(self):
        if self._preview_file_index < len(self._file_paths) - 1:
            self._load_file(self._preview_file_index + 1)

    # ------------------------------------------------------------------
    # Auto-detection
    # ------------------------------------------------------------------

    def _redetect_from_sample(self, lines: list):
        """Recompute the cached auto-detected delimiter/decimal/header from
        *lines*, respecting any 'Auto' vs. manual combo-box overrides —
        the "Update detected cache" step shared by _apply_autodetect (full
        reset, e.g. on file load) and _on_analyze_rows_changed (same file,
        just a bigger/smaller sample window). Does not touch any other
        setting and does not itself refresh the preview."""
        delim   = _autodetect_delimiter(lines)
        decimal = _autodetect_decimal(lines, delim)
        threshold = self._default_settings.get('header_threshold', 0.5)
        header  = _autodetect_header(lines, delim, decimal, threshold)

        if self._delim_combo.currentText() == 'Auto':
            self._detected_delimiter = delim
        else:
            self._detected_delimiter = _DISPLAY_TO_DELIM.get(
                self._delim_combo.currentText(), '\t'
            )

        if self._decimal_combo.currentText() == 'Auto':
            self._detected_decimal = decimal
        else:
            self._detected_decimal = self._decimal_combo.currentText()

        if self._header_combo.currentText() == 'Auto':
            self._detected_header = header
        else:
            self._detected_header = bool(self._header_setting()[0])

    def _apply_autodetect(self, lines: list, reset_separators: bool = False):
        """Run auto-detection and set combo boxes, respecting 'Auto' overrides.

        By default this *preserves* whatever the delimiter/decimal/header
        combos already show — that lets a manual override on one file carry
        forward as a convenience starting point for the next never-configured
        file, the same convenience "Apply to All Other Files" formalizes as
        an explicit action. See _on_reset_to_autodetect for the file-level
        override of that (Reset to Auto-detected forces Auto first, then
        calls this).

        reset_separators=True instead forces delimiter/decimal/header back
        to 'Auto' before detecting — used when moving to an Excel sheet that
        has never been individually configured. Unlike files, silently
        inheriting a sibling sheet's manual override is actively dangerous:
        a header-row/delimiter choice picked for one sheet's odd layout
        (e.g. "Row 2" to skip a banner) can silently misparse a completely
        normal sheet that was never touched, with no visible sign anything
        is wrong. Auto-detection handles the common "sheets share a layout"
        case just as well without that risk, so sheets default to genuinely
        re-detecting on their own sample. Use the "Apply to All Sheets"
        button when you deliberately want one sheet's settings on every
        sheet.
        """
        # Block ALL interactive controls while we update values so that
        # no signal fires mid-update and triggers a premature _refresh_preview
        # (_padding_spin/_analyze_spin included — both now trigger a live
        # preview refresh of their own, see __init__'s connect() calls).
        autodetect_widgets = (
            self._delim_combo, self._decimal_combo, self._header_combo,
            self._layout_standard, self._layout_interlaced, self._layout_row,
            self._padding_spin, self._analyze_spin,
        )
        for w in autodetect_widgets:
            w.blockSignals(True)

        if reset_separators:
            self._delim_combo.setCurrentText('Auto')
            self._decimal_combo.setCurrentText('Auto')
            self._header_combo.setCurrentText('Auto')

        self._redetect_from_sample(lines)

        # Apply defaults for non-separator settings
        self._padding_spin.setValue(self._default_settings.get('zero_padding', 4))
        self._analyze_spin.setValue(self._default_settings.get('analyze_rows', 20))
        self._header_threshold_spin.setValue(
            int(round(self._default_settings.get('header_threshold', 0.5) * 100))
        )
        if self._default_settings.get('row_oriented', False):
            self._layout_row.setChecked(True)
        elif self._default_settings.get('interlaced_format', False):
            self._layout_interlaced.setChecked(True)
        else:
            self._layout_standard.setChecked(True)
        self._apply_layout_visibility()

        # Unblock all signals before updating summary
        for w in autodetect_widgets:
            w.blockSignals(False)

        self._update_summary()

    def _current_delimiter(self) -> str:
        """Return the effective delimiter for the current preview file,
        resolving 'Auto' to the detected value."""
        delim_text = self._delim_combo.currentText()
        if delim_text == 'Auto':
            return self._detected_delimiter
        return _DISPLAY_TO_DELIM.get(delim_text, delim_text)

    def _populate_column_combo(self, combo: QComboBox):
        """
        Refill *combo* from the first sample line of the current file,
        using the currently selected delimiter so the displayed columns
        match what the preview actually shows.

        Each entry shows both the index and the first-row value
        ('Column N: <value>') so columns with duplicate or missing names
        (e.g. two columns both called "Temperature") can still be told
        apart unambiguously. Shared by the label-column and X-scale-column
        pickers — they list the same raw columns, just for different roles.
        """
        delimiter = self._current_delimiter()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Auto (first column)")
        if self._sample_lines:
            # Same fix as the exclude-columns list: use the WIDEST sample row,
            # not the header row, so columns the header doesn't name are still
            # offered (they hold real data and must be selectable).
            rows = [_split_line(line, delimiter) for line in self._sample_lines]
            n_cols = max((len(r) for r in rows), default=0)
            header_tokens = rows[0] if rows else []
            for i in range(n_cols):
                tok = header_tokens[i] if i < len(header_tokens) else ''
                display = tok if tok else "(no name)"
                combo.addItem(f"Column {i + 1}: {display}")
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _populate_label_column_combo(self):
        self._populate_column_combo(self._label_column_combo)

    def _populate_x_scale_column_combo(self):
        self._populate_column_combo(self._x_scale_column_combo)

    def _populate_exclude_columns_list(self):
        """
        Refill the exclude-columns checklist from the first sample line,
        same 'Column N: <value>' format as the other pickers. Unlike the
        combos there's no 'Auto' entry — an unchecked list means nothing
        excluded.
        """
        delimiter = self._current_delimiter()
        self._exclude_columns_list.blockSignals(True)
        self._exclude_columns_list.clear()
        if self._sample_lines:
            # BUG FIX: this used to list only as many columns as the FIRST line
            # (the header) happened to have tokens for. A column with no header
            # name therefore never appeared in the list at all, so it could not
            # be excluded — even though it holds real data. (Trailing empty
            # header cells are also stripped when reading, which made the
            # last such columns vanish entirely.)
            #
            # The real column count is the WIDEST sample row, not the header
            # row, so use that and fall back to a clear "(no name)" caption for
            # columns the header doesn't name.
            rows = [_split_line(line, delimiter) for line in self._sample_lines]
            n_cols = max((len(r) for r in rows), default=0)
            header_tokens = rows[0] if rows else []
            for i in range(n_cols):
                tok = header_tokens[i] if i < len(header_tokens) else ''
                display = tok if tok else "(no name)"
                item = QListWidgetItem(f"Column {i + 1}: {display}")
                item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                item.setCheckState(Qt.Unchecked)
                self._exclude_columns_list.addItem(item)
        self._exclude_columns_list.blockSignals(False)

    def _current_exclude_columns(self) -> List[int]:
        """Zero-based indices of every checked row in the exclude list."""
        result = []
        for i in range(self._exclude_columns_list.count()):
            item = self._exclude_columns_list.item(i)
            if item.checkState() == Qt.Checked:
                result.append(i)
        return result

    def _apply_layout_visibility(self):
        """
        Show only the column picker(s) relevant to the currently selected
        Layout, hiding the rest entirely rather than merely greying them
        out — Label column only means something in Row-oriented; X-scale
        column and Exclude columns only mean something in Standard.
        """
        is_row = self._layout_row.isChecked()
        is_standard = self._layout_standard.isChecked()

        self._label_col_label.setVisible(is_row)
        self._label_column_combo.setVisible(is_row)

        self._x_col_label.setVisible(is_standard)
        self._x_scale_column_combo.setVisible(is_standard)
        self._exclude_col_label.setVisible(is_standard)
        self._exclude_columns_list.setVisible(is_standard)

    def _on_delimiter_changed(self, *_):
        """Value-separator combo changed — refresh whichever column
        picker(s) are currently active (column boundaries depend on the
        delimiter) then re-preview."""
        self._populate_header_row_combo()
        if self._layout_row.isChecked():
            self._populate_label_column_combo()
        elif self._layout_standard.isChecked():
            self._populate_x_scale_column_combo()
            self._populate_exclude_columns_list()
        self._on_settings_changed()

    def _on_layout_changed(self, checked):
        """Any Layout radio toggled — show/refresh whichever column
        picker(s) are meaningful for the newly selected layout and hide
        the rest. Fires once per radio per click (old one turning off,
        new one turning on); harmless since the work is idempotent."""
        self._apply_layout_visibility()
        self._populate_header_row_combo()
        if self._layout_row.isChecked():
            self._populate_label_column_combo()
        elif self._layout_standard.isChecked():
            self._populate_x_scale_column_combo()
            self._populate_exclude_columns_list()
        self._on_settings_changed()

    def _current_label_column(self) -> Optional[int]:
        """Combo index 0 = Auto (None); index N = raw-file column N-1."""
        idx = self._label_column_combo.currentIndex()
        return None if idx <= 0 else idx - 1

    def _current_x_scale_column(self) -> Optional[int]:
        """Combo index 0 = Auto (None); index N = raw-file column N-1."""
        idx = self._x_scale_column_combo.currentIndex()
        return None if idx <= 0 else idx - 1

    def _resolve_settings(self) -> dict:
        """
        Resolve settings for the PREVIEW — 'Auto' uses the detected value
        from the current file so the preview renders correctly.
        """
        delim_text = self._delim_combo.currentText()
        delimiter = self._detected_delimiter if delim_text == 'Auto' \
                    else _DISPLAY_TO_DELIM.get(delim_text, delim_text)

        dec_text = self._decimal_combo.currentText()
        decimal = self._detected_decimal if dec_text == 'Auto' else dec_text

        header, header_row = self._header_setting()

        return {
            'delimiter':         delimiter,
            'decimal_separator': decimal,
            'header':            header,
            'header_row':        header_row,
            'index_x':           self._index_x_cb.isChecked(),
            'zero_padding':      self._padding_spin.value(),
            'analyze_rows':      self._analyze_spin.value(),
            'interlaced_format': self._layout_interlaced.isChecked(),
            'row_oriented':      self._layout_row.isChecked(),
            'header_threshold':  self._header_threshold_spin.value() / 100.0,
            'label_column':      self._current_label_column(),
            'x_scale_column':    self._current_x_scale_column(),
            'exclude_columns':   self._current_exclude_columns(),
            'sheet_name':        self._current_sheet_name(),
            'spe_use_calibration': self._spe_calib_cb.isChecked(),
            'jws_selected_channels': self._current_jws_selected_channels(),
            'jws_channel_type_overrides': self._current_jws_channel_type_overrides(),
        }

    def get_settings(self) -> dict:
        """
        Settings for the IMPORTER, including PER-SHEET settings when several
        sheets are being imported at once.

        Different sheets of one workbook are usually different tables — a
        different layout, different metadata columns to exclude, a different
        header row. Forcing one set of settings onto all of them (which is what
        multi-sheet import did at first) is wrong for anything but the simplest
        workbook. So each ticked sheet keeps its own settings: select a sheet in
        the list to configure it, and the preview follows.

        The top-level keys still describe the CURRENTLY SELECTED sheet, so
        single-sheet import is completely unaffected. When several sheets are
        ticked, 'sheet_settings' maps each sheet name to its own full settings
        dict, and the importer uses those.
        """
        base = self._plain_settings()
        sheets = self._current_sheet_names()
        if sheets:
            self._capture_current_sheet_settings()
            per_sheet = {}
            for sh in sheets:
                saved = self._sheet_settings.get((self._preview_file_index, sh))
                per_sheet[sh] = dict(saved) if saved else dict(base)
                per_sheet[sh].pop('sheet_settings', None)
            base['sheet_settings'] = per_sheet
        return base

    def _plain_settings(self) -> dict:
        """
        Return settings for the IMPORTER.

        When delimiter or decimal is set to 'Auto', None is returned for that
        key so that read_table_data auto-detects each file independently.
        This is essential when importing multiple files that may have different
        separators — e.g. one dot-decimal and one comma-decimal file selected
        together.  A manually chosen value is applied to all files as-is.
        """
        delim_text = self._delim_combo.currentText()
        if delim_text == 'Auto':
            delimiter = None          # auto-detect per file
        else:
            delimiter = _DISPLAY_TO_DELIM.get(delim_text, delim_text)

        dec_text = self._decimal_combo.currentText()
        decimal = None if dec_text == 'Auto' else dec_text   # auto-detect per file

        header, header_row = self._header_setting()

        return {
            'delimiter':         delimiter,
            'decimal_separator': decimal,
            'header':            header,
            'header_row':        header_row,
            'index_x':           self._index_x_cb.isChecked(),
            'zero_padding':      self._padding_spin.value(),
            'analyze_rows':      self._analyze_spin.value(),
            'interlaced_format': self._layout_interlaced.isChecked(),
            'row_oriented':      self._layout_row.isChecked(),
            'header_threshold':  self._header_threshold_spin.value() / 100.0,
            'label_column':      self._current_label_column(),
            'x_scale_column':    self._current_x_scale_column(),
            'exclude_columns':   self._current_exclude_columns(),
            'sheet_name':        self._current_sheet_name(),
            # None unless "Import several sheets" is ticked. When set, the
            # importer reads EACH of these sheets with these same settings
            # (see import_controller._run_import) and ignores 'sheet_name'.
            'sheet_names':       self._current_sheet_names(),
            # Meaningless for text/Excel files (ignored by the importer for
            # those formats) — captured unconditionally anyway, same as
            # index_x above, so an SPE file's calibration choice survives
            # navigating away and back the same way every other per-file
            # setting does.
            'spe_use_calibration': self._spe_calib_cb.isChecked(),
            # Same reasoning, for JWS files' channel table. None (not a
            # JWS file currently on screen) is preserved as None rather
            # than [] — see _current_jws_selected_channels.
            'jws_selected_channels': self._current_jws_selected_channels(),
            'jws_channel_type_overrides': self._current_jws_channel_type_overrides(),
        }

    def _refresh_preview(self):
        # The "Row N" entries depend on the current sample lines, which change
        # whenever the file, sheet or layout changes. Rebuilding them here means
        # every one of those paths keeps the list correct without each having to
        # remember to do it.
        self._populate_header_row_combo()
        """Re-parse sample lines with current settings and populate the table."""
        if not self._sample_lines:
            self._preview_table.setRowCount(0)
            self._preview_table.setColumnCount(0)
            return

        settings  = self._resolve_settings()
        delimiter = settings['delimiter']
        decimal   = settings['decimal_separator']
        is_interlaced = settings['interlaced_format']
        is_row_oriented = settings['row_oriented']
        threshold = settings['header_threshold']

        # Effective X-scale column index for highlighting/labeling purposes.
        # Row-oriented data is already transposed+swapped below so its X is
        # always at index 0; Standard layout may point elsewhere if the
        # user picked a non-default X-scale column. Interlaced doesn't use
        # this (every even column is its own X by definition).
        x_col_display_idx = 0
        x_scale_exclude_conflict = False

        lines = list(self._sample_lines)

        if is_row_oriented:
            # Row-oriented data is the transpose of column data — transpose
            # the sample tokens here so the rest of this method (header
            # extraction, cyan/white highlighting, column labels) can be
            # reused completely unchanged, exactly as the real importer
            # reuses _parse_column_data after transposing.
            tokenized = [_split_line(l, delimiter) for l in lines if l.strip()]
            if tokenized:
                max_len = max(len(r) for r in tokenized)
                for r in tokenized:
                    r.extend([''] * (max_len - len(r)))

                label_col = settings['label_column']
                if label_col is not None and label_col != 0 and label_col < max_len:
                    for r in tokenized:
                        r[0], r[label_col] = r[label_col], r[0]

                transposed = [list(col) for col in zip(*tokenized)]
                lines = ['\t'.join(tok) for tok in transposed]
                delimiter = '\t'

        elif not is_interlaced:
            # Standard layout — apply Exclude columns / X-scale column the
            # same way the real importer does (_apply_standard_column_selection),
            # so the preview matches what will actually be parsed.
            x_scale_col = settings['x_scale_column']
            exclude_cols = settings['exclude_columns']
            if x_scale_col is not None and x_scale_col in exclude_cols:
                # Conflicting selection — show the raw columns unmodified
                # and let the summary line's warning explain why.
                x_scale_exclude_conflict = True
            elif exclude_cols or (x_scale_col is not None and x_scale_col != 0):
                tokenized = [_split_line(l, delimiter) for l in lines if l.strip()]
                if tokenized:
                    max_len = max(len(r) for r in tokenized)
                    for r in tokenized:
                        r.extend([''] * (max_len - len(r)))

                    exclude_set = set(c for c in exclude_cols if c < max_len)
                    kept_indices = [i for i in range(max_len) if i not in exclude_set]
                    if kept_indices:
                        effective_x = x_scale_col if x_scale_col is not None else kept_indices[0]
                        if effective_x in kept_indices:
                            new_x_pos = kept_indices.index(effective_x)
                            filtered = [[r[i] for i in kept_indices] for r in tokenized]
                            for r in filtered:
                                r[0], r[new_x_pos] = r[new_x_pos], r[0]
                            lines = ['\t'.join(r) for r in filtered]
                            delimiter = '\t'
                            x_col_display_idx = 0

        # Determine header. When the user has pointed at a specific header row,
        # the preview must show what the IMPORTER will see — i.e. everything
        # above that row discarded — otherwise the preview and the import
        # disagree, which is worse than no preview at all.
        hdr_flag, hdr_row = self._header_setting()
        if hdr_row is not None and 0 <= hdr_row < len(lines):
            lines = lines[hdr_row:]
        if hdr_flag is None:
            has_header = _autodetect_header(lines, delimiter, decimal, threshold)
        else:
            has_header = bool(hdr_flag)

        headers = []
        if has_header and lines:
            headers = _split_line(lines[0], delimiter)
            lines = lines[1:]

        # Parse rows
        rows = [_split_line(l, delimiter) for l in lines if l.strip()]
        if not rows:
            self._preview_table.setRowCount(0)
            return

        n_cols_actual = max(len(r) for r in rows)
        n_rows = len(rows)

        # Cap columns shown in preview to avoid freezing the UI for very wide
        # files (e.g. 4675 spectra = 4676 columns would create ~37k table cells)
        MAX_PREVIEW_COLS = 20
        n_cols = min(n_cols_actual, MAX_PREVIEW_COLS)
        truncated = n_cols_actual > MAX_PREVIEW_COLS

        self._preview_table.setRowCount(n_rows)
        self._preview_table.setColumnCount(n_cols)

        # Column headers
        if headers:
            # `headers` can be SHORTER than n_cols — e.g. an Excel header row
            # whose trailing cells are blank gets those trailing blanks
            # stripped (see _read_excel_sample), same as the real importer
            # does to its own header row. The real importer then falls back
            # to a running "spectrum counter" (zero-padded, not counting the
            # X column) for any Y column past the end of the header list or
            # with blank header text — see _parse_column_data. If we simply
            # sliced `headers` and handed it to Qt, the missing trailing
            # entries would silently fall back to Qt's own default section
            # numbering (1, 2, 3, ...) instead, which counts the X column
            # too and looks like a real (but wrong) header value — exactly
            # the "preview shows 3/4, import shows 0002/0003" mismatch this
            # fixes. Build the full list ourselves so the preview always
            # shows the same fallback text the importer will actually use.
            zero_padding = settings.get('zero_padding', 4)
            display_headers = []
            spectrum_counter = 0
            for i in range(n_cols):
                raw = headers[i] if i < len(headers) else ''
                if i == x_col_display_idx:
                    display_headers.append(raw)
                    continue
                spectrum_counter += 1
                if raw.strip():
                    display_headers.append(raw)
                else:
                    display_headers.append(str(spectrum_counter).zfill(zero_padding))
            self._preview_table.setHorizontalHeaderLabels(display_headers)
        else:
            if is_interlaced:
                col_labels = ['x' if i % 2 == 0 else 'y' for i in range(n_cols)]
            else:
                y_counter = 1
                col_labels = []
                for i in range(n_cols):
                    if i == x_col_display_idx:
                        col_labels.append('x')
                    else:
                        col_labels.append(f'y{y_counter}')
                        y_counter += 1
            self._preview_table.setHorizontalHeaderLabels(col_labels)

        # Fill cells; highlight x-column(s)
        for r_idx, row in enumerate(rows):
            for c_idx in range(n_cols):
                text = row[c_idx] if c_idx < len(row) else ''
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                if is_interlaced:
                    if c_idx % 2 == 0:
                        item.setBackground(Qt.GlobalColor.cyan)
                        item.setForeground(Qt.GlobalColor.darkBlue)
                else:
                    if c_idx == x_col_display_idx:
                        item.setBackground(Qt.GlobalColor.cyan)
                        item.setForeground(Qt.GlobalColor.darkBlue)

                self._preview_table.setItem(r_idx, c_idx, item)

        self._update_summary(n_cols_actual if truncated else None)

    def _update_summary(self, total_cols=None):
        """Update the one-line detection summary below the settings."""
        settings = self._resolve_settings()

        delim_display = _DELIM_TO_DISPLAY.get(settings['delimiter'], settings['delimiter'])
        dec = settings['decimal_separator']

        hdr_text = self._header_combo.currentText()
        threshold = settings['header_threshold']
        if hdr_text == 'Auto':
            if settings['row_oriented']:
                tokenized = [_split_line(l, settings['delimiter'])
                             for l in self._sample_lines if l.strip()]
                if tokenized:
                    max_len = max(len(r) for r in tokenized)
                    for r in tokenized:
                        r.extend([''] * (max_len - len(r)))
                    label_col = settings['label_column']
                    if label_col is not None and label_col != 0 and label_col < max_len:
                        for r in tokenized:
                            r[0], r[label_col] = r[label_col], r[0]
                    transposed_lines = ['\t'.join(col) for col in zip(*tokenized)]
                    auto_header = _autodetect_header(transposed_lines, '\t', dec, threshold)
                else:
                    auto_header = False
            elif not settings['interlaced_format'] and \
                    (settings['x_scale_column'] is not None or settings['exclude_columns']):
                # Standard layout with a non-default X-scale column and/or
                # excluded columns — mirror the real importer
                # (_apply_standard_column_selection): exclude first, then
                # swap the effective X-scale column into position 0,
                # before header detection.
                x_col = settings['x_scale_column']
                exclude_cols = settings['exclude_columns']
                if x_col is not None and x_col in exclude_cols:
                    # Conflicting selection — summary warning covers this;
                    # fall back to the raw, unmodified lines here.
                    auto_header = _autodetect_header(self._sample_lines, settings['delimiter'], dec, threshold)
                else:
                    tokenized = [_split_line(l, settings['delimiter'])
                                 for l in self._sample_lines if l.strip()]
                    if tokenized:
                        max_len = max(len(r) for r in tokenized)
                        for r in tokenized:
                            r.extend([''] * (max_len - len(r)))
                        exclude_set = set(c for c in exclude_cols if c < max_len)
                        kept_indices = [i for i in range(max_len) if i not in exclude_set]
                        if kept_indices:
                            effective_x = x_col if x_col is not None else kept_indices[0]
                            if effective_x in kept_indices:
                                new_x_pos = kept_indices.index(effective_x)
                                filtered = [[r[i] for i in kept_indices] for r in tokenized]
                                for r in filtered:
                                    r[0], r[new_x_pos] = r[new_x_pos], r[0]
                                swapped_lines = ['\t'.join(r) for r in filtered]
                                auto_header = _autodetect_header(swapped_lines, '\t', dec, threshold)
                            else:
                                auto_header = False
                        else:
                            auto_header = False
                    else:
                        auto_header = False
            else:
                auto_header = _autodetect_header(self._sample_lines, settings['delimiter'], dec, threshold)
            hdr_display = f"auto ({auto_header})"
        else:
            hdr_display = hdr_text.lower()

        if settings['row_oriented']:
            fmt = "row-oriented"
        elif settings['interlaced_format']:
            fmt = "interlaced"
        else:
            fmt = "standard"

        summary = (
            f"Detected:  delimiter = {delim_display}   |   "
            f"decimal = {dec}   |   "
            f"header = {hdr_display}   |   "
            f"format = {fmt}"
        )

        if hdr_text == 'Auto' and abs(threshold - 0.5) > 1e-9:
            summary += f"   |   header threshold = {int(round(threshold * 100))}%"

        if settings['row_oriented'] and settings['label_column'] is not None:
            summary += f"   |   label column = {settings['label_column'] + 1}"

        if (not settings['row_oriented'] and not settings['interlaced_format']
                and settings['x_scale_column'] is not None):
            summary += f"   |   x-scale column = {settings['x_scale_column'] + 1}"

        is_standard = not settings['row_oriented'] and not settings['interlaced_format']
        exclude_cols = settings['exclude_columns']
        x_col = settings['x_scale_column']

        if is_standard and exclude_cols:
            summary += f"   |   excluded columns = {len(exclude_cols)}"

        if total_cols is not None:
            n_spectra = total_cols - 1
            summary += f"   |   {total_cols} columns ({n_spectra} spectra) — preview capped at 20"

        if is_standard and x_col is not None and x_col in exclude_cols:
            summary += "   |   ⚠ X-scale column can't also be excluded — pick a different one"
            self._summary_label.setStyleSheet(
                "color:#8a0000; font-size:9pt; padding:2px 4px;"
                "background:#fff0f0; border-radius:3px; font-weight:bold;"
            )
        else:
            self._summary_label.setStyleSheet(
                "color:#444; font-size:9pt; padding:2px 4px;"
                "background:#f9f9f9; border-radius:3px;"
            )

        self._summary_label.setText(summary)

    # ------------------------------------------------------------------
    # Signal handler
    # ------------------------------------------------------------------

    def _on_settings_changed(self, *_):
        """Called whenever any control changes — refresh preview immediately.

        SPE/SPC files take a different path: _refresh_preview() only knows
        how to re-parse self._sample_lines (text/Excel sample rows), which
        is never populated for binary files (see _load_file) — calling it
        while an SPE/SPC preview is on screen would silently do nothing, or
        worse, redraw stale sample-line content left over from whichever
        text/Excel file was last shown. Zero padding is the only control
        that can actually change while a binary file is on screen, so route
        straight to that format's own preview loader instead.
        """
        if self._file_paths and self._has_loaded_once:
            filepath = self._file_paths[self._preview_file_index]
            ext = os.path.splitext(filepath)[1].lower()
            if ext == '.spe':
                self._load_spe_preview(
                    filepath,
                    use_calibration=self._spe_calib_cb.isChecked()
                    if self._spe_calib_cb.isVisible() else False,
                )
                return
            if ext == '.spc':
                self._load_spc_preview(filepath)
                return

        delim_text = self._delim_combo.currentText()
        if delim_text != 'Auto':
            self._detected_delimiter = _DISPLAY_TO_DELIM.get(delim_text, delim_text)

        dec_text = self._decimal_combo.currentText()
        if dec_text != 'Auto':
            self._detected_decimal = dec_text

        self._refresh_preview()

    def _on_analyze_rows_changed(self, *_):
        """'Rows to analyze' controls how many lines the auto-detection
        heuristics (and, for Excel, the preview table itself) actually look
        at. It used to have no live effect at all — changing it did nothing
        until Import was pressed — the same class of "setting changed but
        the preview doesn't reflect it" issue as zero-padding above. Re-read
        the sample at the new size and re-detect from it so the preview
        stays honest about what it's showing."""
        if not self._file_paths or not self._has_loaded_once:
            return
        filepath = self._file_paths[self._preview_file_index]
        is_excel = os.path.splitext(filepath)[1].lower() in ('.xlsx', '.xls', '.xlsm')
        self._sample_lines = _read_sample(
            filepath,
            n_lines=self._analyze_spin.value(),
            sheet_name=self._current_sheet_name() if is_excel else None,
        )
        self._redetect_from_sample(self._sample_lines)
        self._refresh_preview()

    def _show_help(self):
        """Open the help page in the user's browser."""
        open_help_topic(self, 'import')
