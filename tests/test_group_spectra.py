"""Group Statistics, comparison along the whole spectrum (group_spectra.py
and the window's Spectra tab)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from scipy import stats
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.visualization_analysis import group_spectra as gsp
from src.modules.visualization_analysis import group_tests as gt

app = QApplication.instance() or QApplication([])
X = np.linspace(400, 1800, 281)


@pytest.fixture
def quiet(monkeypatch):
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))


def _peak(x, c, h, w=15):
    return h * np.exp(-((x - c) / w) ** 2)


def _groups_data(seed=1, n=10, effect=0.3, scale=0.0):
    """Two groups, identical except a band at 1000 (+effect in 'b');
    optional random overall intensity."""
    rng = np.random.default_rng(seed)
    sp, groups = [], []
    for g, h in (('a', 1.0), ('b', 1.0 + effect)):
        for i in range(n):
            y = 1 + _peak(X, 600, 2.0) + _peak(X, 1000, h) + rng.normal(0, 0.03, X.size)
            y = y * (1 + rng.uniform(-scale, scale))
            sp.append({'label': f'{g}{i}', 'x_scale': X, 'y_scale': y, 'metadata': {}})
            groups.append(g)
    return sp, groups


def test_benjamini_hochberg_and_holm_by_hand():
    p = np.array([0.01, 0.04, 0.03, 0.005])
    assert gsp.adjust(p, 'fdr') == pytest.approx([0.02, 0.04, 0.04, 0.02])
    assert gsp.adjust(p, 'holm') == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert gsp.adjust(np.array([np.nan, 0.01]), 'fdr') == pytest.approx([1.0, 0.02])


def test_pointwise_tests_match_scipy_column_by_column():
    rng = np.random.default_rng(0)
    mats = [rng.normal(0, 1, (8, 5)), rng.normal(0.5, 2, (10, 5)), rng.normal(1, 1, (7, 5))]
    p, name = gsp.pointwise_p(mats, 'parametric')
    assert name == 'One-way ANOVA'
    assert p == pytest.approx([stats.f_oneway(*[M[:, j] for M in mats]).pvalue for j in range(5)])
    p, name = gsp.pointwise_p(mats, 'welch_gh')
    assert name == 'Welch ANOVA'
    assert p == pytest.approx([gt.welch_anova([M[:, j] for M in mats])[3] for j in range(5)])
    p, _ = gsp.pointwise_p(mats[:2], 'parametric')
    assert p == pytest.approx(stats.ttest_ind(mats[0], mats[1], equal_var=False).pvalue)
    p, name = gsp.pointwise_p(mats, 'nonparametric')
    assert name == 'Kruskal–Wallis test'
    assert p == pytest.approx([stats.kruskal(*[M[:, j] for M in mats]).pvalue for j in range(5)])
    p, _ = gsp.pointwise_p(mats[:2], 'permutation')
    assert np.all((p > 0) & (p <= 1))


def test_significant_ranges():
    x = np.arange(10.0)
    q = np.array([0.5, 0.01, 0.02, 0.5, 0.5, 0.001, 0.5, 0.03, 0.04, 0.01])
    assert gsp.significant_ranges(x, q) == [(1.0, 2.0, 2, 1.0), (5.0, 5.0, 1, 5.0),
                                            (7.0, 9.0, 3, 9.0)]


def test_the_band_that_differs_is_found_and_nothing_else():
    sp, groups = _groups_data()
    r = gsp.compare_spectra(sp, groups)
    assert r['test'] == 'Welch t-test' and r['n'] == {'a': 10, 'b': 10}
    wide = [rg for rg in r['ranges'] if rg[2] >= 3]
    assert len(wide) == 1
    a, b, k, strongest = wide[0]
    assert 970 <= a < 1000 < b <= 1030 and abs(strongest - 1000) <= 10
    same, groups = _groups_data(effect=0.0)
    assert not [rg for rg in gsp.compare_spectra(same, groups)['ranges'] if rg[2] >= 3]


def test_normalization_by_a_band_removes_the_overall_intensity():
    sp, groups = _groups_data(scale=0.3, seed=4)
    raw = gsp.compare_spectra(sp, groups)
    norm = gsp.compare_spectra(sp, groups, normalization='band', band=(560, 640),
                               rng=(800, 1200))           # the band outside the range
    assert min(norm['q']) < min(raw['q'])
    assert any(a <= 1000 <= b for a, b, k, m in norm['ranges'])
    assert norm['x'][0] >= 800 and norm['x'][-1] <= 1200
    assert 'shorter' in gsp.ranges_text(norm) or 'strongest at' in gsp.ranges_text(norm)


def test_different_x_axes_are_interpolated_onto_the_coarsest():
    sp, groups = _groups_data()
    x2 = np.linspace(450, 1750, 131)
    sp[0] = dict(sp[0], x_scale=x2, y_scale=np.interp(x2, X, sp[0]['y_scale']))
    r = gsp.compare_spectra(sp, groups)
    assert not r['same_axis'] and len(r['x']) == 131 and r['x'][0] == 450
    assert any('interpolated' in n for n in r['notes'])


def test_per_sample_and_paired():
    sp, groups = _groups_data(n=8)
    samples = [f's{i % 4}' for i in range(16)]           # 2 spectra per sample and group
    r = gsp.compare_spectra(sp, groups, samples, per_sample=True)
    assert r['n'] == {'a': 4, 'b': 4} and r['unit'] == 'samples'
    r = gsp.compare_spectra(sp, groups, samples, method='paired_t')
    assert r['test'] == 'Paired t-test' and r['n_pairs'] == 4
    with pytest.raises(ValueError):
        gsp.compare_spectra(sp, groups, [''] * 16, method='paired_t')


def test_export_table_columns():
    sp, groups = _groups_data()
    df = gsp.export_table(gsp.compare_spectra(sp, groups))
    assert list(df.columns) == ['x', 'mean a', 'SD a', 'n a', 'mean b', 'SD b', 'n b', 'p',
                                'q (FDR)']
    assert len(df) == len(X)


def test_window_spectra_tab(quiet, tmp_path, monkeypatch):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    sp, groups = _groups_data()
    remembered = {}
    d = GroupStatisticsDialog(sp, None, {}, remembered)
    assert d.tabs.tabText(4) == 'Spectra'
    d.compute_spectra()                                  # no groups yet
    assert d.spectra_result is None and 'groups' in d.sp_note.text()
    d.table.set_values(groups)
    d.compute_spectra()
    assert d.spectra_result['ranges'] and 'differ significantly' in d.sp_note.text()
    assert d.sp_save_btn.isEnabled() and d.sp_export_btn.isEnabled()
    d.table.set_values([f'c{i % 2}' for i in range(20)], col=2)   # 10 spectra / sample
    d.compute_spectra()
    assert 'not independent' in d.sp_note.text()
    d.per_sample_check.setChecked(True)
    d.compute_spectra()
    assert 'not independent' not in d.sp_note.text()
    out = tmp_path / 't.xlsx'
    from PyQt5.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, 'getSaveFileName',
                        staticmethod(lambda *a, **k: (str(out), 'Excel workbook (*.xlsx)')))
    d.export_spectra_table()
    assert out.exists()
    d.sp_norm_combo.setCurrentIndex(d.sp_norm_combo.findData('snv'))
    d.compute_spectra()
    d.accept()
    assert remembered['spectra_norm'] == 'snv'
    d.deleteLater()


def test_window_without_common_range(quiet):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    a = {'label': 'a', 'x_scale': np.linspace(0, 10, 20), 'y_scale': np.ones(20), 'metadata': {}}
    b = {'label': 'b', 'x_scale': np.linspace(20, 30, 20), 'y_scale': np.ones(20), 'metadata': {}}
    d = GroupStatisticsDialog([a, b], None, {}, {})
    assert not d.sp_compare_btn.isEnabled() and 'no x-range in common' in d.sp_note.text()
    d.deleteLater()


def test_permanova_equals_the_distance_matrix_formula():
    rng = np.random.default_rng(1)
    mats = [rng.normal(0, 1, (5, 7)), rng.normal(0.5, 1, (6, 7)), rng.normal(0, 2, (4, 7))]
    Y = np.vstack(mats)
    lab = np.repeat([0, 1, 2], [5, 6, 4])
    N = len(Y)
    D2 = ((Y[:, None, :] - Y[None, :, :]) ** 2).sum(-1)
    sst = D2[np.triu_indices(N, 1)].sum() / N
    ssw = sum(D2[np.ix_(lab == g, lab == g)][np.triu_indices((lab == g).sum(), 1)].sum()
              / (lab == g).sum() for g in range(3))
    F, p = gsp.permanova(mats, n_perm=199)
    assert F == pytest.approx(((sst - ssw) / 2) / (ssw / (N - 3)))
    assert 0 < p <= 1
    sp, groups = _groups_data()
    r = gsp.compare_spectra(sp, groups)
    assert r['permanova'][1] < 0.001 and 'PERMANOVA' in gsp.overall_text(r)
    same, groups0 = _groups_data(effect=0.0)
    assert gsp.compare_spectra(same, groups0)['permanova'][1] > 0.05
    samples = [f's{i % 10}' for i in range(20)]
    assert gsp.overall_text(gsp.compare_spectra(sp, groups, samples, method='paired_t')) == ''
