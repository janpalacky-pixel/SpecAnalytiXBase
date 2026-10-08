# tests/test_parallel_baseline.py
#
# Automated Baseline: serial vs parallel processing. The central promise
# is that the processing mode only changes the SPEED, never the numbers,
# so most tests compare a serial and a parallel run bit for bit.

import os

import numpy as np
import pytest

import src.modules.data_analysis.automated_baseline_manager as abm
from src.modules.data_analysis.automated_baseline_manager import (
    AutomatedBaselineManager, _baseline_chunk_worker)
from src.modules.utils import parallel_utils
from src.modules.utils.parallel_utils import (
    limited_blas_threads, resolve_worker_count, safe_worker_count)

ALL_ALGORITHMS = ['als', 'airpls', 'arpls', 'iarpls', 'aspls', 'drpls', 'psalsa',
                  'imodpoly', 'morphological', 'mpls', 'mollification', 'mpspline',
                  'jbcd']


def _spectra(n=7, points=300, different_x_every=0):
    """n synthetic spectra: peaks on a curved baseline. If
    different_x_every is set, every such spectrum gets its own x axis (so
    the worker payload cannot share one axis per chunk)."""
    rng = np.random.default_rng(42)
    out = []
    for i in range(n):
        lo = 200.0 + (3.0 * i if different_x_every and i % different_x_every == 0 else 0.0)
        x = np.linspace(lo, 3200.0, points)
        y = (0.002 * x + 0.5 * np.sin(x / 700.0) + 2.0
             + 3.0 * np.exp(-((x - 1000 - 20 * i) / 25.0) ** 2)
             + 1.5 * np.exp(-((x - 2200) / 40.0) ** 2)
             + rng.normal(0, 0.02, points))
        out.append({'label': f's{i}', 'x_scale': x, 'y_scale': y, 'metadata': {}})
    return out


def _run(spectra, **settings):
    mgr = AutomatedBaselineManager()
    result = mgr.apply_correction(spectra, settings)
    return mgr, result


def _assert_same_numbers(a, b):
    assert len(a) == len(b)
    for sa, sb in zip(a, b):
        assert sa['label'] == sb['label']
        assert np.array_equal(sa['y_scale'], sb['y_scale'])
        ha = sa['metadata']['correction_history'][-1]
        hb = sb['metadata']['correction_history'][-1]
        assert ha['success'] == hb['success']


# --------------------------------------------------------------------------
# serial == parallel
# --------------------------------------------------------------------------

@pytest.mark.parametrize('algorithm', ['als', 'imodpoly', 'jbcd'])
def test_parallel_gives_identical_numbers(algorithm):
    spectra = _spectra(n=7, different_x_every=3)
    ranges = [(900.0, 1300.0)]
    _, serial = _run(spectra, algorithm=algorithm, processing_mode='serial',
                     fitting_ranges=ranges, invert_regions=True)
    mgr, parallel = _run(spectra, algorithm=algorithm, processing_mode='parallel',
                         max_workers=2, fitting_ranges=ranges, invert_regions=True)
    assert mgr.last_run_info['mode'] == 'parallel', mgr.last_run_info
    assert mgr.last_run_info['workers'] == 2
    _assert_same_numbers(serial, parallel)


@pytest.mark.parametrize('algorithm', ALL_ALGORITHMS)
def test_worker_function_matches_serial_for_every_algorithm(algorithm):
    """The worker entry point (called in-process here, no pool) must give
    exactly what the serial path gives, for every algorithm."""
    spectra = _spectra(n=3, points=200)
    cfg = {'lam': 1e5, 'p': 0.02, 'eta': 0.5, 'n_iter': 20, 'poly_order': 3,
           'alpha': 0.1, 'beta': 10.0, 'fitting_ranges': [(1500.0, 1800.0)],
           'invert_regions': False}
    mgr = AutomatedBaselineManager()
    expected = [mgr._baseline_for_spectrum(algorithm, s['x_scale'], s['y_scale'].copy(), cfg)
                for s in spectra]
    got = _baseline_chunk_worker((algorithm, cfg, spectra[0]['x_scale'], None,
                                  [s['y_scale'] for s in spectra]))
    for e, g in zip(expected, got):
        assert np.array_equal(e, g, equal_nan=True)


def test_progress_callback_runs_while_waiting_for_workers():
    calls = []
    mgr = AutomatedBaselineManager()
    mgr.apply_correction(_spectra(n=6), {'algorithm': 'als', 'processing_mode': 'parallel',
                                         'max_workers': 2},
                         progress_callback=lambda: calls.append(1))
    assert mgr.last_run_info['mode'] == 'parallel'
    assert len(calls) >= 1


def test_status_callback_announces_the_workers():
    texts = []
    AutomatedBaselineManager().apply_correction(
        _spectra(n=4), {'algorithm': 'als', 'processing_mode': 'parallel', 'max_workers': 2},
        status_callback=texts.append)
    assert any('parallel workers' in t for t in texts)


# --------------------------------------------------------------------------
# serial mode, fallback, auto decision
# --------------------------------------------------------------------------

def test_serial_mode_never_starts_a_pool(monkeypatch):
    def boom(*a, **k):
        raise AssertionError('a pool must not be started in serial mode')
    monkeypatch.setattr(abm, 'run_in_process_pool', boom)
    mgr, _ = _run(_spectra(n=5), algorithm='als', processing_mode='serial')
    assert mgr.last_run_info['mode'] == 'serial'
    assert mgr.last_run_info['fallback_reason'] is None


def test_failed_pool_falls_back_to_serial_with_same_result(monkeypatch):
    spectra = _spectra(n=5)
    _, expected = _run(spectra, algorithm='als', processing_mode='serial')

    def broken_pool(*a, **k):
        raise OSError('the paging file is too small (simulated)')
    monkeypatch.setattr(abm, 'run_in_process_pool', broken_pool)
    monkeypatch.setattr(abm, 'resolve_worker_count', lambda requested=None: 2)
    mgr, got = _run(spectra, algorithm='als', processing_mode='parallel')
    assert mgr.last_run_info['mode'] == 'serial'
    assert 'paging file' in mgr.last_run_info['fallback_reason']
    assert 'redone serially' in mgr.run_summary()
    _assert_same_numbers(expected, got)


def test_algorithm_error_is_not_swallowed_by_the_fallback(monkeypatch):
    def bad(self, *a, **k):
        raise ValueError('algorithm bug')
    monkeypatch.setattr(AutomatedBaselineManager, 'calculate_als_baseline', bad)
    monkeypatch.setattr(abm, 'run_in_process_pool',
                        lambda *a, **k: (_ for _ in ()).throw(ValueError('algorithm bug')))
    monkeypatch.setattr(abm, 'resolve_worker_count', lambda requested=None: 2)
    with pytest.raises(ValueError, match='algorithm bug'):
        _run(_spectra(n=4), algorithm='als', processing_mode='parallel')


def test_auto_stays_serial_for_a_short_job(monkeypatch):
    monkeypatch.setattr(abm, 'run_in_process_pool',
                        lambda *a, **k: pytest.fail('pool started for a short job'))
    monkeypatch.setattr(abm, 'resolve_worker_count', lambda requested=None: 4)
    mgr, _ = _run(_spectra(n=20), algorithm='als')          # default mode is auto
    assert mgr.last_run_info['requested_mode'] == 'auto'
    assert mgr.last_run_info['mode'] == 'serial'
    assert 'would not pay off' in mgr.last_run_info['note']


def test_auto_switches_to_parallel_for_a_long_job(monkeypatch):
    spectra = _spectra(n=12)
    _, expected = _run(spectra, algorithm='als', processing_mode='serial')
    monkeypatch.setattr(abm, 'resolve_worker_count', lambda requested=None: 2)
    monkeypatch.setattr(abm, '_AUTO_MIN_SERIAL_SECONDS', 0.0)
    monkeypatch.setattr(abm, '_POOL_STARTUP_SECONDS', 0.0)
    mgr, got = _run(spectra, algorithm='als', processing_mode='auto')
    assert mgr.last_run_info['mode'] == 'parallel'
    _assert_same_numbers(expected, got)      # incl. the 3 timed serially first


def test_one_worker_or_one_spectrum_means_serial(monkeypatch):
    monkeypatch.setattr(abm, 'resolve_worker_count', lambda requested=None: 1)
    mgr, _ = _run(_spectra(n=4), algorithm='als', processing_mode='parallel')
    assert mgr.last_run_info['mode'] == 'serial'
    # ... and the user is told WHY, with the numbers behind it
    summary = mgr.run_summary()
    assert 'Ran serially: only one worker is available (' in summary
    assert 'CPU cores' in summary
    monkeypatch.setattr(abm, 'resolve_worker_count', lambda requested=None: 4)
    mgr, _ = _run(_spectra(n=1), algorithm='als', processing_mode='parallel')
    assert mgr.last_run_info['mode'] == 'serial'


def test_unknown_processing_mode_is_treated_as_auto():
    mgr, _ = _run(_spectra(n=3), algorithm='als', processing_mode='turbo')
    assert mgr.last_run_info['requested_mode'] == 'auto'


def test_run_summary_text():
    mgr, _ = _run(_spectra(n=3), algorithm='als', processing_mode='serial')
    text = mgr.run_summary()
    assert text.startswith('Computed 3 spectra in ') and text.endswith(' s (serial).')
    assert AutomatedBaselineManager().run_summary() == ''


# --------------------------------------------------------------------------
# parallel_utils
# --------------------------------------------------------------------------

def test_safe_worker_count_leaves_a_core_free_on_bigger_machines():
    assert safe_worker_count(cpu_count=16, available_mb=None) == 15
    assert safe_worker_count(cpu_count=4, available_mb=None) == 3
    assert safe_worker_count(cpu_count=2, available_mb=None) == 2
    assert safe_worker_count(cpu_count=1, available_mb=None) == 1


def test_safe_worker_count_is_limited_by_free_memory():
    # (4096 - 1024) / 200 = 15 ; (1500 - 1024) / 200 = 2 ; nothing free -> still 1
    assert safe_worker_count(cpu_count=32, available_mb=4096) == 15
    assert safe_worker_count(cpu_count=32, available_mb=1500) == 2
    assert safe_worker_count(cpu_count=32, available_mb=100) == 1


def test_resolve_worker_count_honours_request_but_not_beyond_cores(monkeypatch):
    monkeypatch.setattr(parallel_utils.os, 'cpu_count', lambda: 8)
    monkeypatch.setattr(parallel_utils, '_available_memory_mb', lambda: None)
    assert resolve_worker_count(None) == 7
    assert resolve_worker_count(0) == 7
    assert resolve_worker_count(3) == 3
    assert resolve_worker_count(50) == 8


def test_blas_thread_limit_is_restored():
    names = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')
    saved = {n: os.environ.get(n) for n in names}
    try:
        os.environ['OMP_NUM_THREADS'] = '6'
        os.environ.pop('OPENBLAS_NUM_THREADS', None)
        with limited_blas_threads():
            assert all(os.environ[n] == '1' for n in names)
        assert os.environ['OMP_NUM_THREADS'] == '6'
        assert 'OPENBLAS_NUM_THREADS' not in os.environ
    finally:
        for n, v in saved.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v


def test_describe_worker_limits_names_cores_memory_and_result(monkeypatch):
    monkeypatch.setattr(parallel_utils.os, 'cpu_count', lambda: 8)
    monkeypatch.setattr(parallel_utils, '_available_memory_mb', lambda: 1100.0)
    text = parallel_utils.describe_worker_limits()
    assert text == '8 CPU cores, 1.1 GB free memory -> 1 worker'


def test_windows_free_memory_takes_the_larger_of_physical_and_commit():
    mb = 1024 * 1024
    # browsers committed almost everything (commit nearly used up) but 3.5 GB of RAM is free
    assert parallel_utils._windows_available_mb(3500 * mb, 1200 * mb) == 3500
    # the reverse: little RAM free, a large page file still uncommitted
    assert parallel_utils._windows_available_mb(800 * mb, 6000 * mb) == 6000
    # the case from the 32 GB test machine: 3.5 GB free RAM -> (3500-1024)/200 = 12 workers
    assert safe_worker_count(cpu_count=20, available_mb=3500) == 12


# --------------------------------------------------------------------------
# progress bar and Cancel
# --------------------------------------------------------------------------

from src.modules.utils.progress_utils import OperationCancelled


def _collect_progress(spectra, **settings):
    seen = []
    mgr = AutomatedBaselineManager()
    mgr.apply_correction(spectra, settings, progress=lambda done, total: seen.append((done, total)))
    return mgr, seen


def test_serial_progress_counts_up_to_the_total():
    mgr, seen = _collect_progress(_spectra(n=9), algorithm='als', processing_mode='serial')
    assert seen[-1] == (9, 9)
    dones = [d for d, _ in seen]
    assert dones == sorted(dones) and all(t == 9 for _, t in seen)


def test_parallel_progress_counts_up_to_the_total():
    mgr, seen = _collect_progress(_spectra(n=10), algorithm='als',
                                  processing_mode='parallel', max_workers=2)
    assert mgr.last_run_info['mode'] == 'parallel'
    assert seen[-1] == (10, 10)
    dones = [d for d, _ in seen]
    assert dones == sorted(dones)


def test_progress_is_reported_often_even_for_a_slow_serial_job(monkeypatch):
    """The window flickered on Windows because it was refreshed only every
    50 spectra; now every spectrum may report (throttled by time only)."""
    monkeypatch.setattr(abm, '_PROGRESS_MIN_INTERVAL', 0.0)
    _, seen = _collect_progress(_spectra(n=7), algorithm='als', processing_mode='serial')
    assert len(seen) >= 7


def test_cancel_in_serial_mode_raises_and_stops_early(monkeypatch):
    # report after every spectrum, so the test does not depend on timing
    monkeypatch.setattr(abm, '_PROGRESS_MIN_INTERVAL', 0.0)
    computed = []
    original = AutomatedBaselineManager._baseline_for_spectrum

    def counting(self, *a, **k):
        computed.append(1)
        return original(self, *a, **k)

    def cancel_at_three(done, total):
        if done >= 3:
            raise OperationCancelled()

    mgr = AutomatedBaselineManager()
    AutomatedBaselineManager._baseline_for_spectrum = counting
    try:
        with pytest.raises(OperationCancelled):
            mgr.apply_correction(_spectra(n=20), {'algorithm': 'als', 'processing_mode': 'serial'},
                                 progress=cancel_at_three)
    finally:
        AutomatedBaselineManager._baseline_for_spectrum = original
    assert len(computed) < 20


def test_cancel_in_parallel_mode_ends_workers_quickly_without_serial_redo(monkeypatch):
    import time
    spectra = _spectra(n=40, points=1500)
    started = time.perf_counter()

    def cancel_at_once(done, total):
        raise OperationCancelled()

    mgr = AutomatedBaselineManager()
    with pytest.raises(OperationCancelled):
        mgr.apply_correction(spectra, {'algorithm': 'jbcd', 'processing_mode': 'parallel',
                                       'max_workers': 2}, progress=cancel_at_once)
    assert time.perf_counter() - started < 15          # not the whole (slow) job
    assert mgr.last_run_info['fallback_reason'] is None   # cancel is not a "failure"
    # and the manager is perfectly usable afterwards
    out = mgr.apply_correction(_spectra(n=3), {'algorithm': 'als', 'processing_mode': 'serial'})
    assert len(out) == 3
