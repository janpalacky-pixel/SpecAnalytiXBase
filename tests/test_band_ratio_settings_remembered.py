"""Regression test for a real bug the user hit while GUI-testing: the Band
Ratio / Peak Area Calculator dialog never restored the Band A/B ranges,
metric, etc. that were last used for the same spectra selection, even
though BandRatioDialog itself has working get_settings()/_restore_settings()
methods and OperationsController.show_parameters_dialog's "Band Ratio"
branch does save the dialog's settings into self.last_op_settings after
every accepted run.

Root cause: that branch never updated self.last_selection_hash after
saving settings -- every OTHER operation in this same dispatch method
does (e.g. "Isosbestic Point Detection", "Resolution enhancement"), which
is what the "same selection -> restore last settings" gate a few lines
above (`self.last_selection_hash == current_selection_hash`) depends on.
Without it, last_selection_hash stayed whatever an unrelated earlier
operation left it as (or None), so the gate almost never passed and
Band Ratio silently reopened with default/empty settings every time.

These tests exercise the real OperationsController.show_parameters_dialog
dispatch with BandRatioDialog swapped for a lightweight fake (no
QApplication needed), and assert directly on what current_settings each
BandRatioDialog construction actually receives -- the same behavior the
user reported and asked to have fixed.

A second, related bug covered here too: settings were only ever saved
when the dialog was Accepted (OK clicked) -- closing it with Cancel or
the window's own X button (QDialog.Rejected either way) skipped saving
entirely, unlike every other dialog in the app (CD/X-axis unit
conversion, FFT Denoising, Combine Spectra, ...), which all remember
whatever was last shown regardless of how the dialog closed. Fixed by
reading get_settings() and updating last_op_settings/last_selection_hash
unconditionally, while still gating the actual commit
(handle_band_ratio(), which writes ratios into spectra metadata and
Operations History) on Accepted specifically -- Cancel/X must still mean
"don't apply this."
"""

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest
from PyQt5.QtWidgets import QDialog

from src.controllers.core.operations_controller import OperationsController


def _spectrum(label):
    x = np.linspace(0, 10, 5)
    return {'label': label, 'x_scale': x, 'y_scale': np.zeros(5)}


class _FakeBandRatioDialog:
    """Records the current_settings it was constructed with, and hands
    back a canned get_settings() result on Accept -- mirrors the real
    BandRatioDialog's public surface without needing a QApplication."""

    last_constructed_with = None  # captured for the test to inspect
    canned_settings = {
        'band_a': {'ranges': [(1500, 1600)], 'is_exclude': False,
                   'metric': 'Peak intensity'},
        'band_b': {'ranges': [(1000, 1050)], 'is_exclude': False,
                   'metric': 'Integral'},
        'operation': 'A / B',
    }

    # Tests that want to simulate Cancel/X set this to QDialog.Rejected
    # before constructing the dialog; defaults to Accepted (OK) so every
    # test written before this existed keeps behaving the same way.
    exec_result = QDialog.Accepted

    def __init__(self, parent, selected_spectra, current_settings=None, controller=None):
        _FakeBandRatioDialog.last_constructed_with = dict(current_settings or {})

    def exec_(self):
        return _FakeBandRatioDialog.exec_result

    def get_settings(self):
        return dict(_FakeBandRatioDialog.canned_settings)


@pytest.fixture
def operations_controller(monkeypatch):
    main_controller = MagicMock()
    main_controller.original_spectra = []

    # show_parameters_dialog computes ONE current_selection_hash up front
    # from spectrum_selector.get_selected_spectra() -- that's the value
    # the "same selection" gate actually compares against, both to decide
    # whether to restore last_op_settings and (with the fix) to record as
    # self.last_selection_hash afterward. _get_current_state_for_selected_
    # spectra() is a separate lookup (matches the list-widget selection by
    # identity against the operations-manager snapshot) that the Band
    # Ratio branch uses for the actual spectra it hands to the dialog --
    # kept in sync with the same labels here so both stand in for "the
    # same real selection", exactly as they would in the running app.
    _same_selection = [_spectrum('Sample A'), _spectrum('Sample B')]
    main_controller.spectrum_selector.get_selected_spectra.return_value = list(_same_selection)

    oc = OperationsController(main_controller)

    monkeypatch.setattr(
        oc, '_get_current_state_for_selected_spectra',
        lambda: list(_same_selection),
    )
    # handle_band_ratio() does real work (saving ratios into spectra
    # metadata, Operations History) that's unrelated to this bug and
    # would need a much heavier fake controller to exercise safely.
    monkeypatch.setattr(oc, 'handle_band_ratio', MagicMock())

    monkeypatch.setattr(
        'src.controllers.core.operations_controller.BandRatioDialog',
        _FakeBandRatioDialog,
    )
    monkeypatch.setattr(
        'src.controllers.core.operations_controller.BandRatioController',
        MagicMock(),
    )

    _FakeBandRatioDialog.last_constructed_with = None
    _FakeBandRatioDialog.exec_result = QDialog.Accepted
    return oc


def test_first_open_has_no_remembered_settings(operations_controller):
    operations_controller.show_parameters_dialog_for('Band Ratio')
    assert _FakeBandRatioDialog.last_constructed_with == {}


def test_settings_saved_after_accept_update_last_selection_hash(operations_controller):
    """The actual bug: last_selection_hash must be updated, or the very
    next open for the SAME selection won't pass the "same selection"
    gate that restores last_op_settings."""
    operations_controller.show_parameters_dialog_for('Band Ratio')

    selected = operations_controller._get_current_state_for_selected_spectra()
    expected_hash = operations_controller._get_selection_hash(selected)
    assert operations_controller.last_selection_hash == expected_hash


def test_reopening_for_same_selection_restores_last_settings(operations_controller):
    operations_controller.show_parameters_dialog_for('Band Ratio')  # first run, saves canned_settings
    operations_controller.show_parameters_dialog_for('Band Ratio')  # reopen, same selection

    assert _FakeBandRatioDialog.last_constructed_with == _FakeBandRatioDialog.canned_settings


def test_different_selection_does_not_inherit_settings(operations_controller, monkeypatch):
    operations_controller.show_parameters_dialog_for('Band Ratio')  # first run, saves canned_settings

    # A different selection must NOT see the previous selection's settings
    # -- this is the flip side of the same bug class (never carry settings
    # over to an unrelated selection). Both lookups the real dispatch code
    # reads from need to change together, same as the fixture above.
    other_selection = [_spectrum('Some Other Sample')]
    operations_controller.controller.spectrum_selector.get_selected_spectra.return_value = list(other_selection)
    monkeypatch.setattr(
        operations_controller, '_get_current_state_for_selected_spectra',
        lambda: list(other_selection),
    )
    operations_controller.show_parameters_dialog_for('Band Ratio')

    assert _FakeBandRatioDialog.last_constructed_with == {}



def test_settings_remembered_even_when_dialog_is_cancelled(operations_controller):
    """The second bug: Cancel (or the window's X, which also reports
    Rejected) must still remember whatever was last configured, exactly
    like OK does -- only the actual commit is OK-only."""
    _FakeBandRatioDialog.exec_result = QDialog.Rejected
    operations_controller.show_parameters_dialog_for('Band Ratio')

    assert operations_controller.last_op_settings['Band Ratio'] == _FakeBandRatioDialog.canned_settings
    selected = operations_controller._get_current_state_for_selected_spectra()
    assert operations_controller.last_selection_hash == operations_controller._get_selection_hash(selected)

    # Reopening for the same selection must see those settings, whether
    # the previous open was accepted or cancelled.
    _FakeBandRatioDialog.exec_result = QDialog.Accepted
    operations_controller.show_parameters_dialog_for('Band Ratio')
    assert _FakeBandRatioDialog.last_constructed_with == _FakeBandRatioDialog.canned_settings


def test_handle_band_ratio_not_called_when_cancelled(operations_controller):
    _FakeBandRatioDialog.exec_result = QDialog.Rejected
    operations_controller.show_parameters_dialog_for('Band Ratio')
    operations_controller.handle_band_ratio.assert_not_called()


def test_handle_band_ratio_called_when_accepted(operations_controller):
    _FakeBandRatioDialog.exec_result = QDialog.Accepted
    operations_controller.show_parameters_dialog_for('Band Ratio')
    operations_controller.handle_band_ratio.assert_called_once()
