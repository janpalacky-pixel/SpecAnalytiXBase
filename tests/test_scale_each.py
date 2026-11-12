"""'scale each' in Basic plot options: every spectrum drawn from 0 (its
lowest point in the view) to 1 (its highest) - only the drawing; the lines
keep their data, the Cursor lists the real values, Detect Peaks' dots stay
on the lines; zoomed in, each spectrum is fitted to the view; Overlay,
Waterfall, Grid with a linear Y-scale; right-click; saved in snapshots."""
import os
import pickle
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')


def _pump(seconds=0.2):
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
    ctrl.spectrum_selector.select_all_items()
    _pump()
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.close()
    ctrl.view.deleteLater()


def _drawn(line):
    """The line's points where they are drawn, in the axes' y units."""
    ax = line.axes
    xy = np.column_stack([line.get_xdata(), line.get_ydata()])
    return ax.transData.inverted().transform(line.get_transform().transform(xy))


def _spectra_lines(ax):
    return [l for l in ax.get_lines() if not l.get_gid() and len(l.get_xdata()) > 2]


def test_the_checkbox_and_the_overlay_plot(mc):
    box = mc.view.scale_each_checkBox
    assert box.text() == 'scale each' and not box.isChecked() and box.isEnabled()
    assert box.parent() is mc.view.groupBox_basic_plot_options
    before = [l.get_ydata().copy() for l in _spectra_lines(mc.static_canvas.figure.axes[0])]
    box.setChecked(True)
    _pump()
    fig = mc.static_canvas.figure
    ax = fig.axes[0]
    lines = _spectra_lines(ax)
    assert len(lines) == 11
    mc.static_canvas.draw()
    for line, y in zip(lines, before):
        assert np.array_equal(line.get_ydata(), y)          # the data unchanged
        d = _drawn(line)[:, 1]
        assert np.nanmin(d) == pytest.approx(0, abs=1e-9)
        assert np.nanmax(d) == pytest.approx(1, abs=1e-9)
    assert ax.get_ylim() == pytest.approx((-0.05, 1.05))
    assert 'scaled 0' in ax.get_ylabel()
    note = mc.static_toolbar._sax_mode_note
    assert 'scale each' in note.text() and note.isVisible()
    # off: the spectra with their own values again
    box.setChecked(False)
    _pump()
    ax = mc.static_canvas.figure.axes[0]
    assert ax.get_ylim()[1] > 1000
    assert 'scale each' not in mc.static_toolbar._sax_mode_note.text()


def test_zoomed_in_each_spectrum_fits_the_view(mc):
    mc.view.scale_each_checkBox.setChecked(True)
    _pump()
    ax = mc.static_canvas.figure.axes[0]
    ax.set_xlim(1450, 1520)                                 # a band
    ax.set_ylim(0.2, 0.4)                                   # e.g. a Zoom rectangle
    _pump(0.3)
    assert ax.get_ylim() == pytest.approx((-0.05, 1.05))    # y follows x
    mc.static_canvas.draw()
    for line in _spectra_lines(ax):
        x = np.asarray(line.get_xdata(), float)
        d = _drawn(line)[:, 1]
        inside = (x >= 1450) & (x <= 1520)
        assert d[inside].min() == pytest.approx(0, abs=1e-9)
        assert d[inside].max() == pytest.approx(1, abs=1e-9)


def test_cursor_lists_the_real_values_and_dots_sit_on_the_lines(mc):
    mc.view.scale_each_checkBox.setChecked(True)
    _pump()
    mc.cursor_checkbox.setChecked(True)
    cc = mc.plot_cursor_controller
    ax = mc.static_canvas.figure.axes[0]
    text, shown = cc.readout_text(ax, 1000.0, None)
    by_label = {lbl: (xx, yy) for lbl, xx, yy in cc.all_curves()}
    for (lbl, v), at in zip(shown, cc.shown_at):
        xx, yy = by_label[lbl]
        assert v == pytest.approx(np.interp(1000.0, xx, yy))   # real
        assert -0.01 <= at <= 1.01                               # drawn in 0..1


def test_detect_peaks_stays_on_the_lines(mc):
    mc.view.scale_each_checkBox.setChecked(True)
    _pump()
    canvas = mc.static_canvas
    from src.modules.data_analysis.peak_detection_manager import PeakDetector
    from src.modules.data_analysis import peak_list as pl
    detector = PeakDetector()
    for labels in ('all', 'band'):
        detector.detect_peaks(canvas, pl.DEFAULTS['threshold'], 8, 0, 0, 'fixed', 'x', True,
                              pl.DEFAULTS['prominence'], pl.DEFAULTS['distance'],
                              pl.DEFAULTS['mode'], labels=labels)
        ax = canvas.figure.axes[0]
        assert detector.peak_lines and detector.peak_texts
        for dot in detector.peak_lines:
            assert dot.get_transform() is not ax.transData
            assert -0.01 <= _drawn(dot)[0, 1] <= 1.01          # on its scaled line
        for text in detector.peak_texts:
            x, y = text.get_position()
            py = ax.transData.inverted().transform(text.get_transform().transform((x, y)))[1]
            assert -0.01 <= py <= 1.01


def test_waterfall_and_grid(mc):
    mc.view.scale_each_checkBox.setChecked(True)
    mc.view.comboBox_plot_type_choice.setCurrentText("Waterfall plot")
    _pump()
    ax = mc.static_canvas.figure.axes[0]
    lines = _spectra_lines(ax)
    mc.static_canvas.draw()
    bottoms = [np.nanmin(_drawn(l)[:, 1]) for l in lines]
    assert bottoms[0] == pytest.approx(0, abs=1e-9)
    assert np.all(np.diff(bottoms) > 0)                     # still stacked
    assert ax.get_ylim()[1] == pytest.approx(bottoms[-1] + 1.05)
    mc.view.comboBox_plot_type_choice.setCurrentText("Grid plot")
    _pump()
    for ax in mc.static_canvas.figure.axes:
        if ax.get_visible():
            assert ax.get_ylim() == pytest.approx((-0.05, 1.05))


@pytest.mark.parametrize('plot_type', ["Mean ± SD", "Difference", "Heatmap"])
def test_greyed_out_in_other_plot_types(mc, plot_type):
    box = mc.view.scale_each_checkBox
    box.setChecked(True)
    mc.view.comboBox_plot_type_choice.setCurrentText(plot_type)
    _pump()
    assert not box.isEnabled() and box.isChecked()          # kept for later
    assert not getattr(mc.static_canvas.figure, '_sax_scale_each', False)
    mc.view.comboBox_plot_type_choice.setCurrentText("Overlay plot")
    _pump()
    assert box.isEnabled() and mc.static_canvas.figure._sax_scale_each


def test_greyed_out_with_a_log_y_scale(mc):
    box = mc.view.scale_each_checkBox
    mc.view.y_scale_comboBox.setCurrentText("log")
    _pump()
    assert not box.isEnabled()
    mc.view.y_scale_comboBox.setCurrentText("linear")
    _pump()
    assert box.isEnabled()


def test_labels_are_kept_but_not_drawn_nor_added(mc):
    notes = mc.plot_notes_controller
    notes.notes.add('text', 1000.0, 50000.0, 'mine')
    notes.redraw()
    assert notes._artists
    mc.view.scale_each_checkBox.setChecked(True)
    _pump()
    assert not notes._artists and len(notes.notes) == 1
    assert notes.add_in_middle('text', 'x') is None
    mc.view.scale_each_checkBox.setChecked(False)
    _pump()
    assert notes._artists


def test_a_pickled_copy_is_scaled_too(mc):
    """Save plot for publication works on a pickled copy of the figure."""
    mc.view.scale_each_checkBox.setChecked(True)
    _pump()
    copy = pickle.loads(pickle.dumps(mc.static_canvas.figure))
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    FigureCanvasAgg(copy).draw()
    ax = copy.axes[0]
    for line in _spectra_lines(ax):
        d = _drawn(line)[:, 1]
        assert np.nanmax(d) == pytest.approx(1, abs=1e-9)


def test_open_in_new_window_is_scaled(mc):
    import matplotlib.pyplot as plt
    mc.view.scale_each_checkBox.setChecked(True)
    _pump()
    before = set(plt.get_fignums())
    mc.open_external_figure()
    new = [n for n in plt.get_fignums() if n not in before]
    try:
        assert new
        fig = plt.figure(new[0]).canvas.figure
        assert getattr(fig, '_sax_scale_each', False)
    finally:
        for n in new:
            plt.close(n)


def test_saved_in_snapshots(mc):
    mc.view.scale_each_checkBox.setChecked(True)
    state = mc.save_controller.save_manager._build_state(mc) if hasattr(
        mc, 'save_controller') else None
    if state is None:
        pytest.skip("no save manager")
    assert state['plot_settings']['scale_each'] is True
    mc.view.scale_each_checkBox.setChecked(False)
    mc.save_controller.save_manager._restore_ui_state(mc, state)
    assert mc.view.scale_each_checkBox.isChecked()
    state['plot_settings'].pop('scale_each')                # an older snapshot
    mc.save_controller.save_manager._restore_ui_state(mc, state)
    assert not mc.view.scale_each_checkBox.isChecked()


# ------------------------------------------------- 1 at a band marker
def _menu(mc, x, monkeypatch, choose=None):
    from PyQt5.QtWidgets import QMenu
    from matplotlib.backend_bases import MouseEvent
    texts = []

    def fake_exec(menu, *a, **k):
        chosen = None
        for act in menu.actions():
            texts.append((act.text(), act.isChecked()))
            if choose and act.text().startswith(choose):
                chosen = act
        return chosen
    monkeypatch.setattr(QMenu, 'exec_', fake_exec)
    canvas = mc.static_canvas
    ax = canvas.figure.axes[0]
    canvas.draw()
    from matplotlib.backend_bases import MouseEvent
    px, py = ax.transData.transform((x, np.mean(ax.get_ylim())))
    mc.handle_mouse_click(MouseEvent('button_press_event', canvas, px, py, button=3))
    _pump()
    return dict(texts)


def test_one_at_a_band_marker(mc, monkeypatch):
    markers = mc.band_markers()
    markers.add_at(1092.0)
    texts = _menu(mc, 1092.0, monkeypatch, choose="Scale each spectrum to 1 at the band marker")
    assert "Scale each spectrum to 1 at the band marker 1092 (only the drawing)" in texts
    assert mc.view.scale_each_checkBox.isChecked() and mc.scale_each_at == 1092.0
    ax = mc.static_canvas.figure.axes[0]
    mc.static_canvas.draw()
    tops = []
    for line in _spectra_lines(ax):
        d = _drawn(line)
        x = d[:, 0]
        order = np.argsort(x)
        assert np.interp(1092.0, x[order], d[order, 1]) == pytest.approx(1.0, abs=1e-6)
        assert np.nanmin(d[:, 1]) == pytest.approx(0.0, abs=1e-9)
        tops.append(np.nanmax(d[:, 1]))
    lo, hi = ax.get_ylim()
    assert hi >= max(tops) and max(tops) > 1.0           # other bands above 1 are shown
    assert '1 at 1092' in ax.get_ylabel()
    assert '1 at 1092' in mc.static_toolbar._sax_mode_note.text()
    # the menu shows which: at the marker ticked, 0-1 not
    texts = _menu(mc, 1092.0, monkeypatch)
    assert texts["Scale each spectrum to 1 at the band marker 1092 (only the drawing)"] is True
    assert texts["Scale each spectrum 0–1 (only the drawing)"] is False
    # 0-1 chosen: each from 0 to 1 again
    _menu(mc, 1092.0, monkeypatch, choose="Scale each spectrum 0–1")
    assert mc.view.scale_each_checkBox.isChecked() and mc.scale_each_at is None
    # 1 at the marker again, then the marker removed: 0-1 again
    mc.set_scale_each_at(1092.0)
    _pump()
    markers.remove(0)
    _pump()
    assert mc.scale_each_at is None
    assert mc.static_canvas.figure.axes[0].get_ylim() == pytest.approx((-0.05, 1.05))


def test_one_at_a_marker_saved_in_snapshots(mc):
    mc.band_markers().add_at(1092.0)
    mc.set_scale_each_at(1092.0)
    _pump()
    manager = mc.save_controller.save_manager
    state = manager._build_state(mc)
    assert state['plot_settings']['scale_each_at'] == 1092.0
    mc.view.scale_each_checkBox.setChecked(False)
    assert mc.scale_each_at is None
    manager._restore_ui_state(mc, state)
    assert mc.scale_each_at == 1092.0 and mc.view.scale_each_checkBox.isChecked()
