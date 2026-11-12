# src/modules/visualization/view_text.py
"""Numbers that mark a point of the data - a peak's position (Detect Peaks),
a pinned cursor's x - are drawn only while that point is in the plot's view.
Zoomed or panned away from it (the mouse wheel, Zoom, Pan, Axis properties)
the number is not left floating outside the axes, over the axis numbers or
beside the plot, and does not make the plot smaller (the layout leaves room
only for what is drawn). Zoomed back: there again.

A matplotlib ax.text is not clipped and always takes part in the layout,
hence this Text that checks its point at every draw. It pickles as any Text
(Save plot for publication works on a pickled copy, where a changed axis
range is checked the same way)."""

import numpy as np
from matplotlib.text import Text
from matplotlib.transforms import Bbox

TOL_PX = 0.5          # a point exactly on the axes' edge is in the view


def point_in_view(ax, x, y=None, transform=None):
    """Is the data point (x, y) - or, y None, the x position - within the
    axes' view? Checked in screen pixels, so reversed and log axes work.
    transform: the point's own (e.g. a scaled line's - scale_each.py),
    otherwise the axes' data."""
    try:
        if y is None:
            px, py = ax.get_xaxis_transform().transform((x, 0.5))
        else:
            px, py = (transform or ax.transData).transform((x, y))
    except Exception:
        return True
    if not (np.isfinite(px) and np.isfinite(py)):
        return False
    box = ax.bbox
    return (box.x0 - TOL_PX <= px <= box.x1 + TOL_PX
            and box.y0 - TOL_PX <= py <= box.y1 + TOL_PX)


class ViewText(Text):
    """A Text drawn only while its point is in the view (see the module)."""

    only_x = False            # True: only x is data (e.g. above the axes)

    def in_view(self):
        ax = self.axes
        if ax is None:
            return True
        x, y = self.get_position()
        return point_in_view(ax, x, None if self.only_x else y, self.get_transform())

    def draw(self, renderer):
        if not self.in_view():
            return
        return super().draw(renderer)

    def get_window_extent(self, renderer=None, dpi=None):
        if not self.in_view():
            return Bbox.unit()                 # as matplotlib's Annotation
        return super().get_window_extent(renderer, dpi)

    def get_tightbbox(self, renderer=None):
        if not self.in_view():
            return Bbox.null()                 # no room made for it
        return super().get_tightbbox(renderer)


def add_view_text(ax, x, y, s, only_x=False, **kwargs):
    """Like ax.text(x, y, s, **kwargs), as a ViewText (not clipped at the
    axes, as ax.text: a number at the top may stand above them)."""
    kwargs.setdefault('clip_on', False)
    text = ViewText(x, y, s, **kwargs)
    text.only_x = only_x
    if text.get_clip_path() is None:
        text.set_clip_path(ax.patch)
    ax._add_text(text)
    return text


class RowText(ViewText):
    """The numbers of the pinned cursors, in one row above the plot: one
    that would overlap a number to its left goes one line higher (e.g.
    cursors at 722 and 726 on a plot from 400 to 1000). Worked out again
    at every draw - zoomed in until they are apart, they are in one row
    again. Its y is in axes fractions (1 = the top of the axes)."""

    only_x = True
    base_y = 1.0
    GAP_PX = 3

    def _row(self):
        ax = self.axes
        if ax is None:
            return []
        return [t for t in ax.texts if isinstance(t, RowText)
                and t.get_gid() == self.get_gid() and t.get_visible() and t.in_view()]

    def restack(self, renderer=None):
        ax = self.axes
        if ax is None:
            return
        if renderer is None:
            try:
                renderer = self.figure._get_renderer()
            except Exception:
                return
        boxes = []
        for t in self._row():
            try:
                b = Text.get_window_extent(t, renderer)
            except Exception:
                continue
            boxes.append((b.x0, b.x1, b.height, t))
        boxes.sort(key=lambda b: b[0])
        right_ends = []                       # per line: where its last number ends
        for x0, x1, height, t in boxes:
            line = 0
            while line < len(right_ends) and right_ends[line] > x0 - self.GAP_PX:
                line += 1
            if line == len(right_ends):
                right_ends.append(x1)
            else:
                right_ends[line] = x1
            y = t.base_y + line * height / max(ax.bbox.height, 1.0)
            x, old = t.get_position()
            if abs(old - y) > 1e-9:            # only a real change (no endless redraw)
                t.set_position((x, y))

    def draw(self, renderer):
        if self.in_view():
            self.restack(renderer)
        return super().draw(renderer)

    def get_tightbbox(self, renderer=None):
        if self.in_view():
            self.restack(renderer)             # the layout makes room for the lines
        return super().get_tightbbox(renderer)


def add_row_text(ax, x, s, **kwargs):
    """A pinned cursor's number above the axes at x (RowText)."""
    kwargs.setdefault('clip_on', False)
    text = RowText(x, RowText.base_y, s, transform=ax.get_xaxis_transform(), **kwargs)
    if text.get_clip_path() is None:
        text.set_clip_path(ax.patch)
    ax._add_text(text)
    return text
