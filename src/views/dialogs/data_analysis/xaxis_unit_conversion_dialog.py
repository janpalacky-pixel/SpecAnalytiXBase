# src/views/dialogs/data_analysis/xaxis_unit_conversion_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
                              QPushButton, QComboBox, QLabel, QTableWidget,
                              QTableWidgetItem, QHeaderView, QAbstractItemView,
                              QMessageBox, QSizePolicy)
from PyQt5.QtCore import Qt
import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    compute_distinguishing_labels, make_display_text_delegate, make_shorten_names_checkbox,
)
from src.modules.data_analysis.xaxis_unit_conversion_manager import (
    XAxisUnitConversionManager, UNIT_CHOICES, UNIT_LABELS, UNIT_SHORT,
)

logger = get_logger(__name__)

COL_SPECTRUM = 0
COL_CURRENT_RANGE = 1
COL_NEW_RANGE = 2


class XAxisUnitConversionDialog(QDialog):
    """Dialog for converting a spectrum's x-axis between wavelength (nm),
    wavenumber (cm^-1), energy (eV), and frequency (Hz).

    Unlike CD Unit Conversion, there is no per-spectrum table of values
    to enter — from_unit/to_unit are pure physics, shared across the
    whole batch — so this dialog is a simple From/To picker plus a live
    preview table showing each spectrum's range before and after.

    Follows the same shell as CDUnitConversionDialog / XAxisAlignmentDialog:
    modal, no minimize button, Apply / Add as New commit directly via
    commit_callback (no separate Run step).
    """

    def __init__(self, parent=None, current_settings=None, controller=None,
                 selected_spectra=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle("X-axis Unit Conversion")
        self.current_settings = current_settings or {}
        self.controller = controller
        # Fixed snapshot of the spectra to convert, taken when the dialog
        # opened — safe because this dialog is modal, so the main window's
        # selection can't change underneath it while it's open.
        self.selected_spectra = list(selected_spectra or [])
        self.commit_callback = commit_callback
        self.manager = XAxisUnitConversionManager()

        # Modal, but with the minimize button disabled — every modal
        # dialog in this app follows this same convention.
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setModal(True)
        self.setMinimumSize(600, 480)
        self.resize(680, 560)

        self._setup_ui()
        self._populate_from_settings(self.current_settings)
        self._update_preview()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- Convert ---------------------------------------------------
        convert_group = QGroupBox("Convert")
        convert_layout = QFormLayout()

        self.from_combo = QComboBox()
        self.to_combo = QComboBox()
        for key in UNIT_CHOICES:
            self.from_combo.addItem(UNIT_LABELS[key], userData=key)
            self.to_combo.addItem(UNIT_LABELS[key], userData=key)
        self.from_combo.setCurrentIndex(0)   # nm
        self.to_combo.setCurrentIndex(1)     # cm-1
        self.from_combo.currentIndexChanged.connect(self._update_preview)
        self.to_combo.currentIndexChanged.connect(self._update_preview)

        from_row = QHBoxLayout()
        from_row.addWidget(self.from_combo)
        convert_layout.addRow("From:", from_row)

        to_row = QHBoxLayout()
        to_row.addWidget(self.to_combo)
        self.swap_button = QPushButton("⇄  Swap")
        self.swap_button.setToolTip("Swap the From and To units.")
        self.swap_button.setAutoDefault(False)
        self.swap_button.clicked.connect(self._on_swap)
        to_row.addWidget(self.swap_button)
        convert_layout.addRow("To:", to_row)

        convert_group.setLayout(convert_layout)
        layout.addWidget(convert_group)

        # --- Preview -----------------------------------------------------
        preview_group = QGroupBox(f"Preview — {len(self.selected_spectra)} spectra")
        preview_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout = QVBoxLayout()

        # Display-only "shorten names" toggle — this dialog's own,
        # independent on/off state (see label_shortening.py's
        # make_shorten_names_checkbox), unrelated to the main window's
        # checkbox and always starting unchecked.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _state: self.table.viewport().update())
        preview_layout.addWidget(self.checkBox_shorten_names)

        self.table = QTableWidget(len(self.selected_spectra), 3)
        self.table.setHorizontalHeaderLabels(["Spectrum", "Current range", "New range"])
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_SPECTRUM, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_CURRENT_RANGE, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_NEW_RANGE, QHeaderView.Stretch)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        for row, spec in enumerate(self.selected_spectra):
            name_item = QTableWidgetItem(spec.get('label', '?'))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_SPECTRUM, name_item)
            for col in (COL_CURRENT_RANGE, COL_NEW_RANGE):
                item = QTableWidgetItem("")
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, col, item)

        # Display-only "shorten names" — mirrors the main window's
        # checkBox_shorten_names, same pattern as every other operation
        # dialog's spectra list/table (see label_shortening.py).
        self.table.setItemDelegateForColumn(
            COL_SPECTRUM, make_display_text_delegate(self._display_labels_map, parent=self.table))

        preview_layout.addWidget(self.table, 1)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #C62828; font-weight: bold;")
        preview_layout.addWidget(self.status_label)

        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group, 1)

        # --- Info text -----------------------------------------------------
        info_label = QLabel(
            "Converting reorders each spectrum's points so the new x-axis is "
            "still ascending (an application-wide requirement) — the same "
            "points, just read left to right in the new unit. See Help for "
            "the formulas and what this operation does NOT cover (e.g. "
            "Raman shift, which needs the excitation laser wavelength)."
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
        self.apply_button.setToolTip("Replace the selected spectra with their x-axis converted.")
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

    # ------------------------------------------------------------------
    # Shorten names (display-only) — this dialog's own independent
    # checkbox (see _setup_ui), no longer tied to the main window's.
    # ------------------------------------------------------------------
    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _display_labels_map(self):
        if not self._shorten_names_enabled():
            return {}
        labels = [s.get('label', '') for s in self.selected_spectra]
        if len(labels) < 2:
            return {}
        return compute_distinguishing_labels(labels)

    # ------------------------------------------------------------------
    # Preview / validation
    # ------------------------------------------------------------------
    def _on_swap(self):
        from_idx = self.from_combo.currentIndex()
        to_idx = self.to_combo.currentIndex()
        self.from_combo.setCurrentIndex(to_idx)
        self.to_combo.setCurrentIndex(from_idx)
        # _update_preview fires automatically via currentIndexChanged

    def _update_preview(self, *_):
        from_unit = self.from_combo.currentData()
        to_unit = self.to_combo.currentData()
        self.manager.from_unit = from_unit
        self.manager.to_unit = to_unit

        # Column headers carry the unit symbol, updated live — this is
        # what makes Swap's effect visible even when the bare NUMBERS in
        # a range happen to come out identical after swapping (this is a
        # real, expected occurrence whenever one of the two units is
        # wavelength: nm<->cm-1, nm<->eV, and nm<->Hz all use the exact
        # same reciprocal formula in both directions — "unit = k / nm"
        # and "nm = k / unit" — so re-running it on the same raw numbers
        # gives the same output range either way, just meaning something
        # different. Without the unit shown right on the header, that
        # looked exactly like Swap doing nothing.
        self.table.setHorizontalHeaderLabels([
            "Spectrum",
            f"Current range ({UNIT_SHORT[from_unit]})",
            f"New range ({UNIT_SHORT[to_unit]})",
        ])

        errors = []
        for row, spec in enumerate(self.selected_spectra):
            x = spec.get('x_scale', [])
            if len(x) == 0:
                self.table.item(row, COL_CURRENT_RANGE).setText("(empty)")
                self.table.item(row, COL_NEW_RANGE).setText("(empty)")
                continue

            x = np.asarray(x, dtype=float)
            self.table.item(row, COL_CURRENT_RANGE).setText(
                f"{np.min(x):.4g} – {np.max(x):.4g}"
            )

            if np.any(x <= 0) and from_unit != to_unit:
                self.table.item(row, COL_NEW_RANGE).setText("invalid (x ≤ 0)")
                errors.append(spec.get('label', '?'))
                continue

            try:
                new_x = self.manager.convert_x_values(x, from_unit, to_unit)
                self.table.item(row, COL_NEW_RANGE).setText(
                    f"{np.min(new_x):.4g} – {np.max(new_x):.4g}"
                )
            except Exception as exc:
                self.table.item(row, COL_NEW_RANGE).setText("error")
                errors.append(f"{spec.get('label', '?')} ({exc})")

        if errors:
            names = ', '.join(errors)
            self.status_label.setText(
                f"Cannot convert — non-positive x-axis value(s) in: {names}."
            )
        else:
            self.status_label.setText("")

        can_apply = not errors and bool(self.selected_spectra)
        self.apply_button.setEnabled(can_apply)
        self.add_as_new_button.setEnabled(can_apply)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _populate_from_settings(self, settings):
        from_unit = settings.get('from_unit', UNIT_CHOICES[0])
        to_unit = settings.get('to_unit', UNIT_CHOICES[1])
        idx = self.from_combo.findData(from_unit)
        if idx >= 0:
            self.from_combo.setCurrentIndex(idx)
        idx = self.to_combo.findData(to_unit)
        if idx >= 0:
            self.to_combo.setCurrentIndex(idx)

    def get_settings(self):
        return {
            'from_unit': self.from_combo.currentData(),
            'to_unit': self.to_combo.currentData(),
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

        settings = self.get_settings()
        if settings['from_unit'] == settings['to_unit']:
            confirm_same = QMessageBox.question(
                self, "Same Unit",
                "The From and To units are the same, so this would have no "
                "effect. Continue anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if confirm_same != QMessageBox.Yes:
                return

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

    def show_help(self):
        try:
            from src.help.xaxis_unit_conversion_help import (
                get_xaxis_unit_conversion_help_content,
                get_xaxis_unit_conversion_help_title,
            )
            from src.help.help_window import show_help_window

            content = get_xaxis_unit_conversion_help_content()
            title = get_xaxis_unit_conversion_help_title()
            show_help_window(self, title, content)
        except Exception as e:
            logger.debug(f"Could not show help: {e}")
            QMessageBox.information(self, "Help",
                                     "Help documentation is not available at this time.")
