"""Detect Peaks and the Peak list: Reset to defaults, the orange "?" (what each
setting means), Apply that marks the peaks without closing the window, and the
tab Plot of the Peak list (one number of the peaks against another)."""
import glob
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from src.modules.data_analysis import peak_list as pl

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
    app.processEvents()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _list(mc, monkeypatch, **kw):
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    monkeypatch.setattr(PeakListDialog, 'exec_', lambda self: 0)
    pdc = mc.peak_detection_controller
    for k, v in kw.items():
        setattr(pdc, k, v)
    return pdc.show_peak_list()


# --- Detect Peaks ------------------------------------------------------------------------

def test_apply_marks_the_peaks_and_the_window_stays_open(mc, monkeypatch):
    from src.views.dialogs.data_analysis import peak_detection_dialog as pdd
    seen = {}

    def run(dialog):
        dialog.show()
        dialog.threshold_input.setValue(0.2)
        dialog.peak_mode_combo.setCurrentText('Both')
        dialog.apply_button.click()
        seen['open_after_apply'] = dialog.isVisible()
        seen['marked'] = sum(len(v) for v in mc.peak_detection_controller.peak_detector
                             .peak_indices.values())
        dialog.threshold_input.setValue(0.9)            # changed, but not applied
        dialog.button_box.button(QDialogButtonBox.Close).click()
        return 0
    monkeypatch.setattr(pdd.PeakDetectionDialog, 'exec_', run)
    pdc = mc.peak_detection_controller
    pdc.show_dialog()
    assert seen['open_after_apply'] and seen['marked'] > 0
    assert (pdc.peak_threshold, pdc.peak_detection_mode) == (0.2, 'Both')     # not 0.9


def test_reset_to_defaults_in_detect_peaks():
    from src.views.dialogs.data_analysis.peak_detection_dialog import DEFAULTS, PeakDetectionDialog
    dlg = PeakDetectionDialog(None, threshold=0.2, prominence=0.3, distance=0.1, peak_mode='Both',
                              font_size=14, rotation=45, decimals=4, number_format='sci',
                              format_type='both')
    assert dlg.get_settings() != DEFAULTS
    dlg.reset_button.click()
    assert dlg.get_settings() == DEFAULTS


def test_the_controller_starts_with_the_defaults(mc):
    from src.views.dialogs.data_analysis.peak_detection_dialog import DEFAULTS
    pdc = mc.peak_detection_controller
    assert (pdc.peak_threshold, pdc.peak_prominence, pdc.peak_distance, pdc.peak_detection_mode) == \
        (DEFAULTS['threshold'], DEFAULTS['prominence'], DEFAULTS['distance'], DEFAULTS['peak_mode'])


def test_question_marks_explain_every_setting(monkeypatch):
    from src.views.dialogs.data_analysis.peak_detection_dialog import PeakDetectionDialog
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    from src.views.dialogs.data_analysis import peak_settings_help as psh
    x = np.linspace(0, 10, 200)
    detect = PeakDetectionDialog(None)
    detect.help_button.click()
    text = detect.settings_help.text.toPlainText()
    for name, _, _ in pl.SETTINGS_HELP + psh.LABEL_HELP:
        assert name in text
    assert 'stand out' in detect.prominence_input.toolTip()
    listing = PeakListDialog(None, [{'label': 'a', 'x_scale': x, 'y_scale': np.sin(x)}])
    listing.help_button.click()
    text = listing.settings_help.text.toPlainText()
    assert 'FWHM' in text and 'Distance' in text
    opened = []
    monkeypatch.setattr('src.help.help_window.open_help_topic',
                        lambda parent, key, anchor=None: opened.append(key))
    listing.settings_help.more_button.click()
    assert opened == ['peak_detection']


def test_the_peak_detection_help_page_opens():
    from src.help import help_window
    from src.help.peak_detection_help import get_peak_detection_help_content
    assert 'peak_detection' in help_window._REGISTRY
    text = get_peak_detection_help_content()
    assert 'Reset to defaults' in text and 'id="peak-plot"' in text and '<b>Apply</b>' in text


# --- Peak list ---------------------------------------------------------------------------

def test_reset_to_defaults_in_the_peak_list(mc, monkeypatch):
    dlg = _list(mc, monkeypatch)
    n_default = dlg.table.rowCount()
    dlg.threshold.setValue(0.1)
    dlg.mode.setCurrentText('Both')
    assert dlg.table.rowCount() != n_default
    dlg.reset_button.click()
    assert dlg.settings() == pl.DEFAULTS and dlg.table.rowCount() == n_default
    assert mc.peak_detection_controller.peak_threshold == 0.5        # Detect Peaks follows


def test_plot_position_against_temperature(mc, monkeypatch):
    dlg = _list(mc, monkeypatch, peak_detection_mode='Both')
    texts = [dlg.x_combo.itemText(i) for i in range(dlg.x_combo.count())]
    assert texts[0] == 'Spectrum (order in the list)' and 'Spectrum: temperature_C' in texts
    dlg.tabs.setCurrentIndex(1)
    dlg.x_combo.setCurrentIndex(texts.index('Spectrum: temperature_C'))
    dlg.y_combo.setCurrentText('Position (x)')
    n = dlg.draw_plot()
    assert n == dlg.table.rowCount()
    ax = dlg.figure.axes[0]
    xs = np.concatenate([c.get_offsets()[:, 0] for c in ax.collections])
    temps = {s['metadata']['temperature_C'] for s in mc.selected_spectra}
    assert set(np.round(xs, 6)) <= {round(t, 6) for t in temps}
    assert ax.get_xlabel() == 'temperature_C' and ax.get_ylabel() == 'Position (x)'
    assert [t.get_text() for t in ax.get_legend().get_texts()][0] == 'Peak 1'
    dlg.join_check.setChecked(True)
    assert len(ax.lines) == 0 and len(dlg.figure.axes[0].lines) > 0


def test_plot_only_the_selected_rows_and_peak_columns(mc, monkeypatch):
    dlg = _list(mc, monkeypatch)
    dlg.tabs.setCurrentIndex(1)
    dlg.selected_check.setChecked(True)
    dlg.table.sortItems(3)                                 # sorted by position
    dlg.table.selectRow(0)
    assert dlg.draw_plot() == 1
    from PyQt5.QtCore import Qt
    row = dlg.table.item(0, 0).data(Qt.UserRole)           # the row in dlg.rows
    ax = dlg.figure.axes[0]
    assert ax.collections[0].get_offsets()[0, 1] == pytest.approx(dlg.rows[row][3])
    dlg.selected_check.setChecked(False)
    dlg.x_combo.setCurrentText('Height (y)')
    dlg.colour_combo.setCurrentText('Maximum / minimum')
    assert dlg.draw_plot() == dlg.table.rowCount()
    dlg.copy_plot()
    assert not QApplication.clipboard().image().isNull()


def test_no_peaks_and_no_values():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    x = np.linspace(0, 10, 50)
    dlg = PeakListDialog(None, [{'label': 'flat', 'x_scale': x, 'y_scale': np.ones(50)}])
    dlg.tabs.setCurrentIndex(1)
    assert dlg.draw_plot() == 0
    assert 'No peaks' in dlg.figure.axes[0].texts[0].get_text()
