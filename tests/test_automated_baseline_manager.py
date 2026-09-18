# tests/test_automated_baseline_manager.py
#
# Tests for the Automated Baseline dialog's business logic
# (src/modules/data_analysis/automated_baseline_manager.py) — the ALS,
# airPLS, arPLS, iarPLS, asPLS, drPLS, psalsa, I-ModPoly,
# Morphological Opening, and mpls baseline-fitting algorithms and their
# shared region-exclusion handling (user fitting ranges + invert mode).
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


class TestIarPLSBaseline:
    def test_recovers_smooth_baseline_under_peaks(self):
        spectrum, true_baseline = _make_spectrum(seed=16)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_iarpls_baseline(spectrum['y_scale'], lam=1e5, itermax=100, ratio=0.001)
        assert not np.isnan(baseline).any()
        rms = np.sqrt(np.mean((baseline - true_baseline) ** 2))
        assert rms < 2.0, f"iarPLS baseline strayed too far from the true baseline (RMS={rms:.3f})"
        assert np.max(baseline - true_baseline) < 5.0

    def test_no_asymmetry_parameter_needed(self):
        # calculate_iarpls_baseline's signature has no 'p', same as
        # calculate_arpls_baseline/calculate_airpls_baseline --
        # documentation-by-test.
        spectrum, _ = _make_spectrum(seed=17)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_iarpls_baseline(spectrum['y_scale'], lam=1e5)
        assert not np.isnan(baseline).any()

    def test_exclude_indices_changes_the_fit(self):
        """Same reasoning as TestArPLSBaseline's own version of this
        check: excluding a region should demonstrably change the fitted
        baseline there, otherwise the exclude_indices plumbing isn't
        doing anything."""
        spectrum, _ = _make_spectrum(seed=18)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = (x >= 850) & (x <= 950)

        baseline_plain = mgr.calculate_iarpls_baseline(y, lam=1e5, exclude_indices=None)
        baseline_excluded = mgr.calculate_iarpls_baseline(y, lam=1e5, exclude_indices=exclude)
        assert not np.isnan(baseline_plain).any()
        assert not np.isnan(baseline_excluded).any()
        assert not np.allclose(baseline_plain[exclude], baseline_excluded[exclude])

    def test_full_exclusion_fails_gracefully(self):
        """Mirrors calculate_arpls_baseline's own contract: too few
        included points -> NaN array, not an exception."""
        spectrum, _ = _make_spectrum(seed=19)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_iarpls_baseline(y, lam=1e5,
                                                  exclude_indices=np.ones_like(x, dtype=bool))
        assert np.isnan(baseline).all()

    def test_single_included_point_fails_gracefully(self):
        spectrum, _ = _make_spectrum(seed=20)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = np.ones_like(x, dtype=bool)
        exclude[0] = False  # exactly one point left -- still "not enough"
        baseline = mgr.calculate_iarpls_baseline(y, lam=1e5, exclude_indices=exclude)
        assert np.isnan(baseline).all()

    def test_converges_without_warnings(self):
        """iarPLS's weight update is a self-normalizing ISRU-style curve
        (x / sqrt(1 + x**2)) rather than arPLS's raw exp(), specifically
        so it can't overflow the way arPLS's exponent needed explicit
        clipping for -- this is the regression check for that."""
        import warnings
        spectrum, _ = _make_spectrum(seed=21, noise=0.1)
        mgr = AutomatedBaselineManager()
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            baseline = mgr.calculate_iarpls_baseline(spectrum['y_scale'], lam=1e5)
        assert not np.isnan(baseline).any()


class TestAsPLSBaseline:
    def test_recovers_smooth_baseline_under_peaks(self):
        spectrum, true_baseline = _make_spectrum(seed=30)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_aspls_baseline(spectrum['y_scale'], lam=1e6, itermax=100, ratio=0.001)
        assert not np.isnan(baseline).any()
        rms = np.sqrt(np.mean((baseline - true_baseline) ** 2))
        assert rms < 2.0, f"asPLS baseline strayed too far from the true baseline (RMS={rms:.3f})"
        assert np.max(baseline - true_baseline) < 5.0

    def test_no_asymmetry_parameter_needed(self):
        # calculate_aspls_baseline's signature has no 'p', same as
        # calculate_arpls_baseline/calculate_iarpls_baseline --
        # documentation-by-test.
        spectrum, _ = _make_spectrum(seed=31)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_aspls_baseline(spectrum['y_scale'], lam=1e6)
        assert not np.isnan(baseline).any()

    def test_exclude_indices_changes_the_fit(self):
        spectrum, _ = _make_spectrum(seed=32)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = (x >= 850) & (x <= 950)

        baseline_plain = mgr.calculate_aspls_baseline(y, lam=1e6, exclude_indices=None)
        baseline_excluded = mgr.calculate_aspls_baseline(y, lam=1e6, exclude_indices=exclude)
        assert not np.isnan(baseline_plain).any()
        assert not np.isnan(baseline_excluded).any()
        assert not np.allclose(baseline_plain[exclude], baseline_excluded[exclude])

    def test_full_exclusion_fails_gracefully(self):
        spectrum, _ = _make_spectrum(seed=33)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_aspls_baseline(y, lam=1e6,
                                                 exclude_indices=np.ones_like(x, dtype=bool))
        assert np.isnan(baseline).all()

    def test_single_included_point_fails_gracefully(self):
        spectrum, _ = _make_spectrum(seed=34)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = np.ones_like(x, dtype=bool)
        exclude[0] = False  # exactly one point left -- still "not enough"
        baseline = mgr.calculate_aspls_baseline(y, lam=1e6, exclude_indices=exclude)
        assert np.isnan(baseline).all()

    def test_converges_without_warnings(self):
        """Regression check for the same class of exp() overflow arPLS
        needed clipping for -- calculate_aspls_baseline's weighting also
        exponentiates an unbounded residual, so it needs the same
        exponent clipping under a tall peak's large residual."""
        import warnings
        spectrum, _ = _make_spectrum(seed=35, noise=0.1)
        mgr = AutomatedBaselineManager()
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            baseline = mgr.calculate_aspls_baseline(spectrum['y_scale'], lam=1e6)
        assert not np.isnan(baseline).any()

    def test_flat_input_does_not_fail(self):
        """Exercises the max(|residual|) == 0 guard in
        calculate_aspls_baseline's alpha update -- a perfectly flat
        spectrum fits (almost) exactly on the first pass, leaving
        nothing for alpha to adapt to."""
        mgr = AutomatedBaselineManager()
        flat = np.full(100, 5.0)
        baseline = mgr.calculate_aspls_baseline(flat, lam=1e6)
        assert not np.isnan(baseline).any()
        assert np.allclose(baseline, 5.0, atol=0.5)


class TestDrPLSBaseline:
    def test_recovers_smooth_baseline_under_peaks(self):
        spectrum, true_baseline = _make_spectrum(seed=37)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_drpls_baseline(spectrum['y_scale'], lam=1e5, eta=0.5, itermax=50, ratio=0.001)
        assert not np.isnan(baseline).any()
        rms = np.sqrt(np.mean((baseline - true_baseline) ** 2))
        assert rms < 2.0, f"drPLS baseline strayed too far from the true baseline (RMS={rms:.3f})"
        assert np.max(baseline - true_baseline) < 5.0

    def test_no_asymmetry_parameter_needed(self):
        # calculate_drpls_baseline's signature has no 'p', same as
        # calculate_arpls_baseline/calculate_iarpls_baseline/
        # calculate_aspls_baseline -- documentation-by-test.
        spectrum, _ = _make_spectrum(seed=38)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_drpls_baseline(spectrum['y_scale'], lam=1e5)
        assert not np.isnan(baseline).any()

    def test_eta_actually_changes_the_fit(self):
        """drPLS's own second tunable parameter -- documentation-by-test
        that it's actually wired into the linear system, not just
        accepted and ignored."""
        spectrum, _ = _make_spectrum(seed=39)
        mgr = AutomatedBaselineManager()
        baseline_low_eta = mgr.calculate_drpls_baseline(spectrum['y_scale'], lam=1e5, eta=0.1)
        baseline_high_eta = mgr.calculate_drpls_baseline(spectrum['y_scale'], lam=1e5, eta=0.9)
        assert not np.isnan(baseline_low_eta).any()
        assert not np.isnan(baseline_high_eta).any()
        assert not np.allclose(baseline_low_eta, baseline_high_eta)

    def test_exclude_indices_changes_the_fit(self):
        spectrum, _ = _make_spectrum(seed=40)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = (x >= 850) & (x <= 950)

        baseline_plain = mgr.calculate_drpls_baseline(y, lam=1e5, exclude_indices=None)
        baseline_excluded = mgr.calculate_drpls_baseline(y, lam=1e5, exclude_indices=exclude)
        assert not np.isnan(baseline_plain).any()
        assert not np.isnan(baseline_excluded).any()
        assert not np.allclose(baseline_plain[exclude], baseline_excluded[exclude])

    def test_full_exclusion_fails_gracefully(self):
        spectrum, _ = _make_spectrum(seed=41)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_drpls_baseline(y, lam=1e5,
                                                 exclude_indices=np.ones_like(x, dtype=bool))
        assert np.isnan(baseline).all()

    def test_single_included_point_fails_gracefully(self):
        spectrum, _ = _make_spectrum(seed=42)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = np.ones_like(x, dtype=bool)
        exclude[0] = False  # exactly one point left -- still "not enough"
        baseline = mgr.calculate_drpls_baseline(y, lam=1e5, exclude_indices=exclude)
        assert np.isnan(baseline).all()

    def test_converges_without_warnings(self):
        """drPLS's weighting is a softsign curve (x/(1+|x|)), the same
        self-normalizing family as iarPLS's ISRU -- this is the
        regression check that it never needs the exponent clipping
        calculate_arpls_baseline's raw exp() weighting does."""
        import warnings
        spectrum, _ = _make_spectrum(seed=43, noise=0.1)
        mgr = AutomatedBaselineManager()
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            baseline = mgr.calculate_drpls_baseline(spectrum['y_scale'], lam=1e5)
        assert not np.isnan(baseline).any()

    def test_flat_input_does_not_fail(self):
        mgr = AutomatedBaselineManager()
        flat = np.full(100, 5.0)
        baseline = mgr.calculate_drpls_baseline(flat, lam=1e5)
        assert not np.isnan(baseline).any()
        assert np.allclose(baseline, 5.0, atol=0.5)


class TestPsalsaBaseline:
    def test_recovers_smooth_baseline_under_peaks(self):
        spectrum, true_baseline = _make_spectrum(seed=23)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_psalsa_baseline(spectrum['y_scale'], lam=1e6, p=0.5, itermax=50, ratio=0.001)
        assert not np.isnan(baseline).any()
        rms = np.sqrt(np.mean((baseline - true_baseline) ** 2))
        assert rms < 2.0, f"psalsa baseline strayed too far from the true baseline (RMS={rms:.3f})"
        assert np.max(baseline - true_baseline) < 5.0

    def test_p_actually_changes_the_fit(self):
        """Unlike arPLS/iarPLS (no asymmetry parameter at all), psalsa
        keeps ALS's p -- documentation-by-test that it's actually wired
        into the weight formula, not just accepted and ignored."""
        spectrum, _ = _make_spectrum(seed=24)
        mgr = AutomatedBaselineManager()
        baseline_low_p = mgr.calculate_psalsa_baseline(spectrum['y_scale'], lam=1e6, p=0.1)
        baseline_high_p = mgr.calculate_psalsa_baseline(spectrum['y_scale'], lam=1e6, p=0.9)
        assert not np.isnan(baseline_low_p).any()
        assert not np.isnan(baseline_high_p).any()
        assert not np.allclose(baseline_low_p, baseline_high_p)

    def test_exclude_indices_changes_the_fit(self):
        spectrum, _ = _make_spectrum(seed=25)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = (x >= 850) & (x <= 950)

        baseline_plain = mgr.calculate_psalsa_baseline(y, lam=1e6, exclude_indices=None)
        baseline_excluded = mgr.calculate_psalsa_baseline(y, lam=1e6, exclude_indices=exclude)
        assert not np.isnan(baseline_plain).any()
        assert not np.isnan(baseline_excluded).any()
        assert not np.allclose(baseline_plain[exclude], baseline_excluded[exclude])

    def test_full_exclusion_fails_gracefully(self):
        spectrum, _ = _make_spectrum(seed=26)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_psalsa_baseline(y, lam=1e6,
                                                  exclude_indices=np.ones_like(x, dtype=bool))
        assert np.isnan(baseline).all()

    def test_single_included_point_fails_gracefully(self):
        spectrum, _ = _make_spectrum(seed=27)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = np.ones_like(x, dtype=bool)
        exclude[0] = False  # exactly one point left -- still "not enough"
        baseline = mgr.calculate_psalsa_baseline(y, lam=1e6, exclude_indices=exclude)
        assert np.isnan(baseline).all()

    def test_converges_without_warnings(self):
        """Regression check for the same class of exp() overflow arPLS
        needed clipping for -- psalsa only ever exponentiates a
        *positive* residual through a negative exponent (exp(-x) for
        x >= 0), which can underflow to 0 but never overflow, so this
        should never warn even on noisy data."""
        import warnings
        spectrum, _ = _make_spectrum(seed=28, noise=0.1)
        mgr = AutomatedBaselineManager()
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            baseline = mgr.calculate_psalsa_baseline(spectrum['y_scale'], lam=1e6)
        assert not np.isnan(baseline).any()

    def test_flat_input_does_not_fail(self):
        """k defaults to std(y)/10, which is exactly 0 for a perfectly
        flat spectrum -- exercises the k==0 fallback in
        calculate_psalsa_baseline rather than dividing by zero."""
        mgr = AutomatedBaselineManager()
        flat = np.full(100, 5.0)
        baseline = mgr.calculate_psalsa_baseline(flat, lam=1e6)
        assert not np.isnan(baseline).any()
        assert np.allclose(baseline, 5.0, atol=0.5)


class TestIModPolyBaseline:
    def test_recovers_smooth_baseline_under_peaks(self):
        spectrum, true_baseline = _make_spectrum(seed=1)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_imodpoly_baseline(
            spectrum['x_scale'], spectrum['y_scale'], poly_order=3, itermax=100)
        assert not np.isnan(baseline).any()
        rms = np.sqrt(np.mean((baseline - true_baseline) ** 2))
        assert rms < 2.0, f"I-ModPoly baseline strayed too far from the true baseline (RMS={rms:.3f})"
        assert np.max(baseline - true_baseline) < 5.0

    def test_exclude_indices_changes_the_fit(self):
        spectrum, _ = _make_spectrum(seed=5)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = (x >= 850) & (x <= 950)

        baseline_plain = mgr.calculate_imodpoly_baseline(x, y, poly_order=3, exclude_indices=None)
        baseline_excluded = mgr.calculate_imodpoly_baseline(x, y, poly_order=3, exclude_indices=exclude)
        assert not np.isnan(baseline_plain).any()
        assert not np.isnan(baseline_excluded).any()
        assert not np.allclose(baseline_plain, baseline_excluded)

    def test_full_exclusion_fails_gracefully(self):
        """Mirrors the Whittaker-family methods' own contract: too few
        included points -> NaN array, not an exception."""
        spectrum, _ = _make_spectrum(seed=6)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_imodpoly_baseline(
            x, y, poly_order=3, exclude_indices=np.ones_like(x, dtype=bool))
        assert np.isnan(baseline).all()

    def test_too_few_points_for_order_fails_gracefully(self):
        """A degree-n polynomial needs at least n+1 points -- leaving
        fewer than that included should fail gracefully (NaN), same
        contract as full exclusion, rather than raising out of
        np.polyfit."""
        spectrum, _ = _make_spectrum(seed=7)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = np.ones_like(x, dtype=bool)
        exclude[:3] = False  # only 3 points left -- order 5 needs 6
        baseline = mgr.calculate_imodpoly_baseline(x, y, poly_order=5, exclude_indices=exclude)
        assert np.isnan(baseline).all()

    def test_converges_without_warnings(self):
        """Regression check for np.polyfit's RankWarning on raw,
        unrescaled cm-1-scale wavenumbers at higher polynomial orders --
        see the zero-mean/unit-variance x rescale in
        calculate_imodpoly_baseline."""
        import warnings
        spectrum, _ = _make_spectrum(seed=13, noise=0.1)
        mgr = AutomatedBaselineManager()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            baseline = mgr.calculate_imodpoly_baseline(
                spectrum['x_scale'], spectrum['y_scale'], poly_order=6, itermax=100)
        assert not np.isnan(baseline).any()


class TestMorphologicalBaseline:
    def test_stays_at_or_below_true_baseline(self):
        """Morphological opening is an order-statistics (min-based)
        method -- unlike the fitted methods above, it's expected to sit
        AT OR BELOW the true background rather than average around it,
        so the check here is one-sided rather than a symmetric RMS
        bound."""
        spectrum, true_baseline = _make_spectrum(seed=1)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_morphological_baseline(spectrum['y_scale'], itermax=300)
        assert not np.isnan(baseline).any()
        # Should not overshoot the true background by more than noise.
        assert np.max(baseline - true_baseline) < 1.0
        # Should still track it reasonably closely, not collapse to a
        # flat line at the global minimum.
        rms = np.sqrt(np.mean((baseline - true_baseline) ** 2))
        assert rms < 10.0, f"Morphological baseline strayed too far below the true baseline (RMS={rms:.3f})"

    def test_no_tunable_parameters_needed(self):
        # calculate_morphological_baseline's signature has no lambda,
        # p, or poly_order -- documentation-by-test, same spirit as
        # TestAirPLSBaseline/TestArPLSBaseline's own version of this.
        spectrum, _ = _make_spectrum(seed=4)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_morphological_baseline(spectrum['y_scale'])
        assert not np.isnan(baseline).any()

    def test_exclude_indices_changes_the_fit(self):
        spectrum, _ = _make_spectrum(seed=5)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = (x >= 850) & (x <= 950)

        baseline_plain = mgr.calculate_morphological_baseline(y, exclude_indices=None)
        baseline_excluded = mgr.calculate_morphological_baseline(y, exclude_indices=exclude)
        assert not np.isnan(baseline_plain).any()
        assert not np.isnan(baseline_excluded).any()
        assert not np.allclose(baseline_plain, baseline_excluded)

    def test_full_exclusion_fails_gracefully(self):
        """Mirrors every other calculate_*_baseline method's contract:
        too few included points -> NaN array, not an exception."""
        spectrum, _ = _make_spectrum(seed=6)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_morphological_baseline(
            y, exclude_indices=np.ones_like(x, dtype=bool))
        assert np.isnan(baseline).all()

    def test_too_few_points_fails_gracefully(self):
        """The growth loop starts at a 3-point window -- fewer than 3
        included points should fail gracefully rather than error out of
        scipy.ndimage."""
        spectrum, _ = _make_spectrum(seed=7)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = np.ones_like(x, dtype=bool)
        exclude[:2] = False  # only 2 points left
        baseline = mgr.calculate_morphological_baseline(y, exclude_indices=exclude)
        assert np.isnan(baseline).all()

    def test_converges_without_warnings(self):
        """The adaptive structuring-element growth loop should converge
        (three consecutive exactly-equal openings) well within the
        default itermax for a realistic spectrum, without needing the
        safety fallback -- and without raising anything."""
        import warnings
        spectrum, _ = _make_spectrum(seed=13, noise=0.1)
        mgr = AutomatedBaselineManager()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            baseline = mgr.calculate_morphological_baseline(spectrum['y_scale'], itermax=300)
        assert not np.isnan(baseline).any()


class TestMplsBaseline:
    def test_recovers_smooth_baseline_under_peaks(self):
        spectrum, true_baseline = _make_spectrum(seed=30)
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_mpls_baseline(spectrum['y_scale'], lam=1e6, p=0.0)
        assert not np.isnan(baseline).any()
        rms = np.sqrt(np.mean((baseline - true_baseline) ** 2))
        assert rms < 5.0, f"mpls baseline strayed too far from the true baseline (RMS={rms:.3f})"

    def test_p_actually_changes_the_fit(self):
        """p is the weight given to every NON-anchor point (0.0 by
        default, i.e. ignored entirely) -- raising it should visibly
        change the fit, same documentation-by-test pattern used for
        ALS/psalsa's own p."""
        spectrum, _ = _make_spectrum(seed=31)
        mgr = AutomatedBaselineManager()
        baseline_p0 = mgr.calculate_mpls_baseline(spectrum['y_scale'], lam=1e6, p=0.0)
        baseline_p_high = mgr.calculate_mpls_baseline(spectrum['y_scale'], lam=1e6, p=0.5)
        assert not np.allclose(baseline_p0, baseline_p_high)

    def test_lambda_actually_changes_the_fit(self):
        spectrum, _ = _make_spectrum(seed=32)
        mgr = AutomatedBaselineManager()
        baseline_low = mgr.calculate_mpls_baseline(spectrum['y_scale'], lam=1e3, p=0.0)
        baseline_high = mgr.calculate_mpls_baseline(spectrum['y_scale'], lam=1e8, p=0.0)
        assert not np.allclose(baseline_low, baseline_high)

    def test_exclude_indices_changes_the_fit(self):
        spectrum, _ = _make_spectrum(seed=33)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = (x >= 850) & (x <= 950)
        baseline_plain = mgr.calculate_mpls_baseline(y, lam=1e6, p=0.0, exclude_indices=None)
        baseline_excluded = mgr.calculate_mpls_baseline(y, lam=1e6, p=0.0, exclude_indices=exclude)
        assert not np.isnan(baseline_plain).any()
        assert not np.isnan(baseline_excluded).any()
        assert not np.allclose(baseline_plain, baseline_excluded)

    def test_full_exclusion_fails_gracefully(self):
        spectrum, _ = _make_spectrum(seed=34)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        baseline = mgr.calculate_mpls_baseline(y, lam=1e6, p=0.0, exclude_indices=np.ones_like(x, dtype=bool))
        assert np.isnan(baseline).all()

    def test_too_few_points_fails_gracefully(self):
        """Same 3-point floor as calculate_morphological_baseline, since
        mpls's own window-growth loop starts there too."""
        spectrum, _ = _make_spectrum(seed=35)
        x, y = spectrum['x_scale'], spectrum['y_scale']
        mgr = AutomatedBaselineManager()
        exclude = np.ones_like(x, dtype=bool)
        exclude[:2] = False
        baseline = mgr.calculate_mpls_baseline(y, lam=1e6, p=0.0, exclude_indices=exclude)
        assert np.isnan(baseline).all()

    def test_flat_input_recovers_the_constant(self):
        """Edge case: a perfectly flat spectrum has no internal
        flat-region *boundaries* at all (morphology sees one giant flat
        run, not several), which would otherwise leave every point
        weighted at p (0.0 by default) and the Whittaker solve
        under-determined -- see the fallback in calculate_mpls_baseline.
        Without that fallback this collapses to a near-zero baseline
        instead of recovering the (correct) flat value."""
        mgr = AutomatedBaselineManager()
        flat = np.full(100, 5.0)
        baseline = mgr.calculate_mpls_baseline(flat, lam=1e6, p=0.0)
        assert not np.isnan(baseline).any()
        assert np.allclose(baseline, 5.0, atol=1e-6)

    def test_converges_without_warnings(self):
        import warnings
        spectrum, _ = _make_spectrum(seed=36, noise=0.1)
        mgr = AutomatedBaselineManager()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            baseline = mgr.calculate_mpls_baseline(spectrum['y_scale'], lam=1e6, p=0.0)
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

    def test_iarpls_dispatch_and_metadata(self):
        spectrum, _ = _make_spectrum(seed=22)
        mgr = AutomatedBaselineManager()
        out = mgr.apply_correction([spectrum], {'algorithm': 'iarpls', 'lambda': 1e5, 'n_iter': 100})
        entry = out[0]['metadata']['correction_history'][-1]
        assert entry['algorithm'] == 'iarPLS'
        assert entry['success'] is True
        # 'p' (asymmetry) is ALS-only, same as airPLS/arPLS.
        assert 'p' not in entry
        assert mgr.failed_labels == []

    def test_aspls_dispatch_and_metadata(self):
        spectrum, _ = _make_spectrum(seed=36)
        mgr = AutomatedBaselineManager()
        out = mgr.apply_correction([spectrum], {'algorithm': 'aspls', 'lambda': 1e6, 'n_iter': 100})
        entry = out[0]['metadata']['correction_history'][-1]
        assert entry['algorithm'] == 'asPLS'
        assert entry['success'] is True
        # 'p' (asymmetry) is ALS/psalsa-only -- asPLS has no such entry.
        assert 'p' not in entry
        assert mgr.failed_labels == []

    def test_drpls_dispatch_and_metadata(self):
        spectrum, _ = _make_spectrum(seed=44)
        mgr = AutomatedBaselineManager()
        out = mgr.apply_correction([spectrum], {'algorithm': 'drpls', 'lambda': 1e5, 'eta': 0.5, 'n_iter': 50})
        entry = out[0]['metadata']['correction_history'][-1]
        assert entry['algorithm'] == 'drPLS'
        assert entry['success'] is True
        assert entry['eta'] == 0.5
        # 'p' (asymmetry) is ALS/psalsa-only -- drPLS has no such entry.
        assert 'p' not in entry
        assert mgr.failed_labels == []

    def test_psalsa_dispatch_and_metadata(self):
        spectrum, _ = _make_spectrum(seed=29)
        mgr = AutomatedBaselineManager()
        out = mgr.apply_correction([spectrum], {'algorithm': 'psalsa', 'lambda': 1e6, 'p': 0.5, 'n_iter': 50})
        entry = out[0]['metadata']['correction_history'][-1]
        assert entry['algorithm'] == 'psalsa'
        assert entry['success'] is True
        # Unlike airPLS/arPLS/iarPLS, psalsa DOES use 'p' the way ALS does.
        assert entry['p'] == 0.5
        assert mgr.failed_labels == []

    def test_imodpoly_dispatch_and_metadata(self):
        spectrum, _ = _make_spectrum(seed=14)
        mgr = AutomatedBaselineManager()
        out = mgr.apply_correction([spectrum], {'algorithm': 'imodpoly', 'poly_order': 3, 'n_iter': 100})
        entry = out[0]['metadata']['correction_history'][-1]
        assert entry['algorithm'] == 'I-ModPoly'
        assert entry['success'] is True
        assert entry['poly_order'] == 3
        # Neither 'lambda' nor 'p' means anything for I-ModPoly.
        assert 'lambda' not in entry
        assert 'p' not in entry
        assert mgr.failed_labels == []

    def test_morphological_dispatch_and_metadata(self):
        spectrum, _ = _make_spectrum(seed=15)
        mgr = AutomatedBaselineManager()
        out = mgr.apply_correction([spectrum], {'algorithm': 'morphological', 'n_iter': 300})
        entry = out[0]['metadata']['correction_history'][-1]
        assert entry['algorithm'] == 'Morphological Opening'
        assert entry['success'] is True
        # Fully parameter-free -- none of lambda/p/poly_order apply.
        assert 'lambda' not in entry
        assert 'p' not in entry
        assert 'poly_order' not in entry
        assert mgr.failed_labels == []

    def test_mpls_dispatch_and_metadata(self):
        spectrum, _ = _make_spectrum(seed=45)
        mgr = AutomatedBaselineManager()
        out = mgr.apply_correction([spectrum], {'algorithm': 'mpls', 'lambda': 1e6, 'p': 0.0, 'n_iter': 300})
        entry = out[0]['metadata']['correction_history'][-1]
        assert entry['algorithm'] == 'mpls'
        assert entry['success'] is True
        # mpls DOES carry 'p', same as ALS/psalsa, just with a different
        # meaning and default (see calculate_mpls_baseline).
        assert entry['p'] == 0.0
        assert entry['lambda'] == 1e6
        # No 'eta' or 'poly_order' -- those are drPLS/I-ModPoly-only.
        assert 'eta' not in entry
        assert 'poly_order' not in entry
        assert mgr.failed_labels == []

    def test_als_and_airpls_produce_different_results(self):
        """Sanity check that algorithm selection actually reaches the
        computation, not just the metadata label."""
        spectrum, _ = _make_spectrum(seed=10)
        mgr = AutomatedBaselineManager()
        out_als = mgr.apply_correction([dict(spectrum)], {'algorithm': 'als', 'lambda': 1e6, 'p': 0.01, 'n_iter': 10})
        out_airpls = mgr.apply_correction([dict(spectrum)], {'algorithm': 'airpls', 'lambda': 200.0, 'n_iter': 20})
        out_arpls = mgr.apply_correction([dict(spectrum)], {'algorithm': 'arpls', 'lambda': 1e5, 'n_iter': 50})
        out_iarpls = mgr.apply_correction([dict(spectrum)], {'algorithm': 'iarpls', 'lambda': 1e5, 'n_iter': 100})
        out_aspls = mgr.apply_correction([dict(spectrum)], {'algorithm': 'aspls', 'lambda': 1e6, 'n_iter': 100})
        out_drpls = mgr.apply_correction([dict(spectrum)], {'algorithm': 'drpls', 'lambda': 1e5, 'eta': 0.5, 'n_iter': 50})
        out_psalsa = mgr.apply_correction([dict(spectrum)], {'algorithm': 'psalsa', 'lambda': 1e6, 'p': 0.5, 'n_iter': 50})
        out_imodpoly = mgr.apply_correction([dict(spectrum)], {'algorithm': 'imodpoly', 'poly_order': 3, 'n_iter': 100})
        out_morph = mgr.apply_correction([dict(spectrum)], {'algorithm': 'morphological', 'n_iter': 300})
        out_mpls = mgr.apply_correction([dict(spectrum)], {'algorithm': 'mpls', 'lambda': 1e6, 'p': 0.0, 'n_iter': 300})
        results = {
            'als': out_als[0]['y_scale'], 'airpls': out_airpls[0]['y_scale'],
            'arpls': out_arpls[0]['y_scale'], 'iarpls': out_iarpls[0]['y_scale'],
            'aspls': out_aspls[0]['y_scale'],
            'drpls': out_drpls[0]['y_scale'],
            'psalsa': out_psalsa[0]['y_scale'],
            'imodpoly': out_imodpoly[0]['y_scale'],
            'morphological': out_morph[0]['y_scale'],
            'mpls': out_mpls[0]['y_scale'],
        }
        names = list(results)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                assert not np.allclose(results[names[i]], results[names[j]]), \
                    f"{names[i]} and {names[j]} produced identical results"

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
