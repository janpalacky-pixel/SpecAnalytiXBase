"""Peak list, tab Plot: x "Peak number" (and joining lines only from
spectrum to spectrum); Select all / Unselect all of the table."""
import glob
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JWB = sorted(glob.glob(os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD melting', '*.jwb')))[0]


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths),
                                                 [{'jws_selected_channels': [0]} for _ in file_paths])))
    controller = MainController()
    controller.import_controller._run_import(clear_first=True, file_paths=[JWB])
    controller.spectrum_selector.select_all_items()
    app.processEvents()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _list(mc, monkeypatch):
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    monkeypatch.setattr(PeakListDialog, 'exec_', lambda self: 0)
    return mc.peak_detection_controller.show_peak_list()


def test_peak_number_axis_and_join_only_between_spectra(mc, monkeypatch):
    dlg = _list(mc, monkeypatch)
    texts = [dlg.x_combo.itemText(i) for i in range(dlg.x_combo.count())]
    assert texts[-1].startswith('Peak number') and 'Peak' not in texts
    dlg.x_combo.setCurrentIndex(len(texts) - 1)
    assert not dlg.join_check.isEnabled()                  # x is a number of the peak
    dlg.join_check.setChecked(True)
    dlg.tabs.setCurrentIndex(1)
    dlg.draw_plot()
    assert dlg.figure.axes[0].get_xlabel() == 'Peak number' and not dlg.figure.axes[0].lines
    dlg.x_combo.setCurrentIndex(0)
    assert dlg.join_check.isEnabled()


def test_select_all_and_unselect_all(mc, monkeypatch):
    dlg = _list(mc, monkeypatch)
    dlg.select_all_button.click()
    assert len(dlg.table.selectionModel().selectedRows()) == dlg.table.rowCount() > 0
    dlg.unselect_all_button.click()
    assert not dlg.table.selectionModel().selectedRows()
