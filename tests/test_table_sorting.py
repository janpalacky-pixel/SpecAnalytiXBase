"""Writing into a table sorted by a click on a heading: Qt sorts it again
after every changed cell of that column, so loops that write row by row
put values into the wrong rows and miss selected cells - unless sorting is
paused (src/views/table_sorting.py). Checked where it happened: Rename
spectra (paste, prefix, suffix, sequential numbers, replace), Melting curve
(Delete / Ctrl+X in the temperature table), Spectrum properties
(tests/test_spectrum_properties.py)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QInputDialog, QMessageBox, QTableWidget,
                             QTableWidgetItem, QTableWidgetSelectionRange as Range)

from src.views.table_sorting import sorting_paused

app = QApplication.instance() or QApplication([])


def test_sorting_paused_keeps_the_rows_and_sorts_once_after():
    t = QTableWidget(5, 2)
    for r, v in enumerate('caebd'):
        t.setItem(r, 0, QTableWidgetItem(v))
        t.setItem(r, 1, QTableWidgetItem(v.upper()))
    t.setSortingEnabled(True)
    t.sortItems(0)                                     # a heading clicked
    with sorting_paused(t):
        for r, v in enumerate('zyxwv'):                # rewrite the sorted column row by row
            t.item(r, 0).setText(v + t.item(r, 1).text())
    pairs = [(t.item(r, 0).text(), t.item(r, 1).text()) for r in range(5)]
    assert all(a[1] == b for a, b in pairs)            # each value stayed in its row
    assert [a for a, _ in pairs] == sorted(a for a, _ in pairs)   # sorted once, after
    assert t.isSortingEnabled()


def _rename(names):
    from src.views.dialogs.misc.rename_spectra_dialog import RenameSpectraDialog
    d = RenameSpectraDialog(None, names)
    d.table.sortItems(1, Qt.DescendingOrder)           # sorted by New Label
    return d


def _pairs(d):
    t = d.table
    return {t.item(r, 0).text(): t.item(r, 1).text() for r in range(t.rowCount())}


def test_rename_prefix_suffix_replace_in_a_sorted_table(monkeypatch):
    names = [f'sp{i:02d}' for i in range(1, 9)]
    d = _rename(names)
    rows = list(range(d.table.rowCount()))
    monkeypatch.setattr(QInputDialog, 'getText', staticmethod(lambda *a, **k: ('X_', True)))
    d.add_prefix(rows)
    assert _pairs(d) == {n: 'X_' + n for n in names}   # every one, each its own name
    monkeypatch.setattr(QInputDialog, 'getText', staticmethod(lambda *a, **k: ('_end', True)))
    d.add_suffix(rows)
    assert _pairs(d) == {n: f'X_{n}_end' for n in names}
    answers = iter([('X_', True), ('', True)])
    monkeypatch.setattr(QInputDialog, 'getText', staticmethod(lambda *a, **k: next(answers)))
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: QMessageBox.Ok))
    d.replace_text(list(range(d.table.rowCount())))
    assert _pairs(d) == {n: f'{n}_end' for n in names}


def test_rename_sequential_numbers_follow_the_rows_shown(monkeypatch):
    names = [f'sp{i:02d}' for i in range(1, 7)]
    d = _rename(names)
    shown = [d.table.item(r, 0).text() for r in range(d.table.rowCount())]   # sp06 ... sp01
    monkeypatch.setattr(QInputDialog, 'getText', staticmethod(lambda *a, **k: ('s_#', True)))
    ints = iter([(1, True), (1, True)])
    monkeypatch.setattr(QInputDialog, 'getInt', staticmethod(lambda *a, **k: next(ints)))
    d.sequential_rename(list(range(d.table.rowCount())))
    assert _pairs(d) == {name: f's_{i + 1}' for i, name in enumerate(shown)}


def test_rename_paste_into_a_sorted_table():
    names = [f'sp{i:02d}' for i in range(1, 7)]
    d = _rename(names)
    shown = [d.table.item(r, 0).text() for r in range(d.table.rowCount())]
    d.table.clearSelection()
    d.table.setRangeSelected(Range(0, 1, 0, 1), True)
    QApplication.clipboard().setText('a1\na2\na3\n')
    from PyQt5.QtWidgets import QShortcut
    from PyQt5.QtGui import QKeySequence
    paste = [s for s in d.table.findChildren(QShortcut) if s.key() == QKeySequence.Paste][0]
    paste.activated.emit()
    pairs = _pairs(d)
    assert [pairs[n] for n in shown[:3]] == ['a1', 'a2', 'a3']   # the rows shown at the top
    assert all(pairs[n] == n for n in shown[3:])                  # the others untouched


def test_melting_curve_delete_in_a_sorted_temperature_table(monkeypatch):
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.views.dialogs.visualization_analysis.melting_curve_dialog import MeltingCurveDialog
    x = np.linspace(220, 320, 101)
    temps = [20.0, 80.0, 35.0, 65.0, 50.0, 95.0]
    spectra = [{'label': f'run {i + 1}', 'x_scale': x, 'metadata': {'temperature_C': t},
                'y_scale': np.exp(-((x - 260) / 10) ** 2) / (1 + np.exp((t - 50) / 5))}
               for i, t in enumerate(temps)]
    d = MeltingCurveDialog(None, spectra)
    t = d.temps_table
    t.sortItems(1, Qt.DescendingOrder)                 # sorted by temperature, highest first
    t.clearSelection()
    t.setRangeSelected(Range(0, 1, 3, 1), True)        # the 4 highest temperatures
    chosen = {t.item(r, 0).text() for r in range(0, 4)}
    d._clear_temps_selection()
    x = {t.item(r, 0).text(): (t.item(r, 1).text() if t.item(r, 1) else '')
         for r in range(t.rowCount())}
    assert {name for name, v in x.items() if v == ''} == chosen   # exactly those
    d.close()
