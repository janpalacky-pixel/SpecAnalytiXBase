"""keep zoom in the tool windows that show one spectrum after another
(tool_keep_zoom.py): zoomed in on a band, a plot drawn anew stays there,
y fitted; Home: the whole range; other windows, the tick off, a range the
window narrows itself, a plot without data there: as before."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout

app = QApplication.instance() or QApplication([])

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.backend_bases import MouseEvent
from matplotlib.figure import Figure

from src.views import toolbar_mode, tool_keep_zoom


def _pump(seconds=0.1):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


X = np.linspace(400, 1800, 1401)


def _spectrum(height):
    return height * (0.2 + np.exp(-0.5 * ((X - 1004) / 6) ** 2)
                     + 0.5 * np.exp(-0.5 * ((X - 1450) / 10) ** 2))


class NormalizationDialog(QDialog):          # a window of tool_keep_zoom.WINDOWS
    def __init__(self):
        super().__init__()
        self.figure = Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        lay = QVBoxLayout(self)
        lay.addWidget(self.canvas)
        lay.addWidget(self.toolbar)
        self.show_spectrum(1.0)

    def show_spectrum(self, height):         # as the windows do: cleared, drawn anew
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.plot(X, _spectrum(height), label='s')
        ax.set_xlabel('Wavenumber')
        self.canvas.draw()
        return ax


class OtherDialog(NormalizationDialog):      # not in the list
    pass


@pytest.fixture(autouse=True)
def installed():
    toolbar_mode.install(app)
    tool_keep_zoom.set_enabled(True)
    yield
    tool_keep_zoom.set_enabled(True)


def _open(cls=NormalizationDialog):
    dlg = cls()
    dlg.resize(700, 500)
    dlg.show()
    _pump()
    return dlg


def _wheel_zoom(dlg, steps=4):
    ax = dlg.figure.axes[0]
    dlg.canvas.draw()
    x, y = ax.transData.transform((1004, np.mean(ax.get_ylim())))
    for _ in range(steps):
        dlg.canvas.callbacks.process('scroll_event', MouseEvent(
            'scroll_event', dlg.canvas, x, y, button='up', step=1))
    _pump()
    return tuple(sorted(ax.get_xlim()))


def test_a_spectrum_drawn_anew_stays_zoomed_and_y_fitted():
    dlg = _open()
    assert tool_keep_zoom.keeper(dlg.canvas) is not None
    zoom = _wheel_zoom(dlg)
    assert zoom[1] - zoom[0] < 1000
    ax = dlg.show_spectrum(5.0)                   # another, 5 x stronger spectrum
    assert tuple(sorted(ax.get_xlim())) == pytest.approx(zoom)
    lo, hi = ax.get_ylim()
    inside = (X >= zoom[0]) & (X <= zoom[1])
    assert lo < (5 * _spectrum(1.0))[inside].min() and hi > (5 * _spectrum(1.0))[inside].max()
    assert hi < 5 * 1.3                           # fitted to it, not to the old one
    # Home: the whole range, and the next spectrum whole too
    dlg.toolbar.home()
    _pump()
    ax = dlg.show_spectrum(2.0)
    assert sorted(ax.get_xlim())[1] > 1790
    dlg.close()


def test_toolbar_zoom_is_kept_too():
    dlg = _open()
    ax = dlg.figure.axes[0]
    tb = dlg.toolbar
    tb.push_current()
    ax.set_xlim(1400, 1500)
    tb._update_view = tb._update_view            # (wrapped by tool_keep_zoom)
    tool_keep_zoom.record(dlg.canvas)            # as after Zoom of the toolbar
    ax = dlg.show_spectrum(3.0)
    assert tuple(sorted(ax.get_xlim())) == pytest.approx((1400, 1500))
    dlg.close()


def test_other_windows_and_the_tick_off():
    other = _open(OtherDialog)
    assert tool_keep_zoom.keeper(other.canvas) is None
    other.close()
    dlg = _open()
    _wheel_zoom(dlg)
    tool_keep_zoom.set_enabled(False)
    ax = dlg.show_spectrum(2.0)
    assert sorted(ax.get_xlim())[1] > 1790
    dlg.close()


def test_a_range_the_window_sets_itself_is_left_alone():
    dlg = _open()
    _wheel_zoom(dlg)
    dlg.figure.clear()
    ax = dlg.figure.add_subplot(111)
    ax.plot(X, _spectrum(1.0))
    ax.set_xlabel('Wavenumber')
    ax.set_xlim(600, 700)                         # the window's own choice
    dlg.canvas.draw()
    assert tuple(sorted(ax.get_xlim())) == pytest.approx((600, 700))
    dlg.close()


def test_no_data_there_or_another_kind_of_plot():
    dlg = _open()
    _wheel_zoom(dlg)
    dlg.figure.clear()
    ax = dlg.figure.add_subplot(111)
    ax.plot(np.arange(10), np.arange(10))         # e.g. components 0..9
    ax.set_xlabel('Component')
    dlg.canvas.draw()
    assert sorted(ax.get_xlim())[1] < 20
    dlg.close()


def test_peak_fitting_and_the_processing_windows_are_listed():
    for name in ('PeakFittingDialog', 'BaselineCorrectionDialog', 'AutomatedBaselineDialog',
                 'SNIPBaselineDialog', 'FFTDenoisingDialog', 'NormalizationDialog',
                 'SpikeRemovalInteractiveDialog', 'InteractiveSubtractionDialog'):
        assert name in tool_keep_zoom.WINDOWS


def test_peak_fitting_arrows_keep_the_zoom():
    """The real window: zoomed on the first band, ▶ shows the next spectrum
    of the series there; Home the whole range."""
    from src.modules.data_analysis.peak_fitting_manager import gaussian
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    x = np.linspace(0, 200, 401)
    series = [{'label': f'scan : {i + 1:02d}', 'x_scale': x,
               'y_scale': (1 + i) * (gaussian(x, 1.0, 60 + 2 * i, 4.0) + gaussian(x, 0.4, 140, 6.0)),
               'metadata': {}} for i in range(3)]
    dlg = PeakFittingDialog(None, spectrum=series[0], series=series)
    dlg.resize(1200, 800)
    dlg.show()
    _pump(0.3)
    assert tool_keep_zoom.keeper(dlg.canvas) is not None
    ax = dlg.ax_main
    dlg.canvas.draw()
    px, py = ax.transData.transform((60, np.mean(ax.get_ylim())))
    for _ in range(5):
        dlg.canvas.callbacks.process('scroll_event', MouseEvent(
            'scroll_event', dlg.canvas, px, py, button='up', step=1))
    _pump()
    zoom = tuple(sorted(ax.get_xlim()))
    assert zoom[1] - zoom[0] < 100
    dlg.step_shown(+1)
    _pump(0.3)
    dlg.canvas.draw()
    ax = dlg.ax_main
    assert tuple(sorted(ax.get_xlim())) == pytest.approx(zoom, rel=1e-6)
    assert ax.get_ylim()[1] > 1.9                # the second spectrum: twice as high
    dlg.toolbar.home() if hasattr(dlg, 'toolbar') else None
    dlg.close()


def test_normalization_list_keeps_the_zoom():
    """The real Normalization window: zoomed, another spectrum chosen in its
    list - the plot stays at the zoom."""
    from src.views.dialogs.data_analysis.normalization_dialog import NormalizationDialog
    spectra = [{'label': f'r : {i}', 'x_scale': X.copy(), 'y_scale': _spectrum(1 + i),
                'metadata': {}} for i in range(3)]
    dlg = NormalizationDialog(selected_spectra=spectra)
    dlg.resize(1200, 800)
    dlg.show()
    _pump(0.3)
    canvas = dlg.canvas
    assert tool_keep_zoom.keeper(canvas) is not None
    ax = canvas.figure.axes[0]
    canvas.draw()
    px, py = ax.transData.transform((1004, np.mean(ax.get_ylim())))
    for _ in range(5):
        canvas.callbacks.process('scroll_event', MouseEvent(
            'scroll_event', canvas, px, py, button='up', step=1))
    _pump()
    zoom = tuple(sorted(ax.get_xlim()))
    assert zoom[1] - zoom[0] < 1000
    lst = dlg.spectra_list
    lst.clearSelection()
    lst.item(2).setSelected(True)
    _pump(0.3)
    canvas.draw()
    ax = canvas.figure.axes[0]
    assert tuple(sorted(ax.get_xlim())) == pytest.approx(zoom, rel=1e-6)
    dlg.close()


# ------------------------------------------------- the real processing windows
WINDOW_LISTS = [('Manual baseline', 'spectra_list'), ('Automated Baseline', 'spectra_list'),
                ('SNIP Baseline', '_list'), ('FFT Denoising', 'spectra_list'),
                ('Spike removal', 'spectrum_list'), ('Interactive subtraction', 'minuend_list')]


@pytest.mark.parametrize('operation, list_name', WINDOW_LISTS)
def test_processing_windows_keep_the_zoom_and_fit_y(operation, list_name, monkeypatch, tmp_path):
    """Opened from the main window on the 11 Raman spectra: zoomed on the 1004
    band of sp001 (by far the strongest), sp005 chosen in the window's list -
    the plot stays at the band, y fitted to sp005 (not left at sp001's height)."""
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    data = os.path.join(root, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, [data], [{}])))
    from src.controllers.core.main_controller import MainController
    mc = MainController()
    mc.import_controller._run_import(clear_first=True, file_paths=[data])
    _pump()
    mc.spectrum_selector.select_all_items()
    _pump()
    seen = {}

    def drive(dlg):
        dlg.resize(1300, 850)
        dlg.show()
        _pump(0.5)
        lst = getattr(dlg, list_name)
        lst.setCurrentRow(0)
        lst.itemClicked.emit(lst.item(0))           # (some windows follow the click only)
        _pump(0.5)
        canvases = [c for c in dlg.findChildren(FigureCanvasQTAgg)
                    if tool_keep_zoom.keeper(c) is not None and c.isVisible()
                    and c.figure.axes and tool_keep_zoom._full(c.figure.axes[0]) is not None]
        assert canvases, 'no plot that keeps the zoom'
        canvas = canvases[0]
        ax = canvas.figure.axes[0]
        canvas.draw()
        px, py = ax.transData.transform((1004, np.mean(ax.get_ylim())))
        for _ in range(6):
            canvas.callbacks.process('scroll_event', MouseEvent(
                'scroll_event', canvas, px, py, button='up', step=1))
        _pump(0.3)
        zoom = tuple(sorted(ax.get_xlim()))
        top_before = ax.get_ylim()[1]
        lst.setCurrentRow(4)
        lst.itemClicked.emit(lst.item(4))
        _pump(1.0)
        canvas.draw()
        _pump(0.2)
        ax = canvas.figure.axes[0]
        seen['zoom'] = zoom
        seen['after'] = tuple(sorted(ax.get_xlim()))
        seen['top_before'], seen['top_after'] = top_before, ax.get_ylim()[1]
        dlg.close()
        return 0
    from PyQt5.QtWidgets import QDialog
    monkeypatch.setattr(QDialog, 'exec_', drive)
    monkeypatch.setattr(QDialog, 'exec', drive)
    try:
        mc.operations_controller.show_parameters_dialog_for(operation)
        _pump(0.3)
    finally:
        mc.autosave_controller.shutdown()
        mc.view.close()
    assert seen, 'the window did not open'
    assert seen['zoom'][1] - seen['zoom'][0] < 1000
    assert seen['after'] == pytest.approx(seen['zoom'], rel=1e-6)
    assert seen['top_after'] < 0.8 * seen['top_before']     # sp005 is much weaker: y fitted


def test_the_zoomed_note_in_a_tool_window():
    dlg = _open()
    note = dlg.toolbar._sax_mode_note
    assert 'Zoomed' not in note.text()
    zoom = _wheel_zoom(dlg)
    assert note.text().startswith('Zoomed: ') and 'Home shows all' in note.text()
    dlg.show_spectrum(2.0)
    _pump()
    assert note.text().startswith('Zoomed: ')
    dlg.toolbar.home()
    _pump()
    assert 'Zoomed' not in note.text()
    dlg.close()
