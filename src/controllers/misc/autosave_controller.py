# src/controllers/misc/autosave_controller.py
"""Automatic saving with crash recovery, and File -> Open recent.

Automatic saving
    Every few minutes (File -> Automatic saving: off / 2 / 5 / 10 min,
    remembered between sessions) the current state is saved as a snapshot
    into the per-user autosave folder -- only when something changed since
    the last automatic save. Building the snapshot text takes well under a
    second even for large maps and happens here; compressing and writing
    it (the slow part) happens on a background thread, so the window never
    freezes. The file is written atomically (temporary file + rename).

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
import os
import threading

from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QMessageBox

from src.modules.misc.save_spectra_manager import SaveManager
from src.modules.misc.session_files import (
    AUTOSAVE_CHOICES, AutosaveManager, Preferences, RecentFiles)
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)

AUTOSAVE_GZIP_LEVEL = 1          # fastest; the file is temporary anyway


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
        self.wait_for_write(30)
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
                self.wait_for_write(30)
                self.manager.remove_snapshot()
                self._last_hash = None

    def autosave_now(self):
        """Save the current state if it changed. Returns True if a save was
        started. Safe to call often: unchanged state costs only building
        and hashing the snapshot text."""
        if not self.started or self.is_writing():
            return False
        if not getattr(self.main, 'original_spectra', None):
            # Nothing loaded (e.g. everything cleared): nothing to recover.
            self.manager.remove_snapshot()
            self._last_hash = None
            return False
        save_manager = self.main.save_controller.save_manager
        try:
            state, digest = save_manager.snapshot_state_and_digest(self.main)
            if digest == self._last_hash:
                return False                      # nothing changed since the last save
            json_bytes = save_manager.snapshot_json_bytes(self.main, state)
        except Exception:
            logger.exception("Automatic save: could not collect the current state")
            return False

        def write():
            try:
                self.manager.write_snapshot(
                    SaveManager.compress_snapshot(json_bytes, AUTOSAVE_GZIP_LEVEL))
                self._last_hash = digest
                self.last_saved_at = datetime.datetime.now()
                self._write_error = None
            except Exception as exc:              # disk full, folder removed, ...
                self._write_error = exc
                logger.warning("Automatic save failed: %s", exc)

        self._writer = threading.Thread(target=write, name='autosave', daemon=True)
        self._writer.start()
        return True

    def is_writing(self):
        return self._writer is not None and self._writer.is_alive()

    def wait_for_write(self, timeout=None):
        if self._writer is not None:
            self._writer.join(timeout)

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
        self.autosave_now()          # protect the restored work under this session
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
