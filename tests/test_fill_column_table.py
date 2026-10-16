"""Spreadsheet-like value column (fill handle, Ctrl+D, copy/paste, Delete,
undo) used for Group Statistics' Group column (fill_column_table.py)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QItemSelection, QItemSelectionModel, QPoint, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from src.views.dialogs.misc.fill_column_table import FillColumnTable

app = QApplication.instance() or QApplication([])


@pytest.fixture
def table():
    t = FillColumnTable([f's{i}' for i in range(10)], ['A', 'B'] + [''] * 8,
                        headers=("Spectrum", "Group"))
    t.resize(400, 600)
    t.show()
    app.processEvents()
    yield t
    t.deleteLater()


def _select(t, first, last, column=1):
    t.clearSelection()
    m = t.model()
    t.selectionModel().select(QItemSelection(m.index(first, column), m.index(last, column)),
                              QItemSelectionModel.Select)


def test_fill_series_repeats_one_value_or_a_pattern(table):
    table.fill_series(0, 0, 3)
    assert table.values()[:5] == ['A', 'A', 'A', 'A', '']
    table.set_values(['A', 'B'] + [''] * 8)
    table.fill_series(0, 1, 6)
    assert table.values()[:8] == ['A', 'B', 'A', 'B', 'A', 'B', 'A', '']


def test_fill_upwards(table):
    table.set_values([''] * 8 + ['X', 'Y'])
    table.fill_series(8, 9, 5)
    assert table.values()[5:] == ['Y', 'X', 'Y', 'X', 'Y']


def test_dragging_the_fill_handle(table):
    _select(table, 0, 0)
    handle = table._handle_rect()
    assert handle is not None
    target = table.visualRect(table.model().index(4, 1)).center()
    QTest.mousePress(table.viewport(), Qt.LeftButton, Qt.NoModifier, handle.center())
    table.mouseMoveEvent(type('E', (), {'pos': lambda self: target, 'accept': lambda self: None,
                                        'buttons': lambda self: Qt.LeftButton})())
    QTest.mouseRelease(table.viewport(), Qt.LeftButton, Qt.NoModifier, target)
    assert table.values()[:6] == ['A'] * 5 + ['']
    assert table.selected_rows() == [0, 1, 2, 3, 4]


def test_ctrl_d_fills_down(table):
    _select(table, 1, 5)
    table.fill_down()
    assert table.values()[:7] == ['A', 'B', 'B', 'B', 'B', 'B', '']


def test_paste_one_value_into_many_rows_and_a_column(table):
    _select(table, 2, 6)
    QApplication.clipboard().setText("treated")
    table.paste_values()
    assert table.values()[2:8] == ['treated'] * 5 + ['']
    _select(table, 0, 0)
    QApplication.clipboard().setText("c1\nc2\r\nc3\n")             # a column from Excel
    table.paste_values()
    assert table.values()[:4] == ['c1', 'c2', 'c3', 'treated']


def test_copy_delete_and_undo(table):
    _select(table, 0, 1)
    table.copy_values()
    assert QApplication.clipboard().text() == "A\nB"
    table.clear_values()
    assert table.values()[:2] == ['', '']
    table.undo()
    assert table.values()[:2] == ['A', 'B']


def test_typing_is_reported_and_undoable(table):
    seen = []
    table.valuesChanged.connect(lambda: seen.append(1))
    table.item(3, 1).setText('typed')
    assert seen and table.values()[3] == 'typed'
    table.undo()
    assert table.values()[3] == ''


def test_names_are_read_only(table):
    assert not (table.item(0, 0).flags() & Qt.ItemIsEditable)


def test_names_cannot_be_selected(table):
    """The Spectrum column is not part of a selection: selecting whole rows
    (or all) marks only the Group cells, and the rows are still known."""
    assert not (table.item(0, 0).flags() & Qt.ItemIsSelectable)
    table.selectAll()
    assert {i.column() for i in table.selectedIndexes()} == {1}
    table.clearSelection()
    table.selectRow(0)
    assert table.selected_rows() == [0]
    assert {i.column() for i in table.selectedIndexes()} == {1}
    table.clear_values()                     # Delete still clears the Group of that row
    assert table.values()[:2] == ['', 'B']
