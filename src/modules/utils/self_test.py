# src/modules/utils/self_test.py
"""Running the program's own test suite from the program (Help -> Run tests...,
Help -> About -> Run tests...), without Qt: whether it is possible here, the
command, and reading pytest's output line by line (progress, counts, result).

The tests run as a separate process -- `python -m pytest tests -v` in the
project folder, with invisible windows (QT_QPA_PLATFORM=offscreen) -- so the
open program and its workspace are never touched; tests/conftest.py also
points the per-user files (automatic saves, preferences) to a temporary
folder. Available when the program runs from its Python source; the
installed (PyInstaller) version contains neither the tests nor pytest."""

import importlib.util
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

_STATUS = re.compile(r'\s(PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)\b')
_PERCENT = re.compile(r'\[\s*(\d{1,3})%\]\s*$')
_SUMMARY = re.compile(r'^=+ (.*\b(?:passed|failed|error|errors|skipped|no tests ran)\b.*) =+$')
_COUNT = re.compile(r'(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|warnings?|deselected)')


def availability(root=PROJECT_ROOT):
    """(True, '') when the tests can be run here, else (False, why)."""
    if getattr(sys, 'frozen', False):
        return False, ("Available when SpecAnalytiXBase runs from its Python source "
                       "(python main.py); the installed version does not contain the tests.")
    if not os.path.isdir(os.path.join(root, 'tests')):
        return False, f"The folder with the tests was not found ({os.path.join(root, 'tests')})."
    if importlib.util.find_spec('pytest') is None:
        return False, "pytest is not installed in this Python (pip install pytest)."
    return True, ''


def command(args=('tests',)):
    """The command line that runs the tests (as a list)."""
    return [sys.executable, '-m', 'pytest', *args, '-v', '--color=no']


def environment():
    """Extra environment variables for the test process."""
    return {'QT_QPA_PLATFORM': 'offscreen',      # no windows pop up
            'PYTHONUNBUFFERED': '1',             # lines arrive as they are printed
            'PYTHONIOENCODING': 'utf-8'}


class OutputReader:
    """Reads pytest -v output line by line: counts of passed / failed /
    skipped / error tests, progress in %, the test running last, and the
    final summary line ("1292 passed, 1 skipped, 564 warnings in 390.18s")."""

    def __init__(self):
        self.counts = {'passed': 0, 'failed': 0, 'skipped': 0, 'error': 0}
        self.percent = 0
        self.current = ''
        self.summary = ''
        self.summary_counts = {}

    def feed(self, line):
        line = line.rstrip('\r\n')
        m = _SUMMARY.match(line.strip())
        if m:
            self.summary = m.group(1).strip()
            self.summary_counts = {}
            for n, word in _COUNT.findall(self.summary):
                word = {'errors': 'error', 'warnings': 'warning'}.get(word, word)
                self.summary_counts[word] = int(n)
            return
        is_test_line = '::' in line and not line.startswith(('FAILED ', 'ERROR '))
        if is_test_line:
            self.current = line.split(' ')[0]
            self._pending = True
        if is_test_line or getattr(self, '_pending', False):
            # the result usually ends the test's own line; when something
            # printed in between (e.g. a maths-library message), it comes
            # at the start of a later line
            s = _STATUS.search(' ' + line)
            if s:
                key = {'XFAIL': 'skipped', 'XPASS': 'passed'}.get(s.group(1), s.group(1).lower())
                self.counts[key] += 1
                self._pending = False
        p = _PERCENT.search(line)
        if p:
            self.percent = min(100, int(p.group(1)))

    def done_tests(self):
        return sum(self.counts.values())

    def result(self, exit_code, stopped=False):
        """(ok, text) for the end of the run."""
        c = self.summary_counts or self.counts
        if stopped:
            return False, f"Stopped by you after {self.done_tests()} tests."
        if exit_code == 0:
            extra = f", {c['skipped']} skipped" if c.get('skipped') else ''
            return True, f"All tests passed: {c.get('passed', 0)} passed{extra}."
        if exit_code == 1 and self.summary:
            bad = c.get('failed', 0) + c.get('error', 0)
            return False, (f"{bad} test{'s' if bad != 1 else ''} failed ({self.summary}). "
                           "Please send the saved output to the developer.")
        return False, (f"The test run ended unexpectedly (exit code {exit_code}) after "
                       f"{self.done_tests()} tests. Please send the saved output to the developer.")


def report(about_text, output, cmd, when):
    """The text saved by 'Save output...': what was run, on which version,
    and pytest's output."""
    return ("SpecAnalytiXBase test run\n"
            f"Date: {when}\n"
            f"Command: {' '.join(cmd)}\n"
            f"Folder: {PROJECT_ROOT}\n\n"
            "--- About ---\n" + about_text.rstrip() + "\n\n"
            "--- Output ---\n" + output)
