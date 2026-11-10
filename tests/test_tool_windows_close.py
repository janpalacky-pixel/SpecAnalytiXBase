"""Processing windows beside the plot: the window's own close button (X)
ends them like Close does (Manual baseline and Spike removal accepted the
close without QDialog's handling, so the window waited and only "Close the
window" above the plot ended it); Interactive subtraction opens beside the
plot like all the others (it was a modal window without the orange line)."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

app = QApplication.instance() or QApplication([])
DATA = os.path.join(os.path.dirname(__file__), '..', 'resources', 'test_data', 'real',
                    'Raman_DNA_conc_dep.txt')


def _pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.No))
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    from src.controllers.core.main_controller import MainController
    ctrl = MainController()
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    ctrl.spectrum_selector.select_all_items()
    _pump()
    yield ctrl, monkeypatch
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


@pytest.mark.parametrize('op', ['Manual baseline', 'Spike removal'])
def test_the_close_button_ends_the_window(mc, op):
    ctrl, mp = mc
    opened = []

    def capture(dlg):
        opened.append(dlg)
        return QDialog.Rejected
    mp.setattr(QDialog, 'exec_', capture)
    mp.setattr(QDialog, 'exec', capture)
    ctrl.operations_controller.show_parameters_dialog_for(op)
    _pump()
    dlg = next(d for d in opened if d.isWindow())
    finished = []
    dlg.finished.connect(finished.append)
    dlg.show()
    _pump()
    dlg.close()                                    # the window's X
    _pump()
    assert finished and not dlg.isVisible()


def test_interactive_subtraction_opens_beside_the_plot(mc):
    ctrl, mp = mc
    import src.controllers.core.operations_controller as oc_module
    beside = []
    mp.setattr(oc_module, 'run_beside_plot', lambda dlg, *a, **k: beside.append(dlg) or 0)
    ctrl.operations_controller.show_parameters_dialog_for('Interactive subtraction')
    _pump()
    from src.views.dialogs.data_analysis.interactive_subtraction_dialog import (
        InteractiveSubtractionDialog)
    assert beside and isinstance(beside[0], InteractiveSubtractionDialog)
    assert not beside[0].isVisible()               # not shown modal on its own any more
    beside[0].deleteLater()
