"""Peak detection, Signal-to-noise (min.): a peak must also stand out at
least 8 x the noise of its spectrum (estimated from the spectrum itself),
so the noise of the weak spectra of a series is not taken for peaks."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from src.modules.data_analysis import peak_list as pl

app = QApplication.instance() or QApplication([])
X = np.linspace(190, 270, 801)


def _weak_noisy(seed=1, size=0.08, noise=0.01):
    """A weak spectrum (two bands, 8 x the noise) with white noise."""
    rng = np.random.default_rng(seed)
    y = (-size * np.exp(-0.5 * ((X - 215) / 5) ** 2) + size * np.exp(-0.5 * ((X - 230) / 5) ** 2))
    return y + noise * rng.standard_normal(len(X))


def test_the_noise_is_estimated_from_the_spectrum():
    rng = np.random.default_rng(2)
    smooth = np.exp(-0.5 * ((X - 230) / 5) ** 2)
    assert pl.noise_level(smooth) < 1e-3
    assert pl.noise_level(smooth + 0.01 * rng.standard_normal(len(X))) == pytest.approx(0.01, rel=0.2)
    assert pl.noise_level(np.array([0, 1, 5, 1, 0, 0, 2, 0], dtype=float)) == 0.0   # too few points


def test_noise_is_not_taken_for_peaks():
    y = _weak_noisy()
    without = pl.spectrum_peaks(X, y, mode='Both', snr=0)
    with_snr = pl.spectrum_peaks(X, y, mode='Both')
    assert len(without) > 4                               # noise peaks of a weak spectrum
    assert sorted(round(p['x']) for p in with_snr) == pytest.approx([215, 230], abs=3)   # noise moves them a bit


def test_clean_spectra_are_not_affected():
    y = _weak_noisy(noise=0.0)
    assert [p['x'] for p in pl.spectrum_peaks(X, y, mode='Both')] == \
        [p['x'] for p in pl.spectrum_peaks(X, y, mode='Both', snr=0)]


def test_the_setting_in_the_peaks_window():
    from src.views.dialogs.data_analysis.peak_detection_dialog import DEFAULTS
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    assert pl.DEFAULTS['snr'] == 8.0 and DEFAULTS['snr'] == 8.0
    listing = PeakListDialog(None, [{'label': 'weak', 'x_scale': X, 'y_scale': _weak_noisy()}],
                             mode='Both')
    assert listing.settings()['snr'] == 8.0 and listing.table.rowCount() == 2
    assert 'noise' in listing.snr.toolTip()
    listing.snr.setValue(0)                                  # the table follows at once
    assert listing.table.rowCount() > 4
    listing.reset_button.click()
    assert listing.settings() == pl.DEFAULTS


def test_detect_peaks_marks_the_same_peaks_as_the_list():
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from src.modules.data_analysis.peak_detection_manager import PeakDetector
    y = _weak_noisy()
    fig = Figure()
    canvas = FigureCanvasAgg(fig)
    fig.add_subplot(111).plot(X, y, label='weak')
    det = PeakDetector()
    det.detect_peaks(canvas, 0.0, 10, 0, 2, 'fixed', 'x_only', True, 0.1, 0.05, 'Both',
                     labels='all', snr=8.0)
    marked = sorted(float(X[i]) for i in det.peak_indices[(0, 0)])
    listed = [r[3] for r in pl.peak_table([{'label': 'weak', 'x_scale': X, 'y_scale': y}],
                                          0.0, 0.1, 0.05, 'Both', 8.0)]
    assert marked == listed and len(listed) == 2


def test_the_help_explains_it():
    from src.help.peak_detection_help import get_peak_detection_help_content
    text = get_peak_detection_help_content()
    assert 'Signal-to-noise' in text and 'signal-to-noise 8' in text
    assert any(n == 'Signal-to-noise' for n, _, _ in pl.SETTINGS_HELP)
