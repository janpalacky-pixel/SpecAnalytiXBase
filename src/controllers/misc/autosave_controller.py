# src/controllers/misc/autosave_controller.py
"""Automatic saving with crash recovery, and File -> Open recent.

Automatic saving
    Every few minutes (File -> Automatic saving: off / 2 / 5 / 10 min,
    remembered between sessions) the current state is saved as a snapshot
    into the per-user autosave folder -- only when something changed since
    the last automatic save (a cheap signature of everything, compared at
    every turn; see autosave_now). It
    waits while an operation shows a progress dialog, writes the file on a
    background thread (snapshot_format.py, atomically), and shows
    "Saving automatically…" / "Saved automatically at …" in the status bar.
    A save that is still being written makes the next turn skip.

Crash recovery
    start() is called once the main window is shown (from main.py). If an
    earlier instance ended without closing normally and left an automatic
    snapshot, the user is asked: Restore / Discard / Not now. A normal close
    (closeEvent -> shutdown()) removes this instance's own files, so only
    abnormal endings are ever offered. See session_files.py for how crashed
    sessions are recognized, also with several instances running.

Open recent
    The last 10 data files and snapshots (imported, opened or saved);
    clicking one re-opens it the normal way (data files through the Import
    dialog, snapshots directly).
"""

import datetime
import hashlib
import json
import os
import threading
import time
import weakref

import numpy as np
from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QMessageBox

from src.modules.misc import snapshot_format
from src.modules.misc.session_files import (
    AUTOSAVE_CHOICES, AutosaveManager, Preferences, RecentFiles)
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)

AUTOSAVE_GZIP_LEVEL = 1          # fastest; the file is temporary anyway
BUSY_RETRY_SECONDS = 20          # app busy: try again after this long


_FINGERPRINTS = {}   # id(array) -> (weak reference, fingerprint)


def _array_fingerprint(a):
    """Cheap stand-in for an array's content in the change signature:
    shape, dtype, the first and last value and the sum of every 37th value
    -- a fraction of the cost of serialising it. Remembered per array
    object (weakly, so nothing is kept alive), which makes the check for
    an unchanged workspace nearly free. Any operation replaces the arrays
    it changes (none is modified in place), so a new array means a new
    fingerprint."""
    key = id(a)
    cached = _FINGERPRINTS.get(key)
    if cached is not None and cached[0]() is a:
        return cached[1]
    flat = a.reshape(-1)
    if flat.size and flat.dtype.kind in 'fiub':
        with np.errstate(all='ignore'):
            fp = [list(a.shape), a.dtype.str, float(flat[::37].sum()),
                  float(flat[0]), float(flat[-1])]
    else:
        fp = [list(a.shape), a.dtype.str, len(flat)]
    try:
        _FINGERPRINTS[key] = (weakref.ref(a), fp)
    except TypeError:                     # (not weak-referenceable)
        pass
    if len(_FINGERPRINTS) > 400000:       # forget arrays that no longer exist
        for k in [k for k, (ref, _) in _FINGERPRINTS.items() if ref() is None]:
            del _FINGERPRINTS[k]
    return fp


def state_signature(state):
    """sha1 over the snapshot state, with arrays replaced by
    _array_fingerprint -- whether anything changed since the last
    automatic save, without building the snapshot."""
    def default(obj):
        if isinstance(obj, np.ndarray):
            return ['nd'] + _array_fingerprint(obj)
        if isinstance(obj, (np.integer, np.floating, np.bool_)):
            return obj.item()
        return str(obj)
    text = json.dumps(state, default=default)
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


def _detach(value):
    """Copy of the state's containers (lists, dicts), sharing the arrays:
    the background writer then never sees a list or dict the main window
    changes meanwhile. Arrays are not changed in place anywhere in the
    app, so sharing them is safe and saves copying hundreds of MB."""
    if isinstance(value, dict):
        return {k: _detach(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_detach(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_detach(v) for v in value)
    return value


class AutosaveController(QObject):

    def __init__(self, main_controller, manager=None, recent=None, preferences=None):
        super().__init__()
        self.main = main_controller
        self.manager = manager or AutosaveManager()
        self.recent = recent or RecentFiles()
        self.preferences = preferences or Preferences()
        self.started = False
        self.last_saved_at = None
        self._last_hash = None
        self._writer = None
        self._write_error = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.autosave_now)
        # Retry shortly after the app stops being busy (see autosave_now).
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self.autosave_now)
        # Watches the background writer to update the status bar.
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._check_writer)
        self.last_duration = 0.0
        self._abort_write = False
        self._build_menus()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def start(self, app_version='', offer_recovery=True):
        """Begin this session: session marker, timer, recovery question."""
        try:
            self.manager.start_session(app_version)
        except OSError as exc:
            logger.warning("Automatic saving unavailable (%s)", exc)
            return
        self.started = True
        self._apply_interval(self.preferences.autosave_minutes())
        if offer_recovery:
            QTimer.singleShot(600, self.offer_recovery)

    def shutdown(self):
        """Normal exit: nothing of this session needs recovering."""
        self.timer.stop()
        self._retry_timer.stop()
        self._status_timer.stop()
        self._stop_writing()
        if self.started:
            self.manager.end_session()
            self.started = False

    # ------------------------------------------------------------------ #
    # Automatic saving                                                    #
    # ------------------------------------------------------------------ #

    def set_interval(self, minutes):
        self.preferences.set('autosave_minutes', minutes)
        self._apply_interval(minutes)

    def _apply_interval(self, minutes):
        for action in self._interval_actions:
            action.setChecked(action.data() == minutes)
        if minutes and self.started:
            self.timer.start(int(minutes * 60 * 1000))
        else:
            self.timer.stop()
            if self.started and not minutes:
                self._stop_writing()
                self.manager.remove_snapshot()
                self._last_hash = None

    def autosave_now(self, force=False):
        """Save the current state if it changed. Returns True if a save was
        started.

        Built for large workspaces (e.g. a 21 000-spectrum map, where a
        snapshot is hundreds of MB):
          * it waits while the app is busy -- a progress dialog is open or a
            wait cursor shows -- and tries again shortly after, so it never
            competes with an operation for the computer (force=True skips
            this check);
          * whether anything changed is decided from a cheap signature (the
            structure plus a sampled checksum of every array), not by
            building the whole snapshot;
          * the slow part -- writing the file -- runs in a background thread,
            with a note in the main window's status bar;
          * while one save is still being written the next one is skipped,
            so saves never overlap.
        The state is taken when the save starts: an operation still running
        then is not in it (it is in the next save)."""
        if not self.started:
            return False
        if self.is_writing():
            return False
        if not force and self._app_is_busy():
            self._retry_timer.start(BUSY_RETRY_SECONDS * 1000)
            return False
        if not getattr(self.main, 'original_spectra', None):
            # Nothing loaded (e.g. everything cleared): nothing to recover.
            self.manager.remove_snapshot()
            self._last_hash = None
            return False
        # The signature covers everything that goes into the snapshot --
        # data, Operations History, selection, plot and other settings,
        # metadata -- and is compared at EVERY turn, so any change is saved
        # at the next turn. (An earlier version first compared a short
        # summary and the full signature only every 5th turn; changes the
        # summary did not include, such as plot colours, were then saved up
        # to 25 minutes late. Measured cost of the full check on a
        # 21 000-spectrum workspace: about 0.5 s on a slow 2-core machine.)
        save_manager = self.main.save_controller.save_manager
        try:
            state = save_manager._build_state(self.main)
            state.pop('timestamp', None)
            digest = state_signature(state)
            if digest == self._last_hash:
                return False                      # nothing changed since the last save
            state = _detach(state)
            state['timestamp'] = datetime.datetime.now().isoformat()
        except Exception:
            logger.exception("Automatic save: could not collect the current state")
            return False

        path = self.manager.autosave_path()
        self._show_status("Saving automatically\u2026", 0)

        def write():
            started = time.perf_counter()
            try:
                snapshot_format.write(state, path, AUTOSAVE_GZIP_LEVEL,
                                      abort=lambda: self._abort_write)
                self._last_hash = digest
                self.last_saved_at = datetime.datetime.now()
                self.last_duration = time.perf_counter() - started
                self._write_error = None
            except snapshot_format.Aborted:
                pass                              # stopped on purpose (closing, switched off)
            except Exception as exc:              # disk full, folder removed, ...
                self._write_error = exc
                logger.warning("Automatic save failed: %s", exc)

        self._abort_write = False
        self._writer = threading.Thread(target=write, name='autosave', daemon=True)
        self._writer.start()
        self._status_timer.start(500)
        return True

    @staticmethod
    def _app_is_busy():
        """True while an operation shows a progress dialog or the wait
        cursor (the main window is then working; an automatic save would
        only slow it down further)."""
        from PyQt5.QtWidgets import QApplication, QProgressDialog
        if QApplication.overrideCursor() is not None:
            return True
        return any(isinstance(w, QProgressDialog) and w.isVisible()
                   for w in QApplication.topLevelWidgets())

    def _check_writer(self):
        if self.is_writing():
            return
        self._status_timer.stop()
        if self._write_error is not None:
            self._show_status("Automatic save failed (see the log)", 15000)
        elif self.last_saved_at is not None:
            took = getattr(self, 'last_duration', 0.0)
            note = f" ({took:.0f} s)" if took >= 2 else ""
            self._show_status(f"Saved automatically at {self.last_saved_at:%H:%M}{note}", 8000)

    def _show_status(self, text, timeout_ms):
        try:
            self.main.view.statusBar().showMessage(text, timeout_ms)
        except Exception:
            pass

    def is_writing(self):
        return self._writer is not None and self._writer.is_alive()

    def wait_for_write(self, timeout=None):
        if self._writer is not None:
            self._writer.join(timeout)

    def _stop_writing(self):
        """Stop a save in progress (it leaves no file behind) and wait for
        its thread -- before this session's files are removed, so a late
        write can never re-create an automatic save that would then look
        like a crashed session."""
        self._abort_write = True
        self.wait_for_write(60)

    # ------------------------------------------------------------------ #
    # Crash recovery                                                      #
    # ------------------------------------------------------------------ #

    def offer_recovery(self):
        """Ask about each session that ended abnormally. Returns the number
        restored (0 or 1 -- restoring replaces the current spectra, so any
        further ones are left for the next start)."""
        for session in self.manager.find_recoverable():
            saved = datetime.datetime.fromtimestamp(session['saved_at'])
            box = QMessageBox(self.main.view)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("Restore unsaved work?")
            box.setText(
                "SpecAnalytiXBase was not closed normally last time "
                "(for example a crash or a power cut).\n\n"
                f"Your work was saved automatically on "
                f"{saved:%d %b %Y at %H:%M} "
                f"({session['size'] / 1e6:.1f} MB). Restore it now?")
            box.setInformativeText(
                "Restore: open it as it was.\n"
                "Discard: delete it.\n"
                "Not now: keep it and ask again next time.")
            restore = box.addButton("Restore", QMessageBox.AcceptRole)
            discard = box.addButton("Discard", QMessageBox.DestructiveRole)
            later = box.addButton("Not now", QMessageBox.RejectRole)
            box.setDefaultButton(restore)
            box.exec_()
            clicked = box.clickedButton()
            if clicked is restore:
                if self._restore(session):
                    return 1
            elif clicked is discard:
                self.manager.discard(session)
            elif clicked is later or clicked is None:
                continue
        return 0

    def _restore(self, session):
        ok = self.main.save_controller.load_snapshot(session['snapshot_path'])
        if not ok:
            QMessageBox.warning(
                self.main.view, "Could not restore",
                "The automatically saved work could not be opened. It has been "
                f"kept, in case it can be opened later:\n{session['snapshot_path']}")
            return False
        self.main.view.spectrum_selection_frame.setVisible(True)
        self.manager.discard(session)
        self._last_hash = None
        self.autosave_now(force=True)    # protect the restored work under this session
        return True

    # ------------------------------------------------------------------ #
    # Open recent                                                         #
    # ------------------------------------------------------------------ #

    def record_recent(self, path, kind):
        if path and os.path.exists(path):
            self.recent.add(path, kind)

    def open_recent(self, entry):
        path, kind = entry['path'], entry['kind']
        if not os.path.exists(path):
            QMessageBox.warning(
                self.main.view, "File not found",
                f"This file no longer exists (moved, renamed or deleted):\n{path}\n\n"
                "It has been removed from the list.")
            self.recent.remove(path)
            return
        if kind == 'snapshot':
            self.main.import_controller.open_snapshot_path(path)
        else:
            self.main.import_controller.execute_paths([path])

    # ------------------------------------------------------------------ #
    # Menus                                                               #
    # ------------------------------------------------------------------ #

    def _build_menus(self):
        view = self.main.view
        file_menu = view.menuFile
        self.recent_menu = QMenu("Open recent", file_menu)
        self.recent_menu.setObjectName("menuOpenRecent")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        actions = file_menu.actions()
        anchor = None
        if getattr(view, 'actionImport_Snapshot', None) in actions:
            i = actions.index(view.actionImport_Snapshot)
            anchor = actions[i + 1] if i + 1 < len(actions) else None
        if anchor is not None:
            file_menu.insertMenu(anchor, self.recent_menu)
        else:
            file_menu.addMenu(self.recent_menu)

        self.autosave_menu = QMenu("Automatic saving", file_menu)
        self.autosave_menu.setObjectName("menuAutomaticSaving")
        self.autosave_menu.aboutToShow.connect(self._update_status_action)
        self._status_action = QAction(self.autosave_menu)
        self._status_action.setEnabled(False)
        self.autosave_menu.addAction(self._status_action)
        self.autosave_menu.addSeparator()
        group = QActionGroup(self.autosave_menu)
        self._interval_actions = []
        for minutes in AUTOSAVE_CHOICES:
            text = "Off" if minutes == 0 else f"Every {minutes} minutes"
            action = QAction(text, self.autosave_menu, checkable=True)
            action.setData(minutes)
            action.triggered.connect(lambda _c=False, m=minutes: self.set_interval(m))
            group.addAction(action)
            self.autosave_menu.addAction(action)
            self._interval_actions.append(action)
        self.autosave_menu.addSeparator()
        explain = QAction("About automatic saving…", self.autosave_menu)
        explain.triggered.connect(self._explain)
        self.autosave_menu.addAction(explain)
        file_menu.addSeparator()
        file_menu.addMenu(self.autosave_menu)
        self._apply_interval(self.preferences.autosave_minutes())

    def _fill_recent_menu(self):
        menu = self.recent_menu
        menu.clear()
        entries = self.recent.items()
        if not entries:
            empty = menu.addAction("(no recent files)")
            empty.setEnabled(False)
            return
        for n, entry in enumerate(entries, 1):
            name = os.path.basename(entry['path'])
            if entry['kind'] == 'snapshot':
                name += "   (snapshot)"
            action = menu.addAction(f"&{n % 10}  {name}" if n <= 10 else name)
            action.setToolTip(entry['path'])
            action.setStatusTip(entry['path'])
            action.triggered.connect(lambda _c=False, e=entry: self.open_recent(e))
        menu.setToolTipsVisible(True)
        menu.addSeparator()
        clear = menu.addAction("Clear list")
        clear.triggered.connect(self.recent.clear)

    def _update_status_action(self):
        minutes = self.preferences.autosave_minutes()
        if not minutes:
            text = "Automatic saving is off"
        elif self._write_error is not None:
            text = "Last automatic save failed (see log)"
        elif self.last_saved_at:
            text = f"Last saved automatically at {self.last_saved_at:%H:%M}"
        else:
            text = "Nothing saved automatically yet"
        self._status_action.setText(text)

    def _explain(self):
        QMessageBox.information(
            self.main.view, "Automatic saving",
            "While you work, SpecAnalytiXBase saves a snapshot of your spectra, "
            "operations history and plot settings every few minutes, but only "
            "when something has changed.\n\n"
            "If the program ends unexpectedly (crash, power cut), you are offered "
            "to restore that work the next time you start it. When you close the "
            "program normally, the automatic save is deleted. It does not replace "
            "File → Save.\n\n"
            f"Folder: {self.manager.folder}")
