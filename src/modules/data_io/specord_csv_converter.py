# src/modules/data_io/specord_csv_converter.py
"""Reader for the row-oriented CSV export straight off the SpecOrd
spectrometer's own software — a fundamentally different layout than the
delimiter/decimal-configurable text tables table_data_converter.py and
row_data_converter.py already handle, so it gets its own converter
(mirroring how spe_data_converter.py / spc_data_converter.py /
jasco_jws_reader.py each own their format rather than being squeezed
into the generic table pipeline) rather than a Layout option on top of
it.

Format, confirmed against 6 real files (~3.4-3.8 MB each) exported from
an Analytik Jena SpecOrd instrument for a pH-titration UV-melting
experiment:
  - ';'-delimited, CRLF line endings, comma-as-decimal-separator
    (European locale) throughout — both the two duplicate 'Temperature'
    columns and every wavelength value use ',' not '.'.
  - One row per (condition, temperature-step) MEASUREMENT — not one
    column per spectrum, and not one sheet per condition either. Header:
    No.;Type;Name;Date/Time;Note;Temperature;Temperature;230,0;231,0;...;330,0;
    i.e. 7 metadata columns then one column per wavelength (230-330nm in
    1nm steps in every file seen so far, but read from the header, not
    assumed).
  - 'Type' is 'Blank' or 'Sample'; 'Name' is the condition label ('blank',
    'pH 8', 'pH 7.5', ...). All conditions (including blank) are measured
    once at each temperature step, in a fixed repeating cycle, so a given
    condition's own rows — taken in file order — trace out that
    condition's full multi-run temperature trajectory (heating, cooling,
    heating, cooling, ...). Run boundaries are recovered generically per
    condition from direction reversals in that condition's own
    temperature sequence (see _segment_runs()) rather than assumed to
    always be exactly 4, so a file with a shorter/different temperature
    range still segments correctly.
  - Two duplicate 'Temperature' header columns per row, confirmed to
    differ by up to ~0.3 C (mean ~0.01 C) on real data — most likely a
    setpoint/actual-reading pair, but nothing in the exported file
    documents which is which. Since the discrepancy is small either way,
    this reader uses their average as each row's canonical temperature.

Each ROW becomes ONE Spectrum (x_scale = wavelengths, y_scale =
absorbance) — this is the natural unit for a general-purpose spectral
tool, unlike MeltAnalytiX's dedicated Run object which bundles a whole
run's temperature series into one array. The spectrum's LABEL embeds the
condition, run/direction, and temperature (e.g.
"250224 dC5U3 : pH 7.5 run2_cooling T=45.20C") so that:
  (a) it reads sensibly in the main spectra list without opening
      Metadata, and
  (b) Melting Curve Analysis's own temperature guesser (which extracts
      numbers from the label and picks whichever position VARIES across
      a selected series — see melting_curve_dialog.py) picks up the
      right one automatically, since condition/run/direction numbers are
      constant within any one series and only temperature varies.
The same values are also stored as structured metadata
('condition_label', 'condition_value', 'run_index', 'direction',
'temperature_C', 'measurement_type') for anything that wants to
filter/group programmatically instead of parsing the label text.
"""

import os
import re
import csv
from datetime import datetime
from typing import List, Dict, Optional

import numpy as np

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

_PH_RE = re.compile(r'pH\s*([\d.]+)', re.IGNORECASE)

# Metadata columns are always: No., Type, Name, Date/Time, Note,
# Temperature, Temperature — wavelength columns start right after.
_N_META_COLS = 7

# The first 3 header tokens that identify this format — used by
# looks_like_specord_csv() for auto-detection in the Import dialog.
_SIGNATURE_TOKENS = ('no.', 'type', 'name')


def _parse_condition(name: str) -> float:
    m = _PH_RE.search(name)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return float('nan')


def _to_float(s: str) -> float:
    """Parse one European-locale numeric field ('4,1' -> 4.1); returns
    NaN for empty/unparseable fields rather than raising, since a single
    bad cell shouldn't take down the whole row."""
    s = s.strip()
    if not s:
        return float('nan')
    try:
        return float(s.replace(',', '.'))
    except ValueError:
        return float('nan')


def _read_header_tokens(filepath: str, encoding: str) -> List[str]:
    with open(filepath, encoding=encoding, newline='') as f:
        reader = csv.reader(f, delimiter=';')
        return next(reader)


def looks_like_specord_csv(filepath: str, encoding: str = 'latin-1') -> bool:
    """Cheap auto-detection: does this .csv file's header row look like a
    SpecOrd row-per-measurement export? Only reads the first line — used
    by the Import dialog to pre-select the right handling without the
    user having to know the format's name up front. Deliberately narrow
    (exact column-name match) rather than a loose heuristic, since a
    false positive would silently mis-route an unrelated CSV into a
    completely different parser."""
    try:
        tokens = _read_header_tokens(filepath, encoding)
    except Exception:
        return False
    if len(tokens) < _N_META_COLS:
        return False
    first_three = [t.strip().lower() for t in tokens[:3]]
    return first_three == list(_SIGNATURE_TOKENS)


def _read_rows(path: str, encoding: str):
    """Parse the raw CSV into (wavelengths, rows), where `rows` is a list
    of dicts {'name', 'type', 'temperature', 'values'} in file order —
    every row whose Type is 'Blank' or 'Sample' with a parseable
    temperature."""
    with open(path, encoding=encoding, newline='') as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader)

        wl_cols, wavelengths = [], []
        for i, h in enumerate(header[_N_META_COLS:], start=_N_META_COLS):
            h = h.strip()
            if not h:
                continue
            wl = _to_float(h)
            if not np.isnan(wl):
                wl_cols.append(i)
                wavelengths.append(wl)
        wavelengths = np.array(wavelengths, dtype=float)
        if wavelengths.size == 0:
            raise ValueError(
                "No wavelength columns found in header — this file's first "
                "3 columns match the SpecOrd signature, but no numeric "
                "wavelength columns follow. Nothing to import."
            )

        rows = []
        max_col = max(wl_cols)
        for raw in reader:
            if len(raw) <= max_col:
                continue
            rtype = raw[1].strip()
            if rtype not in ('Blank', 'Sample'):
                continue
            name = raw[2].strip()
            t1, t2 = _to_float(raw[5]), _to_float(raw[6])
            temps = [t for t in (t1, t2) if not np.isnan(t)]
            if not temps:
                continue
            temperature = sum(temps) / len(temps)
            values = np.array([_to_float(raw[c]) for c in wl_cols], dtype=float)
            rows.append({'name': name, 'type': rtype, 'temperature': temperature,
                          'values': values})

    return wavelengths, rows


def _segment_runs(temperatures: np.ndarray) -> List[tuple]:
    """Split one condition's own temperature sequence (in file order)
    into (start, end) index ranges (end exclusive, Python-slice style),
    one per heating/cooling run, at direction reversals (local extrema).
    The extremum itself is the last point of the run heading into it, not
    the first point of the next one — confirmed against real data (a
    single unique peak/trough value, not a repeated/shared point)."""
    n = len(temperatures)
    if n == 0:
        return []
    reversal_idx = []
    direction = None
    for i in range(1, n):
        if temperatures[i] > temperatures[i - 1]:
            d = 1
        elif temperatures[i] < temperatures[i - 1]:
            d = -1
        else:
            continue  # equal consecutive temps: no new info, keep current direction
        if direction is None:
            direction = d
        elif d != direction:
            reversal_idx.append(i - 1)
            direction = d
    bounds = [0] + [r + 1 for r in reversal_idx] + [n]
    return [(bounds[k], bounds[k + 1]) for k in range(len(bounds) - 1)]


def read_specord_csv_data(
    filepath: str,
    zero_padding: int = 4,
    encoding: str = 'latin-1',
) -> List[Dict]:
    """Parse one row-oriented SpecOrd CSV export into a flat list of
    spectrum dicts (x_scale, y_scale, label, metadata) — one per
    (condition, temperature-step) row in the file, i.e. this is the
    SpecOrd-CSV equivalent of read_table_data() / read_spe_data() etc.

    Args:
        filepath: path to the .csv file.
        zero_padding: unused by this format (every spectrum already has
            a unique label from condition+run+temperature) — accepted
            anyway so this reader has the same call signature as every
            other converter SpectrumManager dispatches to.
        encoding: file text encoding; SpecOrd's own export has been
            plain ASCII/Latin-1 in every file seen so far.

    Returns:
        list of spectrum dicts, one per (condition, run) row actually
        found — typically ~4 runs x 13 conditions x ~95 temperature
        points per file, but this is derived from the data, not assumed.
    """
    base_name = os.path.splitext(os.path.basename(filepath))[0]

    wavelengths, rows = _read_rows(filepath, encoding=encoding)
    if not rows:
        raise ValueError(
            "No usable data rows found — every row's Type was neither "
            "'Blank' nor 'Sample', or no temperature could be parsed."
        )

    by_name: Dict[str, list] = {}
    for row in rows:
        by_name.setdefault(row['name'], []).append(row)

    try:
        file_ctime = datetime.fromtimestamp(os.path.getctime(filepath)).isoformat()
        file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
    except OSError:
        file_ctime = ''
        file_mtime = ''

    import_params = {
        'file_format': 'specord_csv',
        'delimiter': ';',
        'decimal_separator': ',',
        'n_wavelength_columns': int(wavelengths.size),
        'temperature_source': 'average of the two duplicate Temperature '
                               'columns (see module docstring)',
    }

    spectra: List[Dict] = []
    for name, name_rows in by_name.items():
        condition_label = name
        condition_value = _parse_condition(name)
        temps = np.array([r['temperature'] for r in name_rows], dtype=float)

        for run_index, (start, end) in enumerate(_segment_runs(temps), start=1):
            if end - start < 2:
                logger.warning(
                    "specord_csv_converter: '%s'/%s run %d has < 2 temperature "
                    "points (%d) - skipped.", filepath, name, run_index, end - start)
                continue

            direction = 'heating' if temps[start] < temps[end - 1] else 'cooling'
            clean_name = re.sub(r'\s+', '_', name.strip())

            for i in range(start, end):
                r = name_rows[i]
                temperature = r['temperature']
                label = (f"{base_name} : {clean_name} run{run_index}_{direction} "
                         f"T={temperature:.2f}C")

                metadata = {
                    'file_path': filepath,
                    'file_type': 'specord_csv',
                    'original_label': label,
                    'spectrum_name': label,
                    'condition_label': condition_label,
                    'condition_value': condition_value,
                    'run_index': run_index,
                    'direction': direction,
                    'temperature_C': float(temperature),
                    'measurement_type': r['type'],
                    'valid_points': int(wavelengths.size),
                    'file_creation_time': file_ctime,
                    'file_modification_time': file_mtime,
                    'import_parameters': import_params,
                }

                spectra.append({
                    'x_scale': wavelengths.copy(),
                    'y_scale': r['values'],
                    'label': label,
                    'metadata': metadata,
                })

    if not spectra:
        raise ValueError("No valid spectra could be built from this file's rows.")

    logger.info(
        "specord_csv_converter: imported %d spectra from %s (%d conditions)",
        len(spectra), os.path.basename(filepath), len(by_name))
    return spectra
