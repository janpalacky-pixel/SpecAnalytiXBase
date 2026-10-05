"""Tests for Help > About (src/modules/utils/about_info.py, AboutDialog).

Why this feature exists: a source checkout and an installed release look
and behave identically, so a bug report or a "works on my machine, not on
yours" comparison had no way to say which build / which library versions it
was about. The most important test here is the version-consistency one --
the version shown in the app must always equal the one baked into the
installer, or the About box would silently lie about what is installed.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import re
import subprocess
import sys

import pytest
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from src.version import __version__
from src.modules.utils import about_info
from src.views.dialogs.misc.about_dialog import AboutDialog

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_app_version_matches_installer_version():
    """src/version.py and installer.iss must be bumped together; the Release
    workflow separately checks installer.iss against the git tag."""
    iss = open(os.path.join(REPO_ROOT, "installer.iss"), encoding="utf-8").read()
    iss_version = re.search(r'#define MyAppVersion "([^"]+)"', iss).group(1)
    assert __version__ == iss_version


def test_version_looks_like_a_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_info_contains_version_and_libraries():
    info = dict(about_info.get_about_info())
    assert info["Version"] == __version__
    for key in ("Running as", "Python", "Operating system", "Qt bindings",
                "NumPy", "SciPy", "Matplotlib", "pandas", "scikit-learn", "openpyxl"):
        assert key in info and info[key]


def test_running_as_reflects_frozen_state(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert dict(about_info.get_about_info())["Running as"] == "Installed application"
    # An installed copy has no git checkout, so no source-commit line.
    assert "Source commit" not in dict(about_info.get_about_info())

    monkeypatch.delattr(sys, "frozen", raising=False)
    assert dict(about_info.get_about_info())["Running as"] == "Python source code"


def test_missing_git_does_not_break_info(monkeypatch):
    """git absent / failing must only drop the commit line, never crash."""
    def boom(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.delattr(sys, "frozen", raising=False)
    info = dict(about_info.get_about_info())
    assert info["Version"] == __version__
    assert "Source commit" not in info


def test_unimportable_library_is_reported_not_raised(monkeypatch):
    real_import = __import__

    def fake_import(name, *a, **k):
        if name == "scipy":
            raise ImportError("simulated")
        return real_import(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", fake_import)
    libs = dict(about_info._library_versions())
    assert libs["SciPy"] == "not available"
    assert libs["NumPy"] != "not available"


def test_formatted_text_contains_every_line():
    text = about_info.format_about_text()
    assert text.startswith("SpecAnalytiXBase")
    assert __version__ in text
    assert "NumPy" in text


def test_dialog_shows_version_and_copy_button_copies_it():
    dialog = AboutDialog()
    assert __version__ in dialog.details.toPlainText()
    dialog.copy_button.click()
    assert __version__ in QApplication.clipboard().text()
