"""main.py must stay light at module level so parallel workers start fast.

On Windows (and in the PyInstaller build) every worker process created by
multiprocessing re-runs main.py's top level before doing its task. If that
top level imports PyQt, configures logging or imports the GUI, each worker
repeats all of it: slow start-up, a lot of wasted memory (it can fail with
WinError 1455 "paging file too small" on many-core machines) and one extra
open handle on the log file per worker.
"""
import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = ROOT / "main.py"

_LIGHT_STDLIB = {"sys", "os", "importlib", "multiprocessing"}


def test_main_top_level_imports_only_light_modules():
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    offenders = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            continue
        offenders += [n for n in names if n not in _LIGHT_STDLIB]
    assert not offenders, (
        "main.py imports heavy modules at module level: "
        f"{offenders}. Import them inside main() instead.")


def test_main_calls_freeze_support_under_main_guard():
    src = MAIN_PY.read_text(encoding="utf-8")
    assert "multiprocessing.freeze_support()" in src
    guard = src.index('if __name__ == "__main__":')
    assert src.index("multiprocessing.freeze_support()") > guard
    assert src.index("main()", src.index("multiprocessing.freeze_support()")) > 0


def test_importing_main_loads_neither_qt_nor_the_application():
    """What a spawned worker does: import main as a plain module."""
    code = (
        "import sys; sys.path.insert(0, %r); import main; "
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in "
        "('PyQt5', 'matplotlib', 'pandas', 'src')); "
        "print('LOADED:' + ','.join(bad))" % str(ROOT)
    )
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True,
                         text=True, cwd=str(ROOT), timeout=60)
    assert out.returncode == 0, out.stderr
    loaded = out.stdout.strip().split("LOADED:")[-1]
    assert loaded == "", f"importing main.py pulled in: {loaded}"
