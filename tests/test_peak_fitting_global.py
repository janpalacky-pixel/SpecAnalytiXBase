"""Peak Fitting: several spectra fitted together (a global fit) - one set of
peaks, the same positions and widths (or only the same widths) for all,
every spectrum its own heights and background. For a noisy series far more
stable than fitting each spectrum alone."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_analysis.peak_fitting_manager import PeakFittingManager, gaussian
from src.modules.data_analysis import peak_fitting_global as pg
from src.modules.data_analysis import peak_fitting_series as pfs

app = QApplication.instance() or QApplication([])
X = np.linspace(0, 200, 800)
START = [{'id': 'p1', 'model': 'Gaussian', 'center': 62.0, 'amplitude': 1.0, 'width': 5.0},
         {'id': 'p2', 'model': 'Gaussian', 'center': 74.0, 'amplitude': 2.0, 'width': 6.0},
         {'id': 'p3', 'model': 'Gaussian', 'center': 141.0, 'amplitude': 1.0, 'width': 8.0}]


def _series(n=12, noise=0.2, shift=0.0, offset=0.3, seed=1):
    """Band 1 grows, band 2 shrinks (as with temperature), band 3 stays;
    noisy, on an offset."""
    rng = np.random.default_rng(seed)
    return [{'label': f'scan : {i + 1:02d}', 'x_scale': X,
             'y_scale': gaussian(X, 1 + 0.1 * i, 60 + shift * i, 5)
             + gaussian(X, 2 - 0.05 * i, 75, 6) + gaussian(X, 1.0, 140, 8) + offset
             + rng.normal(0, noise, X.size)} for i in range(n)]


def _value(res, k, key):
    return res['peaks'][k]['parameters'][key]


def test_the_same_positions_and_widths_for_all_heights_each():
    spectra = _series()
    results = pg.fit_global(spectra, START, share='positions')
    assert all(r['ok'] and r['global'] == 'positions' for r in results)
    centres = [_value(r, 0, 'center') for r in results]
    assert np.ptp(centres) == 0 and centres[0] == pytest.approx(60, abs=0.2)
    assert _value(results[0], 2, 'sigma') == pytest.approx(8, abs=0.2)
    heights = [_value(r, 0, 'height') for r in results]
    assert np.allclose(heights, [1 + 0.1 * i for i in range(12)], atol=0.08)
    assert all(r['background']['kind'] == 'linear'
               and r['background']['y0'] == pytest.approx(0.3, abs=0.1) for r in results)
    assert all(r['r2'] > 0.8 for r in results)


def test_together_is_more_precise_than_each_alone():
    spectra = _series(noise=0.4)
    together = pg.fit_global(spectra, START, share='positions')
    alone = pfs.fit_series_independent(spectra, START, background='auto',
                                       parallel={'processing_mode': 'serial'})
    err_t = together[0]['peaks'][0]['errors']['center']
    err_a = np.mean([r['peaks'][0]['errors']['center'] for r in alone if r['ok']])
    assert err_t < err_a / 2                   # 12 spectra: about sqrt(12) times better
    # and the errors say the truth: the centre within 3 sigma of 60
    assert abs(_value(together[0], 0, 'center') - 60) < 3 * err_t


def test_the_same_widths_lets_the_bands_shift():
    spectra = _series(shift=0.5)                         # band 1: 60, 60.5, ... 65.5
    results = pg.fit_global(spectra, START, share='widths')
    centres = [_value(r, 0, 'center') for r in results]
    assert np.allclose(centres, [60 + 0.5 * i for i in range(12)], atol=0.4)
    widths = {round(_value(r, 0, 'sigma'), 9) for r in results}
    assert len(widths) == 1                               # one width for all


def test_fixed_and_linked_values_apply_to_all_spectra():
    spectra = _series(6)
    start = [dict(p) for p in START]
    start[2] = dict(start[2], center=140.0, constraints={'center': {'kind': 'fixed'}})
    start[1] = dict(start[1], constraints={'width': {'kind': 'link', 'peak': 'p1'}})
    results = pg.fit_global(spectra, start, share='positions')
    for r in results:
        assert _value(r, 2, 'center') == 140.0 and r['peaks'][2]['errors']['center'] == 0
        assert _value(r, 1, 'sigma') == pytest.approx(_value(r, 0, 'sigma'))


def test_positive_peaks_only_and_a_cd_like_series_without_background():
    rng = np.random.default_rng(3)
    x = np.linspace(190, 260, 141)
    cd = [{'label': f'cd{i}', 'x_scale': x,
           'y_scale': gaussian(x, 8 - i, 193, 4) + gaussian(x, -4 + 0.3 * i, 208, 5)
           + gaussian(x, -3.5, 222, 6) + rng.normal(0, 0.05, x.size)} for i in range(5)]
    start = [{'model': 'Gaussian', 'center': 194, 'amplitude': 8, 'width': 4},
             {'model': 'Gaussian', 'center': 207, 'amplitude': -4, 'width': 5},
             {'model': 'Gaussian', 'center': 223, 'amplitude': -3, 'width': 6}]
    results = pg.fit_global(cd, start, share='positions')
    assert all(r['ok'] and r['background'] is None for r in results)     # Automatic: None
    assert [round(_value(r, 1, 'height'), 1) for r in results] == [-4.0, -3.7, -3.4, -3.1, -2.8]
    raman = _series(4)
    pos = pg.fit_global(raman, START, share='positions',
                        amplitude_constraints=['positive'] * 4)
    assert all(_value(r, k, 'height') >= 0 for r in pos for k in range(3))


def test_results_work_like_a_series_and_are_kept():
    results = pg.fit_global(_series(4), START)
    columns, rows = pfs.series_table(results, 3)
    assert len(rows) == 4 and rows[0][2] > 0                 # position ± from the global fit
    kept = pfs.plain(results)
    assert kept[0]['global'] == 'positions'
    assert 'fitted together' in pfs.summary(results)


def test_nothing_to_fit():
    assert not any(r['ok'] for r in pg.fit_global(_series(2), []))


# ---------------------------------------------------------------- the window
def test_window_fits_the_selected_spectra_together(monkeypatch):
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: None))
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    spectra = _series(6)
    dlg = PeakFittingDialog(None, spectrum=spectra[0], series=spectra)
    assert dlg.together_combo.isVisibleTo(dlg) and dlg.together() == 'each'
    dlg.peaks = [dict(p, color=c) for p, c in zip(START, ('#1f77b4', '#ff7f0e', '#2ca02c'))]
    dlg.update_peaks_table()
    dlg.together_combo.setCurrentIndex(dlg.together_combo.findData('positions'))
    assert not dlg.follow_check.isEnabled()
    dlg.list_all_button.click()
    assert dlg.fit_button.text() == 'Fit Peaks – 6 spectra together'
    assert 'fitted together from the peaks of 01' in dlg.no_peaks_hint.text()
    dlg.fit_selected()
    assert all(r['ok'] and r['global'] == 'positions' for r in dlg.series_results)
    assert 'fitted together' in dlg.series_info.text()
    # every spectrum got its fitted peaks as its own
    assert all(len(dlg.peaks_of(r)) == 3 for r in range(6))
    settings = dlg.get_results()
    assert settings['together'] == 'positions'
    again = PeakFittingDialog(None, spectrum=spectra[0], series=spectra,
                              current_settings=settings)
    assert again.together() == 'positions' and again.series_results[3]['global'] == 'positions'


def test_window_one_spectrum_has_no_together_choice():
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = _series(1)
    dlg = PeakFittingDialog(None, spectrum=sp[0])
    assert not dlg.together_combo.isVisibleTo(dlg) and dlg.together() == 'each'
