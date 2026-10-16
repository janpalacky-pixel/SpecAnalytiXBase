# src/modules/visualization_analysis/group_spectra.py
"""Group Statistics, whole-spectrum comparison (Qt-free).

Instead of one value per spectrum, the groups are compared at every point
along x: the mean +/- SD (or 95 % CI) spectrum of each group, a test at each
point (the same family as the test chosen in the window), and the p-values
corrected for the many points (false discovery rate, Benjamini-Hochberg,
or Holm). Adjacent points are strongly correlated, so the result is read as
*regions* of x where the groups differ, not as single points.

Spectra on different x-axes are interpolated onto one common grid: the
points of the spectrum with the fewest points inside the common range (so
no detail is invented). Spectra that do not cover the range are left out.
"""
import math

import numpy as np
from scipy import stats

from src.modules.utils.spectra_validation import axes_match
from src.modules.visualization_analysis import group_statistics as gs

NORMALIZATIONS = {
    'none': "None",
    'band': "Divide by the maximum in a band",
    'area': "Unit area",
    'snv': "SNV",
}
CORRECTIONS = {
    'fdr': "FDR (Benjamini–Hochberg)",
    'holm': "Holm (strict)",
}
BANDS = {'sd': "mean ± SD", 'ci': "mean ± 95 % CI"}
N_PERMUTATIONS = 2000


def _finite_sorted(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    good = np.isfinite(x) & np.isfinite(y)
    order = np.argsort(x[good])
    return x[good][order], y[good][order]


def common_range(spectra):
    """(lo, hi) covered by every spectrum, or None."""
    xs = [_finite_sorted(s['x_scale'], s['y_scale'])[0] for s in spectra]
    xs = [x for x in xs if len(x) >= 2]
    if len(xs) != len(spectra) or not xs:
        return None
    lo, hi = max(x[0] for x in xs), min(x[-1] for x in xs)
    return (lo, hi) if hi > lo else None


def spectra_matrix(spectra, rng=None):
    """(x, Y, same_axis): every spectrum on one grid within rng (default:
    the common range). Raises ValueError if there is no common range."""
    xys = [_finite_sorted(s['x_scale'], s['y_scale']) for s in spectra]
    common = common_range(spectra)
    if common is None:
        raise ValueError("The spectra have no x-range in common.")
    lo, hi = common
    if rng is not None:
        lo, hi = max(lo, min(rng)), min(hi, max(rng))
        if hi <= lo:
            raise ValueError("The chosen range is outside the x-range all spectra share.")
    same = all(len(x) == len(xys[0][0]) and axes_match(xys[0][0], x) for x, _ in xys[1:])
    if same:
        x0 = xys[0][0]
        m = (x0 >= lo) & (x0 <= hi)
        return x0[m], np.vstack([y[m] for _, y in xys]), True
    counts = [np.sum((x >= lo) & (x <= hi)) for x, _ in xys]
    x_ref = xys[int(np.argmin(counts))][0]
    grid = x_ref[(x_ref >= lo) & (x_ref <= hi)]
    return grid, np.vstack([np.interp(grid, x, y) for x, y in xys]), False


def normalize(x, Y, mode='none', band=None):
    """Each row (spectrum) normalized; rows that cannot be normalized
    (zero / no band point) become NaN."""
    Y = np.array(Y, float)
    with np.errstate(divide='ignore', invalid='ignore'):
        if mode == 'band':
            lo, hi = min(band), max(band)
            m = (x >= lo) & (x <= hi)
            if not np.any(m):
                raise ValueError("The band contains no points of the spectra.")
            d = Y[:, m].max(axis=1)
        elif mode == 'area':
            d = np.trapezoid(Y, x, axis=1) if hasattr(np, 'trapezoid') else np.trapz(Y, x, axis=1)
        elif mode == 'snv':
            mu = Y.mean(axis=1, keepdims=True)
            sd = Y.std(axis=1, ddof=1, keepdims=True)
            out = (Y - mu) / sd
            out[~np.isfinite(out)] = np.nan
            return out
        else:
            return Y
        out = Y / d[:, None]
    out[~np.isfinite(out)] = np.nan
    return out


def adjust(p, how='fdr'):
    """Benjamini-Hochberg q-values or Holm-adjusted p; NaN counts as 1."""
    p = np.where(np.isfinite(p), p, 1.0)
    m = len(p)
    if m == 0:
        return p
    if how == 'holm':
        return gs.holm(p)
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(q, 1.0)
    return out


def _welch_anova_columns(mats):
    n = np.array([len(M) for M in mats], float)[:, None]
    m = np.vstack([M.mean(axis=0) for M in mats])
    var = np.vstack([M.var(axis=0, ddof=1) for M in mats])
    k = len(mats)
    with np.errstate(divide='ignore', invalid='ignore'):
        w = n / var
        W = w.sum(axis=0)
        mw = (w * m).sum(axis=0) / W
        a = (w * (m - mw) ** 2).sum(axis=0) / (k - 1)
        tmp = (((1 - w / W) ** 2) / (n - 1)).sum(axis=0)
        b = 1 + 2 * (k - 2) / (k ** 2 - 1) * tmp
        F = a / b
        df2 = (k ** 2 - 1) / (3 * tmp)
        p = stats.f.sf(F, k - 1, df2)
    return p


def _f_columns(mats):
    allv = np.vstack(mats)
    grand = allv.mean(axis=0)
    ssb = sum(len(M) * (M.mean(axis=0) - grand) ** 2 for M in mats)
    ssw = sum(((M - M.mean(axis=0)) ** 2).sum(axis=0) for M in mats)
    dfb, dfw = len(mats) - 1, len(allv) - len(mats)
    with np.errstate(divide='ignore', invalid='ignore'):
        return (ssb / dfb) / (ssw / dfw)


def permutations_for(n_spectra, n_points, full):
    """Fewer permutations for very large data (e.g. every pixel of a big map),
    so that the comparison stays fast (a few seconds): the full number up to
    10 million numbers (spectra x points), 1 999 up to 50 million, 999 above.
    Fixed by the size (not by the time taken), so the result is the same on
    every computer."""
    size = n_spectra * n_points
    if size <= 1e7:
        return full
    if size <= 5e7:
        return min(full, 1999)
    return min(full, 999)


def _permuted_group_sums(Yc, labels, k, n_perm, seed=0, batch=64):
    """Group sums (k x points) for n_perm random relabellings, several at a
    time as one matrix product (fast, multithreaded). The relabellings are the
    same sequence as drawing rng.permutation(labels) one after another."""
    rng = np.random.default_rng(seed)
    N = len(Yc)
    cols = np.arange(N)
    done = 0
    while done < n_perm:
        b = min(batch, n_perm - done)
        H = np.zeros((b * k, N))
        for j in range(b):
            H[j * k + rng.permutation(labels), cols] = 1.0
        yield (H @ Yc).reshape(b, k, -1)
        done += b


def _stat_from_sums(sums, sizes, sst_col):
    """Per point: |difference of means| (2 groups) or the ANOVA F, from the
    group sums of the centred data (sums: (..., k, points))."""
    n = np.asarray(sizes, float)[:, None]
    if len(sizes) == 2:
        return np.abs(sums[..., 0, :] / n[0] - sums[..., 1, :] / n[1])
    k, N = len(sizes), float(np.sum(sizes))
    ssb = (sums ** 2 / n).sum(axis=-2)
    with np.errstate(divide='ignore', invalid='ignore'):
        return (ssb / (k - 1)) / ((sst_col - ssb) / (N - k))


def _permutation_columns(mats, n_perm=N_PERMUTATIONS, seed=0):
    """Permutation p at every point: |difference of means| (2 groups) or F."""
    Y = np.vstack(mats)
    sizes = [len(M) for M in mats]
    k = len(mats)
    labels = np.repeat(np.arange(k), sizes)
    Yc = Y - Y.mean(axis=0)
    sst_col = (Yc ** 2).sum(axis=0)
    obs_sums = np.stack([Yc[labels == g].sum(axis=0) for g in range(k)])
    obs = _stat_from_sums(obs_sums, sizes, sst_col)
    count = np.zeros(Y.shape[1])
    for S in _permuted_group_sums(Yc, labels, k, n_perm, seed):
        count += (_stat_from_sums(S, sizes, sst_col) >= obs - 1e-12).sum(axis=0)
    return (count + 1) / (n_perm + 1)


def pointwise_p(mats, method='parametric', paired=None):
    """(p at every point, name of the test). mats: one (n_g x points)
    matrix per group; paired: (A, B) matrices of the same samples."""
    if method in ('paired_t', 'wilcoxon'):
        A, B = paired
        if len(A) < 2:
            raise ValueError("A paired comparison needs at least 2 samples measured in both "
                             "groups (the same name in the Sample column).")
        if method == 'paired_t':
            with np.errstate(divide='ignore', invalid='ignore'):
                return stats.ttest_rel(A, B, axis=0).pvalue, "Paired t-test"
        p = np.full(A.shape[1], np.nan)
        for j in range(A.shape[1]):
            d = A[:, j] - B[:, j]
            if np.any(d != 0):
                p[j] = stats.wilcoxon(A[:, j], B[:, j]).pvalue
        return p, "Wilcoxon signed-rank test"
    k = len(mats)
    with np.errstate(divide='ignore', invalid='ignore'):
        if method == 'permutation':
            n_perm = permutations_for(sum(len(M) for M in mats), mats[0].shape[1],
                                      N_PERMUTATIONS)
            name = ("Permutation test" if n_perm == N_PERMUTATIONS
                    else f"Permutation test ({n_perm} permutations)")
            return _permutation_columns(mats, n_perm), name
        if method in ('nonparametric', 'dunn'):
            if k == 2:
                return (stats.mannwhitneyu(mats[0], mats[1], axis=0).pvalue,
                        "Mann–Whitney U test")
            p = np.full(mats[0].shape[1], np.nan)
            for j in range(len(p)):
                cols = [M[:, j] for M in mats]
                if np.ptp(np.concatenate(cols)) > 0:
                    p[j] = stats.kruskal(*cols).pvalue
            return p, "Kruskal–Wallis test"
        if k == 2:
            return stats.ttest_ind(mats[0], mats[1], equal_var=False, axis=0).pvalue, "Welch t-test"
        if method == 'welch_gh':
            return _welch_anova_columns(mats), "Welch ANOVA"
        F = _f_columns(mats)
        allv = sum(len(M) for M in mats)
        return stats.f.sf(F, k - 1, allv - k), "One-way ANOVA"


N_PERMANOVA = 9999


def permanova(mats, n_perm=N_PERMANOVA, seed=0):
    """PERMANOVA (Anderson 2001) on whole spectra with the Euclidean
    distance: pseudo-F = [SS_between / (k - 1)] / [SS_within / (N - k)],
    p = (count of permuted F >= observed + 1) / (n_perm + 1).
    One overall answer to "do the spectra of the groups differ?". With the
    Euclidean distance SS_between comes from the group sums, so the
    permutations run as matrix products. Returns (F, p)."""
    Y = np.vstack(mats)
    sizes = np.array([len(M) for M in mats])
    k, N = len(mats), len(Y)
    if k < 2 or N <= k:
        return np.nan, np.nan
    labels = np.repeat(np.arange(k), sizes)
    Yc = Y - Y.mean(axis=0)
    sst = float((Yc ** 2).sum())

    def f_of(sums):
        ssb = (np.asarray(sums) ** 2).sum(axis=-1) / sizes      # (..., k)
        ssb = ssb.sum(axis=-1)
        ssw = sst - ssb
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.where(ssw > 0, (ssb / (k - 1)) / (ssw / (N - k)), np.inf)

    f_obs = float(f_of(np.stack([Yc[labels == g].sum(axis=0) for g in range(k)])))
    count = 0
    for S in _permuted_group_sums(Yc, labels, k, n_perm, seed):
        count += int((f_of(S) >= f_obs - 1e-12).sum())
    return f_obs, (count + 1) / (n_perm + 1)


def significant_ranges(x, q, alpha=0.05):
    """Contiguous runs of points with q < alpha: [(x_from, x_to, n_points,
    x of the smallest q)]."""
    sig = np.asarray(q) < alpha
    out, i = [], 0
    while i < len(sig):
        if sig[i]:
            j = i
            while j + 1 < len(sig) and sig[j + 1]:
                j += 1
            k = i + int(np.argmin(q[i:j + 1]))
            out.append((float(x[i]), float(x[j]), j - i + 1, float(x[k])))
            i = j + 1
        else:
            i += 1
    return out


def _average_per_sample(Y, groups, samples):
    rows, g_out, s_out, order = {}, [], [], []
    for i, (g, s) in enumerate(zip(groups, samples)):
        key = (g, s if s else f"\0{i}")
        if key not in rows:
            rows[key] = []
            order.append(key)
        rows[key].append(Y[i])
    M = np.vstack([np.nanmean(rows[k], axis=0) for k in order])
    return (M, [k[0] for k in order], [k[1] if not k[1].startswith("\0") else '' for k in order])


def compare_spectra(spectra, groups, samples=None, method='parametric', per_sample=False,
                    normalization='none', band=None, rng=None, correction='fdr',
                    alpha=0.05):
    """Everything the Spectra tab shows. Returns a dict: x, names, mean, sd,
    ci (half-width), n, p, q, ranges, test, notes, same_axis, unit ('spectra'
    or 'samples')."""
    samples = list(samples) if samples is not None else [''] * len(spectra)
    use = [i for i, g in enumerate(groups) if g]
    if not use:
        raise ValueError("Give the spectra their groups first.")
    sp = [spectra[i] for i in use]
    g_used = [groups[i] for i in use]
    s_used = [samples[i] for i in use]
    # the band of 'Divide by the maximum in a band' may lie outside the compared
    # range (e.g. a reference band elsewhere): normalize on the whole common range
    x_all, Y_all, same = spectra_matrix(sp, None)
    if rng is not None:
        keep_x = (x_all >= min(rng)) & (x_all <= max(rng))
    else:
        keep_x = np.ones(len(x_all), dtype=bool)
    if np.sum(keep_x) < 2:
        raise ValueError("The range contains fewer than two points of the spectra.")
    if normalization == 'band':
        Y = normalize(x_all, Y_all, 'band', band)[:, keep_x]
        x = x_all[keep_x]
    else:
        x = x_all[keep_x]
        Y = normalize(x, Y_all[:, keep_x], normalization, band)
    notes = []
    bad = ~np.all(np.isfinite(Y), axis=1)
    if np.any(bad):
        notes.append(f"{int(bad.sum())} spectr{'um' if bad.sum() == 1 else 'a'} could not be "
                     f"normalized and {'was' if bad.sum() == 1 else 'were'} left out.")
        keep = ~bad
        Y = Y[keep]
        g_used = [g for g, k in zip(g_used, keep) if k]
        s_used = [s for s, k in zip(s_used, keep) if k]
    unit = 'spectra'
    if per_sample:
        Y, g_used, s_used = _average_per_sample(Y, g_used, s_used)
        unit = 'samples'
    names = list(dict.fromkeys(g_used))
    mats = {g: Y[[i for i, gg in enumerate(g_used) if gg == g]] for g in names}
    small = [g for g in names if len(mats[g]) < 2]
    if small:
        notes.append("Left out (fewer than 2 " + unit + "): " + ", ".join(small) + ".")
        names = [g for g in names if g not in small]
    if len(names) < 2:
        raise ValueError("At least two groups with 2 or more " + unit + " are needed.")
    paired = None
    if method in ('paired_t', 'wilcoxon'):
        if len(names) != 2:
            raise ValueError("A paired test compares exactly two groups.")
        a, b = names
        per = {}
        for row, g, s in zip(Y, g_used, s_used):
            if s and g in (a, b):
                per.setdefault(s, {}).setdefault(g, []).append(row)
        both = [s for s, d in per.items() if a in d and b in d]
        paired = (np.vstack([np.mean(per[s][a], axis=0) for s in both]) if both else np.empty((0, len(x))),
                  np.vstack([np.mean(per[s][b], axis=0) for s in both]) if both else np.empty((0, len(x))))
    p, test = pointwise_p([mats[g] for g in names], method, paired)
    n_perm = permutations_for(sum(n for n in (len(mats[g]) for g in names)), len(x),
                              N_PERMANOVA)
    overall = (permanova([mats[g] for g in names], n_perm) + (n_perm,) if paired is None
               else (np.nan, np.nan, 0))
    q = adjust(p, correction)
    mean = {g: mats[g].mean(axis=0) for g in names}
    sd = {g: mats[g].std(axis=0, ddof=1) for g in names}
    n = {g: len(mats[g]) for g in names}
    ci = {g: stats.t.ppf(0.975, n[g] - 1) * sd[g] / math.sqrt(n[g]) for g in names}
    if not same:
        notes.append("The spectra have different x-axes: they were interpolated onto the "
                      f"points of the coarsest one ({len(x)} points).")
    return {'x': x, 'names': names, 'mean': mean, 'sd': sd, 'ci': ci, 'n': n, 'p': p, 'q': q,
            'ranges': significant_ranges(x, q, alpha), 'test': test, 'notes': notes,
            'same_axis': same, 'unit': unit, 'correction': correction, 'alpha': alpha,
            'n_pairs': len(paired[0]) if paired is not None else None,
            'normalization': normalization, 'permanova': overall}


def overall_text(result):
    """The PERMANOVA sentence (empty for the paired tests)."""
    F, p, n_perm = (tuple(result.get('permanova', (np.nan, np.nan))) + (N_PERMANOVA,))[:3]
    if not np.isfinite(p):
        return ''
    smallest = 1 / (n_perm + 1)
    ptxt = (f"p = {smallest:.4g} (the smallest possible with {n_perm + 1} permutations)"
            if p <= smallest * 1.0001 else f"p = {p:.4f}")
    return (f"Whole spectrum (PERMANOVA, Euclidean distance): pseudo-F = {F:.3g}, {ptxt}.")


def ranges_text(result, max_listed=6):
    """Plain sentence about where the groups differ. Regions of 3 or more
    points are listed (the widest first if there are many); shorter ones are
    only counted, because an isolated point is often a chance finding."""
    corr = 'FDR q' if result['correction'] == 'fdr' else 'Holm p'
    how = f"{result['test']} at every point, {corr} < {result['alpha']:g}"
    ranges = result['ranges']
    if not ranges:
        text = f"No region where the groups differ significantly ({how})."
        if result['test'] in ("Wilcoxon signed-rank test", "Mann–Whitney U test",
                              "Kruskal–Wallis test", "Permutation test"):
            text += (" With few spectra, rank and permutation tests cannot give very small "
                     "p-values, and after the correction for the many points they may find "
                     "nothing — try a narrower range or the t-test / ANOVA.")
        return text
    wide = [r for r in ranges if r[2] >= 3]
    short = len(ranges) - len(wide)
    x = result['x']
    covered = sum(r[2] for r in ranges) / len(x) * 100
    if len(wide) > max_listed:
        wide = sorted(wide, key=lambda r: -r[2])[:max_listed]
        lead = (f"The groups differ significantly ({how}) in {len(ranges)} regions covering "
                f"{covered:.0f} % of the compared range; the widest: ")
    else:
        lead = f"The groups differ significantly ({how}) in: "
    wide = sorted(wide, key=lambda r: r[0])
    parts = [f"{a:g}–{b:g} (strongest at {m:g})" for a, b, k, m in wide]
    text = lead + ("; ".join(parts) if parts else "only isolated points")
    if short and parts:
        text += (f"; plus {short} shorter one{'s' if short != 1 else ''} (1–2 points, "
                 f"often chance findings)")
    text += "."
    if covered > 50 and result.get('normalization') in ('area', 'snv'):
        text += (" Most of the spectrum differs: with Unit area or SNV a change of one band "
                 "shifts all other points too — dividing by a band that does not change is "
                 "often clearer.")
    return text


def export_table(result):
    """pandas DataFrame: x, mean/SD/n per group, p, adjusted p."""
    import pandas as pd
    cols = {'x': result['x']}
    for g in result['names']:
        cols[f'mean {g}'] = result['mean'][g]
        cols[f'SD {g}'] = result['sd'][g]
        cols[f'n {g}'] = np.full(len(result['x']), result['n'][g])
    cols['p'] = result['p']
    cols['q (FDR)' if result['correction'] == 'fdr' else 'p (Holm)'] = result['q']
    return pd.DataFrame(cols)
