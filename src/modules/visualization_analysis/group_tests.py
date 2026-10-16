# src/modules/visualization_analysis/group_tests.py
"""More specific tests and checks for Group Statistics (Qt-free). The
original two choices (group_statistics.compare: Welch t / one-way ANOVA,
Mann-Whitney / Kruskal-Wallis) are unchanged; this module adds:

- Welch ANOVA + Games-Howell pairs (groups with different spread);
- Kruskal-Wallis + Dunn pairs (the standard post-hoc for Kruskal-Wallis);
- a permutation test (no distribution assumed);
- paired tests (paired t, Wilcoxon signed-rank) for the same samples
  measured in two groups (e.g. before / after);
- replicates: averaging the spectra of one sample, so the test uses one
  value per independent sample, and a warning when a group's spectra come
  from very few samples (pseudoreplication);
- confidence intervals (difference of means, Hedges' g), assumption checks
  (Shapiro-Wilk, Brown-Forsythe), outliers (Tukey fences) and a results
  sentence for a paper.

compare_with(data, method) returns the same dict as group_statistics.compare
plus extra keys; for 'parametric' / 'nonparametric' it calls compare()
itself, so those results are exactly as before.
"""

import math

import numpy as np
from scipy import stats

from src.modules.visualization_analysis import group_statistics as gs

METHODS = {
    'parametric': "Parametric: Welch t-test / one-way ANOVA",
    'nonparametric': "Non-parametric: Mann–Whitney U / Kruskal–Wallis",
    'welch_gh': "Unequal spread: Welch t-test / Welch ANOVA + Games–Howell",
    'dunn': "Non-parametric: Mann–Whitney U / Kruskal–Wallis + Dunn",
    'permutation': "Permutation test (no distribution assumed)",
    'paired_t': "Paired (same samples): paired t-test",
    'wilcoxon': "Paired (same samples): Wilcoxon signed-rank test",
}
PAIRED = ('paired_t', 'wilcoxon')
N_PERMUTATIONS = 10000
N_BOOTSTRAP = 2000


# --- replicates ----------------------------------------------------------------------

def sample_means(groups, samples, values):
    """(groups, samples, values) with one entry per (group, sample): the
    mean of that sample's finite values. Spectra without a sample stay
    single entries (each its own sample)."""
    out, order = {}, []
    for i, (g, s, v) in enumerate(zip(groups, samples, values)):
        if g == gs.NO_GROUP or not np.isfinite(v):
            continue
        key = (g, s if s else f"\0{i}")
        if key not in out:
            out[key] = []
            order.append(key)
        out[key].append(float(v))
    return ([k[0] for k in order], [k[1] if not k[1].startswith("\0") else '' for k in order],
            [float(np.mean(out[k])) for k in order])


def replicate_warnings(groups, sources, values=None, min_spectra=6):
    """Groups whose spectra come from at most two sources (samples or, if
    no sample is given, files / name roots) while there are min_spectra or
    more of them: the spectra are then not independent replicates and the
    p-values are too small. Returns a list of (group, n_spectra, n_sources)."""
    per = {}
    for i, (g, src) in enumerate(zip(groups, sources)):
        if g == gs.NO_GROUP or (values is not None and not np.isfinite(values[i])):
            continue
        n, srcs = per.get(g, (0, set()))
        srcs.add(src)
        per[g] = (n + 1, srcs)
    return [(g, n, len(srcs)) for g, (n, srcs) in per.items()
            if n >= min_spectra and len(srcs) <= 2]


def shared_sample_warnings(groups, samples, values=None):
    """Groups in which the Sample column gives several spectra the same
    sample (e.g. 15 pixels of one cell): those spectra are not independent
    replicates, however many samples there are. Returns (group, n_spectra,
    n_samples) for such groups; spectra without a sample are not counted."""
    per = {}
    for i, (g, smp) in enumerate(zip(groups, samples)):
        if g == gs.NO_GROUP or not smp or (values is not None and not np.isfinite(values[i])):
            continue
        n, names = per.get(g, (0, set()))
        names.add(smp)
        per[g] = (n + 1, names)
    return [(g, n, len(names)) for g, (n, names) in per.items() if len(names) < n]



def repeated_sample_names(groups, samples, values=None):
    """Which sample names are given to several spectra of one group: an
    ordered {group: [(sample, n_spectra), ...]} with only the names used more
    than once (order of first appearance). Same rule as
    shared_sample_warnings(), which only counts them."""
    per = {}
    for i, (g, smp) in enumerate(zip(groups, samples)):
        if g == gs.NO_GROUP or not smp or (values is not None and not np.isfinite(values[i])):
            continue
        counts = per.setdefault(g, {})
        counts[smp] = counts.get(smp, 0) + 1
    out = {}
    for g, counts in per.items():
        rep = [(smp, n) for smp, n in counts.items() if n > 1]
        if rep:
            out[g] = rep
    return out

# --- confidence intervals, checks ---------------------------------------------------------

def mean_difference_ci(a, b, level=0.95):
    """Difference of means a - b with its Welch confidence interval."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return np.nan, np.nan, np.nan
    va, vb = np.var(a, ddof=1) / len(a), np.var(b, ddof=1) / len(b)
    se = math.sqrt(va + vb)
    d = float(np.mean(a) - np.mean(b))
    if se == 0:
        return d, d, d
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    t = stats.t.ppf(0.5 + level / 2, df)
    return d, d - t * se, d + t * se


MIN_BOOTSTRAP_N = 10


def hedges_g_ci(a, b, n_boot=N_BOOTSTRAP, level=0.95, seed=0):
    """Hedges' g with a percentile bootstrap confidence interval (each group
    resampled with replacement). With fewer than MIN_BOOTSTRAP_N values in a
    group the bootstrap is meaningless (resampling 3 values often repeats one
    value, the SD collapses and g explodes), so the usual large-sample
    approximation is used instead: SE = sqrt((na + nb) / (na nb) + g^2 /
    (2 (na + nb))) (Hedges & Olkin 1985)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    g = gs.hedges_g(a, b)
    if not np.isfinite(g):
        return g, np.nan, np.nan
    if min(len(a), len(b)) < MIN_BOOTSTRAP_N:
        na, nb = len(a), len(b)
        se = math.sqrt((na + nb) / (na * nb) + g ** 2 / (2 * (na + nb)))
        z = stats.norm.ppf(0.5 + level / 2)
        return g, float(g - z * se), float(g + z * se)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        gb = gs.hedges_g(rng.choice(a, len(a)), rng.choice(b, len(b)))
        if np.isfinite(gb):
            boots.append(gb)
    if len(boots) < n_boot // 2:
        return g, np.nan, np.nan
    lo, hi = np.percentile(boots, [50 * (1 - level), 50 * (1 + level)])
    return g, float(lo), float(hi)


def assumption_checks(data):
    """Shapiro-Wilk per group (3 <= n <= 5000) and Brown-Forsythe (Levene
    with medians) across groups, with plain advice."""
    out = {'normality': [], 'equal_spread_p': np.nan, 'advice': []}
    for g, v in data.items():
        p = np.nan
        if 3 <= len(v) <= 5000 and np.ptp(v) > 0:
            p = float(stats.shapiro(v).pvalue)
        out['normality'].append((g, len(v), p))
    used = [v for v in data.values() if len(v) >= 2]
    if len(used) >= 2 and all(np.ptp(v) > 0 for v in used):
        out['equal_spread_p'] = float(stats.levene(*used, center='median').pvalue)
    skewed = [g for g, n, p in out['normality'] if np.isfinite(p) and p < 0.05]
    small = [g for g, n, p in out['normality'] if n < 8]
    if skewed:
        out['advice'].append("Not bell-shaped (Shapiro–Wilk p < 0.05): " + ", ".join(skewed)
                             + " — a non-parametric or permutation test is safer.")
    if np.isfinite(out['equal_spread_p']) and out['equal_spread_p'] < 0.05:
        out['advice'].append("The spread differs between the groups (Brown–Forsythe p < 0.05) "
                             "— with three or more groups prefer Welch ANOVA + Games–Howell.")
    if small:
        out['advice'].append("Fewer than 8 values in " + ", ".join(small)
                             + ": these checks have little power there; do not read a large "
                               "p as proof of normality.")
    return out


def outliers(values):
    """Indices of values outside Tukey's fences (1.5 x IQR beyond the quartiles)."""
    v = np.asarray(values, float)
    if len(v) < 4:
        return []
    q1, q3 = np.percentile(v, [25, 75])
    iqr = q3 - q1
    return [i for i, x in enumerate(v) if x < q1 - 1.5 * iqr or x > q3 + 1.5 * iqr]


# --- tests -----------------------------------------------------------------------------

def welch_anova(values):
    """Welch's one-way ANOVA: (F, df1, df2, p)."""
    k = len(values)
    n = np.array([len(v) for v in values], float)
    m = np.array([np.mean(v) for v in values])
    var = np.array([np.var(v, ddof=1) for v in values])
    if np.any(var == 0):
        return np.nan, np.nan, np.nan, np.nan
    w = n / var
    W = w.sum()
    mw = float((w * m).sum() / W)
    a = float((w * (m - mw) ** 2).sum() / (k - 1))
    tmp = float((((1 - w / W) ** 2) / (n - 1)).sum())
    b = 1 + 2 * (k - 2) / (k ** 2 - 1) * tmp
    F = a / b
    df1, df2 = k - 1, (k ** 2 - 1) / (3 * tmp)
    return F, df1, df2, float(stats.f.sf(F, df1, df2))


def games_howell(values, names, level=0.95):
    """Games-Howell pairs: difference of means, CI, t, df, p (already
    adjusted for the number of groups via the studentized range)."""
    k = len(values)
    out = []
    for i in range(k):
        for j in range(i + 1, k):
            a, b = values[i], values[j]
            va, vb = np.var(a, ddof=1) / len(a), np.var(b, ddof=1) / len(b)
            se = math.sqrt(va + vb)
            d = float(np.mean(a) - np.mean(b))
            df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1)) if se else np.nan
            t = d / se if se else np.nan
            p = float(stats.studentized_range.sf(abs(t) * math.sqrt(2), k, df)) if se else np.nan
            qc = stats.studentized_range.ppf(level, k, df) / math.sqrt(2) if se else np.nan
            out.append({'a': names[i], 'b': names[j], 'difference': d, 'statistic': t,
                        'df': df, 'p': p, 'p_holm': p, 'ci': (d - qc * se, d + qc * se),
                        'effect': gs.hedges_g(a, b)})
    return out


def dunn(values, names):
    """Dunn's test after Kruskal-Wallis: z for every pair from the mean ranks
    (tie-corrected), p two-sided, Holm-adjusted."""
    allv = np.concatenate(values)
    ranks = stats.rankdata(allv)
    N = len(allv)
    _, counts = np.unique(allv, return_counts=True)
    ties = float(np.sum(counts ** 3 - counts)) / (12 * (N - 1))
    pos, mean_ranks = 0, []
    for v in values:
        mean_ranks.append(float(np.mean(ranks[pos:pos + len(v)])))
        pos += len(v)
    out = []
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            se = math.sqrt((N * (N + 1) / 12 - ties) * (1 / len(values[i]) + 1 / len(values[j])))
            z = (mean_ranks[i] - mean_ranks[j]) / se if se else np.nan
            out.append({'a': names[i], 'b': names[j],
                        'difference': float(np.median(values[i]) - np.median(values[j])),
                        'statistic': z, 'p': float(2 * stats.norm.sf(abs(z))) if se else np.nan,
                        'effect': gs.rank_biserial(values[i], values[j])})
    for pr, ph in zip(out, gs.holm([pr['p'] for pr in out])):
        pr['p_holm'] = float(ph)
    return out


def _f_stat(values):
    allv = np.concatenate(values)
    grand = allv.mean()
    ssb = sum(len(v) * (v.mean() - grand) ** 2 for v in values)
    ssw = sum(((v - v.mean()) ** 2).sum() for v in values)
    dfb, dfw = len(values) - 1, len(allv) - len(values)
    return (ssb / dfb) / (ssw / dfw) if ssw > 0 else np.inf


def permutation_p(values, n_perm=N_PERMUTATIONS, seed=0):
    """Permutation test: two groups -> |difference of means|, more -> F.
    Two-sided p = (count of permuted statistics >= observed + 1) / (n + 1)."""
    rng = np.random.default_rng(seed)
    sizes = [len(v) for v in values]
    allv = np.concatenate(values)
    cuts = np.cumsum(sizes)[:-1]

    def stat(vals):
        if len(vals) == 2:
            return abs(vals[0].mean() - vals[1].mean())
        return _f_stat(vals)
    observed = stat(values)
    count = 0
    for _ in range(n_perm):
        perm = rng.permutation(allv)
        if stat(np.split(perm, cuts)) >= observed - 1e-12:
            count += 1
    return float(observed), (count + 1) / (n_perm + 1)


def paired_values(groups, samples, values, group_a, group_b):
    """Sample means of the samples measured in both groups: (samples, a, b)."""
    per = {}
    for g, s, v in zip(groups, samples, values):
        if s and g in (group_a, group_b) and np.isfinite(v):
            per.setdefault(s, {}).setdefault(g, []).append(float(v))
    keep = [s for s, d in per.items() if group_a in d and group_b in d]
    return (keep, np.array([np.mean(per[s][group_a]) for s in keep]),
            np.array([np.mean(per[s][group_b]) for s in keep]))



def unpaired_samples(groups, samples, values, group_a, group_b):
    """What a paired test of group_a and group_b leaves out (same rule as
    paired_values): sample names found in only one of the two groups, as
    ({name: group}, in order of first appearance), and the number of spectra
    of the two groups without a sample name. values may be None (all count)."""
    per, no_name = {}, 0
    for i, (g, s) in enumerate(zip(groups, samples)):
        if g not in (group_a, group_b):
            continue
        if values is not None and not np.isfinite(values[i]):
            continue
        if not s:
            no_name += 1
            continue
        per.setdefault(s, set()).add(g)
    only = {s: next(iter(gr)) for s, gr in per.items() if len(gr) == 1}
    return only, no_name

# --- one entry point ----------------------------------------------------------------------

def compare_with(data, method='parametric', paired=None):
    """The result dict of group_statistics.compare (test, statistic, p,
    effect_name, effect, groups, excluded, pairs, note, ...) for any METHODS
    key, plus extras: 'method', 'df', 'ci' (difference of means a - b, two
    groups), 'g_ci', 'checks', 'outliers', 'sentence'.
    paired: (samples, a_values, b_values) for the paired methods."""
    if method in ('parametric', 'nonparametric'):
        result = gs.compare(data, parametric=(method == 'parametric'))
    elif method in PAIRED:
        result = _paired(data, method, paired)
    else:
        result = _other(data, method)
    result['method'] = method
    used = {g: data[g] for g in result.get('groups', []) if g in data}
    result['checks'] = assumption_checks(used) if used else None
    result['outliers'] = {g: outliers(v) for g, v in used.items()}
    if len(used) == 2 and method not in PAIRED:
        a, b = list(used.values())
        result['ci'] = mean_difference_ci(a, b)
        result['g_ci'] = hedges_g_ci(a, b)
    result['sentence'] = results_sentence(result, data)
    return result


def _base(data):
    used = {g: v for g, v in data.items() if len(v) >= 2}
    excluded = [g for g, v in data.items() if len(v) < 2]
    return used, {'test': None, 'statistic': np.nan, 'p': np.nan, 'effect_name': '',
                  'effect': np.nan, 'groups': list(used), 'excluded': excluded, 'pairs': [],
                  'parametric': True, 'note': ''}


def _other(data, method):
    used, result = _base(data)
    if len(used) < 2:
        result['note'] = "At least two groups with two or more values each are needed."
        return result
    names, values = list(used), [np.asarray(used[g], float) for g in used]
    if method == 'welch_gh':
        if len(values) == 2:
            res = stats.ttest_ind(values[0], values[1], equal_var=False)
            d, lo, hi = mean_difference_ci(values[0], values[1])
            result.update(test="Welch t-test", statistic=float(res.statistic),
                          p=float(res.pvalue), effect_name="Hedges' g",
                          effect=gs.hedges_g(values[0], values[1]),
                          df=float(getattr(res, 'df', np.nan)))
        else:
            F, df1, df2, p = welch_anova(values)
            N = sum(len(v) for v in values)
            omega = df1 * (F - 1) / (df1 * (F - 1) + N) if np.isfinite(F) else np.nan
            result.update(test="Welch ANOVA", statistic=F, p=p, df=(df1, df2),
                          effect_name="omega squared (est.)", effect=max(omega, 0.0)
                          if np.isfinite(omega) else np.nan)
            result['pairs'] = games_howell(values, names)
            result['pair_test'] = "Games–Howell"
            result['pair_effect_name'] = "Hedges' g"
            result['pairs_adjusted_by'] = "Games–Howell"
    elif method == 'dunn':
        result['parametric'] = False
        if len(values) == 2:
            res = stats.mannwhitneyu(values[0], values[1], alternative='two-sided')
            result.update(test="Mann–Whitney U test", statistic=float(res.statistic),
                          p=float(res.pvalue), effect_name="rank-biserial r",
                          effect=gs.rank_biserial(values[0], values[1]))
        else:
            res = stats.kruskal(*values)
            n = sum(len(v) for v in values)
            result.update(test="Kruskal–Wallis test", statistic=float(res.statistic),
                          p=float(res.pvalue), effect_name="epsilon squared",
                          effect=float(res.statistic) / (n - 1), df=len(values) - 1)
            result['pairs'] = dunn(values, names)
            result['pair_test'] = "Dunn (Holm-corrected)"
            result['pair_effect_name'] = "rank-biserial r"
    elif method == 'permutation':
        stat, p = permutation_p(values)
        if len(values) == 2:
            result.update(test=f"Permutation test ({N_PERMUTATIONS} permutations, difference "
                               f"of means)", statistic=float(values[0].mean() - values[1].mean()),
                          p=p, effect_name="Hedges' g",
                          effect=gs.hedges_g(values[0], values[1]))
        else:
            result.update(test=f"Permutation test ({N_PERMUTATIONS} permutations, F)",
                          statistic=stat, p=p, effect_name="", effect=np.nan)
            pairs = []
            for i in range(len(values)):
                for j in range(i + 1, len(values)):
                    _, pp = permutation_p([values[i], values[j]], seed=1 + i * 31 + j)
                    pairs.append({'a': names[i], 'b': names[j],
                                  'difference': float(values[i].mean() - values[j].mean()),
                                  'statistic': float(values[i].mean() - values[j].mean()),
                                  'p': pp, 'effect': gs.hedges_g(values[i], values[j])})
            for pr, ph in zip(pairs, gs.holm([pr['p'] for pr in pairs])):
                pr['p_holm'] = float(ph)
            result['pairs'] = pairs
            result['pair_test'] = "permutation (Holm-corrected)"
            result['pair_effect_name'] = "Hedges' g"
    else:
        raise ValueError(f"unknown method {method!r}")
    return result


def _paired(data, method, paired):
    used, result = _base(data)
    result['parametric'] = method == 'paired_t'
    if len(data) != 2:
        result['note'] = ("A paired test compares exactly two groups (e.g. before / after); "
                          f"there are {len(data)}.")
        return result
    samples, a, b = paired if paired is not None else ([], np.array([]), np.array([]))
    if len(samples) < 3:
        result['note'] = ("A paired test needs at least 3 samples measured in both groups "
                          "(set the Sample column: the same sample name in both groups).")
        return result
    diff = a - b
    result['groups'] = list(data)
    result['n_pairs'] = len(samples)
    if method == 'paired_t':
        res = stats.ttest_rel(a, b)
        sd = np.std(diff, ddof=1)
        t = stats.t.ppf(0.975, len(diff) - 1)
        m = float(np.mean(diff))
        se = sd / math.sqrt(len(diff))
        result.update(test="Paired t-test", statistic=float(res.statistic), p=float(res.pvalue),
                      df=len(diff) - 1, effect_name="Cohen's dz",
                      effect=float(m / sd) if sd > 0 else np.nan,
                      ci=(m, m - t * se, m + t * se))
    else:
        res = stats.wilcoxon(a, b)
        nz = diff[diff != 0]
        r = stats.rankdata(np.abs(nz))
        rb = float((r[nz > 0].sum() - r[nz < 0].sum()) / r.sum()) if len(r) else np.nan
        result.update(test="Wilcoxon signed-rank test", statistic=float(res.statistic),
                      p=float(res.pvalue), effect_name="matched-pairs rank-biserial r",
                      effect=rb, median_difference=float(np.median(diff)))
    return result


def results_sentence(r, data):
    """One sentence for a paper, e.g. "Welch t-test: t(17.3) = 4.21,
    p = 0.0006, Hedges' g = 1.90 [0.80; 3.00]; n = 10 vs 10." """
    if not r or not r.get('test'):
        return ''
    ns = " vs ".join(str(len(data[g])) for g in r['groups'] if g in data)
    df = r.get('df')
    if isinstance(df, tuple):
        dft = f"({df[0]:.3g}, {df[1]:.3g})"
    elif df is not None and np.isfinite(df):
        dft = f"({df:.3g})"
    else:
        dft = ""
    symbol = {'Welch t-test': 't', 'Paired t-test': 't', 'One-way ANOVA': 'F',
              'Welch ANOVA': 'F', 'Mann–Whitney U test': 'U', 'Kruskal–Wallis test': 'H',
              'Wilcoxon signed-rank test': 'W'}.get(r['test'], 'statistic')
    text = f"{r['test']}: {symbol}{dft} = {r['statistic']:.3g}, {gs.p_text(r['p'])}"
    if r.get('effect_name') and np.isfinite(r.get('effect', np.nan)):
        text += f", {r['effect_name']} = {r['effect']:.2f}"
        gci = r.get('g_ci')
        if gci and r['effect_name'] == "Hedges' g" and np.isfinite(gci[1]):
            text += f" [95 % CI {gci[1]:.2f}; {gci[2]:.2f}]"
    ci = r.get('ci')
    if ci and np.isfinite(ci[1]):
        text += f"; difference of means {ci[0]:.4g} [95 % CI {ci[1]:.4g}; {ci[2]:.4g}]"
    if r.get('n_pairs'):
        text += f"; n = {r['n_pairs']} pairs."
    else:
        text += f"; n = {ns}."
    return text
