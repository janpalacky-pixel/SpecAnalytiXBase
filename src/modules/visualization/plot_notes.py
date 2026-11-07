# src/modules/visualization/plot_notes.py
"""Your own labels on the main plot (Qt-free): a band's label above its
peak (e.g. "1004"), any text, or an arrow pointing at a place (with an
optional text at its tail). Everything is kept in the plot's own units
(data coordinates): a label stays on its band when the plot is zoomed or the
window made larger, and it is at the same place in Save plot for
publication. Saved in snapshots; drawn with gid 'sax_note:<n>'.

A note: x, y - the point (a band's top, an arrow's tip, a text's place);
tx, ty - where the text is (an arrow's tail; a dragged band label), or None:
at the point (a band label: just above it)."""

import copy as _copy

KINDS = (('band', "band label"), ('text', "text"), ('arrow', "arrow"))
GID = 'sax_note'
DEFAULT = {'kind': 'text', 'text': '', 'x': 0.0, 'y': 0.0, 'tx': None, 'ty': None,
           'fontsize': 8.0, 'color': '#000000', 'rotation': 0.0, 'bold': False,
           'head': 'tip'}
# an arrow's head: at its tip (pointing at the place), at its text, at both ends, none
HEADS = (('tip', "at the tip →"), ('text', "at the text ←"), ('both', "both ends ↔"),
         ('none', "none —"))
_STYLE = {'tip': '->', 'text': '<-', 'both': '<->', 'none': '-'}
BAND_GAP_PT = 4.0            # a band label: this far above the band's top
ARROW_PT = (-30.0, 30.0)     # a new arrow's tail: from its tip (points)


def fmt(x):
    """A band's position as a label: 1004, 12.35 (no needless decimals)."""
    x = float(x)
    if abs(x) >= 100:
        return f"{x:.0f}"
    return f"{x:.4g}"


def peak_top(curves, x, x_range=None, part=0.01):
    """The highest value of the spectra near x (within `part` of the x range)
    - where a band's label goes. curves: [(label, x values, y values)].
    None when no spectrum reaches x."""
    import numpy as np
    best = None
    for _label, xs, ys in curves:
        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        if xs.size == 0:
            continue
        span = (x_range[1] - x_range[0]) if x_range else (np.nanmax(xs) - np.nanmin(xs))
        near = np.abs(xs - x) <= abs(span) * part
        if not near.any():
            continue
        top = np.nanmax(ys[near])
        if np.isfinite(top) and (best is None or top > best):
            best = float(top)
    return best


def offset_in_data(ax, x, y, dx_pt, dy_pt):
    """The point dx_pt, dy_pt points away from (x, y) on `ax`, in data units."""
    dpi = ax.figure.dpi
    px, py = ax.transData.transform((x, y))
    return tuple(float(v) for v in ax.transData.inverted().transform(
        (px + dx_pt * dpi / 72.0, py + dy_pt * dpi / 72.0)))


class PlotNotes:
    """The list of labels; plain dicts (DEFAULT keys)."""

    def __init__(self):
        self.notes = []

    def __len__(self):
        return len(self.notes)

    def add(self, kind, x, y, text='', ax=None, **more):
        """A new label at (x, y); an arrow's tail is put up and to the left
        of it (`ax` needed to place it)."""
        note = dict(DEFAULT)
        note.update(kind=kind if kind in dict(KINDS) else 'text', x=float(x), y=float(y),
                    text=text if text or kind != 'band' else fmt(x))
        if note['kind'] == 'arrow':
            if ax is not None:
                note['tx'], note['ty'] = offset_in_data(ax, x, y, *ARROW_PT)
            else:
                note['tx'], note['ty'] = float(x), float(y)
        note.update({k: v for k, v in more.items() if k in DEFAULT})
        self.notes.append(note)
        return len(self.notes) - 1

    def update(self, i, **values):
        if 0 <= i < len(self.notes):
            self.notes[i].update({k: v for k, v in values.items() if k in DEFAULT})

    def remove(self, i):
        if 0 <= i < len(self.notes):
            self.notes.pop(i)

    def clear(self):
        self.notes = []

    def to_dict(self):
        return {'notes': _copy.deepcopy(self.notes)}

    def from_dict(self, data):
        notes = (data or {}).get('notes', []) if isinstance(data, dict) else []
        self.notes = []
        for n in notes:
            if isinstance(n, dict):
                note = dict(DEFAULT)
                note.update({k: v for k, v in n.items() if k in DEFAULT})
                if note['kind'] == 'arrow' and note['tx'] is None:
                    note['tx'], note['ty'] = note['x'], note['y']
                self.notes.append(note)

    # ---------------------------------------------------------------- drawing
    @staticmethod
    def text_place(n):
        """(x, y) data of the text, or None (a band label above its point)."""
        if n['tx'] is not None and n['ty'] is not None:
            return float(n['tx']), float(n['ty'])
        if n['kind'] == 'band':
            return None
        return float(n['x']), float(n['y'])

    def draw(self, ax, selected=None):
        """Draw the labels on `ax`; returns the annotations (in order). The
        label number `selected` gets a dashed frame (an arrow: blue)."""
        out = []
        for i, n in enumerate(self.notes):
            kind = n['kind']
            place = self.text_place(n)
            kw = dict(xy=(n['x'], n['y']), xycoords='data', fontsize=n['fontsize'],
                      color=n['color'], rotation=n['rotation'],
                      fontweight='bold' if n['bold'] else 'normal', gid=f"{GID}:{i}",
                      zorder=12, annotation_clip=False)
            if place is None:                          # a band label: just above its top
                kw.update(xytext=(0, BAND_GAP_PT), textcoords='offset points',
                          ha='center', va='bottom')
            else:
                kw.update(xytext=place, textcoords='data', ha='center',
                          va='bottom' if kind == 'band' else 'center')
            if kind == 'arrow':
                # Size makes the whole arrow thicker (line and head), not only its head
                kw['arrowprops'] = dict(arrowstyle=_STYLE.get(n.get('head'), '->'),
                                        color=n['color'],
                                        lw=max(0.5, 0.9 * float(n['fontsize']) / 8.0),
                                        shrinkA=2, shrinkB=1)
            if i == selected:
                if n['text']:
                    kw['bbox'] = dict(boxstyle='round,pad=0.25', fc='none', ec='#1976D2',
                                      ls='--', lw=0.9)
                if kind == 'arrow':
                    kw['arrowprops'] = dict(kw['arrowprops'], color='#1976D2')
                    # the two ends as small squares: drag them to turn and stretch it
                    tail = place if place is not None else (n['x'], n['y'])
                    ax.plot([n['x'], tail[0]], [n['y'], tail[1]], linestyle='None',
                            marker='s', markersize=6, markerfacecolor='white',
                            markeredgecolor='#1976D2', gid=f"{GID}_handles", zorder=13,
                            label='_handles')
            out.append(ax.annotate(n['text'], **kw))
        return out

    # ---------------------------------------------------------------- moving
    def move(self, i, part, ax, before, dpx, dpy):
        """Note i dragged by (dpx, dpy) pixels (y up) on `ax`, from its state
        `before`: part 'text' / 'tail' - the text (an arrow turns), 'tip' -
        only an arrow's tip, 'shaft' - the whole arrow; a text label: its
        place. All in data units, so it stays right at any size."""
        if not 0 <= i < len(self.notes):
            return
        to_px = ax.transData.transform
        to_data = ax.transData.inverted().transform
        n = self.notes[i]

        def shifted(x, y):
            px, py = to_px((x, y))
            return tuple(float(v) for v in to_data((px + dpx, py + dpy)))
        if part in ('text', 'tail'):
            place = self.text_place(before)
            if place is None:                          # a band label: above its top
                px, py = to_px((before['x'], before['y']))
                gap = BAND_GAP_PT * ax.figure.dpi / 72.0
                place = tuple(float(v) for v in to_data((px, py + gap)))
            if n['kind'] == 'text':
                n['x'], n['y'] = shifted(*place)
                n['tx'] = n['ty'] = None
            else:
                n['tx'], n['ty'] = shifted(*place)
        elif part == 'tip':
            n['x'], n['y'] = shifted(before['x'], before['y'])
        elif part == 'shaft':
            n['x'], n['y'] = shifted(before['x'], before['y'])
            if before['tx'] is not None:
                n['tx'], n['ty'] = shifted(before['tx'], before['ty'])
