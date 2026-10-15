# src/modules/visualization_analysis/group_values.py
"""The value per spectrum for Group Statistics. Qt-free.

Three families (VALUE_SECTIONS):

1. One band (one range; spectra may have different x-axes): the metrics of
   the 2D Map and Band Ratio -- Integral (area), Baseline-corrected
   integral, Mean, Variance, Peak intensity (maximum), Peak position, FWHM,
   the fitted peak values (the same fit as the peak-fit maps), and
   Intensity at x.
   Refinements: Intensity at x can be the interpolated point, the average
   over x +- w, or a 2nd-order polynomial fitted over x +- w (one noisy
   point no longer decides the value); Peak intensity / Peak position can
   be the highest point or the top of a parabola through the highest points
   of the band (noise spikes matter less, and the position lies between
   measured points).
2. Two bands A and B, each with its own metric, combined as A / B, A - B,
   A + B, A x B, (A - B) / (A + B) or log2(A / B).
3. Whole spectrum (only when all spectra share one x-axis; optionally within
   a range): PCA score, SVD coefficient, correlation with / RMS distance
   from the mean spectrum of a reference group (leave-one-out for the
   reference group's own spectra, so they are not compared with
   themselves).

Rules shared with the 2D Map and Band Ratio (band_integration.py): areas
from exactly the range edges, mean = area / width, and a spectrum that does
not completely cover a range gets no value (NaN).
"""

import math

import numpy as np

from src.modules.utils.band_integration import (
    band_area, band_mean, baseline_corrected_area, covers, covers_x, finite_sorted,
    integration_intervals)
from src.modules.utils.spectra_validation import axes_match

# --- the choices ----------------------------------------------------------------

FITTED = {
    'Fitted peak position': 'center',
    'Fitted FWHM': 'fwhm',
    'Fitted peak height': 'height',
    'Fitted peak area': 'area',
    'Fit quality (R²)': 'r2',
}

# key -> (text, metric) for the one-band values ('intensity_at_x': no metric)
ONE_BAND = {
    'intensity_at_x': ("Intensity at x", None),
    'area': ("Area (integral) over a range", 'Integral'),
    'bc_area': ("Baseline-corrected area", 'Baseline-corrected integral'),
    'mean': ("Mean over a range", 'Mean'),
    'max': ("Maximum (peak intensity) in a range", 'Peak intensity'),
    'peak_position': ("Peak position", 'Peak position'),
    'fwhm': ("FWHM (width of the band)", 'FWHM'),
    'variance': ("Variance in a range", 'Variance'),
    'fit_center': ("Fitted peak position", 'Fitted peak position'),
    'fit_fwhm': ("Fitted FWHM", 'Fitted FWHM'),
    'fit_height': ("Fitted peak height", 'Fitted peak height'),
    'fit_area': ("Fitted peak area", 'Fitted peak area'),
    'fit_r2': ("Fit quality (R²)", 'Fit quality (R²)'),
}
TWO_BANDS = {'ratio': "Two bands A and B (e.g. area A / area B)"}
WHOLE = {
    'pca': "PCA score",
    'svd': "SVD coefficient",
    'corr_ref': "Correlation with a reference group",
    'dist_ref': "Distance from a reference group",
}
VALUE_SECTIONS = (
    ("One band", [(k, v[0]) for k, v in ONE_BAND.items()]),
    ("Two bands", list(TWO_BANDS.items())),
    ("Whole spectrum (same x-axis needed)", list(WHOLE.items())),
)
VALUE_KINDS = {k: t for _, items in VALUE_SECTIONS for k, t in items}

# metrics a band of the two-band value can use (Intensity at x has no range)
BAND_METRICS = ('Integral', 'Baseline-corrected integral', 'Mean', 'Variance',
                'Peak intensity', 'Peak position', 'FWHM', 'Fitted peak position',
                'Fitted FWHM', 'Fitted peak height', 'Fitted peak area')
OPERATIONS = ('A / B', 'A − B', 'A + B', 'A × B', '(A − B) / (A + B)', 'log₂(A / B)')

X_MODES = {
    'point': "the interpolated point",
    'average': "average over x ± w",
    'fit': "polynomial fitted over x ± w",
}
MAX_MODES = {
    'point': "the highest point",
    'parabola': "top of a parabola through the highest points",
}

DEFAULT_SETTINGS = {
    'kind': 'intensity_at_x', 'x0': 0.0, 'x_mode': 'point', 'x_halfwidth': 5.0,
    'max_mode': 'point', 'range_a': (0.0, 1.0), 'range_b': (0.0, 1.0),
    'metric_a': 'Integral', 'metric_b': 'Integral', 'operation': 'A / B',
    'component': 1, 'reference_group': '', 'whole_use_range': False,
}


def is_whole_spectrum(kind):
    return kind in WHOLE


def uses_fit(settings):
    k = settings.get('kind')
    if k in ONE_BAND:
        return ONE_BAND[k][1] in FITTED
    if k in TWO_BANDS:
        return settings.get('metric_a') in FITTED or settings.get('metric_b') in FITTED
    return False


def uses_max_mode(settings):
    k = settings.get('kind')
    metrics = ([ONE_BAND[k][1]] if k in ONE_BAND else
               [settings.get('metric_a'), settings.get('metric_b')] if k in TWO_BANDS else [])
    return any(m in ('Peak intensity', 'Peak position') for m in metrics)


# --- one spectrum, one band -----------------------------------------------------------

def _window(x, y, rng):
    lo, hi = min(rng), max(rng)
    m = (x >= lo) & (x <= hi)
    return x[m], y[m]


def _smooth(y, n=5):
    if len(y) < n:
        return y
    k = np.ones(n) / n
    pad = n // 2
    yp = np.concatenate((np.full(pad, y[0]), y, np.full(pad, y[-1])))
    return np.convolve(yp, k, mode='valid')


def parabola_top(x, y):
    """(x, y) of the top of a band: a parabola fitted through the highest
    points around the maximum of a lightly smoothed copy (so a single noise
    spike does not decide where the top is). Falls back to the highest
    point when no sensible parabola exists."""
    if len(x) < 3:
        i = int(np.argmax(y)) if len(y) else 0
        return (float(x[i]), float(y[i])) if len(y) else (np.nan, np.nan)
    ys = _smooth(y)
    i = int(np.argmax(ys))
    lo_level = ys.min() + 0.7 * (ys[i] - ys.min())       # top 30 % of the band
    a = i
    while a > 0 and ys[a - 1] >= lo_level:
        a -= 1
    b = i
    while b < len(ys) - 1 and ys[b + 1] >= lo_level:
        b += 1
    while b - a + 1 < 5 and (a > 0 or b < len(ys) - 1):  # at least 5 points
        a, b = max(0, a - 1), min(len(ys) - 1, b + 1)
    xs, yy = x[a:b + 1], y[a:b + 1]
    if len(xs) >= 3:
        c2, c1, c0 = np.polyfit(xs - xs.mean(), yy, 2)
        if c2 < 0:
            xv = -c1 / (2 * c2)
            if xs.min() - xs.mean() <= xv <= xs.max() - xs.mean():
                return float(xv + xs.mean()), float(c0 - c1 * c1 / (4 * c2))
    j = int(np.argmax(y))
    return float(x[j]), float(y[j])


def fwhm(x, y):
    """Full width at half maximum of the dominant band (as in the 2D Map)."""
    from src.modules.visualization_analysis.map2d_manager import Map2DManager
    return float(Map2DManager._compute_fwhm(x, y))


def band_value(x, y, metric, rng, max_mode='point'):
    """One non-fitted metric of one spectrum (ascending x) over one range;
    NaN when the spectrum does not completely cover the range."""
    if rng is None or not covers(x, [rng]):
        return np.nan
    iv = integration_intervals(x, include=[rng])
    if metric == 'Integral':
        return band_area(x, y, iv)
    if metric == 'Baseline-corrected integral':
        return baseline_corrected_area(x, y, iv)
    if metric == 'Mean':
        return band_mean(x, y, iv)
    xw, yw = _window(x, y, rng)
    if len(yw) == 0:
        return np.nan
    if metric == 'Variance':
        return float(np.var(yw))
    if metric in ('Peak intensity', 'Peak position'):
        if max_mode == 'parabola':
            px, py = parabola_top(xw, yw)
        else:
            j = int(np.argmax(yw))
            px, py = float(xw[j]), float(yw[j])
        return py if metric == 'Peak intensity' else px
    if metric == 'FWHM':
        return fwhm(xw, yw)
    raise ValueError(f"unknown metric {metric!r}")


def intensity_at_x(x, y, x0, mode='point', halfwidth=0.0):
    """Intensity at x0: the interpolated point, the average over x0 +- w
    (area / width), or a 2nd-order polynomial fitted over x0 +- w and read
    at x0. NaN when x0 (or the window) is not inside the spectrum."""
    if x0 is None or len(x) == 0:
        return np.nan
    if mode == 'point' or halfwidth <= 0:
        if not covers_x(x, x0) or len(x) < 1:
            return np.nan
        return float(np.interp(x0, x, y))
    rng = (x0 - halfwidth, x0 + halfwidth)
    if not covers(x, [rng]):
        return np.nan
    if mode == 'average':
        return band_mean(x, y, integration_intervals(x, include=[rng]))
    xw, yw = _window(x, y, rng)
    if len(xw) < 3:
        return np.nan
    c = np.polyfit(xw - x0, yw, 2)
    return float(c[-1])


def fitted_values(xys, metric, rng, fit_settings=None, mapper=None, progress=None):
    """A fitted metric for every spectrum (the peak-fit maps' fit), NaN for
    spectra that do not cover the range or whose fit is rejected."""
    from src.modules.visualization_analysis.peak_fit_map import PeakFitMapper
    empty = (np.array([]), np.array([]))
    windows = [(_window(x, y, rng) if covers(x, [rng]) else empty) for x, y in xys]
    mapper = mapper or PeakFitMapper()
    return np.asarray(mapper.values(metric, windows, fit_settings, progress), dtype=float)


def band_values(xys, metric, rng, max_mode='point', fit_settings=None, mapper=None,
                progress=None):
    if metric in FITTED:
        return fitted_values(xys, metric, rng, fit_settings, mapper, progress)
    return np.array([band_value(x, y, metric, rng, max_mode) for x, y in xys], dtype=float)


def combine(a, b, operation):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        if operation == 'A / B':
            out = a / b
        elif operation == 'A − B':
            out = a - b
        elif operation == 'A + B':
            out = a + b
        elif operation == 'A × B':
            out = a * b
        elif operation == '(A − B) / (A + B)':
            out = (a - b) / (a + b)
        elif operation == 'log₂(A / B)':
            r = a / b
            out = np.where(r > 0, np.log2(np.where(r > 0, r, 1.0)), np.nan)
        else:
            raise ValueError(f"unknown operation {operation!r}")
    out[~np.isfinite(out)] = np.nan
    return out


# --- whole spectrum ---------------------------------------------------------------------

def same_x_axis(spectra):
    """True if all spectra share one x-axis (within the app's tolerance)."""
    xs = [finite_sorted(s['x_scale'], s['y_scale'])[0] for s in spectra]
    if not xs:
        return False
    return all(len(x) == len(xs[0]) and axes_match(xs[0], x) for x in xs[1:])


def _matrix(xys, rng=None):
    x0 = xys[0][0]
    mask = np.ones(len(x0), dtype=bool) if rng is None else (
        (x0 >= min(rng)) & (x0 <= max(rng)))
    return np.vstack([y[mask] for _, y in xys]), x0[mask]


def whole_spectrum_values(xys, groups, kind, component=1, reference_group='', rng=None):
    """(values, info) for the spectra that have a group (others NaN)."""
    n = len(xys)
    out = np.full(n, np.nan)
    info = {}
    use = [i for i, g in enumerate(groups) if g]
    if len(use) < 2:
        return out, info
    X, xr = _matrix([xys[i] for i in use], rng)
    if X.shape[1] < 2:
        info['note'] = "The range contains fewer than two points."
        return out, info
    if kind in ('pca', 'svd'):
        Z = X - X.mean(axis=0) if kind == 'pca' else X
        U, S, Vt = np.linalg.svd(Z, full_matrices=False)
        k = int(component) - 1
        if k >= len(S):
            info['note'] = f"Only {len(S)} components exist."
            return out, info
        sign = 1.0 if Vt[k][np.argmax(np.abs(Vt[k]))] >= 0 else -1.0   # fixed sign
        scores = sign * U[:, k] * S[k]
        total = float(np.sum(S ** 2))
        info['explained'] = 100.0 * float(S[k] ** 2) / total if total > 0 else np.nan
        out[use] = scores
        return out, info
    ref = [j for j, i in enumerate(use) if groups[i] == reference_group]
    if not ref:
        info['note'] = "Choose a reference group that has spectra."
        return out, info
    ref_sum = X[ref].sum(axis=0)
    for j, i in enumerate(use):
        if j in ref:                              # leave-one-out for the reference group
            if len(ref) < 2:
                continue
            m = (ref_sum - X[j]) / (len(ref) - 1)
        else:
            m = ref_sum / len(ref)
        if kind == 'corr_ref':
            a, b = X[j] - X[j].mean(), m - m.mean()
            den = math.sqrt(float(a @ a) * float(b @ b))
            out[i] = float(a @ b) / den if den > 0 else np.nan
        else:
            out[i] = float(np.sqrt(np.mean((X[j] - m) ** 2)))
    return out, info


# --- everything -------------------------------------------------------------------------

def compute_values(spectra, groups, settings, fit_settings=None, mapper=None, progress=None):
    """(values, info): one value per spectrum (NaN = no value) for the
    settings of the Value panel (see DEFAULT_SETTINGS)."""
    s = dict(DEFAULT_SETTINGS)
    s.update(settings or {})
    kind = s['kind']
    xys = [finite_sorted(sp['x_scale'], sp['y_scale']) for sp in spectra]
    info = {}
    if kind in WHOLE:
        if not same_x_axis([sp for sp, g in zip(spectra, groups) if g] or spectra):
            info['note'] = ("Whole-spectrum values need spectra with the same x-axis; "
                            "the selected spectra have different x-axes.")
            return np.full(len(spectra), np.nan), info
        return whole_spectrum_values(xys, groups, kind, s['component'], s['reference_group'],
                                     s['range_a'] if s['whole_use_range'] else None)
    if kind == 'intensity_at_x':
        return np.array([intensity_at_x(x, y, s['x0'], s['x_mode'], s['x_halfwidth'])
                         for x, y in xys], dtype=float), info
    if kind in ONE_BAND:
        return band_values(xys, ONE_BAND[kind][1], s['range_a'], s['max_mode'], fit_settings,
                           mapper, progress), info
    if kind in TWO_BANDS:
        a = band_values(xys, s['metric_a'], s['range_a'], s['max_mode'], fit_settings,
                        mapper, progress)
        b = band_values(xys, s['metric_b'], s['range_b'], s['max_mode'], fit_settings,
                        mapper, progress)
        return combine(a, b, s['operation']), info
    raise ValueError(f"unknown value kind {kind!r}")


def value_label(settings):
    """Short text for axis titles and exports, e.g. 'Area 950–1050'."""
    s = dict(DEFAULT_SETTINGS)
    s.update(settings or {})
    k = s['kind']
    ra = f"{min(s['range_a']):g}–{max(s['range_a']):g}"
    rb = f"{min(s['range_b']):g}–{max(s['range_b']):g}"
    if k == 'intensity_at_x':
        if s['x_mode'] == 'point' or s['x_halfwidth'] <= 0:
            return f"Intensity at {s['x0']:g}"
        how = 'average' if s['x_mode'] == 'average' else 'fit'
        return f"Intensity at {s['x0']:g} ({how} ± {s['x_halfwidth']:g})"
    if k in ONE_BAND:
        names = {'area': 'Area', 'bc_area': 'Baseline-corrected area', 'mean': 'Mean',
                 'max': 'Maximum', 'peak_position': 'Peak position', 'fwhm': 'FWHM',
                 'variance': 'Variance'}
        name = names.get(k, ONE_BAND[k][1])
        if k in ('max', 'peak_position') and s['max_mode'] == 'parabola':
            name += ' (parabola)'
        return f"{name} over {ra}"
    if k in TWO_BANDS:
        if (s['metric_a'], s['metric_b'], s['operation']) == ('Integral', 'Integral', 'A / B'):
            return f"Area {ra} / area {rb}"
        short = {'Integral': 'area', 'Baseline-corrected integral': 'bc. area'}
        a = f"{short.get(s['metric_a'], s['metric_a'].lower())} {ra}"
        b = f"{short.get(s['metric_b'], s['metric_b'].lower())} {rb}"
        op = s['operation']
        if op in ('A / B', 'A − B', 'A + B', 'A × B'):
            return f"{a} {op[2]} {b}"
        if op == 'log₂(A / B)':
            return f"log₂({a} / {b})"
        return f"{op}; A = {a}, B = {b}"
    where = f" ({ra})" if s['whole_use_range'] else ''
    if k in ('pca', 'svd'):
        return f"{'PC' if k == 'pca' else 'SVD component '}{s['component']} score{where}"
    what = 'Correlation with' if k == 'corr_ref' else 'RMS distance from'
    return f"{what} mean of “{s['reference_group']}”{where}"
