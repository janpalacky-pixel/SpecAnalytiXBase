"""Help -> Run tests... also in the installed version: the build puts the
tests, pytest.ini and every module the tests import into it
(build_hooks/hook-src.modules.utils.self_test.py, used by every build
command), and the tests that check the program's source files are skipped
there (SOURCE_FILE_CHECKS in tests/conftest.py)."""
import os
import re
import runpy
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, 'build_hooks', 'hook-src.modules.utils.self_test.py')


def test_the_build_puts_the_tests_and_what_they_import_into_the_installed_version():
    hook = runpy.run_path(HOOK)
    hidden = set(hook['hiddenimports'])
    assert {'unittest.mock', 'pytest', 'numpy', 'PyQt5.QtWidgets'} <= hidden
    assert not any(n.split('.')[0] in ('tests', 'generate_unmixing_test_dataset') for n in hidden)
    dest = {os.path.relpath(src, ROOT).replace(os.sep, '/'): d.replace(os.sep, '/')
            for src, d in hook['datas']}
    assert dest['tests/conftest.py'] == 'tests' and dest['pytest.ini'] == '.'
    assert dest['tests/test_tests_in_installed_version.py'] == 'tests'
    assert not any('__pycache__' in s for s in dest)


@pytest.mark.parametrize('path', ['BuildInstaller.bat', '.github/workflows/release-build.yml',
                                  '.github/workflows/nightly-build.yml'])
def test_every_build_command_uses_the_hook(path):
    text = open(os.path.join(ROOT, path), encoding='utf-8').read()
    commands = re.findall(r'pyinstaller\b[^\n]*(?:\n\s+--[^\n]*|\n\s+main\.py[^\n]*)*', text)
    commands = [c for c in commands if 'main.py' in c]
    assert commands, path
    assert all('--additional-hooks-dir=build_hooks' in c for c in commands), path


def test_the_source_file_checks_exist():
    """SOURCE_FILE_CHECKS (conftest.py) names real files and tests, so a
    renamed test is not silently run -- and failing -- in the installed version."""
    from tests import conftest
    for file, names in conftest.SOURCE_FILE_CHECKS.items():
        text = open(os.path.join(ROOT, 'tests', file), encoding='utf-8').read()
        for name in names or ():
            assert f'def {name}(' in text, (file, name)


def test_in_the_installed_version_they_are_skipped(monkeypatch):
    from tests import conftest
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    items = []
    for file, name in [('test_about_info.py', 'test_app_version_matches_installer_version'),
                       ('test_about_info.py', 'test_version_looks_like_a_version'),
                       ('test_main_worker_safe.py', 'test_anything')]:
        item = types.SimpleNamespace(fspath=os.path.join(ROOT, 'tests', file), name=name,
                                     originalname=name, marks=[])
        item.add_marker = item.marks.append
        items.append(item)
    conftest.pytest_collection_modifyitems(None, items)
    assert [bool(i.marks) for i in items] == [True, False, True]
    monkeypatch.setattr(sys, 'frozen', False)
    items[1].marks.clear()
    conftest.pytest_collection_modifyitems(None, items[1:2])
    assert not items[1].marks
