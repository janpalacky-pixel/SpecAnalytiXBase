"""Several spectra selected, none of them with peaks: Fit Peaks is greyed and
the orange line under it says how to give them a start (Copy/Paste peaks from
the spectrum that has them, the box "start from the fit before them", or
Auto-Detect Peaks)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from tests.test_peak_fitting_one_fit_button import PEAKS, _select, _series

app = QApplication.instance() or QApplication([])


def _window_with_peaks_on(rows):
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = _series()
    dlg = PeakFittingDialog(None, spectrum=sp[0], series=sp)
    for r in rows:
        _select(dlg, [r])
        dlg.peaks = [dict(p) for p in PEAKS]
        dlg.update_peaks_table()
    return dlg


def test_selected_without_peaks_names_the_one_that_has_them():
    dlg = _window_with_peaks_on([0])                  # like raman_11: only it has peaks
    dlg.follow_check.setChecked(False)
    _select(dlg, [2, 3, 4, 5])                        # like raman_13 - raman_18
    assert dlg.peaks_of(0) and not any(dlg.peaks_of(k) for k in (2, 3, 4, 5))
    assert not dlg.fit_button.isEnabled()
    hint = dlg.no_peaks_hint.text()
    assert not dlg.no_peaks_hint.isHidden()
    assert hint.startswith('None of the 4 selected spectra has peaks.')
    assert 'Copy peaks of' in hint and 'Paste peaks of' in hint and 'to the selected spectra' in hint
    assert 'tick the checkbox' in hint
    assert 'start from the fit before them' in hint
    assert 'Auto-Detect Peaks – 4 spectra' in hint


def test_doing_what_the_hint_says_enables_the_button():
    dlg = _window_with_peaks_on([0])
    _select(dlg, [0, 2, 3])                           # the one with peaks first, then the others
    dlg.follow_check.setChecked(True)
    assert dlg.fit_button.isEnabled()


def test_no_spectrum_has_peaks_yet():
    dlg = _window_with_peaks_on([])
    _select(dlg, [1, 2])
    hint = dlg.no_peaks_hint.text()
    assert not dlg.fit_button.isEnabled()
    assert hint.startswith('None of the 2 selected spectra has peaks yet')
    assert 'Auto-Detect Peaks – 2 spectra' in hint and 'Add via Click' in hint


def test_box_ticked_says_select_the_one_with_peaks_too():
    """The user ticked the box but did not select the spectrum with peaks."""
    dlg = _window_with_peaks_on([0])
    dlg.follow_check.setChecked(True)
    _select(dlg, [2, 3, 4, 5])
    hint = dlg.no_peaks_hint.text()
    assert not dlg.fit_button.isEnabled()
    assert 'is ticked' in hint and 'hold Ctrl and click 01' in hint
    _select(dlg, [0, 2, 3, 4, 5])                     # Ctrl+click on it
    assert dlg.fit_button.isEnabled()


def test_copy_results_follows_the_tab(monkeypatch):
    """Tab Peaks: "Copy table - <shown spectrum>" copies the peaks table, also
    after Auto-Detect with other spectra selected. Tab Series results: "Copy
    results - N spectra" copies the rows of the spectra selected in the list."""
    from PyQt5.QtWidgets import QMessageBox
    said = []
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: said.append(a[2])))
    dlg = _window_with_peaks_on([0])
    dlg.left_tabs.setCurrentIndex(0)
    _select(dlg, [0])
    assert dlg.copy_results_btn.text() == 'Copy table – 01'
    assert 'peaks table above' in dlg.copy_results_btn.toolTip()
    dlg.copy_results_to_clipboard()
    assert said[-1].startswith('The 2 peaks of the table (01: start values, not fitted yet)')
    dlg.fit_selected()
    dlg.left_tabs.setCurrentIndex(0)
    _select(dlg, [0, 1, 2])
    dlg.auto_detect_peaks()
    dlg.copy_results_to_clipboard()
    assert 'of the table (01:' in said[-1]
    assert QApplication.clipboard().text().startswith('Peak\tModel\tCenter')
    dlg.left_tabs.setCurrentIndex(1)
    assert dlg.copy_results_btn.text() == 'Copy peak 1 – 3 spectra'
    assert 'selected in the list' in dlg.copy_results_btn.toolTip()
    dlg.copy_results_to_clipboard()
    assert said[-1].startswith('Peak 1 of 3 spectra (01, 02, 03)')
