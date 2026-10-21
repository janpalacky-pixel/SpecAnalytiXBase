# src/modules/data_analysis/mixture_analysis.py
"""Mixture analysis with known components (classical least squares, CLS):
every sample spectrum is described as a sum of known component spectra,

    sample(x) ~ a1 * component1(x) + a2 * component2(x) + ... [+ background]

and the amounts a1, a2, ... are found by least squares - optionally never
negative (non-negative least squares), optionally with a constant or a
sloping (linear) background. Also given: each component's fraction of the
total (a_k / sum of a), how well the sum describes the sample (R^2) and the
remaining difference (residual). Qt-free; the window is
src/views/dialogs/data_analysis/mixture_analysis_dialog.py.

The components are put on each sample's x values (linear interpolation);
only the x-range covered by all components and the sample is used,
optionally narrowed to a chosen range.
"""

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from scipy.optimize import nnls

BACKGROUNDS = {'none': 'none', 'constant': 'constant', 'linear': 'linear (sloping)'}


@dataclass
class MixtureFit:
    label: str
    amounts: np.ndarray                  # one per component
    background: np.ndarray               # [] / [c] / [c, slope]
    x: np.ndarray
    y: np.ndarray
    fit: np.ndarray
    parts: np.ndarray                    # (n_components, n_points): amount * component
    r2: float
    rms: float
    error: str = ''

    @property
    def fractions(self):
        total = float(np.sum(self.amounts))
        if total <= 0 or not np.isfinite(total):
            return np.full(len(self.amounts), np.nan)
        return self.amounts / total

    @property
    def residual(self):
        return self.y - self.fit


def _sorted(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    order = np.argsort(x)
    return x[order], y[order]


def fit_mixture(sample, components, nonnegative=True, background='none', x_range=None):
    """MixtureFit of one sample spectrum (dict) with component spectra (dicts)."""
    label = str(sample.get('label', ''))
    xs, ys = _sorted(sample['x_scale'], sample['y_scale'])
    comps = [_sorted(c['x_scale'], c['y_scale']) for c in components]
    lo = max([xs.min()] + [cx.min() for cx, _ in comps])
    hi = min([xs.max()] + [cx.max() for cx, _ in comps])
    if x_range is not None:
        lo, hi = max(lo, min(x_range)), min(hi, max(x_range))
    keep = (xs >= lo) & (xs <= hi) & np.isfinite(ys)
    n_terms = len(comps) + {'none': 0, 'constant': 1, 'linear': 2}[background]
    empty = MixtureFit(label, np.full(len(comps), np.nan), np.array([]), xs[keep], ys[keep],
                       np.full(int(keep.sum()), np.nan), np.zeros((len(comps), int(keep.sum()))),
                       np.nan, np.nan)
    if hi <= lo or keep.sum() < n_terms + 2:
        empty.error = ("The sample and the components have too little x-range in common "
                       "(or the chosen range is outside it).")
        return empty
    x, y = xs[keep], ys[keep]
    columns = [np.interp(x, cx, cy) for cx, cy in comps]
    if background in ('constant', 'linear'):
        columns.append(np.ones_like(x))
    if background == 'linear':
        span = (x.max() - x.min()) or 1.0
        columns.append((x - x.mean()) / span)      # scaled, so the numbers stay well behaved
    A = np.column_stack(columns)
    if nonnegative:
        # amounts >= 0; the background may be negative: split it into +/- parts
        nb = A.shape[1] - len(comps)
        A2 = np.column_stack([A] + ([-A[:, len(comps):]] if nb else []))
        coef2, _ = nnls(A2, y)
        coef = coef2[:A.shape[1]].copy()
        if nb:
            coef[len(comps):] -= coef2[A.shape[1]:]
    else:
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    fit = A @ coef
    amounts = coef[:len(comps)]
    parts = np.array([a * col for a, col in zip(amounts, columns[:len(comps)])])
    ss_res = float(np.sum((y - fit) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    bg = coef[len(comps):]
    if background == 'linear':                     # back to "constant at mean x" + slope per x unit
        span = (x.max() - x.min()) or 1.0
        bg = np.array([bg[0], bg[1] / span])
    return MixtureFit(label, amounts, bg, x, y, fit, parts, r2, float(np.sqrt(ss_res / len(y))))


def analyse(samples, components, nonnegative=True, background='none', x_range=None):
    return [fit_mixture(s, components, nonnegative, background, x_range) for s in samples]


def table_columns(component_names, background='none'):
    cols = ['Spectrum'] + [f'Amount of {n}' for n in component_names] \
        + [f'Fraction of {n}' for n in component_names]
    if background in ('constant', 'linear'):
        cols.append('Background (constant)')
    if background == 'linear':
        cols.append('Background (slope)')
    return cols + ['R²', 'Residual (RMS)']


def table_rows(fits, background='none'):
    rows = []
    for f in fits:
        row = [f.label] + list(map(float, f.amounts)) + list(map(float, f.fractions))
        nb = {'none': 0, 'constant': 1, 'linear': 2}[background]
        bg = list(map(float, f.background)) if len(f.background) == nb else [np.nan] * nb
        rows.append(row + bg + [float(f.r2), float(f.rms)])
    return rows


def rows_as_text(columns, rows):
    def cell(v):
        if isinstance(v, float):
            return '' if not np.isfinite(v) else repr(v)
        return str(v)
    return '\n'.join(['\t'.join(columns)] + ['\t'.join(cell(v) for v in r) for r in rows]) + '\n'


def export(columns, rows, path):
    import pandas as pd
    frame = pd.DataFrame(rows, columns=columns)
    if path.lower().endswith('.xlsx'):
        frame.to_excel(path, index=False, sheet_name='Mixture analysis')
    else:
        frame.to_csv(path, index=False, sep='\t' if path.lower().endswith('.txt') else ',')
