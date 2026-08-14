# src/views/dialogs/data_analysis/batch_pipeline_save_dialog.py
"""
"Save as Pipeline..." dialog — captures a named, reusable pipeline from
the current session's Operations History.

Shows every operation committed so far this session, in order. Eligible
operations (see batch_pipeline_manager.ELIGIBLE_OPERATIONS) are
checkable, checked by default; ineligible ones are shown greyed out,
unchecked, with a tooltip explaining exactly why (e.g. Manual baseline is
stateful, CD Unit Conversion's settings are sample-specific). Whatever is
checked, in its original chronological order, becomes the saved
pipeline's step list.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QDialogButtonBox, QMessageBox, QComboBox,
)
from PyQt5.QtCore import Qt

from src.modules.data_analysis.batch_pipeline_manager import BatchPipelineManager
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)


class BatchPipelineSaveDialog(QDialog):

    def __init__(self, parent=None, operations_chain=None, pipeline_manager=None):
        super().__init__(parent)
        self.setWindowTitle('Save as Pipeline')
        self.resize(640, 520)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self.operations_chain = operations_chain or []
        self.pipeline_manager = pipeline_manager

        self._build_ui()
        self._populate_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "Select which of this session's operations to include, in order. "
            "The result can be run again later, on any spectra selection, as a "
            "single named step."
        )
        info.setWordWrap(True)
        info.setStyleSheet('color: #1565C0;')
        layout.addWidget(info)

        self._list = QListWidget()
        layout.addWidget(self._list, stretch=1)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel('Pipeline name:'))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText('e.g. Raman standard prep')
        name_row.addWidget(self._name_edit, stretch=1)
        layout.addLayout(name_row)

        existing = self.pipeline_manager.list_pipelines() if self.pipeline_manager else []
        if existing:
            hint = QLabel(
                'Existing pipelines: ' + ', '.join(existing)
                + ' — saving under one of these names overwrites it.'
            )
            hint.setWordWrap(True)
            hint.setStyleSheet('color: #888; font-size: 11px;')
            layout.addWidget(hint)

        button_row = QHBoxLayout()
        help_btn = QPushButton('Help')
        help_btn.clicked.connect(self._show_help)
        button_row.addWidget(help_btn)
        button_row.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.button(QDialogButtonBox.Save).clicked.connect(self._save)
        button_box.rejected.connect(self.reject)
        button_row.addWidget(button_box)
        layout.addLayout(button_row)

    def _populate_list(self):
        self._list.clear()
        if not self.operations_chain:
            item = QListWidgetItem('No operations have been applied yet this session.')
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)
            return

        for i, op in enumerate(self.operations_chain):
            operation = op.get('type', '?')
            settings = op.get('parameters') or {}
            eligible = BatchPipelineManager.is_eligible(operation)
            desc = BatchPipelineManager.describe_step({'operation': operation, 'settings': settings})
            text = f"{i + 1}. {operation} — {desc}"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, i)
            if eligible:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                if BatchPipelineManager.is_index_sensitive(operation, settings):
                    item.setToolTip(
                        "This step's target depends on which spectrum sits at a "
                        "particular position in the selection — see Help for the caveat."
                    )
                    item.setForeground(Qt.darkYellow)
            else:
                item.setFlags(Qt.ItemIsSelectable)
                item.setCheckState(Qt.Unchecked)
                item.setForeground(Qt.gray)
                item.setToolTip(BatchPipelineManager.ineligible_reason(operation))
            self._list.addItem(item)

    def _checked_steps(self):
        steps = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.flags() & Qt.ItemIsUserCheckable and item.checkState() == Qt.Checked:
                idx = item.data(Qt.UserRole)
                op = self.operations_chain[idx]
                steps.append({'operation': op.get('type'), 'settings': dict(op.get('parameters') or {})})
        return steps

    def _save(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, 'Name required', 'Please enter a name for this pipeline.')
            return

        steps = self._checked_steps()
        if not steps:
            QMessageBox.warning(self, 'No steps selected', 'Select at least one operation to include.')
            return

        try:
            self.pipeline_manager.save_pipeline(name, steps)
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Could not save pipeline', str(exc))
            return

        QMessageBox.information(
            self, 'Pipeline saved',
            f"Saved '{name}' with {len(steps)} step(s). Run it later via "
            "Operations → Batch Pipeline → Run Pipeline…"
        )
        self.accept()

    def _show_help(self):
        try:
            from src.help.batch_pipeline_help import get_batch_pipeline_help_content, get_batch_pipeline_help_title
            from src.help.help_window import show_help_window
            show_help_window(self, get_batch_pipeline_help_title(), get_batch_pipeline_help_content())
        except Exception:
            QMessageBox.information(self, 'Help', 'Help documentation is not available.')
