"""Right-click -> "Open in New Window" for every plot type.

Regression test: the old implementation moved the axes into a new pyplot
figure (ax.figure = new_fig), which current matplotlib refuses with
"Can not put single artist in more than one figure" -- the feature failed
for every plot type and no test noticed."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib.pyplot as plt
import pytest
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


@pytest.mark.parametrize('plot_type', PLOT_TYPES)
def test_open_in_new_window(mc, plot_type):
    from src.modules.visualization.external_figure import create_external_figure
    combo = mc.view.comboBox_plot_type_choice
    combo.blockSignals(True)
    combo.setCurrentText(plot_type)
    combo.blockSignals(False)
    assert combo.currentText() == plot_type
    mc.plot_spectra()
    before = set(plt.get_fignums())
    fig = create_external_figure(mc)
    try:
        assert fig is not None
        assert set(plt.get_fignums()) - before, "no new window was registered"
        assert any(ax.get_visible() and (ax.lines or ax.images or ax.collections)
                   for ax in fig.axes), "the new window is empty"
        assert fig.canvas.manager is not None
        fig.canvas.draw()
    finally:
        if fig is not None:
            plt.close(fig)
