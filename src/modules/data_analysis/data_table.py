# src/modules/data_analysis/data_table.py
"""Analysis & Visualization -> Data Analysis -> Data table (Qt-free part).

The selected spectra as a spreadsheet: x, then one column per spectrum,
named sp1, sp2, ... as in the Spectral Calculator (short names are easier to
type than spectrum names). New columns f1, f2, ... are calculated from a
formula, e.g. ``sp1 / sp2``, ``log10(sp3)`` or ``sp1 - mean(all)``, with the
Spectral Calculator's safe formula engine and functions (the formula is
parsed, never run as Python code), including ``x`` and the functions across
spectra (mean, median, std, sum, minimum, maximum). Formula columns can then be added to the spectra
list as new spectra - one step in the Operations History. The measured
values themselves are never changed here.

Formulas need one common x-axis. Spectra with different x-axes are still
shown (each with its own x column), but formulas are then unavailable.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from src.modules.data_analysis.spectral_calculator_manager import (
    ACROSS_SPECTRA, FormulaSecurityError, SpectralCalculatorManager, _SafeFormulaEvaluator)
from src.modules.utils.spectra_validation import axes_match

EXCEL_MAX_ROWS = 1_048_576
EXCEL_MAX_COLUMNS = 16_384


FUNCTION_HELP = [
    ('sp1 / sp2', 'Divide two spectra point by point'),
    ('sp1 - sp2, sp1 / sp2', 'Several formulas at once: separated by commas, one column each'),
    ('2 * sp1 + 0.5', 'Numbers and + - * / ** (power)'),
    ('sp1 - mean(all)', 'Each point minus the mean spectrum'),
    ('f1 * 100', 'Formula columns can be used too'),
] + [(name, text) for name, text in SpectralCalculatorManager.available_functions()]


@dataclass
class TableColumn:
    name: str                      # 'sp1', 'f2', 'x', 'x3'
    title: str                     # spectrum name or the formula / chosen name
    values: np.ndarray
    kind: str = 'spectrum'         # 'x', 'spectrum' or 'formula'
    formula: str = ''
    source: Optional[dict] = None  # the spectrum dict (spectrum columns)


@dataclass
class DataTable:
    """The table of the selected spectra (and the formula columns)."""
    spectra: List[dict]
    shared_x: bool = True
    columns: List[TableColumn] = field(default_factory=list)

    @classmethod
    def from_spectra(cls, spectra):
        spectra = list(spectra)
        xs = [np.asarray(s['x_scale'], float) for s in spectra]
        shared = bool(spectra) and all(len(x) == len(xs[0]) and axes_match(xs[0], x) for x in xs[1:])
        table = cls(spectra, shared)
        if shared:
            table.columns.append(TableColumn('x', 'x', xs[0].copy(), 'x'))
            for i, s in enumerate(spectra, 1):
                table.columns.append(TableColumn(f'sp{i}', str(s.get('label', f'sp{i}')),
                                                 np.asarray(s['y_scale'], float), 'spectrum',
                                                 source=s))
        else:
            for i, (s, x) in enumerate(zip(spectra, xs), 1):
                table.columns.append(TableColumn(f'x{i}', f"x of sp{i}", x.copy(), 'x'))
                table.columns.append(TableColumn(f'sp{i}', str(s.get('label', f'sp{i}')),
                                                 np.asarray(s['y_scale'], float), 'spectrum',
                                                 source=s))
        return table

    # -- shape
    @property
    def n_rows(self):
        return max((len(c.values) for c in self.columns), default=0)

    @property
    def x(self):
        return self.columns[0].values if self.shared_x and self.columns else None

    def spectrum_columns(self):
        return [c for c in self.columns if c.kind == 'spectrum']

    def formula_columns(self):
        return [c for c in self.columns if c.kind == 'formula']

    def column(self, name):
        return next((c for c in self.columns if c.name == name), None)

    def value(self, row, col):
        """The number in a cell, or None (a spectrum shorter than the table)."""
        values = self.columns[col].values
        if row >= len(values):
            return None
        return float(values[row])

    # -- formulas
    def next_formula_name(self):
        used = [int(c.name[1:]) for c in self.formula_columns()]
        return f'f{max(used, default=0) + 1}'

    def evaluate(self, formula):
        """The values of *formula* (one per row of the table)."""
        formula = (formula or '').strip()
        if not formula:
            raise ValueError("Type a formula, e.g. sp1 / sp2.")
        if not self.shared_x:
            raise ValueError(
                "The selected spectra have different x-axes, so their points do not "
                "line up row by row. Bring them onto one x-axis first: Spectra processing "
                "› Data range with 'Apply linearization' (the same step for all of them).")
        names = {'x': self.x}
        for c in self.columns:
            if c.kind in ('spectrum', 'formula'):
                names[c.name] = c.values
        names['all'] = [c.values for c in self.spectrum_columns()]
        functions = {k: v for k, v in SpectralCalculatorManager.SAFE_FUNCTIONS.items()
                     if k not in ('pi', 'e')}
        x = self.x
        functions['derivative'] = lambda y: np.gradient(y, x)
        functions['second_deriv'] = lambda y: np.gradient(np.gradient(y, x), x)
        functions.update(ACROSS_SPECTRA)
        constants = {'pi': np.pi, 'e': np.e}
        try:
            result = _SafeFormulaEvaluator(names, functions, constants).evaluate(formula)
        except FormulaSecurityError:
            raise
        except ValueError as exc:
            raise ValueError(_plain_error(str(exc))) from exc
        except Exception as exc:                       # e.g. shapes that do not fit
            raise ValueError(f"The formula could not be calculated: {exc}") from exc
        if isinstance(result, (list, tuple)):
            if re.fullmatch(r'\s*all\s*', formula):
                raise ValueError("'all' stands for all spectrum columns together; use it inside a "
                                 "function, e.g. mean(all) or std(all).")
            raise ValueError("The formula gives several results; separate the formulas with "
                             "commas (each becomes its own column).")
        result = np.asarray(result, dtype=float)
        if result.ndim == 0:                           # a single number: the same in every row
            result = np.full(len(x), float(result))
        if result.shape != x.shape:
            raise ValueError(f"The formula gives {result.size} values for {x.size} rows.")
        return result

    def add_formula(self, formula, title=''):
        """Calculate *formula* and add it as the next column f1, f2, ..."""
        with np.errstate(all='ignore'):
            values = self.evaluate(formula)
        name = self.next_formula_name()
        col = TableColumn(name, (title or '').strip() or formula.strip(), values, 'formula',
                          formula=formula.strip())
        self.columns.append(col)
        return col

    def add_formulas(self, text, title=''):
        """Several formulas separated by commas (``sp1 / sp2, log10(sp3)``) give
        one column each; *title* names them (with _1, _2, ... when several).
        Nothing is added when one of them fails."""
        parts = split_formulas(text)
        added = []
        try:
            for k, part in enumerate(parts, 1):
                name = (f"{title.strip()}_{k}" if title.strip() and len(parts) > 1 else title)
                try:
                    added.append(self.add_formula(part, name))
                except ValueError as exc:
                    raise ValueError(f"{part}: {exc}" if len(parts) > 1 else str(exc)) from exc
        except ValueError:
            for col in added:
                self.columns.remove(col)
            raise
        return added

    def remove_column(self, name):
        """Remove a formula column (and nothing else); False when another
        formula column uses it."""
        col = self.column(name)
        if col is None or col.kind != 'formula':
            return False
        users = [c.name for c in self.formula_columns()
                 if c is not col and re.search(rf'\b{name}\b', c.formula)]
        if users:
            raise ValueError(f"{name} is used by {', '.join(users)}; remove that column first.")
        self.columns.remove(col)
        return True

    def used_spectrum_names(self, formula):
        """{'sp1': spectrum name, ...} of the columns a formula (and the formula
        columns it uses) refers to."""
        out, seen, todo = {}, set(), [formula]
        while todo:
            f = todo.pop()
            if re.search(r'\ball\b', f):
                for c in self.spectrum_columns():
                    out[c.name] = c.title
            for m in re.finditer(r'\b((?:sp|f)[1-9]\d*)\b', f):
                c = self.column(m.group(1))
                if c is None or c.name in seen:
                    continue
                seen.add(c.name)
                if c.kind == 'spectrum':
                    out[c.name] = c.title
                elif c.kind == 'formula':
                    todo.append(c.formula)
        return dict(sorted(out.items(), key=lambda kv: int(kv[0][2:])))

    # -- copy and export
    def header(self):
        return [c.name if c.kind == 'x' else f"{c.name}: {c.title}" for c in self.columns]

    def rows_as_text(self, rows=None, cols=None, with_header=True):
        """Tab-separated text for the clipboard (Excel pastes it into cells)."""
        rows = range(self.n_rows) if rows is None else rows
        cols = range(len(self.columns)) if cols is None else cols
        lines = []
        if with_header:
            head = self.header()
            lines.append('\t'.join(head[c] for c in cols))
        for r in rows:
            cells = []
            for c in cols:
                v = self.value(r, c)
                cells.append('' if v is None or not np.isfinite(v) else repr(v))
            lines.append('\t'.join(cells))
        return '\n'.join(lines) + '\n'

    def to_frame(self):
        import pandas as pd
        n = self.n_rows
        data = {}
        for head, c in zip(self.header(), self.columns):
            v = np.full(n, np.nan)
            v[:len(c.values)] = c.values
            data[head] = v
        return pd.DataFrame(data)

    def excel_fits(self):
        return self.n_rows + 1 <= EXCEL_MAX_ROWS and len(self.columns) <= EXCEL_MAX_COLUMNS

    def export(self, path):
        """Save the whole table: .xlsx (Excel) or .csv / .txt."""
        frame = self.to_frame()
        if path.lower().endswith('.xlsx'):
            if not self.excel_fits():
                raise ValueError(
                    f"The table has {len(self.columns)} columns; Excel allows at most "
                    f"{EXCEL_MAX_COLUMNS}. Save it as CSV instead.")
            frame.to_excel(path, index=False, sheet_name='Data table')
        else:
            sep = '\t' if path.lower().endswith('.txt') else ','
            frame.to_csv(path, index=False, sep=sep)

    # -- new spectra
    def new_spectra(self, columns=None):
        """Spectrum dicts for formula columns (all of them by default). Every
        value must be a number: a column with undefined values (log of a
        negative number, division by zero) is refused with the reason."""
        from datetime import datetime
        from src.modules.utils.correction_history import append_correction_history
        out = []
        for col in (columns or self.formula_columns()):
            bad = ~np.isfinite(col.values)
            if bad.any():
                xs = self.x[bad]
                shown = ', '.join(f'{v:.4g}' for v in xs[:5]) + (', …' if len(xs) > 5 else '')
                raise ValueError(
                    f"{col.name} ({col.formula}) is undefined at {int(bad.sum())} of "
                    f"{len(col.values)} points (x = {shown}) — e.g. log or sqrt of zero or "
                    "negative values, or division by zero. Change the formula (e.g. use abs(), "
                    "or an offset) or restrict the x-range first (Data range).")
            used = self.used_spectrum_names(col.formula)
            entry = {'formula': col.formula, 'column': col.name, 'columns': used,
                     'source_spectra': list(used.values())}
            meta = {'creation_method': 'data_table', 'formula': col.formula,
                    'formula_columns': used, 'source_spectra': list(used.values()),
                    'creation_timestamp': datetime.now().isoformat()}
            meta['correction_history'] = append_correction_history(None, 'Data table', entry)
            out.append({'x_scale': self.x.copy(), 'y_scale': col.values.copy(),
                        'label': col.title, 'metadata': meta})
        return out


def split_formulas(text):
    """'sp1 / sp2, mean(sp1, sp2)' -> ['sp1 / sp2', 'mean(sp1, sp2)']: commas inside
    brackets belong to a function call. A leading '=' (typed as in Excel:
    '=b1*2') is left out - the field is already labelled "New column =". """
    text = _without_equals(text)
    if len(text) > 1 and text[0] + text[-1] in ('[]', '()') and _matching_end(text):
        inner = text[1:-1]
        if len(split_formulas(inner)) > 1:            # [sp1 - sp2, sp1 + sp2] as in the Calculator
            text = inner
    parts, depth, cur = [], 0, ''
    for ch in text:
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur.strip())
            cur = ''
        else:
            cur += ch
    parts.append(cur.strip())
    parts = [_without_equals(p) for p in parts]
    parts = [p for p in parts if p]
    return parts or ['']


def _without_equals(text):
    """'=b1*2' -> 'b1*2' (one '=' at the start, as typed in Excel)."""
    text = (text or '').strip()
    return text[1:].strip() if text.startswith('=') and not text.startswith('==') else text


def _matching_end(text):
    """True when the bracket opening *text* closes at its very end."""
    depth = 0
    for i, ch in enumerate(text):
        depth += ch in '(['
        depth -= ch in ')]'
        if depth == 0:
            return i == len(text) - 1
    return False


def _plain_error(text):
    return text.replace("not a selected spectrum alias or a recognised constant",
                        "use sp1, sp2, … (spectra), f1, f2, … (formula columns), x, all, "
                        "pi or e")
