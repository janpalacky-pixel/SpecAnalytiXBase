"""Peak Fitting for a series: the list of the spectra beside the plot works
as in the main window - one selected: it alone with its fit; several
selected: together (Overlay, Waterfall, Grid) with their fits drawn thick in
the colour of their data. A fit of a single spectrum (Fit Peaks) is kept
for the series too."""
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
    rng = np.random.default_rng(3)
    return [{'label': f'scan : {i + 1:02d}', 'x_scale': x,
             'y_scale': gaussian(x, 1.0, 60 + 2 * i, 4.0) + gaussian(x, 0.4, 140, 6.0)
             + rng.normal(0, 0.003, x.size), 'metadata': {}} for i in range(n)]


PEAKS = [{'model': 'Gaussian', 'center': 60.0, 'amplitude': 1.0, 'width': 4.0, 'color': '#1f77b4'},
         {'model': 'Gaussian', 'center': 140.0, 'amplitude': 0.4, 'width': 6.0, 'color': '#ff7f0e'}]


def _window(sp, **kw):
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    dlg = PeakFittingDialog(None, spectrum=sp[0], series=sp, **kw)
    dlg.follow_check.setChecked(True)                            # peaks on the first only
    dlg.peaks = [dict(p) for p in PEAKS]
    dlg.update_peaks_table()
    return dlg


def _select(dlg, rows):
    lst = dlg.spectra_list
    lst.clearSelection()
    for r in rows:
        lst.selectionModel().select(lst.model().index(r, 0), QItemSelectionModel.Select)


def test_the_list_shows_one_or_several_spectra():
    sp = _series()
    dlg = _window(sp)
    assert dlg.spectra_list.count() == 6 and dlg.selected_spectra() == [0]
    assert dlg.spectra_list.item(2).text() == '03'                # short names
    assert not dlg.view_combo.isEnabled() and dlg.view_mode == 'one'
    _select(dlg, [1, 3, 4])
    assert dlg.view_mode == 'overlay' and dlg.view_combo.isEnabled()
    assert len(dlg.figure.axes) == 1 and len(dlg.figure.axes[0].lines) == 3
    dlg.view_combo.setCurrentIndex(2)                            # Grid
    assert len(dlg.figure.axes) == 3
    _select(dlg, [4])                                            # one again: it alone
    assert dlg.view_mode == 'one' and dlg.current_index == 4 and len(dlg.figure.axes) == 2
    assert dlg.ax_main.get_title().endswith('scan : 05')
    dlg.prev_button.click()                                      # ◀ ▶: one spectrum each
    assert dlg.selected_spectra() == [3] and dlg.current_index == 3
    assert '04' in dlg.current_label.text()
    dlg.list_button.click()                                      # the list can be hidden
    assert dlg.spectra_panel.isHidden()
    dlg.list_button.click()
    assert not dlg.spectra_panel.isHidden()


def test_several_fitted_spectra_show_their_fits_thick_in_their_colour():
    sp = _series()
    dlg = _window(sp)
    dlg.fit_all_selected()
    _select(dlg, [0, 2, 5])
    ax = dlg.figure.axes[0]
    lines = ax.get_lines()
    assert len(lines) == 6                                       # 3 data + 3 fits
    data, fit = lines[0], lines[1]
    assert fit.get_linewidth() > 2 * data.get_linewidth()
    assert fit.get_color() == data.get_color() and fit.get_linestyle() == '-'
    assert data.get_alpha() < 1
    assert [t.get_text() for t in ax.get_legend().get_texts()] == ['01', '03', '06']
    assert 'fits thick' in ax.get_title()
    assert dlg.selected_series_rows() == [0, 2, 5]               # the same rows in the table
    dlg.list_fitted_button.click()
    assert dlg.selected_spectra() == list(range(6))


def test_selecting_rows_in_series_results_selects_the_spectra():
    sp = _series()
    dlg = _window(sp)
    dlg.fit_all_selected()
    t = dlg.series_table
    t.clearSelection()
    for r in (1, 2):
        t.selectionModel().select(t.model().index(r, 0),
                                  QItemSelectionModel.Select | QItemSelectionModel.Rows)
    assert dlg.selected_spectra() == [1, 2] and dlg.view_mode != 'one'


def test_fit_all_keeps_several_selected_spectra_shown():
    sp = _series()
    dlg = _window(sp)
    _select(dlg, [0, 1, 2])
    assert len(dlg.figure.axes[0].get_lines()) == 3             # data only
    dlg.fit_all_selected()
    assert dlg.selected_spectra() == [0, 1, 2] and dlg.view_mode == 'overlay'
    assert len(dlg.figure.axes[0].get_lines()) == 6             # now with the fits


def test_a_fit_of_one_spectrum_is_kept_for_the_series():
    sp = _series()
    dlg = _window(sp)
    dlg.show_series_spectrum(2)
    dlg.peaks = [dict(p) for p in PEAKS]                         # spectrum 3's own peaks
    dlg.update_peaks_table()
    dlg.perform_fit()
    res = dlg.series_results
    assert res[2]['ok'] and all(r.get('pending') for k, r in enumerate(res) if k != 2)
    assert dlg.spectra_list.item(2).text().startswith('✓ ')
    assert dlg.spectra_list.item(1).text() == '02'               # not fitted yet: no mark
    assert 'Fitted 1 of 6 spectra. 5 not fitted yet' in dlg.series_info.text()
    assert 'converge' not in dlg.series_info.text()
    _select(dlg, range(6))
    assert len(dlg.figure.axes[0].get_lines()) == 7             # 6 data + its fit
    dlg.view_combo.setCurrentIndex(2)                            # Grid: no "not fitted" in red
    assert all('not fitted' not in ax.get_title() for ax in dlg.figure.axes)
    # remembered with the window
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    again = PeakFittingDialog(None, spectrum=sp[0], current_settings=dlg.get_results(),
                              series=sp)
    assert again.series_results[2]['ok'] and again.series_results[0].get('pending')
    columns, rows = pfs.series_table(again.series_results, 2)
    assert rows[0][1] is None and rows[2][1] is not None
