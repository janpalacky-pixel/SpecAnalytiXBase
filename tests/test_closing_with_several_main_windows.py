"""Closing the main window closes every other window once -- also when some
of them are main windows themselves, whose own closing would otherwise close
every window again (a chain reaction).

Found because `pytest tests/` on Windows stopped for good after
test_panels_fit_on_open.py: closing its main window closed the main windows
left over from earlier tests, each of which closed all windows again; the
automatic stack report (pytest.ini, faulthandler_timeout) showed nine such
closings nested inside each other. In the program there is one main window,
so this concerned the test run only."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox, QWidget

app = QApplication.instance() or QApplication([])


def test_closing_one_main_window_closes_the_others_without_a_chain(monkeypatch):
    from src.controllers.core import main_controller as mcm
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    windows = [mcm.MainController() for _ in range(4)]
    for w in windows:
        w.view.show()
    extra = [QWidget() for _ in range(20)]
    for e in extra:
        e.show()
    calls = []
    real = QApplication.topLevelWidgets
    monkeypatch.setattr(QApplication, 'topLevelWidgets',
                        staticmethod(lambda: calls.append(1) or real()))
    started = time.time()
    windows[0].view.close()
    assert time.time() - started < 20
    assert len(calls) == 1                     # "close all others" ran once, not once per window
    assert not any(w.view.isVisible() for w in windows)
    assert not any(e.isVisible() for e in extra)
    assert mcm._closing_other_windows == [False]
    for w in windows:
        w.autosave_controller.shutdown()
