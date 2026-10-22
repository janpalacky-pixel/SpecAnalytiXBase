"""Right-click -> "Open in New Window": the mouse works in the new window.

The plot is first drawn on a throw-away widget with its own toolbar and then
put into the new window. Its list of mouse handlers still held that
throw-away toolbar: every mouse movement printed "wrapped C/C++ object of
type QLabel has been deleted", and the new window's zoom, pan and x/y
read-out did nothing."""
import gc
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.backend_bases import MouseEvent
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TBA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')
PLOT_TYPES = ['Overlay plot', 'Grid plot', 'Waterfall plot', 'Mean ± SD',
              'Difference', 'Heatmap', 'Single spectrum']


@pytest.fixture(scope='module')
def mc(tmp_path_factory):
    os.environ['SPECANALYTIXBASE_DATA_DIR'] = str(tmp_path_factory.mktemp('appdata'))
    mp = pytest.MonkeyPatch()
    for name in ('information', 'warning', 'critical'):
        mp.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    mp.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    mp.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    controller = MainController()
    controller.import_controller._run_import(clear_first=True, file_paths=[TBA])
    app.processEvents()
    controller.selected_spectra = list(controller.original_spectra[:4])
    controller.spectra_list_widget.setCurrentRow(0)
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()
    mp.undo()


def _new_window(mc, plot_type):
    from src.modules.visualization.external_figure import create_external_figure
    combo = mc.view.comboBox_plot_type_choice
    combo.blockSignals(True)
    combo.setCurrentText(plot_type)
    combo.blockSignals(False)
    mc.plot_spectra()
    fig = create_external_figure(mc)
    gc.collect()                    # the throw-away widget and its toolbar are gone
    app.processEvents()
    fig.canvas.callbacks.exception_handler = None      # an error in a handler fails the test
    return fig


def _mouse(fig, kind, xy, button=None):
    fig.canvas.callbacks.process(kind, MouseEvent(kind, fig.canvas, *xy, button=button))


@pytest.mark.parametrize('plot_type', PLOT_TYPES)
def test_moving_the_mouse_shows_the_position(mc, plot_type):
    fig = _new_window(mc, plot_type)
    try:
        ax = next(a for a in fig.axes if a.get_label() != '<colorbar>')
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        _mouse(fig, 'motion_notify_event', ax.transData.transform(((x0 + x1) / 2, (y0 + y1) / 2)))
        assert fig.canvas.manager.toolbar.locLabel.text()
    finally:
        plt.close(fig)


def test_zoom_works_in_the_new_window(mc):
    fig = _new_window(mc, 'Overlay plot')
    try:
        ax = fig.axes[0]
        lo, hi = sorted(ax.get_xlim())
        a = lo + 0.25 * (hi - lo)
        b = lo + 0.5 * (hi - lo)
        y = np.mean(ax.get_ylim())
        fig.canvas.manager.toolbar.zoom()
        start = ax.transData.transform((a, y + 0.1 * np.ptp(ax.get_ylim())))
        end = ax.transData.transform((b, y - 0.1 * np.ptp(ax.get_ylim())))
        _mouse(fig, 'button_press_event', start, button=1)
        _mouse(fig, 'motion_notify_event', end, button=1)
        _mouse(fig, 'button_release_event', end, button=1)
        assert sorted(ax.get_xlim()) == pytest.approx([a, b], rel=0.02)
    finally:
        plt.close(fig)
