"""The Peak list says how many spectra have no peak only when some have none
("196 peaks in 30 spectra." - before always "... in 30 of 30 spectra");
Groups from spectrum names: how to write the rules is always shown (not only
in the empty box), and without any group the line under it says so plainly
(before "0 groups: ; 30 spectra without a group")."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def _spectra():
    x = np.linspace(0, 100, 501)
    peak = np.exp(-(x - 50) ** 2 / 20)
    return [{'label': f'a : s{i}', 'x_scale': x, 'y_scale': peak * (i + 1), 'metadata': {}}
            for i in range(3)] + [{'label': 'a : flat', 'x_scale': x,
                                   'y_scale': np.zeros_like(x), 'metadata': {}}]


def test_peak_list_summary():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    sp = _spectra()
    dlg = PeakListDialog(None, sp[:3])
    assert dlg.summary_text() == '3 peaks in 3 spectra.'
    dlg = PeakListDialog(None, sp)
    assert dlg.summary_text() == '3 peaks in 4 spectra; 1 of them without a peak.'


def test_groups_from_names_texts():
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import \
        NamesToGroupsDialog
    labels = [f'control_{i}' for i in range(3)] + [f'treated_{i}' for i in range(2)]
    dlg = NamesToGroupsDialog(labels)
    dlg.contains_radio.setChecked(True)
    assert 'text = group name' in dlg.rules_hint.text()
    assert dlg.preview.text().startswith('No groups yet: 5 spectra without a group')
    dlg.rules_edit.setPlainText('control = Control')
    assert dlg.preview.text() == '1 group: Control (3); 2 spectra without a group'
    assert not dlg.rules_hint.isHidden()                       # still shown with rules typed
