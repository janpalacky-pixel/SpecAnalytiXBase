"""Right-click between two band markers > Copy the values between the band
markers A and B (Δ = ...): for each spectrum its maximum, minimum, area and
the band above the straight line joining its ends (position, height, area,
centroid), as a table for Excel; the real values also in a Waterfall plot
and with "scale each"."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.visualization import band_between as bb

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')


def _pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


# ---------------------------------------------------------------- the values
def _band(x, centre=50.0, height=10.0, width=3.0, slope=0.2, offset=100.0):
    return offset + slope * x + height * np.exp(-0.5 * ((x - centre) / width) ** 2)


def test_values_of_a_band_on_a_sloped_background():
    x = np.linspace(0, 100, 2001)
    v = bb.values_between(x, _band(x), 30.0, 70.0)
    assert v["Band position (above the line)"] == pytest.approx(50.0, abs=0.06)
    assert v["Band height (above the line)"] == pytest.approx(10.0, rel=1e-3)
    # the area of the Gaussian: height * width * sqrt(2 pi)
    assert v["Area above the line"] == pytest.approx(10 * 3 * np.sqrt(2 * np.pi), rel=1e-3)
    assert v["Centroid (above the line)"] == pytest.approx(50.0, abs=1e-3)
    # the whole area includes the background (100 + 0.2 x from 30 to 70)
    background = 100 * 40 + 0.1 * (70 ** 2 - 30 ** 2)
    assert v["Area"] == pytest.approx(background + 10 * 3 * np.sqrt(2 * np.pi), rel=1e-4)
    assert v["Max position"] == pytest.approx(50.0, abs=0.5)      # the slope moves it a little
    assert v["Min position"] == pytest.approx(30.0)


def test_a_negative_band_and_descending_x():
    x = np.linspace(100, 0, 1001)                       # high to low (e.g. CD from 320 nm)
    y = -_band(x, offset=0.0, slope=0.0)
    v = bb.values_between(x, y, 70.0, 30.0)             # markers in any order
    assert v["Band position (above the line)"] == pytest.approx(50.0, abs=0.1)
    assert v["Band height (above the line)"] == pytest.approx(-10.0, rel=1e-3)
    assert v["Area above the line"] < 0
    assert v["Centroid (above the line)"] == pytest.approx(50.0, abs=1e-3)
    assert v["Min position"] == pytest.approx(50.0, abs=0.1)


def test_a_spectrum_that_does_not_reach_both_markers():
    x = np.linspace(0, 40, 100)
    assert bb.values_between(x, x, 30.0, 70.0) is None
    text = bb.table_text([("short", x, x)], 30.0, 70.0)
    assert text.splitlines()[1].split("\t")[1:] == [""] * len(bb.COLUMNS)


def test_pair_around():
    markers = [("Phe", 1004.0), ("1480", 1480.0), ("1500", 1500.0)]
    assert bb.pair_around(markers, 1490.0) == (("1480", 1480.0), ("1500", 1500.0))
    assert bb.pair_around(markers, 1200.0) == (("Phe", 1004.0), ("1480", 1480.0))
    assert bb.pair_around(markers, 900.0) is None
    assert bb.pair_around(markers[:1], 1490.0) is None


def test_table_header_names_the_range_and_the_distance():
    x = np.linspace(0, 100, 501)
    text = bb.table_text([("a", x, _band(x)), ("b", x, 2 * _band(x))], 70.0, 30.0,
                         names=("end", "Phe"))
    head = text.splitlines()[0].split("\t")
    assert head[0] == "Spectrum (x Phe (30) – end (70), Δ = 40)"
    assert head[1:] == list(bb.COLUMNS)
    assert len(text.splitlines()) == 3


# ---------------------------------------------------------------- the menu
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


def _menu_texts(mc, x, monkeypatch, choose=None):
    """The right-click menu at x on the plot: its items' texts; choose: the
    item (starting with) to click."""
    from PyQt5.QtWidgets import QMenu
    from matplotlib.backend_bases import MouseEvent
    texts = []

    def fake_exec(menu, *a, **k):
        chosen = None
        for act in menu.actions():
            texts.append(act.text())
            if choose and act.text().startswith(choose):
                chosen = act
        return chosen
    monkeypatch.setattr(QMenu, 'exec_', fake_exec)
    canvas = mc.static_canvas
    ax = canvas.figure.axes[0]
    canvas.draw()
    px, py = ax.transData.transform((x, np.mean(ax.get_ylim())))
    event = MouseEvent('button_press_event', canvas, px, py, button=3)
    mc.handle_mouse_click(event)
    return texts


def test_the_menu_item_between_two_markers(mc, monkeypatch):
    markers = mc.band_markers()
    markers.add_at(1480.0)
    markers.add_at(1500.0)
    texts = _menu_texts(mc, 1490.0, monkeypatch)
    item = [t for t in texts if t.startswith("Copy the values between")]
    assert item == ["Copy the values between the band markers 1480 and 1500 (Δ = 20)"]
    texts = _menu_texts(mc, 1200.0, monkeypatch)        # not between two markers
    assert not [t for t in texts if t.startswith("Copy the values between")]


@pytest.mark.parametrize('plot_type', ["Overlay plot", "Waterfall plot"])
def test_copied_values_are_the_spectra_own(mc, monkeypatch, plot_type):
    mc.view.comboBox_plot_type_choice.setCurrentText(plot_type)
    mc.view.scale_each_checkBox.setChecked(True)
    _pump()
    markers = mc.band_markers()
    markers.add_at(1480.0)
    markers.add_at(1500.0)
    QApplication.clipboard().setText("")
    _menu_texts(mc, 1490.0, monkeypatch, choose="Copy the values between")
    rows = [r.split("\t") for r in QApplication.clipboard().text().splitlines()]
    assert len(rows) == 1 + 11
    by_label = {s['label']: s for s in mc.selected_spectra}
    col = 1 + bb.COLUMNS.index("Max value")
    for row in rows[1:]:
        s = by_label[row[0]]
        x, y = np.asarray(s['x_scale'], float), np.asarray(s['y_scale'], float)
        want = bb.values_between(x, y, 1480.0, 1500.0)["Max value"]
        assert float(row[col]) == pytest.approx(want)
    assert "Δ = 20" in mc.view.statusBar().currentMessage()
