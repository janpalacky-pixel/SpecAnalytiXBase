# src/modules/misc/spectrum_properties.py
"""Spectrum properties: numbers that belong to each spectrum - temperature,
pH, concentration, time, ... - stored in its metadata. Those read from the
file (e.g. temperature_C of a JASCO temperature scan) and those typed in
are the same thing: Line colours > Colours by value, the Data table
("Values per spectrum") and the Peak list plot use them all. Qt-free; the
window is src/views/dialogs/misc/spectrum_properties_dialog.py, the
controller src/controllers/misc/spectrum_properties_controller.py."""

import math
import re

import numpy as np

from src.modules.visualization import color_by_value as cbv

# a property name can also be used in formulas (Data table), e.g. v1 / pH
NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
SUGGESTED = ['temperature_C', 'pH', 'concentration', 'concentration_mM', 'time_s', 'time_min',
             'ionic_strength_mM', 'replicate']


def property_keys(spectra):
    """The properties of the spectra (numbers stored with them), in the
    order they first appear."""
    return cbv.metadata_keys(spectra)


def check_name(name, spectra, existing=()):
    """None if `name` can be a new property, else why not."""
    name = (name or '').strip()
    if not name:
        return "Type a name."
    if not NAME_RE.match(name):
        return ("A name starts with a letter and has only letters, digits and _ (no spaces), "
                "e.g. concentration_mM - so it can also be used in formulas.")
    if name in existing:
        return f"There is already a property “{name}”."
    if name in cbv._INTERNAL_KEYS or name in ('label', 'unique_id'):
        return f"“{name}” is used by the program itself; choose another name."
    for s in spectra:
        v = (s.get('metadata') or {}).get(name)
        if v is not None and not _is_number(v):
            return f"“{name}” is already stored with the spectra as text; choose another name."
    return None


def _is_number(v):
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool) \
        and np.isfinite(float(v))


def value_of(spectrum, key):
    v = (spectrum.get('metadata') or {}).get(key)
    return float(v) if _is_number(v) else None


def parse_value(text):
    """'' -> None (no value); '7,4' -> 7.4; raises ValueError for anything else."""
    text = (text or '').strip().replace('−', '-')
    if not text:
        return None
    if re.fullmatch(r'[-+]?\d+,\d+', text):
        text = text.replace(',', '.')
    value = float(text)
    if not np.isfinite(value):
        raise ValueError(text)
    return value


def value_text(value):
    return '' if value is None else f'{value:.10g}'


def from_name(spectra, number=-1):
    """The `number`-th number written in each name (-1: the last), or None."""
    out = []
    for s in spectra:
        nums = cbv.numbers_in(s.get('label', ''))
        try:
            out.append(float(nums[number]))
        except IndexError:
            out.append(None)
    return out


def series(n, start, step):
    return [start + i * step for i in range(n)]


def changes(spectra, values):
    """values: one {key: value or None} per spectrum. Returns
    [(index, key, old, new)] of what differs from what is stored."""
    out = []
    for i, (s, new) in enumerate(zip(spectra, values)):
        for key, v in new.items():
            old = value_of(s, key)
            # the table shows 10 significant digits: a value read back from it
            # is the same value
            if (old is None) != (v is None) or (
                    old is not None and not math.isclose(old, v, rel_tol=1e-9, abs_tol=1e-300)):
                out.append((i, key, old, v))
    return out


def apply_to(spectrum, values):
    """Store {key: value or None} in the spectrum (None removes the key)."""
    meta = spectrum.setdefault('metadata', {})
    if meta is None:
        meta = spectrum['metadata'] = {}
    for key, v in values.items():
        if v is None:
            meta.pop(key, None)
        else:
            meta[key] = float(v)


def describe(changes_by_label):
    """Short text of a change, e.g. 'pH for 5 spectra, temperature_C for 2'."""
    per_key = {}
    for label, values in changes_by_label.items():
        for key in values:
            per_key[key] = per_key.get(key, 0) + 1
    return ', '.join(f"{k} for {n} spectr{'um' if n == 1 else 'a'}" for k, n in per_key.items())
