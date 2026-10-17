"""X-axis alignment: the shifts found in worker processes (like Automated
Baseline) are the same as one after another; count_callback reports
progress; a failing pool falls back to serial."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.modules.data_analysis import xaxis_alignment_manager as xam   # noqa: E402


def _spectra(n=24):
    x = np.linspace(400, 1800, 300)
    out = []
    for i in range(n):
        shift = (i % 7 - 3) * 0.8
        y = np.exp(-((x - 900 - shift) / 20) ** 2) + 0.5 * np.exp(-((x - 1300 - shift) / 30) ** 2)
        out.append({'label': f's{i}', 'x_scale': x.copy(), 'y_scale': y, 'metadata': {}})
    return out


def _shifts(result):
    return np.array([s['xaxis_alignment_info']['shift'] for s in result])


def test_parallel_shifts_equal_serial_shifts():
    sp = _spectra()
    base = {'reference_spectrum_index': 3, 'max_shift': 5.0}
    m1 = xam.XAxisAlignmentManager()
    serial = m1.align_spectra(sp, dict(base, processing_mode='serial'))
    m2 = xam.XAxisAlignmentManager()
    counts = []
    parallel = m2.align_spectra(sp, dict(base, processing_mode='parallel', max_workers=2),
                                count_callback=lambda d, t: counts.append((d, t)))
    assert m2.last_run_info['mode'] == 'parallel', m2.run_summary()
    assert np.allclose(_shifts(serial), _shifts(parallel))
    assert counts[-1] == (23, 23)
    # the shifts are found (reference: spectrum 3, shift 0)
    assert abs(_shifts(serial)[3]) < 1e-12
    assert np.allclose(_shifts(serial)[10], -((10 % 7 - 3) * 0.8 - (3 % 7 - 3) * 0.8), atol=0.05)


def test_short_job_runs_serially_in_auto_mode():
    m = xam.XAxisAlignmentManager()
    m.align_spectra(_spectra(6), {'reference_spectrum_index': 0, 'max_shift': 5.0})
    assert m.last_run_info['mode'] == 'serial'
    assert 'Shifts of 5 spectra' in m.run_summary()


def test_a_failing_pool_finishes_serially(monkeypatch):
    def broken(*a, **k):
        raise OSError('no workers')
    monkeypatch.setattr(xam, 'run_in_process_pool', broken)
    sp = _spectra(10)
    m = xam.XAxisAlignmentManager()
    out = m.align_spectra(sp, {'reference_spectrum_index': 0, 'max_shift': 5.0,
                               'processing_mode': 'parallel', 'max_workers': 2})
    assert m.last_run_info['fallback_reason'] and len(out) == 10
    ref = xam.XAxisAlignmentManager().align_spectra(
        sp, {'reference_spectrum_index': 0, 'max_shift': 5.0, 'processing_mode': 'serial'})
    assert np.allclose(_shifts(out), _shifts(ref))
