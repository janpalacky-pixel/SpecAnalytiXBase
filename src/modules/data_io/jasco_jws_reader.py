# src/modules/data_io/jasco_jws_reader.py
#
# Reader for JASCO SpectraManager (.jws) files — the native binary format
# written by JASCO's CD spectropolarimeters (e.g. J-815) and UV/Vis
# instruments. A single .jws file can hold one, two, or three co-recorded
# "channels" per scan — commonly CD [mdeg], HT [V] (photomultiplier dynode
# voltage), and Absorbance [AU], all sharing the same x-axis (wavelength).
#
# .jws is not documented by JASCO; this reader was built by directly
# reverse-engineering three real sample files (two 2-channel CD+Abs scans,
# one 3-channel CD+HT+Abs scan) rather than from a published spec. See the
# comments below for exactly what was verified and how.
#
# --- Container format -------------------------------------------------
# A .jws file IS a Microsoft OLE2 Compound File Binary (CFB) container —
# the same structured-storage format historically used for .doc/.xls
# (confirmed by the D0CF11E0A1B11AE1 magic signature at byte 0). Inside
# it, JASCO stores a fixed set of named streams at the root level:
#   Header, BaseInfo, DataInfo, MeasParam, ModuleInfo, SampleInfo,
#   UserInfo, MeasInfo, Histories, Y-Data
# (plus a couple of sub-storages — MicroImages, Results — not used here).
# Every stream observed in the 3 sample files is well under the 4096-byte
# "mini stream" cutoff, so a correct reader must implement CFB's MiniFAT
# mechanism, not just the regular FAT — see _read_ole_streams below.
#
# Rather than add a new third-party dependency (e.g. the `olefile`
# package) for this, _read_ole_streams is a small, self-contained CFB
# reader implementing exactly what's needed to pull named top-level
# streams out of the container: header parsing, (mini)FAT chain
# resolution, and a directory red-black-tree sibling walk (needed because
# MicroImages/BaseInfo is a *different*, unrelated 8-byte stream that
# happens to share the leaf name "BaseInfo" with the real one at root
# level — a naive "search all entries by name" would grab the wrong one).
# Cross-checked byte-for-byte against the `olefile` library's output on
# all 3 sample files during development.
#
# --- DataInfo: channel count, point count, x-axis -----------------------
# The 'DataInfo' stream carries a small binary header (offsets fixed
# regardless of DataInfo's total length, confirmed across both a 140-byte
# 2-channel DataInfo and a 184-byte 3-channel one):
#   offset 12 (int32) — number of channels stored in Y-Data
#   offset 20 (int32) — number of points per channel
#   offset 24 (float64) — x-axis start value (wavelength, nm)
#   offset 32 (float64) — x-axis end value (wavelength, nm)
# The x-axis is regularly spaced (confirmed: linspace(start, end, n)
# lands on exactly 0.5 nm steps in all 3 samples), so it is generated
# rather than read point-by-point — .jws does not store x separately.
#
# --- Y-Data: the actual spectral values ---------------------------------
# 'Y-Data' is a flat array of little-endian float32 values, channel-major
# (i.e. ALL of channel 0's points, then ALL of channel 1's, etc. — NOT
# interleaved per-point). len(Y-Data) == 4 * n_channels * n_points held
# exactly in all 3 samples, which is what confirms both the dtype and the
# channel-major layout (no other combination divides evenly *and* matches
# the declared n_channels/n_points from DataInfo).
#
# --- Channel identity: CD vs HT vs Absorbance ----------------------------
# JASCO does not store a channel-type string anywhere findable in the
# streams above (channel type appears to be an internal numeric code in
# DataInfo's per-channel descriptor blocks, whose exact encoding wasn't
# recoverable from 3 samples alone). Instead, channel identity is inferred
# from each channel's own value range, which is highly discriminating in
# practice for these three quantities:
#   CD [mdeg]   — straddles zero (min < 0 < max); typically small
#                 magnitude (roughly -100..100 for real samples).
#   HT [V]      — always positive; large magnitude (typically 100s,
#                 confirmed 275-973 V in the sample file that has it).
#   Absorbance  — always positive; small magnitude (confirmed 0.7-5.5 AU
#                 across all 3 samples that carry it — every one of them,
#                 in fact, suggesting Abs is very commonly co-recorded).
# This is a heuristic, not a guaranteed-correct decode — which is exactly
# why the import dialog surfaces the guessed label for each channel with
# an editable override rather than silently trusting it (see
# import_dialog.py's JWS channel table).
import os
import struct
from typing import Dict, List, Optional

import numpy as np

from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)

_OLE_SIGNATURE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
_ENDOFCHAIN = 0xFFFFFFFE
_FREESECT = 0xFFFFFFFF
_NOSTREAM = 0xFFFFFFFF

_WANTED_STREAMS = {'DataInfo', 'Y-Data', 'SampleInfo'}

# DataInfo fixed-offset header fields (see module docstring).
_DI_OFF_N_CHANNELS = 12
_DI_OFF_N_POINTS = 20
_DI_OFF_X_START = 24
_DI_OFF_X_END = 32

# Channel-classification thresholds (mdeg / V / AU) — see module docstring
# for the sample-data evidence behind these bands. Deliberately generous
# so real, noisier data still classifies sensibly; the import dialog lets
# the user correct a wrong guess regardless.
_HT_MIN_MAGNITUDE = 50.0     # HT[V] is always well above this
_ABS_MAX_MAGNITUDE = 15.0    # Absorbance stays well below this


# ---------------------------------------------------------------------------
# Minimal OLE2 Compound File reader — see module docstring for scope.
# ---------------------------------------------------------------------------

def _read_ole_streams(data: bytes, wanted_names: set) -> Dict[str, bytes]:
    """Return {name: raw_bytes} for the requested TOP-LEVEL (root) streams
    of an OLE2 Compound File. Streams nested inside sub-storages are
    deliberately not matched even if they share a wanted name — see
    module docstring (MicroImages/BaseInfo collision)."""
    if data[:8] != _OLE_SIGNATURE:
        raise ValueError(
            "Not a JASCO .jws file — missing the OLE2 compound-file "
            "signature. This file may be corrupted, or may be a JASCO "
            "format other than .jws (SpectraManager binary)."
        )

    sector_shift = struct.unpack_from('<H', data, 30)[0]
    mini_sector_shift = struct.unpack_from('<H', data, 32)[0]
    first_dir_sector = struct.unpack_from('<I', data, 48)[0]
    mini_cutoff = struct.unpack_from('<I', data, 56)[0]
    first_minifat_sector = struct.unpack_from('<I', data, 60)[0]
    n_minifat_sectors = struct.unpack_from('<I', data, 64)[0]
    first_difat_sector = struct.unpack_from('<I', data, 68)[0]
    n_difat_sectors = struct.unpack_from('<I', data, 72)[0]

    sector_size = 1 << sector_shift
    mini_sector_size = 1 << mini_sector_shift

    def sector_offset(n):
        return 512 + n * sector_size  # the 512-byte header precedes sector 0 regardless of sector_size

    # --- DIFAT: locates every FAT sector ---
    difat = list(struct.unpack_from('<109I', data, 76))
    if first_difat_sector not in (_ENDOFCHAIN, _FREESECT) and n_difat_sectors > 0:
        sec = first_difat_sector
        seen = set()
        while sec not in (_ENDOFCHAIN, _FREESECT):
            if sec in seen:
                raise ValueError("Corrupt .jws file: DIFAT chain loop detected")
            seen.add(sec)
            off = sector_offset(sec)
            chunk = data[off: off + sector_size]
            difat.extend(struct.unpack_from('<%dI' % (sector_size // 4 - 1), chunk, 0))
            sec = struct.unpack_from('<I', chunk, sector_size - 4)[0]
    difat = [d for d in difat if d != _FREESECT]

    # --- FAT: sector-chain map, built from every FAT sector listed in DIFAT ---
    fat: List[int] = []
    for fs in difat:
        off = sector_offset(fs)
        chunk = data[off: off + sector_size]
        fat.extend(struct.unpack_from('<%dI' % (sector_size // 4), chunk, 0))

    def read_chain(start_sector, size=None):
        out = bytearray()
        sec = start_sector
        seen = set()
        while sec not in (_ENDOFCHAIN, _FREESECT):
            if sec in seen or sec >= len(fat):
                raise ValueError("Corrupt .jws file: FAT chain loop or out-of-range sector")
            seen.add(sec)
            off = sector_offset(sec)
            out.extend(data[off: off + sector_size])
            sec = fat[sec]
        b = bytes(out)
        return b if size is None else b[:size]

    # --- Directory stream: one 128-byte entry per file/storage object ---
    dir_bytes = read_chain(first_dir_sector)
    n_entries = len(dir_bytes) // 128
    entries = []
    for i in range(n_entries):
        base = i * 128
        name_len = struct.unpack_from('<H', dir_bytes, base + 64)[0]
        name = dir_bytes[base: base + max(0, name_len - 2)].decode('utf-16le', errors='replace') if name_len >= 2 else ''
        entries.append({
            'name': name,
            'type': dir_bytes[base + 66],
            'left': struct.unpack_from('<I', dir_bytes, base + 68)[0],
            'right': struct.unpack_from('<I', dir_bytes, base + 72)[0],
            'child': struct.unpack_from('<I', dir_bytes, base + 76)[0],
            'start': struct.unpack_from('<I', dir_bytes, base + 116)[0],
            'size': struct.unpack_from('<Q', dir_bytes, base + 120)[0],
        })
    if not entries:
        raise ValueError("Corrupt .jws file: empty directory stream")
    root = entries[0]

    # --- MiniFAT + the root's ministream (every stream here is small enough to use it) ---
    if first_minifat_sector not in (_ENDOFCHAIN, _FREESECT) and n_minifat_sectors > 0:
        minifat_bytes = read_chain(first_minifat_sector)
        minifat = list(struct.unpack_from('<%dI' % (len(minifat_bytes) // 4), minifat_bytes, 0))
    else:
        minifat = []
    ministream = read_chain(root['start'], size=root['size']) if root['start'] not in (_ENDOFCHAIN, _FREESECT) else b''

    def read_mini_chain(start_minisector, size):
        out = bytearray()
        sec = start_minisector
        seen = set()
        while sec not in (_ENDOFCHAIN, _FREESECT):
            if sec in seen or sec >= len(minifat):
                raise ValueError("Corrupt .jws file: MiniFAT chain loop or out-of-range mini-sector")
            seen.add(sec)
            off = sec * mini_sector_size
            out.extend(ministream[off: off + mini_sector_size])
            sec = minifat[sec]
        return bytes(out[:size])

    def read_entry_stream(entry):
        if entry['size'] == 0:
            return b''
        if entry['size'] < mini_cutoff:
            return read_mini_chain(entry['start'], entry['size'])
        return read_chain(entry['start'], size=entry['size'])

    # --- Walk the sibling (red-black) tree from root.child: TOP-LEVEL entries only ---
    top_level = []

    def walk(node_id):
        if node_id == _NOSTREAM or node_id >= len(entries):
            return
        node = entries[node_id]
        walk(node['left'])
        top_level.append(node)
        walk(node['right'])

    walk(root['child'])

    result = {}
    for e in top_level:
        if e['type'] == 2 and e['name'] in wanted_names:  # type 2 == stream
            result[e['name']] = read_entry_stream(e)
    return result


# ---------------------------------------------------------------------------
# DataInfo / Y-Data parsing
# ---------------------------------------------------------------------------

def _parse_data_info(data_info: bytes) -> Dict:
    if len(data_info) < _DI_OFF_X_END + 8:
        raise ValueError(
            "This .jws file's DataInfo block is smaller than expected — "
            "it may be corrupted, or from an unsupported JASCO software version."
        )
    n_channels = struct.unpack_from('<i', data_info, _DI_OFF_N_CHANNELS)[0]
    n_points = struct.unpack_from('<i', data_info, _DI_OFF_N_POINTS)[0]
    x_start = struct.unpack_from('<d', data_info, _DI_OFF_X_START)[0]
    x_end = struct.unpack_from('<d', data_info, _DI_OFF_X_END)[0]
    if n_channels <= 0 or n_points <= 1:
        raise ValueError(
            f"This .jws file has an invalid channel/point count "
            f"(channels={n_channels}, points={n_points}) — it may be "
            f"corrupted or not actually a JASCO .jws spectrum file."
        )
    return {'n_channels': n_channels, 'n_points': n_points, 'x_start': x_start, 'x_end': x_end}


def _classify_channel(y: np.ndarray) -> str:
    """Best-effort channel-type guess from its value range alone — see
    module docstring for the evidence behind these bands. Always returns
    something (never raises); ambiguous ranges fall back to 'Signal'."""
    y_min, y_max = float(np.nanmin(y)), float(np.nanmax(y))
    max_abs = max(abs(y_min), abs(y_max))
    if y_min < 0 < y_max and max_abs < _HT_MIN_MAGNITUDE:
        return 'CD'
    if y_min >= 0 and max_abs >= _HT_MIN_MAGNITUDE:
        return 'HT'
    if y_min >= -0.5 and max_abs <= _ABS_MAX_MAGNITUDE:
        return 'Abs'
    return 'Signal'


_CHANNEL_UNITS = {'CD': 'mdeg', 'HT': 'V', 'Abs': 'AU', 'Signal': ''}
_CHANNEL_DISPLAY = {'CD': 'CD [mdeg]', 'HT': 'HT [V]', 'Abs': 'Absorbance [AU]', 'Signal': 'Signal'}


def probe_jws_channels(filepath: str) -> Dict:
    """
    Read just enough of a .jws file to describe what it contains, for the
    import dialog's channel-selection UI — without committing to any
    channel-type guess being final (the caller shows these as editable
    defaults).

    Returns:
        {
            'n_points': int,
            'x_start': float, 'x_end': float,
            'channels': [
                {'index': int, 'type': 'CD'|'HT'|'Abs'|'Signal',
                 'display': str, 'unit': str, 'y_min': float, 'y_max': float},
                ...
            ],
        }
    """
    with open(filepath, 'rb') as f:
        data = f.read()

    streams = _read_ole_streams(data, _WANTED_STREAMS)
    if 'DataInfo' not in streams or 'Y-Data' not in streams:
        raise ValueError(
            "This .jws file is missing expected internal streams "
            "(DataInfo/Y-Data) — it may be corrupted, or not a JASCO "
            "spectrum file (e.g. a method or report file saved with a "
            "similar extension)."
        )

    info = _parse_data_info(streams['DataInfo'])
    n_channels, n_points = info['n_channels'], info['n_points']

    y_bytes = streams['Y-Data']
    expected_bytes = 4 * n_channels * n_points
    if len(y_bytes) != expected_bytes:
        raise ValueError(
            f"This .jws file's Y-Data size ({len(y_bytes)} bytes) doesn't "
            f"match its declared {n_channels} channel(s) x {n_points} "
            f"point(s) (expected {expected_bytes} bytes) — it may be "
            f"corrupted, or from an unsupported JASCO software version."
        )

    all_y = np.frombuffer(y_bytes, dtype='<f4').reshape(n_channels, n_points)

    channels = []
    for i, y in enumerate(all_y):
        ctype = _classify_channel(y)
        channels.append({
            'index': i,
            'type': ctype,
            'display': _CHANNEL_DISPLAY[ctype],
            'unit': _CHANNEL_UNITS[ctype],
            'y_min': float(np.nanmin(y)),
            'y_max': float(np.nanmax(y)),
        })

    return {
        'n_points': n_points,
        'x_start': info['x_start'],
        'x_end': info['x_end'],
        'channels': channels,
    }


def read_jws_data(
    filepath: str,
    zero_padding: int = 4,
    selected_channels: Optional[List[int]] = None,
    channel_type_overrides: Optional[Dict[int, str]] = None,
) -> List[Dict]:
    """
    Read a JASCO .jws file into one spectrum dict per selected channel.

    selected_channels: zero-based channel indices to import; None (the
    default) imports every channel found. Matches the "user picks which
    spectra to import (Abs / CD / both)" contract from the import dialog.

    channel_type_overrides: {channel_index: 'CD'|'HT'|'Abs'|'Signal'} to
    override this reader's own value-range-based guess (see module
    docstring) with whatever the user confirmed/corrected in the import
    dialog's channel table. Channels not present in this dict keep their
    auto-detected type.

    Each spectrum's label is "<basename> : <channel display>", e.g.
    "ap19-xii : CD [mdeg]" — consistent with how every other multi-
    spectrum-per-file reader in this app (SPE frames, SPC subfiles, table
    columns) derives labels from the source filename plus something that
    disambiguates the spectrum within that file.
    """
    with open(filepath, 'rb') as f:
        data = f.read()

    streams = _read_ole_streams(data, _WANTED_STREAMS)
    if 'DataInfo' not in streams or 'Y-Data' not in streams:
        raise ValueError(
            "This .jws file is missing expected internal streams "
            "(DataInfo/Y-Data) — it may be corrupted, or not a JASCO "
            "spectrum file (e.g. a method or report file saved with a "
            "similar extension)."
        )

    info = _parse_data_info(streams['DataInfo'])
    n_channels, n_points = info['n_channels'], info['n_points']
    x_scale = np.linspace(info['x_start'], info['x_end'], n_points, dtype=float)

    y_bytes = streams['Y-Data']
    expected_bytes = 4 * n_channels * n_points
    if len(y_bytes) != expected_bytes:
        raise ValueError(
            f"This .jws file's Y-Data size ({len(y_bytes)} bytes) doesn't "
            f"match its declared {n_channels} channel(s) x {n_points} "
            f"point(s) (expected {expected_bytes} bytes) — it may be "
            f"corrupted, or from an unsupported JASCO software version."
        )
    all_y = np.frombuffer(y_bytes, dtype='<f4').reshape(n_channels, n_points)

    channel_type_overrides = channel_type_overrides or {}
    indices = range(n_channels) if selected_channels is None else [
        i for i in selected_channels if 0 <= i < n_channels
    ]

    base_name = os.path.splitext(os.path.basename(filepath))[0]
    zero_padding = max(1, zero_padding)

    try:
        file_ctime = _iso_ctime(filepath)
        file_mtime = _iso_mtime(filepath)
    except OSError:
        file_ctime = file_mtime = ''

    spectra: List[Dict] = []
    for i in indices:
        y = all_y[i].astype(float)
        ctype = channel_type_overrides.get(i) or _classify_channel(all_y[i])
        display = _CHANNEL_DISPLAY.get(ctype, ctype)
        label = f"{base_name} : {display}"
        spectra.append({
            'label': label,
            'x_scale': x_scale.copy(),
            'y_scale': y,
            'metadata': {
                'file_path': filepath,
                'file_type': 'jasco_jws',
                'original_label': label,
                'file_ctime': file_ctime,
                'file_mtime': file_mtime,
                'import_parameters': {
                    'channel_index': i,
                    'channel_type': ctype,
                    'channel_type_auto_detected': i not in channel_type_overrides,
                    'n_channels_in_file': n_channels,
                    'unit': _CHANNEL_UNITS.get(ctype, ''),
                },
            },
        })

    logger.info(
        "Created %d spectra from JASCO .jws file %s (%d channel(s) available, %d selected)",
        len(spectra), os.path.basename(filepath), n_channels, len(spectra),
    )
    return spectra


def _iso_ctime(filepath: str) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(os.path.getctime(filepath)).isoformat()


def _iso_mtime(filepath: str) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
