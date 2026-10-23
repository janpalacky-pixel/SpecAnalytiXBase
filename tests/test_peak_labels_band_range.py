"""Detect Peaks, Labels once per band: a band whose peaks move through the
series (e.g. a CD minimum of overlapping bands that shifts from 247 to 256
nm as the mixture changes) is written as a range "247.2-256.2", not as one
median that hides the shift; a band that stays put keeps one number."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib
matplotlib.use('Agg')
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


def _canvas(shift_per_spectrum, n=8):
    fig = Figure()
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    x = np.linspace(190, 300, 1101)
    for i in range(n):
        y = (-(0.3 + 0.1 * i) * np.exp(-0.5 * ((x - 247 - shift_per_spectrum * i) / 9) ** 2)
             + 0.2 * np.exp(-0.5 * ((x - 210) / 6) ** 2))       # a band that stays put
        ax.plot(x, y, label=f'sp{i + 1}')
    return canvas


def _texts(canvas):
    from src.modules.data_analysis.peak_detection_manager import PeakDetector
    det = PeakDetector()
    det.detect_peaks(canvas, 0.0, 10, 0, 1, 'fixed', 'x_only', True, 0.1, 0.02, 'Both',
                     labels='band')
    return sorted(t.get_text() for t in det.peak_texts)


def test_a_moving_band_is_written_as_its_range():
    texts = _texts(_canvas(1.3))                  # the minimum moves 247 -> 256.1
    assert '210.0' in texts
    ranges = [t for t in texts if '–' in t]
    assert len(ranges) == 1
    lo, hi = (float(v) for v in ranges[0].split('–'))
    assert abs(lo - 247.0) < 0.2 and abs(hi - 256.1) < 0.2


def test_a_band_that_stays_put_keeps_one_number():
    texts = _texts(_canvas(0.1))                  # moves 0.7 in all: noise-like
    assert not any('–' in t for t in texts)
    assert len(texts) == 2


def test_x_and_y_values_with_a_range():
    from src.modules.data_analysis.peak_detection_manager import PeakDetector
    det = PeakDetector()
    det.detect_peaks(_canvas(1.3), 0.0, 10, 0, 1, 'fixed', 'both', True, 0.1, 0.02, 'Both',
                     labels='band')
    texts = [t.get_text() for t in det.peak_texts]
    assert any(t.startswith('(') and '–' in t for t in texts)
