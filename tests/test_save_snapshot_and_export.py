"""Your work and exports apart (1.7.0), as in other programs: File > Save
snapshot (Ctrl+S) saves into the snapshot opened or saved last without a
dialog (the first time: a name), Save snapshot as... (Ctrl+Shift+S),
Export spectra... (Ctrl+E: text, Excel, .spc - no snapshot there any
more). The title names the snapshot, "*" while changes are not saved in
it; closing then asks Save / Discard / Cancel."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')


def _pump(seconds=0.15):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))

    def answer_yes(box):                       # "Loading a snapshot will replace ...?": Yes
        for b in box.buttons():
            if box.buttonRole(b) == QMessageBox.YesRole:
                b.click()
                return QMessageBox.Yes
        return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, 'exec_', answer_yes)
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, [DATA], [{}])))
    from src.controllers.core.main_controller import MainController
    ctrl = MainController()
    ctrl.show()
    ctrl.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump(0.3)
    yield ctrl
    ctrl.snapshot_file.stop()
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def _ask_name(monkeypatch, path):
    asked = []

    def ask(*a, **k):
        asked.append(1)
        return str(path), ''
    from src.controllers.misc import save_spectra_controller as ssc
    monkeypatch.setattr(ssc.QFileDialog, 'getSaveFileName', staticmethod(ask))
    return asked


def test_save_snapshot_asks_once_then_saves_into_it(mc, tmp_path, monkeypatch):
    sf = mc.snapshot_file
    sf.update_title()
    assert mc.view.windowTitle() == '*Untitled – SpecAnalytiXBase'   # in no snapshot yet
    path = tmp_path / 'work.snapx'
    asked = _ask_name(monkeypatch, path)
    mc.view.actionSaveSnapshot.trigger()                 # Ctrl+S: the first time a name
    assert len(asked) == 1 and path.exists()
    assert sf.path == str(path) and mc.view.windowTitle() == 'work.snapx – SpecAnalytiXBase'
    assert not sf.is_modified()
    # a change: "*"
    mc.view.comboBox_plot_type_choice.setCurrentText('Grid plot')
    _pump(0.2)
    sf.update_title()
    assert sf.is_modified() and mc.view.windowTitle().startswith('*work.snapx')
    before = path.stat().st_mtime_ns
    time.sleep(0.02)
    mc.view.actionSaveSnapshot.trigger()                 # again: no dialog, into work.snapx
    assert len(asked) == 1 and path.stat().st_mtime_ns != before
    assert not sf.is_modified() and not mc.view.windowTitle().startswith('*')
    # Save snapshot as...: always a name; from then on that one
    other = tmp_path / 'other.snapx'
    asked2 = _ask_name(monkeypatch, other)
    mc.view.actionSaveSnapshotAs.trigger()
    assert len(asked2) == 1 and other.exists() and sf.path == str(other)


def test_open_names_it_and_import_new_forgets_it(mc, tmp_path, monkeypatch):
    path = tmp_path / 'work.snapx'
    _ask_name(monkeypatch, path)
    mc.save_controller.save_snapshot_as()
    mc.snapshot_file.forget()
    assert mc.snapshot_file.path is None
    assert mc.import_controller.open_snapshot_path(str(path))
    _pump(0.3)
    assert mc.snapshot_file.path == str(path)
    assert mc.view.windowTitle() == 'work.snapx – SpecAnalytiXBase'
    mc.import_controller._run_import(clear_first=True, file_paths=[DATA])   # Import data > New
    _pump(0.2)
    assert mc.snapshot_file.path is None and mc.view.windowTitle().startswith('*Untitled')


def test_closing_with_changes_asks_save_discard_cancel(mc, tmp_path, monkeypatch):
    from PyQt5.QtGui import QCloseEvent
    seen = {}

    def question(parent, title, text, buttons=None, default=None):
        seen['text'], seen['buttons'] = text, buttons
        return seen['answer']
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(question))
    seen['answer'] = QMessageBox.Cancel
    event = QCloseEvent()
    mc.closeEvent(event)
    assert not event.isAccepted()                         # Cancel: stays open
    assert 'not saved in a snapshot' in seen['text']
    assert seen['buttons'] == QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
    # Save: asks a name, saves, then closes; Save cancelled (no name): stays open
    seen['answer'] = QMessageBox.Save
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', staticmethod(lambda *a, **k: ('', '')))
    from src.controllers.misc import save_spectra_controller as ssc
    monkeypatch.setattr(ssc.QFileDialog, 'getSaveFileName', staticmethod(lambda *a, **k: ('', '')))
    event = QCloseEvent()
    mc.closeEvent(event)
    assert not event.isAccepted()
    # nothing changed since the save: the usual question
    _ask_name(monkeypatch, tmp_path / 'w.snapx')
    mc.save_controller.save_snapshot()
    seen['answer'] = QMessageBox.No
    event = QCloseEvent()
    mc.closeEvent(event)
    assert 'Are you sure' in seen['text'] and not event.isAccepted()


def test_export_has_no_snapshot_and_the_compression_setting_is_used(mc, tmp_path, monkeypatch):
    from src.views.dialogs.misc.save_spectra_dialog import SaveOptionsDialog
    d = SaveOptionsDialog(mc.view)
    assert d.windowTitle() == 'Export spectra' and d.fmt_snapshot.isHidden()
    d.close()
    from src.modules.misc.session_files import Preferences
    Preferences().set('snapshot_compression', 9)
    used = {}
    real = mc.save_controller.save_manager.save_snapshot

    def spy(*a, **k):
        used['level'] = k.get('compression_level')
        return real(*a, **k)
    monkeypatch.setattr(mc.save_controller.save_manager, 'save_snapshot', spy)
    _ask_name(monkeypatch, tmp_path / 'max.snapx')
    mc.save_controller.save_snapshot_as()
    assert used['level'] == 9


def test_save_as_offers_a_name(mc, tmp_path, monkeypatch):
    offered = {}

    def ask(parent, caption, start, *a, **k):
        offered['start'] = start
        return '', ''
    from src.controllers.misc import save_spectra_controller as ssc
    monkeypatch.setattr(ssc.QFileDialog, 'getSaveFileName', staticmethod(ask))
    mc.save_controller.save_snapshot_as()
    # the spectra came from Raman_DNA_conc_dep.txt (their names start with it)
    assert os.path.basename(offered['start']) == 'Raman_DNA_conc_dep.snapx'
    assert os.path.dirname(offered['start']) in ('', os.path.dirname(DATA))
    path = tmp_path / 'work.snapx'
    _ask_name(monkeypatch, path)
    mc.save_controller.save_snapshot_as()
    monkeypatch.setattr(ssc.QFileDialog, 'getSaveFileName', staticmethod(ask))
    mc.save_controller.save_snapshot_as()
    assert offered['start'] == str(path)                 # then: the snapshot itself
