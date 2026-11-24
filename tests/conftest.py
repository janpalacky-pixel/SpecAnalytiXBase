# tests/conftest.py
#
# Shared fixtures available to all test files automatically.
# pytest loads this file before running any tests.

import numpy as np
import pytest
import os
import sys
import tempfile


# ---------------------------------------------------------------------------
# In the installed version (Help -> Run tests... of SpecAnalytiXBase.exe)
# ---------------------------------------------------------------------------
# These tests check the program's source and build files (main.py, the source
# code in src/, installer.iss): they make sure the program is written and
# built correctly. The installed version does not contain those files, so
# there they are skipped (test_installer_script.py is not even read: it opens
# installer.iss as soon as it is loaded).

SOURCE_FILE_CHECKS = {
    # file: the tests that read source files (None = all tests of the file)
    'test_installer_script.py': None,
    'test_tests_in_installed_version.py': {
        'test_the_build_puts_the_tests_and_what_they_import_into_the_installed_version',
        'test_every_build_command_uses_the_hook'},
    'test_main_worker_safe.py': None,
    'test_help_modules_bundled.py': None,
    'test_operation_errors_are_logged.py': None,
    'test_about_info.py': {'test_app_version_matches_installer_version'},
    'test_methods_report.py': {'test_every_operation_in_the_app_is_described'},
    'test_version_info.py': None,
}
_SOURCE_ONLY_REASON = ("checks the program's source files, which the installed version "
                       "does not contain")

collect_ignore = ['test_installer_script.py'] if getattr(sys, 'frozen', False) else []


def pytest_collection_modifyitems(config, items):
    if not getattr(sys, 'frozen', False):
        return
    skip = pytest.mark.skip(reason=_SOURCE_ONLY_REASON)
    for item in items:
        file = os.path.basename(str(item.fspath))
        if file in SOURCE_FILE_CHECKS:
            names = SOURCE_FILE_CHECKS[file]
            if names is None or getattr(item, 'originalname', item.name) in names:
                item.add_marker(skip)


# ---------------------------------------------------------------------------
# Never touch the user's real per-user files while testing
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope='session')
def _isolated_app_data_dir(tmp_path_factory):
    """Point the app's per-user folder (automatic saves, the Open recent
    list, preferences -- see src/modules/misc/session_files.py) at a
    temporary folder for the whole test run, so running the tests never
    changes the real ones."""
    old = os.environ.get('SPECANALYTIXBASE_DATA_DIR')
    os.environ['SPECANALYTIXBASE_DATA_DIR'] = str(tmp_path_factory.mktemp('app_data'))
    yield
    if old is None:
        os.environ.pop('SPECANALYTIXBASE_DATA_DIR', None)
    else:
        os.environ['SPECANALYTIXBASE_DATA_DIR'] = old


# ---------------------------------------------------------------------------
# Basic data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_spectrum():
    """A single well-formed spectrum dict."""
    return {
        'label': 'test : 0001',
        'x_scale': np.array([100.0, 200.0, 300.0, 400.0, 500.0]),
        'y_scale': np.array([1.5, 2.5, 3.5, 2.0, 1.0]),
        'metadata': {'file_path': 'test.txt', 'valid_points': 5},
    }


@pytest.fixture
def three_spectra():
    """Three spectra sharing the same x-scale."""
    x = np.linspace(100.0, 500.0, 20)
    return [
        {
            'label': f'test : 000{i}',
            'x_scale': x.copy(),
            'y_scale': np.random.rand(20) * (i + 1),
            'metadata': {'file_path': 'test.txt'},
        }
        for i in range(1, 4)
    ]


@pytest.fixture
def spectra_different_scales():
    """Two spectra with different x-scales (for interlaced save tests)."""
    return [
        {
            'label': 'spec_A',
            'x_scale': np.linspace(100.0, 500.0, 10),
            'y_scale': np.random.rand(10),
            'metadata': {},
        },
        {
            'label': 'spec_B',
            'x_scale': np.linspace(200.0, 800.0, 15),
            'y_scale': np.random.rand(15),
            'metadata': {},
        },
    ]


# ---------------------------------------------------------------------------
# File fixtures — temporary files that are cleaned up after each test
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_txt(tmp_path):
    """Return a path to a temporary .txt file (not yet created)."""
    return str(tmp_path / 'test_spectra.txt')


@pytest.fixture
def tmp_xlsx(tmp_path):
    """Return a path to a temporary .xlsx file (not yet created)."""
    return str(tmp_path / 'test_spectra.xlsx')


@pytest.fixture
def tmp_snapx(tmp_path):
    """Return a path to a temporary .snapx file (not yet created)."""
    return str(tmp_path / 'test_snapshot.snapx')


# ---------------------------------------------------------------------------
# Pre-built sample text file fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tab_dot_file(tmp_path):
    """
    A tab-separated, dot-decimal file with header.
    Layout: x_scale | spec_A | spec_B | spec_C
    """
    content = (
        "x_scale\tspec_A\tspec_B\tspec_C\n"
        "100.0\t1.23\t4.56\t7.89\n"
        "200.0\t2.34\t5.67\t8.90\n"
        "300.0\t3.45\t6.78\t9.01\n"
        "400.0\t4.56\t7.89\t0.12\n"
        "500.0\t5.67\t8.90\t1.23\n"
    )
    path = tmp_path / 'tab_dot.txt'
    path.write_text(content, encoding='utf-8')
    return str(path)


@pytest.fixture
def semicolon_comma_file(tmp_path):
    """
    A semicolon-separated, comma-decimal file with header.
    Simulates European locale export.
    """
    content = (
        "x_scale;spec_A;spec_B\n"
        "100,0;1,23;4,56\n"
        "200,0;2,34;5,67\n"
        "300,0;3,45;6,78\n"
    )
    path = tmp_path / 'semi_comma.txt'
    path.write_text(content, encoding='utf-8')
    return str(path)


@pytest.fixture
def no_header_file(tmp_path):
    """Tab-separated, dot-decimal file WITHOUT a header row."""
    content = (
        "100.0\t1.23\t4.56\n"
        "200.0\t2.34\t5.67\n"
        "300.0\t3.45\t6.78\n"
    )
    path = tmp_path / 'no_header.txt'
    path.write_text(content, encoding='utf-8')
    return str(path)


@pytest.fixture
def single_spectrum_file(tmp_path):
    """File with exactly one spectrum (2 columns: x and y)."""
    content = (
        "x_scale\tintensity\n"
        "100.0\t10.5\n"
        "200.0\t20.3\n"
        "300.0\t15.7\n"
    )
    path = tmp_path / 'single.txt'
    path.write_text(content, encoding='utf-8')
    return str(path)


# ---------------------------------------------------------------------------
# At the top of every run: are the libraries those of the GitHub build?
# (tools/check_libraries.py: "Libraries OK" or "WARNING - LIBRARIES DIFFER")
# ---------------------------------------------------------------------------
def pytest_report_header(config):
    if getattr(sys, 'frozen', False):
        return None
    try:
        import importlib.util
        path = os.path.join(str(config.rootpath), 'tools', 'check_libraries.py')
        spec = importlib.util.spec_from_file_location('_check_libraries', path)
        cl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cl)
        lines, _ = cl.check(cl.read_requirements(), wanted_python=cl.github_python())
        return ['Compared with requirements.txt and the GitHub build:'] + lines
    except Exception as exc:
        return 'Library check not possible: %s' % exc


# ---------------------------------------------------------------------------
# Log of the last test run: tools/logs/tests_last_run.txt
# Written by these hooks however the tests are started (pytest in a terminal,
# the desktop shortcut "Run tests", VS Code's Testing panel). One line per test,
# written as it goes - so even a run that stops suddenly shows the last test -
# then the errors of the failed tests and the totals.
# ---------------------------------------------------------------------------
import datetime as _rl_dt
import platform as _rl_platform
import sys as _rl_sys

_rl = {'file': None, 'counts': {}, 'errors': []}


def pytest_sessionstart(session):
    if getattr(_rl_sys, 'frozen', False) or hasattr(session.config, 'workerinput'):
        return
    try:
        folder = session.config.rootpath / 'tools' / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        fh = open(folder / 'tests_last_run.txt', 'w', encoding='utf-8')
        fh.write('Test run %s\nPython %s  %s\nCommand: pytest %s\n\n' % (
            _rl_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), _rl_platform.python_version(),
            _rl_sys.executable, ' '.join(session.config.invocation_params.args)))
        fh.flush()
        _rl['file'] = fh
    except Exception:
        _rl['file'] = None


def pytest_runtest_logstart(nodeid, location):
    if _rl['file']:
        _rl['file'].write(nodeid + ' ... ')
        _rl['file'].flush()


def pytest_runtest_logreport(report):
    fh = _rl['file']
    if not fh:
        return
    if report.when == 'call' or (report.when == 'setup' and not report.passed):
        word = 'ERROR' if (report.when == 'setup' and report.failed) else report.outcome.upper()
        fh.write('%s (%.2f s)\n' % (word, report.duration))
        _rl['counts'][word] = _rl['counts'].get(word, 0) + 1
    elif report.when == 'teardown' and report.failed:
        fh.write('    ERROR after the test (teardown)\n')
        _rl['counts']['ERROR'] = _rl['counts'].get('ERROR', 0) + 1
    if report.failed:
        _rl['errors'].append((report.nodeid, report.when, report.longreprtext))
    fh.flush()


def pytest_sessionfinish(session, exitstatus):
    fh = _rl['file']
    if not fh:
        return
    for nodeid, when, text in _rl['errors']:
        fh.write('\n' + '=' * 70 + '\n%s  (%s)\n%s\n' % (nodeid, when, text))
    totals = ', '.join('%d %s' % (n, w.lower()) for w, n in sorted(_rl['counts'].items()))
    fh.write('\nFinished %s: %s (exit status %s)\n' % (
        _rl_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), totals or 'no tests', int(exitstatus)))
    fh.close()
    _rl['file'] = None


# ---------------------------------------------------------------------------
# An error in a Qt slot (a button, a timer, a redraw) does not stop the test
# that caused it: PyQt hands it to sys.excepthook - by default printed and lost
# in the output, or (PyQt 5.5+) ending the whole test run without a word. Here
# every test gets a hook that keeps such an error WITH ITS TRACEBACK (file and
# line), and the test fails at its end showing it. A test that installs its own
# hook (monkeypatch.setattr(sys, 'excepthook', ...)) replaces this one for
# itself - and should keep the traceback too (traceback.format_exception).
# Errors of the test itself (an assert, an exception in the test code) are
# shown with their lines by pytest anyway (--tb=short in pytest.ini).
# ---------------------------------------------------------------------------
import traceback as _qt_tb


@pytest.fixture(autouse=True)
def _errors_in_qt_slots(monkeypatch):
    errors = []

    def hook(etype, value, tb):
        errors.append(''.join(_qt_tb.format_exception(etype, value, tb)))
    monkeypatch.setattr(sys, 'excepthook', hook)
    yield errors
    if errors:
        pytest.fail('%d error(s) in a Qt slot (button, timer, redraw) during this test; '
                    'the first:\n%s' % (len(errors), errors[0]), pytrace=False)
