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
import pandas as pd
import numpy as np

from src.modules.utils.spectra_validation import axes_match
from src.modules.utils.spectrum_identity import spectrum_id
from src.modules.data_io.spc_data_writer import write_spc_data


class SaveManager:
    """Business logic for saving spectrum data."""

    def __init__(self):
        pass

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

    SNAPSHOT_VERSION = 2

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

        state = {
            'timestamp': pd.Timestamp.now().isoformat(),
            'version': self.SNAPSHOT_VERSION,
            'original_spectra': main_controller.original_spectra,
            'selected_spectra': main_controller.selected_spectra,
            'selected_indices': list(main_controller.spectrum_selector.selected_indices),
            'plot_settings': plot_settings,
            'link_axes': {
                'link_x':           self._safe_get(ui, 'link_x_axes_checkBox', 'isChecked', default=False),
                'link_y':           self._safe_get(ui, 'link_y_axes_checkBox', 'isChecked', default=False),
                'link_x_direction': self._safe_get(ui, 'comboBox_linking_x_axes', 'currentText', default='all'),
                'link_y_direction': self._safe_get(ui, 'comboBox_linking_y_axes', 'currentText', default='all'),
            },
        }

        if hasattr(main_controller, 'custom_plot_properties_manager'):
            state['plot_properties'] = (
                main_controller.custom_plot_properties_manager.spectrum_properties.copy()
            )

        if hasattr(main_controller, 'operations_controller'):
            op = main_controller.operations_controller
            if hasattr(op, 'operations_manager'):
                state['operations'] = {
                    'original_spectra': op.operations_manager.original_spectra,
                    'operations_chain': op.operations_manager.operations_chain,
                    'active_operation_index': op.operations_manager.active_operation_index,
                    'current_parameters': op.current_parameters,
                }
                if hasattr(op.operations_manager, 'import_batches'):
                    state['operations']['import_batches'] = op.operations_manager.import_batches

        return state

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

    def save_snapshot(self, main_controller, file_path: str) -> bool:
        """Save application state as a JSON snapshot file."""
        try:
            state = self._build_state(main_controller)
            json_text = self._to_json(state)

            with open(file_path, 'w', encoding='utf-8') as fh:
                fh.write(json_text)

            logger.info("Snapshot saved: %s", file_path)
            return True

        except Exception:
            logger.exception("Failed to save snapshot")
            return False

    def load_snapshot(self, main_controller, file_path: str) -> bool:
        """
        Load a snapshot file.

        Supports:
        - JSON snapshots (version 2+, written by this code)
        - Legacy pickle snapshots (version 1, written by older code)
          These are still loaded via pickle for backward compatibility.
        """
        try:
            state = self._load_state(file_path)

            # Basic sanity check
            required = {'original_spectra', 'selected_spectra'}
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

            self._restore_ui_state(main_controller, state)
            main_controller.original_spectra = state['original_spectra']
            main_controller.selected_spectra = state['selected_spectra']

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
            self._resync_spectrum_manager(main_controller, state['original_spectra'])

            if 'operations' in state and hasattr(main_controller, 'operations_controller'):
                self._restore_operations(main_controller, state['operations'])

            if hasattr(main_controller, 'spectrum_selector'):
                self._restore_spectrum_selection(main_controller, state)

            ui = main_controller.view
            plot_type = self._safe_get(ui, 'comboBox_plot_type_choice', 'currentText', default='')
            if plot_type == "Grid plot" and main_controller.selected_spectra:
                rows = main_controller.grid_settings.get('rows', 1)
                cols = main_controller.grid_settings.get('columns', 1)
                # Set to 1 first, then the real value — forces a genuine
                # change even if the restored value happens to match
                # whatever the spinbox already shows, so the grid layout
                # signal fires and the plot actually rebuilds.
                self._safe_set(ui, 'number_of_rows_spinBox', 'setValue', 1)
                self._safe_set(ui, 'number_of_columns_spinBox', 'setValue', 1)
                self._safe_set(ui, 'number_of_rows_spinBox', 'setValue', rows)
                self._safe_set(ui, 'number_of_columns_spinBox', 'setValue', cols)
                main_controller.plot_spectra()
            elif main_controller.selected_spectra:
                main_controller.plot_spectra()

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
        Read and deserialise a JSON snapshot file.
        Raises a clear error if the file is not a valid JSON snapshot.
        """
        with open(file_path, 'rb') as fh:
            magic = fh.read(1)

        if magic != b'{':
            raise ValueError(
                "This file is not a valid snapshot file.\n\n"
                "Snapshot files must have the '.snapx' extension and be "
                "saved using File → Save → Snapshot.\n\n"
                f"Selected file: {os.path.basename(file_path)}"
            )

        with open(file_path, 'r', encoding='utf-8') as fh:
            text = fh.read()

        state = self._from_json(text)
        logger.debug(
            "Loaded JSON snapshot version %s",
            state.get('version', 'unknown')
        )
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
            if 'plot_settings' in state and 'grid_settings' in state['plot_settings']:
                main_controller.update_grid_layout()

    def _restore_operations(self, main_controller, ops: dict) -> None:
        op = main_controller.operations_controller
        if not hasattr(op, 'operations_manager'):
            return
        mgr = op.operations_manager
        if 'original_spectra' in ops:
            mgr.original_spectra = ops['original_spectra']
        if 'operations_chain' in ops:
            mgr.operations_chain = ops['operations_chain']
        if 'active_operation_index' in ops:
            mgr.active_operation_index = ops['active_operation_index']
        if 'current_parameters' in ops:
            op.current_parameters = ops['current_parameters']
        if 'import_batches' in ops and hasattr(mgr, 'import_batches'):
            mgr.import_batches = ops['import_batches']

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
