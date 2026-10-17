"""2D Map -> Map Type "Unmixing" (endmember unmixing, VCA / N-FINDR) on the
demo map unmixing_cell_map_demo.mat (four known substances)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SYNTH = os.path.join(ROOT, 'resources', 'test_data', 'synthetic')
MAP = os.path.join(SYNTH, 'unmixing_cell_map_demo.mat')
sys.path.insert(0, SYNTH)
import generate_unmixing_test_dataset as truth          # noqa: E402


@pytest.fixture
def quiet(monkeypatch, tmp_path):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    shown = []
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(
            lambda *a, **k: shown.append(a[1:3]) or QMessageBox.Ok))
    return shown


def _map_spectra():
    from src.modules.core.spectrum_manager import SpectrumManager
    m = SpectrumManager()
    m.load_spectrum_from_file(MAP)
    return [{'label': l, 'x_scale': s.x_scale, 'y_scale': s.y_scale, 'metadata': s.metadata}
            for l, s in m.spectra.items()]


def _dialog(spectra, main=None):
    from src.controllers.visualization_analysis.map2d_controller import Map2DController
    from src.views.dialogs.visualization_analysis.map2d_dialog import Map2DDialog

    class _Main:
        view = None
    d = Map2DDialog(None, Map2DController(main or _Main()), spectra)
    d._radio_em.setChecked(True)
    d._on_mode_changed(d._radio_em)
    return d


def _matched(res):
    corr = np.corrcoef(np.vstack([res.H, truth.true_spectra()]))[:len(res.H), len(res.H):]
    return [truth.NAMES[j] for j in corr.argmax(axis=1)], corr.max(axis=1)


def test_demo_map_suggest_and_unmix(quiet, monkeypatch):
    from PyQt5.QtWidgets import QDialog
    from src.views.dialogs.visualization_analysis import map2d_dialog as md

    def use_bend(dlg):                      # the Suggest window: "Use 4 (bend)"
        dlg.bend_btn.click()
        return QDialog.Accepted
    monkeypatch.setattr(md._SuggestEndmembersDialog, 'exec_', use_bend)
    d = _dialog(_map_spectra())
    assert (d._rows_spin.value(), d._cols_spin.value()) == (40, 50)    # filled in from the file
    assert d._decomp_n_label.text() == "Endmembers:" and d._em_settings_widget.isVisibleTo(d)
    assert not d._btn_decomp_run_n.isVisibleTo(d) and not d._ref_grp.isVisibleTo(d)
    d._suggest_n_endmembers()
    assert d._decomp_n_spin.value() == 4 and d._suggest_dialog.chosen == 4
    assert 'Use 4 (bend)' in d._suggest_dialog.bend_btn.text()
    assert 'Use 4 (above the noise)' in d._suggest_dialog.noise_btn.text()
    for method in ('vca', 'nfindr'):
        d._em_method_combo.setCurrentIndex(d._em_method_combo.findData(method))
        d._compute_map()
        res = d.controller.get_em_result()
        names, corr = _matched(res)
        assert sorted(names) == sorted(truth.NAMES) and corr.min() > 0.95
        F = truth.true_fractions()
        assert all(F[i].max() > 0.95 for i in res.endmember_indices)     # pure pixels
        assert 'Unmixing' in d._map_canvas.ax.get_title()
        assert d._component_combo.itemText(0).startswith('E1')
        assert len(d._map_canvas.ax.lines) == 4                          # markers
        assert 'Lack of fit' in d._decomp_status_label.text()
        assert d._radio_rgb.isEnabled() and d._btn_em_add.isEnabled()
    d.deleteLater()


def test_fit_error_map_shows_the_missing_droplets(quiet):
    d = _dialog(_map_spectra())
    d._decomp_n_spin.setValue(3)
    d._compute_map()
    d._em_error_map_cb.setChecked(True)
    assert 'fit error' in d._map_canvas.ax.get_title()
    err = d._last_map_data.ravel()
    lipid = truth.true_fractions()[:, 3] > 0.5
    assert err[lipid].mean() > 4 * err[~lipid].mean()
    d._em_markers_cb.setChecked(False)
    assert len(d._map_canvas.ax.lines) == 0
    d._em_error_map_cb.setChecked(False)
    assert 'abundance of endmember' in d._map_canvas.ax.get_title()
    d.deleteLater()


def test_settings_change_asks_for_update_and_fractions(quiet):
    d = _dialog(_map_spectra())
    d._decomp_n_spin.setValue(4)
    d._compute_map()
    d._em_sum_to_one_cb.setChecked(True)
    assert d._decomp_needs_refit['em'] and 'Update Map' in d._decomp_status_label.text()
    d._compute_map()
    res = d.controller.get_em_result()
    assert np.allclose(res.W.sum(axis=1), 1, atol=1e-3)
    assert 'fraction of endmember' in d._map_canvas.ax.get_title()
    # switching to another map type and back redraws from the cache
    d._radio_nmf.setChecked(True)
    d._on_mode_changed(d._radio_nmf)
    d._radio_em.setChecked(True)
    d._on_mode_changed(d._radio_em)
    assert 'Unmixing' in d._map_canvas.ax.get_title()
    d.deleteLater()


def test_add_endmembers_to_the_spectra_list(quiet, monkeypatch):
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths),
                                                 [{} for _ in file_paths])))
    monkeypatch.setattr(QInputDialog, 'getText', staticmethod(lambda *a, **k: ('EM', True)))
    from src.controllers.core.main_controller import MainController
    mc = MainController()
    try:
        mc.import_controller._run_import(clear_first=True, file_paths=[MAP])
        app.processEvents()
        n0 = len(mc.original_spectra)
        d = _dialog(list(mc.original_spectra), main=mc)
        d._decomp_n_spin.setValue(4)
        d._compute_map()
        d._add_endmembers_to_list()
        new = [s for s in mc.original_spectra if s['label'].startswith('EM_')]
        assert len(mc.original_spectra) == n0 + 4 and len(new) == 4
        res = d.controller.get_em_result()
        assert np.array_equal(new[0]['y_scale'], res.H[0])
        assert new[0]['metadata']['method'] == 'VCA'
        assert new[0]['metadata']['correction_history']
        d.deleteLater()
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()


def test_demo_is_listed_under_test_datasets():
    from src.views.main_window import SYNTHETIC_TEST_DATASETS
    assert ('unmixing', 'Unmixing — cell map with 4 substances (2D Map)',
            'unmixing_cell_map_demo.mat') in SYNTHETIC_TEST_DATASETS


def test_rgb_overlay_can_use_the_abundance_maps(quiet):
    d = _dialog(_map_spectra())
    d._decomp_n_spin.setValue(4)
    d._compute_map()
    d._radio_rgb.setChecked(True)
    d._on_mode_changed(d._radio_rgb)
    for ch in range(3):
        w = d._rgb_channel_widgets[ch]
        w['kind'].setCurrentIndex(w['kind'].findData('em'))
        assert w['comp'].count() == 4
        w['comp'].setCurrentIndex(ch + 1)
        w['enable'].setChecked(True)
    assert d._rgb_overlay_array is not None and d._rgb_overlay_array.shape == (40, 50, 3)
    d.deleteLater()



def test_denoise_first_is_on_by_default_and_marks_the_fit_stale(quiet):
    d = _dialog(_map_spectra())
    assert d._em_denoise_cb.isChecked() and d._em_denoise_spin.text() == 'auto'
    d._decomp_n_spin.setValue(4)
    d._compute_map()
    res = d.controller.get_em_result()
    assert res.denoise_k == 4 and 'denoised (4 SVD comp.)' in d._decomp_status_label.text()
    d._em_denoise_cb.setChecked(False)
    assert d._decomp_needs_refit['em'] and not d._em_denoise_spin.isEnabled()
    d._compute_map()
    assert d.controller.get_em_result().denoise_k is None
    d._em_denoise_cb.setChecked(True)
    d._em_denoise_spin.setValue(8)
    d._compute_map()
    assert d.controller.get_em_result().denoise_k == 8
    d.deleteLater()


def test_show_all_endmembers_stacked_and_grid(quiet):
    d = _dialog(_map_spectra())
    d._decomp_n_spin.setValue(4)
    d._compute_map()
    assert d._btn_em_all.isEnabled()
    from src.views.dialogs.visualization_analysis import map2d_dialog as md
    dlg = md._EndmemberSpectraDialog(d.controller.get_em_result(), 40, 50, 'viridis', d)
    assert len(dlg.fig.axes) == 1 and len(dlg.fig.axes[0].lines) == 4      # stacked
    dlg.norm_cb.setChecked(True)
    assert len(dlg.fig.axes[0].lines) == 4
    dlg.grid_radio.setChecked(True)
    assert len(dlg.fig.axes) == 8                                         # 4 maps + 4 spectra
    assert 'row' in dlg.fig.axes[0].get_title()
    dlg.maps_cb.setChecked(False)
    assert len(dlg.fig.axes) == 4
    dlg.deleteLater()
    d.deleteLater()


def test_suggest_and_all_endmembers_windows_can_zoom_and_maximize(quiet):
    from PyQt5.QtCore import Qt
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
    from src.views.dialogs.visualization_analysis import map2d_dialog as md
    d = _dialog(_map_spectra())
    est = d.controller.estimate_n_endmembers(d.spectra)
    sug = md._SuggestEndmembersDialog(est, d)
    assert isinstance(sug.toolbar, NavigationToolbar2QT)
    assert sug.windowFlags() & Qt.WindowMaximizeButtonHint
    d._decomp_n_spin.setValue(4)
    d._compute_map()
    dlg = md._EndmemberSpectraDialog(d.controller.get_em_result(), 40, 50, 'viridis', d)
    assert dlg.findChildren(NavigationToolbar2QT)
    assert dlg.windowFlags() & Qt.WindowMaximizeButtonHint
    for w in (sug, dlg, d):
        w.deleteLater()
