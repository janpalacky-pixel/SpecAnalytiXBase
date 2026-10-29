"""Add spectra, go back in History to the state before, add the same file
again: the spectra get their own names, not "... (2)" - the earlier ones are
no longer in the list."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(ROOT, 'resources', 'test_data', 'real')


def test_adding_again_after_going_back_keeps_the_names(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    mc = MainController()
    try:
        ic = mc.import_controller
        ic._run_import(clear_first=True, file_paths=[os.path.join(REAL, 'CD_spectra_TBA.txt')])
        app.processEvents()
        first = sorted(s['label'] for s in mc.original_spectra)
        ic._run_import(clear_first=False,
                       file_paths=[os.path.join(REAL, 'Raman_DNA_conc_dep.txt')])
        app.processEvents()
        added = sorted(set(s['label'] for s in mc.original_spectra) - set(first))
        assert added and not any(lbl.endswith(')') for lbl in added)
        mc.operations_controller.jump_to_operation_state(-1)      # before the added file
        app.processEvents()
        assert sorted(s['label'] for s in mc.original_spectra) == first
        ic._run_import(clear_first=False,
                       file_paths=[os.path.join(REAL, 'Raman_DNA_conc_dep.txt')])
        app.processEvents()
        again = sorted(set(s['label'] for s in mc.original_spectra) - set(first))
        assert again == added                                        # no "(2)"
        # a real duplicate (the file added twice, both in the list) still gets "(2)"
        ic._run_import(clear_first=False,
                       file_paths=[os.path.join(REAL, 'Raman_DNA_conc_dep.txt')])
        app.processEvents()
        assert any(s['label'].endswith('(2)') for s in mc.original_spectra)
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()
