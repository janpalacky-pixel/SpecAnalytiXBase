"""The File menu with icons and keyboard shortcuts, and the row of buttons
under the menu bar (Import data, Open snapshot, Save, Help), as in
MeltAnalytiX (also icons on the Run, Undo / Redo, History and Refresh Plot
buttons): the buttons, the menu entries and the shortcuts are the same
actions, so they always do the same."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QAction, QApplication, QMessageBox, QShortcut, QToolButton

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


def _spy(action):
    """Replace what the action does by a note of each time it is used."""
    calls = []
    action.triggered.disconnect()
    action.triggered.connect(lambda *a: calls.append(1))
    return calls


def test_file_menu_names_icons_and_shortcuts(mc):
    v = mc.view
    expect = [(v.actionImport_new, 'New…', 'Ctrl+I'),
              (v.actionImport_add, 'Add to current…', 'Ctrl+Shift+I'),
              (v.actionImport_Snapshot, 'Open snapshot…', 'Ctrl+O'),
              (v.actionSave, 'Save…', 'Ctrl+S')]
    for action, text, key in expect:
        assert action.text() == text and action.shortcut().toString() == key
    for action in (v.actionImport_Snapshot, v.actionSave, v.menuImport.menuAction()):
        assert not action.icon().isNull()
    texts = [a.text() for a in v.menuFile.actions() if not a.isSeparator()]
    assert texts[:3] == ['Import data', 'Paste data from clipboard (Excel, text)',
                         'Open snapshot…']
    assert [a.text() for a in v.menuImport.actions()] == ['New…', 'Add to current…']


def test_the_buttons_under_the_menu_bar(mc):
    v = mc.view
    tb = v.mainToolBar
    assert not tb.isMovable() and not tb.toggleViewAction().isVisible()
    buttons = [w for w in tb.findChildren(QToolButton) if w.objectName().startswith('toolbar')]
    assert [b.text() for b in sorted(buttons, key=lambda b: b.x())] == \
        ['Import data', 'Open snapshot', 'Save', 'Help']
    imp = v.toolbarImportButton
    assert imp.menu() is v.menuImport and imp.popupMode() == QToolButton.MenuButtonPopup
    assert 'Ctrl+I' in imp.toolTip()
    assert v.findChild(QToolButton, 'toolbarOpensnapshotButton').toolTip().endswith('[Ctrl+O]')
    assert v.findChild(QToolButton, 'toolbarSaveButton').toolTip().endswith('[Ctrl+S]')
    assert v.toolbarHelpButton.menu() is v.menuHelp


def test_button_and_shortcut_do_the_same_as_the_menu(mc):
    v = mc.view
    new, snap, save = (_spy(a) for a in (v.actionImport_new, v.actionImport_Snapshot,
                                         v.actionSave))
    v.toolbarImportButton.click()
    v.findChild(QToolButton, 'toolbarOpensnapshotButton').click()
    v.findChild(QToolButton, 'toolbarSaveButton').click()
    assert (len(new), len(snap), len(save)) == (1, 1, 1)
    v.show()
    v.activateWindow()
    app.processEvents()
    for key, calls in ((Qt.Key_I, new), (Qt.Key_O, snap), (Qt.Key_S, save)):
        QTest.keyClick(v, key, Qt.ControlModifier)
        app.processEvents()
    assert (len(new), len(snap), len(save)) == (2, 2, 2)
    v.hide()                    # (closing would ask about the unsaved work)


def test_no_keyboard_shortcut_is_used_twice(mc):
    """Each key does one thing: the menu actions and the shortcuts of the
    spectra list (Ctrl+A, Ctrl+C, ...) never share a key."""
    v = mc.view
    keys = [a.shortcut().toString() for a in v.findChildren(QAction) if not a.shortcut().isEmpty()]
    keys += [s.key().toString() for s in v.findChildren(QShortcut)]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, dupes


def test_buttons_and_menu_entries_have_icons(mc):
    v = mc.view
    for button in (v.run_visualization_pushButton, v.parameters_operations_pushButton,
                   v.undo_operations_pushButton, v.redo_operations_pushButton,
                   v.summary_operations_pushButton, mc.refresh_plot_button):
        assert not button.icon().isNull(), button.text()
    assert v.undo_operations_pushButton.text() == 'Undo'          # the arrow is the icon now
    assert v.redo_operations_pushButton.text() == 'Redo'
    for action in v.menuFile.actions():
        if not action.isSeparator() and action.text() != 'Automatic saving':
            assert not action.icon().isNull(), action.text()
