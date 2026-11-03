"""Peak Fitting: is a peak needed? After the fit each peak is left out once,
the spectrum fitted again, and the two fits compared by BIC: the column
Needed? says yes (ΔBIC > 10), probably (2..10) or no (below 2)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_analysis.peak_fitting_manager import (PeakFittingManager, gaussian,
                                                             needed_text)
from src.modules.data_analysis import peak_fitting_series as pfs
from src.modules.data_analysis import peak_fitting_global as pg

app = QApplication.instance() or QApplication([])
X = np.linspace(0, 200, 800)


def _data(seed=0):
    rng = np.random.default_rng(seed)
    return (gaussian(X, 1.0, 60, 5) + gaussian(X, 2.0, 75, 6) + gaussian(X, 1.0, 140, 8)
            + rng.normal(0, 0.1, X.size))


THREE = [{'id': 'p1', 'model': 'Gaussian', 'center': 61.0, 'amplitude': 1.0, 'width': 5.0},
         {'id': 'p2', 'model': 'Gaussian', 'center': 74.0, 'amplitude': 2.0, 'width': 6.0},
         {'id': 'p3', 'model': 'Gaussian', 'center': 141.0, 'amplitude': 1.0, 'width': 8.0}]


def _fit(start, y=None):
    m = PeakFittingManager()
    y = _data() if y is None else y
    fitted, _ = m.fit_peaks(X, y, start)
    m.add_peak_bic(X, y, fitted, start)
    return fitted


def test_real_bands_are_needed_a_peak_on_noise_is_not():
    fitted = _fit(THREE + [{'id': 'p4', 'model': 'Gaussian', 'center': 180.0,
                            'amplitude': 0.05, 'width': 4.0}])
    words = [needed_text(f['delta_bic'])[0] for f in fitted]
    assert words[:3] == ['yes', 'yes', 'yes'] and words[3] == 'no'


def test_two_peaks_on_one_band_neither_is_needed_alone():
    """Like the noisy Raman spectrum: a small band of 3 counts at 413 on an
    offset of 669, two peaks put on it - each alone is enough."""
    x = np.linspace(216, 3849, 1600)
    rng = np.random.default_rng(2)
    y = (669 + gaussian(x, 3, 413, 65) + gaussian(x, 11.4, 3432, 128) + gaussian(x, 6.6, 3202, 96)
         + rng.normal(0, 1, x.size))
    start = [{'id': 'a', 'model': 'Gaussian', 'center': 441, 'amplitude': 2.4, 'width': 60},
             {'id': 'b', 'model': 'Gaussian', 'center': 3364, 'amplitude': 12.5, 'width': 180},
             {'id': 'c', 'model': 'Gaussian', 'center': 359, 'amplitude': 2.5, 'width': 22}]
    m = PeakFittingManager()
    fitted, _ = m.fit_peaks(x, y, start, background='auto')
    m.add_peak_bic(x, y, fitted, start, background='auto')
    words = [needed_text(f['delta_bic'], f.get('remove'))[0] for f in fitted]
    # either one alone is enough: one of them (the less certain) is to be taken out,
    # the other is then needed
    assert sorted([words[0], words[2]]) == ['no', 'yes'] and words[1] == 'yes'
    assert sum(1 for f in fitted if f.get('remove')) == 1
    # one of them removed: the other is needed
    fitted, _ = m.fit_peaks(x, y, start[:2], background='auto')
    m.add_peak_bic(x, y, fitted, start[:2], background='auto')
    assert needed_text(fitted[0]['delta_bic'])[0] == 'yes'


def test_two_not_needed_on_different_places_only_one_is_taken_out():
    """A small band and a broad, low peak beside it: without either, the
    other moves to the band - both look 'not needed', but removing both would
    lose the band. Taken out one at a time: only the broad one."""
    x = np.linspace(216, 3849, 1600)
    rng = np.random.default_rng(2)
    y = (669 + gaussian(x, 3, 413, 65) + gaussian(x, 12.5, 3364, 180)
         + rng.normal(0, 1, x.size))
    start = [{'id': 'a', 'model': 'Gaussian', 'center': 404, 'amplitude': 3, 'width': 61},
             {'id': 'b', 'model': 'Gaussian', 'center': 3363, 'amplitude': 12.5, 'width': 179},
             {'id': 'c', 'model': 'Gaussian', 'center': 627, 'amplitude': 0.47, 'width': 141}]
    m = PeakFittingManager()
    fitted, _ = m.fit_peaks(x, y, start, background='auto')
    m.add_peak_bic(x, y, fitted, start, background='auto')
    n_removed = sum(1 for f in fitted if f.get('remove'))
    words = [needed_text(f['delta_bic'], f.get('remove'), n_removed)[0] for f in fitted]
    assert words[:2] == ['yes', 'yes'] and words[2] == 'no' and fitted[2]['remove'] == 1
    assert 'Judged without the peaks marked no' in needed_text(
        fitted[0]['delta_bic'], None, n_removed)[1]


def test_the_words_and_their_explanation():
    assert needed_text(25.0)[0] == 'yes' and needed_text(5.0)[0] == 'probably'
    assert needed_text(0.5)[0] == 'no' and needed_text(None) == ('', '')
    tip = needed_text(-1.5)[1]
    assert tip.startswith('This peak is not needed.') and '(ΔBIC = -1.5)' in tip
    assert all(len(line) <= 80 for line in tip.split('\n'))


def test_series_and_together_have_it_too():
    spectra = [{'label': f's{i}', 'x_scale': X, 'y_scale': _data(i)} for i in range(3)]
    results = pfs.fit_series_independent(spectra, THREE, parallel={'processing_mode': 'serial'})
    assert all(p['delta_bic'] > 10 for r in results for p in r['peaks'])
    columns, rows = pfs.peaks_long(results, [0])
    assert columns[-2] == 'ΔBIC' and rows[0][-2] > 10
    assert pfs.plain(results)[0]['peaks'][0]['delta_bic'] > 10
    together = pg.fit_global(spectra, THREE)
    d = [r['peaks'][1]['delta_bic'] for r in together]
    assert d[0] > 10 and len(set(d)) == 1                         # one value for the whole fit


def test_the_window_shows_needed_and_copies_it(monkeypatch):
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: None))
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    dlg = PeakFittingDialog(None, spectrum={'label': 'three', 'x_scale': X, 'y_scale': _data(),
                                            'metadata': {}})
    dlg.peaks = [dict(p, color=c) for p, c in zip(THREE, ('#1f77b4', '#ff7f0e', '#2ca02c'))]
    dlg.update_peaks_table()
    t = dlg.peaks_table
    assert t.horizontalHeaderItem(6).text() == 'Needed?' and t.item(0, 6).text() == 'not fitted'
    dlg.perform_fit()
    assert [t.item(r, 6).text() for r in range(3)] == ['yes', 'yes', 'yes']
    assert t.item(0, 6).toolTip().startswith('This peak is needed.')
    dlg.copy_results_to_clipboard()
    lines = QApplication.clipboard().text().splitlines()
    head = lines[0].split('\t')
    assert head[-2:] == ['ΔBIC', 'Fixed / linked']
    assert float(lines[1].split('\t')[head.index('ΔBIC')]) > 10

