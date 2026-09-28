"""Regression test for FFT Denoising's settings-remembering.

The stop-bands table (the actual filter definition) already round-
tripped correctly through get_settings()/_populate_from_settings() --
verified directly here too, so a future change can't silently break
that. What was actually missing (the user's report: "Nothing is
remembered in FFT denoising dialog on reopen") were the dialog's own
view/display preferences: the Signal view Subplots/Overlay radio group,
"Show power spectra", "Show spectra", and "Show legend" -- none of
these were ever written into get_settings() or read back in
_populate_from_settings(), so they silently reset to their hardcoded
defaults every reopen regardless of selection.

"Shorten names" deliberately stays unremembered here too, same
convention as every other dialog in the app.
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
    y = np.sin(x / 10.0)
    return {'label': label, 'x_scale': x, 'y_scale': y}


def _make_dialog(current_settings=None):
    return FFTDenoisingDialog(
        parent=None,
        selected_spectra=[_spectrum('S1'), _spectrum('S2')],
        current_settings=current_settings,
    )


def test_stop_bands_round_trip():
    dlg = _make_dialog()
    dlg._stop_bands.append((0.1, 0.2))
    dlg._refresh_bands_table()

    settings = dlg.get_settings()
    assert settings['stop_bands'] == [(0.1, 0.2)]

    dlg2 = _make_dialog(current_settings=settings)
    assert dlg2._stop_bands == [(0.1, 0.2)]
    assert dlg2._bands_table.rowCount() == 1


def test_view_preferences_round_trip():
    dlg = _make_dialog()
    # Defaults, confirmed directly rather than assumed.
    assert dlg._show_power_cb.isChecked() is True
    assert dlg._show_signal_cb.isChecked() is True
    assert dlg.show_legend_cb.isChecked() is False
    assert dlg._signal_mode.checkedId() == 0  # Subplots

    dlg._show_power_cb.setChecked(False)
    dlg._show_signal_cb.setChecked(False)
    dlg.show_legend_cb.setChecked(True)
    dlg._signal_mode.button(1).setChecked(True)  # Overlay

    settings = dlg.get_settings()
    assert settings['show_power'] is False
    assert settings['show_signal'] is False
    assert settings['show_legend'] is True
    assert settings['signal_mode'] == 1

    dlg2 = _make_dialog(current_settings=settings)
    assert dlg2._show_power_cb.isChecked() is False
    assert dlg2._show_signal_cb.isChecked() is False
    assert dlg2.show_legend_cb.isChecked() is True
    assert dlg2._signal_mode.checkedId() == 1


def test_settings_without_view_keys_keep_dialog_defaults():
    # A settings dict saved before this fix (only stop_bands/low_cutoff/
    # high_cutoff/window) must not crash _populate_from_settings, and
    # must leave the view checkboxes at their normal defaults rather
    # than forcing them to some other state.
    dlg = _make_dialog(current_settings={
        'stop_bands': [], 'low_cutoff': None, 'high_cutoff': None, 'window': 'none',
    })
    assert dlg._show_power_cb.isChecked() is True
    assert dlg._show_signal_cb.isChecked() is True
    assert dlg.show_legend_cb.isChecked() is False
    assert dlg._signal_mode.checkedId() == 0
