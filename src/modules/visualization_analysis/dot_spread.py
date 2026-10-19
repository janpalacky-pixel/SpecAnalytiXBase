# src/modules/visualization_analysis/dot_spread.py
"""Where to draw the dots of a group sideways (Group Statistics plots).

The sideways position of a dot has no meaning -- the value is its height.
It only keeps dots with similar values from covering each other. Three
common ways, all deterministic here (the same data always give the same
picture, whatever the order or number of the other groups):

* jitter()  -- a "random" shift that is fixed per spectrum (computed from
  its name, not drawn from a random sequence), as ggplot2's geom_jitter /
  seaborn's stripplot but reproducible;
* swarm()   -- a beeswarm (GraphPad Prism's scatter dot plot, seaborn's
  swarmplot, R ggbeeswarm): a dot goes on the centre line, and only if it
  would overlap a dot already placed is it moved just enough to the side.
  No dot covers another; the width shows where the values crowd. Gets
  very wide for hundreds of dots;
* density() -- a density-scaled, non-random spread ("quasirandom" in R
  ggbeeswarm): offsets from the van der Corput sequence, scaled by how
  crowded the values are at that height (a kernel density estimate).
  Works for any number of dots.

automatic() uses the beeswarm when it fits into the given half width and
the density-scaled spread otherwise. The beeswarm is laid out for a fixed
reference plot size (reference_dot_size), so the picture does not depend on
the window's size.

All offsets are in x data units (the groups sit at x = 1, 2, 3, ...).
Qt-free.
"""

import hashlib

import numpy as np

MODES = ('auto', 'jitter', 'swarm', 'density')
MODE_NAMES = {
    'auto': "Automatic",
    'jitter': "Random jitter",
    'swarm': "Beeswarm",
    'density': "Density-scaled",
}
SWARM_MAX_POINTS = 600       # automatic(): above this the swarm is not tried


def stable_unit(keys):
    """One fixed number in [-1, 1) per key (e.g. a spectrum name): looks
    random, but the same key always gives the same number."""
    out = np.empty(len(keys))
    for i, k in enumerate(keys):
        h = hashlib.md5(str(k).encode('utf-8')).digest()
        out[i] = int.from_bytes(h[:8], 'big') / 2.0 ** 63 - 1.0
    return out


def jitter(values, keys, half_width):
    """Fixed 'random' offsets in [-half_width, half_width), one per key."""
    if len(values) == 0:
        return np.zeros(0)
    return stable_unit(keys) * half_width


def swarm(values, dx, dy):
    """Beeswarm offsets. dx, dy: a dot's diameter (plus a small gap) in x
    and y data units. The dots are placed from the lowest value up; each
    goes to the position nearest the centre line where it touches no dot
    already placed (left before right when both are equally near)."""
    v = np.asarray(values, dtype=float)
    n = len(v)
    off = np.zeros(n)
    if n == 0 or not (dx > 0 and dy > 0):
        return off
    order = np.argsort(v, kind='stable')
    ys = v[order] / dy                       # in dot diameters
    xs = np.zeros(n)
    start = 0                                # first placed dot within 1 diameter below
    for j in range(n):
        y = ys[j]
        while start < j and y - ys[start] >= 1.0:
            start += 1
        px, py = xs[start:j], ys[start:j]
        if len(px) == 0:
            xs[j] = 0.0
            continue
        h = np.sqrt(np.clip(1.0 - (py - y) ** 2, 0.0, None))
        cands = np.concatenate(([0.0], px - h, px + h))
        cands = cands[np.lexsort((cands, np.round(np.abs(cands), 9)))]
        dist2 = (cands[:, None] - px[None, :]) ** 2 + (py[None, :] - y) ** 2
        ok = np.all(dist2 >= 1.0 - 1e-9, axis=1)
        xs[j] = cands[np.argmax(ok)] if ok.any() else cands[-1]
    off[order] = xs * dx
    return off


def _van_der_corput(n):
    out = np.empty(n)
    for i in range(n):
        k, f, x = i + 1, 0.5, 0.0
        while k:
            x += f * (k & 1)
            k >>= 1
            f /= 2.0
        out[i] = x
    return out


def density(values, half_width):
    """Density-scaled, non-random offsets within [-half_width, half_width]:
    wide where many values lie close together, narrow where they are few."""
    v = np.asarray(values, dtype=float)
    n = len(v)
    if n == 0:
        return np.zeros(0)
    dens = np.ones(n)
    if n >= 3 and np.ptp(v) > 0:
        try:
            from scipy.stats import gaussian_kde
            dens = gaussian_kde(v)(v)
            dens = dens / dens.max()
        except Exception:
            dens = np.ones(n)
    order = np.argsort(v, kind='stable')
    u = 2.0 * _van_der_corput(n) - 1.0       # 0, -0.5, 0.5, -0.75, 0.25, ...
    off = np.zeros(n)
    off[order] = u * half_width * dens[order]
    return off


def automatic(values, dx, dy, half_width):
    """(offsets, 'swarm' or 'density'): the beeswarm when it fits into
    half_width, otherwise the density-scaled spread."""
    if len(values) <= SWARM_MAX_POINTS:
        s = swarm(values, dx, dy)
        if len(s) == 0 or np.max(np.abs(s)) <= half_width:
            return s, 'swarm'
    return density(values, half_width), 'density'


def offsets(mode, values, keys, dx, dy, half_width):
    """(offsets, mode actually used) for one group."""
    if mode == 'jitter':
        return jitter(values, keys, half_width), 'jitter'
    if mode == 'swarm':
        return swarm(values, dx, dy), 'swarm'
    if mode == 'density':
        return density(values, half_width), 'density'
    return automatic(values, dx, dy, half_width)


# The beeswarm is laid out for a plot of this size (inches per group along x,
# height of the plotting area), not for the window's actual size: so the
# picture is the same in a small or a maximized window, in a saved file and
# in the help's screenshots. In a much smaller window neighbouring dots may
# touch a little; in a larger one they get a little more room.
REFERENCE_INCHES_PER_GROUP = 3.0
REFERENCE_PLOT_HEIGHT = 5.0


def reference_dot_size(ylim, marker_area_pt2, gap=1.15):
    """(dx, dy): the diameter of a scatter dot of area marker_area_pt2
    (matplotlib's s, in points^2), times gap, in x data units (one group =
    1) and y data units, for the reference plot size above."""
    d_in = np.sqrt(marker_area_pt2) / 72.0 * gap
    span = abs(float(ylim[1]) - float(ylim[0]))
    return d_in / REFERENCE_INCHES_PER_GROUP, d_in * span / REFERENCE_PLOT_HEIGHT
