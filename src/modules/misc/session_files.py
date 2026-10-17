# src/modules/misc/session_files.py
"""Files the application keeps between sessions, apart from the user's own
data: automatic-save snapshots for crash recovery, the "Open recent" list,
and small preferences (the automatic-save interval).

Qt-free (the timer, menus and prompts live in
src/controllers/misc/autosave_controller.py), so everything here can be
tested without a window.

Where: %LOCALAPPDATA%\\SpecAnalytiXBase\\ on Windows,
~/.specanalytixbase/ elsewhere -- the same per-user folder already used for
import profiles and batch pipelines. The environment variable
SPECANALYTIXBASE_DATA_DIR overrides it (the test suite uses this so that
running the tests never touches the user's real files).

Crash detection
---------------
Each running instance holds an OS file lock on  autosave/session-<id>.lock
for as long as it runs, and removes its files (lock, info, snapshot) when it
is closed normally. The operating system releases a lock when its process
ends in any way, so a session file that can be locked by someone else
belongs to an instance that ended abnormally (crash, power cut, killed); its
snapshot, if one was written, can be offered for restoring. Several
instances can run side by side without mistaking each other for crashed
sessions, and reused process ids cannot confuse it.
"""

import os
import sys
import time
import uuid

from src.modules.utils.app_logger import get_logger
from src.modules.utils.json_store import read_json_store, write_bytes_atomic, write_json_atomic

logger = get_logger(__name__)

RECENT_FILES_MAX = 10
DEFAULT_AUTOSAVE_MINUTES = 10
AUTOSAVE_CHOICES = (0, 5, 10, 20)          # minutes; 0 = off


def app_data_dir():
    """Per-user folder for the application's own files (created on use)."""
    override = os.environ.get('SPECANALYTIXBASE_DATA_DIR')
    if override:
        return override
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
        return os.path.join(base, 'SpecAnalytiXBase')
    return os.path.join(os.path.expanduser('~'), '.specanalytixbase')


def _try_lock(fh):
    """Exclusive, non-blocking lock on an open file. True if acquired."""
    try:
        if sys.platform == 'win32':
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fh):
    try:
        if sys.platform == 'win32':
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def session_is_alive(lock_path):
    """True if the instance owning *lock_path* is still running.

    A running instance holds an OS file lock on its lock file for its whole
    lifetime; the operating system releases it automatically when that
    process ends in any way (normal exit, crash, killed, power loss). So if
    the lock can be taken now, the owner is gone. Unlike checking a process
    id, this cannot be fooled by the OS reusing process ids -- which really
    happens (a new instance got the very same id as a crashed one in
    testing)."""
    if not os.path.exists(lock_path):
        return False
    try:
        fh = open(lock_path, 'a+b')
    except OSError:
        return True                    # cannot even open it: assume it is in use
    try:
        if _try_lock(fh):
            _unlock(fh)
            return False
        return True
    finally:
        fh.close()


# ---------------------------------------------------------------------------
# Automatic saving / crash recovery
# ---------------------------------------------------------------------------

class AutosaveManager:
    """Session lock + automatic snapshot of one running instance.

    Files (in self.folder), for a session id like "1234-a1b2c3d4"
    (process id + random part, unique even if process ids are reused):
        session-<id>.lock    held locked while the instance runs
        session-<id>.json    when it started, which version
        autosave-<id>.snapx  the latest automatic snapshot
    """

    def __init__(self, folder=None, session_id=None, is_alive=None):
        self.folder = folder or os.path.join(app_data_dir(), 'autosave')
        self.session_id = session_id or f'{os.getpid()}-{uuid.uuid4().hex[:8]}'
        self._is_alive = is_alive or (lambda sid: session_is_alive(self.lock_path(sid)))
        self._lock_handle = None
        self.started = None

    # -- paths
    def lock_path(self, sid=None):
        return os.path.join(self.folder, f'session-{sid or self.session_id}.lock')

    def info_path(self, sid=None):
        return os.path.join(self.folder, f'session-{sid or self.session_id}.json')

    def autosave_path(self, sid=None):
        return os.path.join(self.folder, f'autosave-{sid or self.session_id}.snapx')

    # -- own session
    def start_session(self, app_version=''):
        os.makedirs(self.folder, exist_ok=True)
        fh = open(self.lock_path(), 'a+b')
        if not _try_lock(fh):
            fh.close()
            raise OSError(f'could not lock {self.lock_path()}')
        self._lock_handle = fh
        self.started = time.time()
        write_json_atomic(self.info_path(), {
            'session': self.session_id, 'pid': os.getpid(),
            'started': self.started, 'app_version': app_version})

    def write_snapshot(self, data: bytes):
        """Write the compressed snapshot bytes for this session, atomically."""
        write_bytes_atomic(self.autosave_path(), data)

    def remove_snapshot(self):
        _remove(self.autosave_path())

    def end_session(self):
        """Normal exit: nothing to recover from this session."""
        _remove(self.autosave_path())
        _remove(self.info_path())
        if self._lock_handle is not None:
            _unlock(self._lock_handle)
            self._lock_handle.close()
            self._lock_handle = None
        _remove(self.lock_path())

    # -- other sessions
    def _other_session_ids(self):
        ids = set()
        if not os.path.isdir(self.folder):
            return ids
        for name in os.listdir(self.folder):
            for prefix, suffix in (('session-', '.lock'), ('session-', '.json'),
                                   ('autosave-', '.snapx')):
                if name.startswith(prefix) and name.endswith(suffix):
                    sid = name[len(prefix):-len(suffix)]
                    if sid and sid != self.session_id:
                        ids.add(sid)
        return ids

    def find_recoverable(self):
        """Sessions that ended abnormally and left a snapshot, newest first:
        list of dicts session / started / app_version / saved_at / size /
        snapshot_path. Leftovers of ended sessions WITHOUT a snapshot (the
        crash happened before anything was saved) are removed on the way."""
        found = []
        for sid in self._other_session_ids():
            if self._is_alive(sid):
                continue
            snap = self.autosave_path(sid)
            if not os.path.exists(snap):
                self._remove_session_files(sid)
                continue
            info = read_json_store(self.info_path(sid), 'autosave session') \
                if os.path.exists(self.info_path(sid)) else {}
            stat = os.stat(snap)
            found.append({'session': sid, 'started': info.get('started'),
                          'app_version': info.get('app_version', ''),
                          'saved_at': stat.st_mtime, 'size': stat.st_size,
                          'snapshot_path': snap})
        found.sort(key=lambda f: f['saved_at'], reverse=True)
        return found

    def discard(self, session):
        self._remove_session_files(session['session'])

    def _remove_session_files(self, sid):
        for path in (self.autosave_path(sid), self.info_path(sid), self.lock_path(sid)):
            _remove(path)


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Could not remove %s: %s", path, exc)


# ---------------------------------------------------------------------------
# "Open recent"
# ---------------------------------------------------------------------------

class RecentFiles:
    """The last RECENT_FILES_MAX data files and snapshots, newest first.
    kind is 'data' (imported spectra) or 'snapshot' (.snapx)."""

    def __init__(self, path=None):
        self.path = path or os.path.join(app_data_dir(), 'recent_files.json')

    def items(self):
        data = read_json_store(self.path, 'recent files list')
        entries = data.get('files', []) if isinstance(data, dict) else []
        return [e for e in entries
                if isinstance(e, dict) and isinstance(e.get('path'), str)
                and e.get('kind') in ('data', 'snapshot')]

    def add(self, path, kind):
        path = os.path.abspath(path)
        key = os.path.normcase(path)
        entries = [e for e in self.items() if os.path.normcase(e['path']) != key]
        entries.insert(0, {'path': path, 'kind': kind, 'when': time.time()})
        self._write(entries[:RECENT_FILES_MAX])

    def remove(self, path):
        key = os.path.normcase(os.path.abspath(path))
        self._write([e for e in self.items() if os.path.normcase(e['path']) != key])

    def clear(self):
        self._write([])

    def _write(self, entries):
        try:
            write_json_atomic(self.path, {'files': entries})
        except OSError as exc:      # the list is a convenience; never fail an import over it
            logger.warning("Could not save the recent files list: %s", exc)


# ---------------------------------------------------------------------------
# Small preferences
# ---------------------------------------------------------------------------

class Preferences:
    def __init__(self, path=None):
        self.path = path or os.path.join(app_data_dir(), 'preferences.json')

    def get(self, key, default=None):
        return read_json_store(self.path, 'preferences').get(key, default)

    def set(self, key, value):
        data = read_json_store(self.path, 'preferences')
        data[key] = value
        try:
            write_json_atomic(self.path, data)
        except OSError as exc:
            logger.warning("Could not save preferences: %s", exc)

    def autosave_minutes(self):
        value = self.get('autosave_minutes', DEFAULT_AUTOSAVE_MINUTES)
        return value if value in AUTOSAVE_CHOICES else DEFAULT_AUTOSAVE_MINUTES

    # -- CD data quality (see src/modules/data_io/cd_quality.py)
    def cd_quality_limits(self):
        """(HT limit in V, absorbance limit), falling back to the defaults
        for missing or nonsensical stored values."""
        from src.modules.data_io.cd_quality import DEFAULT_ABS_LIMIT, DEFAULT_HT_LIMIT_V
        ht = self.get('cd_ht_limit_V', DEFAULT_HT_LIMIT_V)
        ab = self.get('cd_abs_limit', DEFAULT_ABS_LIMIT)
        ht = float(ht) if isinstance(ht, (int, float)) and 100 <= ht <= 2000 else DEFAULT_HT_LIMIT_V
        ab = float(ab) if isinstance(ab, (int, float)) and 0.1 <= ab <= 10 else DEFAULT_ABS_LIMIT
        return ht, ab

    def cd_quality_shading(self):
        return bool(self.get('cd_quality_shading', True))
