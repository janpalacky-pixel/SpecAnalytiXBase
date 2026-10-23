"""Peak detection: the default Threshold is 0 - a peak is judged locally, by
how much it stands out from the valleys around it (Prominence), not by its
height compared with the tallest peak of the spectrum, which missed clear
smaller peaks next to strong bands."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

from src.modules.data_analysis import peak_list as pl

app = QApplication.instance() or QApplication([])


def _strong_and_small():
    x = np.linspace(200, 1800, 1601)
    y = (1.3 * np.exp(-0.5 * ((x - 815) / 10) ** 2)       # strong band
         + 0.25 * np.exp(-0.5 * ((x - 345) / 14) ** 2)    # small but clear band
         + 0.9 * np.exp(-0.5 * ((x - 1438) / 12) ** 2))
    return x, y


def test_the_default_threshold_is_zero_everywhere():
    from src.views.dialogs.data_analysis.peak_detection_dialog import DEFAULTS, PeakDetectionDialog
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    assert pl.DEFAULTS['threshold'] == 0.0 and DEFAULTS['threshold'] == 0.0
    assert PeakDetectionDialog(None).threshold_input.value() == 0.0
    x, y = _strong_and_small()
    assert PeakListDialog(None, [{'label': 'a', 'x_scale': x, 'y_scale': y}]).threshold.value() == 0.0


def test_a_small_clear_peak_next_to_a_strong_one_is_found():
    x, y = _strong_and_small()
    found = [round(p['x']) for p in pl.spectrum_peaks(x, y, **{k: v for k, v in pl.DEFAULTS.items()})]
    assert found == [345, 815, 1438]
    old = [round(p['x']) for p in pl.spectrum_peaks(x, y, threshold=0.5)]
    assert 345 not in old                         # the old default missed it


def test_threshold_can_still_be_raised():
    x, y = _strong_and_small()
    assert [round(p['x']) for p in pl.spectrum_peaks(x, y, threshold=0.8)] == [815]


def test_the_help_explains_the_new_default():
    from src.help.peak_detection_help import get_peak_detection_help_content
    text = get_peak_detection_help_content()
    assert 'Defaults: threshold 0,' in text and 'locally' in text
    help_text = dict((n, (w, d)) for n, w, d in pl.SETTINGS_HELP)['Threshold (height)']
    assert help_text[1] == '0'
