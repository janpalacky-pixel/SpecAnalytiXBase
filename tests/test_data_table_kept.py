"""The Data table keeps its columns between sessions (data_table_columns.json
next to the settings) and in snapshots."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TBA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')


# --- the memory file -------------------------------------------------------------------

def test_the_memory_file_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path))
    from src.modules.data_analysis import data_table_memory as m
    assert m.load() is None
    memory = {'labels': ['a', 'b'], 'points': [('sp1 - sp2', '')],
              'values': [{'type': 'value', 'name': 'v1',
                          'settings': {'kind': 'max', 'range_a': (215.0, np.float64(225))}}]}
    m.save(memory)
    back = m.load()
    assert back['points'] == [['sp1 - sp2', '']]
    assert back['values'][0]['settings']['range_a'] == [215.0, 225.0]
    m.save({'labels': ['a'], 'points': [], 'values': []})            # all columns removed
    assert m.load() is None


def test_very_many_sent_numbers_are_not_kept(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path))
    from src.modules.data_analysis import data_table_memory as m
    many = {f's{i}': 1.0 for i in range(m.MAX_KEPT_NUMBERS + 1)}
    m.save({'labels': [], 'points': [],
            'values': [{'type': 'fixed', 'name': 'b1', 'by_label': many},
                       {'type': 'formula', 'name': 'f1', 'formula': '2', 'title': ''}]})
    assert [r['name'] for r in m.load()['values']] == ['f1']


# --- in the program ----------------------------------------------------------------------

def _program(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    controller = MainController()
    controller.import_controller._run_import(clear_first=True, file_paths=[TBA])
    app.processEvents()
    return controller


def _close(mc):
    mc.autosave_controller.shutdown()
    mc.view.deleteLater()


def _open_table(mc, monkeypatch, run):
    from src.views.dialogs.data_analysis import data_table_dialog as dtd
    seen = []
    monkeypatch.setattr(dtd.DataTableDialog, 'exec_', lambda self: seen.append(run(self)) or 0)
    mc.spectra_list_widget.clearSelection()
    for r in (0, 1, 2):
        mc.spectra_list_widget.item(r).setSelected(True)
    app.processEvents()
    mc.view.actionMenuDataTable.trigger()
    return seen[0]


def test_the_columns_come_back_after_a_restart(tmp_path, monkeypatch):
    first = _program(tmp_path, monkeypatch)

    def add(dlg):
        dlg.values.add_value({'kind': 'max', 'range_a': (250, 300)})
        dlg.formula_edit.setText('sp1 - sp2')
        dlg.add_column()
        dlg.reject()
        return dlg
    _open_table(first, monkeypatch, add)
    _close(first)
    second = _program(tmp_path, monkeypatch)                    # the program started again
    names = _open_table(second, monkeypatch, lambda dlg: (
        [c.name for c in dlg.values.table.columns], [c.formula for c in dlg.table.formula_columns()]))
    assert names[0][-1] == 'v1' and names[1] == ['sp1 - sp2']
    _close(second)


def test_the_columns_are_saved_in_a_snapshot(tmp_path, monkeypatch):
    mc = _program(tmp_path, monkeypatch)
    dtc = mc.data_table_controller
    dtc.remembered = {'labels': ['x'], 'points': [],
                      'values': [{'type': 'formula', 'name': 'f1', 'formula': 'row * 2',
                                  'title': 'twice'}]}
    manager = mc.save_controller.save_manager
    state = manager._from_json(manager._to_json(manager._build_state(mc)))
    assert state['data_table']['values'][0]['formula'] == 'row * 2'
    dtc.remembered = None
    manager._restore_ui_state(mc, state)                        # the snapshot opened
    assert dtc.remembered['values'][0]['title'] == 'twice'
    state.pop('data_table')                                     # an older snapshot: kept
    manager._restore_ui_state(mc, state)
    assert dtc.remembered['values'][0]['title'] == 'twice'
    _close(mc)
