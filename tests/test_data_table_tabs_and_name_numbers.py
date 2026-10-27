"""Data table: a line at the top of each tab says what it is for (the tab
names alone are easy to overlook), and Values per spectrum has a column for
every number written in the names - except one that is the same in all."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

from src.modules.data_analysis.value_table import ValueTable

app = QApplication.instance() or QApplication([])


def _spectra(names):
    x = np.linspace(0, 10, 11)
    return [{'label': n, 'x_scale': x, 'y_scale': x * (k + 1), 'metadata': {}}
            for k, n in enumerate(names)]


def test_every_number_of_the_names_but_not_one_that_never_changes():
    t = ValueTable.from_spectra(_spectra([
        'raman_2comp_clean : raman_06_alfa_5_ten_155',
        'raman_2comp_clean : raman_07_alfa_6_ten_160',
        'raman_2comp_clean : raman_08_alfa_7_ten_165']))
    numbers = [c for c in t.columns if c.kind == 'number']
    assert [c.name for c in numbers] == ['n2', 'n3', 'n4']            # the "2" of 2comp: left out
    assert [c.title for c in numbers] == ['number 2 in the name', 'number 3 in the name',
                                          'number 4 in the name']
    assert list(t.column('n4').values) == [155, 160, 165]
    t.add_formula('n4 / n3')                                         # usable in formulas


def test_a_name_with_fewer_numbers_gets_no_value_there():
    t = ValueTable.from_spectra(_spectra(['a_1_2_3_4_5', 'a_2_3', 'b']))
    assert [c.name for c in t.columns if c.kind == 'number'] == ['n1', 'n2', 'n3', 'n4', 'n5']
    assert np.isnan(t.column('n5').values[1]) and np.isnan(t.column('n1').values[2])


def test_one_spectrum_keeps_its_numbers():
    t = ValueTable.from_spectra(_spectra(['TBA_45C : 0003']))
    assert [c.name for c in t.columns if c.kind == 'number'] == ['n1', 'n2']


def test_each_tab_says_what_it_is_for():
    from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
    dlg = DataTableDialog(None, _spectra(['s_1', 's_2']))
    assert 'the spectra themselves' in dlg.points_guide.text()
    assert 'Values per spectrum' in dlg.points_guide.text()
    assert 'Each row is one spectrum' in dlg.values.guide.text()
    assert 'Points (one row per x)' in dlg.values.guide.text()
    top = [w.text() for w in dlg.findChildren(type(dlg.points_guide)) if 'Two tabs' in w.text()]
    assert top and 'one row per spectrum' not in top[0]          # not said twice
