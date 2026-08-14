# src/modules/core/spectrum_manager.py

from dataclasses import dataclass, field
import os
import numpy as np
import uuid
from typing import Dict, Optional
from src.modules.data_io.table_data_converter import read_table_data
from src.modules.data_io.spe_data_converter import read_spe_data
from src.modules.data_io.spc_data_converter import read_spc_data
from src.modules.data_io.jasco_jws_reader import read_jws_data

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)


@dataclass
class Spectrum:
    """
    Class representing a single spectrum with x-scale, y-scale, and metadata.

    Attributes:
        x_scale (np.ndarray): X-axis values
        y_scale (np.ndarray): Y-axis values
        metadata (dict): Dictionary containing spectrum metadata
    """
    x_scale: np.ndarray
    y_scale: np.ndarray
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        """Ensure x_scale and y_scale are numpy arrays with compatible shapes."""
        # np.atleast_1d wraps .squeeze()'s result rather than using .squeeze()
        # alone: squeeze() drops EVERY size-1 axis, so a single-point spectrum
        # — shape (1,), or (1, 1) coming out of a spreadsheet column — collapses
        # all the way to a 0-d array. len() on a 0-d array raises TypeError,
        # which SpectrumManager._store_spectrum_dict then caught and logged,
        # silently dropping the spectrum instead of storing it (no error shown
        # to the user — it just never appeared). atleast_1d restores a length-1
        # array afterward, so single-point spectra survive like any other.
        self.x_scale = np.atleast_1d(np.array(self.x_scale).squeeze())
        self.y_scale = np.atleast_1d(np.array(self.y_scale).squeeze())

        if len(self.x_scale) != len(self.y_scale):
            raise ValueError(
                f"X-scale and Y-scale must have same length. "
                f"Got {len(self.x_scale)} and {len(self.y_scale)}"
            )

        if 'unique_id' not in self.metadata:
            self.metadata['unique_id'] = str(uuid.uuid4())


def _sort_spectrum_by_x(spectrum_dict) -> None:
    """
    Reorder a spectrum's points so the X values ascend.

    Some files list their X values out of order. The data is still perfectly
    valid — every (x, y) pair is intact — but a line plot drawn in file order
    zig-zags back and forth across the axis and looks like nonsense. Sorting the
    pairs fixes the picture without changing the data: the same points, drawn
    left to right.

    Applied here, centrally, rather than inside each converter, so it works
    identically for every layout (standard, row-oriented, interlaced) and every
    file type — each converter has already produced x_scale/y_scale pairs by the
    time we get here, and that is all this needs.
    """
    x = spectrum_dict.get('x_scale')
    y = spectrum_dict.get('y_scale')
    if x is None or y is None or len(x) < 2:
        return
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if np.all(np.diff(x) >= 0):
        return                       # already ascending — nothing to do
    order = np.argsort(x, kind='stable')   # stable: ties keep their file order
    spectrum_dict['x_scale'] = x[order]
    spectrum_dict['y_scale'] = y[order]
    spectrum_dict.setdefault('metadata', {})['x_axis_reordered'] = True
    logger.info(
        "Spectrum %r had a descending/unsorted x-axis; reordered to ascending "
        "(x-y pairs preserved). Ascending x is an application-wide invariant.",
        spectrum_dict.get('label', '?'))


def _merge_duplicate_x(spectrum_dict: dict) -> None:
    """
    Collapse duplicate x-values into one point each, by averaging their
    y-values, so x remains a valid function domain — exactly one y per x.

    Why this has to happen somewhere: every operation that works on a
    spectrum's x-values rather than array position — Savitzky-Golay,
    derivatives, FFT denoising, SNIP and other baselines, peak fitting,
    and anything built on np.interp (resampling, Data Range, melting-curve
    extraction) — assumes that. A duplicate x left in place doesn't raise
    an error anywhere downstream; np.interp silently returns whichever
    side of the tie its implementation happens to land on. That's a worse
    failure mode than an explicit, logged merge: silent and inconsistent,
    instead of visible and undoable.

    Why here, centrally: this is the same "single door" as
    _sort_spectrum_by_x, right after it (duplicates are only guaranteed
    adjacent once x is sorted). Previously only the plain-text interlaced
    converter merged duplicates at all — Excel-interlaced, standard, and
    row-oriented imports let them straight through. One rule, applied to
    every format here, replaces four format-specific answers to the same
    question.

    Nothing is silently thrown away: the pre-merge x_scale/y_scale are
    stashed in metadata['duplicate_x_merge'] before merging, so a genuine
    forward/reverse sweep or repeated cycle — where the duplicate is real
    data, not noise — can still be recovered. This deliberately does NOT
    reuse the app's existing 'original_x_scale'/'original_y_scale'
    top-level convention (see e.g. baseline_manager.py,
    spectral_range_manager.py): that convention means "the data before
    the most recent PROCESSING step" and is read/written by several
    analysis tools' own undo/reference logic. Reusing it here, at import
    time, for a different meaning would risk a later processing step
    seeing it already set and skipping its own save — silently pointing
    "original" at already-merged data instead of the true pre-processing
    state.

    Must run AFTER _sort_spectrum_by_x.
    """
    x = spectrum_dict.get('x_scale')
    y = spectrum_dict.get('y_scale')
    if x is None or y is None or len(x) < 2:
        return

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    unique_x, counts = np.unique(x, return_counts=True)
    if len(unique_x) == len(x):
        return   # no duplicates — nothing to do

    label = spectrum_dict.get('label', '?')
    n_dupes = len(x) - len(unique_x)

    metadata = spectrum_dict.setdefault('metadata', {})
    metadata['duplicate_x_merge'] = {
        'x_scale': x.copy(),
        'y_scale': y.copy(),
        'n_merged': int(n_dupes),
    }

    new_y = np.empty_like(unique_x, dtype=float)
    for i, val in enumerate(unique_x):
        new_y[i] = np.mean(y[x == val])

    spectrum_dict['x_scale'] = unique_x
    spectrum_dict['y_scale'] = new_y

    # Every converter stamps metadata['valid_points'] BEFORE this function
    # ever runs — it reflects the point count at parse time, not after any
    # later merge. Left alone, it would silently go stale: a spectrum
    # merged from 6 points to 5 would still claim "Valid Points: 6" in the
    # Metadata dialog, contradicting the x_scale/y_scale actually stored
    # (and contradicting duplicate_x_merge['n_merged'] sitting right next
    # to it). Only touched if the converter set it in the first place —
    # SPE/SPC metadata has no such key and shouldn't gain one here.
    if 'valid_points' in metadata:
        metadata['valid_points'] = len(unique_x)

    logger.warning(
        "Spectrum %r: %d duplicate x-value(s) were MERGED by averaging "
        "their y-values (%d points -> %d). If the same x legitimately "
        "recurs with different y (e.g. a forward/reverse sweep), the "
        "pre-merge data is kept in metadata['duplicate_x_merge'].",
        label, n_dupes, len(x), len(unique_x))


class SpectrumManager:
    """
    Manages loading, storing, and retrieving spectra from table files.
    Supports plain-text (standard and interlaced) and Excel (.xlsx) formats.
    """

    # File extensions handled by read_table_data, plus the binary
    # formats (.spe, .spc) which bypass it entirely — see the file_ext
    # branch in load_spectrum_from_file().
    SUPPORTED_EXTENSIONS = ('.txt', '.csv', '.dat', '.xlsx', '.xls', '.xlsm', '.spe', '.spc', '.jws')

    def __init__(self):
        self.spectra: Dict[str, Spectrum] = {}
        self.id_to_label_map: Dict[str, str] = {}
        self.label_to_id_map: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_spectrum_from_file(
        self,
        filepath: str,
        delimiter: Optional[str] = None,
        decimal_separator: Optional[str] = None,
        header: Optional[bool] = None,
        zero_padding: int = 4,
        analyze_rows: int = 20,
        interlaced_format: bool = False,
        row_oriented: bool = False,
        header_threshold: float = 0.5,
        label_column: Optional[int] = None,
        x_scale_column: Optional[int] = None,
        exclude_columns: Optional[list] = None,
        sheet_name: Optional[str] = None,
        header_row: Optional[int] = None,
        index_x: bool = False,
        spe_use_calibration: bool = False,
        jws_selected_channels: Optional[list] = None,
        jws_channel_type_overrides: Optional[dict] = None,
    ) -> None:
        """
        Load one or more spectra from *filepath* and store them.

        Supported formats
        -----------------
        Plain text : .txt  .csv  .dat
        Excel      : .xlsx  .xls  .xlsm
        SPE        : .spe  (LightField 3.x or legacy WinSpec 2.x,
                     auto-detected — pixel-index x-axis by default;
                     spe_use_calibration=True switches legacy WinSpec
                     files that carry a valid calibration to their real
                     wavelength/wavenumber axis instead. One spectrum
                     per stored frame.)
        SPC        : .spc  (Thermo/GRAMS, old or new format,
                     auto-detected — calibrated x-axis; one spectrum
                     per subfile, almost always exactly one)
        JWS        : .jws  (JASCO SpectraManager — CD spectropolarimeter
                     files; calibrated wavelength x-axis. One spectrum per
                     co-recorded channel — commonly CD [mdeg], sometimes
                     also HT [V] and/or Absorbance [AU]. jws_selected_channels
                     picks which channel(s) to import (None = all);
                     jws_channel_type_overrides corrects this reader's
                     own value-range-based channel-type guess where the
                     import dialog's preview didn't match reality — see
                     jasco_jws_reader.py's module docstring.)

        For Excel files the delimiter / decimal_separator parameters are
        ignored — numbers are read natively from the workbook cells.
        sheet_name selects which worksheet to read (Excel only); None
        auto-selects "spectra" or the first sheet.

        For SPE, SPC, and JWS files, every parameter above except
        zero_padding (and each format's own one or two format-specific
        options) is ignored — none of these binary formats has a
        delimiter/decimal/header/Layout/column-picker concept at all.
        """
        # logger.debug("load_spectrum_from_file called")
        # logger.debug("delimiter=%r, decimal_separator=%r, interlaced=%s", delimiter, decimal_separator, interlaced_format)

        if not os.path.exists(filepath):
            raise ValueError(f"File not found: {filepath}")

        file_ext = os.path.splitext(filepath)[1].lower()
        if file_ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension: '{file_ext}'\n"
                f"Supported formats: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )

        try:
            if file_ext == '.spe':
                # SPE files (LightField 3.x or legacy WinSpec 2.x) have
                # no delimiter/decimal/header/Layout/column-picker
                # concept at all — every other parameter above is simply
                # irrelevant for this format, so it's bypassed entirely
                # rather than threaded through unused. spe_use_calibration
                # is the one SPE-specific choice that does apply here.
                spectra_data = read_spe_data(
                    filepath, zero_padding=zero_padding,
                    use_calibration=spe_use_calibration,
                )
            elif file_ext == '.spc':
                # Same reasoning as .spe above — GRAMS/SPC has its own
                # self-contained header (calibration, axis units, etc.)
                # and none of the text/Excel import settings apply.
                spectra_data = read_spc_data(filepath, zero_padding=zero_padding)
            elif file_ext == '.jws':
                # Same reasoning again — JASCO's own OLE2-based binary
                # container, self-describing channel count/axis, no
                # delimiter/decimal/header concept. jws_selected_channels
                # and jws_channel_type_overrides are the two JWS-specific
                # choices threaded from the import dialog.
                spectra_data = read_jws_data(
                    filepath, zero_padding=zero_padding,
                    selected_channels=jws_selected_channels,
                    channel_type_overrides=jws_channel_type_overrides,
                )
            else:
                spectra_data = read_table_data(
                    filepath,
                    delimiter=delimiter,
                    decimal_separator=decimal_separator,
                    header=header,
                    analyze_rows=analyze_rows,
                    zero_padding=zero_padding,
                    interlaced_format=interlaced_format,
                    row_oriented=row_oriented,
                    header_threshold=header_threshold,
                    label_column=label_column,
                    x_scale_column=x_scale_column,
                    exclude_columns=exclude_columns,
                    sheet_name=sheet_name,
                    header_row=header_row,
                    index_x=index_x,
                )

            for spectrum_dict in spectra_data:
                # ASCENDING X IS AN APPLICATION-WIDE INVARIANT, established here,
                # at the single door all data comes through — every file format,
                # every layout. It is NOT optional — there used to be a sort_x
                # flag to switch it off; it was dead (never actually wired to
                # anything downstream) and has been removed. See
                # _sort_spectrum_by_x.
                #
                # Why it has to be an invariant: a spectrum stored 330 -> 220 and
                # the same spectrum stored 220 -> 330 are the SAME measurement —
                # identical (x, y) pairs, and plot(x, y) draws the same curve. But
                # every piece of code that works on array ORDER rather than on x
                # VALUES sees them as MIRROR IMAGES: Savitzky-Golay, derivatives,
                # FFT/denoising, SNIP and other baselines, peak indices, x[0]/x[-1]
                # range logic, and np.interp (which silently returns nonsense for
                # descending x). That is an unbounded set of places to get right,
                # forever, and every new operation would have to remember. Fixing
                # it once here means nothing downstream ever has to think about it.
                #
                # Sorting cannot lose anything: it is a pure reordering and each y
                # stays attached to its own x.
                _sort_spectrum_by_x(spectrum_dict)

                # DUPLICATE X-VALUES ARE MERGED HERE, at the same single door,
                # for the same reason ascending-x is enforced here rather than
                # per-converter — see _merge_duplicate_x. Must run after the
                # sort above: duplicates are only guaranteed adjacent once x
                # is ascending.
                _merge_duplicate_x(spectrum_dict)

                self._store_spectrum_dict(spectrum_dict)

        except Exception as e:
            logger.exception("Traceback:")
            # Keep the user-facing message to just the underlying reason —
            # the caller (import_controller._show_import_feedback) already
            # shows the filename as a separate label. Repeating the full
            # absolute path here was pure noise, and on long Windows paths
            # it was eating the message-truncation budget before the
            # actually useful reason could even be shown to the user.
            raise ValueError(str(e)) from e

    def _store_spectrum_dict(self, spectrum_dict: dict) -> None:
        """Validate and store a single spectrum dict returned by the converter."""
        label = spectrum_dict['label']

        if 'metadata' not in spectrum_dict:
            spectrum_dict['metadata'] = {}
        if 'unique_id' not in spectrum_dict['metadata']:
            spectrum_dict['metadata']['unique_id'] = str(uuid.uuid4())

        unique_id = spectrum_dict['metadata']['unique_id']

        try:
            x_data = np.asarray(spectrum_dict['x_scale'], dtype=float)
            y_data = np.asarray(spectrum_dict['y_scale'], dtype=float)

            if len(x_data) == 0 or len(y_data) == 0:
                logger.warning("Skipping spectrum %r — empty arrays", label)
                return

            if len(x_data) != len(y_data):
                logger.warning("Skipping spectrum %r — length mismatch: %d vs %d", label, len(x_data), len(y_data))
                return

            # SAFETY: spectra are stored in a dict keyed by label, so storing a
            # spectrum under a label that already exists would SILENTLY DESTROY
            # the existing one — no error, no warning, it would simply vanish.
            # That can happen whenever two sources produce the same label (two
            # sheets of one workbook with identical column names, two files with
            # the same name, ...). Rather than trusting every caller to have
            # avoided it, make it impossible here: uniquify the label, and record
            # what it was originally called. Nothing is ever lost.
            if label in self.spectra:
                base, n = label, 2
                while label in self.spectra:
                    label = f"{base} ({n})"
                    n += 1
                logger.warning(
                    "Duplicate spectrum label %r — stored as %r instead so the "
                    "existing spectrum is not overwritten.", base, label)
                spectrum_dict['metadata']['original_label'] = base

            self.spectra[label] = Spectrum(
                x_scale=x_data,
                y_scale=y_data,
                metadata=spectrum_dict['metadata'],
            )
            self.id_to_label_map[unique_id] = label
            self.label_to_id_map[label] = unique_id
            # logger.debug("Created spectrum %r with %d points", label, len(x_data))

        except Exception as e:
            logger.error("Error creating spectrum %r: %s", label, e)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_spectrum(self, name: str) -> Optional[Spectrum]:
        return self.spectra.get(name)

    def get_spectrum_by_id(self, unique_id: str) -> Optional[Spectrum]:
        label = self.id_to_label_map.get(unique_id)
        return self.spectra.get(label) if label else None

    def get_spectrum_id(self, name: str) -> Optional[str]:
        return self.label_to_id_map.get(name)

    def get_all_spectra(self) -> Dict[str, Spectrum]:
        return self.spectra

    def get_all_spectra_ids(self) -> Dict[str, str]:
        return self.label_to_id_map

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def clear_spectra(self) -> None:
        self.spectra.clear()
        self.id_to_label_map.clear()
        self.label_to_id_map.clear()

    def remove_spectrum(self, name: str) -> bool:
        unique_id = self.label_to_id_map.get(name)
        if unique_id:
            self.id_to_label_map.pop(unique_id, None)
            self.label_to_id_map.pop(name, None)
        return self.spectra.pop(name, None) is not None

    def rename_spectrum(self, old_name: str, new_name: str) -> bool:
        if old_name not in self.spectra or new_name in self.spectra:
            return False

        spectrum = self.spectra.pop(old_name)
        unique_id = self.label_to_id_map.pop(old_name, None)

        if hasattr(spectrum, 'metadata') and 'spectrum_name' in spectrum.metadata:
            spectrum.metadata['spectrum_name'] = new_name

        self.spectra[new_name] = spectrum
        if unique_id:
            self.id_to_label_map[unique_id] = new_name
            self.label_to_id_map[new_name] = unique_id

        return True
