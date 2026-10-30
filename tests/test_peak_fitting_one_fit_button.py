"""Peak Fitting has ONE fit button: it fits the spectra selected in the list
beside the plot - the shown one, or several (a series, with Start each fit
from). Its text says how many; fitting a few spectra again keeps the results
of the others."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtCore import QItemSelectionModel
from PyQt5.QtWidgets import QApplication

from src.modules.data_analysis import peak_fitting_series as pfs
from src.modules.data_analysis.peak_fitting_manager import gaussian

app = QApplication.instance() or QApplication([])


def _series(n=6):
    x = np.linspace(0, 200, 401)
    rng = np.random.default_rng(5)
    return [{'label': f'scan : {i + 1:02d}', 'x_scale': x,
             'y_scale': gaussian(x, 1.0, 60 + 2 * i, 4.0) + gaussian(x, 0.4, 140, 6.0)
             + rng.normal(0, 0.003, x.size), 'metadata': {}} for i in range(n)]


PEAKS = [{'model': 'Gaussian', 'center': 60.0, 'amplitude': 1.0, 'width': 4.0, 'color': '#1f77b4'},
         {'model': 'Gaussian', 'center': 140.0, 'amplitude': 0.4, 'width': 6.0, 'color': '#ff7f0e'}]


def _window(series):
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    dlg = PeakFittingDialog(None, spectrum=series[0], series=series if len(series) > 1 else None)
    if len(series) > 1:
        dlg.follow_check.setChecked(True)                        # peaks on the first only
    dlg.peaks = [dict(p) for p in PEAKS]
    dlg.update_peaks_table()
    return dlg


def _select(dlg, rows):
    lst = dlg.spectra_list
    lst.clearSelection()
    for r in rows:
        lst.selectionModel().select(lst.model().index(r, 0), QItemSelectionModel.Select)


def test_one_spectrum_one_button():
    dlg = _window(_series(1))
    assert dlg.fit_button.text() == 'Fit Peaks' and not dlg.fit_button.icon().isNull()
    dlg.fit_button.click()
    assert dlg.fit_results is not None and dlg.series_results is None


def test_the_button_fits_the_selected_spectra():
    sp = _series()
    dlg = _window(sp)
    assert dlg.fit_button.text() == 'Fit Peaks – 1 spectrum'
    assert not dlg.fit_button.icon().isNull()
    dlg.fit_button.click()                                       # the shown one only
    assert dlg.series_results[0]['ok'] and all(r.get('pending') for r in dlg.series_results[1:])
    dlg.list_all_button.click()
    assert dlg.fit_button.text() == 'Fit Peaks – 6 selected spectra'
    dlg.fit_button.click()                                       # the whole series
    assert all(r['ok'] for r in dlg.series_results) and dlg.left_tabs.currentIndex() == 1
    centres = [r['peaks'][0]['parameters']['center'] for r in dlg.series_results]
    assert np.allclose(centres, [60 + 2 * i for i in range(6)], atol=0.05)


def test_fitting_a_few_again_keeps_the_others():
    sp = _series()
    dlg = _window(sp)
    dlg.fit_all_selected()
    before = list(dlg.series_results)
    _select(dlg, [1, 3])
    assert dlg.fit_button.text().endswith('2 selected spectra')
    new = dlg.fit_selected()
    assert len(new) == 2 and new[0]['label'] == 'scan : 02'
    assert dlg.series_results[1] is new[0] and dlg.series_results[3] is new[1]
    for k in (0, 2, 4, 5):
        assert dlg.series_results[k] is before[k]
    assert dlg.selected_spectra() == [1, 3]                      # still shown together


def test_a_few_spectra_each_from_its_own_peaks_on_several_cores():
    sp = _series()
    dlg = _window(sp)
    _select(dlg, [0, 2, 4, 5])
    assert dlg.copy_peaks_to_selected() == [2, 4, 5]             # the shown one's peaks copied
    _select(dlg, [2, 4, 5])
    dlg.fit_selected()
    assert [k for k, r in enumerate(dlg.series_results) if r['ok']] == [2, 4, 5]
    assert 'Fitted 3 of 6 spectra. 3 not fitted yet' in dlg.series_info.text()


def test_a_spectrum_without_peaks_keeps_its_fit_as_its_peaks():
    sp = _series()
    dlg = _window(sp)
    dlg.fit_all_selected()                                       # 2..6 follow the fit before
    fitted = dlg.series_results[4]['peaks'][0]['parameters']['center']
    assert dlg.peaks_of(4)[0]['center'] == fitted                # 68, not the start 60
    assert dlg.peaks_of(4)[0]['color'] == PEAKS[0]['color']


def test_old_model_dropdowns_do_not_stay_in_the_corner():
    """Refilling the table (after a fit) hid the old Model drop-downs only when
    Qt got round to deleting them; until then they covered the colour column."""
    from PyQt5.QtWidgets import QComboBox
    dlg = _window(_series())
    dlg.show()
    dlg.fit_selected()
    dlg.update_peaks_table()
    combos = [c for c in dlg.peaks_table.viewport().findChildren(QComboBox) if c.isVisible()]
    assert len(combos) == len(dlg.peaks)
    dlg.close()


def test_without_peaks_the_button_is_greyed_and_says_what_to_do():
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = _series()
    dlg = PeakFittingDialog(None, spectrum=sp[0], series=sp)
    assert not dlg.fit_button.isEnabled() and not dlg.no_peaks_hint.isHidden()
    assert 'Auto-Detect Peaks' in dlg.no_peaks_hint.text()
    dlg.auto_detect_peaks()
    assert dlg.fit_button.isEnabled() and dlg.no_peaks_hint.isHidden()
    dlg.clear_peaks()
    assert not dlg.fit_button.isEnabled()


def test_copy_results_says_what_it_copied(monkeypatch):
    """Copy Results follows the tab: Series results - what is shown (By peak
    first) for the spectra selected in the list (those in the plot); Peaks -
    the peaks table of the shown spectrum. Its text says which."""
    from PyQt5.QtWidgets import QMessageBox
    said = []
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: said.append(a[2])))
    sp = _series()
    dlg = _window(sp)
    _select(dlg, [0, 1, 2])
    dlg.fit_selected()                                           # 3 of 6 fitted
    assert dlg.left_tabs.currentIndex() == 1                     # Series results shown
    assert dlg.copy_results_btn.text() == 'Copy peak 1 – 3 spectra'
    dlg.copy_results_to_clipboard()
    assert said[-1].startswith('Peak 1 of 3 spectra (01, 02, 03)')
    assert len(QApplication.clipboard().text().splitlines()) == 4
    _select(dlg, [0, 4])
    assert dlg.copy_results_btn.text() == 'Copy peak 1 – 2 spectra'
    dlg.copy_results_to_clipboard()
    assert said[-1].endswith('1 of them not fitted yet: empty row.')
    dlg.left_tabs.setCurrentIndex(0)                             # tab Peaks: the table
    assert dlg.copy_results_btn.text().startswith('Copy table – ')
    dlg.copy_results_to_clipboard()
    assert said[-1].startswith('The 2 peaks of the table (')
    assert len(QApplication.clipboard().text().splitlines()) == 3   # header + 2 peaks
    dlg.series_table.clearSelection()                            # Copy in Series results:
    assert len(dlg.copy_series().splitlines()) == 4              # all fitted ones
    assert dlg.copied_what == 'all fitted ones'
