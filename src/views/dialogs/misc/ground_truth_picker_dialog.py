# src/views/dialogs/misc/ground_truth_picker_dialog.py
"""
Small picker dialog for the NMF/MCR-ALS "Compare with ground truth
(testing)" feature — lets the user choose one of the shipped synthetic
benchmark workbooks by its friendly name, rather than browsing the raw
resources/test_data/synthetic/ folder (which also holds unrelated demo
files for other tools). Shared by nmf_dialog.py and mcr_als_dialog.py.
"""

import os

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QDialogButtonBox, QMessageBox,
)
from PyQt5.QtCore import Qt

from src.modules.visualization_analysis.ground_truth_comparison import (
    list_ground_truth_datasets, synthetic_datasets_dir,
)


class GroundTruthPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Compare with ground truth (testing)')
        self.setMinimumSize(420, 380)

        layout = QVBoxLayout(self)
        info = QLabel(
            'Pick the synthetic benchmark dataset that matches the spectra '
            'you selected for this run. This overlays the known TRUE pure '
            'components and concentrations on top of your fitted result — '
            'for testing/teaching this tool against known answers only; it '
            'has no meaning for real data.'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._list = QListWidget()
        self._entries = list_ground_truth_datasets()
        for filename, label in self._entries:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, filename)
            self._list.addItem(item)
        if self._entries:
            self._list.setCurrentRow(0)
        else:
            self._list.addItem('(no ground-truth datasets found)')
            self._list.setEnabled(False)
        self._list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._buttons = buttons
        if not self._entries:
            buttons.button(QDialogButtonBox.Ok).setEnabled(False)

    def selected_filepath(self):
        item = self._list.currentItem()
        if item is None or not self._entries:
            return None
        filename = item.data(Qt.UserRole)
        if filename is None:
            return None
        return os.path.join(synthetic_datasets_dir(), filename)


def pick_ground_truth_dataset(parent=None):
    """Show the picker; return the chosen workbook's full path, or None if
    the user cancelled or none were found (a message is shown in that
    second case, since a silent None would look like a bug)."""
    dlg = GroundTruthPickerDialog(parent)
    if not dlg._entries:
        QMessageBox.information(
            parent, 'No ground-truth datasets found',
            'No synthetic benchmark workbooks with Pure_components/'
            'Concentrations sheets were found in the resources/test_data/'
            'synthetic folder.')
        return None
    if dlg.exec_() != QDialog.Accepted:
        return None
    return dlg.selected_filepath()
