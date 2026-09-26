# tests/test_mcr_als_hybrid_nnls.py
#
# MCRALSManager._hybrid_nnls_columns() -- the helper that replaced three
# "for j in range(n): nnls(A, B[:, j])" loops (C-step, and both ST-step
# branches) in compute(). It must produce EXACTLY the same result as the
# plain per-column loop, always -- the whole point is a pure speed-up,
# never a behavior change. See the helper's own docstring for the
# mathematical argument (nnls's definition guarantees this) and the real
# A/B timing measurement it's based on.

import numpy as np
import pytest
from scipy.optimize import nnls

from src.modules.visualization_analysis.mcr_als_manager import MCRALSManager


def _plain_nnls_loop(A, B):
    """The original, unoptimized implementation this is checked against
    -- call scipy.optimize.nnls on every column of B independently, no
    shortcut. Kept intentionally separate from the manager's own code so
    a future edit to _hybrid_nnls_columns can't accidentally "fix" both
    sides of the comparison at once."""
    k = A.shape[1]
    n_cols = B.shape[1]
    result = np.zeros((k, n_cols))
    for j in range(n_cols):
        x_j, _ = nnls(A, B[:, j])
        result[:, j] = x_j
    return result


class TestHybridNnlsColumns:
    def test_all_columns_already_nonneg_matches_plain_loop(self):
        """Every column's unconstrained solution is already >= 0 (a
        well-conditioned A, positive B aligned with A's column space) --
        the fast path should be taken for every column, and still match
        the plain loop exactly."""
        rng = np.random.RandomState(0)
        A = np.abs(rng.rand(30, 3)) + 0.5   # well-conditioned, positive
        true_x = np.abs(rng.rand(3, 10))     # nonneg "true" coefficients
        B = A @ true_x                       # noiseless -- unconstrained solve recovers true_x exactly, all >= 0

        expected = _plain_nnls_loop(A, B)
        actual = MCRALSManager._hybrid_nnls_columns(A, B)

        assert np.allclose(actual, expected, atol=1e-8)

    def test_all_columns_need_fallback_matches_plain_loop(self):
        """Construct B so the unconstrained solution is negative in some
        component for every single column -- every column must fall back
        to a real nnls() call, and the result must still match the plain
        loop exactly (this is the "worst case, zero columns skipped"
        path -- must never be wrong, only never faster than usual)."""
        rng = np.random.RandomState(1)
        A = np.abs(rng.rand(20, 3)) + 0.1
        # Negative-heavy B drives the unconstrained least-squares fit
        # negative in at least one component for every column.
        B = -np.abs(rng.rand(20, 8)) * 5.0

        expected = _plain_nnls_loop(A, B)
        actual = MCRALSManager._hybrid_nnls_columns(A, B)

        assert np.allclose(actual, expected, atol=1e-8)
        # Sanity check the test itself actually exercises the fallback
        # path (every column's unconstrained solve must be negative
        # somewhere, since that's what forces a real nnls() call rather
        # than the fast path) -- NOT that the nnls answer itself is
        # nonzero. For B this negative, the correct nnls solution really
        # is all-zero (A's columns are all positive, b is all negative,
        # so x=0 is the closest non-negative point to b); asserting
        # otherwise was a flawed assumption about this fixture, not a
        # property _hybrid_nnls_columns needs to satisfy.
        unconstrained = np.linalg.pinv(A) @ B
        assert not np.any(np.all(unconstrained >= 0, axis=0))

    def test_mixed_columns_matches_plain_loop(self):
        """Some columns already satisfy non-negativity unconstrained,
        others don't -- realistic mid-fit case. Both paths (skip and
        fallback) exercised within the same call, still must match
        exactly, column by column."""
        rng = np.random.RandomState(2)
        A = np.abs(rng.rand(25, 4)) + 0.2
        true_x = np.abs(rng.rand(4, 6))
        B_pos = A @ true_x                      # these columns: unconstrained already >= 0
        B_neg = -np.abs(rng.rand(25, 6)) * 3.0  # these columns: need the constraint
        B = np.hstack([B_pos, B_neg])

        expected = _plain_nnls_loop(A, B)
        actual = MCRALSManager._hybrid_nnls_columns(A, B)

        assert np.allclose(actual, expected, atol=1e-8)

    def test_output_shape(self):
        A = np.abs(np.random.RandomState(3).rand(15, 2)) + 0.1
        B = np.abs(np.random.RandomState(4).rand(15, 7))
        result = MCRALSManager._hybrid_nnls_columns(A, B)
        assert result.shape == (2, 7)

    def test_single_column(self):
        """B with just one column -- the loop-vs-vectorized boundary
        case, must still agree with a single plain nnls() call."""
        rng = np.random.RandomState(5)
        A = np.abs(rng.rand(10, 3)) + 0.1
        b = -np.abs(rng.rand(10)) * 2.0
        B = b.reshape(-1, 1)

        expected, _ = nnls(A, b)
        actual = MCRALSManager._hybrid_nnls_columns(A, B)

        assert np.allclose(actual[:, 0], expected, atol=1e-8)


class TestMCRALSComputeUnaffectedByHybridNnls:
    """End-to-end: compute() itself, with the real default settings
    (c_nonneg=True, st_nonneg=True) that route through
    _hybrid_nnls_columns for all three call sites, must produce the same
    kind of well-fit, non-negative decomposition it always did -- this
    doesn't re-derive ground truth (see test_ground_truth_correctness.py
    for that), it just locks in that nothing about compute()'s own
    contract (return value, non-negativity, shapes) changed."""

    def _synthetic_mixture(self, n_spectra=12, n_points=40, n_true=2, seed=7):
        rng = np.random.RandomState(seed)
        x = np.linspace(100.0, 500.0, n_points)
        true_ST = np.abs(rng.rand(n_true, n_points)) + 0.1
        true_C = np.abs(rng.rand(n_spectra, n_true))
        D = true_C @ true_ST
        spectra = [
            {'label': f's{i}', 'x_scale': x.copy(), 'y_scale': D[i, :].copy(),
             'metadata': {}}
            for i in range(n_spectra)
        ]
        return spectra

    def test_compute_succeeds_with_nonneg_result(self):
        mgr = MCRALSManager()
        spectra = self._synthetic_mixture()

        ok = mgr.compute(spectra, n_components=2, max_iterations=50)

        assert ok is True
        assert mgr.C.shape == (12, 2)
        assert mgr.ST.shape == (2, 40)
        assert np.all(mgr.C >= -1e-9)   # non-negativity honored (c_nonneg default True)
        assert np.all(mgr.ST >= -1e-9)  # st_nonneg default True
        assert mgr.lof is not None and mgr.lof < 5.0   # noiseless synthetic mixture, should fit tightly
