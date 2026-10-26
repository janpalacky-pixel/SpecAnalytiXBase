"""Peak list > Refine by fitting > Show on the main plot: each fitted peak (the
model band plus its background) drawn dashed over its spectrum on the main
plot - the selected rows, or all peaks; also on a stacked plot; untick or
Clear Peaks removes them."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_analysis import peak_list as pl

app = QApplication.instance() or QApplication([])


def _series(n=3):
    x = np.linspace(0, 100, 501)
    out = []
    for i in range(n):
        y = (1 + 0.2 * i) * np.exp(-((x - 40) / 3) ** 2) + 0.5 * np.exp(-((x - 70) / 2) ** 2) \
            + 0.002 * x
        out.append({'label': f'scan : {i + 1:02d}', 'x_scale': x, 'y_scale': y, 'metadata': {}})
    return out


def test_the_curves_are_the_fits_of_the_table():
    sp = _series()
    rows, index = pl.peak_table_with_index(sp, threshold=0.1, prominence=0.1, distance=0.01)
    fitted, _ = pl.refine_by_fitting(rows, index, sp)
    curves = pl.fit_curves(rows, index, sp)
    assert len(curves) == len(rows) == 6
    centre = pl.ALL_COLUMNS.index('Fitted position')
    for (i, x, y), row, r_i in zip(curves, fitted, index):
        assert i == r_i
        top = x[np.argmax(y)]                                  # the curve peaks where the fit says
        assert abs(top - row[centre]) < (x[1] - x[0]) * 1.01
        xs, ys = np.asarray(sp[i]['x_scale']), np.asarray(sp[i]['y_scale'])
        assert np.max(np.abs(np.interp(x, xs, ys) - y)) < 0.02  # and follows the spectrum
    assert [c[0] for c in pl.fit_curves(rows, index, sp, which=[3])] == [index[3]]


def test_a_line_is_matched_to_its_spectrum_also_when_shifted():
    x = np.linspace(0, 10, 11)
    y = np.sin(x)
    assert pl.line_offset(x, y, x, y) == 0.0
    assert pl.line_offset(x, y + 2.5, x, y) == pytest.approx(2.5)
    assert pl.line_offset(x, 2 * y, x, y) is None                  # another line
    assert pl.line_offset(x[:5], y[:5], x, y) is None


def test_the_tick_draws_and_removes_through_the_callback():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    shown = []

    def show(curves):
        shown.append(curves)
        return None if curves is None else len(curves)
    dlg = PeakListDialog(None, _series(), threshold=0.1, prominence=0.1, distance=0.01,
                         show_fits=show)
    assert not dlg.fits_on_plot_check.isHidden() and not dlg.fits_on_plot_check.isEnabled()
    dlg.refine_check.setChecked(True)
    assert dlg.fits_on_plot_check.isEnabled()
    dlg.fits_on_plot_check.setChecked(True)
    assert len(shown[-1]) == 6 and shown[-1][0][0] is dlg.spectra[0]
    assert 'On the main plot: 6 fitted peak(s)' in dlg.fits_on_plot_info.text()
    dlg.table.selectRow(0)                                         # only the selected row
    assert len(shown[-1]) == 1
    dlg.fits_on_plot_check.setChecked(False)
    assert shown[-1] is None and dlg.fits_on_plot_info.isHidden()
    dlg.fits_on_plot_check.setChecked(True)
    dlg.refine_check.setChecked(False)                             # no fits: removed
    assert shown[-1] is None


def test_without_a_main_plot_there_is_no_tick():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    dlg = PeakListDialog(None, _series(), threshold=0.1, prominence=0.1, distance=0.01)
    assert dlg.fits_on_plot_check.isHidden() and dlg.draw_fits_on_plot() == 0


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    controller = MainController()
    controller.import_controller._run_import(
        clear_first=True, file_paths=[os.path.join(root, 'resources', 'test_data', 'synthetic',
                                                   'raman_2comp_clean.xlsx')])
    controller.spectrum_selector.select_all_items()
    app.processEvents()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def test_on_the_main_plot_and_cleared_by_clear_peaks(mc, monkeypatch):
    from src.views.dialogs.data_analysis import peak_list_dialog as pld
    monkeypatch.setattr(pld.PeakListDialog, 'exec_', lambda self: 0)
    pdc = mc.peak_detection_controller
    dlg = pdc.show_peak_list()
    dlg.refine_check.setChecked(True)
    ax = mc.static_canvas.figure.get_axes()[0]
    limits = ax.get_xlim(), ax.get_ylim()
    dlg.fits_on_plot_check.setChecked(True)
    fits = [ln for ln in ax.get_lines() if ln.get_gid() == pdc.FIT_GID]
    assert len(fits) == len(pdc.fit_artists) > 0
    assert (ax.get_xlim(), ax.get_ylim()) == limits                # the view stays
    assert all(ln.get_linestyle() == '--' for ln in fits)
    pdc.clear_peaks()
    assert not [ln for ln in ax.get_lines() if ln.get_gid() == pdc.FIT_GID]
    assert pdc.fit_artists == []


def test_a_stacked_line_gets_its_offset():
    from types import SimpleNamespace
    from matplotlib.figure import Figure
    from src.controllers.data_analysis.peak_detection_controller import PeakDetectionController
    fig = Figure()
    ax = fig.add_subplot()
    sp = _series(2)
    for k, s in enumerate(sp):
        ax.plot(s['x_scale'], np.asarray(s['y_scale']) + 3 * k)     # stacked by 3
    canvas = SimpleNamespace(figure=fig, draw_idle=lambda: None, draw=lambda: None)
    pdc = PeakDetectionController(SimpleNamespace(static_canvas=canvas))
    x = np.array([39.0, 40.0, 41.0])
    assert pdc.show_fits_on_plot([(sp[1], x, np.array([1.0, 2.0, 1.0])),
                                  ({'x_scale': [1, 2], 'y_scale': [1, 2]}, x, x)]) == 1
    assert list(pdc.fit_artists[0].get_ydata()) == [4.0, 5.0, 4.0]  # + its offset 3
    assert pdc.show_fits_on_plot(None) == 0 and pdc.fit_artists == []


def test_a_selected_row_stays_selected_when_refine_by_fitting_is_ticked():
    """Select a row, then tick Refine by fitting and Show on the main plot:
    only that peak is drawn (ticking used to refill the table and lose the
    selection, so all peaks were drawn)."""
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    shown = []
    dlg = PeakListDialog(None, _series(), threshold=0.1, prominence=0.1, distance=0.01,
                         show_fits=lambda c: shown.append(c) or (0 if c is None else len(c)))
    dlg.table.selectRow(3)
    picked = dlg.selected_rows()
    assert len(picked) == 1
    dlg.refine_check.setChecked(True)
    assert dlg.selected_rows() == picked                         # still selected
    dlg.fits_on_plot_check.setChecked(True)
    assert len(shown[-1]) == 1
    dlg.threshold.setValue(0.5)                                  # other peaks: what is gone is gone
    assert all(r < len(dlg.rows) for r in dlg.selected_rows())
