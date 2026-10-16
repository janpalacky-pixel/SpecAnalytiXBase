# src/views/dialogs/misc/fill_column_table.py
"""A two-column table (read-only name | editable value) that behaves like a
spreadsheet in its value column, for filling in values for thousands of
spectra quickly (first used for Group Statistics' Group column):

* fill handle: the small square at the bottom-right corner of the selected
  value cells; drag it down (or up) and the selected value(s) are repeated
  into the rows dragged over, like Excel's fill handle (several selected
  cells are repeated as a pattern, e.g. A, B, A, B, ...);
* Ctrl+D: fill down -- the top selected value into all selected rows;
* Ctrl+C / Ctrl+X / Ctrl+V / Delete: copy, cut, paste (e.g. a column copied
  from Excel; one copied value pasted into several selected rows fills them
  all), clear;
* Ctrl+Z: undo the last change (up to 50);
* typing replaces the cell; Enter / double-click edits it.

Optional extra editable columns (extra_columns=[(header, values), ...],
e.g. Group Statistics' Sample column) behave the same; the keyboard actions
and the fill handle work on the column of the current cell. values() /
set_values() / set_rows() act on the first value column unless col= is
given; one undo step covers all columns.
"""

from PyQt5.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QKeySequence, QPainter, QPen
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QShortcut, QTableWidget, QTableWidgetItem)

VALUE_COLUMN = 1
_HANDLE = 8            # size of the fill handle, pixels
_UNDO_LIMIT = 50


class FillColumnTable(QTableWidget):

    # Emitted after any change of the value column (typing, fill, paste, ...)
    valuesChanged = pyqtSignal()

    def __init__(self, names, values=None, headers=("Name", "Value"), parent=None,
                 extra_columns=None):
        extra_columns = list(extra_columns or [])
        super().__init__(len(names), 2 + len(extra_columns), parent)
        self.setHorizontalHeaderLabels(list(headers) + [h for h, _ in extra_columns])
        self._cols = [VALUE_COLUMN] + [2 + i for i in range(len(extra_columns))]
        self.verticalHeader().setVisible(False)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                             | QAbstractItemView.AnyKeyPressed)
        values = list(values) if values is not None else [''] * len(names)
        self.blockSignals(True)
        for r, (name, value) in enumerate(zip(names, values)):
            item = QTableWidgetItem(name)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.setItem(r, 0, item)
            self.setItem(r, VALUE_COLUMN, QTableWidgetItem(value))
        for i, (_, col_values) in enumerate(extra_columns):
            col_values = list(col_values) if col_values is not None else [''] * len(names)
            for r in range(len(names)):
                self.setItem(r, 2 + i, QTableWidgetItem(col_values[r] if r < len(col_values)
                                                        else ''))
        self.blockSignals(False)
        self._mirror = self._snapshot()
        self._undo = []
        self._fill = None              # (first source row, last source row, target row) while dragging
        self.viewport().setMouseTracking(True)
        self.itemChanged.connect(self._on_item_changed)
        for keys, slot in ((QKeySequence.Copy, self.copy_values),
                           (QKeySequence.Cut, self.cut_values),
                           (QKeySequence.Paste, self.paste_values),
                           (QKeySequence.Delete, self.clear_values),
                           (QKeySequence.Undo, self.undo),
                           (QKeySequence("Ctrl+D"), self.fill_down)):
            shortcut = QShortcut(keys, self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

    # ------------------------------------------------------------------ values
    def values(self, col=VALUE_COLUMN):
        return [self.item(r, col).text() for r in range(self.rowCount())]

    def _snapshot(self):
        return {c: self.values(c) for c in self._cols}

    def set_values(self, values, record_undo=True, col=VALUE_COLUMN):
        """Replace all values of one column at once (one undo step)."""
        if record_undo:
            self._push_undo()
        self.blockSignals(True)
        for r, v in enumerate(values):
            if r < self.rowCount():
                self.item(r, col).setText(v)
        self.blockSignals(False)
        self._mirror = self._snapshot()
        self.viewport().update()
        self.valuesChanged.emit()

    def set_rows(self, rows, value, col=VALUE_COLUMN):
        values = self.values(col)
        for r in rows:
            values[r] = value
        self.set_values(values, col=col)

    def _push_undo(self, snapshot=None):
        snap = snapshot if snapshot is not None else self._mirror
        self._undo.append({c: list(v) for c, v in snap.items()})
        del self._undo[:-_UNDO_LIMIT]

    def undo(self):
        if self._undo:
            snap = self._undo.pop()
            self.blockSignals(True)
            for c, vals in snap.items():
                for r, v in enumerate(vals):
                    if r < self.rowCount():
                        self.item(r, c).setText(v)
            self.blockSignals(False)
            self._mirror = self._snapshot()
            self.viewport().update()
            self.valuesChanged.emit()

    def _on_item_changed(self, item):
        if item.column() not in self._cols:
            return
        self._push_undo()
        self._mirror = self._snapshot()
        self.valuesChanged.emit()

    def active_column(self):
        """The editable column the keyboard actions / fill handle work on:
        that of the current cell, else the first value column."""
        c = self.currentColumn()
        return c if c in self._cols else VALUE_COLUMN

    def selected_rows(self):
        return sorted({i.row() for i in self.selectedIndexes()})

    def _value_selection(self):
        """Rows of the selected cells in the value column (any selected cell
        of a row counts for that row)."""
        return self.selected_rows()

    # ------------------------------------------------------------------ keyboard actions
    def copy_values(self):
        rows = self.selected_rows()
        col = self.active_column()
        if rows:
            QApplication.clipboard().setText("\n".join(self.item(r, col).text()
                                                       for r in rows))

    def cut_values(self):
        self.copy_values()
        self.clear_values()

    def clear_values(self):
        rows = self.selected_rows()
        if rows:
            self.set_rows(rows, '', col=self.active_column())

    def paste_values(self):
        text = QApplication.clipboard().text()
        if text is None:
            return
        lines = text.replace('\r', '').split('\n')
        while lines and lines[-1] == '':
            lines.pop()
        tokens = [ln.split('\t')[-1].strip() if '\t' in ln else ln.strip() for ln in lines]
        if not tokens:
            return
        rows = self.selected_rows()
        col = self.active_column()
        values = self.values(col)
        if len(tokens) == 1 and len(rows) > 1:
            for r in rows:                     # one value into all selected rows
                values[r] = tokens[0]
        else:
            start = rows[0] if rows else max(self.currentRow(), 0)
            for i, token in enumerate(tokens):
                if start + i < len(values):
                    values[start + i] = token
        self.set_values(values, col=col)

    def fill_down(self):
        rows = self.selected_rows()
        col = self.active_column()
        if len(rows) > 1:
            self.set_rows(rows[1:], self.item(rows[0], col).text(), col=col)

    # ------------------------------------------------------------------ fill handle
    def _source_rows(self):
        rows = self.selected_rows()
        if not rows:
            return None
        return rows[0], rows[-1]

    def _handle_rect(self):
        src = self._source_rows()
        if src is None:
            return None
        cell = self.visualRect(self.model().index(src[1], self.active_column()))
        if not cell.isValid() or cell.isEmpty():
            return None
        corner = cell.bottomRight()
        return QRect(corner.x() - _HANDLE + 2, corner.y() - _HANDLE + 2, _HANDLE, _HANDLE)

    def _on_handle(self, pos):
        rect = self._handle_rect()
        return rect is not None and rect.adjusted(-3, -3, 3, 3).contains(pos)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        rect = self._handle_rect()
        if rect is not None:
            painter.fillRect(rect, QColor('#1B5E20'))
            painter.setPen(QPen(QColor('white'), 1))
            painter.drawRect(rect.adjusted(-1, -1, 0, 0))
        if self._fill is not None:
            first, last, target = self._fill
            lo, hi = min(first, target), max(last, target)
            col = self.active_column()
            top = self.visualRect(self.model().index(lo, col))
            bottom = self.visualRect(self.model().index(hi, col))
            painter.setPen(QPen(QColor('#1B5E20'), 2, Qt.DashLine))
            painter.drawRect(QRect(top.topLeft(), bottom.bottomRight()).adjusted(1, 1, -1, -1))
        painter.end()

    def _row_at(self, pos):
        row = self.rowAt(pos.y())
        if row < 0:
            row = self.rowCount() - 1 if pos.y() > 0 else 0
        return row

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_handle(event.pos()):
            first, last = self._source_rows()
            self._fill = (first, last, last)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._fill is not None:
            first, last, _ = self._fill
            pos = event.pos()
            bar = self.verticalScrollBar()
            if pos.y() > self.viewport().height() - 10:
                bar.setValue(bar.value() + 1)              # scroll while dragging
            elif pos.y() < 10:
                bar.setValue(bar.value() - 1)
            self._fill = (first, last, self._row_at(pos))
            self.viewport().update()
            event.accept()
            return
        self.viewport().setCursor(Qt.CrossCursor if self._on_handle(event.pos())
                                  else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._fill is not None:
            first, last, target = self._fill
            self._fill = None
            self.fill_series(first, last, target)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def fill_series(self, first, last, target):
        """Repeat the values of rows first..last into the rows up to
        target (below or above), like dragging Excel's fill handle."""
        col = self.active_column()
        pattern = [self.item(r, col).text() for r in range(first, last + 1)]
        values = self.values(col)
        if target > last:
            rows = range(last + 1, target + 1)
            for k, r in enumerate(rows):
                values[r] = pattern[k % len(pattern)]
            lo, hi = first, target
        elif target < first:
            rows = range(first - 1, target - 1, -1)
            for k, r in enumerate(rows):
                values[r] = pattern[-1 - (k % len(pattern))]
            lo, hi = target, last
        else:
            self.viewport().update()
            return
        self.set_values(values, col=col)
        self.clearSelection()
        top, bottom = self.model().index(lo, col), self.model().index(hi, col)
        from PyQt5.QtCore import QItemSelection, QItemSelectionModel
        self.selectionModel().select(QItemSelection(top, bottom), QItemSelectionModel.Select)
