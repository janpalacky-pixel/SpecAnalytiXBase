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
from src.modules.data_io.specord_csv_converter import read_specord_csv_data

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


def _detect_repeated_scan_structure(
    x, y, min_repeat: int = 2, min_conformity: float = 0.8
) -> Optional[dict]:
    """
    Look for the signature of several scans stacked on a shared x-axis in one
    column-oriented spectrum — e.g. a forward/reverse sweep, or N spectra
    concatenated into one long x/y column pair — as opposed to the ordinary
    "a handful of x-values happen to repeat" case _merge_duplicate_x already
    handles silently by averaging.

    The distinguishing signal is not "duplicates exist" (that alone is
    common and usually meaningless) but "duplicates exist at a consistent
    multiplicity": if most of the DISTINCT x-values repeat the same number
    of times S, that is much more likely to be S co-registered scans than
    coincidental overlap. S is found as the repeat-count shared by the
    largest number of distinct x-values (i.e. the mode of the per-x-value
    multiplicity, restricted to multiplicities >= min_repeat).

    This deliberately does NOT assume the repeats appear as contiguous
    blocks in file order (row 1..k = scan 1, row k+1..2k = scan 2, ...).
    Real round-trip/hysteresis scans interleave differently: a down-sweep
    followed by an up-sweep shares x-values in REVERSE row order, not
    matching blocks — see _split_into_scans, which recovers scan identity
    from each x-value's occurrence order instead of assuming block layout.

    Returns None when nothing beyond ordinary occasional duplication is
    found (the common case — callers then fall through to the existing
    silent merge, completely unchanged). Otherwise returns a dict:
        repeat_count     S, the detected number of scans
        unique_x_count   number of distinct x-values in the whole array
        n_conforming     number of distinct x-values with multiplicity == S
        conformity       n_conforming / unique_x_count
        total_rows       len(x)
        n_dropped_points rows belonging to x-values that DON'T have
                          multiplicity S, and so would be left out of a
                          split (still present if the caller merges instead)
    """
    if x is None or y is None:
        return None
    x = np.asarray(x, dtype=float)
    if len(x) < 2 * min_repeat:
        return None

    unique_x, counts = np.unique(x, return_counts=True)
    if len(unique_x) == len(x):
        return None   # no duplicates at all

    from collections import Counter
    multiplicity_histogram = Counter(int(c) for c in counts)

    candidates = {m: n for m, n in multiplicity_histogram.items() if m >= min_repeat}
    if not candidates:
        return None   # every duplicate has multiplicity 1... impossible, but be safe

    # Pick the multiplicity shared by the most distinct x-values; ties
    # broken toward the larger (more specific) repeat count.
    best_S = max(candidates, key=lambda m: (candidates[m], m))
    n_conforming = candidates[best_S]
    conformity = n_conforming / len(unique_x)

    if conformity < min_conformity:
        return None

    total_rows = len(x)
    n_dropped_points = total_rows - n_conforming * best_S

    return {
        'repeat_count':     int(best_S),
        'unique_x_count':   int(len(unique_x)),
        'n_conforming':     int(n_conforming),
        'conformity':       float(conformity),
        'total_rows':       int(total_rows),
        'n_dropped_points': int(n_dropped_points),
    }


def _split_into_scans(spectrum_dict: dict, repeat_count: int) -> list:
    """
    Split one duplicate-laden spectrum_dict into `repeat_count` separate
    spectrum dicts, one per scan, instead of merging duplicates away.

    Must run on data that is already x-sorted (see _sort_spectrum_by_x) and
    NOT yet passed through _merge_duplicate_x. Only x-values whose
    multiplicity is exactly `repeat_count` are used — the ones that don't
    fit the pattern are left out of every split spectrum (they are exactly
    the block_info['n_dropped_points'] rows from
    _detect_repeated_scan_structure; the caller's dialog reports that count
    to the user before this is called).

    Scan identity is recovered from each x-value's OCCURRENCE ORDER, not
    from row position/blocks: since np.unique's underlying sort is stable
    relative to the caller's ordering only per equal keys as encountered,
    and this runs on an already x-sorted array, occurrences of the same x
    value stay in their original relative (file) order — first occurrence
    in the file becomes scan 1's point, second becomes scan 2's, etc. This
    is exactly right for a round-trip sweep (down-sweep encountered first
    in the file, up-sweep second) as well as for literal contiguous blocks.
    """
    x = np.asarray(spectrum_dict['x_scale'], dtype=float)
    y = np.asarray(spectrum_dict['y_scale'], dtype=float)
    base_label = spectrum_dict.get('label', 'spectrum')
    base_metadata = spectrum_dict.get('metadata', {})

    unique_x, counts = np.unique(x, return_counts=True)
    conforming_x = np.sort(unique_x[counts == repeat_count])
    n_conforming = len(conforming_x)

    scans_y = [np.empty(n_conforming, dtype=float) for _ in range(repeat_count)]
    for i, val in enumerate(conforming_x):
        positions = np.where(x == val)[0]   # ascending index == file order (stable)
        for j in range(repeat_count):
            scans_y[j][i] = y[positions[j]]

    n_dropped = len(x) - n_conforming * repeat_count

    out = []
    for j in range(repeat_count):
        metadata = dict(base_metadata)
        metadata['duplicate_x_split'] = {
            'scan_index':       j + 1,
            'scan_count':       repeat_count,
            'source_label':     base_label,
            'n_dropped_points': int(n_dropped),
        }
        if 'valid_points' in metadata:
            metadata['valid_points'] = n_conforming
        out.append({
            'label':    f"{base_label} [scan {j + 1}/{repeat_count}]",
            'x_scale':  conforming_x,
            'y_scale':  scans_y[j],
            'metadata': metadata,
        })
    return out


def _sniff_numeric_text(filepath: str, sample_lines: int = 40,
                         min_numeric_fraction: float = 0.6) -> Optional[dict]:
    """
    Lightweight, format-agnostic check of whether *filepath* looks like it
    holds numeric tabular data, independent of its extension.

    Only ever called for a file whose extension ISN'T one this app already
    recognizes (see SpectrumManager.SUPPORTED_EXTENSIONS) — every
    recognized extension has its own dedicated reader and never reaches
    this function. It exists because the three-letter suffix an instrument
    or collaborator happened to save a file with says nothing about
    whether the CONTENT is readable spectral data: a plain x/y column pair
    exported as ".bcw" is exactly as readable as the same data saved
    ".txt" — only the name differs.

    Reads up to *sample_lines* non-blank lines and, for each, splits on
    common delimiters (whitespace, comma, tab, semicolon) and counts how
    many resulting tokens parse as a number — accepting both '.' and ','
    as the decimal separator, since Standard layout's own
    decimal_separator option already supports both. A line only needs 2
    numeric tokens (the minimum for one x/y pair) to count as "numeric",
    and the file only needs a majority of its sampled lines to qualify —
    not every line — so a short text preamble before the real data (column
    headers, an instrument banner, a blank-ish junk line) doesn't sink an
    otherwise good file.

    Returns None if the file can't be read as text at all, or if fewer
    than *min_numeric_fraction* of the sampled lines look numeric.
    Otherwise returns a small dict describing what was found, for display
    in the caller's confirmation prompt: lines_checked, numeric_lines,
    likely_columns (the most common token count among the numeric lines).
    """
    lines = []
    for encoding in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            with open(filepath, 'r', encoding=encoding) as fh:
                for raw in fh:
                    line = raw.strip()
                    if line:
                        lines.append(line)
                        if len(lines) >= sample_lines:
                            break
            break
        except (UnicodeDecodeError, LookupError, OSError):
            lines = []
            continue
    if not lines:
        return None

    import re
    token_re = re.compile(r'[,\t; ]+')

    def _count_numeric_tokens(line):
        n_numeric = 0
        n_tokens = 0
        for tok in token_re.split(line):
            if not tok:
                continue
            n_tokens += 1
            try:
                float(tok)
                n_numeric += 1
                continue
            except ValueError:
                pass
            # A single comma with no '.' present is plausibly a decimal
            # comma (e.g. "12,34") rather than a delimiter that leaked
            # through — same tolerance Standard layout's own
            # decimal_separator=',' option gives every recognized format.
            if tok.count(',') == 1 and '.' not in tok:
                try:
                    float(tok.replace(',', '.'))
                    n_numeric += 1
                except ValueError:
                    pass
        return n_numeric, n_tokens

    numeric_line_count = 0
    column_counts = []
    for line in lines:
        n_numeric, n_tokens = _count_numeric_tokens(line)
        if n_numeric >= 2:
            numeric_line_count += 1
            column_counts.append(n_tokens)

    fraction = numeric_line_count / len(lines)
    if fraction < min_numeric_fraction or not column_counts:
        return None

    from collections import Counter
    likely_columns = Counter(column_counts).most_common(1)[0][0]

    return {
        'lines_checked':  len(lines),
        'numeric_lines':  numeric_line_count,
        'likely_columns': int(likely_columns),
    }


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
        specord_csv_format: bool = False,
        duplicate_block_resolver=None,
        unknown_extension_resolver=None,
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
        duplicate_block_resolver : optional callable(spectrum_dict, block_info)
                     -> 'split' | 'merge'. Called at most once per call to
                     this method (not once per spectrum), the first time
                     _detect_repeated_scan_structure finds that a spectrum's
                     duplicate x-values look like several stacked scans
                     rather than ordinary occasional duplication. Left as
                     None (the default), every spectrum falls straight
                     through to the unconditional merge below, exactly as
                     before this parameter existed — this class stays UI-
                     agnostic; the interactive prompt lives in
                     ImportController, which passes a bound method here.
        unknown_extension_resolver : optional callable(filepath, sniff_info)
                     -> bool. Called at most once, only when filepath's
                     extension ISN'T one of SUPPORTED_EXTENSIONS AND
                     _sniff_numeric_text found its content looks numeric
                     anyway — see that function. Return True to import it
                     as plain text (the same Standard/Interlaced/Row-
                     oriented pipeline any .txt/.csv/.dat file goes
                     through), False to decline. Left as None (the
                     default), an unrecognized extension is always
                     rejected outright — unchanged from this method's
                     behavior before this parameter existed. A file whose
                     content DOESN'T look numeric is always rejected
                     regardless of this parameter; the resolver only ever
                     gets a say once the content already looks plausible.
        SpecOrd CSV : .csv, with specord_csv_format=True — row-oriented
                     export straight off a SpecOrd spectrometer (one row
                     per condition/temperature-step measurement, not one
                     column per spectrum). One spectrum per row; label
                     and metadata carry the condition, run/direction, and
                     temperature parsed from the file — see
                     specord_csv_converter.py's module docstring. A plain
                     .csv (specord_csv_format=False, the default) is
                     completely unaffected and goes through the normal
                     text-table pipeline below as before.

        For Excel files the delimiter / decimal_separator parameters are
        ignored — numbers are read natively from the workbook cells.
        sheet_name selects which worksheet to read (Excel only); None
        auto-selects "spectra" or the first sheet.

        For SPE, SPC, JWS, and SpecOrd-CSV files, every parameter above
        except zero_padding (and each format's own one or two
        format-specific options) is ignored — none of these has a
        delimiter/decimal/header/Layout/column-picker concept at all
        (SpecOrd CSV's own delimiter/decimal are fixed by the format,
        not configurable).
        """
        # logger.debug("load_spectrum_from_file called")
        # logger.debug("delimiter=%r, decimal_separator=%r, interlaced=%s", delimiter, decimal_separator, interlaced_format)

        if not os.path.exists(filepath):
            raise ValueError(f"File not found: {filepath}")

        file_ext = os.path.splitext(filepath)[1].lower()
        if file_ext not in self.SUPPORTED_EXTENSIONS:
            # An extension this app doesn't recognize by name doesn't mean
            # the CONTENT isn't perfectly good spectral data — instruments
            # and collaborators save plain x/y columns under all sorts of
            # extensions. Rather than reject on the name alone, sniff the
            # content (see _sniff_numeric_text) and, if it looks numeric,
            # let the caller's resolver decide whether to read it anyway —
            # exactly as any .txt/.csv/.dat file would be, since nothing
            # below this point actually depends on the extension for plain
            # text files. Binary formats (.spe/.spc/.jws) and Excel aren't
            # affected: they have their own hard extension requirement
            # because sniffing binary bytes as text is meaningless and
            # would either crash or produce garbage.
            sniff = _sniff_numeric_text(filepath)
            if sniff is None:
                raise ValueError(
                    f"Unrecognized file extension '{file_ext}', and this "
                    f"file's content doesn't look like numeric spectral "
                    f"data either (checked the first non-blank lines: too "
                    f"few consistent numeric columns).\n"
                    f"Supported formats: {', '.join(self.SUPPORTED_EXTENSIONS)}"
                )
            approved = (
                unknown_extension_resolver(filepath, sniff)
                if unknown_extension_resolver is not None else False
            )
            if not approved:
                raise ValueError(
                    f"'{os.path.basename(filepath)}' has an unrecognized "
                    f"extension ('{file_ext}') and was not imported."
                )
            # Approved: fall through with file_ext unchanged (still not in
            # SUPPORTED_EXTENSIONS) — none of the branches below match a
            # specific format for it, so it lands in the generic
            # read_table_data() else-branch, exactly like a .txt file.

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
            elif file_ext == '.csv' and specord_csv_format:
                # Opt-in only — see specord_csv_converter.py. A plain
                # .csv with this flag left at its default (False) never
                # reaches this branch, so every existing CSV workflow is
                # completely unaffected.
                spectra_data = read_specord_csv_data(filepath, zero_padding=zero_padding)
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

            # Resolved at most once per file/sheet (not once per spectrum) —
            # a multi-column standard-layout file produces one spectrum_dict
            # per y-column, all sharing the same x-axis structure, so asking
            # the same question again for every column would be pure noise.
            # A per-spectrum sentinel rather than a plain None default: None
            # means "not asked yet", and stays None (never treated as
            # 'merge') until a spectrum actually triggers detection.
            resolved_decision = None

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

                # BLOCK/REPEATED-SCAN DETECTION runs before the unconditional
                # merge below, and only changes anything when a resolver was
                # supplied AND the structure is actually detected — both are
                # required, so every existing caller (tests, scripts, or a
                # future caller that doesn't pass duplicate_block_resolver)
                # gets identically the old merge-only behavior.
                block_info = None
                if duplicate_block_resolver is not None:
                    block_info = _detect_repeated_scan_structure(
                        spectrum_dict.get('x_scale'), spectrum_dict.get('y_scale'))

                if block_info is not None:
                    if resolved_decision is None:
                        resolved_decision = duplicate_block_resolver(spectrum_dict, block_info)
                    if resolved_decision == 'split':
                        for split_dict in _split_into_scans(spectrum_dict, block_info['repeat_count']):
                            self._store_spectrum_dict(split_dict)
                        continue   # replaced by its splits; don't also merge/store the original

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
