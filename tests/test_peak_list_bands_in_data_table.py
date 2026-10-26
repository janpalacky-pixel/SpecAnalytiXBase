"""Peak list > Band table > Open in the Data table: the Data table of the same
spectra opens on its tab Values per spectrum with one column per band (b1,
b2, ...) of the value shown, next to the stored values; the bands can be
used in formulas (b2 / b1), plotted and removed like the other columns."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TBA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')


def _series():
    """Six spectra (temperature_C 20 ... 70): bands near 30 (only in the first
    three), 50 (grows) and 70."""
    x = np.linspace(0, 100, 501)
    out = []
    for i in range(6):
        y = (1 + 0.1 * i) * np.exp(-((x - 50 - 0.2 * i) / 2) ** 2) + 0.8 * np.exp(-((x - 70) / 2) ** 2)
        if i < 3:
            y = y + 0.6 * np.exp(-((x - 30) / 2) ** 2)
        out.append({'label': f'scan : {i + 1:02d}', 'x_scale': x, 'y_scale': y,
                    'metadata': {'temperature_C': 20.0 + 10 * i}})
    return out


def test_the_table_gets_one_column_per_band():
    from src.modules.data_analysis.value_table import ValueTable
    t = ValueTable.from_spectra(_series())
    added = t.add_bands('Height (y)', [('30', [0.6, 0.6, 0.6, None, None, None]),
                                       ('50', [1, 1.1, 1.2, 1.3, 1.4, 1.5])])
    assert [c.name for c in added] == ['b1', 'b2']
    assert added[0].title == 'Height of the band at 30' and added[0].kind == 'band'
    assert np.isnan(t.column('b1').values[3])                       # no peak there
    f = t.add_formula('b2 / b1')
    assert np.allclose(f.values[:3], [1 / 0.6, 1.1 / 0.6, 1.2 / 0.6]) and np.isnan(f.values[3])
    x, y, _ = t.xy('temperature_C', 'b2')
    assert list(x) == [20, 30, 40, 50, 60, 70] and list(y) == [1, 1.1, 1.2, 1.3, 1.4, 1.5]
    assert t.add_bands('FWHM', [('70', [2] * 6)])[0].name == 'b3'
    with pytest.raises(ValueError):                                  # used by f1
        t.remove_column('b1')
    assert t.remove_column('f1') and t.remove_column('b1')
    with pytest.raises(ValueError):
        t.add_bands('Height (y)', [('30', [1, 2])])                  # other spectra


def test_the_button_opens_the_data_table_with_the_bands(monkeypatch):
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
    opened = []

    def open_data_table(parent, spectra, value_name, bands):
        dlg = DataTableDialog(parent, spectra)
        dlg.values.add_bands(value_name, bands)
        opened.append(dlg)
        return dlg
    sp = _series()
    dlg = PeakListDialog(None, sp, threshold=0.1, prominence=0.1, distance=0.01,
                         open_data_table=open_data_table)
    dlg.tabs.setCurrentIndex(2)
    assert not dlg.band_to_data_table_button.isHidden()
    dlg.band_value_combo.setCurrentText('Height (y)')
    dlg.band_to_data_table_button.click()
    table = opened[0].values.table
    bands = [c for c in table.columns if c.kind == 'band']
    assert [c.name for c in bands] == ['b1', 'b2', 'b3']                # bands at 30, 50, 70
    assert table.column('temperature_C') is not None                     # the stored values too
    shown = dlg.fill_band_table()[1]
    for k, c in enumerate(bands, start=2):                                # as in the Band table
        expect = [np.nan if r[k] is None else r[k] for r in shown]
        assert np.allclose(c.values, expect, equal_nan=True)
    assert 'Height of each band from the Peak list' in opened[0].values.message.text()


def test_without_a_data_table_there_is_no_button():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    dlg = PeakListDialog(None, _series(), threshold=0.1, prominence=0.1, distance=0.01)
    assert dlg.band_to_data_table_button.isHidden() and dlg.bands_to_data_table() is None


def test_in_the_program_it_opens_on_the_tab_values_per_spectrum(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    from src.views.dialogs.data_analysis import data_table_dialog as dtd, peak_list_dialog as pld
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    monkeypatch.setattr(pld.PeakListDialog, 'exec_', lambda self: 0)
    monkeypatch.setattr(dtd.DataTableDialog, 'exec_', lambda self: 0)
    mc = MainController()
    try:
        mc.import_controller._run_import(clear_first=True, file_paths=[TBA])
        mc.spectrum_selector.select_all_items()
        app.processEvents()
        dlg = mc.peak_detection_controller.show_peak_list()
        assert not dlg.band_to_data_table_button.isHidden()
        table_dlg = dlg.bands_to_data_table()
        assert table_dlg.tabs.currentWidget() is table_dlg.values
        assert any(c.kind == 'band' for c in table_dlg.values.table.columns)
        assert table_dlg.commit_callback is not None       # Points tab: add as new spectra
        assert table_dlg.values.table.n_rows == 28
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()
