# tests/test_map2d_bootstrap.py
#
# Tests for Bootstrap Uncertainty on the 2D Map's NMF/MCR-ALS panel
# (Map2DManager.compute_bootstrap_uncertainty and its accessors, plus the
# Map2DController passthroughs). Mirrors test_map2d_manager.py's fixture
# and style.
#
# Scope: this is the SAME residual-bootstrap statistics already covered
# end-to-end in test_nmf_bootstrap.py / test_mcr_als_bootstrap.py (via
# NMFController/MCRALSController directly) -- Map2DManager.compute_
# bootstrap_uncertainty is a thin delegate to those, not a reimplementation
# (see its docstring). What's actually new here, and what these tests
# focus on, is: the delegation wiring itself (right manager, right
# kwargs), the two new map-shaped accessors (get_component_subspectrum_band,
# get_component_uncertainty_map) and their reshape/None-handling, and that
# a fresh compute_nmf_map/compute_mcr_map call structurally can't leave a
# stale bootstrap_result behind (unlike the standalone dialogs, which
# needed an explicit fix for that -- see nmf_manager.py/mcr_als_manager.py).

import numpy as np
import pytest

from src.modules.visualization_analysis.map2d_manager import Map2DManager
from src.controllers.visualization_analysis.map2d_controller import Map2DController


# ---------------------------------------------------------------------------
# Fixture builder — same shape of synthetic data as test_map2d_manager.py's
# _make_map_spectra, just factored locally so this file has no import
# dependency on that one.
# ---------------------------------------------------------------------------

def _make_map_spectra(n_rows=4, n_cols=5, n_wl=30, seed=0, noise=0.02):
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 100, n_wl)

    def gaussian(center, width=8.0):
        return np.exp(-0.5 * ((x - center) / width) ** 2)

    comp_a = gaussian(30.0)
    comp_b = gaussian(70.0)

    n_pixels = n_rows * n_cols
    weights_a = np.linspace(1.0, 0.0, n_pixels)
    weights_b = 1.0 - weights_a

    spectra = []
    for p in range(n_pixels):
        y = weights_a[p] * comp_a + weights_b[p] * comp_b
        y = y + rng.normal(0, noise, size=n_wl)
        spectra.append({
            'label': f'px{p}',
            'x_scale': x.copy(),
            'y_scale': y,
            'original_x_scale': x.copy(),
            'original_y_scale': y.copy(),
            'metadata': {},
        })
    return spectra, x, n_rows, n_cols


@pytest.fixture
def map_fixture():
    return _make_map_spectra()


def _fit_nmf(mgr, spectra, n_rows, n_cols):
    result = mgr.compute_nmf_map(
        spectra, n_rows, n_cols, n_components=2, component_index=0,
        max_iter=300, random_state=0)
    assert result is not None, mgr.get_last_decomp_error('nmf')
    return result


def _fit_mcr(mgr, spectra, n_rows, n_cols):
    result = mgr.compute_mcr_map(
        spectra, n_rows, n_cols, n_components=2, component_index=0,
        max_iterations=50, random_state=0)
    assert result is not None, mgr.get_last_decomp_error('mcr')
    return result


# ---------------------------------------------------------------------------
# Before any bootstrap has been run
# ---------------------------------------------------------------------------

def test_no_bootstrap_result_before_it_is_run(map_fixture):
    spectra, x, n_rows, n_cols = map_fixture
    mgr = Map2DManager()
    _fit_nmf(mgr, spectra, n_rows, n_cols)
    assert mgr.get_bootstrap_result('nmf') is None
    lo, hi = mgr.get_component_subspectrum_band('nmf', 0)
    assert lo is None and hi is None
    assert mgr.get_component_uncertainty_map('nmf', 0, n_rows, n_cols) is None


def test_bootstrap_unsupported_kind_raises(map_fixture):
    spectra, x, n_rows, n_cols = map_fixture
    mgr = Map2DManager()
    _fit_nmf(mgr, spectra, n_rows, n_cols)
    with pytest.raises(ValueError):
        mgr.compute_bootstrap_uncertainty(
            'svd', n_components=2, n_resamples=5, confidence_level=0.95)


def test_bootstrap_before_any_fit_returns_none(map_fixture):
    mgr = Map2DManager()
    assert mgr.compute_bootstrap_uncertainty(
        'nmf', n_components=2, n_resamples=5, confidence_level=0.95,
        init='nndsvda', max_iter=200) is None
    assert mgr.compute_bootstrap_uncertainty(
        'mcr', n_components=2, n_resamples=5, confidence_level=0.95,
        max_iterations=50) is None


# ---------------------------------------------------------------------------
# NMF bootstrap on the map
# ---------------------------------------------------------------------------

def test_nmf_bootstrap_basic(map_fixture):
    spectra, x, n_rows, n_cols = map_fixture
    mgr = Map2DManager()
    _fit_nmf(mgr, spectra, n_rows, n_cols)

    result = mgr.compute_bootstrap_uncertainty(
        'nmf', n_components=2, n_resamples=6, confidence_level=0.95,
        init='nndsvda', max_iter=200, random_state=0)
    assert result is not None
    assert mgr.get_bootstrap_result('nmf') is result
    assert result['n_resamples_used'] >= 1
    assert np.all(result['H_lower'] <= result['H_upper'] + 1e-9)
    assert np.all(result['W_lower'] <= result['W_upper'] + 1e-9)

    lo, hi = mgr.get_component_subspectrum_band('nmf', 0)
    assert lo.shape == (len(x),)
    assert hi.shape == (len(x),)
    assert np.all(lo <= hi + 1e-9)

    umap = mgr.get_component_uncertainty_map('nmf', 0, n_rows, n_cols)
    assert umap.shape == (n_rows, n_cols)
    # A band width (upper - lower) can never be negative.
    assert np.all(umap >= -1e-9)


def test_nmf_bootstrap_via_controller(map_fixture):
    """Same thing through Map2DController's thin passthroughs, to catch a
    keyword-argument mismatch between the controller and manager layers
    that calling the manager directly wouldn't."""
    spectra, x, n_rows, n_cols = map_fixture
    ctrl = Map2DController(main_controller=None)
    map_data = ctrl.compute_nmf_map(
        spectra, n_rows, n_cols, n_components=2, component_index=0,
        max_iter=300, random_state=0)
    assert map_data is not None

    result = ctrl.compute_bootstrap_uncertainty(
        'nmf', n_components=2, n_resamples=6, confidence_level=0.95,
        init='nndsvda', max_iter=200, random_state=0)
    assert result is not None
    assert ctrl.get_bootstrap_result('nmf') is result

    lo, hi = ctrl.get_component_subspectrum_band('nmf', 0)
    assert lo is not None and hi is not None

    umap = ctrl.get_component_uncertainty_map('nmf', 0, n_rows, n_cols)
    assert umap is not None
    assert umap.shape == (n_rows, n_cols)


# ---------------------------------------------------------------------------
# MCR-ALS bootstrap on the map
# ---------------------------------------------------------------------------

def test_mcr_bootstrap_basic(map_fixture):
    spectra, x, n_rows, n_cols = map_fixture
    mgr = Map2DManager()
    _fit_mcr(mgr, spectra, n_rows, n_cols)

    result = mgr.compute_bootstrap_uncertainty(
        'mcr', n_components=2, n_resamples=6, confidence_level=0.95,
        max_iterations=50, tol=0.01, c_nonneg=True, st_nonneg=True,
        normalize_spectra=True, closure=False, random_state=0)
    assert result is not None
    assert mgr.get_bootstrap_result('mcr') is result
    assert np.all(result['ST_lower'] <= result['ST_upper'] + 1e-9)
    assert np.all(result['C_lower'] <= result['C_upper'] + 1e-9)

    lo, hi = mgr.get_component_subspectrum_band('mcr', 1)
    assert lo.shape == (len(x),)
    assert np.all(lo <= hi + 1e-9)

    umap = mgr.get_component_uncertainty_map('mcr', 1, n_rows, n_cols)
    assert umap.shape == (n_rows, n_cols)
    assert np.all(umap >= -1e-9)


def test_mcr_bootstrap_via_controller(map_fixture):
    spectra, x, n_rows, n_cols = map_fixture
    ctrl = Map2DController(main_controller=None)
    map_data = ctrl.compute_mcr_map(
        spectra, n_rows, n_cols, n_components=2, component_index=0,
        max_iterations=50, random_state=0)
    assert map_data is not None

    result = ctrl.compute_bootstrap_uncertainty(
        'mcr', n_components=2, n_resamples=6, confidence_level=0.95,
        max_iterations=50, tol=0.01, c_nonneg=True, st_nonneg=True,
        normalize_spectra=True, closure=False, random_state=0)
    assert result is not None
    assert ctrl.get_bootstrap_result('mcr') is result


# ---------------------------------------------------------------------------
# A fresh fit always leaves a brand-new manager in place, so a stale
# bootstrap_result from a PREVIOUS fit can never survive onto it -- unlike
# the standalone dialogs, which needed an explicit fix for exactly this
# (see nmf_manager.py/mcr_als_manager.py's "self.bootstrap_result = None"
# and the regression tests in test_nmf_bootstrap.py/
# test_mcr_als_bootstrap.py). Confirmed here rather than just assumed.
# ---------------------------------------------------------------------------

def test_bootstrap_result_does_not_survive_a_fresh_map_refit(map_fixture):
    spectra, x, n_rows, n_cols = map_fixture
    mgr = Map2DManager()
    _fit_nmf(mgr, spectra, n_rows, n_cols)
    result = mgr.compute_bootstrap_uncertainty(
        'nmf', n_components=2, n_resamples=5, confidence_level=0.95,
        init='nndsvda', max_iter=200, random_state=0)
    assert result is not None
    assert mgr.get_bootstrap_result('nmf') is not None

    # Recompute the map from scratch (e.g. the user pressed "Update Map"
    # again after changing a setting) -- this replaces self._nmf_manager
    # wholesale with a brand-new NMFManager(), so the old bootstrap result
    # must not still be attached afterward.
    _fit_nmf(mgr, spectra, n_rows, n_cols)
    assert mgr.get_bootstrap_result('nmf') is None
    lo, hi = mgr.get_component_subspectrum_band('nmf', 0)
    assert lo is None and hi is None


def test_uncertainty_map_shape_mismatch_returns_none(map_fixture):
    """get_component_uncertainty_map must not silently return a
    wrongly-shaped array if the map grid changed since the bootstrap
    ran."""
    spectra, x, n_rows, n_cols = map_fixture
    mgr = Map2DManager()
    _fit_nmf(mgr, spectra, n_rows, n_cols)
    result = mgr.compute_bootstrap_uncertainty(
        'nmf', n_components=2, n_resamples=5, confidence_level=0.95,
        init='nndsvda', max_iter=200, random_state=0)
    assert result is not None
    # Ask for a grid that doesn't match n_rows * n_cols pixels.
    assert mgr.get_component_uncertainty_map('nmf', 0, n_rows + 1, n_cols) is None
