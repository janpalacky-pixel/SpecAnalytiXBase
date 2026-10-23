"""Melting Curve Analysis: "X from:" - the temperatures come from a value
stored with the spectra (e.g. temperature_C of a JASCO scan, or set in
Spectrum properties) or from the numbers in the names."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def _spectra(with_temperature=True):
    x = np.linspace(220, 320, 101)
    out = []
    for i, t in enumerate((20.0, 35.5, 50.0, 64.5, 80.0)):
        md = {'temperature_C': t} if with_temperature else {}
        md['scan'] = 100 + i
        out.append({'label': f'sample_7 : run {i + 1}', 'x_scale': x,
                    'y_scale': np.exp(-((x - 260) / 10) ** 2) / (1 + np.exp((t - 50) / 5)),
                    'metadata': md})
    return out


def _x_column(d):
    return [float(d.temps_table.item(r, 1).text()) for r in range(d.temps_table.rowCount())]


def test_a_stored_temperature_is_used_first():
    from src.views.dialogs.visualization_analysis.melting_curve_dialog import MeltingCurveDialog
    d = MeltingCurveDialog(None, _spectra())
    assert d.temps_from_combo.currentData() == 'temperature_C'
    assert [d.temps_from_combo.itemText(i) for i in range(d.temps_from_combo.count())] == \
        ['the names', 'the second number in the names (1, 2, 3, \u2026)',
         'temperature_C (stored)', 'scan (stored)']
    assert sorted(_x_column(d)) == [20.0, 35.5, 50.0, 64.5, 80.0]
    d.temps_from_combo.setCurrentIndex(0)                       # the names: run 1, 2, ...
    assert sorted(_x_column(d)) == [1.0, 2.0, 3.0, 4.0, 5.0]
    d.temps_from_combo.setCurrentIndex(d.temps_from_combo.findData('scan'))
    assert sorted(_x_column(d)) == [100.0, 101.0, 102.0, 103.0, 104.0]
    assert d.get_results()['temps_from'] == 'scan'


def test_without_stored_values_the_names_as_before():
    from src.views.dialogs.visualization_analysis.melting_curve_dialog import MeltingCurveDialog
    spectra = _spectra(with_temperature=False)
    for s in spectra:
        s['metadata'] = {}
    d = MeltingCurveDialog(None, spectra)
    assert d.temps_from_combo.currentData() is None and d.temps_from_combo.isEnabled()
    assert d.temps_from_combo.count() == 2       # the names, the second number in the names
    assert sorted(_x_column(d)) == [1.0, 2.0, 3.0, 4.0, 5.0]
