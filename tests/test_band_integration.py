"""Area / mean / baseline-corrected area over spectral ranges, shared by the
2D Map, Band Ratio and Group Statistics (src/modules/utils/band_integration.py):
exact range edges, each range on its own, mean = area / width."""
import numpy as np
import pytest

from src.modules.utils import band_integration as bi
from src.modules.visualization_analysis.band_ratio_manager import BandRatioManager
from src.modules.visualization_analysis.map2d_manager import Map2DManager


def test_area_uses_the_exact_range_edges():
    x = np.arange(0.0, 11.0)                    # points at 0, 1, ..., 10
    y = 2.0 * x                                 # straight line: area is exact
    iv = bi.integration_intervals(x, include=[(2.5, 7.5)])
    assert iv == [(2.5, 7.5)]
    assert bi.band_area(x, y, iv) == pytest.approx(7.5 ** 2 - 2.5 ** 2)   # 50
    # the old way (points 3..7 only) missed the half steps at both ends: 40


def test_area_does_not_depend_on_where_the_points_fall():
    fine = np.linspace(0, 10, 1001)
    coarse = np.linspace(0.3, 9.7, 48)          # a different x-axis
    f = lambda x: np.exp(-((x - 5) / 1.2) ** 2)
    a_fine = bi.band_area(fine, f(fine), bi.integration_intervals(fine, include=[(3, 7)]))
    a_coarse = bi.band_area(coarse, f(coarse), bi.integration_intervals(coarse, include=[(3, 7)]))
    assert a_coarse == pytest.approx(a_fine, rel=2e-3)


def test_two_ranges_are_added_not_bridged():
    x = np.arange(0.0, 11.0)
    y = np.ones_like(x)
    iv = bi.integration_intervals(x, include=[(0, 2), (8, 10)])
    assert bi.band_area(x, y, iv) == pytest.approx(4.0)        # not 10 (gap bridged)
    iv = bi.integration_intervals(x, exclude=[(2, 8)])
    assert iv == [(0.0, 2.0), (8.0, 10.0)]
    assert bi.band_area(x, y, iv) == pytest.approx(4.0)


def test_mean_is_area_over_width_for_uneven_spacing():
    x = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 10.0])   # dense at the start
    y = x.copy()                                     # y = x: true mean over 0..10 is 5
    iv = bi.integration_intervals(x)
    assert bi.band_mean(x, y, iv) == pytest.approx(5.0)
    assert np.mean(y) == pytest.approx(1.83, abs=0.01)   # the plain point average


def test_baseline_corrected_area_uses_values_at_the_range_edges():
    x = np.arange(0.0, 11.0)
    y = 1.0 + 0.5 * x                               # sloping background only
    iv = bi.integration_intervals(x, include=[(1.5, 8.5)])
    assert bi.baseline_corrected_area(x, y, iv) == pytest.approx(0.0, abs=1e-12)


def test_range_is_clipped_to_the_spectrum():
    x = np.arange(0.0, 11.0)
    assert bi.integration_intervals(x, include=[(-5, 3)]) == [(0.0, 3.0)]
    assert bi.integration_intervals(x, include=[(20, 30)]) == []
    assert np.isnan(bi.band_area(x, x, []))


def test_map_and_band_ratio_give_the_same_corrected_values():
    x = np.arange(0.0, 11.0)
    y = 2.0 * x
    spectra = [{'label': 's', 'x_scale': x, 'y_scale': y}]
    mgr = Map2DManager()
    for metric, expected in (('Integral', 50.0), ('Mean', 10.0)):
        m = mgr.compute_intensity_map(spectra, 1, 1, metric=metric,
                                      include_ranges=[[2.5, 7.5]])
        assert m[0, 0] == pytest.approx(expected)
        r = BandRatioManager().compute_results(
            spectra, {'band_a': {'ranges': [[2.5, 7.5]], 'metric': metric},
                      'operation': 'A only'})
        assert r[0]['value_a'] == pytest.approx(expected)


def test_map_exclude_range_is_not_counted():
    x = np.arange(0.0, 11.0)
    y = np.where((x > 3) & (x < 7), 100.0, 1.0)     # a big band in the excluded part
    spectra = [{'label': 's', 'x_scale': x, 'y_scale': y}]
    m = Map2DManager().compute_intensity_map(spectra, 1, 1, metric='Integral',
                                             exclude_ranges=[[3, 7]])
    assert m[0, 0] == pytest.approx(6.0)            # 1.0 over 0..3 and 7..10


# --- a spectrum that does not cover the whole range gets no value -------------------

def test_covers_with_half_a_step_tolerance():
    x = np.arange(200.0, 251.0)                     # step 1
    assert bi.covers(x, [(200, 250)])
    assert bi.covers(x, [(199.6, 250.4)])           # within half a step
    assert not bi.covers(x, [(195, 230)])
    assert not bi.covers(x, [(210, 220), (240, 260)])
    assert bi.covers(x, [])
    assert bi.covers_x(x, 250.3) and not bi.covers_x(x, 251)


def _two_ranges_spectra():
    x1, x2 = np.linspace(235, 288, 54), np.linspace(303, 318, 16)
    return [{'label': 'short', 'x_scale': x1, 'y_scale': np.ones_like(x1)},
            {'label': 'other', 'x_scale': x2, 'y_scale': np.ones_like(x2)}]


def test_map_pixel_without_the_whole_range_is_blank_for_every_metric():
    spectra = _two_ranges_spectra()
    for metric in ('Integral', 'Mean', 'Baseline-corrected integral', 'Peak intensity',
                   'Peak position', 'Variance'):
        m = Map2DManager().compute_intensity_map(spectra, 1, 2, metric=metric,
                                                 include_ranges=[[280, 310]])
        assert np.isnan(m).all(), metric               # neither covers 280-310
        m = Map2DManager().compute_intensity_map(spectra, 1, 2, metric=metric,
                                                 include_ranges=[[240, 280]])
        assert np.isfinite(m[0, 0]) and np.isnan(m[0, 1]), metric


def test_band_ratio_without_the_whole_range_has_no_value_and_says_so():
    spectra = _two_ranges_spectra()
    r = BandRatioManager().compute_results(
        spectra, {'band_a': {'ranges': [[280, 310]], 'metric': 'Integral'},
                  'operation': 'A only'})
    assert [x['value_a'] for x in r] == [None, None]
    assert all(x['missing'] == ['A'] for x in r)
    r = BandRatioManager().compute_results(
        spectra, {'band_a': {'metric': 'Intensity at x', 'x_pos': 300.0},
                  'operation': 'A only'})
    assert [x['value_a'] for x in r] == [None, None]   # was: the nearest edge point


def test_group_statistics_value_needs_the_whole_range():
    from src.modules.visualization_analysis import group_statistics as gs
    sp = _two_ranges_spectra()[0]                      # 235-288
    assert np.isnan(gs.spectrum_value(sp, 'area', range_a=(280, 320)))
    assert np.isnan(gs.spectrum_value(sp, 'max', range_a=(280, 320)))
    assert np.isfinite(gs.spectrum_value(sp, 'area', range_a=(240, 280)))
    assert np.isnan(gs.spectrum_value(sp, 'ratio', range_a=(240, 260), range_b=(280, 300)))
