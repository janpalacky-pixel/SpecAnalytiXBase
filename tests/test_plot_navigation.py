"""The plots of the tool windows: the mouse wheel zooms (x; Ctrl: y), the
left button held and moved drags the plot, Back / Home go back - unless the
window uses the mouse on that plot itself (a click adds a point, a range is
drawn) or Zoom / Pan of its toolbar is on. The pressed Zoom / Pan button and
the note beside it (toolbar_mode.py) are there too."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout

app = QApplication.instance() or QApplication([])

from src.views import plot_navigation, toolbar_mode

toolbar_mode.install(app)


def _pump():
    for _ in range(5):
        app.processEvents()


def _window(twin=False):
    dlg = QDialog()
    fig = Figure(figsize=(6, 4), dpi=100)
    canvas = FigureCanvasQTAgg(fig)
    tb = NavigationToolbar2QT(canvas, dlg)
    lay = QVBoxLayout(dlg)
    lay.addWidget(canvas)
    lay.addWidget(tb)
    ax = fig.add_subplot(111)
    ax.plot(range(100), [i % 10 for i in range(100)], label='data')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 10)
    if twin:
        ax2 = ax.twinx()
        ax2.plot(range(100), range(100))
        ax2.set_ylim(0, 100)
    dlg.resize(700, 500)
    dlg.show()
    _pump()
    canvas.draw()
    return dlg, canvas, tb, ax


def _at(ax, xd, yd):
    return ax.transData.transform((xd, yd))


def _fire(canvas, name, x, y, **kw):
    canvas.callbacks.process(name, MouseEvent(name, canvas, x, y, **kw))


def _drag(canvas, ax, a, b):
    (x0, y0), (x1, y1) = _at(ax, *a), _at(ax, *b)
    _fire(canvas, 'button_press_event', x0, y0, button=1)
    for i in range(1, 5):
        _fire(canvas, 'motion_notify_event', x0 + (x1 - x0) * i / 4, y0 + (y1 - y0) * i / 4,
              button=1)
    _fire(canvas, 'button_release_event', x1, y1, button=1)


def test_every_plot_toolbar_gives_its_plot_the_navigation():
    dlg, canvas, tb, ax = _window()
    assert isinstance(getattr(canvas, '_sax_navigation', None), plot_navigation.PlotNavigation)
    assert getattr(tb, '_sax_mode_note', None) is not None        # the mode note too
    dlg.close()


def test_wheel_zooms_x_ctrl_y_and_home_goes_back():
    dlg, canvas, tb, ax = _window()
    x, y = _at(ax, 50, 5)
    _fire(canvas, 'scroll_event', x, y, button='up', step=1)
    lo, hi = ax.get_xlim()
    assert hi - lo == pytest.approx(80) and lo == pytest.approx(10, abs=0.1)  # around x = 50
    assert ax.get_ylim() == pytest.approx((0, 10))
    _fire(canvas, 'scroll_event', x, y, button='up', step=1, modifiers={'ctrl'})
    assert ax.get_ylim()[1] - ax.get_ylim()[0] == pytest.approx(8)
    tb.home()
    assert ax.get_xlim() == pytest.approx((0, 100)) and ax.get_ylim() == pytest.approx((0, 10))
    dlg.close()


def test_drag_moves_the_plot_a_click_does_not_and_back_goes_back():
    dlg, canvas, tb, ax = _window()
    x, y = _at(ax, 50, 5)
    _fire(canvas, 'button_press_event', x, y, button=1)
    _fire(canvas, 'button_release_event', x + 1, y, button=1)     # a click
    assert ax.get_xlim() == pytest.approx((0, 100))
    _drag(canvas, ax, (50, 5), (70, 5))
    assert ax.get_xlim() == pytest.approx((-20, 80), abs=1)
    tb.back()
    assert ax.get_xlim() == pytest.approx((0, 100))
    dlg.close()


def test_twin_axes_move_together():
    dlg, canvas, tb, ax = _window(twin=True)
    ax2 = canvas.figure.axes[1]
    _drag(canvas, ax, (50, 5), (50, 7))                              # up by 2 of 10
    assert ax.get_ylim() == pytest.approx((-2, 8), abs=0.2)
    assert ax2.get_ylim() == pytest.approx((-20, 80), abs=2)
    dlg.close()


def test_not_when_the_window_uses_presses_itself_but_the_wheel_still_zooms():
    dlg, canvas, tb, ax = _window()
    clicks = []
    canvas.mpl_connect('button_press_event', lambda e: clicks.append(e.xdata))
    _drag(canvas, ax, (50, 5), (70, 5))
    assert ax.get_xlim() == pytest.approx((0, 100)) and len(clicks) == 1
    x, y = _at(ax, 50, 5)
    _fire(canvas, 'scroll_event', x, y, button='up', step=1)
    assert ax.get_xlim()[1] - ax.get_xlim()[0] == pytest.approx(80)
    dlg.close()


def test_a_range_selector_takes_the_drag_only_while_on():
    from matplotlib.widgets import SpanSelector
    dlg, canvas, tb, ax = _window()
    span = SpanSelector(ax, lambda a, b: None, 'horizontal')
    _drag(canvas, ax, (50, 5), (70, 5))
    assert ax.get_xlim() == pytest.approx((0, 100))                 # the range is drawn
    span.set_active(False)
    _drag(canvas, ax, (50, 5), (70, 5))
    assert ax.get_xlim() == pytest.approx((-20, 80), abs=1)          # off: the plot moves
    x, y = _at(ax, 50, 5)
    span.set_active(True)
    _fire(canvas, 'scroll_event', x, y, button='up', step=1)       # its wheel does nothing
    assert ax.get_xlim()[1] - ax.get_xlim()[0] == pytest.approx(80)
    dlg.close()


def test_a_movable_legend_is_dragged_not_the_plot():
    dlg, canvas, tb, ax = _window()
    leg = ax.legend(loc='center')
    leg.set_draggable(True)
    canvas.draw()
    box = leg.get_window_extent(canvas.get_renderer())
    xd, yd = ax.transData.inverted().transform(((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2))
    _drag(canvas, ax, (xd, yd), (xd + 20, yd))
    assert ax.get_xlim() == pytest.approx((0, 100))
    dlg.close()


def test_nothing_while_zoom_or_pan_of_the_toolbar_is_on_nor_on_the_main_plot():
    dlg, canvas, tb, ax = _window()
    tb.zoom()
    x, y = _at(ax, 50, 5)
    _fire(canvas, 'scroll_event', x, y, button='up', step=1)
    assert ax.get_xlim() == pytest.approx((0, 100))
    tb.zoom()
    canvas._sax_main_plot = True                                   # plot_mouse_controller's own
    _fire(canvas, 'scroll_event', x, y, button='up', step=1)
    _drag(canvas, ax, (50, 5), (70, 5))
    assert ax.get_xlim() == pytest.approx((0, 100))
    dlg.close()


def test_a_colour_bar_is_not_zoomed():
    dlg, canvas, tb, ax = _window()
    import numpy as np
    image = ax.imshow(np.random.rand(10, 10), extent=(0, 100, 0, 10), aspect='auto')
    bar = canvas.figure.colorbar(image)
    canvas.draw()
    before = bar.ax.get_ylim()
    box = bar.ax.bbox
    _fire(canvas, 'scroll_event', (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2,
          button='up', step=1, modifiers={'ctrl'})
    assert bar.ax.get_ylim() == pytest.approx(before)
    dlg.close()
