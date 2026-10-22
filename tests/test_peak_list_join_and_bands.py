"""Peak list, tab Plot: Join the same peak number for every x that is not the
peak itself (lines in their own colours, kept when the colour changes), the
peak by its position (common position of a band, as labels or on the x
scale), the Legend switch; a number of the name that is the same in all
spectra is not offered as x."""
import glob
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JWB = sorted(glob.glob(os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD melting', '*.jwb')))[0]

BAND_LABELS = "Peak by its position, as labels (e.g. 686, 1093)"
BAND_SCALE = "Peak by its position, on the x scale"


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


def _plot(mc, monkeypatch):
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    monkeypatch.setattr(PeakListDialog, 'exec_', lambda self: 0)
    dlg = mc.peak_detection_controller.show_peak_list()
    dlg.mode.setCurrentText('Both')                  # several peaks per spectrum
    dlg.tabs.setCurrentIndex(1)
    return dlg


def test_join_for_a_peak_number_on_x_and_kept_when_the_colour_changes(mc, monkeypatch):
    dlg = _plot(mc, monkeypatch)
    dlg.x_combo.setCurrentText('Height (y)')
    assert dlg.join_check.isEnabled()
    dlg.join_by.setCurrentIndex(dlg.join_by.findData('number'))   # band is the default now
    dlg.join_check.setChecked(True)
    ax = dlg.figure.axes[0]
    n_peaks = len({r[1] for r in dlg.rows})
    assert len(ax.lines) == n_peaks
    colours = {tuple(line.get_color()) for line in ax.lines}
    assert len(colours) == min(n_peaks, 10)            # each line its own colour
    dlg.colour_combo.setCurrentText('One colour')      # the lines stay, now named in the legend
    ax = dlg.figure.axes[0]
    assert len(ax.lines) == n_peaks
    assert 'Peak 1 (line)' in [t.get_text() for t in ax.get_legend().get_texts()]


def test_join_greyed_out_when_x_is_the_peak_and_redrawn_at_once(mc, monkeypatch):
    dlg = _plot(mc, monkeypatch)
    dlg.join_by.setCurrentIndex(dlg.join_by.findData('number'))   # band is the default now
    dlg.join_check.setChecked(True)
    assert dlg.figure.axes[0].lines
    for text in (BAND_LABELS, BAND_SCALE):
        dlg.x_combo.setCurrentText(text)
        assert not dlg.join_check.isEnabled() and dlg.tolerance.isVisibleTo(dlg)
        assert not dlg.figure.axes[0].lines            # the plot drawn after the switch
    dlg.x_combo.setCurrentText('Prominence')
    assert dlg.join_check.isEnabled() and not dlg.tolerance.isVisibleTo(dlg)
    assert dlg.figure.axes[0].lines


def test_peak_by_position_labels_and_scale(mc, monkeypatch):
    from src.modules.data_analysis import peak_list as pl
    dlg = _plot(mc, monkeypatch)
    assert dlg.tolerance.value() == pl.default_tolerance(dlg.rows) > 0
    dlg.x_combo.setCurrentText(BAND_SCALE)
    ax = dlg.figure.axes[0]
    import numpy as np
    xs = np.concatenate([c.get_offsets()[:, 0] for c in ax.collections])
    centres = sorted(set(pl.band_positions(dlg.rows, dlg.tolerance.value())))
    assert set(np.round(xs, 6)) == set(np.round(centres, 6))
    dlg.x_combo.setCurrentText(BAND_LABELS)
    ax = dlg.figure.axes[0]
    labels = [t.get_text() for t in ax.get_xticklabels()]
    assert labels == [pl.band_label(c, centres) for c in centres]
    dlg.legend_check.setChecked(False)
    assert dlg.figure.axes[0].get_legend() is None


def test_band_positions_and_tolerance():
    from src.modules.data_analysis import peak_list as pl

    def row(pos, fwhm=10.0):
        r = [''] * len(pl.COLUMNS)
        r[pl.NUMERIC['Position (x)']] = pos
        r[pl.NUMERIC['FWHM']] = fwhm
        return r
    rows = [row(685), row(686), row(687), row(1093), row(1095), row(1371)]
    assert pl.band_positions(rows, 5) == [686, 686, 686, 1094, 1094, 1371]
    assert pl.band_positions(rows, 0.5) == [685, 686, 687, 1093, 1095, 1371]
    assert pl.default_tolerance(rows) == 5.0 and pl.default_tolerance([]) == 0.0
    assert pl.band_label(686.0, [686.0, 1371.0]) == '686'
    assert pl.band_label(0.2345, [0.2, 0.3]) == '0.2345'


def test_select_all_keeps_the_rows_selected(mc, monkeypatch):
    dlg = _plot(mc, monkeypatch)
    dlg.tabs.setCurrentIndex(0)
    dlg.select_all_button.click()
    assert len(dlg.table.selectionModel().selectedRows()) == dlg.table.rowCount() > 0


def test_a_number_that_is_the_same_in_all_names_is_not_offered():
    import numpy as np
    from src.modules.data_analysis import peak_list as pl
    x = np.linspace(0, 10, 50)
    spectra = [{'label': f'raman_2comp_clean : raman_{i:02d}', 'x_scale': x,
                'y_scale': np.sin(x + i), 'metadata': {'pH': 7.4, 'T': 20.0 + i}}
               for i in range(1, 6)]
    texts = [t for t, _ in pl.x_choices(spectra)]
    assert 'Spectrum: the last number in the name' in texts       # 1, 2, 3, ...
    assert 'Spectrum: the first number in the name' not in texts  # always 2
    assert 'Spectrum: T' in texts and 'Spectrum: pH' not in texts # pH 7.4 everywhere
    one = [t for t, _ in pl.x_choices(spectra[:1])]
    assert 'Spectrum: the first number in the name' in one        # one spectrum: all offered
