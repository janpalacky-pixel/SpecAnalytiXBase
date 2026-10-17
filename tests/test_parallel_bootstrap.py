"""Bootstrap replicates in several processes (parallel_bootstrap.py, used by
NMF and MCR-ALS Bootstrap Uncertainty) and the faster leading SVD used by
the SVD / PCA bootstrap."""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from src.modules.utils import parallel_bootstrap as pb                      # noqa: E402
from src.modules.visualization_analysis.factor_diagnostics import leading_svd  # noqa: E402


def _replicate(common, b, row_idx):
    """Cheap top-level replicate: mean of the resampled rows, plus b."""
    X = np.asarray(common['X'])[row_idx]
    return True, X.mean(axis=0) + b * common['scale'], None


def _common(n=40, p=5, seed=0):
    rng = np.random.RandomState(seed)
    X = rng.normal(size=(n, p))
    rows = [rng.randint(0, n, size=n) for _ in range(12)]
    return {'X': X, 'scale': 0.5}, rows


def test_parallel_gives_the_same_replicates_as_serial(monkeypatch):
    common, rows = _common()
    monkeypatch.setattr(pb, 'MIN_PARALLEL_SECONDS', 1e9)
    serial = pb.run_replicates(_replicate, common, rows, workers=2)
    monkeypatch.setattr(pb, 'MIN_PARALLEL_SECONDS', 0.0)
    progress = []
    parallel = pb.run_replicates(_replicate, common, rows, workers=2,
                                 progress_callback=lambda a, b: progress.append((a, b)))
    assert [r[0] for r in parallel] == list(range(12))
    for a, b in zip(serial, parallel):
        assert a[1] and b[1] and np.allclose(a[2], b[2])
    assert progress[0] == (0, 12) and all(n == 12 and a < 12 for a, n in progress)


def test_cancel_keeps_the_finished_replicates(monkeypatch):
    common, rows = _common()
    monkeypatch.setattr(pb, 'MIN_PARALLEL_SECONDS', 1e9)
    calls = []

    def cancel():
        calls.append(1)
        return len(calls) > 4
    out = pb.run_replicates(_replicate, common, rows, cancel_check=cancel)
    assert 1 <= len(out) < 12
    assert [r[0] for r in out] == list(range(len(out)))


def test_a_failing_pool_falls_back_to_this_process(monkeypatch):
    common, rows = _common()
    monkeypatch.setattr(pb, 'MIN_PARALLEL_SECONDS', 0.0)

    def broken(*a, **k):
        raise OSError('cannot start worker processes')
    monkeypatch.setattr(pb, '_run_parallel', broken)
    out = pb.run_replicates(_replicate, common, rows, workers=4)
    assert [r[0] for r in out] == list(range(12))


def test_worker_count_respects_memory():
    assert pb.bootstrap_worker_count(0, cpu_count=8, available_mb=None) == 7
    assert pb.bootstrap_worker_count(0, cpu_count=2, available_mb=None) == 2
    # a 270 MB table (a 21 000 x 1 600 map): ~1.3 GB per worker
    assert pb.bootstrap_worker_count(270 * 2 ** 20, cpu_count=16, available_mb=6000) == 3
    assert pb.bootstrap_worker_count(270 * 2 ** 20, cpu_count=16, available_mb=500) == 1


def test_nmf_bootstrap_is_the_same_in_parallel(monkeypatch):
    from src.controllers.visualization_analysis.nmf_controller import NMFController
    rng = np.random.RandomState(3)
    x = np.linspace(400, 1800, 120)
    S = np.stack([np.exp(-0.5 * ((x - c) / 40) ** 2) for c in (700, 1100, 1500)])
    Y = rng.random((30, 3)) @ S + rng.random((30, 120)) * 0.02
    spectra = [{'label': f's{i}', 'x_scale': x, 'y_scale': Y[i], 'metadata': {}}
               for i in range(30)]
    ctrl = NMFController(None)
    ref, ok = ctrl.compute_trial(spectra, n_components=3, init='nndsvda', max_iter=200,
                                 random_state=0)
    assert ok
    out = {}
    for mode, limit in (('serial', 1e9), ('parallel', 0.0)):
        monkeypatch.setattr(pb, 'MIN_PARALLEL_SECONDS', limit)
        monkeypatch.setattr(pb, 'bootstrap_worker_count', lambda *a, **k: 2)
        out[mode] = ctrl.compute_bootstrap_uncertainty(ref, 3, 'nndsvda', 200, 6, 0.95,
                                                       random_state=1)
    assert out['serial']['n_resamples_used'] == out['parallel']['n_resamples_used'] == 6
    assert np.allclose(out['serial']['H_samples'], out['parallel']['H_samples'])


@pytest.mark.parametrize('shape', [(500, 450), (450, 600), (120, 80)])
def test_leading_svd_matches_the_full_svd(shape):
    rng = np.random.RandomState(1)
    X = rng.normal(size=shape) + 5 * np.outer(rng.random(shape[0]), rng.random(shape[1]))
    U, s, Vt = np.linalg.svd(X, full_matrices=False)
    u, ss, vt = leading_svd(X, 4)
    assert np.allclose(s[:4], ss)
    for j in range(4):
        sign = np.sign(np.dot(U[:, j], u[:, j]))
        assert np.allclose(U[:, j], sign * u[:, j], atol=1e-7)
        assert np.allclose(Vt[j], sign * vt[j], atol=1e-7)


def test_a_large_table_is_refitted_here(monkeypatch):
    common, rows = _common()
    monkeypatch.setattr(pb, 'MIN_PARALLEL_SECONDS', 0.0)
    called = []
    monkeypatch.setattr(pb, '_run_parallel', lambda *a, **k: called.append(1))
    out = pb.run_replicates(_replicate, common, rows, workers=4,
                            table_bytes=pb.MAX_PARALLEL_TABLE_BYTES + 1)
    assert not called and [r[0] for r in out] == list(range(12))
