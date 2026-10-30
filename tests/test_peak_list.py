"""Right-click on the plot -> Peak list... (and the button in the Peak
Detection Settings): every peak of the selected spectra - position, height,
prominence, FWHM - found by the same rule as Detect Peaks, which labels them
on the plot."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_analysis import peak_list as pl

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TBA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')
FWHM = lambda w: 2 * w * np.sqrt(np.log(2))          # of exp(-((x - c) / w)^2)


def _two_bands(x):
    return 2 * np.exp(-((x - 30) / 5) ** 2) + np.exp(-((x - 70) / 2) ** 2)


def test_positions_heights_and_widths():
    x = np.linspace(0, 100, 1001)
    peaks = pl.spectrum_peaks(x, _two_bands(x), threshold=0.2)
    assert [round(p['x'], 3) for p in peaks] == [30.0, 70.0]
    assert [round(p['y'], 3) for p in peaks] == [2.0, 1.0]
    assert peaks[0]['fwhm'] == pytest.approx(FWHM(5), rel=1e-3)
    assert peaks[1]['fwhm'] == pytest.approx(FWHM(2), rel=1e-3)
    assert peaks[0]['left'] == pytest.approx(30 - FWHM(5) / 2, abs=0.01)


def test_minima_and_uneven_steps():
    x = np.sort(np.concatenate([np.linspace(0, 50, 101), np.linspace(50.2, 100, 1500)]))
    y = 5 - _two_bands(x)
    peaks = pl.spectrum_peaks(x, y, threshold=0.2, mode='Negative')
    assert [p['kind'] for p in peaks] == ['min', 'min']
    assert peaks[1]['fwhm'] == pytest.approx(FWHM(2), rel=2e-3)        # fine steps there
    assert all(p['kind'] == 'max' for p in pl.spectrum_peaks(x, y, threshold=0.2, mode='Positive'))


def test_the_same_peaks_as_detect_peaks_labels():
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from src.modules.data_analysis.peak_detection_manager import PeakDetector
    x = np.linspace(0, 100, 1001)
    rng = np.random.default_rng(0)
    y = _two_bands(x) + 0.05 * rng.standard_normal(len(x))
    fig = Figure()
    canvas = FigureCanvasAgg(fig)
    fig.add_subplot(111).plot(x, y, label='s')
    det = PeakDetector()
    det.detect_peaks(canvas, 0.3, 10, 0, 2, 'fixed', 'x_only', True, 0.1, 0.05, 'Both')
    labelled = sorted(float(x[i]) for i in det.peak_indices[(0, 0)])
    listed = [r[3] for r in pl.peak_table([{'label': 's', 'x_scale': x, 'y_scale': y}],
                                          0.3, 0.1, 0.05, 'Both')]
    assert labelled == listed and len(listed) >= 2


def test_table_copy_and_export(tmp_path):
    x = np.linspace(0, 100, 501)
    spectra = [{'label': 'one', 'x_scale': x, 'y_scale': _two_bands(x)},
               {'label': 'flat', 'x_scale': x, 'y_scale': np.zeros_like(x) + 1}]
    rows = pl.peak_table(spectra, threshold=0.2)
    assert [(r[0], r[1], r[2]) for r in rows] == [('one', 1, 'maximum'), ('one', 2, 'maximum')]
    text = pl.rows_as_text(rows)
    assert text.splitlines()[0].split('\t') == pl.COLUMNS
    import pandas as pd
    pl.export(rows, str(tmp_path / 'p.xlsx'))
    pl.export(rows, str(tmp_path / 'p.csv'))
    assert pd.read_excel(tmp_path / 'p.xlsx').shape == (2, len(pl.COLUMNS))
    assert list(pd.read_csv(tmp_path / 'p.csv').columns) == pl.COLUMNS


# --- in the program ---------------------------------------------------------------------

@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    controller = MainController()
    controller.import_controller._run_import(clear_first=True, file_paths=[TBA])
    controller.spectrum_selector.select_all_items()
    app.processEvents()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def test_window_shares_the_settings_of_detect_peaks(mc, monkeypatch):
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    monkeypatch.setattr(PeakListDialog, 'exec_', lambda self: 0)
    pdc = mc.peak_detection_controller
    dlg = pdc.show_peak_list()
    n_all = dlg.table.rowCount()
    assert n_all > 0
    assert dlg.summary.text().endswith('of 28 spectra.')
    dlg.mode.setCurrentText('Both')
    dlg.threshold.setValue(0.1)
    assert dlg.table.rowCount() > n_all
    assert (pdc.peak_detection_mode, pdc.peak_threshold) == ('Both', 0.1)     # kept for Detect Peaks
    dlg.table.selectRow(0)
    dlg.copy()
    lines = QApplication.clipboard().text().splitlines()
    assert lines[0].startswith('Spectrum\tPeak') and len(lines) == 2


def test_detect_peaks_opens_the_same_window_on_its_tab_mark(mc, monkeypatch):
    from src.views.dialogs.data_analysis import peak_list_dialog as pld
    monkeypatch.setattr(pld.PeakListDialog, 'exec_', lambda self: 0)
    dlg = mc.peak_detection_controller.show_dialog()
    assert dlg.tabs.currentWidget() is dlg.mark_tab
    dlg.tabs.setCurrentIndex(0)                          # the tab List: the same spectra
    assert dlg.table.rowCount() > 0
