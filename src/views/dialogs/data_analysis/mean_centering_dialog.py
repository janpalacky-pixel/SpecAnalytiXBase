# src/views/dialogs/data_analysis/mean_centering_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                              QPushButton, QCheckBox, QLabel, QTableWidget,
                              QTableWidgetItem, QHeaderView, QAbstractItemView,
                              QMessageBox, QSizePolicy)
from PyQt5.QtCore import Qt
import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    compute_distinguishing_labels, make_display_text_delegate, make_shorten_names_checkbox,
)
from src.modules.data_analysis.mean_centering_manager import MeanCenteringManager

logger = get_logger(__name__)

COL_SPECTRUM = 0
COL_ORIGINAL_RANGE = 1
COL_CENTERED_RANGE = 2


class MeanCenteringDialog(QDialog):
    """Dialog for ensemble mean-centering: subtract the average spectrum
    of the selected batch from every spectrum in it.

    Unlike Normalization, CD Unit Conversion, or X-axis Unit Conversion,
    there is no tunable numeric parameter to pick — the only setting is
    whether to also emit the computed ensemble mean spectrum itself as an
    extra output. So this dialog is a live preview table (showing each
    spectrum's y-range before/after) plus that one checkbox.

    Follows the same shell as XAxisUnitConversionDialog: modal, no
    minimize button, Apply / Add as New commit directly via
    commit_callback (no separate Run step).
    """

    def __init__(self, parent=None, current_settings=None, controller=None,
                 selected_spectra=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Mean-Center Spectra (Dataset)")
        self.current_settings = current_settings or {}
        self.controller = controller
        # Fixed snapshot of the spectra to center, taken when the dialog
        # opened — safe because this dialog is modal, so the main
        # window's selection can't change underneath it while it's open.
        self.selected_spectra = list(selected_spectra or [])
        self.commit_callback = commit_callback
        self.manager = MeanCenteringManager()

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

        # --- Info text -----------------------------------------------------
        info_label = QLabel(
            "Computes the average spectrum across the selected batch (the "
            "per-wavelength mean, one value per wavelength) and subtracts "
            "it from every spectrum in the batch. This is the same step "
            "the PCA / SVD dialogs perform internally when their "
            "'Mean-center' checkbox is on — exposed here as its own "
            "operation, independent of running any decomposition. See "
            "Help for how this differs from Normalization's per-spectrum "
            "'Mean Centering' mode."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #1565C0;")
        layout.addWidget(info_label)

        # --- Settings ---------------------------------------------------
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()
        self.include_mean_cb = QCheckBox("Also add the ensemble mean spectrum as a new spectrum")
        self.include_mean_cb.setToolTip(
            "Adds one extra spectrum — the computed average that was "
            "subtracted from everything else — useful as a reference or "
            "QC artifact. Always added, regardless of the Apply / Add as "
            "New choice below."
        )
        self.include_mean_cb.stateChanged.connect(lambda _s: self._update_preview())
        settings_layout.addWidget(self.include_mean_cb)
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

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
        self.table.setHorizontalHeaderLabels(["Spectrum", "Original Y range", "Centered Y range"])
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_SPECTRUM, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_ORIGINAL_RANGE, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_CENTERED_RANGE, QHeaderView.Stretch)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        for row, spec in enumerate(self.selected_spectra):
            name_item = QTableWidgetItem(spec.get('label', '?'))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_SPECTRUM, name_item)
            for col in (COL_ORIGINAL_RANGE, COL_CENTERED_RANGE):
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

        # --- Buttons -------------------------------------------------------
        button_layout = QHBoxLayout()

        self.help_button = QPushButton("Help")
        self.help_button.setAutoDefault(False)
        self.help_button.clicked.connect(self.show_help)
        button_layout.addWidget(self.help_button)

        button_layout.addStretch()

        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Replace the selected spectra with their mean-centered result.")
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        button_layout.addWidget(self.apply_button)

        self.add_as_new_button = QPushButton("Add as New")
        self.add_as_new_button.setToolTip(
            "Keep the original spectra unchanged and add the mean-centered\n"
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
    def _update_preview(self, *_):
        for row, spec in enumerate(self.selected_spectra):
            y = spec.get('y_scale', [])
            if len(y) == 0:
                self.table.item(row, COL_ORIGINAL_RANGE).setText("(empty)")
            else:
                y = np.asarray(y, dtype=float)
                self.table.item(row, COL_ORIGINAL_RANGE).setText(f"{np.min(y):.4g} – {np.max(y):.4g}")
            self.table.item(row, COL_CENTERED_RANGE).setText("")

        errors = []
        try:
            self.manager.validate_shared_x_axis(self.selected_spectra)
            centered = self.manager.compute_centered_spectra(list(self.selected_spectra))
            for row, spec in enumerate(centered):
                y = np.asarray(spec['y_scale'], dtype=float)
                self.table.item(row, COL_CENTERED_RANGE).setText(f"{np.min(y):.4g} – {np.max(y):.4g}")
        except ValueError as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append(f"Could not compute preview: {exc}")

        if len(self.selected_spectra) < 2:
            self.status_label.setText(
                "Only one spectrum is selected — its 'mean' is itself, so the "
                "centered result would be exactly zero everywhere. Select at "
                "least two spectra for a meaningful result."
            )
        elif errors:
            self.status_label.setText(errors[0])
        else:
            self.status_label.setText("")

        can_apply = not errors and len(self.selected_spectra) >= 1
        self.apply_button.setEnabled(can_apply)
        self.add_as_new_button.setEnabled(can_apply)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _populate_from_settings(self, settings):
        self.include_mean_cb.setChecked(bool(settings.get('include_mean_spectrum', False)))

    def get_settings(self):
        return {
            'include_mean_spectrum': self.include_mean_cb.isChecked(),
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
        action = ("add the mean-centered result as new spectra" if add_as_new
                  else "replace the selected spectra with their mean-centered result")
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
            from src.help.mean_centering_help import (
                get_mean_centering_help_content,
                get_mean_centering_help_title,
            )
            from src.help.help_window import show_help_window

            content = get_mean_centering_help_content()
            title = get_mean_centering_help_title()
            show_help_window(self, title, content)
        except Exception as e:
            logger.debug(f"Could not show help: {e}")
            QMessageBox.information(self, "Help",
                                     "Help documentation is not available at this time.")
