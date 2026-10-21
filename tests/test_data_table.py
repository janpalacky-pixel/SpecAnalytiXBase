"""Analysis & Visualization -> Data Analysis -> Data table: the selected
spectra as a spreadsheet (x, sp1, sp2, ... as in the Spectral Calculator), columns calculated from formulas,
copy / export, and formula columns added as new spectra in one History step
(Undo removes them; the Methods report gives the formulas)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.modules.data_analysis.data_table import DataTable

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TBA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')


def _spectra(n=3, x=None):
    x = np.linspace(200, 300, 11) if x is None else x
    return [{'label': f'sample {i}', 'x_scale': x.copy(), 'y_scale': (i + 1) * x / 100,
             'metadata': {}} for i in range(n)]


# --- the table (no window) --------------------------------------------------------------

def test_columns_and_formulas():
    t = DataTable.from_spectra(_spectra())
    assert [c.name for c in t.columns] == ['x', 'sp1', 'sp2', 'sp3'] and t.shared_x
    f1 = t.add_formula('sp2 / sp1', 'ratio')
    assert f1.name == 'f1' and f1.title == 'ratio' and np.allclose(f1.values, 2)
    assert np.allclose(t.add_formula('mean(all)').values, 2 * t.x / 100)
    assert np.allclose(t.add_formula('sp3 - mean(sp1, sp2, sp3)').values, t.x / 100)
    assert np.allclose(t.add_formula('f1 * x').values, 2 * t.x)          # x and earlier columns
    assert np.allclose(t.add_formula('max_val(sp1)').values, 3.0)         # one number: every row
    assert np.allclose(t.add_formula('std(sp1, sp1)').values, 0)
    assert t.used_spectrum_names('f4') == {'sp1': 'sample 0', 'sp2': 'sample 1'}


@pytest.mark.parametrize('formula, words', [
    ('', 'Type a formula'), ('sp9 + 1', "Unknown name 'sp9'"), ('foo(sp1)', 'Unknown function'),
    ('sp1.__class__', 'not allowed'), ('all', 'inside a function')])
def test_formula_errors_are_explained(formula, words):
    t = DataTable.from_spectra(_spectra())
    with pytest.raises(ValueError) as e:
        t.add_formula(formula)
    assert words in str(e.value)
    assert not t.formula_columns()


def test_several_formulas_separated_by_commas():
    t = DataTable.from_spectra(_spectra())
    cols = t.add_formulas('sp1 / sp2, mean(sp1, sp2), log10(sp3)', 'r')
    assert [(c.name, c.formula, c.title) for c in cols] == [
        ('f1', 'sp1 / sp2', 'r_1'), ('f2', 'mean(sp1, sp2)', 'r_2'), ('f3', 'log10(sp3)', 'r_3')]
    with pytest.raises(ValueError, match="sp9"):
        t.add_formulas('sp1 * 2, sp9')
    assert len(t.formula_columns()) == 3                                # nothing half-added


def test_different_x_axes_are_shown_but_formulas_need_one_axis():
    sp = _spectra(1) + _spectra(1, np.linspace(210, 290, 7))
    t = DataTable.from_spectra(sp)
    assert not t.shared_x and [c.name for c in t.columns] == ['x1', 'sp1', 'x2', 'sp2']
    assert t.n_rows == 11 and t.value(8, 3) is None                     # the shorter spectrum
    with pytest.raises(ValueError, match='Data range'):
        t.add_formula('sp1 + sp2')


def test_removing_a_column_another_one_uses_is_refused():
    t = DataTable.from_spectra(_spectra())
    t.add_formula('sp1 + 1')
    t.add_formula('f1 * 2')
    with pytest.raises(ValueError, match='f2'):
        t.remove_column('f1')
    assert t.remove_column('f2') and t.remove_column('f1') and not t.remove_column('sp1')


def test_copy_text_and_export(tmp_path):
    t = DataTable.from_spectra(_spectra(2))
    t.add_formula('sp1 - sp2', 'difference')
    text = t.rows_as_text(range(2))
    assert text.splitlines()[0] == 'x\tsp1: sample 0\tsp2: sample 1\tf1: difference'
    assert text.splitlines()[1].split('\t')[0] == '200.0'
    import pandas as pd
    t.export(str(tmp_path / 't.csv'))
    frame = pd.read_csv(tmp_path / 't.csv')
    assert list(frame.columns)[-1] == 'f1: difference' and len(frame) == 11
    t.export(str(tmp_path / 't.xlsx'))
    assert pd.read_excel(tmp_path / 't.xlsx').shape == (11, 4)


def test_undefined_values_are_shown_but_not_added_as_a_spectrum():
    t = DataTable.from_spectra(_spectra(2))
    t.add_formula('log10(sp1 - 2)')                                      # negative for small x
    with pytest.raises(ValueError, match='undefined at'):
        t.new_spectra()


# --- in the program ---------------------------------------------------------------------

@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    controller = MainController()
    controller.import_controller._run_import(clear_first=True, file_paths=[TBA])
    app.processEvents()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _open(mc, monkeypatch, rows=(0, 1, 2)):
    from src.views.dialogs.data_analysis import data_table_dialog as dtd
    shown = []
    monkeypatch.setattr(dtd.DataTableDialog, 'exec_', lambda self: shown.append(self) or 0)
    mc.spectra_list_widget.clearSelection()
    for r in rows:
        mc.spectra_list_widget.item(r).setSelected(True)
    app.processEvents()
    mc.view.actionMenuDataTable.trigger()
    assert len(shown) == 1
    return shown[0]


def _open_selected(mc, monkeypatch):
    """Open the table for whatever is selected now (as the user does)."""
    from src.views.dialogs.data_analysis import data_table_dialog as dtd
    shown = []
    monkeypatch.setattr(dtd.DataTableDialog, 'exec_', lambda self: shown.append(self) or 0)
    mc.view.actionMenuDataTable.trigger()
    return shown[-1]


def test_long_names_fit_the_column_width(mc, monkeypatch):
    dlg = _open(mc, monkeypatch)
    dlg.view.horizontalHeader().resizeSection(1, 60)
    short = dlg.model.headerData(1, 1).split('\n')[1]
    dlg.view.horizontalHeader().resizeSection(1, 400)
    full = dlg.model.headerData(1, 1).split('\n')[1]
    assert full == dlg.table.columns[1].title and short.startswith('\u2026') and len(short) < len(full)


def test_menu_button_and_window(mc, monkeypatch):
    v = mc.view
    assert v.actionMenuDataTable in v.menuAnalysisVisualizationData.actions()
    assert v.findChild(type(v.toolbarHelpButton), 'toolbarDataTableButton') is not None
    dlg = _open(mc, monkeypatch)
    assert dlg.model.columnCount() == 4 and dlg.model.rowCount() > 100
    assert dlg.model.headerData(1, 1).startswith('sp1\n')
    dlg.formula_edit.setText('sp1 - sp2')
    dlg.name_edit.setText('TBA difference')
    dlg.add_column()
    assert dlg.model.columnCount() == 5 and dlg.add_spectra_button.isEnabled()
    dlg.formula_edit.setText('nonsense(')
    assert dlg.add_column() is None and 'syntax' in dlg.message.text().lower()
    dlg.view.selectAll()
    dlg.copy_selection()
    assert QApplication.clipboard().text().startswith('x\tsp1: ')


def test_formula_columns_become_spectra_in_one_undoable_step(mc, monkeypatch):
    n0 = len(mc.original_spectra)
    dlg = _open(mc, monkeypatch)
    for formula, name in (('sp1 - sp2', 'TBA difference'), ('mean(all)', '')):
        dlg.formula_edit.setText(formula)
        dlg.name_edit.setText(name)
        dlg.add_column()
    assert dlg.add_as_spectra()
    labels = [s['label'] for s in mc.original_spectra]
    assert len(labels) == n0 + 2 and 'TBA difference' in labels and 'mean(all)' in labels
    om = mc.operations_controller.operations_manager
    record = om.operations_chain[-1]
    assert record['type'] == 'Data table (add as new)'
    assert [f['formula'] for f in record['parameters']['formulas']] == ['sp1 - sp2', 'mean(all)']
    from src.modules.misc import methods_report as mr
    text = mr.report_for_main_controller(mc).text
    assert '“TBA difference” = sp1 - sp2' in text and 'sp1 is “' in text
    new = next(s for s in om.get_current_spectra() if s['label'] == 'TBA difference')
    src = {s['label']: s for s in om.get_current_spectra()}
    sp1, sp2 = (src[c] for c in record['parameters']['formulas'][0]['columns'].values())
    assert np.allclose(new['y_scale'], np.asarray(sp1['y_scale']) - np.asarray(sp2['y_scale']))
    # the same name again gets "(2)"
    dlg = _open(mc, monkeypatch)
    dlg.formula_edit.setText('sp1 * 2')
    dlg.name_edit.setText('TBA difference')
    dlg.add_column()
    assert dlg.add_as_spectra()
    assert 'TBA difference (2)' in [s['label'] for s in mc.original_spectra]
    # opened again: the table shows the new spectra (now selected), not the old ones
    dlg = _open_selected(mc, monkeypatch)
    assert [c.title for c in dlg.table.spectrum_columns()] == ['TBA difference (2)']
    mc.operations_controller.undo_operation()
    mc.operations_controller.undo_operation()
    app.processEvents()
    assert len(om.get_current_spectra()) == n0


def test_calculator_brackets_work_in_the_table_too():
    t = DataTable.from_spectra(_spectra())
    assert [c.formula for c in t.add_formulas('[sp1 - sp2, sp1 + sp2]')] == ['sp1 - sp2', 'sp1 + sp2']
    assert [c.formula for c in t.add_formulas('(sp1 + sp2) / 2')] == ['(sp1 + sp2) / 2']


# --- the Spectral Calculator speaks the same language ------------------------------------

def test_calculator_x_alone_and_all_bracket_forms():
    from src.modules.data_analysis.spectral_calculator_manager import SpectralCalculatorManager
    sp = _spectra(2)
    sp[0]['label'], sp[1]['label'] = 'a1', 'a2'          # short names: one inside the other's token
    m = SpectralCalculatorManager()
    assert np.allclose(m.evaluate('1/x', sp)[0]['y_scale'], 1 / sp[0]['x_scale'])
    for f in ('(a1 + a2, a1 - a2)', '[a1 + a2, a1 - a2]', 'a1 + a2, a1 - a2'):
        out = m.evaluate(f, sp)
        assert len(out) == 2 and np.allclose(out[1]['y_scale'], -sp[0]['y_scale']), f
    t = DataTable.from_spectra(sp)
    for f in ('(sp1 + sp2, sp1 - sp2)', '[sp1 + sp2, sp1 - sp2]', 'sp1 + sp2, sp1 - sp2', '1/x'):
        assert t.add_formulas(f), f


def test_calculator_knows_x_all_and_commas():
    from src.modules.data_analysis.spectral_calculator_manager import SpectralCalculatorManager
    sp = _spectra()
    m = SpectralCalculatorManager()
    x = sp[0]['x_scale']
    out = m.evaluate('sample 0 * x', sp)
    assert np.allclose(out[0]['y_scale'], x * x / 100)
    out = m.evaluate('mean(all)', sp)
    assert len(out) == 1 and np.allclose(out[0]['y_scale'], 2 * x / 100)
    assert set(out[0]['metadata']['source_spectra']) == {'sample 0', 'sample 1', 'sample 2'}
    out = m.evaluate('sample 2 - mean(sample 0, sample 1), std(all)', sp)   # commas, no brackets
    assert len(out) == 2 and np.allclose(out[0]['y_scale'], 1.5 * x / 100)
    names = [n for n, _ in m.available_functions()]
    assert 'x' in names and 'mean(all)' in names and not any('(x)' in n for n in names)


def test_calculator_show_as_table(mc, monkeypatch):
    from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
    from src.views.dialogs.data_analysis.spectral_calculator_dialog import SpectralCalculatorDialog
    sel = mc.original_spectra[:3]
    calc = SpectralCalculatorDialog(mc.view, selected_spectra=sel, current_settings={},
                                    commit_callback=lambda *a: (True, ''), main_controller=mc)
    calc.formula_edit.setPlainText('')
    calc.name_edit.setText('diff')
    calc._insert_function(type('I', (), {'row': lambda self: [n for n, _ in
                          calc.manager.available_functions()].index('x')})())
    assert calc.formula_edit.toPlainText() == 'x'                      # a name, not 'x()'
    calc.formula_edit.setPlainText('sp1 - sp2,\n mean(all)')
    monkeypatch.setattr(DataTableDialog, 'exec_', lambda self: 0)
    table = calc.show_as_table().table
    assert [(c.name, c.formula, c.title) for c in table.formula_columns()] == [
        ('f1', 'sp1 - sp2', 'diff_1'), ('f2', 'mean(all)', 'diff_2')]
    assert [c.title for c in table.spectrum_columns()] == [s['label'] for s in sel]
