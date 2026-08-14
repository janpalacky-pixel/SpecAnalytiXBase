# src/modules/visualization/band_marker_manager.py
"""
Band Marker Manager — stores named reference lines that are drawn on
every plot simultaneously. A marker can be a vertical line at a constant
x (marking an x-value, e.g. a band position) or a horizontal line at a
constant y (marking a y-value, e.g. a threshold or baseline level).

Each marker has:
    position   : float — the coordinate value: an x-axis value if
                          axis == 'x' (vertical line), or a y-axis value
                          if axis == 'y' (horizontal line)
    axis       : str   — which axis the marker's line spans: 'x' (default;
                          a vertical line at x == position, drawn with
                          axvline — marks an x-value) or 'y' (a horizontal
                          line at y == position, drawn with axhline —
                          marks a y-value)
    label      : str   — display label, e.g. "Phe 1004"
    color      : str   — hex color, default '#E65100' (orange)
    linestyle  : str   — '-', '--', ':', '-.'
    linewidth  : float — default 1.0
    fontsize   : float — label text size in points, default 7.0
    label_offset: float — gap between the plot's edge and where THIS
                          marker's label starts, as a fraction of the
                          relevant axis's range (default 0.02, i.e. 2%).
                          For an 'x'-axis marker this is measured down
                          from the top of the plot (fraction of the
                          y-range); for a 'y'-axis marker it's measured in
                          from the right edge (fraction of the x-range).
                          Increase this if a label collides with a top
                          tick number or scientific-notation exponent.
                          Per-marker (not global) so different markers can
                          be offset by different amounts — e.g. to stack
                          labels at different heights when several sit
                          close together on the axis.
    orientation: str   — how the LABEL TEXT itself is drawn: 'vertical'
                          (default) or 'horizontal'. This is independent
                          of axis above (which controls the LINE's
                          direction) — any combination of axis and
                          orientation is valid. 'vertical' text reads
                          bottom-to-top and takes almost no space along
                          the line; 'horizontal' text reads left-to-right,
                          easier to read but takes more room and can run
                          into a neighbouring marker if two are close
                          together.
    visible    : bool  — per-marker show/hide toggle

Two settings apply to every marker at once (see __init__):
    visible       : bool  — global show/hide toggle for all markers together
    label_line_gap: float — gap, in points (screen units, so it stays the
                             same visual size regardless of zoom or either
                             axis's data scale), between the marker's line
                             and the start of its label, measured
                             perpendicular to the line (horizontal gap for
                             an 'x'-axis marker, vertical gap for a
                             'y'-axis marker). Default 3.0. Increase this
                             if a label's characters sit on top of / are
                             crossed by the line itself. (Unlike
                             label_offset above, this one IS shared by
                             every marker — it wasn't asked to be made
                             per-marker.)
"""

from matplotlib.transforms import offset_copy

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)


class BandMarkerManager:

    DEFAULT_COLORS = [
        '#E65100', '#1565C0', '#2E7D32', '#6A1B9A',
        '#00838F', '#AD1457', '#F9A825', '#4E342E',
    ]

    # Default gap between the plot's edge and where each marker's label
    # starts, as a fraction of the relevant axis's range. Configurable
    # (see label_offset below) because a fixed gap can collide with a tick
    # number or scientific-notation exponent, depending on scale.
    DEFAULT_LABEL_OFFSET = 0.02

    # Default gap, in points, between the marker's line and the start of
    # its label. Expressed in points (not data units) so it stays a
    # consistent, small visual gap regardless of either axis's scale or
    # current zoom level — a data-unit offset would need a different value
    # for every dataset and would stop working correctly after zooming.
    DEFAULT_LABEL_LINE_GAP = 3.0

    def __init__(self):
        self._markers = []   # list of dicts
        self.visible  = True # global toggle
        self.label_line_gap = self.DEFAULT_LABEL_LINE_GAP
        # Monotonically increasing — NOT the same as len(self._markers).
        # Cycling colors based on the current marker count meant removing
        # a marker and then adding a new one could silently reuse a color
        # already assigned to a marker that was never removed (e.g. remove
        # marker B from [A(color0), B(color1), C(color2)] -> [A, C]; the
        # next add() used len()==2 -> color index 2, duplicating C's own
        # color, instead of correctly continuing on to color index 3).
        self._next_color_index = 0

    # ------------------------------------------------------------------ #
    # CRUD                                                                 #
    # ------------------------------------------------------------------ #

    def add(self, position: float, label: str = '',
            color: str = None, linestyle: str = '--',
            linewidth: float = 1.0, orientation: str = 'vertical',
            axis: str = 'x', fontsize: float = 7.0,
            label_offset: float = None) -> int:
        """Add a marker. Returns its index."""
        if color is None:
            color = self.DEFAULT_COLORS[self._next_color_index % len(self.DEFAULT_COLORS)]
            self._next_color_index += 1
        self._markers.append({
            'position':     float(position),
            'axis':         axis if axis in ('x', 'y') else 'x',
            'label':        label or f'{position:.6g}',
            'color':        color,
            'linestyle':    linestyle,
            'linewidth':    linewidth,
            'fontsize':     fontsize,
            'label_offset': label_offset if label_offset is not None else self.DEFAULT_LABEL_OFFSET,
            'orientation':  orientation if orientation in ('vertical', 'horizontal') else 'vertical',
            'visible':      True,
        })
        logger.debug("BandMarkerManager: added %s marker '%s' at %.6g",
                     axis, label, position)
        return len(self._markers) - 1

    def remove(self, index: int):
        if 0 <= index < len(self._markers):
            self._markers.pop(index)

    def update(self, index: int, **kwargs):
        if 0 <= index < len(self._markers):
            self._markers[index].update(kwargs)

    def clear(self):
        self._markers.clear()

    @property
    def markers(self):
        return list(self._markers)

    def __len__(self):
        return len(self._markers)

    # ------------------------------------------------------------------ #
    # Drawing                                                              #
    # ------------------------------------------------------------------ #

    def apply_to_axes(self, axes):
        """
        Draw all visible markers on one or more matplotlib Axes objects.

        Parameters
        ----------
        axes : Axes or list of Axes
        """
        if not self.visible or not self._markers:
            return

        if not isinstance(axes, (list, tuple)):
            axes = [axes]

        for ax in axes:
            for m in self._markers:
                if not m.get('visible', True):
                    continue
                if m.get('axis', 'x') == 'y':
                    self._draw_horizontal_marker(ax, m)
                else:
                    self._draw_vertical_marker(ax, m)

    def _draw_vertical_marker(self, ax, m):
        """An 'x'-axis marker: a vertical line at x == position, marking
        an x-value. Label sits near the top of the axes, offset sideways
        (away from the line) by label_line_gap points."""
        pos = m.get('position', 0.0)
        ax.axvline(
            x         = pos,
            color     = m['color'],
            linestyle = m['linestyle'],
            linewidth = m['linewidth'],
            alpha     = 0.75,
            zorder    = 10,
        )
        ylim = ax.get_ylim()
        y_pos = ylim[1] - (ylim[1] - ylim[0]) * m.get('label_offset', self.DEFAULT_LABEL_OFFSET)
        rotation = 90 if m.get('orientation', 'vertical') == 'vertical' else 0
        text_transform = offset_copy(
            ax.transData, fig=ax.figure,
            x=self.label_line_gap, y=0, units='points')
        ax.text(
            pos, y_pos, m['label'],
            transform   = text_transform,
            fontsize    = m.get('fontsize', 7.0),
            color       = m['color'],
            va          = 'top',
            ha          = 'left',
            rotation    = rotation,
            clip_on     = True,
            zorder      = 11,
        )

    def _draw_horizontal_marker(self, ax, m):
        """A 'y'-axis marker: a horizontal line at y == position, marking
        a y-value (e.g. a threshold). Label sits near the right edge of
        the axes, offset upward (away from the line) by label_line_gap
        points — the same idea as the vertical-marker case, rotated 90°."""
        pos = m.get('position', 0.0)
        ax.axhline(
            y         = pos,
            color     = m['color'],
            linestyle = m['linestyle'],
            linewidth = m['linewidth'],
            alpha     = 0.75,
            zorder    = 10,
        )
        xlim = ax.get_xlim()
        x_pos = xlim[1] - (xlim[1] - xlim[0]) * m.get('label_offset', self.DEFAULT_LABEL_OFFSET)
        rotation = 90 if m.get('orientation', 'vertical') == 'vertical' else 0
        text_transform = offset_copy(
            ax.transData, fig=ax.figure,
            x=0, y=self.label_line_gap, units='points')
        ax.text(
            x_pos, pos, m['label'],
            transform   = text_transform,
            fontsize    = m.get('fontsize', 7.0),
            color       = m['color'],
            va          = 'bottom',
            ha          = 'right',
            rotation    = rotation,
            clip_on     = True,
            zorder      = 11,
        )

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        return {
            'visible':        self.visible,
            'label_line_gap': self.label_line_gap,
            'next_color_index': self._next_color_index,
            'markers':        list(self._markers),
        }

    def from_dict(self, d: dict):
        self.visible        = d.get('visible', True)
        self.label_line_gap = d.get('label_line_gap', self.DEFAULT_LABEL_LINE_GAP)
        self._markers = [self._normalize_marker(m) for m in d.get('markers', [])]
        # Falls back to len(markers) for sessions saved before this field
        # existed — not perfect (could still collide with a manually-set
        # marker color) but at least continues past however many markers
        # were already loaded, rather than resetting to 0 and immediately
        # risking a repeat of the collision this field exists to prevent.
        self._next_color_index = d.get('next_color_index', len(self._markers))

    @classmethod
    def _normalize_marker(cls, m: dict) -> dict:
        """Fill in any missing optional fields with their defaults, in case
        a marker dict is only partially populated. Assumes the current
        schema (position/axis/etc.) — no support for older, pre-refactor
        snapshot formats."""
        m = dict(m)
        m.setdefault('axis', 'x')
        m.setdefault('orientation', 'vertical')
        m.setdefault('linewidth', 1.0)
        m.setdefault('fontsize', 7.0)
        m.setdefault('label_offset', cls.DEFAULT_LABEL_OFFSET)
        m.setdefault('visible', True)
        return m
