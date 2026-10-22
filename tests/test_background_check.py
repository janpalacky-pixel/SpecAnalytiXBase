"""NMF / MCR-ALS on spectra that still sit on a large shared background
(e.g. a detector offset of ~670 under bands ~20 high, as in the raw
Chlorella map) give jagged components; the program now says so: in the
2D map's status line (orange) and in the warnings of the NMF and MCR-ALS
windows (background_check.py)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])


def _map(offset, n=36):
    """n spectra: two bands whose amounts vary, on a flat offset."""
    x = np.linspace(400, 1800, 300)
    rng = np.random.default_rng(0)
    out = []
    for i in range(n):
        a, b = rng.uniform(0, 20, 2)
        y = (offset + a * np.exp(-((x - 800) / 15) ** 2) + b * np.exp(-((x - 1400) / 20) ** 2)
             + rng.normal(0, 0.3, x.size))
        out.append({'label': f'map : {i + 1:03d}', 'x_scale': x, 'y_scale': y, 'metadata': {}})
    return out


def test_the_measure():
    from src.modules.visualization_analysis import background_check as bc
    level, height = bc.shared_background(_map(670))
    assert 660 < level < 680 and 5 < height < 30
    text = bc.warning_text(_map(670), 'NMF')
    assert text and 'large background' in text and 'Baseline-correct' in text and 'NMF' in text
    assert bc.warning_text(_map(0), 'NMF') is None                 # baseline-corrected
    signed = _map(0)
    for s in signed:
        s['y_scale'] = s['y_scale'] - 10                           # CD-like, around zero
    assert bc.warning_text(signed, 'MCR-ALS') is None
    assert bc.shared_background([]) == (None, None)


@pytest.fixture
def quiet(monkeypatch, tmp_path):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))


def _map_dialog(spectra, radio):
    from src.controllers.visualization_analysis.map2d_controller import Map2DController
    from src.views.dialogs.visualization_analysis.map2d_dialog import Map2DDialog

    class _Main:
        view = None
    d = Map2DDialog(None, Map2DController(_Main()), spectra)
    d._rows_spin.setValue(6)
    d._cols_spin.setValue(6)
    button = getattr(d, radio)
    button.setChecked(True)
    d._on_mode_changed(button)
    d._decomp_n_spin.setValue(2)
    d._compute_map()
    return d


@pytest.mark.parametrize('radio, name', [('_radio_nmf', 'NMF'), ('_radio_mcr', 'MCR-ALS')])
def test_the_map_says_so(quiet, radio, name):
    d = _map_dialog(_map(670), radio)
    text = d._decomp_status_label.text()
    assert 'Lack of fit' in text and 'large background' in text and name in text
    d = _map_dialog(_map(0), radio)
    assert 'large background' not in d._decomp_status_label.text()


def _wait(condition, limit=60):
    import time
    end = time.time() + limit
    while time.time() < end and not condition():
        app.processEvents()
        time.sleep(0.02)
    return condition()


@pytest.mark.parametrize('analysis, name', [('NMF', 'NMF'), ('MCR-ALS', 'MCR-ALS')])
def test_the_nmf_and_mcr_windows_say_so(quiet, monkeypatch, tmp_path, analysis, name):
    from PyQt5.QtWidgets import QDialog
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    spectra = _map(670, n=12)
    table = np.column_stack([spectra[0]['x_scale']] + [s['y_scale'] for s in spectra])
    path = tmp_path / 'offset_map.txt'
    np.savetxt(path, table, header='x ' + ' '.join(f's{i}' for i in range(12)), comments='')
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    mc = MainController()
    try:
        mc.import_controller._run_import(clear_first=True, file_paths=[str(path)])
        mc.spectrum_selector.select_all_items()
        app.processEvents()
        seen = []

        def run(dlg, *a):
            dlg._n_spin.setValue(2)
            dlg.run_btn.click()
            _wait(lambda: 'lack of fit' in dlg._status_label.text())
            seen.append(getattr(dlg, '_warning_text', ''))
            return QDialog.Rejected
        monkeypatch.setattr(QDialog, 'exec_', run)
        mc.run_visualization_analysis(analysis)
        assert seen and 'large background' in seen[0] and name in seen[0]
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()
