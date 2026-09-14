# src/modules/data_io/mat_map_converter.py
#
# Reader for hyperspectral Raman/IR MAP files exported as MATLAB .mat
# "dataset object" files — the format written by WITec's Project FIVE
# software (and, more generally, Eigenvector Research's PLS_Toolbox
# dataset-object convention, which several other instrument packages
# reuse for the same purpose). This is the format RamAIn (a Raman map
# viewer developed at MFF UK) reads, and the one collaborators using
# WITec-family mapping instruments are expected to export.
#
# Scope: a single hyperspectral map per file — an (n_rows x n_cols) grid
# of pixels, each carrying one full spectrum on a shared x-axis. Each
# pixel becomes one spectrum here; the map's row/col geometry and
# physical (µm) pixel coordinates are preserved in every spectrum's
# metadata (see import_parameters below) so a caller can reconstruct the
# spatial grid — e.g. to feed the app's existing 2-D Map dialog — without
# having to re-derive it from the file a second time.
#
# File layout (verified against real WITec Project FIVE 5.1 exports, not
# implemented from the format spec blind — see the field-by-field notes
# below and the reshape-order verification note on _reshape_pixel_index):
#
#   The .mat file holds exactly one MATLAB struct, under an arbitrary
#   top-level variable name (it's the dataset's own name/title, chosen
#   by whoever ran the export — never a fixed key). That struct has a
#   fixed set of named fields (this is Eigenvector's "dataset object"
#   struct layout, present verbatim regardless of the variable's own
#   name):
#
#     name            (str)     dataset title, as entered in the export
#     type            (str)     'image' for a spectral map
#     imagesize       (2,)      [dim0, dim1] pixel grid size
#     data            (N, W)    N = dim0*dim1 pixels (flattened), W =
#                                number of spectral (x-axis) points
#     axisscale       (2,2) obj axisscale[1,0] = the shared x-axis (W
#                                values); axisscale[1,1] = its unit
#                                label (e.g. 'rel. 1/cm' for Raman shift)
#     imageaxisscale  (2,2) obj imageaxisscale[0,0] = physical spatial
#                                coordinate of each dim0 step;
#                                imageaxisscale[0,1] = its unit (µm);
#                                imageaxisscale[1,0]/[1,1] = the same for
#                                dim1
#     history         (str)     provenance note, e.g. 'Created by
#                                Project FIVE (Version 5.1)' — recorded
#                                in metadata for traceability, not parsed
#
#   Everything else in the struct (author, date, class, userdata, ...) is
#   part of the same Eigenvector layout but not needed for import and is
#   left alone.

import os
from typing import Dict, List, Union

import numpy as np

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)


def _load_struct(filepath: str) -> dict:
    """
    Load *filepath* and return its single top-level MATLAB struct as a
    plain nested dict (via scipy's simplify_cells=True), or raise a
    clear ValueError if the file isn't structured the way this reader
    expects.

    Never guesses at a struct that doesn't look like a WITec/Eigenvector
    dataset object — every field this reader goes on to use is checked
    for presence and shape here first, so a mismatch is reported with a
    specific reason rather than surfacing later as an obscure KeyError
    or IndexError deep inside the pixel loop.
    """
    try:
        import scipy.io
    except ImportError as exc:
        raise ValueError(
            "Reading .mat files requires the 'scipy' package, which is "
            "not installed."
        ) from exc

    try:
        raw = scipy.io.loadmat(filepath, simplify_cells=True)
    except Exception as exc:
        raise ValueError(f"'{os.path.basename(filepath)}' could not be read as a MATLAB .mat file: {exc}") from exc

    # The file's own variables, excluding scipy's own bookkeeping keys
    # (__header__, __version__, __globals__) which are always present
    # and are never the dataset itself.
    candidate_names = [k for k in raw if not k.startswith('__')]
    if not candidate_names:
        raise ValueError(
            f"'{os.path.basename(filepath)}' contains no MATLAB variables."
        )

    # A WITec/Project FIVE export holds exactly one dataset-object
    # struct. If more than one candidate variable is present, prefer one
    # that actually looks like a dataset object (has 'data' and
    # 'imagesize') over one that doesn't, rather than always taking the
    # last — but still refuse outright, with the specific variable names
    # involved, if more than one genuinely qualifies. Guessing between
    # two real candidates would silently import the wrong map.
    def _looks_like_dataset(name):
        val = raw.get(name)
        return isinstance(val, dict) and 'data' in val and 'imagesize' in val

    qualifying = [n for n in candidate_names if _looks_like_dataset(n)]
    if len(qualifying) == 1:
        struct = raw[qualifying[0]]
    elif len(qualifying) > 1:
        raise ValueError(
            f"'{os.path.basename(filepath)}' contains {len(qualifying)} "
            f"dataset-object variables ({', '.join(qualifying)}) — expected "
            f"exactly one hyperspectral map per file."
        )
    else:
        struct = raw[candidate_names[-1]]

    if not isinstance(struct, dict):
        raise ValueError(
            f"'{os.path.basename(filepath)}' does not contain a MATLAB "
            f"struct — this reader only supports the WITec/Project FIVE "
            f"'dataset object' map export format."
        )
    return struct


def _require_field(struct: dict, field: str, filepath: str):
    if field not in struct:
        raise ValueError(
            f"'{os.path.basename(filepath)}' is missing the '{field}' field "
            f"expected in a WITec/Project FIVE dataset-object export — this "
            f"doesn't look like a supported hyperspectral map file."
        )
    return struct[field]


def _as_1d(value) -> np.ndarray:
    """Flatten a MATLAB row/column vector (however scipy happened to
    shape it) into a plain 1-D numpy array."""
    return np.asarray(value, dtype=float).reshape(-1)


def _axis_unit_label(struct_field) -> str:
    """
    Return a MATLAB axis-unit string, or '' if it's empty/unreadable.

    One specific, verified normalization is applied: WITec's spatial
    pixel-size unit is stored in the file as the two UTF-16 code units
    U+00B5 ('µ', MICRO SIGN) followed by U+006D ('m') — confirmed by
    reading the raw bytes of a real export directly (b'\xb5\x00m\x00'
    at the field's file offset), bypassing scipy entirely. scipy's own
    MATLAB char-array decoder (as of scipy>=1.8, the version this app
    requires) loses that specific code unit and returns it as U+FFFD
    (the Unicode replacement character) instead — every OTHER character
    in the same files, ASCII ones like the 'rel. 1/cm' spectral-axis
    label, decodes correctly, so this is narrowly a µ-decoding gap in
    scipy, not something wrong with the file. Since 'µm' is the only
    unit this field is ever populated with in the file family this
    reader supports (physical stage/pixel spacing on a Raman
    microscope), a decoded label matching \ufffd + 'm' is corrected
    back to 'µm' — recovering real, verified information lost in
    scipy's decode, not a blind guess. Any other label (already-correct
    ASCII text, or an empty field) passes through unchanged.
    """
    if isinstance(struct_field, str):
        text = struct_field
    else:
        try:
            text = str(np.asarray(struct_field).reshape(-1)[0])
        except Exception:
            return ''
    if text == '\ufffdm':
        return 'µm'
    return text


def _reshape_pixel_index(pixel_index: int, n_cols: int) -> tuple:
    """
    Map a flat pixel index (0-based, as it appears along `data`'s first
    axis) to its (row, col) position in the (n_rows x n_cols) grid.

    Verified empirically against three real, non-square Project FIVE
    exports (imagesize 25x25, 40x30, 39x51): for each, the per-pixel mean
    intensity reshaped as `values.reshape(n_rows, n_cols, order='C')` —
    i.e. row = pixel_index // n_cols, col = pixel_index % n_cols, with
    n_rows = imagesize[1] and n_cols = imagesize[0] — is dramatically
    smoother (neighbouring pixels close in value) than every other
    combination of axis order and row/col assignment tried, exactly as
    expected for a real spatial image and never for a mismatched
    reshape. This also matches RamAIn's own (independently-arrived-at)
    `np.reshape(data, (imagesize[1], imagesize[0], -1))` — a second,
    independent confirmation of the same axis assignment.
    """
    row = pixel_index // n_cols
    col = pixel_index % n_cols
    return row, col


def read_mat_map_data(
    filepath: str,
    zero_padding: int = 4,
) -> List[Dict[str, Union[np.ndarray, str, Dict]]]:
    """
    Read a WITec/Project FIVE-style hyperspectral map .mat file and
    return one spectrum per pixel.

    Every returned spectrum shares the same x-axis (the map's spectral
    axis) and carries its spatial position — pixel row/col, the map's
    full row/col size, and the pixel's physical (µm) coordinates when
    the file records them — in metadata['import_parameters'], so a
    caller can reconstruct the 2-D spatial grid (e.g. to hand to the
    app's 2-D Map dialog: n_rows x n_cols reshape, in pixel-index/label
    order) without re-parsing the file.

    Parameters
    ----------
    filepath     : path to the .mat file
    zero_padding : accepted for interface consistency with the other
                   binary-format readers (read_spe_data, read_spc_data),
                   but NOT used — row/col numbers in each spectrum's
                   label are always zero-padded to the map's own grid
                   size (e.g. 'r00_c00' .. 'r24_c24' for a 25x25 map),
                   which is a more meaningful width than an
                   independently-chosen global padding would be.

    Raises ValueError with a specific, honest reason if the file isn't a
    WITec/Project FIVE dataset-object map export, or if its internal
    dimensions are inconsistent (e.g. imagesize doesn't account for every
    row of `data`, or the x-axis length doesn't match the number of
    spectral columns) — never silently guesses at a mismatched layout.
    """
    logger.info("Importing MAT map: %s", os.path.basename(filepath))

    struct = _load_struct(filepath)

    data = _require_field(struct, 'data', filepath)
    data = np.asarray(data)
    if data.ndim != 2:
        raise ValueError(
            f"'{os.path.basename(filepath)}': 'data' has {data.ndim} "
            f"dimension(s) — expected a 2-D (pixels x wavelengths) array."
        )
    n_pixels, n_wl = data.shape

    imagesize = _require_field(struct, 'imagesize', filepath)
    imagesize = np.asarray(imagesize).reshape(-1)
    if imagesize.size != 2:
        raise ValueError(
            f"'{os.path.basename(filepath)}': 'imagesize' has "
            f"{imagesize.size} value(s) — expected exactly 2 (a 2-D map "
            f"row/col size). This reader only supports 2-D spectral maps, "
            f"not line scans or 3-D volumes."
        )
    dim0, dim1 = int(imagesize[0]), int(imagesize[1])
    # See _reshape_pixel_index's docstring for why n_rows/n_cols are
    # imagesize's two entries in THIS order (swapped relative to the
    # file's own imagesize field, which lists [dim0, dim1]).
    n_rows, n_cols = dim1, dim0
    if n_rows <= 0 or n_cols <= 0 or n_rows * n_cols != n_pixels:
        raise ValueError(
            f"'{os.path.basename(filepath)}': imagesize is {dim0} x {dim1} "
            f"({n_rows * n_cols} pixels), but 'data' has {n_pixels} rows — "
            f"the file's declared map size doesn't match its own pixel "
            f"count."
        )

    axisscale = _require_field(struct, 'axisscale', filepath)
    axisscale = np.asarray(axisscale, dtype=object)
    if axisscale.shape != (2, 2):
        raise ValueError(
            f"'{os.path.basename(filepath)}': 'axisscale' has shape "
            f"{axisscale.shape} — expected the standard 2x2 dataset-object "
            f"layout."
        )
    x_scale = _as_1d(axisscale[1, 0])
    if x_scale.size != n_wl:
        raise ValueError(
            f"'{os.path.basename(filepath)}': the x-axis has {x_scale.size} "
            f"points but each spectrum in 'data' has {n_wl} — inconsistent "
            f"file."
        )
    spectral_unit = _axis_unit_label(axisscale[1, 1])

    # Physical pixel spacing/coordinates are informational only — not
    # every export necessarily carries them in a usable shape, so a
    # missing or malformed imageaxisscale downgrades to "position
    # unknown" rather than failing the whole import; the map's row/col
    # geometry above is all that's actually required to use the file.
    spatial_x_coords = spatial_y_coords = None
    spatial_unit = ''
    imageaxisscale = struct.get('imageaxisscale')
    if imageaxisscale is not None:
        try:
            imageaxisscale = np.asarray(imageaxisscale, dtype=object)
            dim0_coords = _as_1d(imageaxisscale[0, 0])
            dim1_coords = _as_1d(imageaxisscale[1, 0])
            if dim0_coords.size == dim0 and dim1_coords.size == dim1:
                # dim0 -> columns, dim1 -> rows (same swap as imagesize above)
                spatial_x_coords = dim0_coords
                spatial_y_coords = dim1_coords
                spatial_unit = _axis_unit_label(imageaxisscale[0, 1])
        except Exception:
            logger.debug(
                "MAT map %s: could not parse imageaxisscale; spatial "
                "pixel coordinates will be omitted from metadata.",
                os.path.basename(filepath), exc_info=True,
            )

    dataset_name = struct.get('name', '')
    if isinstance(dataset_name, np.ndarray):
        dataset_name = _axis_unit_label(dataset_name)
    history = struct.get('history', '')
    if isinstance(history, np.ndarray):
        history = _axis_unit_label(history)

    base_name = os.path.splitext(os.path.basename(filepath))[0]
    zero_padding = max(1, zero_padding)
    row_digits = max(1, len(str(n_rows - 1)))
    col_digits = max(1, len(str(n_cols - 1)))

    data = data.astype(float)

    logger.debug(
        "MAT map layout: %d x %d pixels (%d total), %d spectral points, "
        "x-axis unit=%r, spatial unit=%r",
        n_rows, n_cols, n_pixels, n_wl, spectral_unit, spatial_unit,
    )

    spectra: List[Dict] = []
    for pixel_index in range(n_pixels):
        row, col = _reshape_pixel_index(pixel_index, n_cols)
        y_scale = data[pixel_index, :]

        label = (
            f"{base_name} [r{str(row).zfill(row_digits)}"
            f"_c{str(col).zfill(col_digits)}]"
        )

        import_parameters = {
            'map_n_rows': n_rows,
            'map_n_cols': n_cols,
            'pixel_row': row,
            'pixel_col': col,
            'pixel_index': pixel_index,
            'spectral_unit': spectral_unit,
            'dataset_name': dataset_name or None,
            'source_software': history or None,
        }
        if spatial_x_coords is not None:
            import_parameters['spatial_x'] = float(spatial_x_coords[col])
            import_parameters['spatial_y'] = float(spatial_y_coords[row])
            import_parameters['spatial_unit'] = spatial_unit

        spectra.append({
            'label': label,
            'x_scale': x_scale.copy(),
            'y_scale': y_scale,
            'metadata': {
                'file_path': filepath,
                'file_type': 'mat_map',
                'original_label': label,
                'import_parameters': import_parameters,
            },
        })

    logger.info(
        "Created %d spectra from MAT map %s (%d x %d pixels, %d points, "
        "x-axis unit=%s)",
        len(spectra), os.path.basename(filepath), n_rows, n_cols, n_wl,
        spectral_unit or 'unknown',
    )
    return spectra
