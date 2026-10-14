"""Adding a dataset while many spectra are selected must not select list
rows one by one (that froze the window for ~40 s with a 21 000-spectrum map
selected) -- and must keep the selection. See list_selection.py."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QListWidget, QListWidgetItem, QMessageBox

from src.modules.utils.list_selection import row_ranges, select_rows

app = QApplication.instance() or QApplication([])
DATA = os.path.join(os.path.dirname(__file__), '..', 'resources', 'test_data', 'real')


def test_row_ranges_merge_neighbours():
    assert row_ranges([5, 1, 2, 3, 9, 8, 3]) == [(1, 3), (5, 5), (8, 9)]
    assert row_ranges([]) == []


def test_select_rows_replace_add_remove():
    w = QListWidget()
    w.setSelectionMode(QListWidget.ExtendedSelection)
    for i in range(10):
        w.addItem(QListWidgetItem(str(i)))
    select_rows(w, [1, 2, 3, 7, 99])
    assert sorted(w.row(i) for i in w.selectedItems()) == [1, 2, 3, 7]
    select_rows(w, [8], mode='add')
    select_rows(w, [2], mode='remove')
    assert sorted(w.row(i) for i in w.selectedItems()) == [1, 3, 7, 8]
    select_rows(w, [])
    assert w.selectedItems() == []


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths),
                                                 [{} for _ in file_paths])))
    from src.controllers.core.main_controller import MainController
    controller = MainController()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def test_adding_spectra_keeps_the_selection_without_selecting_row_by_row(mc, monkeypatch):
    mc.import_controller._run_import(clear_first=True,
                                     file_paths=[os.path.join(DATA, 'CD_spectra_TBA.txt')])
    mc.spectrum_selector.select_all_items()
    app.processEvents()
    selected = {s['label'] for s in mc.spectrum_selector.get_selected_spectra()}
    assert len(selected) > 10
    calls = []
    real = QListWidgetItem.setSelected
    monkeypatch.setattr(QListWidgetItem, 'setSelected',
                        lambda self, on: calls.append(on) or real(self, on))
    mc.import_controller._run_import(clear_first=False,
                                     file_paths=[os.path.join(DATA, 'Raman_DNA_conc_dep.txt')])
    app.processEvents()
    assert calls == []                                            # one batched selection instead
    assert len(mc.original_spectra) > len(selected)
    assert {s['label'] for s in mc.spectrum_selector.get_selected_spectra()} == selected
    assert {i.text() for i in mc.spectra_list_widget.selectedItems()} == selected
