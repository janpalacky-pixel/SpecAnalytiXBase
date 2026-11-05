# src/modules/data_analysis/peak_fitting_series.py
"""Peak Fitting for a series (Qt-free): the peaks set up in the Peak Fitting
window on one spectrum are fitted to every selected spectrum in turn, each
fit starting from the result of the one before - so a band that shifts or
grows slowly along a series (a temperature scan, a titration, a time
series) is followed from spectrum to spectrum. The result is a table with
one row per spectrum: position, FWHM, height and area of every peak and
R² of the fit. The window is
src/views/dialogs/data_analysis/peak_fitting_dialog.py (tab Series results, the
spectrum chooser and the views above the plot)."""

import numpy as np

from src.modules.data_analysis.peak_fitting_manager import PeakFittingManager
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)


# the parameter the dialog calls 'width' and the model's extra parameter, in
# the result of PeakFittingManager.get_peak_properties
WIDTH_KEY = {'Gaussian': 'sigma', 'Lorentzian': 'gamma', 'Voigt': 'sigma', 'Pseudo-Voigt': 'fwhm'}
EXTRA_KEY = {'Voigt': 'gamma', 'Pseudo-Voigt': 'eta'}
VALUES = [('position', 'center'), ('FWHM', 'fwhm'), ('height', 'height'), ('area', 'area')]


def start_from(fitted, previous_start):
    """The starting peaks (the Peak Fitting window's peak dicts: model,
    center, amplitude, width, extra, colour) for the next spectrum: the
    fitted values of this one."""
    out = []
    for fit, before in zip(fitted, previous_start):
        model, par = fit['model'], fit['parameters']
        peak = dict(before)
        peak.update(model=model, center=float(par['center']), amplitude=float(par['height']),
                    width=abs(float(par[WIDTH_KEY[model]])))
        if model in EXTRA_KEY:
            peak['extra'] = float(par[EXTRA_KEY[model]])
        out.append(peak)
    return out


def _xy(spectrum):
    x = np.asarray(spectrum.get('x_scale', []), dtype=float)
    y = np.asarray(spectrum.get('y_scale', []), dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    return x[good], y[good]


def fit_one(x, y, start, amplitude_constraint='unrestricted', manager=None,
            background='none', bic=True):
    """(fitted peaks or None, R², fitted background or None) of one spectrum
    from the starting peaks; the background ('auto', 'none', 'constant',
    'linear') is fitted together with the peaks (PeakFittingManager.fit_peaks;
    'auto' chooses for this spectrum from its data)."""
    manager = manager or PeakFittingManager()
    if not start or len(x) <= 4 * len(start):
        return None, np.nan, None
    fitted, y_fit = manager.fit_peaks(x, y, start, amplitude_constraint, background=background)
    if fitted is None:
        return None, np.nan, None
    ss_res = float(np.sum((y - y_fit) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    bg = plain_background(manager.last_background)
    if bic:
        manager.add_peak_bic(x, y, fitted, start, amplitude_constraint, background)
    return (fitted, (1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan), bg)


def plain_background(background):
    """The fitted background with plain Python numbers (or None)."""
    if not background:
        return None
    return {k: (round(float(v), 10) if isinstance(v, (int, float, np.floating)) else v)
            for k, v in background.items()}


def _fit_chunk_worker(payload):
    """Worker-process entry point (top level so it can be pickled):
    (start peaks, constraint, [(x, y), ...][, background]) ->
    [(fitted or None, r2, background or None), ...]."""
    from src.modules.utils.parallel_utils import count_item
    start, constraint, pairs = payload[:3]
    background = payload[3] if len(payload) > 3 else 'none'
    manager = PeakFittingManager()
    out = []
    for item in pairs:                    # (x, y[, its own starting peaks[, its constraint]])
        x, y = item[0], item[1]
        own = item[2] if len(item) > 2 and item[2] is not None else start
        own_constraint = item[3] if len(item) > 3 and item[3] else constraint
        fitted, r2, bg = fit_one(np.asarray(x), np.asarray(y), own, own_constraint, manager,
                                 background)
        if fitted is not None:            # plain floats: picklable, no numpy scalars
            fitted = [_plain_peak(f, digits=None) for f in fitted]
        out.append((fitted, float(r2), bg))
        count_item()
    return out


def fit_series_independent(spectra, start_peaks, amplitude_constraint='unrestricted',
                           progress=None, parallel=None, starts=None, constraints=None,
                           background='none'):
    """Every spectrum fitted from the same starting peaks (those of the shown
    spectrum's fit) - or, with `starts` (one list per spectrum), each from its
    own peaks - independently of the others, so on several processor cores
    (the program's Parallel processing setting; 'serial' there, few spectra
    or a failed pool: one after another). Returns the same as fit_series.
    progress(done, total) may raise OperationCancelled."""
    from src.modules.utils import parallel_utils as pu
    from src.modules.utils.progress_utils import OperationCancelled
    start = [dict(p) for p in (start_peaks or [])]
    own = [[dict(p) for p in st] for st in starts] if starts is not None else None
    cons = list(constraints) if constraints is not None else None
    pairs = []
    for i, s in enumerate(spectra):
        item = _xy(s)
        if own is not None or cons is not None:
            item = item + (own[i] if own is not None else None,
                           cons[i] if cons is not None else None)
        pairs.append(item)
    n = len(pairs)
    rows = [None] * n
    settings = pu.default_parallel_settings() if parallel is None else parallel
    workers = (pu.resolve_worker_count(pu.requested_workers(settings.get('max_workers')))
               if settings.get('processing_mode') != 'serial' else 1)
    done = [0]

    def report():
        if progress is not None:
            progress(min(done[0], n), n)
    if workers >= 2 and n >= 4:
        chunks = [list(c) for c in np.array_split(np.arange(n), pu.chunk_count(n, workers))]
        payloads = [(start, amplitude_constraint, [pairs[i] for i in c], background)
                    for c in chunks]

        def items_done(count):
            done[0] = count
        try:
            results = pu.run_in_process_pool(_fit_chunk_worker, payloads, workers, report,
                                             on_items_done=items_done)
            for c, part in zip(chunks, results):
                for i, row in zip(c, part):
                    rows[i] = row
        except OperationCancelled:
            raise
        except Exception as exc:
            logger.warning("Parallel series fit failed (%r); fitting one after another.", exc)
    manager = PeakFittingManager()
    for i in range(n):
        if rows[i] is None:
            rows[i] = fit_one(pairs[i][0], pairs[i][1], own[i] if own is not None else start,
                              cons[i] if cons is not None else amplitude_constraint, manager,
                              background)
            done[0] = i + 1
            report()
    return [{'label': str(s.get('label', '')), 'ok': fitted is not None, 'peaks': fitted,
             'r2': r2, 'background': bg} for s, (fitted, r2, bg) in zip(spectra, rows)]


def fit_series(spectra, initial_peaks, amplitude_constraint='unrestricted', progress=None,
               manager=None, background='none'):
    """Fit the peaks to each spectrum in turn (in the order given), each
    starting from the previous successful fit (the first from
    initial_peaks). Returns one dict per spectrum: label, ok, peaks (the
    fitted peaks as PeakFittingManager.fit_peaks gives them, or None), r2.
    A spectrum whose fit fails is left without values; the next one starts
    from the last successful fit. progress(done, total) may raise to stop."""
    manager = manager or PeakFittingManager()
    start = [dict(p) for p in initial_peaks]
    results = []
    for k, s in enumerate(spectra):
        x, y = _xy(s)
        fitted, r2, bg = fit_one(x, y, start, amplitude_constraint, manager, background)
        results.append({'label': str(s.get('label', '')), 'ok': fitted is not None,
                        'peaks': fitted, 'r2': r2, 'background': bg})
        if fitted is not None:
            start = start_from(fitted, start)
        if progress is not None:
            progress(k + 1, len(spectra))
    return results


def fit_each(spectra, starts, amplitude_constraint='unrestricted', progress=None,
             manager=None, constraints=None, background='none'):
    """Fit the spectra in turn (in the order given): each from its own
    starting peaks (starts[i]), or - where starts[i] is None - from the
    result of the last successful fit before it (follows shifting bands).
    Returns (results as fit_series, the starting peaks used for each)."""
    manager = manager or PeakFittingManager()
    previous = None
    results, used = [], []
    for k, (s, own) in enumerate(zip(spectra, starts)):
        start = [dict(p) for p in own] if own else previous
        x, y = _xy(s)
        if start:
            fitted, r2, bg = fit_one(x, y, start, constraints[k] if constraints else
                                     amplitude_constraint, manager, background)
        else:
            fitted, r2, bg = None, np.nan, None
        results.append({'label': str(s.get('label', '')), 'ok': fitted is not None,
                        'peaks': fitted, 'r2': r2, 'background': bg})
        used.append(start)
        if fitted is not None:
            previous = start_from(fitted, start)
        if progress is not None:
            progress(k + 1, len(spectra))
    return results, used


def series_table(results, n_peaks, sigmas=1):
    """(columns, rows) of the series: one row per spectrum - its name, then
    position, FWHM, height and area of peak 1, 2, ..., each followed by its
    uncertainty (±, `sigmas` x the standard error), then R². A failed fit
    gives None (an empty cell)."""
    columns = ['Spectrum'] + [f'Peak {j + 1} {name}{p}' for j in range(n_peaks)
                              for name, _ in VALUES for p in ('', pm(sigmas))] + ['R²']
    rows = []
    for r in results:
        row = [r['label']]
        for j in range(n_peaks):
            peak = r['peaks'][j] if r['ok'] and j < len(r['peaks']) else None
            for _, key in VALUES:
                row += ([float(peak['parameters'][key]), error_of(peak, key, sigmas)]
                        if peak is not None else [None, None])
        r2 = r.get('r2')
        row.append(float(r2) if r['ok'] and r2 is not None and np.isfinite(r2) else None)
        rows.append(row)
    return columns, rows


# The values of one fitted peak, named as in the Peaks table of the window
# (Width and Extra mean what the model uses: Gaussian/Voigt sigma, Lorentzian
# gamma, Pseudo-Voigt FWHM; Voigt gamma, Pseudo-Voigt eta), each followed by
# its standard error (±, from the fit).
# The uncertainty is the standard error (1 sigma) - or, chosen in the window
# ("± shown as"), 2 or 3 sigma: then the columns say so ("Center ±2σ").
SIGMAS = ((1, "1 \u03c3 (68 %)"), (2, "2 \u03c3 (95 %)"), (3, "3 \u03c3 (99.7 %)"))


def pm(sigmas=1):
    """The end of an uncertainty column's name: ' ±' (1 sigma), ' ±2σ', ..."""
    return ' \u00b1' if sigmas == 1 else f' \u00b1{sigmas:g}\u03c3'


def peak_columns(sigmas=1):
    """The columns of one fitted peak: Model, each value with its ±, and
    \u0394BIC (is the peak needed? see PeakFittingManager.add_peak_bic)."""
    return ['Model'] + [name + p for name in ('Center', 'Height', 'Width', 'Extra', 'FWHM',
                                              'Area') for p in ('', pm(sigmas))] + [DBIC]


DBIC = '\u0394BIC'


PM = pm(1)
PEAK_COLUMNS = peak_columns(1)


def peak_values(fitted_peak, sigmas=1):
    """[model, center, ±, height, ±, width, ±, extra, ±, FWHM, ±, area, ±]
    of one fitted peak (± = `sigmas` x the standard error); extra is None for
    a model without one, an error None where it is not known."""
    model = fitted_peak['model']
    par = fitted_peak['parameters']

    def num(key):
        v = par.get(key) if key else None
        return float(v) if v is not None else None
    out = [model]
    for key in ('center', 'height', WIDTH_KEY.get(model, 'sigma'), EXTRA_KEY.get(model),
                'fwhm', 'area'):
        out += [num(key), error_of(fitted_peak, key, sigmas) if num(key) is not None else None]
    d = fitted_peak.get('delta_bic')
    out.append(float(d) if d is not None and np.isfinite(d) else None)
    return out


def status(result):
    """'' for a fitted spectrum, else why it has no values."""
    if result.get('ok'):
        return ''
    return 'not fitted yet' if result.get('pending') else 'fit failed'


def peaks_long(results, rows, peak=None, sigmas=1):
    """(columns, rows) one row per spectrum and peak - Spectrum, Peak, then
    PEAK_COLUMNS and R² - for the spectra `rows` (in this order); only peak
    number `peak` (0-based) if given. A spectrum without values gives one
    row with its status in the column Model."""
    columns = ['Spectrum', 'Peak'] + peak_columns(sigmas) + ['R\u00b2']
    out = []
    for k in rows:
        r = results[k]
        r2 = r.get('r2')
        r2 = float(r2) if r.get('ok') and r2 is not None and np.isfinite(r2) else None
        peaks = (r.get('peaks') or []) if r.get('ok') else []
        numbers = range(len(peaks)) if peak is None else [peak]
        rows_k = [[r['label'], j + 1] + peak_values(peaks[j], sigmas) + [r2]
                  for j in numbers if j < len(peaks) and peaks[j] is not None]
        if not rows_k:
            rows_k = [[r['label'], None if peak is None else peak + 1, status(r) or 'no such peak']
                      + [None] * (len(PEAK_COLUMNS) - 1) + [r2]]
        out += rows_k
    return columns, out


def model_curves(x, fitted, manager=None, background=None):
    """(total, [one curve per peak]) of fitted peaks at x; with the fitted
    background (a dict of PeakFittingManager.fit_peaks) the total includes
    it - the peaks themselves are without it."""
    manager = manager or PeakFittingManager()
    x = np.asarray(x, dtype=float)
    parts = []
    for f in fitted or []:
        model = f['model']
        par = f['parameters']
        params = [par['height'], par['center'], par[WIDTH_KEY[model]]]
        if model in EXTRA_KEY:
            params.append(par[EXTRA_KEY[model]])
        parts.append(manager.peak_models[model][0](x, *params))
    total = np.sum(parts, axis=0) if parts else np.zeros_like(x)
    if background:
        from src.modules.data_analysis.peak_fitting_manager import background_values
        total = total + background_values(background, x)
    return total, parts


# A poor fit (marked \u26a0 in the window's list of spectra): R\u00b2 below POOR_R2
# AND the residual clearly larger than the noise (POOR_NOISE times or more).
# R\u00b2 alone is low also for a good fit of noisy data (the noise itself is
# not described by any peak); a residual no larger than the noise is all a
# fit can do.
POOR_R2 = 0.9
POOR_NOISE = 1.3


def _best_assignment(centres, refs):
    """Peaks (centres, ascending) to bands (refs, ascending), in order, each
    band at most one peak: {peak index: band index} with the smallest total
    distance. More peaks than bands: the farthest ones get none."""
    import itertools
    n, m = len(centres), len(refs)
    best, best_cost = {}, None
    if n <= m:
        for bands in itertools.combinations(range(m), n):
            cost = sum(abs(centres[i] - refs[b]) for i, b in enumerate(bands))
            if best_cost is None or cost < best_cost:
                best, best_cost = {i: b for i, b in enumerate(bands)}, cost
    else:
        for keep in itertools.combinations(range(n), m):
            cost = sum(abs(centres[i] - refs[b]) for b, i in enumerate(keep))
            if best_cost is None or cost < best_cost:
                best, best_cost = {i: b for b, i in enumerate(keep)}, cost
    return best


def match_by_position(results):
    """The peaks of the fitted spectra matched by position across the
    series, instead of by their row number: (bands, aligned results).

    bands: one per band of the series, ascending by position, each
    {'center': median position, 'peaks': {spectrum: its peak index}};
    aligned results: copies of `results` whose 'peaks' lists have one entry
    per band - the spectrum's peak in that band (with '_index', its row in
    the spectrum's own list) or None.

    How: the positions of all fitted peaks, sorted, are grouped wherever
    neighbouring ones are closer than half their FWHM (so a band that moves
    a little along the series stays one group). A group in which most
    spectra have m peaks (e.g. a doublet: 2) gives m bands - their
    positions the medians of the spectra with m peaks; every spectrum's
    peaks of the group go to these bands in order of position, the nearest
    ones. Peaks left over (a spectrum with a band split into two, e.g. 814
    and 842 where the others have one at 832) get bands of their own,
    shown as extra bands next to it."""
    from collections import Counter
    items = []
    for k, r in enumerate(results):
        if r.get('ok') and r.get('peaks'):
            for j, p in enumerate(r['peaks']):
                if p is None:
                    continue
                par = p.get('parameters') or {}
                try:
                    c = float(par['center'])
                except (KeyError, TypeError, ValueError):
                    continue
                w = abs(float(par.get('fwhm') or 0.0))
                items.append((c, w, k, j))
    if not items:
        return [], [dict(r) for r in results]
    items.sort()

    def close(a, b):
        widths = [w for w in (a[1], b[1]) if w > 0]
        return b[0] - a[0] <= 0.5 * min(widths) if widths else b[0] == a[0]
    groups = [[items[0]]]
    for a, b in zip(items, items[1:]):
        if close(a, b):
            groups[-1].append(b)
        else:
            groups.append([b])
    bands = []
    for group in groups:
        by_k = {}
        for it in group:
            by_k.setdefault(it[2], []).append(it)
        counts = Counter(len(v) for v in by_k.values())
        m = max(counts, key=lambda n: (counts[n], -n))       # most common; a tie: fewer
        refs = [float(np.median([v[i][0] for v in by_k.values() if len(v) == m]))
                for i in range(m)]
        main = [{} for _ in range(m)]
        extras = []
        for k, v in by_k.items():
            pick = _best_assignment([it[0] for it in v], refs)
            for i, it in enumerate(v):
                if i in pick:
                    main[pick[i]][k] = it[3]
                else:
                    extras.append(it)
        found = [{'center': refs[b], 'peaks': main[b]} for b in range(m) if main[b]]
        # the left-over peaks: bands of their own (one peak per spectrum each)
        for it in sorted(extras):
            for band in found[m:] if len(found) > m else []:
                if it[2] not in band['peaks'] and abs(it[0] - band['center']) <= 0.5 * max(it[1], 1e-12):
                    band['peaks'][it[2]] = it[3]
                    break
            else:
                found.append({'center': it[0], 'peaks': {it[2]: it[3]}})
        bands += sorted(found, key=lambda b: b['center'])
    aligned = []
    for k, r in enumerate(results):
        a = dict(r)
        if r.get('ok') and r.get('peaks'):
            a['peaks'] = [(dict(r['peaks'][b['peaks'][k]], _index=b['peaks'][k])
                           if k in b['peaks'] else None) for b in bands]
        aligned.append(a)
    return bands, aligned


def residual_to_noise(result, x, y, manager=None):
    """How many times the residual (data minus fit) is larger than the noise
    of the data: about 1 when the fit leaves only noise, clearly more when
    something is not described (a missing peak, a wrong background). The
    noise is taken from the residual itself - from the differences of
    neighbouring points, which a smooth leftover band hardly changes:
    rms(residual) / (rms(differences) / sqrt 2). None when it cannot be told."""
    if not result or not result.get('ok') or not result.get('peaks'):
        return None
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    total, _ = model_curves(x, result['peaks'], manager, result.get('background'))
    res = y - total
    res = res[np.isfinite(res)]
    if res.size < 10:
        return None
    res = res - np.mean(res)
    noise = np.sqrt(np.mean(np.diff(res) ** 2)) / np.sqrt(2.0)
    if not np.isfinite(noise) or noise <= 0:
        return None
    return float(np.sqrt(np.mean(res ** 2)) / noise)


def poor_fit(result, x, y, manager=None):
    """(poor?, R\u00b2, residual / noise or None): poor when R\u00b2 is below
    POOR_R2 and the residual is POOR_NOISE times the noise or more (or the
    noise cannot be told)."""
    r2 = result.get('r2') if result else None
    if r2 is None or not np.isfinite(r2) or r2 >= POOR_R2:
        return False, r2, None
    ratio = residual_to_noise(result, x, y, manager)
    return (ratio is None or ratio >= POOR_NOISE), r2, ratio


def hand_result(label, fitted, x, y, background=None, manager=None):
    """The result of a spectrum whose values were set by hand (changed in
    the table of peaks after a fit, or a peak removed): its values as they
    are now - no uncertainties, no \u0394BIC (those only come from a fit) - and
    the R\u00b2 of these values. Marked 'manual' (shown as "set by hand")."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    total, _ = model_curves(x, fitted, manager, background)
    good = np.isfinite(x) & np.isfinite(y) & np.isfinite(total)
    ss_res = float(np.sum((y[good] - total[good]) ** 2))
    ss_tot = float(np.sum((y[good] - np.mean(y[good])) ** 2)) if good.any() else 0.0
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {'label': label, 'ok': True, 'manual': True, 'peaks': list(fitted),
            'background': background, 'r2': r2}


def _number(v, digits):
    if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool):
        v = float(v)
        if not np.isfinite(v):
            return None
        return round(v, digits) if digits is not None else v
    return v


def _plain_peak(f, digits=10):
    """One fitted peak with plain Python numbers (its values and their
    errors; an error that could not be estimated is None)."""
    out = {'model': f['model'],
           'parameters': {k: _number(v, digits) for k, v in f['parameters'].items()}}
    if f.get('errors') is not None:
        out['errors'] = {k: _number(v, digits) for k, v in f['errors'].items()}
    if f.get('delta_bic') is not None:
        out['delta_bic'] = _number(f['delta_bic'], digits)
    return out


def error_of(fitted_peak, key, sigmas=1):
    """The uncertainty of one value of a fitted peak: `sigmas` x its
    standard error (None if unknown)."""
    v = (fitted_peak.get('errors') or {}).get(key) if key else None
    return float(v) * sigmas if v is not None and np.isfinite(v) else None


def plain(results):
    """The results with plain Python numbers (no numpy), to keep them with
    the window's settings."""
    out = []
    for r in results:
        peaks = None
        if r.get('peaks'):
            peaks = [_plain_peak(f) for f in r['peaks']]
        r2 = r.get('r2')
        out.append({'label': r.get('label', ''), 'ok': bool(r.get('ok')), 'peaks': peaks,
                    'r2': (float(r2) if r2 is not None and np.isfinite(r2) else None)})
        if r.get('background'):
            out[-1]['background'] = plain_background(r['background'])
        if r.get('global'):
            out[-1]['global'] = r['global']
        if r.get('pending'):
            out[-1]['pending'] = True
        if r.get('manual'):
            out[-1]['manual'] = True
    return out


def pending(spectra):
    """Results for a series none of whose spectra is fitted yet (one is
    fitted on its own with Fit Peaks)."""
    return [{'label': str(s.get('label', '')), 'ok': False, 'peaks': None, 'r2': None,
             'pending': True} for s in spectra]


def summary(results):
    ok = sum(bool(r['ok']) for r in results)
    waiting = sum(bool(r.get('pending')) for r in results)
    text = f"Fitted {ok} of {len(results)} spectra."
    together = {r.get('global') for r in results if r.get('ok') and r.get('global')}
    if together:
        from src.modules.data_analysis.peak_fitting_global import SHARE_TEXT
        n = sum(1 for r in results if r.get('ok') and r.get('global'))
        text += (f" {n} of them fitted together (" + ", ".join(SHARE_TEXT.get(t, t)
                                                              for t in sorted(together))
                 + " for all).")
    by_hand = sum(1 for r in results if r.get('ok') and r.get('manual'))
    if by_hand:
        text += (f" {by_hand} of them set by hand (\u270e: values changed after the fit - no "
                 "\u00b1; Fit Peaks fits them again).")
    if waiting:
        text += f" {waiting} not fitted yet (select them, or All, and click Fit Peaks)."
    bad = [r['label'] for r in results if not r['ok'] and not r.get('pending')]
    if bad:
        text += (f" Not fitted (empty rows): {', '.join(bad[:3])}{', …' if len(bad) > 3 else ''}"
                 " - the fit did not converge; check the starting peaks or fit a shorter series.")
    return text
