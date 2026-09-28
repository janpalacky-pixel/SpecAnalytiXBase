"""Regression test for a real bug the user hit while GUI-testing: reopening
Melting Curve Analysis for the exact same, unmodified spectra selection is
supposed to bring back "whatever was last shown" (see the GUI Test Guide's
"Tools that already double-check the data" section) -- but it was actually
bringing back a STALE result from before the user's last change.

Concretely: the user opened the dialog (an old, previously-accepted
1-component fit came back, correctly, from the fingerprint-gated cache),
pressed the "Fit" button with n_components changed to 2 (a properly
converged fit), then closed the dialog WITHOUT clicking OK -- and the next
reopen went straight back to the stale 1-component fit, discarding the
2-component one entirely.

Root cause, in OperationsController.show_parameters_dialog's "Melting Curve
Analysis" branch: dialog.get_results() was only read and saved into
self.last_op_settings when dialog.exec_() == QDialog.Accepted. Cancel or
the window's own close button (both QDialog.Rejected) skipped saving
entirely -- exactly the same bug class already found and fixed for Band
Ratio earlier in this session (see test_band_ratio_settings_remembered.py).
Fixed by reading get_results() and updating last_op_settings/
current_parameters/last_selection_hash unconditionally, while still gating
the actual commit (handle_melting_curve_analysis(), which creates new
spectra from the checked Output Options) on Accepted specifically.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest
from PyQt5.QtWidgets import QDialog

from src.controllers.core.operations_controller import OperationsController


def _spectrum(label):
    x = np.linspace(0, 10, 5)
    return {'label': label, 'x_scale': x, 'y_scale': np.zeros(5)}


class _FakeMeltingCurveDialog:
    """Records nothing itself -- get_results() always returns whatever
    _FakeMeltingCurveController.next_results is currently set to, mirroring
    how the real dialog's get_results() just reads live widget state
    regardless of how the dialog is about to be closed."""

    exec_result = QDialog.Accepted  # tests override this per-case

    def __init__(self, controller):
        self._controller = controller

    def exec_(self):
        return _FakeMeltingCurveDialog.exec_result

    def get_results(self):
        return dict(self._controller.next_results)


class _FakeMeltingCurveController:
    """Stands in for the real MeltingCurveController -- pre-installed onto
    main_controller.melting_curve_controller so OperationsController's
    hasattr(...) lazy-construct check finds it already there and never
    imports/constructs the real one (which would need a QApplication)."""

    def __init__(self):
        self.next_results = {}
        self.last_current_settings = None
        self.handle_calls = 0

    def show_dialog(self, selected_spectra, current_settings=None):
        self.last_current_settings = current_settings
        return _FakeMeltingCurveDialog(self)


@pytest.fixture
def operations_controller(monkeypatch):
    main_controller = MagicMock()
    main_controller.original_spectra = []

    oc = OperationsController(main_controller)

    two_spectra = [_spectrum('T10'), _spectrum('T20')]
    main_controller.spectrum_selector.get_selected_spectra.return_value = two_spectra

    fake_mcc = _FakeMeltingCurveController()
    main_controller.melting_curve_controller = fake_mcc

    monkeypatch.setattr(oc, 'handle_melting_curve_analysis', MagicMock())

    return oc, fake_mcc


def _one_component_results():
    return {
        'curve': {'x_temperature': [10, 20], 'y_raw': [0.1, 0.2], 'source_labels': ['T10', 'T20']},
        'fit_settings': {'n_components': 1, 'shape_name': 'Logistic'},
        'fit_result': {'params': [1.0], 'quality': {'r_squared': 0.8}},
        'output_options': {},
    }


def _two_component_results():
    return {
        'curve': {'x_temperature': [10, 20], 'y_raw': [0.1, 0.2], 'source_labels': ['T10', 'T20']},
        'fit_settings': {'n_components': 2, 'shape_name': 'Logistic'},
        'fit_result': {'params': [1.0, 2.0], 'quality': {'r_squared': 0.99}},
        'output_options': {},
    }


def test_settings_remembered_even_when_dialog_is_cancelled(operations_controller):
    oc, fake_mcc = operations_controller

    fake_mcc.next_results = _one_component_results()
    _FakeMeltingCurveDialog.exec_result = QDialog.Accepted
    oc.show_parameters_dialog_for('Melting Curve Analysis')

    # User re-fits with 2 components, then closes with Cancel (not OK).
    fake_mcc.next_results = _two_component_results()
    _FakeMeltingCurveDialog.exec_result = QDialog.Rejected
    oc.show_parameters_dialog_for('Melting Curve Analysis')

    # Reopening for the SAME, unchanged selection must show the 2-component
    # fit that was actually last on screen -- not fall back to the earlier,
    # stale 1-component one just because Cancel was clicked.
    fake_mcc.next_results = _one_component_results()  # would be a giveaway if wrongly used
    oc.show_parameters_dialog_for('Melting Curve Analysis')

    assert fake_mcc.last_current_settings == _two_component_results()


def test_handle_melting_curve_analysis_not_called_when_cancelled(operations_controller):
    oc, fake_mcc = operations_controller

    fake_mcc.next_results = _two_component_results()
    _FakeMeltingCurveDialog.exec_result = QDialog.Rejected
    oc.show_parameters_dialog_for('Melting Curve Analysis')

    oc.handle_melting_curve_analysis.assert_not_called()


def test_handle_melting_curve_analysis_called_when_accepted(operations_controller):
    oc, fake_mcc = operations_controller

    fake_mcc.next_results = _two_component_results()
    _FakeMeltingCurveDialog.exec_result = QDialog.Accepted
    oc.show_parameters_dialog_for('Melting Curve Analysis')

    oc.handle_melting_curve_analysis.assert_called_once()


def test_no_curve_result_is_not_remembered_regardless_of_accept(operations_controller):
    oc, fake_mcc = operations_controller

    fake_mcc.next_results = {'curve': None}
    _FakeMeltingCurveDialog.exec_result = QDialog.Accepted
    oc.show_parameters_dialog_for('Melting Curve Analysis')

    assert 'Melting Curve Analysis' not in oc.last_op_settings
    assert 'Melting Curve Analysis' not in oc.current_parameters
