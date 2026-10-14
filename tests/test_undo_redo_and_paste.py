"""Main window Undo / Redo buttons (one step in the Operations History) and
Ctrl+C / Ctrl+V on the spectra list (Ctrl+C remembers, Ctrl+V copies)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from types import SimpleNamespace

import numpy as np
from PyQt5.QtWidgets import QApplication

from src.controllers.core.main_controller import MainController
from src.controllers.core.operations_controller import OperationsController
from src.modules.data_analysis.incremental_operations_manager import (
    IncrementalOperationsManager)

app = QApplication.instance() or QApplication([])


def _sp(label, h=1.0):
    x = np.linspace(0, 10, 11)
    return {'label': label, 'x_scale': x, 'y_scale': h * x, 'metadata': {}}


def _history(n_ops):
    mgr = IncrementalOperationsManager()
    mgr.initialize_with_spectra([_sp('a'), _sp('b')])
    for i in range(n_ops):
        mgr.apply_operation(f'Op{i + 1}', {}, [_sp('a', i + 2)])
    return mgr


def _fake_ops(mgr):
    jumps = []
    fake = SimpleNamespace(operations_manager=mgr, jumps=jumps,
                           update_undo_redo_buttons=lambda: None)
    fake.undo_redo_targets = lambda: OperationsController.undo_redo_targets(fake)

    def jump(index):
        jumps.append(index)
        mgr.set_active_operation(index)
    fake.jump_to_operation_state = jump
    return fake


def test_undo_and_redo_step_one_operation():
    mgr = _history(2)                          # Original, Op1, Op2 (active)
    fake = _fake_ops(mgr)
    OperationsController.undo_operation(fake)
    OperationsController.undo_operation(fake)
    OperationsController.undo_operation(fake)  # already at Original: nothing
    assert fake.jumps == [0, -1]
    OperationsController.redo_operation(fake)
    OperationsController.redo_operation(fake)
    OperationsController.redo_operation(fake)  # already at the last step: nothing
    assert fake.jumps == [0, -1, 0, 1]


def test_undo_redo_targets_at_the_ends():
    assert OperationsController.undo_redo_targets(_fake_ops(_history(0))) == (None, None)
    mgr = _history(1)
    assert OperationsController.undo_redo_targets(_fake_ops(mgr)) == (-1, None)
    mgr.set_active_operation(-1)
    assert OperationsController.undo_redo_targets(_fake_ops(mgr)) == (None, 0)


def test_new_operation_after_undo_removes_redo():
    mgr = _history(2)
    mgr.set_active_operation(0)
    mgr.apply_operation('New', {}, [_sp('b', 5)])
    assert OperationsController.undo_redo_targets(_fake_ops(mgr)) == (0, None)


def test_main_window_has_undo_redo_buttons_disabled_without_data():
    from src.views.main_window import MainWindow
    w = MainWindow(None)
    assert w.undo_operations_pushButton.text().endswith('Undo')
    assert not w.undo_operations_pushButton.isEnabled()
    assert not w.redo_operations_pushButton.isEnabled()
    w.deleteLater()


def _fake_main(selected):
    copies = []
    fake = SimpleNamespace(
        spectrum_selector=SimpleNamespace(get_selected_spectra=lambda: list(selected)),
        _status=lambda *a, **k: None,
        _copy_selected_spectra=lambda sources=None: copies.append(list(sources)))
    return fake, copies


def test_ctrl_c_only_remembers_and_ctrl_v_makes_the_copies():
    a, b = _sp('a'), _sp('b')
    selected = [a, b]
    fake, copies = _fake_main(selected)
    MainController.copy_spectra_to_clipboard(fake)
    assert copies == []                                  # Ctrl+C: nothing copied yet
    selected[:] = []                                     # selection changes before pasting
    MainController.paste_spectra_from_clipboard(fake)
    assert copies == [[a, b]]                            # Ctrl+V copies what Ctrl+C took
    MainController.paste_spectra_from_clipboard(fake)
    assert len(copies) == 2                              # paste again: another set


def test_ctrl_v_without_ctrl_c_does_nothing():
    fake, copies = _fake_main([_sp('a')])
    MainController.paste_spectra_from_clipboard(fake)
    assert copies == []


# --- importing more spectra is an "Import" step in the history -------------------

def _fake_import_controller(mgr, current):
    fake = SimpleNamespace(operations_manager=mgr,
                           controller=SimpleNamespace(original_spectra=list(current)))
    return fake


def test_added_import_is_a_history_step_that_can_be_undone():
    mgr = _history(1)                                   # Original (a, b), Op1
    current = mgr.get_current_spectra()
    new = [_sp('c'), _sp('d')]
    new[0]['metadata'] = {'file_path': r'C:\data\run2.txt'}
    fake = _fake_import_controller(mgr, current)
    OperationsController._register_import_step(fake, new)
    assert len(mgr.operations_chain) == 2
    step = mgr.operations_chain[-1]
    assert step['type'] == 'Import'
    assert step['parameters']['imported_count'] == 2
    assert step['parameters']['files'] == ['run2.txt']
    assert sorted(s['label'] for s in mgr.get_current_spectra()) == ['a', 'b', 'c', 'd']
    assert sorted(s['label'] for s in mgr.original_spectra) == ['a', 'b']   # Original unchanged
    mgr.set_active_operation(0)                          # Undo
    assert sorted(s['label'] for s in mgr.get_current_spectra()) == ['a', 'b']
    assert OperationsController.undo_redo_targets(_fake_ops(mgr)) == (-1, 1)


def test_first_spectra_of_a_session_are_the_original_state():
    mgr = IncrementalOperationsManager()
    fake = _fake_import_controller(mgr, [])
    OperationsController._register_import_step(fake, [_sp('a')])
    assert mgr.operations_chain == []
    assert [s['label'] for s in mgr.original_spectra] == ['a']


def test_import_of_already_present_labels_adds_no_step():
    mgr = _history(0)
    fake = _fake_import_controller(mgr, mgr.get_current_spectra())
    OperationsController._register_import_step(fake, [_sp('a')])
    assert mgr.operations_chain == []


def test_methods_report_describes_import_in_one_sentence():
    from src.modules.misc import methods_report as mr
    d = mr.describe_operation('Import', {'imported_count': 11, 'files': ['run2.txt']})
    assert d.sentence == "11 further spectra were imported from run2.txt."
