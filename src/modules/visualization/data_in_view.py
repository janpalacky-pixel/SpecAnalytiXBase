# src/modules/visualization/data_in_view.py
"""Right-click on the plot > Copy the data in view: the spectra shown, only
within the x range in view (zoomed in on a band: that band), as a
tab-separated table for Excel - the spectra's own values (also in a
Waterfall plot and with "scale each"), hidden spectra left out.

One x column and a column per spectrum when all of them have the same x
values there; otherwise two columns per spectrum (its x and its values),
as Export spectra's interlaced layout. Qt-free; curves: [(label, x values,
y values)] (PlotCursorController.all_curves)."""

import numpy as np

from src.modules.visualization.cursor_values import fmt


def _inside(x, y, lo, hi):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    keep = np.isfinite(x) & (x >= lo) & (x <= hi)
    x, y = x[keep], y[keep]
    order = np.argsort(x, kind='stable')
    return x[order], y[order]


def _cell(v):
    return "" if v is None or not np.isfinite(v) else repr(float(v))


def table_text(curves, lo, hi):
    """(text, spectra, rows): the table and its size."""
    lo, hi = min(lo, hi), max(lo, hi)
    parts = [(str(label),) + _inside(x, y, lo, hi) for label, x, y in curves]
    parts = [p for p in parts if len(p[1])]
    if not parts:
        return "", 0, 0
    same = all(len(p[1]) == len(parts[0][1]) and np.allclose(p[1], parts[0][1])
               for p in parts[1:])
    lines = []
    if same:
        lines.append("\t".join([f"x ({fmt(lo)} – {fmt(hi)})"] + [p[0] for p in parts]))
        for i, xv in enumerate(parts[0][1]):
            lines.append("\t".join([_cell(xv)] + [_cell(p[2][i]) for p in parts]))
        n_rows = len(parts[0][1])
    else:
        head = []
        for p in parts:
            head += [f"x: {p[0]}", p[0]]
        lines.append("\t".join(head))
        n_rows = max(len(p[1]) for p in parts)
        for i in range(n_rows):
            cells = []
            for _, x, y in parts:
                cells += [_cell(x[i]), _cell(y[i])] if i < len(x) else ["", ""]
            lines.append("\t".join(cells))
    return "\n".join(lines) + "\n", len(parts), n_rows
