"""Regression tests for a real crash: opening Melting Curve Analysis on
non-physical data (the user's own reproduction: selecting two spectra that
were themselves previously EXPORTED from this same tool -- "melting_curve_
normalized" and "melting_curve_raw" -- and feeding them back in as source
spectra) made the baseline-region least-squares fit inside
MeltingCurveManager.normalize_melting_curve unsolvable, raising an unhandled
numpy.linalg.LinAlgError: "SVD did not converge in Linear Least Squares" all
the way up through dialog construction. In the GUI this showed as "nothing
happens" (the dialog silently failed to open) with the traceback only in the
console/log -- the user asked for this to be handled with a warning instead.

Fixed in two places:
1. MeltingCurveManager.normalize_melting_curve now catches
   (np.linalg.LinAlgError, ValueError) around the two np.polyfit() calls and
   returns None -- extending the existing "return None, can't normalize"
   convention already used for the empty-baseline-mask case -- while
   recording a specific, human-readable explanation in
   self.last_normalization_error for the caller to show.
2. MeltingCurveDialog.perform_normalization() already showed a QMessageBox
   warning for a None result, but only when not silent, and
   _finalize_curve() used to hardcode silent=True for its own normalization
   recompute regardless of whether the surrounding extraction itself was
   silent -- so even a genuine, non-transient failure on a real ("loud")
   extraction never reached the user. That hardcoded True is now
   silent=silent, passing the caller's own intent through, while every
   live baseline-slider drag (which independently calls
   _run_current_normalization(silent=True) and is unrelated to this fix)
   stays quiet as before.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from src.modules.visualization_analysis.melting_curve_manager import MeltingCurveManager
from src.views.dialogs.visualization_analysis.melting_curve_dialog import MeltingCurveDialog

app = QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------- #
# MeltingCurveManager.normalize_melting_curve
# ---------------------------------------------------------------------- #

def test_baseline_fit_failure_returns_none_instead_of_raising(monkeypatch):
    manager = MeltingCurveManager()

    def _raise(*args, **kwargs):
        raise np.linalg.LinAlgError("SVD did not converge in Linear Least Squares")

    monkeypatch.setattr(np, "polyfit", _raise)

    result = manager.normalize_melting_curve(
        x=np.array([5.0, 10.0, 15.0]), y=np.array([0.1, 0.5, 0.9]),
        low_range=(5.0, 7.0), high_range=(13.0, 15.0), order=1)

    assert result is None
    assert manager.last_normalization_error  # a non-empty explanation
    assert "baseline" in manager.last_normalization_error.lower()


def test_empty_baseline_mask_still_returns_none_without_a_fit_error(monkeypatch):
    """The pre-existing "no points fall inside either baseline region" case
    is unrelated to the new try/except -- it returns None before ever
    reaching polyfit, and must keep doing so without last_normalization_error
    being set (perform_normalization falls back to its own generic wording
    for that case)."""
    manager = MeltingCurveManager()

    result = manager.normalize_melting_curve(
        x=np.array([5.0, 10.0, 15.0]), y=np.array([0.1, 0.5, 0.9]),
        low_range=(100.0, 110.0), high_range=(120.0, 130.0), order=1)

    assert result is None
    assert manager.last_normalization_error is None


def test_successful_fit_clears_a_previous_failure(monkeypatch):
    """last_normalization_error must not linger from an earlier failed call
    once a later call on the same manager instance succeeds -- otherwise a
    stale message could be shown for an unrelated, currently-successful
    normalization."""
    manager = MeltingCurveManager()
    manager.last_normalization_error = "stale message from a previous failure"

    result = manager.normalize_melting_curve(
        x=np.array([5.0, 10.0, 15.0]), y=np.array([0.1, 0.5, 0.9]),
        low_range=(5.0, 7.0), high_range=(13.0, 15.0), order=1)

    assert result is not None
    assert manager.last_normalization_error is None


# ---------------------------------------------------------------------- #
# MeltingCurveDialog.perform_normalization -- exercised directly on a bare
# object (no real QDialog construction, which needs a fully populated
# spectra selection and matplotlib canvas) since perform_normalization is
# an ordinary method that only touches attributes set on self.
# ---------------------------------------------------------------------- #

class _FakeSpin:
    def __init__(self, val):
        self._val = val

    def value(self):
        return self._val


class _FakeCombo:
    def __init__(self, index):
        self._index = index

    def currentIndex(self):
        return self._index


def _fake_dialog_self(manager):
    fake = MagicMock()
    fake.manager = manager
    fake.curve = {'x_temperature': np.array([5.0, 10.0, 15.0]),
                  'y_raw': np.array([0.1, 0.5, 0.9])}
    fake.norm_combo = _FakeCombo(2)  # "First order (linear)"
    fake.low_min_spin = _FakeSpin(5.0)
    fake.low_max_spin = _FakeSpin(7.0)
    fake.high_min_spin = _FakeSpin(13.0)
    fake.high_max_spin = _FakeSpin(15.0)
    fake.normalization_result = None
    fake.x_trans = None
    return fake


def test_perform_normalization_warns_with_managers_specific_message(monkeypatch):
    manager = MeltingCurveManager()

    def _raise(*args, **kwargs):
        raise np.linalg.LinAlgError("SVD did not converge in Linear Least Squares")

    monkeypatch.setattr(np, "polyfit", _raise)

    warnings = []
    monkeypatch.setattr(
        "src.views.dialogs.visualization_analysis.melting_curve_dialog.QMessageBox.warning",
        lambda parent, title, text: warnings.append((title, text)))

    fake = _fake_dialog_self(manager)
    MeltingCurveDialog.perform_normalization(fake, silent=False)

    assert len(warnings) == 1
    title, text = warnings[0]
    assert title == "Normalization Failed"
    assert text == manager.last_normalization_error
    assert "degenerate" in text.lower()


def test_perform_normalization_stays_silent_when_asked(monkeypatch):
    """Live baseline-slider dragging calls this with silent=True and must
    not pop a warning on every frame, even for a genuine fit failure --
    unchanged by this fix."""
    manager = MeltingCurveManager()

    def _raise(*args, **kwargs):
        raise np.linalg.LinAlgError("SVD did not converge in Linear Least Squares")

    monkeypatch.setattr(np, "polyfit", _raise)

    warnings = []
    monkeypatch.setattr(
        "src.views.dialogs.visualization_analysis.melting_curve_dialog.QMessageBox.warning",
        lambda parent, title, text: warnings.append((title, text)))

    fake = _fake_dialog_self(manager)
    MeltingCurveDialog.perform_normalization(fake, silent=True)

    assert warnings == []
