# src/modules/visualization_analysis/band_ratio_manager.py
"""
Band Ratio / Peak Area Calculator manager — v2.

Reuses the Map2DManager range-filter and integration logic so that band
definitions (include/exclude sub-ranges, global clip) are fully consistent
with the 2D map feature.

Each band is characterised by:
    ranges      : list of [x_start, x_end]  (sub-ranges to include or exclude)
    is_exclude  : bool  (True → exclude the listed ranges, keep the rest)
    metric      : str   same set as Map2DManager
                  "Integral" | "Mean" | "Variance" |
                  "Peak intensity" | "Peak position" |
                  "Baseline-corrected integral"

Operations:
    "A only"  — area of Band A
    "B only"  — area of Band B
    "A / B"   — ratio
    "A - B"   — difference
    "A + B"   — sum
"""

import numpy as np
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)

# np.trapz was removed in NumPy 2.0 (renamed to np.trapezoid). Using this
# shim instead of calling either name directly means this module works
# whether the app is running on NumPy 1.x or 2.x, rather than crashing
# with AttributeError the moment anyone upgrades.
_trapz = getattr(np, 'trapezoid', None) or np.trapz


class BandRatioManager:

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def compute_results(self, spectra: list, settings: dict) -> list:
        """
        Compute band values and arithmetic result for every spectrum.

        Parameters
        ----------
        spectra  : list of spectrum dicts
        settings : dict with keys
            band_a      : dict(ranges, is_exclude, metric)
            band_b      : dict(ranges, is_exclude, metric) or None
            operation   : "A only" | "B only" | "A / B" | "A - B" | "A + B"

        Returns
        -------
        list of result dicts, one per spectrum:
            label, value_a, value_b, result,
            x_a, y_a_raw, y_a_masked,      (for preview)
            x_b, y_b_raw, y_b_masked
        """
        band_a    = settings.get('band_a', {})
        band_b    = settings.get('band_b')
        operation = settings.get('operation', 'A only')

        results = []
        for s in spectra:
            x = np.asarray(s.get('x_scale', []), dtype=float)
            y = np.asarray(s.get('y_scale', []), dtype=float)
            if len(x) < 2:
                # Previously just skipped (`continue`) — the spectrum
                # silently vanished from the Results table with no trace,
                # so a user who selected N spectra could get fewer than N
                # rows back with nothing telling them why or which ones
                # were missing. Now it still gets a row (values shown as
                # "—" by the dialog's table formatter, same as any other
                # None/NaN result), so the spectrum stays visible and
                # accounted for, and a warning is logged with its label.
                logger.warning(
                    "Band Ratio: spectrum '%s' has fewer than 2 data points "
                    "— skipping band computation, shown as empty in results.",
                    s.get('label', '?')
                )
                results.append({
                    'label': s.get('label', '?'), 'value_a': None, 'value_b': None,
                    'result': None, 'x_a': None, 'y_a_raw': None, 'y_a_masked': None,
                    'x_b': None, 'y_b_raw': None, 'y_b_masked': None,
                })
                continue

            # Band A
            x_a, y_a_raw, y_a_masked, value_a = self._compute_band(
                x, y, band_a
            )

            # Band B (optional)
            value_b = None
            x_b = y_b_raw = y_b_masked = None
            if band_b is not None:
                x_b, y_b_raw, y_b_masked, value_b = self._compute_band(
                    x, y, band_b
                )

            # Arithmetic
            result = self._apply_operation(value_a, value_b, operation)

            results.append({
                'label':      s['label'],
                'value_a':    value_a,
                'value_b':    value_b,
                'result':     result,
                'x_a':        x_a,
                'y_a_raw':    y_a_raw,
                'y_a_masked': y_a_masked,
                'x_b':        x_b,
                'y_b_raw':    y_b_raw,
                'y_b_masked': y_b_masked,
            })

        return results

    # ------------------------------------------------------------------ #
    # Band computation                                                     #
    # ------------------------------------------------------------------ #

    def _compute_band(self, x, y, band_def: dict):
        """
        Apply range filter and compute the scalar metric for one band.

        Returns (x_region, y_raw_region, y_masked, value)
        """
        ranges     = band_def.get('ranges', [])
        is_exclude = band_def.get('is_exclude', False)
        metric     = band_def.get('metric', 'Integral')

        # Special case: Intensity at x — snap to nearest point, no range filter
        if metric == 'Intensity at x':
            x_pos = band_def.get('x_pos', 0.0)
            if len(x) < 1:
                return None, None, None, None
            idx   = int(np.argmin(np.abs(x - x_pos)))
            value = float(y[idx])
            return np.array([x[idx]]), np.array([y[idx]]), np.array([y[idx]]), value

        if not ranges:
            # No range defined — use full spectrum
            x_r, y_r = x.copy(), y.copy()
        else:
            include = [] if is_exclude else ranges
            exclude = ranges if is_exclude else []
            x_r, y_r = self._apply_range_filter(x, y, include, exclude)

        if len(x_r) < 2:
            return None, None, None, None

        value = self._compute_metric(x_r, y_r, metric)
        return x_r, y_r, y_r, value

    @staticmethod
    def _apply_range_filter(x, y, include_ranges, exclude_ranges):
        """Mirror of Map2DManager._apply_range_filter."""
        if len(x) == 0:
            return x.copy(), y.copy()
        active = include_ranges or exclude_ranges
        is_excl = bool(exclude_ranges)
        if active:
            bit = np.zeros(len(x), dtype=bool)
            for lo, hi in active:
                lo, hi = min(lo, hi), max(lo, hi)
                bit |= (x >= lo) & (x <= hi)
            if is_excl:
                bit = ~bit
            x, y = x[bit], y[bit]
        return x.copy(), y.copy()

    @staticmethod
    def _compute_metric(x, y, metric: str) -> float:
        """Compute the scalar metric from (x, y) arrays."""
        if len(y) == 0:
            return np.nan
        if metric == 'Integral':
            return float(_trapz(y, x)) if len(x) > 1 else float(y[0])
        elif metric == 'Baseline-corrected integral':
            # Drop-line baseline between first and last point
            if len(x) < 2:
                return float(y[0])
            x0, y0 = x[0], y[0]
            x1, y1 = x[-1], y[-1]
            slope = (y1 - y0) / (x1 - x0) if x1 != x0 else 0.0
            baseline = y0 + slope * (x - x0)
            return float(_trapz(y - baseline, x))
        elif metric == 'Mean':
            return float(np.mean(y))
        elif metric == 'Peak intensity':
            return float(np.max(y))
        elif metric == 'Peak position':
            return float(x[np.argmax(y)])
        elif metric == 'Variance':
            return float(np.var(y))
        elif metric == 'Intensity at x':
            # Handled upstream in _compute_band; fallback: return max
            return float(np.max(y))
        else:
            return float(_trapz(y, x)) if len(x) > 1 else float(y[0])

    @staticmethod
    def _apply_operation(value_a, value_b, operation: str):
        """Combine value_a and value_b according to operation."""
        if value_a is None:
            return None
        if operation == 'A only':
            return value_a
        if operation == 'B only':
            return value_b
        if value_b is None:
            return None
        if operation == 'A / B':
            return float(value_a / value_b) if value_b != 0 else np.nan
        elif operation == 'A - B':
            return float(value_a - value_b)
        elif operation == 'A + B':
            return float(value_a + value_b)
        return None
