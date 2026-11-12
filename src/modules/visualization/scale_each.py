# src/modules/visualization/scale_each.py
""""scale each" (Basic plot options): every spectrum is drawn from 0 (its
lowest point in the view) to 1 (its highest point in the view), so spectra
of very different intensity - or on different baselines - can be compared
by their shape (e.g. unnormalized Raman spectra). Zoomed in on a band, each
spectrum is fitted to that band; zoomed out again, to the whole spectrum.

Only the drawing changes. The lines keep their data (line.get_ydata() is
the spectrum's own values): the Cursor lists the real values, Copy the
values at the band markers copies them, Detect Peaks finds the same peaks
with their real heights. Each line gets a transform of its own
(ViewScale + ax.transData) that is worked out from the axes' x range when
the line is drawn; whatever is drawn with the line's transform
(line.get_transform(): the peaks' dots and numbers, a peak shown from the
Peak list, the fitted peaks) stays on the line.

At a band marker (right-click on a marker > Scale each spectrum to 1 at
the band marker ...): 0 is still each spectrum's lowest point in the view,
1 its value at the marker (e.g. an internal standard such as Phe at 1004 -
other bands may be higher than 1); the y range follows what is shown.

Overlay, Waterfall (the offsets in the same proportion as without it)
and Grid plot, with a linear Y-scale. Qt-free: the main window and Open in
New Window call apply() on a finished plot (as cd_quality_shading)."""

import numpy as np
from matplotlib.transforms import Affine2DBase

PLOT_TYPES = ('Overlay plot', 'Waterfall plot', 'Grid plot')
MARGIN = 0.05            # below 0 and above 1 (the top spectrum's 1)
Y_NOTE = "each scaled 0–1"


def available(plot_type, y_scale='linear'):
    """Can the spectra be scaled in this plot type with this Y-scale?"""
    return plot_type in PLOT_TYPES and str(y_scale).lower() == 'linear'


class ViewScale(Affine2DBase):
    """y -> a*y + b: the line's lowest value within the axes' x range at
    `base`, its highest at base + 1 (a line flat there: at base + 0.5).
    Worked out again whenever the x range changes (zoom, pan, Home)."""

    def __init__(self, line, view_lim, base=0.0, at_x=None):
        super().__init__()
        self.at_x = None if at_x is None else float(at_x)
        self._x = line.get_xdata()             # the line's own arrays, not copies
        self._y = line.get_ydata()
        self._view = view_lim                  # ax.viewLim: invalidates this
        self.base = float(base)
        self._key = None
        self._mtx = np.eye(3)
        self.set_children(view_lim)

    def factors(self, x0, x1):
        """(a, b) for the x range x0..x1."""
        x = np.asarray(self._x, dtype=float)
        y = np.asarray(self._y, dtype=float)
        lo, hi = min(x0, x1), max(x0, x1)
        inside = (x >= lo) & (x <= hi) & np.isfinite(y)
        if np.count_nonzero(inside) < 2:       # (almost) nothing in view: the whole
            inside = np.isfinite(y)
        if not inside.any():
            return 1.0, self.base
        y_lo, y_hi = float(np.min(y[inside])), float(np.max(y[inside]))
        if self.at_x is not None:
            # 1 at the band marker: the spectrum's value there (if it reaches it
            # and it is above the lowest point in view; otherwise as without)
            at = _value_at(x, y, self.at_x)
            if at is not None and at > y_lo:
                y_hi = at
        if not y_hi > y_lo:
            return 0.0, self.base + 0.5
        a = 1.0 / (y_hi - y_lo)
        return a, self.base - y_lo * a

    def get_matrix(self):
        try:
            x0, x1 = (float(v) for v in self._view.intervalx)
        except Exception:
            return self._mtx
        key = (x0, x1)
        if key != self._key or self._invalid:
            a, b = self.factors(x0, x1)
            self._mtx = np.array([[1.0, 0.0, 0.0], [0.0, a, b], [0.0, 0.0, 1.0]])
            self._key = key
            self._invalid = 0
        return self._mtx


def _value_at(x, y, x0):
    from src.modules.visualization.cursor_values import value_at
    return value_at(x, y, x0)


def _plot_axes(figure):
    return [ax for ax in figure.axes
            if ax.get_visible() and not hasattr(ax, '_colorbar')
            and ax.get_label() != '<colorbar>']


def _spectrum_lines(ax):
    """The spectra's lines (and their points): not band markers, the
    cursor or other marks of the program (gid 'sax_...', 'peak_...')."""
    out = []
    for line in ax.get_lines():
        gid = str(line.get_gid() or '')
        if gid:
            continue
        if len(np.atleast_1d(line.get_xdata())) < 2:
            continue
        out.append(line)
    return out


def apply(figure, y_label=True, at_x=None):
    """Scale every spectrum of a finished plot (see the module). Returns
    the number of lines scaled. The y range: 0..1 (Waterfall: up to the top
    spectrum's 1) with a small margin - reset_y()."""
    n = 0
    for ax in _plot_axes(figure):
        lines = _spectrum_lines(ax)
        if not lines:
            continue
        # Waterfall: the spectra shifted by k x offset (line._sax_shift) are
        # shifted by k x offset / (the largest spectrum's height): as far
        # apart, in proportion, as without scaling
        height = float(getattr(ax, '_sax_waterfall_height', 0.0) or 0.0)
        top = 1.0
        for line in lines:
            shift = float(getattr(line, '_sax_shift', 0.0) or 0.0)
            base = shift / height if height > 0 else 0.0
            scale = ViewScale(line, ax.viewLim, base, at_x)
            line._sax_scale = scale
            line.set_transform(scale + ax.transData)
            top = max(top, base + 1.0)
            n += 1
        ax._sax_scaled_top = top
        ax._sax_scale_at = None if at_x is None else float(at_x)
        reset_y(ax)
        if y_label:
            note = Y_NOTE if at_x is None else y_note_at(at_x)
            label = ax.get_ylabel()
            if label:
                ax.set_ylabel(f"{label} – {note}")
            elif len(_plot_axes(figure)) == 1:
                ax.set_ylabel(f"Intensity – {note}")
    if n:
        figure._sax_scale_each = True
    return n


def y_note_at(x0):
    from src.modules.visualization.plot_notes import fmt
    return f"each 1 at {fmt(x0)}"


def y_range(ax):
    """0..1 (Waterfall: up to the top spectrum's 1) with a margin; at a band
    marker: what the scaled spectra reach in the view."""
    top = float(getattr(ax, '_sax_scaled_top', 1.0))
    if getattr(ax, '_sax_scale_at', None) is None:
        return -MARGIN, top + MARGIN
    x0, x1 = sorted(float(v) for v in ax.get_xlim())
    lo, hi = None, None
    for line in ax.get_lines():
        scale = getattr(line, '_sax_scale', None)
        if scale is None or not line.get_visible():
            continue
        x = np.asarray(line.get_xdata(), dtype=float)
        y = np.asarray(line.get_ydata(), dtype=float)
        inside = (x >= x0) & (x <= x1) & np.isfinite(y)
        if not inside.any():
            continue
        m = scale.get_matrix()
        shown = y[inside] * m[1, 1] + m[1, 2]
        lo = float(shown.min()) if lo is None else min(lo, float(shown.min()))
        hi = float(shown.max()) if hi is None else max(hi, float(shown.max()))
    if lo is None or not hi > lo:
        return -MARGIN, top + MARGIN
    pad = (hi - lo) * MARGIN
    return lo - pad, hi + pad


def reset_y(ax):
    """The y range that shows every scaled spectrum whole. True if changed."""
    if getattr(ax, '_sax_scaled_top', None) is None:
        return False
    lo, hi = y_range(ax)
    if np.allclose(ax.get_ylim(), (lo, hi), rtol=1e-12, atol=1e-12):
        return False
    ax.set_ylim(lo, hi)
    return True


def follow_x(figure, later):
    """After a change of the x range (zoom, pan, Home - which may also have
    changed y, e.g. a Zoom rectangle) the y range is reset: the spectra are
    fitted to the new x range, so the whole 0..1 is to be seen. `later`
    (callable taking a function) runs it once the change is complete (Qt:
    QTimer.singleShot(0, ...)). Ctrl + wheel (y only) is kept until x
    changes."""
    for ax in _plot_axes(figure):
        if getattr(ax, '_sax_scaled_top', None) is None:
            continue

        def changed(_ax, ax=ax):
            if getattr(ax, '_sax_reset_pending', False):
                return
            ax._sax_reset_pending = True

            def run():
                ax._sax_reset_pending = False
                try:
                    if reset_y(ax) and ax.figure.canvas is not None:
                        ax.figure.canvas.draw_idle()
                except Exception:
                    pass
            later(run)
        ax.callbacks.connect('xlim_changed', changed)


def is_on(figure):
    return bool(getattr(figure, '_sax_scale_each', False))


def shown_y(line, y):
    """Where the value y of `line` is drawn (in the axes' y units): itself
    unless the line is scaled."""
    scale = getattr(line, '_sax_scale', None)
    if scale is None or y is None:
        return y
    m = scale.get_matrix()
    return float(y) * m[1, 1] + m[1, 2]
