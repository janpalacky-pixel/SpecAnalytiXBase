"""Melting Curve Analysis: "X from:" also offers one particular number of
the names - the first, second, ... or the last (as Line colours by value) -
when it differs between the spectra; a name without that number gives an
empty X cell."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def _spectra(labels):
    x = np.linspace(220, 320, 101)
    return [{'label': lab, 'x_scale': x,
             'y_scale': np.exp(-((x - 260) / 10) ** 2) / (1 + np.exp((i * 10 - 30) / 5)),
             'metadata': {}} for i, lab in enumerate(labels)]


def _dialog(labels):
    from src.views.dialogs.visualization_analysis.melting_curve_dialog import MeltingCurveDialog
    return MeltingCurveDialog(None, _spectra(labels))


def _texts(d):
    return [d.temps_from_combo.itemText(i) for i in range(d.temps_from_combo.count())]


def _x_column(d):
    out = []
    for r in range(d.temps_table.rowCount()):
        item = d.temps_table.item(r, 1)
        out.append(float(item.text()) if item is not None and item.text() else None)
    return out


def test_the_names_of_the_raman_example():
    # the "2" of "2comp" is the same everywhere: not offered; the last
    # number is the second one here: offered once
    d = _dialog([f'raman_2comp_clean : raman_{n}' for n in (10, 11, 12, 13)])
    assert d.temps_from_combo.isEnabled()
    assert _texts(d) == ['the names', 'the second number in the names (10, 11, 12, …)']


def test_choose_which_number_of_the_names():
    labels = ['pH 7 T=20 : 1', 'pH 7 T=40 : 2', 'pH 8 T=60 : 3', 'pH 8 T=80 : 4']
    d = _dialog(labels)
    texts = _texts(d)
    assert texts[0] == 'the names'
    assert any(t.startswith('the first number') for t in texts)     # 7, 8
    assert any(t.startswith('the second number') for t in texts)    # 20 ... 80
    assert any(t.startswith('the third number') for t in texts)     # 1 ... 4
    assert not any(t.startswith('the last number') for t in texts)  # = the third
    second = next(i for i, t in enumerate(texts) if t.startswith('the second number'))
    d.temps_from_combo.setCurrentIndex(second)
    assert _x_column(d) == [20.0, 40.0, 60.0, 80.0]
    third = next(i for i, t in enumerate(texts) if t.startswith('the third number'))
    d.temps_from_combo.setCurrentIndex(third)
    assert _x_column(d) == [1.0, 2.0, 3.0, 4.0]
    assert d.get_results()['temps_from'] == d.temps_from_combo.currentData()


def test_a_name_without_that_number_gets_an_empty_cell():
    labels = ['run 1 T=20', 'run 2 T=40', 'run 3', 'run 4 T=80']
    d = _dialog(labels)
    texts = _texts(d)
    second = next(i for i, t in enumerate(texts) if t.startswith('the second number'))
    d.temps_from_combo.setCurrentIndex(second)
    assert _x_column(d) == [20.0, 40.0, None, 80.0]
    note = d.temps_missing_label.text()
    assert 'No second number in the name' in note and 'run 3' in note
