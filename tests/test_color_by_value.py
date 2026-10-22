"""Line colours > Colours by value (also right-click on the plot): the lines
of the Overlay, Waterfall and Grid plots coloured along a colour scale by
their order, a number in their name or a stored value, with a colour bar;
spectra without a value grey; kept in snapshots."""
import glob
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from matplotlib.colors import to_hex
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.visualization import color_by_value as cbv

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TBA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')
JWB = sorted(glob.glob(os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD melting', '*.jwb')))[0]


# --- the values (no window) ------------------------------------------------------------

@pytest.mark.parametrize('name, numbers', [
    ('TBA_45C : 0003', [45, 3]), ('CD_melt : CD [mdeg] T=10.04C', [10.04]), ('pH 7,4', [7.4]),
    ('T = -5 C', [-5]), ('run-5', [5]), ('no number', [])])
def test_numbers_in_a_name(name, numbers):
    assert cbv.numbers_in(name) == pytest.approx(numbers)


def test_values_colours_and_grey_for_missing():
    spectra = [{'label': 'a 10'}, {'label': 'b'}, {'label': 'c 30'}]
    s = {'mode': 'name', 'number': -1, 'colormap': 'viridis'}
    vals = cbv.values(spectra, s)
    assert vals == [10, None, 30]
    cols = cbv.colours(vals, s)
    assert cols[0] == '#440154' and cols[2] == '#fde725' and cols[1] == cbv.NO_VALUE_COLOR
    assert cbv.colours(vals, dict(s, reverse=True))[0] == '#fde725'
    assert cbv.values(spectra, {'mode': 'order'}) == [1, 2, 3]
    meta = [{'label': 'x', 'metadata': {'temperature_C': 25.0, 'valid_points': 5, 'unique_id': 'u'}}]
    assert cbv.metadata_keys(meta) == ['temperature_C']
    assert cbv.values(meta, {'mode': 'metadata', 'metadata_key': 'temperature_C'}) == [25.0]
    assert cbv.normalized({'mode': 'nonsense', 'colormap': 'x'})['mode'] == 'off'


# --- in the program ---------------------------------------------------------------------

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
    app.processEvents()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _line_colours(mc):
    ax = [a for a in mc.static_canvas.figure.axes if a.get_label() != '<colorbar>'][0]
    return [to_hex(line.get_color()) for line in ax.lines]


def _colorbars(mc):
    return [a for a in mc.static_canvas.figure.axes if a.get_label() == '<colorbar>']


def test_overlay_by_temperature_with_a_colour_bar(mc):
    c = mc.color_by_value_controller
    assert mc.line_colours_controller.action in mc.view.menuView.actions()
    c.set_settings({'mode': 'metadata', 'metadata_key': 'temperature_C', 'colormap': 'coolwarm'})
    app.processEvents()
    temps = [s['metadata']['temperature_C'] for s in mc.selected_spectra]
    expected = cbv.colours(temps, c.settings)
    assert _line_colours(mc) == expected and len(set(expected)) > 3
    bars = _colorbars(mc)
    assert len(bars) == 1 and bars[0].get_ylabel() == 'temperature_C'
    assert mc.view.line_colours_comboBox.currentText() == 'colours by value'
    c.set_settings({'mode': 'name', 'number': -1})                  # T=10.04C ... in the names
    app.processEvents()
    assert _line_colours(mc) == cbv.colours(temps, c.settings)
    c.set_settings({'mode': 'off'})
    app.processEvents()
    assert not _colorbars(mc) and mc.view.line_colours_comboBox.currentText() != 'colours by value'


@pytest.mark.parametrize('plot_type', ['Waterfall plot', 'Grid plot'])
def test_waterfall_and_grid(mc, plot_type):
    mc.grid_settings.update(rows=3, columns=5)
    mc.view.comboBox_plot_type_choice.setCurrentText(plot_type)
    mc.color_by_value_controller.set_settings({'mode': 'order'})
    app.processEvents()
    axes = [a for a in mc.static_canvas.figure.axes if a.get_label() != '<colorbar>' and a.get_visible()]
    used = {to_hex(l.get_color()) for a in axes for l in a.lines}
    assert len(used) > 3 and len(_colorbars(mc)) == 1


def test_other_plot_types_keep_their_colours(mc):
    mc.view.comboBox_plot_type_choice.setCurrentText('Heatmap')
    mc.color_by_value_controller.set_settings({'mode': 'order'})
    app.processEvents()
    assert mc.color_by_value_controller.last_values is None


def test_window_preview_and_apply(mc):
    from src.views.dialogs.visualization.color_by_value_dialog import ColorByValueDialog
    applied = []
    dlg = ColorByValueDialog(None, mc.selected_spectra, {}, apply_callback=applied.append)
    assert not dlg.cmap_combo.isEnabled()                            # Off
    dlg.mode_combo.setCurrentIndex(cbv.MODES.index('metadata'))
    assert dlg.key_combo.currentText() == 'temperature_C' and dlg.preview.rowCount() > 0
    assert '15 of 15 spectra have a value' in dlg.summary.text()
    dlg.mode_combo.setCurrentIndex(cbv.MODES.index('name'))
    dlg.number_combo.setCurrentIndex(dlg.number_combo.findData(0))  # the first number: "1" of sample_1
    assert dlg.preview.item(0, 1).text() == '1'
    dlg.apply()
    assert applied[-1]['mode'] == 'name' and applied[-1]['number'] == 0


def test_kept_in_snapshots(mc, tmp_path):
    c = mc.color_by_value_controller
    c.set_settings({'mode': 'metadata', 'metadata_key': 'temperature_C', 'colormap': 'plasma'})
    state = mc.save_controller.save_manager._build_state(mc)
    assert state['plot_settings']['color_by_value']['colormap'] == 'plasma'
    c.set_settings({'mode': 'off'})
    mc.save_controller.save_manager._restore_ui_state(mc, state)
    assert c.settings['mode'] == 'metadata' and c.settings['colormap'] == 'plasma'
