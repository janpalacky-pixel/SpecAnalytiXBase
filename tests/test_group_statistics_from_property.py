"""Group Statistics > From a property...: groups from a number stored with
each spectrum (Spectrum properties) - every value a group, or two groups
split at a value; spectra without the value get no group."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication, QDialog, QPushButton

app = QApplication.instance() or QApplication([])


def _spectra():
    x = np.linspace(0, 10, 50)
    ph = [7.0, 7.0, 7.4, 7.4, 8.0, None]
    out = []
    for i, v in enumerate(ph):
        md = {'unique_id': f'id{i}'}
        if v is not None:
            md['pH'] = v
        md['T'] = 20.0 + 5 * i
        out.append({'label': f'cell {i + 1}', 'x_scale': x, 'y_scale': np.sin(x + i), 'metadata': md})
    return out


def test_groups_from_property():
    from src.modules.visualization_analysis import group_statistics as gs
    sp = _spectra()
    assert gs.groups_from_property(sp, 'pH') == ['pH 7', 'pH 7', 'pH 7.4', 'pH 7.4', 'pH 8', '']
    assert gs.groups_from_property(sp, 'T', split=32.5) == \
        ['T < 32.5'] * 3 + ['T ≥ 32.5'] * 3
    assert gs.property_value({'metadata': {'x': 'abc'}}, 'x') is None


def test_the_window_and_the_button(monkeypatch):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    sp = _spectra()
    dlg = gsd.PropertyToGroupsDialog(sp)
    keys = [dlg.key_combo.itemText(i) for i in range(dlg.key_combo.count())]
    assert keys == ['pH', 'T']
    assert '3 group(s)' in dlg.preview.text() and 'without a value' in dlg.preview.text()
    dlg.key_combo.setCurrentText('T')
    assert dlg.split_spin.value() == 32.5                        # the median
    dlg.split_radio.setChecked(True)
    assert '2 group(s)' in dlg.preview.text()

    def choose_ph(self):
        self.key_combo.setCurrentText('pH')
        self.each_radio.setChecked(True)
        return QDialog.Accepted
    monkeypatch.setattr(gsd.PropertyToGroupsDialog, 'exec_', choose_ph)
    w = gsd.GroupStatisticsDialog(sp, None, {}, {})
    button = [b for b in w.findChildren(QPushButton) if b.text() == 'From a property…'][0]
    button.click()
    assert w.groups() == ['pH 7', 'pH 7', 'pH 7.4', 'pH 7.4', 'pH 8', '']
