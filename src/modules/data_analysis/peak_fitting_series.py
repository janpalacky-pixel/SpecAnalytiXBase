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


def fit_one(x, y, start, amplitude_constraint='unrestricted', manager=None):
    """(fitted peaks or None, R²) of one spectrum from the starting peaks."""
    manager = manager or PeakFittingManager()
    if not start or len(x) <= 4 * len(start):
        return None, np.nan
    fitted, y_fit = manager.fit_peaks(x, y, start, amplitude_constraint)
    if fitted is None:
        return None, np.nan
    ss_res = float(np.sum((y - y_fit) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return fitted, (1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan)


def _fit_chunk_worker(payload):
    """Worker-process entry point (top level so it can be pickled):
    (start peaks, constraint, [(x, y), ...]) -> [(fitted or None, r2), ...]."""
    from src.modules.utils.parallel_utils import count_item
    start, constraint, pairs = payload
    manager = PeakFittingManager()
    out = []
    for item in pairs:                    # (x, y[, its own starting peaks[, its constraint]])
        x, y = item[0], item[1]
        own = item[2] if len(item) > 2 and item[2] is not None else start
        own_constraint = item[3] if len(item) > 3 and item[3] else constraint
        fitted, r2 = fit_one(np.asarray(x), np.asarray(y), own, own_constraint, manager)
        if fitted is not None:            # plain floats: picklable, no numpy scalars
            fitted = [{'model': f['model'],
                       'parameters': {k: (float(v) if isinstance(v, (int, float, np.floating))
                                          else v) for k, v in f['parameters'].items()}}
                      for f in fitted]
        out.append((fitted, float(r2)))
        count_item()
    return out


def fit_series_independent(spectra, start_peaks, amplitude_constraint='unrestricted',
                           progress=None, parallel=None, starts=None, constraints=None):
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
        payloads = [(start, amplitude_constraint, [pairs[i] for i in c]) for c in chunks]

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
                              cons[i] if cons is not None else amplitude_constraint, manager)
            done[0] = i + 1
            report()
    return [{'label': str(s.get('label', '')), 'ok': fitted is not None, 'peaks': fitted,
             'r2': r2} for s, (fitted, r2) in zip(spectra, rows)]


def fit_series(spectra, initial_peaks, amplitude_constraint='unrestricted', progress=None,
               manager=None):
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
        fitted, r2 = fit_one(x, y, start, amplitude_constraint, manager)
        results.append({'label': str(s.get('label', '')), 'ok': fitted is not None,
                        'peaks': fitted, 'r2': r2})
        if fitted is not None:
            start = start_from(fitted, start)
        if progress is not None:
            progress(k + 1, len(spectra))
    return results


def fit_each(spectra, starts, amplitude_constraint='unrestricted', progress=None,
             manager=None, constraints=None):
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
            fitted, r2 = fit_one(x, y, start, constraints[k] if constraints else
                                 amplitude_constraint, manager)
        else:
            fitted, r2 = None, np.nan
        results.append({'label': str(s.get('label', '')), 'ok': fitted is not None,
                        'peaks': fitted, 'r2': r2})
        used.append(start)
        if fitted is not None:
            previous = start_from(fitted, start)
        if progress is not None:
            progress(k + 1, len(spectra))
    return results, used


def series_table(results, n_peaks):
    """(columns, rows) of the series: one row per spectrum - its name, then
    position, FWHM, height and area of peak 1, 2, ..., then R². A failed
    fit gives None (an empty cell)."""
    columns = ['Spectrum'] + [f'Peak {j + 1} {name}' for j in range(n_peaks)
                              for name, _ in VALUES] + ['R²']
    rows = []
    for r in results:
        row = [r['label']]
        for j in range(n_peaks):
            par = r['peaks'][j]['parameters'] if r['ok'] and j < len(r['peaks']) else None
            row += [float(par[key]) if par is not None else None for _, key in VALUES]
        r2 = r.get('r2')
        row.append(float(r2) if r['ok'] and r2 is not None and np.isfinite(r2) else None)
        rows.append(row)
    return columns, rows


def model_curves(x, fitted, manager=None):
    """(total, [one curve per peak]) of fitted peaks at x."""
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
    return total, parts


def plain(results):
    """The results with plain Python numbers (no numpy), to keep them with
    the window's settings."""
    out = []
    for r in results:
        peaks = None
        if r.get('peaks'):
            peaks = [{'model': f['model'],
                      'parameters': {k: (round(float(v), 10) if isinstance(v, (int, float, np.floating))
                                         else v) for k, v in f['parameters'].items()}}
                     for f in r['peaks']]
        r2 = r.get('r2')
        out.append({'label': r.get('label', ''), 'ok': bool(r.get('ok')), 'peaks': peaks,
                    'r2': (float(r2) if r2 is not None and np.isfinite(r2) else None)})
        if r.get('pending'):
            out[-1]['pending'] = True
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
    if waiting:
        text += f" {waiting} not fitted yet (select them, or All, and click Fit Peaks)."
    bad = [r['label'] for r in results if not r['ok'] and not r.get('pending')]
    if bad:
        text += (f" Not fitted (empty rows): {', '.join(bad[:3])}{', …' if len(bad) > 3 else ''}"
                 " - the fit did not converge; check the starting peaks or fit a shorter series.")
    return text
