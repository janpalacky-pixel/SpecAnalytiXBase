"""Data table > Values per spectrum > As new spectrum: one column against
another (e.g. a band's area against temperature_C - a melting curve) added to
the spectra list as a new spectrum, sorted by x; x may be 'row' (the order of
the spectra). One Operations History step: Undo removes it."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_analysis.value_table import ValueTable

app = QApplication.instance() or QApplication([])


def _melting(temps=(60.0, 20.0, 40.0, 80.0)):
    """Spectra in the list NOT in temperature order; band height = 1 + T/100."""
    x = np.linspace(0, 100, 501)
    return [{'label': f'scan : T={t:g}C', 'x_scale': x,
             'y_scale': (1 + t / 100) * np.exp(-((x - 50) / 5) ** 2),
             'metadata': {'temperature_C': t}} for t in temps]


def test_a_column_against_another_is_a_spectrum_sorted_by_x():
    t = ValueTable.from_spectra(_melting())
    t.add_value({'kind': 'max', 'range_a': (40, 60)})
    spectrum, sources = t.as_spectrum('v1', 'temperature_C')
    assert list(spectrum['x_scale']) == [20, 40, 60, 80]                  # sorted by x
    assert np.allclose(spectrum['y_scale'], [1.2, 1.4, 1.6, 1.8], atol=1e-3)
    assert spectrum['label'].endswith(' vs temperature_C') and spectrum['label'].startswith('Max')
    assert [s['metadata']['temperature_C'] for s in sources] == [60, 20, 40, 80]
    meta = spectrum['metadata']
    made = meta['correction_history'][-1]               # what it was made of - said once
    assert made['operation'] == 'Data table (values)'
    assert made['x'] == 'temperature_C' and made['y'] == 'v1' and made['y_settings']['kind'] == 'max'
    assert made['y_meaning'].startswith('Max') and 'x_meaning' not in made   # x says it itself
    assert made['y_settings'] == {'kind': 'max', 'range_a': [40, 60], 'max_mode': 'point'}
    # a formula column: its formula, no "meaning" repeating it; n1 gets its meaning
    t.add_formula('v1 * 2')
    made = t.as_spectrum('f1', 'n1')[0]['metadata']['correction_history'][-1]
    assert made['y_formula'] == 'v1 * 2' and 'y_meaning' not in made
    assert made['x_meaning'] == 'number 1 in the name'
    t.add_formula('v1 / 2', 'half')
    made = t.as_spectrum('f2', 'temperature_C')[0]['metadata']['correction_history'][-1]
    assert made['y_meaning'] == 'half' and made['y_formula'] == 'v1 / 2'
    assert 'source_spectra' not in made and len(meta['source_spectra']) == 4
    assert 'values_as_spectrum' not in meta and 'x_axis_title' not in meta


def test_row_as_x_follows_the_order_of_the_table():
    t = ValueTable.from_spectra(_melting())
    spectrum, _ = t.as_spectrum('temperature_C', 'row')
    assert list(spectrum['x_scale']) == [1, 2, 3, 4]
    assert list(spectrum['y_scale']) == [60, 20, 40, 80]
    assert spectrum['label'] == 'temperature_C vs spectrum number (row)'
    x, y, _ = t.xy('row', 'temperature_C')                               # the Plot too
    assert list(x) == [1, 2, 3, 4]


def test_repeated_x_or_too_few_points_are_refused():
    sp = _melting((20.0, 20.0, 40.0))
    t = ValueTable.from_spectra(sp)
    with pytest.raises(ValueError, match=r'the same value 20 more than once \(sp1, sp2\)'):
        t.as_spectrum('n1', 'temperature_C')
    with pytest.raises(ValueError, match='Choose two different columns'):
        ValueTable.from_spectra(_melting()).as_spectrum('n1', 'n1')
    sp = _melting((20.0,)) + [{'label': 'blank', 'x_scale': np.arange(3.0),
                               'y_scale': np.zeros(3), 'metadata': {}}]
    with pytest.raises(ValueError, match='Fewer than 2 spectra'):
        ValueTable.from_spectra(sp).as_spectrum('temperature_C', 'row')


def test_the_button_adds_it_and_stays_in_the_table(monkeypatch):
    from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
    added = []
    dlg = DataTableDialog(None, _melting(),
                          value_callback=lambda s, src: added.append((s, src)) or (True, 'Added.'))
    panel = dlg.values
    assert not panel.as_spectrum_button.isHidden()
    from src.views.dialogs.data_analysis.value_table_panel import ROW_TEXT
    assert panel.x_combo.findText(ROW_TEXT) >= 0 and panel.y_combo.findText(ROW_TEXT) < 0
    panel.x_combo.setCurrentText(ROW_TEXT)
    assert panel.x_name() == 'row'
    panel.y_combo.setCurrentText('n1')
    panel.x_combo.setCurrentText('temperature_C')
    panel.as_spectrum_button.click()
    assert list(added[0][0]['x_scale']) == [20, 40, 60, 80] and 'Added.' in panel.message.text()
    assert dlg.isVisible() is False and dlg.result() == 0          # not closed by it
    assert DataTableDialog(None, _melting()).values.as_spectrum_button.isHidden()


def test_in_the_program_it_is_one_step_that_undo_takes_back(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.data_analysis import data_table_dialog as dtd
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    monkeypatch.setattr(dtd.DataTableDialog, 'exec_', lambda self: 0)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mc = MainController()
    try:
        mc.import_controller._run_import(clear_first=True, file_paths=[
            os.path.join(root, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')])
        mc.spectrum_selector.select_all_items()
        app.processEvents()
        n0 = len(mc.original_spectra)
        mc.data_table_controller.show_dialog(mc.spectrum_selector.get_selected_spectra())
        panel = mc.data_table_controller.dialog.values
        assert not panel.as_spectrum_button.isHidden()
        panel.y_combo.setCurrentText('n1')
        from src.views.dialogs.data_analysis.value_table_panel import ROW_TEXT
        panel.x_combo.setCurrentText(ROW_TEXT)
        spectrum = panel.add_as_spectrum()
        assert spectrum is not None and len(mc.original_spectra) == n0 + 1
        assert spectrum['label'] in [s['label'] for s in mc.original_spectra]
        assert 'Added' in panel.message.text()
        om = mc.operations_controller.operations_manager
        record = om.operations_chain[-1]
        assert record['type'] == 'Data table (values) (add as new)'
        assert record['parameters']['values_as_spectrum']['x'] == 'row'
        from src.modules.misc import methods_report as mr
        text = mr.report_for_main_controller(mc).text            # the Methods report says it
        assert f"A new spectrum “{spectrum['label']}” was made from one value per spectrum: number 1 " \
               "in the name against spectrum number (row), for 28 spectra" in text
        mc.operations_controller.undo_operation()
        app.processEvents()
        assert len(om.get_current_spectra()) == n0
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()


def test_the_plot_joins_the_points_only_when_each_x_occurs_once():
    from src.views.dialogs.data_analysis.value_table_panel import ValuePlotDialog
    t = ValueTable.from_spectra(_melting((20.0, 20.0, 40.0)))
    lines = ValuePlotDialog(None, t, 'temperature_C', 'n1').figure.axes[0].get_lines()
    assert [ln.get_linestyle() for ln in lines] == ['None']            # the points only
    t = ValueTable.from_spectra(_melting())
    lines = ValuePlotDialog(None, t, 'temperature_C', 'n1').figure.axes[0].get_lines()
    assert [ln.get_linestyle() for ln in lines] == ['-', 'None']       # a line and the points
