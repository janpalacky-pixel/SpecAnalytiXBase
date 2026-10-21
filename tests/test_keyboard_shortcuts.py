"""Help -> Keyboard shortcuts... and the table in the User Guide come from
one list (src/modules/misc/keyboard_shortcuts.py). The main window's and the
spectra list's shortcuts must all be in it, and everything it lists for them
must really exist - so the list cannot silently go out of date."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QAction, QApplication, QMessageBox, QShortcut

from src.modules.misc import keyboard_shortcuts as ks

app = QApplication.instance() or QApplication([])


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    controller = MainController()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def test_the_list_matches_the_program(mc):
    v = mc.view
    in_program = {a.shortcut().toString() for a in v.findChildren(QAction) if not a.shortcut().isEmpty()}
    in_program |= {s.key().toString() for s in v.findChildren(QShortcut)}
    from PyQt5.QtGui import QKeySequence           # as Qt writes them ('Delete' -> 'Del')
    listed = {QKeySequence(keys).toString() for where, keys, _ in ks.SHORTCUTS
              if where in ks.GROUPS_CHECKED and 'click' not in keys}
    assert in_program - listed == set(), "shortcuts missing from keyboard_shortcuts.py"
    assert listed - in_program == set(), "listed, but not in the program"


def test_help_menu_window_and_user_guide(mc):
    v = mc.view
    texts = [a.text() for a in v.menuHelp.actions()]
    assert texts.index('Keyboard shortcuts…') == texts.index("What's New") + 1
    win = mc.show_keyboard_shortcuts()
    text = win.text.toPlainText()
    for where, keys, what in ks.SHORTCUTS:
        assert keys in text and what in text and where in text
    win.close()
    guide = __import__('src.help.user_guide_help', fromlist=['x']).get_user_guide_help_content()
    assert '$SHORTCUTS_TABLE' not in guide and 'Ctrl+Shift+I' in guide and 'id="keyboard"' in guide
