# src/modules/visualization_analysis/peak_fit_map.py
"""Peak-fit maps: fit one band, in every pixel of a hyperspectral map, with
a peak model plus a simple baseline, and map the fitted position, width
(FWHM), height, area and fit quality (R²).

Why: the 2D Map's quick metrics ("Peak position" = x of the highest point,
"FWHM" = half-maximum crossings) are fast but coarse -- the position can
only take the measured x values, and noise or a sloping background shifts
both. A least-squares fit uses every point of the band, gives positions
between data points (a band shift of a fraction of a data point across a
cell becomes visible) and separates the band from the background.

Used through the 2D Map's Metric list ("Fitted peak position", ...);
Map2DManager calls PeakFitMapper. Qt-free; the per-spectrum work can run
in several processes (src/modules/utils/parallel_utils.py), like the
Automated Baseline.

Model, all with the full width at half maximum (FWHM) as width parameter:
    y(x) = height * shape((x - center) / FWHM) + baseline(x)
    shape:    Gaussian | Lorentzian | Pseudo-Voigt (eta = Lorentzian fraction)
    baseline: none | constant | linear
"""

import math
import time

import numpy as np
from scipy.optimize import curve_fit

from src.modules.utils.app_logger import get_logger
from src.modules.utils.parallel_utils import (
    chunk_count, count_item, describe_worker_limits, requested_workers, resolve_worker_count,
    run_in_process_pool)
from src.modules.utils.progress_utils import OperationCancelled

logger = get_logger(__name__)

SHAPES = ('Gaussian', 'Lorentzian', 'Pseudo-Voigt')
BASELINES = ('None', 'Constant', 'Linear')
PROCESSING_MODES = ('auto', 'serial', 'parallel')

# Metric names in the 2D Map's Metric list -> result key.
FITTED_METRICS = {
    'Fitted peak position': 'center',
    'Fitted FWHM': 'fwhm',
    'Fitted peak height': 'height',
    'Fitted peak area': 'area',
    'Fit quality (R²)': 'r2',
}
RESULT_KEYS = ('center', 'fwhm', 'height', 'area', 'r2', 'eta')

DEFAULT_SETTINGS = {
    'shape': 'Gaussian',
    'baseline': 'Linear',
    'min_r2': 0.0,              # pixels with a worse fit are left blank (0 = show all)
    'processing_mode': 'auto',
    'max_workers': 0,           # 0 = the maximum (all CPU cores)
    'min_band_points': 0,       # narrower fitted bands are spikes, not bands (0 = off)
}

# Choices for 'min_band_points' offered in the settings dialog.
MIN_BAND_POINTS_CHOICES = (0, 2, 3, 4)

_SQRT_LN2 = math.sqrt(math.log(2.0))
_GAUSS_AREA = math.sqrt(math.pi) / (2.0 * _SQRT_LN2)    # area = factor * height * FWHM
_LORENTZ_AREA = math.pi / 2.0

_AUTO_MIN_SERIAL_SECONDS = 6.0
_POOL_STARTUP_SECONDS = 4.0
_AUTO_CALIBRATION_SPECTRA = 5
_PROGRESS_MIN_INTERVAL = 0.05


def normalized_settings(settings=None):
    s = dict(DEFAULT_SETTINGS)
    s.update({k: v for k, v in (settings or {}).items() if k in DEFAULT_SETTINGS})
    if s['shape'] not in SHAPES:
        s['shape'] = DEFAULT_SETTINGS['shape']
    if s['baseline'] not in BASELINES:
        s['baseline'] = DEFAULT_SETTINGS['baseline']
    if s['processing_mode'] not in PROCESSING_MODES:
        s['processing_mode'] = 'auto'
    try:
        s['min_r2'] = float(min(max(float(s['min_r2']), 0.0), 1.0))
    except (TypeError, ValueError):
        s['min_r2'] = 0.0
    try:
        s['min_band_points'] = float(min(max(float(s['min_band_points']), 0.0), 20.0))
    except (TypeError, ValueError):
        s['min_band_points'] = float(DEFAULT_SETTINGS['min_band_points'])
    return s


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------

def _gauss(u):
    return np.exp(-4.0 * math.log(2.0) * u * u)


def _lorentz(u):
    return 1.0 / (1.0 + 4.0 * u * u)


def peak_shape(x, center, fwhm, shape, eta=0.5):
    u = (np.asarray(x, dtype=float) - center) / fwhm
    if shape == 'Gaussian':
        return _gauss(u)
    if shape == 'Lorentzian':
        return _lorentz(u)
    return eta * _lorentz(u) + (1.0 - eta) * _gauss(u)


def peak_area(height, fwhm, shape, eta=0.5):
    if shape == 'Gaussian':
        factor = _GAUSS_AREA
    elif shape == 'Lorentzian':
        factor = _LORENTZ_AREA
    else:
        factor = eta * _LORENTZ_AREA + (1.0 - eta) * _GAUSS_AREA
    return factor * height * fwhm


def _make_model(shape, baseline, x_ref):
    """f(x, *params) for curve_fit. Parameter order:
    height, center, fwhm, [eta], [b0], [b1]."""
    has_eta = shape == 'Pseudo-Voigt'
    n_base = {'None': 0, 'Constant': 1, 'Linear': 2}[baseline]

    def model(x, *p):
        height, center, fwhm = p[0], p[1], p[2]
        k = 3
        eta = 0.5
        if has_eta:
            eta = p[k]
            k += 1
        y = height * peak_shape(x, center, fwhm, shape, eta)
        if n_base >= 1:
            y = y + p[k]
        if n_base == 2:
            y = y + p[k + 1] * (x - x_ref)
        return y
    return model, has_eta, n_base


def _nan_result():
    return {key: np.nan for key in RESULT_KEYS} | {'ok': False, 'params': None}


def fit_single_peak(x, y, shape='Gaussian', baseline='Linear',
                    min_band_points=DEFAULT_SETTINGS['min_band_points']):
    """Fit one peak (+ baseline) to the points (x, y).

    Returns a dict: center, fwhm, height, area, r2, eta (NaN when not
    Pseudo-Voigt), ok (bool), params (the fitted parameter vector, for
    drawing the curve with model_curve), and 'reason' when not ok.
    A fit is rejected (ok False, values NaN) when it does not converge,
    when its centre ends at the edge of the window (the band maximum is
    then outside the window), or when the fitted band is wider than the
    window (then it is not a band in the window but noise or background), or
    narrower than *min_band_points* data-point spacings (then it is a single
    spike -- noise or a cosmic ray -- not a band; 0 switches this off) --
    in those cases the numbers would be meaningless.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    model, has_eta, n_base = _make_model(shape, baseline, 0.0)
    n_params = 3 + int(has_eta) + n_base
    result = _nan_result()
    if len(x) < n_params + 2:
        result['reason'] = 'too few points'
        return result
    order = np.argsort(x)
    x, y = x[order], y[order]
    span = x[-1] - x[0]
    if span <= 0:
        result['reason'] = 'no x range'
        return result
    x_ref = 0.5 * (x[0] + x[-1])
    model, has_eta, n_base = _make_model(shape, baseline, x_ref)
    dx = span / (len(x) - 1)

    # Starting values: a straight line through the ends as background, the
    # largest deviation from it as the peak (positive, or negative -- a CD
    # band may point down), its width from the half-height points.
    n_end = max(1, min(3, len(x) // 6))
    y_left, y_right = float(np.mean(y[:n_end])), float(np.mean(y[-n_end:]))
    slope0 = (y_right - y_left) / span if n_base == 2 else 0.0
    base0 = 0.5 * (y_left + y_right) if n_base >= 1 else 0.0
    background = base0 + slope0 * (x - x_ref)
    net = y - background
    i_peak = int(np.argmax(net)) if net.max() >= -net.min() else int(np.argmin(net))
    height0 = float(net[i_peak])
    if height0 == 0:
        result['reason'] = 'flat signal'
        return result
    above = np.abs(net) >= 0.5 * abs(height0)
    width0 = float(np.clip(above.sum() * dx, 2 * dx, span))

    lower = [-np.inf, x[0], 0.5 * dx]
    upper = [np.inf, x[-1], 2.0 * span]
    if has_eta:
        lower.append(0.0)
        upper.append(1.0)
    if n_base >= 1:
        lower.append(-np.inf)
        upper.append(np.inf)
    if n_base == 2:
        lower.append(-np.inf)
        upper.append(np.inf)

    def start(height, center, width, b0, b1):
        p0 = [height, float(np.clip(center, x[0], x[-1])),
              float(np.clip(width, lower[2], upper[2]))]
        if has_eta:
            p0.append(0.5)
        if n_base >= 1:
            p0.append(b0)
        if n_base == 2:
            p0.append(b1)
        return p0

    def fit_from(p0):
        """(params, residual sum of squares), or None if no convergence."""
        try:
            params, _ = curve_fit(model, x, y, p0=p0, bounds=(lower, upper), maxfev=4000)
        except Exception:                     # no convergence, singular, ...
            return None
        return params, float(np.sum((y - model(x, *params)) ** 2))

    def is_spike(params):
        return bool(min_band_points) and float(params[2]) < min_band_points * dx

    def verdict(params):
        """None if the fit describes a band in the window, else the reason."""
        center, fwhm = float(params[1]), float(params[2])
        edge = 0.5 * dx
        if center <= x[0] + edge or center >= x[-1] - edge:
            return 'centre at the window edge'
        if is_spike(params):
            # Narrower than a few data points: a single spike (noise, a
            # cosmic ray), not a band -- its position, width and area
            # would be meaningless.
            return (f'narrower than {min_band_points:g} data points '
                    f'(a spike, not a band)')
        if fwhm > span:
            # A "band" wider than the whole window is not a band in the
            # window: typically noise or the background itself fitted as a
            # broad hump, with a meaningless (often huge) area.
            return 'band wider than the window'
        return None

    try:
        params, _ = curve_fit(model, x, y, p0=start(height0, x[i_peak], width0, base0, slope0),
                              bounds=(lower, upper), maxfev=4000)
        first_error = None
        fits = [(params, float(np.sum((y - model(x, *params)) ** 2)))]
        reason = verdict(params)
    except Exception as exc:                  # no convergence, singular, ...
        first_error = type(exc).__name__
        fits, reason = [], first_error
    best = fits[0] if fits else None

    if reason is not None:
        # The fit searches downhill from its starting values and can stop in
        # a worse solution than the best one, e.g. when the starting peak is
        # a single noise point (seen on a weak band in a noisy Raman map:
        # a downward "band" at the window edge on a steep background,
        # although an ordinary band on a gentle background fits better).
        # So a rejected or failed fit is repeated from two other starts: the
        # highest and lowest point of a smoothed copy of the data. The fit
        # with the smallest residual -- the best one, whichever start it
        # came from -- is then judged by the same rules. A fit that was
        # accepted at once is not changed.
        #
        # Spikes are the one exception to "best fit wins": with the spike
        # rule on, a fit on a single spike (a cosmic ray, a noise point) is
        # an artefact, not a band, so it must not win just because hitting
        # one very high point lowers the residual most. A weak broad band
        # with a cosmic ray on top would otherwise always end up blank.
        # Spike fits are therefore set aside and the best of the remaining
        # fits is judged -- by all rules, so it can still be rejected (e.g.
        # wider than the window). Only if every fit is a spike is the pixel
        # rejected as a spike.
        fits += _fits_from_smoothed_starts(x, y, span, dx, start, fit_from)
        if not fits:
            result['reason'] = first_error
            return result
        fits.sort(key=lambda f: f[1])
        not_spikes = [f for f in fits if not is_spike(f[0])]
        best = not_spikes[0] if not_spikes else fits[0]
        reason = verdict(best[0])

    params, ss_res = best
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    if reason is not None:
        result.update(r2=r2, params=params, x_ref=x_ref, reason=reason)
        return result
    height, center, fwhm = float(params[0]), float(params[1]), float(params[2])
    eta = float(params[3]) if has_eta else np.nan
    result.update(center=center, fwhm=fwhm, height=height,
                  area=float(peak_area(height, fwhm, shape, eta if has_eta else 0.5)),
                  r2=float(r2), eta=eta, ok=True, params=params, x_ref=x_ref)
    return result


def _fits_from_smoothed_starts(x, y, span, dx, start, fit_from):
    """Fits (params, residual) from two more starting guesses taken from a
    smoothed copy of the window -- its highest and its lowest point. Smoothing (a moving
    average over about a tenth of the points) removes the single noise
    points that misled the first guess. Measured on a 21 000-pixel Raman
    map: these two starts rescue as many rejected pixels as twelve
    (adding a grid of 5 positions x 2 widths gained nothing) at a seventh
    of the time."""
    n = len(x)
    window = max(3, (n // 10) | 1)                 # odd, about a tenth of the points
    kernel = np.ones(window) / window
    padded = np.concatenate([np.full(window // 2, y[0]), y, np.full(window // 2, y[-1])])
    smooth = np.convolve(padded, kernel, mode='valid')
    n_end = max(1, min(window, n // 6))
    s_left, s_right = float(np.mean(smooth[:n_end])), float(np.mean(smooth[-n_end:]))
    b1 = (s_right - s_left) / span
    x_ref = 0.5 * (x[0] + x[-1])
    b0 = 0.5 * (s_left + s_right)
    net = smooth - (b0 + b1 * (x - x_ref))
    scale = float(np.std(y)) or 1.0

    starts = []
    for i in (int(np.argmax(net)), int(np.argmin(net))):
        h = float(net[i]) or scale
        width = max(2 * dx, float(np.sum(np.abs(net) >= 0.5 * abs(h))) * dx)
        starts.append(start(h, x[i], width, b0, b1))

    return [found for found in (fit_from(p0) for p0 in starts) if found is not None]


def model_curve(x, result, shape, baseline):
    """(fitted curve, baseline) at x for a result of fit_single_peak, or
    (None, None) if there is nothing to draw."""
    if result is None or result.get('params') is None:
        return None, None
    model, has_eta, n_base = _make_model(shape, baseline, result.get('x_ref', 0.0))
    x = np.asarray(x, dtype=float)
    p = result['params']
    curve = model(x, *p)
    k = 3 + int(has_eta)
    base = np.zeros_like(x)
    if n_base >= 1:
        base = base + p[k]
    if n_base == 2:
        base = base + p[k + 1] * (x - result.get('x_ref', 0.0))
    return curve, base


# ---------------------------------------------------------------------------
# Many spectra
# ---------------------------------------------------------------------------

def _fit_chunk_worker(payload):
    """Worker-process entry point (top level so it can be pickled)."""
    shape, baseline, pairs = payload[:3]
    min_band_points = payload[3] if len(payload) > 3 else DEFAULT_SETTINGS['min_band_points']
    out = []
    for x, y in pairs:
        r = fit_single_peak(x, y, shape, baseline, min_band_points)
        out.append([r[k] for k in RESULT_KEYS] + [bool(r['ok'])])
        count_item()                          # smooth progress (see parallel_utils)
    return out


class PeakFitMapper:
    """Fits every spectrum of a map and keeps the result, so switching
    between position / FWHM / height / area / R² maps does not refit."""

    _CACHE_SIZE = 4     # e.g. Band A and Band B of a ratio map, two settings

    def __init__(self):
        self._caches = {}          # key -> results, most recent last
        self._last_results = None
        self.last_run_info = None
        self._progress_fn = None

    def clear(self):
        self.__init__()

    # -- public
    def results(self, windows, settings=None, progress=None, status_callback=None):
        """Fit results for *windows* -- a list of (x, y) arrays, one per
        pixel, already cut to the fitting window. Returns a dict of numpy
        arrays (RESULT_KEYS plus 'ok'). Cached for identical input.

        progress(done, total) is called regularly; it may raise
        OperationCancelled to stop (nothing is cached then)."""
        s = normalized_settings(settings)
        key = self._key(windows, s)
        if key in self._caches:
            out = self._caches.pop(key)
            self._caches[key] = out
            self._last_results = out
            return out
        rows = self._fit_all(windows, s, progress, status_callback)
        out = {k: np.array([r[i] for r in rows], dtype=float) for i, k in enumerate(RESULT_KEYS)}
        out['ok'] = np.array([bool(r[-1]) for r in rows], dtype=bool)
        self._caches[key] = out
        while len(self._caches) > self._CACHE_SIZE:
            self._caches.pop(next(iter(self._caches)))
        self._last_results = out
        return out

    def values(self, metric, windows, settings=None, progress=None, status_callback=None):
        """Per-pixel values of one FITTED_METRICS entry; failed fits, and
        fits below settings['min_r2'], are NaN (blank pixels)."""
        s = normalized_settings(settings)
        res = self.results(windows, s, progress, status_callback)
        vals = res[FITTED_METRICS[metric]].copy()
        bad = ~res['ok']
        if s['min_r2'] > 0:
            bad |= ~(res['r2'] >= s['min_r2'])
        vals[bad] = np.nan
        return vals

    def summary(self):
        """One sentence for the user: how many pixels were fitted, how."""
        info = self.last_run_info
        if not info or self._last_results is None:
            return ''
        n = info['n']
        ok = int(np.sum(self._last_results['ok']))
        how = (f"parallel, {info['workers']} workers" if info['mode'] == 'parallel' else 'serial')
        took = info['seconds']
        text = f"Fitted {ok} of {n} pixels in {took:.1f} s ({how})."
        if ok < n:
            text += f" {n - ok} have no value (fit rejected; hatched grey in the map)."
        if info.get('note'):
            text += f" Ran serially: {info['note']}."
        if info.get('fallback_reason'):
            text += f" Parallel processing failed and was redone serially ({info['fallback_reason']})."
        return text

    # -- internals
    @staticmethod
    def _key(windows, s):
        h = []
        for x, y in windows:
            h.append((len(x), float(np.sum(x)) if len(x) else 0.0,
                      float(np.sum(y)) if len(y) else 0.0,
                      float(np.sum(y * y)) if len(y) else 0.0))
        return (tuple(h), s['shape'], s['baseline'], s['min_band_points'])

    def _report(self, done, total, force=False):
        if self._progress_fn is None:
            return
        now = time.perf_counter()
        if not force and now - self._last_report < _PROGRESS_MIN_INTERVAL:
            return
        self._last_report = now
        self._progress_fn(done, total)

    def _fit_all(self, windows, s, progress, status_callback):
        n = len(windows)
        started = time.perf_counter()
        self._progress_fn = progress
        self._last_report = 0.0
        rows = [None] * n
        mode = s['processing_mode']
        info = {'n': n, 'mode': 'serial', 'workers': 1, 'seconds': 0.0,
                'note': None, 'fallback_reason': None}
        workers = (resolve_worker_count(requested_workers(s['max_workers']))
                   if mode != 'serial' else 1)
        if mode != 'serial' and (workers < 2 or n < 2):
            info['note'] = (f'only one worker is available ({describe_worker_limits()})'
                            if workers < 2 else 'there is only one spectrum')
            mode = 'serial'
        remaining = list(range(n))
        done = [0]

        def serial(indices):
            for i in indices:
                x, y = windows[i]
                r = fit_single_peak(x, y, s['shape'], s['baseline'], s['min_band_points'])
                rows[i] = [r[k] for k in RESULT_KEYS] + [bool(r['ok'])]
                done[0] += 1
                self._report(done[0], n)

        if mode == 'auto':
            calib = remaining[:_AUTO_CALIBRATION_SPECTRA]
            t0 = time.perf_counter()
            serial(calib)
            per = (time.perf_counter() - t0) / max(1, len(calib))
            remaining = remaining[len(calib):]
            serial_est = per * len(remaining)
            if (serial_est >= _AUTO_MIN_SERIAL_SECONDS
                    and _POOL_STARTUP_SECONDS + serial_est / workers <= 0.7 * serial_est):
                mode = 'parallel'
            else:
                info['note'] = (f'the job is short (about {serial_est:.1f} s for the rest), '
                                f'so parallel workers would not pay off')
                mode = 'serial'

        if mode == 'parallel' and remaining:
            n_chunks = chunk_count(len(remaining), workers)
            chunks = [list(c) for c in np.array_split(np.array(remaining), n_chunks)]
            payloads = [(s['shape'], s['baseline'],
                         [(np.asarray(windows[i][0]), np.asarray(windows[i][1])) for i in c],
                         s['min_band_points'])
                        for c in chunks]

            running = [False]
            before = done[0]                  # pixels already fitted (auto's first few)
            by_chunks, by_items = [0], [0]

            def update_done():
                # Spectra counted inside the chunks (smooth), or whole
                # finished chunks -- whichever is further.
                done[0] = before + max(by_chunks[0], by_items[0])

            def items_done(count):
                by_items[0] = count
                update_done()

            def chunk_done(k):
                by_chunks[0] += len(chunks[k])
                update_done()
                if not running[0]:
                    # The workers are up: replace "Starting parallel workers…".
                    running[0] = True
                    if status_callback is not None:
                        status_callback(f"Fitting in {workers} parallel workers\u2026")

            try:
                if status_callback is not None:
                    status_callback("Starting parallel workers…")
                results = run_in_process_pool(
                    _fit_chunk_worker, payloads, workers,
                    lambda: self._report(done[0], n, force=True), chunk_done,
                    on_items_done=items_done)
                for c, chunk_rows in zip(chunks, results):
                    for i, row in zip(c, chunk_rows):
                        rows[i] = row
                info['mode'], info['workers'] = 'parallel', workers
                remaining = []
            except OperationCancelled:
                raise
            except Exception as exc:
                logger.warning("Parallel peak fitting failed (%r); redoing it serially.", exc)
                info['fallback_reason'] = f'{type(exc).__name__}: {exc}'
                done[0] = n - len(remaining)
        if remaining:
            serial(remaining)
        info['seconds'] = time.perf_counter() - started
        self.last_run_info = info
        self._report(n, n, force=True)
        return rows
