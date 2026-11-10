"""Your own order of the spectra in the list: drag the selected spectra to
their place, Alt+Up / Alt+Down, right-click › Order (Move to top / up /
down / to bottom, Sort by name). The order counts everywhere (the plot, tool
windows), new spectra go to the end, it is kept in snapshots."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.utils import spectra_order as so

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')


def _pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


def test_the_order_without_qt():
    v = list('ABCDE')
    assert so.move_to(v, ['B', 'D'], 0) == list('BDACE')           # dragged to the top
    assert so.move_to(v, ['B', 'D'], 5) == list('ACEBD')           # to the end
    assert so.move_to(v, ['A'], 3) == list('BCADE')                # before D
    assert so.step(v, ['C', 'D']) == list('ACDBE')                 # a block one up
    assert so.step(v, ['A', 'C']) == list('ACBDE')                 # A stays at the top
    assert so.step(v, ['B', 'C'], up=False) == list('ADBCE')
    assert so.step(v, ['E'], up=False) == v                        # nothing below the end
    names = {'a': 'n3', 'b': 'n1', 'c': 'n2', 'x': 'z1', 'y': 'a0'}
    spectra = [{'k': k} for k in 'abcxy']
    key, by_name = (lambda s: s['k']), (lambda s: names[s['k']])
    ordered, custom = so.apply(spectra, ['c', 'a', 'b'], False, key, by_name)
    assert [s['k'] for s in ordered] == list('cabyx')               # new ones at the end
    assert custom == list('cabyx')
    ordered, custom = so.apply(spectra, ['c', 'a', 'b'], True, key, by_name)
    assert [s['k'] for s in ordered] == list('bacyx')               # upside down, new at the end
    assert [s['k'] for s in so.apply(spectra, custom, True, key, by_name)[0]] == list('bacyx')
    # a deleted spectrum (q) keeps its place for an Undo
    assert so.from_visible(list('bac'), False, list('cqab')) == list('bacq')
    assert so.from_visible(list('bac'), True, list('cqab')) == list('cqab')


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
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def _labels(mc):
    lw = mc.spectra_list_widget
    return [lw.item(i).text().split(' : ')[-1] for i in range(lw.count())]


def _select(mc, *names):
    lw = mc.spectra_list_widget
    lw.clearSelection()
    for i in range(lw.count()):
        if lw.item(i).text().split(' : ')[-1] in names:
            lw.item(i).setSelected(True)
    _pump(0.1)


def test_move_the_selected_spectra(mc):
    start = _labels(mc)
    assert start[:3] == ['sp001', 'sp002', 'sp003'] and mc.custom_order is None
    _select(mc, 'sp003', 'sp005')
    assert mc.move_selected_spectra('top')
    assert _labels(mc)[:4] == ['sp003', 'sp005', 'sp001', 'sp002']
    assert [s['label'].split(' : ')[-1] for s in mc.original_spectra][:2] == ['sp003', 'sp005']
    assert [s['label'].split(' : ')[-1] for s in mc.selected_spectra] == ['sp003', 'sp005']
    # what every tool window under Analysis gets: in your order
    assert [s['label'].split(' : ')[-1] for s in mc.spectrum_selector.get_selected_spectra()] \
        == ['sp003', 'sp005']
    mc.move_selected_spectra('down')                               # Alt+Down
    assert _labels(mc)[:4] == ['sp001', 'sp003', 'sp005', 'sp002']
    mc.move_selected_spectra('bottom')
    assert _labels(mc)[-2:] == ['sp003', 'sp005']
    mc.spectra_list_widget.dropped_at.emit(1)                      # dragged before the 2nd
    _pump(0.1)
    assert _labels(mc)[:4] == ['sp001', 'sp003', 'sp005', 'sp002']
    # the plot follows: the legend in the list's order
    _pump(0.3)
    legend = mc.static_canvas.figure.axes[0].get_legend()
    assert [t.get_text().split(' : ')[-1] for t in legend.get_texts()] == ['sp003', 'sp005']
    # reverse sorting: your order upside down; unticked: back again
    mine = _labels(mc)
    mc.checkBox_reverse_order.setChecked(True)
    _pump(0.1)
    assert _labels(mc) == list(reversed(mine))
    mc.checkBox_reverse_order.setChecked(False)
    _pump(0.1)
    assert _labels(mc) == mine
    # new spectra (copies) go to the end, not to their place by name
    _select(mc, 'sp001')
    mc.copy_spectra_to_clipboard()
    mc.paste_spectra_from_clipboard()
    _pump(0.1)
    assert _labels(mc)[:-1] == mine and _labels(mc)[-1] == 'sp001_copy'
    # Sort by name: back to the names' order
    assert mc.sort_spectra_by_name()
    assert mc.sort_mode == {'by': 'name'} and _labels(mc)[:3] == ['sp001', 'sp001_copy', 'sp002']
    assert 'name' in mc.sort_button.text()
    # your own order is kept: Sort ▾ › Your own order brings it back
    assert mc.set_sort_mode({'by': 'own'})
    assert _labels(mc)[:-1] == mine and 'own order' in mc.sort_button.text()


def test_keys_menu_and_mouse(mc):
    from PyQt5.QtGui import QKeySequence
    from PyQt5.QtWidgets import QShortcut
    keys = {s.key().toString() for s in mc.view.findChildren(QShortcut)}
    assert {'Alt+Up', 'Alt+Down'} <= keys
    _select(mc, 'sp004')
    shortcut = [s for s in mc.view.findChildren(QShortcut) if s.key() == QKeySequence('Alt+Up')][0]
    shortcut.activated.emit()
    assert _labels(mc)[:4] == ['sp001', 'sp002', 'sp004', 'sp003']
    lw = mc.spectra_list_widget
    # where a move puts them: above / below the middle of a row
    r1 = lw.visualItemRect(lw.item(1))
    assert lw.drop_row(r1.center() + QPoint(0, 3)) == 2
    assert lw.drop_row(r1.center() - QPoint(0, 3)) == 1
    assert lw.drop_row(QPoint(5, lw.viewport().height() - 2)) == lw.count()


def _mouse(lw, kind, pos, buttons=Qt.LeftButton, button=Qt.LeftButton):
    event = QMouseEvent(kind, QPointF(pos), button, buttons, Qt.NoModifier)
    {QEvent.MouseButtonPress: lw.mousePressEvent, QEvent.MouseMove: lw.mouseMoveEvent,
     QEvent.MouseButtonRelease: lw.mouseReleaseEvent}[kind](event)


def _handle(lw, row):
    """The move handle (six dots) at the left of a row."""
    return QPoint(8, lw.visualItemRect(lw.item(row)).center().y())


def test_drag_with_the_mouse(mc):
    """A real drag of the handle: press on a selected spectrum's handle,
    move, let go - the selected spectra are there, none disappears; a blue
    line while moving; Esc cancels. Elsewhere in a row the mouse selects as
    before - also a drag that starts on a selected spectrum."""
    lw = mc.spectra_list_widget
    n = lw.count()
    _select(mc, 'sp002', 'sp003')
    start = _handle(lw, 1)                                         # sp002's handle
    end = lw.visualItemRect(lw.item(6)).center() + QPoint(0, 3)    # below the middle of sp007
    assert lw.on_handle(start) and not lw.on_handle(lw.visualItemRect(lw.item(1)).center())
    lw.repaint()                                                   # the handles drawn
    _mouse(lw, QEvent.MouseButtonPress, start)
    _mouse(lw, QEvent.MouseMove, start + QPoint(0, 12))
    assert lw.is_moving()
    _mouse(lw, QEvent.MouseMove, end)
    assert lw._line.isVisible() and lw._row == 7                   # the line: after sp007
    _mouse(lw, QEvent.MouseButtonRelease, end, buttons=Qt.NoButton)
    _pump(0.2)
    assert not lw.is_moving() and not lw._line.isVisible()
    assert lw.count() == n                                         # nothing disappears
    assert _labels(mc)[:7] == ['sp001', 'sp004', 'sp005', 'sp006', 'sp007', 'sp002', 'sp003']
    assert sorted(i.text().split(' : ')[-1] for i in lw.selectedItems()) == ['sp002', 'sp003']
    # Esc while moving: nothing moves
    before = _labels(mc)
    _mouse(lw, QEvent.MouseButtonPress, _handle(lw, 5))
    _mouse(lw, QEvent.MouseMove, lw.visualItemRect(lw.item(0)).center())
    from PyQt5.QtGui import QKeyEvent
    lw.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    _mouse(lw, QEvent.MouseButtonRelease, lw.visualItemRect(lw.item(0)).center(),
           buttons=Qt.NoButton)
    _pump(0.2)
    assert _labels(mc) == before and not lw._line.isVisible()
    # the handle of a spectrum that is not selected: only it moves
    _select(mc, 'sp002', 'sp003')
    _mouse(lw, QEvent.MouseButtonPress, _handle(lw, 0))            # sp001, not selected
    _mouse(lw, QEvent.MouseMove, lw.visualItemRect(lw.item(3)).center() + QPoint(0, 3))
    _mouse(lw, QEvent.MouseButtonRelease, lw.visualItemRect(lw.item(3)).center() + QPoint(0, 3),
           buttons=Qt.NoButton)
    _pump(0.2)
    assert _labels(mc)[:4] == ['sp004', 'sp005', 'sp006', 'sp001']
    assert [i.text().split(' : ')[-1] for i in lw.selectedItems()] == ['sp001']
    before = _labels(mc)
    # a click on a selected spectrum's name: only it stays selected (as before)
    _select(mc, 'sp002', 'sp003')
    pos = lw.visualItemRect(lw.item(before.index('sp002'))).center()
    _mouse(lw, QEvent.MouseButtonPress, pos)
    _mouse(lw, QEvent.MouseButtonRelease, pos, buttons=Qt.NoButton)
    _pump(0.1)
    assert [i.text().split(' : ')[-1] for i in lw.selectedItems()] == ['sp002']
    # dragging over the names selects - also when it starts on a selected one
    a = lw.visualItemRect(lw.item(before.index('sp002'))).center()
    b = lw.visualItemRect(lw.item(before.index('sp002') + 2)).center()
    _mouse(lw, QEvent.MouseButtonPress, a)
    _mouse(lw, QEvent.MouseMove, b)
    _mouse(lw, QEvent.MouseButtonRelease, b, buttons=Qt.NoButton)
    _pump(0.1)
    assert not lw.is_moving() and _labels(mc) == before
    assert len(lw.selectedItems()) == 3


def test_the_order_in_snapshots(mc, tmp_path):
    from src.modules.misc.save_spectra_manager import SaveManager
    _select(mc, 'sp007')
    mc.move_selected_spectra('top')
    mine = _labels(mc)
    path = str(tmp_path / 'order.snapx')
    SaveManager().save_snapshot(mc, path)
    mc.import_controller._run_import(clear_first=True, file_paths=[DATA])   # a new import
    _pump()
    assert mc.custom_order is None and _labels(mc)[0] == 'sp001'
    SaveManager().load_snapshot(mc, path)
    _pump()
    assert mc.custom_order is not None
    from src.controllers.misc.spectrum_selector_controller import SpectrumSelector  # noqa
    order = [s['label'].split(' : ')[-1] for s in mc.original_spectra]
    assert order == mine
    mc.update_spectra_order_and_redraw_plot()                      # sorted again: still yours
    assert _labels(mc) == mine


def test_operations_delete_and_undo_keep_your_order(mc):
    _select(mc, 'sp009')
    mc.move_selected_spectra('top')
    mine = _labels(mc)
    assert mine[0] == 'sp009'
    _select(mc, 'sp003')
    mc.spectrum_selector.delete_selected_spectra()                 # asks: Yes (patched)
    _pump(0.2)
    assert _labels(mc) == [n for n in mine if n != 'sp003']
    mc.operations_controller.undo_operation()                      # back: at its place again
    _pump(0.2)
    assert _labels(mc) == mine


@pytest.mark.parametrize('op', ['Manual baseline', 'FFT Denoising', 'Data range',
                                'X-axis alignment', 'Normalization'])
def test_the_processing_windows_show_your_order(mc, monkeypatch, op):
    """The windows with their own list of spectra (Spectra: ▲) show them in
    the main list's order (also your own); ▼ upside down."""
    from PyQt5.QtWidgets import QDialog
    _select(mc, 'sp004', 'sp005', 'sp009')
    mc.move_selected_spectra('bottom')
    _select(mc, 'sp009')
    mc.move_selected_spectra('top')
    mc.spectrum_selector.select_all_items()
    _pump(0.2)
    _select(mc, 'sp009', 'sp001', 'sp004', 'sp005')
    mine = [n for n in _labels(mc) if n in ('sp009', 'sp001', 'sp004', 'sp005')]
    assert mine == ['sp009', 'sp001', 'sp004', 'sp005']
    seen = []

    def record(dlg):
        seen.append(dlg)
        return 0
    monkeypatch.setattr(QDialog, 'exec_', record)
    mc.operations_controller.show_parameters_dialog_for(op)
    _pump(0.3)
    dlg = seen[0] if seen else next(w for w in app.topLevelWidgets()
                                     if hasattr(w, 'sort_button') and w.isVisible())
    lst = dlg.spectra_list
    shown = [lst.item(i).text().split(' : ')[-1] for i in range(lst.count())]
    assert shown == mine
    dlg.sort_button.click()                                        # ▼
    shown = [lst.item(i).text().split(' : ')[-1] for i in range(lst.count())]
    assert shown == list(reversed(mine))
    dlg.close()


def test_the_ways_of_sorting(mc):
    """Sort: ▾ - by name, in the order added, by a property, by a number in
    the name, your own order; reverse for each; spectra without the value
    at the end."""
    from src.modules.utils import spectra_order as so
    # a property: temperature, given to some spectra (sp003 has none)
    temps = {'sp001': 40.0, 'sp002': 20.0, 'sp004': 30.0, 'sp005': 10.0}
    for s in mc.original_spectra:
        t = temps.get(s['label'].split(' : ')[-1])
        if t is not None:
            s['metadata']['temperature_C'] = t
    mc._fill_sort_menu()
    texts = [a.text() for a in mc.sort_menu.actions()]
    assert texts[:2] == ['By name', 'In the order added'] and 'By a property' in texts
    assert 'By a number in the name' in texts
    props = [a for a in mc.sort_menu.actions() if a.text().startswith('By a property')][0].menu()
    assert 'temperature_C' in [a.text() for a in props.actions()]
    own = [a for a in mc.sort_menu.actions() if a.text() == 'Your own order'][0]
    assert own.isEnabled()                                        # also before moving anything
    assert mc.set_sort_mode({'by': 'property', 'key': 'temperature_C'})
    assert _labels(mc)[:4] == ['sp005', 'sp002', 'sp004', 'sp001']
    assert _labels(mc)[4] == 'sp003'                              # no value: at the end, by name
    assert 'temperature_C' in mc.sort_button.text()
    mc.checkBox_reverse_order.setChecked(True)
    _pump(0.1)
    assert _labels(mc)[:4] == ['sp001', 'sp004', 'sp002', 'sp005']
    assert _labels(mc)[4] == 'sp003'                              # still at the end
    mc.checkBox_reverse_order.setChecked(False)
    _pump(0.1)
    # a number in the name: the last number ('sp007' -> 7)
    assert mc.set_sort_mode({'by': 'number', 'number': -1})
    assert _labels(mc)[:3] == ['sp001', 'sp002', 'sp003']
    # the order added: a copy is the newest, even sorted by name it would be 2nd
    _select(mc, 'sp001')
    mc.copy_spectra_to_clipboard()
    mc.paste_spectra_from_clipboard()
    _pump(0.2)
    assert mc.set_sort_mode({'by': 'added'})
    assert _labels(mc)[0] == 'sp001' and _labels(mc)[-1] == 'sp001_copy'
    mc.set_sort_mode({'by': 'name'})
    assert _labels(mc)[:2] == ['sp001', 'sp001_copy']
    # moving a spectrum: your own order (from the list as it is)
    _select(mc, 'sp010')
    mc.move_selected_spectra('top')
    assert mc.sort_mode == {'by': 'own'} and _labels(mc)[0] == 'sp010'
    assert so.describe({'by': 'number', 'number': 1}) == 'by the second number in the name'


def test_the_sorting_in_snapshots(mc, tmp_path):
    from src.modules.misc.save_spectra_manager import SaveManager
    for s in mc.original_spectra:
        s['metadata']['pH'] = 14.0 - float(s['label'][-2:])
    mc.set_sort_mode({'by': 'property', 'key': 'pH'})
    mc.checkBox_reverse_order.setChecked(True)
    _pump(0.1)
    shown = _labels(mc)
    path = str(tmp_path / 'sorted.snapx')
    SaveManager().save_snapshot(mc, path)
    mc.checkBox_reverse_order.setChecked(False)
    mc.set_sort_mode({'by': 'name'})
    SaveManager().load_snapshot(mc, path)
    _pump(0.2)
    assert mc.sort_mode == {'by': 'property', 'key': 'pH'}
    assert 'pH' in mc.sort_button.text()
    assert [s['label'].split(' : ')[-1] for s in mc.original_spectra] == shown


@pytest.mark.parametrize('clear_first', [True, False])
def test_the_order_added_follows_the_file(mc, clear_first):
    """In the order added = the columns of the file, also for Import › Add
    and the Start page (an Add into the empty list) - before, a set
    difference shuffled the added spectra."""
    cd = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')
    if not clear_first:
        mc.import_controller.clear_spectra()
        _pump(0.2)
    mc.import_controller._run_import(clear_first=clear_first, file_paths=[cd])
    _pump(0.2)
    mc.set_sort_mode({'by': 'added'})
    cols = [s['metadata'].get('column_index') for s in mc.original_spectra]
    assert cols == sorted(cols) and len(cols) > 10
    # a second file added: after the first one, in its own column order
    mc.import_controller._run_import(clear_first=False, file_paths=[DATA])
    _pump(0.2)
    names = [s['label'].split(' : ')[-1] for s in mc.original_spectra]
    assert names[-11:] == [f'sp{i:03d}' for i in range(1, 12)]


def test_the_orange_help_of_the_sort_row(mc, monkeypatch):
    """The orange "?" after reverse explains sorting, reverse and moving;
    "Open the help" opens User Guide › Sorting the list."""
    from PyQt5.QtWidgets import QMessageBox as Box
    from src.help import help_window
    opened = []
    monkeypatch.setattr(help_window, 'open_help_topic', lambda *a: opened.append(a[1:]))
    shown = []

    def fake_exec(box):
        shown.append(box.text())
        assert box.escapeButton() is not None          # the window's X and Esc close it
        more = [b for b in box.buttons() if b.text() == 'Open the help'][0]
        more.click()
        return 0
    monkeypatch.setattr(Box, 'exec_', fake_exec)
    assert mc.sort_help_button.text() == '?' and mc.sort_help_button.isVisible()
    mc.sort_help_button.click()
    assert 'In the order added' in shown[0] and 'handle' in shown[0] and 'reverse' in shown[0]
    assert 'Esc' in shown[0] and 'Alt+Up' in shown[0] and 'Order' in shown[0]
    assert opened == [('user_guide', 'sorting')]


def test_choosing_your_own_order_keeps_the_list_as_it_is(mc):
    """Sort ▾ › Your own order before anything was moved: the list stays as
    it is (here by the last number, reversed), then new spectra go to the end
    and a renamed one keeps its place."""
    mc.set_sort_mode({'by': 'number', 'number': -1})
    mc.checkBox_reverse_order.setChecked(True)
    _pump(0.1)
    before = _labels(mc)
    assert before[0] == 'sp011'
    assert mc.custom_order is None and mc.set_sort_mode({'by': 'own'})
    assert _labels(mc) == before and 'own order' in mc.sort_button.text()
    mc.checkBox_reverse_order.setChecked(False)                    # upside down, and back
    _pump(0.1)
    assert _labels(mc) == list(reversed(before))
    mc.checkBox_reverse_order.setChecked(True)
    _pump(0.1)
    _select(mc, 'sp005')
    mc.copy_spectra_to_clipboard()
    mc.paste_spectra_from_clipboard()
    _pump(0.2)
    assert _labels(mc)[:-1] == before and _labels(mc)[-1] == 'sp005_copy'   # at the end
    mid = before[3]
    renamed = {s['label']: s['label'].replace(mid, 'zzz') for s in mc.original_spectra
               if s['label'].endswith(mid)}
    mc.spectrum_selector.rename_spectra(renamed)
    _pump(0.2)
    assert _labels(mc)[3] == 'zzz'                                 # kept its place


def test_a_new_import_sorts_by_name_and_no_impossible_sorting(mc, tmp_path):
    """Import data (new): sorted by name again (reverse stays). A sorting no
    spectrum has a value for any more falls back to by name - the button
    never shows what the menu greys out."""
    mc.set_sort_mode({'by': 'number', 'number': -1})
    mc.checkBox_reverse_order.setChecked(True)
    _pump(0.1)
    one = tmp_path / 'test_spectrum.txt'                           # one spectrum, no number
    one.write_text('x\ttest_spectrum\n' + ''.join(f'{x}\t{x * 0.5}\n' for x in range(100, 200)))
    mc.import_controller._run_import(clear_first=True, file_paths=[str(one)])
    _pump(0.2)
    assert mc.sort_mode == {'by': 'name'} and mc.sort_button.text() == 'by name'
    assert mc.checkBox_reverse_order.isChecked()                   # reverse stays
    mc.checkBox_reverse_order.setChecked(False)
    # a property removed while sorted by it: by name, said in the status bar
    mc.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump(0.2)
    for s in mc.original_spectra:
        s['metadata']['pH'] = 7.0
    assert mc.set_sort_mode({'by': 'property', 'key': 'pH'})
    for s in mc.original_spectra:
        s['metadata'].pop('pH')
    mc.update_spectra_order_and_redraw_plot()
    assert mc.sort_mode == {'by': 'name'} and mc.sort_button.text() == 'by name'
    assert 'Sorted by name' in mc.view.statusBar().currentMessage()
    # your own order: always there, also for a single spectrum
    mc._fill_sort_menu()
    own = [a for a in mc.sort_menu.actions() if a.text() == 'Your own order'][0]
    assert own.isEnabled()


def test_the_orange_help_of_the_list(mc, monkeypatch):
    """The "?" next to shorten names: the whole list in short (selecting, the
    arrow keys, Alt+Left / Alt+Right, keys, shorten names); "Open the help"
    opens User Guide › 2. Spectrum Selection. The Sort row's "?" mentions the
    arrow keys too."""
    from PyQt5.QtWidgets import QMessageBox as Box
    from src.help import help_window
    opened, shown = [], []
    monkeypatch.setattr(help_window, 'open_help_topic', lambda *a: opened.append(a[1:]))

    def fake_exec(box):
        shown.append(box.text())
        assert box.escapeButton() is not None
        [b for b in box.buttons() if b.text() == 'Open the help'][0].click()
        return 0
    monkeypatch.setattr(Box, 'exec_', fake_exec)
    mc.sort_shorten_help_button.click()
    text = shown[0]
    for part in ('&darr;', 'Alt+Left', 'Ctrl+click', 'Shift+click', 'shorten names', 'Undo'):
        assert part in text, part
    assert opened == [('user_guide', 'selection')]
    mc.sort_help_button.click()
    assert '&darr;' in shown[1]
