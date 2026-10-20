"""'reverse x' in Basic plot options: the main plot (every plot type) and Open
in New Window draw the x-axis from high to low; only the direction changes,
not the data or the zoomed range; saved in snapshots (older snapshots: off)."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')
PLOT_TYPES = ["Single spectrum", "Overlay plot", "Grid plot", "Waterfall plot", "Mean ± SD",
              "Difference", "Heatmap"]


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


def _plot_axes(fig):
    return [ax for ax in fig.axes if ax.get_label() != '<colorbar>']


def test_checkbox_sits_in_basic_plot_options_and_is_off(mc):
    box = mc.view.reverse_x_checkBox
    assert box.text() == 'reverse x' and not box.isChecked()
    assert box.parent() is mc.view.groupBox_basic_plot_options
    mc.plot_spectra()
    assert all(not ax.xaxis_inverted() for ax in _plot_axes(mc.static_canvas.figure))


@pytest.mark.parametrize('plot_type', PLOT_TYPES)
def test_every_plot_type_is_drawn_high_to_low(mc, plot_type):
    if plot_type == "Grid plot":                           # 4 panels sharing one x-axis
        mc.grid_settings['rows'] = mc.grid_settings['columns'] = 2
        mc.view.link_x_axes_checkBox.setChecked(True)
        mc.view.comboBox_linking_x_axes.setCurrentText("all")
    mc.view.comboBox_plot_type_choice.setCurrentText(plot_type)
    mc.plot_spectra()
    normal = [sorted(ax.get_xlim()) for ax in _plot_axes(mc.static_canvas.figure)]
    mc.view.reverse_x_checkBox.setChecked(True)
    mc.plot_spectra()
    fig = mc.static_canvas.figure
    axes = _plot_axes(fig)
    assert axes
    for ax in axes:
        lo, hi = ax.get_xlim()
        assert lo > hi, (plot_type, ax.get_xlim())
    # the same range, only turned around (grid plot: shared axes not flipped twice)
    assert len(axes) == len(normal) and (plot_type != "Grid plot" or len(axes) == 4)
    assert np.allclose(sorted(sorted(ax.get_xlim()) for ax in axes), sorted(normal))
    for cb in [ax for ax in fig.axes if ax.get_label() == '<colorbar>']:
        assert not cb.xaxis_inverted()


def test_ticking_turns_the_shown_plot_without_drawing_it_again(mc):
    mc.view.comboBox_plot_type_choice.setCurrentText("Overlay plot")
    mc.plot_spectra()
    fig = mc.static_canvas.figure
    ax = _plot_axes(fig)[0]
    lines = list(ax.lines)
    ax.set_xlim(900, 1200)                                   # zoomed in
    mc.view.reverse_x_checkBox.setChecked(True)
    assert mc.static_canvas.figure is fig and list(ax.lines) == lines
    assert ax.get_xlim() == pytest.approx((1200, 900))      # same range, other way round
    mc.view.reverse_x_checkBox.setChecked(False)
    assert ax.get_xlim() == pytest.approx((900, 1200))


def test_data_and_cursor_values_do_not_change(mc):
    mc.view.comboBox_plot_type_choice.setCurrentText("Overlay plot")
    mc.plot_spectra()
    ax = _plot_axes(mc.static_canvas.figure)[0]
    before = mc.plot_cursor_controller.readout_text(ax, 1000.0, None)
    data_before = [np.array(s['y_scale'], copy=True) for s in mc.selected_spectra]
    mc.view.reverse_x_checkBox.setChecked(True)
    mc.plot_spectra()
    ax = _plot_axes(mc.static_canvas.figure)[0]
    assert mc.plot_cursor_controller.readout_text(ax, 1000.0, None) == before
    for s, y in zip(mc.selected_spectra, data_before):
        assert np.array_equal(s['y_scale'], y)


def test_open_in_new_window_is_reversed_too(mc):
    import matplotlib.pyplot as plt
    from src.modules.visualization.external_figure import create_external_figure
    mc.view.comboBox_plot_type_choice.setCurrentText("Overlay plot")
    mc.view.reverse_x_checkBox.setChecked(True)
    fig = create_external_figure(mc)
    try:
        assert fig is not None
        assert all(ax.xaxis_inverted() for ax in _plot_axes(fig))
    finally:
        plt.close('all')


def test_saved_in_snapshots_and_older_snapshots_are_drawn_low_to_high(mc):
    mgr = mc.save_controller.save_manager
    mc.view.reverse_x_checkBox.setChecked(True)
    state = mgr._build_state(mc)
    assert state['plot_settings']['reverse_x'] is True
    mc.view.reverse_x_checkBox.setChecked(False)
    mgr._restore_ui_state(mc, state)
    assert mc.view.reverse_x_checkBox.isChecked()
    old = dict(state, plot_settings={k: v for k, v in state['plot_settings'].items()
                                     if k != 'reverse_x'})
    mgr._restore_ui_state(mc, old)
    assert not mc.view.reverse_x_checkBox.isChecked()
