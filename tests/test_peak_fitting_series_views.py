"""The tab Series results shows the spectra selected in the list By peak (one
peak at a time, a row per spectrum), By spectrum (each spectrum with its
peaks, collapsible) or All in one table; Copy results copies what is shown.
The names of the values are those of the table of peaks (Center, Height,
Width, Extra, FWHM, Area)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from src.modules.data_analysis import peak_fitting_series as pfs
from tests.test_peak_fitting_one_fit_button import _select, _series, _window

app = QApplication.instance() or QApplication([])


def _fitted():
    dlg = _window(_series())
    dlg.list_all_button.click()
    dlg.fit_button.click()                                       # all 6 fitted
    return dlg


def test_values_have_the_names_of_the_peaks_table():
    dlg = _window(_series())
    heads = [dlg.peaks_table.horizontalHeaderItem(c).text() for c in range(2, 6)]
    assert heads == ['Center', 'Height', 'Width', 'Extra']
    assert pfs.PEAK_COLUMNS[1:5] == heads


def test_peaks_long_keeps_a_row_for_a_spectrum_without_values():
    results = pfs.pending([{'label': 'a : s1'}, {'label': 'a : s2'}])
    results[0] = {'label': 'a : s1', 'ok': True, 'r2': 0.99, 'peaks': [
        {'model': 'Voigt', 'parameters': {'center': 5.0, 'height': 2.0, 'sigma': 1.0,
                                          'gamma': 0.5, 'fwhm': 3.0, 'area': 7.0}}]}
    columns, rows = pfs.peaks_long(results, [0, 1])
    assert columns == ['Spectrum', 'Peak', 'Model', 'Center', 'Height', 'Width', 'Extra',
                       'FWHM', 'Area', 'R²']
    assert rows[0] == ['a : s1', 1, 'Voigt', 5.0, 2.0, 1.0, 0.5, 3.0, 7.0, 0.99]
    assert rows[1][:3] == ['a : s2', None, 'not fitted yet'] and rows[1][-1] is None


def test_by_peak_one_peak_at_a_time_for_the_selected_spectra():
    dlg = _fitted()
    dlg.left_tabs.setCurrentIndex(1)
    assert dlg.series_view() == 'peak' and dlg.series_stack.currentIndex() == 0
    t = dlg.by_peak_table
    heads = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    assert heads == ['Spectrum', 'Model', 'Center', 'Height', 'Width', 'FWHM', 'Area', 'R²']
    # (Extra only when a peak has one: Voigt, Pseudo-Voigt)
    assert t.rowCount() == 6
    centres = [float(t.item(r, 2).text()) for r in range(6)]
    assert np.allclose(centres, [60 + 2 * i for i in range(6)], atol=0.05)
    assert dlg.series_peak_label.text().startswith('1 of 2')
    assert not dlg.series_peak_prev.isEnabled()
    dlg.series_peak_next.click()
    assert dlg.series_peak_label.text().startswith('2 of 2 (≈ 140')
    assert float(t.item(0, 2).text()) == pytest.approx(140, abs=0.1)
    assert dlg.copy_results_btn.text() == 'Copy peak 2 – 6 spectra'
    _select(dlg, [1, 3])                                         # the list decides the rows
    assert t.rowCount() == 2 and t.item(0, 0).text() == '02'
    assert dlg.copy_results_btn.text() == 'Copy peak 2 – 2 spectra'
    dlg.series_view_text()
    lines = QApplication.clipboard().text().splitlines()
    assert lines[0].startswith('Spectrum\tPeak\tModel\tCenter\tHeight') and len(lines) == 3
    assert lines[1].startswith('scan : 02\t2\tGaussian\t')


def test_by_spectrum_each_with_its_peaks_and_folding_is_kept():
    dlg = _fitted()
    dlg.left_tabs.setCurrentIndex(1)
    dlg.set_series_view('spectrum')
    assert dlg.series_stack.currentIndex() == 1
    tree = dlg.by_spectrum_tree
    assert tree.topLevelItemCount() == 6
    first = tree.topLevelItem(0)
    assert first.text(0) == '01' and first.childCount() == 2 and first.isExpanded()
    assert first.child(0).text(0) == 'Peak 1' and first.child(0).text(1) == 'Gaussian'
    assert tree.isColumnHidden(5)                                # no Extra for Gaussians
    first.setExpanded(False)
    dlg._refresh_series_views()
    assert not tree.topLevelItem(0).isExpanded() and tree.topLevelItem(1).isExpanded()
    assert dlg.copy_results_btn.text() == 'Copy results – 6 spectra'
    dlg.series_view_text()
    assert len(QApplication.clipboard().text().splitlines()) == 1 + 6 * 2


def test_a_spectrum_not_fitted_yet_is_shown_as_such():
    dlg = _window(_series())
    _select(dlg, [0])
    dlg.fit_selected()                                           # only the first one
    _select(dlg, [0, 1])
    dlg.left_tabs.setCurrentIndex(1)
    assert dlg.by_peak_table.item(1, 1).text() == 'not fitted yet'
    dlg.set_series_view('spectrum')
    assert dlg.by_spectrum_tree.topLevelItem(1).text(1) == 'not fitted yet'
    assert dlg.by_spectrum_tree.topLevelItem(1).childCount() == 0


def test_all_in_one_table_is_the_wide_one():
    dlg = _fitted()
    dlg.left_tabs.setCurrentIndex(1)
    dlg.set_series_view('wide')
    assert dlg.series_stack.currentWidget() is dlg.series_table
    dlg.series_view_text()
    lines = QApplication.clipboard().text().splitlines()
    assert lines[0].startswith('Spectrum\tPeak 1 position') and len(lines) == 7
