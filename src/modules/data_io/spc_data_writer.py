# src/modules/data_io/spc_data_writer.py
#
# Writer for Thermo/GRAMS Universal Data Format (.spc) files — the export
# counterpart to spc_data_converter.py's reader.
#
# Scope, deliberately narrow and chosen to match what the reader already
# verifiably supports round-tripping, rather than the full Galactic UDF
# spec:
#
#   - New format only (fversn = 0x4B, LSB-first). This is the modern
#     GRAMS/32-era format current software expects by default; the old
#     0x4D format's word-swapped fixed-point Y encoding has no benefit
#     for freshly-written files and just adds risk.
#
#   - Y values always written as plain IEEE float32 (the fexp=128
#     sentinel) — never the old fixed-point encoding. No precision lost
#     for this app's data (already float64 in memory; float32 is what
#     GRAMS itself stores for float-mode files) and it sidesteps an
#     entire class of encoding bugs.
#
#   - X values always written EXPLICITLY (TXVALS), never as an implicit
#     evenly-spaced ffirst/flast/fnpts range — real imported spectra are
#     not reliably evenly spaced, and explicit X is lossless regardless.
#
#   - One shared X-axis across every subfile in a file (TMULTI off,
#     shared fexp, one shared X array). Multiple spectra with DIFFERING
#     x-axes are not written into a single .spc — write them as separate
#     single-subfile files instead (see write_spc_data's docstring).
#
# This mirrors exactly the "Y-only shared-X files (any fnsub), and shared
# explicit-X files (TXVALS)" case spc_data_converter._read_new_format's
# own docstring lists as supported — so every file this writer produces
# is verified readable by this app's own importer.

import os
import struct
from datetime import datetime
from typing import List, Optional

import numpy as np

from src.modules.data_io.spc_data_converter import (
    _NEW_HEADER_FMT, _NEW_HEADER_SIZE,
    _SUBHEADER_FMT, _SUBHEADER_SIZE,
    _XTYPE_LABELS, _YTYPE_LABELS,
)

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)


def _guess_axis_code(label: Optional[str], table: list) -> int:
    """Reverse-lookup a human-readable axis label (e.g. from a spectrum
    that was originally imported FROM an .spc file, see
    spc_data_converter's 'x_label'/'y_label' import_parameters) back to
    its Galactic UDF type code. Falls back to 0 ("Arbitrary" /
    "Arbitrary Intensity") when the label is missing or unrecognised —
    always a safe, valid code, never a guess that could mislead a reader
    about the data's actual units.
    """
    if not label:
        return 0
    try:
        return table.index(label)
    except ValueError:
        return 0


def _axis_codes_for_spectrum(spectrum: dict) -> (int, int):
    """Best-effort (x_type, y_type) codes for *spectrum*, using labels
    stashed by spc_data_converter on a previous SPC import if present
    (see its 'import_parameters'), else "Arbitrary" for both — never
    fabricated."""
    params = (spectrum.get('metadata') or {}).get('import_parameters', {}) or {}
    x_code = _guess_axis_code(params.get('x_label'), _XTYPE_LABELS)
    y_code = _guess_axis_code(params.get('y_label'), _YTYPE_LABELS)
    return x_code, y_code


def _pack_fdate(dt: Optional[datetime]) -> int:
    """Pack a datetime into the fdate bitfield spc_data_converter reads
    as: year(12) | month(4) | day(5) | hour(5) | minute(6). Returns 0
    (which the reader treats as "no date", see 'if year else None')
    when *dt* is None."""
    if dt is None:
        return 0
    return ((dt.year & 0xFFF) << 20) | ((dt.month & 0xF) << 16) | \
           ((dt.day & 0x1F) << 11) | ((dt.hour & 0x1F) << 6) | (dt.minute & 0x3F)


def _str_field(text: Optional[str], size: int) -> bytes:
    """Encode *text* (or '') as ASCII, replacing anything that doesn't
    fit, and null-pad/truncate to exactly *size* bytes — struct.pack's
    Ns format requires exactly this length."""
    raw = (text or '').encode('ascii', errors='replace')[:size]
    return raw + b'\x00' * (size - len(raw))


def write_spc_data(
    filepath: str,
    spectra: List[dict],
    comment: Optional[str] = None,
) -> None:
    """
    Write *spectra* to a new-format (fversn=0x4B) GRAMS/Thermo .spc file,
    one subfile per spectrum, all sharing one explicit X-axis.

    Parameters
    ----------
    filepath : destination path
    spectra  : list of spectrum dicts, each with 'x_scale' and 'y_scale'.
               MUST all share an IDENTICAL x-scale (same length, same
               values) — this is not checked here; the caller (see
               SaveManager) is responsible for that, using the same
               axes_match-based check every other "combine spectra" tool
               in this app already applies. Passing spectra with
               different x-axes will silently write the FIRST spectrum's
               x-axis as the shared axis and pair it with every other
               spectrum's y-values regardless of what x they actually
               belong to — exactly the kind of silent mismatch this
               app's ascending-x/common-axis invariants exist to avoid
               elsewhere, so callers must not skip validating this.
    comment  : optional text stored in the file's comment field
               (fcmnt) — round-trips back out as
               metadata['import_parameters']['comment'] if this file is
               later re-imported.

    Multiple spectra with DIFFERING x-axes are not supported in one
    file — call this once per spectrum (a 1-element list) for each, the
    same way SaveManager.save_individual already does for text/Excel.

    Raises ValueError if *spectra* is empty, spectra have mismatched
    lengths, or any spectrum is empty.
    """
    if not spectra:
        raise ValueError("No spectra to write")

    n_sub = len(spectra)
    x_ref = np.asarray(spectra[0]['x_scale'], dtype=np.float32)
    n_pts = len(x_ref)
    if n_pts == 0:
        raise ValueError("Cannot write an SPC file with zero data points")

    for sp in spectra:
        y = np.asarray(sp['y_scale'], dtype=np.float32)
        if len(y) != n_pts:
            raise ValueError(
                f"All spectra written to one .spc file must share the same "
                f"x-scale — spectrum {sp.get('label', '?')!r} has "
                f"{len(y)} points, expected {n_pts}."
            )

    x_type, y_type = _axis_codes_for_spectrum(spectra[0])

    # ftflg bits: bit0 tsprec, bit1 tcgram, bit2 tmulti, bit3 trandm,
    # bit4 tordrd, bit5 talabs, bit6 txyxys, bit7 txvals.
    # txvals=1 (explicit shared X array follows the header); everything
    # else off — see module docstring for why.
    ftflg = 0b10000000  # txvals only

    header = struct.pack(
        _NEW_HEADER_FMT,
        ftflg,                  # ftflg
        0x4B,                   # fversn — new format, LSB-first
        0,                      # fexper — unspecified/general
        128,                    # fexp — 128 sentinel: Y values are float32
        n_pts,                  # fnpts
        float(x_ref.min()) if n_pts else 0.0,  # ffirst (informational only — txvals wins)
        float(x_ref.max()) if n_pts else 0.0,  # flast  (informational only — txvals wins)
        n_sub,                  # fnsub
        x_type,                 # fxtype
        y_type,                 # fytype
        0,                      # fztype — not a Z-plane series
        0,                      # fpost
        _pack_fdate(datetime.now()),  # fdate — export timestamp
        _str_field(None, 9),    # fres
        _str_field(None, 9),    # fsource
        0,                      # fpeakpt
        _str_field(None, 32),   # fspare
        _str_field(comment or 'Exported by SpecAnalytiXBase', 130),  # fcmnt
        _str_field(None, 30),   # fcatxt — unused (talabs off)
        0,                      # flogoff — no log block
        0,                      # fmods
        0,                      # fprocs
        0,                      # flevel
        0,                      # fsampin
        0.0,                    # ffactor
        _str_field(None, 48),   # fmethod
        0.0,                    # fzinc
        0,                      # fwplanes
        0.0,                    # fwinc
        0,                      # fwtype
        _str_field(None, 187),  # freserv
    )
    if len(header) != _NEW_HEADER_SIZE:
        # Defensive — would mean _NEW_HEADER_FMT and this function have
        # drifted apart; must never actually happen since the format is
        # imported directly from the reader, not duplicated here.
        raise RuntimeError(
            f"Internal error: built a {len(header)}-byte SPC header, "
            f"expected {_NEW_HEADER_SIZE}."
        )

    chunks = [header, struct.pack(f'<{n_pts}f', *x_ref.tolist())]

    for i, sp in enumerate(spectra):
        y = np.asarray(sp['y_scale'], dtype=np.float32)
        subheader = struct.pack(
            _SUBHEADER_FMT,
            0,      # subflgs
            128,    # subexp — ignored when tmulti=0, set for consistency
            i,      # subindx
            0.0,    # subtime
            0.0,    # subnext
            0.0,    # subnois
            n_pts,  # subnpts
            0,      # subscan
            0.0,    # subwlevel
            b'\x00\x00\x00\x00',  # subresv
        )
        if len(subheader) != _SUBHEADER_SIZE:
            raise RuntimeError(
                f"Internal error: built a {len(subheader)}-byte SPC "
                f"subheader, expected {_SUBHEADER_SIZE}."
            )
        chunks.append(subheader)
        chunks.append(struct.pack(f'<{n_pts}f', *y.tolist()))

    try:
        with open(filepath, 'wb') as fh:
            fh.write(b''.join(chunks))
    except OSError as exc:
        raise RuntimeError(f"Failed to write SPC file '{filepath}': {exc}") from exc

    logger.info(
        "Wrote SPC file %s: %d subfile(s), %d points each, x=%s, y=%s",
        os.path.basename(filepath), n_sub, n_pts,
        _XTYPE_LABELS[x_type] if 0 <= x_type < len(_XTYPE_LABELS) else x_type,
        _YTYPE_LABELS[y_type] if 0 <= y_type < len(_YTYPE_LABELS) else y_type,
    )
