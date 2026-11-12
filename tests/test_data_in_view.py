"""Right-click on the plot > Copy the data in view: the spectra shown within
the x range in view, as a table for Excel - one x column when they share x,
otherwise x and values per spectrum; their own values (Waterfall, scale
each); hidden spectra left out."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.visualization import data_in_view as div

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')


def _pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


def test_one_x_column_when_shared():
    x = np.linspace(0, 10, 11)
    text, n, rows = div.table_text([("a", x, x * 2), ("b", x[::-1], (x * 3)[::-1])], 7, 3)
    lines = [l.split("\t") for l in text.splitlines()]
    assert lines[0] == ["x (3 – 7)", "a", "b"]
    assert (n, rows) == (2, 5)
    assert [float(c) for c in lines[1]] == [3.0, 6.0, 9.0]       # low to high x


def test_x_and_values_per_spectrum_otherwise():
    xa, xb = np.linspace(0, 10, 11), np.linspace(0, 10, 21)
    text, n, rows = div.table_text([("a", xa, xa), ("b", xb, -xb)], 2, 4)
    lines = [l.split("\t") for l in text.splitlines()]
    assert lines[0] == ["x: a", "a", "x: b", "b"]
    assert rows == 5 and lines[-1][:2] == ["", ""]                # a is shorter
    assert float(lines[1][2]) == 2.0 and float(lines[1][3]) == -2.0


def test_nothing_in_view():
    x = np.linspace(0, 10, 11)
    assert div.table_text([("a", x, x)], 20, 30) == ("", 0, 0)


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


@pytest.mark.parametrize('plot_type', ["Overlay plot", "Waterfall plot"])
def test_copy_the_data_in_view(mc, plot_type):
    mc.view.comboBox_plot_type_choice.setCurrentText(plot_type)
    mc.view.scale_each_checkBox.setChecked(True)
    _pump()
    ax = mc.static_canvas.figure.axes[0]
    ax.set_xlim(1450, 1520)
    first = mc.selected_spectra[0]['label']
    mc.plot_mouse_controller.toggle((mc._display_labels or {}).get(first, first))   # hidden
    _pump()
    n, rows = mc.copy_data_in_view()
    lines = [l.split("\t") for l in QApplication.clipboard().text().splitlines()]
    assert n == 10 and len(lines) == rows + 1 and first not in lines[0]
    s = mc.selected_spectra[1]
    x, y = np.asarray(s['x_scale'], float), np.asarray(s['y_scale'], float)
    keep = (x >= 1450) & (x <= 1520)
    col = lines[0].index(s['label'])
    got = [float(r[col]) for r in lines[1:]]
    assert sorted(got) == pytest.approx(sorted(y[keep]))           # its own values


def test_heatmap_has_nothing_to_copy(mc):
    mc.view.comboBox_plot_type_choice.setCurrentText("Heatmap")
    _pump()
    assert mc._view_x_range() is None
    assert mc.copy_data_in_view() == (0, 0)
