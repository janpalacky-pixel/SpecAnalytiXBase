# src/modules/visualization/kept_view.py
""""keep zoom" (Basic plot options): the x range you zoomed to stays when
the plot is drawn again - other spectra selected, one stepped to with the
arrow keys, one hidden in the legend, another plot type with the same
x-axis. y is fitted to the spectra shown in that range (another selection
may have very different intensities). Home shows the whole range, as
before; unticked, every new plot shows the whole range (as before 1.7.0).

Qt-free: MainController remembers the range before a new plot
(zoomed_range) and puts it on the new plot (apply). A plot remembers its
whole range (home) in ax._sax_home_x when it is drawn (mark_home)."""

import numpy as np

REL_TOL = 1e-6           # a range this close to the whole one is not "zoomed"


def plot_axes(figure):
    """The plots of a figure (not colour bars nor hidden panels)."""
    return [ax for ax in figure.axes
            if ax.get_visible() and not hasattr(ax, '_colorbar')
            and ax.get_label() != '<colorbar>']


def x_range(ax):
    lo, hi = ax.get_xlim()
    return (min(lo, hi), max(lo, hi))


def mark_home(figure):
    """Remember each plot's whole x range (as drawn, before any zoom) and
    its y range then."""
    for ax in plot_axes(figure):
        ax._sax_home_x = x_range(ax)
        ax._sax_home_y = tuple(ax.get_ylim())


def push_home(figure, toolbar):
    """The toolbar's history starts again (e.g. "reverse x" switched while
    zoomed): its first view - Home - the whole range, then the view shown
    now (Back from it: the whole range)."""
    now = []
    for ax in plot_axes(figure):
        home = getattr(ax, '_sax_home_x', None)
        if home is None:
            continue
        now.append((ax, ax.get_xlim(), ax.get_ylim()))
        lo, hi = home
        ax.set_xlim((hi, lo) if ax.xaxis_inverted() else (lo, hi))
        if getattr(ax, '_sax_scaled_top', None) is None and \
                getattr(ax, '_sax_home_y', None) is not None:
            ax.set_ylim(*ax._sax_home_y)
    if not now:
        return False
    toolbar.push_current()
    for ax, xlim, ylim in now:
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
    toolbar.push_current()
    return True


def _same(a, b):
    span = max(abs(b[1] - b[0]), 1e-300)
    return abs(a[0] - b[0]) <= REL_TOL * span and abs(a[1] - b[1]) <= REL_TOL * span


def zoomed_range(figure):
    """The x range (low, high) the plot is zoomed to, or None when it shows
    its whole range (or was never marked)."""
    if figure is None:
        return None
    for ax in plot_axes(figure):
        home = getattr(ax, '_sax_home_x', None)
        if home is None:
            continue
        now = x_range(ax)
        if not _same(now, home):
            return now
    return None


def _spectrum_lines(ax):
    """The spectra's visible lines (no gid: not band markers, the cursor...)."""
    return [line for line in ax.get_lines()
            if not line.get_gid() and line.get_visible()
            and len(np.atleast_1d(line.get_xdata())) >= 2]


def has_data_in(figure, lo, hi):
    """Has any spectrum of the plot at least two points within lo..hi?"""
    for ax in plot_axes(figure):
        for line in _spectrum_lines(ax):
            x = np.asarray(line.get_xdata(), dtype=float)
            if np.count_nonzero((x >= lo) & (x <= hi)) >= 2:
                return True
        if ax.images:                          # e.g. a heatmap: its x extent
            for im in ax.images:
                x0, x1 = sorted(im.get_extent()[:2])
                if x0 < hi and x1 > lo:
                    return True
    return False


def _visible_y(ax, lo, hi):
    """The lowest and highest y drawn in the axes' data units between lo and
    hi: the spectra's lines and filled bands (e.g. Mean +- SD)."""
    values = []
    for line in _spectrum_lines(ax):
        if line.get_transform() != ax.transData:
            continue                           # e.g. "scale each": fitted on its own
        x = np.asarray(line.get_xdata(), dtype=float)
        y = np.asarray(line.get_ydata(), dtype=float)
        if x.shape != y.shape:
            continue
        inside = (x >= lo) & (x <= hi) & np.isfinite(y)
        if inside.any():
            values.append(y[inside])
    for coll in ax.collections:
        if coll.get_transform() != ax.transData or not coll.get_visible() or coll.get_gid():
            continue
        try:
            paths = coll.get_paths()
        except Exception:
            continue
        for path in paths:
            v = np.asarray(path.vertices, dtype=float)
            if v.ndim != 2 or v.shape[1] != 2:
                continue
            inside = (v[:, 0] >= lo) & (v[:, 0] <= hi) & np.isfinite(v[:, 1])
            if inside.any():
                values.append(v[inside, 1])
    if not values:
        return None
    y = np.concatenate(values)
    if ax.get_yscale() == 'log':
        y = y[y > 0]
    if not y.size:
        return None
    return float(np.min(y)), float(np.max(y))


def fit_y(ax, lo, hi, margin=0.05, found=None):
    """y of the axes fitted to what is drawn between lo and hi (with a
    margin as matplotlib's own); found: (lowest, highest) to fit instead
    (e.g. of all panels sharing y). True if set."""
    if found is None:
        found = _visible_y(ax, lo, hi)
    if found is None:
        return False
    y0, y1 = found
    if ax.get_yscale() == 'log':
        ly0, ly1 = np.log10(y0), np.log10(y1)
        pad = (ly1 - ly0) * margin if ly1 > ly0 else 0.5
        y0, y1 = 10 ** (ly0 - pad), 10 ** (ly1 + pad)
    else:
        pad = (y1 - y0) * margin if y1 > y0 else (abs(y0) * 0.05 or 1.0)
        y0, y1 = y0 - pad, y1 + pad
    if ax.yaxis_inverted():
        y0, y1 = y1, y0
    ax.set_ylim(y0, y1)
    return True


def apply(figure, lo, hi, refit_y=True):
    """Every plot of the figure shows x from lo to hi (in its own direction:
    "reverse x" stays reversed), y fitted to it (refit_y). Returns the
    number of plots changed."""
    axes = plot_axes(figure)
    for ax in axes:
        if ax.xaxis_inverted():
            ax.set_xlim(hi, lo)
        else:
            ax.set_xlim(lo, hi)
    if refit_y:
        found = {ax: _visible_y(ax, lo, hi) for ax in axes
                 if getattr(ax, '_sax_scaled_top', None) is None}   # not "scale each"
        for ax in found:
            # panels sharing y (Grid plot, Link y-axes): all of them fitted
            group = [a for a in ax.get_shared_y_axes().get_siblings(ax) if a in found]
            ys = [found[a] for a in group if found[a] is not None]
            if ys:
                fit_y(ax, lo, hi, found=(min(y[0] for y in ys), max(y[1] for y in ys)))
    return len(axes)
