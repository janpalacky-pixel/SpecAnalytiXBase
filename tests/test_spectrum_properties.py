"""Spectrum properties (right-click on the spectra list): temperature, pH,
concentration, ... per spectrum - typed, pasted, filled from the names or as
a series; stored in the metadata as one Operations History step (Undo takes
it back); used by Colours by value, the Data table and the Peak list plot."""
import glob
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.misc import spectrum_properties as sp
from src.modules.visualization import color_by_value as cbv

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TBA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')
JWB = sorted(glob.glob(os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD melting', '*.jwb')))[0]


# --- the rules (no window) ---------------------------------------------------------------

def test_values_names_and_changes():
    assert sp.parse_value('7,4') == 7.4 and sp.parse_value(' 25 ') == 25.0
    assert sp.parse_value('') is None and sp.parse_value('−5') == -5.0
    with pytest.raises(ValueError):
        sp.parse_value('abc')
    spectra = [{'label': 'a 20C', 'metadata': {'temperature_C': 20.0, 'file': 'x.txt'}},
               {'label': 'b 30C', 'metadata': {}}]
    assert sp.check_name('pH', spectra) is None
    assert 'no spaces' in sp.check_name('conc mM', spectra)
    assert 'already' in sp.check_name('temperature_C', spectra, existing=['temperature_C'])
    assert 'as text' in sp.check_name('file', spectra)
    assert 'program' in sp.check_name('unique_id', spectra)
    assert sp.from_name(spectra) == [20.0, 30.0]
    assert sp.series(3, 20, 5) == [20, 25, 30]
    diff = sp.changes(spectra, [{'temperature_C': 20.0, 'pH': 7.0}, {'temperature_C': None}])
    assert diff == [(0, 'pH', None, 7.0)]
    sp.apply_to(spectra[0], {'pH': 7.0, 'temperature_C': None})
    assert spectra[0]['metadata'] == {'pH': 7.0, 'file': 'x.txt'}
    # a value as the table shows it (10 digits) is not a change
    exact = [{'label': 'c', 'metadata': {'temperature_C': 10.0399999999987}}]
    shown = sp.parse_value(sp.value_text(exact[0]['metadata']['temperature_C']))
    assert sp.changes(exact, [{'temperature_C': shown}]) == []


# --- the window --------------------------------------------------------------------------

def _window(spectra, calls=None):
    from src.views.dialogs.misc.spectrum_properties_dialog import SpectrumPropertiesDialog
    return SpectrumPropertiesDialog(None, spectra, apply_callback=lambda s, v: (
        calls.append(v) if calls is not None else None) or (True, 'stored'))


def test_window_add_paste_fill_and_bad_cells(monkeypatch):
    spectra = [{'label': f'TBA_{t}C : 000{i}', 'metadata': {'unique_id': str(i)}}
               for i, t in enumerate((20, 30, 40))]
    calls = []
    dlg = _window(spectra, calls)
    assert dlg.keys == [] and not dlg.apply_button.isEnabled()
    assert dlg.add_property('pH') == 'pH' and dlg.keys == ['pH']
    monkeypatch.setattr(QMessageBox, 'warning', staticmethod(lambda *a, **k: QMessageBox.Ok))
    assert dlg.add_property('pH') is None                  # already there
    QApplication.clipboard().setText('7\n7,5\n8\n')
    dlg.table.setCurrentCell(0, 1)
    assert dlg.paste() == 3
    assert dlg.values()[0] == [{'pH': 7.0}, {'pH': 7.5}, {'pH': 8.0}]
    assert dlg.apply_button.isEnabled()
    dlg.add_property('temperature_C')
    dlg.table.clearSelection()
    dlg.table.setCurrentCell(0, 2)
    dlg.table.clearSelection()
    dlg.fill_from_names(number=0)                          # 20, 30, 40 from the names
    assert [v['temperature_C'] for v in dlg.values()[0]] == [20.0, 30.0, 40.0]
    dlg.fill_series(start=10, step=2.5)
    assert [v['temperature_C'] for v in dlg.values()[0]] == [10.0, 12.5, 15.0]
    dlg.table.item(1, 1).setText('seven')
    assert not dlg.apply_button.isEnabled() and 'not numbers' in dlg.summary.text()
    dlg.table.item(1, 1).setText('7.5')
    assert dlg.apply()
    assert calls[-1][2] == {'pH': 8.0, 'temperature_C': 15.0}
    assert not dlg.apply_button.isEnabled()                # nothing left to apply
    assert spectra[0]['metadata'] == {'unique_id': '0'}    # the window never changes the spectra


def test_closing_with_changes_asks(monkeypatch):
    dlg = _window([{'label': 'a', 'metadata': {}}])
    dlg.add_property('pH')
    dlg.table.item(0, 1).setText('7')
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Cancel))
    dlg.show()
    dlg.reject()
    assert dlg.isVisible()
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.No))
    dlg.reject()
    assert not dlg.isVisible()


# --- in the program ----------------------------------------------------------------------

@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths),
                                                 [{'jws_selected_channels': [0]} for _ in file_paths])))
    controller = MainController()
    controller.import_controller._run_import(clear_first=True, file_paths=[TBA])
    controller.spectrum_selector.select_all_items()
    app.processEvents()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _open(mc, monkeypatch):
    from src.views.dialogs.misc import spectrum_properties_dialog as spd
    monkeypatch.setattr(spd.SpectrumPropertiesDialog, 'exec_', lambda self: 0)
    return mc.spectrum_properties_controller.show_dialog()


def test_stored_used_and_undone(mc, monkeypatch):
    dlg = _open(mc, monkeypatch)
    assert dlg.table.rowCount() == 28 and dlg.keys == []
    dlg.add_property('pH')
    dlg.table.sortItems(0)
    dlg.table.clearSelection()
    dlg.table.setCurrentCell(0, 1)
    dlg.table.clearSelection()
    dlg.fill_series(start=5, step=0.1)
    assert dlg.apply()
    assert 'pH for 28 spectra' in dlg.summary.text()
    om = mc.operations_controller.operations_manager
    assert om.operations_chain[-1]['type'] == 'Spectrum properties'
    ph = {s['label']: s['metadata'].get('pH') for s in mc.original_spectra}
    assert ph['CD_spectra_TBA : 0001'] == pytest.approx(5.0)
    assert ph['CD_spectra_TBA : 0028'] == pytest.approx(7.7)
    assert all(s['metadata'].get('pH') is not None for s in mc.selected_spectra)
    # used by Colours by value, the Data table and the Peak list plot
    assert 'pH' in cbv.metadata_keys(mc.selected_spectra)
    from src.modules.data_analysis import peak_list as pl, value_table as vt
    assert 'pH' in [c.name for c in vt.ValueTable.from_spectra(mc.selected_spectra).columns]
    assert ('Spectrum: pH', ('spectrum', {'mode': 'metadata', 'metadata_key': 'pH'})) in \
        pl.x_choices(mc.selected_spectra)
    # one step in the History: Undo takes it back, Redo brings it again
    mc.operations_controller.undo_operation()
    assert all('pH' not in s['metadata'] for s in mc.original_spectra)
    mc.operations_controller.redo_operation()
    assert all('pH' in s['metadata'] for s in mc.original_spectra)


def test_correcting_and_removing_a_property(mc, monkeypatch):
    dlg = _open(mc, monkeypatch)
    dlg.add_property('replicate')
    dlg.table.setCurrentCell(0, 1)
    dlg.table.clearSelection()
    dlg.fill_series(start=1, step=0)
    assert dlg.apply()
    dlg = _open(mc, monkeypatch)
    assert dlg.keys == ['replicate']
    dlg.table.setCurrentCell(0, 1)
    assert dlg.remove_property()
    assert dlg.apply()
    assert all('replicate' not in s['metadata'] for s in mc.original_spectra)
    assert [op['type'] for op in mc.operations_controller.operations_manager.operations_chain][-2:] \
        == ['Spectrum properties', 'Spectrum properties']


def test_in_the_spectra_list_menu_and_the_methods_report(mc):
    import inspect
    from src.modules.misc import methods_report as mr
    src = inspect.getsource(type(mc).show_spectra_list_context_menu)
    assert 'Spectrum properties' in src
    d = mr.describe_operation('Spectrum properties',
                              {'properties': {'a': {'pH': 7.0}, 'b': {'pH': 7.5, 'time_s': 3.0}}})
    assert d.sentence == "Sample properties were entered for the spectra: pH (2 spectra), " \
                         "time_s (1 spectrum)."


def test_kept_in_snapshots(mc, monkeypatch, tmp_path):
    dlg = _open(mc, monkeypatch)
    dlg.add_property('concentration_mM')
    dlg.table.setCurrentCell(0, 1)
    dlg.table.clearSelection()
    dlg.fill_series(start=0.5, step=0.5)
    assert dlg.apply()
    manager = mc.save_controller.save_manager
    path = str(tmp_path / 'props.snapx')
    manager.save_snapshot(mc, path)
    mc.operations_controller.undo_operation()
    assert all('concentration_mM' not in s['metadata'] for s in mc.original_spectra)
    assert manager.load_snapshot(mc, path)
    assert sorted(s['metadata']['concentration_mM'] for s in mc.original_spectra)[:2] == [0.5, 1.0]
    assert mc.operations_controller.operations_manager.operations_chain[-1]['type'] == \
        'Spectrum properties'


def test_like_a_spreadsheet(monkeypatch):
    """Ctrl+C / Ctrl+X / Ctrl+V (one value into all selected cells, a block
    from the top-left selected cell), Delete, Ctrl+D (fill down), Ctrl+Z,
    the right-click menu; sorting does not move rows while pasting."""
    from PyQt5.QtWidgets import QMenu, QTableWidgetSelectionRange as Range
    spectra = [{'label': f's{i}', 'metadata': {}} for i in range(1, 6)]
    calls = []
    dlg = _window(spectra, calls)
    dlg.add_property('pH')
    dlg.add_property('conc')
    t = dlg.table
    clip = QApplication.clipboard()

    def select(r0, c0, r1, c1):
        t.clearSelection()
        t.setRangeSelected(Range(r0, c0, r1, c1), True)
    # one copied value into all five selected pH cells
    clip.setText('7.4')
    select(0, 1, 4, 1)
    assert dlg.paste() == 5
    assert [t.item(r, 1).text() for r in range(5)] == ['7.4'] * 5
    # a block of two columns from Excel, from the top-left selected cell
    clip.setText('1\t10\n2\t20\n')
    select(1, 1, 1, 1)
    dlg.paste()
    assert [t.item(r, 1).text() for r in range(4)] == ['7.4', '1', '2', '7.4']
    assert [t.item(r, 2).text() for r in range(4)] == ['', '10', '20', '']
    # Ctrl+D: the top selected value down
    select(1, 2, 4, 2)
    assert dlg.fill_down() == 3
    assert [t.item(r, 2).text() for r in range(5)] == ['', '10', '10', '10', '10']
    # Ctrl+C: a block (tabs, lines)
    select(1, 1, 2, 2)
    assert dlg.copy_cells() == '1\t10\n2\t10'
    # Ctrl+X: copied and emptied
    dlg.cut_cells()
    assert clip.text() == '1\t10\n2\t10'
    assert [t.item(r, 1).text() for r in (1, 2)] == ['', '']
    # Ctrl+Z: back step by step
    assert dlg.undo()
    assert [t.item(r, 1).text() for r in (1, 2)] == ['1', '2']
    dlg.undo()                                                     # the fill down
    assert t.item(4, 2).text() == ''
    # a typed value is undone too
    t.item(0, 2).setText('5')
    dlg.undo()
    assert t.item(0, 2).text() == ''
    # pasting into a sorted column keeps the rows where they are
    t.sortItems(1)
    names = [t.item(r, 0).text() for r in range(5)]
    clip.setText('0')
    select(0, 1, 4, 1)
    dlg.paste()
    assert [t.item(r, 0).text() for r in range(5)] == names
    # the right-click menu has the same
    shown = []
    monkeypatch.setattr(QMenu, 'exec_', lambda m, *a: shown.append(
        [a.text().split('\t')[0] for a in m.actions() if a.text()]))
    dlg._table_menu(t.visualItemRect(t.item(0, 1)).center())
    assert shown[0] == ['Copy', 'Cut', 'Paste', 'Delete', 'Fill down', 'Undo']
    dlg.apply_button.setEnabled(False)
    dlg.close()


def test_remove_property_takes_the_column_away(monkeypatch):
    """Remove property: the column goes at once; Apply removes the values
    from the spectra; Ctrl+Z brings the column back before that."""
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    spectra = [{'label': 's1', 'metadata': {'pH': 7.0, 'T': 20.0}},
               {'label': 's2', 'metadata': {'pH': 8.0, 'T': 30.0}}]
    calls = []
    dlg = _window(spectra, calls)
    assert dlg.keys == ['pH', 'T']
    dlg.table.setCurrentCell(0, 1)                                 # pH
    assert dlg.remove_property()
    assert dlg.keys == ['T'] and dlg.table.columnCount() == 2
    assert dlg.table.horizontalHeaderItem(1).text() == 'T'
    assert dlg.apply_button.isEnabled()
    assert dlg.undo()                                              # back again
    assert dlg.keys == ['pH', 'T'] and dlg.table.item(0, 1).text() == '7'
    dlg.table.setCurrentCell(0, 1)
    dlg.remove_property()
    assert dlg.apply()
    assert calls and all(v['pH'] is None and v['T'] is not None for v in calls[-1])
    assert 'pH' not in dlg.spectra[0]['metadata'] and not dlg.apply_button.isEnabled()
    dlg.close()


def test_delete_in_a_sorted_table_clears_all_and_keeps_the_alignment():
    """Delete with the table sorted by the column: every selected cell is
    emptied (the rows used to move under it); a value typed into a cleared
    cell is right-aligned and sorted as a number like the others."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QTableWidgetSelectionRange as Range
    spectra = [{'label': f's{i}', 'metadata': {'T': float(t)}}
               for i, t in enumerate((88, 15, 74.88, 60, 74.78, 74.78, 20))]
    dlg = _window(spectra)
    t = dlg.table
    t.sortItems(1)                                                 # sorted by T (empty cells go last)
    t.clearSelection()
    t.setRangeSelected(Range(0, 1, 4, 1), True)                    # 5 of the 7 cells
    chosen = {t.item(r, 0).text() for r in range(5)}
    assert dlg.clear_cells() == 5
    texts = [t.item(r, 1).text() for r in range(7)]
    assert texts.count('') == 5
    assert {t.item(r, 0).text() for r in range(7) if t.item(r, 1).text() == ''} == chosen
    for r in range(7):
        item = t.item(r, 1)
        assert int(item.textAlignment()) & int(Qt.AlignRight)
    empty = next(r for r in range(7) if t.item(r, 1).text() == '')
    t.item(empty, 1).setText('9')                                  # typed in
    row = next(r for r in range(7) if t.item(r, 1).text() == '9')
    assert int(t.item(row, 1).textAlignment()) & int(Qt.AlignRight)
    numbers = [float(t.item(r, 1).text()) for r in range(7) if t.item(r, 1).text()]
    assert numbers == sorted(numbers)                              # 9 among the numbers
    dlg.apply_button.setEnabled(False)
    dlg.close()


def test_headings_are_centred_not_right_aligned():
    """The value cells are right-aligned (the item prototype); the headings
    must not copy that, also after a property is added."""
    spectra = [{'label': 's1', 'metadata': {'pH': 7.0}},
               {'label': 's2', 'metadata': {'pH': 8.0}}]
    dlg = _window(spectra)

    def right(c):
        a = dlg.table.horizontalHeaderItem(c).textAlignment()
        return bool(int(a) & int(Qt.AlignRight))
    assert not right(0) and not right(1)
    assert dlg.table.item(0, 1).textAlignment() & int(Qt.AlignRight)
    dlg.add_property('T')
    assert not any(right(c) for c in range(dlg.table.columnCount()))
    dlg.close()
