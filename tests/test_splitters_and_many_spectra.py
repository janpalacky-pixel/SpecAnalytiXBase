"""Splitters that move gradually and never hide a whole part (controls in a
scroll area, no collapsing), and tool windows that draw an evenly spread
subset of very many spectra (View -> Plotting many spectra... -> Tool
windows)."""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QDialog, QFileDialog, QLabel, QMessageBox,
                             QSplitter, QVBoxLayout, QWidget)

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')

from src.modules.visualization import large_selection as ls                     # noqa: E402
from src.views.dialogs.misc.splitter_utils import no_collapse, scrollable_panel  # noqa: E402


def _pump(seconds=0.1):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


def test_scrollable_panel_releases_a_fixed_width_and_no_collapse():
    panel = QWidget()
    panel.setFixedWidth(400)
    QVBoxLayout(panel).addWidget(QLabel('controls'))
    area = scrollable_panel(panel, 240)
    assert panel.minimumWidth() == 0 and panel.maximumWidth() > 10000
    assert area.widget() is panel and area.minimumWidth() == 240
    sp = QSplitter(Qt.Horizontal)
    sp.addWidget(area)
    sp.addWidget(QWidget())
    no_collapse(sp, 300)
    assert not sp.childrenCollapsible()
    assert sp.widget(1).minimumWidth() == 300


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
    ctrl = MainController()
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    ctrl.spectrum_selector.select_all_items()
    _pump()
    yield ctrl, mp
    ctrl.view.close()
    mp.undo()


def _open(mc, kind, name):
    ctrl, mp = mc
    shown = []

    def fake_exec(dlg):
        dlg.resize(1400, 850)
        dlg.show()
        _pump(0.2)
        shown.append(dlg)
        return QDialog.Rejected
    mp.setattr(QDialog, 'exec_', fake_exec)
    mp.setattr(QDialog, 'exec', fake_exec)
    before = {id(w) for w in app.topLevelWidgets() if w.isVisible()}
    if kind == 'op':
        ctrl.operations_controller.show_parameters_dialog_for(name)
    else:
        ctrl.run_visualization_analysis(name)
    _pump(0.2)
    shown += [w for w in app.topLevelWidgets()
              if w.isVisible() and id(w) not in before and w is not ctrl.view]
    return shown


@pytest.mark.parametrize('kind, name', TOOLS, ids=[t[1] for t in TOOLS])
def test_splitters_move_gradually_and_never_hide_a_part(mc, kind, name):
    windows = _open(mc, kind, name)
    assert windows, f'{name}: no window'
    win = windows[0]
    if not win.isVisible():
        win.resize(1400, 850)
        win.show()
        _pump(0.2)
    splitters = [s for s in win.findChildren(QSplitter) if s.isVisible() and s.count() >= 2
                 and all(s.widget(i).isVisible() for i in range(s.count()))]
    assert splitters, f'{name}: no splitter'
    for sp in splitters:
        assert not sp.childrenCollapsible(), name
        total = sum(sp.sizes())
        firsts = set()
        for pos in range(0, total, 20):
            sp.moveSplitter(pos, 1)
            app.processEvents()
            firsts.add(sp.sizes()[0])
        assert 0 not in firsts and min(sp.sizes()) > 0, f'{name}: a part collapsed'
        if sp.orientation() == Qt.Horizontal and sp is splitters[0]:
            assert len(firsts) >= 10, f'{name}: the handle hardly moves ({sorted(firsts)})'
    for w in windows:
        w.close()


def test_dialog_subset_and_note():
    items = list(range(3000))
    shown, n = ls.dialog_subset(items, 300)
    assert n == 3000 and len(shown) == 300 and shown[0] == 0 and shown[-1] == 2999
    shown, n = ls.dialog_subset(items, 300, keep=lambda i: i == 1234)
    assert 1234 in shown
    assert ls.dialog_subset(items[:50], 300) == (items[:50], 50)
    assert ls.shown_note(300, 3000) == '300 of 3 000 shown'
    assert ls.shown_note(50, 50) == ''
    assert ls.normalized_dialog_count('x') == ls.DEFAULT_DIALOG_COUNT == 100
    assert ls.normalized_dialog_count(3) == 10


def test_fft_denoising_draws_only_the_limit(monkeypatch):
    from matplotlib.lines import Line2D
    from src.controllers.visualization import large_plot_controller as lpc
    from src.views.dialogs.data_analysis.fft_denoising_dialog import FFTDenoisingDialog
    monkeypatch.setattr(lpc, 'dialog_draw_limit', lambda: 40)
    x = np.linspace(400, 1800, 300)
    spectra = [{'label': f's{i:03d}', 'x_scale': x, 'y_scale': np.sin(x / 50 + i),
                'metadata': {}} for i in range(200)]
    dlg = FFTDenoisingDialog(None, selected_spectra=spectra)
    dlg.resize(1300, 800)
    dlg.show()
    _pump(0.5)
    dlg._refresh_all()
    sig_lines = [ln for ax in dlg._signal_canvas.figure.axes for ln in ax.get_lines()]
    assert 0 < len(sig_lines) <= 2 * 41                  # original + denoised per spectrum
    titles = ' '.join(ax.get_title() for ax in dlg._signal_canvas.figure.axes)
    assert '40 of 200' in titles
    dlg.close()


def test_svd_background_large_table_computes_in_background(monkeypatch):
    """A large table: the window opens at once and the SVD runs on a
    background thread with a progress window; the settings are filled in
    when it is done."""
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.data_analysis import svd_background_dialog as sbd
    monkeypatch.setattr(sbd, '_ASYNC_SVD_VALUES', 1)         # every table counts as large
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    x = np.linspace(400, 1800, 200)
    rng = np.random.RandomState(0)
    spectra = [{'label': f's{i}', 'x_scale': x,
                'y_scale': np.exp(-((x - 900 - 3 * i) / 40) ** 2) + rng.normal(0, 0.01, 200),
                'metadata': {}} for i in range(40)]
    mc = MainController()
    dlg = sbd.SVDBackgroundDialog(None, {}, mc, selected_spectra=spectra,
                                  commit_callback=lambda *a, **k: None)
    assert dlg._svd_async_pending and not dlg.apply_button.isEnabled()
    dlg.show()
    end = time.time() + 30
    while time.time() < end and (dlg._svd_async_pending or not dlg.apply_button.isEnabled()):
        app.processEvents()
        time.sleep(0.01)
    assert dlg.apply_button.isEnabled() and dlg.components_list.count() > 0
    dlg.close()
    mc.view.close()


def test_select_all_in_a_tool_window_selects_every_row():
    from src.views.dialogs.data_analysis.fft_denoising_dialog import FFTDenoisingDialog
    x = np.linspace(400, 1800, 50)
    spectra = [{'label': f's{i:04d}', 'x_scale': x, 'y_scale': np.sin(x / 50 + i),
                'metadata': {}} for i in range(500)]
    dlg = FFTDenoisingDialog(None, selected_spectra=spectra)
    assert len(dlg.spectra_list.selectedItems()) == 500       # selected on opening
    dlg._unselect_all()
    assert not dlg.spectra_list.selectedItems()
    dlg._select_all()
    assert len(dlg.spectra_list.selectedItems()) == 500
    dlg.close()


def test_tool_windows_select_all_by_default_and_remember_the_selection(mc):
    """Normalization, Combine Spectra and Data range open with all spectra
    selected (like FFT Denoising); the selection of the last time comes
    back when a tool window is opened again."""
    from src.views.dialogs.misc import selection_memory
    selection_memory.forget_all()
    ctrl, mp = mc
    n_total = len(ctrl.spectrum_selector.get_selected_spectra())

    def lists(win):
        from PyQt5.QtWidgets import QListWidget
        return [lw for lw in win.findChildren(QListWidget)
                if lw.count() == n_total and lw.selectionMode() != lw.SingleSelection]

    for name in ('Normalization', 'Combine Spectra', 'Data range', 'FFT Denoising'):
        wins = _open(mc, 'op', name)
        lw = lists(wins[0])[0]
        assert len(lw.selectedItems()) == n_total, name
        # choose two spectra, close, open again: the two come back
        keep = [lw.item(1).text(), lw.item(3).text()]
        from src.modules.utils.list_selection import select_rows
        select_rows(lw, [1, 3])
        for w in wins:
            w.reject() if isinstance(w, QDialog) else w.close()
        wins2 = _open(mc, 'op', name)
        lw2 = lists(wins2[0])[0]
        assert sorted(i.text() for i in lw2.selectedItems()) == sorted(keep), name
        for w in wins2:
            w.close()
    selection_memory.forget_all()


def test_interactive_subtraction_controls_use_the_room(mc):
    """Dragging the divider to the left makes the controls (right) wider --
    no empty space next to them."""
    wins = _open(mc, 'op', 'Interactive subtraction')
    win = wins[0]
    if not win.isVisible():
        win.resize(1400, 850)
        win.show()
        _pump(0.2)
    sp = [s for s in win.findChildren(QSplitter) if s.isVisible()][0]
    area = sp.widget(1)
    panel = area.widget()
    sp.moveSplitter(1000, 1)
    app.processEvents()
    narrow = panel.width()
    sp.moveSplitter(450, 1)
    app.processEvents()
    assert panel.width() > narrow + 300
    assert panel.width() >= area.viewport().width() - 2       # fills the area
    for w in wins:
        w.close()
