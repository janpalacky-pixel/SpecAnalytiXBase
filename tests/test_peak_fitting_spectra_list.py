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
    data, fit = lines[2], lines[3]                               # 03, not the shown one
    assert data.get_marker() == '.' and data.get_linestyle() == 'None'   # Data: Points
    assert fit.get_color() == data.get_color() and fit.get_linestyle() == '-'
    assert data.get_alpha() < 1
    assert lines[1].get_linewidth() > fit.get_linewidth()        # the shown one (01) stronger
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
    # data only, and the 2 starting peaks of the shown spectrum (dashed)
    assert len(dlg.figure.axes[0].get_lines()) == 3 + 2
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
    # 6 data + its fit + the 2 starting peaks of the shown spectrum (01, not fitted)
    assert len(dlg.figure.axes[0].get_lines()) == 7 + 2
    dlg.view_combo.setCurrentIndex(2)                            # Grid: no "not fitted" in red
    assert all('not fitted' not in ax.get_title() for ax in dlg.figure.axes)
    # remembered with the window
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    again = PeakFittingDialog(None, spectrum=sp[0], current_settings=dlg.get_results(),
                              series=sp)
    assert again.series_results[2]['ok'] and again.series_results[0].get('pending')
    columns, rows = pfs.series_table(again.series_results, 2)
    assert rows[0][1] is None and rows[2][1] is not None


def test_the_list_selection_is_kept_when_opened_again(monkeypatch):
    """Opened again for the same spectra: the spectra selected in the list
    last time (e.g. All) are selected again - not only the first one."""
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: None))
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = _series(4)
    dlg = PeakFittingDialog(None, spectrum=sp[0], series=sp)
    dlg.peaks = [dict(p) for p in PEAKS]
    dlg.update_peaks_table()
    dlg._select_in_list([0, 2, 3], notify=True)
    again = PeakFittingDialog(None, spectrum=sp[0], series=sp,
                              current_settings=dlg.get_results())
    assert again.selected_spectra() == [0, 2, 3] and again.view_mode != 'one'
    dlg.list_all_button.click()
    dlg.fit_selected()
    again = PeakFittingDialog(None, spectrum=sp[0], series=sp,
                              current_settings=dlg.get_results())
    assert again.selected_spectra() == [0, 1, 2, 3] and again.view_mode != 'one'


def test_the_shown_spectrum_has_a_frame_among_the_selected():
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = _series(5)
    dlg = PeakFittingDialog(None, spectrum=sp[0], series=sp)
    assert dlg.list_delegate.shown_row == 0
    dlg._select_in_list([2], notify=True)                     # one alone: it is shown
    assert dlg.current_index == 2 and dlg.list_delegate.shown_row == 2
    dlg._select_in_list([1, 2, 4], notify=True)               # several: the shown one stays
    assert dlg.current_index == 2 and dlg.list_delegate.shown_row == 2
    assert 'Orange frame' in dlg.spectra_list.toolTip()


def test_add_via_click_with_several_spectra_adds_to_the_shown_one(monkeypatch):
    """Overlay of several spectra: a click adds a peak to the shown spectrum
    (orange frame), its height from that spectrum's data under the click."""
    sp = _series(4)
    dlg = _window(sp)
    _select(dlg, [0, 1, 3])
    assert dlg.view_mode == 'overlay' and dlg.current_index == 0
    assert 'adds a peak to 01 (orange frame)' in dlg.click_hint.text()

    class Click:
        inaxes = dlg._series_ax
        button = 1
        xdata = 140.0
        ydata = 0.9                      # where clicked - not used for the height
    n = len(dlg.peaks)
    dlg.on_canvas_click(Click())
    assert len(dlg.peaks) == n + 1
    assert abs(dlg.peaks[-1]['amplitude'] - 0.4) < 0.05       # spectrum 01's band at 140
    assert dlg.selected_spectra() == [0, 1, 3]                  # still several shown


class _Click:
    button = 1

    def __init__(self, ax, x, y):
        self.inaxes, self.xdata, self.ydata = ax, x, y


def test_waterfall_and_grid_a_click_adds_to_the_spectrum_clicked_on():
    """Waterfall: the band clicked in; Grid: the small plot clicked in - that
    spectrum gets the peak and becomes the shown one (orange frame)."""
    sp = _series(4)
    dlg = _window(sp)
    _select(dlg, [0, 1, 3])
    dlg.view_combo.setCurrentIndex(1)                           # Waterfall
    assert dlg.view_mode == 'waterfall'
    assert 'spectrum clicked on' in dlg.click_hint.text()
    bands = dict((r, (lo, hi)) for r, lo, hi in dlg._bands)
    lo, hi = bands[3]
    dlg.on_canvas_click(_Click(dlg._series_ax, 140.0, (lo + hi) / 2))
    assert dlg.current_index == 3 and dlg.list_delegate.shown_row == 3
    assert [round(p['center']) for p in dlg.peaks] == [140]     # spectrum 04 had no peaks
    assert dlg.selected_spectra() == [0, 1, 3]
    assert dlg._series_ax.patches                               # its band framed in orange
    dlg.view_combo.setCurrentIndex(2)                           # Grid
    assert 'small plot' in dlg.click_hint.text()
    ax1 = next(a for a, r in dlg._grid_axes.items() if r == 1)
    dlg.on_canvas_click(_Click(ax1, 60.0, 0.5))
    assert dlg.current_index == 1 and [round(p['center']) for p in dlg.peaks] == [60]
    ax1 = next(a for a, r in dlg._grid_axes.items() if r == 1)  # (drawn again)
    assert ax1.spines['top'].get_linewidth() > 2                # the orange frame
    assert ax1.title.get_fontweight() == 'bold'


def test_the_arrows_move_the_orange_frame_among_the_selected():
    from PyQt5.QtGui import QKeySequence
    from PyQt5.QtWidgets import QShortcut
    sp = _series(6)
    dlg = _window(sp)
    _select(dlg, [1, 3, 4])
    assert dlg.current_index == 1                               # (selected first)
    assert not dlg.prev_button.isEnabled() and dlg.next_button.isEnabled()
    assert 'all stay selected' in dlg.next_button.toolTip()
    dlg.next_button.click()
    assert dlg.current_index == 3 and dlg.view_mode == 'overlay'
    dlg.step_shown(+1)
    assert dlg.current_index == 4 and not dlg.next_button.isEnabled()
    dlg.prev_button.click()
    assert dlg.current_index == 3 and dlg.selected_spectra() == [1, 3, 4]
    keys = {s.key().toString() for s in dlg.findChildren(QShortcut)}
    assert {'Alt+Left', 'Alt+Right', 'Alt+Up', 'Alt+Down'} <= keys
    # the keys work wherever the focus is - and a drop-down list with the
    # focus does not change its value or open
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    # (shown, so closed again at the end: a window left open confuses later
    # tests that look for "the open window")
    dlg.show()
    try:
        dlg.activateWindow()
        QApplication.processEvents()
        combo = dlg.background_combo
        for widget in (dlg.spectra_list, combo, dlg.peaks_table, dlg.view_combo):
            for key, want in ((Qt.Key_Up, 1), (Qt.Key_Down, 3), (Qt.Key_Left, 1),
                              (Qt.Key_Right, 3)):
                widget.setFocus()
                value = combo.currentIndex()
                QTest.keyClick(widget, key, Qt.AltModifier)
                assert dlg.current_index == want, (widget, key)
                assert combo.currentIndex() == value and QApplication.activePopupWidget() is None
        assert dlg.selected_spectra() == [1, 3, 4]
    finally:
        dlg.hide()
    _select(dlg, [3])                                           # one alone: as before
    dlg.step_shown(+1)
    assert dlg.current_index == 4 and dlg.selected_spectra() == [4]
    dlg.deleteLater()


def test_the_columns_of_the_table_can_be_moved():
    from PyQt5.QtWidgets import QHeaderView
    dlg = _window(_series(1))
    h = dlg.peaks_table.horizontalHeader()
    assert h.sectionResizeMode(2) == QHeaderView.Interactive
    dlg.peaks_table.setColumnWidth(2, 222)                      # moved by hand
    dlg._share_columns()
    assert dlg.peaks_table.columnWidth(2) == 222 and dlg._columns_moved


def test_the_mouse_wheel_does_not_change_the_drop_down_lists():
    """The wheel over a drop-down list (also the Model of a peak) leaves it
    as it is; the left part or the table scrolls instead."""
    from PyQt5.QtCore import QPoint, QPointF, Qt
    from PyQt5.QtGui import QWheelEvent
    from PyQt5.QtWidgets import QComboBox
    dlg = _window(_series(4))
    dlg.show()
    try:
        QApplication.processEvents()
        model = dlg.peaks_table.cellWidget(0, 1)
        for combo in (dlg.background_combo, dlg.amplitude_combo, dlg.sigma_combo, model):
            assert isinstance(combo, QComboBox)
            before = combo.currentIndex()
            for delta in (-120, 120, -120):
                pos = QPointF(combo.width() / 2, combo.height() / 2)
                e = QWheelEvent(pos, QPointF(combo.mapToGlobal(pos.toPoint())), QPoint(0, 0),
                                QPoint(0, delta), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase,
                                False)
                QApplication.sendEvent(combo, e)
            assert combo.currentIndex() == before
        dlg.update_peaks_table()                                  # new Model drop-downs too
        model = dlg.peaks_table.cellWidget(1, 1)
        before = model.currentIndex()
        pos = QPointF(5, 5)
        QApplication.sendEvent(model, QWheelEvent(pos, QPointF(model.mapToGlobal(QPoint(5, 5))),
                                                  QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                                                  Qt.NoModifier, Qt.NoScrollPhase, False))
        assert model.currentIndex() == before
    finally:
        dlg.hide()
        dlg.deleteLater()
