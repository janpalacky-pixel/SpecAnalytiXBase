"""Group Statistics: groups, values, tests and the window
(group_statistics.py, group_statistics_dialog.py)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from scipy import stats
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from src.modules.visualization_analysis import group_statistics as gs

app = QApplication.instance() or QApplication([])
X = np.linspace(400, 1800, 701)


def _spectrum(label, height, x=X):
    y = height * np.exp(-((x - 1000) / 20) ** 2) + 0.5 * np.exp(-((x - 1450) / 30) ** 2)
    return {'label': label, 'x_scale': x, 'y_scale': y, 'metadata': {}}


# --- groups ---------------------------------------------------------------------

def test_groups_from_contains_first_rule_wins_and_ignores_case():
    labels = ['Ctrl_01', 'treat_ctrl', 'Mock 3', 'other']
    rules = [('treat', 'Treated'), ('ctrl', 'Control'), ('mock', '')]
    assert gs.groups_from_contains(labels, rules) == ['Control', 'Treated', 'mock', '']


def test_groups_from_part_of_the_name():
    labels = ['cellA_day3_01', 'cellB_day7_02', 'nosep']
    assert gs.groups_from_part(labels, '_', 2) == ['day3', 'day7', '']
    assert gs.groups_from_part(labels, '_', -1) == ['01', '02', 'nosep']


def test_group_table_csv_and_excel(tmp_path):
    csv = tmp_path / 'g.csv'
    csv.write_text("name,group\nA1,ctrl\nB1,treated\n", encoding='utf-8')
    mapping = gs.read_group_table(str(csv))
    assert mapping == {'A1': 'ctrl', 'B1': 'treated'}
    assert gs.groups_from_table(['a1 ', 'B1', 'C'], mapping) == ['ctrl', 'treated', '']
    import pandas as pd
    xlsx = tmp_path / 'g.xlsx'
    pd.DataFrame([['A1', 'ctrl'], ['B1', 'treated']]).to_excel(xlsx, header=False, index=False)
    assert gs.read_group_table(str(xlsx)) == mapping


# --- values -----------------------------------------------------------------------

def test_values_from_each_spectrums_own_axis():
    s = _spectrum('a', 2.0)
    other = _spectrum('b', 2.0, x=np.linspace(300, 2000, 1500))     # a different axis
    for sp in (s, other):
        assert gs.spectrum_value(sp, 'intensity_at_x', x0=1000) == pytest.approx(2.0, rel=1e-3)
        assert gs.spectrum_value(sp, 'max', range_a=(950, 1050)) == pytest.approx(2.0, rel=1e-3)
        area = gs.spectrum_value(sp, 'area', range_a=(900, 1100))
        assert area == pytest.approx(2.0 * 20 * np.sqrt(np.pi), rel=1e-3)
    ratio = gs.spectrum_value(s, 'ratio', range_a=(900, 1100), range_b=(1300, 1600))
    assert ratio == pytest.approx((2.0 * 20) / (0.5 * 30), rel=1e-3)
    assert np.isnan(gs.spectrum_value(s, 'intensity_at_x', x0=5000))     # outside: no value
    assert np.isnan(gs.spectrum_value(s, 'mean', range_a=(3000, 4000)))


# --- statistics: the same numbers as scipy, plus corrections ------------------------

def test_two_groups_parametric_and_nonparametric():
    rng = np.random.default_rng(1)
    a, b = rng.normal(0, 1, 12), rng.normal(1.5, 1, 15)
    r = gs.compare({'A': a, 'B': b})
    ref = stats.ttest_ind(a, b, equal_var=False)
    assert r['test'] == 'Welch t-test' and r['p'] == pytest.approx(ref.pvalue)
    assert r['effect'] < -0.8                                    # large, A below B
    r = gs.compare({'A': a, 'B': b}, parametric=False)
    assert r['p'] == pytest.approx(stats.mannwhitneyu(a, b, alternative='two-sided').pvalue)
    assert -1 <= r['effect'] < 0


def test_three_groups_with_holm_corrected_pairs():
    rng = np.random.default_rng(2)
    data = {'A': rng.normal(0, 1, 10), 'B': rng.normal(0, 1, 10), 'C': rng.normal(3, 1, 10),
            'D': np.array([5.0])}                                # too small: left out
    r = gs.compare(data)
    assert r['test'] == 'One-way ANOVA' and r['excluded'] == ['D']
    assert r['p'] == pytest.approx(stats.f_oneway(data['A'], data['B'], data['C']).pvalue)
    assert len(r['pairs']) == 3
    raw = [p['p'] for p in r['pairs']]
    assert [p['p_holm'] for p in r['pairs']] == pytest.approx(list(gs.holm(raw)))
    assert all(p['p_holm'] >= p['p'] for p in r['pairs'])
    k = gs.compare(data, parametric=False)
    assert k['test'] == 'Kruskal–Wallis test'
    assert k['p'] == pytest.approx(stats.kruskal(data['A'], data['B'], data['C']).pvalue)


def test_holm_by_hand():
    assert list(gs.holm([0.01, 0.04, 0.03])) == pytest.approx([0.03, 0.06, 0.06])


def test_too_few_groups_is_explained_not_crashed():
    r = gs.compare({'A': np.array([1.0, 2.0])})
    assert r['test'] is None and 'two groups' in r['note']


# --- the window -------------------------------------------------------------------------

@pytest.fixture
def dialog(monkeypatch):
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    spectra = ([_spectrum(f'ctrl_{i}', 1.0 + 0.05 * i) for i in range(6)]
               + [_spectrum(f'treat_{i}', 2.0 + 0.05 * i) for i in range(6)])
    d = GroupStatisticsDialog(spectra, None, {})
    yield d
    d.deleteLater()


def test_dialog_groups_from_names_compute_and_export(dialog, tmp_path, monkeypatch):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    dialog.compute()                                        # no groups: a warning, no crash
    assert dialog.comparison is None

    def fake_exec(dlg):
        dlg.part_radio.setChecked(True)
        dlg.separators_edit.setText('_')
        dlg.part_spin.setValue(1)
        return QDialog.Accepted
    monkeypatch.setattr(gsd.NamesToGroupsDialog, 'exec_', fake_exec)
    dialog.groups_from_names()
    assert dialog.groups() == ['ctrl'] * 6 + ['treat'] * 6
    dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findData('max'))
    dialog.a_from.setValue(950)
    dialog.a_to.setValue(1050)
    dialog.compute()
    r = dialog.comparison
    assert r['test'] == 'Welch t-test' and r['p'] < 0.001
    assert dialog.summary_table.rowCount() == 2
    assert 'Welch t-test' in dialog.tests_view.toPlainText()
    out = tmp_path / 'gs.xlsx'
    gsd.export_results(str(out), dialog.labels, dialog.groups(), dialog.values, dialog.data,
                       dialog.comparison, dialog.value_label())
    import pandas as pd
    sheets = pd.read_excel(out, sheet_name=None)
    assert set(sheets) == {'Values', 'Summary', 'Tests'} and len(sheets['Values']) == 12
    csv = tmp_path / 'gs.csv'
    gsd.export_results(str(csv), dialog.labels, dialog.groups(), dialog.values, dialog.data,
                       dialog.comparison, dialog.value_label())
    assert 'Welch t-test' in csv.read_text(encoding='utf-8-sig')


def test_groups_are_remembered_between_openings(dialog):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    dialog.table.selectRow(0)
    dialog.table.item(0, 1).setText('special')
    again = GroupStatisticsDialog(dialog.spectra, None, dialog.saved_groups)
    assert again.groups()[0] == 'special'


def test_help_page_exists():
    from src.help import group_statistics_help as h
    html = h.get_group_statistics_help_content()
    assert 'Holm' in html and '$GS_' not in html


def test_very_small_p_is_shown_not_swallowed_as_html(dialog):
    dialog._set_groups(['ctrl'] * 6 + ['treat'] * 6)
    dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findData('max'))
    dialog.a_from.setValue(950)
    dialog.a_to.setValue(1050)
    dialog.compute()
    assert dialog.comparison['p'] < 1e-4
    assert 'p < 0.0001' in dialog.tests_view.toPlainText()


# --- added 2026-10-14: root-name groups, window size, column widths --------------

def test_groups_from_root_name_like_rename_dialog():
    labels = ['CD_spectra_TBA : 0019', 'CD_spectra_TBA : 0028',
              'Glenodinium [r001_c001]', 'Glenodinium [r001_c027]',
              'Chlorella [r24_c14]', 'sample_012']
    assert gs.groups_from_root_name(labels) == [
        'CD_spectra_TBA', 'CD_spectra_TBA', 'Glenodinium', 'Glenodinium',
        'Chlorella', 'sample']


def test_names_dialog_offers_root_name_first():
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        NamesToGroupsDialog)
    d = NamesToGroupsDialog(['Chlorella [r24_c14]', 'Chlorella [r24_c15]',
                             'Glenodinium [r001_c001]'])
    assert d.root_radio.isChecked()
    assert d.groups() == ['Chlorella', 'Chlorella', 'Glenodinium']
    assert '2 groups' in d.preview.text()
    d.deleteLater()


def test_window_can_be_maximized_and_both_columns_resized(dialog):
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QHeaderView
    assert dialog.windowFlags() & Qt.WindowMaximizeButtonHint
    header = dialog.table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.Interactive
    assert header.sectionResizeMode(1) == QHeaderView.Interactive
    dialog.table.setColumnWidth(0, 300)
    assert dialog.table.columnWidth(0) == 300


def test_window_has_no_minimize_button_because_it_is_modal(dialog):
    from PyQt5.QtCore import Qt
    assert not dialog.windowFlags() & Qt.WindowMinimizeButtonHint
    assert dialog.windowFlags() & Qt.WindowMaximizeButtonHint


def test_tabs_are_wide_enough_for_bold_text(dialog):
    assert 'min-width' in dialog.tabs.styleSheet()


def test_part_of_the_name_trims_spaces_around_the_separator():
    labels = ['CD_melt_sample_1_heating : CD [mdeg] T=10.04C', 'CD_spectra_TBA : 0001',
              'Raman_DNA_conc_dep : sp001']
    assert gs.groups_from_part(labels, ':', 1) == [
        'CD_melt_sample_1_heating', 'CD_spectra_TBA', 'Raman_DNA_conc_dep']


# --- default ranges (2026-10-14): one range = the whole common x-range --------------

def _dialog_for(xs):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    spectra = [{'label': f's{i}', 'x_scale': x, 'y_scale': np.ones_like(x), 'metadata': {}}
               for i, x in enumerate(xs)]
    return GroupStatisticsDialog(spectra, None, {})


def test_single_range_defaults_to_the_whole_common_range_ratio_to_two_halves():
    d = _dialog_for([np.linspace(200, 330, 261), np.linspace(190, 340, 301)])
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('mean'))
    assert (d.a_from.value(), d.a_to.value()) == (200.0, 330.0)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('ratio'))
    assert (d.a_from.value(), d.a_to.value()) == (248.75, 265.0)
    assert (d.b_from.value(), d.b_to.value()) == (265.0, 281.25)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('area'))
    assert (d.a_from.value(), d.a_to.value()) == (200.0, 330.0)
    assert not d.no_common_range_label.isVisibleTo(d)
    d.deleteLater()


def test_a_range_typed_by_the_user_is_kept_when_switching():
    d = _dialog_for([np.linspace(200, 330, 261)])
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('mean'))
    d.a_from.setValue(220)
    d.a_to.setValue(240)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('ratio'))
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('max'))
    assert (d.a_from.value(), d.a_to.value()) == (220.0, 240.0)
    d.deleteLater()


def test_no_common_range_is_announced():
    d = _dialog_for([np.linspace(200, 250, 51), np.linspace(270, 330, 61)])
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('mean'))
    assert d.no_common_range_label.isVisibleTo(d)
    assert (d.a_from.value(), d.a_to.value()) == (200.0, 330.0)
    d.deleteLater()


def test_a_group_without_values_is_named_with_its_x_range(monkeypatch):
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    d = _dialog_for([np.linspace(235, 288, 54)] * 3 + [np.linspace(303, 318, 16)] * 3)
    d.table.set_values(['A'] * 3 + ['B'] * 3)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('intensity_at_x'))
    assert d.no_common_range_label.isVisibleTo(d)        # also for one x-value
    d.x_spin.setValue(260)
    d.compute()
    text = d.note.text()
    assert text.startswith('No test was computed.')
    assert '“B” (3 spectra) has no value' in text and '303–318' in text
    assert 'x = 260' in text
    d.deleteLater()


def test_a_group_left_out_of_a_computed_test_is_shown_in_red(monkeypatch):
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    rng = np.random.default_rng(1)
    x1, x2 = np.linspace(235, 288, 54), np.linspace(303, 318, 16)
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    spectra = ([{'label': f'a{i}', 'x_scale': x1, 'y_scale': rng.normal(1, .1, 54)} for i in range(4)]
               + [{'label': f'c{i}', 'x_scale': x1, 'y_scale': rng.normal(2, .1, 54)} for i in range(4)]
               + [{'label': f'b{i}', 'x_scale': x2, 'y_scale': np.ones(16)} for i in range(3)])
    d = GroupStatisticsDialog(spectra, None, {})
    d.table.set_values(['1'] * 4 + ['3'] * 4 + ['2'] * 3)
    d.x_spin.setValue(260)
    d.compute()
    assert d.comparison['test'] is not None                 # 1 vs 3 is tested
    assert '#B71C1C' in d.note.styleSheet()                 # but red: group 2 is missing
    assert 'not in the test' in d.note.text()
    assert 'not in the test: group 2' in d.figure.axes[0].get_title()
    d.deleteLater()
