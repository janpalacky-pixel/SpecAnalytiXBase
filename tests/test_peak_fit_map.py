"""Peak-fit maps: one band fitted in every pixel of a 2D map
(peak_fit_map.py, Map2DManager, the 2D Map dialog's Fitted … metrics)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QDialog

from src.modules.visualization_analysis import peak_fit_map as pf
from src.modules.visualization_analysis.map2d_manager import Map2DManager

app = QApplication.instance() or QApplication([])
X = np.arange(950.0, 1050.0, 1.7)


def _band(center=1001.3, fwhm=12.0, height=500.0, shape='Gaussian', eta=0.4,
          offset=20.0, slope=0.3, noise=5.0, seed=0):
    rng = np.random.default_rng(seed)
    return (height * pf.peak_shape(X, center, fwhm, shape, eta) + offset + slope * (X - 1000)
            + rng.normal(0, noise, len(X)))


# --- single fits ---------------------------------------------------------------

@pytest.mark.parametrize('shape', pf.SHAPES)
def test_fit_recovers_the_true_band(shape):
    r = pf.fit_single_peak(X, _band(shape=shape), shape, 'Linear')
    assert r['ok']
    assert r['center'] == pytest.approx(1001.3, abs=0.3)       # far below the 1.7 data spacing
    assert r['fwhm'] == pytest.approx(12.0, rel=0.03)
    assert r['height'] == pytest.approx(500, rel=0.03)
    assert r['area'] == pytest.approx(pf.peak_area(500, 12, shape, 0.4), rel=0.03)
    assert r['r2'] > 0.99
    assert (r['eta'] == pytest.approx(0.4, abs=0.1)) if shape == 'Pseudo-Voigt' else np.isnan(r['eta'])


def test_position_is_more_precise_than_the_highest_point():
    """The reason for the feature: a shift smaller than the data spacing."""
    shifts = np.linspace(0, 1.5, 7)
    fitted = [pf.fit_single_peak(X, _band(center=1000 + s, noise=2, seed=i))['center']
              for i, s in enumerate(shifts)]
    assert np.allclose(np.array(fitted) - 1000, shifts, atol=0.15)
    highest = [X[np.argmax(_band(center=1000 + s, noise=2, seed=i))] for i, s in enumerate(shifts)]
    assert len(set(highest)) <= 2                               # quick metric barely moves


def test_negative_band_and_background_options():
    y = -30 * pf.peak_shape(X, 990, 15, 'Gaussian') + np.random.default_rng(3).normal(0, 0.5, len(X))
    r = pf.fit_single_peak(X, y, 'Gaussian', 'None')
    assert r['ok'] and r['height'] == pytest.approx(-30, rel=0.05) and r['center'] == pytest.approx(990, abs=0.3)
    r = pf.fit_single_peak(X, y + 100, 'Gaussian', 'Constant')
    assert r['ok'] and r['center'] == pytest.approx(990, abs=0.3)


def test_unusable_windows_are_rejected_not_guessed():
    out_of_window = 100 * pf.peak_shape(X, 1065, 10, 'Gaussian')
    r = pf.fit_single_peak(X, out_of_window)
    assert not r['ok'] and 'edge' in r['reason'] and np.isnan(r['center'])
    assert not pf.fit_single_peak(X[:4], X[:4])['ok']                      # too few points
    assert not pf.fit_single_peak(X, np.zeros_like(X), baseline='None')['ok']   # flat
    y = _band(); y[5] = np.nan
    assert pf.fit_single_peak(X, y)['ok']                                    # a NaN is skipped


def test_a_band_wider_than_the_window_is_rejected():
    """Noise (or background) fitted as one broad hump -- seen on real map
    pixels without a band -- must not produce a value (it gave huge areas)."""
    rng = np.random.default_rng(5)
    hump = 30 * pf.peak_shape(X, 1000, 120, 'Gaussian') + rng.normal(0, 3, len(X))
    r = pf.fit_single_peak(X, hump, 'Gaussian', 'Linear')
    assert not r['ok'] and r['reason'] == 'band wider than the window' and np.isnan(r['area'])
    assert pf.fit_single_peak(X, _band())['ok']                  # a real band still passes


def test_model_curve_matches_the_fit():
    y = _band()
    r = pf.fit_single_peak(X, y)
    curve, base = pf.model_curve(X, r, 'Gaussian', 'Linear')
    assert np.sqrt(np.mean((curve - y) ** 2)) < 7
    assert base[0] < base[-1]                                   # the sloping background
    assert pf.model_curve(X, pf._nan_result(), 'Gaussian', 'Linear') == (None, None)


def test_settings_are_sanitized():
    s = pf.normalized_settings({'shape': 'Weird', 'baseline': 'x', 'min_r2': '7',
                                'processing_mode': 'fast', 'unknown': 1})
    assert s == dict(pf.DEFAULT_SETTINGS, min_r2=1.0)


# --- many pixels ----------------------------------------------------------------

def _windows(n=12, seed=0):
    rng = np.random.default_rng(seed)
    return [(X, _band(center=1000 + rng.normal(0, 2), seed=i)) for i in range(n)]


def test_mapper_caches_and_switches_metrics_without_refitting(monkeypatch):
    mapper = pf.PeakFitMapper()
    calls = []
    real = pf.fit_single_peak
    monkeypatch.setattr(pf, 'fit_single_peak', lambda *a, **k: calls.append(1) or real(*a, **k))
    w = _windows()
    pos = mapper.values('Fitted peak position', w, {'processing_mode': 'serial'})
    width = mapper.values('Fitted FWHM', w, {'processing_mode': 'serial'})
    assert len(calls) == len(w)                                 # fitted once for both
    assert np.all(np.abs(pos - 1000) < 8) and np.all(np.abs(width - 12) < 1.5)
    mapper.values('Fitted FWHM', w, {'processing_mode': 'serial', 'shape': 'Lorentzian'})
    assert len(calls) == 2 * len(w)                             # other shape -> refit
    assert 'Fitted 12 of 12 pixels' in mapper.summary()


def test_min_r2_blanks_poor_fits():
    w = _windows(6) + [(X, np.random.default_rng(9).normal(0, 1, len(X)))]   # last: noise only
    mapper = pf.PeakFitMapper()
    all_fits = mapper.values('Fitted peak area', w, {'processing_mode': 'serial'})
    filtered = mapper.values('Fitted peak area', w, {'processing_mode': 'serial', 'min_r2': 0.8})
    assert np.all(np.isfinite(filtered[:6])) and np.isnan(filtered[6])
    r2 = mapper.values('Fit quality (R²)', w, {'processing_mode': 'serial'})
    assert r2[6] < 0.8 < r2[:6].min()
    assert np.isfinite(all_fits[:6]).all()


def test_cancel_stops_and_caches_nothing():
    mapper = pf.PeakFitMapper()

    def progress(done, total):
        if done >= 3:
            raise pf.OperationCancelled()
    with pytest.raises(pf.OperationCancelled):
        mapper.results(_windows(), {'processing_mode': 'serial'}, progress)
    assert mapper._caches == {}


def test_parallel_gives_the_same_numbers_as_serial():
    w = _windows(40)
    serial = pf.PeakFitMapper().results(w, {'processing_mode': 'serial'})
    mapper = pf.PeakFitMapper()
    parallel = mapper.results(w, {'processing_mode': 'parallel', 'max_workers': 2})
    for key in ('center', 'fwhm', 'area', 'r2'):
        assert np.array_equal(serial[key], parallel[key])
    info = mapper.last_run_info
    assert info['mode'] == 'parallel' or info['note'] or info['fallback_reason']


# --- Map2DManager ---------------------------------------------------------------

def _map_spectra(n_rows=3, n_cols=4):
    out = []
    for r in range(n_rows):
        for c in range(n_cols):
            y = _band(center=995 + 2 * c, height=300 + 50 * r, seed=r * 10 + c, noise=2)
            out.append({'x_scale': X.copy(), 'y_scale': y, 'label': f'p{r}{c}'})
    return out


def test_manager_maps_the_fitted_values():
    mgr = Map2DManager()
    mgr.peak_fit_settings = dict(pf.DEFAULT_SETTINGS, processing_mode='serial')
    spectra = _map_spectra()
    pos = mgr.compute_intensity_map(spectra, 3, 4, metric='Fitted peak position',
                                    include_ranges=[[960, 1040]])
    assert pos.shape == (3, 4)
    assert np.allclose(pos, np.array([[995, 997, 999, 1001]] * 3), atol=0.4)
    height = mgr.compute_intensity_map(spectra, 3, 4, metric='Fitted peak height',
                                       include_ranges=[[960, 1040]])
    assert np.allclose(height[:, 0], [300, 350, 400], rtol=0.03)
    ratio = mgr.compute_arithmetic_map(
        spectra, 3, 4, metric_a='Fitted peak area', metric_b='Fitted peak area',
        include_ranges_a=[[960, 1040]], include_ranges_b=[[955, 1045]], operation='A / B')
    assert np.allclose(ratio, 1.0, atol=0.03)
    assert mgr.metric == 'Fitted peak height' or mgr.map_mode == 'arithmetic'


# --- the dialog -----------------------------------------------------------------

@pytest.fixture
def dialog(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    from src.controllers.visualization_analysis.map2d_controller import Map2DController
    from src.views.dialogs.visualization_analysis.map2d_dialog import Map2DDialog

    class _Main:
        view = None
    controller = Map2DController(_Main())
    spectra = _map_spectra()
    dlg = Map2DDialog(None, controller, spectra)
    dlg._rows_spin.setValue(3)
    dlg._cols_spin.setValue(4)
    dlg._ranges = [[960, 1040]]
    dlg._is_exclude = False
    controller.manager.peak_fit_settings['processing_mode'] = 'serial'
    yield dlg
    dlg.deleteLater()


def test_dialog_lists_the_fitted_metrics_and_draws_a_map(dialog):
    items = [dialog._metric_combo.itemText(i) for i in range(dialog._metric_combo.count())]
    for name in pf.FITTED_METRICS:
        assert name in items
    assert dialog._peak_fit_btn.isHidden()
    dialog._radio_intensity.setChecked(True)
    dialog._metric_combo.setCurrentText('Fitted peak position')
    assert not dialog._peak_fit_btn.isHidden()
    dialog._compute_map()
    assert dialog._last_map_data.shape == (3, 4)
    assert np.allclose(dialog._last_map_data[0], [995, 997, 999, 1001], atol=0.4)
    assert 'Fitted 12 of 12 pixels' in dialog._click_info_label.text()

    class _Event:
        inaxes = dialog._map_canvas.ax
        xdata, ydata, button = 2.0, 1.0, 1
    dialog._ranges = [[985, 1015]]          # a narrower band, so zooming is visible
    dialog._on_map_click(_Event())
    lines = [l.get_label() for l in dialog._spectrum_canvas.ax.get_lines()]
    assert 'Gaussian fit' in lines and 'background' in lines

    # zoomed to the band by default; "Full spectrum" shows everything
    ax = dialog._spectrum_canvas.ax
    cb = dialog._svd_full_range_cb
    assert not cb.isHidden() and not cb.isChecked()
    zoom = ax.get_xlim()
    assert zoom == pytest.approx((970, 1030), abs=2)          # band 985-1015 + half its width
    cb.setChecked(True)
    full = ax.get_xlim()
    assert full[0] <= X.min() and full[1] >= X.max()
    cb.setChecked(False)
    assert ax.get_xlim() == pytest.approx(zoom)
    dialog._metric_combo.setCurrentText('Integral')          # quick metric: checkbox hidden
    assert cb.isHidden()


def test_settings_dialog_changes_are_remembered_and_refit(dialog, monkeypatch):
    from src.views.dialogs.visualization_analysis import peak_fit_settings_dialog as sd
    dialog._radio_intensity.setChecked(True)
    dialog._metric_combo.setCurrentText('Fitted FWHM')
    dialog._compute_map()
    before = dialog._last_map_data.copy()

    def fake_exec(self):
        self.shape_combo.setCurrentText('Lorentzian')
        self.mode_combo.setCurrentIndex(1)
        return QDialog.Accepted
    monkeypatch.setattr(sd.PeakFitSettingsDialog, 'exec_', fake_exec)
    dialog._edit_peak_fit_settings()
    assert dialog.controller.manager.peak_fit_settings['shape'] == 'Lorentzian'
    assert sd.load_settings()['shape'] == 'Lorentzian'                 # remembered
    assert not np.allclose(dialog._last_map_data, before)              # refitted


def test_dialog_cancel_keeps_the_previous_map(dialog, monkeypatch):
    dialog._radio_intensity.setChecked(True)
    dialog._metric_combo.setCurrentText('Integral')
    dialog._compute_map()
    previous = dialog._last_map_data.copy()
    mgr = dialog.controller.manager

    def boom(*a, **k):
        raise pf.OperationCancelled()
    monkeypatch.setattr(mgr.peak_fit, 'values', boom)
    dialog._metric_combo.blockSignals(True)
    dialog._metric_combo.setCurrentText('Fitted peak area')
    dialog._metric_combo.blockSignals(False)
    dialog._compute_map()
    assert np.array_equal(dialog._last_map_data, previous)
    assert 'cancelled' in dialog._click_info_label.text()
    assert mgr.peak_fit_progress is None


def test_help_shows_peak_fit_screenshots_only_when_they_exist(monkeypatch):
    from src.help import map2d_help
    html = map2d_help.get_map2d_help_content()
    assert '$PEAK_FIT' not in html and 'id="peak-fit"' in html
    real_isfile = map2d_help.os.path.isfile
    monkeypatch.setattr(map2d_help.os.path, 'isfile',
                        lambda p: 'peak_fit_' in str(p) or real_isfile(p))
    html = map2d_help.get_map2d_help_content()
    for name in ('peak_fit_settings.png', 'peak_fit_map_result.png', 'peak_fit_pixel_fit.png'):
        assert name in html


def test_pixels_without_a_value_are_hatched_grey(dialog):
    from src.views.dialogs.visualization_analysis.map2d_dialog import NO_VALUE_COLOR
    data = np.arange(12, dtype=float).reshape(3, 4)
    data[1, 2] = np.nan
    dialog._map_canvas.update_map(data)
    patch = dialog._map_canvas.ax.patch
    assert patch.get_hatch() == '////'
    import matplotlib.colors as mcolors
    assert mcolors.to_hex(patch.get_facecolor()) == NO_VALUE_COLOR


def test_progress_comes_in_small_steps():
    from src.modules.utils.parallel_utils import chunk_count
    assert chunk_count(21000, 20) == 200             # ~0.5 % per step, not 80 big ones
    assert chunk_count(21000, 61) == 244
    assert chunk_count(50, 20) == 50 and chunk_count(1, 4) == 1
