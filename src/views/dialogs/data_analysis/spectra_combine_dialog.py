# src/views/dialogs/data_analysis/spectra_combine_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                              QRadioButton, QLineEdit, QDialogButtonBox,
                              QLabel, QListWidget, QButtonGroup, QPushButton,
                              QMessageBox, QFileDialog, QSizePolicy, QCheckBox)
from PyQt5.QtCore import QTimer, Qt

from src.help.spectra_combine_help import (get_combine_spectra_help_content,
                                           get_combine_spectra_help_title)
from src.help.help_window import show_help_window
from src.modules.data_analysis.spectra_combine_manager import CombineSpectraManager
from src.modules.utils.label_shortening import make_shortened_name_delegate, make_shorten_names_checkbox

# Reuses the same preview canvas the Spectral Calculator uses (debounced
# redraw, empty/error states already handled there) rather than
# duplicating that matplotlib boilerplate for a second, simpler dialog.
from src.views.dialogs.data_analysis.spectral_calculator_dialog import (
    SpectralCalculatorPlotCanvas,
)


class CombineSpectraDialog(QDialog):
    """Dialog for configuring spectra combine (average / sum) operations.

    Follows the same pattern as the Spectral Calculator dialog: output
    mode (add new vs. replace) is decided centrally by the main window's
    "Add as new" checkbox at Apply time, not duplicated as a setting in
    here, and a live preview shows the result before committing to
    anything.
    """

    def __init__(self, parent=None, selected_spectra=None, num_selected=0,
                 current_settings=None, commit_callback=None, main_controller=None):
        super().__init__(parent)
        self.setWindowTitle("Combine Spectra")
        self.setModal(True)
        self.resize(700, 650)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowMaximizeButtonHint
        )

        self._main_controller = main_controller
        self.selected_spectra = selected_spectra or []
        self.current_settings = current_settings or {}
        self.manager = CombineSpectraManager()
        self._last_result = None
        # Bound method (OperationsController.commit_spectral_arithmetic)
        # passed in by whatever opened this dialog, so Apply / Add as New
        # can commit the result directly, without a separate Run step.
        self.commit_callback = commit_callback

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(200)
        self._preview_timer.timeout.connect(self._do_update_preview)

        self.setup_ui(num_selected)
        self.load_settings()
        self._update_preview()

    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def setup_ui(self, num_selected):
        layout = QVBoxLayout(self)

        info_label = QLabel(
            "Creates a new spectrum by averaging or summing the selected spectra. "
            "All selected spectra must have an identical x-axis."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            'background-color: #E3F2FD; color: #1976D2; '
            'padding: 6px; border-radius: 3px; font-style: italic;'
        )
        layout.addWidget(info_label)

        spectra_group = QGroupBox(f"Selected Spectra ({num_selected} items)")
        spectra_layout = QVBoxLayout(spectra_group)

        preview_only_note = QLabel(
            '\U0001F4A1 This selection is for preview only \u2014 the operation '
            'always combines all spectra selected in the main window. Use '
            'this list to choose which individual spectra are also drawn '
            'alongside the result below.'
        )
        preview_only_note.setWordWrap(True)
        preview_only_note.setStyleSheet(
            'background-color: #E3F2FD; color: #1976D2; '
            'padding: 5px; border-radius: 3px; font-size: 11px;'
        )
        spectra_layout.addWidget(preview_only_note)

        # Bug fix (2026-09-04): created BEFORE setItemDelegate below, not
        # after. addItems()/setMaximumHeight() on spectra_list can trigger
        # an immediate paint, which calls _shorten_names_enabled() via the
        # delegate's initStyleOption() - if that ran while this attribute
        # didn't exist yet, it raised AttributeError from inside a Qt
        # virtual method override, which PyQt5 reports and then aborts the
        # whole app on (a real, confirmed crash - see label_shortening.py's
        # own initStyleOption for the general-case guard against the same
        # class of bug; this fixes the actual trigger for this dialog too).
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _: self.spectra_list.viewport().update()
        )

        self.spectra_list = QListWidget()
        self.spectra_list.addItems([s['label'] for s in self.selected_spectra])
        self.spectra_list.setSelectionMode(QListWidget.ExtendedSelection)
        # Display-only "shorten names" — item.text() (what selection
        # matching in _do_update_preview reads) is untouched by this
        # paint-only delegate.
        self.spectra_list.setItemDelegate(
            make_shortened_name_delegate(self.spectra_list, self._shorten_names_enabled)
        )
        # Capped to roughly 5 visible rows (scrollable beyond that) so this
        # reference list doesn't compete with Preview for vertical space —
        # Preview is what the user actually needs room to see.
        row_h = self.spectra_list.sizeHintForRow(0) if self.spectra_list.count() else 18
        self.spectra_list.setMaximumHeight(row_h * 5 + 2 * self.spectra_list.frameWidth())
        self.spectra_list.itemSelectionChanged.connect(self._update_preview)
        spectra_layout.addWidget(self.spectra_list)

        btn_row = QHBoxLayout()
        select_all_btn = QPushButton('Select all')
        select_all_btn.clicked.connect(self._select_all)
        btn_row.addWidget(select_all_btn)
        clear_btn = QPushButton('Clear')
        clear_btn.clicked.connect(self._unselect_all)
        btn_row.addWidget(clear_btn)
        self.show_selected_cb = QCheckBox('Show selected spectra with result')
        self.show_selected_cb.setChecked(False)
        self.show_selected_cb.stateChanged.connect(self._update_preview)
        btn_row.addWidget(self.show_selected_cb)
        self.show_legend_cb = QCheckBox('Show legend')
        self.show_legend_cb.setChecked(False)
        self.show_legend_cb.stateChanged.connect(self._on_legend_visibility_changed)
        btn_row.addWidget(self.show_legend_cb)
        # (created earlier, before spectra_list's delegate was installed -
        # see the comment up there; just placed into the layout here)
        btn_row.addWidget(self.checkBox_shorten_names)
        btn_row.addStretch()
        spectra_layout.addLayout(btn_row)

        layout.addWidget(spectra_group)

        operation_group = QGroupBox("Operation")
        op_layout = QHBoxLayout(operation_group)
        self.op_button_group = QButtonGroup(self)

        self.average_radio = QRadioButton("Average Spectra")
        self.op_button_group.addButton(self.average_radio)
        op_layout.addWidget(self.average_radio)

        self.sum_radio = QRadioButton("Sum Spectra")
        self.op_button_group.addButton(self.sum_radio)
        op_layout.addWidget(self.sum_radio)

        # Only meaningful for Average — variance around a Sum isn't a
        # standard quantity, so this is disabled (not just unchecked)
        # when Sum is selected, to make that clear rather than silently
        # doing nothing.
        self.show_variance_cb = QCheckBox('Show \u00b11 std-dev band')
        self.show_variance_cb.setChecked(False)
        self.show_variance_cb.setToolTip(
            'Shades the region one standard deviation above and below the '
            'average, computed across the selected spectra at each point.'
        )
        self.show_variance_cb.stateChanged.connect(self._update_preview)
        op_layout.addWidget(self.show_variance_cb)

        self.average_radio.toggled.connect(self._on_operation_toggled)
        self.sum_radio.toggled.connect(self._on_operation_toggled)
        layout.addWidget(operation_group)

        # Output settings — name only. Add-vs-replace is decided by the
        # main window's "Add as new" checkbox at Apply time, same as the
        # Spectral Calculator and every other operation, so it isn't
        # duplicated as a setting here.
        output_group = QGroupBox("Output")
        out_layout = QHBoxLayout(output_group)
        out_layout.addWidget(QLabel("New spectrum name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setText(f"Avg_of_{num_selected}_spectra")
        self.name_edit.textChanged.connect(self._update_preview)
        out_layout.addWidget(self.name_edit)
        layout.addWidget(output_group)

        # Live preview
        preview_group = QGroupBox("Preview")
        preview_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        preview_layout = QVBoxLayout(preview_group)
        self.preview_canvas = SpectralCalculatorPlotCanvas()
        self.preview_canvas.legend_visible = False  # matches show_legend_cb's default (unchecked)
        preview_layout.addWidget(self.preview_canvas)
        layout.addWidget(preview_group, 1)

        button_box = QDialogButtonBox()
        help_button = QPushButton("Help")
        save_button = QPushButton("Save\u2026")
        save_button.setToolTip(
            'Save the current preview result to a file, without closing '
            'this dialog or applying the operation to the main spectrum list.'
        )
        self.apply_button = QPushButton('Apply')
        self.apply_button.setToolTip(
            'Replace the source spectra with the combined result.'
        )
        self.add_as_new_button = QPushButton('Add as New')
        self.add_as_new_button.setToolTip(
            'Keep the source spectra unchanged and add the combined result '
            'to the list under a new name.'
        )
        self.close_button = QPushButton('Close')
        button_box.addButton(help_button, QDialogButtonBox.HelpRole)
        button_box.addButton(save_button, QDialogButtonBox.ActionRole)
        button_box.addButton(self.apply_button, QDialogButtonBox.ActionRole)
        button_box.addButton(self.add_as_new_button, QDialogButtonBox.ActionRole)
        button_box.addButton(self.close_button, QDialogButtonBox.RejectRole)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        button_box.rejected.connect(self.reject)
        help_button.clicked.connect(self.show_help)
        save_button.clicked.connect(self._save_preview_spectrum)
        layout.addWidget(button_box)

    def _on_operation_toggled(self):
        is_average = self.average_radio.isChecked()
        self.show_variance_cb.setEnabled(is_average)
        if not is_average:
            self.show_variance_cb.setChecked(False)
        self._update_preview()

    def _on_legend_visibility_changed(self, state):
        self.preview_canvas.set_legend_visible(state == Qt.Checked)

    def _select_all(self):
        self.spectra_list.blockSignals(True)
        for i in range(self.spectra_list.count()):
            self.spectra_list.item(i).setSelected(True)
        self.spectra_list.blockSignals(False)
        self._update_preview()

    def _unselect_all(self):
        self.spectra_list.blockSignals(True)
        for i in range(self.spectra_list.count()):
            self.spectra_list.item(i).setSelected(False)
        self.spectra_list.blockSignals(False)
        self._update_preview()

    def load_settings(self):
        """Load settings into the UI controls."""
        if not self.current_settings:
            self.average_radio.setChecked(True)
            return

        op_type = self.current_settings.get('operation_type', 'average')
        if op_type == 'sum':
            self.sum_radio.setChecked(True)
        else:
            self.average_radio.setChecked(True)

        name = self.current_settings.get('new_spectrum_name')
        if name:
            self.name_edit.setText(name)

    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — validates the name field (same check
        get_settings() already enforces), then commits directly via
        commit_callback. The dialog closes itself once the commit
        succeeds.
        """
        settings = self.get_settings()
        if settings is None:
            QMessageBox.warning(self, 'No Name', 'Please enter a name for the result spectrum.')
            return

        if self.commit_callback is None:
            QMessageBox.critical(
                self, 'Not Available',
                'This dialog was opened without a way to apply changes. '
                'Please reopen it via Parameters.'
            )
            return

        action = 'add the combined result as a new spectrum' if add_as_new else 'replace the source spectra with the combined result'
        confirm = QMessageBox.question(
            self, 'Confirm', f'{action[0].upper() + action[1:]}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        settings['source_labels'] = [s['label'] for s in self.selected_spectra]
        success, message = self.commit_callback(settings, add_as_new, list(self.selected_spectra))
        if success:
            QMessageBox.information(self, 'Done', message)
            self.accept()
        else:
            QMessageBox.warning(self, 'Could Not Apply', message)

    def show_help(self):
        content = get_combine_spectra_help_content()
        title = get_combine_spectra_help_title()
        show_help_window(self, title, content)

    def get_settings(self):
        if not self.name_edit.text().strip():
            return None

        return {
            'operation_type': 'average' if self.average_radio.isChecked() else 'sum',
            'new_spectrum_name': self.name_edit.text().strip(),
        }

    # =================================================================
    # Live preview
    # =================================================================
    def _update_preview(self, *_args):
        """Request a preview recompute, debounced so toggling the
        operation or retyping the name doesn't recompute on every event."""
        if not hasattr(self, 'preview_canvas'):
            return
        self._preview_timer.start()

    def _do_update_preview(self):
        if len(self.selected_spectra) < 2:
            self.preview_canvas.show_message(
                'Select at least two spectra to combine.'
            )
            return

        error = self.manager.validate(self.selected_spectra)
        if error:
            self.preview_canvas.show_message(error)
            return

        # The operation itself always combines every spectrum selected in
        # the main window (self.selected_spectra) — this list selection
        # is preview-only and never changes what gets combined.
        operation_type = 'sum' if self.sum_radio.isChecked() else 'average'
        try:
            result = self.manager.perform_operation(self.selected_spectra, operation_type)
        except Exception as e:
            self.preview_canvas.show_message(f'Error: {e}')
            return

        name = self.name_edit.text().strip() or 'Calculator_result'
        result['label'] = name
        self._last_result = result

        plot_list = [result]
        if self.show_selected_cb.isChecked():
            selected_labels = {item.text() for item in self.spectra_list.selectedItems()}
            individuals = [s for s in self.selected_spectra if s['label'] in selected_labels]
            # Result drawn last so its line isn't hidden underneath
            # individual source spectra when both are shown.
            plot_list = individuals + [result]

        self.preview_canvas.plot_spectra(plot_list)

        if (self.show_variance_cb.isChecked()
                and self.show_variance_cb.isEnabled()
                and result.get('y_std') is not None):
            ax = self.preview_canvas.axes
            ax.fill_between(
                result['x_scale'],
                result['y_scale'] - result['y_std'],
                result['y_scale'] + result['y_std'],
                color='#1f77b4', alpha=0.2, label='\u00b11 std dev',
                zorder=0,
            )
            if self.show_legend_cb.isChecked():
                ax.legend(loc='best', fontsize='small')
            self.preview_canvas.draw()

    # =================================================================
    # Save
    # =================================================================
    def _save_preview_spectrum(self):
        """
        Export the current preview result using the same save pipeline as
        the Spectral Calculator's Save button (SaveOptionsDialog +
        SaveManager) — the same one used by Normalization's "Save
        selected spectra..." and by File > Save in the main window. Does
        not apply the operation or close this dialog.
        """
        to_save = [self._last_result] if getattr(self, '_last_result', None) else []
        if not to_save:
            QMessageBox.information(
                self, 'Nothing to save',
                'There is no valid preview result to save right now. '
                'Select at least two spectra with an identical x-axis first.'
            )
            return

        from src.views.dialogs.misc.save_spectra_dialog import SaveOptionsDialog
        from src.modules.misc.save_spectra_manager import SaveManager

        dialog = SaveOptionsDialog(self)
        dialog.setWindowTitle('Save Combine Result')
        dialog.fmt_snapshot.setVisible(False)

        if dialog.exec_() != QDialog.Accepted:
            return

        settings = dialog.get_settings()
        save_manager = SaveManager()

        if settings['mode'] == 'table':
            ext = '.xlsx' if settings['format'] == 'excel' else '.txt'
            file_filter = (
                'Excel Files (*.xlsx);;All Files (*.*)' if settings['format'] == 'excel'
                else 'Text Files (*.txt);;CSV Files (*.csv);;All Files (*.*)'
            )
            file_path, _ = QFileDialog.getSaveFileName(
                self, 'Save Combine Result', '', file_filter
            )
            if not file_path:
                return
            import os
            root_path, current_ext = os.path.splitext(file_path)
            if not current_ext:
                file_path = root_path + ext

            try:
                save_manager.save_table(to_save, file_path, settings)
                QMessageBox.information(
                    self, 'Save Successful',
                    f'Saved the result spectrum to:\n{file_path}'
                )
            except Exception as e:
                QMessageBox.critical(self, 'Save Error', f'Failed to save spectrum:\n{e}')

        else:  # individual files
            directory = QFileDialog.getExistingDirectory(
                self, 'Select Directory for Individual Files'
            )
            if not directory:
                return

            try:
                saved_files = save_manager.save_individual(to_save, directory, settings)
                QMessageBox.information(
                    self, 'Save Successful',
                    f'Saved {len(saved_files)} file(s) to:\n{directory}'
                )
            except Exception as e:
                QMessageBox.critical(self, 'Save Error', f'Failed to save files:\n{e}')
