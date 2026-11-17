"""2D Correlation: redrawing a map whose colorbar belongs to a cleared plot.

With matplotlib 3.11, removing the old colorbar after ax.clear() failed with
"'NoneType' object has no attribute 'get_position'" (found by the smoke test
on 2026-11-17: 2D Correlation > Run, a second time)."""
import numpy as np
from matplotlib.figure import Figure
from mpl_toolkits.axes_grid1 import make_axes_locatable

from src.views.dialogs.visualization_analysis.two_d_correlation_dialog import TwoDCorrelationDialog


class _Canvas:
    def __init__(self):
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)
        self._cbar_ax = None


def _draw(canvas, m):
    TwoDCorrelationDialog._drop_colorbar(canvas)
    canvas.ax.clear()
    cf = canvas.ax.contourf(m, levels=np.linspace(-1, 1, 21), cmap="RdBu_r", extend="both")
    canvas._cbar_ax = make_axes_locatable(canvas.ax).append_axes("right", size="4%", pad=0.4)
    canvas.fig.colorbar(cf, cax=canvas._cbar_ax)
    canvas.fig.canvas.draw()


def test_redraw_and_message_keep_one_colorbar():
    canvas = _Canvas()
    m = np.outer(np.sin(np.linspace(0, 6, 20)), np.cos(np.linspace(0, 5, 20)))
    _draw(canvas, m)
    box = canvas.ax.get_position().bounds
    _draw(canvas, m)                       # the second Run
    canvas.ax.clear()                      # a message on the Difference tab ...
    _draw(canvas, m)                       # ... then a map again
    assert len(canvas.fig.axes) == 2       # the plot and one colorbar
    assert np.allclose(canvas.ax.get_position().bounds, box)   # the plot does not shrink
