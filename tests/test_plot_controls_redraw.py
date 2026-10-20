"""The plot controls that redraw the plot directly (X-scale, Y-scale, Link x / y
axes and their direction, Waterfall offset, Mean +/- SD and Difference boxes,
Heatmap colours) redraw it without an error.

Found 2026-10-20 (it was there since the first version): Qt passes the new
value of such a control (an index, a check state) to plot_spectra, which took
it for its progress callback and called it -- "'int' object is not callable"
before anything was drawn. The plot was not redrawn, and on Windows the error
inside a Qt callback closed the program (the test run stopped in
test_reverse_x_axis, whose Grid case ticks Link x-axes)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')


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
    app.processEvents()
    ctrl.spectrum_selector.select_all_items()
    app.processEvents()
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda t, v, tb: errors.append(f"{t.__name__}: {v}"))
    ctrl.errors = errors
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def _toggle(box):
    box.setChecked(not box.isChecked())


@pytest.mark.parametrize('plot_type', ["Overlay plot", "Grid plot"])
def test_scale_and_link_controls_redraw_without_an_error(mc, plot_type):
    v = mc.view
    v.comboBox_plot_type_choice.setCurrentText(plot_type)
    app.processEvents()
    v.x_scale_comboBox.setCurrentText("log")
    app.processEvents()
    assert mc.errors == []
    if plot_type == "Overlay plot":
        assert mc.static_canvas.figure.axes[0].get_xscale() == 'log'      # really redrawn
    v.y_scale_comboBox.setCurrentText("log")
    app.processEvents()
    assert mc.errors == []
    if plot_type == "Overlay plot":
        assert mc.static_canvas.figure.axes[0].get_yscale() == 'log'
    v.x_scale_comboBox.setCurrentText("linear")
    v.y_scale_comboBox.setCurrentText("linear")
    for change in (lambda: _toggle(v.link_x_axes_checkBox), lambda: _toggle(v.link_y_axes_checkBox),
                   lambda: v.comboBox_linking_x_axes.setCurrentText("row"),
                   lambda: v.comboBox_linking_y_axes.setCurrentText("col")):
        change()
        app.processEvents()
    assert mc.errors == []


def test_mode_specific_controls_redraw_without_an_error(mc):
    v = mc.view
    v.comboBox_plot_type_choice.setCurrentText("Waterfall plot")
    v.waterfall_offset_spinBox.setValue(v.waterfall_offset_spinBox.value() + 1)
    v.comboBox_plot_type_choice.setCurrentText("Mean ± SD")
    _toggle(v.mean_sd_show_individual_checkBox)
    v.comboBox_plot_type_choice.setCurrentText("Difference")
    _toggle(v.difference_show_ref_checkBox)
    if v.difference_reference_comboBox.count() > 1:
        v.difference_reference_comboBox.setCurrentIndex(1)
    v.comboBox_plot_type_choice.setCurrentText("Heatmap")
    v.heatmap_colormap_comboBox.setCurrentIndex(min(1, v.heatmap_colormap_comboBox.count() - 1))
    v.heatmap_interpolation_comboBox.setCurrentIndex(
        min(1, v.heatmap_interpolation_comboBox.count() - 1))
    app.processEvents()
    assert mc.errors == []


def test_a_real_progress_callback_is_still_used(mc):
    calls = []
    mc.view.comboBox_plot_type_choice.setCurrentText("Overlay plot")
    mc.plot_spectra(progress_callback=lambda: calls.append(1))
    assert calls and mc.errors == []

