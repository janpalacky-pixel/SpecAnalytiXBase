"""A formula typed as in Excel, with '=' at the start ('=b8*2'), works in the
Data table (the field is labelled "New column =" already) - before, it gave
"Formula syntax error"."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from src.modules.data_analysis.data_table import split_formulas
from src.modules.data_analysis.value_table import ValueTable
from tests.test_value_table import _spectra


def test_a_leading_equals_is_left_out():
    assert split_formulas('=b8*2') == ['b8*2']
    assert split_formulas(' = sp1 - sp2 ') == ['sp1 - sp2']
    assert split_formulas('=sp1 - sp2, =mean(sp1, sp2)') == ['sp1 - sp2', 'mean(sp1, sp2)']
    assert split_formulas('sp1 / sp2') == ['sp1 / sp2']


def test_values_per_spectrum_formula_with_equals():
    t = ValueTable.from_spectra(_spectra())
    v1 = t.add_value({'kind': 'max', 'range_a': (30, 70)})
    f = t.add_formulas('=v1*2')[0]
    assert f.formula == 'v1*2' and f.name == 'f1'
    assert np.allclose(f.values, 2 * v1.values, equal_nan=True)
