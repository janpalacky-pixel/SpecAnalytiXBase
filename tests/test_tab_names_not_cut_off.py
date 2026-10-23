"""The name of the open tab is not cut off (e.g. "Band table" in the Peak
list): Qt measures every tab with the font of the normal tab, so the open
tab's look in the program's stylesheet may change colours only - not the
font (bold, size) nor anything else that changes the size."""
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])

SIZE_PROPERTIES = ('font', 'padding', 'margin', 'min-width', 'max-width', 'width',
                   'min-height', 'height', 'border-width', 'border-top-width',
                   'border-left-width', 'border-right-width')
BORDER_SHORTHANDS = ('border', 'border-top', 'border-left', 'border-right')   # include a width


@pytest.fixture(scope='module')
def stylesheet(tmp_path_factory):
    os.environ['SPECANALYTIXBASE_DATA_DIR'] = str(tmp_path_factory.mktemp('appdata'))
    mp = pytest.MonkeyPatch()
    for name in ('information', 'warning', 'critical'):
        mp.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    controller = MainController()
    css = controller.view.styleSheet()
    yield css
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()
    mp.undo()


def _state_rules(css):
    """{selector: body} of the QTabBar::tab rules with a state (:selected, ...)."""
    return {m.group(1).strip(): m.group(2)
            for m in re.finditer(r'(QTabBar::tab:[^{]+)\{([^}]*)\}', css)}


def test_there_is_a_look_for_the_open_tab(stylesheet):
    assert any(':selected' in sel for sel in _state_rules(stylesheet))


def test_the_open_tab_changes_colours_only(stylesheet):
    for selector, body in _state_rules(stylesheet).items():
        names = [p.split(':')[0].strip() for p in body.split(';') if ':' in p]
        changed = [n for n in names if n.startswith(SIZE_PROPERTIES) or n in BORDER_SHORTHANDS]
        assert not changed, f"{selector} changes {changed}: the tab name could be cut off"

