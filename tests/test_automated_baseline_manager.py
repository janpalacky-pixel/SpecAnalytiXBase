# tests/test_automated_baseline_manager.py
#
# Tests for the Automated Baseline dialog's business logic
# (src/modules/data_analysis/automated_baseline_manager.py) — the ALS,
# airPLS, and arPLS baseline-fitting algorithms and their shared
# region-exclusion handling (user fitting ranges + invert mode).
#
# Before this file, NONE of AutomatedBaselineManager had any automated
# coverage at all (verified: `grep -rl "AutomatedBaselineManager" tests/`
# returned nothing before this file existed). ALS itself predates this
# session's work; it's covered here mainly as a regression check
# (unchanged behavior/contract across airPLS's and arPLS's additions),
# while airPLS and arPLS get the most thorough checks since they're the
# genuinely new logic.

import numpy as np
import pytest

from src.modules.data_analysis.automated_baseline_manager import AutomatedBaselineManager

# Region Shortcuts (e.g. the water-band preset) are a dialog-level
# concern now (see src/modules/data_analysis/baseline_region_presets.py
# and AutomatedBaselineDialog._on_preset_toggled) -- by the time settings
# reach AutomatedBaselineManager.apply_correction, a preset-added range
# is just another entry in params['fitting_ranges'], indistinguishable
# from a manually drawn one. There is nothing preset-specific left for
# this manager-level test file to cover.


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def _make_spectrum(label="s1", seed=0, n=600, x_lo=200.0, x_hi=3200.0,
                    noise=0.3):
    """
    A synthetic spectrum with a smooth, genuinely curving baseline plus a
    few sharp peaks and light noise — enough structure that "did the
    baseline follow the peaks up" and "did the baseline track the curve"
    are both meaningful, distinguishable checks.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(x_lo, x_hi, n)
    true_baseline = 20.0 + 0.01 * (x - x_lo)
    peaks = (
        120 * np.exp(-((x - 900) ** 2) / (2 * 8 ** 2))
        + 90 * np.exp(-((x - 1800) ** 2) / (2 * 10 ** 2))
    )
    y = true_baseline + peaks + rng.normal(0, noise, size=n)
    return {
        'label': label,
        'x_scale': x,
        'y_scale': y,
        'metadata': {},
    }, true_baseline


# ---------------------------------------------------------------------------
# calculate_als_baseline — regression coverage (behavior predates airPLS)
# ---------------------------------------------------------------------------

class TestALSBaseline:
    def test_recovers_smooth_baseline_under_peaks(self):
        spectrum, true_baseline = _make_spectrum(seed=1)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_als_baseline(
            spectrum['y_scale'], lam=1e6, p=0.01, niter=10)
        assert not np.isnan(baseline).any()
        rms = np.sqrt(np.mean((baseline - true_baseline) ** 2))
        assert rms < 2.0, f"ALS baseline strayed too far from the true baseline (RMS={rms:.3f})"
        # Should stay comfortably below the peak tops, not chase them up.
        assert np.max(baseline - true_baseline) < 5.0

    def test_exclude_indices_interpolates_through_excluded_region(self):
        spectrum, true_baseline = _make_spectrum(seed=2)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = (x >= 850) & (x <= 950)
        baseline = mgr.calculate_als_baseline(y, lam=1e6, p=0.01, niter=10, exclude_indices=exclude)
        assert not np.isnan(baseline).any()

    def test_full_exclusion_fails_gracefully(self):
        spectrum, _ = _make_spectrum(seed=3)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_als_baseline(y, lam=1e6, p=0.01, niter=10,
                                               exclude_indices=np.ones_like(x, dtype=bool))
        assert np.isnan(baseline).all()


# ---------------------------------------------------------------------------
# calculate_airpls_baseline — new coverage
# ---------------------------------------------------------------------------

class TestAirPLSBaseline:
    def test_recovers_smooth_baseline_under_peaks(self):
        spectrum, true_baseline = _make_spectrum(seed=1)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_airpls_baseline(
            spectrum['y_scale'], lam=200.0, porder=1, itermax=20)
        assert not np.isnan(baseline).any()
        rms = np.sqrt(np.mean((baseline - true_baseline) ** 2))
        assert rms < 2.0, f"airPLS baseline strayed too far from the true baseline (RMS={rms:.3f})"
        # Should stay comfortably below the peak tops, not chase them up.
        assert np.max(baseline - true_baseline) < 5.0

    def test_no_asymmetry_parameter_needed(self):
        # calculate_airpls_baseline's signature has no 'p' — this is
        # mostly a documentation-by-test that the call works without one.
        spectrum, _ = _make_spectrum(seed=4)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_airpls_baseline(spectrum['y_scale'], lam=200.0)
        assert not np.isnan(baseline).any()

    def test_exclude_indices_changes_the_fit(self):
        """Excluding a region should demonstrably change the fitted
        baseline there relative to not excluding it — otherwise the
        exclude_indices plumbing (weight-zeroing + post-hoc
        interpolation, mirroring calculate_als_baseline) isn't doing
        anything."""
        spectrum, _ = _make_spectrum(seed=5)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = (x >= 850) & (x <= 950)

        baseline_plain = mgr.calculate_airpls_baseline(y, lam=200.0, exclude_indices=None)
        baseline_excluded = mgr.calculate_airpls_baseline(y, lam=200.0, exclude_indices=exclude)
        assert not np.isnan(baseline_plain).any()
        assert not np.isnan(baseline_excluded).any()
        assert not np.allclose(baseline_plain[exclude], baseline_excluded[exclude])

    def test_full_exclusion_fails_gracefully(self):
        """Mirrors calculate_als_baseline's own contract: too few
        included points -> NaN array, not an exception. This is also the
        edge case most likely to trip up airPLS's own weight-update
        (d[neg].max() on a possibly-empty array) if the try/except
        wrapper around the loop were ever removed."""
        spectrum, _ = _make_spectrum(seed=6)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_airpls_baseline(y, lam=200.0,
                                                  exclude_indices=np.ones_like(x, dtype=bool))
        assert np.isnan(baseline).all()

    def test_single_included_point_fails_gracefully(self):
        spectrum, _ = _make_spectrum(seed=7)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = np.ones_like(x, dtype=bool)
        exclude[0] = False  # exactly one point left -- still "not enough"
        baseline = mgr.calculate_airpls_baseline(y, lam=200.0, exclude_indices=exclude)
        assert np.isnan(baseline).all()


# ---------------------------------------------------------------------------
# calculate_arpls_baseline — new coverage
# ---------------------------------------------------------------------------

class TestArPLSBaseline:
    def test_recovers_smooth_baseline_under_peaks(self):
        spectrum, true_baseline = _make_spectrum(seed=1)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_arpls_baseline(spectrum['y_scale'], lam=1e5, itermax=50, ratio=0.05)
        assert not np.isnan(baseline).any()
        rms = np.sqrt(np.mean((baseline - true_baseline) ** 2))
        assert rms < 2.0, f"arPLS baseline strayed too far from the true baseline (RMS={rms:.3f})"
        assert np.max(baseline - true_baseline) < 5.0

    def test_no_asymmetry_parameter_needed(self):
        # calculate_arpls_baseline's signature has no 'p', same as
        # calculate_airpls_baseline -- documentation-by-test.
        spectrum, _ = _make_spectrum(seed=4)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_arpls_baseline(spectrum['y_scale'], lam=1e5)
        assert not np.isnan(baseline).any()

    def test_exclude_indices_changes_the_fit(self):
        """Same reasoning as TestAirPLSBaseline's own version of this
        check: excluding a region should demonstrably change the fitted
        baseline there, otherwise the exclude_indices plumbing isn't
        doing anything."""
        spectrum, _ = _make_spectrum(seed=5)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = (x >= 850) & (x <= 950)

        baseline_plain = mgr.calculate_arpls_baseline(y, lam=1e5, exclude_indices=None)
        baseline_excluded = mgr.calculate_arpls_baseline(y, lam=1e5, exclude_indices=exclude)
        assert not np.isnan(baseline_plain).any()
        assert not np.isnan(baseline_excluded).any()
        assert not np.allclose(baseline_plain[exclude], baseline_excluded[exclude])

    def test_full_exclusion_fails_gracefully(self):
        """Mirrors calculate_als_baseline/calculate_airpls_baseline's own
        contract: too few included points -> NaN array, not an
        exception."""
        spectrum, _ = _make_spectrum(seed=6)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_arpls_baseline(y, lam=1e5,
                                                 exclude_indices=np.ones_like(x, dtype=bool))
        assert np.isnan(baseline).all()

    def test_single_included_point_fails_gracefully(self):
        spectrum, _ = _make_spectrum(seed=7)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = np.ones_like(x, dtype=bool)
        exclude[0] = False  # exactly one point left -- still "not enough"
        baseline = mgr.calculate_arpls_baseline(y, lam=1e5, exclude_indices=exclude)
        assert np.isnan(baseline).all()

    def test_converges_without_warnings(self):
        """Regression check for the exp() overflow that used to print a
        RuntimeWarning under a tall peak's large negative residual --
        see the exponent clipping in calculate_arpls_baseline."""
        import warnings
        spectrum, _ = _make_spectrum(seed=13, noise=0.1)
        mgr = AutomatedBaselineManager()
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            baseline = mgr.calculate_arpls_baseline(spectrum['y_scale'], lam=1e5)
        assert not np.isnan(baseline).any()


# ---------------------------------------------------------------------------
# apply_correction — algorithm dispatch, water band, metadata contract
# ---------------------------------------------------------------------------

class TestApplyCorrectionDispatch:
    def test_default_algorithm_is_als(self):
        spectrum, _ = _make_spectrum(seed=8)
        mgr = AutomatedBaselineManager()
        out = mgr.apply_correction([spectrum], {'lambda': 1e6, 'p': 0.01, 'n_iter': 10})
        entry = out[0]['metadata']['correction_history'][-1]
        assert entry['algorithm'] == 'ALS'
        assert entry['success'] is True
        assert 'p' in entry

    def test_airpls_dispatch_and_metadata(self):
        spectrum, _ = _make_spectrum(seed=9)
        mgr = AutomatedBaselineManager()
        out = mgr.apply_correction([spectrum], {'algorithm': 'airpls', 'lambda': 200.0, 'n_iter': 20})
        entry = out[0]['metadata']['correction_history'][-1]
        assert entry['algorithm'] == 'airPLS'
        assert entry['success'] is True
        # 'p' (asymmetry) is ALS-only -- an airPLS entry shouldn't carry
        # a meaningless value for a parameter the algorithm doesn't have.
        assert 'p' not in entry
        assert mgr.failed_labels == []

    def test_arpls_dispatch_and_metadata(self):
        spectrum, _ = _make_spectrum(seed=11)
        mgr = AutomatedBaselineManager()
        out = mgr.apply_correction([spectrum], {'algorithm': 'arpls', 'lambda': 1e5, 'n_iter': 50})
        entry = out[0]['metadata']['correction_history'][-1]
        assert entry['algorithm'] == 'arPLS'
        assert entry['success'] is True
        # 'p' (asymmetry) is ALS-only, same as airPLS.
        assert 'p' not in entry
        assert mgr.failed_labels == []

    def test_als_and_airpls_produce_different_results(self):
        """Sanity check that algorithm selection actually reaches the
        computation, not just the metadata label."""
        spectrum, _ = _make_spectrum(seed=10)
        mgr = AutomatedBaselineManager()
        out_als = mgr.apply_correction([dict(spectrum)], {'algorithm': 'als', 'lambda': 1e6, 'p': 0.01, 'n_iter': 10})
        out_airpls = mgr.apply_correction([dict(spectrum)], {'algorithm': 'airpls', 'lambda': 200.0, 'n_iter': 20})
        out_arpls = mgr.apply_correction([dict(spectrum)], {'algorithm': 'arpls', 'lambda': 1e5, 'n_iter': 50})
        assert not np.allclose(out_als[0]['y_scale'], out_airpls[0]['y_scale'])
        assert not np.allclose(out_als[0]['y_scale'], out_arpls[0]['y_scale'])
        assert not np.allclose(out_airpls[0]['y_scale'], out_arpls[0]['y_scale'])

    def test_failed_fit_leaves_spectrum_unchanged_and_records_label(self):
        spectrum, _ = _make_spectrum(seed=12)
        x = spectrum['x_scale']
        mgr = AutomatedBaselineManager()
        out = mgr.apply_correction(
            [dict(spectrum)],
            {'algorithm': 'airpls', 'lambda': 200.0, 'n_iter': 20,
             # Exclude everything via an absurd fitting range covering the whole axis.
             'fitting_ranges': [[x.min() - 1, x.max() + 1]], 'invert_regions': False},
        )
        assert mgr.failed_labels == [spectrum['label']]
        entry = out[0]['metadata']['correction_history'][-1]
        assert entry['success'] is False
        np.testing.assert_array_equal(out[0]['y_scale'], spectrum['y_scale'])


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
