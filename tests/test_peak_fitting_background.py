"""Peak Fitting with a background: a spectrum sitting on an offset (e.g. a
noisy Raman spectrum at ~669 counts with a water band of ~15 counts) is
fitted with a Linear background together with the peaks; the peaks' heights
are above it. Automatic (the default) chooses from the data: Linear for such
an offset, None for data that come back to zero (CD with bands up and down,
baseline-corrected spectra). The plot keeps the y range of the data (the
starting peaks do not stretch it) and shows the data as points or as a line.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_analysis.peak_fitting_manager import (
    PeakFittingManager, background_values, initial_background, resolve_background, gaussian,
    voigt)
from src.modules.data_analysis import peak_fitting_series as pfs

app = QApplication.instance() or QApplication([])

# like the user's data: offset 669, a small band at 430, a broad water band
# made of two bands (3200, 3430), integer counts with noise
X = np.linspace(216.0, 3849.0, 1600)
TRUE = [(3.0, 430.0, 65.0), (6.5, 3200.0, 95.0), (11.5, 3430.0, 125.0)]


def _offset_spectrum(seed=1, offset=669.0, slope=0.0):
    rng = np.random.default_rng(seed)
    y = offset + slope * (X - X[0]) + sum(gaussian(X, *p) for p in TRUE)
    return np.round(y + rng.normal(0, 1.0, X.size))


def _r2(y, fit):
    return 1 - np.sum((y - fit) ** 2) / np.sum((y - y.mean()) ** 2)


def test_background_values_and_first_guess():
    bg = {'kind': 'linear', 'x0': 0.0, 'x1': 10.0, 'y0': 1.0, 'y1': 3.0}
    assert np.allclose(background_values(bg, [0, 5, 10]), [1, 2, 3])
    assert np.allclose(background_values(dict(bg, kind='constant'), [0, 10]), [1, 1])
    assert np.allclose(background_values(None, [0, 10]), [0, 0])
    y = _offset_spectrum()
    guess = initial_background(X, y, 'linear')
    assert guess['kind'] == 'linear' and abs(guess['y0'] - 669) < 2
    assert initial_background(X, y, 'none') is None


def _cd_spectrum(seed=2):
    """A CD-like spectrum (nm): a positive band at the short end, two negative
    bands, zero at the long end, a little noise."""
    rng = np.random.default_rng(seed)
    x = np.linspace(190.0, 260.0, 141)
    y = gaussian(x, 8.0, 193.0, 4.0) + gaussian(x, -4.0, 208.0, 5.0) + gaussian(x, -3.5, 222.0, 6.0)
    return x, y + rng.normal(0, 0.05, x.size)


def test_automatic_chooses_linear_for_an_offset_and_none_for_zero_based_data():
    assert resolve_background(X, _offset_spectrum(), 'auto') == 'linear'
    assert resolve_background(X, _offset_spectrum(slope=0.002), 'auto') == 'linear'
    x, y = _cd_spectrum()
    assert resolve_background(x, y, 'auto') == 'none'              # bands up and down
    assert resolve_background(x, y - 0.0, 'auto') == 'none'
    assert resolve_background(x, np.minimum(y, 0), 'auto') == 'none'   # one end at zero
    rng = np.random.default_rng(5)                                   # baseline corrected
    corrected = sum(gaussian(X, *p) for p in TRUE) + rng.normal(0, 1.0, X.size)
    assert resolve_background(X, corrected, 'auto') == 'none'
    # the other kinds are kept as chosen
    for kind in ('none', 'constant', 'linear'):
        assert resolve_background(X, _offset_spectrum(), kind) == kind
    assert initial_background(x, y, 'auto') is None
    assert initial_background(X, _offset_spectrum(), 'auto')['kind'] == 'linear'


def test_cd_spectrum_fits_with_automatic_without_a_background():
    m = PeakFittingManager()
    x, y = _cd_spectrum()
    start = m.auto_detect_peaks(y, x, background='auto')
    fitted, total = m.fit_peaks(x, y, start, background='auto')
    assert fitted is not None and _r2(y, total) > 0.95
    assert m.last_background is None and m.last_background_kind == 'none'


def test_offset_spectrum_fits_with_automatic_as_linear():
    m = PeakFittingManager()
    y = _offset_spectrum()
    start = m.auto_detect_peaks(y, X, background='auto')
    fitted, total = m.fit_peaks(X, y, start, background='auto')
    assert fitted is not None and _r2(y, total) > 0.85
    assert m.last_background_kind == 'linear' and abs(m.last_background['y0'] - 669) < 2


def test_offset_spectrum_fits_with_linear_background():
    m = PeakFittingManager()
    y = _offset_spectrum()
    start = m.auto_detect_peaks(y, X, background='linear')
    assert start, "the bands must be found"
    # heights above the background, not from zero (669 + ...)
    assert all(abs(p['amplitude']) < 30 for p in start)
    fitted, total = m.fit_peaks(X, y, start, background='linear')
    assert fitted is not None
    assert _r2(y, total) > 0.85
    assert abs(m.last_background['y0'] - 669) < 2 and abs(m.last_background['y1'] - 669) < 2
    assert all(f['parameters']['height'] < 30 for f in fitted)


def test_three_bands_and_a_sloped_background():
    m = PeakFittingManager()
    y = _offset_spectrum(seed=3, slope=0.002)
    start = [{'model': 'Gaussian', 'center': c, 'amplitude': a, 'width': w} for a, c, w in TRUE]
    fitted, total = m.fit_peaks(X, y, start, background='linear')
    assert fitted is not None and _r2(y, total) > 0.85
    centres = sorted(f['parameters']['center'] for f in fitted)
    assert np.allclose(centres, [430, 3200, 3430], atol=40)
    slope = (m.last_background['y1'] - m.last_background['y0']) / (X[-1] - X[0])
    assert abs(slope - 0.002) < 0.001


def test_a_height_given_from_zero_is_taken_above_the_background():
    """A peak clicked in an older version (height = the clicked y, ~680)
    still fits: its height is measured above the background."""
    m = PeakFittingManager()
    y = _offset_spectrum()
    start = [{'model': 'Gaussian', 'center': 430.0, 'amplitude': 672.0, 'width': 60.0},
             {'model': 'Gaussian', 'center': 3400.0, 'amplitude': 681.0, 'width': 150.0}]
    fitted, total = m.fit_peaks(X, y, start, background='linear')
    assert fitted is not None and _r2(y, total) > 0.8


def test_no_background_keeps_the_old_behaviour():
    m = PeakFittingManager()
    y = gaussian(X, 5.0, 2000.0, 100.0)
    fitted, total = m.fit_peaks(X, y, [{'model': 'Gaussian', 'center': 1900.0,
                                        'amplitude': 4.0, 'width': 80.0}])
    assert m.last_background is None
    assert abs(fitted[0]['parameters']['height'] - 5.0) < 1e-3


def test_noisy_band_width_is_the_band_not_the_noise():
    m = PeakFittingManager()
    y = _offset_spectrum()
    sigma = m.estimate_width(X, y, 3400.0)
    assert sigma is not None and sigma > 50          # not a point of noise (a few units)


def test_a_click_on_noisy_data_gets_the_band_width_not_a_bump_of_the_noise():
    """Whole-number counts with noise (as measured): a click near the top
    or on the side of a band gets about that band's width - not a bump of
    the noise (a few units); on the flat baseline: None."""
    m = PeakFittingManager()
    y = _offset_spectrum()
    for click in (380.0, 430.0, 470.0):                          # the small band (sigma 65)
        sigma = m.estimate_width(X, y, click)
        assert sigma is not None and 40 < sigma < 100, (click, sigma)
    for click in (3150.0, 3220.0, 3300.0, 3430.0, 3550.0):       # the large one (two bands)
        sigma = m.estimate_width(X, y, click)
        assert sigma is not None and 90 < sigma < 300, (click, sigma)
    assert m.estimate_width(X, y, 1500.0) is None                # flat baseline


def test_one_band_split_by_noise_is_found_once():
    m = PeakFittingManager()
    guesses = [{'model': 'Gaussian', 'center': 391.0, 'amplitude': 3.0, 'width': 80.0},
               {'model': 'Gaussian', 'center': 420.0, 'amplitude': 3.0, 'width': 80.0},
               {'model': 'Gaussian', 'center': 3440.0, 'amplitude': 13.0, 'width': 200.0}]
    merged = m._merge_split(guesses)
    assert [round(g['center']) for g in merged] == [406, 3440]


def test_series_results_carry_the_background():
    spectra = [{'label': f's{i}', 'x_scale': X, 'y_scale': _offset_spectrum(seed=i)}
               for i in range(3)]
    start = [{'model': 'Gaussian', 'center': c, 'amplitude': a, 'width': w} for a, c, w in TRUE]
    results = pfs.fit_series_independent(spectra, start, background='linear',
                                         parallel={'processing_mode': 'serial'})
    assert all(r['ok'] and r['background']['kind'] == 'linear' for r in results)
    total, parts = pfs.model_curves(X, results[0]['peaks'], background=results[0]['background'])
    assert _r2(spectra[0]['y_scale'], total) > 0.85
    assert max(np.max(p) for p in parts) < 30             # the peaks alone, without the 669
    kept = pfs.plain(results)
    assert kept[0]['background']['kind'] == 'linear'
    each, _ = pfs.fit_each(spectra, [start, None, None], background='linear')
    assert all(r['ok'] and r['background'] for r in each)
    # Automatic: each spectrum its own choice (Raman on an offset: Linear; CD: None)
    xc, yc = _cd_spectrum()
    cd = {'label': 'cd', 'x_scale': xc, 'y_scale': yc}
    cd_start = PeakFittingManager().auto_detect_peaks(yc, xc, background='auto')
    mixed = pfs.fit_series_independent([spectra[0], cd], None, starts=[start, cd_start],
                                       background='auto', parallel={'processing_mode': 'serial'})
    assert mixed[0]['background']['kind'] == 'linear' and mixed[1]['background'] is None


def test_outputs_include_the_background_and_voigt_is_right():
    from src.controllers.data_analysis.peak_fitting_controller import PeakFittingController
    ctl = PeakFittingController.__new__(PeakFittingController)
    ctl.manager = PeakFittingManager()
    m = ctl.manager
    params = m.get_peak_properties('Voigt', [2.0, 1000.0, 50.0, 30.0])
    fit = [{'model': 'Voigt', 'parameters': params}]
    bg = {'kind': 'constant', 'x0': X[0], 'x1': X[-1], 'y0': 669.0, 'y1': 669.0}
    total = ctl.compute_total_fit_curve(X, fit, bg)
    assert np.allclose(total, voigt(X, 2.0, 1000.0, 50.0, 30.0) + 669.0, atol=1e-6)
    assert np.allclose(ctl.compute_individual_peak_curves(X, fit)[0],
                       voigt(X, 2.0, 1000.0, 50.0, 30.0), atol=1e-6)


# ---------------------------------------------------------------- the window
@pytest.fixture
def dialog(monkeypatch):
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, 'warning', staticmethod(lambda *a, **k: None))
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog

    def make(settings=None):
        sp = {'label': 'water', 'x_scale': X, 'y_scale': _offset_spectrum(), 'metadata': {}}
        return PeakFittingDialog(None, spectrum=sp, current_settings=settings)
    return make


def test_window_fits_offset_data_with_the_default_automatic_background(dialog):
    dlg = dialog()
    assert dlg.background_combo.currentData() == 'auto'
    assert dlg.background_combo.currentText() == "Automatic (Linear)"   # what it chose
    dlg.auto_detect_peaks()
    dlg.perform_fit()
    assert dlg.fit_results and dlg.fit_background['kind'] == 'linear'
    labels = [ln.get_label() for ln in dlg.ax_main.get_lines()]
    assert 'Background' in labels and 'Total Fit' in labels
    dlg.background_combo.setCurrentIndex(dlg.background_combo.findData('none'))
    assert dlg.background_combo.itemText(dlg.background_combo.findData('auto')) == "Automatic"


def test_window_with_a_cd_spectrum_automatic_is_none(dialog, monkeypatch):
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    x, y = _cd_spectrum()
    dlg = PeakFittingDialog(None, spectrum={'label': 'cd', 'x_scale': x, 'y_scale': y,
                                            'metadata': {}})
    assert dlg.background_combo.currentText() == "Automatic (None)"
    dlg.auto_detect_peaks()
    assert any(p['amplitude'] < 0 for p in dlg.peaks) and any(p['amplitude'] > 0 for p in dlg.peaks)
    dlg.perform_fit()
    assert dlg.fit_results and dlg.fit_background is None
    assert 'Background' not in [ln.get_label() for ln in dlg.ax_main.get_lines()]


def test_starting_peaks_do_not_stretch_the_y_axis(dialog):
    dlg = dialog()
    y = dlg.y_roi
    # a starting peak far too high (e.g. typed in the table)
    dlg.peaks = [{'model': 'Gaussian', 'center': 3400.0, 'amplitude': 700.0, 'width': 150.0,
                  'color': '#1f77b4'}]
    dlg.update_plot()
    lo, hi = dlg.ax_main.get_ylim()
    assert lo >= y.min() - 0.1 * np.ptp(y) and hi <= y.max() + 0.1 * np.ptp(y)


def test_a_clicked_peak_gets_its_height_above_the_background(dialog):
    dlg = dialog()

    class Click:
        inaxes = dlg.ax_main
        button = 1
        xdata = 3430.0
        ydata = 680.0
    dlg.on_canvas_click(Click())
    assert 5 < dlg.peaks[-1]['amplitude'] < 15


def test_a_clicked_peak_with_the_background_subtracted_is_not_negative(dialog):
    """"− background" ticked: the plot is drawn without the background, so
    the clicked height is already the peak's height (not minus ~669 again)."""
    dlg = dialog()
    dlg.subtract_check.setChecked(True)

    class Click:
        inaxes = dlg.ax_main
        button = 1
        xdata = 3430.0
        ydata = 11.0
    dlg.on_canvas_click(Click())
    peak = min(dlg.peaks, key=lambda p: abs(p['center'] - 3430.0))
    assert peak['amplitude'] == 11.0


def test_data_as_points_or_line_is_remembered(dialog):
    dlg = dialog()
    data = [ln for ln in dlg.ax_main.get_lines() if ln.get_label() == 'Original Data'][0]
    assert dlg.data_style_combo.currentData() == 'points' and data.get_linestyle() == 'None'
    dlg.data_style_combo.setCurrentIndex(dlg.data_style_combo.findData('line'))
    data = [ln for ln in dlg.ax_main.get_lines() if ln.get_label() == 'Original Data'][0]
    assert data.get_linestyle() == '-'
    dlg.background_combo.setCurrentIndex(dlg.background_combo.findData('constant'))
    dlg.auto_detect_peaks()
    dlg.perform_fit()
    settings = dlg.get_results()
    assert settings['data_style'] == 'line' and settings['background'] == 'constant'
    again = dialog(settings)
    assert again.data_style_combo.currentData() == 'line'
    assert again.background_combo.currentData() == 'constant'
    assert again.fit_background and again.fit_background['kind'] == 'constant'


def test_fitted_peaks_are_shown_whole_starting_peaks_not(dialog):
    """After a fit the y range also covers the fitted peaks (e.g. CD bands
    partly cancelling each other); before it only the data."""
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    x, y = _cd_spectrum()
    dlg = PeakFittingDialog(None, spectrum={'label': 'cd', 'x_scale': x, 'y_scale': y,
                                            'metadata': {}})
    dlg.auto_detect_peaks()
    dlg.perform_fit()
    lo, hi = dlg.ax_main.get_ylim()
    for line, curve in dlg._peak_lines.values():
        assert lo <= np.min(curve) and np.max(curve) <= hi


def test_closed_before_the_fit_opens_again_with_the_starting_peaks(dialog):
    """OK without Fit Peaks: the starting peaks are kept (and used for the
    outputs on their background) - opened again they are starting peaks, not
    a fit drawn without its background."""
    dlg = dialog()
    dlg.auto_detect_peaks()
    settings = dlg.get_results()
    assert settings['fitted'] is False and settings['fit_results']
    assert settings['fit_background']['kind'] == 'linear'          # the guess, for OK
    again = dialog(settings)
    assert not again.fit_results and again.fit_background is None
    assert again.background_combo.currentText() == "Automatic (Linear)"
    labels = [ln.get_label() for ln in again.ax_main.get_lines()]
    assert 'Total Fit' not in labels and 'Background (guess)' in labels
    lo, hi = again.ax_main.get_ylim()
    assert lo > 600                                                   # not stretched to 0


def test_subtract_background_draws_the_peaks_from_zero(dialog):
    dlg = dialog()
    dlg.auto_detect_peaks()
    dlg.perform_fit()
    dlg.subtract_check.setChecked(True)
    lines = {ln.get_label(): ln for ln in dlg.ax_main.get_lines()}
    assert 'Background' not in lines and 'Original Data − background' in lines
    data = lines['Original Data − background'].get_ydata()
    assert abs(np.median(data)) < 2                                  # 669 taken off
    lo, hi = dlg.ax_main.get_ylim()
    assert lo < 0 < hi < 30
    # only the drawing: the fit and its values stay
    heights = [f['parameters']['height'] for f in dlg.fit_results]
    dlg.subtract_check.setChecked(False)
    assert [f['parameters']['height'] for f in dlg.fit_results] == heights
    assert 'Background' in [ln.get_label() for ln in dlg.ax_main.get_lines()]
    dlg.subtract_check.setChecked(True)
    again = dialog(dlg.get_results())
    assert again.subtract_check.isChecked()
