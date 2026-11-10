"""Which spectra are selected after a change - one rule for the whole
program (v1.7.0):
  * Apply (in place), rename, move: the selection stays;
  * new spectra (Add as New, copies, an added import, results of tools):
    the new ones are selected; Alt+Left - the previous selection, Alt+Right
    forward again; Select All / Unselect All / Select spectra are kept too;
  * Delete: nothing of the deleted stays selected; Undo: they are selected again;
  * Undo / a jump in the History: the selection you had at that step.
Everything by the spectra's permanent ids (renames do not matter)."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')
SG = {'window_length': 11, 'polyorder': 3, 'deriv_order': 0, 'delta': 1.0, 'mode': 'interp'}


def _pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths or [DATA]),
                                                 [{} for _ in (file_paths or [DATA])])))
    from src.controllers.core.main_controller import MainController
    ctrl = MainController()
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def _short(label):
    return label.split(' : ')[-1]


def _selected(mc):
    return [_short(i.text()) for i in mc.spectra_list_widget.selectedItems()]


def _cache(mc):
    """What the tool windows and the plot get."""
    return sorted(_short(s['label']) for s in mc.spectrum_selector.get_selected_spectra())


def _select(mc, *names):
    lw = mc.spectra_list_widget
    lw.clearSelection()
    for i in range(lw.count()):
        if _short(lw.item(i).text()) in names:
            lw.item(i).setSelected(True)
    _pump(0.1)


def _smooth(mc, add_as_new):
    ok, msg = mc.savitzky_golay_controller.commit_sg_smoothing(
        dict(SG), add_as_new, mc.spectrum_selector.get_selected_spectra())
    _pump(0.2)
    assert ok, msg


def test_apply_keeps_add_as_new_selects_the_new_ones(mc):
    _select(mc, 'sp002', 'sp003')
    _smooth(mc, add_as_new=False)                                  # Apply: in place
    assert sorted(_selected(mc)) == ['sp002', 'sp003'] == _cache(mc)
    _smooth(mc, add_as_new=True)                                   # Add as New
    new = sorted(_selected(mc))
    assert len(new) == 2 and all(n.startswith(('sp002_', 'sp003_')) for n in new)
    assert new == _cache(mc)
    assert 'added and selected' in mc.view.statusBar().currentMessage()
    assert sorted(_short(s['label']) for s in mc.selected_spectra) == new   # the plot
    assert mc.selection_back()                                     # Alt+Left
    assert sorted(_selected(mc)) == ['sp002', 'sp003'] == _cache(mc)
    assert mc.selection_forward()                                  # Alt+Right
    assert sorted(_selected(mc)) == new
    assert not mc.selection_forward()                              # nothing further


def test_copies_and_bulk_actions(mc):
    _select(mc, 'sp004')
    mc.copy_spectra_to_clipboard()
    mc.paste_spectra_from_clipboard()
    _pump(0.2)
    assert _selected(mc) == ['sp004_copy'] == _cache(mc)            # the copy, as the help says
    mc.spectrum_selector.unselect_all_items()                       # by mistake ...
    assert _selected(mc) == []
    assert mc.selection_back()                                      # ... back again
    assert _selected(mc) == ['sp004_copy']
    mc.spectrum_selector.select_all_items()
    assert mc.selection_back() and _selected(mc) == ['sp004_copy']


def test_delete_undo_and_history_steps(mc):
    oc = mc.operations_controller
    _select(mc, 'sp001', 'sp002')
    _smooth(mc, add_as_new=False)                                  # step A
    _select(mc, 'sp007')                                           # you change the selection
    mc.spectrum_selector.delete_selected_spectra()                 # step B: delete sp007
    _pump(0.2)
    assert 'sp007' not in [_short(s['label']) for s in mc.original_spectra]
    assert _selected(mc) == []
    oc.undo_operation()                                            # back to A
    _pump(0.2)
    assert _selected(mc) == ['sp007'] == _cache(mc)                # what you had at A
    _select(mc, 'sp009')                                           # changed again at A
    oc.redo_operation()                                            # B again
    _pump(0.2)
    assert _selected(mc) == []
    oc.undo_operation()
    _pump(0.2)
    assert _selected(mc) == ['sp009']                              # A, as you left it
    oc.jump_to_operation_state(-1)                                 # the original state
    _pump(0.2)
    assert sorted(_selected(mc)) == ['sp001', 'sp002']             # before A


def test_rename_keeps_the_selection(mc):
    _select(mc, 'sp005', 'sp006')
    lw = mc.spectra_list_widget
    ids = sorted(i.data(0x0100) for i in lw.selectedItems())
    renamed = {s['label']: s['label'] + '_r' for s in mc.spectrum_selector.get_selected_spectra()}
    mc.spectrum_selector.rename_spectra(renamed)
    _pump(0.2)
    assert sorted(i.data(0x0100) for i in lw.selectedItems()) == ids
    assert sorted(_selected(mc)) == ['sp005_r', 'sp006_r']


def test_the_counter_above_the_list_follows_at_once(mc):
    """The counter (selected/all) is right straight after Add as New and
    after an Apply that adds a spectrum - not only after a click."""
    def counter():
        return mc.num_label.text()
    _select(mc, 'sp002', 'sp003')
    assert counter() == '2/11'
    _smooth(mc, add_as_new=True)
    assert counter() == '2/13'
    _select(mc, 'sp001', 'sp002', 'sp003')
    from src.controllers.data_analysis.mean_centering_controller import MeanCenteringController
    mc.mean_centering_controller = MeanCenteringController(mc)
    ok, msg = mc.mean_centering_controller.commit_mean_centering(
        {'include_mean_spectrum': True}, False, mc.spectrum_selector.get_selected_spectra())
    assert ok, msg
    assert counter() == '4/14'


def test_mean_centering_apply_keeps_the_selection_and_adds_the_mean(mc):
    """Apply that also makes a spectrum (the mean): the selection stays,
    the mean is selected too."""
    _select(mc, 'sp001', 'sp002', 'sp003')
    from src.controllers.data_analysis.mean_centering_controller import MeanCenteringController
    mc.mean_centering_controller = MeanCenteringController(mc)
    ok, msg = mc.mean_centering_controller.commit_mean_centering(
        {'include_mean_spectrum': True}, False, mc.spectrum_selector.get_selected_spectra())
    _pump(0.2)
    assert ok, msg
    sel = _selected(mc)
    assert {'sp001', 'sp002', 'sp003'} <= set(sel) and len(sel) == 4


def test_the_first_import_selects_nothing(mc):
    """The Start page imports with "Add" into the empty list: like File ›
    Import, nothing is selected (not "all new ones")."""
    mc.import_controller.clear_spectra() if hasattr(mc.import_controller, 'clear_spectra') \
        else None
    _pump(0.2)
    assert mc.spectra_list_widget.count() == 0
    mc.import_controller._run_import(clear_first=False, file_paths=[DATA])   # Add, empty list
    _pump(0.2)
    assert mc.spectra_list_widget.count() > 0 and _selected(mc) == []


def _controller(mc, module, cls):
    import importlib
    return getattr(importlib.import_module(module), cls)(mc)


def test_combine_calculator_and_rename_follow_the_rule(mc):
    """Combine, Spectral calculator and Rename (Add as New) used their own
    list rebuild: Alt+Left did not know the selection before, and the
    calculator left only the first of several results selected."""
    # Combine, Add as New: the result selected, Alt+Left the sources
    _select(mc, 'sp001', 'sp002')
    cc = _controller(mc, 'src.controllers.data_analysis.combine_spectra_controller',
                     'CombineSpectraController')
    ok, msg = cc.commit_combine_spectra(
        {'operation_type': 'average', 'new_spectrum_name': 'avg12'}, True,
        mc.spectrum_selector.get_selected_spectra())
    _pump(0.2)
    assert ok, msg
    assert _selected(mc) == ['avg12'] == _cache(mc)
    assert mc.selection_back() and sorted(_selected(mc)) == ['sp001', 'sp002']
    assert mc.selection_forward() and _selected(mc) == ['avg12']
    # Spectral calculator, two results: both selected
    _select(mc, 'sp003', 'sp004')
    sc = _controller(mc, 'src.controllers.data_analysis.spectral_calculator_controller',
                     'SpectralCalculatorController')
    l3, l4 = [s['label'] for s in mc.spectrum_selector.get_selected_spectra()]
    ok, msg = sc.commit_spectral_calculator(            # as the dialog's "sp1+sp2, sp1-sp2"
        {'formula': f'{l3} + {l4}, {l3} - {l4}', 'new_spectrum_name': 'calc'}, True,
        mc.spectrum_selector.get_selected_spectra())
    _pump(0.2)
    assert ok, msg
    new = sorted(_selected(mc))
    assert len(new) == 2 and all(n.startswith('calc') for n in new) and new == _cache(mc)
    assert mc.selection_back() and sorted(_selected(mc)) == ['sp003', 'sp004']
    # Rename › Add as New: the copies selected, Alt+Left the originals
    _select(mc, 'sp005')
    label = [s['label'] for s in mc.original_spectra if s['label'].endswith('sp005')][0]
    from src.controllers.misc.rename_spectra_controller import RenameSpectraController
    rc = RenameSpectraController(mc)
    ok, msg = rc._commit_rename_as_new({label: label + '_r'})
    _pump(0.2)
    assert ok, msg
    assert _selected(mc) == ['sp005_r']
    assert mc.selection_back() and _selected(mc) == ['sp005']
    # Rename › Apply: the selection stays (the same spectra)
    _select(mc, 'sp006', 'sp007')
    names = {s['label']: s['label'] + '_x' for s in mc.spectrum_selector.get_selected_spectra()}
    rc.apply_renamed_labels(names)
    _pump(0.2)
    assert sorted(_selected(mc)) == ['sp006_x', 'sp007_x']


def test_no_single_spectrum_plot_type_the_arrow_keys_instead(mc, tmp_path):
    """The plot type "Single spectrum" is gone: the Up / Down arrow keys show
    one spectrum after another; changing the plot type keeps the Excel-like
    selection (it used to switch the list to click-toggles); an older snapshot
    with "Single spectrum" opens as an Overlay plot."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QListWidget
    combo = mc.view.comboBox_plot_type_choice
    assert 'Single spectrum' not in [combo.itemText(i) for i in range(combo.count())]
    lw = mc.spectra_list_widget
    combo.setCurrentText('Grid plot')
    combo.setCurrentText('Overlay plot')
    _pump(0.2)
    assert lw.selectionMode() == QListWidget.ExtendedSelection
    QTest.mouseClick(lw.viewport(), Qt.LeftButton, Qt.NoModifier,
                     lw.visualItemRect(lw.item(2)).center())
    _pump(0.2)
    for key, expect in ((Qt.Key_Down, 'sp004'), (Qt.Key_Down, 'sp005'), (Qt.Key_Up, 'sp004')):
        QTest.keyClick(lw, key)
        _pump(0.2)
        lines = [l.get_label().split(' : ')[-1] for l in mc.static_canvas.figure.axes[0].get_lines()
                 if l.get_label().startswith('Raman')]
        assert _selected(mc) == [expect] and lines == [expect]
    # an older snapshot that used "Single spectrum"
    from src.modules.misc.save_spectra_manager import SaveManager
    mgr = SaveManager()
    state = mgr._build_state(mc)
    state['plot_settings']['plot_type'] = 'Single spectrum'
    combo.setCurrentText('Grid plot')
    mgr._restore_ui_state(mc, state)
    _pump(0.2)
    assert combo.currentText() == 'Overlay plot'
