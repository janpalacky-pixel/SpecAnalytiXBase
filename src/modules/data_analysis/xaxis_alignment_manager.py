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

from src.modules.utils.app_logger import get_logger
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.progress_utils import notify_progress

logger = get_logger(__name__)


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

    def align_spectra(self, spectra: list, settings: dict, progress_callback=None) -> list:
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
            default) — no change from before.

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

            # Optimise shift
            shift = self._find_optimal_shift(ref_x, ref_y, test_x, test_y)

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
