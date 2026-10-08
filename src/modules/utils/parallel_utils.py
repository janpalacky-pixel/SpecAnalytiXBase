# src/modules/utils/parallel_utils.py
"""Small, Qt-free helpers for running per-spectrum work in several
processes (used by the Automated Baseline correction).

Why separate processes and not threads: the baseline algorithms are
numpy/scipy code that already uses several BLAS threads internally, and
Python threads would fight over the same cores (measured: slower than
serial, see the Developer Guide). Separate worker processes, each limited
to ONE BLAS thread, scale properly.

Lessons from MeltAnalytiX's parallel fitting that are built in here:

* the number of workers is capped by the memory that is actually free
  (many-core CPUs with little free RAM otherwise end in "paging file is
  too small", WinError 1455/1450);
* workers get OPENBLAS/OMP/MKL_NUM_THREADS=1 (otherwise every worker
  starts one BLAS thread per CPU core, each with its own reserved buffer);
* the pool uses the "spawn" start method on every platform, i.e. the same
  behaviour as Windows, which is where the installed application runs;
* the caller keeps the user interface alive by passing a progress callback
  that is called while waiting for results.
"""

import concurrent.futures
import contextlib
import multiprocessing
import os
import sys

from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)

# Each worker process (Python + numpy/scipy) needs roughly this much memory.
_MB_PER_WORKER = 200
# Memory left to the operating system and the application itself.
_RESERVED_MB = 1024
# Windows' ProcessPoolExecutor cannot use more than 61 workers.
_MAX_POOL_WORKERS = 61
# How often (seconds) the progress callback is called while waiting.
_POLL_SECONDS = 0.1

_BLAS_THREAD_VARIABLES = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')


def _windows_available_mb(avail_physical_bytes, avail_commit_bytes):
    """Free memory on Windows, in MB: the LARGER of free physical RAM and
    free commit.

    Free commit alone proved too pessimistic: browsers and other programs
    "commit" far more memory than they really use, so on a 32 GB machine
    with 11% of the RAM free the commit figure said ~1 GB and Auto chose
    ONE worker -- while 20 workers then ran fine and 5.6x faster. Free
    physical RAM alone was the older, even more cautious choice in
    MeltAnalytiX. Taking the larger of the two is the optimistic reading;
    if it is ever too optimistic, a worker that cannot start or dies makes
    the job fall back to serial processing (see the Automated Baseline
    manager) instead of failing.
    """
    return max(avail_physical_bytes, avail_commit_bytes) / (1024 * 1024)


def _available_memory_mb():
    """Memory still available for new processes, in MB, or None if unknown.

    On Windows two numbers are read through ctypes (no psutil dependency,
    same approach as the PARAFAC/MeltAnalytiX helpers): the free physical
    RAM and the free *commit* (RAM + page file not yet promised to
    programs). See _windows_available_mb() for how they are combined.
    """
    try:
        if sys.platform.startswith('win'):
            import ctypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong),
                    ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong),
                    ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong),
                    ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong),
                    ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('sullAvailExtendedVirtual', ctypes.c_ulonglong),
                ]

            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)) != 0:
                return _windows_available_mb(stat.ullAvailPhys, stat.ullAvailPageFile)
            return None
        pages = os.sysconf('SC_AVPHYS_PAGES')
        page_size = os.sysconf('SC_PAGE_SIZE')
        return pages * page_size / (1024 * 1024)
    except Exception:
        return None


def safe_worker_count(cpu_count=None, available_mb='measure'):
    """Number of worker processes it is sensible to start right now.

    One less than the number of CPU cores on machines with more than two
    (so the window stays responsive), but never more than the free memory
    allows (about 200 MB per worker after leaving 1 GB free). Always >= 1.

    cpu_count / available_mb can be passed in for testing.
    """
    cores = cpu_count if cpu_count is not None else (os.cpu_count() or 1)
    workers = cores - 1 if cores > 2 else cores
    if available_mb == 'measure':
        available_mb = _available_memory_mb()
    if available_mb is not None:
        by_memory = int((available_mb - _RESERVED_MB) / _MB_PER_WORKER)
        workers = min(workers, by_memory)
    return max(1, min(workers, _MAX_POOL_WORKERS))


def describe_worker_limits():
    """Plain-language description of what limits the worker count right
    now, e.g. "8 CPU cores, 3.2 GB free memory -> 7 workers". Shown to the
    user so an unexpectedly small worker count can be understood."""
    cores = os.cpu_count() or 1
    free_mb = _available_memory_mb()
    workers = safe_worker_count()
    memory = 'free memory unknown' if free_mb is None else f'{free_mb / 1024:.1f} GB free memory'
    noun = 'worker' if workers == 1 else 'workers'
    return f'{cores} CPU cores, {memory} -> {workers} {noun}'


def resolve_worker_count(requested=None):
    """Worker count to use. requested None/0 = automatic (safe_worker_count);
    a positive number is honoured but limited to the CPU cores."""
    auto = safe_worker_count()
    if not requested or int(requested) <= 0:
        return auto
    cores = os.cpu_count() or 1
    return max(1, min(int(requested), cores, _MAX_POOL_WORKERS))


@contextlib.contextmanager
def limited_blas_threads():
    """Set OPENBLAS/OMP/MKL_NUM_THREADS=1 for processes started inside the
    block, then restore the previous environment.

    The current process has already loaded its BLAS libraries, so changing
    the variables does not affect it; only worker processes, which inherit
    the environment when they start, are limited.
    """
    previous = {name: os.environ.get(name) for name in _BLAS_THREAD_VARIABLES}
    for name in _BLAS_THREAD_VARIABLES:
        os.environ[name] = '1'
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _terminate_workers(executor):
    """End the worker processes of an executor right now (a cancelled job
    must not keep computing until each worker finishes its chunk).
    executor.shutdown() cannot interrupt a running task, and
    ProcessPoolExecutor has no public "kill workers" before Python 3.14,
    hence the private attribute; failures here are harmless."""
    try:
        for process in list(getattr(executor, '_processes', {}).values()):
            process.terminate()
    except Exception as exc:
        logger.debug("Could not terminate worker processes: %r", exc)


def run_in_process_pool(worker_fn, payloads, max_workers, progress_callback=None,
                        on_payload_done=None):
    """Run worker_fn(payload) for every payload in separate processes and
    return the results in payload order.

    worker_fn must be a top-level (picklable) function. Any exception in
    a worker, or a pool that cannot start/dies (BrokenProcessPool,
    memory, pickling), is raised to the caller, which decides about a
    serial fallback.

    progress_callback (no arguments, may be None) is called about ten
    times a second while waiting, so a caller can pass
    ``QApplication.processEvents`` to keep its window alive. It may raise
    an exception (e.g. OperationCancelled) to stop the job: the workers
    are then ended at once and the exception propagates.

    on_payload_done(i) (may be None) is called in this process when the
    i-th payload has finished, so a caller can count progress.
    """
    results = [None] * len(payloads)
    context = multiprocessing.get_context('spawn')
    with limited_blas_threads():
        executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=max_workers, mp_context=context)
        try:
            future_to_index = {
                executor.submit(worker_fn, payload): i
                for i, payload in enumerate(payloads)
            }
            pending = set(future_to_index)
            while pending:
                done, pending = concurrent.futures.wait(
                    pending, timeout=_POLL_SECONDS,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    index = future_to_index[future]
                    results[index] = future.result()
                    if on_payload_done is not None:
                        on_payload_done(index)
                if progress_callback is not None:
                    progress_callback()
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            _terminate_workers(executor)
            raise
        else:
            executor.shutdown(wait=True)
    return results
