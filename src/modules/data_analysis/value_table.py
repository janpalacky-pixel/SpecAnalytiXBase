# src/modules/data_analysis/value_table.py
"""The Data table's second tab, "Values per spectrum" (Qt-free): one row per
selected spectrum - sp1, sp2, ... with its name, the numbers stored with it
(e.g. temperature_C) and the number(s) in its name - plus columns of values
chosen by the user (v1, v2, ...: area or mean over a range, maximum, peak
position, FWHM, fitted peak values, intensity at x, two bands combined, PCA /
SVD score), computed exactly as in Group Statistics (group_values.py), the
bands of the Peak list (b1, b2, ...: e.g. the height of each band, sent from
its Band table), the results of Peak Fitting for a series (p1, p2, ...), and
formula columns (f1, f2, ...: e.g. v1 / v2). Any two columns can be plotted
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
# columns of fixed numbers sent from another window (Peak list bands, a
# Peak Fitting series); removed like value columns
FIXED_KINDS = ('band', 'fit')


@dataclass
class ValueColumn:
    name: str                # 'name', 'temperature_C', 'n1', 'v2', 'f1'
    title: str               # shown under the name
    values: np.ndarray       # float (NaN = no value); text for 'name'
    kind: str                # 'name', 'metadata', 'number', 'value', 'band', 'fit', 'formula'
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
        # every number written in the names (n1 = the first, ...); a number that
        # is the same in all names (e.g. the "2" of raman_2comp) says nothing
        # and is left out, as in the Peak list
        most = max((len(cbv.numbers_in(s.get('label', ''))) for s in t.spectra), default=0)
        for i in range(most):
            vals = _floats(cbv.values(t.spectra, {'mode': 'name', 'number': i}))
            if len(vals) > 1 and np.all(np.isfinite(vals)) and np.all(vals == vals[0]):
                continue
            t.columns.append(ValueColumn(f'n{i + 1}', f'number {i + 1} in the name', vals,
                                         'number'))
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
                if c.name[:1] == prefix and c.name[1:].isdigit() and c.kind in ('value', 'formula') + FIXED_KINDS]
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
        return self.add_fixed('b', [(f"{what} of the band at {position}", values)
                                    for position, values in bands], 'band')

    def add_fixed(self, prefix, items, kind='fit'):
        """Columns prefix1, prefix2, ... of fixed numbers sent from another
        window: items = [(title, [value or None per spectrum, in this table's
        order])]."""
        if any(len(values) != self.n_rows for _, values in items):
            raise ValueError("That window has other spectra than this table.")
        added = []
        for title, values in items:
            col = ValueColumn(self._next(prefix), title, _floats(values), kind)
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
        if col is None or col.kind not in ('value', 'formula') + FIXED_KINDS:
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

    ROW = 'row'          # x = the place of the spectrum in the table (1, 2, 3, ...)

    def _numbers(self, name):
        if name == self.ROW:
            return np.arange(1, self.n_rows + 1, dtype=float)
        col = self.column(name)
        if col is None or col.kind == 'name':
            raise ValueError("Choose two columns with numbers.")
        return col.values.astype(float)

    def describe(self, name):
        """A column for people: 'temperature_C', 'n1', 'Area over 30–70', 'row'."""
        if name == self.ROW:
            return 'spectrum number (row)'
        col = self.column(name)
        if col is None or col.kind in ('metadata', 'number', 'name'):
            return name
        return col.title or name

    def meaning(self, name):
        """What a column holds, when its name alone does not say it (None
        otherwise): v1 -> 'Maximum over 600–1800', n1 -> 'number 1 in the
        name', a formula column with a name of its own -> that name."""
        if name == self.ROW:
            return 'spectrum number (row)'
        col = self.column(name)
        if col is None or col.kind in ('metadata', 'name'):
            return None
        if col.kind == 'formula' and (not col.title or col.title == col.formula):
            return None                               # the formula says it
        return col.title or None

    def xy(self, x_name, y_name):
        """(x, y, labels) of the rows where both columns have a number;
        x_name may be 'row' (the order of the spectra in the table)."""
        x, y = self._numbers(x_name), self._numbers(y_name)
        ok = np.isfinite(x) & np.isfinite(y)
        labels = [s.get('label', '') for s, k in zip(self.spectra, ok) if k]
        return x[ok], y[ok], labels

    def as_spectrum(self, y_name, x_name):
        """Column y against column x as a new spectrum (e.g. a band's area
        against temperature_C: a melting curve), sorted by x; rows without both
        values are left out. x = 'row': the order of the spectra in the table.
        Returns (spectrum dict, the source spectra). Refused (ValueError) when
        fewer than 2 points remain or an x value occurs twice (a spectrum needs
        each x once)."""
        from datetime import datetime
        from src.modules.utils.correction_history import append_correction_history
        if x_name == y_name:
            raise ValueError(f"Choose two different columns ({y_name} against itself gives only a "
                             "straight line).")
        x, y, _ = self.xy(x_name, y_name)
        xs = self._numbers(x_name)
        ys = self._numbers(y_name)
        ok = np.isfinite(xs) & np.isfinite(ys)
        sources = [s for s, k in zip(self.spectra, ok) if k]
        if len(x) < 2:
            raise ValueError(f"Fewer than 2 spectra have both {x_name} and {y_name}.")
        values, counts = np.unique(x, return_counts=True)
        if np.any(counts > 1):
            same = values[counts > 1][0]
            rows = [f'sp{i + 1}' for i in np.nonzero(xs == same)[0]]
            raise ValueError(
                f"{x_name} has the same value {same:g} more than once ({', '.join(rows[:4])}"
                f"{', …' if len(rows) > 4 else ''}) - a spectrum needs each x once. Choose another "
                "x, e.g. row (the order of the spectra), or select fewer spectra.")
        order = np.argsort(x)
        label = f"{self.describe(y_name)} vs {self.describe(x_name)}"
        # what it was made of, once: y and x, with their meaning when the name
        # alone does not say it (v1 = "Maximum over 600-1800", n1 = "number 1
        # in the name"), the formula of a formula column and only the settings
        # that matter for that value - the spectra it came from are listed
        # once, under source_spectra
        entry = {'y': y_name, 'x': x_name}
        for key, name in (('y', y_name), ('x', x_name)):
            meaning = self.meaning(name)
            if meaning:
                entry[key + '_meaning'] = meaning
            col = self.column(name)
            if col is not None and col.formula:
                entry[key + '_formula'] = col.formula
            if col is not None and col.settings:
                entry[key + '_settings'] = relevant_settings(col.settings)
        meta = {'creation_method': 'data_table_values',
                'source_spectra': [str(s.get('label', '')) for s in sources],
                'creation_timestamp': datetime.now().isoformat()}
        meta['correction_history'] = append_correction_history(None, 'Data table (values)', entry)
        spectrum = {'x_scale': x[order].copy(), 'y_scale': y[order].copy(), 'label': label,
                    'metadata': meta}
        return spectrum, sources


def relevant_settings(settings):
    """Only the settings that matter for this kind of value (as the Add
    value window shows them): e.g. a maximum - its range and how the top is
    taken; not the x of 'Intensity at x' or the bands of 'Two bands'."""
    s = dict(settings)
    k = s.get('kind')
    keep = ['kind']
    if k == 'intensity_at_x':
        keep += ['x0', 'x_mode'] + (['x_halfwidth'] if s.get('x_mode') != 'point' else [])
    elif k in gv.ONE_BAND:
        keep.append('range_a')
    elif k in gv.TWO_BANDS:
        keep += ['range_a', 'metric_a', 'range_b', 'metric_b', 'operation']
    elif k in ('pca', 'svd'):
        keep += ['component', 'whole_use_range'] + (['range_a'] if s.get('whole_use_range') else [])
    if gv.uses_max_mode(s):
        keep.append('max_mode')
    return {key: (list(s[key]) if isinstance(s[key], tuple) else s[key])
            for key in keep if key in s}


def _floats(vals):
    return np.array([np.nan if v is None else float(v) for v in vals], dtype=float)
