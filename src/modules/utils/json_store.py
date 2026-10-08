# src/modules/utils/json_store.py
"""Safe reading and writing of the small JSON files in which the app keeps
user-created items between sessions (normalization region presets, import
profiles, batch pipelines).

Two failure modes these helpers prevent:

1. A save interrupted half-way (crash, power cut, full disk) used to leave a
   truncated file: open(path, 'w') empties the file first, then writes.
   write_json_atomic() writes to a temporary file in the same folder and
   only then replaces the real file in one step (os.replace), so the file
   is always either the complete old version or the complete new one.

2. An unreadable file used to be treated silently as "nothing saved yet";
   the next save then wrote a new file holding only the new item, and
   every earlier item was gone for good. read_json_store() now keeps a
   copy of an unreadable file (<name>.corrupt-<timestamp>.json) before
   reporting it as empty, and logs where that copy is, so nothing is lost.
"""

import json
import os
import shutil
import tempfile
import time

from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)


def read_json_store(path, what):
    """Return the dict stored in *path*; {} if the file does not exist.

    *what* names the contents for the log, e.g. "import profiles".
    An unreadable or malformed file is copied aside first (see module
    docstring) and then treated as empty.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
        problem = 'it does not contain a JSON object'
    except (OSError, ValueError) as exc:          # json.JSONDecodeError is a ValueError
        problem = str(exc)
    backup = _keep_damaged_copy(path)
    logger.warning(
        "Could not read the saved %s (%s): %s. %s", what, path, problem,
        f"A copy of the unreadable file was kept as {backup}." if backup
        else "No copy could be kept.")
    return {}


def write_json_atomic(path, data):
    """Write *data* as JSON to *path* so that the file is never left
    half-written. Raises OSError (or TypeError for unserialisable data);
    the original file is then unchanged."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix='.tmp-', suffix='.json', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _keep_damaged_copy(path):
    """Copy *path* to <name>.corrupt-<timestamp><ext> next to it; return the
    copy's path, or None if even that failed."""
    root, ext = os.path.splitext(path)
    backup = f"{root}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}{ext or '.json'}"
    n = 1
    while os.path.exists(backup):
        n += 1
        backup = f"{root}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}-{n}{ext or '.json'}"
    try:
        shutil.copy2(path, backup)
        return backup
    except OSError:
        return None
