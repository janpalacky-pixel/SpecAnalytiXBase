# src/modules/visualization/band_between.py
"""Values of the spectra between two band markers (right-click on the plot
between them): for each spectrum its maximum and minimum, its area, and -
above the straight line that joins the spectrum's values at the two
markers (a local baseline, as for a band on a background) - the band's
position and height, its area and its centroid. Also the distance between
the two markers. Copied as a tab-separated table for Excel.

Qt-free. curves: [(label, x values, y values)] - the spectra's own values
(PlotCursorController.all_curves)."""

import numpy as np

from src.modules.visualization.cursor_values import fmt, value_at

COLUMNS = ("Max position", "Max value", "Min position", "Min value", "Area",
           "Band position (above the line)", "Band height (above the line)",
           "Area above the line", "Centroid (above the line)")

_trapz = getattr(np, 'trapezoid', None) or np.trapz


def pair_around(markers, x):
    """The two neighbouring markers [(label, position)] with x between them:
    ((label, low), (label, high)), or None (x outside them, fewer than 2)."""
    xs = sorted(((float(p), lab) for lab, p in markers), key=lambda t: t[0])
    for (a, la), (b, lb) in zip(xs, xs[1:]):
        if a < b and a <= x <= b:
            return (la, a), (lb, b)
    return None


def segment(xd, yd, a, b):
    """The spectrum between a and b (a < b), from low to high x, with its
    values exactly at a and b (interpolated). None if it does not reach
    both a and b."""
    x = np.asarray(xd, dtype=float)
    y = np.asarray(yd, dtype=float)
    ya, yb = value_at(x, y, a), value_at(x, y, b)
    if ya is None or yb is None:
        return None
    ok = np.isfinite(x) & np.isfinite(y) & (x > a) & (x < b)
    xs = np.concatenate([[a], x[ok], [b]])
    ys = np.concatenate([[ya], y[ok], [yb]])
    order = np.argsort(xs, kind='stable')
    return xs[order], ys[order]


def values_between(xd, yd, a, b):
    """{column: value} of one spectrum between a and b (see COLUMNS), or
    None when the spectrum does not reach both."""
    seg = segment(xd, yd, min(a, b), max(a, b))
    if seg is None:
        return None
    xs, ys = seg
    lo, hi = xs[0], xs[-1]
    line = ys[0] + (ys[-1] - ys[0]) * (xs - lo) / (hi - lo) if hi > lo else np.full_like(ys, ys[0])
    above = ys - line
    i_max, i_min = int(np.argmax(ys)), int(np.argmin(ys))
    i_band = int(np.argmax(np.abs(above)))
    # the centroid of the band: of the part on the side of its extreme
    side = np.clip(above, 0, None) if above[i_band] >= 0 else np.clip(-above, 0, None)
    weight = float(_trapz(side, xs))
    centroid = float(_trapz(xs * side, xs) / weight) if weight > 0 else None
    return {
        "Max position": float(xs[i_max]), "Max value": float(ys[i_max]),
        "Min position": float(xs[i_min]), "Min value": float(ys[i_min]),
        "Area": float(_trapz(ys, xs)),
        "Band position (above the line)": float(xs[i_band]),
        "Band height (above the line)": float(above[i_band]),
        "Area above the line": float(_trapz(above, xs)),
        "Centroid (above the line)": centroid,
    }


def table_text(curves, a, b, names=(None, None)):
    """Tab-separated table for Excel: one row per spectrum, the columns of
    COLUMNS; the first cell names the range (and the markers' own names,
    e.g. "Phe"). Empty cells where a spectrum does not reach both."""
    lo, hi = min(a, b), max(a, b)
    na, nb = names if a <= b else names[::-1]

    def name(n, x):
        return f"{n} ({fmt(x)})" if n and str(n) != fmt(x) else fmt(x)
    head = [f"Spectrum (x {name(na, lo)} – {name(nb, hi)}, Δ = {fmt(hi - lo)})"]
    rows = ["\t".join(head + list(COLUMNS))]
    for label, xd, yd in curves:
        v = values_between(xd, yd, lo, hi)
        cells = ["" if v is None or v[c] is None else repr(float(v[c])) for c in COLUMNS]
        rows.append("\t".join([str(label)] + cells))
    return "\n".join(rows) + "\n"
