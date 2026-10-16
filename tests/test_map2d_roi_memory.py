"""2D Map: ROI regions are remembered when the map is closed and opened
again (per map, for the session), and saved in snapshots."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MAP = os.path.join(ROOT, 'resources', 'test_data', 'synthetic', 'group_stats_cell_map_demo.mat')


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.modules.core.spectrum_manager import SpectrumManager
    from src.controllers.visualization_analysis.map2d_controller import Map2DController
    m = SpectrumManager()
    m.load_spectrum_from_file(MAP)
    spectra = [{'label': l, 'x_scale': s.x_scale, 'y_scale': s.y_scale, 'metadata': s.metadata}
               for l, s in m.spectra.items()]

    class _Main:
        view = None
    return Map2DController(_Main()), spectra


def _dialog(controller, spectra):
    from src.views.dialogs.visualization_analysis.map2d_dialog import Map2DDialog
    return Map2DDialog(None, controller, spectra)


def _draw_regions(dlg, spectra):
    """One region of every kind, as the drawing tools store them."""
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MPath

    def labels(inside):
        return [spectra[r * 40 + c]['label'] for r in range(30) for c in range(40) if inside(r, c)]
    verts = np.array([[5, 5], [10, 5], [10, 9], [5, 9], [5, 5]], float)
    dlg._roi_regions = [
        {'type': 'rect', 'bounds': (12, 18, 26, 31), 'spectra': [], 'patch': None,
         'labels': labels(lambda r, c: 12 <= r <= 18 and 26 <= c <= 31)},
        {'type': 'ellipse', 'bounds': (10, 18, 13, 21), 'cx': 17.0, 'cy': 14.0, 'a': 4.0,
         'b': 4.0, 'spectra': [], 'patch': None, 'name': 'nucleus',
         'labels': labels(lambda r, c: ((c - 17) / 4) ** 2 + ((r - 14) / 4) ** 2 <= 1)},
        {'type': 'lasso', 'bounds': None, 'spectra': [], 'patch': PathPatch(MPath(verts)),
         'labels': labels(lambda r, c: 5 <= r <= 9 and 5 <= c <= 10)},
        {'type': 'line', 'bounds': (2, 2, 3, 12), 'spectra': [], 'patch': None,
         'labels': [spectra[2 * 40 + c]['label'] for c in range(3, 13)]},
    ]
    dlg._update_roi_count()


def test_regions_come_back_when_the_map_is_opened_again(env):
    controller, spectra = env
    dlg = _dialog(controller, spectra)
    assert dlg._roi_regions == []
    _draw_regions(dlg, spectra)
    before = dlg.roi_state()
    controller.remember_rois(dlg)
    dlg.deleteLater()
    again = _dialog(controller, spectra)
    assert [r['type'] for r in again._roi_regions] == ['rect', 'ellipse', 'lasso', 'line']
    assert again.roi_state() == before
    assert all(r['patch'] is not None for r in again._roi_regions)        # drawn
    assert again._roi_regions[1]['spectra'][0] is spectra[  # the current spectra
        [s['label'] for s in spectra].index(again._roi_regions[1]['labels'][0])]
    assert again._act_roi_groups.isEnabled()
    assert '(' in again._act_view_roi.text() and '(0)' not in again._act_view_roi.text()
    # removing all regions is remembered too
    again._clear_all_rois()
    controller.remember_rois(again)
    assert controller.saved_rois == {}
    assert _dialog(controller, spectra)._roi_regions == []


def test_other_map_or_other_size_does_not_get_the_regions(env):
    controller, spectra = env
    dlg = _dialog(controller, spectra)
    _draw_regions(dlg, spectra)
    controller.remember_rois(dlg)
    other = [dict(s, label=s['label'].replace('group_stats_cell_map_demo', 'other'),
                  metadata=dict(s['metadata'], unique_id=f"other-{i}"))
             for i, s in enumerate(spectra)]
    assert _dialog(controller, other)._roi_regions == []
    # a text map has no size in its metadata: the regions return once the
    # same size is entered
    plain = [dict(s, metadata={'unique_id': s['metadata']['unique_id']}) for s in spectra]
    d = _dialog(controller, plain)
    assert d._roi_regions == []
    d._rows_spin.setValue(30)
    d._cols_spin.setValue(40)
    assert len(d._roi_regions) == 4
    d._cols_spin.setValue(30)                       # a different size: cleared
    assert d._roi_regions == []


def test_region_with_missing_pixels_is_skipped(env):
    controller, spectra = env
    dlg = _dialog(controller, spectra)
    _draw_regions(dlg, spectra)
    state = dlg.roi_state()
    state['regions'][0]['ids'].append('no such pixel')
    fresh = _dialog(controller, spectra)
    fresh._clear_all_rois()
    assert fresh.restore_roi_state(state) == 3


def test_region_names_are_remembered(env, monkeypatch):
    controller, spectra = env
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    monkeypatch.setattr(gsd.GroupStatisticsDialog, 'exec_', lambda self: 0)
    dlg = _dialog(controller, spectra)
    _draw_regions(dlg, spectra)
    monkeypatch.setattr(dlg, '_ask_region_names',
                        lambda: (['cytoplasm', 'nucleus', 'corner', 'line'], None))
    dlg._open_roi_group_statistics()
    assert [r.get('name') for r in dlg._roi_regions] == ['cytoplasm', 'nucleus', 'corner', 'line']
    controller.remember_rois(dlg)
    again = _dialog(controller, spectra)
    assert again._roi_regions[0]['name'] == 'cytoplasm'


def test_exclude_mode_is_remembered(env):
    controller, spectra = env
    dlg = _dialog(controller, spectra)
    _draw_regions(dlg, spectra)
    dlg._toggle_roi_mode()
    controller.remember_rois(dlg)
    assert _dialog(controller, spectra)._roi_exclude_mode is True


def test_snapshot_keeps_the_regions(env, tmp_path):
    from types import SimpleNamespace
    from src.modules.misc.save_spectra_manager import SaveManager
    from tests.test_snapshot import _FakeMainController, _make_spectra
    controller, spectra = env
    dlg = _dialog(controller, spectra)
    _draw_regions(dlg, spectra)
    controller.remember_rois(dlg)
    mgr = SaveManager()
    main = _FakeMainController(original_spectra=_make_spectra(2))
    main.map2d_controller = controller
    state = mgr._build_state(main)
    assert state['map2d_rois'] == controller.saved_rois
    path = tmp_path / 's.snapx'
    mgr.save_snapshot(main, str(path))
    target = _FakeMainController(plot_type='Overlay plot')
    existing = {'old map|4': {'regions': []}}
    target.map2d_controller = SimpleNamespace(saved_rois=existing)
    mgr.load_snapshot(target, str(path))
    assert target.map2d_controller.saved_rois is existing          # in place
    assert existing == controller.saved_rois
    # the loaded regions draw again on the map
    controller.saved_rois = existing
    assert len(_dialog(controller, spectra)._roi_regions) == 4
    # no regions: no key; loading such a snapshot leaves the current ones alone
    main.map2d_controller = SimpleNamespace(saved_rois={})
    assert 'map2d_rois' not in mgr._build_state(main)


def test_regions_follow_the_spectra_not_their_names(env):
    """Remembered by the pixels' unique_id: renamed spectra keep the regions
    (under their new names); the same map imported again (same names, new
    unique_ids) starts without them."""
    controller, spectra = env
    dlg = _dialog(controller, spectra)
    _draw_regions(dlg, spectra)
    controller.remember_rois(dlg)
    renamed = [dict(s, label='renamed ' + s['label']) for s in spectra]
    again = _dialog(controller, renamed)
    assert len(again._roi_regions) == 4
    assert all(l.startswith('renamed ') for l in again._roi_regions[0]['labels'])
    assert again._roi_regions[0]['spectra'][0] is renamed[
        [s['label'] for s in renamed].index(again._roi_regions[0]['labels'][0])]
    reimported = [dict(s, metadata=dict(s['metadata'], unique_id=f"new-{i}"))
                  for i, s in enumerate(spectra)]
    assert _dialog(controller, reimported)._roi_regions == []
