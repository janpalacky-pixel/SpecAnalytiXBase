"""Conveniences: the vertical cursor of the main plot."""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.visualization import cursor_values as cv

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')


def _pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


# --- cursor values (Qt-free) ------------------------------------------------------------

def test_values_are_interpolated_never_extrapolated():
    x, y = np.array([1.0, 2.0, 3.0]), np.array([10.0, 20.0, 40.0])
    assert cv.value_at(x, y, 2.5) == 30.0
    assert cv.value_at(x[::-1], y[::-1], 1.5) == 15.0          # decreasing x works
    assert cv.value_at(x, y, 0.5) is None and cv.value_at(x, y, 3.5) is None
    vals = cv.values_at([('a', x, y), ('b', x + 10, y)], 2.0)
    assert vals == [('a', 20.0)]


def test_listed_values_nearest_to_the_pointer_and_table():
    vals = [(f's{i}', float(i)) for i in range(15)]
    shown, hidden = cv.listed(vals, pointer_y=7.2, limit=4)
    assert hidden == 11 and [l for l, _ in shown] == ['s9', 's8', 's7', 's6']
    x = np.array([1.0, 2.0, 3.0])
    table = cv.table_text([('a', x, x * 2), ('b', x + 5, x)], [1.5, 2.0])
    lines = table.rstrip('\n').split('\n')
    assert lines[0] == 'Spectrum\tx = 1.5\tx = 2'
    assert lines[1] == 'a\t3.0\t4.0' and lines[2] == 'b\t\t'
    assert cv.fmt(270234.4) == '270234' and cv.fmt(1.2e-5) == '1.2e-05' and cv.fmt(None) == '—'


# --- the main window -----------------------------------------------------------------------

@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    seen = []
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(
            lambda *a, **k: seen.append(a[2] if len(a) > 2 else '') or QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, 'exec_', lambda self: QMessageBox.Yes)
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths or [DATA]),
                                                 [{} for _ in (file_paths or [DATA])])))
    from src.controllers.core.main_controller import MainController
    ctrl = MainController()
    ctrl.messages = seen
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def _labels(mc):
    return [mc.spectra_list_widget.item(i).text() for i in range(mc.spectra_list_widget.count())]


def test_cursor_lists_values_and_copies_pinned_ones(mc):
    mc.view.resize(1400, 900)
    mc.view.show()
    mc.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    mc.spectrum_selector.select_all_items()
    _pump(0.5)
    cc = mc.plot_cursor_controller
    assert cc.canvas is mc.static_canvas
    mc.cursor_checkbox.setChecked(True)
    assert cc.enabled
    ax = mc.static_canvas.figure.axes[0]
    text, shown = cc.readout_text(ax, 1000.0, None)
    assert text.startswith('x = 1000') and len(shown) == 10 and '+ 1 more' in text
    curves = cc.all_curves()
    assert len(curves) == 11
    by_label = {lbl: (xx, yy) for lbl, xx, yy in curves}
    for lbl, v in shown:
        xx, yy = by_label[lbl]
        assert v == pytest.approx(np.interp(1000.0, xx, yy))
    # a mouse move draws the live cursor without an error
    from matplotlib.backend_bases import MouseEvent
    mc.static_canvas.draw()
    px, py = ax.transData.transform((1200.0, np.mean(ax.get_ylim())))
    mc.static_canvas.callbacks.process('motion_notify_event',
                                       MouseEvent('motion_notify_event', mc.static_canvas, px, py))
    cc.pin(800.0)
    cc.pin(1500.0)
    assert cc.copy_table() == 11
    rows = QApplication.clipboard().text().strip().split('\n')
    assert rows[0] == 'Spectrum\tx = 800\tx = 1500' and len(rows) == 12
    mc.plot_spectra()                                   # pinned cursors stay
    _pump()
    assert mc.plot_cursor_controller.pinned == [800.0, 1500.0]
    cc.clear_pinned()
    assert cc.pinned == []

