# src/modules/utils/band_integration.py
"""Area, mean and baseline-corrected area of a spectrum over spectral
ranges -- shared by the 2D Map, Band Ratio and Group Statistics.

Why not simply np.trapz over the points that fall inside the range (as
these tools did before)?

1. Range edges: the area then starts and ends at the first / last measured
   point INSIDE the range, so up to one point spacing is missing at each
   end, and how much depends on where the points happen to fall. Spectra
   with different x-axes were therefore integrated over slightly different
   widths. Here the spectrum is interpolated exactly at the range edges.
2. Several ranges (include mode with 2+ ranges, or exclude mode): the
   points of all ranges were joined into one list, so the trapezoid
   bridged every gap with a straight line and added the area UNDER that
   bridge -- the area of the excluded part was counted after all. Here
   each range is integrated on its own and the areas are added.
3. Mean: the plain average of the points over-weights densely sampled
   parts when the spacing is uneven. Here mean = area / width (the
   average height of the curve), which does not depend on the spacing.
4. Baseline-corrected area: the straight baseline now runs between the
   spectrum's values AT the range edges (interpolated), not between the
   first and last point inside the range.

5. Coverage: a spectrum that does not cover the whole range gets NO
   value (covers() below), instead of a value computed over the part it
   has -- such a value looks like a real, just smaller one, and comparing
   it with spectra that cover the whole range is meaningless.
"""
import numpy as np

_trapz = getattr(np, 'trapezoid', None) or np.trapz      # numpy 2 renamed trapz


def finite_sorted(x, y):
    """x, y as float arrays without NaN/inf points, x ascending."""
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    if len(x) > 1 and np.any(np.diff(x) < 0):
        order = np.argsort(x, kind='stable')
        x, y = x[order], y[order]
    return x, y


def edge_tolerance(x):
    """Half a point spacing: a range edge this close outside the measured
    points still counts as covered (e.g. 200.0 typed, first point 200.02)."""
    if len(x) < 2:
        return 0.0
    return 0.5 * float(np.median(np.diff(x)))


def covers(x, ranges):
    """True if the spectrum (ascending x) covers every range completely
    (within edge_tolerance). No ranges = nothing to cover = True."""
    if not ranges:
        return True
    if len(x) < 2:
        return False
    tol = edge_tolerance(x)
    return all(min(a, b) >= x[0] - tol and max(a, b) <= x[-1] + tol for a, b in ranges)


def covers_x(x, x0):
    """True if x0 lies within the spectrum (within edge_tolerance)."""
    return len(x) > 0 and x[0] - edge_tolerance(x) <= x0 <= x[-1] + edge_tolerance(x)


def _merge(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def integration_intervals(x, x_min=None, x_max=None, include=None, exclude=None):
    """The x-intervals to integrate over, sorted and non-overlapping.

    x            : ascending x of one spectrum (its measured range is the limit)
    x_min, x_max : optional overall clip (used only when both are given)
    include      : list of (start, end): only these parts
    exclude      : list of (start, end): everything except these parts
    (give include OR exclude; with neither, the whole clipped range)."""
    if len(x) < 2:
        return []
    lo, hi = float(x[0]), float(x[-1])
    if x_min is not None and x_max is not None:
        lo, hi = max(lo, min(x_min, x_max)), min(hi, max(x_min, x_max))
    if lo >= hi:
        return []
    if include:
        parts = [(max(lo, min(a, b)), min(hi, max(a, b))) for a, b in include]
        return _merge([(a, b) for a, b in parts if a < b])
    if exclude:
        out, cur = [], lo
        for a, b in _merge([(min(a, b), max(a, b)) for a, b in exclude]):
            if b <= cur:
                continue
            if a >= hi:
                break
            if a > cur:
                out.append((cur, a))
            cur = max(cur, b)
        if cur < hi:
            out.append((cur, hi))
        return out
    return [(lo, hi)]


def _segment(x, y, a, b):
    """Points of the spectrum from a to b, with values interpolated exactly
    at a and b."""
    inside = (x > a) & (x < b)
    xs = np.concatenate(([a], x[inside], [b]))
    ys = np.concatenate(([np.interp(a, x, y)], y[inside], [np.interp(b, x, y)]))
    return xs, ys


def band_area(x, y, intervals):
    """Area under the spectrum over the intervals (NaN if there are none)."""
    if not intervals or len(x) < 2:
        return np.nan
    return float(sum(_trapz(*_segment(x, y, a, b)[::-1]) for a, b in intervals))


def band_mean(x, y, intervals):
    """Average height of the spectrum over the intervals = area / width."""
    width = sum(b - a for a, b in intervals) if intervals else 0.0
    if width <= 0:
        return np.nan
    return band_area(x, y, intervals) / width


def baseline_corrected_area(x, y, intervals):
    """Area above the straight line joining the spectrum's values at the
    first and the last range edge (the "chord"), over the intervals."""
    if not intervals or len(x) < 2:
        return np.nan
    a0, b1 = intervals[0][0], intervals[-1][1]
    if b1 <= a0:
        return np.nan
    ya, yb = np.interp(a0, x, y), np.interp(b1, x, y)
    total = 0.0
    for a, b in intervals:
        xs, ys = _segment(x, y, a, b)
        line = ya + (yb - ya) * (xs - a0) / (b1 - a0)
        total += _trapz(ys - line, xs)
    return float(total)


def metric_value(x, y, metric, intervals):
    """'Integral' | 'Mean' | 'Baseline-corrected integral' over intervals."""
    if metric == 'Integral':
        return band_area(x, y, intervals)
    if metric == 'Mean':
        return band_mean(x, y, intervals)
    if metric == 'Baseline-corrected integral':
        return baseline_corrected_area(x, y, intervals)
    raise ValueError(f"not an area metric: {metric!r}")


AREA_METRICS = ('Integral', 'Mean', 'Baseline-corrected integral')
