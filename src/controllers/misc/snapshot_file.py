# src/controllers/misc/snapshot_file.py
"""The snapshot you work in (since 1.7.0), as a document in other programs:

* File > Save snapshot (Ctrl+S) saves into the snapshot opened or saved
  last - without a dialog; the first time (or after Import data > New) it
  asks for a name, as Save snapshot as... (Ctrl+Shift+S) always does.
* The window's title names it: "TBA_series.snapx - SpecAnalytiXBase", with
  a "*" in front while there are changes not saved in it ("Untitled" while
  the spectra are in no snapshot yet).
* Closing the program with unsaved changes asks: Save / Discard / Cancel.

Whether something changed is decided as for automatic saving
(autosave_controller.state_signature: everything a snapshot holds, arrays
by a cheap fingerprint) - compared with the signature at the last save or
open. The title is checked a moment after the user did something (a click,
a key, the wheel), not while the program is busy, and on a very large
workspace (where the check takes long) less often."""

import os
import time

from PyQt5.QtCore import QEvent, QObject, QTimer

APP = "SpecAnalytiXBase"
CHECK_MS = 2000            # the title is checked this long after the user did something
_INPUT = (QEvent.MouseButtonRelease, QEvent.KeyRelease, QEvent.Wheel)


class SnapshotFile(QObject):

    def __init__(self, main_controller):
        super().__init__()
        self.main = main_controller
        self.path = None               # the snapshot opened or saved last (None: none)
        self._saved = None             # the signature at that moment
        self._input = False
        self._next_check = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(CHECK_MS)
        self.timer.timeout.connect(self._check)

    def start(self):
        """After the main window is shown."""
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.timer.start()
        self.update_title(False)

    def stop(self):
        self.timer.stop()
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
        except RuntimeError:
            pass

    def eventFilter(self, obj, event):
        if event.type() in _INPUT:
            self._input = True
        return False

    # ------------------------------------------------------------ state
    def has_work(self):
        return bool(getattr(self.main, 'original_spectra', None))

    def digest(self):
        from src.controllers.misc.autosave_controller import state_signature
        state = self.main.save_controller.save_manager._build_state(self.main)
        state.pop('timestamp', None)
        return state_signature(state)

    def is_modified(self):
        """Changes not saved in the snapshot (spectra in no snapshot yet: yes;
        nothing loaded: no)."""
        if not self.has_work():
            return False
        if self._saved is None:
            return True
        try:
            return self.digest() != self._saved
        except Exception:
            return True

    def suggestion(self):
        """The name offered by Save snapshot as... when the work is in no
        snapshot yet: the data file the spectra came from (their names start
        with it, e.g. "raman_2comp_clean : raman_01" -> raman_2comp_clean.snapx),
        else "Untitled.snapx"; in that file's folder when it is in Open
        recent, else in the folder of the last snapshot there."""
        if self.path:
            return self.path
        labels = []
        for s in (getattr(self.main, 'original_spectra', None) or []):
            label = s.get('label', '') if isinstance(s, dict) else ''
            labels.append(str(label))
        stems = {l.split(' : ', 1)[0].strip() for l in labels if ' : ' in l}
        stem = stems.pop() if len(stems) == 1 and len(labels) == sum(
            1 for l in labels if ' : ' in l) else ''
        stem = ''.join(c for c in stem if c not in '\\/:*?"<>|').strip() or 'Untitled'
        folder = ''
        recent = getattr(getattr(self.main, 'autosave_controller', None), 'recent', None)
        try:
            items = recent.items() if recent is not None else []
        except Exception:
            items = []
        for item in items:                     # the data file itself
            p = item.get('path', '')
            if item.get('kind') != 'snapshot' and os.path.splitext(os.path.basename(p))[0] == stem:
                folder = os.path.dirname(p)
                break
        if not folder:
            for item in items:                 # else: where the last snapshot is
                if item.get('kind') == 'snapshot':
                    folder = os.path.dirname(item.get('path', ''))
                    break
        name = stem + '.snapx'
        return os.path.join(folder, name) if folder and os.path.isdir(folder) else name

    def name(self):
        if self.path:
            return os.path.basename(self.path)
        return "Untitled" if self.has_work() else ''

    # ------------------------------------------------------------ changes
    def mark_saved(self, path):
        """Saved into / opened from `path`: this is the snapshot now, and
        nothing is changed (checked once more a moment later - opening
        finishes a few things after it returns)."""
        self.path = path
        try:
            self._saved = self.digest()
        except Exception:
            self._saved = None
        self.update_title(False)
        QTimer.singleShot(800, self._resettle)

    def _resettle(self):
        if self.path and self._saved is not None:
            try:
                self._saved = self.digest()
            except Exception:
                pass
            self.update_title(False)

    def forget(self):
        """Import data > New (new spectra instead of the current ones): no
        snapshot yet - Save snapshot asks for a name."""
        self.path = None
        self._saved = None
        self.update_title()

    def mark_unsaved(self):
        """E.g. work restored after a crash: in no snapshot."""
        self.path = None
        self._saved = None
        self.update_title()

    def update_title(self, modified=None):
        view = getattr(self.main, 'view', None)
        if view is None:
            return
        if modified is None:
            modified = self.is_modified()
        name = self.name()
        title = APP if not name else f"{'*' if modified else ''}{name} – {APP}"
        try:
            view.setWindowTitle(title)
        except RuntimeError:
            pass

    def _check(self):
        """A moment after the user did something: the "*" in the title."""
        if not self._input or time.monotonic() < self._next_check:
            return
        try:
            from src.controllers.misc.autosave_controller import AutosaveController
            if AutosaveController._app_is_busy():
                return
        except Exception:
            pass
        self._input = False
        started = time.monotonic()
        self.update_title()
        # a large workspace (the check takes long): not more often than every
        # 20 times the check's own duration
        self._next_check = time.monotonic() + 20 * (time.monotonic() - started)
