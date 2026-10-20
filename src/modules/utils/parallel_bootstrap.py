# src/modules/utils/parallel_bootstrap.py
"""Bootstrap replicates in several processes (NMF and MCR-ALS Bootstrap
Uncertainty, in their own windows and in the 2D Map). Qt-free.

Every replicate refits the whole decomposition (0.4-1 s for NMF on 100-1 000
spectra), one after the other, and a single refit uses only part of the
CPU. The replicates are independent, so they can run in separate worker
processes, like Automated Baseline (src/modules/utils/parallel_utils.py:
"spawn" processes, each limited to one BLAS thread).

How it decides (no setting needed):

* The first replicate runs here and is timed. If the rest would take less
  than MIN_PARALLEL_SECONDS serially, or only one worker is sensible, the
  rest also runs here -- starting worker processes costs a few seconds.
* Large tables (more than MAX_PARALLEL_TABLE_BYTES, e.g. a whole map) are
  always refitted here: one refit already keeps all cores busy, and many
  workers each holding copies of a large table can exhaust the memory and
  slow the whole computer down.
* Otherwise the rest runs in worker processes. The number of workers is one
  less than the CPU cores and is limited by the free memory (each worker
  needs its own copy of one resampled data table plus the refit's working
  memory).
* The resampling (which rows each replicate draws) is decided here, in the
  same order as before, and replicate b is refitted with random_state=b, so
  the result is the same whether it ran in parallel or not.
* Cancel stops the workers at once and keeps the replicates finished so
  far. If the pool cannot start or a worker dies, the remaining replicates
  run here instead (logged).

The data the workers need (model, residuals, starting spectra, ...) is
written once to a temporary folder and read by each worker once (not sent
with every task).
"""
import concurrent.futures
import multiprocessing
import os
import pickle
import shutil
import tempfile
import time

import numpy as np

from src.modules.utils.app_logger import get_logger
from src.modules.utils.parallel_utils import (
    _available_memory_mb, _init_worker, _terminate_workers, count_item,
    limited_blas_threads)

logger = get_logger(__name__)

MIN_PARALLEL_SECONDS = 4.0   # below this expected serial time: no processes
# Larger data tables (e.g. a 21 000-spectrum map: 270 MB) are refitted here:
# one refit then already uses all cores through the multi-threaded BLAS,
# while every worker would need its own copies of the table (memory!).
MAX_PARALLEL_TABLE_BYTES = 64 * 2 ** 20
_RESERVED_MB = 1024
_BASE_MB_PER_WORKER = 250
_POLL_SECONDS = 0.1


class BootstrapCancelled(Exception):
    pass


def bootstrap_worker_count(table_bytes, cpu_count=None, available_mb='measure'):
    """Workers for bootstrap refits: cores - 1 (all of them on <= 2 cores),
    limited by free memory -- each worker holds about 4 copies of the data
    table (resampled table, its copy in the refit, work arrays) plus
    ~250 MB for Python and numpy. Always >= 1."""
    cores = cpu_count if cpu_count is not None else (os.cpu_count() or 1)
    workers = cores - 1 if cores > 2 else cores
    if available_mb == 'measure':
        available_mb = _available_memory_mb()
    if available_mb is not None:
        per_worker = _BASE_MB_PER_WORKER + 4 * table_bytes / 2 ** 20
        workers = min(workers, int((available_mb - _RESERVED_MB) / per_worker))
    return max(1, min(workers, 61))


# --------------------------------------------------------------- workers

_COMMON_CACHE = {}


def _load_common(folder):
    """The shared data, read once per worker process."""
    common = _COMMON_CACHE.get(folder)
    if common is None:
        with open(os.path.join(folder, 'meta.pkl'), 'rb') as fh:
            common = pickle.load(fh)
        for name in common.pop('_arrays'):
            common[name] = np.load(os.path.join(folder, name + '.npy'), mmap_mode='r')
        _COMMON_CACHE.clear()
        _COMMON_CACHE[folder] = common
    return common


def _run_chunk(payload):
    """Worker task: payload = (replicate_fn, folder, [(b, row_idx), ...])."""
    replicate_fn, folder, jobs = payload
    common = _load_common(folder)
    out = []
    for b, row_idx in jobs:
        out.append((b,) + tuple(replicate_fn(common, b, row_idx)))
        count_item()
    return out


def _write_common(common):
    folder = tempfile.mkdtemp(prefix='sax_bootstrap_')
    meta = {k: v for k, v in common.items() if not isinstance(v, np.ndarray)}
    arrays = [k for k, v in common.items() if isinstance(v, np.ndarray)]
    meta['_arrays'] = arrays
    for name in arrays:
        np.save(os.path.join(folder, name + '.npy'), common[name])
    with open(os.path.join(folder, 'meta.pkl'), 'wb') as fh:
        pickle.dump(meta, fh)
    return folder


# --------------------------------------------------------------- driver

def run_replicates(replicate_fn, common, row_indices, progress_callback=None,
                   cancel_check=None, workers=None, table_bytes=0, worker_fn=None):
    """Run replicate_fn(common, b, row_idx) -> (ok, result, error) for every
    b, row_idx in enumerate(row_indices). In worker processes worker_fn is
    used instead (default: replicate_fn); it must be a top-level function
    (it is sent to the workers by name) that computes the same thing.

    progress_callback(b, n) is called before replicate b when running here
    (as before), and with the number of finished replicates (at most n-1)
    while workers run; cancel_check() -> True stops early. Returns the
    finished replicates as a list of (b, ok, result, error), ordered by b.
    """
    n = len(row_indices)
    results = []
    if n == 0:
        return results
    worker_fn = worker_fn or replicate_fn

    def report(count):
        if progress_callback is not None:
            progress_callback(min(count, n - 1), n)

    def cancelled():
        return cancel_check is not None and cancel_check()

    def run_here(b):
        report(b)
        results.append((b,) + tuple(replicate_fn(common, b, row_indices[b])))

    # 1. the first replicate here, timed
    if cancelled():
        return results
    t0 = time.perf_counter()
    run_here(0)
    per_rep = time.perf_counter() - t0
    rest = list(range(1, n))

    if workers is None and rest:
        workers = bootstrap_worker_count(table_bytes)
        # File > Settings and saved items... > Parallel processing
        from src.modules.utils.parallel_utils import default_parallel_settings
        shared = default_parallel_settings()
        if shared['processing_mode'] == 'serial':
            workers = 1
        elif shared['max_workers'] > 0:
            workers = min(workers, shared['max_workers'])
    if (rest and min(workers, len(rest)) > 1 and table_bytes <= MAX_PARALLEL_TABLE_BYTES
            and per_rep * len(rest) >= MIN_PARALLEL_SECONDS):
        try:
            _run_parallel(worker_fn, common, row_indices, rest, min(workers, len(rest)),
                          results, report, cancelled)
            rest = []
        except BootstrapCancelled:
            results.sort(key=lambda r: r[0])
            return results
        except Exception as exc:                      # pool failed: finish here
            logger.warning("Bootstrap: parallel run failed (%r); the remaining "
                           "replicates run in this process.", exc)
            done = {r[0] for r in results}
            rest = [b for b in rest if b not in done]
    # 2. (the rest of) the replicates here
    for b in rest:
        if cancelled():
            break
        run_here(b)
    results.sort(key=lambda r: r[0])
    return results


def _run_parallel(replicate_fn, common, row_indices, todo, workers, results,
                  report, cancelled):
    """Run the replicates `todo` in worker processes; append to `results`.
    Returns the set of b finished. Raises BootstrapCancelled on cancel
    (results keeps what finished)."""
    folder = _write_common(common)
    finished = set()
    try:
        n_chunks = max(1, min(len(todo), workers * 3))
        chunks = [todo[i::n_chunks] for i in range(n_chunks)]
        context = multiprocessing.get_context('spawn')
        counter = context.Value('q', 0)
        with limited_blas_threads():
            executor = concurrent.futures.ProcessPoolExecutor(
                max_workers=workers, mp_context=context,
                initializer=_init_worker, initargs=(counter,))
            try:
                futures = {executor.submit(
                    _run_chunk, (replicate_fn, folder,
                                 [(b, row_indices[b]) for b in chunk])): chunk
                    for chunk in chunks if chunk}
                pending = set(futures)
                base = len(results)
                while pending:
                    done, pending = concurrent.futures.wait(
                        pending, timeout=_POLL_SECONDS,
                        return_when=concurrent.futures.FIRST_COMPLETED)
                    for fut in done:
                        for res in fut.result():
                            results.append(res)
                            finished.add(res[0])
                    if cancelled():
                        raise BootstrapCancelled()
                    # smooth progress: replicates counted inside the chunks
                    report(max(len(results), base + counter.value))
            except BaseException:
                executor.shutdown(wait=False, cancel_futures=True)
                _terminate_workers(executor)
                raise
            else:
                executor.shutdown(wait=True)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return finished

