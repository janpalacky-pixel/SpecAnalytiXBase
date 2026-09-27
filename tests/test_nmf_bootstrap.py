# tests/test_nmf_bootstrap.py
#
# Tests for NMF's "Bootstrap Uncertainty" feature -- the direct
# counterpart to MCR-ALS's own (see tests/test_mcr_als_bootstrap.py),
# covering:
#   - NMFManager.compute()'s init_H warm-start parameter (and the
#     matching skip of the end-of-fit reorder-by-explained-variance step)
#   - NMFManager.X_nn (the aligned, clipped data matrix kept for later
#     reuse)
#   - NMFController.compute_bootstrap_uncertainty() -- the residual
#     bootstrap itself
#
# See the Developer Guide's "NMF Bootstrap Uncertainty" section for the
# full method and reasoning. One thing genuinely differs from MCR-ALS's
# version here: NMF's cold reference fit (when it has no references)
# runs through scikit-learn's own solver, while every bootstrap
# replicate is ALWAYS refit through the hand-written multiplicative-
# update (MU) loop (NMFManager._fit_with_references), regardless of
# which algorithm produced the reference. This is a deliberate cross-
# algorithm warm start, justified because any genuine local minimum of
# the Frobenius NMF objective is also a fixed point of the Lee & Seung
# MU update rule -- so it never drifts to some OTHER point/rotation.
# It does NOT, however, mean the warm start always finishes in a couple
# of iterations: that turns out to depend on how tightly the reference
# itself converged. TestInitHWarmStart below has two tests for this --
# test_warm_start_from_own_converged_result_is_stable, which forces the
# reference through the SAME algorithm (MU loop, via a trivial
# non-fixed reference) and confirms near-instant, near-exact stability
# (2 iterations, atol=1e-3), and
# test_warm_start_from_sklearn_cold_fit_stays_in_same_basin, which uses
# a REAL scikit-learn cold fit (no references) and confirms the looser,
# but still meaningful, guarantee that actually holds there: the warm
# fit never ends up worse than the reference, and never rotates to a
# different component identity, even though it may need many more
# iterations to fully converge (scikit-learn's default tol=1e-4 was
# confirmed empirically, while building this test, to stop well short
# of the MU loop's own tighter convergence criterion on this data).

import numpy as np
import pytest

from src.modules.visualization_analysis.nmf_manager import NMFManager
from src.controllers.visualization_analysis.nmf_controller import NMFController


def _synthetic_mixture(n_spectra=30, n_points=50, n_true=2, seed=7, noise=0.01):
    """A noisy, ground-truth-known 2-component non-negative mixture --
    large enough for the bootstrap's residual resampling to be
    meaningful (30 rows), small enough to keep these tests fast. Same
    construction as test_mcr_als_bootstrap.py's own helper (both
    factors already non-negative, so it's equally valid input for NMF)."""
    rng = np.random.RandomState(seed)
    x = np.linspace(100.0, 500.0, n_points)
    true_H = np.abs(rng.rand(n_true, n_points)) + 0.1
    true_W = np.abs(rng.rand(n_spectra, n_true)) + 0.05
    X = true_W @ true_H
    if noise:
        X = X + rng.normal(scale=noise * X.std(), size=X.shape)
        X = np.clip(X, 0, None)
    spectra = [
        {'label': f's{i}', 'x_scale': x.copy(), 'y_scale': X[i, :].copy(),
         'metadata': {}}
        for i in range(n_spectra)
    ]
    return spectra, true_W, true_H, x


class DummyController:
    """Fake main_controller -- NMFController.__init__ only stores it,
    never calls anything on it, matching test_mcr_als_bootstrap.py's own
    convention (nothing here exercises main_controller interaction, only
    the bootstrap math itself)."""
    pass


# ── NMFManager.compute(): init_H warm start ─────────────────────────────

class TestInitHWarmStart:
    def test_shape_mismatch_returns_false_with_error(self):
        spectra, _, _, _ = _synthetic_mixture()
        mgr = NMFManager()
        bad_init_H = np.ones((5, 999))   # wrong n_components AND wrong n_wl
        ok = mgr.compute(spectra, n_components=2, init_H=bad_init_H)
        assert ok is False
        assert mgr.last_error is not None
        assert 'shape mismatch' in mgr.last_error.lower()

    def test_warm_start_from_own_converged_result_is_stable(self):
        """Warm-starting a fit from ITS OWN converged H, on the exact
        same data (zero perturbation), must reproduce essentially the
        same W/H -- a warm start should never meaningfully move an
        already-good answer on unchanged data.

        This needs the REFERENCE fit itself to run through the SAME
        algorithm (the hand-written MU loop) the warm-started refit
        uses, exactly like MCR-ALS's version of this test -- so it uses
        a trivial, non-fixed reference spectrum (fix_references=False)
        to route the cold reference fit through _fit_with_references()
        too, rather than through scikit-learn's solver. This is a real,
        supported code path (references anchor a component's STARTING
        guess without holding it fixed), not a test-only trick.

        Deliberately NOT tested this way: a reference fit via
        scikit-learn's own solver (no references at all) -- see
        test_warm_start_from_sklearn_cold_fit_stays_in_same_basin below
        for why that case needs different, looser assertions.
        """
        spectra, _, true_H, x = _synthetic_mixture(noise=0.0)
        trivial_ref = {0: (x, true_H[0].copy())}
        ref = NMFManager()
        ok = ref.compute(spectra, n_components=2, max_iter=5000,
                          references=trivial_ref, fix_references=False)
        assert ok
        assert ref.converged, "reference fit must genuinely converge for this test to be meaningful"

        warm = NMFManager()
        ok2 = warm.compute(spectra, n_components=2, max_iter=200,
                            init_H=ref.H)
        assert ok2
        # Warm-starting from an already-converged fixed point should take
        # only a couple of iterations (the MU loop always runs at least 1
        # before it can compare consecutive reconstruction errors).
        assert warm.iterations_used <= 5
        assert np.allclose(warm.H, ref.H, atol=1e-3)
        assert np.allclose(warm.W, ref.W, atol=1e-3)

    def test_warm_start_from_sklearn_cold_fit_stays_in_same_basin(self):
        """The realistic case: the reference fit has NO references, so it
        runs entirely through scikit-learn's own solver, using scikit-
        learn's own default convergence tolerance (tol=1e-4). That
        tolerance is measurably looser than the MU loop's own convergence
        check (confirmed empirically while building this test: on this
        exact synthetic mixture, tightening scikit-learn's tol from 1e-4
        to 1e-6/1e-8/1e-10 kept driving its reconstruction error down by
        orders of magnitude further at the SAME fixed point) -- so unlike
        the same-algorithm case above, a warm start from a real sklearn
        cold fit should NOT be expected to stabilize in a couple of
        iterations. What it must still do: never increase reconstruction
        error beyond the reference's own (plain multiplicative updates
        are monotonically non-increasing by construction) and stay in the
        same component-identity basin (no rotation) rather than
        wandering to some other, unrelated local optimum -- exactly what
        actually matters for the bootstrap band being meaningful.
        """
        spectra, _, _, _ = _synthetic_mixture(noise=0.0)
        ref = NMFManager()
        ok = ref.compute(spectra, n_components=2, init='nndsvda', max_iter=2000)
        assert ok

        warm = NMFManager()
        ok2 = warm.compute(spectra, n_components=2, max_iter=1000, init_H=ref.H)
        assert ok2

        # Never worse than the reference it started from (small numerical
        # slack for floating-point noise right at a shared fixed point).
        assert warm.reconstruction_error <= ref.reconstruction_error + 1e-9

        # Same component identity, no rotation.
        for k in range(2):
            corr = np.corrcoef(warm.H[k], ref.H[k])[0, 1]
            assert corr > 0.999, f"component {k}: corr={corr}"

    def test_warm_start_skips_reorder_by_explained_variance(self):
        """A plain (non-warm-started, no-reference) fit reorders
        components by explained variance. Feed init_H components in the
        OPPOSITE order from what that reordering would produce, on data
        where the two components have clearly different explained
        variance -- confirm the warm-started fit keeps init_H's own
        order rather than silently re-sorting itself."""
        n_true = 2
        rng = np.random.RandomState(11)
        x = np.linspace(100.0, 500.0, 50)
        # Make the two true components have very different magnitudes,
        # so explained variance clearly differs between them.
        true_H = np.abs(rng.rand(n_true, 50)) + 0.1
        true_W = np.abs(rng.rand(40, n_true))
        true_W[:, 0] *= 5.0   # component 0 dominates -> higher EV%
        X = true_W @ true_H
        spectra = [
            {'label': f's{i}', 'x_scale': x.copy(), 'y_scale': X[i, :].copy(),
             'metadata': {}}
            for i in range(40)
        ]

        ref = NMFManager()
        assert ref.compute(spectra, n_components=2, init='nndsvda', max_iter=500)
        # Confirm the reference fit really did put the higher-EV component first.
        assert ref.explained_variance[0] >= ref.explained_variance[1]

        # Warm-start from H rows in the REVERSED order.
        reversed_init_H = ref.H[::-1, :].copy()
        warm = NMFManager()
        assert warm.compute(spectra, n_components=2, max_iter=500,
                             init_H=reversed_init_H)
        # If reordering were still happening, warm.H would come back in
        # the SAME (EV-sorted) order as ref.H, undoing the reversal.
        # Confirm it instead stayed in the reversed order it started in:
        # warm.H[0] should correlate with ref.H[1] (not ref.H[0]).
        corr_same_slot = abs(np.corrcoef(warm.H[0], ref.H[1])[0, 1])
        corr_swapped = abs(np.corrcoef(warm.H[0], ref.H[0])[0, 1])
        assert corr_same_slot > 0.9
        assert corr_same_slot > corr_swapped

    def test_X_nn_is_stored_after_a_successful_compute(self):
        spectra, _, _, x = _synthetic_mixture()
        mgr = NMFManager()
        assert mgr.compute(spectra, n_components=2)
        assert mgr.X_nn is not None
        expected_X_nn = np.clip(np.array([s['y_scale'] for s in spectra]), 0, None)
        assert np.allclose(mgr.X_nn, expected_X_nn)

    def test_bootstrap_result_is_none_before_any_bootstrap_call(self):
        spectra, _, _, _ = _synthetic_mixture()
        mgr = NMFManager()
        assert mgr.bootstrap_result is None
        assert mgr.compute(spectra, n_components=2)
        assert mgr.bootstrap_result is None   # plain compute() never sets it

    def test_bootstrap_result_cleared_by_a_subsequent_fresh_fit(self):
        """Real bug found in practice: the dialog reuses ONE manager
        instance across repeated "Run NMF" clicks (NMFController.manager
        is created once, not recreated per click). If a stale
        bootstrap_result from an earlier fit survived a later, unrelated
        compute() call on the SAME manager, the Components/Concentrations
        tabs would redraw the new curves together with a confidence band
        computed for a DIFFERENT (possibly differently-shaped) fit --
        either a visibly mismatched/ghosted overlay, or an IndexError if
        the component count changed. compute() must clear
        bootstrap_result on every fresh successful fit."""
        spectra, _, _, _ = _synthetic_mixture()
        mgr = NMFManager()
        assert mgr.compute(spectra, n_components=2)

        ctrl = NMFController(DummyController())
        ctrl.manager = mgr
        result = ctrl.compute_bootstrap_uncertainty(
            mgr, n_components=2, init='nndsvda', max_iter=200,
            n_resamples=5, confidence_level=0.95, random_state=0)
        assert result is not None
        assert mgr.bootstrap_result is result

        # Re-run the SAME manager with a different component count --
        # exactly the "change settings, don't re-run before bootstrapping,
        # then run again" sequence that surfaced this bug.
        assert mgr.compute(spectra, n_components=3)
        assert mgr.bootstrap_result is None


# ── NMFController.compute_bootstrap_uncertainty() ──────────────────────

class TestComputeBootstrapUncertainty:
    def _fitted_controller(self, **mixture_kwargs):
        spectra, true_W, true_H, x = _synthetic_mixture(**mixture_kwargs)
        ctrl = NMFController(DummyController())
        ok = ctrl.compute(spectra, n_components=2, init='nndsvda', max_iter=300)
        assert ok
        return ctrl, spectra, true_W, true_H

    def test_requires_a_fitted_reference_manager(self):
        ctrl = NMFController(DummyController())
        fresh = NMFManager()   # never compute()'d
        result = ctrl.compute_bootstrap_uncertainty(
            fresh, n_components=2, init='nndsvda', max_iter=50,
            n_resamples=5, confidence_level=0.95)
        assert result is None
        assert fresh.last_error is not None

    def test_end_to_end_shapes_and_band_sanity(self):
        ctrl, spectra, true_W, true_H = self._fitted_controller()
        ref = ctrl.manager
        m, k = ref.W.shape
        n_wl = ref.H.shape[1]

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, init='nndsvda', max_iter=300,
            n_resamples=15, confidence_level=0.95, random_state=0)

        assert result is not None
        assert result['H_lower'].shape == (k, n_wl)
        assert result['H_upper'].shape == (k, n_wl)
        assert result['W_lower'].shape == (m, k)
        assert result['W_upper'].shape == (m, k)
        assert result['n_resamples_used'] <= result['n_resamples_requested'] == 15
        assert result['H_samples'].shape[0] == result['n_resamples_used']
        assert result['W_samples'].shape[0] == result['n_resamples_used']
        assert result['confidence_level'] == 0.95

        # A confidence band's lower bound must never exceed its upper bound.
        assert np.all(result['H_lower'] <= result['H_upper'] + 1e-12)
        assert np.all(result['W_lower'] <= result['W_upper'] + 1e-12)

        # Stored back on the reference manager too.
        assert ref.bootstrap_result is result

    def test_bootstrap_preserves_component_identity_no_rotation(self):
        """The warm start's whole point: every bootstrap replicate's
        component k should still correspond to the REFERENCE fit's
        component k, not a rotated/relabeled one. Check this directly --
        each replicate's H[k] should correlate strongly with the
        reference's own H[k], for every replicate and every k."""
        ctrl, spectra, true_W, true_H = self._fitted_controller()
        ref = ctrl.manager

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, init='nndsvda', max_iter=300,
            n_resamples=12, confidence_level=0.95, random_state=1)
        assert result is not None

        for b in range(result['n_resamples_used']):
            for k in range(ref.H.shape[0]):
                corr = np.corrcoef(result['H_samples'][b, k], ref.H[k])[0, 1]
                assert corr > 0.8, f"replicate {b}, component {k}: corr={corr}"

    def test_progress_callback_called_for_every_resample(self):
        ctrl, spectra, true_W, true_H = self._fitted_controller()
        ref = ctrl.manager
        seen = []
        ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, init='nndsvda', max_iter=200,
            n_resamples=6, confidence_level=0.95, random_state=2,
            progress_callback=lambda b, n: seen.append((b, n)))
        assert seen == [(b, 6) for b in range(6)]

    def test_cancel_check_stops_early_and_still_returns_partial_result(self):
        ctrl, spectra, true_W, true_H = self._fitted_controller()
        ref = ctrl.manager
        calls = {'n': 0}

        def cancel_after_three():
            calls['n'] += 1
            return calls['n'] > 3

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, init='nndsvda', max_iter=200,
            n_resamples=20, confidence_level=0.95, random_state=3,
            cancel_check=cancel_after_three)

        assert result is not None
        assert result['n_resamples_requested'] == 20
        assert result['n_resamples_used'] <= 3

    def test_all_replicates_failing_returns_none_with_error(self, monkeypatch):
        ctrl, spectra, true_W, true_H = self._fitted_controller()
        ref = ctrl.manager

        def always_fail(*args, **kwargs):
            failed_mgr = NMFManager()
            failed_mgr.last_error = "forced failure for this test"
            return failed_mgr, False

        monkeypatch.setattr(ctrl, "compute_trial", always_fail)
        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, init='nndsvda', max_iter=200,
            n_resamples=5, confidence_level=0.95, random_state=4)
        assert result is None
        assert ref.last_error is not None
        assert 'failed' in ref.last_error.lower()

    def test_fixed_reference_row_stays_fixed_across_bootstrap_replicates(self):
        """When a component is anchored to a known reference spectrum
        with fix_references=True, every bootstrap replicate's warm start
        already has that row correct -- and the per-iteration
        fixed-row-holding logic (unrelated to init_H) re-applies it
        every iteration regardless. Confirm the referenced row comes
        back essentially unchanged in every replicate."""
        spectra, true_W, true_H, x = _synthetic_mixture(n_true=2, seed=13)
        ref_spectrum = (x, true_H[0].copy())

        ctrl = NMFController(DummyController())
        ok = ctrl.compute(
            spectra, n_components=2, init='nndsvda', max_iter=300,
            references={0: ref_spectrum}, fix_references=True)
        assert ok
        ref = ctrl.manager
        assert ref.references_fixed

        result = ctrl.compute_bootstrap_uncertainty(
            ref, n_components=2, init='nndsvda', max_iter=300,
            n_resamples=8, confidence_level=0.95, random_state=5,
            references={0: ref_spectrum}, fix_references=True)
        assert result is not None

        for b in range(result['n_resamples_used']):
            corr = np.corrcoef(result['H_samples'][b, 0], ref.H[0])[0, 1]
            assert corr > 0.999
