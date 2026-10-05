# src/modules/utils/about_info.py
"""
Collects "what exactly am I running?" information for Help > About:
application version, whether this is the installed (frozen) application or
a source checkout, and the Python / library versions it is running on.

Why this exists: a source checkout and an installed release look and behave
identically, so without this there is no way to tell which build (or which
library versions) a bug report or a "works on my machine" comparison refers
to. Every lookup is best-effort -- a missing library or an unavailable git
must never stop the About dialog from opening.
"""

import os
import platform
import subprocess
import sys

from src.version import __version__


def is_frozen():
    """True when running as the PyInstaller-built (installed) application."""
    return bool(getattr(sys, "frozen", False))


def _repo_root():
    # src/modules/utils/about_info.py -> repository root is four levels up.
    here = os.path.abspath(__file__)
    for _ in range(4):
        here = os.path.dirname(here)
    return here


def _git_info(repo_root):
    """Return (short_commit, has_uncommitted_changes) for a source checkout,
    or None if this is not a git checkout or git is unavailable."""
    if not os.path.isdir(os.path.join(repo_root, ".git")):
        return None
    kwargs = dict(cwd=repo_root, capture_output=True, text=True, timeout=3)
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW: no console flash
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], **kwargs)
        if commit.returncode != 0 or not commit.stdout.strip():
            return None
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"], **kwargs)
        dirty = status.returncode == 0 and bool(status.stdout.strip())
        return commit.stdout.strip(), dirty
    except Exception:
        return None


def _library_versions():
    """(name, version) for the libraries the app depends on. Uses each
    module's own __version__ rather than importlib.metadata, because package
    metadata is not reliably present inside a PyInstaller bundle."""
    out = []

    def add(name, getter):
        try:
            out.append((name, str(getter())))
        except Exception:
            out.append((name, "not available"))

    def qt():
        from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
        return "PyQt5 %s (Qt %s)" % (PYQT_VERSION_STR, QT_VERSION_STR)

    def lib(module_name):
        def _get():
            return __import__(module_name).__version__
        return _get

    add("Qt bindings", qt)
    add("NumPy", lib("numpy"))
    add("SciPy", lib("scipy"))
    add("Matplotlib", lib("matplotlib"))
    add("pandas", lib("pandas"))
    add("scikit-learn", lib("sklearn"))
    add("openpyxl", lib("openpyxl"))
    return out


def get_about_info():
    """Ordered list of (label, value) pairs describing this running copy."""
    info = [("Version", __version__)]

    if is_frozen():
        info.append(("Running as", "Installed application"))
    else:
        info.append(("Running as", "Python source code"))
        git = _git_info(_repo_root())
        if git:
            commit, dirty = git
            info.append(("Source commit",
                         commit + (" (with uncommitted changes)" if dirty else "")))

    info.append(("Python", "%s (%s)" % (platform.python_version(),
                                         platform.architecture()[0])))
    info.append(("Operating system", platform.platform()))
    info.extend(_library_versions())
    return info


def format_about_text(info=None):
    """Plain-text rendering, suitable for pasting into a bug report."""
    info = get_about_info() if info is None else info
    width = max(len(label) for label, _ in info)
    lines = ["SpecAnalytiXBase"]
    lines += ["%s : %s" % (label.ljust(width), value) for label, value in info]
    return "\n".join(lines)
