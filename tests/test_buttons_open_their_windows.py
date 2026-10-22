"""A button's click must open the window asking for the value. A button sends
clicked(False); connected straight to a method like add_property(name=None)
the False arrived as the name, so no window opened and only "Type a name."
appeared (Spectrum properties: Add property, Fill from the names, Fill a
series; Data table: Add value)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox

app = QApplication.instance() or QApplication([])


def _spectra(n=4):
    x = np.linspace(0, 100, 201)
    return [{'label': f'raman_2comp_clean : raman_{i:02d}', 'x_scale': x,
             'y_scale': np.exp(-((x - 50) / 5) ** 2) * (i + 1), 'metadata': {}}
            for i in range(1, n + 1)]


def test_spectrum_properties_buttons_ask_first(monkeypatch):
    from src.views.dialogs.misc import spectrum_properties_dialog as spd
    warnings, asked = [], []
    monkeypatch.setattr(QMessageBox, 'warning', staticmethod(lambda *a, **k: warnings.append(a)))

    def name_window(self):
        asked.append('name')
        self.name_edit.setText('pH')
        return QDialog.Accepted
    monkeypatch.setattr(spd.AddPropertyDialog, 'exec_', name_window)
    win = spd.SpectrumPropertiesDialog(None, _spectra())
    win.add_button.click()
    assert asked == ['name'] and win.keys == ['pH'] and not warnings

    def which_number(*a, **k):
        asked.append('number')
        return a[3][0], True                     # "the last number"
    monkeypatch.setattr(QInputDialog, 'getItem', staticmethod(which_number))
    win.name_button.click()
    assert asked[-1] == 'number'
    values, _ = win.values()
    assert [v['pH'] for v in values] == [1, 2, 3, 4]

    monkeypatch.setattr(QDialog, 'exec_', lambda self: asked.append('series') or QDialog.Rejected)
    win.series_button.click()                    # the start/step window, cancelled
    assert asked[-1] == 'series' and not warnings


def test_data_table_add_value_button_asks_first(monkeypatch):
    from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
    from src.views.dialogs.data_analysis import value_table_panel as vtp
    opened = []
    monkeypatch.setattr(vtp.ValueChoiceDialog, 'exec_',
                        lambda self: opened.append(1) or QDialog.Rejected)
    dlg = DataTableDialog(None, _spectra(3))
    dlg.values.add_value_button.click()
    assert opened == [1]                         # the choice window, not an error
