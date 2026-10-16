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
