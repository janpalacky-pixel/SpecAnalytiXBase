"""Line colours in one place: automatic colours, own colours (Plot
Properties) or colours by value - the list in Basic plot options with its
"…" button, View > Line colours…, the plot's right-click menu and the
spectra list's right-click menu; old snapshots keep their colours; setting a
colour in Plot Properties switches to own colours."""
import glob
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from matplotlib.colors import to_hex
from PyQt5.QtWidgets import QApplication, QDialog, QMenu, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JWB = sorted(glob.glob(os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD melting', '*.jwb')))[0]


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths),
                                                 [{'jws_selected_channels': [0]} for _ in file_paths])))
    controller = MainController()
    controller.import_controller._run_import(clear_first=True, file_paths=[JWB])
    controller.spectrum_selector.select_all_items()
    controller.view.comboBox_plot_type_choice.setCurrentText('Overlay plot')
    app.processEvents()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _colours(mc):
    ax = mc.static_canvas.figure.axes[0]
    return [to_hex(line.get_color()) for line in ax.lines]


def _colorbars(mc):
    return [a for a in mc.static_canvas.figure.axes if a.get_label() == '<colorbar>']


def _choose(mc, text):
    combo = mc.view.line_colours_comboBox
    combo.setCurrentIndex(combo.findText(text))
    app.processEvents()


def test_the_list_switches_the_colours(mc):
    combo = mc.view.line_colours_comboBox
    assert [combo.itemText(i) for i in range(combo.count())] == \
        ['automatic colours', 'own colours', 'colours by value']
    assert combo.currentText() == 'automatic colours'
    assert len(set(_colours(mc))) > 3                       # the standard sequence
    _choose(mc, 'own colours')
    assert set(_colours(mc)) == {to_hex('blue')}            # nothing set: the default colour
    assert mc.use_automatic_line_colors is False
    _choose(mc, 'colours by value')
    assert len(set(_colours(mc))) > 3 and len(_colorbars(mc)) == 1
    _choose(mc, 'automatic colours')
    assert not _colorbars(mc) and mc.use_automatic_line_colors is True
    assert mc.color_by_value_controller.settings['mode'] == 'off'


def test_by_value_comes_back_with_its_settings(mc):
    lc = mc.line_colours_controller
    lc.set_mode('value', {'mode': 'metadata', 'metadata_key': 'temperature_C', 'colormap': 'plasma'})
    assert mc.view.line_colours_comboBox.currentText() == 'colours by value'
    _choose(mc, 'own colours')
    assert lc.mode() == 'own'
    _choose(mc, 'colours by value')
    s = mc.color_by_value_controller.settings
    assert s['mode'] == 'metadata' and s['colormap'] == 'plasma'


def test_menus_and_the_button(mc, monkeypatch):
    from src.views.dialogs.visualization import line_colours_dialog as lcd
    opened = []
    monkeypatch.setattr(lcd.LineColoursDialog, 'exec_', lambda self: opened.append(self) or 0)
    lc = mc.line_colours_controller
    assert lc.action in mc.view.menuView.actions() and lc.action.text() == 'Line colours…'
    lc.action.trigger()
    mc.view.line_colours_button.click()
    assert len(opened) == 2 and opened[0].mode() == 'automatic'
    menu = QMenu()
    sub = lc.add_to_menu(menu)
    texts = [a.text() for a in sub.actions() if not a.isSeparator()]
    assert texts == ['Automatic colours', 'Own colours', 'Colours by value', 'Line colours…']
    assert [a.isChecked() for a in sub.actions()[:3]] == [True, False, False]
    sub.actions()[2].trigger()                                 # Colours by value
    assert lc.mode() == 'value' and _colorbars(mc)
    names = [a.text() for a in mc.plot_properties_button.menu().actions()]
    assert 'Line colours…' in names


def test_the_window(mc):
    from src.views.dialogs.visualization.line_colours_dialog import LineColoursDialog
    applied, own = [], []
    dlg = LineColoursDialog(None, mc.selected_spectra, 'own', {},
                            apply_callback=lambda m, s: applied.append((m, s)),
                            set_own_colours=lambda: own.append(1))
    assert dlg.mode() == 'own' and not dlg.panel.isEnabled() and dlg.own_button.isEnabled()
    modes = [dlg.panel.mode_combo.itemData(i) for i in range(dlg.panel.mode_combo.count())]
    assert 'off' not in modes                                  # "off" = the other two choices
    dlg.own_button.click()
    assert own == [1]
    dlg.radios['value'].setChecked(True)
    assert dlg.panel.isEnabled() and not dlg.own_button.isEnabled()
    dlg.panel.mode_combo.setCurrentIndex(modes.index('metadata'))
    dlg.apply()
    assert applied[-1][0] == 'value' and applied[-1][1]['metadata_key'] == 'temperature_C'


def test_setting_a_colour_in_plot_properties_switches_to_own(mc, monkeypatch):
    from src.controllers.visualization import custom_plot_properties_controller as cpc
    wanted = {}

    def fake_exec(self):
        return QDialog.Accepted

    def fake_settings(self):
        s = dict(self.current_settings)
        s.update(wanted)
        return s
    monkeypatch.setattr(cpc.CustomPlotPropertiesDialog, 'exec_', fake_exec)
    monkeypatch.setattr(cpc.CustomPlotPropertiesDialog, 'get_settings', fake_settings)
    lc = mc.line_colours_controller
    wanted.update(linewidth=2.5)                               # no new colour: no switch
    mc.custom_plot_properties_controller.show_dialog()
    assert lc.mode() == 'automatic'
    wanted.update(linecolor='red')
    mc.custom_plot_properties_controller.show_dialog()
    assert lc.mode() == 'own' and mc.view.line_colours_comboBox.currentText() == 'own colours'
    mc.plot_spectra()
    assert to_hex('red') in _colours(mc)


def test_snapshots(mc):
    lc = mc.line_colours_controller
    manager = mc.save_controller.save_manager
    lc.set_mode('value', {'mode': 'order', 'colormap': 'coolwarm'})
    state = manager._build_state(mc)
    lc.set_mode('own')
    manager._restore_ui_state(mc, state)
    assert mc.view.line_colours_comboBox.currentText() == 'colours by value'
    # an older snapshot: automatic line colours off, no "colour by value"
    old = manager._build_state(mc)
    old['plot_settings'].pop('color_by_value', None)
    old['plot_settings']['use_automatic_line_colors'] = False
    manager._restore_ui_state(mc, old)
    assert lc.mode() == 'own' and mc.view.line_colours_comboBox.currentText() == 'own colours'
