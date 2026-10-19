"""A tool window opens with its control panel wide enough for its controls
(no sideways scroll bar right after opening). Found 2026-10-19: once the
control panels sat in scroll areas without a fixed width, several windows
opened with the panel too narrow (Automated Baseline, X-axis alignment,
Resolution enhancement, Spike removal, SVD Interpolation, Group Statistics).
splitter_utils.fit_panel() widens the panel when the window is first shown
-- from the other parts of the splitter, then by widening the window, never
beyond the screen; afterwards the user can drag it narrower again."""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QScrollArea, QSplitter, QVBoxLayout,
                             QWidget)

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')

from src.views.dialogs.misc import splitter_utils as su        # noqa: E402


def _pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


def _wide_controls(width):
    panel = QWidget()
    row = QHBoxLayout(panel)
    for i in range(4):
        b = QPushButton(f"button {i}")
        b.setMinimumWidth(width // 4)
        row.addWidget(b)
    return panel


def _window(panel_width, window_width, fixed=None, plot_min=300):
    win = QDialog()
    lay = QVBoxLayout(win)
    sp = QSplitter(Qt.Horizontal)
    panel = _wide_controls(panel_width)
    if fixed:
        panel.setFixedWidth(fixed)
    area = su.scrollable_panel(panel, 240)
    plot = QLabel("plot")
    sp.addWidget(area)
    sp.addWidget(plot)
    su.no_collapse(sp, plot_min)
    sp.setSizes([240, window_width - 240])
    lay.addWidget(sp)
    win.resize(window_width, 500)
    return win, sp, area


@pytest.fixture
def screen_width(monkeypatch):
    def set_width(w):
        monkeypatch.setattr(su, '_available_width', lambda window: w)
    return set_width


def test_panel_gets_its_width_from_the_plot(screen_width):
    screen_width(1920)
    win, sp, area = _window(520, 1200)
    win.show()
    _pump()
    assert not area.horizontalScrollBar().isVisible()
    assert sp.sizes()[0] >= su.needed_width(area)
    assert win.width() == 1200                     # room came from the plot
    assert sp.sizes()[1] >= 300
    # afterwards the user can drag the panel narrower again
    sp.setSizes([300, sum(sp.sizes()) - 300])
    _pump()
    win.hide(); win.show(); _pump()                # not widened again
    assert sp.sizes()[0] == 300 < su.needed_width(area)
    win.close()


def test_window_grows_but_never_beyond_the_screen(screen_width):
    screen_width(1000)
    win, sp, area = _window(900, 700)              # 900 + 300 do not fit in 700
    win.show()
    _pump()
    assert win.width() == 1000                     # widened up to the screen
    assert sp.sizes()[1] >= 300 - 1                # the plot keeps its minimum
    win.close()
    screen_width(1920)
    win, sp, area = _window(900, 700)
    win.show()
    _pump()
    assert 1200 <= win.width() <= 1920
    assert not area.horizontalScrollBar().isVisible()
    win.close()


def test_a_former_fixed_width_is_kept_when_opening(screen_width):
    screen_width(1920)
    win, sp, area = _window(100, 1200, fixed=400)
    win.show()
    _pump()
    assert area.preferred_width == 400
    assert sp.sizes()[0] >= 400
    win.close()


# --- the real tool windows ---------------------------------------------------------------

TOOLS = [('op', 'Manual baseline'), ('op', 'Automated Baseline'), ('op', 'SNIP Baseline'),
         ('op', 'SVD background'), ('op', 'FFT Denoising'), ('op', 'X-axis alignment'),
         ('op', 'Resolution enhancement'), ('op', 'Interactive subtraction'),
         ('op', 'Spike removal'), ('op', 'SVD Interpolation'), ('op', 'Spectral Calculator'),
         ('an', '2D map'), ('an', 'Reference Matching'), ('an', 'Group Statistics'),
         ('an', 'Isosbestic Point Detection')]


@pytest.fixture(scope='module')
def mc():
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    mp = pytest.MonkeyPatch()
    for n in ('information', 'warning', 'critical', 'question'):
        mp.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Yes))
    mp.setattr(QFileDialog, 'getOpenFileName', staticmethod(lambda *a, **k: ('', '')))
    mp.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, [DATA], [{'sheet_name': None,
                                                                 'jws_selected_channels': None}])))
    mp.setattr(su, '_available_width', lambda window: 1920)      # a Full HD screen
    ctrl = MainController()
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    ctrl.spectrum_selector.select_all_items()
    _pump()
    yield ctrl, mp
    ctrl.view.close()
    mp.undo()


@pytest.mark.parametrize('kind, name', TOOLS, ids=[t[1] for t in TOOLS])
def test_tool_windows_open_without_a_sideways_scroll_bar(mc, kind, name):
    ctrl, mp = mc
    shown = []

    def fake_exec(dlg):                    # opened at its own size, not resized here
        dlg.show()
        _pump(0.3)
        shown.append(dlg)
        return QDialog.Rejected
    mp.setattr(QDialog, 'exec_', fake_exec)
    mp.setattr(QDialog, 'exec', fake_exec)
    before = {id(w) for w in app.topLevelWidgets() if w.isVisible()}
    if kind == 'op':
        ctrl.operations_controller.show_parameters_dialog_for(name)
    else:
        ctrl.run_visualization_analysis(name)
    _pump(0.3)
    windows = shown + [w for w in app.topLevelWidgets()
                       if w.isVisible() and id(w) not in before and w is not ctrl.view]
    assert windows, name
    win = windows[-1]
    cut = [a for a in win.findChildren(QScrollArea)
           if a.isVisible() and a.horizontalScrollBar().isVisible()]
    assert not cut, (name, [(a.widget().minimumSizeHint().width(), a.width()) for a in cut])
    assert win.width() <= 1920
    for w in windows:
        w.close()
    _pump(0.1)
