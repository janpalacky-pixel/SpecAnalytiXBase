"""Regression test for a real bug the user hit while GUI-testing: running
QC / Outlier Detection with fewer than 5 selected spectra correctly showed
the "Insufficient Spectra" warning, but Windows' own spinning "busy"
cursor was left on screen at the same time.

Root cause: MainController.run_visualization_analysis's generic dispatch
sets QApplication.setOverrideCursor(Qt.WaitCursor) before calling into
QCOutlierController.run_qc_outlier_analysis(), which is where the "need
at least 5 spectra" check actually lived -- so that warning box popped up
while the wait cursor was still active, exactly the same bug class
run_visualization_analysis's own pre-existing comment already describes
(and already fixed) for a mismatched x-axis: the fix there was moving
validate_common_x_axis's call to before the cursor is set. This one just
didn't cover QC/Outlier's OWN extra "at least 5 spectra" check.

Fix: that check is pulled out into QCOutlierController.validate_selection,
callable by MainController before it ever touches the cursor -- these
tests cover validate_selection directly (no real QApplication needed;
QMessageBox is mocked at the module level, same pattern as
test_snapshot.py's controller-level tests) and confirm
run_qc_outlier_analysis still uses it as its own first gate.
"""

from unittest.mock import MagicMock, patch

import numpy as np

from src.controllers.visualization_analysis.qc_outlier_controller import (
    QCOutlierController)


def _spectrum(label, n_points=10):
    x = np.linspace(0, 10, n_points)
    return {'label': label, 'x_scale': x, 'y_scale': np.random.default_rng(0).normal(size=n_points)}


class _FakeMainController:
    def __init__(self):
        self.view = None
        self.selected_spectra = []


def _controller():
    return QCOutlierController(_FakeMainController())


@patch('src.controllers.visualization_analysis.qc_outlier_controller.QMessageBox')
def test_validate_selection_rejects_empty(mock_box):
    ctrl = _controller()

    assert ctrl.validate_selection([]) is False
    assert mock_box.warning.call_count == 1
    assert mock_box.warning.call_args[0][1] == "No Spectra Selected"


@patch('src.controllers.visualization_analysis.qc_outlier_controller.QMessageBox')
def test_validate_selection_rejects_fewer_than_five(mock_box):
    ctrl = _controller()
    spectra = [_spectrum(f's{i}') for i in range(4)]

    assert ctrl.validate_selection(spectra) is False
    assert mock_box.warning.call_count == 1
    assert mock_box.warning.call_args[0][1] == "Insufficient Spectra"


@patch('src.controllers.visualization_analysis.qc_outlier_controller.QMessageBox')
def test_validate_selection_accepts_five_or_more(mock_box):
    ctrl = _controller()
    spectra = [_spectrum(f's{i}') for i in range(5)]

    assert ctrl.validate_selection(spectra) is True
    mock_box.warning.assert_not_called()


@patch('src.controllers.visualization_analysis.qc_outlier_controller.validate_common_x_axis')
@patch('src.controllers.visualization_analysis.qc_outlier_controller.QMessageBox')
def test_run_qc_outlier_analysis_bails_out_via_validate_selection(mock_box, mock_axis_check):
    """With too few spectra, run_qc_outlier_analysis must return before
    ever reaching validate_common_x_axis (or opening a dialog) -- it
    should be gated entirely by validate_selection, the same check
    MainController now calls before setting its wait cursor."""
    ctrl = _controller()
    ctrl.main_controller.selected_spectra = [_spectrum('s0'), _spectrum('s1')]

    ctrl.run_qc_outlier_analysis()

    mock_axis_check.assert_not_called()
    assert mock_box.warning.call_count == 1
    assert mock_box.warning.call_args[0][1] == "Insufficient Spectra"
