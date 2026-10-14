# src/modules/visualization_analysis/group_statistics.py
"""Group statistics: compare groups of spectra (e.g. treated vs control)
on one value per spectrum. Qt-free.

1. Groups -- every spectrum gets a group name (or none):
   groups_from_contains  "name contains <text>" rules, first match wins;
   groups_from_part      a part of the name split at a separator
                         (e.g. "sampleA_day3_01" -> part 2 -> "day3");
   groups_from_table     a table of name -> group (CSV/Excel), read with
                         read_group_table.
2. Value -- one number per spectrum, from its own x-axis (spectra may have
   different axes): VALUE_KINDS.
3. Comparison -- describe() per group; compare():
   two groups:   Welch t-test (unequal variances) or Mann-Whitney U;
   three or more: one-way ANOVA or Kruskal-Wallis, plus every pair
                  (Welch t or Mann-Whitney) with Holm correction;
   effect sizes: Hedges' g (pairs), eta squared (ANOVA), rank-biserial r
                 (Mann-Whitney), epsilon squared (Kruskal-Wallis).
   Groups with fewer than 2 values are left out of the tests (reported).
"""

import math
import re

import numpy as np
from scipy import stats

from src.modules.utils.band_integration import (
    band_area, band_mean, covers, integration_intervals)

VALUE_KINDS = {
    'intensity_at_x': "Intensity at x",
    'mean': "Mean over a range",
    'area': "Area over a range",
    'max': "Maximum in a range",
    'ratio': "Band ratio: area A / area B",
}

TESTS = {
    'parametric': "Parametric: Welch t-test / one-way ANOVA",
    'nonparametric': "Non-parametric: Mann–Whitney U / Kruskal–Wallis",
}

NO_GROUP = ''

_trapz = getattr(np, 'trapezoid', None) or np.trapz      # numpy 2 renamed trapz


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def groups_from_contains(labels, rules, case_sensitive=False):
    """rules: list of (text, group). A spectrum gets the group of the first
    rule whose text occurs in its name; NO_GROUP if none matches."""
    out = []
    for label in labels:
        name = label if case_sensitive else label.lower()
        group = NO_GROUP
        for text, grp in rules:
            text = (text or '').strip()
            if text and (text if case_sensitive else text.lower()) in name:
                group = grp.strip() or text
                break
        out.append(group)
    return out


def groups_from_part(labels, separators='_', part=1):
    """The `part`-th piece (1-based; negative counts from the end) of each
    name split at any of the `separators` characters; NO_GROUP if the name
    has fewer pieces."""
    pattern = '[' + re.escape(separators or '_') + ']'
    out = []
    for label in labels:
        # pieces trimmed: "CD_spectra_TBA : 0001" split at ':' gives
        # "CD_spectra_TBA", not "CD_spectra_TBA " (an invisible extra group)
        pieces = [p.strip() for p in re.split(pattern, label) if p.strip() != '']
        try:
            index = part - 1 if part > 0 else part
            out.append(pieces[index] if part != 0 else NO_GROUP)
        except IndexError:
            out.append(NO_GROUP)
    return out


def groups_from_root_name(labels):
    """Group = the "common root name" of each label, the same rule the
    Select / Rename dialogs use (derive_root_name): the name without its
    numbering, e.g. "Chlorella [r24_c14]" -> "Chlorella",
    "CD_spectra_TBA : 0019" -> "CD_spectra_TBA", "sample_012" -> "sample".
    """
    from src.views.dialogs.misc.spectra_selection_dialog import derive_root_name
    return [derive_root_name(str(label)) for label in labels]


def groups_from_table(labels, mapping):
    """mapping: {spectrum name: group}. Names are matched exactly first,
    then ignoring case and surrounding spaces."""
    exact = {str(k): str(v).strip() for k, v in mapping.items()}
    loose = {str(k).strip().lower(): str(v).strip() for k, v in mapping.items()}
    return [exact.get(label, loose.get(label.strip().lower(), NO_GROUP)) for label in labels]


def read_group_table(path):
    """{name: group} from a CSV/TXT or Excel file whose first two columns are
    the spectrum name and the group (a header row is recognised and skipped
    if its second cell is 'group')."""
    import pandas as pd
    if path.lower().endswith(('.xlsx', '.xlsm', '.xls')):
        frame = pd.read_excel(path, header=None, dtype=str)
    else:
        frame = pd.read_csv(path, header=None, dtype=str, sep=None, engine='python')
    if frame.shape[1] < 2:
        raise ValueError("The table needs two columns: spectrum name and group.")
    frame = frame.iloc[:, :2].dropna(how='any')
    if len(frame) and str(frame.iloc[0, 1]).strip().lower() in ('group', 'groups', 'class'):
        frame = frame.iloc[1:]
    return {str(a).strip(): str(b).strip() for a, b in frame.itertuples(index=False)}


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def _xy(spectrum):
    x = np.asarray(spectrum['x_scale'], dtype=float)
    y = np.asarray(spectrum['y_scale'], dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    order = np.argsort(x)
    return x[order], y[order]


def _window(x, y, lo, hi):
    lo, hi = min(lo, hi), max(lo, hi)
    mask = (x >= lo) & (x <= hi)
    return x[mask], y[mask]


def spectrum_value(spectrum, kind, x0=None, range_a=None, range_b=None):
    """The value of one spectrum (NaN if it cannot be computed, e.g. the
    range lies outside the spectrum)."""
    x, y = _xy(spectrum)
    if len(x) == 0:
        return np.nan
    if kind == 'intensity_at_x':
        if x0 is None or x0 < x[0] or x0 > x[-1]:
            return np.nan
        return float(np.interp(x0, x, y))
    # A range not completely inside the spectrum: no value (not a value
    # from the part it has; see band_integration.py, point 5)
    if not covers(x, [range_a] + ([range_b] if kind == 'ratio' else [])):
        return np.nan
    xa, ya = _window(x, y, *range_a)
    # Area / mean: exact range edges, mean = area / width (correct for
    # unevenly spaced points); see src/modules/utils/band_integration.py
    def area(rng):
        return band_area(x, y, integration_intervals(x, include=[rng]))
    if kind == 'mean':
        return band_mean(x, y, integration_intervals(x, include=[range_a])) \
            if len(ya) else np.nan
    if kind == 'max':
        return float(np.max(ya)) if len(ya) else np.nan
    if kind == 'area':
        return area(range_a) if len(ya) >= 2 else np.nan
    if kind == 'ratio':
        xb, yb = _window(x, y, *range_b)
        if len(ya) < 2 or len(yb) < 2:
            return np.nan
        b = area(range_b)
        return area(range_a) / b if b != 0 else np.nan
    raise ValueError(f"unknown value kind {kind!r}")


def spectrum_values(spectra, kind, **kwargs):
    return np.array([spectrum_value(s, kind, **kwargs) for s in spectra], dtype=float)


def collect(groups, values):
    """{group: array of finite values}, groups in order of first appearance;
    spectra without a group or with a NaN value are left out."""
    out = {}
    for g, v in zip(groups, values):
        if g == NO_GROUP or not np.isfinite(v):
            continue
        out.setdefault(g, []).append(float(v))
    return {g: np.array(v) for g, v in out.items()}


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def describe(data):
    """Per group: n, mean, SD (n-1), median, min, max."""
    rows = []
    for g, v in data.items():
        rows.append({'group': g, 'n': len(v),
                     'mean': float(np.mean(v)) if len(v) else np.nan,
                     'sd': float(np.std(v, ddof=1)) if len(v) > 1 else np.nan,
                     'median': float(np.median(v)) if len(v) else np.nan,
                     'min': float(np.min(v)) if len(v) else np.nan,
                     'max': float(np.max(v)) if len(v) else np.nan})
    return rows


def hedges_g(a, b):
    """Standardised difference of means (a - b), small-sample corrected."""
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return np.nan
    s = math.sqrt(((n1 - 1) * np.var(a, ddof=1) + (n2 - 1) * np.var(b, ddof=1)) / (n1 + n2 - 2))
    if s == 0:
        return np.nan
    d = (np.mean(a) - np.mean(b)) / s
    return float(d * (1 - 3 / (4 * (n1 + n2) - 9)))


def rank_biserial(a, b):
    """Rank-biserial correlation for Mann-Whitney (positive: a tends to be larger)."""
    u = stats.mannwhitneyu(a, b, alternative='two-sided').statistic
    return float(2 * u / (len(a) * len(b)) - 1)


def holm(pvalues):
    """Holm-Bonferroni adjusted p-values (same order as given)."""
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    order = np.argsort(p)
    adjusted = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        adjusted[i] = running
    return adjusted


def _pair(a, b, parametric):
    if parametric:
        res = stats.ttest_ind(a, b, equal_var=False)
        return float(res.statistic), float(res.pvalue), hedges_g(a, b)
    res = stats.mannwhitneyu(a, b, alternative='two-sided')
    return float(res.statistic), float(res.pvalue), rank_biserial(a, b)


def compare(data, parametric=True):
    """Test whether the groups differ. Returns a dict:
    test, statistic, p, effect_name, effect, groups (used), excluded
    (groups with < 2 values), pairs (list of dicts: a, b, difference
    (mean or median a - b), statistic, p, p_holm, effect), note."""
    used = {g: v for g, v in data.items() if len(v) >= 2}
    excluded = [g for g, v in data.items() if len(v) < 2]
    result = {'test': None, 'statistic': np.nan, 'p': np.nan, 'effect_name': '',
              'effect': np.nan, 'groups': list(used), 'excluded': excluded, 'pairs': [],
              'parametric': parametric, 'note': ''}
    if len(used) < 2:
        result['note'] = "At least two groups with two or more values each are needed."
        return result
    names = list(used)
    values = [used[g] for g in names]
    centre = np.mean if parametric else np.median
    if len(used) == 2:
        stat, p, effect = _pair(values[0], values[1], parametric)
        result.update(test="Welch t-test" if parametric else "Mann–Whitney U test",
                      statistic=stat, p=p,
                      effect_name="Hedges' g" if parametric else "rank-biserial r",
                      effect=effect)
    elif parametric:
        res = stats.f_oneway(*values)
        allv = np.concatenate(values)
        ss_total = float(np.sum((allv - allv.mean()) ** 2))
        ss_between = float(sum(len(v) * (v.mean() - allv.mean()) ** 2 for v in values))
        result.update(test="One-way ANOVA", statistic=float(res.statistic), p=float(res.pvalue),
                      effect_name="eta squared",
                      effect=ss_between / ss_total if ss_total > 0 else np.nan)
    else:
        res = stats.kruskal(*values)
        n = sum(len(v) for v in values)
        result.update(test="Kruskal–Wallis test", statistic=float(res.statistic),
                      p=float(res.pvalue), effect_name="epsilon squared",
                      effect=float(res.statistic) / (n - 1) if n > 1 else np.nan)
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            stat, p, effect = _pair(values[i], values[j], parametric)
            pairs.append({'a': names[i], 'b': names[j],
                          'difference': float(centre(values[i]) - centre(values[j])),
                          'statistic': stat, 'p': p, 'effect': effect})
    adjusted = holm([pr['p'] for pr in pairs])
    for pr, ph in zip(pairs, adjusted):
        pr['p_holm'] = float(ph)
    result['pairs'] = pairs
    result['pair_test'] = "Welch t-test" if parametric else "Mann–Whitney U"
    result['pair_effect_name'] = "Hedges' g" if parametric else "rank-biserial r"
    return result


def format_p(p):
    if not np.isfinite(p):
        return "–"
    return "< 0.0001" if p < 1e-4 else f"{p:.4f}"


def p_text(p):
    """'p = 0.0123' or 'p < 0.0001' (plain text; escape it for HTML)."""
    f = format_p(p)
    return "p " + f if f.startswith("<") else "p = " + f
