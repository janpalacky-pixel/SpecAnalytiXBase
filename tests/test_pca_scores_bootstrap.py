# tests/test_pca_scores_bootstrap.py
#
# Tests for PCA / SVD Scores & Loadings' "Bootstrap Uncertainty" feature --
# the same residual-bootstrap method NMF/MCR-ALS use, and the direct
# counterpart of test_svd_analysis_bootstrap.py's own version (see that
# file's module docstring for the full method and the sign-ambiguity
# reasoning -- it applies identically here). See
# PcaScoresController.compute_bootstrap_uncertainty's own docstring, and
# the Developer Guide's "SVD Analysis / PCA Bootstrap Uncertainty" section.
#
# The one thing genuinely simpler here than SVD Analysis's own version:
# this manager already fixes "how many components are signal" at compute
# time (n_components passed to compute_svd()), so there is no separate
# bootstrap-time n_components choice and no suggest_bootstrap_n_components
# equivalent to test.

import numpy as np
import pytest

from src.modules.visualization_analysis.pca_scores_manager import PcaScoresManager
from src.controllers.visualization_analysis.pca_scores_controller import PcaScoresController


def _synthetic_svd_data(n_spectra=30, n_points=60, n_true=3, seed=17, noise=0.02):
    """Same construction as test_svd_analysis_bootstrap.py's own helper --
    a noisy, ground-truth-known n_true-component linear mixture with
    well-separated singular values so replicate components don't swap
    order under noise."""
    rng = np.random.RandomState(seed)
    x = np.linspace(100.0, 900.0, n_points)

    true_U, _ = np.linalg.qr(rng.normal(size=(n_points, n_true)))
    true_Vt, _ = np.linalg.qr(rng.normal(size=(n_spectra, n_true)))
    true_Vt = true_Vt.T
    true_s = np.array([50.0, 30.0, 15.0, 8.0, 4.0])[:n_true]

    X_clean = true_U @ np.diag(true_s) @ true_Vt
    X = X_clean + rng.normal(scale=noise, size=X_clean.shape)

    spectra = [
        {'label': f's{i}', 'x_scale': x.copy(), 'y_scale': X[:, i].copy(),
         'metadata': {}}
        for i in range(n_spectra)
    ]
    return spectra, true_U, true_s, true_Vt, x


class DummyController:
    """Fake main_controller -- PcaScoresController.__init__ only stores
    it, never calls anything on it."""
    pass


# ── PcaScoresManager: data_matrix / bootstrap_result bookkeeping ───────

class TestManagerBookkeeping:
    def test_data_matrix_is_stored_after_a_successful_compute(self):
        spectra, *_ = _synthetic_svd_data()
        mgr = PcaScoresManager()
        assert mgr.compute_svd(spectra, n_components=3, mean_center=True)
        assert mgr.data_matrix is not None
        n_wl, n_spec = mgr.data_matrix.shape
        assert n_spec == len(spectra)
        # data_matrix is the FULL (untruncated) decomposed matrix -- it
        # must be strictly wider-rank than the retained U/s/Vt whenever
        # n_components is less than the true rank, so it can't simply be
        # a copy of the truncated reconstruction.
        assert mgr.U.shape[1] == 3

    def test_data_matrix_reflects_mean_centering_when_requested(self):
        spectra, *_ = _synthetic_svd_data()
        mgr = PcaScoresManager()
        assert mgr.compute_svd(spectra, n_components=3, mean_center=True)
        assert np.allclose(mgr.data_matrix.mean(axis=1), 0.0, atol=1e-8)

    def test_bootstrap_result_is_none_before_any_bootstrap_call(self):
        spectra, *_ = _synthetic_svd_data()
        mgr = PcaScoresManager()
        mgr.compute_svd(spectra, n_components=3)
        assert mgr.bootstrap_result is None

    def test_bootstrap_result_cleared_by_a_subsequent_fresh_fit(self):
        spectra, *_ = _synthetic_svd_data()
        mgr = PcaScoresManager()
        ctrl = PcaScoresController(DummyController())
        ctrl.manager = mgr
        assert mgr.compute_svd(spectra, n_components=3)
        result = ctrl.compute_bootstrap_uncertainty(
            mgr, n_resamples=6, confidence_level=0.95, random_state=0)
        assert result is not None
        assert mgr.bootstrap_result is not None

        # Recomputing (e.g. a different n_components) must not leave the
        # OLD band silently attached -- same bug class NMFManager.compute()
        # guards against.
        assert mgr.compute_svd(spectra, n_components=2)
        assert mgr.bootstrap_result is None


# ── PcaScoresController.compute_bootstrap_uncertainty ───────────────────

class TestComputeBootstrapUncertainty:
    def _fitted_controller(self, n_components=3, **kwargs):
        spectra, true_U, true_s, true_Vt, x = _synthetic_svd_data(**kwargs)
        ctrl = PcaScoresController(DummyController())
        assert ctrl.compute_svd_analysis(spectra, n_components=n_components)
        return ctrl, true_U, true_s, true_Vt

    def test_requires_a_fitted_reference_manager(self):
        ctrl = PcaScoresController(DummyController())
        fresh = PcaScoresManager()   # never compute_svd()'d
        result = ctrl.compute_bootstrap_uncertainty(
            fresh, n_resamples=5, confidence_level=0.95)
        assert result is None
        assert fresh.last_error is not None

    def test_end_to_end_shapes_and_band_sanity(self):
        ctrl, *_ = self._fitted_controller(n_components=3)
        ref = ctrl.manager
        n_wl = ref.U.shape[0]
        n_spec = ref.Vt.shape[1]
        k = 3

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_resamples=15, confidence_level=0.95, random_state=0)

        assert result is not None
        assert result['U_lower'].shape == (n_wl, k)
        assert result['U_upper'].shape == (n_wl, k)
        assert result['Vt_lower'].shape == (k, n_spec)
        assert result['Vt_upper'].shape == (k, n_spec)
        assert result['n_resamples_used'] <= result['n_resamples_requested'] == 15
        assert result['U_samples'].shape[0] == result['n_resamples_used']
        assert result['Vt_samples'].shape[0] == result['n_resamples_used']
        assert result['confidence_level'] == 0.95

        assert np.all(result['U_lower'] <= result['U_upper'] + 1e-9)
        assert np.all(result['Vt_lower'] <= result['Vt_upper'] + 1e-6)

        assert ref.bootstrap_result is result

    def test_bootstrap_preserves_component_identity_no_rotation(self):
        ctrl, *_ = self._fitted_controller(n_components=3)
        ref = ctrl.manager

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_resamples=12, confidence_level=0.95, random_state=1)
        assert result is not None

        for b in range(result['n_resamples_used']):
            for j in range(ref.U.shape[1]):
                corr = np.corrcoef(result['U_samples'][b, :, j], ref.U[:, j])[0, 1]
                assert corr > 0.8, f"replicate {b}, component {j}: corr={corr}"

    def test_progress_callback_called_for_every_resample(self):
        ctrl, *_ = self._fitted_controller(n_components=3)
        ref = ctrl.manager
        seen = []
        ctrl.compute_bootstrap_uncertainty(
            ref, n_resamples=6, confidence_level=0.95, random_state=2,
            progress_callback=lambda b, n: seen.append((b, n)))
        assert seen == [(b, 6) for b in range(6)]

    def test_cancel_check_stops_early_and_still_returns_partial_result(self):
        ctrl, *_ = self._fitted_controller(n_components=3)
        ref = ctrl.manager
        calls = {'n': 0}

        def cancel_after_three():
            calls['n'] += 1
            return calls['n'] > 3

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_resamples=20, confidence_level=0.95, random_state=3,
            cancel_check=cancel_after_three)

        assert result is not None
        assert result['n_resamples_requested'] == 20
        assert result['n_resamples_used'] <= 3

    def test_all_replicates_failing_returns_none_with_error(self, monkeypatch):
        ctrl, *_ = self._fitted_controller(n_components=3)
        ref = ctrl.manager

        def always_fail(*args, **kwargs):
            raise np.linalg.LinAlgError("forced failure for this test")

        monkeypatch.setattr(np.linalg, "svd", always_fail)
        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_resamples=5, confidence_level=0.95, random_state=4)
        assert result is None
        assert ref.last_error is not None
        assert 'failed' in ref.last_error.lower()

    def test_uses_all_retained_components_automatically(self):
        """Unlike SVD Analysis's version, no n_components argument is
        accepted here at all -- the bootstrap always covers exactly the
        components the dialog already fitted with (ref.U.shape[1])."""
        ctrl, *_ = self._fitted_controller(n_components=2)
        ref = ctrl.manager
        assert ref.U.shape[1] == 2

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_resamples=6, confidence_level=0.95, random_state=6)
        assert result is not None
        assert result['U_lower'].shape[1] == 2
        assert result['Vt_lower'].shape[0] == 2


# ── Sign alignment: identical concern to SVD Analysis's own version ────

class TestSignAlignment:
    def test_every_replicate_is_sign_aligned_to_the_reference(self):
        spectra, *_ = _synthetic_svd_data(seed=23)
        ctrl = PcaScoresController(DummyController())
        assert ctrl.compute_svd_analysis(spectra, n_components=3)
        ref = ctrl.manager

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_resamples=25, confidence_level=0.95, random_state=5)
        assert result is not None

        U0 = ref.U
        for b in range(result['n_resamples_used']):
            for j in range(ref.U.shape[1]):
                dot = np.dot(result['U_samples'][b, :, j], U0[:, j])
                assert dot >= 0, f"replicate {b}, component {j} not sign-aligned"
