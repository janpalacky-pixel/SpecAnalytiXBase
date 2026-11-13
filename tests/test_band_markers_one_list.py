"""Band markers and the former pinned cursors are one list (1.7.0): a click
on the plot with the Cursor ticked - or right-click > Add a band marker
here - adds a band marker (its x as the label, above the plot); it is in
the Band markers window like the others, restyled there, saved in
snapshots; right-click > Copy the values at the band markers reads the
spectra at every X marker, Remove the band marker ... / Remove all."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from matplotlib.backend_bases import MouseEvent
from PyQt5.QtWidgets import QApplication, QMenu, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')

from src.modules.visualization.band_marker_manager import BandMarkerManager
from src.modules.visualization.view_text import RowText


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
    for i in (4, 5, 6):
        lw.item(i).setSelected(True)
    _pump(0.3)
    ctrl.plot_spectra()
    _pump(0.3)
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def _ax(mc):
    return mc.static_canvas.figure.axes[0]


def _click(mc, xdata):
    canvas = mc.static_canvas
    canvas.draw()
    ax = _ax(mc)
    x, y = ax.transData.transform((xdata, sum(ax.get_ylim()) / 2))
    for name in ('button_press_event', 'button_release_event'):
        canvas.callbacks.process(name, MouseEvent(name, canvas, x, y, button=1))
    _pump(0.05)


def _menu(mc, monkeypatch, starts, xdata):
    """Right-click at xdata and choose the item whose text starts with `starts`."""
    chosen = {}

    def exec_(menu, *a, **k):
        texts = [a.text() for a in menu.actions()]
        chosen['texts'] = texts
        for action in menu.actions():
            if action.text().startswith(starts):
                return action
        return None
    monkeypatch.setattr(QMenu, 'exec_', exec_)
    canvas = mc.static_canvas
    canvas.draw()
    ax = _ax(mc)
    x, y = ax.transData.transform((xdata, sum(ax.get_ylim()) / 2))
    mc.show_context_menu(MouseEvent('button_press_event', canvas, x, y, button=3))
    _pump(0.05)
    return chosen['texts']


def test_the_manager_click_style_x_markers_and_the_nearest():
    m = BandMarkerManager()
    m.add(1004.0, label='Phe')
    m.add(0.5, axis='y')
    i = m.add_at_click(1092.37)
    mk = m.markers[i]
    assert mk['label'] == '1092' and mk['orientation'] == 'above' and mk['linestyle'] == ':'
    assert m.x_markers() == [('Phe', 1004.0), ('1092', 1092.37)]        # not the Y marker
    m.update(0, visible=False)
    assert m.x_markers() == [('1092', 1092.37)]
    m.visible = False
    assert m.x_markers() == []


def test_a_click_with_the_cursor_adds_a_band_marker_drawn_at_once(mc):
    mc.cursor_checkbox.setChecked(True)
    ax = _ax(mc)
    limits = ax.get_xlim(), ax.get_ylim()
    _click(mc, 1000.0)
    markers = mc.band_markers()
    assert len(markers.manager) == 1
    assert markers.manager.markers[0]['position'] == pytest.approx(1000.0, abs=5)
    texts = [t for t in ax.texts if t.get_gid() == 'sax_band']
    assert len(texts) == 1 and isinstance(texts[0], RowText)          # above the plot
    assert ax.get_xlim() == pytest.approx(limits[0])                  # the view stays
    assert ax.get_ylim() == pytest.approx(limits[1])
    mc.plot_spectra()                                                 # drawn by every plot
    _pump(0.2)
    assert [t.get_text() for t in _ax(mc).texts if t.get_gid() == 'sax_band'] == \
        [markers.manager.markers[0]['label']]
    mc.cursor_checkbox.setChecked(False)
    _click(mc, 1200.0)                                                # no Cursor: no marker
    assert len(markers.manager) == 1


def test_the_window_lists_them_and_restyles_them(mc, monkeypatch):
    from src.controllers.visualization import band_marker_controller as bmc
    monkeypatch.setattr(bmc, 'run_beside_plot', lambda d: d.show())   # open, not waiting
    mc.cursor_checkbox.setChecked(True)
    dialog = mc.band_markers().show_dialog()
    _pump(0.1)
    _click(mc, 900.0)
    assert dialog._table.rowCount() == 1                              # listed at once
    assert dialog._table.item(0, 1) is not None
    mc.band_markers().manager.update(0, orientation='vertical', label='Phe')
    mc.plot_spectra()
    _pump(0.2)
    texts = [t for t in _ax(mc).texts if t.get_gid() == 'sax_band']
    assert texts[0].get_text() == 'Phe' and not isinstance(texts[0], RowText)
    from src.views.dialogs.visualization_analysis import band_marker_dialog as bmd
    assert 'above' in bmd._ORIENTATIONS and 'Above the plot' in bmd._ORIENTATION_LABELS
    dialog.close()
    mc.cursor_checkbox.setChecked(False)


def test_right_click_add_here_copy_values_remove_one_and_all(mc, monkeypatch):
    texts = _menu(mc, monkeypatch, 'Add a band marker here', 1000.0)
    assert any(t.startswith('Add a band marker here (') for t in texts)
    markers = mc.band_markers()
    assert len(markers.manager) == 1
    markers.manager.add(1500.0, label='PO2')
    mc.plot_spectra()
    _pump(0.2)
    texts = _menu(mc, monkeypatch, 'Copy the values at the band markers', 1200.0)
    assert 'Copy the values at the band markers (2)' in texts
    rows = QApplication.clipboard().text().strip().split('\n')
    assert rows[0].split('\t')[2] == 'PO2 (x = 1500)' and len(rows) == 4    # 3 spectra
    texts = _menu(mc, monkeypatch, 'Remove the band marker', 1500.0)    # the one under the mouse
    assert 'Remove the band marker PO2' in texts
    assert [m['label'] for m in markers.manager.markers] == [markers.manager.markers[0]['label']]
    texts = _menu(mc, monkeypatch, 'Remove all band markers', 1200.0)
    assert len(markers.manager) == 0
    assert not [t for t in _ax(mc).texts if t.get_gid() == 'sax_band']


def test_they_are_saved_in_a_snapshot_with_the_others():
    m = BandMarkerManager()
    m.add(1004.0, label='Phe')
    m.add_at_click(800.0)
    n = BandMarkerManager()
    n.from_dict(m.to_dict())
    assert [(k['label'], k['orientation']) for k in n.markers] == [('Phe', 'above'),
                                                                    ('800', 'above')]


def test_a_new_marker_in_the_window_looks_like_one_added_with_a_click():
    from src.views.dialogs.visualization_analysis.band_marker_dialog import BandMarkerDialog
    m = BandMarkerManager()
    d = BandMarkerDialog(None, band_marker_manager=m, on_change=None)
    d._position_edit.setText('1000')
    d._add_btn.click()
    m.add_at_click(1092.0)
    a, b = m.markers
    for key in ('color', 'linestyle', 'linewidth', 'fontsize', 'orientation'):
        assert a[key] == b[key], key
    assert a['label'] == '1000'
    d.close()


def test_esc_in_the_main_window_ends_zoom_first_then_the_cursor(mc):
    from PyQt5.QtCore import QEvent, Qt
    from PyQt5.QtGui import QKeyEvent
    from src.views import toolbar_mode
    mc.view.activateWindow()
    mc.cursor_checkbox.setChecked(True)
    toolbar = mc.static_canvas.toolbar
    note = toolbar_mode.decorate(toolbar)
    assert note.text().startswith('Cursor on')                   # the note while it is on
    toolbar.zoom()
    _pump(0.05)
    assert note.text().startswith('Zoom on') and 'Esc' in note.text()
    assert toolbar_mode.escape(mc.view)                          # Esc: Zoom off ...
    assert not toolbar_mode.mode_of(toolbar) and mc.cursor_checkbox.isChecked()
    assert note.text().startswith('Cursor on')
    assert toolbar_mode.escape(mc.view)                          # ... then the Cursor
    assert not mc.cursor_checkbox.isChecked() and not mc.plot_cursor_controller.enabled
    assert not toolbar._sax_mode_action.isVisible()
    assert not toolbar_mode.escape(mc.view)                      # nothing left: Esc as before
    # the real key, wherever the focus is in the main window
    mc.cursor_checkbox.setChecked(True)
    toolbar_mode.install(app)
    key = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    QApplication.sendEvent(mc.spectra_list_widget, key)
    if QApplication.activeWindow() is mc.view:                   # offscreen: maybe no active window
        assert not mc.cursor_checkbox.isChecked()
    mc.cursor_checkbox.setChecked(False)


def test_right_click_switches_the_cursor_on_and_off(mc, monkeypatch):
    _menu(mc, monkeypatch, 'Cursor: a click adds a band marker', 1000.0)
    assert mc.cursor_checkbox.isChecked()
    _menu(mc, monkeypatch, 'Cursor: a click adds a band marker', 1000.0)
    assert not mc.cursor_checkbox.isChecked()


def test_esc_in_a_tool_window_ends_its_zoom_and_does_not_close_it():
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
    from matplotlib.figure import Figure
    from PyQt5.QtWidgets import QDialog, QVBoxLayout
    from src.views import toolbar_mode
    dlg = QDialog()
    canvas = FigureCanvasQTAgg(Figure())
    tb = NavigationToolbar2QT(canvas, dlg)
    lay = QVBoxLayout(dlg)
    lay.addWidget(canvas)
    lay.addWidget(tb)
    dlg.show()
    _pump(0.05)
    tb.pan()
    assert toolbar_mode.escape(dlg) and not toolbar_mode.mode_of(tb)
    assert dlg.isVisible()
    assert not toolbar_mode.escape(dlg)                          # no mode: Esc closes it (Qt)
    dlg.close()


def test_esc_closes_a_tool_window_also_when_its_plot_has_the_focus():
    """Manual baseline, SVD, PCA ...: the plot takes the keyboard focus and
    matplotlib's canvas kept Esc - those windows did not close, others did."""
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
    from matplotlib.figure import Figure
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QDialog, QVBoxLayout
    from src.views import toolbar_mode
    toolbar_mode.install(app)
    dlg = QDialog()
    canvas = FigureCanvasQTAgg(Figure())
    canvas.setFocusPolicy(Qt.StrongFocus)
    tb = NavigationToolbar2QT(canvas, dlg)
    lay = QVBoxLayout(dlg)
    lay.addWidget(canvas)
    lay.addWidget(tb)
    dlg.show()
    canvas.setFocus()
    _pump(0.05)
    tb.zoom()
    QTest.keyClick(canvas, Qt.Key_Escape)                          # first: Zoom off
    _pump(0.05)
    assert dlg.isVisible() and not toolbar_mode.mode_of(tb)
    QTest.keyClick(canvas, Qt.Key_Escape)                          # then: the window closes
    _pump(0.05)
    assert not dlg.isVisible()


def test_the_update_button_shows_its_whole_text():
    """Several markers selected: "Update 3 selected" (with its icon) was cut
    off to "Update 3 selecte" - the button kept a fixed minimum of 120 px."""
    from PyQt5.QtWidgets import QApplication
    from src.views import button_icons
    from src.modules.visualization.band_marker_manager import BandMarkerManager
    from src.views.dialogs.visualization_analysis.band_marker_dialog import BandMarkerDialog
    app = QApplication.instance()
    button_icons.install(app)
    mgr = BandMarkerManager()
    for x in (1004, 1092, 1485):
        mgr.add(x)
    d = BandMarkerDialog(None, mgr)
    try:
        d.show()
        for rows in ([0], [0, 1, 2]):
            d._select_rows(rows)
            d._on_selection()
            for _ in range(20):
                app.processEvents()
            b = d._add_btn
            assert b.text().startswith('Update')
            assert b.width() >= b.sizeHint().width(), (b.text(), b.width(), b.sizeHint().width())
    finally:
        d.close()
        d.deleteLater()
