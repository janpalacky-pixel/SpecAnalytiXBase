"""Group Statistics, more specific tests and checks (group_tests.py):
Welch ANOVA + Games-Howell, Dunn, permutation, paired tests, replicates
(one value per sample), confidence intervals, assumption checks, outliers,
results sentence. Reference values from pingouin 0.5 / scikit-posthocs /
statsmodels on the same data."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.visualization_analysis import group_statistics as gs
from src.modules.visualization_analysis import group_tests as gt

app = QApplication.instance() or QApplication([])
rng = np.random.default_rng(3)
VALS = [rng.normal(0, 1, 10), rng.normal(1, 3, 12), rng.normal(2, 1, 8)]
NAMES = ['A', 'B', 'C']


def test_welch_anova_matches_pingouin_and_statsmodels():
    F, df1, df2, p = gt.welch_anova(VALS)
    assert (F, df1, df2, p) == pytest.approx((8.230188058081126, 2, 17.15245263495785,
                                              0.0031203850836041), rel=1e-9)


def test_games_howell_matches_pingouin():
    gh = gt.games_howell(VALS, NAMES)
    assert [round(x['p'], 6) for x in gh] == [0.38027, 0.004106, 0.15571]
    assert [round(x['df'], 4) for x in gh] == [19.9949, 13.4079, 15.2556]
    for x in gh:                                            # the CI contains the difference
        assert x['ci'][0] < x['difference'] < x['ci'][1]


def test_dunn_matches_scikit_posthocs_also_with_ties():
    assert [round(x['p_holm'], 6) for x in gt.dunn(VALS, NAMES)] == [0.204444, 0.009487,
                                                                      0.121068]
    tied = [np.round(v) for v in VALS]
    assert [round(x['p_holm'], 6) for x in gt.dunn(tied, NAMES)] == [0.220912, 0.006674,
                                                                      0.084679]


def test_two_groups_games_howell_equals_welch_t():
    a, b = VALS[0], VALS[1]
    from scipy import stats
    assert gt.games_howell([a, b], ['a', 'b'])[0]['p'] == pytest.approx(
        stats.ttest_ind(a, b, equal_var=False).pvalue, rel=1e-6)
    F, _, df2, p = gt.welch_anova([a, b])
    assert p == pytest.approx(stats.ttest_ind(a, b, equal_var=False).pvalue, rel=1e-9)


def test_old_methods_are_exactly_as_before():
    data = dict(zip(NAMES, VALS))
    for method, parametric in (('parametric', True), ('nonparametric', False)):
        old = gs.compare(data, parametric=parametric)
        new = gt.compare_with(data, method)
        for key in ('test', 'statistic', 'p', 'effect', 'effect_name'):
            assert new[key] == old[key]
        assert [p['p_holm'] for p in new['pairs']] == [p['p_holm'] for p in old['pairs']]


def test_permutation_test_agrees_with_t_for_a_clear_difference():
    a = rng.normal(0, 1, 15)
    b = rng.normal(1.5, 1, 15)
    r = gt.compare_with({'a': a, 'b': b}, 'permutation')
    assert r['p'] < 0.01 and r['p'] >= 1 / (gt.N_PERMUTATIONS + 1)
    r = gt.compare_with({'a': a, 'b': a + rng.normal(0, 0.01, 15)}, 'permutation')
    assert r['p'] > 0.5


def test_paired_tests_use_the_sample_pairs():
    samples = [f's{i}' for i in range(8)]
    before = rng.normal(10, 3, 8)                        # large sample-to-sample spread
    after = before + 0.5 + rng.normal(0, 0.1, 8)          # small, consistent shift
    groups = ['before'] * 8 + ['after'] * 8
    values = list(before) + list(after)
    s, a, b = gt.paired_values(groups, samples + samples, values, 'before', 'after')
    assert s == samples
    paired = gt.compare_with({'before': before, 'after': after}, 'paired_t', (s, a, b))
    unpaired = gt.compare_with({'before': before, 'after': after}, 'parametric')
    assert paired['p'] < 0.001 < unpaired['p']           # pairing reveals the shift
    assert paired['ci'][1] < -0.4 and paired['ci'][2] > -0.6
    w = gt.compare_with({'before': before, 'after': after}, 'wilcoxon', (s, a, b))
    assert w['p'] < 0.01 and w['n_pairs'] == 8


def test_paired_test_explains_missing_pairs():
    r = gt.compare_with({'a': VALS[0], 'b': VALS[1]}, 'paired_t', ([], np.array([]),
                                                                   np.array([])))
    assert r['test'] is None and 'Sample' in r['note']


def test_sample_means_and_replicate_warning():
    groups = ['A'] * 6 + ['B'] * 6
    samples = ['m1'] * 3 + ['m2'] * 3 + ['m3'] * 3 + ['m4'] * 3
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12.0]
    g, s, v = gt.sample_means(groups, samples, values)
    assert (g, s, v) == (['A', 'A', 'B', 'B'], ['m1', 'm2', 'm3', 'm4'], [2.0, 5.0, 8.0, 11.0])
    assert gt.replicate_warnings(groups, samples) == [('A', 6, 2), ('B', 6, 2)]
    assert gt.replicate_warnings(groups, [f'x{i}' for i in range(12)]) == []


def test_confidence_intervals_checks_outliers_sentence():
    d, lo, hi = gt.mean_difference_ci(VALS[0], VALS[1])
    assert (lo, hi) == pytest.approx((-2.851143911086388, 0.6011352237446508), rel=1e-9)
    g, glo, ghi = gt.hedges_g_ci(VALS[0], VALS[1])
    assert glo < g < ghi
    checks = gt.assumption_checks({'A': VALS[0], 'B': VALS[1], 'C': np.r_[VALS[2], 40.0]})
    assert any('Not bell-shaped' in t for t in checks['advice'])
    assert gt.outliers(np.r_[np.arange(10.0), 100.0]) == [10]
    r = gt.compare_with({'A': VALS[0], 'B': VALS[1]}, 'welch_gh')
    assert r['sentence'].startswith("Welch t-test: t(") and '95 % CI' in r['sentence']


# --- the window -----------------------------------------------------------------------

@pytest.fixture
def quiet(monkeypatch):
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))


def _spectra(n_per_map=6):
    x = np.linspace(400, 1800, 200)
    out = []
    for m, h in (('mapA', 1.0), ('mapB', 1.0), ('mapC', 1.6), ('mapD', 1.6)):
        for i in range(n_per_map):
            out.append({'label': f'{m} [r0_c{i}]', 'x_scale': x,
                        'y_scale': h * np.exp(-((x - 1000) / 20) ** 2)
                        + rng.normal(0, 0.02, x.size), 'metadata': {}})
    return out


def test_window_sample_column_per_sample_and_warning(quiet):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    spectra = _spectra()
    remembered = {}
    d = GroupStatisticsDialog(spectra, None, {}, remembered)
    d.table.set_values(['ctrl'] * 12 + ['treat'] * 12)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('max'))
    d.a_from.setValue(950)
    d.a_to.setValue(1050)
    d.compute()                                       # Sample column empty: as before
    assert 'not independent replicates' not in d.note.text()
    assert d.comparison['p'] < 1e-6
    d.table.set_values(gs.groups_from_root_name(d.labels), col=2)   # Sample = map
    assert d.samples()[0] == 'mapA'
    d.compute()                                       # 12 spectra from 2 maps per group
    assert 'not independent replicates' in d.note.text()
    d.per_sample_check.setChecked(True)
    d.compute()                                       # now 2 values per group
    assert [len(v) for v in d.data.values()] == [2, 2]
    assert 'not independent replicates' not in d.note.text()
    assert 'Few independent samples' in d.note.text()
    assert 'one value per sample' in d.tests_view.toPlainText()
    d.accept()
    assert remembered['per_sample'] is True and remembered['_samples']['mapA [r0_c0]'] == 'mapA'
    d.deleteLater()


def test_window_new_methods_extras_outliers_and_sentence(quiet, tmp_path):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    spectra = _spectra()
    d = gsd.GroupStatisticsDialog(spectra, None, {})
    d.table.set_values(['a'] * 6 + ['b'] * 6 + ['c'] * 12)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('max'))
    d.a_from.setValue(950)
    d.a_to.setValue(1050)
    for method in gt.METHODS:
        if method in gt.PAIRED:
            continue
        d.test_combo.setCurrentIndex(d.test_combo.findData(method))
        d.compute()
        assert d.comparison['test'], method
        text = d.tests_view.toPlainText()
        assert 'Checks of the test' in text and 'Results sentence' in text
    d.test_combo.setCurrentIndex(d.test_combo.findData('welch_gh'))
    d.compute()
    assert 'Welch ANOVA' in d.tests_view.toPlainText() and '95 % CI' in d.tests_view.toPlainText()
    d.copy_results_sentence()
    assert QApplication.clipboard().text().startswith('Welch ANOVA')
    d.outliers_check.setChecked(True)                 # redraw with circles, no error
    out = tmp_path / 'r.xlsx'
    gsd.export_results(str(out), d.labels, d.groups(), d.values, d.data, d.comparison,
                       d.value_label(), samples=d.samples(), report=True)
    import pandas as pd
    assert set(pd.read_excel(out, sheet_name=None)) == {'Values', 'Summary', 'Tests', 'Report'}
    d.deleteLater()


def test_window_paired(quiet):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    x = np.linspace(400, 1800, 200)
    spectra = []
    for s in range(6):
        base = 1 + s * 0.5                          # samples differ a lot
        for when, shift in (('before', 0.0), ('after', 0.1)):
            spectra.append({'label': f'{when}_s{s}', 'x_scale': x, 'metadata': {},
                            'y_scale': (base + shift) * np.exp(-((x - 1000) / 20) ** 2)})
    d = GroupStatisticsDialog(spectra, None, {})
    d.table.set_values([sp['label'].split('_')[0] for sp in spectra])
    d.table.set_values([sp['label'].split('_')[1] for sp in spectra], col=2)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('max'))
    d.a_from.setValue(950)
    d.a_to.setValue(1050)
    d.test_combo.setCurrentIndex(d.test_combo.findData('paired_t'))
    d.compute()
    assert d.comparison['test'] == 'Paired t-test' and d.comparison['n_pairs'] == 6
    assert d.comparison['p'] < 1e-6
    d.deleteLater()


def test_hedges_g_ci_small_groups_uses_the_approximation():
    a, b = np.array([1.0, 1.1, 1.3]), np.array([0.9, 1.0, 1.05])
    g, lo, hi = gt.hedges_g_ci(a, b)
    se = np.sqrt(6 / 9 + g ** 2 / 12)
    assert (lo, hi) == pytest.approx((g - 1.959964 * se, g + 1.959964 * se), rel=1e-5)
    assert lo < 0 < hi                         # not "significant" with 3 vs 3


def test_window_recomputes_when_the_test_changes_and_shows_exact_p(quiet, monkeypatch):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    spectra = _spectra()
    d = gsd.GroupStatisticsDialog(spectra, None, {}, {})
    d.table.set_values(['ctrl'] * 12 + ['treat'] * 12)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('max'))
    d.a_from.setValue(950)
    d.a_to.setValue(1050)
    d.test_combo.setCurrentIndex(d.test_combo.findData('nonparametric'))
    assert d.comparison is None                      # nothing before the first Compute
    calls = []
    real = gsd.gv.compute_values
    monkeypatch.setattr(gsd.gv, 'compute_values', lambda *a, **k: calls.append(1) or real(*a, **k))
    d.compute()
    assert d.comparison['test'] == 'Mann–Whitney U test'
    d.test_combo.setCurrentIndex(d.test_combo.findData('parametric'))
    assert d.comparison['test'] == 'Welch t-test'    # recomputed by itself
    assert len(calls) == 1                           # the values were reused
    text = d.tests_view.toPlainText()
    assert 'p < 0.0001 (p = ' in text and '× 10' in text
    d.test_combo.setCurrentIndex(d.test_combo.findData('welch_gh'))
    assert 'With two groups this is the Welch t-test' in d.note.text()
    d.test_combo.setCurrentIndex(d.test_combo.findData('dunn'))
    assert 'Mann–Whitney U test' in d.note.text()
    d.test_combo.setCurrentIndex(d.test_combo.findData('permutation'))
    assert 'smallest possible' in d.tests_view.toPlainText()
    d.per_sample_check.setChecked(True)              # recomputes too
    assert 'one value per sample' in d.tests_view.toPlainText()
    d.deleteLater()


def test_exact_p_text():
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import _exact_p
    assert _exact_p(6.1e-8) == ' (p = 6.1 × 10⁻⁸)'
    assert _exact_p(0.03) == '' and _exact_p(float('nan')) == ''


def test_paired_tests_only_for_two_groups_and_title_without_test(quiet):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    spectra = _spectra()
    d = gsd.GroupStatisticsDialog(spectra, None, {}, {'test': 'paired_t'})
    model = d.test_combo.model()
    paired_rows = [i for i in range(d.test_combo.count()) if d.test_combo.itemData(i) in gt.PAIRED]
    d.table.set_values(['a'] * 12 + ['b'] * 12)               # two groups, but no pairs
    assert not any(model.item(i).isEnabled() for i in paired_rows)
    assert 'same samples' in model.item(paired_rows[0]).toolTip()
    assert d.test_combo.currentData() == 'paired_t'           # kept while typing
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('max'))
    d.a_from.setValue(950)
    d.a_to.setValue(1050)
    d.compute()                                               # no pairs: no test
    assert d.comparison['test'] is None
    title = d.figure.axes[0].get_title()
    assert title.startswith('No test') and 'Sample' in title
    d.table.set_values(['a'] * 8 + ['b'] * 8 + ['c'] * 8)     # three groups
    assert not any(model.item(i).isEnabled() for i in paired_rows)
    assert 'exactly two groups' in model.item(paired_rows[0]).toolTip()
    assert d.test_combo.currentData() == 'parametric'         # switched, recomputed
    assert d.comparison['test'] == 'One-way ANOVA'
    assert 'switched to Parametric' in d.note.text()
    d.table.set_values(['a'] * 12 + ['b'] * 12)
    d.table.set_values([f's{i % 12}' for i in range(24)], col=2)   # 12 pairs
    assert all(model.item(i).isEnabled() for i in paired_rows)
    d.deleteLater()


def test_remembered_paired_test_without_pairs_switches_when_the_window_opens(quiet):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    spectra = _spectra()
    saved = {sp['label']: g for sp, g in zip(spectra, ['a'] * 12 + ['b'] * 12)}
    d = gsd.GroupStatisticsDialog(spectra, None, saved, {'test': 'paired_t'})
    assert d.test_combo.currentData() == 'parametric'
    assert 'at least 3 samples measured in both groups' in d.note.text()
    d.deleteLater()


def test_table_colours_match_the_plot(quiet):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    spectra = _spectra()
    d = gsd.GroupStatisticsDialog(spectra, None, {}, {})
    d.table.set_values(['b'] * 12 + ['a'] * 12)
    d.table.set_values(['m1'] * 6 + ['m2'] * 6 + ['m1'] * 6 + [''] * 6, col=2)
    cmap = d.group_colours()
    assert list(cmap) == ['b', 'a']                            # order of the table
    assert d.table.item(0, 1).background().color().name() == gsd._tint(cmap['b'])
    assert d.table.item(23, 1).background().color().name() == gsd._tint(cmap['a'])
    # the same sample, the same colour; no sample, no colour
    assert d.table.item(0, 2).background().color() == d.table.item(12, 2).background().color()
    assert d.table.item(0, 2).background().color() != d.table.item(6, 2).background().color()
    assert d.table.item(23, 2).background().style() == 0       # Qt.NoBrush
    undo_before = len(d.table._undo)
    d._colour_table()
    assert len(d.table._undo) == undo_before                   # colouring is not an edit
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('max'))
    d.a_from.setValue(950)
    d.a_to.setValue(1050)
    d.compute()
    from matplotlib.colors import to_hex
    dots = [c for c in d.figure.axes[0].collections if len(c.get_offsets())]
    assert to_hex(dots[0].get_facecolor()[0]) == cmap['b'].lower()
    d.deleteLater()


def test_switch_from_a_remembered_paired_test_is_shown_when_the_window_opens(quiet):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    spectra = _spectra()
    saved = {sp['label']: g for sp, g in zip(spectra, ['a'] * 8 + ['b'] * 8 + ['c'] * 8)}
    d = gsd.GroupStatisticsDialog(spectra, None, saved, {'test': 'wilcoxon'})
    assert d.test_combo.currentData() == 'parametric'
    assert 'switched to Parametric' in d.note.text()          # before any Compute
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('max'))
    d.a_from.setValue(950)
    d.a_to.setValue(1050)
    d.compute()
    assert 'switched to Parametric' in d.note.text()          # still said with the result
    assert 'E65100' in d.note.styleSheet()                    # in orange, as before Compute
    d.compute()
    assert 'switched to Parametric' not in d.note.text()      # said once
    d.deleteLater()


def test_ctrl_z_works_after_pressing_a_button(quiet):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QPushButton
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    d = gsd.GroupStatisticsDialog(_spectra(), None, {}, {})
    d.table.set_values(['a'] * 12 + ['b'] * 12)
    clear = [b for b in d.findChildren(QPushButton) if b.text() == 'Clear all groups'][0]
    # as after a real click: the window is the active one and the button has the
    # focus (otherwise a window left open by an earlier test can keep the focus
    # on Windows and receive the Ctrl+Z)
    d.show()
    QApplication.setActiveWindow(d)
    clear.setFocus()
    clear.click()                                    # removes all groups
    assert not any(d.groups())
    QTest.keyClick(clear, Qt.Key_Z, Qt.ControlModifier)   # the button has the focus
    assert d.groups() == ['a'] * 12 + ['b'] * 12
    d.close()
    d.deleteLater()


def test_outdated_hint_colours_and_similar_group_names(quiet):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    d = gsd.GroupStatisticsDialog(_spectra(), None, {}, {})
    d.table.set_values(['ctrl'] * 12 + ['treat'] * 12)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('max'))
    d.a_from.setValue(950)
    d.a_to.setValue(1050)
    assert not d.outdated_label.isVisibleTo(d)               # nothing computed yet
    d.compute()
    assert not d.outdated_label.isVisibleTo(d)
    d.a_to.setValue(1060)                                    # the value changed
    assert d.outdated_label.isVisibleTo(d) and 'FFE0B2' in d.compute_btn.styleSheet()
    d.a_to.setValue(1050)                                    # back: up to date again
    assert not d.outdated_label.isVisibleTo(d)
    d.table.set_values(['ctrl'] * 11 + ['treat'] * 13)       # the groups changed
    assert d.outdated_label.isVisibleTo(d)
    d.compute()
    assert not d.outdated_label.isVisibleTo(d) and 'FFE0B2' not in d.compute_btn.styleSheet()
    # colours: summary line, Summary tab, Values tab
    cmap = d.group_colours()
    assert cmap['ctrl'] in d.group_summary.text()
    assert d.summary_table.item(0, 0).background().color().name() == gsd._tint(cmap['ctrl'])
    assert d.values_table.item(23, 1).background().color().name() == gsd._tint(cmap['treat'])
    # names that differ only in case / spaces
    d.table.set_values(['ctrl'] * 12 + ['Ctrl'] * 12)
    assert 'differ only in upper/lower case' in d.group_summary.text()
    d.deleteLater()


def test_right_click_wording(quiet, monkeypatch):
    from PyQt5.QtWidgets import QMenu
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    d = gsd.GroupStatisticsDialog(_spectra(), None, {}, {})
    texts = []
    monkeypatch.setattr(QMenu, 'exec_', lambda self, *a: texts.extend(
        x.text() for x in self.actions()) or None)
    d.table.setCurrentCell(0, 1)
    d._table_menu(d.table.rect().center())
    assert 'Remove group of selected rows (Delete)' in texts
    texts.clear()
    d.table.setCurrentCell(0, 2)
    d._table_menu(d.table.rect().center())
    assert 'Clear sample of selected rows (Delete)' in texts
    d.deleteLater()


def test_a_new_group_does_not_shift_the_colours_of_the_others(quiet):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    d = gsd.GroupStatisticsDialog(_spectra(), None, {}, {})
    d.table.set_values(['ctrl'] * 12 + ['treat'] * 12)
    before = d.group_colours()
    d.table.set_values(['Ctrl'] + ['ctrl'] * 11 + ['treat'] * 12)   # a new group first
    after = d.group_colours()
    assert after['ctrl'] == before['ctrl'] and after['treat'] == before['treat']
    assert after['Ctrl'] not in (before['ctrl'], before['treat'])
    d.deleteLater()


def test_repeated_sample_names_are_listed():
    groups = ['after'] * 4 + ['before'] * 4
    samples = ['s1', 's66', 's66', 's4', 'm', 'm', 'm', '']
    assert gt.repeated_sample_names(groups, samples) == {'after': [('s66', 2)],
                                                         'before': [('m', 3)]}
    assert gt.repeated_sample_names(groups, [''] * 8) == {}
    assert gt.repeated_sample_names(groups, samples, values=[1, 1, np.nan, 1] + [1] * 4) == {
        'before': [('m', 3)]}


def test_repeated_sample_warning_names_them_and_says_what_to_do():
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        repeated_samples_text)
    text = repeated_samples_text(['after'] * 3 + ['before'] * 3,
                                 ['s1', 's66', 's66', 's1', 's2', 's3'])
    assert '“after”: s66 (2 spectra)' in text and 'within a group' in text
    assert 'e.g. s1 in \u201cafter\u201d and \u201cbefore\u201d, is fine' in text
    assert 'One value per sample' in text and 'different sample names' in text
    assert 'too small' not in text                       # no claim about the p-value
    many = repeated_samples_text(['a'] * 10, ['c1', 'c1', 'c2', 'c2', 'c3', 'c3', 'c4', 'c4',
                                              'c5', 'c5'])
    assert 'c1 (2 spectra), c2 (2 spectra), c3 (2 spectra) and 2 more' in many
    assert repeated_samples_text(['a', 'b'], ['', '']) == ''
    assert 'is fine' not in many                      # no name in two groups there
    # the same name in two groups only (s7 before / s7 after): no warning at all
    assert repeated_samples_text(['after', 'before'], ['s7', 's7']) == ''


def test_unpaired_samples_and_the_pairs_note():
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import paired_note
    groups = ['after', 'before'] * 4 + ['after', 'before']
    samples = ['s1', 's1', 's2', 's2', 's66', 's5', 's66', 's6', '', 's7']
    only, no_name = gt.unpaired_samples(groups, samples, None, 'before', 'after')
    assert only == {'s66': 'after', 's5': 'before', 's6': 'before', 's7': 'before'}
    assert no_name == 1
    text = paired_note(2, groups, samples, None, 'before', 'after')
    assert text.startswith('2 pairs (Sample column). Left out')
    assert 's5, s6, s7 (only in “before”); s66 (only in “after”)' in text
    assert '1 spectrum without a sample name' in text
    assert paired_note(2, ['a', 'b', 'a', 'b'], ['x', 'x', 'y', 'y'], None, 'a', 'b') == \
        '2 pairs (Sample column).'                          # nothing left out


def test_spectra_tab_outdated_hint(quiet):
    """After Compare spectra, changing a group or sample shows the orange
    line (and an orange Compare spectra button) even without Compute."""
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    d = gsd.GroupStatisticsDialog(_spectra(), None, {}, {})
    d.table.set_values(['ctrl'] * 12 + ['treat'] * 12)
    d.compute_spectra()
    assert not d.outdated_label.isVisibleTo(d)
    d.table.set_values(['ctrl'] * 11 + ['treat'] * 13)
    assert d.outdated_label.isVisibleTo(d) and 'Compare spectra' in d.outdated_label.text()
    assert 'FFE0B2' in d.sp_compare_btn.styleSheet()
    assert 'FFE0B2' not in d.compute_btn.styleSheet()        # nothing was computed there
    d.compute_spectra()
    assert not d.outdated_label.isVisibleTo(d) and 'FFE0B2' not in d.sp_compare_btn.styleSheet()
    d.deleteLater()


def test_enter_does_not_open_set_group(quiet, monkeypatch):
    """Enter in a table cell (not being edited) or in a number box must not
    press a button: before, 'Set group of selected rows...' was the dialog's
    default button and its window opened."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QInputDialog, QPushButton
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    calls = []
    monkeypatch.setattr(QInputDialog, 'getItem',
                        staticmethod(lambda *a, **k: (calls.append(1), ('x', False))[1]))
    d = gsd.GroupStatisticsDialog(_spectra(), None, {}, {})
    d.show()
    assert not any(b.isDefault() for b in d.findChildren(QPushButton))
    d.table.setFocus()
    d.table.setCurrentCell(3, 2)
    QTest.keyClick(d.table, Qt.Key_Return)
    d.x_spin.setFocus()
    QTest.keyClick(d.x_spin, Qt.Key_Return)
    assert calls == []
    d.close()
    d.deleteLater()
