import sys
import os
import importlib.util

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QIcon

from src.modules.utils.app_logger import configure_logging, enable_crash_diagnostics
from src.modules.utils.resource_path import resource_path

# Configure logging before importing anything else
configure_logging()

# Arm faulthandler so a true native crash (not a catchable Python
# exception) still leaves a diagnostic trace instead of the process just
# disappearing with no output at all. See enable_crash_diagnostics()'s
# docstring for why this is a separate safety net from the sys.excepthook
# configure_logging() already installs.
enable_crash_diagnostics()


# Packages the application cannot start without, beyond PyQt5 itself (already
# imported above — if PyQt5 is missing, nothing here could show a Qt dialog
# about it anyway, so that one failure mode is unavoidable and left as a
# plain Python traceback). Checked with importlib.util.find_spec rather than
# actually importing each one, so this stays cheap and doesn't trigger the
# heavy import chain these packages pull in themselves.
#
# This list — and the fact that each one is genuinely required at startup,
# not just for one specific feature — was confirmed by scanning every import
# in src/ and this file, then empirically verifying the application's import
# chain actually fails without each one. See requirements.txt for the same
# list with an explanation of what each package is used for.
_REQUIRED_PACKAGES = [
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("matplotlib", "matplotlib"),
    ("pandas", "pandas"),
    ("sklearn", "scikit-learn"),
]


def _missing_required_packages() -> list:
    """Return [(import_name, pip_name), ...] for any required package that
    isn't installed. Checked BEFORE importing the rest of the application —
    a missing package deep inside that import chain would otherwise surface
    as a raw traceback (or, in the --windowed PyInstaller build, no visible
    error at all: no console exists to print a traceback to)."""
    missing = []
    for import_name, pip_name in _REQUIRED_PACKAGES:
        if importlib.util.find_spec(import_name) is None:
            missing.append((import_name, pip_name))
    return missing


def _fail_with_missing_packages(missing: list) -> None:
    """Show a clear message box naming exactly what's missing and how to
    install it, then exit — instead of letting the application crash into
    an unreadable traceback the user has no way to act on."""
    app = QApplication.instance() or QApplication(sys.argv)
    lines = "\n".join(f"  • {imp}  (pip install {pkg})" for imp, pkg in missing)
    pip_names = " ".join(pkg for _, pkg in missing)
    QMessageBox.critical(
        None,
        "Missing Required Packages",
        "SpecAnalytiXBase cannot start because the following required "
        f"Python package(s) are not installed:\n\n{lines}\n\n"
        "Install everything this application needs with:\n\n"
        "    pip install -r requirements.txt\n\n"
        "or install just the missing package(s) with:\n\n"
        f"    pip install {pip_names}\n\n"
        "See INSTALLATION.txt at the project root, or Help -> Installation "
        "once the application is running, for the full setup guide."
    )
    sys.exit(1)


_missing = _missing_required_packages()
if _missing:
    _fail_with_missing_packages(_missing)

from src.controllers.core.main_controller import MainController


def _check_optional_dependencies() -> None:
    """
    Check optional dependencies and warn the user if any are missing.
    Called once at startup before the main window appears.

    Unlike _REQUIRED_PACKAGES above, every import of these packages in the
    codebase is deferred (inside a function, only when that function
    actually runs) — the application starts and runs fine without them;
    only the specific feature that needs one is unavailable until it's
    installed.
    """
    missing = []

    try:
        import openpyxl
    except ImportError:
        missing.append(
            "• openpyxl — required for Excel (.xlsx) import and export\n"
            "  Install with:  pip install openpyxl"
        )

    if missing:
        QMessageBox.warning(
            None,
            "Optional Dependencies Missing",
            "The following optional packages are not installed.\n"
            "Some features will be unavailable until they are installed.\n\n"
            + "\n\n".join(missing)
        )


def main():
    app = QApplication(sys.argv)
    icon_path = resource_path(os.path.join('resources', 'icons', 'app_icon.ico'))
    app.setWindowIcon(QIcon(icon_path))

    _check_optional_dependencies()

    main_controller = MainController()
    main_controller.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
