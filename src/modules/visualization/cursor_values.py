# src/modules/visualization/cursor_values.py
"""Values of the drawn spectra at one x-position (the vertical cursor of the
main plot, see plot_cursor_controller.py). Qt-free.

A spectrum's value at x is interpolated linearly between its two measured
points around x -- what the drawn line shows there. Outside a spectrum's
x-range it has no value (None), never an extrapolated one."""

import numpy as np

MAX_LISTED = 10          # the box next to the cursor lists at most this many


def value_at(x_data, y_data, x):
    """The value of one curve at x, or None outside its x-range."""
    xd = np.asarray(x_data, dtype=float)
    yd = np.asarray(y_data, dtype=float)
    ok = np.isfinite(xd) & np.isfinite(yd)
    xd, yd = xd[ok], yd[ok]
    if len(xd) < 2:
        return None
    if xd[0] > xd[-1]:
        xd, yd = xd[::-1], yd[::-1]
    if not np.all(np.diff(xd) >= 0):
        order = np.argsort(xd, kind='stable')
        xd, yd = xd[order], yd[order]
    if x < xd[0] or x > xd[-1]:
        return None
    return float(np.interp(x, xd, yd))


def values_at(curves, x):
    """[(label, value), ...] for the curves (label, x_data, y_data) that
    have a value at x, in the given order."""
    out = []
    for label, xd, yd in curves:
        v = value_at(xd, yd, x)
        if v is not None:
            out.append((label, v))
    return out


def listed(values, pointer_y=None, limit=MAX_LISTED):
    """The (label, value) pairs to list next to the cursor and how many are
    left out: all of them when there are at most `limit`, otherwise the
    `limit` nearest to the mouse pointer's height. Listed from the highest
    value down (as they lie in the plot)."""
    vals = list(values)
    hidden = 0
    if len(vals) > limit:
        if pointer_y is not None:
            vals.sort(key=lambda lv: abs(lv[1] - pointer_y))
        hidden = len(vals) - limit
        vals = vals[:limit]
    vals.sort(key=lambda lv: -lv[1])
    return vals, hidden


def fmt(v):
    """A value for the readout: 6 significant digits without an exponent for
    ordinary sizes, otherwise 4 with one."""
    if v is None or not np.isfinite(v):
        return '\u2014'
    a = abs(v)
    if a == 0 or 1e-3 <= a < 1e7:
        return f"{v:.6g}"          # 270234, 1234.57, 0.53213
    return f"{v:.4g}"              # 1.2e-05, 3.4e+08


def table_text(curves, xs):
    """Tab-separated table (for Excel): one row per curve, one column per
    pinned cursor; an empty cell where a curve has no value at that x."""
    head = ["Spectrum"] + [f"x = {fmt(x)}" for x in xs]
    rows = ["\t".join(head)]
    for label, xd, yd in curves:
        cells = []
        for x in xs:
            v = value_at(xd, yd, x)
            cells.append("" if v is None else repr(float(v)))
        rows.append("\t".join([str(label)] + cells))
    return "\n".join(rows) + "\n"
