"""Peak Fitting > Fit all selected spectra: the peaks set up on one spectrum
are fitted to every selected spectrum in turn, each starting from the
previous result, so a band that shifts along a series is followed; the
results (one row per spectrum) can be copied, exported and opened in the
Data table."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_analysis import peak_fitting_series as pfs
from src.modules.data_analysis.peak_fitting_manager import gaussian

app = QApplication.instance() or QApplication([])


def _series(n=12, shift=2.0):
    """Two overlapping Gaussian bands; band 1 moves by `shift` per spectrum
    (in total much more than its width) and band 2 grows."""
    x = np.linspace(0, 200, 801)
    rng = np.random.default_rng(1)
    out = []
    for i in range(n):
        c1 = 60 + shift * i
        y = gaussian(x, 1.0, c1, 4.0) + gaussian(x, 0.3 + 0.05 * i, 140, 6.0)
        y = y + rng.normal(0, 0.003, x.size)
        out.append({'label': f'scan : {i + 1:02d}', 'x_scale': x, 'y_scale': y,
                    'metadata': {'temperature_C': 20.0 + 5 * i}})
    return out


START = [{'model': 'Gaussian', 'center': 60.0, 'amplitude': 1.0, 'width': 4.0, 'color': '#1f77b4'},
         {'model': 'Gaussian', 'center': 140.0, 'amplitude': 0.3, 'width': 6.0, 'color': '#ff7f0e'}]


def test_a_moving_band_is_followed_from_spectrum_to_spectrum():
    sp = _series()
    results = pfs.fit_series(sp, START)
    assert all(r['ok'] for r in results)
    centres = [r['peaks'][0]['parameters']['center'] for r in results]
    assert np.allclose(centres, [60 + 2.0 * i for i in range(12)], atol=0.05)   # 60 ... 82
    heights = [r['peaks'][1]['parameters']['height'] for r in results]
    assert np.allclose(heights, [0.3 + 0.05 * i for i in range(12)], atol=0.01)
    assert all(r['r2'] > 0.99 for r in results)
    columns, rows = pfs.series_table(results, 2)
    assert columns[:5] == ['Spectrum', 'Peak 1 position', 'Peak 1 FWHM', 'Peak 1 height',
                           'Peak 1 area'] and columns[-1] == 'R²' and len(columns) == 10
    assert rows[3][0] == 'scan : 04' and rows[3][1] == pytest.approx(66, abs=0.05)
    assert rows[0][2] == pytest.approx(2 * np.sqrt(2 * np.log(2)) * 4.0, rel=1e-2)   # FWHM


def test_without_following_the_previous_fit_the_band_would_be_lost():
    """The reason for starting from the previous fit: fitted from the first
    starting values, the moved band is out of reach (centre bounds ± 2 widths)."""
    from src.modules.data_analysis.peak_fitting_manager import PeakFittingManager
    last = _series()[-1]
    fitted, _ = PeakFittingManager().fit_peaks(last['x_scale'], last['y_scale'], START)
    assert fitted is None or abs(fitted[0]['parameters']['center'] - 82) > 1


def test_a_failed_spectrum_is_left_empty_and_the_next_starts_from_the_last_good_fit():
    sp = _series(4)
    sp[1] = {'label': 'too short', 'x_scale': np.arange(5.0), 'y_scale': np.zeros(5)}
    results = pfs.fit_series(sp, START)
    assert [r['ok'] for r in results] == [True, False, True, True]
    columns, rows = pfs.series_table(results, 2)
    assert rows[1][0] == 'too short' and all(v is None for v in rows[1][1:])
    assert 'Fitted 3 of 4 spectra' in pfs.summary(results) and 'too short' in pfs.summary(results)


def test_other_models_keep_their_extra_parameter():
    fitted = [{'model': 'Pseudo-Voigt', 'parameters': {'center': 5.0, 'height': 2.0, 'fwhm': 3.0,
                                                       'eta': 0.3, 'area': 1.0}},
              {'model': 'Voigt', 'parameters': {'center': 9.0, 'height': 1.0, 'sigma': 1.5,
                                                'gamma': 0.7, 'fwhm': 4.0, 'area': 1.0}}]
    start = pfs.start_from(fitted, [{'color': 'red'}, {'color': 'blue'}])
    assert start[0] == {'color': 'red', 'model': 'Pseudo-Voigt', 'center': 5.0, 'amplitude': 2.0,
                        'width': 3.0, 'extra': 0.3}
    assert start[1]['width'] == 1.5 and start[1]['extra'] == 0.7


def _window(sp, **kw):
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    dlg = PeakFittingDialog(None, spectrum=sp[0], series=sp, **kw)
    dlg.follow_check.setChecked(True)                            # peaks on the first only
    dlg.peaks = [dict(p) for p in START]
    dlg.update_peaks_table()
    return dlg


def test_the_series_is_fitted_in_the_window_and_its_results_stay_there(monkeypatch):
    """No extra window: the results go to the tab Series results; a click on a
    row (or the spectrum chooser) shows that spectrum with its fit."""
    from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
    tables = []

    def open_data_table(parent, spectra, columns):
        dlg = DataTableDialog(parent, spectra)
        dlg.values.add_fixed('p', columns, "the Peak Fitting series")
        tables.append(dlg)
        return dlg
    sp = _series(6)
    dlg = _window(sp, open_data_table=open_data_table)
    assert dlg.fit_button.text() == 'Fit Peaks \u2013 1 spectrum'
    assert dlg.left_tabs.tabText(1) == 'Series results'
    assert not dlg.view_combo.isEnabled()                     # one spectrum selected in the list
    dlg.list_all_button.click()                                  # all 6 selected
    dlg.fit_button.click()
    assert dlg.left_tabs.currentIndex() == 1
    assert dlg.series_table.rowCount() == 6 and dlg.series_table.columnCount() == 10
    assert 'Fitted 6 of 6 spectra' in dlg.series_info.text()
    assert dlg.spectra_list.item(5).text().startswith('\u2713 ')
    # show the 5th spectrum: its data and its fit, its fitted values in the tab Peaks
    dlg.series_table.selectRow(4)
    assert dlg.current_index == 4 and dlg.spectrum is sp[4]
    assert dlg.fit_results is dlg.series_results[4]['peaks']
    assert float(dlg.peaks_table.item(0, 2).text()) == pytest.approx(68, abs=0.05)
    assert dlg.ax_main.get_title().endswith('scan : 05')
    dlg.next_button.click()
    assert dlg.current_index == 5 and dlg.selected_spectra() == [5]
    assert not dlg.next_button.isEnabled()
    # Copy: the selected row(s) - or the whole table; Copy Results: the whole table
    assert len(dlg.copy_series().splitlines()) == 2              # row 6 is selected
    dlg.series_table.clearSelection()
    lines = dlg.copy_series().splitlines()
    assert lines[0].startswith('Spectrum\tPeak 1 position') and len(lines) == 7
    said = []
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: said.append(a[2])))
    dlg.series_table.clearSelection()
    dlg.copy_results_btn.click()
    assert 'series results of 6 spectra' in said[-1]
    assert QApplication.clipboard().text().count('\n') == 7
    dlg.series_data_table_button.click()
    t = tables[0].values.table
    assert [c.name for c in t.columns if c.kind == 'fit'][:2] == ['p1', 'p2']
    x, y, _ = t.xy('temperature_C', 'p1')
    assert np.allclose(y, [60, 62, 64, 66, 68, 70], atol=0.05)


def test_several_spectra_at_once_overlay_waterfall_grid():
    sp = _series(6)
    dlg = _window(sp)
    dlg.fit_all_selected()
    dlg.list_all_button.click()                                  # all selected: Overlay
    ax = dlg.figure.axes[0]
    assert len(dlg.figure.axes) == 1 and len(ax.get_lines()) == 12   # 6 data + 6 fits
    dlg.view_combo.setCurrentIndex(1)                            # Waterfall: shifted
    lines = dlg.figure.axes[0].get_lines()
    assert lines[2].get_ydata().min() > lines[0].get_ydata().min() + 0.5
    dlg.view_combo.setCurrentIndex(2)                            # Grid: one plot each
    assert len(dlg.figure.axes) == 6
    dlg.series_table.selectRow(1)
    from PyQt5.QtCore import QItemSelectionModel
    model = dlg.series_table.selectionModel()
    model.select(dlg.series_table.model().index(3, 0),
                 QItemSelectionModel.Select | QItemSelectionModel.Rows)
    assert len(dlg.figure.axes) == 2                            # the selected rows only
    dlg.series_table.selectRow(1)                                # back to one spectrum
    assert len(dlg.figure.axes) == 2 and dlg.ax_main is dlg.figure.axes[0]


def test_a_bad_fit_is_corrected_on_its_own():
    sp = _series(4)
    dlg = _window(sp)
    dlg.fit_all_selected()
    dlg.series_results[2] = dict(dlg.series_results[2], ok=False, peaks=None)  # as if it failed
    dlg._refresh_series_table()
    dlg.show_series_spectrum(2)
    assert dlg.fit_results is None and dlg.series_table.item(2, 1).text() == ''
    dlg.fit_button.click()                                       # fit only this one
    assert dlg.series_results[2]['ok'] and dlg.series_table.item(2, 1).text() != ''
    assert dlg.series_results[2]['peaks'][0]['parameters']['center'] == pytest.approx(64, abs=0.05)


def test_start_each_fit_from_the_shown_spectrum_on_several_cores():
    sp = _series(6, shift=0.5)                                  # small shifts: independent fits do
    res = pfs.fit_series_independent(sp, START, parallel={'processing_mode': 'parallel',
                                                          'max_workers': 2})
    assert all(r['ok'] for r in res)
    centres = [r['peaks'][0]['parameters']['center'] for r in res]
    assert np.allclose(centres, [60 + 0.5 * i for i in range(6)], atol=0.05)
    serial = pfs.fit_series_independent(sp, START, parallel={'processing_mode': 'serial'})
    assert np.allclose(centres, [r['peaks'][0]['parameters']['center'] for r in serial])
    dlg = _window(sp)
    assert not hasattr(dlg, 'start_combo')                       # own peaks, else the fit before
    import src.modules.data_analysis.peak_fitting_series as mod
    called = []
    orig = mod.fit_series_independent
    mod.fit_series_independent = lambda *a, **k: called.append(1) or orig(
        *a, parallel={'processing_mode': 'serial'})
    try:
        dlg.list_all_button.click()
        dlg.copy_peaks_to_selected()                             # all their own: fitted independently
        dlg.fit_all_selected()
    finally:
        mod.fit_series_independent = orig
    assert called and all(r['ok'] for r in dlg.series_results)


def test_the_results_are_remembered_for_the_same_spectra():
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = _series(4)
    dlg = _window(sp)
    dlg.fit_all_selected()
    dlg.show_series_spectrum(3)
    saved = dlg.get_results()
    assert saved['series_labels'] == [s['label'] for s in sp] and saved['series_index'] == 3
    assert saved['spectrum_label'] == 'scan : 04' and len(saved['series_results']) == 4
    again = PeakFittingDialog(None, spectrum=sp[0], series=sp, current_settings=saved)
    assert again.series_results is not None and again.series_table.rowCount() == 4
    assert again.current_index == 3 and again.spectrum is sp[3]
    other = PeakFittingDialog(None, spectrum=sp[0], series=sp[:3], current_settings=saved)
    assert other.series_results is None                          # other spectra: not shown


def test_one_spectrum_has_no_series_controls_and_no_peaks_only_informs(monkeypatch):
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    said = []
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: said.append(a[2])))
    sp = _series(3)
    one = PeakFittingDialog(None, spectrum=sp[0])
    assert one.fit_button.text() == 'Fit Peaks' and not hasattr(one, 'spectra_list')
    assert one.left_tabs.count() == 1
    dlg = PeakFittingDialog(None, spectrum=sp[0], series=sp)
    dlg.peaks = []
    assert dlg.fit_all_selected() is None and 'Add the peaks first' in said[-1]


def test_export(tmp_path):
    sp = _series(3)
    dlg = _window(sp)
    dlg.fit_all_selected()
    assert dlg.series_data_table_button.isHidden()                # no Data table given
    path = dlg.export_series(str(tmp_path / 'series.xlsx'))
    import pandas as pd
    frame = pd.read_excel(path)
    assert list(frame.columns)[:2] == ['Spectrum', 'Peak 1 position'] and len(frame) == 3


def test_several_selected_spectra_open_the_window_with_the_series(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    from src.views.dialogs.data_analysis import peak_fitting_dialog as pfd
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    opened = []
    monkeypatch.setattr(pfd.PeakFittingDialog, 'exec_', lambda self: opened.append(self) or 0)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mc = MainController()
    try:
        mc.import_controller._run_import(
            clear_first=True, file_paths=[os.path.join(root, 'resources', 'test_data', 'real',
                                                       'CD_spectra_TBA.txt')])
        mc.spectrum_selector.select_all_items()
        app.processEvents()
        mc.run_visualization_analysis('Peak Fitting')
        assert opened and len(opened[0].series) == 28
        assert opened[0].spectrum['label'] == opened[0].series[0]['label']
        assert opened[0].spectra_list.count() == 28
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()


def test_ok_with_output_options_adds_the_curves_of_every_fitted_spectrum(tmp_path, monkeypatch):
    """Output options with series results: the total fit (etc.) of every fitted
    spectrum is added, not only of the shown one."""
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    from src.controllers.data_analysis.peak_fitting_controller import PeakFittingController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mc = MainController()
    try:
        mc.import_controller._run_import(clear_first=True, file_paths=[
            os.path.join(root, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')])
        mc.spectrum_selector.select_all_items()
        app.processEvents()
        n0 = len(mc.original_spectra)
        labels = [s['label'] for s in mc.original_spectra[:3]]
        peak = [{'model': 'Gaussian', 'parameters': {'center': 260.0, 'height': 1.0, 'sigma': 5.0,
                                                     'fwhm': 11.77, 'area': 12.53}}]
        results = [{'label': labels[0], 'ok': True, 'peaks': peak, 'r2': 0.9},
                   {'label': labels[1], 'ok': False, 'peaks': None, 'r2': None},   # not fitted
                   {'label': labels[2], 'ok': True, 'peaks': peak, 'r2': 0.9}]
        mc.operations_controller.current_parameters['Peak Fitting'] = {
            'fit_results': peak, 'spectrum_label': labels[0],
            'series_results': results, 'output_options': {'add_fit': True}}
        PeakFittingController(mc).handle_peak_fitting()
        now = [s['label'] for s in mc.original_spectra]
        assert len(now) == n0 + 2
        assert labels[0] + '_fit' in now and labels[2] + '_fit' in now
        assert labels[1] + '_fit' not in now
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()
