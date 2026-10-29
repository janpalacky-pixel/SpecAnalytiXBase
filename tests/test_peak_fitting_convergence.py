"""Peak Fitting converges better: Auto-Detect gives the Gaussian width
(sigma, not the full width at half height) and no false negative peaks in the
dips between bands; a fit cannot run away to huge peaks of opposite sign,
centres outside the data or widths beyond half the x range; a peak added by a
click gets the width of the band under the click."""
import os

import numpy as np
import pytest

from src.modules.data_analysis.peak_fitting_manager import PeakFittingManager, gaussian

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bands(noise=0.01, seed=0):
    """Six positive bands on a flat baseline, some close together."""
    x = np.linspace(200, 1800, 800)
    y = (gaussian(x, 0.5, 730, 20) + gaussian(x, 1.2, 1081, 8) + gaussian(x, 0.55, 1150, 20)
         + gaussian(x, 0.4, 1293, 7) + gaussian(x, 0.9, 1640, 18) + gaussian(x, 1.2, 1742, 8))
    return x, y + np.random.default_rng(seed).normal(0, noise, x.size)


def test_auto_detect_finds_the_bands_with_their_sigma_and_no_dips():
    x, y = _bands()
    found = PeakFittingManager().auto_detect_peaks(y, x)
    centres = [p['center'] for p in found]
    assert len(found) == 6 and all(p['amplitude'] > 0 for p in found)   # no "negative" dips
    assert np.allclose(centres, [730, 1081, 1150, 1293, 1640, 1742], atol=6)
    widths = [p['width'] for p in found]
    assert np.allclose(widths, [20, 8, 20, 7, 18, 8], rtol=0.35)        # sigma, not FWHM


def test_a_real_negative_band_is_still_found():
    x = np.linspace(200, 300, 400)
    y = gaussian(x, 1.0, 230, 4) - gaussian(x, 0.8, 270, 5)              # e.g. a CD spectrum
    found = PeakFittingManager().auto_detect_peaks(y, x)
    assert [round(p['center']) for p in found] == [230, 270]
    assert found[1]['amplitude'] < 0


def test_detected_peaks_fit_well_and_fast_on_the_noisy_raman_series():
    import time
    import pandas as pd
    from src.modules.data_analysis import peak_fitting_series as pfs
    frame = pd.read_excel(os.path.join(ROOT, 'resources', 'test_data', 'synthetic',
                                       'raman_2comp_noisy.xlsx'))
    x = frame.iloc[:, 0].values
    m = PeakFittingManager()
    start = time.time()
    for column in frame.columns[1:11]:
        y = frame[column].values
        found = m.auto_detect_peaks(y, x)
        assert 5 <= len(found) <= 8
        for constraint in ('unrestricted', 'positive'):
            fitted, total = m.fit_peaks(x, y, found, amplitude_constraint=constraint)
            assert fitted is not None
            r2 = 1 - np.sum((y - total) ** 2) / np.sum((y - y.mean()) ** 2)
            assert r2 > 0.98
            assert max(abs(f['parameters']['height']) for f in fitted) < 3 * np.max(np.abs(y))
    assert time.time() - start < 30


def test_the_fit_is_kept_within_the_data():
    x, y = _bands()
    m = PeakFittingManager()
    bad = [{'model': 'Gaussian', 'center': 1100, 'amplitude': 40.0, 'width': 900.0},
           {'model': 'Gaussian', 'center': 1100, 'amplitude': -40.0, 'width': 900.0},
           {'model': 'Gaussian', 'center': 1081, 'amplitude': 1.0, 'width': 8.0}]
    fitted, _ = m.fit_peaks(x, y, bad)
    assert fitted is not None
    cap = 3 * np.max(np.abs(y))
    for f in fitted:
        p = f['parameters']
        assert abs(p['height']) <= cap * (1 + 1e-9)
        assert x.min() <= p['center'] <= x.max()
        assert p['sigma'] <= (x.max() - x.min()) / 2 * (1 + 1e-9)


def test_the_width_of_a_clicked_band():
    x, y = _bands(noise=0.0)
    m = PeakFittingManager()
    assert m.estimate_width(x, y, 1083) == pytest.approx(8, rel=0.1)    # near the top
    assert m.estimate_width(x, y, 730) == pytest.approx(20, rel=0.1)
    assert m.estimate_width(x, y, 450) is None                          # flat baseline
