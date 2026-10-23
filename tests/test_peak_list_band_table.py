"""Peak list > tab Band table: the peak list turned round for Excel - one row
per spectrum, one column per band (peaks of all spectra at the same
position), holding the chosen value; stored values (e.g. temperature_C)
before the bands; Copy and Export take it when its tab is open."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def _series():
    """Six spectra (temperature_C 20 ... 70) with bands near 30, 50 and 70;
    the band at 30 disappears from the 4th spectrum on; the band at 50
    shifts a little and grows."""
    x = np.linspace(0, 100, 501)
    out = []
    for i in range(6):
        y = (1 + 0.1 * i) * np.exp(-((x - 50 - 0.2 * i) / 2) ** 2) + 0.8 * np.exp(-((x - 70) / 2) ** 2)
        if i < 3:
            y = y + 0.6 * np.exp(-((x - 30) / 2) ** 2)
        out.append({'label': f'scan : {i + 1:02d}', 'x_scale': x, 'y_scale': y,
                    'metadata': {'temperature_C': 20.0 + 10 * i}})
    return out


def test_band_table():
    from src.modules.data_analysis import peak_list as pl
    sp = _series()
    rows, index = pl.peak_table_with_index(sp, threshold=0.1, prominence=0.1, distance=0.01)
    columns, table, merged = pl.band_table(rows, index, sp, 'Height (y)', 5.0, ['temperature_C'])
    assert columns[:2] == ['Spectrum', 'temperature_C'] and len(columns) == 5      # 3 bands
    assert [r[0] for r in table] == [s['label'] for s in sp] and merged == 0
    assert [r[1] for r in table] == [20, 30, 40, 50, 60, 70]
    band30 = [r[2] for r in table]
    assert all(v is not None for v in band30[:3]) and band30[3:] == [None, None, None]
    band50 = [r[3] for r in table]
    assert band50 == sorted(band50)                                  # grows with the series
    text = pl.rows_as_text(table, columns)
    assert '\tNone' not in text and text.splitlines()[0].startswith('Spectrum\ttemperature_C')


def test_two_peaks_in_one_band_take_the_nearer():
    from src.modules.data_analysis import peak_list as pl
    sp = _series()
    rows, index = pl.peak_table_with_index(sp, threshold=0.1, prominence=0.1, distance=0.01)
    columns, table, merged = pl.band_table(rows, index, sp, 'Position (x)', 100.0)
    assert len(columns) == 2 and merged > 0                          # all in one band


def test_the_tab_copy_and_fitted_values(tmp_path):
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    from src.modules.data_analysis import peak_list as pl
    dlg = PeakListDialog(None, _series(), threshold=0.1, prominence=0.1, distance=0.01)
    assert dlg.tabs.tabText(2) == 'Band table'
    dlg.tabs.setCurrentIndex(2)
    t = dlg.band_table_widget
    headers = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    assert headers[:2] == ['Spectrum', 'temperature_C'] and len(headers) == 5
    assert dlg.band_tolerance.value() == dlg.tolerance.value()
    dlg.band_stored_check.setChecked(False)
    assert t.columnCount() == 4
    dlg.copy()
    assert QApplication.clipboard().text().splitlines()[0].startswith('Spectrum\t')
    assert 'band table' in dlg.summary.text()
    dlg.refine_check.setChecked(True)
    values = [dlg.band_value_combo.itemText(i) for i in range(dlg.band_value_combo.count())]
    assert 'Fitted area' in values
    dlg.band_value_combo.setCurrentText('Fitted area')
    assert 'Fitted area' in dlg.band_info.text()
    columns, rows = dlg.fill_band_table()
    pl.export(rows, str(tmp_path / 'b.csv'), columns)
    assert open(tmp_path / 'b.csv').readline().startswith('Spectrum,')
    dlg.band_tolerance.setValue(0.0)                                 # one tolerance for both tabs
    assert dlg.tolerance.value() == 0.0 and t.columnCount() > 4


def test_rows_in_the_order_of_the_spectra_list():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    sp = _series()[::-1]                                 # names not in alphabetical order
    dlg = PeakListDialog(None, sp, threshold=0.1, prominence=0.1, distance=0.01)
    dlg.tabs.setCurrentIndex(2)
    t = dlg.band_table_widget
    assert [t.item(r, 0).text() for r in range(t.rowCount())] == [s['label'] for s in sp]
