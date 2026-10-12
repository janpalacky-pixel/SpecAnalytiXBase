# src/modules/misc/snapshot_format.py
"""The .snapx file format, version 2: a ZIP archive with the snapshot's
structure as JSON and every numeric array as plain binary.

    format.json   {"format": "SpecAnalytiXBase snapshot", "version": 2}
    state.json    the snapshot state; each numpy array replaced by
                  {"__ndref__": k}
    arrays.json   table of the arrays: dtype, stored dtype, shape, byte
                  offset and length in arrays.bin
    arrays.bin    the arrays' raw bytes, one after the other

Why (measured on a 140 x 150 Raman map, 21 000 spectra x 1600 points,
two operations applied): version 1 -- gzip-compressed JSON with every array
base64-encoded -- was ~1.4 GB and took about two minutes to save, ten times
the original 134 MB .mat file:
  * base64 text is ~33 % larger than the numbers and defeats compression;
  * every spectrum carried its own copy of the identical wavenumber axis;
  * each Operations History step stored all spectra again, also the ones it
    did not change;
  * 32-bit instrument data was stored as 64-bit numbers.
Version 2 stores each distinct array once (identical arrays -- the shared
axis, spectra an operation left unchanged -- by content), stores a 64-bit
array as 32-bit when that is exactly lossless (the values come back
bit-identical), and writes plain binary that compresses well.

Loading gives the same state as before: every array as its original dtype.
Loaded arrays are read-only (as with version 1, whose arrays came from
np.frombuffer), and arrays that were identical may now be one shared
object -- both safe because no code changes spectrum arrays in place.

Version 1 files (gzip or plain JSON) are still read by
SaveManager._load_state. Qt-free and thread-safe (no global state), so
automatic saving can run it in a background thread.
"""

import hashlib
import io
import json
import os
import tempfile
import zipfile

import numpy as np

FORMAT_NAME = "SpecAnalytiXBase snapshot"
FORMAT_VERSION = 2
ZIP_MAGIC = b'PK\x03\x04'


class _ArrayTable:
    """Collects the arrays met while encoding the state, each distinct one
    once."""

    def __init__(self):
        self.entries = []          # dicts written to arrays.json
        self.payloads = []         # bytes-like objects written to arrays.bin
        self._by_id = {}           # id(array) -> index (arrays stay alive in the state)
        self._by_content = {}      # (dtype, shape, digest) -> index
        self._offset = 0

    def ref(self, arr):
        key = id(arr)
        if key in self._by_id:
            return self._by_id[key]
        a = np.ascontiguousarray(arr)
        stored = a
        if a.dtype == np.float64 and a.size:
            as32 = a.astype(np.float32)
            if np.array_equal(as32.astype(np.float64), a, equal_nan=True):
                stored = as32
        payload = memoryview(stored).cast('B') if stored.size else b''
        digest = hashlib.blake2b(payload, digest_size=20).digest()
        content_key = (a.dtype.str, a.shape, stored.dtype.str, digest)
        index = self._by_content.get(content_key)
        if index is None:
            index = len(self.entries)
            self.entries.append({
                'dtype': a.dtype.str, 'stored': stored.dtype.str, 'shape': list(a.shape),
                'offset': self._offset, 'nbytes': stored.nbytes,
            })
            self.payloads.append(payload)
            self._offset += stored.nbytes
            self._by_content[content_key] = index
        self._by_id[key] = index
        return index


def _encoder(table):
    def default(obj):
        if isinstance(obj, np.ndarray):
            if obj.dtype.kind in 'OUSV':         # not plain numbers: keep as a list
                return obj.tolist()
            return {'__ndref__': table.ref(obj)}
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if hasattr(obj, 'isoformat'):            # pandas/datetime time stamps
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")
    return default


def encode(state):
    """(state JSON bytes, _ArrayTable) -- the arrays are only referenced,
    nothing is copied."""
    table = _ArrayTable()
    text = json.dumps(state, default=_encoder(table), separators=(',', ':'))
    return text.encode('utf-8'), table


class Aborted(Exception):
    """write() was stopped by its abort() callable; nothing was written."""


def write(state, path, compression_level=6, progress=None, abort=None):
    """Write *state* to *path* as a version-2 snapshot, atomically (a
    temporary file in the same folder replaces *path* only when complete).

    progress(stage, label), optional: 1 encoding, 2 writing arrays,
    3 finishing. abort(), optional: checked while writing; when it returns
    True the write stops, the temporary file is removed and Aborted is
    raised (*path* is untouched). Returns the file size in bytes."""
    level = max(0, min(9, int(compression_level)))
    if progress:
        progress(1, "Preparing data…")
    state_bytes, table = encode(state)
    arrays_json = json.dumps({'arrays': table.entries}).encode('utf-8')

    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.tmp-', suffix='.snapx', dir=folder)
    os.close(fd)
    try:
        method = zipfile.ZIP_DEFLATED if level > 0 else zipfile.ZIP_STORED
        with zipfile.ZipFile(tmp, 'w', compression=method, compresslevel=level or None,
                             allowZip64=True) as z:
            z.writestr('format.json', json.dumps({'format': FORMAT_NAME,
                                                  'version': FORMAT_VERSION}))
            if progress:
                progress(2, "Writing spectra…")
            with z.open('arrays.bin', 'w', force_zip64=True) as fh:
                for payload in table.payloads:
                    if abort is not None and abort():
                        raise Aborted()
                    fh.write(payload)
            if progress:
                progress(3, "Finishing…")
            z.writestr('arrays.json', arrays_json)
            z.writestr('state.json', state_bytes)
        with open(tmp, 'rb+') as fh:
            os.fsync(fh.fileno())
        if abort is not None and abort():
            raise Aborted()
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return os.path.getsize(path)


def to_bytes(state, compression_level=6):
    """The version-2 file content as bytes (for tests and small states)."""
    fd, tmp = tempfile.mkstemp(suffix='.snapx')
    os.close(fd)
    try:
        write(state, tmp, compression_level)
        with open(tmp, 'rb') as fh:
            return fh.read()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def is_v2(head: bytes) -> bool:
    return head[:4] == ZIP_MAGIC


def read(source):
    """State from a version-2 snapshot (*source*: path, bytes or file
    object). Raises ValueError if it is not one."""
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    try:
        with zipfile.ZipFile(source) as z:
            info = json.loads(z.read('format.json'))
            if info.get('format') != FORMAT_NAME:
                raise ValueError("not a SpecAnalytiXBase snapshot")
            if int(info.get('version', 0)) > FORMAT_VERSION:
                raise ValueError(
                    "This snapshot was saved by a newer version of SpecAnalytiXBase. "
                    "Please update the program to open it.")
            entries = json.loads(z.read('arrays.json'))['arrays']
            blob = z.read('arrays.bin')
            state_text = z.read('state.json').decode('utf-8')
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"damaged snapshot file ({exc})") from exc

    arrays = []
    for e in entries:
        count = int(np.prod(e['shape'], dtype=np.int64))
        if count == 0:
            stored = np.empty(e['shape'], dtype=np.dtype(e['stored']))
            stored.setflags(write=False)
        else:
            stored = np.frombuffer(blob, dtype=np.dtype(e['stored']), count=count,
                                   offset=e['offset']).reshape(e['shape'])
        if e['stored'] != e['dtype']:
            stored = stored.astype(np.dtype(e['dtype']))
            stored.setflags(write=False)
        arrays.append(stored)

    def hook(obj):
        if '__ndref__' in obj and len(obj) == 1:
            return arrays[obj['__ndref__']]
        return obj
    return json.loads(state_text, object_hook=hook)
