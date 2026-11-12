# src/views/plot_navigation.py
"""The mouse conveniences of the main plot for the plots of the tool
windows (Peak Fitting, Baseline, SVD, PCA, 2D Map, Open in New Window ...):

* the mouse wheel zooms the x axis around the mouse - forward (away from
  you) in, back out; with Ctrl the y axis. Back / Home of the plot's
  toolbar go back, step by step or to the start;
* the left mouse button held and the mouse moved drags the plot, as Pan of
  the toolbar does - without choosing Pan first.

Attached by toolbar_mode's application event filter to the canvas of every
plot toolbar (NavigationToolbar2QT) when the toolbar is first shown, so no
window has to do anything. The main plot has its own, richer version
(plot_mouse_controller, which marks its canvas) and is left alone here.

So that nothing a window does with the mouse itself is disturbed, decided
at the moment of the press or the wheel:
* nothing while Zoom or Pan of the toolbar is chosen (they take the mouse);
* no dragging when the window listens to presses on that plot itself -
  e.g. a click adds a peak or a baseline point, a range or a region of the
  map is drawn with the mouse (a SpanSelector, RectangleSelector ...) - or
  when the press is on a movable legend or label (it is dragged instead);
* no wheel zoom when the window uses the wheel on that plot itself;
* only axes that can be zoomed and panned (not a colour bar).
A click without moving stays a click for the window."""

import numpy as np

WHEEL_IN = 0.8          # one wheel step forward zooms in by this
DRAG_PX = 3             # moved further with the button held: a drag, not a click
_OWN = '_sax_navigation'


def zoomed(lo, hi, at, factor, log=False):
    """New limits after zooming by `factor` around `at` (the order - a
    reversed axis - is kept; a log axis zooms in its logarithm)."""
    if log:
        if at <= 0 or lo <= 0 or hi <= 0:
            return lo, hi
        lo, hi, at = np.log10(lo), np.log10(hi), np.log10(at)
    new = at - (at - lo) * factor, at + (hi - at) * factor
    if log:
        new = 10 ** new[0], 10 ** new[1]
    return float(new[0]), float(new[1])


def ctrl_held(event):
    """Ctrl held during the wheel (event.modifiers in matplotlib 3.8+, else
    the Qt event's modifiers, else the last key pressed)."""
    mods = getattr(event, 'modifiers', None) or ()
    if 'ctrl' in mods or 'control' in mods:
        return True
    gui = getattr(event, 'guiEvent', None)
    try:
        from PyQt5.QtCore import Qt
        if gui is not None and gui.modifiers() & Qt.ControlModifier:
            return True
    except Exception:
        pass
    key = str(getattr(event, 'key', '') or '')
    return 'control' in key or 'ctrl' in key


def _group(shared, ax):
    """One key for all axes sharing this axis with `ax`."""
    try:
        return min(id(a) for a in shared.get_siblings(ax))
    except Exception:
        return id(ax)


def _handlers(canvas, signal):
    """The functions connected to `signal` of this canvas (alive ones)."""
    out = []
    for proxy in list(canvas.callbacks.callbacks.get(signal, {}).values()):
        try:
            func = proxy()
        except Exception:
            continue
        if func is not None:
            out.append(func)
    return out


def _is_foreign(func, nav):
    """A handler of the window itself (not matplotlib's own, not ours)."""
    owner = getattr(func, '__self__', None)
    if owner is nav:
        return False
    module = getattr(func, '__module__', '') or ''
    if owner is not None:
        module = type(owner).__module__ or ''
        try:
            from matplotlib.backend_bases import NavigationToolbar2
            from matplotlib.figure import Figure
            if isinstance(owner, (NavigationToolbar2, Figure)):
                return False
        except Exception:
            pass
        if module.startswith('matplotlib.widgets'):
            # a selector (SpanSelector, RectangleSelector ...) switched off
            # does not take the mouse
            active = getattr(owner, 'get_active', None)
            try:
                return bool(active()) if callable(active) else True
            except Exception:
                return True
    return not module.startswith('matplotlib.backend_bases')


class PlotNavigation:
    """The wheel zoom and dragging for one canvas (see the module)."""

    def __init__(self, canvas):
        self.canvas = canvas
        self._drag = None
        self._cids = [canvas.mpl_connect('scroll_event', self._on_scroll),
                      canvas.mpl_connect('button_press_event', self._on_press),
                      canvas.mpl_connect('motion_notify_event', self._on_move),
                      canvas.mpl_connect('button_release_event', self._on_release)]

    # ------------------------------------------------------------ checks
    def _main_plot(self):
        return bool(getattr(self.canvas, '_sax_main_plot', False))

    def _toolbar(self):
        return getattr(self.canvas, 'toolbar', None)

    def _toolbar_busy(self):
        tb = self._toolbar()
        return bool(tb is not None and str(getattr(tb, 'mode', '') or ''))

    def window_listens(self, signal):
        """The window has its own handler for `signal` on this canvas."""
        if signal == 'scroll_event':
            # a selector's scroll handler does nothing with the wheel
            funcs = [f for f in _handlers(self.canvas, signal)
                     if not (type(getattr(f, '__self__', None)).__module__ or '')
                     .startswith('matplotlib.widgets')]
        else:
            funcs = _handlers(self.canvas, signal)
        return any(_is_foreign(f, self) for f in funcs)

    def _on_draggable(self, event):
        """A press on a movable legend or label: that is dragged instead."""
        fig = self.canvas.figure
        artists = list(getattr(fig, 'legends', []))
        for ax in fig.axes:
            if ax.get_legend() is not None:
                artists.append(ax.get_legend())
            artists.extend(t for t in ax.texts if getattr(t, '_draggable', None) is not None)
        for a in artists:
            try:
                if a.get_visible() and a.contains(event)[0]:
                    return True
            except Exception:
                pass
        return False

    def _axes_at(self, event):
        """The axes under the mouse that can be zoomed and panned (twin axes
        included, as Pan of the toolbar does)."""
        out = []
        for ax in self.canvas.figure.get_axes():
            try:
                if (ax.in_axes(event) and ax.get_navigate() and ax.can_pan()
                        and ax.can_zoom() and not hasattr(ax, '_colorbar')
                        and ax.name == 'rectilinear'):
                    out.append(ax)
            except Exception:
                pass
        return out

    def _push(self):
        tb = self._toolbar()
        try:
            if tb is not None:
                tb.push_current()
        except Exception:
            pass

    def _push_home(self):
        """The view before the first wheel step / drag: Home goes there."""
        tb = self._toolbar()
        stack = getattr(tb, '_nav_stack', None)
        try:
            if tb is not None and stack is not None and stack() is None:
                tb.push_current()
        except Exception:
            pass

    # ------------------------------------------------------------ the wheel
    def _on_scroll(self, event):
        if self._main_plot() or self._toolbar_busy() or event.x is None:
            return
        if self.window_listens('scroll_event'):
            return
        axes = self._axes_at(event)
        if not axes:
            return
        steps = getattr(event, 'step', 0) or (1 if event.button == 'up' else -1)
        factor = WHEEL_IN ** float(np.clip(steps, -2, 2))
        self._push_home()
        y_axis = ctrl_held(event)
        done = set()                  # an axis shared by twin axes: zoomed once
        for ax in axes:
            xd, yd = ax.transData.inverted().transform((event.x, event.y))
            if y_axis:
                key = _group(ax.get_shared_y_axes(), ax)
                if key not in done:
                    ax.set_ylim(*zoomed(*ax.get_ylim(), yd, factor, ax.get_yscale() == 'log'))
                    done.add(key)
            else:
                key = _group(ax.get_shared_x_axes(), ax)
                if key not in done:
                    ax.set_xlim(*zoomed(*ax.get_xlim(), xd, factor, ax.get_xscale() == 'log'))
                    done.add(key)
        self._push()
        self.canvas.draw_idle()

    # ------------------------------------------------------------ dragging
    def _on_press(self, event):
        self._drag = None
        if (event.button != 1 or getattr(event, 'dblclick', False) or self._main_plot()
                or self._toolbar_busy() or event.x is None):
            return
        if self.window_listens('button_press_event') or self._on_draggable(event):
            return
        axes = self._axes_at(event)
        if axes:
            self._drag = {'x': event.x, 'y': event.y, 'axes': axes, 'moving': False}

    def _on_move(self, event):
        drag = self._drag
        if drag is None or event.x is None:
            return
        if not drag['moving']:
            if abs(event.x - drag['x']) <= DRAG_PX and abs(event.y - drag['y']) <= DRAG_PX:
                return
            if self._toolbar_busy():
                self._drag = None
                return
            self._push_home()
            for ax in drag['axes']:
                ax.start_pan(drag['x'], drag['y'], 1)
            drag['moving'] = True
            try:
                from PyQt5.QtCore import Qt
                self.canvas.setCursor(Qt.ClosedHandCursor)
            except Exception:
                pass
        for ax in drag['axes']:
            ax.drag_pan(1, None, event.x, event.y)
        self.canvas.draw_idle()

    def _on_release(self, event):
        drag, self._drag = self._drag, None
        if drag is None or not drag['moving']:
            return
        for ax in drag['axes']:
            try:
                ax.end_pan()
            except Exception:
                pass
        try:
            from PyQt5.QtCore import Qt
            self.canvas.setCursor(Qt.ArrowCursor)
        except Exception:
            pass
        self._push()
        self.canvas.draw_idle()


def attach(canvas):
    """The wheel zoom and dragging for `canvas` (once; the main plot: no)."""
    if canvas is None or getattr(canvas, _OWN, None) is not None:
        return getattr(canvas, _OWN, None) if canvas is not None else None
    nav = PlotNavigation(canvas)
    setattr(canvas, _OWN, nav)
    return nav
