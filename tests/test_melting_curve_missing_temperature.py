"""Melting Curve Analysis: a spectrum without a temperature gets an EMPTY X
cell - never a number guessed from its name (when a stored value is chosen
in "X from") or its position in the list. The orange note under the table
names it, no curve is drawn until it has one, and no warning box pops up;
typing the temperature draws the curve."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])


@pytest.fixture
def boxes(monkeypatch):
    shown = []
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(
            lambda *a, **k: shown.append(a[1:3]) or QMessageBox.Ok))
    return shown


def _spectra(temps, labels=None):
    x = np.linspace(220, 320, 101)
    out = []
    for i, t in enumerate(temps):
        md = {} if t is None else {'temperature_C': t}
        label = labels[i] if labels else f'sample_7 : run {i + 1}'
        out.append({'label': label, 'x_scale': x, 'metadata': md,
                    'y_scale': np.exp(-((x - 260) / 10) ** 2) / (1 + np.exp(((t or 50) - 50) / 5))})
    return out


def _x(d):
    return [d.temps_table.item(r, 1).text() for r in range(d.temps_table.rowCount())]


def test_a_missing_stored_temperature_stays_empty(boxes):
    from src.views.dialogs.visualization_analysis.melting_curve_dialog import MeltingCurveDialog
    d = MeltingCurveDialog(None, _spectra([20.0, 35.0, None, 65.0, 80.0]))
    assert d.temps_from_combo.currentData() == 'temperature_C'
    assert _x(d).count('') == 1 and '3' not in _x(d)                 # not "run 3" from the name
    assert d.temps_missing_label.isVisibleTo(d)
    assert 'No temperature_C stored for 1' in d.temps_missing_label.text()
    assert 'run 3' in d.temps_missing_label.text()
    assert d.curve is None and not boxes                             # no curve, no warning box
    row = _x(d).index('')
    d.temps_table.item(row, 1).setText('50')                         # typed in
    assert not d.temps_missing_label.isVisibleTo(d)
    assert d.curve is not None and len(d.curve['x_temperature']) == 5
    assert not boxes


def test_names_without_numbers_stay_empty(boxes):
    from src.views.dialogs.visualization_analysis.melting_curve_dialog import MeltingCurveDialog
    names = ['alpha', 'beta', 'gamma']
    d = MeltingCurveDialog(None, _spectra([None, None, None], labels=names))
    assert d.temps_from_combo.currentData() is None
    assert _x(d) == ['', '', '']                                     # not 0, 1, 2 (positions)
    assert 'No temperature in the name for 3' in d.temps_missing_label.text()
    assert d.curve is None and not boxes
