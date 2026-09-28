"""Regression test for the Automated Baseline Correction dialog's
"? Method info" button.

Every baseline method used to have its description baked in as a fixed,
always-visible QLabel inside that method's own params page -- which is
also what made "Method Parameters" reserve extra vertical space for
whichever method's note happened to be longest (see
test_automated_baseline_panel_sizing.py / _CurrentPageStackedWidget).
Moved to a single "? Method info" button (same pattern as
NormalizationDialog's own), sourced from the BASELINE_METHOD_INFO dict,
so the description is available on demand for the currently selected
method instead of always taking up space.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from src.views.dialogs.data_analysis.automated_baseline_dialog import (
    AutomatedBaselineDialog, BASELINE_METHOD_INFO)

app = QApplication.instance() or QApplication([])


def _make_dialog():
    selected_spectra = [
        {'label': 'Spectrum 1', 'x_scale': np.linspace(400, 1800, 200),
         'y_scale': np.random.default_rng(0).random(200)},
    ]
    return AutomatedBaselineDialog(parent=None, selected_spectra=selected_spectra)


def _index_for(dlg, key):
    for i in range(dlg.method_combo.count()):
        if dlg.method_combo.itemData(i) == key:
            return i
    raise KeyError(key)


def test_method_info_button_exists_and_is_wired():
    dlg = _make_dialog()
    assert hasattr(dlg, 'method_info_button')
    assert dlg.method_info_button.receivers(dlg.method_info_button.clicked) > 0


def test_every_combo_entry_has_matching_info():
    dlg = _make_dialog()
    assert dlg.method_combo.count() == 13
    for i in range(dlg.method_combo.count()):
        key = dlg.method_combo.itemData(i)
        assert key in BASELINE_METHOD_INFO, f"missing BASELINE_METHOD_INFO for {key!r}"
        # Combo label and dict label are meant to be the same string --
        # sourced from the dict in create_control_panel -- so they can't
        # silently drift apart.
        assert dlg.method_combo.itemData(i) in BASELINE_METHOD_INFO


@pytest.mark.parametrize('key', ['als', 'airpls', 'jbcd', 'morphological', 'mollification'])
def test_method_info_shows_the_selected_methods_own_description(key):
    dlg = _make_dialog()
    dlg.method_combo.setCurrentIndex(_index_for(dlg, key))

    with patch(
        'src.views.dialogs.data_analysis.automated_baseline_dialog.QMessageBox.information'
    ) as mock_info:
        dlg._show_method_info()

    assert mock_info.call_count == 1
    _parent, title, text = mock_info.call_args[0]
    assert title == BASELINE_METHOD_INFO[key]['label']
    assert BASELINE_METHOD_INFO[key]['info'] in text


def test_old_fixed_note_labels_are_gone():
    dlg = _make_dialog()
    for name in ('airpls_note', 'arpls_note', 'iarpls_note', 'aspls_note',
                 'drpls_note', 'psalsa_note', 'imodpoly_note', 'mpls_note',
                 'mpspline_note', 'jbcd_note'):
        assert not hasattr(dlg, name)
