# build_hooks/hook-src.modules.utils.self_test.py
"""PyInstaller hook: puts the program's own tests into the installed version,
so that Help -> Run tests... works there too (src/modules/utils/self_test.py).

Used by the build commands (BuildInstaller.bat and the GitHub workflows) with
--additional-hooks-dir=build_hooks. PyInstaller runs it when it packs
self_test.py, and it adds:
- the tests folder (without __pycache__) and pytest.ini, next to the program's
  other files (_internal), where Run tests runs them;
- every module the tests import (e.g. unittest.mock), which the program itself
  never imports and PyInstaller would otherwise leave out. They are read from
  the tests' import lines, so a new test needs no change here.
pytest itself is packed because self_test.py imports it."""

import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TESTS = os.path.join(_ROOT, 'tests')


def _test_files():
    for folder, dirs, files in os.walk(_TESTS):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for name in files:
            yield os.path.join(folder, name)


def _imported_modules(paths):
    names = set()
    for path in paths:
        try:
            with open(path, encoding='utf-8') as fh:
                tree = ast.parse(fh.read(), path)
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names.add(node.module)
    return names


def _local(name):
    """Modules of the tests or test-data folders themselves (found there when
    the tests run, not packed as modules)."""
    top = name.split('.')[0]
    return top == 'tests' or any(
        os.path.exists(os.path.join(folder, top + '.py'))
        for folder, _d, _f in os.walk(os.path.join(_ROOT, 'resources')))


_py = [p for p in _test_files() if p.endswith('.py')]
_py += [os.path.join(folder, f) for folder, _d, files in os.walk(os.path.join(_ROOT, 'resources'))
        for f in files if f.endswith('.py')]

hiddenimports = sorted(n for n in _imported_modules(_py) if not _local(n))
datas = [(p, os.path.relpath(os.path.dirname(p), _ROOT)) for p in _test_files()]
datas.append((os.path.join(_ROOT, 'pytest.ini'), '.'))
