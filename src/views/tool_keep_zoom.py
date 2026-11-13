# src/views/tool_keep_zoom.py
""""keep zoom" in the tool windows that show one spectrum after another:
Peak Fitting (the arrows, the list), the baseline windows (manual,
automated, SNIP), FFT denoising, Normalization, Spike removal and
Interactive subtraction. (Smoothing - Savitzky-Golay - shows its preview
on the main plot, which keeps its zoom itself.) Zoomed in on a band (mouse wheel,
Zoom, Pan, a drag), the plot stays there when the window draws it again -
another spectrum chosen in its list, a parameter changed - and y is fitted
to what is shown, as in the main window (kept_view.py). Home shows the
whole range; "keep zoom" unticked in the main window: as before.

Works for any plot of these windows without changing them: attached by
toolbar_mode's application event filter to the canvas of each plot toolbar
of such a window (WINDOWS). It remembers the x range the user zoomed to
(after the wheel or a drag - plot_navigation.py -, after Zoom, Pan, Home,
Back, Forward of the toolbar) for each plot of the canvas (by its place in
the figure), and just before the canvas draws: a plot that shows its whole
range again (the window drew it anew) while the user had zoomed is set
back to that range - if it has data there and the same x-axis title. A
range the window narrows itself is left alone."""

from src.modules.visualization import kept_view

WINDOWS = ('PeakFittingDialog', 'BaselineCorrectionDialog', 'AutomatedBaselineDialog',
           'SNIPBaselineDialog', 'FFTDenoisingDialog',
           'NormalizationDialog', 'SpikeRemovalInteractiveDialog',
           'InteractiveSubtractionDialog')
INSIDE = 0.005           # a range this far (of the data's span) inside the data: zoomed
_OWN = '_sax_keep_zoom'
ZOOM_NOTE = "Zoomed: {lo}\u2013{hi} \u2013 Home shows all"
enabled = True           # MainController: the "keep zoom" tick of the main window


def set_enabled(on):
    global enabled
    enabled = bool(on)


def wanted(toolbar):
    """Is the toolbar's plot in one of WINDOWS?"""
    try:
        window = toolbar.window()
    except Exception:
        return False
    return type(window).__name__ in WINDOWS


def _full(ax):
    """(low, high) of the data the spectra's lines have, or None."""
    lo = hi = None
    for line in kept_view._spectrum_lines(ax):
        try:
            import numpy as np
            x = np.asarray(line.get_xdata(), dtype=float)
            x = x[np.isfinite(x)]
        except Exception:
            continue
        if x.size < 2:
            continue
        lo = float(x.min()) if lo is None else min(lo, float(x.min()))
        hi = float(x.max()) if hi is None else max(hi, float(x.max()))
    return None if lo is None or not hi > lo else (lo, hi)


def is_zoomed(rng, full):
    """A range inside the data's range (not the whole of it)."""
    span = full[1] - full[0]
    return (rng[0] > full[0] + INSIDE * span or rng[1] < full[1] - INSIDE * span) \
        and rng[1] > full[0] and rng[0] < full[1]


class KeepZoom:
    def __init__(self, canvas):
        self.canvas = canvas
        self.kept = {}                 # place of the plot -> (low, high, x-axis title)
        original = canvas.draw

        def draw(*args, **kwargs):
            try:
                self.fix()
            except Exception:
                pass
            return original(*args, **kwargs)
        canvas.draw = draw

    def record(self):
        """After the user zoomed, panned or went Home / Back / Forward."""
        self.kept = {}
        for i, ax in enumerate(kept_view.plot_axes(self.canvas.figure)):
            full = _full(ax)
            if full is None:
                continue
            rng = kept_view.x_range(ax)
            if is_zoomed(rng, full):
                self.kept[i] = (rng[0], rng[1], ax.get_xlabel())
        self.note()

    def note(self):
        """The orange "Zoomed: ... - Home shows all" note beside the plot's
        toolbar buttons while a zoom is kept (as in the main window)."""
        toolbar = getattr(self.canvas, 'toolbar', None)
        if toolbar is None:
            return
        text = ''
        if enabled and self.kept:
            from src.modules.visualization.plot_notes import fmt
            lo, hi, _label = self.kept[min(self.kept)]
            text = ZOOM_NOTE.format(lo=fmt(lo), hi=fmt(hi))
        try:
            from src.views import toolbar_mode
            toolbar_mode.set_note(toolbar, text, key='zoom')
        except Exception:
            pass

    def fix(self):
        """Just before a draw: a plot drawn anew (its whole range) goes back
        to the range the user zoomed to."""
        if not enabled or not self.kept:
            return
        axes = kept_view.plot_axes(self.canvas.figure)
        done = set()
        restored = []
        for i, (lo, hi, label) in self.kept.items():
            if i >= len(axes) or i in done:
                continue
            ax = axes[i]
            full = _full(ax)
            if full is None or is_zoomed(kept_view.x_range(ax), full):
                continue                       # zoomed (by the user or the window): as it is
            if label and ax.get_xlabel() and ax.get_xlabel() != label:
                continue                       # another kind of plot there now
            if not _has_data(ax, lo, hi):
                continue
            ax._sax_home_x = kept_view.x_range(ax)    # Home: the whole range
            ax._sax_home_y = tuple(ax.get_ylim())
            restored.append(ax)
            ax.set_xlim((hi, lo) if ax.xaxis_inverted() else (lo, hi))
            kept_view.fit_y(ax, lo, hi)
            # axes sharing x follow by themselves; their y fitted too
            for j, other in enumerate(axes):
                if other is not ax and other in ax.get_shared_x_axes().get_siblings(ax):
                    kept_view.fit_y(other, lo, hi)
                    done.add(j)
        toolbar = getattr(self.canvas, 'toolbar', None)
        if restored and toolbar is not None:
            # the plot was drawn anew: the toolbar's history is of the old one
            # (Home would do nothing) - it starts again with the whole range
            # (Home), then the zoom (Back from Home)
            try:
                toolbar.update()
                kept_view.push_home(self.canvas.figure, toolbar)
            except Exception:
                pass


def _has_data(ax, lo, hi):
    import numpy as np
    for line in kept_view._spectrum_lines(ax):
        x = np.asarray(line.get_xdata(), dtype=float)
        if np.count_nonzero((x >= lo) & (x <= hi)) >= 2:
            return True
    return False


def keeper(canvas):
    return getattr(canvas, _OWN, None) if canvas is not None else None


def record(canvas):
    """The user changed the view of `canvas` (plot_navigation, the toolbar)."""
    kz = keeper(canvas)
    if kz is not None:
        try:
            kz.record()
        except Exception:
            pass


def attach(toolbar):
    """Keep the zoom of this toolbar's plot (a window of WINDOWS; once)."""
    canvas = getattr(toolbar, 'canvas', None)
    if canvas is None or keeper(canvas) is not None or not wanted(toolbar):
        return keeper(canvas)
    kz = KeepZoom(canvas)
    setattr(canvas, _OWN, kz)
    # the toolbar's own view changes: remembered afterwards (Home, Back and
    # Forward all go through _update_view; the buttons hold the bound
    # methods made at the start, so those are not wrapped themselves)
    for name in ('_update_view', 'release_zoom', 'release_pan'):
        method = getattr(toolbar, name, None)
        if method is None:
            continue

        def wrapped(*args, _method=method, **kwargs):
            result = _method(*args, **kwargs)
            record(canvas)
            return result
        setattr(toolbar, name, wrapped)
    return kz
