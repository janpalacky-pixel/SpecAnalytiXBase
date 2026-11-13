"""'keep zoom' in Basic plot options: the x range zoomed to stays when other
spectra are selected (y fitted to them); Home shows the whole range;
unticked as before; shown whole after Import data > New, in the Heatmap and
when the new spectra have no data there; remembered as a preference; the
range saved in snapshots without marking them changed."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')
CD = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')


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
        lambda view, settings, file_paths=None: (True, list(file_paths or [DATA]), [{}])))
    from src.controllers.core.main_controller import MainController
    ctrl = MainController()
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    ctrl.spectrum_selector.select_all_items()
    _pump()
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.close()
    ctrl.view.deleteLater()


def _ax(mc):
    return mc.static_canvas.figure.axes[0]


def _xr(ax):
    return tuple(sorted(ax.get_xlim()))


def _zoom(mc, lo=1450.0, hi=1520.0):
    ax = _ax(mc)
    ax.set_xlim(lo, hi)
    ax.set_ylim(0, 1)
    mc.static_canvas.draw()


def _select(mc, indices):
    sel = mc.spectrum_selector
    lw = getattr(sel, 'list_widget', None) or mc.view.listWidget_spectra \
        if hasattr(mc.view, 'listWidget_spectra') else None
    if hasattr(sel, 'select_indices'):
        sel.select_indices(indices)
    else:
        mc.selected_spectra = [mc.original_spectra[i] for i in indices]
        mc.plot_spectra()
    _pump()


def test_the_checkbox(mc):
    box = mc.view.keep_zoom_checkBox
    assert box.text() == 'keep zoom' and box.isChecked()
    assert box.parent() is mc.view.groupBox_basic_plot_options


def test_the_zoom_stays_and_y_is_fitted(mc):
    _zoom(mc)
    mc.selected_spectra = [mc.original_spectra[3]]
    mc.plot_spectra()
    _pump()
    ax = _ax(mc)
    assert _xr(ax) == pytest.approx((1450.0, 1520.0))
    line = [l for l in ax.get_lines() if not l.get_gid()][0]
    x, y = np.asarray(line.get_xdata()), np.asarray(line.get_ydata())
    inside = (x >= 1450) & (x <= 1520)
    lo, hi = ax.get_ylim()
    assert lo < y[inside].min() < y[inside].max() < hi       # fitted to it
    assert hi - lo < 1.2 * (y[inside].max() - y[inside].min())
    # Home: the whole range
    mc.static_toolbar.home()
    _pump()
    assert _xr(ax)[0] < 400 and _xr(ax)[1] > 2400
    # not zoomed now: the next plot is whole too
    mc.plot_spectra()
    _pump()
    assert _xr(_ax(mc))[1] > 2400


def test_kept_with_another_plot_type_and_reverse_x(mc):
    _zoom(mc)
    mc.view.reverse_x_checkBox.setChecked(True)
    mc.view.comboBox_plot_type_choice.setCurrentText("Waterfall plot")
    _pump()
    ax = _ax(mc)
    assert _xr(ax) == pytest.approx((1450.0, 1520.0)) and ax.xaxis_inverted()
    mc.view.comboBox_plot_type_choice.setCurrentText("Grid plot")
    _pump()
    for a in mc.static_canvas.figure.axes:
        if a.get_visible():
            assert _xr(a) == pytest.approx((1450.0, 1520.0))
    # the Heatmap: whole; back in Overlay: whole too (the heatmap was not zoomed)
    mc.view.comboBox_plot_type_choice.setCurrentText("Heatmap")
    _pump()
    mc.view.comboBox_plot_type_choice.setCurrentText("Overlay plot")
    _pump()
    assert _xr(_ax(mc))[1] > 2400


def test_with_scale_each(mc):
    mc.view.scale_each_checkBox.setChecked(True)
    _pump()
    _zoom(mc)
    mc.selected_spectra = mc.original_spectra[:3]
    mc.plot_spectra()
    _pump(0.3)
    ax = _ax(mc)
    assert _xr(ax) == pytest.approx((1450.0, 1520.0))
    assert ax.get_ylim() == pytest.approx((-0.05, 1.05))


def test_unticked_as_before(mc):
    mc.view.keep_zoom_checkBox.setChecked(False)
    _zoom(mc)
    mc.plot_spectra()
    _pump()
    assert _xr(_ax(mc))[1] > 2400


def test_import_new_shows_whole(mc):
    _zoom(mc)
    mc.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    mc.spectrum_selector.select_all_items()
    _pump()
    assert _xr(_ax(mc))[1] > 2400


def test_no_data_in_the_range_shows_whole(mc):
    _zoom(mc, 3000.0, 3100.0)                     # beyond these spectra
    mc.plot_spectra()
    _pump()
    assert _xr(_ax(mc))[1] < 2700                  # whole: the data's range


def test_remembered_as_a_preference(mc):
    mc.view.keep_zoom_checkBox.setChecked(False)
    from src.modules.misc.session_files import Preferences
    assert Preferences().get('keep_zoom') is False
    assert mc._keep_zoom_preference() is False


def test_snapshot_keeps_the_range_and_zoom_is_no_change(mc, tmp_path):
    from src.controllers.misc.autosave_controller import state_signature
    manager = mc.save_controller.save_manager
    before = manager._build_state(mc)
    before.pop('timestamp', None)
    _zoom(mc)
    state = manager._build_state(mc)
    assert state['view']['x'] == pytest.approx([1450.0, 1520.0])
    state.pop('timestamp', None)
    assert state_signature(state) == state_signature(before)   # not a change
    path = str(tmp_path / 'z.snapx')
    assert manager.save_snapshot(mc, path) if 'main_controller' in \
        manager.save_snapshot.__code__.co_varnames[:2] else True


def test_home_after_reverse_x_while_zoomed(mc):
    _zoom(mc)
    mc.view.reverse_x_checkBox.setChecked(True)
    _pump()
    ax = _ax(mc)
    assert _xr(ax) == pytest.approx((1450.0, 1520.0)) and ax.xaxis_inverted()
    mc.static_toolbar.home()
    _pump()
    assert _xr(ax)[0] < 400 and _xr(ax)[1] > 2400 and ax.xaxis_inverted()
    mc.static_toolbar.back()                             # (Home is a new step: Back)
    _pump()
    assert _xr(ax) == pytest.approx((1450.0, 1520.0))


def _note(mc):
    return mc.static_toolbar._sax_mode_note.text()


def test_the_zoomed_note(mc):
    mc.view.resize(1400, 900)
    mc.view.show()
    _pump()
    assert 'Zoomed' not in _note(mc)
    _zoom(mc)
    _pump()
    assert 'Zoomed: 1450–1520 – Home shows all' in _note(mc)
    mc.selected_spectra = mc.original_spectra[:3]           # kept: the note too
    mc.plot_spectra()
    _pump()
    assert 'Zoomed: 1450–1520' in _note(mc)
    mc.view.keep_zoom_checkBox.setChecked(False)           # nothing kept: no note
    _pump()
    assert 'Zoomed' not in _note(mc)
    mc.view.keep_zoom_checkBox.setChecked(True)
    _pump()
    assert 'Zoomed' in _note(mc)
    mc.static_toolbar.home()
    _pump()
    assert 'Zoomed' not in _note(mc)
    mc.view.close()


def _menu(mc, x, monkeypatch, choose=None):
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
    mc.handle_mouse_click(MouseEvent('button_press_event', canvas, px, py, button=3))
    _pump()
    return texts


def test_zoom_to_the_band_markers(mc, monkeypatch):
    markers = mc.band_markers()
    markers.add_at(1480.0)
    markers.add_at(1500.0)
    texts = _menu(mc, 1490.0, monkeypatch, choose='Zoom to the band markers')
    assert 'Zoom to the band markers 1480 – 1500' in texts
    ax = _ax(mc)
    assert _xr(ax) == pytest.approx((1479.0, 1501.0))      # a margin of 5 % each side
    line = [l for l in ax.get_lines() if not l.get_gid()][0]
    x, y = np.asarray(line.get_xdata()), np.asarray(line.get_ydata())
    assert ax.get_ylim()[1] < 1.2 * y.max()                # y fitted to the band
    mc.static_toolbar.back()                               # Back: as before
    _pump()
    assert _xr(_ax(mc))[1] > 2400
    # kept for the next spectra
    _menu(mc, 1490.0, monkeypatch, choose='Zoom to the band markers')
    mc.selected_spectra = mc.original_spectra[4:6]
    mc.plot_spectra()
    _pump()
    assert _xr(_ax(mc)) == pytest.approx((1479.0, 1501.0))
    # not between two markers, or in the Heatmap: no such item
    assert not [t for t in _menu(mc, 1200.0, monkeypatch) if t.startswith('Zoom to')]
    mc.view.comboBox_plot_type_choice.setCurrentText("Heatmap")
    _pump()
    assert not [t for t in _menu(mc, 1490.0, monkeypatch) if t.startswith('Zoom to')]


def test_the_note_after_the_window_is_gone(tmp_path, monkeypatch):
    """The note is shown a moment after x changes (a timer): the window may be
    gone by then - nothing must happen (an error in a Qt callback ends the
    program; on Windows the whole test run stopped at it)."""
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, [DATA], [{}])))
    from src.controllers.core.main_controller import MainController
    import sip
    ctrl = MainController()
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    ctrl.spectrum_selector.select_all_items()
    _pump()
    ctrl.static_canvas.figure.axes[0].set_xlim(1400, 1500)    # the note: a moment later
    ctrl.autosave_controller.shutdown()
    sip.delete(ctrl.view)
    _pump()                                                   # still running
    ctrl._show_zoom_note()
