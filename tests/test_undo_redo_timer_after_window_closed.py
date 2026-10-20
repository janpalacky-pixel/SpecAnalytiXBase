"""The timer that refreshes the Undo / Redo buttons goes away with the main
window and never touches its deleted buttons.

Found because the full test suite closed itself on Windows (exit code
0xC0000409) in the cursor test, right after test_autosave_and_recent.py: the
timer of an earlier, already deleted main window was still firing and raised
"wrapped C/C++ object of type QPushButton has been deleted" -- an error inside
a Qt callback, which PyQt5 on Windows answers by aborting the program. (On
Linux it was only printed.)"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def _pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def test_timer_is_a_child_of_the_main_window():
    from src.controllers.core.main_controller import MainController
    mc = MainController()
    oc = mc.operations_controller
    assert oc._undo_redo_timer.parent() is mc.view and oc._undo_redo_timer.isActive()
    mc.autosave_controller.shutdown()
    sip.delete(mc.view)                                   # the window is gone ...
    assert sip.isdeleted(oc._undo_redo_timer)              # ... and its timer with it


def test_no_error_after_the_window_is_deleted(monkeypatch):
    from src.controllers.core.main_controller import MainController
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda *exc: errors.append(exc))
    mc = MainController()
    oc = mc.operations_controller
    mc.autosave_controller.shutdown()
    sip.delete(mc.view)
    oc._undo_redo_key = None                               # as if the History had changed
    oc.update_undo_redo_buttons()                          # a late call: no error
    _pump(1.0)                                             # 2+ timer periods: nothing fires
    assert errors == []
