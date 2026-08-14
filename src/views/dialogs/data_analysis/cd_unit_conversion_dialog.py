# src/views/dialogs/data_analysis/cd_unit_conversion_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
                              QPushButton, QComboBox, QLabel, QTableWidget,
                              QTableWidgetItem, QHeaderView, QAbstractItemView,
                              QMessageBox, QRadioButton, QButtonGroup, QApplication,
                              QSizePolicy, QShortcut)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key
from src.modules.utils.label_shortening import (
    compute_distinguishing_labels, make_display_text_delegate, make_shorten_names_checkbox,
)
from src.modules.data_analysis.cd_unit_conversion_manager import CDUnitConversionManager

logger = get_logger(__name__)

# Table column indices — kept as module constants since several methods
# (paste/copy/delete, column show/hide, validation) all need to agree on
# which column is which.
COL_SPECTRUM = 0
COL_PATH_LENGTH = 1
COL_CONCENTRATION = 2
COL_MOLECULAR_WEIGHT = 3
COL_NUM_RESIDUES = 4
EDITABLE_COLUMNS = (COL_PATH_LENGTH, COL_CONCENTRATION, COL_MOLECULAR_WEIGHT, COL_NUM_RESIDUES)


class CDUnitConversionDialog(QDialog):
    """Dialog for converting raw millidegree CD spectra to molar/mean-
    residue ellipticity, differential molar extinction coefficient
    (Delta-epsilon), or differential absorbance (Delta-A).

    Path length, concentration, and molecular weight are entered PER
    SPECTRUM in an Excel-like table (real CD experiments routinely vary
    concentration and/or path length from spectrum to spectrum within one
    batch — a titration series, or several samples each measured once).
    Concentration unit, ellipticity convention, and output type stay
    single shared controls below the table.

    Follows the same shell as SavitzkyGolayDialog / XAxisAlignmentDialog:
    modal, no minimize button, Apply / Add as New commit directly via
    commit_callback (no separate Run step).
    """

    def __init__(self, parent=None, current_settings=None, controller=None,
                 selected_spectra=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle("CD Unit Conversion")
        self.current_settings = current_settings or {}
        self.controller = controller
        # Fixed snapshot of the spectra to convert, taken when the dialog
        # opened — safe because this dialog is modal, so the main window's
        # selection can't change underneath it while it's open.
        self.selected_spectra = list(selected_spectra or [])
        self.commit_callback = commit_callback

        # Modal, but with the minimize button disabled — every modal
        # dialog in this app follows this same convention (see
        # ReferenceMatchingDialog, XAxisAlignmentDialog, and the rest of
        # the minimize-button audit).
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setModal(True)
        self.setMinimumSize(640, 520)
        self.resize(760, 640)

        self._setup_ui()
        self._populate_from_settings(self.current_settings)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- Per-spectrum sample parameters table ------------------------
        # This IS the "which spectra are selected" display too — no
        # separate read-only list alongside it — so there's only one
        # place showing spectrum names, and it's the one you actually
        # enter values into.
        table_group = QGroupBox(f"Sample parameters — {len(self.selected_spectra)} spectra")
        table_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_layout = QVBoxLayout()

        unit_row = QHBoxLayout()
        unit_row.addWidget(QLabel("Concentration unit (applies to the whole table):"))
        self.concentration_unit_combo = QComboBox()
        # Molar units first — this is the common case (e.g. DNA/RNA
        # concentration determined from A260 absorbance), and needs no
        # molecular weight at all. 'mg/mL' is listed last since it's the
        # one case that DOES need a molecular weight, purely to convert
        # to a molar concentration.
        self.concentration_unit_combo.addItems(list(CDUnitConversionManager.CONCENTRATION_UNITS))
        self.concentration_unit_combo.currentTextChanged.connect(self._update_field_states)
        unit_row.addWidget(self.concentration_unit_combo)
        unit_row.addStretch()
        self.concentration_help_btn = self._make_help_button(self.show_concentration_help)
        unit_row.addWidget(self.concentration_help_btn)
        table_layout.addLayout(unit_row)

        hint_label = QLabel(
            "Type directly, or select cells and use Ctrl+C / Ctrl+X / Ctrl+V / Delete — "
            "including pasting from an external spreadsheet. Pasting one value onto\n"
            "several selected cells fills all of them (click a column header to select "
            "the whole column first)."
        )
        hint_label.setStyleSheet("color: #666; font-size: 11px;")
        table_layout.addWidget(hint_label)

        # Display-only "shorten names" toggle — this dialog's own,
        # independent on/off state (see label_shortening.py's
        # make_shorten_names_checkbox), unrelated to the main window's
        # checkbox and always starting unchecked.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _state: self.table.viewport().update())
        table_layout.addWidget(self.checkBox_shorten_names)

        self.table = QTableWidget(len(self.selected_spectra), 5)
        self.table.setHorizontalHeaderLabels(
            ["Spectrum", "Path length (cm)", "Concentration", "Molecular weight (g/mol)",
             "Residues/Nucleotides (N)"]
        )
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_SPECTRUM, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_PATH_LENGTH, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_CONCENTRATION, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_MOLECULAR_WEIGHT, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_NUM_RESIDUES, QHeaderView.Stretch)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        for row, spec in enumerate(self.selected_spectra):
            name_item = QTableWidgetItem(spec.get('label', '?'))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_SPECTRUM, name_item)
            for col in EDITABLE_COLUMNS:
                self.table.setItem(row, col, QTableWidgetItem(""))

        # Display-only "shorten names" — mirrors the main window's
        # checkBox_shorten_names, same as every other operation dialog's
        # spectra list/table (see label_shortening.py). This is a
        # paint-only delegate: QTableWidgetItem.text() (what
        # spectrum_key()/_read_per_spectrum/get_settings/clipboard copy
        # all read) always keeps the full, original label regardless of
        # what's shown on screen, so identity and the settings dict this
        # dialog produces are completely unaffected by whether the
        # checkbox happens to be on.
        self.table.setItemDelegateForColumn(
            COL_SPECTRUM, make_display_text_delegate(self._display_labels_map, parent=self.table))

        self._install_clipboard_shortcuts()

        table_layout.addWidget(self.table, 1)

        self.mw_status_label = QLabel()
        self.mw_status_label.setStyleSheet("color: #777; font-size: 11px;")
        self.mw_status_label.setWordWrap(True)
        table_layout.addWidget(self.mw_status_label)

        table_group.setLayout(table_layout)
        # Stretch factor 1 so this group claims the extra vertical space
        # when the dialog is resized/maximized — the table is the whole
        # point of the dialog, so it (not empty margin) should grow.
        layout.addWidget(table_group, 1)

        # --- Output --------------------------------------------------------
        # Placed BEFORE Concentration basis (below) so that group's "the
        # output above" wording is literally true — Concentration basis
        # only applies to [θ]/Δε, chosen right here.
        output_group = QGroupBox("Output")
        output_layout = QFormLayout()
        self.output_combo = QComboBox()
        for key in CDUnitConversionManager.OUTPUT_CHOICES:
            name, unit = CDUnitConversionManager.OUTPUT_LABELS[key]
            self.output_combo.addItem(f"{name}  [{unit}]", userData=key)
        self.output_combo.currentIndexChanged.connect(self._update_field_states)
        output_layout.addRow("Convert to:", self.output_combo)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # --- Concentration basis (relevant for [theta] AND Delta-epsilon,
        # since [theta] = 3298 x Delta-epsilon regardless of which
        # concentration basis was used to compute both — see
        # cd_unit_conversion_manager.py's module docstring) -------------
        self.convention_group = QGroupBox("Concentration basis (for [θ] / Δε output)")
        convention_layout = QVBoxLayout()

        # The '?' button lives in its own row, OUTSIDE the radios' enabled
        # state — the group itself is never disabled (see below), only the
        # two radio buttons are, so this button stays clickable regardless
        # of which output is currently selected. Reaching for
        # convention_group.setEnabled(False) here would look tidy but
        # actually disables every descendant widget including this button,
        # since Qt's effective-enabled state is the AND of the whole
        # ancestor chain — a child's own setEnabled(True) can't override a
        # disabled parent.
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Only used when the output above is [θ] or Δε:"))
        header_row.addStretch()
        self.convention_help_btn = self._make_help_button(self.show_convention_help)
        header_row.addWidget(self.convention_help_btn)
        convention_layout.addLayout(header_row)

        self.molecular_radio = QRadioButton("Molecular / per-strand (whole molecule)")
        self.mean_residue_radio = QRadioButton(
            "Mean-residue / mean-nucleotide — divide by N "
            "(enter N per spectrum in the table above)"
        )
        self.molecular_radio.setChecked(True)
        convention_button_group = QButtonGroup(self)
        convention_button_group.addButton(self.molecular_radio)
        convention_button_group.addButton(self.mean_residue_radio)
        convention_layout.addWidget(self.molecular_radio)
        convention_layout.addWidget(self.mean_residue_radio)

        self.molecular_radio.toggled.connect(self._update_field_states)
        self.mean_residue_radio.toggled.connect(self._update_field_states)

        self.convention_group.setLayout(convention_layout)
        layout.addWidget(self.convention_group)

        # --- Info text -----------------------------------------------------
        info_label = QLabel(
            "Assumes the selected spectra's y-axis is raw ellipticity in "
            "millidegrees (mdeg) — the standard raw output of a CD "
            "spectropolarimeter. See Help for the formulas and references."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #1565C0;")
        layout.addWidget(info_label)

        # --- Buttons -------------------------------------------------------
        button_layout = QHBoxLayout()

        self.help_button = QPushButton("Help")
        self.help_button.setAutoDefault(False)
        self.help_button.clicked.connect(self.show_help)
        button_layout.addWidget(self.help_button)

        button_layout.addStretch()

        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Replace the selected spectra with their converted result.")
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        button_layout.addWidget(self.apply_button)

        self.add_as_new_button = QPushButton("Add as New")
        self.add_as_new_button.setToolTip(
            "Keep the original spectra unchanged and add the converted\n"
            "results to the list under new names."
        )
        self.add_as_new_button.setAutoDefault(False)
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        button_layout.addWidget(self.add_as_new_button)

        self.close_button = QPushButton("Close")
        self.close_button.setAutoDefault(False)
        self.close_button.clicked.connect(self.reject)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

        self._update_field_states()

    # ------------------------------------------------------------------
    # Shorten names (display-only) — this dialog's own independent
    # checkbox (see _setup_ui), no longer tied to the main window's.
    # ------------------------------------------------------------------
    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _display_labels_map(self):
        """{full_label: display_label} for every row of self.selected_spectra
        — called on every paint by the delegate installed on the Spectrum
        column (see _setup_ui), so it always reflects the checkbox's
        CURRENT state without needing to reinstall anything when it's
        toggled. Grouped across self.selected_spectra only, matching what
        this dialog's own table actually shows (not the whole app's
        spectra list) — the same scoping used by every other per-dialog
        table shortening in this app."""
        if not self._shorten_names_enabled():
            return {}
        labels = [s.get('label', '') for s in self.selected_spectra]
        if len(labels) < 2:
            return {}
        return compute_distinguishing_labels(labels)

    @staticmethod
    def _make_help_button(slot):
        """Small orange '?' button that opens a focused context-help popup
        for one specific field/group — same style and pattern as the
        Coefficient X-axis help button in SVD Analysis
        (xaxis_help_btn/show_xaxis_help). Used here instead of cramming a
        long explanation into a tooltip, which is hard to read as one
        unbroken line."""
        btn = QPushButton("?")
        btn.setFixedWidth(24)
        btn.setToolTip("Help for this setting")
        btn.setStyleSheet(
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
        btn.setAutoDefault(False)
        btn.clicked.connect(slot)
        return btn

    # ------------------------------------------------------------------
    # Excel-like clipboard support for the table
    # ------------------------------------------------------------------
    def _install_clipboard_shortcuts(self):
        """Copy/Cut/Paste/Delete on the table, scoped to editable cells
        only (the read-only Spectrum column is never touched). Mirrors
        the pattern already used for SVD Analysis's parameter-entry table
        (ParameterEntryDialog), extended from one column to a full 2D
        block so it behaves like pasting a spreadsheet range into Excel."""
        table = self.table

        def selected_editable_items():
            return [it for it in table.selectedItems() if it.column() in EDITABLE_COLUMNS]

        def do_copy():
            items = selected_editable_items()
            if not items:
                return
            rows = sorted(set(it.row() for it in items))
            cols = sorted(set(it.column() for it in items))
            lines = []
            for r in rows:
                cells = []
                for c in cols:
                    cell = table.item(r, c)
                    cells.append(cell.text() if cell else "")
                lines.append("\t".join(cells))
            QApplication.clipboard().setText("\n".join(lines))

        def do_delete():
            for it in selected_editable_items():
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
            grid = [ln.split('\t') for ln in rows_text]

            selected = selected_editable_items()
            if not selected:
                return
            sel_rows = sorted(set(it.row() for it in selected))
            sel_cols = sorted(set(it.column() for it in selected))

            # Pasting a SINGLE clipboard value onto a MULTI-cell selection
            # fills every selected cell with that one value — matches
            # Excel's behaviour, and is the direct way to "copy one value
            # to some or all spectra": copy a single cell, select the
            # target cells (a column, a range, or the whole column via
            # its header), paste.
            if len(grid) == 1 and len(grid[0]) == 1 and len(selected) > 1:
                value = grid[0][0].strip()
                for it in selected:
                    it.setText(value)
                return

            # Otherwise paste the block starting at the top-left selected
            # cell, same as pasting a spreadsheet range into Excel.
            start_row, start_col = sel_rows[0], sel_cols[0]
            for i, row_vals in enumerate(grid):
                r = start_row + i
                if r >= table.rowCount():
                    break
                for j, val in enumerate(row_vals):
                    c = start_col + j
                    if c not in EDITABLE_COLUMNS:
                        continue
                    cell = table.item(r, c)
                    if cell is None:
                        cell = QTableWidgetItem()
                        table.setItem(r, c, cell)
                    cell.setText(val.strip())

        QShortcut(QKeySequence.Copy, table).activated.connect(do_copy)
        QShortcut(QKeySequence.Cut, table).activated.connect(do_cut)
        QShortcut(QKeySequence.Paste, table).activated.connect(do_paste)
        QShortcut(QKeySequence.Delete, table).activated.connect(do_delete)

    # ------------------------------------------------------------------
    # Field enable/disable/show-hide logic — only ask the user for what
    # the currently selected output actually needs.
    # ------------------------------------------------------------------
    def _set_column_enabled(self, col, enabled):
        """Grey out (and make read-only) every cell in *col* when the
        current output type doesn't need it, e.g. path length/
        concentration for Delta-A — visually consistent with how every
        other disabled control in this dialog behaves."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, col)
            if item is None:
                continue
            flags = item.flags()
            if enabled:
                item.setFlags(flags | Qt.ItemIsEnabled | Qt.ItemIsEditable)
            else:
                item.setFlags(flags & ~Qt.ItemIsEnabled & ~Qt.ItemIsEditable)

    def _update_field_states(self, *_):
        output_key = self.output_combo.currentData()
        needs_concentration = output_key != CDUnitConversionManager.OUTPUT_DELTA_A
        # The molecular/mean-residue concentration basis choice applies
        # equally to [θ] and Δε (both are derived from the same molar
        # concentration, just scaled by a fixed constant — see
        # CDUnitConversionManager's module docstring for why the N
        # division carries through identically to both). It's meaningless
        # for ΔA, which never involves concentration at all.
        needs_convention = needs_concentration

        unit = self.concentration_unit_combo.currentText()
        # Molecular weight is ONLY relevant when concentration is entered
        # as a mass concentration (mg/mL) — it's needed purely to convert
        # that to a molar concentration. When concentration is already
        # molar (M / mM / µM), the column is hidden entirely: both Δε and
        # [θ] (either convention) use the molar concentration directly
        # and never need a molecular weight in that case.
        needs_mw = needs_concentration and unit == 'mg/mL'

        use_mean_residue = self.mean_residue_radio.isChecked()
        needs_residues = needs_convention and use_mean_residue

        self._set_column_enabled(COL_PATH_LENGTH, needs_concentration)
        self._set_column_enabled(COL_CONCENTRATION, needs_concentration)
        self.table.setColumnHidden(COL_MOLECULAR_WEIGHT, not needs_mw)
        self.table.setColumnHidden(COL_NUM_RESIDUES, not needs_residues)

        if needs_mw:
            self.mw_status_label.setText(
                "Both Concentration and Molecular weight are required together: "
                "Molecular weight only converts that row's mg/mL value into a molar "
                "concentration — it doesn't replace the Concentration entry itself."
            )
        elif needs_concentration:
            self.mw_status_label.setText(
                "Molecular weight column hidden — not needed for a molar "
                "concentration unit (M / mM / µM)."
            )
        else:
            self.mw_status_label.setText(
                "Path length and concentration are greyed out — ΔA is computed "
                "directly from the raw signal alone, independent of concentration unit."
            )

        # Only the two radio buttons are disabled when the convention
        # doesn't apply — never the whole convention_group — so its '?'
        # help button (see _setup_ui) stays clickable no matter which
        # output is selected.
        self.molecular_radio.setEnabled(needs_convention)
        self.mean_residue_radio.setEnabled(needs_convention)

    # ------------------------------------------------------------------
    # Settings <-> table
    # ------------------------------------------------------------------
    def _populate_from_settings(self, settings):
        unit = settings.get('concentration_unit', 'µM')
        if unit in CDUnitConversionManager.CONCENTRATION_UNITS:
            self.concentration_unit_combo.setCurrentText(unit)
        if settings.get('ellipticity_convention') == CDUnitConversionManager.CONVENTION_MEAN_RESIDUE:
            self.mean_residue_radio.setChecked(True)
        else:
            self.molecular_radio.setChecked(True)
        output_key = settings.get('output_type', CDUnitConversionManager.OUTPUT_MOLAR_ELLIPTICITY)
        idx = self.output_combo.findData(output_key)
        if idx >= 0:
            self.output_combo.setCurrentIndex(idx)

        # Restore per-spectrum values by stable identity, so values
        # entered for a spectrum survive reopening the dialog even if the
        # current selection differs from last time (e.g. one more
        # spectrum added). Path length defaults to 1.0 cm (a common
        # cuvette) for rows with nothing stored yet; concentration,
        # molecular weight, and residue/nucleotide count default to
        # blank, forcing a deliberate entry rather than silently reusing
        # an arbitrary placeholder number.
        per_spectrum = settings.get('per_spectrum', {})
        for row, spec in enumerate(self.selected_spectra):
            key = spectrum_key(spec)
            params = per_spectrum.get(key)
            path_length_text = f"{params['path_length_cm']:g}" if params and params.get('path_length_cm') else "1"
            conc_text = f"{params['concentration_value']:g}" if params and params.get('concentration_value') else ""
            mw_text = f"{params['molecular_weight']:g}" if params and params.get('molecular_weight') else ""
            residues_text = f"{params['num_residues']:g}" if params and params.get('num_residues') else ""
            self.table.item(row, COL_PATH_LENGTH).setText(path_length_text)
            self.table.item(row, COL_CONCENTRATION).setText(conc_text)
            self.table.item(row, COL_MOLECULAR_WEIGHT).setText(mw_text)
            self.table.item(row, COL_NUM_RESIDUES).setText(residues_text)

        self._update_field_states()

    def _read_per_spectrum(self):
        """Parse the table into {spectrum_key: {...}}. Returns
        (per_spectrum_dict, errors) — errors is a list of human-readable
        strings for any cell that isn't a valid number; the caller
        decides whether to block the commit on those."""
        per_spectrum = {}
        errors = []
        col_names = {
            COL_PATH_LENGTH: 'path length',
            COL_CONCENTRATION: 'concentration',
            COL_MOLECULAR_WEIGHT: 'molecular weight',
            COL_NUM_RESIDUES: 'residues/nucleotides count',
        }
        for row, spec in enumerate(self.selected_spectra):
            label = spec.get('label', '?')
            values = {}
            for col, field in (
                (COL_PATH_LENGTH, 'path_length_cm'),
                (COL_CONCENTRATION, 'concentration_value'),
                (COL_MOLECULAR_WEIGHT, 'molecular_weight'),
                (COL_NUM_RESIDUES, 'num_residues'),
            ):
                item = self.table.item(row, col)
                text = item.text().strip() if item else ""
                if not text:
                    values[field] = 0.0
                    continue
                try:
                    values[field] = float(text)
                except ValueError:
                    errors.append(f"Row {row + 1} ('{label}'): {col_names[col]} '{text}' is not a number.")
                    values[field] = 0.0
            per_spectrum[spectrum_key(spec)] = values
        return per_spectrum, errors

    def get_settings(self):
        convention = (
            CDUnitConversionManager.CONVENTION_MEAN_RESIDUE if self.mean_residue_radio.isChecked()
            else CDUnitConversionManager.CONVENTION_MOLECULAR
        )
        per_spectrum, _errors = self._read_per_spectrum()
        return {
            'concentration_unit': self.concentration_unit_combo.currentText(),
            'ellipticity_convention': convention,
            'output_type': self.output_combo.currentData(),
            'per_spectrum': per_spectrum,
        }

    # ------------------------------------------------------------------
    # Commit / help
    # ------------------------------------------------------------------
    def _on_commit_clicked(self, add_as_new):
        if self.commit_callback is None:
            QMessageBox.critical(
                self, "Not Available",
                "This dialog was opened without a way to apply changes. "
                "Please reopen it via Parameters."
            )
            return

        per_spectrum, errors = self._read_per_spectrum()
        if errors:
            QMessageBox.warning(
                self, "Invalid Table Values",
                "Please fix the following before converting:\n\n" + "\n".join(errors)
            )
            return

        settings = self.get_settings()

        action = ("add the converted result as new spectra" if add_as_new
                  else "replace the selected spectra with their converted result")
        confirm = QMessageBox.question(
            self, "Confirm", f"{action[0].upper() + action[1:]}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(settings, add_as_new, list(self.selected_spectra))
        if success:
            QMessageBox.information(self, "Done", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Could Not Apply", message)

    def show_concentration_help(self):
        """Context help for the Concentration column — explains why
        molecular weight is only sometimes needed, and the two workflows
        this supports (nucleic-acid-style molar concentration, vs.
        protein-style mass concentration), triggered by the '?' button
        next to the concentration unit selector."""
        QMessageBox.information(
            self, "Concentration — Help",
            "<html><body style='font-family: Arial, sans-serif; font-size: 12px;'>"
            "<p>This operation supports two different ways of specifying "
            "concentration, matching two common workflows:</p>"
            "<p><b>1. Concentration already in a molar unit (M / mM / µM).</b> "
            "Typical for nucleic acids, where concentration is usually "
            "determined directly from A260 absorbance and a known or "
            "estimated extinction coefficient. <b>No molecular weight is "
            "needed at all</b> — the molecular weight column is hidden, "
            "because it cancels out of the formulas once concentration is "
            "already molar.</p>"
            "<p><b>2. Concentration in mg/mL, with a molecular weight.</b> "
            "Typical for proteins, where concentration is often determined "
            "by mass (A280, BCA/Bradford assay) and the molecular weight is "
            "known from the sequence. Switch the unit to mg/mL and the "
            "molecular weight column reappears — it's used once per row, "
            "purely to convert that row's mass concentration to mol/L. "
            "After that conversion, both workflows use exactly the same "
            "formulas.</p>"
            "<p><b>The Concentration column is always required</b> — molecular "
            "weight is never a substitute for it. Molecular weight only tells "
            "the app how to convert a row's mg/mL number into a molar "
            "concentration; the mg/mL number itself (how much of the sample "
            "is actually in solution) still has to be entered separately, "
            "since it isn't a property of the molecule the way molecular "
            "weight is.</p>"
            "<p>Either path is equally valid; pick whichever matches how "
            "you actually determined your samples' concentration. The unit "
            "applies to every row — if some spectra were quantified in "
            "mg/mL and others in a molar unit, convert them in two "
            "separate passes.</p>"
            "</body></html>"
        )

    def show_convention_help(self):
        """Context help for the Concentration basis group, triggered by
        the '?' button at the top of the group — deliberately placed
        outside the two radio buttons' enabled/disabled state, so it stays
        clickable no matter which output is currently selected (see
        _update_field_states)."""
        QMessageBox.information(
            self, "Concentration Basis — Help",
            "<html><body style='font-family: Arial, sans-serif; font-size: 12px;'>"
            "<p>This choice applies equally to <b>both</b> [θ] and Δε — not "
            "just [θ] — because [θ] = 3298 × Δε holds no matter which "
            "concentration basis was used to compute both sides of that "
            "equation. It has no meaning for ΔA, which never involves "
            "concentration at all, which is why the two radio buttons are "
            "greyed out for that output (the '?' button itself stays active "
            "either way).</p>"
            "<p><b>Molecular / per-strand (whole molecule)</b> needs nothing "
            "beyond each row's path length and concentration — it's simply "
            "[θ] = θ_obs / (10 × l × c[M]) and Δε = θ_obs / (32980 × l × "
            "c[M]), using c[M] as the concentration of the whole molecule "
            "(one mole per strand/molecule). This is the natural choice "
            "for samples of precisely known, defined length, e.g. "
            "synthetic oligonucleotides or a well-characterized protein.</p>"
            "<p><b>Mean-residue / mean-nucleotide</b> divides that "
            "whole-molecule value by <b>N</b>, the number of amino-acid "
            "residues (protein/peptide) or nucleotides (DNA/RNA) in the "
            "molecule — a plain count, read directly from the sequence "
            "length. This is the standard way to compare molecules of "
            "different length on an equal footing, and applies the same "
            "division to Δε as it does to [θ]: entering a per-residue "
            "concentration (c[M] × N) instead of a per-strand one divides "
            "both quantities by N identically.</p>"
            "<p>If your concentration unit is mg/mL, this is a normal "
            "two-step calculation using two independent numbers: "
            "Molecular weight converts your mg/mL entry to a molar "
            "concentration c[M] (step 1), and — separately — N divides "
            "the resulting θ or Δε for the mean-residue basis (step 2). "
            "Nothing needs to 'cancel out' between them; they answer two "
            "different questions. Some older CD workflows instead skip "
            "step 1's ordinary molecular weight and ask for a single "
            "'mean residue weight' (MRW = molecular weight ÷ N) to convert "
            "mg/mL straight to a per-residue concentration in one step. "
            "That gives the identical final number, but requires looking "
            "up or computing MRW yourself; entering the molecule's normal "
            "molecular weight and N as two separate values (what this "
            "dialog does) needs nothing extra to look up.</p>"
            "<p><b>N is entered per spectrum</b>, in the 'Residues/Nucleotides "
            "(N)' column of the table above (shown only when this convention "
            "is selected) — so a batch can freely mix molecules of different "
            "length, or different molecules entirely, in one conversion.</p>"
            "</body></html>"
        )

    def show_help(self):
        try:
            from src.help.cd_unit_conversion_help import (
                get_cd_unit_conversion_help_content,
                get_cd_unit_conversion_help_title,
            )
            from src.help.help_window import show_help_window

            content = get_cd_unit_conversion_help_content()
            title = get_cd_unit_conversion_help_title()
            show_help_window(self, title, content)
        except Exception as e:
            logger.debug(f"Could not show help: {e}")
            QMessageBox.information(self, "Help",
                                     "Help documentation is not available at this time.")
