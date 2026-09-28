"""Regression test for a real gap the user reported while GUI-testing:
Combine Spectra's dialog only remembered the Average/Sum radio selection
and the output name across reopens -- the "Show +/-1 std-dev band",
"Show legend", and "Show selected spectra with result" checkboxes were
never included in get_settings()/load_settings() at all, so they
silently reset to unchecked every time the dialog reopened, even for the
exact same spectra selection (where OperationsController's own
selection-hash gating was already correct; the gap was entirely inside
this dialog's own settings round-trip).

"Shorten names" deliberately stays out of get_settings()/load_settings()
here, same as every other dialog in the app -- it's a display-only
convenience, not remembered anywhere, and this test doesn't ask it to be.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from src.views.dialogs.data_analysis.spectra_combine_dialog import CombineSpectraDialog

app = QApplication.instance() or QApplication([])


def _spectrum(label):
    x = np.linspace(400, 1800, 50)
    return {'label': label, 'x_scale': x, 'y_scale': np.random.default_rng(0).normal(size=50)}


def _make_dialog(current_settings=None):
    return CombineSpectraDialog(
        parent=None,
        selected_spectra=[_spectrum('A'), _spectrum('B')],
        num_selected=2,
        current_settings=current_settings,
    )


def test_show_variance_and_show_legend_round_trip():
    dlg = _make_dialog()
    dlg.average_radio.setChecked(True)
    dlg.show_variance_cb.setChecked(True)
    dlg.show_legend_cb.setChecked(True)
    dlg.name_edit.setText("Combined_1")

    settings = dlg.get_settings()
    assert settings['show_variance'] is True
    assert settings['show_legend'] is True

    dlg2 = _make_dialog(current_settings=settings)
    assert dlg2.show_variance_cb.isChecked() is True
    assert dlg2.show_legend_cb.isChecked() is True


def test_unset_settings_default_to_unchecked():
    # A settings dict saved before this fix existed (no show_variance/
    # show_legend keys at all) must not crash load_settings, and should
    # fall back to the same unchecked default these checkboxes already
    # start with.
    dlg = _make_dialog(current_settings={'operation_type': 'average',
                                          'new_spectrum_name': 'Old'})
    assert dlg.show_variance_cb.isChecked() is False
    assert dlg.show_legend_cb.isChecked() is False


def test_show_variance_forced_off_when_restoring_sum_operation():
    dlg = _make_dialog(current_settings={
        'operation_type': 'sum',
        'new_spectrum_name': 'Sum_1',
        'show_variance': True,  # shouldn't normally happen, but guard it
        'show_legend': True,
    })
    assert dlg.sum_radio.isChecked() is True
    assert dlg.show_variance_cb.isEnabled() is False
    assert dlg.show_variance_cb.isChecked() is False
    # show_legend is independent of operation type -- stays restored.
    assert dlg.show_legend_cb.isChecked() is True


def test_show_selected_round_trip():
    dlg = _make_dialog()
    dlg.show_selected_cb.setChecked(True)
    dlg.name_edit.setText("Combined_1")

    settings = dlg.get_settings()
    assert settings['show_selected'] is True

    dlg2 = _make_dialog(current_settings=settings)
    assert dlg2.show_selected_cb.isChecked() is True


def test_show_selected_defaults_to_unchecked_when_unset():
    dlg = _make_dialog(current_settings={'operation_type': 'average',
                                          'new_spectrum_name': 'Old'})
    assert dlg.show_selected_cb.isChecked() is False
