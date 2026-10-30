"""The Peaks window, tab List: a double-clicked peak is shown on the main plot -
its spectrum highlighted and the peak circled with its position."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


# --- a double-clicked peak on the main plot -----------------------------------------------

def _plot(offsets=(0.0, 5.0)):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    x = np.linspace(0, 100, 501)
    spectra = [{'label': f's{k}', 'x_scale': x,
                'y_scale': (k + 1) * np.exp(-((x - 40) / 3) ** 2)} for k in range(len(offsets))]
    fig = Figure()
    ax = fig.add_subplot(111)
    for sp, b in zip(spectra, offsets):
        ax.plot(sp['x_scale'], sp['y_scale'] + b)                # a stacked plot
    canvas = FigureCanvasAgg(fig)
    return canvas, ax, spectra


def _controller(canvas):
    from src.controllers.data_analysis.peak_detection_controller import PeakDetectionController

    class Main:
        view = None
        static_canvas = canvas
    return PeakDetectionController(Main())


def test_a_peak_is_shown_on_the_main_plot_and_removed_again():
    canvas, ax, spectra = _plot()
    pdc = _controller(canvas)
    limits = ax.get_xlim(), ax.get_ylim()
    assert pdc.show_peak_on_plot(spectra[1], 40.0, 2.0)
    band, ring, text = pdc.shown_artists
    assert ring.get_ydata()[0] == pytest.approx(7.0)              # at the line's offset
    assert 's1' in text.get_text() and '40' in text.get_text()
    assert (ax.get_xlim(), ax.get_ylim()) == limits                # the view stays
    assert pdc.show_peak_on_plot(spectra[0], 40.0, 1.0)            # the next one replaces it
    assert sum(1 for ln in ax.get_lines() if ln.get_gid() == pdc.SHOWN_GID) == 2
    pdc.clear_peaks()
    assert not [ln for ln in ax.get_lines() if ln.get_gid() == pdc.SHOWN_GID]
    other = {'label': 'not plotted', 'x_scale': np.arange(3.0), 'y_scale': np.ones(3)}
    assert not pdc.show_peak_on_plot(other, 1.0, 1.0)


def test_a_double_click_in_the_list_shows_its_peak():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    _, _, spectra = _plot()
    shown = []
    dlg = PeakListDialog(None, spectra, show_peak=lambda sp, x, y: shown.append((sp, x, y)) or True)
    assert 'Double-click' in dlg.table.toolTip()
    dlg.table.cellDoubleClicked.emit(1, 3)
    sp, x, y = shown[0]
    assert sp is spectra[1] and x == pytest.approx(40) and y == pytest.approx(2)
    assert 'On the main plot: s1' in dlg.fits_on_plot_info.text()
    dlg = PeakListDialog(None, spectra, show_peak=lambda *a: False)
    assert not dlg.show_row_on_plot(0)
    assert 'not on the main plot' in dlg.fits_on_plot_info.text()
