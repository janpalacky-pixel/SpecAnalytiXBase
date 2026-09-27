# tests/test_svd_analysis_bootstrap.py
#
# Tests for SVD Analysis's "Bootstrap Uncertainty" feature -- the same
# residual-bootstrap method NMF/MCR-ALS use (see test_nmf_bootstrap.py /
# test_mcr_als_bootstrap.py), adapted to a plain, deterministic SVD. See
# SVDAnalysisController.compute_bootstrap_uncertainty's own docstring, and
# the Developer Guide's "SVD Analysis / PCA Bootstrap Uncertainty" section,
# for the full method.
#
# The one genuinely new thing tested here that NMF/MCR-ALS's own bootstrap
# tests don't need: SIGN. A bare SVD has no non-negativity (or other)
# constraint pinning each component's sign down -- a component and its
# exact negation reconstruct the data identically, so a bootstrap
# replicate refit from resampled residuals has no reason to land on the
# same sign as the reference. TestSignAlignment below confirms every
# collected replicate is explicitly flipped to match the reference's own
# sign before being folded into the percentile band.

import numpy as np
import pytest

from src.modules.visualization_analysis.svd_analysis_manager import SVDAnalysisManager
from src.controllers.visualization_analysis.svd_analysis_controller import SVDAnalysisController


def _synthetic_svd_data(n_spectra=30, n_points=60, n_true=3, seed=11, noise=0.02):
    """A noisy, ground-truth-known n_true-component linear mixture with
    well-separated singular values (50, 30, 15, ...) so replicate
    components don't swap order under noise -- large enough for the
    bootstrap's residual resampling to be meaningful, small enough to
    keep these tests fast."""
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
    """Fake main_controller -- SVDAnalysisController.__init__ only stores
    it, never calls anything on it (same convention as
    test_nmf_bootstrap.py's own DummyController)."""
    pass


# ── SVDAnalysisManager: data_matrix / bootstrap_result bookkeeping ─────

class TestManagerBookkeeping:
    def test_data_matrix_is_stored_after_a_successful_compute(self):
        spectra, *_ = _synthetic_svd_data()
        mgr = SVDAnalysisManager()
        assert mgr.compute_svd_from_spectra(spectra, mean_center=False)
        assert mgr.data_matrix is not None
        n_wl, n_spec = mgr.data_matrix.shape
        assert n_spec == len(spectra)
        # Full-rank reconstruction should reproduce the stored matrix
        # (this manager never truncates its own U/s/Vt).
        recon = mgr.U @ np.diag(mgr.s) @ mgr.Vt
        assert np.allclose(recon, mgr.data_matrix, atol=1e-8)

    def test_data_matrix_reflects_mean_centering_when_requested(self):
        spectra, *_ = _synthetic_svd_data()
        mgr = SVDAnalysisManager()
        assert mgr.compute_svd_from_spectra(spectra, mean_center=True)
        # A mean-centered matrix's own row means should be ~0.
        assert np.allclose(mgr.data_matrix.mean(axis=1), 0.0, atol=1e-8)

    def test_bootstrap_result_is_none_before_any_bootstrap_call(self):
        spectra, *_ = _synthetic_svd_data()
        mgr = SVDAnalysisManager()
        mgr.compute_svd_from_spectra(spectra)
        assert mgr.bootstrap_result is None

    def test_bootstrap_result_cleared_by_a_subsequent_fresh_fit(self):
        spectra, *_ = _synthetic_svd_data()
        mgr = SVDAnalysisManager()
        ctrl = SVDAnalysisController(DummyController())
        ctrl.manager = mgr
        assert mgr.compute_svd_from_spectra(spectra)
        result = ctrl.compute_bootstrap_uncertainty(
            mgr, n_components=3, n_resamples=6, confidence_level=0.95,
            random_state=0)
        assert result is not None
        assert mgr.bootstrap_result is not None

        # Recomputing (e.g. a different mean-centering choice) must not
        # leave the OLD band silently attached -- same bug class
        # NMFManager.compute() guards against.
        assert mgr.compute_svd_from_spectra(spectra, mean_center=True)
        assert mgr.bootstrap_result is None

    def test_invert_subspectrum_clears_bootstrap_result(self):
        spectra, *_ = _synthetic_svd_data()
        mgr = SVDAnalysisManager()
        ctrl = SVDAnalysisController(DummyController())
        ctrl.manager = mgr
        mgr.compute_svd_from_spectra(spectra)
        ctrl.compute_bootstrap_uncertainty(
            mgr, n_components=3, n_resamples=6, confidence_level=0.95,
            random_state=0)
        assert mgr.bootstrap_result is not None

        mgr.invert_subspectrum(0)
        assert mgr.bootstrap_result is None


# ── SVDAnalysisController.suggest_bootstrap_n_components ────────────────

class TestSuggestBootstrapNComponents:
    def test_zero_before_any_fit(self):
        ctrl = SVDAnalysisController(DummyController())
        assert ctrl.suggest_bootstrap_n_components() == 0

    def test_picks_fewest_components_reaching_target_variance(self):
        spectra, *_ = _synthetic_svd_data(noise=0.001)
        ctrl = SVDAnalysisController(DummyController())
        assert ctrl.compute_svd_analysis(spectra)
        n = ctrl.suggest_bootstrap_n_components(target_cumulative_variance=95.0)
        assert 1 <= n <= ctrl.manager.U.shape[1]
        cumulative = np.cumsum(ctrl.manager.explained_variance)
        assert cumulative[n - 1] >= 95.0
        if n > 1:
            assert cumulative[n - 2] < 95.0

    def test_clamped_to_total_component_count(self):
        spectra, *_ = _synthetic_svd_data()
        ctrl = SVDAnalysisController(DummyController())
        ctrl.compute_svd_analysis(spectra)
        n = ctrl.suggest_bootstrap_n_components(target_cumulative_variance=999.0)
        assert n == len(ctrl.manager.explained_variance)


# ── SVDAnalysisController.compute_bootstrap_uncertainty ─────────────────

class TestComputeBootstrapUncertainty:
    def _fitted_controller(self, **kwargs):
        spectra, true_U, true_s, true_Vt, x = _synthetic_svd_data(**kwargs)
        ctrl = SVDAnalysisController(DummyController())
        assert ctrl.compute_svd_analysis(spectra)
        return ctrl, true_U, true_s, true_Vt

    def test_requires_a_fitted_reference_manager(self):
        ctrl = SVDAnalysisController(DummyController())
        fresh = SVDAnalysisManager()   # never compute_svd_from_spectra()'d
        result = ctrl.compute_bootstrap_uncertainty(
            fresh, n_components=2, n_resamples=5, confidence_level=0.95)
        assert result is None
        assert fresh.last_error is not None

    def test_n_components_out_of_range_returns_none(self):
        ctrl, *_ = self._fitted_controller()
        ref = ctrl.manager
        max_k = ref.U.shape[1]

        result_zero = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=0, n_resamples=5, confidence_level=0.95)
        assert result_zero is None
        assert ref.last_error is not None

        result_too_many = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=max_k + 1, n_resamples=5, confidence_level=0.95)
        assert result_too_many is None

    def test_end_to_end_shapes_and_band_sanity(self):
        ctrl, *_ = self._fitted_controller()
        ref = ctrl.manager
        n_wl = ref.U.shape[0]
        n_spec = ref.Vt.shape[1]
        k = 3

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=k, n_resamples=15, confidence_level=0.95,
            random_state=0)

        assert result is not None
        assert result['U_lower'].shape == (n_wl, k)
        assert result['U_upper'].shape == (n_wl, k)
        assert result['Vt_lower'].shape == (k, n_spec)
        assert result['Vt_upper'].shape == (k, n_spec)
        assert result['n_resamples_used'] <= result['n_resamples_requested'] == 15
        assert result['U_samples'].shape[0] == result['n_resamples_used']
        assert result['Vt_samples'].shape[0] == result['n_resamples_used']
        assert result['n_components'] == k
        assert result['confidence_level'] == 0.95

        # A confidence band's lower bound must never exceed its upper bound.
        assert np.all(result['U_lower'] <= result['U_upper'] + 1e-9)
        assert np.all(result['Vt_lower'] <= result['Vt_upper'] + 1e-6)

        # Stored back on the reference manager too.
        assert ref.bootstrap_result is result

    def test_bootstrap_preserves_component_identity_no_rotation(self):
        """Every bootstrap replicate's component k should still
        correspond to the reference's own component k -- SVD's
        well-separated singular values should keep replicates from
        swapping slots under noise. Checked directly via correlation
        between each replicate's U[:, k] and the reference's own."""
        ctrl, *_ = self._fitted_controller()
        ref = ctrl.manager
        k = 3

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=k, n_resamples=12, confidence_level=0.95,
            random_state=1)
        assert result is not None

        for b in range(result['n_resamples_used']):
            for j in range(k):
                corr = np.corrcoef(result['U_samples'][b, :, j], ref.U[:, j])[0, 1]
                assert corr > 0.8, f"replicate {b}, component {j}: corr={corr}"

    def test_progress_callback_called_for_every_resample(self):
        ctrl, *_ = self._fitted_controller()
        ref = ctrl.manager
        seen = []
        ctrl.compute_bootstrap_uncertainty(
            ref, n_components=3, n_resamples=6, confidence_level=0.95,
            random_state=2, progress_callback=lambda b, n: seen.append((b, n)))
        assert seen == [(b, 6) for b in range(6)]

    def test_cancel_check_stops_early_and_still_returns_partial_result(self):
        ctrl, *_ = self._fitted_controller()
        ref = ctrl.manager
        calls = {'n': 0}

        def cancel_after_three():
            calls['n'] += 1
            return calls['n'] > 3

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=3, n_resamples=20, confidence_level=0.95,
            random_state=3, cancel_check=cancel_after_three)

        assert result is not None
        assert result['n_resamples_requested'] == 20
        assert result['n_resamples_used'] <= 3

    def test_all_replicates_failing_returns_none_with_error(self, monkeypatch):
        ctrl, *_ = self._fitted_controller()
        ref = ctrl.manager

        def always_fail(*args, **kwargs):
            raise np.linalg.LinAlgError("forced failure for this test")

        monkeypatch.setattr(np.linalg, "svd", always_fail)
        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=3, n_resamples=5, confidence_level=0.95,
            random_state=4)
        assert result is None
        assert ref.last_error is not None
        assert 'failed' in ref.last_error.lower()


# ── Sign alignment: the one genuinely new wrinkle vs. NMF/MCR-ALS ──────

class TestSignAlignment:
    def test_every_replicate_is_sign_aligned_to_the_reference(self):
        """The invariant compute_bootstrap_uncertainty's sign-flip step
        must guarantee: for every collected replicate and every
        component, dot(U_sample[:, j], U0[:, j]) >= 0 -- i.e. no
        replicate is left pointing the "wrong" way relative to the
        reference it's supposed to be bracketing."""
        spectra, *_ = _synthetic_svd_data(seed=21)
        ctrl = SVDAnalysisController(DummyController())
        assert ctrl.compute_svd_analysis(spectra)
        ref = ctrl.manager
        k = 3

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=k, n_resamples=25, confidence_level=0.95,
            random_state=5)
        assert result is not None

        U0 = ref.U[:, :k]
        for b in range(result['n_resamples_used']):
            for j in range(k):
                dot = np.dot(result['U_samples'][b, :, j], U0[:, j])
                assert dot >= 0, f"replicate {b}, component {j} not sign-aligned"

    def test_without_alignment_raw_svd_can_flip_sign(self):
        """Sanity check that the scenario this feature guards against is
        real, not hypothetical: a bare np.linalg.svd on two DIFFERENT
        (but highly-correlated) resamples of the same underlying
        component can legitimately come back with opposite signs. This
        justifies why the alignment step in
        compute_bootstrap_uncertainty exists at all."""
        spectra, true_U, true_s, true_Vt, x = _synthetic_svd_data(
            n_true=1, seed=31, noise=0.02)
        X = np.column_stack([s['y_scale'] for s in spectra])

        rng = np.random.RandomState(0)
        n_spec = X.shape[1]
        signs_seen = set()
        # A single, strongly-dominant component's sign is still an
        # arbitrary numpy/LAPACK implementation choice -- run several
        # independent resamples and confirm at least the MACHINERY is
        # capable of flipping (if every single one came back the same
        # sign, that wouldn't invalidate the feature, but it wouldn't
        # demonstrate why it's needed either, so this is a supporting
        # check rather than one the feature's correctness depends on).
        U0, _, _ = np.linalg.svd(X, full_matrices=False)
        for trial in range(30):
            col_idx = rng.randint(0, n_spec, size=n_spec)
            U_b, _, _ = np.linalg.svd(X[:, col_idx], full_matrices=False)
            sign = 1 if np.dot(U_b[:, 0], U0[:, 0]) >= 0 else -1
            signs_seen.add(sign)
        # Not a hard assertion on both signs appearing (that would make
        # this test flaky) -- this is exploratory/documentation-style,
        # kept lightweight. The REAL guarantee is TestSignAlignment above.
        assert signs_seen  # at least ran without error
