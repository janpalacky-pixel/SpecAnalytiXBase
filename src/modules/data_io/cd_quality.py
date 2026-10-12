# src/modules/data_io/cd_quality.py
"""CD data quality: where along the wavelength axis a CD spectrum cannot be
trusted because the detector received too little light.

Background (for users and developers)
-------------------------------------
A CD spectrometer measures a tiny difference between left- and right-
circularly polarized light. When the sample (plus buffer and cell) absorbs
almost all of the light, the detector's photomultiplier compensates by
raising its high voltage (HT). Above roughly 600-700 V, or at a total
absorbance above about 1-2, so little light remains that the CD signal is
mostly noise and can even look like real bands. Instrument guides
(e.g. JASCO J-1500 training notes; MIT Biophysical Instrumentation
Facility CD notes) therefore advise discarding the CD signal where HT is
above ~700 V or where absorbance is above ~1 (ideal) to ~2 (still
usable).

JASCO files usually store, next to the CD channel, the HT voltage or an
absorbance channel recorded in the same scan. This module uses that
channel to find the unreliable wavelengths:

    HT channel present   ->  unreliable where HT  > ht_limit  (default 700 V)
    else Abs channel     ->  unreliable where Abs > abs_limit (default 3.0)

The default absorbance limit is 3.0 rather than the textbook ideal of 1.0
because the absorbance channel JASCO records is not referenced to a blank
and carries an offset of roughly 1: a pure-buffer blank measured by the
user reads about 0.9 at 320 nm and 3.3 at 200 nm, and the bundled sample
files read about 1.1 at 450-480 nm, where nothing absorbs. A limit of 1.0
would flag every wavelength. 3.0 matches the user's laboratory experience
(trouble usually below 220-230 nm) and is deliberately lenient so as not
to alarm users; stricter users lower it (View -> CD data quality).
The check uses the raw, NOT blank-subtracted absorbance on purpose: the
detector is starved by everything in the beam, buffer and cell included.

What is stored
--------------
The readers keep the reference trace itself (not just yes/no flags) in a
CD spectrum's metadata['cd_quality'], so that changing the limits later
takes effect immediately without re-importing:

    {'source': 'HT' | 'Abs', 'unit': 'V' | 'AU', 'channel_index': int,
     'x_unit': 'nm', 'x': [...], 'values': [...]}

Its x is the wavelength axis of the scan, independent of the spectrum's own
x, so cropping, smoothing etc. of the spectrum do not affect it; X-axis
Unit Conversion converts it together with the spectrum (convert_quality_x).

Qt-free: plotting lives in src/modules/visualization/cd_quality_shading.py,
the menu in src/controllers/visualization/cd_quality_controller.py.
"""

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

DEFAULT_HT_LIMIT_V = 700.0
DEFAULT_ABS_LIMIT = 3.0

_SOURCE_UNITS = {'HT': 'V', 'Abs': 'AU'}


def pick_reference_channel(channel_types: Dict[int, str]) -> Optional[Tuple[int, str]]:
    """(channel_index, 'HT'|'Abs') of the channel to judge CD quality by:
    the first HT channel if there is one (it is the instrument's own
    measure of how starved the detector is), otherwise the first Abs
    channel, otherwise None."""
    for wanted in ('HT', 'Abs'):
        for i in sorted(channel_types):
            if channel_types[i] == wanted:
                return i, wanted
    return None


def build_quality(x, values, source: str, channel_index: int, x_unit: str = 'nm') -> Dict:
    """metadata['cd_quality'] entry for one CD spectrum (plain lists, so it
    is saved in snapshots like any other metadata)."""
    x = np.asarray(x, dtype=float)
    values = np.asarray(values, dtype=float)
    order = np.argsort(x, kind='stable')
    return {
        'source': source,
        'unit': _SOURCE_UNITS.get(source, ''),
        'channel_index': int(channel_index),
        'x_unit': x_unit,
        'x': [float(v) for v in x[order]],
        'values': [round(float(v), 6) for v in values[order]],
    }


def is_valid_quality(quality) -> bool:
    return (isinstance(quality, dict)
            and quality.get('source') in _SOURCE_UNITS
            and isinstance(quality.get('x'), (list, tuple, np.ndarray))
            and isinstance(quality.get('values'), (list, tuple, np.ndarray))
            and len(quality['x']) == len(quality['values']) and len(quality['x']) > 0)


def limit_for(quality: Dict, ht_limit: float = DEFAULT_HT_LIMIT_V,
              abs_limit: float = DEFAULT_ABS_LIMIT) -> float:
    return float(ht_limit) if quality.get('source') == 'HT' else float(abs_limit)


def unreliable_ranges(quality: Dict, ht_limit: float = DEFAULT_HT_LIMIT_V,
                      abs_limit: float = DEFAULT_ABS_LIMIT) -> List[Tuple[float, float]]:
    """Sorted, non-overlapping (x_low, x_high) ranges where the reference
    channel is above its limit. Each range reaches halfway to the next
    reliable point, so neighbouring ranges and the reliable part tile the
    axis without gaps. Missing values (NaN) count as reliable. Returns []
    for anything that is not a valid quality record."""
    if not is_valid_quality(quality):
        return []
    x = np.asarray(quality['x'], dtype=float)
    v = np.asarray(quality['values'], dtype=float)
    bad = np.nan_to_num(v, nan=-np.inf) > limit_for(quality, ht_limit, abs_limit)
    if not bad.any():
        return []
    ranges = []
    n = len(x)
    i = 0
    while i < n:
        if not bad[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and bad[j + 1]:
            j += 1
        lo = x[i] if i == 0 else 0.5 * (x[i - 1] + x[i])
        hi = x[j] if j == n - 1 else 0.5 * (x[j] + x[j + 1])
        if lo == hi:                          # single flagged point at an end
            step = abs(x[1] - x[0]) / 2 if n > 1 else 0.5
            lo, hi = lo - (step if i == 0 else 0), hi + (step if j == n - 1 else 0)
        ranges.append((float(lo), float(hi)))
        i = j + 1
    return ranges


def clip_ranges(ranges: Iterable[Tuple[float, float]], x_min: float,
                x_max: float) -> List[Tuple[float, float]]:
    """Ranges limited to [x_min, x_max]; empty pieces dropped."""
    out = []
    for lo, hi in ranges:
        lo, hi = max(lo, x_min), min(hi, x_max)
        if hi > lo:
            out.append((lo, hi))
    return out


def merge_ranges(ranges: Iterable[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Union of possibly overlapping ranges, sorted."""
    merged: List[List[float]] = []
    for lo, hi in sorted(ranges):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(a, b) for a, b in merged]


def convert_quality_x(quality: Dict, convert, new_unit: str) -> Dict:
    """Copy of *quality* with its x converted by convert(array) -> array
    (e.g. nm -> cm-1 in X-axis Unit Conversion) and re-sorted."""
    if not is_valid_quality(quality):
        return quality
    x = np.asarray(convert(np.asarray(quality['x'], dtype=float)), dtype=float)
    v = np.asarray(quality['values'], dtype=float)
    order = np.argsort(x, kind='stable')
    out = dict(quality)
    out['x'] = [float(a) for a in x[order]]
    out['values'] = [float(a) for a in v[order]]
    out['x_unit'] = new_unit
    return out


def _fmt(value: float) -> str:
    return f"{value:.0f}" if abs(value) >= 10 else f"{value:.3g}"


def describe_ranges(ranges: Sequence[Tuple[float, float]], unit: str = 'nm') -> str:
    """'below 278 nm', '200-215 nm and 300-320 nm', ... for one spectrum."""
    if not ranges:
        return 'none'
    return ' and '.join(f"{_fmt(lo)}–{_fmt(hi)} {unit}".strip() for lo, hi in ranges)


def import_summary(spectra_metadata: Sequence[Dict], ht_limit: float = DEFAULT_HT_LIMIT_V,
                   abs_limit: float = DEFAULT_ABS_LIMIT) -> Optional[str]:
    """One paragraph for the Import Results message, or None if there is
    nothing to say (no CD spectra from files that carry HT/Abs).

    spectra_metadata: metadata dicts of the imported spectra."""
    cd = [m for m in spectra_metadata
          if (m.get('import_parameters') or {}).get('channel_type') == 'CD']
    if not cd:
        return None
    checked = [m for m in cd if is_valid_quality(m.get('cd_quality'))]
    if not checked:
        if any(m.get('file_type') in ('jasco_jws', 'jasco_jwb') for m in cd):
            return ("ℹ️  CD data quality could not be checked: these files contain no HT "
                    "(detector voltage) or absorbance channel to judge it by.")
        return None

    flagged = []
    for m in checked:
        rng = unreliable_ranges(m['cd_quality'], ht_limit, abs_limit)
        if rng:
            flagged.append((m['cd_quality'], rng))
    n_cd = len(checked)
    sources = sorted({m['cd_quality']['source'] for m in checked})
    if not flagged:
        return (f"✅  CD data quality: all {n_cd} CD spectra are within the limits "
                f"({_limits_text(sources, ht_limit, abs_limit)}) at every wavelength.")

    unit = flagged[0][0].get('x_unit', 'nm')
    x_lows = [min(q['x']) for q, _ in flagged]
    whole = [len(r) == 1 and r[0][0] <= min(q['x']) and r[0][1] >= max(q['x'])
             for q, r in flagged]
    if all(whole):
        return (f"⚠️  CD data quality: in {len(flagged)} CD spectra the light check "
                f"({_limits_text(sources, ht_limit, abs_limit, 'above ')}) fails "
                f"at EVERY wavelength. If the spectra look fine, the limit is probably too "
                f"strict for your instrument (an absorbance channel often carries an "
                f"offset); change it in View → CD data quality.")
    # Typical case: one flagged range per spectrum, starting at the short-
    # wavelength end of the scan -> "below about 272-282 nm".
    if all(len(r) == 1 and abs(r[0][0] - lo) < 1e-9 for (q, r), lo in zip(flagged, x_lows)):
        highs = [r[0][1] for _, r in flagged]
        lo_h, hi_h = min(highs), max(highs)
        where = (f"below about {_fmt(lo_h)} {unit}" if _fmt(lo_h) == _fmt(hi_h)
                 else f"below about {_fmt(lo_h)}–{_fmt(hi_h)} {unit} (depending on the spectrum)")
    else:
        union = merge_ranges(r for _, rng in flagged for r in rng)
        where = "in " + describe_ranges(union, unit)
    n = len(flagged)
    word = 'spectrum has' if n == 1 else 'spectra have'
    of = '' if n == n_cd else f" (of {n_cd})"
    return (f"⚠️  CD data quality: {n}{of} CD {word} wavelengths where the detector "
            f"got too little light ({_limits_text(sources, ht_limit, abs_limit, 'above ')}), "
            f"{where}. CD values there are unreliable. They are shaded grey in the plot; "
            f"limits and shading: View → CD data quality.")


def _limits_text(sources, ht_limit, abs_limit, above='') -> str:
    parts = []
    if 'HT' in sources:
        parts.append(f"HT {above}{_fmt(ht_limit)} V")
    if 'Abs' in sources:
        parts.append(f"absorbance {above}{abs_limit:g}")
    return ' / '.join(parts)
