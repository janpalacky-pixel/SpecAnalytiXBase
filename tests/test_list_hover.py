"""The mouse over a spectrum's row of the list: its line is drawn thicker
and on top on the plot (which one is sp007 among many lines); back when the
mouse moves on or leaves the list."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')


def _pump(seconds=0.2):
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
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    ctrl.spectrum_selector.select_all_items()
    _pump()
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def _line(mc, label):
    shown = (mc._display_labels or {}).get(label, label)
    return [l for l in mc.static_canvas.figure.axes[0].get_lines() if l.get_label() == shown][0]


@pytest.mark.parametrize('shorten', [False, True])
def test_the_row_under_the_mouse_marks_its_line(mc, shorten):
    mc.checkBox_shorten_names.setChecked(shorten)
    _pump()
    lw = mc.spectra_list_widget
    a, b = lw.item(2).text(), lw.item(5).text()
    width = _line(mc, a).get_linewidth()
    lw.itemEntered.emit(lw.item(2))
    assert _line(mc, a).get_linewidth() > width and _line(mc, a).get_zorder() > 2.5
    lw.itemEntered.emit(lw.item(5))                     # the next row: the first back
    assert _line(mc, a).get_linewidth() == width
    assert _line(mc, b).get_linewidth() > width
    QApplication.sendEvent(lw, QEvent(QEvent.Leave))    # left the list: back
    assert _line(mc, b).get_linewidth() == width


def test_a_hidden_spectrum_is_not_marked(mc):
    lw = mc.spectra_list_widget
    label = lw.item(1).text()
    mc.plot_mouse_controller.toggle((mc._display_labels or {}).get(label, label))
    _pump()
    assert mc.plot_mouse_controller.hover(label) is False
