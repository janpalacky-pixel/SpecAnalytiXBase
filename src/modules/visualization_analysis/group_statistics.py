# src/modules/visualization_analysis/group_statistics.py
"""Group statistics: compare groups of spectra (e.g. treated vs control)
on one value per spectrum. Qt-free.

1. Groups -- every spectrum gets a group name (or none):
   groups_from_contains  "name contains <text>" rules, first match wins;
   groups_from_part      a part of the name split at a separator
                         (e.g. "sampleA_day3_01" -> part 2 -> "day3");
   groups_from_table     a table of name -> group (CSV/Excel), read with
                         read_group_table.
2. Value -- one number per spectrum (group_values.py: one band with the
   2D Map / Band Ratio metrics, two bands A and B combined, or a
   whole-spectrum value): VALUE_KINDS, compute_values.
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

# All value choices (one band, two bands, whole spectrum): group_values.py
from src.modules.visualization_analysis.group_values import VALUE_KINDS, VALUE_SECTIONS  # noqa: E402,F401

TESTS = {
    'parametric': "Parametric: Welch t-test / one-way ANOVA",
    'nonparametric': "Non-parametric: Mann–Whitney U / Kruskal–Wallis",
}

NO_GROUP = ''

_trapz = getattr(np, 'trapezoid', None) or np.trapz      # numpy 2 renamed trapz


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def property_value(spectrum, key):
    """A number stored with the spectrum (Spectrum properties, or read from
    the file, e.g. temperature_C), or None."""
    value = (spectrum.get('metadata') or {}).get(key)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def groups_from_property(spectra, key, split=None):
    """Groups from a value stored with each spectrum: every value its own
    group ("pH 7.4"), or - with `split` - two groups below and from that
    value on ("pH < 7.2", "pH \u2265 7.2"). A spectrum without the value
    gets no group."""
    out = []
    for s in spectra:
        v = property_value(s, key)
        if v is None:
            out.append(NO_GROUP)
        elif split is None:
            out.append(f"{key} {v:g}")
        else:
            out.append(f"{key} < {split:g}" if v < split else f"{key} \u2265 {split:g}")
    return out


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


_HEADER_WORDS = ('group', 'groups', 'class')
_TABLE_SEPARATORS = ' \t,;'


def _split_table_line(line, known):
    """(name, group) from one line of a text table, or None.

    Spectrum names often contain spaces ("run : temp_01"), so a plain
    "split at spaces" is wrong. Order of attempts:
    1. a known spectrum name (`known`: {lower-case name: name}) at the start
       of the line, followed by a separator -> the rest is the group (works
       with any separator: space, tab, comma, semicolon);
    2. tab-separated cells;  3. semicolon / comma;
    4. spaces: the group is the last word, the name everything before it."""
    s = line.rstrip('\r\n')
    if not s.strip():
        return None
    low = s.lower()
    if known:
        cuts = [i for i, ch in enumerate(s) if ch in _TABLE_SEPARATORS] + [len(s)]
        for i in sorted(set(cuts), reverse=True):         # longest name first
            name = known.get(low[:i].strip().strip('"'))
            if name is not None:
                group = s[i:].strip(_TABLE_SEPARATORS + '"\'')
                return name, group
    cells = [c.strip().strip('"') for c in s.split('\t') if c.strip()]
    if '\t' in s and len(cells) >= 2:
        return cells[0], cells[1]
    for sep in (';', ','):
        cells = [c.strip().strip('"') for c in s.split(sep) if c.strip()]
        if sep in s and len(cells) >= 2:
            return cells[0], cells[1]
    parts = s.strip().rsplit(None, 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None


def read_group_table(path, labels=None):
    """{name: group} from a CSV/TXT or Excel file: spectrum name and group
    in the first two columns (a header row whose second cell is 'group' is
    skipped). For text files `labels` (the spectrum names in the window)
    lets names that contain spaces be recognised whatever the separator."""
    if path.lower().endswith(('.xlsx', '.xlsm', '.xls')):
        import pandas as pd
        frame = pd.read_excel(path, header=None, dtype=str)
        if frame.shape[1] < 2:
            raise ValueError("The table needs two columns: spectrum name and group.")
        frame = frame.iloc[:, :2].dropna(how='any')
        rows = [(str(a).strip(), str(b).strip()) for a, b in frame.itertuples(index=False)]
    else:
        with open(path, encoding='utf-8-sig', errors='replace') as fh:
            lines = fh.read().splitlines()
        known = {str(l).strip().lower(): str(l) for l in (labels or [])}
        rows = [r for r in (_split_table_line(line, known) for line in lines) if r]
        rows = [(a, b) for a, b in rows if a and b]
        if not rows:
            raise ValueError("The table needs two columns: spectrum name and group.")
    if rows and rows[0][1].strip().lower() in _HEADER_WORDS:
        rows = rows[1:]
    return {a: b for a, b in rows}


def read_group_sample_table(path, labels=None):
    """({name: group}, {name: sample}) from a table file: spectrum name,
    group and an optional third column, the sample. Excel: the sheet named
    'Groups' if there is one, else the first sheet. Text: like
    read_group_table; the sample column needs a tab, semicolon or comma
    between the columns (with spaces only, everything after the name is
    the group)."""
    groups, samples = {}, {}
    if path.lower().endswith(('.xlsx', '.xlsm', '.xls')):
        import pandas as pd
        book = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
        sheet = next((df for name, df in book.items() if str(name).strip().lower() == 'groups'),
                     next(iter(book.values())))
        if sheet.shape[1] < 2:
            raise ValueError("The table needs two columns: spectrum name and group.")
        rows = [[('' if (isinstance(c, float) or c is None or str(c) == 'nan') else str(c).strip())
                 for c in r] for r in sheet.itertuples(index=False)]
        if rows and rows[0][1].lower() in _HEADER_WORDS:
            rows = rows[1:]
        for r in rows:
            if r[0] and r[1]:
                groups[r[0]] = r[1]
                if len(r) > 2 and r[2]:
                    samples[r[0]] = r[2]
        return groups, samples
    with open(path, encoding='utf-8-sig', errors='replace') as fh:
        lines = fh.read().splitlines()
    known = {str(l).strip().lower(): str(l) for l in (labels or [])}
    first = True
    for line in lines:
        pair = _split_table_line(line, known)
        if not pair:
            continue
        name, rest = pair
        rest = rest.strip(_TABLE_SEPARATORS + '"\'')
        sep = next((c for c in ('\t', ';', ',') if c in rest), None)
        if sep is None:
            # the plain split may have cut "group<TAB>sample" already
            raw = line.rstrip('\r\n')
            sep_raw = next((c for c in ('\t', ';', ',') if c in raw), None)
            cells = ([c.strip().strip('"') for c in raw.split(sep_raw)] if sep_raw else [])
            cells = [c for c in cells if c]
            if not known and len(cells) >= 3:
                name, group, sample = cells[0], cells[1], cells[2]
            else:
                group, sample = rest, ''
        else:
            cells = [c.strip().strip('"') for c in rest.split(sep)]
            group = cells[0]
            sample = cells[1] if len(cells) > 1 else ''
        if first:
            first = False
            if group.strip().lower() in _HEADER_WORDS:
                continue
        if name and group:
            groups[name] = group
            if sample:
                samples[name] = sample
    if not groups:
        raise ValueError("The table needs two columns: spectrum name and group.")
    return groups, samples


GROUP_TABLE_SUFFIXES = ('_groups.csv', '_groups.txt', '_groups.xlsx')


def find_group_table(spectra):
    """A group table that belongs to the spectra's own data file(s): a sheet
    'Groups' in the Excel workbook they were imported from, or a file
    '<data file name>_groups.csv / .txt / .xlsx' next to it. Returns the
    path or None."""
    import os
    seen = []
    for sp in spectra:
        path = (sp.get('metadata') or {}).get('file_path')
        if path and path not in seen:
            seen.append(path)
    for path in seen:
        stem, ext = os.path.splitext(path)
        for suffix in GROUP_TABLE_SUFFIXES:
            if os.path.isfile(stem + suffix):
                return stem + suffix
        if ext.lower() in ('.xlsx', '.xlsm') and os.path.isfile(path):
            try:
                import openpyxl
                book = openpyxl.load_workbook(path, read_only=True)
                names = [n.strip().lower() for n in book.sheetnames]
                book.close()
                if 'groups' in names:
                    return path
            except Exception:
                continue
    return None


def _name_key(name):
    """Loose key of a spectrum name: case, spaces and punctuation ignored
    (the importer turns e.g. "cell1 [px01]" into "cell1__px01_")."""
    import re
    return re.sub(r'[^0-9a-z]+', '_', str(name).strip().lower()).strip('_')


def groups_from_own_table(spectra, labels, table_path, mapping):
    """Like groups_from_table, for the group table that belongs to the
    spectra's own data file (see find_group_table): there the table names
    the spectra by their column name in that file ("control_01"), while in
    the window they are called "<file> : control_01". So, after the full
    name, the part after " : " is matched too -- only for the spectra that
    came from that data file."""
    import os
    result = groups_from_table(labels, mapping)
    by_key = {}
    for k, v in mapping.items():
        by_key.setdefault(_name_key(k), str(v).strip())
    t_stem = os.path.splitext(os.path.abspath(table_path))[0]
    for i, (sp, label) in enumerate(zip(spectra, labels)):
        if result[i]:
            continue
        fp = (sp.get('metadata') or {}).get('file_path')
        if not fp:
            continue
        d_stem = os.path.splitext(os.path.abspath(fp))[0]
        if t_stem not in (d_stem, d_stem + '_groups'):
            continue
        names = [label, (sp.get('metadata') or {}).get('original_label') or '']
        for name in names:
            short = str(name).rsplit(' : ', 1)[-1]
            hit = by_key.get(_name_key(short))
            if hit:
                result[i] = hit
                break
    return result


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
    # the other one-band values (group_values.py), default options
    from src.modules.visualization_analysis import group_values as gv
    if kind in gv.ONE_BAND:
        vals, _ = gv.compute_values([spectrum], ['g'], {'kind': kind, 'x0': x0,
                                                        'range_a': range_a})
        return float(vals[0])
    raise ValueError(f"unknown value kind {kind!r}")


def spectrum_values(spectra, kind, **kwargs):
    return np.array([spectrum_value(s, kind, **kwargs) for s in spectra], dtype=float)


def collect(groups, values, order=None):
    """{group: array of finite values}, groups in order of first appearance
    (or in `order` first, see ordered_names); spectra without a group or
    with a NaN value are left out."""
    out = {}
    for g, v in zip(groups, values):
        if g == NO_GROUP or not np.isfinite(v):
            continue
        out.setdefault(g, []).append(float(v))
    return {g: np.array(out[g]) for g in ordered_names(list(out), order)}


def ordered_names(names, order=None):
    """The group names in `order` first (e.g. the order of the rows of the
    group table they were read from: control, low dose, high dose), then the
    others in their given order (first appearance)."""
    names = list(dict.fromkeys(names))
    order = [g for g in dict.fromkeys(order or []) if g in names]
    return order + [g for g in names if g not in order]


def table_group_order(mapping):
    """The order of the groups in a group table (name -> group, in the
    table's row order)."""
    return [g for g in dict.fromkeys(str(v).strip() for v in mapping.values()) if g]


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
