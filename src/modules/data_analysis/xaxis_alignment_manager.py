# src/modules/data_analysis/xaxis_alignment_manager.py
"""
X-axis alignment manager.

Aligns a group of spectra to a single reference spectrum by finding the
x-axis shift that minimises the RMSD between each spectrum and the reference.
Only the x-scale is modified; spectral shapes are preserved exactly.

Algorithm (translated from the original MATLAB xshift implementation):
    For each test spectrum i, find the scalar shift δᵢ that minimises

        RMSD(δᵢ) = √ Σ [y_ref(x) − y_i(x + δᵢ)]²

    using scipy's Nelder-Mead (fminsearch equivalent).  The shifted y-values
    at the reference x-grid are obtained by cubic-spline interpolation.
"""

import numpy as np
try:
    from scipy.optimize import minimize
    from scipy.interpolate import interp1d
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False

import time

from src.modules.utils.app_logger import get_logger
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.progress_utils import notify_progress
from src.modules.utils.parallel_utils import (
    chunk_count, count_item, describe_worker_limits, requested_workers,
    resolve_worker_count, run_in_process_pool)

logger = get_logger(__name__)

# 'auto' processing mode (as in Automated Baseline): the first few spectra
# are timed here; worker processes are started only if the rest would take
# at least _AUTO_MIN_SERIAL_SECONDS and parallel is clearly faster.
_AUTO_CALIBRATION_SPECTRA = 3
_AUTO_MIN_SERIAL_SECONDS = 6.0
_POOL_STARTUP_SECONDS = 4.0


def _shift_chunk_worker(payload):
    """Worker process: the optimal shift of every spectrum of one chunk
    (top-level, so it can be sent to worker processes)."""
    settings, ref_x, ref_y, xs, ys = payload
    manager = XAxisAlignmentManager()
    manager.update_settings(settings)
    shifts = []
    for x, y in zip(xs, ys):
        shifts.append(manager._shift_for(ref_x, ref_y, np.asarray(x, float),
                                         np.asarray(y, float)))
        count_item()
    return shifts


class XAxisAlignmentManager:
    """Business logic for x-axis alignment (x-shift correction) of spectra."""

    # Interpolation methods available in the dialog
    INTERPOLATION_METHODS = ['cubic', 'linear', 'quadratic']

    def __init__(self):
        # Index of the reference spectrum inside the group that is currently
        # being processed.  Stored so the controller can remember the last
        # used setting.
        self.reference_spectrum_index: int = 0

        # Maximum shift magnitude (cm⁻¹ or whatever x-unit the spectra use)
        # used as search bounds for the optimiser.
        self.max_shift: float = 10.0

        # Interpolation kind passed to scipy.interpolate.interp1d.
        self.interpolation_method: str = 'cubic'

        # Optional x-range to restrict the RMSD computation (improves speed
        # and accuracy when a clean spectral region is known).  None = full range.
        self.x_range: tuple | None = None   # (x_min, x_max) or None

    @staticmethod
    def _key_for(spectrum):
        """Stable per-spectrum key — uses the spectrum's persistent
        unique_id rather than its label, since labels can change (rename)
        or collide (re-import). Used by the controller to track which
        actual spectrum was chosen as the alignment reference, instead of
        a raw position in the selection list — a list position is not a
        stable identity across reopens, since the selection can be
        reordered, reduced, or extended without the previously-chosen
        reference spectrum changing identity."""
        metadata = spectrum.get('metadata') or {}
        return metadata.get('unique_id') or spectrum['label']

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def align_spectra(self, spectra: list, settings: dict, progress_callback=None,
                      count_callback=None) -> list:
        """Align *spectra* to the reference and return a new list.

        The reference spectrum is returned unchanged (shift = 0 by definition).
        All other spectra have their x_scale shifted so they best match the
        reference within the common overlap region.

        Parameters
        ----------
        spectra:  list of spectrum dicts (must contain 'x_scale', 'y_scale', 'label')
        settings: dict produced by XAxisAlignmentDialog.get_settings()
        progress_callback: optional callable, invoked every 50 spectra
            during the loop below — see SNIPBaselineManager.apply_correction
            for the full reasoning; same hook/contract. None (the
            default) — no change from before. While worker processes run it
            is called about ten times a second.
        count_callback: optional callable(done, total) -- how many shifts
            have been found so far (for a progress bar).
        settings['processing_mode'] ('auto' default / 'serial' / 'parallel')
            and settings['max_workers'] (0 = all cores) choose how the shifts
            are found -- like Automated Baseline. last_run_info / run_summary()
            tell how it ran.

        Returns
        -------
        list of spectrum dicts – same order as input, x_scales updated in-place
        on deep copies so originals are untouched.
        """
        if not _SCIPY_AVAILABLE:
            raise RuntimeError(
                "scipy is required for x-axis alignment but is not installed."
            )

        self.update_settings(settings)

        if not spectra:
            return []

        ref_idx = self.reference_spectrum_index
        if ref_idx < 0 or ref_idx >= len(spectra):
            logger.warning(
                "Reference index %d out of range (N=%d); defaulting to 0",
                ref_idx, len(spectra),
            )
            ref_idx = 0

        ref = spectra[ref_idx]
        ref_x = ref['x_scale'].astype(float)
        ref_y = ref['y_scale'].astype(float)

        # 1. the shifts (the slow part): here or in worker processes
        shifts = self._compute_shifts(spectra, ref_idx, ref_x, ref_y, settings,
                                      progress_callback, count_callback)

        # 2. apply them
        result_spectra = []

        for i, spectrum in enumerate(spectra):
            notify_progress(progress_callback, i)
            # Deep-copy the spectrum so we never mutate originals
            s = self._copy_spectrum(spectrum)

            if i == ref_idx:
                # Reference spectrum: record zero shift and return as-is
                s['xaxis_alignment_info'] = {
                    'is_reference': True,
                    'shift': 0.0,
                    'reference_label': ref['label'],
                    'interpolation_method': self.interpolation_method,
                }
                s['metadata'] = dict(s.get('metadata') or {})
                s['metadata']['correction_history'] = append_correction_history(
                    spectrum.get('metadata'), 'X-axis alignment', s['xaxis_alignment_info']
                )
                result_spectra.append(s)
                continue

            test_x = s['x_scale'].astype(float)
            test_y = s['y_scale'].astype(float)

            if len(test_x) < 4 or len(ref_x) < 4:
                logger.warning(
                    "Spectrum '%s' has too few points for alignment; skipping.",
                    s['label'],
                )
                result_spectra.append(s)
                continue

            shift = shifts[i]

            # Apply the shift: move the test x-scale so it lines up with reference
            aligned_x, aligned_y = self._apply_shift(
                ref_x, test_x, test_y, shift
            )

            s['x_scale'] = aligned_x
            s['y_scale'] = aligned_y
            s['xaxis_alignment_info'] = {
                'is_reference': False,
                'shift': float(shift),
                'reference_label': ref['label'],
                'interpolation_method': self.interpolation_method,
            }
            s['metadata'] = dict(s.get('metadata') or {})
            s['metadata']['correction_history'] = append_correction_history(
                spectrum.get('metadata'), 'X-axis alignment', s['xaxis_alignment_info']
            )

            logger.debug(
                "Aligned '%s': shift = %.5f",
                s['label'], shift,
            )
            result_spectra.append(s)

        return result_spectra

    def _shift_for(self, ref_x, ref_y, test_x, test_y):
        """The optimal shift of one spectrum (0.0 with too few points)."""
        if len(test_x) < 4 or len(ref_x) < 4:
            return 0.0
        return self._find_optimal_shift(ref_x, ref_y, test_x, test_y)

    def _compute_shifts(self, spectra, ref_idx, ref_x, ref_y, settings,
                        progress_callback=None, count_callback=None):
        """{index: shift} for every spectrum except the reference."""
        started = time.perf_counter()
        todo = [i for i in range(len(spectra)) if i != ref_idx]
        n = len(todo)
        mode = settings.get('processing_mode', 'auto')
        if mode not in ('auto', 'serial', 'parallel'):
            mode = 'auto'
        info = {'mode': 'serial', 'workers': 1, 'n_spectra': n, 'seconds': 0.0,
                'note': None, 'fallback_reason': None}
        self.last_run_info = info
        shifts = {ref_idx: 0.0}
        done = [0]

        def report():
            if count_callback is not None:
                count_callback(done[0], n)

        def serial(indices):
            for i in indices:
                sp = spectra[i]
                shifts[i] = self._shift_for(ref_x, ref_y, np.asarray(sp['x_scale'], float),
                                            np.asarray(sp['y_scale'], float))
                done[0] += 1
                notify_progress(progress_callback, done[0])
                if done[0] % 20 == 0:
                    report()

        workers = (resolve_worker_count(requested_workers(settings.get('max_workers', 0)))
                   if mode != 'serial' else 1)
        if mode != 'serial' and (workers < 2 or n < 2):
            info['note'] = (f'only one worker is available ({describe_worker_limits()})'
                            if workers < 2 else 'there is only one spectrum to align')
            mode = 'serial'
        remaining = list(todo)
        if mode == 'auto':
            calibration = remaining[:_AUTO_CALIBRATION_SPECTRA]
            t0 = time.perf_counter()
            serial(calibration)
            per_spectrum = (time.perf_counter() - t0) / max(len(calibration), 1)
            remaining = remaining[len(calibration):]
            serial_estimate = per_spectrum * len(remaining)
            parallel_estimate = _POOL_STARTUP_SECONDS + serial_estimate / workers
            if (serial_estimate >= _AUTO_MIN_SERIAL_SECONDS
                    and parallel_estimate <= 0.7 * serial_estimate):
                mode = 'parallel'
            else:
                info['note'] = (f'the job is short (about {serial_estimate:.1f} s), so '
                                f'parallel workers would not pay off')
        if mode == 'parallel' and remaining:
            try:
                self._compute_parallel(spectra, remaining, ref_x, ref_y, settings, workers,
                                       shifts, done, progress_callback, report)
                info['mode'], info['workers'] = 'parallel', workers
                remaining = []
            except Exception as exc:
                # cannot start / out of memory / ...: finish here
                from src.modules.utils.progress_utils import OperationCancelled
                if isinstance(exc, OperationCancelled):
                    raise
                logger.warning("Parallel x-axis alignment failed (%r); "
                               "finishing serially.", exc)
                info['fallback_reason'] = f'{type(exc).__name__}: {exc}'
                remaining = [i for i in remaining if i not in shifts]
        if remaining:
            serial(remaining)
        done[0] = n
        report()
        info['seconds'] = time.perf_counter() - started
        return shifts

    def _compute_parallel(self, spectra, indices, ref_x, ref_y, settings, workers,
                          shifts, done, progress_callback, report):
        n_chunks = chunk_count(len(indices), workers)
        chunks = [list(part) for part in np.array_split(np.array(indices), n_chunks)]
        cfg = {k: settings[k] for k in ('max_shift', 'interpolation_method', 'x_range')
               if k in settings}
        cfg.setdefault('max_shift', self.max_shift)
        cfg.setdefault('interpolation_method', self.interpolation_method)
        cfg.setdefault('x_range', self.x_range)
        payloads = [(cfg, ref_x, ref_y,
                     [np.asarray(spectra[i]['x_scale'], float) for i in chunk],
                     [np.asarray(spectra[i]['y_scale'], float) for i in chunk])
                    for chunk in chunks]
        before = done[0]

        def items_done(count):
            done[0] = before + count

        def tick():
            if progress_callback is not None:
                progress_callback()
            report()

        results = run_in_process_pool(_shift_chunk_worker, payloads, workers, tick,
                                      on_items_done=items_done)
        for chunk, chunk_shifts in zip(chunks, results):
            for i, shift in zip(chunk, chunk_shifts):
                shifts[i] = shift

    def run_summary(self):
        """One sentence on how the last alignment ran ('' if none)."""
        info = getattr(self, 'last_run_info', None)
        if not info:
            return ''
        how = (f"parallel, {info['workers']} workers" if info['mode'] == 'parallel'
               else 'serial')
        text = f"Shifts of {info['n_spectra']} spectra found in {info['seconds']:.1f} s ({how})."
        if info['fallback_reason']:
            text += f" Parallel processing failed, finished serially ({info['fallback_reason']})."
        return text

    def update_settings(self, settings: dict):
        """Update manager state from a settings dict."""
        if 'reference_spectrum_index' in settings:
            self.reference_spectrum_index = int(settings['reference_spectrum_index'])
        if 'max_shift' in settings:
            self.max_shift = float(settings['max_shift'])
        if 'interpolation_method' in settings:
            self.interpolation_method = str(settings['interpolation_method'])
        if 'x_range' in settings:
            self.x_range = settings['x_range']  # tuple or None

    def get_default_range(self, spectra: list) -> tuple:
        """Return (x_min, x_max) covering all provided spectra."""
        if not spectra:
            return None, None
        x_mins, x_maxs = [], []
        for s in spectra:
            x = s.get('x_scale', np.array([]))
            if len(x) > 0:
                x_mins.append(float(np.min(x)))
                x_maxs.append(float(np.max(x)))
        if not x_mins:
            return None, None
        return min(x_mins), max(x_maxs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_optimal_shift(
        self,
        ref_x: np.ndarray,
        ref_y: np.ndarray,
        test_x: np.ndarray,
        test_y: np.ndarray,
    ) -> float:
        """Find the x-shift that minimises RMSD between test and ref."""
        # Build interpolator for the test spectrum on its original x grid.
        # We shift by evaluating the interpolator at (ref_x − shift).
        try:
            interp_fn = interp1d(
                test_x,
                test_y,
                kind=self.interpolation_method,
                bounds_error=False,
                fill_value=np.nan,
            )
            # Replace NaN fill with 0 so the objective doesn't blow up at borders
            def safe_interp(x):
                y = interp_fn(x)
                y = np.where(np.isfinite(y), y, 0.0)
                return y

        except Exception as exc:
            logger.warning("Could not build interpolator: %s", exc)
            return 0.0

        # Redefine objective so interpolation shifts the test towards the ref.
        # Shifting the x-scale right by δ means spectrum_1(x) = spectrum_2(x − δ).
        # Equivalently, the y-value at ref_x is test_y interpolated at (ref_x − δ).
        def objective_neg_shift(shift_arr):
            shift = float(shift_arr[0])
            shifted_test_x = test_x + shift
            x_lo = max(float(np.min(shifted_test_x)), float(np.min(ref_x)))
            x_hi = min(float(np.max(shifted_test_x)), float(np.max(ref_x)))

            if self.x_range is not None:
                x_lo = max(x_lo, float(self.x_range[0]))
                x_hi = min(x_hi, float(self.x_range[1]))

            if x_hi <= x_lo:
                return 1e12

            mask = (ref_x >= x_lo) & (ref_x <= x_hi)
            if mask.sum() < 2:
                return 1e12

            eval_x = ref_x[mask] - shift   # evaluate the test interp at unshifted coords
            test_y_interp = safe_interp(eval_x)
            diff = test_y_interp - ref_y[mask]
            return float(np.sqrt(np.mean(diff ** 2)))

        # Grid search across the allowed range to find a good starting point
        n_grid = 21
        shifts_grid = np.linspace(-self.max_shift, self.max_shift, n_grid)
        costs = [objective_neg_shift([s]) for s in shifts_grid]
        best_grid_idx = int(np.argmin(costs))
        x0 = shifts_grid[best_grid_idx]

        # Nelder-Mead refinement (equivalent to MATLAB fminsearch).
        # bounds= constrains the refinement to the same [-max_shift,
        # max_shift] range the grid search above already respects — without
        # it, only the STARTING point was bounded; Nelder-Mead's own search
        # steps are free to wander arbitrarily far from that starting point,
        # so the result could end up well beyond the range the "Max shift"
        # control tells the user it searches. Verified directly: a spectrum
        # whose true best-fit shift was 8.0, with max_shift set to 2.0,
        # returned exactly 8.0 without this — four times the stated limit,
        # with nothing to indicate the bound had been silently ignored.
        # (scipy Nelder-Mead has supported bounds since 1.7, released 2021.)
        result = minimize(
            objective_neg_shift,
            x0=[x0],
            method='Nelder-Mead',
            bounds=[(-self.max_shift, self.max_shift)],
            options={
                'xatol': 1e-6,
                'fatol': 1e-8,
                'maxiter': 2000,
                'maxfev': 4000,
            },
        )

        if result.success or result.fun < costs[best_grid_idx]:
            return float(result.x[0])

        logger.debug(
            "Nelder-Mead did not fully converge (fun=%.4e); using best grid shift %.4f",
            result.fun, x0,
        )
        return float(x0)

    def _apply_shift(
        self,
        ref_x: np.ndarray,
        test_x: np.ndarray,
        test_y: np.ndarray,
        shift: float,
    ) -> tuple:
        """Apply *shift* to test spectrum and re-sample onto the reference x-grid.

        Returns (new_x, new_y) both on the reference x-grid within the
        overlapping range.
        """
        shifted_test_x = test_x + shift

        x_lo = max(float(np.min(shifted_test_x)), float(np.min(ref_x)))
        x_hi = min(float(np.max(shifted_test_x)), float(np.max(ref_x)))

        mask = (ref_x >= x_lo) & (ref_x <= x_hi)
        new_x = ref_x[mask]

        interp_fn = interp1d(
            shifted_test_x,
            test_y,
            kind=self.interpolation_method,
            bounds_error=False,
            fill_value=np.nan,
        )
        new_y = interp_fn(new_x)

        # Guard: replace any NaN introduced at edges with zero
        new_y = np.where(np.isfinite(new_y), new_y, 0.0)

        return new_x, new_y

    @staticmethod
    def _copy_spectrum(spectrum: dict) -> dict:
        """Return a deep copy of *spectrum* (arrays copied, dicts recursed)."""
        copy = {}
        for key, val in spectrum.items():
            if isinstance(val, np.ndarray):
                copy[key] = val.copy()
            elif isinstance(val, dict):
                copy[key] = {
                    k: v.copy() if isinstance(v, np.ndarray) else v
                    for k, v in val.items()
                }
            else:
                copy[key] = val
        return copy
