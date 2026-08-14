# src/modules/data_io/spc_data_converter.py
#
# Reader for Thermo/GRAMS Universal Data Format (.spc) files.
#
# .SPC is a binary format with two structurally unrelated header layouts
# that happen to share one file extension, distinguished by a single
# byte (fversn, offset 1):
#
#   0x4D ("old format") — the legacy SpectraCalc/LabCalc header, 256
#       bytes, no multifile/log-block support. This branch is verified
#       against a real sample file (see _read_old_format docstring) —
#       both the header layout AND the unusual word-swapped fixed-point
#       Y-value encoding it uses were cross-checked against that file's
#       actual bytes, not taken from the spec alone.
#
#   0x4B ("new format", LSB-first) — the modern GRAMS/32-era header,
#       512 bytes, with optional multifile and log-block support. This
#       branch follows the published Galactic Universal Data Format
#       Specification and a well-established open-source reference
#       implementation; it has NOT been verified against a real 0x4B
#       sample file (none was available at implementation time — only
#       an 0x4D sample was). It's included because the format is
#       documented and stable, but if a real new-format file produces
#       something that looks wrong, that's the branch to distrust first.
#
#   0x4C ("new format", MSB-first) and any other fversn value — not
#       implemented (MSB-first SPC files are rare in practice; almost
#       everything written on Windows, which is effectively all SPC
#       files, uses 0x4B). Raises a clear error rather than guessing.
#
# Scope: this reads Y-vs-X spectral data (single or multiple subfiles /
# traces per file) into the same flat list-of-spectrum-dicts shape the
# rest of this app's importers use. It does not interpret the optional
# free-text log block beyond exposing it as metadata, and it does not
# handle 4D (W-plane) files — those raise a clear error.

import os
import struct
from typing import List, Dict, Union, Optional

import numpy as np

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared: subheader flag bits, axis-unit label tables
# ---------------------------------------------------------------------------

_SUBHEADER_FMT = '<BBhfffiif4s'   # subflgs, subexp, subindx, subtime, subnext,
                                  # subnois, subnpts, subscan, subwlevel, subresv
_SUBHEADER_SIZE = struct.calcsize(_SUBHEADER_FMT)   # 32 bytes


def _flag_bits(byte_val: int):
    """Return (tsprec, tcgram, tmulti, trandm, tordrd, talabs, txyxys, txvals)
    — the 8 flag bits of ftflgs/oftflgs, bit0 (LSB) through bit7 (MSB)."""
    return tuple((byte_val >> i) & 1 for i in range(8))


def _read_subheader(b: bytes) -> dict:
    (subflgs, subexp, subindx, subtime, subnext,
     subnois, subnpts, subscan, subwlevel, subresv) = struct.unpack(_SUBHEADER_FMT, b)
    return {
        'subflgs': subflgs, 'subexp': subexp, 'subindx': subindx,
        'subtime': subtime, 'subnext': subnext, 'subnois': subnois,
        'subnpts': subnpts, 'subscan': subscan, 'subwlevel': subwlevel,
    }


# X/Y axis type -> human-readable unit, straight from the Galactic UDF
# spec's fxtype/fytype tables. Used only to label metadata; never
# affects parsing.
_XTYPE_LABELS = [
    "Arbitrary", "Wavenumber (cm-1)", "Micrometers (um)", "Nanometers (nm)",
    "Seconds", "Minutes", "Hertz (Hz)", "Kilohertz (KHz)", "Megahertz (MHz)",
    "Mass (M/z)", "Parts per million (PPM)", "Days", "Years",
    "Raman Shift (cm-1)", "eV", "XYZ text labels", "Diode Number", "Channel",
    "Degrees", "Temperature (F)", "Temperature (C)", "Temperature (K)",
    "Data Points", "Milliseconds (mSec)", "Microseconds (uSec)",
    "Nanoseconds (nSec)", "Gigahertz (GHz)", "Centimeters (cm)",
    "Meters (m)", "Millimeters (mm)", "Hours",
]
_YTYPE_LABELS = [
    "Arbitrary Intensity", "Interferogram", "Absorbance", "Kubelka-Munk",
    "Counts", "Volts", "Degrees", "Milliamps", "Millimeters", "Millivolts",
    "Log(1/R)", "Percent", "Intensity", "Relative Intensity", "Energy", "",
    "Decibel", "", "", "Temperature (F)", "Temperature (C)",
    "Temperature (K)", "Index of Refraction [N]", "Extinction Coeff. [K]",
    "Real", "Imaginary", "Complex",
]
_YTYPE_LABELS_HIGH = {128: "Transmission", 129: "Reflectance",
                       130: "Arbitrary or Single Beam with Valley Peaks", 131: "Emission"}


def _axis_label(code: int, table: list) -> str:
    if 0 <= code < len(table) and table[code]:
        return table[code]
    return f"Unknown ({code})"


def _y_label(code: int) -> str:
    if code in _YTYPE_LABELS_HIGH:
        return _YTYPE_LABELS_HIGH[code]
    return _axis_label(code, _YTYPE_LABELS)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def read_spc_data(filepath: str, zero_padding: int = 4) -> List[Dict[str, Union[np.ndarray, str, Dict]]]:
    """
    Read a Thermo/GRAMS .spc file and return one spectrum per subfile
    (trace) it contains — almost always 1, occasionally more for a
    file holding a short time series or similar.

    Parameters
    ----------
    filepath     : path to the .spc file
    zero_padding : digit width for auto-generated subfile numbers, used
                   only when a file has more than one subfile (matches
                   the convention used elsewhere in this app)

    Raises ValueError with a specific, honest message for file-format
    variants this reader doesn't recognise (MSB new-format, 4D/W-plane
    files, corrupted/truncated data) — never silently guesses.
    """
    logger.info("Importing SPC: %s", os.path.basename(filepath))

    with open(filepath, 'rb') as fh:
        data = fh.read()

    if len(data) < 2:
        raise ValueError("File is too small to be a valid .spc file.")

    ftflgs, fversn = data[0], data[1]

    if fversn == 0x4D:
        return _read_old_format(data, filepath, zero_padding)
    if fversn == 0x4B:
        return _read_new_format(data, filepath, zero_padding)
    if fversn == 0x4C:
        raise ValueError(
            "This is a new-format SPC file in MSB-first byte order "
            "(fversn=0x4C) — vanishingly rare in practice and not "
            "currently supported. If this is a genuine file, please "
            "report it."
        )
    raise ValueError(
        f"Unrecognised SPC file version byte {hex(fversn)} at offset 1 — "
        f"this doesn't look like a Thermo/GRAMS SPC file (expected 0x4B, "
        f"0x4C, or 0x4D)."
    )


# ---------------------------------------------------------------------------
# Old format (fversn = 0x4D)
# ---------------------------------------------------------------------------

# oftflgs, oversn, oexp, onpts, ofirst, olast, fxtype, fytype, oyear,
# omonth, oday, ohour, ominute, ores(8s), opeakpt, onscans, ospare(28s),
# ocmnt(130s), ocatxt(30s), osubh1(32s, the first subfile's subheader,
# embedded in the tail of the main header)
_OLD_HEADER_FMT = '<BBhfffBBhBBBB8shh28s130s30s32s'
_OLD_HEADER_SIZE = struct.calcsize(_OLD_HEADER_FMT)   # 256 bytes


def _read_old_format(data: bytes, filepath: str, zero_padding: int) -> List[Dict]:
    """
    Parse an old-format (fversn=0x4D) SPC file — the legacy
    SpectraCalc/LabCalc header, verified against a real sample file
    (940-point Raman-shift spectrum, single subfile): header layout,
    the embedded first-subheader trick (see below), and the Y-value
    word-swapped fixed-point decoding all reproduced that file's values
    exactly against an independent reference parser before being
    reimplemented here.

    Layout
    ------
    A 256-byte main header, whose LAST 32 bytes double as the subheader
    for the first subfile (there's no separate leading subheader block
    for subfile 0 — the old format folds it into the main header to
    save space). Each subfile is then [32-byte subheader][pts * 4 bytes
    of Y data], back-to-back, for as many subfiles as fit in the file
    (the old format doesn't declare a subfile count up front the way
    the new format's fnsub does, so subfiles are read until the data
    runs out).

    Y-value encoding
    -----------------
    If the subfile's own exponent byte is 128, Y values are plain
    IEEE float32. Otherwise they're Galactic's old fixed-point format:
    4 bytes per point, stored as an unsigned 32-bit word with its two
    16-bit halves swapped (byte order becomes B1,B0,B3,B2 instead of
    B0,B1,B2,B3), reinterpreted as a signed 32-bit integer, then scaled
    by 2**(exponent - 32).

    X values are implicit and evenly spaced between ofirst and olast
    over onpts points — the old format doesn't support explicit/uneven
    X arrays.
    """
    if len(data) < _OLD_HEADER_SIZE:
        raise ValueError(
            "This file is smaller than the fixed 256-byte old-format SPC "
            "header — it may be truncated or corrupted."
        )

    (oftflgs, oversn, oexp, onpts, ofirst, olast, fxtype, fytype,
     oyear, omonth, oday, ohour, ominute, ores, opeakpt, onscans,
     ospare, ocmnt, ocatxt, osubh1) = struct.unpack(_OLD_HEADER_FMT, data[:_OLD_HEADER_SIZE])

    onpts = int(onpts)
    if onpts <= 0:
        raise ValueError(
            f"This old-format SPC file declares {onpts} points — it may "
            f"be corrupted, or use a variant (e.g. an XYXY directory) "
            f"this reader doesn't recognise."
        )

    _tsprec, _tcgram, _tmulti, _trandm, _tordrd, talabs, txyxys, txvals = _flag_bits(oftflgs)
    if txyxys or txvals:
        raise ValueError(
            "This old-format SPC file uses explicit per-point X values "
            "(TXYXYS/TXVALS) — only the common implicit evenly-spaced "
            "X-axis variant is currently supported for old-format files."
        )

    x_scale = np.linspace(ofirst, olast, onpts)

    ores_txt = ores.split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()
    ocmnt_txt = ocmnt.split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()

    # The first subfile's subheader is the last 32 bytes of the main
    # header — so "rewind" 32 bytes to line up with the general
    # [subheader][data] loop below.
    sub_pos = _OLD_HEADER_SIZE - _SUBHEADER_SIZE
    subfiles = []
    while sub_pos + _SUBHEADER_SIZE <= len(data):
        subhead = _read_subheader(data[sub_pos: sub_pos + _SUBHEADER_SIZE])
        pts = subhead['subnpts'] if subhead['subnpts'] > 0 else onpts

        y_start = sub_pos + _SUBHEADER_SIZE
        y_end = y_start + 4 * pts
        if y_end > len(data):
            # Not enough data left for a full subfile — stop here rather
            # than raising, since the old format has no declared subfile
            # count and this is simply "end of file reached".
            break

        subexp = subhead['subexp']
        if subexp == 128:
            y_scale = np.array(struct.unpack(f'<{pts}f', data[y_start:y_end]))
        else:
            exp = subexp if 0 < subexp < 128 else oexp
            raw = struct.unpack(f'>{4 * pts}B', data[y_start:y_end])
            words = np.empty(pts, dtype=np.int64)
            for k in range(pts):
                b0, b1, b2, b3 = raw[4 * k: 4 * k + 4]
                words[k] = b1 * (256 ** 3) + b0 * (256 ** 2) + b3 * 256 + b2
            y_scale = np.int32(words).astype(float) / (2.0 ** (32 - exp))

        subfiles.append({'y_scale': y_scale, 'subheader': subhead})
        sub_pos = y_end

    if not subfiles:
        raise ValueError(
            "Could not read any subfile data from this old-format SPC "
            "file — it may be truncated or corrupted."
        )

    xlabel = _axis_label(fxtype, _XTYPE_LABELS)
    ylabel = _y_label(fytype)
    if talabs and ocatxt:
        parts = ocatxt.split(b'\x00')
        if len(parts) >= 2:
            xl = parts[0].decode('ascii', errors='replace').strip()
            yl = parts[1].decode('ascii', errors='replace').strip()
            xlabel = xl or xlabel
            ylabel = yl or ylabel

    base_name = os.path.splitext(os.path.basename(filepath))[0]
    zero_padding = max(1, zero_padding)
    multi = len(subfiles) > 1

    spectra: List[Dict] = []
    for i, sub in enumerate(subfiles):
        label = f"{base_name} : {str(i + 1).zfill(zero_padding)}" if multi else base_name
        spectra.append({
            'label': label,
            'x_scale': x_scale.copy(),
            'y_scale': sub['y_scale'],
            'metadata': {
                'file_path': filepath,
                'file_type': 'spc_old_format',
                'original_label': label,
                'import_parameters': {
                    'spc_format': 'old (0x4D)',
                    'subfile_index': i,
                    'n_subfiles': len(subfiles),
                    'x_label': xlabel,
                    'y_label': ylabel,
                    'resolution': ores_txt or None,
                    'comment': ocmnt_txt or None,
                    'acquisition_date': (
                        f"{omonth:02d}/{oday:02d}/{oyear:04d} {ohour:02d}:{ominute:02d}"
                        if oyear else None
                    ),
                    'uncalibrated': False,
                    'detection_mode': 'spc_old',
                },
            },
        })

    logger.info(
        "Created %d spectra from SPC file %s (old format, x=%s, y=%s)",
        len(spectra), os.path.basename(filepath), xlabel, ylabel,
    )
    return spectra


# ---------------------------------------------------------------------------
# New format (fversn = 0x4B, LSB-first)
# ---------------------------------------------------------------------------

# ftflg, fversn, fexper, fexp, fnpts, ffirst, flast, fnsub, fxtype,
# fytype, fztype, fpost, fdate, fres(9s), fsource(9s), fpeakpt,
# fspare(32s), fcmnt(130s), fcatxt(30s), flogoff, fmods, fprocs,
# flevel, fsampin, ffactor, fmethod(48s), fzinc, fwplanes, fwinc,
# fwtype, freserv(187s)
_NEW_HEADER_FMT = '<BBBBiddiBBBBi9s9sh32s130s30siiBBhf48sfifB187s'
_NEW_HEADER_SIZE = struct.calcsize(_NEW_HEADER_FMT)   # 512 bytes


def _read_new_format(data: bytes, filepath: str, zero_padding: int) -> List[Dict]:
    """
    Parse a new-format (fversn=0x4B, LSB-first) SPC file, per the
    published Galactic Universal Data Format Specification.

    NOT verified against a real 0x4B sample file — see the module
    docstring. Structurally this mirrors the old-format reader above
    but with the richer new-format capabilities: an explicit subfile
    count (fnsub), optional shared or per-subfile X arrays (TXVALS /
    TXYXYS), and per-subfile exponents when TMULTI is set.

    Supported: Y-only shared-X files (any fnsub), and shared explicit-X
    files (TXVALS). NOT supported: per-subfile explicit X (TXYXYS) or
    a subfile directory (both raise a clear error) — these are
    genuinely rarer variants and better added once a real sample
    surfaces to verify against.
    """
    if len(data) < _NEW_HEADER_SIZE:
        raise ValueError(
            "This file is smaller than the fixed 512-byte new-format SPC "
            "header — it may be truncated or corrupted."
        )

    (ftflg, fversn, fexper, fexp, fnpts, ffirst, flast, fnsub, fxtype,
     fytype, fztype, fpost, fdate, fres, fsource, fpeakpt, fspare,
     fcmnt, fcatxt, flogoff, fmods, fprocs, flevel, fsampin, ffactor,
     fmethod, fzinc, fwplanes, fwinc, fwtype, freserv) = struct.unpack(
        _NEW_HEADER_FMT, data[:_NEW_HEADER_SIZE])
    # fexp (and each subfile's subexp) is read as an unsigned byte: 0x80
    # (128) is the documented sentinel meaning "Y values are floats",
    # not a two's-complement -128 — matches the Galactic UDF spec and
    # every reference reader of this format.

    tsprec, _tcgram, tmulti, _trandm, _tordrd, talabs, txyxys, txvals = _flag_bits(ftflg)

    if txyxys:
        raise ValueError(
            "This SPC file stores a separate X array per subfile "
            "(TXYXYS) — this variant isn't currently supported. Please "
            "report this file so support can be added and verified "
            "against it."
        )

    fnpts = int(fnpts)
    fnsub = max(1, int(fnsub))
    if fnpts <= 0:
        raise ValueError(
            f"This SPC file declares {fnpts} points per subfile — it may "
            f"be corrupted or use a directory-based layout this reader "
            f"doesn't recognise."
        )

    pos = _NEW_HEADER_SIZE
    if txvals:
        x_end = pos + 4 * fnpts
        if x_end > len(data):
            raise ValueError("SPC file is truncated — not enough data for the declared X array.")
        x_scale = np.array(struct.unpack(f'<{fnpts}f', data[pos:x_end]))
        pos = x_end
    else:
        x_scale = np.linspace(ffirst, flast, fnpts)

    subfiles = []
    for _ in range(fnsub):
        if pos + _SUBHEADER_SIZE > len(data):
            raise ValueError(
                f"SPC file is truncated — expected {fnsub} subfile(s) but "
                f"ran out of data after {len(subfiles)}."
            )
        subhead = _read_subheader(data[pos: pos + _SUBHEADER_SIZE])
        y_start = pos + _SUBHEADER_SIZE

        exp = subhead['subexp'] if tmulti else fexp
        if not (-128 < exp <= 128):
            exp = 0

        if exp == 128:
            y_end = y_start + 4 * fnpts
            if y_end > len(data):
                raise ValueError("SPC file is truncated — not enough data for a subfile's Y values.")
            y_scale = np.array(struct.unpack(f'<{fnpts}f', data[y_start:y_end]))
        elif tsprec:
            y_end = y_start + 2 * fnpts
            if y_end > len(data):
                raise ValueError("SPC file is truncated — not enough data for a subfile's Y values.")
            y_raw = np.array(struct.unpack(f'<{fnpts}h', data[y_start:y_end]))
            y_scale = y_raw * (2.0 ** (exp - 16))
        else:
            y_end = y_start + 4 * fnpts
            if y_end > len(data):
                raise ValueError("SPC file is truncated — not enough data for a subfile's Y values.")
            y_raw = np.array(struct.unpack(f'<{fnpts}i', data[y_start:y_end]))
            y_scale = y_raw * (2.0 ** (exp - 32))

        subfiles.append(y_scale)
        pos = y_end

    xlabel = _axis_label(fxtype, _XTYPE_LABELS)
    ylabel = _y_label(fytype)
    if talabs and fcatxt:
        parts = fcatxt.split(b'\x00')
        if len(parts) >= 2:
            xl = parts[0].decode('ascii', errors='replace').strip()
            yl = parts[1].decode('ascii', errors='replace').strip()
            xlabel = xl or xlabel
            ylabel = yl or ylabel

    fcmnt_txt = fcmnt.split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()

    # fdate is a packed bitfield: year(12) | month(4) | day(5) | hour(5) | minute(6)
    year = fdate >> 20
    month = (fdate >> 16) % 16
    day = (fdate >> 11) % 32
    hour = (fdate >> 6) % 32
    minute = fdate % 64

    base_name = os.path.splitext(os.path.basename(filepath))[0]
    zero_padding = max(1, zero_padding)
    multi = len(subfiles) > 1

    spectra: List[Dict] = []
    for i, y_scale in enumerate(subfiles):
        label = f"{base_name} : {str(i + 1).zfill(zero_padding)}" if multi else base_name
        spectra.append({
            'label': label,
            'x_scale': x_scale.copy(),
            'y_scale': y_scale,
            'metadata': {
                'file_path': filepath,
                'file_type': 'spc_new_format',
                'original_label': label,
                'import_parameters': {
                    'spc_format': 'new (0x4B)',
                    'subfile_index': i,
                    'n_subfiles': len(subfiles),
                    'x_label': xlabel,
                    'y_label': ylabel,
                    'comment': fcmnt_txt or None,
                    'acquisition_date': f"{month:02d}/{day:02d}/{year:04d} {hour:02d}:{minute:02d}" if year else None,
                    'uncalibrated': False,
                    'detection_mode': 'spc_new',
                },
            },
        })

    logger.info(
        "Created %d spectra from SPC file %s (new format, x=%s, y=%s)",
        len(spectra), os.path.basename(filepath), xlabel, ylabel,
    )
    return spectra
