"""Spectrum properties > Add property...: a small window with suggestions;
Add is possible only for a good name and what is wrong is shown at once
(no warning afterwards); after adding, the window says what to do next."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

app = QApplication.instance() or QApplication([])


def _window():
    from src.views.dialogs.misc.spectrum_properties_dialog import SpectrumPropertiesDialog
    x = np.linspace(0, 1, 5)
    spectra = [{'label': f'raman_2comp_clean : raman_{i:02d}', 'x_scale': x, 'y_scale': x,
                'metadata': {}} for i in range(6, 13)]
    return SpectrumPropertiesDialog(None, spectra)


def test_the_name_is_checked_while_typing():
    from src.modules.misc import spectrum_properties as sp
    from src.views.dialogs.misc.spectrum_properties_dialog import AddPropertyDialog
    dlg = AddPropertyDialog(None, ['temperature_C', 'pH'], lambda n: sp.check_name(n, [], ['pH']))
    assert dlg.name() == '' and not dlg.ok_button.isEnabled()          # starts empty
    assert dlg.problem.text() == ''                                     # empty: just wait
    first = dlg.suggestion_list.item(0)
    dlg.suggestion_list.itemClicked.emit(first)                         # clicked in the list
    assert dlg.name() == 'temperature_C' and dlg.ok_button.isEnabled()
    dlg.name_edit.setText('my value')
    assert not dlg.ok_button.isEnabled() and 'no spaces' in dlg.problem.text()
    dlg.name_edit.setText('pH')
    assert not dlg.ok_button.isEnabled() and 'already' in dlg.problem.text()
    dlg.name_edit.setText('concentration_mM')
    assert dlg.ok_button.isEnabled() and dlg.problem.text() == ''


def test_add_property_through_the_window(monkeypatch):
    from src.views.dialogs.misc import spectrum_properties_dialog as spd
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', staticmethod(lambda *a, **k: warnings.append(a)))

    def pick(self):
        self.name_edit.setText('pH')
        return QDialog.Accepted if self.ok_button.isEnabled() else QDialog.Rejected
    monkeypatch.setattr(spd.AddPropertyDialog, 'exec_', pick)
    win = _window()
    assert 'Start with Add property' in win.summary.text()
    assert win.add_property() == 'pH' and win.keys == ['pH'] and not warnings
    assert 'Added “pH”' in win.summary.text() and 'Fill a series' in win.summary.text()
    monkeypatch.setattr(spd.AddPropertyDialog, 'exec_', lambda self: QDialog.Rejected)
    assert win.add_property() is None and win.keys == ['pH'] and not warnings


def test_sorting_by_number_and_natural_names():
    from PyQt5.QtCore import Qt
    from src.views.dialogs.misc.spectrum_properties_dialog import SpectrumPropertiesDialog
    x = np.linspace(0, 1, 5)
    names = ['s_1', 's_2', 's_10', 's_11', 's_3']
    win = SpectrumPropertiesDialog(None, [{'label': n, 'x_scale': x, 'y_scale': x, 'metadata': {}}
                                          for n in names])
    win.add_property('alfa')
    win._fill_column(1, [0, 1, 10, 11, None])            # s_3 has no value
    win.table.sortItems(1, Qt.AscendingOrder)
    assert [win.table.item(r, 1).text() for r in range(5)] == ['0', '1', '10', '11', '']
    win.table.item(4, 1).setText('2')                     # typed into the empty cell
    win.table.sortItems(1, Qt.AscendingOrder)
    assert [win.table.item(r, 1).text() for r in range(5)] == ['0', '1', '2', '10', '11']
    win.table.sortItems(0, Qt.AscendingOrder)
    assert [win.table.item(r, 0).text() for r in range(5)] == ['s_1', 's_2', 's_3', 's_10', 's_11']


def test_double_click_on_a_suggestion_adds_it():
    from src.views.dialogs.misc.spectrum_properties_dialog import AddPropertyDialog
    dlg = AddPropertyDialog(None, ['concentration', 'pH'], lambda n: None if n else "Type a name.")
    dlg.show()
    dlg.suggestion_list.itemDoubleClicked.emit(dlg.suggestion_list.item(1))
    assert dlg.result() == QDialog.Accepted and dlg.name() == 'pH'


def test_three_ways_to_give_the_name():
    """Typing (completed from the suggestions), the arrow of the field, the list."""
    from src.views.dialogs.misc.spectrum_properties_dialog import AddPropertyDialog
    dlg = AddPropertyDialog(None, ['concentration', 'pH', 'temperature'], lambda n: None)
    assert dlg.name_box.isEditable() and dlg.name_box.count() == 3       # the arrow's list
    assert dlg.name_box.completer() is not None                           # completes while typing
    dlg.name_box.setCurrentIndex(2)                                       # picked with the arrow
    assert dlg.name() == 'temperature'
    dlg.suggestion_list.itemClicked.emit(dlg.suggestion_list.item(1))     # clicked in the list
    assert dlg.name() == 'pH'
