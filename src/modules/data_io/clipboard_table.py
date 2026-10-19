# src/modules/data_io/clipboard_table.py
"""Numbers copied from Excel (or any table / text) -> spectra. Qt-free.

What is accepted (what Excel puts on the clipboard, and plain text):
* columns separated by tabs (Excel), semicolons, commas or spaces;
* a decimal comma (Czech / German Excel) as well as a decimal point;
* an optional header row: its first cell names the x column, the others
  become the spectra's names;
* first column = x, every further column = one spectrum (y); a single
  column becomes one spectrum with x = 1, 2, 3, ...;
* a table written in rows instead (one spectrum per row) is recognised:
  - names in the first column (text in every row) and the x-values in the
    header row ("Name", 230, 231, ...) or in the first row (empty or named
    first cell, then the x-values) -- e.g. a Specord export with only the
    Name column and the numbers copied;
  - only numbers: when the first column is not a usable x-axis (not
    increasing or decreasing) but the first row is, the first row is x;
* empty cells: that spectrum simply has no point there.
The x-axis must be increasing or decreasing (it is stored increasing).
"""
import re

import numpy as np


class ClipboardTableError(ValueError):
    """The clipboard text is not a table of numbers (message for the user)."""


def _number(cell, decimal_comma):
    c = cell.strip().replace(' ', '').replace(' ', '')
    if c == '':
        return np.nan
    if decimal_comma:
        c = c.replace(',', '.')
    try:
        return float(c)
    except ValueError:
        return None          # not a number


def _split(lines):
    """(rows of cells, separator, decimal comma?)"""
    sample = lines[:50]
    if any('\t' in ln for ln in sample):
        sep = '\t'
    elif sum(';' in ln for ln in sample) >= max(1, len(sample) // 2):
        sep = ';'
    elif sum(',' in ln for ln in sample) >= max(1, len(sample) // 2) and not any(
            re.search(r'\S\s+\S', ln.strip()) for ln in sample):
        sep = ','            # commas and no spaces between values
    else:
        sep = None           # whitespace
    rows = [(ln.split(sep) if sep else ln.split()) for ln in lines]
    body = '\n'.join(lines)
    decimal_comma = sep != ',' and re.search(r'\d,\d', body) is not None
    return rows, sep, decimal_comma


def _monotonic(v):
    v = v[np.isfinite(v)]
    if len(v) < 2:
        return False
    d = np.diff(v)
    return bool(np.all(d > 0) or np.all(d < 0))


_NAME_HEADERS = ('name', 'label', 'sample', 'sample name', 'spectrum', 'title', 'id')


def _rows_with_leading_columns(rows, header, decimal_comma):
    """A table in rows with several leading columns before the numbers, as
    an export of a spectrometer (No. | Type | Name | Date | ... | 230 | 231
    | ...): the header row ends with the x-values; every row ends with one
    spectrum's numbers. The spectrum's name comes from a column headed
    Name / Label / Sample (else the first text column that differs between
    rows). Returns (x_name, [(name, x, y)], notes) or None."""
    width = len(header)
    k = None
    for start in range(1, width - 2):
        hx = [_number(c, decimal_comma) for c in header[start:]]
        if all(v is not None and np.isfinite(v) for v in hx) and _monotonic(np.array(hx)):
            k = start
            break
    if k is None:
        return None
    x = np.array([_number(c, decimal_comma) for c in header[k:]], dtype=float)
    data = []
    for r in rows:
        vals = [_number(c, decimal_comma) for c in r[k:]]
        if any(v is None for v in vals):
            return None
        data.append(np.array(vals, dtype=float))
    lead_names = [h.strip().lower() for h in header[:k]]
    name_col = next((j for j, h in enumerate(lead_names) if h in _NAME_HEADERS), None)
    if name_col is None:
        for j in range(k):
            col = [r[j].strip() for r in rows]
            if any(_number(c, decimal_comma) is None for c in col if c) and len(set(col)) > 1:
                name_col = j
                break
    if name_col is None:
        name_col = 0
    names = [rows[i][name_col].strip() or f"row {i + 2}" for i in range(len(rows))]
    note = (f"The table was read in rows: x = the header row from column {k + 1} on, "
            f"names from the column \u201c{header[name_col].strip() or name_col + 1}\u201d")
    if k > 1:
        note += (f"; the other {k - 1} leading column{'s were' if k - 1 != 1 else ' was'} "
                 "left out")
    notes = [note + "."]
    return ((header[name_col].strip() or 'x'), list(zip(names, [x] * len(data), data)), notes)


def parse_table(text):
    """-> (x_name, [(name, x, y), ...], notes). Raises ClipboardTableError."""
    lines = [ln.rstrip('\r') for ln in (text or '').split('\n')]
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        raise ClipboardTableError("The clipboard is empty.")
    rows, sep, decimal_comma = _split(lines)
    width = max(len(r) for r in rows)
    rows = [r + [''] * (width - len(r)) for r in rows]
    # columns empty in every row (e.g. a separator at the end of each line)
    keep = [j for j in range(width) if any(r[j].strip() for r in rows)]
    rows = [[r[j] for j in keep] for r in rows]
    parsed = [[_number(c, decimal_comma) for c in r] for r in rows]
    notes = []

    # header row: any non-number in the first row (an empty first cell is
    # a number-less corner, fine)
    header = None
    if any(v is None for v in parsed[0]):
        header = [c.strip() for c in rows[0]]
        rows, parsed = rows[1:], parsed[1:]
    if not parsed:
        raise ClipboardTableError("The clipboard holds only a header row, no numbers.")
    # text in the data rows: a table in rows with leading columns (name,
    # date, note, ...) before the numbers?
    if header is not None and any(v is None for r in parsed for v in r):
        lead = _rows_with_leading_columns(rows, header, decimal_comma)
        if lead is not None:
            x_name, rows_spectra, lead_notes = lead
            return _finish(x_name, [n for n, _, _ in rows_spectra], rows_spectra[0][1],
                           [y for _, _, y in rows_spectra], notes + lead_notes)

    # the first cell of each row may be a name: a table in rows (one
    # spectrum per row). Its x-values are then either the header row
    # ("Name", 230, 231, ...) or the first row (an empty or named first
    # cell, then the x-values).
    row_names = None
    header_x = None
    names_in_rows = (all(r[0] is None for r in parsed)
                     and all(all(v is not None for v in r[1:]) for r in parsed))
    if names_in_rows and header is not None and len(header) > 2:
        hx = [_number(c, decimal_comma) for c in header[1:]]
        if all(v is not None and np.isfinite(v) for v in hx) and _monotonic(np.array(hx)):
            header_x = np.array(hx, dtype=float)
    first_ok = parsed[0][0] is None or np.isnan(parsed[0][0])
    if header_x is not None or (
            len(parsed) >= 2 and first_ok and all(r[0] is None for r in parsed[1:])
            and all(all(v is not None for v in r[1:]) for r in parsed)):
        row_names = [r[0].strip() for r in rows]
        parsed = [r[1:] for r in parsed]
    bad = [(i, j) for i, r in enumerate(parsed) for j, v in enumerate(r) if v is None]
    if bad:
        i, j = bad[0]
        cell = (rows[i][j + (1 if row_names else 0)]).strip()
        raise ClipboardTableError(
            f"Not a table of numbers: \u201c{cell[:40]}\u201d in row "
            f"{i + 1 + (1 if header else 0)}, column {j + 1 + (1 if row_names else 0)}. "
            "Copy only the numbers (and at most one header row and one name column).")
    table = np.array(parsed, dtype=float)

    if header_x is not None:
        # spectra in rows, x-values in the header row, names in the first column
        x = header_x
        names = [n or f"row {i + 2}" for i, n in enumerate(row_names)]
        x_name = header[0] or 'x'
        ys = [table[i, :] for i in range(table.shape[0])]
        notes.append("The table was read in rows (header row = x, one spectrum per row).")
    elif row_names is not None or (not _monotonic(table[:, 0]) and table.shape[0] >= 2
                                   and _monotonic(table[0, :]) and table.shape[1] > 2):
        # spectra in rows: first row = x
        x = table[0, :]
        names = (row_names[1:] if row_names else
                 [f"row {i + 1}" for i in range(1, table.shape[0])])
        x_name = (row_names[0] if row_names and row_names[0] else 'x')
        ys = [table[i, :] for i in range(1, table.shape[0])]
        notes.append("The table was read in rows (first row = x, one spectrum per row).")
    elif table.shape[1] == 1:
        x = np.arange(1, table.shape[0] + 1, dtype=float)
        ys = [table[:, 0]]
        x_name = 'point'
        names = [header[0] if header and header[0] else 'column 1']
        notes.append("One column only: x = 1, 2, 3, … (point number).")
    else:
        x = table[:, 0]
        ys = [table[:, j] for j in range(1, table.shape[1])]
        x_name = (header[0] if header and header[0] else 'x')
        names = [(header[j] if header and j < len(header) and header[j] else f"column {j + 1}")
                 for j in range(1, table.shape[1])]
        notes.append("The table was read in columns: x = the first column, one spectrum per "
                     "further column" + (", names from the header row." if header else "."))

    return _finish(x_name, names, x, ys, notes)


def _finish(x_name, names, x, ys, notes):
    """Check x, sort it increasing, drop empty cells, number repeated
    names: (x_name, [(name, x, y)], notes)."""
    x = np.asarray(x, dtype=float)
    if np.any(~np.isfinite(x)):
        raise ClipboardTableError("The x column (first column) has empty cells.")
    if not _monotonic(x):
        raise ClipboardTableError(
            "The first column is not increasing or decreasing, so it cannot be the x-axis. "
            "Copy x in the first column and one spectrum per further column.")
    spectra = []
    seen = {}
    for name, y in zip(names, ys):
        ok = np.isfinite(y)
        if ok.sum() < 2:
            notes.append(f"“{name}” left out (fewer than 2 numbers).")
            continue
        xs, ysel = x[ok], y[ok]
        if xs[0] > xs[-1]:
            xs, ysel = xs[::-1], ysel[::-1]
        n = seen.get(name, 0)
        seen[name] = n + 1
        spectra.append((name if n == 0 else f"{name} ({n + 1})",
                        np.array(xs, float), np.array(ysel, float)))
    if not spectra:
        raise ClipboardTableError("No column has at least 2 numbers.")
    return x_name, spectra, notes
