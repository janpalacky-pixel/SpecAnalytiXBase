"""The main window opens as it was left: its size and place (also
maximized) and the width of the spectra list are kept on a normal close and
used at the next start; closed on the start page (the list hidden), the
width from before is kept."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')


def _pump(seconds=0.15):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, [DATA], [{}])))
    from src.controllers.core.main_controller import MainController
    ctrl = MainController()
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump(0.3)
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def test_the_window_opens_as_it_was_left(mc):
    view = mc.view
    view.resize(1234, 777)
    view.main_splitter.setSizes([500, 734])
    _pump()
    assert mc.remember_window_layout()
    size, widths = view.size(), view.main_splitter.sizes()
    from src.controllers.core.main_controller import MainController
    assert widths[0] >= 80                                          # the list is shown
    other = MainController()                                        # the next start
    assert other.restore_window_layout()
    other.view.show()
    _pump(0.4)
    assert other.view.size() == size
    other.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump(0.4)                                                      # the list appears
    assert other.view.main_splitter.sizes()[0] == pytest.approx(widths[0], abs=6)
    # closed on the start page (no list shown): the width kept from before
    assert other.remember_window_layout()
    assert other.autosave_controller.preferences.get('main_window_layout')['list_width']
    other.autosave_controller.shutdown()
    other.view.deleteLater()
