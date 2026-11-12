"""Your own labels on the main plot (right-click: Label the band here, Add
text here, Add an arrow here; Labels on the plot...): drawn on the plot,
dragged with the mouse, saved in snapshots, in Save plot for publication;
pinned cursors labelled with their x value."""
import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox

from src.modules.visualization.plot_notes import PlotNotes, fmt, peak_top

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')


def _pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


def test_notes_qt_free():
    from matplotlib.figure import Figure
    assert fmt(1003.6) == '1004' and fmt(12.345) == '12.35'
    x = np.linspace(900, 1100, 201)
    curves = [('a', x, np.exp(-((x - 1000) / 5) ** 2)), ('b', x, 0.5 + 0 * x)]
    assert peak_top(curves, 1001.0) == pytest.approx(1.0)              # the top nearby
    assert peak_top(curves, 2000.0) is None
    ax = Figure().add_subplot()
    ax.set_xlim(900, 1100)
    ax.set_ylim(0, 2)
    notes = PlotNotes()
    notes.add('band', 1000.0, 1.0)
    notes.add('text', 950.0, 0.2, 'sample A', fontsize=10)
    notes.add('arrow', 1050.0, 0.5, 'shoulder', ax=ax)
    assert [n['text'] for n in notes.notes] == ['1000', 'sample A', 'shoulder']
    arrow = notes.notes[2]
    assert arrow['tx'] < 1050 and arrow['ty'] > 0.5          # the tail up and to the left
    anns = notes.draw(ax)
    assert [a.get_gid() for a in anns] == ['sax_note:0', 'sax_note:1', 'sax_note:2']
    assert anns[1].get_fontsize() == 10 and anns[2].arrow_patch is not None
    assert anns[2].anncoords == 'data'                        # in the plot's units
    before = dict(notes.notes[2])
    notes.move(2, 'tip', ax, before, 10, 0)                    # only the tip moves
    assert notes.notes[2]['x'] > 1050 and notes.notes[2]['tx'] == before['tx']
    before = dict(notes.notes[2])
    notes.move(2, 'shaft', ax, before, 0, 20)                  # the whole arrow moves up
    assert notes.notes[2]['y'] > before['y'] and notes.notes[2]['ty'] > before['ty']
    before = dict(notes.notes[1])
    notes.move(1, 'text', ax, before, 20, 0)                   # a text: its place
    assert notes.notes[1]['x'] > 950 and notes.notes[1]['tx'] is None
    other = PlotNotes()
    other.from_dict(notes.to_dict())
    assert other.notes == notes.notes


def test_notes_in_snapshots(tmp_path):
    from src.controllers.visualization.plot_notes_controller import PlotNotesController
    from src.modules.misc.save_spectra_manager import SaveManager
    from tests.test_snapshot import _FakeMainController, _make_spectra
    main = _FakeMainController(original_spectra=_make_spectra(2))
    main.plot_notes_controller = PlotNotesController(main)
    main.plot_notes_controller.notes.add('band', 1003.0, 2.0, 'Phe')
    target = _FakeMainController(plot_type='Overlay plot')
    target.plot_notes_controller = PlotNotesController(target)
    mgr = SaveManager()
    mgr.save_snapshot(main, str(tmp_path / 's.snapx'))
    mgr.load_snapshot(target, str(tmp_path / 's.snapx'))
    assert [(n['x'], n['text']) for n in target.plot_notes_controller.notes.notes] == [
        (1003.0, 'Phe')]
    empty = _FakeMainController(original_spectra=_make_spectra(2))
    empty.plot_notes_controller = PlotNotesController(empty)
    assert 'plot_notes' not in SaveManager()._build_state(empty)


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths or [DATA]),
                                                 [{} for _ in (file_paths or [DATA])])))
    from src.controllers.core.main_controller import MainController
    ctrl = MainController()
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def test_labels_on_the_main_plot(mc, monkeypatch):
    mc.view.resize(1400, 900)
    mc.view.show()
    mc.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    mc.spectrum_selector.select_all_items()
    _pump(0.5)
    ax = mc.static_canvas.figure.axes[0]
    event = SimpleNamespace(inaxes=ax, xdata=1092.0, ydata=0.0)
    nc = mc.plot_notes_controller
    from src.views.dialogs.misc.rich_text import RichTextDialog
    monkeypatch.setattr(RichTextDialog, 'ask',
                        staticmethod(lambda text='', *a, **k: (text or 'PO2', True)))
    assert nc.add_at('band', event) == 0
    note = nc.notes.notes[0]
    assert note['text'] == '1092' and note['y'] > 1000              # above the highest peak
    nc.add_at('arrow', event, text='here')
    texts = [t for t in ax.texts if str(t.get_gid()).startswith('sax_note')]
    assert [t.get_text() for t in texts] == ['1092', 'here']
    mc.plot_spectra()                                                # a new plot: drawn again
    _pump()
    ax = mc.static_canvas.figure.axes[0]
    assert len([t for t in ax.texts if str(t.get_gid()).startswith('sax_note')]) == 2
    dlg = nc.show_dialog()
    assert dlg.table.rowCount() == 2
    dlg.table.cellWidget(0, 3).setValue(12)                          # size
    assert nc.notes.notes[0]['fontsize'] == 12
    dlg.table.cellWidget(1, 8).click()                               # delete the arrow
    assert len(nc.notes) == 1 and dlg.table.rowCount() == 1
    from src.modules.visualization import publication_figure as pf
    _, boxes = pf.render(mc.static_canvas.figure, 8.5, 6.5, 100, font_pt=8)
    assert 'note:0:0' in [b[0] for b in boxes]                       # draggable in the picture
    # a click with the Cursor on adds a band marker labelled with its x value
    mc.cursor_checkbox.setChecked(True)
    mc.plot_cursor_controller.pin(800.0)
    pinned = [t.get_text() for t in mc.static_canvas.figure.axes[0].texts
              if t.get_gid() == 'sax_band']
    assert pinned == ['800']
    mc.band_markers().remove_all()
    dlg.close()


def _plot_with_labels(mc):
    mc.view.resize(1400, 900)
    mc.view.show()
    mc.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    mc.spectrum_selector.select_all_items()
    _pump(0.5)
    ax = mc.static_canvas.figure.axes[0]
    nc = mc.plot_notes_controller
    nc.add_at('text', SimpleNamespace(inaxes=ax, xdata=1000.0, ydata=150000.0), text='note')
    nc.add_at('arrow', SimpleNamespace(inaxes=ax, xdata=1500.0, ydata=100000.0), text='')
    mc.static_canvas.draw()
    return ax, nc


def _mouse(canvas, kind, x, y, dblclick=False):
    from matplotlib.backend_bases import MouseEvent
    canvas.callbacks.process(kind, MouseEvent(kind, canvas, x, y, button=1,
                                              dblclick=dblclick))


def test_choose_drag_edit_and_delete_on_the_main_plot(mc, monkeypatch):
    ax, nc = _plot_with_labels(mc)
    canvas = mc.static_canvas
    # an arrow without text: its tip dragged - the tip moves, the tail stays
    n = nc.notes.notes[1]
    tip = ax.transData.transform((n['x'], n['y']))
    tail = ax.transData.transform((n['tx'], n['ty']))
    _mouse(canvas, 'button_press_event', *tip)
    assert nc.selected == 1
    _mouse(canvas, 'motion_notify_event', tip[0] + 40, tip[1] - 20)
    _mouse(canvas, 'button_release_event', tip[0] + 40, tip[1] - 20)
    n = nc.notes.notes[1]
    new_tip = ax.transData.transform((n['x'], n['y']))
    assert new_tip[0] == pytest.approx(tip[0] + 40, abs=1)
    new_tail = ax.transData.transform((n['tx'], n['ty']))
    assert new_tail == pytest.approx(tail, abs=1)
    # chosen: its two ends as small squares; the tail end dragged - it turns and
    # stretches, the tip stays
    handles = [l for l in ax.get_lines() if l.get_gid() == 'sax_note_handles']
    assert len(handles) == 1
    _mouse(canvas, 'button_press_event', *new_tail)
    _mouse(canvas, 'motion_notify_event', new_tail[0] - 25, new_tail[1] + 35)
    _mouse(canvas, 'button_release_event', new_tail[0] - 25, new_tail[1] + 35)
    n = nc.notes.notes[1]
    assert ax.transData.transform((n['x'], n['y'])) == pytest.approx(new_tip, abs=1)
    stretched = ax.transData.transform((n['tx'], n['ty']))
    assert stretched == pytest.approx((new_tail[0] - 25, new_tail[1] + 35), abs=1)
    new_tail = stretched
    # the arrow's middle dragged: the whole arrow moves
    mid = (new_tip + new_tail) / 2
    _mouse(canvas, 'button_press_event', *mid)
    _mouse(canvas, 'motion_notify_event', mid[0] + 30, mid[1])
    _mouse(canvas, 'button_release_event', mid[0] + 30, mid[1])
    n2 = nc.notes.notes[1]
    assert ax.transData.transform((n2['x'], n2['y']))[0] == pytest.approx(new_tip[0] + 30, abs=1)
    assert ax.transData.transform((n2['tx'], n2['ty']))[0] == pytest.approx(new_tail[0] + 30,
                                                                             abs=1)
    # a larger window: the labels stay at their places in the plot (the plot's units)
    x_before = n2['x']
    mc.view.resize(1800, 1000)
    _pump()
    assert nc.notes.notes[1]['x'] == x_before
    # a click on a text: chosen (a dashed frame); with the Cursor on no cursor is pinned
    mc.cursor_checkbox.setChecked(True)
    text = [t for t in ax.texts if t.get_gid() == 'sax_note:0'][0]
    box = text.get_window_extent()
    _mouse(canvas, 'button_press_event', box.x0 + box.width / 2, box.y0 + box.height / 2)
    _mouse(canvas, 'button_release_event', box.x0 + box.width / 2, box.y0 + box.height / 2)
    assert nc.selected == 0 and mc.plot_cursor_controller.pinned == []
    chosen = [t for t in ax.texts if t.get_gid() == 'sax_note:0'][0]
    assert chosen.get_bbox_patch() is not None
    # a double-click: the small window (OK changes, Delete deletes)
    from src.views.dialogs.visualization.plot_notes_dialog import NoteEditDialog
    answers = [1, NoteEditDialog.DELETE]

    def run(dlg):
        dlg.text_edit.setText('changed')
        return answers.pop(0)
    monkeypatch.setattr(NoteEditDialog, 'exec_', run)
    nc.edit(0)
    assert nc.notes.notes[0]['text'] == 'changed'
    nc.edit(0)
    assert len(nc.notes) == 1
    # the Delete key: the chosen label (with the plot focused), else the spectra
    nc.select(0)
    deleted = []
    monkeypatch.setattr(mc.spectrum_selector, 'delete_selected_spectra',
                        lambda: deleted.append(1))
    monkeypatch.setattr(QApplication, 'focusWidget', staticmethod(lambda: canvas))
    mc._delete_key()
    assert len(nc.notes) == 0 and deleted == []
    mc._delete_key()
    assert deleted == [1]


def test_your_labels_in_save_plot_for_publication(mc, monkeypatch):
    ax, nc = _plot_with_labels(mc)
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    dlg = PublicationDialog(mc.static_canvas.figure, notes=nc)
    assert 'Labels' in [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert dlg.notes_table.rowCount() == 2 and nc.selected is None
    dlg._update_preview()
    keys = [b[0] for b in dlg.preview.boxes]
    assert 'note:0:0' in keys and 'note:0:1' in keys          # also the arrow without text
    before = dict(nc.notes.notes[0])
    dlg.preview.text_moved.emit('note:0:0', 30.0, 20.0)              # right and down
    assert nc.notes.notes[0]['x'] > before['x']                      # the main plot too
    assert nc.notes.notes[0]['y'] < before['y']
    dlg._record()
    dlg.preview.clicked.emit('note:0:1')
    assert dlg.preview.selected == 'note:0:1'
    dlg.preview.delete_pressed.emit()
    assert len(nc.notes) == 1 and dlg.notes_table.rowCount() == 1
    dlg._record()
    assert dlg.undo() and len(nc.notes) == 2                     # Undo brings it back
    assert dlg.add_note('text') == 2 and nc.notes.notes[2]['text'] == 'text'
    nc.notes.update(0, fontsize=12, color='#ff0000', rotation=30, bold=True)
    dlg.restore_defaults()                                        # the labels' look too
    n = nc.notes.notes[0]
    assert (n['fontsize'], n['color'], n['rotation'], n['bold']) == (8.0, '#000000', 0.0, False)
    assert n['text'] == 'note'                                    # the text stays
    dlg.close()


def test_the_colour_window_is_not_coloured_by_its_button(monkeypatch):
    from PyQt5.QtWidgets import QColorDialog, QDialog, QWidget
    from src.views.dialogs.visualization.publication_dialog import ColourButton
    holder = QWidget()
    button = ColourButton('#00aaff')
    button.setParent(holder)
    seen = []

    def run(dlg):
        from PyQt5.QtCore import QEvent, QPoint, Qt
        from PyQt5.QtGui import QMouseEvent
        seen.append(dlg.parent())
        dlg.setCurrentColor(QColor('#000000'))
        picker = [w for w in dlg.findChildren(QWidget)
                  if w.metaObject().className() == 'QColorPicker'][0]
        pos = QPoint(picker.width() // 2, picker.height() // 4)      # a click in the field
        for t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            app.sendEvent(picker, QMouseEvent(t, pos, Qt.LeftButton, Qt.LeftButton,
                                              Qt.NoModifier))
        return QDialog.Accepted
    from PyQt5.QtGui import QColor
    monkeypatch.setattr(QColorDialog, 'exec_', run)
    button.click()
    assert seen == [holder]
    assert QColor(button.colour()).value() == 255              # not left black


def test_arrow_heads_and_ends_in_the_preview(mc):
    ax, nc = _plot_with_labels(mc)
    nc.notes.update(1, head='text')
    nc.redraw()
    arrow = [t for t in mc.static_canvas.figure.axes[0].texts
             if t.get_gid() == 'sax_note:1'][0]
    assert arrow.arrow_patch.get_arrowstyle().__class__.__name__ == 'CurveA'   # '<-'
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    dlg = PublicationDialog(mc.static_canvas.figure, notes=nc)
    dlg._update_preview()
    box = [b for b in dlg.preview.boxes if b[0] == 'note:0:1'][0]
    assert 'tip' in box[2] and 'tail' in box[2]
    before = dict(nc.notes.notes[1])
    dlg.preview.text_moved.emit('note:0:1|tip', 40.0, 0.0)          # only the tip moves
    n = nc.notes.notes[1]
    assert n['x'] > before['x'] and (n['tx'], n['ty']) == (before['tx'], before['ty'])
    before = dict(n)
    dlg._update_preview()
    dlg.preview.text_moved.emit('note:0:1|tail', 0.0, -30.0)        # the tail up: it turns
    n = nc.notes.notes[1]
    assert n['ty'] > before['ty'] and (n['x'], n['y']) == (before['x'], before['y'])
    dlg.preview.selected = 'note:0:1'
    dlg.preview.repaint()                                            # its two ends drawn
    dlg.close()


def test_a_dragged_arrow_follows_the_mouse_in_the_preview(mc):
    """While an arrow's end is dragged in the preview it is drawn at once
    where the mouse is (the picture is made again only at the end)."""
    from PyQt5.QtCore import QPoint, QPointF, Qt
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtCore import QEvent
    ax, nc = _plot_with_labels(mc)
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    dlg = PublicationDialog(mc.static_canvas.figure, notes=nc)
    dlg._update_preview()
    p = dlg.preview
    extra = [b for b in p.boxes if b[0] == 'note:0:1'][0][2]
    tip = QPoint(round(extra['tip'][0] / p.ratio), round(extra['tip'][1] / p.ratio))
    tail = QPointF(extra['tail'][0] / p.ratio, extra['tail'][1] / p.ratio)

    def mouse(kind, pos, button=Qt.LeftButton):
        return QMouseEvent(kind, QPointF(pos), button, button, Qt.NoModifier)
    p.mousePressEvent(mouse(QEvent.MouseButtonPress, tip))
    assert p._drag is not None and p._drag[0] == 'note:0:1|tip'
    p.mouseMoveEvent(mouse(QEvent.MouseMove, tip + QPoint(25, 10), Qt.NoButton))
    now_tip, now_tail, _box = p.dragged_arrow()
    start = QPointF(extra['tip'][0] / p.ratio, extra['tip'][1] / p.ratio)
    assert (now_tip.x() - start.x(), now_tip.y() - start.y()) == (25, 10)
    assert now_tail == tail                                  # only the tip moves
    p.repaint()                                              # drawn without an error
    before = dict(nc.notes.notes[1])
    p.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, tip + QPoint(25, 10)))
    assert p.dragged_arrow() is None and nc.notes.notes[1]['x'] > before['x']
    dlg.close()
