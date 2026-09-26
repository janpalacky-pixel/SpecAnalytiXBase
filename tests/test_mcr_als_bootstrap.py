# tests/test_mcr_als_bootstrap.py
#
# Tests for MCR-ALS's "Bootstrap Uncertainty" feature:
#   - MCRALSManager.compute()'s init_ST warm-start parameter (and the
#     matching skip of the end-of-fit reorder-by-explained-variance step)
#   - MCRALSManager.D (the aligned data matrix kept for later reuse)
#   - MCRALSController.compute_bootstrap_uncertainty() -- the residual
#     bootstrap itself
#
# See the Developer Guide's "MCR-ALS Bootstrap Uncertainty" section for
# the full method and reasoning (residual bootstrap, warm-started refit,
# to isolate measurement-noise sensitivity from the separate rotational-
# ambiguity risk "Run N times, keep best" already covers).

import numpy as np
import pytest

from src.modules.visualization_analysis.mcr_als_manager import MCRALSManager
from src.controllers.visualization_analysis.mcr_als_controller import MCRALSController


def _synthetic_mixture(n_spectra=30, n_points=50, n_true=2, seed=7, noise=0.01):
    """A noisy, noiseless-ground-truth-known 2-component mixture -- large
    enough for the bootstrap's residual resampling to be meaningful (30
    rows), small enough to keep these tests fast."""
    rng = np.random.RandomState(seed)
    x = np.linspace(100.0, 500.0, n_points)
    true_ST = np.abs(rng.rand(n_true, n_points)) + 0.1
    true_C = np.abs(rng.rand(n_spectra, n_true)) + 0.05
    D = true_C @ true_ST
    if noise:
        D = D + rng.normal(scale=noise * D.std(), size=D.shape)
        D = np.clip(D, 0, None)
    spectra = [
        {'label': f's{i}', 'x_scale': x.copy(), 'y_scale': D[i, :].copy(),
         'metadata': {}}
        for i in range(n_spectra)
    ]
    return spectra, true_C, true_ST, x


class DummyController:
    """Fake main_controller -- MCRALSController.__init__ only stores it,
    never calls anything on it, matching the other controller tests'
    convention in this file (nothing here exercises main_controller
    interaction, only the bootstrap math itself)."""
    pass


# ── MCRALSManager.compute(): init_ST warm start ─────────────────────────

class TestInitSTWarmStart:
    def test_shape_mismatch_returns_false_with_error(self):
        spectra, _, _, _ = _synthetic_mixture()
        mgr = MCRALSManager()
        bad_init_ST = np.ones((5, 999))   # wrong n_components AND wrong n_wl
        ok = mgr.compute(spectra, n_components=2, init_ST=bad_init_ST)
        assert ok is False
        assert mgr.last_error is not None
        assert 'shape mismatch' in mgr.last_error.lower()

    def test_warm_start_from_own_converged_result_is_stable(self):
        """Warm-starting a fit from ITS OWN converged C/ST, on the exact
        same data (zero perturbation), must reproduce essentially the
        same C/ST -- a warm start should never meaningfully move an
        already-good answer on unchanged data.

        Needs a REFERENCE fit that has genuinely reached its fixed point
        (ref.converged is True), not just exhausted max_iterations while
        still slowly improving -- ALS's asymptotic convergence can be
        slow, so a reference that stopped early only because it hit
        max_iterations is itself still moving, and warm-starting from it
        will keep moving too (confirmed directly: with an inadequate
        budget the two runs' ST differed by ~2e-4, purely because the
        "reference" had not actually converged yet -- not a bug in
        init_ST). A genuinely converged reference needs ~900 iterations
        for this particular synthetic case, so a generous ceiling is used
        here specifically to guarantee that, not because warm-started
        refits normally need anywhere near this many (they don't -- see
        the 2-iteration result below).
        """
        spectra, _, _, _ = _synthetic_mixture(noise=0.0)
        ref = MCRALSManager()
        ok = ref.compute(spectra, n_components=2, max_iterations=5000, tol=1e-10)
        assert ok
        assert ref.converged, "reference fit must genuinely converge for this test to be meaningful"

        warm = MCRALSManager()
        ok2 = warm.compute(spectra, n_components=2, max_iterations=200,
                            tol=1e-8, init_ST=ref.ST)
        assert ok2
        # Warm-starting from an already-converged fixed point should take
        # only the minimum possible number of iterations (the loop always
        # runs at least 2 before it can compare consecutive lof values).
        assert warm.iterations_used <= 3
        assert np.allclose(warm.ST, ref.ST, atol=1e-6)
        assert np.allclose(warm.C, ref.C, atol=1e-6)

    def test_warm_start_skips_reorder_by_explained_variance(self):
        """A plain (non-warm-started) fit reorders components by
        explained variance. Feed init_ST components in the OPPOSITE
        order from what that reordering would produce, on data where the
        two components have clearly different explained variance --
        confirm the warm-started fit keeps init_ST's own order rather
        than silently re-sorting itself."""
        n_true = 2
        rng = np.random.RandomState(11)
        x = np.linspace(100.0, 500.0, 50)
        # Make the two true components have very different magnitudes,
        # so explained variance clearly differs between them.
        true_ST = np.abs(rng.rand(n_true, 50)) + 0.1
        true_C = np.abs(rng.rand(40, n_true))
        true_C[:, 0] *= 5.0   # component 0 dominates -> higher EV%
        D = true_C @ true_ST
        spectra = [
            {'label': f's{i}', 'x_scale': x.copy(), 'y_scale': D[i, :].copy(),
             'metadata': {}}
            for i in range(40)
        ]

        ref = MCRALSManager()
        assert ref.compute(spectra, n_components=2, max_iterations=100)
        # Confirm the reference fit really did put the higher-EV component first.
        assert ref.explained_variance[0] >= ref.explained_variance[1]

        # Warm-start from ST rows in the REVERSED order.
        reversed_init_ST = ref.ST[::-1, :].copy()
        warm = MCRALSManager()
        assert warm.compute(spectra, n_components=2, max_iterations=100,
                             init_ST=reversed_init_ST)
        # If reordering were still happening, warm.ST would come back in
        # the SAME (EV-sorted) order as ref.ST, undoing the reversal.
        # Confirm it instead stayed in the reversed order it started in:
        # warm.ST[0] should correlate with ref.ST[1] (not ref.ST[0]).
        corr_same_slot = abs(np.corrcoef(warm.ST[0], ref.ST[1])[0, 1])
        corr_swapped = abs(np.corrcoef(warm.ST[0], ref.ST[0])[0, 1])
        assert corr_same_slot > 0.9
        assert corr_same_slot > corr_swapped

    def test_D_is_stored_after_a_successful_compute(self):
        spectra, _, _, x = _synthetic_mixture()
        mgr = MCRALSManager()
        assert mgr.compute(spectra, n_components=2)
        assert mgr.D is not None
        expected_D = np.array([s['y_scale'] for s in spectra])
        assert np.allclose(mgr.D, expected_D)

    def test_bootstrap_result_is_none_before_any_bootstrap_call(self):
        spectra, _, _, _ = _synthetic_mixture()
        mgr = MCRALSManager()
        assert mgr.bootstrap_result is None
        assert mgr.compute(spectra, n_components=2)
        assert mgr.bootstrap_result is None   # plain compute() never sets it


# ── MCRALSController.compute_bootstrap_uncertainty() ────────────────────

class TestComputeBootstrapUncertainty:
    def _fitted_controller(self, **mixture_kwargs):
        spectra, true_C, true_ST, x = _synthetic_mixture(**mixture_kwargs)
        ctrl = MCRALSController(DummyController())
        ok = ctrl.compute(spectra, n_components=2, max_iterations=100)
        assert ok
        return ctrl, spectra, true_C, true_ST

    def test_requires_a_fitted_reference_manager(self):
        ctrl = MCRALSController(DummyController())
        fresh = MCRALSManager()   # never compute()'d
        result = ctrl.compute_bootstrap_uncertainty(
            fresh, n_components=2, max_iterations=50, tol=0.01,
            c_nonneg=True, st_nonneg=True, normalize_spectra=True,
            closure=False, n_resamples=5, confidence_level=0.95)
        assert result is None
        assert fresh.last_error is not None

    def test_end_to_end_shapes_and_band_sanity(self):
        ctrl, spectra, true_C, true_ST = self._fitted_controller()
        ref = ctrl.manager
        m, k = ref.C.shape
        n_wl = ref.ST.shape[1]

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, max_iterations=100, tol=0.01,
            c_nonneg=True, st_nonneg=True, normalize_spectra=True,
            closure=False, n_resamples=15, confidence_level=0.95,
            random_state=0)

        assert result is not None
        assert result['ST_lower'].shape == (k, n_wl)
        assert result['ST_upper'].shape == (k, n_wl)
        assert result['C_lower'].shape == (m, k)
        assert result['C_upper'].shape == (m, k)
        assert result['n_resamples_used'] <= result['n_resamples_requested'] == 15
        assert result['ST_samples'].shape[0] == result['n_resamples_used']
        assert result['C_samples'].shape[0] == result['n_resamples_used']
        assert result['confidence_level'] == 0.95

        # A confidence band's lower bound must never exceed its upper bound.
        assert np.all(result['ST_lower'] <= result['ST_upper'] + 1e-12)
        assert np.all(result['C_lower'] <= result['C_upper'] + 1e-12)

        # Stored back on the reference manager too.
        assert ref.bootstrap_result is result

    def test_bootstrap_preserves_component_identity_no_rotation(self):
        """The warm start's whole point: every bootstrap replicate's
        component k should still correspond to the REFERENCE fit's
        component k, not a rotated/relabeled one. Check this directly --
        each replicate's ST[k] should correlate strongly with the
        reference's own ST[k], for every replicate and every k."""
        ctrl, spectra, true_C, true_ST = self._fitted_controller()
        ref = ctrl.manager

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, max_iterations=100, tol=0.01,
            c_nonneg=True, st_nonneg=True, normalize_spectra=True,
            closure=False, n_resamples=12, confidence_level=0.95,
            random_state=1)
        assert result is not None

        for b in range(result['n_resamples_used']):
            for k in range(ref.ST.shape[0]):
                corr = np.corrcoef(result['ST_samples'][b, k], ref.ST[k])[0, 1]
                assert corr > 0.8, f"replicate {b}, component {k}: corr={corr}"

    def test_progress_callback_called_for_every_resample(self):
        ctrl, spectra, true_C, true_ST = self._fitted_controller()
        ref = ctrl.manager
        seen = []
        ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, max_iterations=50, tol=0.01,
            c_nonneg=True, st_nonneg=True, normalize_spectra=True,
            closure=False, n_resamples=6, confidence_level=0.95,
            random_state=2, progress_callback=lambda b, n: seen.append((b, n)))
        assert seen == [(b, 6) for b in range(6)]

    def test_cancel_check_stops_early_and_still_returns_partial_result(self):
        ctrl, spectra, true_C, true_ST = self._fitted_controller()
        ref = ctrl.manager
        calls = {'n': 0}

        def cancel_after_three():
            calls['n'] += 1
            return calls['n'] > 3

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, max_iterations=50, tol=0.01,
            c_nonneg=True, st_nonneg=True, normalize_spectra=True,
            closure=False, n_resamples=20, confidence_level=0.95,
            random_state=3, cancel_check=cancel_after_three)

        assert result is not None
        assert result['n_resamples_requested'] == 20
        assert result['n_resamples_used'] <= 3

    def test_all_replicates_failing_returns_none_with_error(self, monkeypatch):
        ctrl, spectra, true_C, true_ST = self._fitted_controller()
        ref = ctrl.manager

        def always_fail(*args, **kwargs):
            failed_mgr = MCRALSManager()
            failed_mgr.last_error = "forced failure for this test"
            return failed_mgr, False

        monkeypatch.setattr(ctrl, "compute_trial", always_fail)
        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, max_iterations=50, tol=0.01,
            c_nonneg=True, st_nonneg=True, normalize_spectra=True,
            closure=False, n_resamples=5, confidence_level=0.95,
            random_state=4)
        assert result is None
        assert ref.last_error is not None
        assert 'failed' in ref.last_error.lower()

    def test_fixed_reference_row_stays_fixed_across_bootstrap_replicates(self):
        """When a component is anchored to a known reference spectrum
        with fix_references=True, every bootstrap replicate's warm start
        already has that row correct -- and the per-iteration
        fixed-row-holding logic (unrelated to init_ST) re-applies it
        every iteration regardless. Confirm the referenced row comes
        back essentially unchanged in every replicate."""
        spectra, true_C, true_ST, x = _synthetic_mixture(n_true=2, seed=13)
        ref_spectrum = (x, true_ST[0].copy())

        ctrl = MCRALSController(DummyController())
        ok = ctrl.compute(
            spectra, n_components=2, max_iterations=100,
            references={0: ref_spectrum}, fix_references=True)
        assert ok
        ref = ctrl.manager
        assert ref.references_fixed

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, max_iterations=100, tol=0.01,
            c_nonneg=True, st_nonneg=True, normalize_spectra=True,
            closure=False, n_resamples=8, confidence_level=0.95,
            random_state=5,
            references={0: ref_spectrum}, fix_references=True)
        assert result is not None

        for b in range(result['n_resamples_used']):
            corr = np.corrcoef(result['ST_samples'][b, 0], ref.ST[0])[0, 1]
            assert corr > 0.999
