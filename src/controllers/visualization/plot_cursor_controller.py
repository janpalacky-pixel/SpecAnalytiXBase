# src/controllers/visualization/plot_cursor_controller.py
"""The vertical cursor of the main plot ('Cursor' checkbox above the plot).

* While it is on, a dashed vertical line follows the mouse; a dot marks
  where it crosses each drawn spectrum and a box lists x and the value of
  every spectrum there (at most cursor_values.MAX_LISTED, those nearest the
  mouse pointer's height, when more are drawn). Values are interpolated
  between measured points; a spectrum has none outside its x-range.
* A left click pins a cursor at that x (several can be pinned: a "multi-
  cursor"); right-click on the plot -> 'Copy cursor values' puts a table
  (one row per spectrum, one column per pinned cursor) on the clipboard for
  Excel, 'Clear pinned cursors' removes them. Pinned cursors stay when the
  plot is drawn again (e.g. another selection) until cleared.
* Waterfall: the curves are shifted, so no values are listed (only x);
  Heatmap: x only.

The moving parts are drawn with blitting (only the line, dots and box are
redrawn on a mouse move, not the spectra), so it stays smooth with
thousands of drawn lines. The mouse position itself (x, y) is also shown
by the toolbar under the plot.
"""
import numpy as np

from src.modules.visualization.view_text import add_row_text

DRAG_PX = 3        # moved further with the button held: the plot dragged, no cursor pinned

from src.modules.visualization import cursor_values as cv

CURSOR_GID = 'sax_cursor'          # artists of this controller (not spectra)


def _label(x):
    """A pinned cursor's label: its x without needless decimals (1004, 12.35)."""
    from src.modules.visualization.plot_notes import fmt
    return fmt(x)
_NO_VALUES_TYPES = ('Waterfall plot', 'Heatmap')


class PlotCursorController:

    def __init__(self, main_controller):
        self.main = main_controller
        self.enabled = False
        self.pinned = []               # x positions of the pinned cursors
        self._press = None             # a press: pinned on the release unless dragged
        self.canvas = None
        self.plot_type = ''
        self._cids = []
        self._background = None
        self._live = {}                # axes -> (vline, dots, box)
        self._live_ax = None

    # ------------------------------------------------------------ wiring
    def set_enabled(self, on):
        self.enabled = bool(on)
        if not self.enabled:
            self._hide_live()

    def attach(self, canvas, plot_type=''):
        """Called after every plot (the canvas is new each time)."""
        self.detach()
        self.canvas = canvas
        self.plot_type = plot_type or ''
        if canvas is None:
            return
        self._cids = [
            canvas.mpl_connect('motion_notify_event', self._on_move),
            canvas.mpl_connect('button_press_event', self._on_click),
            canvas.mpl_connect('button_release_event', self._on_release),
            canvas.mpl_connect('draw_event', self._on_draw),
            canvas.mpl_connect('axes_leave_event', lambda e: self._hide_live()),
            canvas.mpl_connect('figure_leave_event', lambda e: self._hide_live()),
        ]
        if self.pinned:
            self._draw_pinned()

    def detach(self):
        if self.canvas is not None:
            for cid in self._cids:
                try:
                    self.canvas.mpl_disconnect(cid)
                except Exception:
                    pass
        self._cids = []
        self._background = None
        self._live = {}
        self._live_ax = None
        self.canvas = None

    # ------------------------------------------------------------ data
    @staticmethod
    def _curves(ax):
        """(label, x, y) of the spectra drawn in ax (not markers, bands or
        this controller's own lines)."""
        out = []
        for ln in ax.get_lines():
            if ln.get_gid() == CURSOR_GID or not ln.get_visible():
                continue
            x = np.asarray(ln.get_xdata(), dtype=float)
            if len(x) <= 2:
                continue
            label = ln.get_label()
            if label.startswith('_'):
                label = '(unnamed line)'
            out.append((label, x, np.asarray(ln.get_ydata(), dtype=float)))
        return out

    def all_curves(self):
        """(label, x, y) of every drawn spectrum, each label once."""
        if self.canvas is None:
            return []
        seen, out = set(), []
        for ax in self.canvas.figure.axes:
            for c in self._curves(ax):
                if c[0] not in seen:
                    seen.add(c[0])
                    out.append(c)
        return out

    def shows_values(self):
        return self.plot_type not in _NO_VALUES_TYPES

    def readout_text(self, ax, x, pointer_y=None):
        """The text of the box next to the cursor."""
        lines = [f"x = {cv.fmt(x)}"]
        if not self.shows_values():
            if self.plot_type == 'Waterfall plot':
                lines.append("(values not listed: the curves are shifted)")
            return "\n".join(lines), []
        vals = cv.values_at(self._curves(ax), x)
        shown, hidden = cv.listed(vals, pointer_y)
        for label, v in shown:
            name = label if len(label) <= 32 else '…' + label[-31:]
            lines.append(f"{name}: {cv.fmt(v)}")
        if hidden:
            lines.append(f"+ {hidden} more (nearest to the pointer listed)")
        return "\n".join(lines), shown

    # ------------------------------------------------------------ live cursor
    def _artists_for(self, ax):
        if ax not in self._live:
            vline = ax.axvline(np.nan, color='#455A64', lw=0.9, ls='--', animated=True,
                               gid=CURSOR_GID)
            dots, = ax.plot([], [], 'o', ms=5, mfc='white', mec='#263238', mew=1.2,
                            animated=True, gid=CURSOR_GID, zorder=20)
            # the box sits at the top, beside the cursor line (moves with it)
            box = ax.annotate('', xy=(np.nan, 0.98), xycoords=('data', 'axes fraction'),
                              xytext=(8, 0), textcoords='offset points', va='top',
                              ha='left', multialignment='left', fontsize=7.5,
                              family='monospace', animated=True, gid=CURSOR_GID, zorder=21,
                              annotation_clip=False,
                              bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='#90A4AE',
                                        alpha=0.92))
            self._live[ax] = (vline, dots, box)
        return self._live[ax]

    def _on_draw(self, event):
        try:
            self._background = self.canvas.copy_from_bbox(self.canvas.figure.bbox)
        except Exception:
            self._background = None

    def _toolbar_busy(self):
        tb = getattr(self.main, 'static_toolbar', None)
        return bool(tb is not None and str(getattr(tb, 'mode', '')))

    def _on_move(self, event):
        notes = getattr(self.main, 'plot_notes_controller', None)
        if notes is not None and notes.dragging():
            return                             # a label is dragged: the cursor waits
        if getattr(event, 'button', None) is not None:
            self._hide_live()                  # the plot is dragged: the cursor waits
            return
        if not self.enabled or self.canvas is None or event.inaxes is None \
                or event.xdata is None or self._toolbar_busy():
            return
        ax = event.inaxes
        if self._background is None:
            self.canvas.draw()                 # sets the background (_on_draw)
            if self._background is None:
                return
        vline, dots, box = self._artists_for(ax)
        x = float(event.xdata)
        text, shown = self.readout_text(ax, x, event.ydata)
        for a in (vline, dots, box):
            a.set_visible(True)
        vline.set_xdata([x, x])
        if shown:
            dots.set_data([x] * len(shown), [v for _, v in shown])
        else:
            dots.set_data([], [])
        box.set_text(text)
        # the box on the side of the line with more room
        box.xy = (x, 0.98)
        left = event.x > (ax.bbox.x0 + ax.bbox.x1) / 2
        box.set_position((-8, 0) if left else (8, 0))
        box.set_ha('right' if left else 'left')
        self.canvas.restore_region(self._background)
        for a in (vline, dots, box):
            ax.draw_artist(a)
        self.canvas.blit(self.canvas.figure.bbox)
        self._live_ax = ax

    def _hide_live(self):
        # hidden also for a saved or copied picture (savefig draws them too)
        for artists in self._live.values():
            for a in artists:
                a.set_visible(False)
        if self.canvas is None or self._background is None or self._live_ax is None:
            return
        try:
            self.canvas.restore_region(self._background)
            self.canvas.blit(self.canvas.figure.bbox)
        except Exception:
            pass
        self._live_ax = None

    # ------------------------------------------------------------ pinned cursors
    def _on_click(self, event):
        """A press: a cursor is pinned on the release, if the mouse did not
        move meanwhile - held and moved, the plot is dragged instead
        (plot_mouse_controller) and no cursor is pinned."""
        self._press = None
        if (not self.enabled or event.button != 1 or event.inaxes is None
                or event.xdata is None or self._toolbar_busy() or event.dblclick):
            return
        notes = getattr(self.main, 'plot_notes_controller', None)
        if notes is not None and notes.hit(event):
            return                             # a label is dragged, no cursor pinned
        self._press = (event.x, event.y, float(event.xdata))

    def _on_release(self, event):
        press, self._press = getattr(self, '_press', None), None
        if press is None or event.button != 1 or not self.enabled:
            return
        x, y, xdata = press
        if event.x is None or abs(event.x - x) > DRAG_PX or abs(event.y - y) > DRAG_PX:
            return                             # the plot was dragged
        self.pin(xdata)

    def pin(self, x):
        self.pinned.append(float(x))
        self._draw_pinned()

    def clear_pinned(self):
        self.pinned = []
        self._draw_pinned()

    def _draw_pinned(self):
        if self.canvas is None:
            return
        for ax in self.canvas.figure.axes:
            for a in list(ax.lines) + list(ax.texts):
                if a.get_gid() in (CURSOR_GID, CURSOR_GID + '_pinned'):
                    a.remove()                 # the live cursor is made again
            for x in self.pinned:                    # labelled with its x value
                ax.axvline(x, color='#6D4C41', lw=1.0, ls=':', gid=CURSOR_GID + '_pinned')
                # its number only while x is in the view (zoomed away: not
                # floating beside the plot), one line higher where it would
                # overlap the number of a cursor next to it - view_text.py
                add_row_text(ax, x, _label(x), va='bottom', ha='center', fontsize=7.5,
                             color='#6D4C41', gid=CURSOR_GID + '_pinned')
        self._live = {}
        self.canvas.draw_idle()

    def copy_table(self):
        """The pinned cursors' values as a tab-separated table on the
        clipboard. Returns the number of spectra (0 = nothing copied)."""
        curves = self.all_curves()
        if not curves or not self.pinned:
            return 0
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(cv.table_text(curves, self.pinned))
        return len(curves)
