# src/modules/utils/list_selection.py
"""Select many rows of a QListWidget at once.

Calling item.setSelected(True) once per row costs real Qt work on every
call (blockSignals() only suppresses the signals, not the work): with
21 000 spectra that was 42 s of a frozen window when adding a dataset to
an existing all-selected map. One QItemSelection built from contiguous
row ranges and applied in a single call takes milliseconds. See the
Developer Guide ("Qt Widget Operations: Batch, Don't Loop").
"""

from PyQt5.QtCore import QAbstractItemModel, QItemSelection, QItemSelectionModel

_MODES = {
    'replace': QItemSelectionModel.ClearAndSelect,
    'add': QItemSelectionModel.Select,
    'remove': QItemSelectionModel.Deselect,
}


def row_ranges(rows):
    """Sorted, merged (first, last) ranges of the given row numbers."""
    ranges = []
    for r in sorted(set(int(r) for r in rows)):
        if ranges and r == ranges[-1][1] + 1:
            ranges[-1][1] = r
        else:
            ranges.append([r, r])
    return [tuple(x) for x in ranges]


def select_rows(list_widget, rows, mode='replace'):
    """Select (mode 'replace' or 'add') or deselect ('remove') the given
    rows of a QListWidget in one call. Rows outside the list are ignored.
    'replace' with no rows clears the selection."""
    count = list_widget.count()
    rows = [r for r in rows if 0 <= r < count]
    model = list_widget.model()
    if not isinstance(model, QAbstractItemModel):
        # A stand-in for a real list widget (e.g. a mock in a test): fall
        # back to selecting item by item.
        for r in rows:
            list_widget.item(r).setSelected(mode != 'remove')
        return
    selection = QItemSelection()
    for first, last in row_ranges(rows):
        selection.select(model.index(first, 0), model.index(last, 0))
    if not rows and mode != 'replace':
        return
    list_widget.selectionModel().select(selection, _MODES[mode])
