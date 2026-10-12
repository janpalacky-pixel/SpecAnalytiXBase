"""Automatic saving with crash recovery, and File -> Open recent."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import time

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from src.modules.misc import session_files
from src.modules.misc.session_files import (
    AutosaveManager, Preferences, RecentFiles, RECENT_FILES_MAX)

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TBA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')


# ===========================================================================
# session_files (no Qt)
# ===========================================================================

def _manager(tmp_path, sid='me-0001', alive=()):
    return AutosaveManager(folder=str(tmp_path / 'autosave'), session_id=sid,
                           is_alive=lambda s: s in alive)


def _crashed_session(folder, sid, content=b'snapshot bytes', with_info=True):
    """Files left behind by an instance that ended abnormally."""
    os.makedirs(folder, exist_ok=True)
    if with_info:
        with open(os.path.join(folder, f'session-{sid}.json'), 'w') as fh:
            json.dump({'session': sid, 'started': 1.0}, fh)
    open(os.path.join(folder, f'session-{sid}.lock'), 'wb').close()
    with open(os.path.join(folder, f'autosave-{sid}.snapx'), 'wb') as fh:
        fh.write(content)


def test_normal_session_leaves_nothing_behind(tmp_path):
    m = _manager(tmp_path)
    m.start_session('1.6.0')
    m.write_snapshot(b'abc')
    assert os.path.exists(m.lock_path()) and os.path.exists(m.autosave_path())
    m.end_session()
    assert os.listdir(m.folder) == []


def test_crashed_session_is_found_with_its_snapshot(tmp_path):
    m = _manager(tmp_path)
    _crashed_session(m.folder, '2222-dead')
    found = m.find_recoverable()
    assert [f['session'] for f in found] == ['2222-dead']
    assert found[0]['snapshot_path'].endswith('autosave-2222-dead.snapx')
    assert found[0]['size'] == len(b'snapshot bytes')


def test_another_running_instance_is_not_mistaken_for_a_crash(tmp_path):
    m = _manager(tmp_path, alive={'3333-live'})
    _crashed_session(m.folder, '3333-live')
    assert m.find_recoverable() == []


def test_own_session_is_never_offered(tmp_path):
    m = _manager(tmp_path)
    m.start_session()
    m.write_snapshot(b'mine')
    assert m.find_recoverable() == []
    m.end_session()


def test_crash_before_any_save_is_just_cleaned_up(tmp_path):
    m = _manager(tmp_path)
    os.makedirs(m.folder)
    for name in ('session-4444-x.json', 'session-4444-x.lock'):
        open(os.path.join(m.folder, name), 'w').close()
    assert m.find_recoverable() == []
    assert os.listdir(m.folder) == []


def test_snapshot_without_info_file_is_still_recoverable(tmp_path):
    m = _manager(tmp_path)
    _crashed_session(m.folder, '5555-y', with_info=False)
    assert [f['session'] for f in m.find_recoverable()] == ['5555-y']


def test_several_crashes_newest_first_and_discard(tmp_path):
    m = _manager(tmp_path)
    _crashed_session(m.folder, '11-a')
    _crashed_session(m.folder, '22-b')
    old = os.path.join(m.folder, 'autosave-11-a.snapx')
    os.utime(old, (time.time() - 600, time.time() - 600))
    found = m.find_recoverable()
    assert [f['session'] for f in found] == ['22-b', '11-a']
    m.discard(found[0])
    assert [f['session'] for f in m.find_recoverable()] == ['11-a']
    assert not any(n.startswith(('session-22-b', 'autosave-22-b')) for n in os.listdir(m.folder))


def test_real_lock_running_versus_crashed(tmp_path):
    """With the real OS file lock (no stand-in): a running instance is seen
    as running; once it ends WITHOUT cleaning up -- a crash -- its lock is
    gone and its snapshot is offered."""
    folder = str(tmp_path / 'autosave')
    running = AutosaveManager(folder=folder, session_id='100-run')
    running.start_session()
    running.write_snapshot(b'work in progress')
    other = AutosaveManager(folder=folder, session_id='200-new')
    assert other.find_recoverable() == []                     # it is still running
    running._lock_handle.close()                              # the process dies: lock released
    running._lock_handle = None
    assert [f['session'] for f in other.find_recoverable()] == ['100-run']


def test_reused_process_id_does_not_hide_or_delete_a_crash(tmp_path):
    """A new instance may get the same process id as a crashed one (seen in
    testing). It must still offer the crashed work and must not delete it."""
    folder = str(tmp_path / 'autosave')
    _crashed_session(folder, '12-crashed1')
    new = AutosaveManager(folder=folder, session_id='12-newone22')   # same pid 12
    new.start_session()
    assert [f['session'] for f in new.find_recoverable()] == ['12-crashed1']
    new.end_session()                                          # a normal close of the NEW one
    assert os.path.exists(os.path.join(folder, 'autosave-12-crashed1.snapx'))


def test_recent_files_newest_first_no_duplicates_limited(tmp_path):
    r = RecentFiles(path=str(tmp_path / 'recent.json'))
    files = []
    for i in range(RECENT_FILES_MAX + 3):
        f = tmp_path / f'f{i}.txt'
        f.write_text('x')
        files.append(str(f))
        r.add(str(f), 'data')
    r.add(files[5], 'data')                                   # re-opened: moves to the top
    items = r.items()
    assert len(items) == RECENT_FILES_MAX
    assert items[0]['path'] == os.path.abspath(files[5])
    assert len({os.path.normcase(e['path']) for e in items}) == RECENT_FILES_MAX
    r.remove(files[5])
    assert all(e['path'] != os.path.abspath(files[5]) for e in r.items())
    r.clear()
    assert r.items() == []


def test_recent_files_survive_a_damaged_list(tmp_path):
    path = tmp_path / 'recent.json'
    path.write_text('{"files": [ {broken')
    r = RecentFiles(path=str(path))
    assert r.items() == []
    r.add(str(path), 'snapshot')
    assert len(r.items()) == 1


def test_preferences_default_and_invalid_interval(tmp_path):
    p = Preferences(path=str(tmp_path / 'prefs.json'))
    assert p.autosave_minutes() == session_files.DEFAULT_AUTOSAVE_MINUTES
    p.set('autosave_minutes', 0)
    assert p.autosave_minutes() == 0
    p.set('autosave_minutes', 7)                              # not offered in the menu
    assert p.autosave_minutes() == session_files.DEFAULT_AUTOSAVE_MINUTES


def test_tests_never_use_the_real_user_folder():
    assert os.environ.get('SPECANALYTIXBASE_DATA_DIR')
    assert session_files.app_data_dir() == os.environ['SPECANALYTIXBASE_DATA_DIR']


# ===========================================================================
# In the application
# ===========================================================================

@pytest.fixture
def mc(tmp_path, monkeypatch):
    """A main window (not shown) whose per-user files live in tmp_path."""
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))

    def answer_yes(box):                      # e.g. "replace your current workspace?"
        yes = box.button(QMessageBox.Yes) if isinstance(box, QMessageBox) else None
        if yes is not None:
            yes.click()
        return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, 'exec_', answer_yes)
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths or [TBA]),
                                                 [{} for _ in (file_paths or [TBA])])))
    controller = MainController()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _import(mc, path=TBA):
    mc.import_controller._run_import(clear_first=True, file_paths=[path])
    app.processEvents()


def test_menus_are_in_the_file_menu(mc):
    titles = [a.text() for a in mc.view.menuFile.actions()]
    assert 'Open recent' in titles and 'Automatic saving' in titles
    assert titles.index('Open recent') == titles.index(mc.view.actionImport_Snapshot.text()) + 1


def test_creating_the_window_alone_writes_no_session_files(mc):
    assert not mc.autosave_controller.started
    assert not os.path.exists(mc.autosave_controller.manager.folder) or \
        os.listdir(mc.autosave_controller.manager.folder) == []


def test_autosave_writes_only_when_something_changed(mc):
    ac = mc.autosave_controller
    ac.start(offer_recovery=False)
    assert ac.autosave_now() is False                         # nothing loaded yet
    _import(mc)
    assert ac.autosave_now() is True
    ac.wait_for_write(30)
    assert os.path.getsize(ac.manager.autosave_path()) > 0
    assert ac.last_saved_at is not None
    assert ac.autosave_now() is False                         # unchanged -> skipped
    mc.original_spectra = mc.original_spectra[:5]
    assert ac.autosave_now() is True                          # changed -> saved again
    ac.wait_for_write(30)


def test_autosaved_file_restores_the_same_spectra(mc):
    ac = mc.autosave_controller
    ac.start(offer_recovery=False)
    _import(mc)
    labels = [s['label'] for s in mc.original_spectra]
    ac.autosave_now(); ac.wait_for_write(30)
    snap = ac.manager.autosave_path()
    mc.original_spectra = []
    assert mc.save_controller.load_snapshot(snap)
    assert [s['label'] for s in mc.original_spectra] == labels


def test_clearing_everything_removes_the_automatic_save(mc):
    ac = mc.autosave_controller
    ac.start(offer_recovery=False)
    _import(mc)
    ac.autosave_now(); ac.wait_for_write(30)
    mc.original_spectra = []
    ac.autosave_now()
    assert not os.path.exists(ac.manager.autosave_path())


def test_interval_choice_is_remembered_and_off_deletes(mc):
    ac = mc.autosave_controller
    ac.start(offer_recovery=False)
    assert ac.timer.isActive()
    _import(mc)
    ac.autosave_now(); ac.wait_for_write(30)
    ac.set_interval(0)
    assert not ac.timer.isActive()
    assert not os.path.exists(ac.manager.autosave_path())
    assert Preferences().autosave_minutes() == 0
    ac.set_interval(2)
    assert ac.timer.isActive() and ac.timer.interval() == 2 * 60 * 1000


def test_normal_close_removes_this_sessions_files(mc):
    ac = mc.autosave_controller
    ac.start(offer_recovery=False)
    _import(mc)
    ac.autosave_now(); ac.wait_for_write(30)
    ac.shutdown()
    assert os.listdir(ac.manager.folder) == []


def _answer_recovery(monkeypatch, button_text):
    def exec_(box):
        if isinstance(box, QMessageBox):
            for b in box.buttons():
                if b.text() == button_text:
                    b.click()
            return 0
        return QDialog.Rejected
    monkeypatch.setattr(QMessageBox, 'exec_', exec_)


def _make_crashed_snapshot(mc, sid='987654-crashed'):
    """Save a real snapshot of TBA as if another instance had crashed."""
    _import(mc)
    data = mc.save_controller.save_manager.compress_snapshot(
        mc.save_controller.save_manager.snapshot_json_bytes(mc))
    labels = [s['label'] for s in mc.original_spectra]
    _crashed_session(mc.autosave_controller.manager.folder, sid, content=data)
    mc.original_spectra = []
    return labels


def test_restore_after_a_crash(mc, monkeypatch):
    ac = mc.autosave_controller
    labels = _make_crashed_snapshot(mc)
    ac.start(offer_recovery=False)
    _answer_recovery(monkeypatch, 'Restore')
    assert ac.offer_recovery() == 1
    assert [s['label'] for s in mc.original_spectra] == labels
    assert ac.manager.find_recoverable() == []                # the crashed files are gone
    ac.wait_for_write(30)
    assert os.path.exists(ac.manager.autosave_path())         # and protected under this session


def test_discard_after_a_crash(mc, monkeypatch):
    ac = mc.autosave_controller
    _make_crashed_snapshot(mc)
    ac.start(offer_recovery=False)
    _answer_recovery(monkeypatch, 'Discard')
    assert ac.offer_recovery() == 0
    assert ac.manager.find_recoverable() == []
    assert mc.original_spectra == []


def test_not_now_keeps_it_for_next_time(mc, monkeypatch):
    ac = mc.autosave_controller
    _make_crashed_snapshot(mc)
    ac.start(offer_recovery=False)
    _answer_recovery(monkeypatch, 'Not now')
    assert ac.offer_recovery() == 0
    assert len(ac.manager.find_recoverable()) == 1


def test_imports_and_snapshots_appear_in_open_recent(mc, tmp_path):
    _import(mc)
    ac = mc.autosave_controller
    assert ac.recent.items()[0] == {**ac.recent.items()[0], 'path': os.path.abspath(TBA), 'kind': 'data'}
    snap = str(tmp_path / 'saved.snapx')
    assert mc.save_controller.save_manager.save_snapshot(mc, snap)
    assert mc.import_controller.open_snapshot_path(snap)
    assert ac.recent.items()[0]['path'] == os.path.abspath(snap)
    assert ac.recent.items()[0]['kind'] == 'snapshot'
    ac._fill_recent_menu()
    texts = [a.text() for a in ac.recent_menu.actions()]
    assert any('saved.snapx' in t and 'snapshot' in t for t in texts)
    assert any('CD_spectra_TBA.txt' in t for t in texts)
    assert texts[-1] == 'Clear list'


def test_open_recent_reopens_a_data_file(mc):
    _import(mc)
    mc.original_spectra = []
    entry = mc.autosave_controller.recent.items()[0]
    mc.autosave_controller.open_recent(entry)
    app.processEvents()
    # the usual "add to or replace the current spectra?" question is asked
    # (answered automatically here); either way the file was imported again
    labels = set(mc.import_controller.spectrum_manager.spectra)
    assert 'CD_spectra_TBA : 0001' in labels and len(labels) >= 28


def test_open_recent_with_a_missing_file_removes_it(mc, tmp_path):
    gone = tmp_path / 'gone.txt'
    gone.write_text('x')
    ac = mc.autosave_controller
    ac.recent.add(str(gone), 'data')
    gone.unlink()
    ac.open_recent(ac.recent.items()[0])
    assert all(e['path'] != str(gone) for e in ac.recent.items())


def test_loading_a_snapshot_asks_only_when_something_would_be_replaced(mc, tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, 'exec_', lambda box: asked.append(box.text()) or
                        (box.button(QMessageBox.Yes).click() if box.button(QMessageBox.Yes) else None))
    _import(mc)
    snap = str(tmp_path / 's.snapx')
    assert mc.save_controller.save_manager.save_snapshot(mc, snap)
    assert mc.save_controller.load_snapshot(snap)          # workspace has data -> asked
    assert len(asked) == 1 and 'replace' in asked[0]
    mc.original_spectra = []
    assert mc.save_controller.load_snapshot(snap)          # empty workspace -> nothing to lose
    assert len(asked) == 1


def test_reverse_sorting_is_saved_and_restored_in_snapshots(mc, tmp_path):
    """It used to be looked up on the window instead of the main
    controller, so it was silently never saved."""
    _import(mc)
    mc.checkBox_reverse_order.setChecked(True)
    snap = str(tmp_path / 'r.snapx')
    assert mc.save_controller.save_manager.save_snapshot(mc, snap)
    mc.checkBox_reverse_order.setChecked(False)
    assert mc.save_controller.load_snapshot(snap)
    assert mc.checkBox_reverse_order.isChecked()
