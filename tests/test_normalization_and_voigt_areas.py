"""Unit-area normalization uses the exact region edges and integrates the
parts of a region separately; a spectrum the region is not completely inside
is left unchanged (and named) instead of being normalized by the part it has
or by its whole spectrum. Voigt peak areas are exact."""
import numpy as np
import pytest
from scipy.integrate import quad

from src.modules.data_analysis.normalization_manager import NormalizationManager
from src.modules.data_analysis.peak_fitting_manager import PeakFittingManager, voigt

X = np.arange(0.0, 11.0)                     # points 0, 1, ..., 10


def _mgr(ranges, exclude=False, mode='unit_area'):
    m = NormalizationManager()
    m.x_ranges = list(ranges)
    m.is_exclude_mode = exclude
    m.normalization_mode = mode
    return m


def _settings(m):
    return {'normalization_mode': m.normalization_mode, 'x_ranges': list(m.x_ranges),
            'is_exclude_mode': m.is_exclude_mode}


def test_unit_area_region_from_exactly_its_edges():
    y = 2.0 * X
    m = _mgr([(2.5, 7.5)])
    assert m._get_unit_area_factor(X, y) == pytest.approx(50.0)    # was 40 (points 3..7)


def test_unit_area_two_regions_are_added_not_bridged():
    y = np.ones_like(X)
    assert _mgr([(0, 2), (8, 10)])._get_unit_area_factor(X, y) == pytest.approx(4.0)  # was 10
    assert _mgr([(2, 8)], exclude=True)._get_unit_area_factor(X, y) == pytest.approx(4.0)


def test_normalized_area_is_one():
    y = 3.0 + X
    m = _mgr([(1.3, 6.6)])
    out = m.normalize_spectra([{'label': 's', 'x_scale': X, 'y_scale': y, 'metadata': {}}],
                              _settings(m))[0]['y_scale']
    m2 = _mgr([(1.3, 6.6)])
    assert m2._get_unit_area_factor(X, out) == pytest.approx(1.0)


@pytest.mark.parametrize('mode', ['unit_area', 'max_peak', 'vector', 'offset_correction', 'snv'])
def test_spectrum_without_the_whole_region_is_left_unchanged_and_named(mode):
    inside = {'label': 'inside', 'x_scale': X, 'y_scale': 1.0 + X, 'metadata': {}}
    short = {'label': 'short', 'x_scale': X[:5], 'y_scale': 1.0 + X[:5], 'metadata': {}}
    outside = {'label': 'outside', 'x_scale': X + 50, 'y_scale': 1.0 + X, 'metadata': {}}
    m = _mgr([(2, 8)], mode=mode)
    out = m.normalize_spectra([inside, short, outside], _settings(m))
    assert m.uncovered_labels == ['short', 'outside']
    assert not np.allclose(out[0]['y_scale'], inside['y_scale'])     # normalized
    assert np.array_equal(out[1]['y_scale'], short['y_scale'])       # unchanged
    assert np.array_equal(out[2]['y_scale'], outside['y_scale'])     # (was: whole spectrum)


def test_no_region_normalizes_everything():
    m = _mgr([])
    out = m.normalize_spectra([{'label': 's', 'x_scale': X, 'y_scale': 1.0 + X,
                                'metadata': {}}], _settings(m))
    assert m.uncovered_labels == []
    assert m._get_unit_area_factor(X, out[0]['y_scale']) == pytest.approx(1.0)


@pytest.mark.parametrize('sigma,gamma', [(1.0, 0.01), (1.0, 1.0), (0.01, 1.0), (2.0, 0.0)])
def test_voigt_area_is_exact(sigma, gamma):
    area = PeakFittingManager().get_peak_properties('Voigt', (2.0, 5.0, sigma, gamma))['area']
    exact = quad(lambda x: voigt(x, 2.0, 5.0, sigma, gamma), -np.inf, np.inf, limit=500)[0]
    assert area == pytest.approx(exact, rel=1e-6)


def test_offset_correction_uses_area_over_width():
    x = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 10.0])      # dense at the start
    y = x.copy()                                       # mean height over 0..10 = 5
    m = _mgr([], mode='offset_correction')
    out = m._normalize_offset_correction(y, x)
    assert out == pytest.approx(y - 5.0)               # plain point average would be 1.83
    m = _mgr([(0.0, 0.4)], mode='offset_correction')
    assert m._normalize_offset_correction(y, x) == pytest.approx(y - 0.2)
