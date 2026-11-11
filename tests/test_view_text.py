"""Numbers marking a point of the data (a peak's position, a pinned cursor's
x, your own labels) are drawn only while that point is in the view: zoomed
away (the mouse wheel, Zoom, Pan) they are not left floating outside the
plot, and the plot does not shrink to make room for them."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from src.modules.visualization.view_text import ViewText, add_view_text, point_in_view


def _figure():
    fig = Figure(figsize=(6, 4), dpi=100, layout='constrained')
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    x = np.linspace(200, 1300, 500)
    ax.plot(x, np.exp(-((x - 1245) / 10) ** 2))
    return fig, ax


def test_a_peak_number_out_of_the_view_is_not_drawn_nor_makes_room():
    fig, ax = _figure()
    label = add_view_text(ax, 1245.31, 1.0, '1245.31', ha='center', va='bottom')
    fig.canvas.draw()
    assert label.in_view()
    ax.set_xlim(345, 1065)                                  # zoomed: the peak out of the view
    fig.canvas.draw()
    width_without = ax.bbox.width
    assert not label.in_view()
    assert not np.isfinite(label.get_tightbbox(fig.canvas.get_renderer()).width) \
        or label.get_tightbbox(fig.canvas.get_renderer()).width <= 0
    # an ordinary text there would have made the plot narrower (as in the report)
    other = ax.text(1245.31, 1.0, '1245.31')
    fig.canvas.draw()
    assert ax.bbox.width < width_without - 20
    other.remove()
    ax.set_xlim(200, 1300)                                  # back: drawn again
    fig.canvas.draw()
    assert label.in_view()


def test_only_x_for_a_pinned_cursors_number_above_the_plot():
    fig, ax = _figure()
    t = add_view_text(ax, 722, 1.0, '722', only_x=True, transform=ax.get_xaxis_transform(),
                      va='bottom', ha='center')
    fig.canvas.draw()
    assert t.in_view()                                      # above the axes, x inside
    ax.set_xlim(800, 1300)
    fig.canvas.draw()
    assert not t.in_view()


def test_reversed_axis_and_the_edge():
    fig, ax = _figure()
    ax.set_xlim(1300, 200)                                  # reverse x
    fig.canvas.draw()
    assert point_in_view(ax, 1245, 0.5)
    assert point_in_view(ax, 200, 0.5)                      # on the edge: in
    assert not point_in_view(ax, 150, 0.5)
    assert not point_in_view(ax, 1245, 5.0)                 # above the y range


def test_it_pickles_as_save_plot_for_publication_needs():
    import pickle
    fig, ax = _figure()
    add_view_text(ax, 1245.31, 1.0, '1245.31')
    copy = pickle.loads(pickle.dumps(fig))
    t = [t for t in copy.axes[0].texts if isinstance(t, ViewText)][0]
    copy.axes[0].set_xlim(300, 400)
    FigureCanvasAgg(copy).draw()
    assert not t.in_view()


def test_detect_peaks_numbers_use_it():
    from src.modules.data_analysis.peak_detection_manager import PeakDetector
    fig, ax = _figure()
    det = PeakDetector()
    det.detect_peaks(fig.canvas, 0.0, 9, 0, 2, 'fixed', 'x', True, 0.1, 0.05, 'Positive',
                     labels='all')
    assert det.peak_texts and all(isinstance(t, ViewText) for t in det.peak_texts)
    assert not any(t.get_clip_on() for t in det.peak_texts)  # not cut at the axes' top


def test_pinned_cursors_numbers_close_together_go_one_line_higher():
    from src.modules.visualization.view_text import add_row_text
    fig, ax = _figure()
    ax.set_xlim(345, 1065)
    a = add_row_text(ax, 722, '722', va='bottom', ha='center', fontsize=7.5)
    b = add_row_text(ax, 726, '726', va='bottom', ha='center', fontsize=7.5)
    c = add_row_text(ax, 950, '950', va='bottom', ha='center', fontsize=7.5)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ba, bb = a.get_window_extent(renderer), b.get_window_extent(renderer)
    assert ba.y1 <= bb.y0 + 1 or bb.y1 <= ba.y0 + 1        # not on top of each other
    assert {a.get_position()[1], b.get_position()[1]} != {1.0}
    assert c.get_position()[1] == 1.0                      # far away: in the row
    assert max(ba.y1, bb.y1) <= fig.bbox.y1 + 0.5         # the layout made room for it
    ax.set_xlim(715, 735)                                  # zoomed in: apart, one row
    fig.canvas.draw()
    assert a.get_position()[1] == b.get_position()[1] == 1.0
