"""Melting Curve Analysis never gives the maths library a straight-line fit
that turns into NaN (empty values) inside it.

Found because the full test suite hung on Windows: with two spectra, the
Low-T window held one point at x = 0. np.polyfit of a line through it gives
NaN to LAPACK ("On entry to DLASCL parameter number 4 had an illegal
value"); on Linux that is an error the program caught, on the Windows build
of the library the call never returned. Now such a window is recognised
before the fit and reported like any other unusable baseline window."""
import numpy as np
import pytest

from src.modules.visualization_analysis import melting_curve_manager as mcm


@pytest.fixture
def no_undefined_polyfit(monkeypatch):
    """np.polyfit may never be given input that turns into NaN inside it."""
    real = np.polyfit

    def checked(x, y, deg, *a, **k):
        x = np.asarray(x, float)
        assert np.all(np.isfinite(x)) and np.all(np.isfinite(np.asarray(y, float)))
        assert not (deg >= 1 and np.all(x == 0)), f"line through points all at x = 0: {x}"
        return real(x, y, deg, *a, **k)
    monkeypatch.setattr(np, 'polyfit', checked)


@pytest.mark.parametrize('x, y, low, high', [
    ([0.0, 1.0], [1.0, 2.0], (0, 0), (1, 1)),               # one point per window, at x = 0
    ([0.0, 0.0, 5.0, 6.0], [1, 2, 3, 4], (0, 0), (5, 6)),     # two points, both at x = 0
    ([0.0, 1.0, 5.0, 6.0], [1, np.nan, 3, 4], (0, 1), (5, 6)),  # a missing value
])
def test_baseline_window_without_a_defined_line_gives_no_fit_and_a_message(
        no_undefined_polyfit, x, y, low, high):
    m = mcm.MeltingCurveManager()
    assert m.normalize_melting_curve(x, y, low, high, order=1) is None
    assert 'too degenerate' in m.last_normalization_error


def test_ordinary_baseline_windows_are_fitted_as_before(no_undefined_polyfit):
    # one point per window away from 0 is fitted as before (see
    # test_melting_curve_normalize_baseline_failure.py)
    assert mcm.MeltingCurveManager().normalize_melting_curve(
        [5.0, 10.0, 15.0], [0.1, 0.5, 0.9], (5, 7), (13, 15), order=1) is not None
    x = np.linspace(20, 90, 36)
    y = 1 + 0.002 * x + 0.5 / (1 + np.exp(-(x - 55) / 3))
    m = mcm.MeltingCurveManager()
    res = m.normalize_melting_curve(x, y, (20, 35), (75, 90), order=1)
    assert res is not None and m.last_normalization_error is None
    assert res['y_norm'][0] == pytest.approx(0, abs=0.02) and res['y_norm'][-1] == pytest.approx(1, abs=0.02)
    # a constant (order 0) baseline needs only one point per window
    assert m.normalize_melting_curve([0.0, 1.0], [1.0, 2.0], (0, 0), (1, 1), order=0) is not None


def test_vant_hoff_line_through_points_all_at_zero_is_none(no_undefined_polyfit):
    m = mcm.MeltingCurveManager()
    assert m.compute_thermodynamic_params(np.zeros(3), np.array([1.0, 2.0, 3.0])) is None
    assert m.compute_thermodynamic_params(np.array([0.0030, 0.0031, 0.0032]),
                                          np.array([1.0, 0.0, -1.0])) is not None


def test_fit_starting_guesses_survive_temperatures_at_zero(no_undefined_polyfit):
    x = np.array([0.0, 0.0, 0.0, 50, 55, 60, 90, 90, 90])
    y = np.array([0.0, 0.0, 0.0, 0.3, 0.5, 0.7, 1, 1, 1])
    m = mcm.MeltingCurveManager()
    m.fit_two_state_curve(x, y, baseline_fraction=0.3)          # must not raise
    m.fit_multi_state_curve(x, y, 1, baseline_fraction=0.3)
