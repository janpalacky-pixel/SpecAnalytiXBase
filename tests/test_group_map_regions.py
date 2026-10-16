"""2D Map: ROI regions as groups in Group Statistics (ROI -> Compare ROI
regions in Group Statistics...), on the demo map of one cell."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MAP = os.path.join(ROOT, 'resources', 'test_data', 'synthetic', 'group_stats_cell_map_demo.mat')


@pytest.fixture
def quiet(monkeypatch):
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))


@pytest.fixture
def map_dialog(tmp_path, monkeypatch, quiet):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    from src.modules.core.spectrum_manager import SpectrumManager
    from src.controllers.visualization_analysis.map2d_controller import Map2DController
    from src.views.dialogs.visualization_analysis.map2d_dialog import Map2DDialog
    m = SpectrumManager()
    m.load_spectrum_from_file(MAP)
    spectra = [{'label': l, 'x_scale': s.x_scale, 'y_scale': s.y_scale, 'metadata': s.metadata}
               for l, s in m.spectra.items()]

    class _Main:
        view = None
    dlg = Map2DDialog(None, Map2DController(_Main()), spectra)
    assert (dlg._rows_spin.value(), dlg._cols_spin.value()) == (30, 40)   # from the .mat
    yield dlg, spectra
    dlg.deleteLater()


def _region(spectra, kind, inside):
    labels = [spectra[r * 40 + c]['label'] for r in range(30) for c in range(40) if inside(r, c)]
    return {'type': kind, 'bounds': None, 'labels': labels, 'spectra': [], 'patch': None}


def _nucleus_and_cytoplasm(dlg, spectra):
    dlg._roi_regions = [
        _region(spectra, 'ellipse', lambda r, c: ((c - 17) / 4) ** 2 + ((r - 14) / 4) ** 2 <= 1),
        _region(spectra, 'rect', lambda r, c: 12 <= r <= 18 and 26 <= c <= 31)]
    dlg._update_roi_count()


def test_action_needs_two_regions(map_dialog):
    dlg, spectra = map_dialog
    assert not dlg._act_roi_groups.isEnabled()
    _nucleus_and_cytoplasm(dlg, spectra)
    assert dlg._act_roi_groups.isEnabled()


def test_roi_groups_overlap_and_rest(map_dialog):
    dlg, spectra = map_dialog
    _nucleus_and_cytoplasm(dlg, spectra)
    dlg._roi_regions.append(_region(spectra, 'rect', lambda r, c: r == 14 and 15 <= c <= 30))
    sp, groups, overlap = dlg.roi_groups(['nucleus', 'cytoplasm', 'cytoplasm'])
    n_line = 16
    assert overlap > 0 and len(sp) == 49 + 42 + n_line - overlap
    assert set(groups.values()) == {'nucleus', 'cytoplasm'}
    sp, groups, _ = dlg.roi_groups(['a', 'b'], rest_name='rest')
    assert len(sp) == 1200 and list(groups.values()).count('rest') == 1200 - len(
        set(dlg._roi_regions[0]['labels']) | set(dlg._roi_regions[1]['labels'])
        | set(dlg._roi_regions[2]['labels']))


def test_compare_regions_in_group_statistics(map_dialog, monkeypatch):
    dlg, spectra = map_dialog
    from src.views.dialogs.visualization_analysis import group_statistics_dialog as gsd
    monkeypatch.setattr(gsd.GroupStatisticsDialog, 'exec_', lambda self: 0)
    _nucleus_and_cytoplasm(dlg, spectra)
    monkeypatch.setattr(dlg, '_ask_region_names', lambda: (['nucleus', 'cytoplasm'], None))
    dlg._open_roi_group_statistics()
    d = dlg._roi_group_dialog
    assert sorted(set(d.groups())) == ['cytoplasm', 'nucleus'] and len(d.groups()) == 91
    assert 'ROI regions of the map' in d.table_source.text()
    assert 'one map' in d.table_source.text()

    def two(a, b):
        d.kind_combo.setCurrentIndex(d.kind_combo.findData('ratio'))
        d.a_from.setValue(a[0]); d.a_to.setValue(a[1])
        d.b_from.setValue(b[0]); d.b_to.setValue(b[1])
        d.metric_a_combo.setCurrentText('Baseline-corrected integral')
        d.metric_b_combo.setCurrentText('Baseline-corrected integral')
        d.operation_combo.setCurrentText('A / B')
        d.compute()
    two((770, 800), (1420, 1480))                      # DNA band: nucleus only
    assert d.comparison['p'] < 1e-10
    two((990, 1015), (1420, 1480))                     # protein: the same everywhere
    assert d.comparison['p'] > 0.05
    d.compute_spectra()                                # raw: the focus drift differs too
    raw = d.spectra_result
    d.sp_norm_combo.setCurrentIndex(d.sp_norm_combo.findData('band'))
    d.sp_band_from.setValue(1420); d.sp_band_to.setValue(1480)
    d.compute_spectra()
    wide = [r for r in d.spectra_result['ranges'] if r[2] >= 3]
    assert sum(r[2] for r in raw['ranges']) > 3 * sum(r[2] for r in wide)
    assert [round(r[3] / 10) * 10 for r in wide] == [790, 1090, 1580]
    # cancelling the names dialog opens nothing
    dlg._roi_group_dialog = None
    monkeypatch.setattr(dlg, '_ask_region_names', lambda: None)
    dlg._open_roi_group_statistics()
    assert dlg._roi_group_dialog is None
