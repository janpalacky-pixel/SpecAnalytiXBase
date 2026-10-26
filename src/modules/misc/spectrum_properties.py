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
SUGGESTED = ['concentration', 'pH', 'temperature', 'time', 'replicate', 'sample_number',
             'concentration_mM', 'temperature_C', 'time_s', 'time_min', 'ionic_strength_mM']


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


# ---------------------------------------------------------------------------
# Fill from a file: a table with the spectrum names in the first column and
# one column per property, e.g.
#     spectrum      pH    temperature_C
#     control_01    7.4   25
# ---------------------------------------------------------------------------

TABLE_FILTER = "Tables (*.csv *.txt *.tsv *.xlsx *.xlsm *.xls);;All files (*)"


def _cell_text(c):
    if c is None or (isinstance(c, float) and not np.isfinite(c)):
        return ''
    text = str(c).strip()
    return '' if text.lower() == 'nan' else text


def read_table(path):
    """(header, rows) of a CSV/TXT/TSV or Excel file, all cells as text.
    Excel: the sheet named 'Properties' if there is one, else the first.
    Text: cells separated by tabs, semicolons, commas or - when there is
    none of these - spaces (then the name is everything before the values,
    so names with spaces work too)."""
    if path.lower().endswith(('.xlsx', '.xlsm', '.xls')):
        import pandas as pd
        book = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
        sheet = next((df for name, df in book.items()
                      if str(name).strip().lower() == 'properties'), next(iter(book.values())))
        rows = [[_cell_text(c) for c in r] for r in sheet.itertuples(index=False)]
    else:
        with open(path, encoding='utf-8-sig', errors='replace') as fh:
            lines = [line.rstrip('\r\n') for line in fh if line.strip()]
        if not lines:
            raise ValueError("The file is empty.")
        sep = next((c for c in ('\t', ';', ',') if c in lines[0]), None)
        if sep is not None:
            rows = [[c.strip().strip('"') for c in line.split(sep)] for line in lines]
        else:
            n = len(lines[0].split())
            rows = [[c.strip('"') for c in line.strip().rsplit(None, max(n - 1, 0))]
                    for line in lines]
    rows = [r for r in rows if any(r)]
    while rows and rows[0] and all(r and not r[-1] for r in rows):    # empty last column
        rows = [r[:-1] for r in rows]
    if len(rows) < 2 or max(len(r) for r in rows) < 2:
        raise ValueError("The table needs a heading row and at least two columns: the spectrum "
                         "names, then one column per property.")
    return rows[0], rows[1:]


def make_name(text, k=1):
    """A property name from a column heading: 'Temperature (°C)' ->
    'Temperature_C', '2nd run' -> 'p_2nd_run'."""
    name = re.sub(r'[^A-Za-z0-9_]+', '_', str(text or '').strip()).strip('_')
    name = re.sub(r'_+', '_', name)
    if not name:
        return f'property_{k}'
    return name if name[0].isalpha() else 'p_' + name


def _name_keys(spectrum):
    """The names a table may use for a spectrum, in the order they are tried:
    (0, its full name), (1, its original name - before a rename), (2, the
    part after ' : ' - the column name in its data file)."""
    meta = spectrum.get('metadata') or {}
    full, original = str(spectrum.get('label', '')), str(meta.get('original_label') or '')
    keys = [(0, full), (1, original)]
    keys += [(2, n.rsplit(' : ', 1)[-1]) for n in (full, original) if ' : ' in n]
    seen, out = set(), []
    for level, name in keys:
        if name.strip() and name not in seen:
            seen.add(name)
            out.append((level, name))
    return out


def _loose(name):
    return re.sub(r'[^0-9a-z]+', '_', str(name).strip().lower()).strip('_')


def match_rows(spectra, table_names):
    """Which row of the table belongs to which spectrum. Returns (where,
    twice, unclear): where = for each spectrum the index of its row or None;
    twice = names that are in the table more than once (case, spaces and
    punctuation ignored) - those rows are not used, the program cannot know
    which is right; unclear = [(table name, [spectrum names])] - a row that
    fits several spectra equally well (e.g. 'control_01' when the list holds
    'day1 : control_01' and 'day2 : control_01') - given to none of them.

    Each spectrum tries its names in order - full name, original name,
    short name (the part after ' : ') - each first exactly, then ignoring
    case and spaces, then ignoring punctuation too. A row found by its full
    name beats one found by a short name."""
    count = {}
    for name in table_names:
        if name:
            count[_loose(name)] = count.get(_loose(name), 0) + 1
    twice_keys = {k for k, n in count.items() if n > 1}
    twice = []
    exact, lower, loose = {}, {}, {}
    for i, name in enumerate(table_names):
        if not name:
            continue
        if _loose(name) in twice_keys:
            if name not in twice:
                twice.append(name)
            continue
        exact.setdefault(name, i)
        lower.setdefault(name.strip().lower(), i)
        loose.setdefault(_loose(name), i)
    found = []                                  # (row, level) or None per spectrum
    for s in spectra:
        hit = None
        for level, key in _name_keys(s):
            for table, k in ((exact, key), (lower, key.strip().lower()), (loose, _loose(key))):
                if k in table:
                    hit = (table[k], level)
                    break
            if hit is not None:
                break
        found.append(hit)
    best = {}                                   # row -> the best level that found it
    for hit in found:
        if hit is not None:
            best[hit[0]] = min(best.get(hit[0], 99), hit[1])
    takers = {}
    for i, hit in enumerate(found):
        if hit is not None and hit[1] == best[hit[0]]:
            takers.setdefault(hit[0], []).append(i)
    where = [None] * len(spectra)
    unclear = []
    for row, members in takers.items():
        if len(members) == 1:
            where[members[0]] = row
        else:
            unclear.append((table_names[row], [str(spectra[i].get('label', '')) for i in members]))
    return where, twice, unclear


def from_table(spectra, header, rows, existing=()):
    """What a table file gives the spectra. Returns a dict:
    keys: property names (column headings made valid names);
    values: {key: [value or None per spectrum]} - None = not changed (not
        in the table, or an empty cell);
    found: number of spectra found in the table;
    not_found: names of spectra not in the table;
    unused: table names that match no spectrum;
    twice: names in the table more than once (not used);
    unclear: [(table name, [spectrum names])] rows that fit several spectra
        (not used; see match_rows);
    bad_cells: [(name, heading, text)] cells that are not numbers;
    skipped: [(heading, reason)] columns that cannot be properties."""
    names = [r[0] if r else '' for r in rows]
    where, twice, unclear = match_rows(spectra, names)
    in_unclear = {n for _, labels in unclear for n in labels}
    twice_keys = {_loose(n) for n in twice}
    in_twice = {str(s.get('label', '')) for s, r in zip(spectra, where)
                if r is None and any(_loose(k) in twice_keys for _, k in _name_keys(s))}
    unclear_rows = {t for t, _ in unclear}
    keys, values, skipped, bad, headings = [], {}, [], [], {}
    taken = set()
    for c in range(1, len(header)):
        heading = header[c] if header[c] else f'column {c + 1}'
        key = make_name(header[c], c)
        if key in taken:
            skipped.append((heading, f"the same name as another column ({key})"))
            continue
        problem = check_name(key, spectra, ())
        if problem:
            skipped.append((heading, problem))
            continue
        col, col_bad = [], []
        for i, r in enumerate(where):
            text = rows[r][c] if r is not None and c < len(rows[r]) else ''
            try:
                col.append(parse_value(text))
            except ValueError:
                col.append(None)
                col_bad.append((names[r], heading, text))
        if all(v is None for v in col):          # e.g. a column of notes
            if any(r is not None for r in where):
                skipped.append((heading, "no numbers (properties must be numbers)"))
            continue
        bad += col_bad
        taken.add(key)
        keys.append(key)
        values[key] = col
        headings[key] = heading
    used = {r for r in where if r is not None}
    return {'keys': keys, 'values': values,
            'found': sum(r is not None for r in where),
            'not_found': [s.get('label', '') for s, r in zip(spectra, where)
                          if r is None and str(s.get('label', '')) not in in_unclear | in_twice],
            'unused': [n for i, n in enumerate(names) if n and i not in used
                       and n not in twice and n not in unclear_rows],
            'twice': twice, 'unclear': unclear, 'n_spectra': len(spectra),
            'headings': headings,
            'bad_cells': bad, 'skipped': skipped}


def _q(text):
    return f"\u201c{text}\u201d"


def _some(names, k=3):
    return ', '.join(_q(n) for n in names[:k]) + (', \u2026' if len(names) > k else '')


def table_report(result):
    """What from_table found, for the user: what was filled, then what was
    not used and why (one line each)."""
    n = result.get('n_spectra', result['found'] + len(result['not_found']))
    headings = result.get('headings', {})
    lines = []
    if result['found']:
        lines.append(f"Found: {result['found']} of {n} spectra.")
    else:
        lines.append(f"Found: 0 of {n} spectra \u2013 nothing filled.")
    if result['keys']:
        lines.append("Filled: " + ', '.join(
            k if headings.get(k, k) == k else f"{k} (column {_q(headings[k])})"
            for k in result['keys']) + ".")
    elif result['found']:
        lines.append("Filled: nothing \u2013 no column has numbers for these spectra.")
    issues = []
    twice, unclear = result.get('twice', []), result.get('unclear', [])
    for name in twice[:5]:
        issues.append(f"row {_q(name)} \u2013 it is in the table twice; which one is right?")
    if len(twice) > 5:
        issues.append(f"\u2026 and {len(twice) - 5} more names that are in the table twice")
    if unclear:
        name, labels = unclear[0]
        fits = f"{_q(name)} fits " + ' and '.join(_q(l) for l in labels[:2]) + \
            (f" (and {len(labels) - 2} more)" if len(labels) > 2 else '')
        head = (f"row {_q(name)} fits {len(labels)} spectra" if len(unclear) == 1 else
                f"{len(unclear)} names fit several spectra each")
        issues.append(f"{head}, e.g. {fits}.\n   Write the full names, as in the spectra list, "
                      "in the table.")
    unused = result['unused']
    if len(unused) == 1:
        issues.append(f"row {_q(unused[0])} \u2013 no spectrum has this name")
    elif unused:
        issues.append(f"{len(unused)} rows \u2013 no spectrum has these names: {_some(unused)}")
    if result['not_found'] and result['found']:
        nf = result['not_found']
        issues.append(f"{len(nf)} spectr{'um' if len(nf) == 1 else 'a'} not in the table "
                      f"(left as they were): {_some(nf)}")
    by_heading = {}
    for name, heading, text in result['bad_cells']:
        by_heading.setdefault(heading, []).append((name, text))
    key_of = {h: k for k, h in headings.items()}
    for heading, cells in by_heading.items():
        key = key_of.get(heading, heading)
        name, text = cells[0]
        if len(cells) == 1:
            issues.append(f"{name}, {_q(heading)}: {_q(text)} is not a number \u2013 {name} gets "
                          f"no {key}")
        else:
            issues.append(f"column {_q(heading)}: {len(cells)} cells are not numbers (e.g. "
                          f"{_q(text)} for {name}) \u2013 those spectra get no {key}")
    for heading, reason in result['skipped']:
        issues.append(f"column {_q(heading)} \u2013 {reason}")
    if issues:
        lines.append("Not used:")
        lines += [" \u2022 " + t for t in issues]
    if not result['found'] and not twice and not unclear:
        lines.append("The first column must hold the spectrum names as in the list (or as in "
                     "the data file, e.g. control_01 for \u201cfile : control_01\u201d).")
    return '\n'.join(lines)
