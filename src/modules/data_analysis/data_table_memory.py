# src/modules/data_analysis/data_table_memory.py
"""What the last Data table added (its formulas, Add value... columns and the
columns sent from the Peak list or Peak Fitting), kept between sessions in
data_table_columns.json in the program's data folder (next to the settings),
and in snapshots (save_spectra_manager). Qt-free. DataTableController reads
it when the program starts and writes it each time a Data table closes; a
column removed in the Data table is therefore forgotten too."""

import json
import os

from src.modules.misc.session_files import app_data_dir
from src.modules.utils.app_logger import get_logger
from src.modules.utils.json_store import read_json_store, write_json_atomic

logger = get_logger(__name__)

FILE_NAME = 'data_table_columns.json'
# numbers sent from another window are kept per spectrum name; a huge map
# (thousands of spectra x many bands) would make the file large for little
# use after a restart - then only the columns that can be made again are kept
MAX_KEPT_NUMBERS = 50_000


def path():
    return os.path.join(app_data_dir(), FILE_NAME)


def plain(memory):
    """The memory as JSON data (tuples become lists, numpy numbers floats);
    None stays None."""
    if not memory:
        return None
    return json.loads(json.dumps(memory, default=float))


def shrunk(memory):
    """Without the per-spectrum numbers when there are too many of them."""
    memory = plain(memory)
    if not memory:
        return memory
    values = memory.get('values') or []
    numbers = sum(len(r.get('by_label') or {}) for r in values if r.get('type') == 'fixed')
    if numbers > MAX_KEPT_NUMBERS:
        memory['values'] = [r for r in values if r.get('type') != 'fixed']
    return memory


def load():
    """The remembered columns, or None (nothing, or an unreadable file)."""
    data = read_json_store(path(), 'Data table columns')
    return data or None


def save(memory):
    """Keep the memory for the next session (None or empty: forget it)."""
    memory = shrunk(memory)
    try:
        if not memory or not (memory.get('points') or memory.get('values')):
            if os.path.isfile(path()):
                write_json_atomic(path(), {})
            return
        write_json_atomic(path(), memory)
    except (OSError, TypeError, ValueError):
        logger.exception("The Data table columns could not be kept")
