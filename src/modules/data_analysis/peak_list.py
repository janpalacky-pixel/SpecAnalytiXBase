# src/modules/data_analysis/peak_list.py
"""The peaks of spectra: which points are peaks (the same rule as Detect
Peaks, which labels them on the plot) and a list of them for all selected
spectra - position, height, prominence and width at half height (FWHM) -
to copy into Excel or export (right-click on the plot -> Peak list...).
Qt-free.

The settings are those of Detect Peaks, all relative to the spectrum:
  threshold   a peak must be higher than min + threshold * (max - min)
  prominence  ... and stand out from its surroundings by prominence * (max - min)
  distance    ... and be at least distance * (number of points) from the next peak
  mode        'Positive' (maxima), 'Negative' (minima) or 'Both'
"""

import numpy as np
from scipy.signal import find_peaks, peak_widths

COLUMNS = ['Spectrum', 'Peak', 'Kind', 'Position (x)', 'Height (y)', 'Prominence', 'FWHM',
           'Left half-height x', 'Right half-height x']
# the numbers of a peak that can be plotted (column name -> index in a row)
NUMERIC = {name: COLUMNS.index(name) for name in
           ('Position (x)', 'Height (y)', 'Prominence', 'FWHM', 'Peak')}
# the settings of Detect Peaks and the Peak list when nothing was changed
DEFAULTS = {'threshold': 0.5, 'prominence': 0.1, 'distance': 0.05, 'mode': 'Positive'}

# What each setting means (the "?" of Detect Peaks and of the Peak list):
# (name, what it does, default)
SETTINGS_HELP = [
    ("Threshold (height)",
     "A point counts as a peak only if it is higher than min + threshold \u00d7 (max \u2212 min) "
     "of its own spectrum: 0.5 = only the upper half of the spectrum's range. Lower it to find "
     "smaller peaks.", "0.5"),
    ("Prominence",
     "How much the peak must stand out above the valleys around it, as a fraction of the "
     "spectrum's range (max \u2212 min). Raise it to ignore small bumps and noise riding on a "
     "larger band; lower it when a clear shoulder or small band is missed.", "0.1"),
    ("Distance",
     "The smallest gap between two peaks, as a fraction of the number of points: 0.05 = 5 % of "
     "the points. Raise it when one broad or noisy band gives several peaks next to each other.",
     "0.05"),
    ("Peaks (mode)",
     "Positive: the maxima. Negative: the minima (dips). Both: maxima and minima. For the "
     "minima the same settings are measured downward (on the spectrum turned upside down).",
     "Positive"),
]
COLUMNS_HELP = [
    ("Peak, Kind", "The peak's number within its spectrum, counted from low to high x; maximum or "
     "minimum. When a peak appears or disappears in some spectra (e.g. above a temperature), the "
     "numbers of the peaks after it shift - the same number is then not always the same band. "
     "In the tab Plot, x = Peak by its position groups the peaks by their position instead.",
     ""),
    ("Position (x), Height (y)",
     "Of the highest (or lowest) measured point, so as precise as the point spacing. For a "
     "position between the points use Peak Fitting.", ""),
    ("Prominence", "How far the peak stands out from the valleys around it (in y units).", ""),
    ("FWHM, Left / Right half-height x",
     "The width at half of the prominence and where it starts and ends, interpolated between "
     "the points. Overlapping bands make it a rough estimate.", ""),
]


def _side(y, threshold, prominence, distance):
    span = float(np.max(y) - np.min(y))
    height = np.min(y) + threshold * span
    idx, _ = find_peaks(y, height=height, prominence=prominence * span,
                        distance=max(1, int(distance * len(y))))
    return idx


def peak_indices(y, threshold=0.5, prominence=0.1, distance=0.05, mode='Positive'):
    """Indices of the peaks of *y* (sorted), as Detect Peaks finds them. For
    'Negative', the minima: each side is judged on its own range (see
    peak_detection_manager.py for why)."""
    y = np.asarray(y, dtype=float)
    if len(y) < 2 or not np.all(np.isfinite(y)):
        y = np.nan_to_num(y, nan=np.nanmin(y) if np.isfinite(y).any() else 0.0)
    if len(y) < 2:
        return np.array([], dtype=int)
    pos = _side(y, threshold, prominence, distance) if mode in ('Positive', 'Both') else []
    neg = _side(-y, threshold, prominence, distance) if mode in ('Negative', 'Both') else []
    return np.unique(np.concatenate((np.asarray(pos, int), np.asarray(neg, int)))).astype(int)


def _x_at(x, positions):
    """x at fractional point positions (interpolated: also for uneven steps)."""
    return np.interp(positions, np.arange(len(x)), x)


def spectrum_peaks(x, y, threshold=0.5, prominence=0.1, distance=0.05, mode='Positive'):
    """[{'kind', 'index', 'x', 'y', 'prominence', 'fwhm', 'left', 'right'}] of one spectrum."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    out = []
    if len(y) < 3:
        return out
    idx = peak_indices(y, threshold, prominence, distance, mode)
    if not len(idx):
        return out
    # a maximum when it is higher than its neighbours' mean, else a minimum
    for i in idx:
        lo, hi = max(i - 1, 0), min(i + 1, len(y) - 1)
        kind = 'max' if y[i] >= (y[lo] + y[hi]) / 2 else 'min'
        sig = y if kind == 'max' else -y
        prom = float(_prominence(sig, i))
        width = peak_widths(sig, [i], rel_height=0.5)
        left, right = _x_at(x, width[2])[0], _x_at(x, width[3])[0]
        out.append({'kind': kind, 'index': int(i), 'x': float(x[i]), 'y': float(y[i]),
                    'prominence': prom, 'fwhm': float(abs(right - left)),
                    'left': float(min(left, right)), 'right': float(max(left, right))})
    return out


def _prominence(sig, i):
    from scipy.signal import peak_prominences
    return peak_prominences(sig, [i])[0][0]


def peak_table(spectra, threshold=0.5, prominence=0.1, distance=0.05, mode='Positive'):
    """Rows (lists, in COLUMNS order) for all spectra, peaks by position."""
    return peak_table_with_index(spectra, threshold, prominence, distance, mode)[0]


def peak_table_with_index(spectra, threshold=0.5, prominence=0.1, distance=0.05, mode='Positive'):
    """(rows, index): the rows of peak_table and, for every row, the place of
    its spectrum in `spectra` (names can repeat)."""
    rows, index = [], []
    for i, sp in enumerate(spectra):
        peaks = spectrum_peaks(sp['x_scale'], sp['y_scale'], threshold, prominence, distance, mode)
        peaks.sort(key=lambda p: p['x'])
        for k, p in enumerate(peaks, 1):
            rows.append([str(sp.get('label', '')), k, 'maximum' if p['kind'] == 'max' else 'minimum',
                         p['x'], p['y'], p['prominence'], p['fwhm'], p['left'], p['right']])
            index.append(i)
    return rows, index


def settings_help_html(entries):
    """A table of (name, what it does, default) for the "?" windows."""
    show_default = any(d for _, _, d in entries)
    head = '<tr><th width="22%">Setting</th><th>What it does</th>' + \
        ('<th width="16%">Default</th>' if show_default else '') + '</tr>'
    body = ''.join(f'<tr><td><b>{n}</b></td><td>{w}</td>' + (f'<td>{d}</td>' if show_default else '')
                   + '</tr>' for n, w, d in entries)
    return f'<table border="1" cellspacing="0" cellpadding="5" width="100%">{head}{body}</table>'


def rows_as_text(rows, columns=COLUMNS):
    """Tab-separated, with a header line (Excel pastes it into cells)."""
    def cell(v):
        return repr(v) if isinstance(v, float) else str(v)
    return '\n'.join(['\t'.join(columns)] + ['\t'.join(cell(v) for v in r) for r in rows]) + '\n'


def export(rows, path):
    import pandas as pd
    frame = pd.DataFrame(rows, columns=COLUMNS)
    if path.lower().endswith('.xlsx'):
        frame.to_excel(path, index=False, sheet_name='Peaks')
    else:
        frame.to_csv(path, index=False, sep='\t' if path.lower().endswith('.txt') else ',')


# --- the plot of the peaks (Peak list, tab "Plot") ---------------------------------------

Y_CHOICES = ['Position (x)', 'Height (y)', 'Prominence', 'FWHM']


def x_choices(spectra):
    """[(text, key)] for the x-axis of the peak plot: a value of the spectrum
    (its order, a value stored with it, a number in its name) or a number of
    the peak itself."""
    from src.modules.visualization import color_by_value as cbv
    out = [("Spectrum (order in the list)", ('spectrum', {'mode': 'order'}))]

    def varies(settings):
        # a value that is the same in all spectra (e.g. the "2" of
        # "raman_2comp : raman_01", "raman_2comp : raman_02", ...) would put
        # every point above one x: not offered
        if len(spectra) < 2:
            return True
        found = {v for v in cbv.values(spectra, settings) if v is not None}
        return len(found) >= 2

    for key in cbv.metadata_keys(spectra):
        settings = {'mode': 'metadata', 'metadata_key': key}
        if varies(settings):
            out.append((f"Spectrum: {key}", ('spectrum', settings)))
    if any(cbv.numbers_in(s.get('label', '')) for s in spectra):
        for i, text in cbv.name_number_choices(spectra):
            settings = {'mode': 'name', 'number': i}
            if varies(settings):
                out.append((f"Spectrum: {text} in the name", ('spectrum', settings)))
    for name in ('Position (x)', 'Height (y)', 'Prominence', 'FWHM'):
        out.append((name, ('column', name)))
    out.append(("Peak by its position, as labels (e.g. 686, 1093)", ('band', 'label')))
    out.append(("Peak by its position, on the x scale", ('band', 'position')))
    out.append(("Peak number (1st, 2nd, \u2026 in its spectrum)", ('column', 'Peak')))
    return out


def default_tolerance(rows):
    """How close two peaks of different spectra must be to count as the same
    peak: half of the median FWHM, rounded (0 when there are no widths)."""
    widths = [r[NUMERIC['FWHM']] for r in rows]
    widths = [float(w) for w in widths if isinstance(w, (int, float)) and np.isfinite(w) and w > 0]
    if not widths:
        return 0.0
    half = float(np.median(widths)) / 2
    return float(f'{half:.2g}')


def band_positions(rows, tolerance):
    """For each row, the common position of its peak: the peaks of all
    spectra are sorted by position and neighbours closer than the tolerance
    (in x units) are the same peak; its position is their median. So the same
    band gets the same position in every spectrum, even when it is measured
    at 685 in one spectrum and 686 in the next, and even when a peak before
    it is missing in some spectra (unlike the peak number)."""
    pos = [float(r[NUMERIC['Position (x)']]) for r in rows]
    if not pos:
        return []
    order = sorted(range(len(pos)), key=pos.__getitem__)
    groups, current = [], [order[0]]
    for i in order[1:]:
        if pos[i] - pos[current[-1]] <= tolerance:
            current.append(i)
        else:
            groups.append(current)
            current = [i]
    groups.append(current)
    out = [0.0] * len(pos)
    for g in groups:
        centre = float(np.median([pos[i] for i in g]))
        for i in g:
            out[i] = centre
    return out


def band_label(value, all_values):
    """The text of a peak position on the axis: whole numbers when the
    positions are large (e.g. wavenumbers), else 4 significant digits."""
    span = (max(all_values) - min(all_values)) if all_values else 0
    if span >= 50 or abs(value) >= 1000:
        return f'{value:.0f}'
    return f'{value:.4g}'


def plot_values(rows, index, spectra, x_key, y_name, tolerance=0.0):
    """(x, y) of the rows for the peak plot; x is None for a spectrum without
    that value (e.g. no number in its name). For x = the peak by its position
    x is the common position of the peak (band_positions)."""
    from src.modules.visualization import color_by_value as cbv
    kind, what = x_key
    if kind == 'spectrum':
        per_spectrum = cbv.values(spectra, what)
        xs = [per_spectrum[i] for i in index]
    elif kind == 'band':
        xs = band_positions(rows, tolerance)
    else:
        xs = [float(r[NUMERIC[what]]) for r in rows]
    ys = [float(r[NUMERIC[y_name]]) for r in rows]
    return xs, ys
