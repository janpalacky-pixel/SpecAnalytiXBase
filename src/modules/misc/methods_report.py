# src/modules/misc/methods_report.py
""""Methods" report for publications: a readable description of everything
that was done to the spectra, ready to adapt for a paper's Methods section,
plus a parameter table and a numbered reference list.

Source of truth: the Operations History chain
(IncrementalOperationsManager.operations_chain), up to the step that is
currently active -- i.e. exactly the processing that produced what is on
screen. Each record holds the operation type and the very settings dict the
operation ran with.

Qt-free; the dialog lives in src/views/dialogs/misc/methods_report_dialog.py.

Adding a new operation: write a describer (see _DESCRIBERS) returning a
_Description; anything without one still gets a generic sentence and all
its simple settings in the table, so nothing is ever silently left out.
"""

import re
import html
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Sequence, Tuple

SOFTWARE_URL = "https://github.com/janpalacky-pixel/SpecAnalytiXBase"

# ---------------------------------------------------------------------------
# References (cited in the order of first use)
# ---------------------------------------------------------------------------

REFERENCES: Dict[str, str] = {
    'als': "Eilers, P. H. C., & Boelens, H. F. M. (2005). Baseline correction with "
           "asymmetric least squares smoothing. Leiden University Medical Centre report.",
    'airpls': "Zhang, Z.-M., Chen, S., & Liang, Y.-Z. (2010). Baseline correction using "
              "adaptive iteratively reweighted penalized least squares. Analyst, 135(5), 1138–1146.",
    'arpls': "Baek, S.-J., Park, A., Ahn, Y.-J., & Choo, J. (2015). Baseline correction using "
             "asymmetrically reweighted penalized least squares smoothing. Analyst, 140(1), 250–257.",
    'iarpls': "Ye, J., Tian, Z., Wei, H., & Li, Y. (2020). Baseline correction method based on "
              "improved asymmetrically reweighted penalized least squares for the Raman spectrum. "
              "Applied Optics, 59(34), 10933–10943.",
    'aspls': "Zhang, F., Tang, X., Tong, A., Wang, B., Wang, J., Lv, Y., Tang, C., & Wang, J. (2020). "
             "Baseline correction for infrared spectra using adaptive smoothness parameter "
             "penalized least squares method. Spectroscopy Letters, 53(3), 222–233.",
    'drpls': "Xu, D., Liu, S., Cai, Y., & Yang, C. (2019). Baseline correction method based on "
             "doubly reweighted penalized least squares. Applied Optics, 58(14), 3913–3920.",
    'psalsa': "Oller-Moreno, S., Pardo, A., Jimenez-Soto, J. M., Samitier, J., & Marco, S. (2014). "
              "Adaptive asymmetric least squares baseline estimation for analytical instruments. "
              "2014 IEEE 11th International Multi-Conference on Systems, Signals & Devices (SSD14), 1–5.",
    'modpoly': "Lieber, C. A., & Mahadevan-Jansen, A. (2003). Automated method for subtraction of "
               "fluorescence from biological Raman spectra. Applied Spectroscopy, 57(11), 1363–1367.",
    'imodpoly': "Zhao, J., Lui, H., McLean, D. I., & Zeng, H. (2007). Automated autofluorescence "
                "background subtraction algorithm for biomedical Raman spectroscopy. "
                "Applied Spectroscopy, 61(11), 1225–1232.",
    'morphological': "Perez-Pueyo, R., Soneira, M. J., & Ruiz-Moreno, S. (2010). Morphology-based "
                     "automated baseline removal for Raman spectra of artistic pigments. "
                     "Applied Spectroscopy, 64(6), 595–600.",
    'mpls': "Li, Z., Zhan, D., Wang, J., Huang, J., Xu, Q., Zhang, Z., Zheng, Y., Liang, Y., & "
            "Wang, H. (2013). Morphological weighted penalized least squares for background "
            "correction. Analyst, 138(16), 4483–4492.",
    'mollification_koch': "Koch, M., Suhr, C., Roth, B., & Meinhardt-Wollweber, M. (2017). Iterative "
                          "morphological and mollifier-based baseline correction for Raman spectra. "
                          "Journal of Raman Spectroscopy, 48(2), 336–342.",
    'mollification_chen': "Chen, H., Xu, W., & Broderick, N. G. R. (2019). An adaptive and fully "
                          "automated baseline correction method for Raman spectroscopy based on "
                          "morphological operations and mollification. Applied Spectroscopy, 73(3), 284–293.",
    'mpspline': "Gonzalez-Vidal, J. J., Perez-Pueyo, R., & Soneira, M. J. (2017). Automatic "
                "morphology-based cubic p-spline fitting methodology for smoothing and "
                "baseline-removal of Raman spectra. Journal of Raman Spectroscopy, 48(6), 878–883.",
    'jbcd': "Liu, H., Zhang, Z., Liu, S., Yan, L., Liu, T., & Zhang, T. (2015). Joint "
            "baseline-correction and denoising for Raman spectra. Applied Spectroscopy, 69(9), 1013–1022.",
    'snip': "Ryan, C. G., Clayton, E., Griffin, W. L., Sie, S. H., & Cousens, D. R. (1988). SNIP, a "
            "statistics-sensitive background treatment for the quantitative analysis of PIXE "
            "spectra in geoscience applications. Nuclear Instruments and Methods in Physics "
            "Research B, 34(3), 396–402.",
    'savgol': "Savitzky, A., & Golay, M. J. E. (1964). Smoothing and differentiation of data by "
              "simplified least squares procedures. Analytical Chemistry, 36(8), 1627–1639.",
    'steinier': "Steinier, J., Termonia, Y., & Deltour, J. (1972). Comments on smoothing and "
                "differentiation of data by simplified least square procedure. Analytical "
                "Chemistry, 44(11), 1906–1909.",
    'snv': "Barnes, R. J., Dhanoa, M. S., & Lister, S. J. (1989). Standard normal variate "
           "transformation and de-trending of near-infrared diffuse reflectance spectra. "
           "Applied Spectroscopy, 43(5), 772–777.",
    'msc': "Geladi, P., MacDougall, D., & Martens, H. (1985). Linearization and scatter-correction "
           "for near-infrared reflectance spectra of meat. Applied Spectroscopy, 39(3), 491–500.",
    'svd_water': "Palacký, J., Mojzeš, P., & Bok, J. (2011). SVD-based method for intensity "
                 "normalization, background correction and solvent subtraction in Raman "
                 "spectroscopy exploiting the properties of water stretching vibrations. "
                 "Journal of Raman Spectroscopy, 42(7), 1528–1539.",
    'whitaker': "Whitaker, D. A., & Hayes, K. (2018). A simple algorithm for despiking Raman "
                "spectra. Chemometrics and Intelligent Laboratory Systems, 179, 82–84.",
    'wiener': "Wiener, N. (1949). Extrapolation, Interpolation, and Smoothing of Stationary "
              "Time Series. MIT Press.",
}

# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------

_SUPERSCRIPT = str.maketrans('-0123456789', '⁻⁰¹²³⁴⁵⁶⁷⁸⁹')


def fmt_num(value, digits: int = 4) -> str:
    """Readable number: 100000 -> '1 × 10⁵', 0.01 -> '0.01', 11 -> '11'."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(v) or math.isinf(v):
        return str(v)
    if v == int(v) and abs(v) < 1e5:
        return str(int(v))
    if v != 0 and (abs(v) >= 1e5 or abs(v) < 1e-3):
        exp = int(math.floor(math.log10(abs(v))))
        mant = v / 10 ** exp
        mant_s = f"{mant:.3g}"
        exp_s = str(exp).translate(_SUPERSCRIPT)
        return f"10{exp_s}" if mant_s == '1' else f"{mant_s} × 10{exp_s}"
    return f"{v:.{digits}g}"


def _fmt_range(r, unit: str) -> str:
    try:
        lo, hi = float(r[0]), float(r[1])
    except (TypeError, ValueError, IndexError):
        return str(r)
    lo, hi = min(lo, hi), max(lo, hi)
    return f"{fmt_num(lo)}–{fmt_num(hi)}{(' ' + unit) if unit else ''}"


def _join_and(parts) -> str:
    parts = list(parts)
    return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1]


def _fmt_ranges(ranges, unit: str) -> str:
    parts = [_fmt_range(r, unit) for r in (ranges or [])]
    if len(parts) <= 1:
        return ''.join(parts)
    return ', '.join(parts[:-1]) + ' and ' + parts[-1]


def _plain(value):
    """numpy scalars/arrays -> plain Python (for the table)."""
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    except ImportError:
        pass
    return value


def _table_value(value) -> Optional[str]:
    """Value for the parameter table, or None if it is not worth a row
    (long per-spectrum lists, nested structures)."""
    value = _plain(value)
    if value is None:
        return '—'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, (int, float)):
        return fmt_num(value)
    if isinstance(value, str):
        return value if len(value) <= 120 else value[:117] + '…'
    if isinstance(value, (list, tuple)):
        if not value:
            return 'none'
        if all(isinstance(_plain(v), (int, float)) for v in value) and len(value) <= 8:
            return ', '.join(fmt_num(v) for v in value)
        if all(isinstance(v, (list, tuple)) and len(v) == 2 for v in value) and len(value) <= 8:
            return '; '.join(_fmt_range(v, '') for v in value)
        return f"{len(value)} items"
    if isinstance(value, dict):
        return f"{len(value)} entries" if value else 'none'
    return None


# ---------------------------------------------------------------------------
# Describing one operation
# ---------------------------------------------------------------------------

@dataclass
class _Description:
    sentence: str                                  # may contain {ref:key} markers
    rows: List[Tuple[str, str]] = field(default_factory=list)


def _cite(*keys) -> str:
    return '{ref:' + ','.join(keys) + '}'


_BASELINE = {
    # algorithm: (name for the text, reference keys, parameters it uses)
    'als': ("asymmetric least squares (ALS)", ('als',), ('lambda', 'p', 'n_iter')),
    'airpls': ("adaptive iteratively reweighted penalized least squares (airPLS)", ('airpls',), ('lambda', 'n_iter')),
    'arpls': ("asymmetrically reweighted penalized least squares (arPLS)", ('arpls',), ('lambda', 'n_iter')),
    'iarpls': ("improved arPLS (iarPLS)", ('iarpls',), ('lambda', 'n_iter')),
    'aspls': ("adaptive smoothness penalized least squares (asPLS)", ('aspls',), ('lambda', 'n_iter')),
    'drpls': ("doubly reweighted penalized least squares (drPLS)", ('drpls',), ('lambda', 'eta', 'n_iter')),
    'psalsa': ("peaked signal's asymmetric least squares (psalsa)", ('psalsa',), ('lambda', 'p', 'n_iter')),
    'imodpoly': ("improved modified polynomial fitting (I-ModPoly)", ('modpoly', 'imodpoly'), ('poly_order', 'n_iter')),
    'morphological': ("morphological opening with an adaptive structuring element", ('morphological',), ()),
    'mpls': ("morphological weighted penalized least squares (MPLS)", ('mpls',), ('lambda', 'p')),
    'mollification': ("iterative morphology and mollification", ('mollification_koch', 'mollification_chen'), ('n_iter',)),
    'mpspline': ("morphology-based cubic penalized spline fitting (mpspline)", ('mpspline',), ('lambda', 'p')),
    'jbcd': ("joint baseline correction and denoising (JBCD)", ('jbcd',), ('alpha', 'beta', 'n_iter')),
}

_PARAM_WORDS = {
    'lambda': ('smoothness', 'λ'), 'p': ('asymmetry', 'p'), 'n_iter': ('maximum iterations', None),
    'eta': ('peak-region relaxation', 'η'), 'poly_order': ('polynomial order', None),
    'alpha': ('regularization', 'α'), 'beta': ('regularization', 'β'),
}


def _describe_automated_baseline(p, ctx):
    algo = p.get('algorithm', 'als')
    name, refs, used = _BASELINE.get(algo, (str(algo), (), ()))
    bits = []
    for key in used:
        if key in p and p[key] is not None:
            word, sym = _PARAM_WORDS[key]
            if key == 'n_iter':
                bits.append(f"at most {fmt_num(p[key])} iterations")
            else:
                bits.append(f"{sym} = {fmt_num(p[key])}" if sym else f"{word} {fmt_num(p[key])}")
    text = f"The baseline was estimated and subtracted by {name}" + (f" {_cite(*refs)}" if refs else '')
    if bits:
        text += " with " + _join_and(bits)
    ranges = p.get('fitting_ranges') or []
    if ranges:
        where = _fmt_ranges(ranges, ctx.x_unit)
        text += (f", excluding the regions {where} from the fit" if p.get('invert_regions')
                 else f", fitted only to the regions {where}")
    rows = [('method', name)] + [(_PARAM_WORDS[k][1] or _PARAM_WORDS[k][0], fmt_num(p[k]))
                                 for k in used if k in p and p[k] is not None]
    if ranges:
        rows.append(('regions excluded from fit' if p.get('invert_regions') else 'fitting regions',
                     _fmt_ranges(ranges, ctx.x_unit)))
    return _Description(text + '.', rows)


def _describe_snip(p, ctx):
    n = p.get('n_iter', 100)
    text = (f"The background was removed with the SNIP algorithm {_cite('snip')} "
            f"({fmt_num(n)} clipping iterations")
    extra = []
    if p.get('decreasing', True):
        extra.append("decreasing clipping window")
    if p.get('transform', True):
        extra.append("square-root variance-stabilizing transform")
    if p.get('smooth_window'):
        extra.append(f"pre-smoothing half-window {fmt_num(p['smooth_window'])} points")
    text += (', ' + ', '.join(extra) if extra else '') + ').'
    return _Description(text, [('clipping iterations', fmt_num(n)),
                               ('decreasing window', 'yes' if p.get('decreasing', True) else 'no'),
                               ('variance-stabilizing transform', 'yes' if p.get('transform', True) else 'no'),
                               ('pre-smoothing half-window', fmt_num(p.get('smooth_window', 0)))])


def _describe_sg(p, ctx):
    w, o, d = p.get('window_length'), p.get('polyorder'), int(p.get('deriv_order', 0) or 0)
    what = "smoothed" if d == 0 else f"differentiated ({_ordinal(d)} derivative)"
    text = (f"The spectra were {what} with a Savitzky–Golay filter {_cite('savgol', 'steinier')} "
            f"(window {fmt_num(w)} points, polynomial order {fmt_num(o)}).")
    rows = [('window (points)', fmt_num(w)), ('polynomial order', fmt_num(o)), ('derivative order', str(d))]
    return _Description(text, rows)


def _ordinal(n):
    return {1: 'first', 2: 'second', 3: 'third', 4: 'fourth'}.get(n, f"{n}th")


_NORMALIZATION_TEXT = {
    'max_peak': ("normalized to the maximum intensity", ()),
    'unit_area': ("normalized to unit area", ()),
    'vector': ("normalized to unit vector length (L2 norm)", ()),
    'quantile': ("normalized to a high percentile of the intensity", ()),
    'top_mean': ("normalized to the mean of their most intense points", ()),
    'min_max': ("scaled to the range 0–1 (min–max scaling)", ()),
    'offset_correction': ("offset-corrected", ()),
    'reference': ("normalized to a reference spectrum", ()),
    'snv': ("corrected for scatter by standard normal variate (SNV) transformation", ('snv',)),
    'msc': ("corrected for scatter by multiplicative scatter correction (MSC)", ('msc',)),
    'svd': ("normalized by the SVD-based intensity normalization", ('svd_water',)),
    'mean_center': ("mean-centered", ()),
    'z_score': ("autoscaled (z-score)", ()),
    'range_scaling': ("range-scaled", ()),
    'robust_scaling': ("robustly scaled (median and interquartile range)", ()),
    'baseline_correction': ("offset-corrected by their minimum", ()),
}


def _describe_normalization(p, ctx):
    mode = p.get('normalization_mode', 'max_peak')
    words, refs = _NORMALIZATION_TEXT.get(mode, (f"normalized ({mode})", ()))
    text = f"The spectra were {words}" + (f" {_cite(*refs)}" if refs else '')
    rows = [('method', words)]
    if mode == 'quantile' and p.get('percentile_value') is not None:
        text += f" ({fmt_num(p['percentile_value'])}th percentile)"
        rows.append(('percentile', fmt_num(p['percentile_value'])))
    regions = p.get('x_ranges') or []
    region_modes = ('max_peak', 'unit_area', 'vector', 'quantile', 'top_mean', 'min_max',
                    'offset_correction', 'msc')
    if regions and mode in region_modes and (mode != 'msc' or p.get('msc_use_region')):
        where = _fmt_ranges(regions, ctx.x_unit)
        text += (f", computed over the whole spectrum except {where}" if p.get('is_exclude_mode')
                 else f", computed within {where}")
        rows.append(('regions excluded' if p.get('is_exclude_mode') else 'regions used', where))
    target = p.get('target_mode', 'standard')
    if target == 'mean_relative':
        text += "; the result was rescaled to the mean intensity level of the set"
        rows.append(('output scale', 'relative to the mean factor'))
    elif target == 'custom' and p.get('target_value') not in (None, 1, 1.0):
        text += f"; the result was multiplied by {fmt_num(p['target_value'])}"
        rows.append(('output scale', f"× {fmt_num(p['target_value'])}"))
    return _Description(text + '.', rows)


def _describe_data_range(p, ctx):
    ranges = p.get('ranges') or []
    where = _fmt_ranges(ranges, ctx.x_unit)
    if not ranges:
        text = "The spectral range was left unchanged"
    elif p.get('is_exclude_mode'):
        text = f"The regions {where} were removed from the spectra"
    else:
        text = f"The spectra were restricted to {where}"
    rows = [('kept' if not p.get('is_exclude_mode') else 'removed', where or 'whole range')]
    if p.get('apply_linearization') and p.get('x_step'):
        text += (f" and interpolated onto a common axis with a step of "
                 f"{fmt_num(p['x_step'])}{(' ' + ctx.x_unit) if ctx.x_unit else ''}")
        rows.append(('common axis step', fmt_num(p['x_step'])))
    return _Description(text + '.', rows)


def _describe_manual_baseline(p, ctx):
    corrections = p.get('corrections') or {}
    types, counts = set(), []
    for info in corrections.values():
        if isinstance(info, dict):
            t = info.get('type', 'curve')
            if t == 'polynomial' and info.get('order') is not None:
                t = f"polynomial (order {info['order']})"
            types.add(t)
            pts = info.get('points', 0)          # a list of (x, y) pairs, or a count
            try:
                counts.append(len(pts) if hasattr(pts, '__len__') else int(pts))
            except (TypeError, ValueError):
                counts.append(0)
    kind = ' / '.join(sorted(types)) or 'curve'
    text = (f"The baseline was subtracted manually: a {kind} was fitted through baseline points "
            f"chosen by hand in each spectrum")
    if counts and max(counts) > 0:
        text += (f" ({min(counts)} points per spectrum)" if min(counts) == max(counts)
                 else f" ({min(counts)}–{max(counts)} points per spectrum)")
    return _Description(text + '.', [('baseline shape', kind), ('spectra', str(len(corrections)))])


def _describe_svd_background(p, ctx):
    sel = p.get('selected_subspectra') or []
    mode = p.get('correction_mode', 'all_subspectra')
    text = f"The background was removed by SVD-based background correction {_cite('svd_water')}"
    if mode != 'all_subspectra' and sel:
        text += f" using {len(sel)} selected SVD components"
    return _Description(text + '.', [('mode', str(mode)), ('components used', str(len(sel)) if sel else 'all')])


def _describe_spikes(p, ctx):
    thr, hw = p.get('threshold'), p.get('half_window')
    text = (f"Spikes were removed with the Whitaker–Hayes algorithm {_cite('whitaker')} "
            f"(modified z-score threshold {fmt_num(thr)}, replacement half-window {fmt_num(hw)} points)")
    if p.get('mode') == 'interactive':
        text += "; the detected spikes were checked visually before removal"
    return _Description(text + '.', [('z-score threshold', fmt_num(thr)), ('half-window (points)', fmt_num(hw))])


def _describe_cosmic(p, ctx):
    thr, w = p.get('threshold'), p.get('replace_window')
    text = (f"Cosmic-ray artefacts were detected as points deviating from the median of all spectra "
            f"at the same position (modified z-score based on the median absolute deviation, "
            f"threshold {fmt_num(thr)}) and replaced"
            + (f" together with {fmt_num(w)} neighbouring point(s) on each side" if w else '') + '.')
    return _Description(text, [('z-score threshold', fmt_num(thr)), ('replacement window (points)', fmt_num(w))])


def _describe_fft(p, ctx):
    lo, hi = p.get('low_cutoff'), p.get('high_cutoff')
    parts = []
    if lo is not None:
        parts.append(f"frequency components below {fmt_num(lo)}")
    if hi is not None:
        parts.append(f"above {fmt_num(hi)}" if parts else f"frequency components above {fmt_num(hi)}")
    bands = p.get('stop_bands') or []
    if bands:
        parts.append(f"{len(bands)} stop band(s)")
    text = "The spectra were filtered in the Fourier domain"
    if parts:
        text += " (" + ', '.join(parts) + " removed"
        if p.get('window') and p.get('window') != 'none':
            text += f", {p['window']} window on the transition edges"
        text += ")"
    rows = [('low cut-off', fmt_num(lo) if lo is not None else '—'),
            ('high cut-off', fmt_num(hi) if hi is not None else '—'),
            ('stop bands', str(len(bands))), ('window', str(p.get('window', 'none')))]
    return _Description(text + '.', rows)


def _describe_resolution(p, ctx):
    s, snr = p.get('irf_sigma'), p.get('snr')
    unit = f" {ctx.x_unit}" if ctx.x_unit else ''
    text = (f"The spectral resolution was enhanced by Wiener deconvolution {_cite('wiener')} assuming "
            f"a Gaussian instrument response (σ = {fmt_num(s)}{unit}, signal-to-noise ratio {fmt_num(snr)}).")
    return _Description(text, [('instrument response σ', fmt_num(s)), ('signal-to-noise ratio', fmt_num(snr))])


def _describe_alignment(p, ctx):
    ref = p.get('reference_spectrum_index', 0)
    text = (f"The spectra were aligned along the x-axis to a reference spectrum by shifting them by up "
            f"to ±{fmt_num(p.get('max_shift'))}{(' ' + ctx.x_unit) if ctx.x_unit else ''} "
            f"({p.get('interpolation_method', 'cubic')} interpolation)")
    if p.get('x_range'):
        text += f", using the region {_fmt_range(p['x_range'], ctx.x_unit)} to determine the shift"
    return _Description(text + '.', [('reference spectrum (position)', str(int(ref) + 1)),
                                     ('maximum shift', fmt_num(p.get('max_shift'))),
                                     ('interpolation', str(p.get('interpolation_method', 'cubic')))])


_UNIT_WORDS = {'nm': 'wavelength (nm)', 'cm-1': 'wavenumber (cm⁻¹)', 'eV': 'energy (eV)', 'Hz': 'frequency (Hz)'}


def _describe_xunit(p, ctx):
    a, b = p.get('from_unit'), p.get('to_unit')
    text = f"The x-axis was converted from {_UNIT_WORDS.get(a, a)} to {_UNIT_WORDS.get(b, b)}."
    ctx.x_unit = {'cm-1': 'cm⁻¹'}.get(b, b or ctx.x_unit)
    return _Description(text, [('from', str(a)), ('to', str(b))])


_CD_OUTPUT = {'molar_ellipticity': 'molar ellipticity [θ] (deg·cm²·dmol⁻¹)',
              'delta_epsilon': 'differential molar extinction coefficient Δε (M⁻¹·cm⁻¹)',
              'delta_a': 'differential absorbance ΔA'}


def _describe_cd_units(p, ctx):
    out = p.get('output_type', 'molar_ellipticity')
    words = _CD_OUTPUT.get(out, out)
    if p.get('ellipticity_convention') == 'mean_residue' and out != 'delta_a':
        words = words.replace('molar ellipticity', 'mean-residue molar ellipticity').replace(
            'molar extinction', 'mean-residue molar extinction')
    text = f"The CD signal was converted from ellipticity (mdeg) to {words}"
    per = p.get('per_spectrum') or {}
    convention = {'mean_residue': 'per residue / nucleotide', 'molecular': 'per molecule'}.get(
        p.get('ellipticity_convention'), str(p.get('ellipticity_convention', '')))
    rows = [('output', words), ('concentration basis', convention)]
    values = list(per.values()) if isinstance(per, dict) else []
    for key, word, fmt in (('path_length_cm', 'path length', '{} cm'),
                           ('concentration_value', 'concentration', '{} ' + str(p.get('concentration_unit', '')))):
        vals = sorted({fmt_num(v.get(key)) for v in values if isinstance(v, dict) and v.get(key) is not None})
        if vals:
            rows.append((word, ', '.join(fmt.format(v) for v in vals[:4]) + (' …' if len(vals) > 4 else '')))
    lengths = [r for r in rows if r[0] == 'path length']
    if lengths:
        text += f" (path length {lengths[0][1]})"
    return _Description(text + '.', rows)


def _describe_mean_center(p, ctx):
    return _Description("The mean spectrum of the data set was subtracted from every spectrum "
                        "(mean-centering).", [('mean spectrum kept', 'yes' if p.get('include_mean_spectrum') else 'no')])


def _describe_combine(p, ctx):
    op = p.get('operation_type', 'average')
    n = len(p.get('source_labels') or [])
    verb = {'average': 'averaged', 'sum': 'summed'}.get(op, op)
    name = p.get('new_spectrum_name')
    text = f"{n} spectra were {verb}" + (f" into the spectrum “{name}”" if name else '') + '.'
    return _Description(text, [('operation', str(op)), ('number of spectra', str(n)), ('result', str(name or ''))])


def _describe_calculator(p, ctx):
    f, name = p.get('formula', ''), p.get('new_spectrum_name', '')
    text = f"A new spectrum “{name}” was calculated as {f}."
    return _Description(text, [('formula', f), ('result', name)])


def _describe_subtraction(p, ctx):
    factors = p.get('stored_factors') or {}
    vals = [v for v in (factors.values() if isinstance(factors, dict) else []) if isinstance(_plain(v), (int, float))]
    text = "A reference spectrum was subtracted, scaled by a factor chosen interactively"
    if vals:
        text += (f" ({fmt_num(vals[0])})" if len(set(map(fmt_num, vals))) == 1
                 else f" ({fmt_num(min(vals))}–{fmt_num(max(vals))})")
    elif p.get('subtraction_factor') is not None:
        text += f" ({fmt_num(p['subtraction_factor'])})"
    return _Description(text + '.', [('factor(s)', ', '.join(fmt_num(v) for v in vals[:6]) if vals
                                      else fmt_num(p.get('subtraction_factor')))])


_DESCRIBERS: Dict[str, Callable] = {
    'Automated Baseline': _describe_automated_baseline,
    'SNIP Baseline': _describe_snip,
    'SG-smoothing': _describe_sg,
    'Normalization': _describe_normalization,
    'Data range': _describe_data_range,
    'Manual baseline': _describe_manual_baseline,
    'SVD background': _describe_svd_background,
    'Spike removal': _describe_spikes,
    'Cosmic ray removal': _describe_cosmic,
    'FFT Denoising': _describe_fft,
    'Resolution enhancement': _describe_resolution,
    'X-axis alignment': _describe_alignment,
    'X-axis Unit Conversion': _describe_xunit,
    'CD Unit Conversion': _describe_cd_units,
    'Mean-Center Spectra (Dataset)': _describe_mean_center,
    'Combine Spectra': _describe_combine,
    'Spectral Calculator': _describe_calculator,
    'Interactive subtraction': _describe_subtraction,
}

def _describe_import(p, ctx):
    """More spectra imported into the workspace (an "Add" import), so later
    steps may apply to a different set of spectra than earlier ones."""
    n = p.get('imported_count')
    files = p.get('files') or []
    what = f"{n} further spectr{'um was' if n == 1 else 'a were'}" if n else "Further spectra were"
    text = what + " imported"
    if files:
        text += " from " + _join_and(files[:5]) + (" and other files" if len(files) > 5 else '')
    rows = [('number of spectra', str(n))] if n else []
    if files:
        rows.append(('files', ', '.join(files)))
    return _Description(text + '.', rows or [('spectra', 'imported')])


_DESCRIBERS['Import'] = _describe_import


def _describe_data_table(p, ctx):
    """Formula columns of the Data table added as new spectra."""
    formulas = p.get('formulas') or []
    if not formulas:
        return _describe_generic('Data table (add as new)', p, ctx)
    parts, rows, columns = [], [], {}
    for f in formulas:
        parts.append(f"“{f.get('name', '')}” = {f.get('formula', '')}")
        rows.append((f.get('name', ''), f.get('formula', '')))
        columns.update(f.get('columns') or {})
    text = ("New spectr" + ("um was" if len(formulas) == 1 else "a were")
            + " calculated point by point from the spectra: " + '; '.join(parts))
    if columns:
        names = sorted(columns.items(), key=lambda kv: (re.sub(r'\d', '', kv[0]), int(re.sub(r'\D', '', kv[0]) or 0)))
        text += ", where " + ', '.join(f"{k} is “{v}”" for k, v in names)
        rows += [(k, v) for k, v in names]
    return _Description(text + '.', rows)


_DESCRIBERS['Data table (add as new)'] = _describe_data_table

# Operations that change nothing a reader of a Methods section needs to know.
_SKIPPED = {'Rename'}

# Settings that only steer the user interface, never the result.
_UI_ONLY_KEYS = {'show_power', 'show_signal', 'show_legend', 'show_variance', 'show_selected',
                 'processing_mode', 'max_workers', 'signal_mode', 'delta_values',
                 'half_window_map', 'effective_spikes', 'source_labels', 'selected_subspectra',
                 'baseline_corrections', 'inverted_subspectra', 'stored_factors', 'per_spectrum',
                 'corrections', 'minuend_indices', 'subtrahend_index'}


def _describe_generic(op_type, p, ctx):
    rows = []
    for k, v in (p or {}).items():
        if k in _UI_ONLY_KEYS:
            continue
        shown = _table_value(v)
        if shown is not None:
            rows.append((k.replace('_', ' '), shown))
    text = f"{op_type} was applied" + (
        " (" + ', '.join(f"{k} {v}" for k, v in rows[:4]) + ")" if rows else '') + '.'
    return _Description(text, rows)


@dataclass
class _Ctx:
    x_unit: str = ''


def describe_operation(op_type: str, params: dict, ctx: Optional[_Ctx] = None) -> _Description:
    ctx = ctx or _Ctx()
    params = params or {}
    if op_type.startswith('Batch Pipeline'):
        steps = params.get('steps') or []
        name = params.get('pipeline_name', '')
        inner = [describe_operation(s.get('operation', '?'), s.get('settings') or {}, ctx)
                 for s in steps if s.get('operation') not in _SKIPPED]
        text = (f"The saved processing pipeline “{name}” was applied, consisting of the "
                f"following steps. " if name
                else "A processing pipeline was applied, consisting of the following steps. ")
        text += ' '.join(d.sentence for d in inner)
        rows = []
        for i, (s, d) in enumerate(zip(steps, inner), 1):
            rows += [(f"step {i}: {s.get('operation')} – {k}", v) for k, v in d.rows]
        return _Description(text, rows)
    fn = _DESCRIBERS.get(op_type)
    if fn is None:
        return _describe_generic(op_type, params, ctx)
    try:
        return fn(params, ctx)
    except Exception:                       # never let one odd record spoil the report
        return _describe_generic(op_type, params, ctx)


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

@dataclass
class ReportStep:
    number: int
    operation: str
    applied_to: str
    sentence: str               # final text, references already numbered
    rows: List[Tuple[str, str]]


@dataclass
class MethodsReport:
    text: str                   # the Methods paragraph(s)
    steps: List[ReportStep]
    references: List[str]       # numbered in order of first citation
    software_line: str

    def table_rows(self) -> List[Tuple[str, str, str, str, str]]:
        """(step, operation, applied to, parameter, value) rows."""
        out = []
        for s in self.steps:
            if not s.rows:
                out.append((str(s.number), s.operation, s.applied_to, '', ''))
            for i, (k, v) in enumerate(s.rows):
                out.append((str(s.number) if i == 0 else '', s.operation if i == 0 else '',
                            s.applied_to if i == 0 else '', k, v))
        return out

    def export_content(self, include_table: bool = True, include_references: bool = True):
        return ExportContent(self.text, self.table_rows(), self.numbered_references(),
                             include_table, include_references)

    def numbered_references(self) -> List[str]:
        return [f"[{i}] {r}" for i, r in enumerate(self.references, 1)]

    # -- renderings (everything included)
    def as_plain_text(self) -> str:
        return self.export_content().as_plain_text()

    def as_markdown(self) -> str:
        return self.export_content().as_markdown()

    def as_html(self) -> str:
        return self.export_content().as_html()


TABLE_HEADER = ("Step", "Operation", "Applied to", "Parameter", "Value")
TITLE = "Data processing"


@dataclass
class ExportContent:
    """What is copied or saved: the (possibly edited) text, table rows and
    references, and which of the optional parts to include. References are
    exported exactly as written -- the user may have changed them to a
    journal's citation style."""
    text: str
    table_rows: List[Sequence[str]]
    references: List[str]
    include_table: bool = True
    include_references: bool = True

    def _paragraphs(self) -> List[str]:
        return [p.strip() for p in self.text.split("\n\n") if p.strip()]

    def _parts(self):
        return (self.include_table and bool(self.table_rows),
                self.include_references and bool(self.references))

    def as_plain_text(self) -> str:
        table, refs = self._parts()
        lines = [TITLE.upper(), "", "\n\n".join(self._paragraphs())]
        if table:
            lines += ["", "PARAMETERS", "", " | ".join(TABLE_HEADER)]
            lines += [" | ".join(row) for row in self.table_rows]
        if refs:
            lines += ["", "REFERENCES", ""] + list(self.references)
        return "\n".join(lines) + "\n"

    def as_markdown(self) -> str:
        table, refs = self._parts()
        lines = [f"## {TITLE}", "", "\n\n".join(self._paragraphs())]
        if table:
            lines += ["", "### Parameters", "", "| " + " | ".join(TABLE_HEADER) + " |",
                      "|" + "---|" * len(TABLE_HEADER)]
            lines += ["| " + " | ".join(str(c).replace('|', '\\|') for c in row) + " |"
                      for row in self.table_rows]
        if refs:
            lines += ["", "### References", ""] + [f"{r}  " for r in self.references]
        return "\n".join(lines) + "\n"

    def as_html(self) -> str:
        e = html.escape
        table, refs = self._parts()
        body = [f"<h2>{TITLE}</h2>"] + [f"<p>{e(p)}</p>" for p in self._paragraphs()]
        if table:
            body.append("<h3>Parameters</h3><table><tr>"
                        + ''.join(f"<th>{e(h)}</th>" for h in TABLE_HEADER) + "</tr>")
            body += ["<tr>" + ''.join(f"<td>{e(str(c))}</td>" for c in row) + "</tr>"
                     for row in self.table_rows]
            body.append("</table>")
        if refs:
            body.append("<h3>References</h3>")
            body += [f"<p class='ref'>{e(r)}</p>" for r in self.references]
        return ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>Methods – data processing</title>"
                "<style>body{font-family:Calibri,Arial,sans-serif;max-width:900px;margin:2em auto;"
                "line-height:1.45}table{border-collapse:collapse;font-size:10pt}td,th{border:1px solid #bbb;"
                "padding:3px 6px;vertical-align:top}th{background:#eee;text-align:left}"
                ".ref{margin:0 0 .4em 0}</style></head><body>" + ''.join(body) + "</body></html>")

    def docx_blocks(self):
        table, refs = self._parts()
        blocks = [('heading', TITLE, 1)] + [('paragraph', p) for p in self._paragraphs()]
        if table:
            blocks += [('heading', 'Parameters', 2),
                       ('table', list(TABLE_HEADER), [list(map(str, r)) for r in self.table_rows],
                        (7, 18, 11, 25, 39))]
        if refs:
            blocks += [('heading', 'References', 2)] + [('paragraph', r) for r in self.references]
        return blocks

    def save(self, path: str) -> None:
        """Save in the format given by the file extension (.docx, .html,
        .md, otherwise plain text)."""
        ext = os.path.splitext(path)[1].lower()
        if ext == '.docx':
            from src.modules.misc.simple_docx import write_docx
            write_docx(path, self.docx_blocks(), title="Methods – data processing")
            return
        content = (self.as_html() if ext in ('.html', '.htm')
                   else self.as_markdown() if ext == '.md' else self.as_plain_text())
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(content)


def _resolve_refs(text: str, order: List[str]) -> str:
    """Replace {ref:a,b} markers with [n] / [n, m] numbers, registering new
    references in *order* as they are first cited."""
    out, i = [], 0
    while True:
        j = text.find('{ref:', i)
        if j < 0:
            out.append(text[i:])
            break
        k = text.find('}', j)
        out.append(text[i:j])
        nums = []
        for key in text[j + 5:k].split(','):
            if key not in order:
                order.append(key)
            nums.append(order.index(key) + 1)
        out.append('[' + ', '.join(map(str, nums)) + ']')
        i = k + 1
    return ''.join(out)


def _add_note(sentence: str, note: str) -> str:
    """'... (a, b).' + note -> '... (a, b; note).'; otherwise '... (note).'"""
    if sentence.endswith(').'):
        return sentence[:-2] + f"; {note})."
    return sentence.rstrip('.') + f" ({note})."


def _guess_x_unit(spectra) -> str:
    for s in spectra or []:
        meta = s.get('metadata') if isinstance(s, dict) else getattr(s, 'metadata', None)
        meta = meta or {}
        if meta.get('file_type') in ('jasco_jws', 'jasco_jwb'):
            return 'nm'
    return ''


def _source_sentence(original_spectra) -> str:
    n = len(original_spectra or [])
    files = []
    for s in original_spectra or []:
        meta = (s.get('metadata') if isinstance(s, dict) else getattr(s, 'metadata', None)) or {}
        fp = meta.get('file_path')
        if fp and fp not in files:
            files.append(fp)
    if not n:
        return ''
    text = f"The data set comprised {n} spectr{'um' if n == 1 else 'a'}"
    if files:
        text += f" (imported from {len(files)} file{'s' if len(files) != 1 else ''})"
    return text + '.'


def build_report(operations_chain: Sequence[dict], active_index: int,
                 original_spectra: Sequence = (), app_version: str = '',
                 library_versions: Optional[Dict[str, str]] = None,
                 x_unit: Optional[str] = None) -> MethodsReport:
    """Methods report for the operations up to and including *active_index*
    (-1 = nothing applied yet)."""
    ctx = _Ctx(x_unit=x_unit if x_unit is not None else _guess_x_unit(original_spectra))
    order: List[str] = ['software']
    steps: List[ReportStep] = []
    previous_count = len(original_spectra or [])
    number = 0
    for record in list(operations_chain)[:active_index + 1]:
        op = record.get('type', '?')
        output = record.get('output_spectra') or []
        if op in _SKIPPED:
            previous_count = len(output) or previous_count
            continue
        number += 1
        d = describe_operation(op, record.get('parameters') or {}, ctx)
        n_aff = len(record.get('affected_labels') or [])
        applied = f"{n_aff} of {previous_count}" if n_aff and previous_count and n_aff < previous_count \
            else (f"all {previous_count}" if previous_count else str(n_aff))
        sentence = _resolve_refs(d.sentence, order)
        if n_aff and previous_count and n_aff < previous_count and op != 'Import':
            sentence = _add_note(sentence, f"applied to {n_aff} of {previous_count} spectra")
        steps.append(ReportStep(number, op, applied, sentence, d.rows))
        previous_count = len(output) or previous_count

    software = (f"SpecAnalytiXBase{(' version ' + app_version) if app_version else ''} "
                f"(open-source software, GPL-3.0), {SOFTWARE_URL}")
    intro = (f"Spectra were processed and analysed in SpecAnalytiXBase"
             f"{(' ' + app_version) if app_version else ''} [1].")
    src = _source_sentence(original_spectra)
    if src:
        intro += ' ' + src
    if steps:
        body = ' '.join(s.sentence for s in steps)
        text = intro + ' ' + body
    else:
        text = intro + " No processing was applied to the spectra."
    if library_versions:
        libs = ', '.join(f"{k} {v}" for k, v in library_versions.items() if v)
        if libs:
            text += f"\n\nCalculations used {libs}."
    references = [software if key == 'software' else REFERENCES.get(key, key) for key in order]
    return MethodsReport(text=text, steps=steps, references=references, software_line=software)


def report_for_main_controller(main) -> MethodsReport:
    """Convenience: the report for what the main window currently shows."""
    from src.version import __version__
    om = main.operations_controller.operations_manager
    libs = {}
    try:
        import numpy, scipy
        libs = {'Python': '.'.join(map(str, __import__('sys').version_info[:3])),
                'NumPy': numpy.__version__, 'SciPy': scipy.__version__}
    except Exception:
        pass
    return build_report(om.operations_chain, om.active_operation_index,
                        om.original_spectra, __version__, libs)


def default_file_name() -> str:
    return f"methods_{datetime.now():%Y-%m-%d}"
