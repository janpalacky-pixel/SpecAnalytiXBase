# -*- coding: utf-8 -*-
# src/modules/misc/save_spectra_manager.py
#
# SaveManager – column-oriented and row-oriented export.
#
# Column formats produced (default; also the only option for "Individual
# x-scales")
# -----------------------
#
# "Common x-scale" (all spectra share the same x grid):
#
#     x_scale | spectrum_A | spectrum_B | …
#     --------+-----------+-----------+--
#     100.0   |    1.2    |    3.4    |
#     …
#
# "Individual x-scales" (spectra may have different grids).
# Uses the standard column layout so files can be re-imported without
# any special import-mode flag:
#
#     x_specA | specA | x_specB | specB | …
#     --------+-------+--------+-------+--
#     100.0   |  1.2  | 200.0  |  5.6  |
#     …
#
# This is the same interlaced (x1,y1,x2,y2) layout – the importer's
# "Interlaced Format" option must be selected to re-import such files.
# The save dialog warns the user when this layout is used.
#
# Row layout (optional, "common x-scale" only)
# ---------------------------------------------
# When the dialog's Layout option is set to "Rows", the common-x-scale
# table above is transposed before writing — spectra become rows, the
# shared X-scale becomes the header row:
#
#         | 100.0 | 102.0 | …
#     ----+-------+-------+--
#     spectrum_A |  1.2  |  1.3  |
#     spectrum_B |  3.4  |  3.5  |
#
# This round-trips through Import → Row-oriented layout directly, no
# extra settings needed. Only offered for the common-x-scale path, since
# it needs one shared X-axis to move into the header row — "Individual
# x-scales" has no single shared axis, so it stays column-only.
#
# The app's internal representation is always column-based (one x_scale
# array + one y_scale array per spectrum); row layout is purely an
# output transformation applied right before writing.

import os
import gzip
import pandas as pd
import numpy as np

from src.modules.utils.spectra_validation import axes_match
from src.modules.utils.spectrum_identity import spectrum_id
from src.modules.data_io.spc_data_writer import write_spc_data


class SaveManager:
    """Business logic for saving spectrum data."""

    # Number of progress stages load_snapshot() reports through its
    # optional progress_callback -- kept as a named constant so a caller
    # (SaveController.load_snapshot) can size a progress bar's range
    # without hard-coding the same number twice.
    LOAD_SNAPSHOT_STAGE_COUNT = 6

    # Same idea as LOAD_SNAPSHOT_STAGE_COUNT above, for save_snapshot()'s
    # own optional progress_callback (see SaveController._save_snapshot).
    SAVE_SNAPSHOT_STAGE_COUNT = 4

    # gzip level for .snapx files. Level 6 (Python's own gzip default) --
    # not the max (9) -- is a deliberate choice: on a genuinely large
    # snapshot (a big 2D map with a couple of operations applied), level
    # 9 measured under 10% smaller than level 6 but took noticeably
    # longer to compress. If you need to retune this, measure both size
    # AND wall-clock time on a large real snapshot, not just size -- see
    # the Developer Guide's ".snapx File Size" section for the numbers
    # this was chosen from.
    SNAPSHOT_GZIP_LEVEL = 6

    def __init__(self):
        pass

    @staticmethod
    def _report_progress(progress_callback, stage: int, label: str) -> None:
        """Call progress_callback(stage, label) if one was given. Wrapped
        in its own try/except so a callback that itself raises (a UI
        callback is arbitrary caller code) can never abort the load --
        reporting progress is a nice-to-have, not something the restore
        should ever depend on succeeding."""
        if progress_callback is None:
            return
        try:
            progress_callback(stage, label)
        except Exception:
            logger.warning("Snapshot: progress_callback raised, ignoring", exc_info=True)

    # ------------------------------------------------------------------
    # Public: save a table (all selected spectra in one file)
    # ------------------------------------------------------------------

    def save_table(self, spectra: list, file_path: str, settings: dict) -> None:
        """
        Save selected spectra to a single table file.

        Parameters
        ----------
        spectra   : list of spectrum dicts in selection order
        file_path : destination path
        settings  : dict from SaveOptionsDialog.get_settings(). Recognises
                    an optional 'save_layout' key: 'columns' (default) or
                    'rows'. 'rows' only applies when the common x-scale
                    path is used (it needs a single shared X-axis to move
                    into the header row) — the dialog only offers it in
                    that combination, and it's silently ignored otherwise.
        """
        if not spectra:
            raise ValueError("No spectra to save")

        if settings.get('format') == 'spc':
            # GRAMS/.spc has no equivalent of the text/Excel "individual
            # x-scales" interlaced trick — a single .spc file's subfiles
            # all share ONE x-axis by construction (see spc_data_writer's
            # module docstring). So this is not an option the user can
            # toggle for this format; it's mandatory, and checked here
            # exactly like every other "combine spectra" tool in this app
            # checks it (spectra_validation.axes_match), so the same
            # spectra that would be rejected by SVD/PCA/2D-correlation for
            # mismatched axes are rejected here for the same reason.
            if not self.validate_common_scale(spectra):
                raise ValueError(
                    "Cannot save as .spc: the selected spectra don't share "
                    "a common x-scale. A single .spc file requires every "
                    "spectrum in it to be sampled on the same x-axis — use "
                    "the Data Range operation to put them on a common axis "
                    "first, or save each spectrum to its own .spc file "
                    "instead (Save Individual Files)."
                )
            write_spc_data(file_path, spectra)
            return

        use_common = settings.get('use_common_scale', False) and self.validate_common_scale(spectra)
        save_layout = settings.get('save_layout', 'columns')

        if use_common:
            data = self._prepare_common_scale_data(spectra, settings)
            if save_layout == 'rows':
                data = self._transpose_to_row_layout(data)
                # Row 0 (the shared X-scale) is mandatory in Row-oriented
                # layout, unlike the optional header row in Standard
                # layout — always write it regardless of the "Include
                # column labels" checkbox, which here only controls
                # whether the label *column* holds real names or numbers
                # (already baked into `data` by _prepare_common_scale_data).
                self._write(data, file_path, settings, force_header=True)
                return
        else:
            data = self._prepare_individual_scales_data(spectra, settings)

        self._write(data, file_path, settings)

    # ------------------------------------------------------------------
    # Public: save each spectrum as its own file
    # ------------------------------------------------------------------

    def save_individual(self, spectra: list, directory: str, settings: dict) -> list:
        """
        Save each spectrum in its own file inside *directory*.

        Returns the list of filenames that were successfully written.
        Raises RuntimeError if every file fails; logs a warning for
        partial failures.
        """
        if not os.path.exists(directory):
            raise FileNotFoundError(f"Directory does not exist: {directory}")
        if not os.access(directory, os.W_OK):
            raise PermissionError(f"No write permission for directory: {directory}")

        fmt = settings.get('format')
        ext = '.spc' if fmt == 'spc' else '.xlsx' if fmt == 'excel' else '.txt'
        saved, failed = [], []
        used_filenames = set()

        for spectrum in spectra:
            try:
                filename = self._safe_filename(spectrum['label'], ext)
                # _safe_filename() strips filesystem-illegal characters and
                # truncates to 200 chars — meaning two DIFFERENT spectra
                # (duplicate labels from separate import sessions, or
                # labels that only differ by a character the sanitizer
                # strips, e.g. 'sample/01' vs 'sample_01') can collide on
                # the SAME output filename. Without this check, the
                # second write here just silently overwrites the first
                # spectrum's file — no exception, so it never reaches the
                # 'failed' handling below; one spectrum's data quietly
                # vanishes with no warning at all. Disambiguated with a
                # counter suffix instead, same convention this app
                # already uses for colliding spectrum names elsewhere
                # (see e.g. find_unique_name() in operations_controller.py).
                if filename in used_filenames:
                    stem = filename[:-len(ext)] if filename.endswith(ext) else filename
                    counter = 2
                    candidate = f"{stem}_{counter}{ext}"
                    while candidate in used_filenames:
                        counter += 1
                        candidate = f"{stem}_{counter}{ext}"
                    filename = candidate
                used_filenames.add(filename)

                path = os.path.join(directory, filename)
                if fmt == 'spc':
                    # One subfile, no common-x-scale requirement to check
                    # here — each spectrum gets its own file, so there's
                    # nothing to share an axis WITH.
                    write_spc_data(path, [spectrum])
                else:
                    data = self._single_spectrum_dataframe(spectrum, settings)
                    self._write(data, path, settings)
                saved.append(filename)
            except Exception as exc:
                failed.append((spectrum['label'], str(exc)))

        if failed:
            msg = f"Failed to save {len(failed)} file(s):\n"
            msg += "\n".join(f"  - {lbl}: {err}" for lbl, err in failed)
            if not saved:
                raise RuntimeError(msg)
            logger.warning(msg)

        return saved

    # ------------------------------------------------------------------
    # Data preparation: common x-scale
    # ------------------------------------------------------------------

    def _prepare_common_scale_data(self, spectra: list, settings: dict) -> pd.DataFrame:
        """
        One shared x column followed by one y column per spectrum.

            x_scale | label_A | label_B | …
        """
        common_x = spectra[0]['x_scale']
        col_order = []

        if settings.get('use_labels', True):
            data = {'x_scale': common_x}
            col_order.append('x_scale')
            for sp in spectra:
                data[sp['label']] = sp['y_scale']
                col_order.append(sp['label'])
        else:
            # Numeric column names: 1, 2, 3, …
            data = {'1': common_x}
            col_order.append('1')
            for i, sp in enumerate(spectra, start=2):
                data[str(i)] = sp['y_scale']
                col_order.append(str(i))

        return pd.DataFrame(data, columns=col_order)

    def _transpose_to_row_layout(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Transpose a column-oriented, common-x-scale DataFrame
        (x_scale | label_A | label_B | …) into Row-oriented layout —
        spectra in rows, shared X-scale in the header row — matching the
        importer's Row-oriented convention exactly (row 0 = shared
        X-scale, first column = spectrum labels), so the output round-
        trips through Import → Row-oriented with no extra settings beyond
        selecting that layout.

        Internally the app always represents spectra as columns; this is
        purely an output transformation applied right before writing —
        nothing about how spectra are stored or processed changes.
        """
        x_col_name = data.columns[0]   # 'x_scale' (labelled) or '1' (numeric mode)
        transposed = data.set_index(x_col_name).T
        transposed = transposed.rename_axis(None, axis=0).rename_axis(None, axis=1)
        transposed = transposed.reset_index().rename(columns={'index': ''})
        return transposed

    def _prepare_individual_scales_data(self, spectra: list, settings: dict) -> pd.DataFrame:
        """
        Interlaced layout: x1, y1, x2, y2, … (one x+y pair per spectrum).
        Spectra with different lengths are padded with NaN.

        NOTE: to re-import this file the user must enable
              "Interlaced Format" in Import Settings.
        """
        max_len = max(len(sp['x_scale']) for sp in spectra)
        use_labels = settings.get('use_labels', True)
        data: dict = {}
        col_order: list = []

        for i, sp in enumerate(spectra):
            x_data = _pad(sp['x_scale'], max_len)
            y_data = _pad(sp['y_scale'], max_len)

            if use_labels:
                x_col = f"x_{sp['label']}"
                y_col = sp['label']
            else:
                x_col = str(2 * i + 1)   # 1, 3, 5, …
                y_col = str(2 * i + 2)   # 2, 4, 6, …

            data[x_col] = x_data
            data[y_col] = y_data
            col_order.extend([x_col, y_col])

        return pd.DataFrame(data, columns=col_order)

    # ------------------------------------------------------------------
    # Single-spectrum DataFrame (for save_individual)
    # ------------------------------------------------------------------

    def _single_spectrum_dataframe(self, spectrum: dict, settings: dict) -> pd.DataFrame:
        """
        Two-column DataFrame: x_scale | label  (or  1 | 2).
        Always column-oriented; always uses index=False on write.
        """
        use_labels = settings.get('use_labels', True)

        if use_labels:
            return pd.DataFrame({
                'x_scale': spectrum['x_scale'],
                spectrum['label']: spectrum['y_scale'],
            })
        else:
            return pd.DataFrame({
                '1': spectrum['x_scale'],
                '2': spectrum['y_scale'],
            })

    # ------------------------------------------------------------------
    # Writing helpers  (Bug 7/10 fix: index=False is always correct now
    #  because labels are stored as regular columns, not the DataFrame index)
    # ------------------------------------------------------------------

    def _write(self, data: pd.DataFrame, file_path: str, settings: dict,
               force_header: bool = None) -> None:
        if settings.get('format') == 'excel':
            self._write_excel(data, file_path, settings, force_header)
        else:
            self._write_text(data, file_path, settings, force_header)

    def _write_text(self, data: pd.DataFrame, file_path: str, settings: dict,
                     force_header: bool = None) -> None:
        sep = settings.get('value_separator', '\t')
        dec = settings.get('decimal_separator', '.')
        header = settings.get('use_labels', True) if force_header is None else force_header
        try:
            data.to_csv(
                file_path,
                sep=sep,
                decimal=dec,
                index=False,          # labels live in columns, not the index
                header=header,
                encoding='utf-8-sig', # BOM for Excel compatibility
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to write text file '{file_path}': {exc}") from exc

    def _write_excel(self, data: pd.DataFrame, file_path: str, settings: dict,
                      force_header: bool = None) -> None:
        # Note: Excel stores numbers as native floats; the decimal_separator
        # setting has no effect on .xlsx output (this is correct behaviour).
        header = settings.get('use_labels', True) if force_header is None else force_header
        try:
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                data.to_excel(
                    writer,
                    sheet_name='spectra',
                    index=False,
                    header=header,
                )
        except Exception as exc:
            raise RuntimeError(f"Failed to write Excel file '{file_path}': {exc}") from exc

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_common_scale(self, spectra: list) -> bool:
        """Return True when every spectrum shares the same x-scale.

        Uses spectra_validation.axes_match — the same adaptive-tolerance
        comparison every analysis tool that combines spectra (SVD, PCA,
        Cluster analysis, MCR-ALS, NMF, 2D correlation, ...) uses to answer
        this exact question. Previously this method had its own,
        independent fixed-tolerance comparison (rtol=atol=1e-10), so a set
        of spectra could be accepted as "common x-scale" by one and
        rejected by the other — e.g. axes rebuilt by arithmetic (Data
        Range linearisation, a unit conversion) that agree well within any
        real instrument's precision but not to 1e-10. One shared
        definition of "same x-axis" now applies everywhere.
        """
        if len(spectra) < 2:
            return True
        ref = spectra[0]['x_scale']
        for sp in spectra[1:]:
            if not axes_match(ref, sp['x_scale']):
                return False
        return True

    # ------------------------------------------------------------------
    # Filename helper
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_filename(label: str, extension: str) -> str:
        safe = re.sub(r'[/\\:*?"<>|]', '_', label)
        safe = safe[:200].rstrip('.')
        return safe + extension

    # ------------------------------------------------------------------
    # Snapshot save / load  — JSON format with base64 numpy encoding
    #
    # Why JSON instead of pickle?
    # Pickle encodes the full Python module path of every object it stores.
    # If a class moves between files during refactoring, old snapshots become
    # unloadable with a cryptic error.  JSON has no such dependency — it stores
    # plain data, so snapshots survive any amount of code reorganisation.
    #
    # Why base64 for numpy arrays?
    # Storing arrays as JSON lists (e.g. [100.0, 200.0, ...]) is human-readable
    # but slow and large — each number becomes a text string. For large datasets
    # (1000+ spectra × 2000 points) this becomes noticeable.
    # Base64 encodes the raw binary bytes of the array as a compact text string,
    # giving near-pickle speed and size while keeping the JSON format.
    #
    # The rest of the snapshot (labels, settings, metadata) remains fully
    # human-readable plain text.
    #
    # Numpy arrays are serialised as:
    #   {"__ndarray__": true, "data": "<base64 string>", "dtype": "float64", "shape": [261]}
    # ------------------------------------------------------------------

    @staticmethod
    def _json_encode(obj):
        """
        Custom JSON encoder.
        Converts numpy arrays to base64-encoded binary strings.
        Everything else (dicts, lists, strings, numbers) is handled natively.
        """
        if isinstance(obj, np.ndarray):
            import base64
            return {
                '__ndarray__': True,
                'data': base64.b64encode(obj.tobytes()).decode('ascii'),
                'dtype': str(obj.dtype),
                'shape': list(obj.shape),
            }
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")

    @staticmethod
    def _json_decode(obj):
        """
        Custom JSON decoder.
        Restores numpy arrays from their base64-encoded form.
        All other objects are returned unchanged.
        """
        if isinstance(obj, dict) and obj.get('__ndarray__'):
            import base64
            raw = base64.b64decode(obj['data'])
            return np.frombuffer(raw, dtype=obj['dtype']).reshape(obj['shape'])
        return obj

    @classmethod
    def _to_json(cls, state: dict) -> str:
        """Serialise *state* to a JSON string, handling numpy arrays."""
        import json
        return json.dumps(state, default=cls._json_encode, indent=2)

    @classmethod
    def _from_json(cls, text: str) -> dict:
        """Deserialise a JSON string, restoring numpy arrays."""
        import json

        def object_hook(obj):
            return cls._json_decode(obj)

        return json.loads(text, object_hook=object_hook)

    def _build_state(self, main_controller) -> dict:
        """Collect the full application state into a plain-data dict."""
        ui = main_controller.view

        plot_settings = {
            'plot_type':                 self._safe_get(ui, 'comboBox_plot_type_choice', 'currentText'),
            'use_automatic_line_colors': main_controller.use_automatic_line_colors,
            'use_default_points':        main_controller.use_default_points,
            'x_scale':                   self._safe_get(ui, 'x_scale_comboBox', 'currentText'),
            'y_scale':                   self._safe_get(ui, 'y_scale_comboBox', 'currentText'),
            'grid_settings':             main_controller.grid_settings.copy(),
            'spectra_ordering':          self._safe_get(ui, 'comboBox_spectra_ordering', 'currentText'),
            'reverse_order':             self._safe_get(ui, 'checkBox_reverse_order', 'isChecked'),
        }
        # Drop any field whose widget no longer exists in this build of the
        # UI (e.g. after a refactor) rather than storing None/False as if
        # it were a real value — this keeps old and new snapshots equally
        # valid, and _restore_ui_state's "if 'x' in s" checks naturally
        # skip whatever wasn't saved.
        plot_settings = {k: v for k, v in plot_settings.items() if v is not None}

        selected_indices = list(main_controller.spectrum_selector.selected_indices)

        state = {
            'timestamp': pd.Timestamp.now().isoformat(),
            'original_spectra': main_controller.original_spectra,
            'selected_indices': selected_indices,
            'plot_settings': plot_settings,
            'link_axes': {
                'link_x':           self._safe_get(ui, 'link_x_axes_checkBox', 'isChecked', default=False),
                'link_y':           self._safe_get(ui, 'link_y_axes_checkBox', 'isChecked', default=False),
                'link_x_direction': self._safe_get(ui, 'comboBox_linking_x_axes', 'currentText', default='all'),
                'link_y_direction': self._safe_get(ui, 'comboBox_linking_y_axes', 'currentText', default='all'),
            },
        }

        # selected_spectra is reconstructable from original_spectra +
        # selected_indices in the exact same order
        # SpectrumSelectorController.get_selected_spectra() always builds
        # it -- see that method's own "sort indices to maintain the order
        # as they appear in original_spectra" comment. Only store it
        # explicitly (a second time) when it does NOT match that
        # reconstruction; on a large snapshot with most/all spectra
        # selected, that's normally never, which is most of where the
        # old file-size blowup came from (see the Developer Guide's
        # ".snapx File Size" section).
        reconstructed_selection = [
            main_controller.original_spectra[i]
            for i in sorted(selected_indices)
            if 0 <= i < len(main_controller.original_spectra)
        ]
        if not self._spectra_lists_equal(
                main_controller.selected_spectra, reconstructed_selection):
            state['selected_spectra'] = main_controller.selected_spectra

        if hasattr(main_controller, 'custom_plot_properties_manager'):
            state['plot_properties'] = (
                main_controller.custom_plot_properties_manager.spectrum_properties.copy()
            )

        if hasattr(main_controller, 'operations_controller'):
            op = main_controller.operations_controller
            if hasattr(op, 'operations_manager'):
                # Any chain entry whose output_spectra is content-identical
                # to the top-level original_spectra just saved above (in
                # practice: whichever entry is currently active --
                # main_controller.original_spectra always mirrors
                # get_current_spectra()'s output, see the comment on
                # MainController.original_spectra) is a second full copy
                # of data already being saved. Omit output_spectra from
                # that entry and mark it for backfilling on load instead
                # of storing it twice -- checked per entry, by content,
                # rather than assumed to only ever be the active one, so
                # this stays correct even if that invariant is ever
                # violated somewhere.
                deduped_chain = []
                for entry in op.operations_manager.operations_chain:
                    if (isinstance(entry, dict)
                            and self._spectra_lists_equal(
                                entry.get('output_spectra', []),
                                state['original_spectra'])):
                        entry_copy = {k: v for k, v in entry.items()
                                      if k != 'output_spectra'}
                        entry_copy['output_spectra_omitted'] = True
                        deduped_chain.append(entry_copy)
                    else:
                        deduped_chain.append(entry)

                state['operations'] = {
                    'operations_chain': deduped_chain,
                    'active_operation_index': op.operations_manager.active_operation_index,
                    'current_parameters': op.current_parameters,
                }
                # operations_manager.original_spectra is the state BEFORE any
                # operation was applied — needed so the chain can be
                # replayed/redone. Whether it needs to be stored separately
                # from the top-level original_spectra already saved above is
                # decided by comparing the two directly and completely (every
                # field, including metadata, not just label/x_scale/y_scale)
                # — not by any assumption about which code path changed
                # what. An earlier version of this trusted an empty
                # operations chain as a proxy for "nothing changed"; that's
                # only correct as long as every other part of the app keeps
                # these two lists in sync whenever the chain is empty, which
                # is an invariant upheld by convention across several files,
                # not something this one file can verify — and this
                # codebase has a documented history of exactly this kind of
                # desync (see the comment in rename_spectra_controller.py
                # about renames silently vanishing once two spectra lists
                # drifted apart). Comparing the actual content removes that
                # assumption entirely: if the two are provably identical,
                # skip the duplicate; if they differ in ANY way — or the
                # comparison can't be sure — keep both (see
                # _spectra_lists_equal: it fails toward "not equal", i.e.
                # toward keeping both copies, on anything ambiguous).
                ops_baseline = op.operations_manager.original_spectra
                if not self._spectra_lists_equal(ops_baseline, state['original_spectra']):
                    state['operations']['original_spectra'] = ops_baseline
                if hasattr(op.operations_manager, 'import_batches'):
                    state['operations']['import_batches'] = op.operations_manager.import_batches

        # Melting Curve Analysis' "Saved Fits" -- a named container of
        # complete result snapshots (curve, fit, thermodynamics) the user
        # explicitly asked to keep around for comparison via "Save Current
        # Fit", independent of whatever curve is currently active. Unlike
        # the many small "last dialog settings" caches elsewhere in this
        # app (never snapshotted -- they're throwaway conveniences), this
        # one holds content the user deliberately chose to keep, so losing
        # it on every snapshot load defeats its own purpose. Only written
        # when there's actually something in it, same reasoning as the
        # None-filtering on plot_settings above.
        mcc = getattr(main_controller, 'melting_curve_controller', None)
        if mcc is not None and getattr(mcc, 'saved_fits', None):
            state['melting_curve_saved_fits'] = mcc.saved_fits

        return state

    @staticmethod
    def _values_equal(va, vb) -> bool:
        """
        Numpy- and container-safe equality check for one value from a
        spectrum dict (used by _spectra_lists_equal). Recurses into dicts
        and lists/tuples so a nested array inside metadata is compared
        correctly instead of tripping Python's "truth value of an array
        is ambiguous" error. Anything it can't confidently compare counts
        as NOT equal -- the safe direction, since the only thing that
        depends on this is whether to keep a second copy of the data.
        """
        if isinstance(va, np.ndarray) or isinstance(vb, np.ndarray):
            if not (isinstance(va, np.ndarray) and isinstance(vb, np.ndarray)):
                return False
            if va.shape != vb.shape:
                return False
            try:
                return bool(np.array_equal(va, vb, equal_nan=True))
            except Exception:
                return False
        if isinstance(va, dict) and isinstance(vb, dict):
            if va.keys() != vb.keys():
                return False
            return all(SaveManager._values_equal(va[k], vb[k]) for k in va)
        if isinstance(va, (list, tuple)) and isinstance(vb, (list, tuple)):
            if len(va) != len(vb):
                return False
            return all(SaveManager._values_equal(x, y) for x, y in zip(va, vb))
        try:
            return bool(va == vb)
        except Exception:
            return False

    @staticmethod
    def _spectra_lists_equal(a: list, b: list) -> bool:
        """
        Exhaustive equality check between two spectrum-dict lists -- every
        key each spectrum has, including nested metadata, not a curated
        subset of fields. Used by _build_state to decide whether three
        different things are genuinely identical to the top-level
        original_spectra already being saved -- operations_manager's
        pre-operations baseline, main_controller.selected_spectra, and
        each operations_chain entry's output_spectra -- so the snapshot
        file isn't made to store the same spectral data twice (see the
        Developer Guide's ".snapx File Size" section). An earlier
        version of this compared only label/x_scale/y_scale, which a
        metadata-only change could have fooled into a false "equal" --
        this compares everything, and defers to _values_equal's
        fail-toward-"not-equal" behavior on anything it can't be sure
        about.

        Order-independent: a positional (zip-based) pass is tried first
        as a fast path, but a real, confirmed bug meant this dedup
        silently never fired for operations_chain entries in actual GUI
        use. main_controller.original_spectra is re-sorted into natural
        label order by MainController.order_spectra() right after most
        operations (SNIP Baseline, Cosmic Ray Removal, ...), while the
        corresponding operations_chain entry's output_spectra is built
        as "unaffected spectra in their current order, then the
        processed spectra appended at the end" and is never sorted. Both
        lists end up holding the exact same spectra, just in a different
        order -- which the positional pass alone reports as "not equal",
        defeating the whole optimization on every real snapshot with more
        than a couple of spectra (measured: this alone roughly doubled
        the size of the affected chain entry's contribution to the file).
        When the fast path fails, this falls back to matching spectra by
        their 'label' and comparing those pairs instead -- but only when
        every label in each list is unique, so there's no ambiguity in
        the pairing; if either list has a duplicate or missing label, or
        the label sets don't match, it stays with "not equal" (the safe
        direction: at worst a second copy is kept, never data loss).
        """
        if a is b:
            return True
        if len(a) != len(b):
            return False

        def _positional_equal(list_a, list_b):
            for sa, sb in zip(list_a, list_b):
                if sa.keys() != sb.keys():
                    return False
                for key in sa:
                    if not SaveManager._values_equal(sa[key], sb[key]):
                        return False
            return True

        if _positional_equal(a, b):
            return True

        # Fast path failed -- possibly just a different order for the
        # exact same spectra. Only attempt to re-pair by label when that
        # pairing is unambiguous on both sides.
        try:
            labels_a = [sa['label'] for sa in a]
            labels_b = [sb['label'] for sb in b]
        except (KeyError, TypeError):
            return False
        if len(set(labels_a)) != len(labels_a) or len(set(labels_b)) != len(labels_b):
            return False
        if set(labels_a) != set(labels_b):
            return False

        a_by_label = sorted(a, key=lambda s: s['label'])
        b_by_label = sorted(b, key=lambda s: s['label'])
        return _positional_equal(a_by_label, b_by_label)

    @staticmethod
    def _deep_copy_spectra_list(spectra: list) -> list:
        """
        Independent copy of a list of spectrum dicts -- a fresh dict per
        spectrum, and a fresh .copy() of every numpy array and nested
        dict inside it, so the result shares no mutable object with
        *spectra*. Used only to backfill an operations_chain entry whose
        output_spectra was omitted at save time because it was identical
        to main_controller.original_spectra (see _build_state and
        _restore_operations): that entry needs its OWN copy, not a
        second reference to the same list object main_controller.
        original_spectra already points at, or a later in-place edit to
        one would silently corrupt the other. Mirrors the same
        shallow-dict-plus-array-copy pattern used for the same reason in
        SpectrumSelectorController.get_selected_spectra() and
        IncrementalOperationsManager's own _deep_copy_spectra.
        """
        out = []
        for spectrum in spectra:
            copy = {}
            for key, value in spectrum.items():
                if isinstance(value, np.ndarray):
                    copy[key] = value.copy()
                elif isinstance(value, dict):
                    copy[key] = value.copy()
                else:
                    copy[key] = value
            out.append(copy)
        return out

    # ------------------------------------------------------------------
    # Defensive UI widget access (snapshot save/load)
    #
    # The snapshot save/load code has to reach into a large number of
    # named widgets on the main window. Those widget names are exactly
    # the kind of thing that changes during a UI refactor — and when one
    # does, a plain attribute access (ui.some_widget) throws
    # AttributeError and, left unguarded, aborts the ENTIRE save or load
    # partway through: on save, the whole snapshot silently fails to
    # write; on load, everything that *would* have restored successfully
    # is lost too, and the user sees a misleading "file may be corrupted"
    # message for what's actually just one renamed widget.
    #
    # These two helpers make each individual widget read/write
    # independently fault-tolerant: a missing or renamed widget is
    # skipped (with a logged warning naming exactly which one), and
    # everything else still saves or restores normally.
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_get(ui, attr: str, getter: str, default=None):
        """Defensively read a value from a named widget on *ui*.
        Returns *default* (and logs a warning) if the widget doesn't
        exist, or if calling the getter on it fails for any reason."""
        widget = getattr(ui, attr, None)
        if widget is None:
            logger.warning(
                "Snapshot: UI widget '%s' not found (skipped) — the UI may "
                "have changed since this was written.", attr)
            return default
        try:
            return getattr(widget, getter)()
        except Exception:
            logger.warning(
                "Snapshot: failed reading %s.%s()", attr, getter, exc_info=True)
            return default

    @staticmethod
    def _safe_set(ui, attr: str, setter: str, value) -> None:
        """Defensively write a value to a named widget on *ui*. Skips
        (with a logged warning) if the widget doesn't exist, or if
        calling the setter fails for any reason — never raises, so one
        stale widget reference can't abort the rest of a snapshot
        restore."""
        widget = getattr(ui, attr, None)
        if widget is None:
            logger.warning(
                "Snapshot: UI widget '%s' not found, skipping restore of "
                "this value — the UI may have changed since the snapshot "
                "was saved.", attr)
            return
        try:
            getattr(widget, setter)(value)
        except Exception:
            logger.warning(
                "Snapshot: failed restoring %s.%s(%r)", attr, setter, value,
                exc_info=True)

    def save_snapshot(self, main_controller, file_path: str, progress_callback=None,
                       compression_level=None) -> bool:
        """
        Save application state as a gzip-compressed JSON snapshot file.

        The '.snapx' extension and the Save/Load dialogs' file filters
        are unchanged -- only the bytes on disk are now a gzip stream
        instead of plain UTF-8 text, the same way a .docx or .xlsx file
        is really a zip archive wearing a familiar extension. See the
        Developer Guide's ".snapx File Size" section for why, and the
        real measured numbers this was based on. _load_state() reads
        both this and the older, uncompressed format transparently.

        progress_callback, if given, is called as progress_callback(stage,
        label) at each of SAVE_SNAPSHOT_STAGE_COUNT points below -- same
        (stage, label) contract as load_snapshot()'s own progress_callback
        -- so a caller can drive a progress dialog through a slow save (a
        large 2D map's worth of spectra, where the gzip step alone can
        take several seconds) instead of the UI just sitting there
        looking frozen. Purely optional -- every existing caller that
        doesn't pass one behaves exactly as before.

        compression_level, if given, overrides SNAPSHOT_GZIP_LEVEL for
        this one save (SaveOptionsDialog's "Fast"/"Balanced"/"Maximum"
        presets map to gzip levels 1/6/9 -- see
        SaveOptionsDialog._COMPRESSION_PRESETS). Anything outside gzip's
        valid 1-9 range is quietly clamped rather than raising, since a
        bad value here should never be the reason a save fails. None (the
        default) uses SNAPSHOT_GZIP_LEVEL, unchanged from before this
        parameter existed.
        """
        try:
            self._report_progress(progress_callback, 1, "Collecting application state…")
            state = self._build_state(main_controller)

            self._report_progress(progress_callback, 2, "Serializing…")
            json_text = self._to_json(state)
            json_bytes = json_text.encode('utf-8')

            if compression_level is None:
                level = self.SNAPSHOT_GZIP_LEVEL
            else:
                level = max(1, min(9, int(compression_level)))

            self._report_progress(progress_callback, 3, "Compressing…")
            compressed = gzip.compress(json_bytes, compresslevel=level)

            self._report_progress(progress_callback, 4, "Writing file…")
            with open(file_path, 'wb') as fh:
                fh.write(compressed)

            logger.info(
                "Snapshot saved: %s (%d bytes, gzip level %d, %.1fx "
                "smaller than uncompressed JSON)", file_path, len(compressed),
                level, len(json_bytes) / max(len(compressed), 1))
            return True

        except Exception:
            logger.exception("Failed to save snapshot")
            return False

    def load_snapshot(self, main_controller, file_path: str, progress_callback=None) -> bool:
        """
        Load a JSON snapshot file (as written by save_snapshot) and restore
        the full application state from it: spectra, operations history,
        and UI/plot settings.

        progress_callback, if given, is called as progress_callback(stage,
        label) at each of LOAD_SNAPSHOT_STAGE_COUNT points below, so a
        caller can drive a progress dialog through a slow load (a large
        2D map's worth of spectra) instead of the UI just sitting there
        looking frozen. Purely optional -- every existing caller that
        doesn't pass one behaves exactly as before.
        """
        try:
            self._report_progress(progress_callback, 1, "Reading snapshot file…")
            state = self._load_state(file_path)

            # Basic sanity check. 'selected_spectra' is deliberately NOT
            # required here -- _build_state omits it whenever it's
            # reconstructable from original_spectra + selected_indices (see
            # that method's comment), which is the common case, so a valid
            # snapshot may legitimately not have that key at all.
            required = {'original_spectra', 'selected_indices'}
            if not required.issubset(state.keys()):
                raise ValueError(
                    "The file does not appear to be a valid snapshot "
                    "(missing required data)."
                )

            # Every normal path that creates or renames a spectrum in
            # this app actively guarantees unique labels
            # (SpectrumManager._store_spectrum_dict auto-uniquifies on
            # import; RenameSpectraController checks app-wide before
            # allowing any rename) — but this snapshot's
            # 'original_spectra' is restored via a direct assignment
            # below, bypassing both of those guards entirely. A snapshot
            # with duplicate labels can only mean the file was
            # hand-edited or corrupted after being saved from a
            # legitimately unique state. Refused here, cleanly, rather
            # than silently proceeding — auto-renaming and hoping every
            # OTHER piece of restored state that references a spectrum
            # by label (selected_spectra, custom plot properties,
            # operations history, grid settings) still resolves
            # correctly afterward is far riskier than just stopping,
            # the same "stop rather than silently corrupt" response
            # already used elsewhere in this app for exactly this kind
            # of situation (see RenameSpectraDialog's own duplicate-name
            # check).
            self._validate_unique_labels(state['original_spectra'])

            self._report_progress(progress_callback, 2, "Restoring plot settings…")
            self._restore_ui_state(main_controller, state)
            main_controller.original_spectra = state['original_spectra']
            # 'selected_spectra' is only present in state when it wasn't
            # reconstructable from original_spectra + selected_indices at
            # save time (see _build_state's dedupe) -- when it's missing,
            # rebuild it exactly the way
            # SpectrumSelectorController.get_selected_spectra() always
            # does: original_spectra filtered by selected_indices, in
            # ascending index order.
            if 'selected_spectra' in state:
                main_controller.selected_spectra = state['selected_spectra']
            else:
                main_controller.selected_spectra = [
                    main_controller.original_spectra[i]
                    for i in sorted(state.get('selected_indices', []))
                    if 0 <= i < len(main_controller.original_spectra)
                ]

            # SpectrumManager's own bookkeeping (the dict spectra are
            # actually stored under, plus its id<->label maps) was
            # previously left completely untouched by a snapshot load —
            # main_controller.original_spectra now reflects the
            # snapshot, but spectrum_manager.spectra would still reflect
            # whatever was loaded BEFORE it. That matters because
            # _store_spectrum_dict()'s collision-avoidance (the auto-
            # uniquify guard mentioned above) checks against THIS dict —
            # stale, it could let a freshly-imported spectrum collide
            # with one that's only "real" in the old, pre-snapshot
            # state, or fail to detect a collision with what's actually
            # showing now.
            self._report_progress(progress_callback, 3, "Restoring spectra…")
            self._resync_spectrum_manager(main_controller, state['original_spectra'])

            if 'operations' in state and hasattr(main_controller, 'operations_controller'):
                self._report_progress(progress_callback, 4, "Restoring operations history…")
                self._restore_operations(main_controller, state['operations'])

            if 'melting_curve_saved_fits' in state:
                self._restore_melting_curve_saved_fits(
                    main_controller, state['melting_curve_saved_fits'])

            if hasattr(main_controller, 'spectrum_selector'):
                self._report_progress(progress_callback, 5, "Restoring spectrum selection…")
                self._restore_spectrum_selection(main_controller, state)

            # Exactly one render for the whole load, now that every other
            # piece of state (UI values, operations, selection) has already
            # been restored above. _restore_ui_state already set
            # main_controller.grid_settings (and the row/col spinboxes) to
            # their restored values, so plot_spectra() alone — which reads
            # comboBox_plot_type_choice and grid_settings itself — is all
            # ANY plot type needs here, Grid included; there's no separate
            # update_grid_layout() call (it would only re-read the same
            # spinbox values _restore_ui_state already set, then call
            # plot_spectra() anyway). Doing this only once here (instead of
            # once per intermediate step) matters most for a large 2D map
            # in Grid plot mode, where each render rebuilds every subplot
            # in the grid.
            self._report_progress(progress_callback, 6, "Rendering plot…")

            # For that same large-2D-map case, the render itself can take
            # long enough that the caller's progress dialog needs to keep
            # pumping QApplication.processEvents() *during* it, not just
            # before/after — see plot_spectra()'s own progress_callback
            # parameter (forwarded straight through to grid_plot_mode /
            # overlay_plot_mode's per-item notify_progress() calls; see
            # progress_utils.py). That callback's contract is "no
            # arguments", unlike the (stage, label) contract this method's
            # own progress_callback uses (see the Developer Guide's
            # "Snapshot Files (.snapx): Save/Load Pipeline" section) — so
            # build a small no-arg adapter around it here rather than
            # confusing the two conventions at the call site.
            render_progress_callback = None
            if progress_callback is not None:
                def render_progress_callback():
                    self._report_progress(
                        progress_callback, self.LOAD_SNAPSHOT_STAGE_COUNT,
                        "Rendering plot…")

            if main_controller.selected_spectra:
                main_controller.plot_spectra(progress_callback=render_progress_callback)

            logger.info("Snapshot loaded: %s", file_path)
            return True

        except ValueError as exc:
            logger.exception("Invalid snapshot file")
            raise RuntimeError(str(exc)) from exc

        except Exception:
            logger.exception("Failed to load snapshot")
            raise RuntimeError(
                "Failed to load snapshot. The file may be corrupted or was "
                "saved with an incompatible version of the application."
            )

    def _validate_unique_labels(self, original_spectra: list) -> None:
        """Refuse to load a snapshot whose spectra don't have unique
        labels — see the call site in load_snapshot for why this can
        only happen via a hand-edited/corrupted file, and why refusing
        cleanly is safer than trying to auto-fix it.

        Raises ValueError (converted to a clean RuntimeError by
        load_snapshot's own exception handling, same as the sanity
        check right above this call).
        """
        counts = {}
        for spectrum in original_spectra:
            label = spectrum.get('label')
            counts[label] = counts.get(label, 0) + 1
        duplicates = sorted(label for label, n in counts.items() if n > 1)
        if duplicates:
            names = "', '".join(str(d) for d in duplicates)
            raise ValueError(
                f"This snapshot file can't be loaded: the label(s) '{names}' "
                f"are used by more than one spectrum. A snapshot saved by "
                f"this application should never contain duplicate spectrum "
                f"labels — this usually means the file was edited by hand "
                f"or corrupted after being saved."
            )

    def _resync_spectrum_manager(self, main_controller, original_spectra: list) -> None:
        """Rebuild SpectrumManager's internal bookkeeping (self.spectra,
        id_to_label_map, label_to_id_map) to match the just-restored
        original_spectra list — see the call site in load_snapshot for
        why this was previously left stale after a snapshot load.

        No-op if main_controller doesn't expose a spectrum_manager (e.g.
        a lighter-weight test harness) — this is a consistency
        improvement, not something later code should hard-depend on
        existing.
        """
        import_controller = getattr(main_controller, 'import_controller', None)
        spectrum_manager = getattr(import_controller, 'spectrum_manager', None) if import_controller else None
        if spectrum_manager is None:
            return

        from src.modules.core.spectrum_manager import Spectrum

        spectrum_manager.clear_spectra()
        for spectrum_dict in original_spectra:
            label = spectrum_dict.get('label')
            metadata = spectrum_dict.get('metadata') or {}
            if label is None:
                continue
            try:
                spectrum_manager.spectra[label] = Spectrum(
                    x_scale=spectrum_dict['x_scale'],
                    y_scale=spectrum_dict['y_scale'],
                    metadata=metadata,
                )
            except Exception:
                logger.warning(
                    "Snapshot: could not rebuild SpectrumManager entry for %r",
                    label, exc_info=True)
                continue
            unique_id = metadata.get('unique_id')
            if unique_id:
                spectrum_manager.id_to_label_map[unique_id] = label
                spectrum_manager.label_to_id_map[label] = unique_id

    def _load_state(self, file_path: str) -> dict:
        """
        Read and deserialise a JSON snapshot file -- gzip-compressed
        (the current format, see save_snapshot) or plain UTF-8 text (any
        snapshot saved before that change). Raises a clear error if the
        file is not a valid snapshot in either form.
        """
        not_a_snapshot_error = ValueError(
            "This file is not a valid snapshot file.\n\n"
            "Snapshot files must have the '.snapx' extension and be "
            "saved using File → Save → Snapshot.\n\n"
            f"Selected file: {os.path.basename(file_path)}"
        )

        with open(file_path, 'rb') as fh:
            raw = fh.read()

        # gzip's own magic number -- present at the start of every file
        # this codebase's current save_snapshot() writes. A file that
        # starts this way but isn't actually a valid gzip stream (rare,
        # but possible for a truncated/corrupted download) must still
        # give the same friendly message as any other unreadable file,
        # not a raw gzip.BadGzipFile/OSError.
        if raw[:2] == b'\x1f\x8b':
            try:
                raw = gzip.decompress(raw)
            except OSError:
                raise not_a_snapshot_error

        if raw[:1] != b'{':
            raise not_a_snapshot_error

        text = raw.decode('utf-8')
        state = self._from_json(text)
        return state

    def _restore_ui_state(self, main_controller, state: dict) -> None:
        ui = main_controller.view
        self._safe_set(ui, 'number_of_rows_spinBox', 'blockSignals', True)
        self._safe_set(ui, 'number_of_columns_spinBox', 'blockSignals', True)
        try:
            if 'plot_settings' in state:
                s = state['plot_settings']
                if 'grid_settings' in s:
                    main_controller.grid_settings = s['grid_settings'].copy()
                    self._safe_set(ui, 'number_of_rows_spinBox', 'setValue',
                                    s['grid_settings'].get('rows', 1))
                    self._safe_set(ui, 'number_of_columns_spinBox', 'setValue',
                                    s['grid_settings'].get('columns', 1))
                if 'plot_type' in s:
                    self._safe_set(ui, 'comboBox_plot_type_choice', 'setCurrentText', s['plot_type'])
                if 'x_scale' in s:
                    self._safe_set(ui, 'x_scale_comboBox', 'setCurrentText', s['x_scale'])
                if 'y_scale' in s:
                    self._safe_set(ui, 'y_scale_comboBox', 'setCurrentText', s['y_scale'])
                if 'use_automatic_line_colors' in s:
                    main_controller.use_automatic_line_colors = s['use_automatic_line_colors']
                    self._safe_set(ui, 'automatic_line_colors_checkBox', 'setChecked',
                                    s['use_automatic_line_colors'])
                if 'use_default_points' in s:
                    main_controller.use_default_points = s['use_default_points']
                if 'spectra_ordering' in s:
                    self._safe_set(ui, 'comboBox_spectra_ordering', 'setCurrentText',
                                    s['spectra_ordering'])
                if 'reverse_order' in s:
                    self._safe_set(ui, 'checkBox_reverse_order', 'setChecked', s['reverse_order'])

            if 'link_axes' in state:
                la = state['link_axes']
                self._safe_set(ui, 'link_x_axes_checkBox', 'setChecked', la.get('link_x', False))
                self._safe_set(ui, 'link_y_axes_checkBox', 'setChecked', la.get('link_y', False))
                self._safe_set(ui, 'comboBox_linking_x_axes', 'setCurrentText',
                                la.get('link_x_direction', 'all'))
                self._safe_set(ui, 'comboBox_linking_y_axes', 'setCurrentText',
                                la.get('link_y_direction', 'all'))

            if 'plot_properties' in state and hasattr(main_controller, 'custom_plot_properties_manager'):
                main_controller.custom_plot_properties_manager.spectrum_properties = (
                    state['plot_properties']
                )
        finally:
            self._safe_set(ui, 'number_of_rows_spinBox', 'blockSignals', False)
            self._safe_set(ui, 'number_of_columns_spinBox', 'blockSignals', False)
            # Deliberately NOT calling update_grid_layout() or plot_spectra()
            # here — this method only restores widget VALUES. load_snapshot()
            # triggers exactly one render after every piece of state (UI,
            # operations, selection) has been restored, so the grid/plot
            # isn't rebuilt multiple times over the course of one load.

    def _restore_melting_curve_saved_fits(self, main_controller, saved_fits: dict) -> None:
        """Restore Melting Curve Analysis' "Saved Fits" container (see
        _build_state's comment on why this -- unlike every other dialog's
        in-memory "last settings" cache -- is worth snapshotting: the user
        explicitly chose to keep each entry via "Save Current Fit").

        Restored in place (clear() + update() on the existing dict, never a
        reassignment) because MeltingCurveController.saved_fits is handed to
        MeltingCurveDialog BY REFERENCE (see MeltingCurveController.show_dialog);
        an already-open dialog's reference would go stale if this replaced
        the dict object instead of mutating it.

        A problem here shouldn't abort the rest of the snapshot load -- same
        defensive spirit as _restore_operations below.
        """
        try:
            if not hasattr(main_controller, 'melting_curve_controller'):
                from src.controllers.visualization_analysis.melting_curve_controller import (
                    MeltingCurveController)
                main_controller.melting_curve_controller = MeltingCurveController(main_controller)
            mcc = main_controller.melting_curve_controller
            mcc.saved_fits.clear()
            mcc.saved_fits.update(saved_fits)
        except Exception:
            logger.warning(
                "Snapshot: failed restoring Melting Curve Analysis Saved Fits",
                exc_info=True)

    def _restore_operations(self, main_controller, ops: dict) -> None:
        """
        Restore the operations-history state saved by _build_state.

        Most pieces below are restored independently and defensively, same
        spirit as _safe_get/_safe_set above: a problem with one of them
        (e.g. a malformed or hand-edited entry) shouldn't abort restoring
        the rest of the operations history, or the rest of the snapshot
        load that follows this method.

        operations_chain and active_operation_index are the one exception,
        and are restored together as a single atomic, mutually-validated
        unit instead — see the comment above that block for why.
        """
        op = main_controller.operations_controller
        if not hasattr(op, 'operations_manager'):
            return
        mgr = op.operations_manager

        # 'original_spectra' (the pre-operations baseline) is only present
        # in ops when it actually differed from the top-level
        # original_spectra at save time (see _build_state's dedupe) — when
        # it's missing, the two were identical, so the original_spectra
        # just restored onto main_controller a moment ago IS that baseline.
        try:
            mgr.original_spectra = ops.get('original_spectra', main_controller.original_spectra)
        except Exception:
            logger.warning(
                "Snapshot: failed restoring operations baseline "
                "(original_spectra)", exc_info=True)

        # operations_chain and active_operation_index are a PAIR — every
        # consumer of the operations history (starting with
        # IncrementalOperationsManager.get_current_spectra(), which does a
        # direct self.operations_chain[self.active_operation_index] lookup
        # with no bounds check) trusts that active_operation_index is
        # always a valid position in operations_chain, or -1. Restoring
        # them as two independent try/except blocks — as this used to do —
        # could let one succeed while the other fails (or one key is
        # simply missing from a hand-edited snapshot), leaving a mismatched
        # pair that doesn't raise here, but later: as an IndexError the
        # next time the user opens History, jumps to a step, or applies a
        # new operation — disconnected in time from the load that actually
        # caused it. So both are computed first, validated together, and
        # only then assigned together. If anything about that fails, BOTH
        # fall back to a guaranteed-consistent empty state (no chain,
        # "Original State") instead of leaving one half updated and the
        # other stale.
        new_chain = ops.get('operations_chain', mgr.operations_chain)
        new_index = ops.get('active_operation_index', mgr.active_operation_index)

        # Backfill any entry whose output_spectra was omitted at save
        # time because it was identical to the top-level original_spectra
        # (see _build_state's dedupe) -- BEFORE the validation below ever
        # sees it, so that validation keeps seeing exactly what it always
        # has: either a real list, or something genuinely malformed that
        # it should reset. This never touches a live, in-memory chain
        # entry (only ops.get('operations_chain', ...)'s JSON-decoded
        # fallback would reach this, and a live entry never carries the
        # 'output_spectra_omitted' key in the first place). A backfill
        # failure is deliberately not special-cased: it just leaves that
        # one entry without a usable output_spectra, which the validation
        # immediately below already treats as malformed.
        if isinstance(new_chain, list):
            for entry in new_chain:
                if isinstance(entry, dict) and entry.get('output_spectra_omitted'):
                    try:
                        entry['output_spectra'] = self._deep_copy_spectra_list(
                            main_controller.original_spectra)
                        # Clear the flag now that output_spectra is a
                        # real list again -- if this snapshot gets
                        # re-saved later and THIS entry is no longer the
                        # one matching the (by-then-different) current
                        # state, a stale flag left behind here would
                        # make a FUTURE load overwrite this entry's own,
                        # by-then-legitimately-different output_spectra
                        # with whatever original_spectra happens to be
                        # at that later load -- silently corrupting a
                        # step in the operations history. _build_state
                        # always re-derives this flag fresh from actual
                        # content on every save, never from a leftover
                        # flag, so it isn't needed once backfilled.
                        del entry['output_spectra_omitted']
                    except Exception:
                        logger.warning(
                            "Snapshot: failed to backfill a deduped "
                            "operations_chain entry's output_spectra",
                            exc_info=True)

        try:
            if not isinstance(new_chain, list):
                raise TypeError(
                    f"operations_chain must be a list, got "
                    f"{type(new_chain).__name__}")
            # Beyond the chain/index pairing itself, several consumers
            # index directly into one entry's fields with no .get()
            # fallback -- IncrementalOperationsManager.set_active_operation()
            # reads operation['type'], get_operation_description() reads
            # operation['type']/['parameters'], and
            # OperationsSummaryDialog reads operation['affected_labels']
            # in a couple of places. A malformed entry there wouldn't be
            # caught by the chain/index range check above, but would
            # raise a KeyError the next time History tries to describe or
            # jump to that step -- same disconnected-in-time failure mode
            # as the chain/index mismatch, just one level deeper. So each
            # entry's minimal required shape is checked here too.
            for i, entry in enumerate(new_chain):
                if not isinstance(entry, dict):
                    raise TypeError(
                        f"operations_chain[{i}] must be a dict, got "
                        f"{type(entry).__name__}")
                if 'type' not in entry:
                    raise ValueError(f"operations_chain[{i}] is missing 'type'")
                if not isinstance(entry.get('parameters'), dict):
                    raise TypeError(
                        f"operations_chain[{i}]['parameters'] must be a "
                        f"dict, got {type(entry.get('parameters')).__name__}")
                if not isinstance(entry.get('output_spectra'), list):
                    raise TypeError(
                        f"operations_chain[{i}]['output_spectra'] must be "
                        f"a list, got "
                        f"{type(entry.get('output_spectra')).__name__}")
                if not isinstance(entry.get('affected_labels'), list):
                    raise TypeError(
                        f"operations_chain[{i}]['affected_labels'] must be "
                        f"a list, got "
                        f"{type(entry.get('affected_labels')).__name__}")
            if not isinstance(new_index, int) or isinstance(new_index, bool):
                raise TypeError(
                    f"active_operation_index must be an int, got "
                    f"{type(new_index).__name__}")
            if not (-1 <= new_index < len(new_chain)):
                raise ValueError(
                    f"active_operation_index {new_index} out of range for "
                    f"operations_chain of length {len(new_chain)}")
            mgr.operations_chain = new_chain
            mgr.active_operation_index = new_index
        except Exception:
            logger.warning(
                "Snapshot: operations_chain/active_operation_index were "
                "missing, malformed, or mutually inconsistent — resetting "
                "operations history to empty ('Original State') instead of "
                "restoring a pair that could crash later.", exc_info=True)
            # This reset is itself not guaranteed to succeed (e.g. a
            # manager whose active_operation_index setter always raises,
            # for whatever reason) -- if it fails too, that failure must
            # not be allowed to escape _restore_operations and abort the
            # rest of the snapshot load, which is the exact fault
            # tolerance this method exists to provide. Whatever partial
            # state results is logged loudly rather than silently
            # swallowed, since it's the one case this method can't fully
            # repair on its own.
            try:
                mgr.operations_chain = []
                mgr.active_operation_index = -1
            except Exception:
                logger.error(
                    "Snapshot: could not reset operations_chain/"
                    "active_operation_index to a safe state either -- "
                    "operations history may be left inconsistent. The "
                    "History dialog or further operations may misbehave "
                    "until spectra are re-imported.", exc_info=True)

        if 'current_parameters' in ops:
            try:
                op.current_parameters = ops['current_parameters']
            except Exception:
                logger.warning(
                    "Snapshot: failed restoring current_parameters",
                    exc_info=True)
        if 'import_batches' in ops and hasattr(mgr, 'import_batches'):
            try:
                mgr.import_batches = ops['import_batches']
            except Exception:
                logger.warning(
                    "Snapshot: failed restoring import_batches",
                    exc_info=True)

    def _restore_spectrum_selection(self, main_controller, state: dict) -> None:
        if not hasattr(main_controller, 'spectra_list_widget'):
            logger.warning(
                "Snapshot: 'spectra_list_widget' not found on the "
                "controller, skipping spectrum-list restore — the UI may "
                "have changed since this snapshot was written.")
            return
        # Local import — this module is otherwise PyQt-agnostic; only this
        # one method needs to build list widget rows directly.
        from PyQt5.QtWidgets import QListWidgetItem
        from PyQt5.QtCore import Qt

        main_controller.spectra_list_widget.blockSignals(True)
        main_controller.spectrum_selector.is_batch_updating = True
        try:
            main_controller.spectra_list_widget.clear()
            for sp in main_controller.original_spectra:
                item = QListWidgetItem(sp['label'])
                # Identity, not just display text — every other rebuild of
                # this widget tags Qt.UserRole with the spectrum's
                # unique_id (see developer_guide_help.py's "Golden Rule:
                # Spectrum Identity"); restoring a saved session is no
                # exception, or selection/rename tracking silently breaks
                # for the whole list until some other full rebuild happens.
                item.setData(Qt.UserRole, spectrum_id(sp))
                main_controller.spectra_list_widget.addItem(item)
            if 'selected_indices' in state:
                main_controller.spectrum_selector.selected_indices = set(state['selected_indices'])
                for idx in state['selected_indices']:
                    if idx < main_controller.spectra_list_widget.count():
                        main_controller.spectra_list_widget.item(idx).setSelected(True)
            main_controller.spectrum_selector.update_spectra_count_label()
        finally:
            main_controller.spectra_list_widget.blockSignals(False)
            main_controller.spectrum_selector.is_batch_updating = False

        # Make the spectrum-selection panel visible now, as soon as the
        # list actually has real content -- not after stage 6's plot
        # render, and not after the "Snapshot Loaded" confirmation dialog.
        # ImportController.import_snapshot() used to be the only place
        # that showed this panel, right at the very end of the whole
        # load. On a fresh app session the panel starts hidden (see
        # main_controller's own setup), so the very first time it's ever
        # shown, Qt pays a one-time layout/paint cost -- leaving that cost
        # to land after the render made a large snapshot look "frozen
        # twice": once for the render itself, then again for the panel to
        # pop in afterwards. Showing it here instead, right after this
        # stage populates the list, means that one-time cost lands while
        # the progress dialog is still up (already covering the render
        # that's about to happen), not stacked visibly on top of it.
        # Best-effort: a display quirk here must never abort an otherwise
        # successful load.
        try:
            main_controller.view.spectrum_selection_frame.setVisible(True)
        except Exception:
            logger.warning(
                "Snapshot: failed to show the spectrum selection panel",
                exc_info=True)


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------

def _pad(arr: np.ndarray, length: int) -> np.ndarray:
    """Return arr padded with NaN to *length*, or arr unchanged if already long enough."""
    if len(arr) >= length:
        return arr
    padded = np.full(length, np.nan)
    padded[:len(arr)] = arr
    return padded


import re   # needed by _safe_filename – import at module level

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)
