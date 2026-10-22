"""The main window stylesheet: switched-off (disabled) controls look greyed
out, and the selection of a table keeps its colour when the table is not
focused (e.g. after a "Select all" button)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.controllers.core.main_controller import MainController
    controller = MainController()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def test_stylesheet_greys_out_disabled_controls_and_keeps_selection_colour(mc):
    css = mc.view.styleSheet()
    for rule in ('QWidget:disabled', 'QCheckBox::indicator:disabled',
                 'QCheckBox::indicator:checked:disabled', 'QTableView, QTreeView'):
        assert rule in css
