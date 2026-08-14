# src/views/dialogs/data_analysis/batch_pipeline_run_dialog.py
"""
Run Pipeline dialog — pick a saved, named pipeline and replay it against
the currently selected spectra.

Follows the same modal Apply / Add as New commit pattern as every other
processing-operation dialog in this app (e.g.
xaxis_unit_conversion_dialog.py): the target spectra are whatever was
selected before this dialog was opened (shown read-only here, not
re-pickable from inside the dialog — consistent with how every other
operation dialog works), and commit_callback does the actual run + Apply
/ Add as New bookkeeping.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QListWidget,
    QListWidgetItem, QPushButton, QMessageBox,
)
from PyQt5.QtCore import Qt

from src.modules.data_analysis.batch_pipeline_manager import BatchPipelineManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import shorten_spectra_labels

logger = get_logger(__name__)


class BatchPipelineRunDialog(QDialog):

    def __init__(self, parent=None, selected_spectra=None, pipeline_manager=None,
                 replay_manager=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle('Run Batch Pipeline')
        self.resize(620, 560)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self.selected_spectra = list(selected_spectra or [])
        self.pipeline_manager = pipeline_manager
        self.replay_manager = replay_manager
        self.commit_callback = commit_callback
        self._current_steps = []

        self._build_ui()
        self._populate_pipelines()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        target_label = QLabel(self._target_text())
        target_label.setWordWrap(True)
        target_label.setStyleSheet('color: #1565C0;')
        layout.addWidget(target_label)
        self._target_label = target_label

        pick_row = QHBoxLayout()
        pick_row.addWidget(QLabel('Pipeline:'))
        self._pipeline_combo = QComboBox()
        self._pipeline_combo.currentTextChanged.connect(self._on_pipeline_changed)
        pick_row.addWidget(self._pipeline_combo, stretch=1)
        delete_btn = QPushButton('Delete')
        delete_btn.setAutoDefault(False)
        delete_btn.clicked.connect(self._delete_current)
        pick_row.addWidget(delete_btn)
        layout.addLayout(pick_row)

        layout.addWidget(QLabel('Steps (run in this order):'))
        self._steps_list = QListWidget()
        layout.addWidget(self._steps_list, stretch=1)

        self._caveat_label = QLabel('')
        self._caveat_label.setWordWrap(True)
        self._caveat_label.setStyleSheet(
            'background-color: #FFF8E1; padding: 6px; border-radius: 4px; color: #E65100;'
        )
        self._caveat_label.setVisible(False)
        layout.addWidget(self._caveat_label)

        button_layout = QHBoxLayout()
        help_btn = QPushButton('Help')
        help_btn.clicked.connect(self.show_help)
        button_layout.addWidget(help_btn)
        button_layout.addStretch()

        self.apply_button = QPushButton('Apply')
        self.apply_button.setToolTip('Replace the selected spectra with the pipeline output.')
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        button_layout.addWidget(self.apply_button)

        self.add_as_new_button = QPushButton('Add as New')
        self.add_as_new_button.setToolTip('Keep the originals and add the pipeline output as new spectra.')
        self.add_as_new_button.setAutoDefault(False)
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        button_layout.addWidget(self.add_as_new_button)

        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def _target_text(self):
        n = len(self.selected_spectra)
        if n == 0:
            return 'No spectra selected — select spectra in the main list before running a pipeline.'
        dmap = shorten_spectra_labels(self.selected_spectra, False)
        names = ', '.join(dmap.get(s['label'], s['label']) for s in self.selected_spectra[:5])
        more = f' and {n - 5} more' if n > 5 else ''
        noun = 'spectrum' if n == 1 else 'spectra'
        return f'Will run on {n} selected {noun}: {names}{more}'

    def _populate_pipelines(self):
        names = self.pipeline_manager.list_pipelines() if self.pipeline_manager else []
        self._pipeline_combo.clear()
        self._pipeline_combo.addItems(names)
        can_run = bool(names) and bool(self.selected_spectra)
        self.apply_button.setEnabled(can_run)
        self.add_as_new_button.setEnabled(can_run)
        if names:
            self._on_pipeline_changed(names[0])

    def _on_pipeline_changed(self, name):
        self._steps_list.clear()
        self._current_steps = []
        self._caveat_label.setVisible(False)
        if not name or not self.pipeline_manager:
            return

        try:
            self._current_steps = self.pipeline_manager.load_pipeline(name)
        except KeyError:
            return

        caveats = []
        for i, step in enumerate(self._current_steps, start=1):
            operation = step.get('operation')
            settings = step.get('settings') or {}
            desc = BatchPipelineManager.describe_step(step)
            self._steps_list.addItem(QListWidgetItem(f"{i}. {operation} — {desc}"))
            if BatchPipelineManager.is_index_sensitive(operation, settings):
                caveats.append(
                    f"Step {i} ({operation}) targets a spectrum by its POSITION in the "
                    "selection, not by name — verify the equivalent spectrum is at the "
                    "same position in the current selection, or edit this step before running."
                )
        if caveats:
            self._caveat_label.setText('⚠  ' + '\n'.join(caveats))
            self._caveat_label.setVisible(True)

    def _delete_current(self):
        name = self._pipeline_combo.currentText()
        if not name:
            return
        confirm = QMessageBox.question(
            self, 'Delete pipeline', f"Delete the saved pipeline '{name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.pipeline_manager.delete_pipeline(name)
        self._populate_pipelines()

    def _on_commit_clicked(self, add_as_new):
        if self.commit_callback is None:
            QMessageBox.critical(
                self, 'Not Available',
                'This dialog was opened without a way to apply changes. Please reopen it.'
            )
            return

        name = self._pipeline_combo.currentText()
        if not name or not self._current_steps:
            QMessageBox.warning(self, 'No pipeline selected', 'Choose a pipeline to run first.')
            return
        if not self.selected_spectra:
            QMessageBox.warning(self, 'No spectra selected', 'Select spectra in the main list first.')
            return

        action = ('add the pipeline output as new spectra' if add_as_new
                  else 'replace the selected spectra with the pipeline output')
        confirm = QMessageBox.question(
            self, 'Confirm', f"Run pipeline '{name}' and {action}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(name, self._current_steps, add_as_new, list(self.selected_spectra))
        if success:
            QMessageBox.information(self, 'Done', message)
            self.accept()
        else:
            QMessageBox.warning(self, 'Could Not Run Pipeline', message)

    def show_help(self):
        try:
            from src.help.batch_pipeline_help import get_batch_pipeline_help_content, get_batch_pipeline_help_title
            from src.help.help_window import show_help_window
            show_help_window(self, get_batch_pipeline_help_title(), get_batch_pipeline_help_content())
        except Exception:
            QMessageBox.information(self, 'Help', 'Help documentation is not available.')
