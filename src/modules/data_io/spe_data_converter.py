# src/modules/data_io/spe_data_converter.py
#
# Reader for Princeton Instruments / Roper / Teledyne .spe files.
#
# Two structurally different formats share the .spe extension, and both
# are handled here:
#
#   - LightField SPE 3.x  — identified by the XML "SpeFormat" footer.
#     Handled by _read_lightfield_spe(). See that function's docstring
#     for the scope notes that applied before legacy support was added
#     (single-region, single-row, RAW pixel data only).
#
#   - WinSpec 2.x (legacy) — no XML footer; a fixed 4100-byte binary
#     header only, as written by WinSpec/WinView (Roper/Princeton
#     Instruments) prior to LightField. Handled by _read_legacy_spe().
#     Verified against a real WinSpec 2.6 file (see _validate_layout
#     comments below) rather than implemented from the spec blind.
#
# Both formats share the same 4100-byte legacy header size (the new
# format keeps it for backward compatibility, even though it then
# ignores most of it in favour of the XML footer). That's the only
# thing they share structurally — everything else is format-specific.
#
# Common scope, deliberately narrow for both formats:
#
#   - RAW pixel data only, no wavelength calibration. Each stored frame
#     becomes one spectrum, with a plain pixel-index x-axis
#     (0..width-1) — explicitly NOT wavelength or wavenumber. This
#     matches the intended use case: quick viewing of raw acquisitions
#     during measurement, not final calibrated analysis (that happens
#     via a separate calibration step producing calibrated text files,
#     which already import through the normal Standard/Row-oriented/
#     Interlaced paths — see table_data_converter.py). WinSpec 2.x
#     files do carry an X-calibration block in the legacy header (at
#     byte offset 3000), but it's left unread here for the same reason
#     LightField's calibration is: this reader is for quick raw viewing,
#     and reading it out would make the two formats behave differently
#     for no benefit to that use case.
#
#   - Single-region (single ROI), single-row (fully vertically-binned)
#     frames only — i.e. 1D spectra, not 2D images or multi-ROI
#     acquisitions. Anything else raises a clear error.

import os
import struct
import xml.etree.ElementTree as ET
from typing import List, Dict, Union, Optional

import numpy as np

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

_LEGACY_HEADER_SIZE = 4100   # fixed by the SPE format spec (v2 and v3 alike)

_SPE_XML_NS = {'spe': 'http://www.princetoninstruments.com/spe/2009'}

# Princeton Instruments pixelFormat -> numpy dtype (little-endian).
# Only formats actually documented/observed are mapped; anything else
# raises a clear error rather than guessing at byte width or signedness.
_PIXEL_FORMATS = {
    'MonochromeUnsigned16': '<u2',
    'MonochromeUnsigned32': '<u4',
    'MonochromeFloating32': '<f4',
}

# WinSpec 2.x legacy header "datatype" field (offset 108) -> numpy dtype.
# This is the same 4-way encoding used throughout the WinSpec-family
# ecosystem (confirmed against multiple independent readers of the
# format, and cross-checked against our own sample file: datatype=0
# with xdim=1340 leaves exactly xdim*4 bytes of frame data, which only
# lines up if 0 means a 4-byte float).
_LEGACY_DATATYPES = {
    0: '<f4',   # float
    1: '<i4',   # long (32-bit signed)
    2: '<i2',   # short (16-bit signed)
    3: '<u2',   # unsigned short (16-bit unsigned) — the common case for
                # raw camera counts
}

# WinSpec 2.x legacy "AxisCalibration" struct — one copy at byte offset
# 3000 (x-axis) inside the 4100-byte header, describing an optional
# calibration polynomial that maps pixel number -> a real physical unit
# (wavelength, wavenumber, ...). Offsets below, relative to the struct's
# own start, are NOT taken from the spec blind — they were derived from
# the full WinSpec 2.6 header layout (every other field's offset in this
# module, including xdim/datatype/ydim/NumFrames/NumROI above, matches
# this exact same layout) and then independently verified against
# kwater001.SPE, a real calibrated sample file: evaluating this
# polynomial at the file's own recorded calibration pixel positions
# (1.0, 670.5, 1340.0) reproduces its own recorded calibration values
# (547.7003195150578, 584.0, 618.6296787355756 nm) to full float64
# precision — not an approximate match, an exact one.
_XCALIB_STRUCT_OFFSET   = 3000   # absolute offset of AxisCalibration within the header
_XCALIB_VALID_OFFSET    = 98     # bool: whether this calibration is populated at all
_XCALIB_POLY_ORDER_OFFSET = 101  # order of the calibration polynomial (0-6)
_XCALIB_POLY_COEFF_OFFSET = 263  # 6 x float64: constant term first (c0, c1, c2, ...)
_XCALIB_UNIT_STRING_OFFSET = 18  # 40-byte null-terminated axis unit label, e.g. "Wavelength [nm]"
_XCALIB_LASER_POS_OFFSET = 311   # float64: laser wavelength/wavenumber, 0.0 if not applicable


def read_spe_data(
    filepath: str,
    zero_padding: int = 4,
    use_calibration: bool = False,
) -> List[Dict[str, Union[np.ndarray, str, Dict]]]:
    """
    Read a Princeton Instruments / Roper .spe file (LightField 3.x or
    legacy WinSpec 2.x — auto-detected) and return one spectrum per
    stored frame.

    By default (use_calibration=False) every spectrum gets a raw,
    uncalibrated pixel-index x-axis (0..width-1) — this reader's
    original, unconditional behaviour.

    Parameters
    ----------
    filepath        : path to the .spe file
    zero_padding    : digit width for auto-generated frame numbers
                       (matches the convention used for headerless text
                       files elsewhere in this app)
    use_calibration : if True, and the file is a legacy WinSpec file
                       carrying a valid x-axis calibration (see
                       _read_x_calibration), spectra get that real,
                       physical x-axis (wavelength, wavenumber, ...)
                       instead of the pixel index. Every spectrum's
                       metadata records whether calibration was actually
                       available and used (see 'calibration_available' /
                       'x_axis_calibrated'), regardless of this flag, so
                       the caller can always tell what it got — silently
                       falls back to the pixel axis (not an error) if
                       calibration was requested but this specific file
                       doesn't have any. LightField 3.x files are not
                       currently supported for calibration (see
                       _read_lightfield_spe) — this flag is simply
                       ignored for them, pixel index only, same as
                       before.

    Raises ValueError with a specific, honest message if the file uses
    a layout this reader doesn't recognise (multi-region, 2D frames, or
    an unmapped pixel format/datatype) — never silently guesses at an
    unverified binary layout.
    """
    logger.info("Importing SPE: %s", os.path.basename(filepath))

    with open(filepath, 'rb') as fh:
        data = fh.read()

    if data.find(b'<SpeFormat') != -1:
        return _read_lightfield_spe(data, filepath, zero_padding)
    return _read_legacy_spe(data, filepath, zero_padding, use_calibration)


# ---------------------------------------------------------------------------
# WinSpec 2.x legacy X-axis calibration
# ---------------------------------------------------------------------------

def _read_x_calibration(data: bytes) -> Optional[Dict]:
    """
    Parse the legacy WinSpec "AxisCalibration" struct for the x-axis
    (byte offset 3000 in the 4100-byte header — see the module-level
    _XCALIB_* offset constants and their verification note).

    Returns None if the file carries no valid calibration (calib_valid
    byte is 0 — the common case for a raw/uncalibrated acquisition, and
    always the case for non-spectral acquisitions like a 2D image).
    Otherwise returns a dict with the polynomial and axis label needed
    to convert pixel number -> physical x-value:

        {'polynom_coeff': [c0, c1, ...],  # constant term first
         'unit_label': 'Wavelength [nm]', # or '' if the file left it blank
         'laser_position': 532.0}         # or None if not recorded
    """
    base = _XCALIB_STRUCT_OFFSET
    if len(data) < base + 400:   # calibration struct plus a safety margin
        return None

    calib_valid = data[base + _XCALIB_VALID_OFFSET]
    if not calib_valid:
        return None

    polynom_order = data[base + _XCALIB_POLY_ORDER_OFFSET]
    if not (0 <= polynom_order <= 5):
        # A corrupt/garbage order would index past the 6-coefficient
        # array below — treat as "no usable calibration" rather than
        # guessing or raising, the same as calib_valid=0.
        return None

    coeff_all = struct.unpack_from('<6d', data, base + _XCALIB_POLY_COEFF_OFFSET)
    polynom_coeff = list(coeff_all[:polynom_order + 1])

    unit_label = data[base + _XCALIB_UNIT_STRING_OFFSET: base + _XCALIB_UNIT_STRING_OFFSET + 40]
    unit_label = unit_label.split(b'\x00')[0].decode('ascii', errors='replace')

    laser_position = struct.unpack_from('<d', data, base + _XCALIB_LASER_POS_OFFSET)[0]

    return {
        'polynom_coeff': polynom_coeff,
        'unit_label': unit_label,
        'laser_position': laser_position if laser_position else None,
    }


def _evaluate_x_calibration(calib: Dict, xdim: int) -> np.ndarray:
    """
    Evaluate a calibration polynomial (see _read_x_calibration) across
    *xdim* pixels, returning the calibrated x-axis as a float64 array.

    WinSpec's own calibration convention uses 1-indexed pixel numbers
    (pixel_position control points in the file itself run 1..xdim, not
    0..xdim-1) — confirmed directly: evaluating with 1-indexed pixels
    reproduces kwater001.SPE's own recorded calibration values exactly
    (see the offset-table comment above). This is purely an internal
    detail of the polynomial evaluation; the UNCALIBRATED pixel-index
    x-axis this reader normally produces elsewhere is unaffected and
    stays 0-indexed as before.
    """
    coeff_highest_first = calib['polynom_coeff'][::-1]   # np.polyval wants highest-order first
    pixels = np.arange(1, xdim + 1, dtype=float)
    return np.polyval(coeff_highest_first, pixels)


# ---------------------------------------------------------------------------
# LightField SPE 3.x
# ---------------------------------------------------------------------------

def _read_lightfield_spe(data: bytes, filepath: str, zero_padding: int) -> List[Dict[str, Union[np.ndarray, str, Dict]]]:
    """
    Parse a LightField SPE 3.x file (identified by its XML "SpeFormat"
    footer) — raw CCD/CMOS camera frame data, as written by LightField
    (the successor to WinSpec) for Raman, CD, and other spectroscopic
    detectors.

    Scope, deliberately narrow and verified against a real file rather
    than written from memory of the spec — see module docstring.

    File layout (verified against a real LightField 6.17 SPE 3.0 file —
    see the byte-offset cross-check below):

      [ 4100-byte legacy header ] [ N frames, each `stride` bytes ] [ XML footer ]

    The 4100-byte legacy header is a fixed constant of the SPE format
    (present in both version 2 and 3 files, for backward compatibility)
    — not something read from the file. Everything else (frame count,
    pixel format, region size/stride) is read fresh from each file's own
    XML footer, so this isn't hardcoded to one acquisition's dimensions.
    """
    xml_start = data.find(b'<SpeFormat')
    xml_text = data[xml_start:].decode('utf-8', errors='replace')
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse the SPE file's XML footer: {exc}") from exc

    frame_block = root.find('.//spe:DataFormat/spe:DataBlock[@type="Frame"]', _SPE_XML_NS)
    if frame_block is None:
        raise ValueError("SPE XML footer has no Frame DataBlock — unrecognised layout.")

    n_frames     = int(frame_block.get('count'))
    frame_stride = int(frame_block.get('stride'))
    pixel_format = frame_block.get('pixelFormat')

    regions = frame_block.findall('spe:DataBlock[@type="Region"]', _SPE_XML_NS)
    if len(regions) != 1:
        raise ValueError(
            f"This SPE file has {len(regions)} regions per frame — only "
            f"single-region (single-ROI) files are currently supported."
        )
    region = regions[0]
    width       = int(region.get('width'))
    height      = int(region.get('height'))
    region_size = int(region.get('size'))

    if height != 1:
        raise ValueError(
            f"This SPE file's region is {width}x{height} pixels (2D "
            f"image data, not a 1D spectrum) — only fully vertically-"
            f"binned, single-row acquisitions are currently supported."
        )

    dtype = _PIXEL_FORMATS.get(pixel_format)
    if dtype is None:
        raise ValueError(
            f"Unsupported SPE pixel format {pixel_format!r} — supported: "
            f"{', '.join(_PIXEL_FORMATS)}."
        )

    expected_data_end = _LEGACY_HEADER_SIZE + n_frames * frame_stride
    if expected_data_end > xml_start:
        raise ValueError(
            "This SPE file's declared frame data doesn't fit before its "
            "XML footer — the file may be truncated or corrupted."
        )

    logger.debug(
        "SPE layout (LightField 3.x): %d frames, %d px/frame, format=%s, stride=%d, region_size=%d",
        n_frames, width, pixel_format, frame_stride, region_size,
    )

    base_name = os.path.splitext(os.path.basename(filepath))[0]
    x_scale = np.arange(width, dtype=float)   # raw pixel index — uncalibrated
    zero_padding = max(1, zero_padding)

    spectra: List[Dict] = []
    for i in range(n_frames):
        offset = _LEGACY_HEADER_SIZE + i * frame_stride
        frame_bytes = data[offset: offset + region_size]
        y_scale = np.frombuffer(frame_bytes, dtype=dtype).astype(float)

        label = f"{base_name} : {str(i + 1).zfill(zero_padding)}"
        spectra.append({
            'label': label,
            'x_scale': x_scale.copy(),
            'y_scale': y_scale,
            'metadata': {
                'file_path': filepath,
                'file_type': 'spe_lightfield',
                'original_label': label,
                'import_parameters': {
                    'pixel_format': pixel_format,
                    'frame_index': i,
                    'n_frames': n_frames,
                    'width': width,
                    'uncalibrated': True,
                    'detection_mode': 'spe',
                },
            },
        })

    logger.info(
        "Created %d spectra from SPE file %s (LightField 3.x, uncalibrated pixel-index x-axis)",
        len(spectra), os.path.basename(filepath),
    )
    return spectra


# ---------------------------------------------------------------------------
# WinSpec 2.x (legacy)
# ---------------------------------------------------------------------------

def _read_legacy_spe(
    data: bytes, filepath: str, zero_padding: int, use_calibration: bool = False,
) -> List[Dict[str, Union[np.ndarray, str, Dict]]]:
    """
    Parse a legacy WinSpec 2.x .spe file — a fixed 4100-byte binary
    header (no XML footer) followed by raw frame data.

    Field offsets below are the ones that matter for raw single-row
    extraction, cross-checked against a real WinSpec 2.6.11 file (see
    the byte-count assertion in this function): xdim=1340, ydim=1,
    1 frame, datatype=0 (float) leaves exactly xdim*4 bytes of data
    after the header, which only lines up for this offset table and
    this datatype encoding — so this isn't taken from the spec blind.

    Offsets (all little-endian, within the 4100-byte header):
        42   (u16) xdim      — pixels per row (the x-axis width)
        108  (s16) datatype  — 0=float32, 1=int32, 2=int16, 3=uint16
        656  (u16) ydim      — rows per frame (must be 1 — see below)
        1446 (i32) NumFrames — number of stored frames
        3000 ...   x-axis calibration struct — see _read_x_calibration
    Plus a few purely-informational fields carried into metadata:
        10   (f32) exp_sec      — exposure time, seconds
        20   (10s) date         — acquisition date, null-terminated
        688  (16s) sw_version   — WinSpec software version string

    use_calibration: if True and this file has a valid x-axis
    calibration, spectra get that calibrated axis instead of the raw
    pixel index — see read_spe_data's docstring for the full contract.
    """
    if len(data) < _LEGACY_HEADER_SIZE:
        raise ValueError(
            "This file is smaller than the fixed 4100-byte SPE header — "
            "not a recognised SPE file."
        )

    xdim     = struct.unpack_from('<H', data, 42)[0]
    ydim     = struct.unpack_from('<H', data, 656)[0]
    n_frames = struct.unpack_from('<i', data, 1446)[0]
    datatype = struct.unpack_from('<h', data, 108)[0]

    if ydim != 1:
        raise ValueError(
            f"This legacy SPE file has {ydim} rows per frame (2D image "
            f"data, not a 1D spectrum) — only fully vertically-binned, "
            f"single-row acquisitions are currently supported."
        )
    if xdim <= 0 or n_frames <= 0:
        raise ValueError(
            f"This legacy SPE file has an invalid frame size (xdim={xdim}, "
            f"NumFrames={n_frames}) — it may be corrupted or not actually "
            f"a WinSpec 2.x SPE file."
        )

    dtype = _LEGACY_DATATYPES.get(datatype)
    if dtype is None:
        raise ValueError(
            f"Unsupported legacy SPE datatype code {datatype} — supported "
            f"codes: {', '.join(f'{k} ({v})' for k, v in _LEGACY_DATATYPES.items())}."
        )
    itemsize = np.dtype(dtype).itemsize

    frame_bytes = xdim * ydim * itemsize
    expected_total = _LEGACY_HEADER_SIZE + n_frames * frame_bytes
    if expected_total != len(data):
        raise ValueError(
            f"This legacy SPE file's declared size ({expected_total} bytes, "
            f"for {n_frames} frame(s) of {xdim} px) doesn't match its actual "
            f"size ({len(data)} bytes) — the file may be truncated, "
            f"corrupted, or use a layout this reader doesn't recognise."
        )

    exp_sec = struct.unpack_from('<f', data, 10)[0]
    date_str = data[20:30].split(b'\x00')[0].decode('ascii', errors='replace')
    sw_version = data[688:704].split(b'\x00')[0].decode('ascii', errors='replace')

    logger.debug(
        "SPE layout (WinSpec 2.x legacy): %d frames, %d px/frame, datatype=%d (%s), date=%r, sw=%r",
        n_frames, xdim, datatype, dtype, date_str, sw_version,
    )

    base_name = os.path.splitext(os.path.basename(filepath))[0]
    pixel_index = np.arange(xdim, dtype=float)   # raw pixel index — always available, 0..xdim-1
    zero_padding = max(1, zero_padding)

    # Calibration is read regardless of use_calibration, so its
    # availability is always known and recorded in metadata — the
    # calling code (the Import dialog's per-file checkbox) needs that to
    # decide whether to even offer the choice for this specific file,
    # not just whether to apply it.
    calibration = _read_x_calibration(data)
    calibration_available = calibration is not None
    apply_calibration = use_calibration and calibration_available
    if apply_calibration:
        x_scale = _evaluate_x_calibration(calibration, xdim)
    else:
        x_scale = pixel_index

    spectra: List[Dict] = []
    for i in range(n_frames):
        offset = _LEGACY_HEADER_SIZE + i * frame_bytes
        frame = data[offset: offset + frame_bytes]
        y_scale = np.frombuffer(frame, dtype=dtype).astype(float)

        label = f"{base_name} : {str(i + 1).zfill(zero_padding)}"
        import_parameters = {
            'datatype_code': datatype,
            'datatype': dtype,
            'frame_index': i,
            'n_frames': n_frames,
            'width': xdim,
            'exposure_sec': exp_sec,
            'acquisition_date': date_str or None,
            'sw_version': sw_version or None,
            'uncalibrated': not apply_calibration,
            'detection_mode': 'spe_legacy',
            # Always recorded, whether or not calibration was actually
            # requested/applied for THIS import — lets a later look at
            # the metadata answer "could this have been calibrated?"
            # even for a spectrum that was imported with the pixel axis.
            'calibration_available': calibration_available,
            'x_axis_calibrated': apply_calibration,
        }
        if calibration_available:
            import_parameters['calibration_unit_label'] = calibration['unit_label']
            import_parameters['calibration_laser_position'] = calibration['laser_position']
        spectra.append({
            'label': label,
            'x_scale': x_scale.copy(),
            'y_scale': y_scale,
            'metadata': {
                'file_path': filepath,
                'file_type': 'spe_winspec_legacy',
                'original_label': label,
                'import_parameters': import_parameters,
            },
        })

    logger.info(
        "Created %d spectra from SPE file %s (WinSpec 2.x legacy, %s x-axis%s)",
        len(spectra), os.path.basename(filepath),
        "calibrated" if apply_calibration else "uncalibrated pixel-index",
        f" ({calibration['unit_label']})" if apply_calibration and calibration['unit_label'] else "",
    )
    return spectra
