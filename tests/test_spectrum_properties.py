"""Spectrum properties (right-click on the spectra list): temperature, pH,
concentration, ... per spectrum - typed, pasted, filled from the names or as
a series; stored in the metadata as one Operations History step (Undo takes
it back); used by Colours by value, the Data table and the Peak list plot."""
import glob
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
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
