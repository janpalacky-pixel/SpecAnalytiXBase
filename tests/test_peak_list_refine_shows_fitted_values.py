"""Peak list: ticking Refine by fitting switches the Plot and the Band table
to the fitted values at once (Position (x) -> Fitted position, Height (y) ->
Fitted height, FWHM -> Fitted FWHM) and back when it is unticked; the
drop-down lists are wide enough for the longer fitted names."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QComboBox

from src.modules.data_analysis import peak_list as pl

app = QApplication.instance() or QApplication([])


def _series():
    x = np.linspace(400, 1800, 701)
    out = []
    for i, shift in enumerate((0.0, 0.7, 1.4)):
        y = (1.0 * np.exp(-0.5 * ((x - 800 - shift) / 12) ** 2)
             + 0.6 * np.exp(-0.5 * ((x - 1300 + shift) / 20) ** 2))
        out.append({'x_scale': x, 'y_scale': y, 'label': f'sp{i + 1}', 'metadata': {}})
    return out


@pytest.mark.parametrize('measured, fitted', [
    ('Position (x)', 'Fitted position'), ('Height (y)', 'Fitted height'),
    ('FWHM', 'Fitted FWHM')])
def test_matching_value(measured, fitted):
    assert pl.matching_value(measured, True) == fitted
    assert pl.matching_value(fitted, False) == measured


def test_other_values_stay():
    assert pl.matching_value('Prominence', True) == 'Prominence'
    assert pl.matching_value('Fitted area', False) == 'Fitted area'   # not offered: the 1st


@pytest.fixture
def dlg():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    d = PeakListDialog(None, _series(), threshold=0.1, prominence=0.1, distance=0.01)
    d.show()
    app.processEvents()
    yield d
    d.close()


def _band_values(d):
    t = d.band_table_widget
    return [float(t.item(0, c).text()) for c in range(1, t.columnCount())]


def test_ticking_shows_the_fitted_values(dlg):
    dlg.tabs.setCurrentIndex(2)
    dlg.band_value_combo.setCurrentText('FWHM')
    dlg.y_combo.setCurrentText('Position (x)')
    app.processEvents()
    measured = _band_values(dlg)
    dlg.refine_check.setChecked(True)
    app.processEvents()
    assert dlg.band_value_combo.currentText() == 'Fitted FWHM'
    assert dlg.y_combo.currentText() == 'Fitted position'
    fitted = _band_values(dlg)
    assert fitted == pytest.approx([2.3548 * 12, 2.3548 * 20], rel=0.02)   # the true widths
    assert fitted != measured
    assert 'Shown: the fitted values' in dlg.fit_info.text()
    dlg.refine_check.setChecked(False)
    app.processEvents()
    assert dlg.band_value_combo.currentText() == 'FWHM'
    assert dlg.y_combo.currentText() == 'Position (x)'
    assert _band_values(dlg) == pytest.approx(measured)


def test_a_value_without_a_fitted_one_stays(dlg):
    dlg.band_value_combo.setCurrentText('Prominence')
    dlg.refine_check.setChecked(True)
    app.processEvents()
    assert dlg.band_value_combo.currentText() == 'Prominence'


def test_the_lists_are_wide_enough_for_the_fitted_names(dlg):
    dlg.refine_check.setChecked(True)
    app.processEvents()
    for combo in (dlg.band_value_combo, dlg.x_combo, dlg.y_combo):
        assert combo.sizeAdjustPolicy() == QComboBox.AdjustToContents
    dlg.tabs.setCurrentIndex(2)
    app.processEvents()
    combo = dlg.band_value_combo
    combo.setCurrentText('Fitted position')
    app.processEvents()
    widest = max(combo.fontMetrics().horizontalAdvance(combo.itemText(i))
                 for i in range(combo.count()))
    assert combo.width() >= widest
