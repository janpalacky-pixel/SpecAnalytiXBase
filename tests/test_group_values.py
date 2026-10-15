"""Group Statistics values (group_values.py): the 2D Map / Band Ratio
metrics for one band, two bands with their own metric and an operation, and
whole-spectrum values (PCA, SVD, similarity to a reference group)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.visualization_analysis import group_values as gv

app = QApplication.instance() or QApplication([])
X = np.linspace(0.0, 20.0, 81)                          # step 0.25


def _peak(x, h=5.0, c=10.0, w=3.0):
    return h * np.exp(-4 * np.log(2) * ((x - c) / w) ** 2)


def _sp(label, y, x=X):
    return {'label': label, 'x_scale': x, 'y_scale': y, 'metadata': {}}


# --- one band -----------------------------------------------------------------------

def test_intensity_at_x_average_and_fit_resist_one_outlier():
    y = 1.0 + 0.1 * X
    y[np.argmin(abs(X - 10))] += 3.0                    # one bad point at x = 10
    assert gv.intensity_at_x(X, y, 10.0, 'point') == pytest.approx(5.0)
    assert gv.intensity_at_x(X, y, 10.0, 'average', 2.0) == pytest.approx(2.0, abs=0.2)
    assert abs(gv.intensity_at_x(X, y, 10.0, 'fit', 2.0) - 2.0) < 0.5   # point: off by 3
    assert np.isnan(gv.intensity_at_x(X, y, 19.5, 'average', 2.0))   # window leaves spectrum


def test_parabola_top_ignores_a_spike_and_lies_between_points():
    rng = np.random.default_rng(0)
    y = _peak(X, c=10.1) + rng.normal(0, 0.05, X.size)
    y[np.argmin(abs(X - 12))] += 4.5                    # a spike on the flank
    j = int(np.argmax(y))
    assert X[j] == pytest.approx(12.0)                  # the highest point is the spike
    px, py = gv.parabola_top(X, y)
    assert px == pytest.approx(10.1, abs=0.15) and py == pytest.approx(5.0, abs=0.2)
    rng_ = (2, 18)
    assert gv.band_value(X, y, 'Peak position', rng_, 'parabola') == pytest.approx(10.1, abs=0.15)
    assert gv.band_value(X, y, 'Peak position', rng_, 'point') == pytest.approx(12.0)


def test_band_metrics_like_the_2d_map():
    y = _peak(X) + 1.0 + 0.05 * X                        # band on a sloping background
    rng = (2, 18)
    assert gv.band_value(X, y, 'Baseline-corrected integral', rng) == pytest.approx(
        5.0 * 3.0 * np.sqrt(np.pi / (4 * np.log(2))), rel=0.01)
    assert gv.band_value(X, _peak(X), 'FWHM', rng) == pytest.approx(3.0, abs=0.1)
    assert gv.band_value(X, _peak(X), 'Variance', rng) == pytest.approx(np.var(_peak(X)[(X >= 2) & (X <= 18)]))
    assert np.isnan(gv.band_value(X, y, 'Integral', (15, 25)))      # not covered


def test_fitted_metric_uses_the_peak_fit():
    spectra = [_sp('a', _peak(X, c=9.8)), _sp('b', _peak(X, c=10.3))]
    vals, _ = gv.compute_values(spectra, ['g', 'g'],
                                {'kind': 'fit_center', 'range_a': (3, 17)})
    assert vals == pytest.approx([9.8, 10.3], abs=1e-3)


# --- two bands ----------------------------------------------------------------------

def test_two_bands_each_with_its_own_metric_and_all_operations():
    y = _peak(X, h=4.0, c=6.0, w=2.0) + _peak(X, h=2.0, c=14.0, w=2.0)
    spectra = [_sp('s', y)]
    base = {'kind': 'ratio', 'range_a': (3, 9), 'range_b': (11, 17),
            'metric_a': 'Peak intensity', 'metric_b': 'Peak intensity'}
    expected = {'A / B': 2.0, 'A − B': 2.0, 'A + B': 6.0, 'A × B': 8.0,
                '(A − B) / (A + B)': 1 / 3, 'log₂(A / B)': 1.0}
    for op, value in expected.items():
        vals, _ = gv.compute_values(spectra, ['g'], dict(base, operation=op))
        assert vals[0] == pytest.approx(value, rel=1e-6), op
    vals, _ = gv.compute_values(spectra, ['g'], dict(base, metric_b='Peak position',
                                                     operation='A − B'))
    assert vals[0] == pytest.approx(4.0 - 14.0)


def test_undefined_combinations_give_no_value():
    assert np.isnan(gv.combine([1.0], [0.0], 'A / B')[0])
    assert np.isnan(gv.combine([-1.0], [2.0], 'log₂(A / B)')[0])
    assert np.isnan(gv.combine([1.0], [-1.0], '(A − B) / (A + B)')[0])


def test_old_band_ratio_is_unchanged():
    from src.modules.visualization_analysis import group_statistics as gs
    y = _peak(X, c=6.0, w=2.0) + _peak(X, h=2.5, c=14.0, w=2.0)
    sp = _sp('s', y)
    old = gs.spectrum_value(sp, 'ratio', range_a=(3, 9), range_b=(11, 17))
    vals, _ = gv.compute_values([sp], ['g'], {'kind': 'ratio', 'range_a': (3, 9),
                                              'range_b': (11, 17)})
    assert vals[0] == pytest.approx(old) == pytest.approx(2.0, rel=1e-3)


# --- whole spectrum -----------------------------------------------------------------

def _two_groups(n=5, shift=0.6, seed=1):
    rng = np.random.default_rng(seed)
    a = [_sp(f'a{i}', _peak(X, c=10) + rng.normal(0, .05, X.size)) for i in range(n)]
    b = [_sp(f'b{i}', _peak(X, c=10 + shift) + rng.normal(0, .05, X.size)) for i in range(n)]
    return a + b, ['A'] * n + ['B'] * n


def test_pca_score_separates_the_groups_and_reports_the_variance():
    spectra, groups = _two_groups()
    vals, info = gv.compute_values(spectra, groups, {'kind': 'pca', 'component': 1})
    a, b = vals[:5], vals[5:]
    assert (a.max() < b.min()) or (b.max() < a.min())
    assert info['explained'] > 50
    groups[0] = ''                                       # no group: no value
    vals, _ = gv.compute_values(spectra, groups, {'kind': 'pca', 'component': 1})
    assert np.isnan(vals[0]) and np.isfinite(vals[1:]).all()


def test_reference_group_is_compared_leave_one_out():
    spectra, groups = _two_groups()
    corr, _ = gv.compute_values(spectra, groups, {'kind': 'corr_ref', 'reference_group': 'A'})
    dist, _ = gv.compute_values(spectra, groups, {'kind': 'dist_ref', 'reference_group': 'A'})
    assert corr[:5].min() > corr[5:].max()               # A is closer to A's mean
    assert dist[:5].max() < dist[5:].min()
    assert (corr[:5] < 1.0).all()                        # not compared with itself


def test_whole_spectrum_needs_one_x_axis():
    spectra, groups = _two_groups()
    spectra[0] = _sp('a0', _peak(X + 0.1), x=X + 0.1)
    assert not gv.same_x_axis(spectra)
    vals, info = gv.compute_values(spectra, groups, {'kind': 'pca'})
    assert np.isnan(vals).all() and 'same x-axis' in info['note']


def test_whole_spectrum_within_a_range():
    spectra, groups = _two_groups()
    vals, _ = gv.compute_values(spectra, groups, {'kind': 'svd', 'component': 1,
                                                  'whole_use_range': True,
                                                  'range_a': (0, 2)})   # flat part only
    assert np.isfinite(vals).all()


# --- the window ---------------------------------------------------------------------

@pytest.fixture
def quiet(monkeypatch):
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))


def test_window_offers_whole_spectrum_only_for_one_x_axis(quiet):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    spectra, _ = _two_groups()
    d = GroupStatisticsDialog(spectra, None, {})
    i = d.kind_combo.findData('pca')
    assert d.kind_combo.model().item(i).isEnabled()
    d.deleteLater()
    spectra[0] = _sp('a0', _peak(X + 0.1), x=X + 0.1)
    d = GroupStatisticsDialog(spectra, None, {})
    assert not d.kind_combo.model().item(d.kind_combo.findData('pca')).isEnabled()
    assert d.kind_combo.currentData() == 'intensity_at_x'  # not a section header
    d.deleteLater()


def test_window_two_bands_and_reference_group_and_settings_remembered(quiet):
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    spectra, groups = _two_groups()
    remembered = {}
    d = GroupStatisticsDialog(spectra, None, {}, remembered)
    d.table.set_values(groups)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('ratio'))
    assert d.metric_a_combo.isVisibleTo(d) and d.operation_row.isVisibleTo(d)
    d.metric_a_combo.setCurrentText('Fitted peak area')
    assert d.fit_row.isVisibleTo(d)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('corr_ref'))
    assert [d.reference_combo.itemText(i) for i in range(d.reference_combo.count())] == ['A', 'B']
    d.reference_combo.setCurrentText('B')
    d.compute()
    assert d.comparison['p'] < 0.01
    assert 'Correlation with mean of “B”' in d.value_label()
    d.accept()
    assert remembered['kind'] == 'corr_ref' and remembered['reference_group'] == 'B'
    d2 = GroupStatisticsDialog(spectra, None, {s['label']: g for s, g in zip(spectra, groups)},
                               remembered)
    assert d2.kind_combo.currentData() == 'corr_ref'
    assert d2.reference_combo.currentText() == 'B'
    assert d2.metric_a_combo.currentText() == 'Fitted peak area'
    d.deleteLater()
    d2.deleteLater()


def test_plot_types_save_and_remembered(quiet, tmp_path, monkeypatch):
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    spectra, groups = _two_groups(n=5)
    remembered = {}
    d = gsd.GroupStatisticsDialog(spectra, None, {}, remembered)
    d.table.set_values(groups)
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('pca'))
    d.compute()
    assert d.save_plot_btn.isEnabled()
    for kind in ('box', 'violin', 'ci'):
        d.plot_combo.setCurrentIndex(d.plot_combo.findData(kind))
        ax = d.figure.axes[0]
        assert len(ax.collections) >= 2                 # the dots of both groups
        texts = ' '.join(t.get_text() for t in d.figure.texts)
        if kind == 'violin':
            assert 'Fewer than 10 values' in texts      # 5 per group: shape unreliable
        if kind == 'ci':
            assert '95 % confidence interval' in texts
    path = tmp_path / 'plot.png'
    monkeypatch.setattr(gsd.QFileDialog, 'getSaveFileName',
                        staticmethod(lambda *a, **k: (str(path), 'PNG image (*.png)')))
    d.save_plot()
    assert path.exists() and path.stat().st_size > 1000
    d.accept()
    assert remembered['plot'] == 'ci'
    d2 = gsd.GroupStatisticsDialog(spectra, None, {}, remembered)
    assert d2.plot_combo.currentData() == 'ci'
    d.deleteLater()
    d2.deleteLater()
