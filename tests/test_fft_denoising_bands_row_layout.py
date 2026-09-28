"""Regression test for the FFT Denoising dialog's stop-bands layout
rework: "Cut below"/"Cut low" and "Cut above"/"Cut high" now share one
row instead of two, "Add band" is shortened to "Add" (and its "Update
band" edit-mode label to "Update"), and Add/Update, Cancel edit and
Remove now sit on the same row as the F low/F high spinboxes instead of
a separate row below them -- all purely a layout change, so these tests
check the button text and that adding/editing/removing a band still
behaves the same as before.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from src.views.dialogs.data_analysis.fft_denoising_dialog import FFTDenoisingDialog

app = QApplication.instance() or QApplication([])


def _spectrum(label):
    x = np.linspace(0, 1000, 64)
    return {'label': label, 'x_scale': x, 'y_scale': np.sin(x / 10.0)}


def _make_dialog():
    return FFTDenoisingDialog(parent=None, selected_spectra=[_spectrum('S1')])


def test_add_button_starts_as_add():
    dlg = _make_dialog()
    assert dlg._add_band_btn.text() == 'Add'


def test_selecting_a_band_switches_button_to_update():
    dlg = _make_dialog()
    dlg._band_lo_spin.setValue(0.1)
    dlg._band_hi_spin.setValue(0.2)
    dlg._add_band()
    assert dlg._bands_table.rowCount() == 1

    dlg._bands_table.selectRow(0)
    assert dlg._add_band_btn.text() == 'Update'
    assert dlg._cancel_band_edit_btn.isHidden() is False


def test_cancel_edit_switches_button_back_to_add():
    dlg = _make_dialog()
    dlg._band_lo_spin.setValue(0.1)
    dlg._band_hi_spin.setValue(0.2)
    dlg._add_band()
    dlg._bands_table.selectRow(0)

    dlg._cancel_band_edit()
    assert dlg._add_band_btn.text() == 'Add'
    assert dlg._cancel_band_edit_btn.isHidden() is True


def test_quick_cut_buttons_still_add_to_stop_bands():
    dlg = _make_dialog()
    dlg._quick_low_spin.setValue(5.0)
    dlg._quick_cut_low()
    dlg._quick_high_spin.setValue(60.0)
    dlg._quick_cut_high()
    assert len(dlg._stop_bands) == 2


def test_remove_button_removes_selected_band():
    dlg = _make_dialog()
    dlg._band_lo_spin.setValue(0.1)
    dlg._band_hi_spin.setValue(0.2)
    dlg._add_band()
    assert dlg._bands_table.rowCount() == 1

    dlg._bands_table.selectRow(0)
    dlg._remove_band()
    assert dlg._bands_table.rowCount() == 0
    assert dlg._stop_bands == []
