"""File -> Copy plot to clipboard (Ctrl+Shift+C, also the plot's right-click
menu): the plot as a picture at 300 dpi, in the size it has on the screen
(the resolution is stored in the picture), on a white background."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TBA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    controller = MainController()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def test_menu_entry_shortcut_and_icon(mc):
    a = mc.view.actionCopyPlot
    assert a in mc.view.menuFile.actions() and a.shortcut().toString() == 'Ctrl+Shift+C'
    assert not a.icon().isNull()
    texts = [x.text() for x in mc.view.menuFile.actions()]
    assert texts.index('Copy plot to clipboard') == texts.index('Methods report for publication…') + 1


def test_nothing_to_copy_without_a_plot(mc):
    QApplication.clipboard().clear()
    assert mc.copy_plot_to_clipboard() is None
    assert QApplication.clipboard().image().isNull()


def test_the_plot_is_copied_at_300_dpi_in_its_screen_size(mc):
    mc.import_controller._run_import(clear_first=True, file_paths=[TBA])
    mc.spectrum_selector.select_all_items()
    app.processEvents()
    mc.plot_spectra()
    app.processEvents()
    fig = mc.static_canvas.figure
    dpi_before, size = fig.dpi, fig.get_size_inches()
    image = mc.view.actionCopyPlot.trigger() or QApplication.clipboard().image()
    assert not image.isNull()
    assert abs(image.width() - size[0] * 300) <= 2 and abs(image.height() - size[1] * 300) <= 2
    assert abs(image.dotsPerMeterX() - 300 / 0.0254) < 2          # pasted in the screen size
    assert image.pixelColor(2, 2).name() == '#ffffff'              # white background
    assert fig.dpi == dpi_before                                   # the plot on screen unchanged
    assert 'copied' in mc.view.statusBar().currentMessage()
