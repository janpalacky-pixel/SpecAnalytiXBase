# tests/test_regression_bugs.py
"""
Regression tests for specific, previously-shipped bugs that were found and
fixed by hand (via manual testing, screenshots, and numeric investigation)
rather than caught by the existing test suite. Each test locks in the
scenario that used to break, with a comment giving the concrete before/after
numbers so a future change that silently reintroduces the bug fails loudly
here instead of requiring another round of manual debugging.

Unlike the rest of the suite (import/export pipeline, snapshot system),
these tests reach into a handful of pure-Python/numpy computational modules
directly — no PyQt, no file I/O beyond what a test itself sets up.
"""

import numpy as np
import pytest

from src.modules.core.spectrum_manager import Spectrum, _merge_duplicate_x
from src.modules.visualization_analysis.ground_truth_comparison import (
    GroundTruth, align_concentration_rows,
)
from src.modules.visualization_analysis.mcr_als_manager import MCRALSManager


# ---------------------------------------------------------------------- #
# MCR-ALS: Closure + fixed-reference scale mismatch                       #
# ---------------------------------------------------------------------- #

class TestMCRALSClosureReferenceScale:
    """
    Bug: when a reference (known pure) spectrum was fixed AND Closure was
    on, the reference row was still being force-rescaled to unit L2 norm —
    a leftover from the non-closure code path, where ST rows are unit-normed
    and C absorbs the scale. Under closure, C's rows are constrained to sum
    to exactly 1 (a real absolute-scale constraint), so an arbitrarily
    rescaled fixed row could not be compensated for by C the way it can
    when closure is off. Measured on a real benchmark at the time: lack-of-
    fit went from 0.11% (no reference) to 59.8% (reference fixed, closure
    on, buggy) — the referenced component's concentration got pinned near
    its ceiling everywhere instead of tracking its true profile.

    Fixed by only rescaling the reference to unit norm when closure=False;
    under closure it is used at its own natural (data-matching) scale, the
    same scale every other spectrum is already on.

    This test builds a genuinely closed synthetic system (concentrations
    sum to 1 per spectrum, noise-free) so a correct fit should recover it
    almost exactly. The threshold is set well below the ~60% the bug
    produced but well above achievable noise-free recovery error, so it
    fails clearly if the unconditional rescale is ever reintroduced.
    """

    @staticmethod
    def _closed_system():
        x = np.linspace(0.0, 100.0, 60)

        def gauss(mu, sigma):
            return np.exp(-0.5 * ((x - mu) / sigma) ** 2)

        st_true = np.array([gauss(20, 8), gauss(50, 8), gauss(80, 8)])

        rng = np.random.RandomState(0)
        raw = rng.rand(8, 3) + 0.1
        c_true = raw / raw.sum(axis=1, keepdims=True)   # rows sum to 1

        d = c_true @ st_true
        spectra = [
            {'label': f'mix_{i:02d}', 'x_scale': x.copy(), 'y_scale': d[i].copy()}
            for i in range(d.shape[0])
        ]
        return x, st_true, spectra

    def test_closure_with_fixed_reference_does_not_blow_up_lof(self):
        x, st_true, spectra = self._closed_system()
        references = {0: (x, st_true[0].copy())}

        mgr = MCRALSManager()
        ok = mgr.compute(
            spectra, n_components=3, closure=True,
            references=references, fix_references=True,
            max_iterations=200,
        )
        assert ok
        # Bug produced ~59.8% on an analogous case; a correct fit on this
        # noise-free closed system should be near-perfect (< 2%).
        assert mgr.lof < 2.0

    def test_closure_with_fixed_reference_matches_unreferenced_baseline(self):
        """The reference shouldn't make the fit worse than not using one —
        under the bug it made it dramatically worse (0.11% -> 59.8%)."""
        x, st_true, spectra = self._closed_system()
        references = {0: (x, st_true[0].copy())}

        baseline = MCRALSManager()
        baseline.compute(spectra, n_components=3, closure=True, max_iterations=200)

        referenced = MCRALSManager()
        referenced.compute(
            spectra, n_components=3, closure=True,
            references=references, fix_references=True,
            max_iterations=200,
        )
        assert referenced.lof < baseline.lof * 5 + 1.0

    def test_closure_off_still_unit_norms_reference(self):
        """Regression guard for the fix's OWN caveat: the fix only skips
        the rescale when closure=True. With closure=False, the reference
        row must still come out unit-normed, exactly as before the fix —
        otherwise the fix would have broken the still-working case while
        solving the closure case."""
        x, st_true, spectra = self._closed_system()
        references = {0: (x, st_true[0].copy())}

        mgr = MCRALSManager()
        ok = mgr.compute(
            spectra, n_components=3, closure=False,
            references=references, fix_references=True,
            max_iterations=200,
        )
        assert ok
        assert mgr.ST[0] is not None
        np.testing.assert_allclose(np.linalg.norm(mgr.ST[0]), 1.0, atol=1e-8)


# ---------------------------------------------------------------------- #
# Ground-truth comparison: label matching across import prefixes          #
# ---------------------------------------------------------------------- #

class TestGroundTruthLabelMatching:
    """
    Bug: align_concentration_rows() only tried an exact match between a
    fitted spectrum's label and the ground-truth workbook's bare column
    header ("raman_01"). A normally-imported spectrum is never labelled
    with the bare header — table_data_converter._parse_column_data always
    prefixes it with the workbook's filename ("raman_3comp_noisy :
    raman_01"), and importing multiple sheets adds a further "[<sheet>]"
    tag on top of that. Under the bug this matched 0/30 spectra for any
    normally-imported dataset. Fixed by falling back to matching on the
    part after the LAST " : " when the exact match fails.
    """

    @staticmethod
    def _truth():
        return GroundTruth(
            filename='raman_3comp_noisy.xlsx',
            x_axis=np.linspace(0, 10, 5),
            components=np.zeros((3, 5)),
            component_labels=['Component_1', 'Component_2', 'Component_3'],
            spectrum_labels=['raman_01', 'raman_02', 'raman_03'],
            concentrations=np.array([[0.5, 0.3, 0.2], [0.2, 0.5, 0.3], [0.1, 0.1, 0.8]]),
        )

    def test_exact_match_still_works(self):
        truth = self._truth()
        rows, unmatched = align_concentration_rows(['raman_01', 'raman_02'], truth)
        assert rows == [0, 1]
        assert unmatched == []

    def test_single_import_prefix_falls_back_to_suffix(self):
        """'<workbook> : <header>' — the label shape produced by a normal
        single-sheet import."""
        truth = self._truth()
        fitted_labels = [
            'raman_3comp_noisy : raman_01',
            'raman_3comp_noisy : raman_02',
            'raman_3comp_noisy : raman_03',
        ]
        rows, unmatched = align_concentration_rows(fitted_labels, truth)
        assert rows == [0, 1, 2]
        assert unmatched == []

    def test_multi_sheet_import_tag_falls_back_to_suffix(self):
        """'<workbook> [<sheet>] : <header>' — the label shape produced by
        "import several sheets"."""
        truth = self._truth()
        fitted_labels = [
            'raman_3comp_noisy [Spectra] : raman_01',
            'raman_3comp_noisy [Spectra] : raman_02',
        ]
        rows, unmatched = align_concentration_rows(fitted_labels, truth)
        assert rows == [0, 1]
        assert unmatched == []

    def test_genuinely_unmatched_label_reported(self):
        truth = self._truth()
        rows, unmatched = align_concentration_rows(
            ['raman_3comp_noisy : raman_01', 'some_other_file : not_in_truth'], truth)
        assert rows == [0, None]
        assert unmatched == ['some_other_file : not_in_truth']


# ---------------------------------------------------------------------- #
# Duplicate x-values: merge, don't silently drop or misinterpolate        #
# ---------------------------------------------------------------------- #

class TestDuplicateXMerge:
    """
    Bug: spectra with a repeated x-value behaved inconsistently between the
    Save path and the analysis path, each using its own independently-coded
    tolerance for "duplicate" — and neither told the user anything happened.
    Downstream, every np.interp-based operation (Savitzky-Golay, FFT
    denoising, SNIP/other baselines, peak fitting, resampling) assumes
    exactly one y per x; a leftover duplicate doesn't error, it silently
    returns whichever side of the tie np.interp's implementation lands on.
    Fixed with one shared merge routine, run centrally at import time, that
    averages duplicate y-values, warns, and preserves the pre-merge data
    (not just silently drops points).
    """

    def test_duplicate_x_values_are_averaged(self):
        spectrum = {
            'label': 'dup_test',
            'x_scale': np.array([1.0, 2.0, 2.0, 3.0]),
            'y_scale': np.array([10.0, 20.0, 30.0, 40.0]),
        }
        _merge_duplicate_x(spectrum)
        np.testing.assert_array_equal(spectrum['x_scale'], [1.0, 2.0, 3.0])
        np.testing.assert_allclose(spectrum['y_scale'], [10.0, 25.0, 40.0])

    def test_pre_merge_data_preserved_in_metadata(self):
        spectrum = {
            'label': 'dup_test',
            'x_scale': np.array([1.0, 2.0, 2.0, 3.0]),
            'y_scale': np.array([10.0, 20.0, 30.0, 40.0]),
            'metadata': {},
        }
        _merge_duplicate_x(spectrum)
        stash = spectrum['metadata']['duplicate_x_merge']
        assert stash['n_merged'] == 1
        np.testing.assert_array_equal(stash['x_scale'], [1.0, 2.0, 2.0, 3.0])
        np.testing.assert_array_equal(stash['y_scale'], [10.0, 20.0, 30.0, 40.0])

    def test_valid_points_metadata_updated_when_present(self):
        spectrum = {
            'label': 'dup_test',
            'x_scale': np.array([1.0, 2.0, 2.0, 3.0]),
            'y_scale': np.array([10.0, 20.0, 30.0, 40.0]),
            'metadata': {'valid_points': 4},
        }
        _merge_duplicate_x(spectrum)
        assert spectrum['metadata']['valid_points'] == 3

    def test_no_duplicates_is_a_no_op(self):
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([10.0, 20.0, 30.0])
        spectrum = {'label': 'clean', 'x_scale': x.copy(), 'y_scale': y.copy(), 'metadata': {}}
        _merge_duplicate_x(spectrum)
        np.testing.assert_array_equal(spectrum['x_scale'], x)
        np.testing.assert_array_equal(spectrum['y_scale'], y)
        assert 'duplicate_x_merge' not in spectrum['metadata']


# ---------------------------------------------------------------------- #
# Single-point spectrum: squeeze() collapsing to a 0-d array               #
# ---------------------------------------------------------------------- #

class TestSinglePointSpectrumSurvives:
    """
    Bug: Spectrum.__post_init__ used .squeeze() alone to drop stray size-1
    axes from freshly-parsed data (e.g. a (1, 1) array from a spreadsheet
    column). squeeze() drops EVERY size-1 axis, so a genuinely single-point
    spectrum — shape (1,) — collapsed all the way to a 0-d array. len() on
    a 0-d array raises TypeError, which SpectrumManager._store_spectrum_dict
    caught and logged, silently dropping the spectrum with no error shown
    to the user — it just never appeared in the list. Fixed by wrapping the
    squeeze() result in np.atleast_1d, which restores a length-1 array
    afterward for genuinely single-point data while still dropping stray
    size-1 axes for everything else.
    """

    def test_single_point_from_1d_arrays_does_not_raise(self):
        s = Spectrum(x_scale=np.array([100.0]), y_scale=np.array([5.0]))
        assert len(s.x_scale) == 1
        assert len(s.y_scale) == 1
        assert s.x_scale[0] == 100.0
        assert s.y_scale[0] == 5.0

    def test_single_point_from_2d_column_does_not_raise(self):
        """The (1, 1)-shaped case a spreadsheet single-cell column produces."""
        s = Spectrum(x_scale=np.array([[100.0]]), y_scale=np.array([[5.0]]))
        assert len(s.x_scale) == 1
        assert len(s.y_scale) == 1

    def test_multi_point_still_works_normally(self):
        s = Spectrum(x_scale=np.array([1.0, 2.0, 3.0]), y_scale=np.array([4.0, 5.0, 6.0]))
        assert len(s.x_scale) == 3
        assert len(s.y_scale) == 3

    def test_mismatched_lengths_still_raise(self):
        with pytest.raises(ValueError):
            Spectrum(x_scale=np.array([1.0, 2.0]), y_scale=np.array([1.0]))


# ---------------------------------------------------------------------- #
# NumPy/Matplotlib API removals (NumPy 2.x, Matplotlib 3.11)              #
# ---------------------------------------------------------------------- #
#
# The four tests below lock in real crashes found by running the app
# itself against freshly-installed, current-at-the-time library versions
# (NumPy 2.5.3, Matplotlib 3.11.2, pandas 3.0.6) — not just the code's own
# lower-bound requirements, which had drifted out of date. Two distinct
# API removals were involved:
#
#   * np.row_stack was removed (renamed to np.vstack back in NumPy 2.0).
#     Hit in Cluster Analysis (K-Means/Hierarchical) and SOM — but those
#     are already covered by test_cluster_analysis_silhouette_bounds.py
#     and test_som_last_error.py, which is how this was first caught.
#     compute_elbow_curve() has the identical call but, unlike the other
#     two, had no test coverage at all before this — added here.
#
#   * np.trapz was removed (renamed to np.trapezoid in NumPy 2.0). Five
#     modules already had a `getattr(np, 'trapezoid', None) or np.trapz`
#     shim guarding against exactly this; normalization_manager.py and
#     map2d_manager.py had been missed. Covered below.


from src.modules.visualization_analysis.cluster_analysis_manager import ClusterAnalysisManager
from src.modules.visualization_analysis.map2d_manager import Map2DManager
from src.modules.data_analysis.normalization_manager import NormalizationManager


class TestClusterAnalysisElbowCurveNoCrash:
    """
    Bug: compute_elbow_curve() builds its data matrix with np.row_stack,
    same as compute_clustering() and compute_som() — but unlike those two,
    no test exercised this method at all, so a reintroduced np.row_stack
    here would currently pass CI even though it crashes the app (the
    "suggest number of clusters" elbow plot in the Cluster Analysis tool).
    """

    def test_elbow_curve_runs_without_crashing(self):
        rng = np.random.default_rng(0)
        spectra = [
            {'label': f'sp{i}', 'y_scale': rng.random(30), 'x_scale': np.arange(30)}
            for i in range(8)
        ]
        mgr = ClusterAnalysisManager()
        k_values, wcss = mgr.compute_elbow_curve(spectra, max_clusters=5)
        assert k_values is not None
        assert wcss is not None
        assert len(k_values) == len(wcss)
        assert all(np.isfinite(w) for w in wcss)


class TestMap2DIntegralMetricUsesTrapezoid:
    """
    Bug: compute_intensity_map's "Integral" metric called np.trapz
    directly (no fallback shim), so it crashed with AttributeError on
    NumPy 2.5.3 the moment anyone chose Integral in the 2D Map tool —
    confirmed by running the real app. Fixed via the same
    `getattr(np, 'trapezoid', None) or np.trapz` shim already used
    elsewhere in the codebase.

    Each spectrum here is a flat line (constant y) over x = [0, 1, 2, 3],
    so the trapezoidal integral has an exact, hand-checkable answer:
    constant_value * (x_max - x_min).
    """

    def test_integral_metric_matches_hand_computed_area(self):
        x = np.array([0.0, 1.0, 2.0, 3.0])
        constants = [2.0, 5.0, 10.0, 1.0]
        spectra = [
            {'label': f'flat{i}', 'x_scale': x, 'y_scale': np.full(4, c)}
            for i, c in enumerate(constants)
        ]
        mgr = Map2DManager()
        result = mgr.compute_intensity_map(spectra, n_rows=2, n_cols=2, metric="Integral")
        assert result is not None
        expected = np.array(constants).reshape(2, 2) * 3.0  # width = 3 - 0
        np.testing.assert_allclose(result, expected)


class TestMap2DBaselineCorrectedIntegral:
    """Same bug/fix as above, second call site (_baseline_corrected_integral,
    used by the "Baseline-corrected integral" metric). A triangular bump
    sitting on a straight-line baseline between its endpoints has a known
    area once the baseline is subtracted, computed via the trapezoidal
    rule over the exact sample points (not a continuous-triangle formula,
    since the samples include flat zero segments either side of the rise).
    """

    def test_baseline_corrected_integral_removes_linear_background(self):
        x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        baseline = np.array([1.0, 2.0, 3.0, 4.0, 5.0])  # straight line, endpoints match y below
        bump = np.array([0.0, 0.0, 2.0, 0.0, 0.0])       # triangular bump of height 2 at x=2
        y = baseline + bump
        area = Map2DManager._baseline_corrected_integral(x, y)
        # Trapezoidal rule on [0, 0, 2, 0, 0] over x = [0,1,2,3,4]:
        # (1)*(0+0)/2 + (1)*(0+2)/2 + (1)*(2+0)/2 + (1)*(0+0)/2 = 0+1+1+0 = 2
        assert area == pytest.approx(2.0)


class TestNormalizationUnitAreaUsesTrapezoid:
    """
    Bug: _get_unit_area_factor (used by "Unit area" normalization) called
    np.trapz directly with no fallback, same removal as above. Checked
    against the same hand-computable flat-spectrum case.
    """

    def test_unit_area_factor_matches_hand_computed_area(self):
        x = np.array([0.0, 1.0, 2.0, 3.0])
        y = np.full(4, 5.0)
        mgr = NormalizationManager()
        factor = mgr._get_unit_area_factor(x, y)
        assert factor == pytest.approx(15.0)  # 5.0 * (3 - 0)

    def test_normalize_unit_area_divides_by_that_factor(self):
        x = np.array([0.0, 1.0, 2.0, 3.0])
        y = np.full(4, 5.0)
        mgr = NormalizationManager()
        normalized = mgr._normalize_unit_area(x, y)
        np.testing.assert_allclose(normalized, y / 15.0)
