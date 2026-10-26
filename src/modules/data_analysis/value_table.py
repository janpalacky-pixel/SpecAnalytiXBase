# src/modules/data_analysis/value_table.py
"""The Data table's second tab, "Values per spectrum" (Qt-free): one row per
selected spectrum - sp1, sp2, ... with its name, the numbers stored with it
(e.g. temperature_C) and the number(s) in its name - plus columns of values
chosen by the user (v1, v2, ...: area or mean over a range, maximum, peak
position, FWHM, fitted peak values, intensity at x, two bands combined, PCA /
SVD score), computed exactly as in Group Statistics (group_values.py), the
bands of the Peak list (b1, b2, ...: e.g. the height of each band, sent from
its Band table), and formula columns (f1, f2, ...: e.g. v1 / v2). Any two columns can be plotted
against each other (e.g. area against temperature)."""

import re
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from src.modules.data_analysis.spectral_calculator_manager import (
    ACROSS_SPECTRA, FormulaSecurityError, SpectralCalculatorManager, _SafeFormulaEvaluator)
from src.modules.visualization import color_by_value as cbv
from src.modules.visualization_analysis import group_values as gv

# Values a column can hold: Group Statistics' values without the ones that
# need groups (correlation with / distance from a reference group).
VALUE_SECTIONS = [(title, [(k, t) for k, t in items if k not in ('corr_ref', 'dist_ref')])
                  for title, items in gv.VALUE_SECTIONS]

_IDENT = re.compile(r'[^A-Za-z0-9_]')


@dataclass
class ValueColumn:
    name: str                # 'name', 'temperature_C', 'n1', 'v2', 'f1'
    title: str               # shown under the name
    values: np.ndarray       # float (NaN = no value); text for 'name'
    kind: str                # 'name', 'metadata', 'number', 'value', 'band', 'formula'
    settings: Optional[dict] = None
    formula: str = ''


@dataclass
class ValueTable:
    spectra: List[dict]
    columns: List[ValueColumn] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @classmethod
    def from_spectra(cls, spectra):
        t = cls(list(spectra))
        t.columns.append(ValueColumn('name', 'Spectrum', np.array(
            [str(s.get('label', '')) for s in t.spectra], dtype=object), 'name'))
        for key in cbv.metadata_keys(t.spectra):
            name = _IDENT.sub('_', key)
            if name[0].isdigit():
                name = '_' + name
            vals = cbv.values(t.spectra, {'mode': 'metadata', 'metadata_key': key})
            t.columns.append(ValueColumn(name, 'stored with the spectrum', _floats(vals), 'metadata'))
        most = max((len(cbv.numbers_in(s.get('label', ''))) for s in t.spectra), default=0)
        for i in range(min(most, 3)):
            vals = cbv.values(t.spectra, {'mode': 'name', 'number': i})
            t.columns.append(ValueColumn(f'n{i + 1}', f'number {i + 1} in the name',
                                         _floats(vals), 'number'))
        return t

    # -- shape
    @property
    def n_rows(self):
        return len(self.spectra)

    def row_names(self):
        return [f'sp{i + 1}' for i in range(self.n_rows)]

    def column(self, name):
        return next((c for c in self.columns if c.name == name), None)

    def numeric_columns(self):
        return [c for c in self.columns if c.kind != 'name']

    def value(self, row, col):
        v = self.columns[col].values[row]
        return v if self.columns[col].kind == 'name' else float(v)

    def _next(self, prefix):
        used = [int(c.name[1:]) for c in self.columns
                if c.name[:1] == prefix and c.name[1:].isdigit() and c.kind in ('value', 'band', 'formula')]
        return f'{prefix}{max(used, default=0) + 1}'

    # -- value columns
    def add_value(self, settings, fit_settings=None, progress=None):
        """A column of one value per spectrum (Group Statistics' values)."""
        s = dict(gv.DEFAULT_SETTINGS)
        s.update(settings or {})
        if s['kind'] in ('corr_ref', 'dist_ref'):
            raise ValueError("Values compared with a reference group are in Group Statistics.")
        groups = ['all'] * self.n_rows                 # whole-spectrum values: one group
        vals, info = gv.compute_values(self.spectra, groups, s, fit_settings, progress=progress)
        col = ValueColumn(self._next('v'), gv.value_label(s), np.asarray(vals, dtype=float),
                          'value', settings=s)
        self.columns.append(col)
        if info.get('note'):
            self.notes.append(f"{col.name}: {info['note']}")
        return col

    def add_bands(self, value_name, bands):
        """Columns b1, b2, ... from the Peak list's Band table: bands =
        [(position text, [value or None per spectrum, in this table's
        order])], value_name e.g. 'Height (y)'. A spectrum without a peak in
        a band gets no value."""
        what = value_name.split(' (')[0]
        added = []
        for position, values in bands:
            if len(values) != self.n_rows:
                raise ValueError("The Peak list has other spectra than this table.")
            col = ValueColumn(self._next('b'), f"{what} of the band at {position}",
                              _floats(values), 'band')
            self.columns.append(col)
            added.append(col)
        return added

    # -- formula columns
    def add_formula(self, formula, title=''):
        formula = (formula or '').strip()
        if not formula:
            raise ValueError("Type a formula, e.g. v1 / v2.")
        names = {c.name: c.values.astype(float) for c in self.numeric_columns()}
        names['row'] = np.arange(1, self.n_rows + 1, dtype=float)
        functions = {k: v for k, v in SpectralCalculatorManager.SAFE_FUNCTIONS.items()
                     if k not in ('pi', 'e', 'derivative', 'second_deriv', 'cumsum', 'normalise',
                                  'snv')}
        functions.update(ACROSS_SPECTRA)
        # Spectra without a value (NaN) do not spoil a whole column: max_val(v1)
        # is the largest value there is.
        functions.update({'mean_val': np.nanmean, 'sum_val': np.nansum, 'min_val': np.nanmin,
                          'max_val': np.nanmax})
        try:
            with np.errstate(all='ignore'):
                result = _SafeFormulaEvaluator(names, functions,
                                               {'pi': np.pi, 'e': np.e}).evaluate(formula)
        except FormulaSecurityError:
            raise
        except ValueError as exc:
            raise ValueError(str(exc).replace(
                "not a selected spectrum alias or a recognised constant",
                "use the column names: " + ', '.join(c.name for c in self.numeric_columns())
                + ", row, pi or e")) from exc
        except Exception as exc:
            raise ValueError(f"The formula could not be calculated: {exc}") from exc
        if isinstance(result, (list, tuple)):
            raise ValueError("Write one formula per column.")
        result = np.asarray(result, dtype=float)
        if result.ndim == 0:
            result = np.full(self.n_rows, float(result))
        if result.shape != (self.n_rows,):
            raise ValueError(f"The formula gives {result.size} values for {self.n_rows} rows.")
        col = ValueColumn(self._next('f'), (title or '').strip() or formula, result, 'formula',
                          formula=formula)
        self.columns.append(col)
        return col

    def add_formulas(self, text, title=''):
        from src.modules.data_analysis.data_table import split_formulas
        parts = split_formulas(text)
        added = []
        try:
            for k, part in enumerate(parts, 1):
                name = f"{title.strip()}_{k}" if title.strip() and len(parts) > 1 else title
                added.append(self.add_formula(part, name))
        except ValueError:
            for col in added:
                self.columns.remove(col)
            raise
        return added

    def remove_column(self, name):
        col = self.column(name)
        if col is None or col.kind not in ('value', 'band', 'formula'):
            return False
        users = [c.name for c in self.columns
                 if c.kind == 'formula' and c is not col and re.search(rf'\b{name}\b', c.formula)]
        if users:
            raise ValueError(f"{name} is used by {', '.join(users)}; remove that column first.")
        self.columns.remove(col)
        return True

    # -- copy, export, plot
    def header(self):
        return ['sp'] + [c.title if c.kind == 'name' else c.name if c.kind == 'metadata'
                         else f"{c.name}: {c.title}" for c in self.columns]

    def rows_as_text(self, rows=None, cols=None, with_header=True):
        rows = range(self.n_rows) if rows is None else rows
        cols = range(len(self.columns)) if cols is None else cols
        head = self.header()
        lines = ['\t'.join([head[0]] + [head[c + 1] for c in cols])] if with_header else []
        names = self.row_names()
        for r in rows:
            cells = [names[r]]
            for c in cols:
                v = self.value(r, c)
                cells.append(v if isinstance(v, str) else ('' if not np.isfinite(v) else repr(v)))
            lines.append('\t'.join(cells))
        return '\n'.join(lines) + '\n'

    def to_frame(self):
        import pandas as pd
        data = {'sp': self.row_names()}
        for head, c in zip(self.header()[1:], self.columns):
            data[head] = c.values
        return pd.DataFrame(data)

    def export(self, path):
        frame = self.to_frame()
        if path.lower().endswith('.xlsx'):
            frame.to_excel(path, index=False, sheet_name='Values per spectrum')
        else:
            frame.to_csv(path, index=False, sep='\t' if path.lower().endswith('.txt') else ',')

    def xy(self, x_name, y_name):
        """(x, y, labels) of the rows where both columns have a number."""
        cx, cy = self.column(x_name), self.column(y_name)
        if cx is None or cy is None or 'name' in (cx.kind, cy.kind):
            raise ValueError("Choose two columns with numbers.")
        x, y = cx.values.astype(float), cy.values.astype(float)
        ok = np.isfinite(x) & np.isfinite(y)
        labels = [s.get('label', '') for s, k in zip(self.spectra, ok) if k]
        return x[ok], y[ok], labels


def _floats(vals):
    return np.array([np.nan if v is None else float(v) for v in vals], dtype=float)
