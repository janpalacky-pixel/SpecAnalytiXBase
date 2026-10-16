"""Group Statistics: group / sample tables (Excel sheet 'Groups', sidecar
'<data file>_groups.csv'), automatic filling when the window opens, the
orange '?' context-help buttons and the three demo datasets."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import openpyxl
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox, QPushButton

from src.modules.visualization_analysis import group_statistics as gs
from src.modules.visualization_analysis import group_tests as gt

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SYNTH = os.path.join(ROOT, 'resources', 'test_data', 'synthetic')
X = np.linspace(400, 1800, 200)


@pytest.fixture
def quiet(monkeypatch):
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))


def _workbook(path, rows, first_sheet='Spectra'):
    wb = openpyxl.Workbook()
    wb.active.title = first_sheet
    wb.active.append(['x', 'a1'])
    ws = wb.create_sheet('Groups')
    for r in rows:
        ws.append(r)
    wb.save(path)


def _sp(label, file_path=None, h=1.0):
    meta = {'file_path': str(file_path)} if file_path else {}
    return {'label': label, 'x_scale': X, 'metadata': meta,
            'y_scale': h * np.exp(-((X - 1000) / 20) ** 2)}


# --- reading tables ------------------------------------------------------------------

def test_read_group_sample_table_excel_uses_the_groups_sheet(tmp_path):
    path = tmp_path / 'data.xlsx'
    _workbook(path, [['Spectrum', 'Group', 'Sample'], ['a1', 'ctrl', 's1'], ['a2', 'treat', None]])
    groups, samples = gs.read_group_sample_table(str(path))
    assert groups == {'a1': 'ctrl', 'a2': 'treat'}
    assert samples == {'a1': 's1'}


@pytest.mark.parametrize('sep', ['\t', ';', ','])
def test_read_group_sample_table_text_with_separators(tmp_path, sep):
    path = tmp_path / 'g.csv'
    path.write_text(sep.join(['Spectrum', 'Group', 'Sample']) + '\n'
                    + sep.join(['run : t1', 'ctrl', 'cuv1']) + '\n'
                    + sep.join(['run : t2', 'heat', 'cuv1']) + '\n', encoding='utf-8')
    groups, samples = gs.read_group_sample_table(str(path), labels=['run : t1', 'run : t2'])
    assert groups == {'run : t1': 'ctrl', 'run : t2': 'heat'}
    assert samples == {'run : t1': 'cuv1', 'run : t2': 'cuv1'}


def test_read_group_sample_table_two_columns_like_before(tmp_path):
    path = tmp_path / 'g.txt'
    path.write_text('a1 ctrl\na2 treat\n', encoding='utf-8')
    assert gs.read_group_sample_table(str(path)) == ({'a1': 'ctrl', 'a2': 'treat'}, {})
    assert gs.read_group_table(str(path)) == {'a1': 'ctrl', 'a2': 'treat'}


def test_find_group_table_sidecar_and_groups_sheet(tmp_path):
    data = tmp_path / 'meas.txt'
    data.write_text('x\n', encoding='utf-8')
    assert gs.find_group_table([_sp('meas : a1', data)]) is None
    (tmp_path / 'meas_groups.csv').write_text('a1,ctrl\n', encoding='utf-8')
    assert gs.find_group_table([_sp('meas : a1', data)]) == str(tmp_path / 'meas_groups.csv')
    book = tmp_path / 'book.xlsx'
    _workbook(book, [['Spectrum', 'Group'], ['a1', 'ctrl']])
    assert gs.find_group_table([_sp('x', None), _sp('book : a1', book)]) == str(book)
    plain = tmp_path / 'plain.xlsx'
    openpyxl.Workbook().save(plain)
    assert gs.find_group_table([_sp('plain : a1', plain)]) is None


def test_groups_from_own_table_matches_column_names_of_that_file_only(tmp_path):
    book = tmp_path / 'book.xlsx'
    other = tmp_path / 'other.xlsx'
    spectra = [_sp('book : cell1 [px01]', book), _sp('book : a2', book),
               _sp('other : a2', other), _sp('a3', book)]
    labels = [s['label'] for s in spectra]
    mapping = {'cell1 [px01]': 'WT', 'a2': 'MUT', 'a3': 'WT'}
    # the importer writes "cell1 [px01]" as "cell1__px01_": still matched
    spectra[0]['label'] = labels[0] = 'book : cell1__px01_'
    assert gs.groups_from_own_table(spectra, labels, str(book), mapping) == [
        'WT', 'MUT', '', 'WT']
    # the old function is unchanged: full names only
    assert gs.groups_from_table(labels, mapping) == ['', '', '', 'WT']


def test_shared_sample_warning():
    groups = ['a'] * 4 + ['b'] * 4
    samples = ['c1', 'c1', 'c2', 'c2', 'c3', 'c4', 'c5', '']
    assert gt.shared_sample_warnings(groups, samples) == [('a', 4, 2)]
    assert gt.shared_sample_warnings(groups, [''] * 8) == []


# --- the window ------------------------------------------------------------------------

def _book_spectra(tmp_path):
    book = tmp_path / 'demo.xlsx'
    _workbook(book, [['Spectrum', 'Group', 'Sample'], ['a1', 'ctrl', 's1'], ['a2', 'ctrl', 's2'],
                     ['b1', 'treat', 's3'], ['b2', 'treat', 's4']])
    return [_sp(f'demo : {n}', book, h) for n, h in (('a1', 1), ('a2', 1.1), ('b1', 2), ('b2', 2.1))]


def test_window_fills_groups_and_samples_from_the_data_file(quiet, tmp_path):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    d = GroupStatisticsDialog(_book_spectra(tmp_path), None, {}, {})
    assert d.groups() == ['ctrl', 'ctrl', 'treat', 'treat']
    assert d.samples() == ['s1', 's2', 's3', 's4']
    assert d.table_source.isVisibleTo(d) and 'sheet “Groups” of demo.xlsx' in d.table_source.text()
    d.table.undo()                                     # one step removes both columns
    assert d.groups() == [''] * 4 and d.samples() == [''] * 4
    d.deleteLater()


def test_window_keeps_groups_already_set(quiet, tmp_path):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    spectra = _book_spectra(tmp_path)
    saved = {spectra[0]['label']: 'mine'}
    d = GroupStatisticsDialog(spectra, None, saved, {})
    assert d.groups()[0] == 'mine' and d.groups()[2] == ''
    assert not d.table_source.isVisibleTo(d)
    d.deleteLater()


def test_orange_help_buttons_show_their_text(quiet, monkeypatch):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    shown = []
    monkeypatch.setattr(QMessageBox, 'exec_', lambda box: shown.append(box.text()) or 0)
    d = GroupStatisticsDialog([_sp('a'), _sp('b')], None, {}, {})
    buttons = [b for b in d.findChildren(QPushButton) if b.text() == '?']
    assert len(buttons) == 7                           # 6 + the Spectra tab
    for b in buttons:
        assert '#F57C00' in b.styleSheet() and b.toolTip()
        b.click()
    assert len(shown) == 7 and all(t.startswith('<h3>') for t in shown)
    d.deleteLater()


# --- the demo datasets -----------------------------------------------------------------

DEMOS = ('group_stats_treatment_demo.xlsx', 'group_stats_cells_samples_demo.xlsx',
         'group_stats_paired_demo.xlsx', 'group_stats_skewed_demo.xlsx')


def _load_demo(name):
    from src.modules.core.spectrum_manager import SpectrumManager
    m = SpectrumManager()
    m.load_spectrum_from_file(os.path.join(SYNTH, name))
    return [{'label': l, 'x_scale': s.x_scale, 'y_scale': s.y_scale, 'metadata': s.metadata}
            for l, s in m.spectra.items()]


def test_demo_datasets_are_in_the_help_menu_list():
    from src.views.main_window import SYNTHETIC_TEST_DATASETS
    listed = [f for g, _, f in SYNTHETIC_TEST_DATASETS if g == 'groupstats']
    assert listed == list(DEMOS) + ['group_stats_cell_map_demo.mat']
    for f in listed:
        assert os.path.isfile(os.path.join(SYNTH, f))


def _window(name):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    d = GroupStatisticsDialog(_load_demo(name), None, {}, {})
    assert all(d.groups()) and d.table_source.text()
    return d


def test_demo_treatment(quiet):
    d = _window(DEMOS[0])
    assert sorted(set(d.groups())) == ['control', 'high dose', 'low dose']
    assert not any(d.samples())
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('ratio'))
    d.a_from.setValue(1620); d.a_to.setValue(1690)
    d.b_from.setValue(1420); d.b_to.setValue(1480)
    d.metric_a_combo.setCurrentText('Integral'); d.metric_b_combo.setCurrentText('Integral')
    d.operation_combo.setCurrentText('A / B')
    d.compute()
    assert d.comparison['p'] < 1e-4                           # the dose effect
    assert 'not independent' not in d.note.text()             # empty Sample column: no warning
    assert d.comparison['checks']['equal_spread_p'] < 0.05     # unequal spread
    control = [lab for lab, g in zip(d.labels, d.groups()) if g == 'control']
    assert [control[i] for i in d.comparison['outliers']['control']] == [
        'group_stats_treatment_demo : control_05']
    d.deleteLater()


def test_demo_cells_pseudoreplication(quiet):
    d = _window(DEMOS[1])
    assert len(set(d.samples())) == 6
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('ratio'))
    d.a_from.setValue(1620); d.a_to.setValue(1690)
    d.b_from.setValue(1420); d.b_to.setValue(1480)
    d.metric_a_combo.setCurrentText('Integral'); d.metric_b_combo.setCurrentText('Integral')
    d.compute()
    assert d.comparison['p'] < 0.001
    assert 'not independent replicates' in d.note.text() and 'B71C1C' in d.note.styleSheet()
    d.per_sample_check.setChecked(True)
    d.compute()
    assert [len(v) for v in d.data.values()] == [3, 3] and d.comparison['p'] > 0.05
    d.deleteLater()


def test_demo_paired(quiet):
    d = _window(DEMOS[2])
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('max'))
    d.a_from.setValue(1630); d.a_to.setValue(1680)
    d.compute()
    assert d.comparison['p'] > 0.05                            # unpaired: hidden
    d.test_combo.setCurrentIndex(d.test_combo.findData('paired_t'))
    d.compute()
    assert d.comparison['n_pairs'] == 8 and d.comparison['p'] < 0.001
    d.deleteLater()
