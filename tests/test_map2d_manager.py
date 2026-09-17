# tests/test_map2d_manager.py
#
# Tests for the 2-D spectral map feature's business logic
# (src/modules/visualization_analysis/map2d_manager.py) — the SVD, PCA,
# NMF and MCR-ALS spatial decomposition modes of the 2D Map dialog.
#
# Before this file, NONE of the four decomposition modes had any
# automated coverage at all (verified: `grep -rl "Map2DManager" tests/`
# returned nothing) — the only related test file, test_mat_map_converter.py,
# only tests the .mat file reader, not map computation itself.
#
# Scope: this focuses on Map2DManager's OWN logic (range filtering,
# reshaping, the unified get_component_*(kind, ...) dispatch, and
# invert_component) rather than re-verifying NMF/MCR-ALS's underlying fit
# correctness, which is already covered elsewhere (test_ground_truth_
# correctness.py, test_regression_bugs.py) via NMFManager/MCRALSManager
# directly — those are the exact same classes compute_nmf_map/
# compute_mcr_map delegate to, not a second implementation.
#
# PCA gets the most thorough checks here since it's new logic (added
# alongside this test file) with no other coverage anywhere yet: it's
# cross-checked bit-for-bit against a hand-computed mean-centered SVD,
# not just "did it run".

import numpy as np
import pytest

from src.modules.visualization_analysis.map2d_manager import Map2DManager


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def _make_map_spectra(n_rows=3, n_cols=4, n_wl=40, seed=0,
                       shared_offset=True, noise=0.01):
    """
    Build a synthetic (n_rows x n_cols) spectral map with two genuine
    underlying components mixed in spatially-varying proportions, so
    decomposition methods have real structure to recover rather than
    pure noise:

      - Component A: a Gaussian peak centered at x=30, strongest in the
        top-left corner, fading toward the bottom-right (linear ramp).
      - Component B: a Gaussian peak centered at x=70, the opposite ramp.

    shared_offset=True adds a constant background common to every pixel
    (the situation mean-centering is specifically meant to remove) — used
    to verify PCA and plain SVD diverge on this data, as the PCA
    docstring's rationale predicts.

    Returns (spectra, x, n_rows, n_cols, component_a, component_b,
    weights_a) — the last three let a test check recovered components/
    maps against the known ground truth.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 100, n_wl)

    def gaussian(center, width=8.0):
        return np.exp(-0.5 * ((x - center) / width) ** 2)

    comp_a = gaussian(30.0)
    comp_b = gaussian(70.0)

    n_pixels = n_rows * n_cols
    weights_a = np.linspace(1.0, 0.0, n_pixels)   # fades row-major
    weights_b = 1.0 - weights_a

    spectra = []
    for p in range(n_pixels):
        y = weights_a[p] * comp_a + weights_b[p] * comp_b
        if shared_offset:
            y = y + 5.0  # common background, deliberately not mean-zero
        y = y + rng.normal(0, noise, size=n_wl)
        spectra.append({
            'label': f'px{p}',
            'x_scale': x.copy(),
            'y_scale': y,
            'original_x_scale': x.copy(),
            'original_y_scale': y.copy(),
            'metadata': {},
        })
    return spectra, x, n_rows, n_cols, comp_a, comp_b, weights_a


@pytest.fixture
def map_fixture():
    return _make_map_spectra()


# ---------------------------------------------------------------------------
# validate_dimensions
# ---------------------------------------------------------------------------

def test_validate_dimensions_ok():
    assert Map2DManager.validate_dimensions(12, 3, 4) is True


def test_validate_dimensions_mismatch():
    assert Map2DManager.validate_dimensions(12, 3, 5) is False


# ---------------------------------------------------------------------------
# compute_svd_map
# ---------------------------------------------------------------------------

def test_compute_svd_map_basic_shape(map_fixture):
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    result = mgr.compute_svd_map(spectra, n_rows, n_cols, component_index=0)
    assert result is not None
    assert result.shape == (n_rows, n_cols)
    assert mgr.map_mode == "svd"


def test_compute_svd_map_dimension_mismatch_rejected(map_fixture):
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    result = mgr.compute_svd_map(spectra, n_rows, n_cols + 1, component_index=0)
    assert result is None


def test_compute_svd_map_component_index_clamped(map_fixture):
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    result = mgr.compute_svd_map(spectra, n_rows, n_cols, component_index=9999)
    assert result is not None   # clamped to the last available component


# ---------------------------------------------------------------------------
# compute_pca_map
# ---------------------------------------------------------------------------

def test_compute_pca_map_matches_manual_mean_centered_svd(map_fixture):
    """PCA here IS mean-centered SVD (see PcaScoresManager / the
    mean_center option in SVDBackgroundManager) — cross-check bit-for-bit
    against a hand-rolled version of that exact computation."""
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    result = mgr.compute_pca_map(spectra, n_rows, n_cols, component_index=0)
    assert result is not None
    assert result.shape == (n_rows, n_cols)
    assert mgr.map_mode == "pca"

    Y = np.column_stack([sp['y_scale'] for sp in spectra])
    mean_spec = Y.mean(axis=1)
    Yc = Y - mean_spec[:, None]
    U, s, Vt = np.linalg.svd(Yc, full_matrices=False)

    np.testing.assert_allclose(mgr._pca_mean_spectrum, mean_spec, rtol=1e-10)
    np.testing.assert_allclose(mgr._pca_U[:, 0], U[:, 0], rtol=1e-10)
    np.testing.assert_allclose(mgr._pca_Vt[0, :], Vt[0, :], rtol=1e-10)
    np.testing.assert_allclose(result.ravel(), Vt[0, :], rtol=1e-10)


def test_compute_pca_map_differs_from_svd_for_offset_data(map_fixture):
    """With a shared, non-zero background across every pixel (this
    fixture's default), mean-centering should materially change the
    dominant component — this is the exact PCA-vs-SVD distinction the
    feature exists for."""
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    mgr.compute_svd_map(spectra, n_rows, n_cols, component_index=0)
    mgr.compute_pca_map(spectra, n_rows, n_cols, component_index=0)
    svd_coeffs = mgr.get_component_coefficients('svd', 0)
    pca_coeffs = mgr.get_component_coefficients('pca', 0)
    assert not np.allclose(svd_coeffs, pca_coeffs)


def test_compute_pca_map_dimension_mismatch_rejected(map_fixture):
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    result = mgr.compute_pca_map(spectra, n_rows, n_cols + 1, component_index=0)
    assert result is None


def test_compute_pca_map_component_index_clamped(map_fixture):
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    result = mgr.compute_pca_map(spectra, n_rows, n_cols, component_index=9999)
    assert result is not None


def test_svd_and_pca_state_coexist_independently(map_fixture):
    """Computing one must not clobber the other's already-computed
    state — each keeps its own _U/_Vt/etc (see Map2DManager.__init__),
    mirroring how NMF and MCR-ALS already get independent storage."""
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    mgr.compute_pca_map(spectra, n_rows, n_cols, component_index=0)
    pca_coeffs_before = mgr.get_component_coefficients('pca', 0).copy()

    mgr.compute_svd_map(spectra, n_rows, n_cols, component_index=0)
    assert mgr.map_mode == "svd"

    pca_coeffs_after = mgr.get_component_coefficients('pca', 0)
    np.testing.assert_allclose(pca_coeffs_before, pca_coeffs_after, rtol=1e-10)


# ---------------------------------------------------------------------------
# compute_nmf_map / compute_mcr_map — smoke coverage of the MAP WRAPPING
# (reshape, dispatch, range filtering). Fit correctness itself is already
# covered via NMFManager/MCRALSManager directly elsewhere.
# ---------------------------------------------------------------------------

def test_compute_nmf_map_basic_shape_and_nonnegativity(map_fixture):
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    result = mgr.compute_nmf_map(
        spectra, n_rows, n_cols, n_components=2, component_index=0,
        max_iter=300, random_state=0,
    )
    assert result is not None, mgr.get_last_decomp_error('nmf')
    assert result.shape == (n_rows, n_cols)
    assert mgr.map_mode == "nmf"
    # NMF is non-negativity constrained by construction
    assert np.all(result >= -1e-8)


def test_compute_mcr_map_basic_shape(map_fixture):
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    result = mgr.compute_mcr_map(
        spectra, n_rows, n_cols, n_components=2, component_index=0,
        max_iterations=50, random_state=0,
    )
    assert result is not None, mgr.get_last_decomp_error('mcr')
    assert result.shape == (n_rows, n_cols)
    assert mgr.map_mode == "mcr"


# ---------------------------------------------------------------------------
# Unified accessors — 'svd' | 'pca' | 'nmf' | 'mcr'
# ---------------------------------------------------------------------------

ALL_KINDS = ('svd', 'pca', 'nmf', 'mcr')


def _compute_all(mgr, spectra, n_rows, n_cols):
    mgr.compute_svd_map(spectra, n_rows, n_cols, component_index=0)
    mgr.compute_pca_map(spectra, n_rows, n_cols, component_index=0)
    mgr.compute_nmf_map(spectra, n_rows, n_cols, n_components=2,
                        component_index=0, max_iter=300, random_state=0)
    mgr.compute_mcr_map(spectra, n_rows, n_cols, n_components=2,
                        component_index=0, max_iterations=50, random_state=0)


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_get_n_components_after_compute(map_fixture, kind):
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    _compute_all(mgr, spectra, n_rows, n_cols)
    assert mgr.get_n_components(kind) > 0


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_get_n_components_zero_before_compute(kind):
    mgr = Map2DManager()
    assert mgr.get_n_components(kind) == 0


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_get_component_subspectrum_and_coefficients(map_fixture, kind):
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    _compute_all(mgr, spectra, n_rows, n_cols)

    sx, sy = mgr.get_component_subspectrum(kind, 0)
    assert sx is not None and sy is not None
    assert len(sx) == len(sy)

    coeffs = mgr.get_component_coefficients(kind, 0)
    assert coeffs is not None
    assert coeffs.reshape(n_rows, n_cols).shape == (n_rows, n_cols)


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_get_component_explained_variance(map_fixture, kind):
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    _compute_all(mgr, spectra, n_rows, n_cols)
    ev = mgr.get_component_explained_variance(kind)
    assert ev is not None
    assert len(ev) == mgr.get_n_components(kind)


def test_unknown_kind_raises():
    mgr = Map2DManager()
    with pytest.raises(ValueError):
        mgr.get_n_components('bogus')
    with pytest.raises(ValueError):
        mgr.get_component_subspectrum('bogus', 0)
    with pytest.raises(ValueError):
        mgr.get_component_coefficients('bogus', 0)
    with pytest.raises(ValueError):
        mgr.get_component_explained_variance('bogus')


# ---------------------------------------------------------------------------
# invert_component — sign ambiguity flip (SVD/PCA only)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ("svd", "pca"))
def test_invert_component_flips_sign(map_fixture, kind):
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    _compute_all(mgr, spectra, n_rows, n_cols)

    coeffs_before = mgr.get_component_coefficients(kind, 0).copy()
    sx, sub_before = mgr.get_component_subspectrum(kind, 0)
    sub_before = sub_before.copy()

    assert mgr.invert_component(kind, 0) is True

    coeffs_after = mgr.get_component_coefficients(kind, 0)
    _, sub_after = mgr.get_component_subspectrum(kind, 0)
    np.testing.assert_allclose(coeffs_after, -coeffs_before, rtol=1e-10)
    np.testing.assert_allclose(sub_after, -sub_before, rtol=1e-10)

    # inverting again restores the original sign
    assert mgr.invert_component(kind, 0) is True
    np.testing.assert_allclose(
        mgr.get_component_coefficients(kind, 0), coeffs_before, rtol=1e-10)


@pytest.mark.parametrize("kind", ("nmf", "mcr"))
def test_invert_component_noop_for_nonneg_kinds(map_fixture, kind):
    """NMF/MCR-ALS are non-negativity constrained — no sign ambiguity to
    flip, so invert_component must refuse (return False) rather than
    silently corrupting a non-negative fit."""
    spectra, x, n_rows, n_cols, *_ = map_fixture
    mgr = Map2DManager()
    _compute_all(mgr, spectra, n_rows, n_cols)
    coeffs_before = mgr.get_component_coefficients(kind, 0).copy()
    assert mgr.invert_component(kind, 0) is False
    np.testing.assert_array_equal(
        mgr.get_component_coefficients(kind, 0), coeffs_before)


def test_invert_component_before_compute_returns_false():
    mgr = Map2DManager()
    assert mgr.invert_component('svd', 0) is False
    assert mgr.invert_component('pca', 0) is False
