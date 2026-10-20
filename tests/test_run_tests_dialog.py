"""Help -> Run tests... and the button in Help -> About: the program's own tests
run in a separate, invisible process; the window shows progress, counts and
the output, the result in green or red, and saves / copies one report with the
About information. The real suite is not run here -- small demo test files are."""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.modules.utils import self_test

app = QApplication.instance() or QApplication([])

DEMO = '''
import pytest, time

def test_ok():
    assert 1 + 1 == 2

def test_also_ok():
    assert True

def test_broken():
    assert 1 == 2

@pytest.mark.skip(reason="demo")
def test_skipped():
    pass
'''


def _wait(dlg, limit=120):
    end = time.time() + limit
    while dlg.is_running() and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    assert not dlg.is_running()


def _demo(tmp_path, text=DEMO):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_demo.py').write_text(text)
    return tmp_path


# --- reading the output (no Qt) ---------------------------------------------------------

def test_output_is_counted_also_when_a_message_comes_in_between():
    r = self_test.OutputReader()
    for line in ['tests/test_a.py::test_x PASSED                      [ 10%]',
                 'tests/test_s.py::test_smoke[two spectra]  ** On entry to DLASCL parameter number  4',
                 ' ** On entry to DLASCL parameter number  4 had an illegal value',
                 'PASSED                         [ 50%]',
                 'tests/test_p.py::test_w[Group Statistics] SKIPPED (on Windows)   [ 60%]',
                 'tests/test_c.py::test_t FAILED                     [100%]',
                 'FAILED tests/test_c.py::test_t - assert 1 == 2',
                 '====== 1 failed, 2 passed, 1 skipped, 564 warnings in 390.18s (0:06:30) ======']:
        r.feed(line)
    assert r.counts == {'passed': 2, 'failed': 1, 'skipped': 1, 'error': 0}
    assert r.percent == 100 and r.current == 'tests/test_c.py::test_t'
    assert r.summary_counts == {'failed': 1, 'passed': 2, 'skipped': 1, 'warning': 564}
    ok, text = r.result(1)
    assert not ok and text.startswith('1 test failed (1 failed, 2 passed')


def test_result_texts():
    r = self_test.OutputReader()
    r.feed('==== 1292 passed, 1 skipped, 564 warnings in 390.18s (0:06:30) ====')
    assert r.result(0) == (True, 'All tests passed: 1292 passed, 1 skipped.')
    r = self_test.OutputReader()
    r.feed('tests/test_a.py::test_x PASSED [ 20%]')
    assert r.result(3221226505) == (False, 'The test run ended unexpectedly (exit code 3221226505) '
                                           'after 1 tests. Please send the saved output to the developer.')
    assert r.result(-9, stopped=True) == (False, 'Stopped by you after 1 tests.')


def test_available_from_the_python_source_and_in_the_installed_version(monkeypatch, tmp_path):
    assert self_test.availability() == (True, '')
    assert self_test.availability(str(tmp_path))[0] is False            # no tests folder
    start = ([sys.executable] if getattr(sys, 'frozen', False)          # installed
             else [sys.executable, os.path.join(self_test.PROJECT_ROOT, 'main.py')])
    cmd = self_test.command(output='out.txt')
    assert cmd[:len(start) + 4] == start + ['--run-tests', '--output', 'out.txt', 'tests']
    assert '-v' in cmd
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    assert self_test.availability() == (True, '')        # the build puts the tests in
    ok, why = self_test.availability(str(tmp_path))
    assert not ok and 'built without the tests' in why
    assert self_test.command()[:3] == [sys.executable, '--run-tests', 'tests']
    assert self_test.environment()['QT_QPA_PLATFORM'] == 'offscreen'


def test_the_run_writes_everything_to_the_output_file(tmp_path):
    """main.py --run-tests --output FILE: pytest's output goes to FILE, also
    what is printed below Python (the installed program has no console)."""
    import subprocess
    _demo(tmp_path, "import os\n\ndef test_a():\n    os.write(1, b'LOW LEVEL\\n')\n")
    out = tmp_path / 'out.txt'
    cmd = self_test.command(('tests', '-s'), output=str(out))
    # stdin=DEVNULL: in the installed program (a Windows program without a
    # console) there is no input to hand on, and Windows refuses to try
    proc = subprocess.run(cmd, cwd=str(tmp_path), capture_output=True, timeout=120,
                          stdin=subprocess.DEVNULL,
                          env=dict(os.environ, **self_test.environment()))
    text = out.read_text(encoding='utf-8')
    assert proc.returncode == 0, text
    assert 'LOW LEVEL' in text and 'test_demo.py::test_a' in text and '1 passed' in text
    assert proc.stdout == b''                             # nothing lost on the way


# --- the window ----------------------------------------------------------------------

def test_a_run_shows_counts_progress_and_a_red_result_and_saves_one_report(tmp_path, monkeypatch):
    from src.views.dialogs.misc.run_tests_dialog import RunTestsDialog
    dlg = RunTestsDialog(None, workdir=str(_demo(tmp_path)))
    assert dlg.start_button.isEnabled() and not dlg.save_button.isEnabled()
    dlg.start()
    assert dlg.is_running() and dlg.stop_button.isEnabled()
    _wait(dlg)
    assert dlg.reader.counts == {'passed': 2, 'failed': 1, 'skipped': 1, 'error': 0}
    assert dlg.progress.value() == 100
    assert dlg.result_label.text().startswith('1 test failed')
    assert '#c62828' in dlg.result_label.styleSheet()
    assert 'test_demo.py::test_broken FAILED' in dlg.output.toPlainText()
    assert dlg.save_button.isEnabled() and dlg.start_button.text() == 'Run again'
    out = tmp_path / 'report.txt'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', staticmethod(lambda *a, **k: (str(out), '')))
    assert dlg.save_report() == str(out)
    text = out.read_text(encoding='utf-8')
    assert text.startswith('SpecAnalytiXBase test run') and '--- About ---' in text
    assert 'Version' in text and 'test_demo.py::test_ok PASSED' in text
    assert 'Result: 1 test failed' in text
    dlg.copy_report()
    assert QApplication.clipboard().text() == dlg.report_text()
    dlg.close()


def test_all_passing_is_green(tmp_path):
    from src.views.dialogs.misc.run_tests_dialog import RunTestsDialog
    dlg = RunTestsDialog(None, workdir=str(_demo(tmp_path, "def test_a():\n    pass\n")))
    dlg.start()
    _wait(dlg)
    assert dlg.result_label.text() == 'All tests passed: 1 passed.'
    assert '#1a7f37' in dlg.result_label.styleSheet()
    dlg.close()


def test_it_is_a_window_of_its_own_that_can_be_minimized(monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QWidget
    from src.views.dialogs.misc import run_tests_dialog as rtd
    monkeypatch.setattr(rtd, '_open', [])
    main = QWidget()
    dlg = rtd.open_run_tests_dialog(main)
    try:
        assert dlg.parent() is None                       # not kept on top of the main window
        flags = dlg.windowFlags()
        assert flags & Qt.WindowMinimizeButtonHint and flags & Qt.WindowMaximizeButtonHint
        assert not dlg.isModal()
        assert rtd.open_run_tests_dialog(main) is dlg       # one window, raised again
    finally:
        dlg.close()


def test_closing_after_failures_asks_to_save_first(tmp_path, monkeypatch):
    from src.views.dialogs.misc.run_tests_dialog import RunTestsDialog
    dlg = RunTestsDialog(None, workdir=str(_demo(tmp_path)))
    dlg.show()
    dlg.start()
    _wait(dlg)
    asked = []
    monkeypatch.setattr(QMessageBox, 'question',
                        staticmethod(lambda *a, **k: asked.append(a[1]) or QMessageBox.No))
    dlg.reject()                                             # Esc: same as closing
    assert asked == ['Close without saving?'] and dlg.isVisible()
    dlg.copy_report()                                        # copied: no question any more
    dlg.close()
    assert asked == ['Close without saving?'] and not dlg.isVisible()


def test_stop_ends_the_run_and_closing_asks_first(tmp_path, monkeypatch):
    from src.views.dialogs.misc.run_tests_dialog import RunTestsDialog
    dlg = RunTestsDialog(None, workdir=str(_demo(
        tmp_path, "import time\n\ndef test_slow():\n    time.sleep(60)\n")))
    dlg.start()
    end = time.time() + 30
    while 'test_slow' not in dlg.output.toPlainText() and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    asked = []
    monkeypatch.setattr(QMessageBox, 'question',
                        staticmethod(lambda *a, **k: asked.append(a[1]) or QMessageBox.No))
    dlg.close()                                              # "Stop the tests?" No
    assert asked == ['Stop the tests?'] and dlg.is_running()
    dlg.reject()                                             # Esc asks the same
    assert asked == ['Stop the tests?'] * 2 and dlg.is_running()
    dlg.stop()
    _wait(dlg, 20)
    assert dlg.result_label.text().startswith('Stopped by you')
    dlg.close()


def test_about_button_and_help_menu_open_it(monkeypatch):
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import about_dialog, run_tests_dialog
    opened = []
    monkeypatch.setattr(run_tests_dialog, 'open_run_tests_dialog',
                        lambda parent=None: opened.append(parent) or 'window')
    mc = MainController()
    try:
        actions = [a.text() for a in mc.view.menuHelp.actions()]
        assert actions.index('Run tests…') == actions.index('About SpecAnalytiXBase') - 1
        assert mc.view.actionRunTests.isEnabled()
        mc.view.actionRunTests.trigger()
        assert opened == [mc.view]
        about = about_dialog.AboutDialog(mc.view)
        assert about.run_tests_button.isEnabled()
        assert about.run_tests() == 'window' and opened[-1] is mc.view
        monkeypatch.setattr(sys, 'frozen', True, raising=False)
        frozen = about_dialog.AboutDialog(mc.view)               # the installed version
        assert frozen.run_tests_button.isEnabled()
        monkeypatch.setattr(self_test, 'availability',
                            lambda root=None: (False, 'built without the tests'))
        without = about_dialog.AboutDialog(mc.view)
        assert not without.run_tests_button.isEnabled()
        assert 'built without the tests' in without.run_tests_button.toolTip()
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()
