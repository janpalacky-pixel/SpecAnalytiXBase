"""Every Help topic module must be visible to PyInstaller.

Regression: help_window.py loads topic modules by string via
importlib.import_module(), which PyInstaller's static analysis cannot see.
Twelve topic modules (User Guide, Quick Start, Installation, Developer
Guide, License, Import, Save, Plot controls, Band markers, PCA scores,
QC/outlier, Kinetics fitting) were therefore missing from the installers of
v1.3.0 - v1.4.1: the Help menu entries silently opened nothing, while
everything worked when run from source.

An ``import`` statement anywhere in a module (even inside a function that is
never called) is found by the analysis. help_window.py lists them all in
_declare_help_modules_for_bundlers(); this test makes sure a topic added to
_REGISTRY later is listed there too.
"""

import ast
from pathlib import Path

HELP_WINDOW = Path(__file__).resolve().parent.parent / "src" / "help" / "help_window.py"


def _registry_modules(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "_REGISTRY" for t in node.targets
        ):
            return {v.elts[0].value for v in node.value.values}
    raise AssertionError("_REGISTRY not found in help_window.py")


def _statically_imported_modules(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_every_registered_help_module_is_statically_imported():
    tree = ast.parse(HELP_WINDOW.read_text(encoding="utf-8"))
    registered = _registry_modules(tree)
    assert len(registered) > 40  # sanity: the registry was actually parsed
    missing = sorted(registered - _statically_imported_modules(tree))
    assert not missing, (
        "These help modules are loaded by name only, so PyInstaller would leave "
        "them out of the installer. Add them to _declare_help_modules_for_bundlers() "
        f"in help_window.py: {missing}"
    )


def test_declaration_function_imports_really_resolve():
    # Importing every listed module proves none of the names is misspelled.
    import importlib

    tree = ast.parse(HELP_WINDOW.read_text(encoding="utf-8"))
    for name in _registry_modules(tree):
        importlib.import_module(name)
