"""Peak list > Refine by fitting: every found peak fitted with a model band
plus a background (the fit of the 2D map's peak-fit maps) - position between
the measured points, FWHM, height above the background, area, R² in extra
columns, also for copy, export and the tab Plot."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

TRUE_CENTRES = [700.23, 700.63, 701.03, 701.43, 701.83]


def _spectra():
    x = np.linspace(600, 800, 401)                       # a point every 0.5
    rng = np.random.default_rng(1)
    out = []
    for i, c in enumerate(TRUE_CENTRES):
        y = (100 * np.exp(-4 * np.log(2) * ((x - c) / 8.0) ** 2)
             + 40 * np.exp(-4 * np.log(2) * ((x - 650.6) / 6.0) ** 2)
             + 0.05 * x + rng.normal(0, 0.5, x.size))
        out.append({'label': f'scan : {i + 1}', 'x_scale': x, 'y_scale': y, 'metadata': {}})
    return out


def test_fitted_positions_between_the_points():
    from src.modules.data_analysis import peak_list as pl
    sp = _spectra()
    rows, index = pl.peak_table_with_index(sp, threshold=0.1, prominence=0.1)
    fitted, text = pl.refine_by_fitting(rows, index, sp)
    assert 'Fitted 10 of 10 peaks' in text
    c = pl.ALL_COLUMNS.index
    big = [r for r in fitted if r[c('Position (x)')] > 690]
    measured = [r[c('Position (x)')] for r in big]
    assert all(abs(m * 2 - round(m * 2)) < 1e-9 for m in measured)   # only on the 0.5 grid
    for r, true in zip(big, TRUE_CENTRES):
        assert r[c('Fitted position')] == pytest.approx(true, abs=0.05)
        assert r[c('Fitted FWHM')] == pytest.approx(8.0, abs=0.2)
        assert r[c('Fitted height')] == pytest.approx(100, rel=0.02)       # above the background
        assert r[c('Fitted area')] == pytest.approx(100 * 8 * 1.0645, rel=0.02)
        assert r[c('R²')] > 0.99


def test_the_window_stops_halfway_to_the_neighbour():
    from src.modules.data_analysis import peak_list as pl
    x = np.linspace(0, 100, 501)
    y = np.exp(-((x - 45) / 3) ** 2) + np.exp(-((x - 55) / 3) ** 2)
    sp = [{'label': 'two', 'x_scale': x, 'y_scale': y}]
    rows, index = pl.peak_table_with_index(sp, threshold=0.1, prominence=0.05, distance=0.01)
    assert len(rows) == 2
    windows = pl.fit_windows(rows, index, sp)
    assert windows[0][0].max() <= 50.0 + 1e-9 and windows[1][0].min() >= 50.0 - 1e-9


def test_the_window_columns_copy_and_plot(tmp_path):
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    from src.modules.data_analysis import peak_list as pl
    dlg = PeakListDialog(None, _spectra(), threshold=0.1, prominence=0.1)
    assert dlg.table.columnCount() == len(pl.COLUMNS) and not dlg.fit_shape.isEnabled()
    dlg.refine_check.setChecked(True)
    assert dlg.table.columnCount() == len(pl.ALL_COLUMNS) and dlg.fit_shape.isEnabled()
    assert dlg.table.horizontalHeaderItem(len(pl.COLUMNS)).text() == 'Fitted position'
    assert 'Fitted 10 of 10 peaks' in dlg.fit_info.text()
    ys = [dlg.y_combo.itemText(i) for i in range(dlg.y_combo.count())]
    xs = [dlg.x_combo.itemText(i) for i in range(dlg.x_combo.count())]
    assert 'Fitted area' in ys and 'Fitted position' in xs and xs[-1].startswith('Peak number')
    dlg.table.selectAll()
    dlg.copy()
    text = QApplication.clipboard().text()
    assert text.splitlines()[0].endswith('Fitted area\tR²')
    import pandas as pd
    pl.export(dlg.rows, str(tmp_path / 'p.xlsx'), dlg.columns)
    assert list(pd.read_excel(tmp_path / 'p.xlsx').columns)[-1] == 'R²'
    dlg.tabs.setCurrentIndex(1)
    dlg.y_combo.setCurrentText('Fitted position')
    assert dlg.draw_plot() == 10
    dlg.fit_shape.setCurrentText('Lorentzian')                         # fitted again
    assert dlg.table.columnCount() == len(pl.ALL_COLUMNS)
    dlg.refine_check.setChecked(False)
    assert dlg.table.columnCount() == len(pl.COLUMNS)
    assert dlg.y_combo.currentText() == 'Position (x)'                 # the fitted one is gone
    assert 'Fitted area' not in [dlg.y_combo.itemText(i) for i in range(dlg.y_combo.count())]


def test_a_rejected_fit_is_an_empty_cell():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    from src.modules.data_analysis import peak_list as pl
    x = np.linspace(0, 10, 12)                                        # too few points to fit
    y = np.array([0, 0, 1, 3, 1, 0, 0, 0, 2, 0, 0, 0], dtype=float)
    dlg = PeakListDialog(None, [{'label': 'short', 'x_scale': x, 'y_scale': y}],
                         threshold=0.1, prominence=0.1, distance=0.01)
    dlg.refine_check.setChecked(True)
    col = pl.ALL_COLUMNS.index('Fitted position')
    cells = [dlg.table.item(r, col).text() for r in range(dlg.table.rowCount())]
    assert '' in cells and 'could not be fitted' in dlg.fit_info.text()
    rows = dlg._shown_rows(selected_only=False)
    assert all(v != 'None' for row in rows for v in row)
