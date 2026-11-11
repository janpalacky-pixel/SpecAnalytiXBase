"""Small mouse conveniences on the main plot (as in Origin, Spectragryph,
Excel): the mouse wheel zooms where the mouse is (x; Ctrl: y; Home goes
back); pointing at a line shows its name and a click on it makes its row of
the list current (the selection stays) and draws it thicker; a click on a
name in the legend hides / shows that spectrum (not in a publication picture
either)."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from matplotlib.backend_bases import MouseEvent
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')

from src.controllers.visualization.plot_mouse_controller import PlotMouseController


def _pump(seconds=0.15):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, [DATA], [{}])))
    from src.controllers.core.main_controller import MainController
    ctrl = MainController()
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    lw = ctrl.spectra_list_widget
    lw.clearSelection()
    for i in (4, 5, 6):                                # sp005 - sp007
        lw.item(i).setSelected(True)
    _pump(0.3)
    ctrl.plot_spectra()
    _pump(0.3)
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def _ax(mc):
    return mc.static_canvas.figure.axes[0]


def _event(mc, name, xdata, ydata, **kw):
    canvas = mc.static_canvas
    canvas.draw()
    x, y = _ax(mc).transData.transform((xdata, ydata))
    return MouseEvent(name, canvas, x, y, **kw)


def _fire(mc, event):
    mc.static_canvas.callbacks.process(event.name, event)
    _pump(0.05)


def _line(mc, short):
    return next(l for l in mc.plot_mouse_controller.data_lines(_ax(mc))
                if str(l.get_label()).endswith(short))


def test_zoomed_keeps_a_reversed_axis_and_works_on_log():
    z = PlotMouseController.zoomed
    assert z(0, 100, 50, 0.5) == (25, 75)
    assert z(100, 0, 50, 0.5) == (75, 25)                      # x from high to low
    lo, hi = z(1, 1000, 10, 0.5, log=True)
    assert lo == pytest.approx(10 ** 0.5) and hi == pytest.approx(10 ** 2)


def test_the_wheel_zooms_x_where_the_mouse_is_ctrl_y_and_home_goes_back(mc):
    ax = _ax(mc)
    x0, y0 = ax.get_xlim(), ax.get_ylim()
    at = 1000.0
    _fire(mc, _event(mc, 'scroll_event', at, sum(y0) / 2, button='up', step=1))
    x1 = ax.get_xlim()
    assert x1[1] - x1[0] == pytest.approx(0.8 * (x0[1] - x0[0]))
    assert (at - x1[0]) / (x1[1] - x1[0]) == pytest.approx((at - x0[0]) / (x0[1] - x0[0]))
    assert ax.get_ylim() == y0
    # Ctrl held: as matplotlib reports it from Qt (modifiers; key is None)
    _fire(mc, _event(mc, 'scroll_event', at, sum(y0) / 2, button='down', step=-1,
                     modifiers=frozenset({'ctrl'})))
    assert ax.get_ylim()[1] - ax.get_ylim()[0] > y0[1] - y0[0]    # Ctrl: y, zoomed out
    assert ax.get_xlim() == x1
    mc.static_canvas.toolbar.home()
    assert ax.get_xlim() == pytest.approx(x0) and ax.get_ylim() == pytest.approx(y0)


def test_ctrl_is_seen_however_it_is_reported():
    from types import SimpleNamespace as E
    held = PlotMouseController.ctrl_held
    assert held(E(modifiers=frozenset({'ctrl'}), key=None))
    assert held(E(modifiers=frozenset(), key='control'))
    assert not held(E(modifiers=frozenset({'shift'}), key=None))
    assert not held(E(modifiers=None, key=None))


def test_pointing_and_clicking_a_line(mc):
    line = _line(mc, 'sp006')
    xs, ys = line.get_xdata(), line.get_ydata()
    k = len(xs) // 2
    event = _event(mc, 'button_press_event', xs[k], ys[k], button=1)
    m = mc.plot_mouse_controller
    assert m.line_at(event) is line                              # its name on pointing
    width = line.get_linewidth()
    before = [i.text() for i in mc.spectra_list_widget.selectedItems()]
    _fire(mc, event)
    lw = mc.spectra_list_widget
    assert lw.currentItem().text().endswith('sp006')               # its row of the list
    assert [i.text() for i in lw.selectedItems()] == before       # the selection stays
    assert line.get_linewidth() > width                           # drawn thicker
    _fire(mc, _event(mc, 'button_press_event', xs[k], ys[k] * 10, button=1))   # elsewhere
    assert line.get_linewidth() == width


def test_not_while_the_cursor_is_on(mc):
    mc.plot_cursor_controller.set_enabled(True)
    line = _line(mc, 'sp006')
    xs, ys = line.get_xdata(), line.get_ydata()
    width = line.get_linewidth()
    _fire(mc, _event(mc, 'button_press_event', xs[10], ys[10], button=1))
    assert line.get_linewidth() == width
    mc.plot_cursor_controller.set_enabled(False)


def _click_legend_name(mc, short):
    canvas = mc.static_canvas
    canvas.draw()
    leg = _ax(mc).get_legend()
    text = next(t for t in leg.get_texts() if t.get_text().endswith(short))
    box = text.get_window_extent(canvas.get_renderer())
    x, y = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    for name in ('button_press_event', 'button_release_event'):
        _fire(mc, MouseEvent(name, canvas, x, y, button=1))
    return text


def test_a_click_on_the_legend_hides_and_shows_a_spectrum(mc):
    from src.modules.visualization import publication_figure as pf
    from src.modules.visualization import publication_style as pst
    line = _line(mc, 'sp006')
    text = _click_legend_name(mc, 'sp006')
    assert not line.get_visible() and text.get_alpha() == pytest.approx(0.3)
    assert 'hidden' in mc.view.statusBar().currentMessage()
    # not in a publication picture: neither the line nor its legend entry
    copy = pf.copy_for_publication(mc.static_canvas.figure, 8.5, 6.5, font_pt=7)
    assert not any(s['label'].endswith('sp006') for s in pst.series(copy))
    legend_texts = [t.get_text() for a in copy.axes if a.get_legend()
                    for t in a.get_legend().get_texts()]
    assert legend_texts and not any(t.endswith('sp006') for t in legend_texts)
    # the same spectra plotted again: still hidden; a click shows it again
    mc.plot_spectra()
    _pump(0.3)
    assert not _line(mc, 'sp006').get_visible()
    _click_legend_name(mc, 'sp006')
    assert _line(mc, 'sp006').get_visible()


def test_other_spectra_plotted_show_all_again(mc):
    _click_legend_name(mc, 'sp006')
    assert mc.plot_mouse_controller.hidden
    mc.spectra_list_widget.item(7).setSelected(True)               # one more spectrum
    _pump(0.3)
    mc.plot_spectra()
    _pump(0.3)
    assert not mc.plot_mouse_controller.hidden
    assert _line(mc, 'sp006').get_visible()


def test_the_nearest_line_counts_not_the_one_on_top():
    """Two lines a few pixels apart (as raman_06 under raman_07): a click
    just on the lower one marks the lower one, although the other is drawn
    on top and is also within reach."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    class _Main:
        plot_cursor_controller = None
        plot_notes_controller = None
    fig = Figure(figsize=(4, 3), dpi=100)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 100)
    low, = ax.plot([0, 10], [50, 50], label='raman_06')
    high, = ax.plot([0, 10], [52, 52], label='raman_07')        # ~4 px higher, on top
    canvas.draw()
    m = PlotMouseController(_Main())
    m.canvas = canvas
    x, y = ax.transData.transform((5, 50))
    assert m.line_at(MouseEvent('button_press_event', canvas, x, y + 0.5)) is low
    x, y = ax.transData.transform((5, 52))
    assert m.line_at(MouseEvent('button_press_event', canvas, x, y - 0.5)) is high
    x, y = ax.transData.transform((5, 80))
    assert m.line_at(MouseEvent('button_press_event', canvas, x, y)) is None   # far from both


def test_the_marked_spectrums_row_is_bold(mc):
    line = _line(mc, 'sp006')
    xs, ys = line.get_xdata(), line.get_ydata()
    k = len(xs) // 2
    _fire(mc, _event(mc, 'button_press_event', xs[k], ys[k], button=1))
    lw = mc.spectra_list_widget
    bold = [lw.item(i).text() for i in range(lw.count()) if lw.item(i).font().bold()]
    assert len(bold) == 1 and bold[0].endswith('sp006')
    assert lw.marked_item is not None and lw.marked_item.text().endswith('sp006')  # its frame
    lw.viewport().repaint()                                       # the frame is drawn
    _fire(mc, _event(mc, 'button_press_event', xs[k], ys[k] * 10, button=1))
    assert not any(lw.item(i).font().bold() for i in range(lw.count()))
    assert lw.marked_item is None


def _names(mc):
    """The data lines' names, thin spaces as plain ones."""
    return [' '.join(str(l.get_label()).replace('\u2009', ' ').replace('\u202f', ' ').split())
            for l in mc.plot_mouse_controller.data_lines(_ax(mc))]


def _plot_as(mc, plot_type):
    mc.view.comboBox_plot_type_choice.setCurrentText(plot_type)
    _pump(0.2)
    mc.plot_spectra()
    _pump(0.3)


def test_hidden_stays_hidden_in_every_plot_type_and_is_left_out(mc):
    """A hidden spectrum is in no plot: Grid draws it invisible, Mean ± SD,
    Difference and Heatmap are computed without it; back in Overlay it is
    still hidden (the same selection)."""
    _click_legend_name(mc, 'sp006')
    mouse = mc.plot_mouse_controller
    assert len(mouse.hidden) == 1 and next(iter(mouse.hidden)).endswith('sp006')

    _plot_as(mc, "Grid plot")
    lines = [l for a in mc.static_canvas.figure.axes for l in mouse.data_lines(a)]
    assert lines and all(l.get_visible() != str(l.get_label()).endswith('sp006')
                         for l in lines)

    _plot_as(mc, "Mean ± SD")
    names = _names(mc)
    assert any('n = 2' in n for n in names), names            # 3 selected, 1 hidden
    _click_legend_name(mc, '2)')                              # not a spectrum: nothing
    assert len(mouse.hidden) == 1

    _plot_as(mc, "Heatmap")
    image = _ax(mc).images[0]
    assert image.get_array().shape[0] == 2                    # no row for sp006

    _plot_as(mc, "Difference")
    names = _names(mc)
    assert names and not any(n.endswith('sp006') for n in names), names

    _plot_as(mc, "Overlay plot")
    assert not _line(mc, 'sp006').get_visible()
    assert _line(mc, 'sp005').get_visible()


def test_show_all_spectra_from_the_right_click(mc):
    _click_legend_name(mc, 'sp006')
    _plot_as(mc, "Mean ± SD")
    mouse = mc.plot_mouse_controller
    mouse.show_all()                                          # right-click > Show all spectra
    _pump(0.3)
    assert not mouse.hidden
    names = _names(mc)
    assert any('n = 3' in n for n in names), names
    _plot_as(mc, "Overlay plot")
    assert _line(mc, 'sp006').get_visible()


def test_visible_keeps_the_reference_and_never_leaves_nothing():
    class _Main:
        _display_labels = {'a': 'a', 'b': 'b'}
    m = PlotMouseController(_Main())
    spectra = [{'label': 'a'}, {'label': 'b'}]
    m.hidden = {'a'}
    assert [s['label'] for s in m.visible(spectra)] == ['b']
    assert [s['label'] for s in m.visible(spectra, keep='a')] == ['a', 'b']
    m.hidden = {'a', 'b'}
    assert len(m.visible(spectra)) == 2                     # all hidden: all of them
    assert m.full_label('Mean (n = 2)') is None             # not a spectrum
    m.sync_selection(spectra)
    assert not m.hidden                                      # a new selection
    m.hidden = {'a'}
    m.sync_selection(list(reversed(spectra)))                # the same selection
    assert m.hidden == {'a'}


def _entry(mc, short):
    leg = _ax(mc).get_legend()
    handles = list(getattr(leg, 'legend_handles', None) or leg.legendHandles)
    i = next(i for i, t in enumerate(leg.get_texts()) if t.get_text().endswith(short))
    return leg.get_texts()[i], handles[i]


def test_show_legend_off_and_on_keeps_the_hidden_entry_pale_and_the_place(mc):
    """show legend unticked and ticked again: the hidden spectrum's entry
    pale with its line (before: no line, not pale), a dragged legend where
    it was."""
    _click_legend_name(mc, 'sp006')
    leg = _ax(mc).get_legend()
    leg._loc = (0.3, 0.4)                                   # as if dragged there
    mc.legend_checkbox.setChecked(False)
    _pump(0.1)
    mc.legend_checkbox.setChecked(True)
    _pump(0.1)
    text, handle = _entry(mc, 'sp006')
    assert text.get_alpha() == pytest.approx(0.3)
    assert handle.get_visible() and handle.get_alpha() == pytest.approx(0.3)
    text, handle = _entry(mc, 'sp005')
    assert handle.get_visible() and (text.get_alpha() in (None, 1.0))
    assert tuple(_ax(mc).get_legend()._loc) == pytest.approx((0.3, 0.4))


def test_copy_to_clipboard_without_the_hidden_entry(mc, monkeypatch):
    from src.controllers.visualization import plot_clipboard
    seen = {}
    real = plot_clipboard.copy_figure

    def spy(figure):
        seen['texts'] = [t.get_text() for t in _ax(mc).get_legend().get_texts()]
        return real(figure)
    monkeypatch.setattr(plot_clipboard, 'copy_figure', spy)
    _click_legend_name(mc, 'sp006')
    assert mc.copy_plot_to_clipboard() is not None
    assert seen['texts'] and not any(t.endswith('sp006') for t in seen['texts'])
    text, _ = _entry(mc, 'sp006')                           # on the screen: as before
    assert text.get_alpha() == pytest.approx(0.3)
    assert not _line(mc, 'sp006').get_visible()


def test_detect_peaks_leaves_a_hidden_spectrum_out(mc):
    peaks = mc.peak_detection_controller
    peaks.detect_peaks()
    before = len(peaks.peak_detector.peak_indices)
    assert before >= 3
    _click_legend_name(mc, 'sp006')                        # the peaks are marked again
    assert len(peaks.peak_detector.peak_indices) == before - 1
    _click_legend_name(mc, 'sp006')
    assert len(peaks.peak_detector.peak_indices) == before


def test_open_in_new_window_drops_the_hidden_one():
    from matplotlib.figure import Figure
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1], label='a')
    ax.plot([0, 1], [1, 0], label='b')
    ax.legend()

    class _Manager:
        def apply_settings_to_legend(self, ax):
            ax.get_legend().remove()
            ax.legend()
    PlotMouseController.drop_hidden(fig, {'a'}, _Manager())
    assert [t.get_text() for t in ax.get_legend().get_texts()] == ['b']
    assert not ax.get_lines()[0].get_visible()
