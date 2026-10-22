"""Plot Properties in one window (button below the spectra list, right-click
on the list): the table of what the selected spectra have now, Apply without
closing, Reset to defaults, Line colours...; and long tooltips in several
lines."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

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
    controller.import_controller._run_import(clear_first=True, file_paths=[TBA])
    for i in range(3):
        controller.spectra_list_widget.item(i).setSelected(True)
    app.processEvents()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _open(mc, monkeypatch, run):
    from src.views.dialogs.visualization import custom_plot_properties_dialog as cpd
    seen = {}

    def fake_exec(dialog):
        seen['dialog'] = dialog
        return run(dialog)
    monkeypatch.setattr(cpd.CustomPlotPropertiesDialog, 'exec_', fake_exec)
    mc.plot_properties_button.click()
    return seen['dialog']


def test_one_window_table_apply_and_reset(mc, monkeypatch):
    assert isinstance(mc.plot_properties_button, QPushButton)
    assert mc.plot_properties_button.menu() is None
    opened = []
    monkeypatch.setattr(mc.line_colours_controller, 'show_dialog', lambda: opened.append(1))

    def run(dialog):
        assert dialog.table.rowCount() == 3
        assert {dialog.table.item(r, 5).text() for r in range(3)} == {'default'}
        dialog.line_color_combo.setCurrentText('red')
        dialog.line_width_spin.setValue(2.5)
        dialog.apply_button.click()                       # applied, window still there
        assert {dialog.table.item(r, 5).text() for r in range(3)} == {'own'}
        assert dialog.table.item(0, 1).text() == 'red' and dialog.table.item(0, 3).text() == '2.5'
        assert mc.line_colours_controller.mode() == 'own'
        dialog.line_colours_button.click()
        dialog.reset_button.click()
        assert {dialog.table.item(r, 5).text() for r in range(3)} == {'default'}
        assert dialog.line_color_combo.currentText() == 'blue'
        return QDialog.Rejected
    _open(mc, monkeypatch, run)
    assert opened == [1]
    assert mc.custom_plot_properties_manager.spectrum_properties == {}


def test_ok_applies(mc, monkeypatch):
    def run(dialog):
        dialog.line_style_combo.setCurrentText('--')
        return QDialog.Accepted
    _open(mc, monkeypatch, run)
    props = mc.custom_plot_properties_manager.spectrum_properties
    assert len(props) == 3 and all(p['linestyle'] == '--' for p in props.values())


def test_spectra_list_menu_has_one_plot_properties_entry(mc):
    import inspect
    src = inspect.getsource(type(mc).show_spectra_list_context_menu)
    assert 'Plot Properties\\u2026' in src and 'Show Info' not in src and 'Modify' not in src


def test_long_tooltips_are_wrapped():
    from src.views import tooltips
    short = 'A short tip.'
    assert tooltips.wrapped(short) == short
    assert tooltips.wrapped('<b>rich</b> ' + 'x ' * 100).startswith('<b>')
    long = 'Prominence: ' + 'how much the peak stands out above the valleys around it, ' * 4
    lines = tooltips.wrapped(long).split('\n')
    assert len(lines) > 2 and max(len(l) for l in lines) <= tooltips.WIDTH


def test_tooltip_filter_wraps_when_shown():
    from PyQt5.QtCore import QEvent, QPoint
    from PyQt5.QtGui import QHelpEvent
    from src.views import tooltips
    tooltips.install(app)
    try:
        b = QPushButton('x')
        b.setToolTip('word ' * 60)
        app.sendEvent(b, QHelpEvent(QEvent.ToolTip, QPoint(1, 1), QPoint(1, 1)))
        assert '\n' in b.toolTip()
    finally:
        tooltips.uninstall()
