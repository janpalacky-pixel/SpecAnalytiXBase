"""Icons on the buttons of the dialogs (src/views/button_icons.py): chosen by
the button text, not on the main window's buttons, not where the button has
its own icon or a symbol, and taken away again (for the whole row) where the
icon would cut off the text."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QMainWindow,
                             QPushButton, QVBoxLayout, QWidget)

from src.views import button_icons as bi

app = QApplication.instance() or QApplication([])


@pytest.fixture
def installed():
    bi.install(app)
    yield
    bi.uninstall()


def _pump(n=6):
    for _ in range(n):
        app.processEvents()


@pytest.mark.parametrize('text, icon', [
    ('Close', 'std:SP_DialogCloseButton'), ('&Save…', 'std:SP_DialogSaveButton'),
    ('Export CSV...', 'std:SP_DialogSaveButton'), ('Add as New', 'add'), ('Copy', 'copy'),
    ('Copy to Clipboard', 'copy'), ('Copy plot', 'plot'), ('Help', 'help'),
    ('Reset to defaults', 'std:SP_DialogResetButton'), ('Remove Selected', 'std:SP_TrashIcon'),
    ('Load from file…', 'std:SP_DialogOpenButton'), ('Run N times, keep best…', 'run'),
    ('Apply to All Sheets', 'std:SP_DialogApplyButton'), ('Peak list…', 'table'),
    ('Stop', 'stop'), ('Cancel', 'std:SP_DialogCancelButton'),
    ('▶  Run NMF', None), ('💾  Export CSV…', None), ('?', None), ('Select all', None),
    ('Next ▶', None), ('Bootstrap Uncertainty…', None), ('', None)])
def test_icon_for_the_text(text, icon):
    assert bi.icon_name(text) == icon


def test_dialog_buttons_get_icons(installed):
    dlg = QDialog()
    v = QVBoxLayout(dlg)
    close, save, run, select, own = (QPushButton(t) for t in
                                     ('Close', 'Save…', '▶  Run', 'Select all', 'Copy'))
    own.setIcon(QIcon(bi.icons.run_icon()))           # an icon of its own stays
    for b in (close, save, run, select, own):
        v.addWidget(b)
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
    v.addWidget(box)
    dlg.resize(400, 300)
    dlg.show()
    _pump()
    assert close.property('_autoIconName') == 'std:SP_DialogCloseButton'
    assert not close.icon().isNull() and not save.icon().isNull()
    assert run.icon().isNull() and select.icon().isNull()
    assert own.property('_autoIconName') is None and not own.icon().isNull()
    for which in (QDialogButtonBox.Ok, QDialogButtonBox.Cancel, QDialogButtonBox.Apply):
        assert not box.button(which).icon().isNull()
    dlg.close()


def test_not_on_the_main_window(installed):
    win = QMainWindow()
    central = QWidget()
    button = QPushButton('Close', central)
    win.setCentralWidget(central)
    win.show()
    _pump()
    assert button.icon().isNull()
    win.close()


def test_narrow_row_gets_no_icons(installed):
    dlg = QDialog()
    row = QHBoxLayout(dlg)
    buttons = [QPushButton(t) for t in ('Help', 'Apply', 'Add as New', 'Close')]
    buttons[2].setMaximumWidth(60)                     # too narrow for icon + text
    buttons[2].setMinimumWidth(60)
    for b in buttons:
        row.addWidget(b)
    dlg.show()
    _pump(10)
    assert all(b.icon().isNull() for b in buttons)     # the whole row, not some of it
    dlg.close()


def test_text_change_follows(installed):
    dlg = QDialog()
    b = QPushButton('Close')
    QVBoxLayout(dlg).addWidget(b)          # the layout makes the button wider for its icon
    dlg.show()
    _pump()
    assert b.property('_autoIconName') == 'std:SP_DialogCloseButton'
    b.setText('Bootstrap…')
    b.hide()
    b.show()
    _pump()
    assert b.icon().isNull()
    dlg.close()


def test_uninstall():
    bi.install(app)
    bi.uninstall()
    dlg = QDialog()
    b = QPushButton('Close', dlg)
    dlg.show()
    _pump()
    assert b.icon().isNull()
    dlg.close()
