"""Peak Fitting with several spectra: every spectrum has its own peaks, and
everything acts on the spectra selected in the list - Auto-Detect Peaks finds
the peaks of each selected spectrum, "Copy these peaks to the selected
spectra" gives them the shown spectrum's peaks, Fit Peaks fits them (each from
its own peaks, or one after another from the previous result). Spectra not
selected are never changed."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtCore import QItemSelectionModel
from PyQt5.QtWidgets import QApplication

from src.modules.data_analysis import peak_fitting_series as pfs
from src.modules.data_analysis.peak_fitting_manager import gaussian

app = QApplication.instance() or QApplication([])


def _mixed():
    """Three 'Raman-like' spectra (bands at 60 and 140) and three different
    ones (bands at 100 and 175)."""
    x = np.linspace(0, 200, 801)
    rng = np.random.default_rng(2)
    out = []
    for i in range(3):
        y = gaussian(x, 1.0, 60, 3.0) + gaussian(x, 0.5, 140, 5.0)
        out.append({'label': f'raman : r{i + 1}', 'x_scale': x,
                    'y_scale': y + rng.normal(0, 0.003, x.size), 'metadata': {}})
    for i in range(3):
        y = gaussian(x, 0.8, 100, 12.0) + gaussian(x, 0.6, 175, 8.0)
        out.append({'label': f'uv : u{i + 1}', 'x_scale': x,
                    'y_scale': y + rng.normal(0, 0.003, x.size), 'metadata': {}})
    return out


def _window(sp, **kw):
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    return PeakFittingDialog(None, spectrum=sp[0], series=sp, **kw)


def _select(dlg, rows):
    lst = dlg.spectra_list
    lst.clearSelection()
    for r in rows:
        lst.selectionModel().select(lst.model().index(r, 0), QItemSelectionModel.Select)


def _centres(peaks):
    return [p['center'] for p in peaks]


def test_auto_detect_changes_only_the_selected_spectra():
    dlg = _window(_mixed())
    assert dlg.peaks_group.title() == 'Peaks of r1 (the shown spectrum)'
    assert not hasattr(dlg, 'peaks_mode_combo')
    dlg.auto_detect_peaks()                                        # one selected: r1 only
    assert np.allclose(_centres(dlg.peaks), [60, 140], atol=1)
    assert all(dlg.peaks_of(k) == [] for k in range(1, 6))
    _select(dlg, [0, 4])
    assert dlg.auto_detect_btn.text() == 'Auto-Detect Peaks – 2 spectra'
    dlg.auto_detect_peaks()
    assert np.allclose(_centres(dlg.peaks_of(4)), [100, 175], atol=1)
    assert dlg.peaks_of(3) == [] and dlg.peaks_of(5) == []        # not selected: untouched
    assert not dlg.select_hint.isHidden() and 'select them first' in dlg.select_hint.text()


def test_copy_and_paste_the_peaks():
    dlg = _window(_mixed())
    assert not dlg.copy_peaks_button.isEnabled() and not dlg.paste_peaks_button.isEnabled()
    dlg.auto_detect_peaks()
    assert dlg.copy_peaks_button.text() == 'Copy peaks of r1'
    dlg.copy_peaks_button.click()
    assert not dlg.paste_peaks_button.isEnabled() or dlg.selected_spectra() == [0]
    _select(dlg, [1, 2])                                           # r2 shown, then both
    assert dlg.paste_peaks_button.text() == 'Paste peaks of r1 to the selected spectra (2)'
    dlg.paste_peaks_button.click()
    assert np.allclose(_centres(dlg.peaks_of(2)), [60, 140], atol=1)
    assert np.allclose(_centres(dlg.peaks_of(1)), [60, 140], atol=1)
    assert dlg.peaks_of(2) is not dlg.peaks_of(1) and dlg.peaks_of(4) == []
    dlg.show_series_spectrum(2)
    assert dlg.peaks_group.title() == 'Peaks of r3 (the shown spectrum)'
    assert float(dlg.peaks_table.item(0, 2).text()) == pytest.approx(60, abs=1)


def test_each_spectrum_from_its_own_peaks():
    sp = _mixed()
    dlg = _window(sp)
    dlg.list_all_button.click()
    dlg.auto_detect_peaks()                                        # each selected one its own
    dlg.fit_selected()
    assert all(r['ok'] and r['r2'] > 0.99 for r in dlg.series_results)
    centre = dlg.series_results[5]['peaks'][1]['parameters']['center']
    assert centre == pytest.approx(175, abs=0.3)
    dlg.show_series_spectrum(4)                                    # its own peaks in the table
    assert dlg.peaks_group.title() == 'Peaks of u2 (the shown spectrum)'
    assert float(dlg.peaks_table.item(0, 2).text()) == pytest.approx(100, abs=0.5)
    dlg.clear_peaks()                                              # only u2's peaks go
    assert dlg.peaks_of(4) == [] and len(dlg.peaks_of(0)) == 2
    _select(dlg, [4])
    assert not dlg.fit_button.isEnabled()                          # u2 has no peaks now
    _select(dlg, [3, 4])
    assert dlg.fit_button.isEnabled() and not dlg.no_peaks_hint.isHidden()
    assert dlg.no_peaks_hint.text() == 'Left out (no peaks): u2.'
    new = dlg.fit_selected()                                       # u2 left out
    assert [r['label'] for r in new] == ['uv : u1']
    dlg.follow_check.setChecked(True)                              # u2 from u1's fit
    assert dlg.no_peaks_hint.text().startswith('No peaks of their own: u2')
    new = dlg.fit_selected()
    assert [r['label'] for r in new] == ['uv : u1', 'uv : u2'] and all(r['ok'] for r in new)


def test_the_peaks_of_each_spectrum_are_remembered():
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = _mixed()
    dlg = _window(sp)
    _select(dlg, [0, 5])
    dlg.auto_detect_peaks()
    settings = dlg.get_results()
    assert len(settings['own_peaks']) == 6 and 'peaks_mode' not in settings
    again = PeakFittingDialog(None, spectrum=sp[0], current_settings=settings, series=sp)
    assert np.allclose(_centres(again.peaks_of(5)), [100, 175], atol=1)
    assert np.allclose(_centres(again.peaks), [60, 140], atol=1)


def test_series_table_has_columns_for_the_most_peaks():
    sp = _mixed()
    dlg = _window(sp)
    dlg.list_all_button.click()
    dlg.auto_detect_peaks()
    dlg.show_series_spectrum(0)
    dlg.peaks.pop()                                                # r1: one peak only
    dlg.update_peaks_table()
    dlg.list_all_button.click()
    dlg.fit_selected()
    columns, rows = dlg.series_rows()
    assert columns[-1] == 'R²' and len(columns) == 1 + 2 * len(pfs.VALUES) + 1
    assert rows[0][5] is None and rows[1][5] is not None           # r1 has no Peak 2


def test_independent_fit_with_own_starts():
    sp = _mixed()
    starts = [[{'model': 'Gaussian', 'center': 60.0, 'amplitude': 1.0, 'width': 3.0}],
              [{'model': 'Gaussian', 'center': 100.0, 'amplitude': 0.8, 'width': 12.0}]]
    res = pfs.fit_series_independent([sp[0], sp[3]], None, starts=starts,
                                     parallel={'processing_mode': 'serial'})
    assert [round(r['peaks'][0]['parameters']['center']) for r in res] == [60, 100]


def test_the_shown_spectrum_stays_when_more_are_selected():
    """Adding spectra to the selection does not change the shown spectrum (its
    peaks stay in the table); selecting one spectrum alone shows it."""
    dlg = _window(_mixed())
    dlg.auto_detect_peaks()
    lst = dlg.spectra_list
    for r in (2, 3):                                               # Ctrl+click
        lst.selectionModel().select(lst.model().index(r, 0), QItemSelectionModel.Select)
    assert dlg.selected_spectra() == [0, 2, 3] and dlg.current_index == 0
    assert 'r1' in dlg.peaks_group.title()
    assert dlg.copy_peaks_to_selected() == [2, 3]
    assert all(np.allclose(_centres(dlg.peaks_of(r)), [60, 140], atol=1) for r in (2, 3))
    _select(dlg, [3])                                              # one alone: shown
    assert dlg.current_index == 3


def test_copy_and_paste_say_why_they_are_greyed():
    dlg = _window(_mixed())
    assert 'has no peaks yet' in dlg.copy_peaks_button.toolTip()
    assert 'First Copy peaks' in dlg.paste_peaks_button.toolTip()


def test_changing_the_peaks_makes_the_fit_not_fitted_yet():
    sp = _mixed()
    dlg = _window(sp)
    _select(dlg, [0, 1, 2])
    dlg.auto_detect_peaks()
    dlg.fit_selected()
    assert all(dlg.series_results[r]['ok'] for r in (0, 1, 2))
    _select(dlg, [0])
    dlg.clear_peaks()                                              # r1: no peaks, no fit
    assert dlg.series_results[0].get('pending') and dlg.spectra_list.item(0).text() == 'r1'
    assert dlg.series_results[1]['ok']                             # the others keep theirs
    _select(dlg, [1])
    dlg.peaks_table.selectRow(0)
    dlg.remove_peak()                                              # Remove Selected Peak(s)
    assert dlg.series_results[1].get('pending') and len(dlg.peaks) == 1
    columns, rows = dlg.series_rows()
    assert rows[0][1] is None and rows[2][1] is not None


def test_own_peaks_or_the_fit_before_and_the_line_says_which():
    """Each selected spectrum starts from its own peaks; one without peaks
    from the fit of the selected spectrum before it; none before it: left out."""
    sp = _mixed()
    dlg = _window(sp)
    _select(dlg, [0, 3])
    dlg.auto_detect_peaks()                                        # r1 and u1 have peaks
    _select(dlg, [0, 1, 3, 4])
    assert dlg.fit_button.isEnabled() and not dlg.follow_check.isChecked()   # off by default
    assert dlg.no_peaks_hint.text() == 'Left out (no peaks): r2, u2.'
    dlg.follow_check.setChecked(True)
    assert dlg.no_peaks_hint.text().startswith('No peaks of their own: r2, u2 \u2013 each starts')
    new = dlg.fit_selected()
    assert [r['label'] for r in new] == ['raman : r1', 'raman : r2', 'uv : u1', 'uv : u2']
    assert all(r['ok'] and r['r2'] > 0.99 for r in new)            # u2 followed u1, not r2
    assert np.allclose(_centres(dlg.peaks_of(4)), [100, 175], atol=1)
    _select(dlg, [2, 5])                                           # r3 has none and none before
    assert not dlg.fit_button.isEnabled()
    _select(dlg, [2, 3])
    assert 'Left out (no peaks, no fit before them): r3' in dlg.no_peaks_hint.text()
    assert dlg.fit_button.isEnabled()


def test_clear_all_peaks_clears_the_selected_spectra():
    sp = _mixed()
    dlg = _window(sp)
    dlg.list_all_button.click()
    dlg.auto_detect_peaks()
    dlg.fit_selected()
    _select(dlg, [0, 1, 2])
    assert dlg.clear_peaks_btn.text() == 'Clear All Peaks \u2013 3 spectra'
    dlg.clear_peaks()
    assert all(dlg.peaks_of(r) == [] for r in (0, 1, 2)) and dlg.peaks_of(3)
    assert all(dlg.series_results[r].get('pending') for r in (0, 1, 2))
    assert dlg.series_results[3]['ok']
    assert not dlg.spectra_list.item(1).text().startswith('\u2713')


def test_spectra_with_peaks_are_marked_in_the_list():
    dlg = _window(_mixed())
    _select(dlg, [0, 4])
    dlg.auto_detect_peaks()
    lst = dlg.spectra_list
    assert lst.item(4).font().bold() and not lst.item(3).font().bold()
    assert lst.item(4).foreground().color().name() == '#2e7d32'
    assert lst.item(3).foreground().color().name() == '#9e9e9e'
    assert not lst.item(4).icon().isNull()                         # the dot, seen also selected


def test_a_long_name_is_shortened_above_the_plot():
    sp = _mixed()
    sp[1]['label'] = 'f : Raman_spectrum_of_cell_in_liquid_buffer_with_mg_and_ca_corrected'
    dlg = _window(sp)
    dlg.show_series_spectrum(1)
    assert dlg.current_label.text() == '<b>Raman_spectrum_of_cell_in_liquid\u2026</b>'
    assert 'corrected' in dlg.current_label.toolTip()


def test_a_peak_selected_in_the_table_is_emphasized_in_the_plot():
    dlg = _window(_mixed())
    dlg.auto_detect_peaks()
    dlg.update_plot()
    dlg.peaks_table.selectRow(1)
    line0, line1 = dlg._peak_lines[0][0], dlg._peak_lines[1][0]
    assert line1.get_linewidth() == 3.0 and line0.get_linewidth() == 1.5
    assert len(dlg._peak_fills) == 1
    dlg.peaks_table.clearSelection()
    assert line1.get_linewidth() == 1.5 and not dlg._peak_fills


def test_off_by_default_and_remembered_and_a_poor_fit_is_marked():
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = _mixed()
    dlg = _window(sp)
    _select(dlg, [2])
    dlg.auto_detect_peaks()                                        # r3: Raman peaks
    dlg.follow_check.setChecked(True)
    _select(dlg, [2, 3])                                           # u1 follows r3: a poor fit
    new = dlg.fit_selected()
    assert new[1]['ok'] and new[1]['r2'] < 0.9
    assert dlg.spectra_list.item(3).text().startswith('\u26a0 ')    # ⚠, not ✓
    assert dlg.spectra_list.item(2).text().startswith('\u2713 ')
    again = PeakFittingDialog(None, spectrum=sp[0], current_settings=dlg.get_results(),
                              series=sp)
    assert again.follow_check.isChecked()
    fresh = _window(sp)
    assert not fresh.follow_check.isChecked()
