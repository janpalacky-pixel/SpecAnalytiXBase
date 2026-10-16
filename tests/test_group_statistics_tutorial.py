"""The Group Statistics tutorial (help topic 'group_statistics_tutorial')
quotes results of every step on the demo datasets. These tests run the
same steps in the window and check that the quoted numbers still hold."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SYNTH = os.path.join(ROOT, 'resources', 'test_data', 'synthetic')


@pytest.fixture
def quiet(monkeypatch):
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))


def _open(name):
    from src.modules.core.spectrum_manager import SpectrumManager
    from src.views.dialogs.visualization_analysis.group_statistics_dialog import (
        GroupStatisticsDialog)
    m = SpectrumManager()
    m.load_spectrum_from_file(os.path.join(SYNTH, name))
    spectra = [{'label': l, 'x_scale': s.x_scale, 'y_scale': s.y_scale, 'metadata': s.metadata}
               for l, s in m.spectra.items()]
    d = GroupStatisticsDialog(spectra, None, {}, {})
    assert d.table_source.text().startswith('Groups')
    return d


def _two_bands(d, a, b, metric='Integral', op='A / B'):
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('ratio'))
    d.a_from.setValue(a[0]); d.a_to.setValue(a[1])
    d.b_from.setValue(b[0]); d.b_to.setValue(b[1])
    d.metric_a_combo.setCurrentText(metric); d.metric_b_combo.setCurrentText(metric)
    d.operation_combo.setCurrentText(op)


def _one_band(d, kind, lo, hi):
    d.kind_combo.setCurrentIndex(d.kind_combo.findData(kind))
    d.a_from.setValue(lo); d.a_to.setValue(hi)


def _test(d, method):
    d.test_combo.setCurrentIndex(d.test_combo.findData(method))


def _pairs(d):
    return [p['p_holm'] for p in d.comparison['pairs']]


def _means(d):
    return [sum(v) / len(v) for v in d.data.values()]


def test_lesson_1_treatment(quiet):
    d = _open('group_stats_treatment_demo.xlsx')
    _one_band(d, 'area', 1620, 1690); d.compute()
    assert round(d.comparison['p'], 2) == 0.03
    assert [round(p, 2) for p in _pairs(d)] == [0.03, 0.07, 0.88]
    _two_bands(d, (1620, 1690), (1420, 1480)); d.compute()
    r = d.comparison
    assert r['p'] < 1e-4 and max(_pairs(d)) < 1e-4 and round(r['effect'], 2) == 0.82
    assert round(r['pairs'][0]['difference'], 3) == -0.135
    assert [round(p['effect'], 1) for p in r['pairs']] == [-2.9, -4.0, -2.7]
    normality = {g: p for g, n, p in r['checks']['normality']}
    assert round(normality['control'], 4) == 0.0005
    assert round(r['checks']['equal_spread_p'], 3) == 0.013
    assert any('Games' in a for a in r['checks']['advice'])
    control = [l for l, g in zip(d.labels, d.groups()) if g == 'control']
    assert [control[i] for i in r['outliers']['control']] == [
        'group_stats_treatment_demo : control_05']
    _test(d, 'welch_gh'); d.compute()
    assert d.comparison['p'] < 1e-4 and max(_pairs(d)) < 1e-4
    assert d.comparison['sentence'].startswith(
        'Welch ANOVA: F(2, 17.4) = 52.6, p < 0.0001, omega squared (est.) = 0.74')
    _test(d, 'parametric')
    _one_band(d, 'fit_center', 1560, 1610); d.compute()
    assert [round(m, 1) for m in _means(d)] == [1584.9, 1585.6, 1586.4]
    assert d.comparison['p'] < 1e-4
    d.kind_combo.setCurrentIndex(d.kind_combo.findData('pca'))
    d.whole_range_check.setChecked(False)
    d.component_spin.setValue(1); d.compute()
    assert round(d.comparison['p'], 2) == 0.34 and '89.0 %' in d.note.text()
    d.component_spin.setValue(2); d.compute()
    assert d.comparison['p'] < 1e-4 and '10.0 %' in d.note.text()
    d.deleteLater()


def test_lesson_2_skewed(quiet):
    d = _open('group_stats_skewed_demo.xlsx')
    _two_bands(d, (1715, 1775), (1420, 1480), metric='Baseline-corrected integral')
    d.compute()
    r = d.comparison
    assert round(r['p'], 3) == 0.074
    sw = [p for g, n, p in r['checks']['normality']]
    assert sw[0] < 1e-4 and round(sw[1], 4) == 0.0045
    assert any('non-parametric' in a for a in r['checks']['advice'])
    _test(d, 'nonparametric'); d.compute()
    assert round(d.comparison['p'], 3) == 0.006
    _test(d, 'parametric'); d.operation_combo.setCurrentText('log₂(A / B)'); d.compute()
    assert round(d.comparison['p'], 3) == 0.005
    assert [round(p, 2) for g, n, p in d.comparison['checks']['normality']] == [0.91, 0.91]
    d.deleteLater()


def test_lesson_3_cells(quiet):
    d = _open('group_stats_cells_samples_demo.xlsx')
    _two_bands(d, (1620, 1690), (1420, 1480)); d.compute()
    assert d.comparison['p'] < 1e-4 and 'not independent replicates' in d.note.text()
    d.per_sample_check.setChecked(True); d.compute()
    assert [len(v) for v in d.data.values()] == [3, 3]
    assert round(d.comparison['p'], 2) == 0.26 and 'not independent' not in d.note.text()
    d.deleteLater()


def test_lesson_4_paired(quiet):
    d = _open('group_stats_paired_demo.xlsx')
    _one_band(d, 'max', 1630, 1680); d.compute()
    assert round(d.comparison['p'], 2) == 0.64
    _test(d, 'paired_t'); d.compute()
    r = d.comparison
    assert r['p'] < 1e-4 and r['n_pairs'] == 8
    assert [round(x, 3) for x in r['ci']] == [0.048, 0.034, 0.062]
    _test(d, 'wilcoxon'); d.compute()
    assert round(d.comparison['p'], 3) == 0.008
    d.deleteLater()


def test_tutorial_page_is_registered_linked_and_has_its_pictures():
    from src.help import help_window, group_statistics_help, user_guide_help
    from src.help import group_statistics_tutorial_help as t
    assert 'group_statistics_tutorial' in help_window._REGISTRY
    html = t.get_group_statistics_tutorial_help_content()
    assert '$FIG_' not in html and html.count('<img ') == len(t._FIGURES)
    for f, _ in t._FIGURES.values():
        assert os.path.isfile(os.path.join(ROOT, t._SCREENSHOT_DIR, f))
    assert 'help://group_statistics_tutorial' in group_statistics_help.get_group_statistics_help_content()
    assert 'help://group_statistics_tutorial' in user_guide_help.get_user_guide_help_content()


def _spectra_tab(d, norm='none'):
    d.sp_norm_combo.setCurrentIndex(d.sp_norm_combo.findData(norm))
    d.sp_band_from.setValue(1420); d.sp_band_to.setValue(1480)
    d.compute_spectra()
    return d.spectra_result


def _wide(r):
    return [(round(a), round(b)) for a, b, k, m in r['ranges'] if k >= 3]


def test_lesson_5_along_the_spectrum(quiet):
    d = _open('group_stats_treatment_demo.xlsx')
    r = _spectra_tab(d, 'none')
    assert r['ranges'] == [] and round(r['permanova'][1], 2) == 0.08
    r = _spectra_tab(d, 'band')
    assert r['permanova'][1] == pytest.approx(1e-4)
    assert _wide(r) == [(1573, 1584), (1587, 1598), (1620, 1689)]
    assert 'plus 4 shorter ones' in d.sp_note.text()
    r = _spectra_tab(d, 'area')
    covered = sum(k for a, b, k, m in r['ranges']) / len(r['x'])
    assert round(covered, 1) == 0.6 and 'Most of the spectrum differs' in d.sp_note.text()
    d.deleteLater()
    d = _open('group_stats_cells_samples_demo.xlsx')
    r = _spectra_tab(d, 'band')
    assert _wide(r) == [(1629, 1684)] and 'not independent' in d.sp_note.text()
    assert r['permanova'][1] == pytest.approx(1e-4)
    d.per_sample_check.setChecked(True)
    r = _spectra_tab(d, 'band')
    assert r['ranges'] == [] and round(r['permanova'][1], 2) == 0.10
    d.deleteLater()


def test_lesson_6_map_regions(quiet, tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    from src.modules.core.spectrum_manager import SpectrumManager
    from src.controllers.visualization_analysis.map2d_controller import Map2DController
    from src.views.dialogs.visualization_analysis.map2d_dialog import Map2DDialog
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    m = SpectrumManager()
    m.load_spectrum_from_file(os.path.join(SYNTH, 'group_stats_cell_map_demo.mat'))
    sp = [{'label': l, 'x_scale': s.x_scale, 'y_scale': s.y_scale, 'metadata': s.metadata}
          for l, s in m.spectra.items()]

    class _Main:
        view = None
    md = Map2DDialog(None, Map2DController(_Main()), sp)
    assert (md._rows_spin.value(), md._cols_spin.value()) == (30, 40)

    def region(inside):
        return {'type': 'rect', 'bounds': None, 'spectra': [], 'patch': None,
                'labels': [sp[r * 40 + c]['label'] for r in range(30) for c in range(40)
                           if inside(r, c)]}
    md._roi_regions = [region(lambda r, c: ((c - 17) / 4) ** 2 + ((r - 14) / 4) ** 2 <= 1),
                       region(lambda r, c: 12 <= r <= 18 and 26 <= c <= 31)]
    md._update_roi_count()
    monkeypatch.setattr(md, '_ask_region_names', lambda: (['nucleus', 'cytoplasm'], None))
    monkeypatch.setattr(gsd.GroupStatisticsDialog, 'exec_', lambda self: 0)
    md._open_roi_group_statistics()
    d = md._roi_group_dialog
    assert 'one map' in d.table_source.text()
    _two_bands(d, (770, 800), (1420, 1480), metric='Baseline-corrected integral'); d.compute()
    assert d.comparison['p'] < 1e-4 and _means(d)[0] > 10 * _means(d)[1]
    _two_bands(d, (990, 1015), (1420, 1480), metric='Baseline-corrected integral'); d.compute()
    assert round(d.comparison['p'], 2) == 0.87
    raw = _spectra_tab(d, 'none')
    assert sum(k for a, b, k, m in raw['ranges']) / len(raw['x']) > 0.9
    assert _wide(_spectra_tab(d, 'band')) == [(774, 798), (1082, 1108), (1566, 1590)]
    d.deleteLater(); md.deleteLater()
