"""Group Statistics: a Group or Sample column made "From a property..." or
"From names..." is worked out again from the current values each time the
window opens (a property changed or deleted in Spectrum properties, an
earlier state chosen in the History, a renamed spectrum) - not the
remembered, stale one; a column edited by hand stays as it is. The Group
and the Sample column have the same five buttons."""
import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))


def _spectra(conc=(30, 35, 40, 50, 55, 60)):
    x = np.linspace(0, 10, 50)
    out = []
    for i, c in enumerate(conc):
        md = {'unique_id': f'id{i}', 'cuvette': 1 + i % 3}
        if c is not None:
            md['conc'] = c
        out.append({'label': f'cellA_r{i + 1}', 'x_scale': x, 'y_scale': np.sin(x + i),
                    'metadata': md})
    return out


def _choose(monkeypatch, key, split=None):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd

    def fake_exec(self):
        self.key_combo.setCurrentText(key)
        if split is None:
            self.each_radio.setChecked(True)
        else:
            self.split_spin.setValue(split)
            self.split_radio.setChecked(True)
        return QDialog.Accepted
    monkeypatch.setattr(gsd.PropertyToGroupsDialog, 'exec_', fake_exec)


def _open(spectra, groups, settings):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import \
        GroupStatisticsDialog
    return GroupStatisticsDialog(spectra, None, groups, settings)


def test_groups_from_a_property_follow_the_current_values(monkeypatch):
    saved, settings = {}, {}
    d = _open(_spectra(), saved, settings)
    _choose(monkeypatch, 'conc', split=45)
    d.groups_from_property()
    assert d.groups() == ['conc < 45'] * 3 + ['conc ≥ 45'] * 3
    assert 'the property conc (split at 45)' in d.recipe_note.text()
    d.close()
    # conc deleted for one spectrum, changed for another (Spectrum properties or History)
    d = _open(_spectra(conc=(30, None, 40, 50, 20, 60)), saved, settings)
    assert d.groups() == ['conc < 45', '', 'conc < 45', 'conc ≥ 45', 'conc < 45',
                          'conc ≥ 45']
    assert 'updated from the current values' in d.recipe_note.text()
    assert 'without a group' in d.group_summary.text()
    d.close()
    # no property at all (an earlier state of the History): no groups
    d = _open(_spectra(conc=(None,) * 6), saved, settings)
    assert d.groups() == [''] * 6
    d.close()


def test_a_column_edited_by_hand_stays_as_it_is(monkeypatch):
    saved, settings = {}, {}
    d = _open(_spectra(), saved, settings)
    _choose(monkeypatch, 'conc', split=45)
    d.groups_from_property()
    d.table.set_rows([0], 'my group')                     # edited by hand
    assert not d.recipe_note.isVisibleTo(d) and 'group_recipe' not in settings
    d.close()
    d = _open(_spectra(conc=(60,) * 6), saved, settings)
    assert d.groups()[0] == 'my group' and d.groups()[1] == 'conc < 45'   # kept as it was
    d.close()


def test_groups_from_names_follow_a_rename(monkeypatch):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd

    def fake_exec(self):
        self.part_radio.setChecked(True)
        self.separators_edit.setText('_')
        self.part_spin.setValue(1)
        return QDialog.Accepted
    monkeypatch.setattr(gsd.NamesToGroupsDialog, 'exec_', fake_exec)
    saved, settings = {}, {}
    sp = _spectra()
    d = _open(sp, saved, settings)
    d.groups_from_names()
    assert set(d.groups()) == {'cellA'}
    d.close()
    sp2 = copy.deepcopy(sp)
    sp2[0]['label'] = 'cellB_r1'                           # renamed
    d = _open(sp2, saved, settings)
    assert d.groups()[0] == 'cellB' and 'part 1' in d.recipe_note.text()
    d.close()


def test_samples_from_a_property_and_from_names(monkeypatch):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    saved, settings = {}, {}
    d = _open(_spectra(), saved, settings)
    _choose(monkeypatch, 'cuvette')
    d.samples_from_property()
    assert d.samples() == ['cuvette 1', 'cuvette 2', 'cuvette 3'] * 2
    assert 'Samples from the property cuvette' in d.recipe_note.text()
    d.close()
    sp = _spectra()
    sp[0]['metadata']['cuvette'] = 9
    d = _open(sp, saved, settings)
    assert d.samples()[0] == 'cuvette 9'

    def fake_exec(self):
        self.part_radio.setChecked(True)
        self.separators_edit.setText('_')
        self.part_spin.setValue(-1)
        return QDialog.Accepted
    monkeypatch.setattr(gsd.NamesToGroupsDialog, 'exec_', fake_exec)
    d.samples_from_names()
    assert d.samples() == [f'r{i}' for i in range(1, 7)]
    d.close()


@pytest.mark.parametrize('rows, expected', [
    ("cellA_r1\tS1\ncellA_r2\tS2\n", ['S1', 'S2', '', '', '', '']),
    ("cellA_r1\tcontrol\tS7\ncellA_r3\ttreated\tS8\n", ['S7', '', 'S8', '', '', '']),
])
def test_samples_from_a_table_file(tmp_path, monkeypatch, rows, expected):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    path = tmp_path / 'samples.txt'
    path.write_text(rows, encoding='utf-8')
    monkeypatch.setattr(gsd.QFileDialog, 'getOpenFileName',
                        staticmethod(lambda *a, **k: (str(path), '')))
    d = _open(_spectra(), {}, {})
    d.samples_from_table_file()
    assert d.samples() == expected
    d.close()


def test_the_same_buttons_for_groups_and_samples():
    d = _open(_spectra(), {}, {})
    texts = {what: [d.column_buttons[(what, c)].text() for c in range(1, 6)]
             for what in ('Group', 'Sample')}
    assert texts['Group'][:4] == texts['Sample'][:4] == [
        'Set for selected rows…', 'From names…', 'From a property…',
        'From table file…']
    assert (texts['Group'][4], texts['Sample'][4]) == ('Clear all groups', 'Clear all samples')
    first = [b for b in d.findChildren(QPushButton) if b.text() == 'From a property…'][0]
    assert first is d.column_buttons[('Group', 3)]
    d.column_buttons[('Sample', 5)].click()
    assert d.samples() == [''] * 6
    d.close()
