"""Data range -> Apply linearization never invents values outside a
spectrum's measured range (found 2026-10-19: two spectra that do not
overlap, limits covering both, linearized -> values up to 4 million where
nothing had been measured). The new points lie on one common grid
(X-min + k*step), so spectra linearized together share their x-values; a
spectrum that does not cover the limits gets only the grid points inside
its data, and the result message names it."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_analysis.spectral_range_manager import SpectralRangeManager
from src.controllers.data_analysis.spectral_range_controller import linearization_note

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _sp(label, x, y):
    return {'label': label, 'x_scale': np.asarray(x, float), 'y_scale': np.asarray(y, float)}


def _manager(lo, hi, step=1.0):
    m = SpectralRangeManager()
    m.x_min, m.x_max, m.x_step, m.apply_linearization = lo, hi, step, True
    return m


def test_overlapping_spectra_get_the_same_x_values():
    xa = np.arange(400.0, 500.01, 0.7)
    xb = np.arange(399.5, 501.0, 1.3)
    a, b = _sp('a', xa, np.sin(xa / 9)), _sp('b', xb, np.cos(xb / 9))
    m = _manager(*m_default([a, b]), step=1.0)
    out = m.apply_ranges_to_spectra([a, b])
    assert np.array_equal(out[0]['x_scale'], out[1]['x_scale'])
    assert m.last_clipped == []
    # interior values: the spline through the data, close to the true curve
    assert np.allclose(out[0]['y_scale'], np.sin(out[0]['x_scale'] / 9), atol=1e-3)


def m_default(spectra):
    return SpectralRangeManager().get_default_range(spectra)     # what Reset fills in


def test_spectra_that_do_not_overlap_are_never_extended():
    xa, xb = np.arange(799.0, 999.0), np.arange(1493.0, 1799.0)
    a = _sp('control_11', xa, 0.3 + 0.5 * np.sin(xa / 30) ** 2)
    b = _sp('high_dose_07', xb, 0.4 + 1.3 * np.cos(xb / 40) ** 2)
    m = _manager(799.0, 1798.0)
    out = {s['label']: s for s in m.apply_ranges_to_spectra([a, b])}
    ca, hb = out['control_11'], out['high_dose_07']
    assert ca['x_scale'][0] == 799.0 and ca['x_scale'][-1] == 998.0 and len(ca['x_scale']) == 200
    assert hb['x_scale'][0] == 1493.0 and hb['x_scale'][-1] == 1798.0
    # nothing far outside the measured values (before: up to 4 million)
    assert ca['y_scale'].max() <= 0.8 + 1e-6 and hb['y_scale'].max() <= 1.7 + 1e-6
    assert [c[0] for c in m.last_clipped] == ['control_11', 'high_dose_07']


def test_a_spectrum_starting_later_keeps_the_common_grid():
    xa = np.arange(400.0, 500.01, 0.5)
    xb = np.arange(410.3, 500.0, 2.0)
    a, b = _sp('a', xa, np.ones_like(xa)), _sp('b', xb, (xb - 410.3) ** 2 / 100)
    m = _manager(400.0, 500.0)
    out = m.apply_ranges_to_spectra([a, b])
    xa_new, xb_new = out[0]['x_scale'], out[1]['x_scale']
    assert xa_new[0] == 400.0 and xa_new[-1] == 500.0
    assert xb_new[0] == 411.0 and xb_new[-1] == 498.0          # inside 410.3 .. 498.3
    assert set(xb_new) <= set(xa_new)                            # the same x-values
    assert [c[0] for c in m.last_clipped] == ['b']


def test_negative_step_and_no_limits():
    x = np.arange(410.3, 500.0, 2.0)
    s = _sp('b', x, np.sqrt(x))
    m = _manager(400.0, 500.0, step=-1.0)
    out = m.apply_ranges_to_spectra([s])[0]['x_scale']
    assert out[0] == 498.0 and out[-1] == 411.0 and np.all(np.diff(out) == -1.0)
    m2 = _manager(None, None, step=1.0)                          # no limits: its own range
    out2 = m2.apply_ranges_to_spectra([s])[0]['x_scale']
    assert out2[0] == 410.3 and m2.last_clipped == []


def test_the_message_names_the_spectra():
    assert linearization_note([], {'x_min': 1, 'x_max': 2}) == ''
    note = linearization_note([('control_11', 799.0, 998.0)], {'x_min': 799.0, 'x_max': 1798.0})
    assert 'control_11 (measured 799–998)' in note and '799–1798' in note
    assert 'no values were invented' in note
    many = linearization_note([(f's{i}', 0, 1) for i in range(8)], {'x_min': 0, 'x_max': 5})
    assert 'and 3 more' in many


def test_apply_from_the_window_reports_it(tmp_path, monkeypatch):
    """The whole path: the user's snapshot situation (two groups of spectra
    that do not overlap), Data range with limits over both and linearization."""
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path))
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    mc = MainController()
    try:
        xa, xb = np.arange(799.0, 999.0), np.arange(1493.0, 1799.0)
        spectra = [_sp('control_11', xa, 0.5 + 0.1 * np.sin(xa / 20)),
                   _sp('high_dose_07', xb, 1.0 + 0.2 * np.cos(xb / 20))]
        for s in spectra:
            s['metadata'] = {}
        mc.original_spectra = list(spectra)
        mc.operations_controller.operations_manager.set_original_spectra(list(spectra)) \
            if hasattr(mc.operations_controller.operations_manager, 'set_original_spectra') else None
        settings = {'ranges': [], 'is_exclude_mode': True, 'apply_linearization': True,
                    'x_step': 1.0, 'x_min': 799.0, 'x_max': 1798.0}
        processed = mc.spectral_range_controller.apply_settings_to_spectra(settings, spectra)
        assert [len(s['x_scale']) for s in processed] == [200, 306]
        assert max(float(np.abs(s['y_scale']).max()) for s in processed) < 1.3
        note = linearization_note(mc.spectral_range_controller.manager.last_clipped, settings)
        assert 'control_11' in note and 'high_dose_07' in note
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()
