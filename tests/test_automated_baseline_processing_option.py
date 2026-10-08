"""Automated Baseline dialog: the Processing (serial / parallel) option.

It must be saved with the other settings, restored when the dialog is
reopened, default to Automatic for settings saved before it existed, and
be switched off (Workers box disabled) for Serial.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import numpy as np
from PyQt5.QtWidgets import QApplication

from src.controllers.data_analysis.automated_baseline_controller import (
    AutomatedBaselineController)
from src.modules.data_analysis.automated_baseline_manager import AutomatedBaselineManager
from src.views.dialogs.data_analysis.automated_baseline_dialog import AutomatedBaselineDialog

app = QApplication.instance() or QApplication([])


def _spectrum(label):
    x = np.linspace(200, 3200, 300)
    return {'label': label, 'x_scale': x, 'y_scale': np.exp(-((x - 1500) / 50) ** 2) + 0.001 * x,
            'metadata': {}}


def _dialog(current_settings=None):
    return AutomatedBaselineDialog(
        parent=None, selected_spectra=[_spectrum('a'), _spectrum('b')],
        current_settings=current_settings)


def test_default_is_automatic_with_automatic_workers():
    s = _dialog().get_settings()
    assert s['processing_mode'] == 'auto'
    assert s['max_workers'] == 0
    assert s['algorithm'] == 'als'            # the normal settings are still there


def test_choice_is_saved_and_restored_on_reopen():
    first = _dialog()
    first.processing_mode_combo.setCurrentIndex(first.processing_mode_combo.findData('parallel'))
    first.max_workers_spin.setValue(1)
    saved = first.get_settings()
    assert (saved['processing_mode'], saved['max_workers']) == ('parallel', 1)

    again = _dialog(current_settings=saved).get_settings()
    assert (again['processing_mode'], again['max_workers']) == ('parallel', 1)


def test_settings_saved_before_the_option_existed_open_as_automatic():
    old = {'algorithm': 'arpls', 'lambda': 1e5, 'n_iter': 50, 'fitting_ranges': [],
           'invert_regions': False}
    s = _dialog(current_settings=old).get_settings()
    assert s['algorithm'] == 'arpls'
    assert s['processing_mode'] == 'auto'


def test_workers_box_is_disabled_for_serial():
    d = _dialog()
    d.processing_mode_combo.setCurrentIndex(d.processing_mode_combo.findData('serial'))
    assert not d.max_workers_spin.isEnabled()
    d.processing_mode_combo.setCurrentIndex(d.processing_mode_combo.findData('parallel'))
    assert d.max_workers_spin.isEnabled()


def test_dialog_settings_work_with_the_manager():
    d = _dialog()
    d.processing_mode_combo.setCurrentIndex(d.processing_mode_combo.findData('serial'))
    mgr = AutomatedBaselineManager()
    out = mgr.apply_correction([_spectrum('a'), _spectrum('b')], d.get_settings())
    assert len(out) == 2 and mgr.last_run_info['mode'] == 'serial'


def _controller():
    oc = SimpleNamespace(_PROGRESS_DIALOG_SPECTRA_THRESHOLD=200)
    return AutomatedBaselineController(SimpleNamespace(operations_controller=oc))


def test_progress_dialog_is_shown_for_parallel_or_slow_methods_but_not_for_one_spectrum():
    c = _controller()
    assert c._spectra_count_for_progress({'algorithm': 'als'}, 5) == 5            # quick: no dialog
    assert c._spectra_count_for_progress({'algorithm': 'als', 'processing_mode': 'parallel'}, 5) == 200
    assert c._spectra_count_for_progress({'algorithm': 'mpspline'}, 5) == 200
    assert c._spectra_count_for_progress({'algorithm': 'mpspline', 'processing_mode': 'parallel'}, 1) == 1
    assert c._spectra_count_for_progress({'algorithm': 'als'}, 500) == 500
