"""CD data-quality warning: wavelengths where CD is unreliable because the
detector got too little light (HT voltage or absorbance too high)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import glob

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_io import cd_quality as cq
from src.modules.data_io import jasco_jws_reader as reader
from src.modules.misc.session_files import Preferences

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JWB_FILES = sorted(glob.glob(os.path.join(ROOT, 'resources', 'test_data', 'real',
                                          'CD melting', '*.jwb')))
JWB = JWB_FILES[0]


def _q(x, values, source='Abs'):
    return cq.build_quality(np.asarray(x, float), np.asarray(values, float), source, 1)


# ===========================================================================
# The rule (no Qt)
# ===========================================================================

def test_reference_channel_prefers_ht_then_abs():
    assert cq.pick_reference_channel({0: 'CD', 1: 'Abs', 2: 'HT'}) == (2, 'HT')
    assert cq.pick_reference_channel({0: 'CD', 1: 'Abs'}) == (1, 'Abs')
    assert cq.pick_reference_channel({0: 'CD', 1: 'Signal'}) is None


def test_ranges_reach_halfway_to_the_next_reliable_point():
    q = _q([200, 201, 202, 203, 204], [4.0, 3.5, 1.0, 1.0, 1.0])
    assert cq.unreliable_ranges(q) == [(200.0, 201.5)]
    assert cq.unreliable_ranges(q, abs_limit=0.5) == [(200.0, 204.0)]
    assert cq.unreliable_ranges(q, abs_limit=5) == []


def test_ht_uses_the_ht_limit_and_descending_input_is_sorted():
    q = _q([204, 203, 202, 201, 200], [500, 500, 650, 720, 800], source='HT')
    assert q['x'] == [200, 201, 202, 203, 204] and q['unit'] == 'V'
    assert cq.unreliable_ranges(q) == [(200.0, 201.5)]
    assert cq.unreliable_ranges(q, ht_limit=600) == [(200.0, 202.5)]
    assert cq.unreliable_ranges(q, abs_limit=0.1) == [(200.0, 201.5)]  # Abs limit not used


def test_several_ranges_single_points_and_missing_values():
    q = _q([0, 1, 2, 3, 4, 5, 6], [5, 0, 0, 5, np.nan, 0, 5])
    assert cq.unreliable_ranges(q) == [(0.0, 0.5), (2.5, 3.5), (5.5, 6.0)]


def test_invalid_quality_records_are_ignored():
    for bad in (None, {}, {'source': 'CD', 'x': [1], 'values': [1]},
                {'source': 'Abs', 'x': [1, 2], 'values': [1]}):
        assert cq.unreliable_ranges(bad) == []


def test_clip_and_merge():
    assert cq.clip_ranges([(0, 5), (8, 9)], 2, 8.5) == [(2, 5), (8, 8.5)]
    assert cq.merge_ranges([(4, 6), (0, 2), (1, 3)]) == [(0, 3), (4, 6)]


def test_unit_conversion_of_the_quality_trace():
    q = _q([200, 250, 500], [3, 1, 1])
    out = cq.convert_quality_x(q, lambda nm: 1e7 / nm, 'cm⁻¹')
    assert out['x'] == pytest.approx([2e4, 4e4, 5e4])
    assert out['values'] == [1, 1, 3]
    assert out['x_unit'] == 'cm⁻¹'
    assert q['x'] == [200, 250, 500]          # original untouched


def _meta(q=None, ctype='CD', file_type='jasco_jwb'):
    m = {'file_type': file_type, 'import_parameters': {'channel_type': ctype}}
    if q is not None:
        m['cd_quality'] = q
    return m


def test_import_summary_texts():
    assert cq.import_summary([_meta(ctype='Abs')]) is None
    assert cq.import_summary([_meta(file_type='text')]) is None
    assert 'could not be checked' in cq.import_summary([_meta()])
    ok = cq.import_summary([_meta(_q([200, 300], [1, 1]))])
    assert ok.startswith('✅') and 'absorbance 3' in ok
    low = cq.import_summary([_meta(_q([200, 201, 202, 203], [4, 4, 1, 1])),
                             _meta(_q([200, 201, 202, 203], [4, 4, 4, 1]))])
    assert 'below about 202 nm' in low and '2 CD spectra' in low, low
    some = cq.import_summary([_meta(_q([200, 201], [1, 1])), _meta(_q([200, 201], [4, 1]))])
    assert '1 (of 2) CD spectrum has' in some
    everywhere = cq.import_summary([_meta(_q([200, 300], [4, 4]))])
    assert 'EVERY wavelength' in everywhere and 'View → CD data quality' in everywhere


def test_limits_preferences(tmp_path):
    p = Preferences(str(tmp_path / 'p.json'))
    assert p.cd_quality_limits() == (cq.DEFAULT_HT_LIMIT_V, cq.DEFAULT_ABS_LIMIT)
    assert p.cd_quality_shading() is True
    p.set('cd_ht_limit_V', 600)
    p.set('cd_abs_limit', 'nonsense')
    assert p.cd_quality_limits() == (600.0, cq.DEFAULT_ABS_LIMIT)


# ===========================================================================
# Readers
# ===========================================================================

def _cd_and_other(spectra):
    cd = [s for s in spectra if s['metadata']['import_parameters']['channel_type'] == 'CD']
    other = [s for s in spectra if s not in cd]
    return cd, other


@pytest.mark.parametrize('path', JWB_FILES)
def test_sample_jwb_files_are_flagged_below_about_240_nm(path):
    cd, other = _cd_and_other(reader.read_jwb_data(path))
    assert cd and other
    assert all('cd_quality' not in s['metadata'] for s in other)
    for s in cd:
        q = s['metadata']['cd_quality']
        assert q['source'] == 'Abs' and q['channel_index'] == 1 and q['x_unit'] == 'nm'
        assert len(q['x']) == len(s['x_scale'])
        (lo, hi), = cq.unreliable_ranges(q)
        assert lo == pytest.approx(min(s['x_scale'])) and 225 < hi < 250


def test_quality_is_kept_when_only_the_cd_channel_is_imported():
    spectra = reader.read_jwb_data(JWB, selected_channels=[0])
    assert spectra and all('cd_quality' in s['metadata'] for s in spectra)


def test_temperature_scan_uses_the_matching_temperature(monkeypatch):
    x = np.linspace(260, 200, 4)
    y = np.zeros((3, 2, 4))
    y[0] = [[1, -1, 2, -2], [1, -1, 2, -2]]         # CD
    y[1] = [[0.5, 0.5, 0.5, 3], [0.5, 0.5, 3, 3]]   # Abs, worse when hot
    y[2] = [[300, 300, 650, 750], [300, 300, 750, 800]]  # HT
    monkeypatch.setattr(reader, '_read_jwb_streams', lambda p: {
        'n_channels': 3, 'n_spectra': 2, 'n_points': 4, 'x_start': 260.0, 'x_end': 200.0,
        'temperatures': np.array([20.0, 90.0]), 'y': y, 'sample_name': '', 'comment': ''})
    cd, _ = _cd_and_other(reader.read_jwb_data(__file__))
    assert [s['metadata']['cd_quality']['source'] for s in cd] == ['HT', 'HT']
    assert [cq.unreliable_ranges(s['metadata']['cd_quality']) for s in cd] == [
        [(200.0, 210.0)], [(200.0, 230.0)]]
    assert x[-1] == 200


def test_jws_single_scan(monkeypatch, tmp_path):
    f = tmp_path / 'scan.jws'
    f.write_bytes(b'')
    ys = np.array([[1, -1, 2, -2], [0.2, 0.5, 3.5, 4.0]], dtype='<f4')
    monkeypatch.setattr(reader, '_read_ole_streams',
                        lambda data, wanted: {'DataInfo': b'', 'Y-Data': ys.tobytes()})
    monkeypatch.setattr(reader, '_parse_data_info', lambda b: {
        'n_channels': 2, 'n_points': 4, 'x_start': 230.0, 'x_end': 200.0})
    spectra = reader.read_jws_data(str(f))
    cd, (absorb,) = _cd_and_other(spectra)
    assert cq.unreliable_ranges(cd[0]['metadata']['cd_quality']) == [(200.0, 215.0)]
    assert 'cd_quality' not in absorb['metadata']
    # the user says channel 1 is not absorbance -> nothing to judge by
    spectra = reader.read_jws_data(str(f), channel_type_overrides={1: 'Signal'})
    assert all('cd_quality' not in s['metadata'] for s in spectra)


# ===========================================================================
# In the application
# ===========================================================================

@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    shown = []
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(
        lambda parent, title, text, *a, **k: shown.append((title, text)) or QMessageBox.Ok))
    for name in ('warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    controller = MainController()
    controller.shown_messages = shown
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _import(mc, path=JWB):
    mc.import_controller._run_import(clear_first=True, file_paths=[path])
    app.processEvents()


def _select_cd(mc):
    mc.selected_spectra = [s for s in mc.original_spectra
                           if 'cd_quality' in (s.get('metadata') or {})]
    assert mc.selected_spectra


def _spans(mc):
    return [p for ax in mc.static_canvas.figure.axes for p in ax.patches
            if p.get_gid() == 'cd_quality']


def _plot(mc, plot_type):
    mc.view.comboBox_plot_type_choice.blockSignals(True)
    mc.view.comboBox_plot_type_choice.setCurrentText(plot_type)
    mc.view.comboBox_plot_type_choice.blockSignals(False)
    mc.plot_spectra()


def test_import_message_mentions_unreliable_wavelengths(mc):
    _import(mc)
    results = [text for title, text in mc.shown_messages if title == 'Import Results']
    assert results and 'CD data quality' in results[-1] and 'below about' in results[-1]


def test_overlay_is_shaded_without_changing_the_axis_limits(mc):
    _import(mc)
    _select_cd(mc)
    mc.cd_quality_controller.set_shading(False)
    _plot(mc, 'Overlay plot')
    assert _spans(mc) == []
    xlim = mc.static_canvas.figure.axes[0].get_xlim()
    mc.cd_quality_controller.set_shading(True)
    assert len(_spans(mc)) == 1
    assert mc.static_canvas.figure.axes[0].get_xlim() == pytest.approx(xlim)
    legend = mc.static_canvas.figure.axes[0].get_legend()
    if legend is not None:
        assert all('cd' not in t.get_text().lower() or 'mdeg' in t.get_text().lower()
                   for t in legend.get_texts())


def test_changing_the_limits_redraws(mc):
    _import(mc)
    _select_cd(mc)
    _plot(mc, 'Overlay plot')
    span = _spans(mc)[0].get_window_extent()
    mc.cd_quality_controller.set_limits(700, 3.5)       # less strict -> narrower
    assert _spans(mc)[0].get_window_extent().width < span.width
    mc.cd_quality_controller.set_limits(700, 9.9)
    assert _spans(mc) == []


def test_grid_plot_shades_each_panel_and_heatmap_is_left_alone(mc):
    _import(mc)
    _select_cd(mc)
    mc.selected_spectra = mc.selected_spectra[:4]
    mc.grid_settings = {**mc.grid_settings, 'rows': 2, 'columns': 2}
    _plot(mc, 'Grid plot')
    assert len(_spans(mc)) == 4
    _plot(mc, 'Heatmap')
    assert _spans(mc) == []


def test_open_in_new_window_is_shaded_too(mc):
    import matplotlib.pyplot as plt
    from src.modules.visualization.external_figure import create_external_figure
    _import(mc)
    _select_cd(mc)
    for plot_type in ('Overlay plot', 'Grid plot'):
        _plot(mc, plot_type)
        new_fig = create_external_figure(mc)
        assert new_fig is not None
        spans = [p for ax in new_fig.axes for p in ax.patches if p.get_gid() == 'cd_quality']
        assert spans and all(p.figure is new_fig for p in spans)
        new_fig.canvas.draw()
        plt.close(new_fig)


def test_menu_and_setting_are_remembered(mc):
    titles = [a.text() for a in mc.view.menuView.actions()]
    assert 'CD data quality' in titles
    mc.cd_quality_controller.set_shading(False)
    assert Preferences().cd_quality_shading() is False
    assert not mc.cd_quality_controller.shade_action.isChecked()


def test_quality_survives_a_snapshot(mc, tmp_path):
    _import(mc)
    before = {s['label']: s['metadata']['cd_quality'] for s in mc.original_spectra
              if 'cd_quality' in s['metadata']}
    snap = str(tmp_path / 's.snapx')
    assert mc.save_controller.save_manager.save_snapshot(mc, snap)
    mc.original_spectra = []
    assert mc.save_controller.load_snapshot(snap)
    after = {s['label']: s['metadata'].get('cd_quality') for s in mc.original_spectra
             if s['label'] in before}
    assert after.keys() == before.keys()
    label = next(iter(before))
    assert cq.unreliable_ranges(after[label]) == cq.unreliable_ranges(before[label])


def test_x_axis_unit_conversion_converts_the_quality_trace():
    from src.modules.data_analysis.xaxis_unit_conversion_manager import XAxisUnitConversionManager
    spectra = [s for s in reader.read_jwb_data(JWB) if 'cd_quality' in s['metadata']][:1]
    out = XAxisUnitConversionManager().convert_spectra(
        spectra, {'from_unit': 'nm', 'to_unit': 'cm-1'})
    q = out[0]['metadata']['cd_quality']
    assert q['x_unit'] == 'cm⁻¹'
    (lo, hi), = cq.unreliable_ranges(q)
    assert hi == pytest.approx(max(out[0]['x_scale']))  # short wavelengths = high wavenumbers
    assert 1e7 / lo == pytest.approx(cq.unreliable_ranges(spectra[0]['metadata']['cd_quality'])[0][1],
                                     rel=0.02)
    assert spectra[0]['metadata']['cd_quality']['x_unit'] == 'nm'
