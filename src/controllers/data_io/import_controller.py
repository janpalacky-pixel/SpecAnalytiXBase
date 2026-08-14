# src/controllers/data_io/import_controller.py

from PyQt5.QtWidgets import QMessageBox, QFileDialog, QProgressDialog, QApplication
from PyQt5.QtCore import pyqtSignal, QObject, Qt
from src.modules.core.spectrum_manager import SpectrumManager
from src.views.dialogs.misc.import_dialog import ImportDialog
from typing import Optional
import os

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)


class ImportController(QObject):
    """Controller for importing spectrum data in standard and interlaced formats."""

    spectra_imported = pyqtSignal()
    # NOT pyqtSignal(list): PyQt marshals a typed pyqtSignal(list) argument
    # through Qt's C++ container types, and a nested Python dict inside it
    # gets converted to QVariantMap — a QMap, which Qt always keeps SORTED
    # BY KEY. That silently alphabetized every spectrum's metadata dict
    # (and nested import_parameters/duplicate_x_merge dicts) on every
    # "Add spectra" import, the only place in the app that sends spectrum
    # data through a typed signal rather than reading it directly.
    # pyqtSignal(object) instead tells PyQt to treat the payload as an
    # opaque Python object — no conversion, no reordering; the exact same
    # list/dict objects come out the other side. Confirmed directly: with
    # pyqtSignal(list) a dict's key order changes across the emit/receive
    # boundary; with pyqtSignal(object) it doesn't.
    spectra_added    = pyqtSignal(object)
    spectra_cleared  = pyqtSignal()

    def __init__(self, view, main_controller=None):
        super().__init__()
        self.view             = view
        self.main_controller  = main_controller
        self.spectrum_manager = SpectrumManager()
        self.setup_import_snapshot_action()
        self.setup_drag_drop_import()

    def setup_import_snapshot_action(self):
        if hasattr(self.view, 'actionImport_Snapshot'):
            self.view.actionImport_Snapshot.triggered.connect(self.import_snapshot)

    def setup_drag_drop_import(self):
        if hasattr(self.view, 'files_dropped'):
            self.view.files_dropped.connect(self._handle_dropped_files)

    def _handle_dropped_files(self, file_paths: list) -> None:
        """
        Files dragged onto the main window.

        Previously this ALWAYS added (never replaced), because silently
        discarding loaded spectra on a passive drag gesture would be awful.
        But that meant drag-and-drop was the only import route with no way to
        replace — the Add/New choice lives in the File menu, upstream of the
        Import dialog, so any import that doesn't come through that menu
        (drag-drop, and the Test-datasets menu) couldn't express it.

        Now the choice is asked explicitly, right before the Import dialog, but
        only when it actually matters (i.e. when spectra are already loaded —
        otherwise Add and New are the same thing and a prompt is just noise).
        Nothing is ever discarded without the user saying so.
        """
        clear_first = self._ask_add_or_replace('the dropped file(s)')
        if clear_first is None:
            return   # cancelled
        self._run_import(clear_first=clear_first, file_paths=file_paths)

    def _ask_add_or_replace(self, what: str = 'this data'):
        """
        Ask whether to ADD to the currently loaded spectra or REPLACE them.

        Returns True (replace), False (add), or None (cancelled).

        Skipped entirely — returning False (add) — when nothing is loaded yet,
        since Add and Replace are then identical and asking would be pure
        friction. Add is the default and the safe answer: it can't destroy
        anything.
        """
        if not self.spectrum_manager.spectra:
            return False

        n = len(self.spectrum_manager.spectra)
        box = QMessageBox(self.view)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle('Import data')
        box.setText(f'You already have {n} spectr{"um" if n == 1 else "a"} loaded.')
        box.setInformativeText(
            f'How should {what} be imported?\n\n'
            '• Add — keep the existing spectra and add the new ones alongside.\n'
            '• Replace all — discard the existing spectra first.'
        )
        add_btn     = box.addButton('Add', QMessageBox.AcceptRole)
        replace_btn = box.addButton('Replace all', QMessageBox.DestructiveRole)
        cancel_btn  = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(add_btn)      # safe default: never destroys data
        box.exec_()

        clicked = box.clickedButton()
        if clicked is cancel_btn:
            return None
        return clicked is replace_btn

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def _get_settings(self) -> dict:
        if hasattr(self.main_controller, 'import_settings'):
            return self.main_controller.import_settings
        return {}

    def _update_settings(self, settings: dict) -> None:
        if hasattr(self.main_controller, 'import_settings'):
            persistent = {k: v for k, v in settings.items()
                          if k not in ('interlaced_format', 'row_oriented',
                                       'label_column', 'x_scale_column',
                                       'exclude_columns', 'sheet_name',
                                       'sheet_names', 'header_row',
                                       'index_x', 'sheet_settings')}
            self.main_controller.import_settings.update(persistent)

    def _reset_non_persistent_settings(self) -> None:
        if hasattr(self.main_controller, 'import_settings_controller'):
            self.main_controller.import_settings_controller.reset_after_import()

    # ------------------------------------------------------------------
    # Shared import pipeline
    # ------------------------------------------------------------------

    def _run_import(self, *, clear_first: bool, file_paths: Optional[list] = None) -> None:
        accepted, file_paths, settings_list = ImportDialog.run(
            self.view, self._get_settings(), file_paths=file_paths
        )
        if not accepted or not file_paths:
            return

        # Persist session defaults (delimiter/decimal/header_threshold)
        # from the LAST file's settings — a reasonable, predictable choice
        # for "what should the next import start from" when different
        # files in this batch may have used different settings. Per-file
        # layout/label/x-scale/exclude choices are never persisted
        # regardless of which file supplies them — see _update_settings.
        if settings_list:
            self._update_settings(settings_list[-1])
        logger.debug("Using per-file import settings: %s", settings_list)

        # Import into a SCRATCH manager when replacing ("Import New"),
        # rather than clearing the live one up front. Previously,
        # clear_spectra() ran unconditionally before parsing even started
        # — if every file then failed (e.g. wrong Layout selected), the
        # user was left with an empty app, having lost spectra that were
        # already successfully loaded. Now the existing spectra are only
        # ever touched once we know at least one new file succeeded.
        # "Add spectra" was never affected by this — it only ever adds
        # alongside the existing set, never clears anything.
        work_manager = SpectrumManager() if clear_first else self.spectrum_manager
        initial_labels = set() if clear_first else set(self.spectrum_manager.spectra.keys())
        n_files = len(file_paths)

        # --- progress dialog -----------------------------------------------
        progress = QProgressDialog(self.view)
        progress.setWindowTitle("Importing")
        progress.setCancelButtonText("Cancel")
        progress.setRange(0, n_files)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)   # show immediately

        # Force the dialog to appear and paint before any parsing begins
        progress.setValue(0)
        progress.setLabelText(f"Starting import of {n_files} file{'s' if n_files > 1 else ''}…")
        QApplication.processEvents()

        successful_imports: list = []
        failed_imports:     list = []

        # --- file loop -----------------------------------------------------
        for i, (file_path, settings) in enumerate(zip(file_paths, settings_list)):
            if progress.wasCanceled():
                logger.debug("Import cancelled by user after %d file(s)", i)
                break

            short_name = os.path.basename(file_path)
            progress.setLabelText(
                f"Parsing file {i + 1} of {n_files}:\n{short_name}"
            )
            QApplication.processEvents()

            try:
                # Multi-sheet Excel import. 'sheet_names' is only set when the
                # user ticked "Import several sheets"; otherwise this is a
                # one-element list holding the single chosen sheet (or None,
                # meaning auto-select), so the single-sheet path is completely
                # unchanged.
                sheets = settings.get('sheet_names') or [settings.get('sheet_name')]
                multi = len(sheets) > 1
                # Each sheet carries its OWN settings when several are imported
                # at once (different sheets are usually different tables — a
                # different layout, different columns to exclude, a different
                # header row). Falls back to the shared settings for a single
                # sheet, so nothing changes for the ordinary case.
                per_sheet = settings.get('sheet_settings') or {}

                for sheet in sheets:
                    cfg = per_sheet.get(sheet, settings)
                    before = set(work_manager.spectra.keys())
                    work_manager.load_spectrum_from_file(
                        file_path,
                        delimiter         = cfg.get('delimiter'),
                        decimal_separator = cfg.get('decimal_separator'),
                        header            = cfg.get('header'),
                        zero_padding      = cfg.get('zero_padding', 4),
                        analyze_rows      = cfg.get('analyze_rows', 20),
                        interlaced_format = cfg.get('interlaced_format', False),
                        row_oriented      = cfg.get('row_oriented', False),
                        header_threshold  = cfg.get('header_threshold', 0.5),
                        label_column      = cfg.get('label_column'),
                        x_scale_column    = cfg.get('x_scale_column'),
                        exclude_columns   = cfg.get('exclude_columns'),
                        sheet_name        = sheet,
                        header_row        = cfg.get('header_row'),
                        index_x           = cfg.get('index_x', False),
                        spe_use_calibration = cfg.get('spe_use_calibration', False),
                        jws_selected_channels = cfg.get('jws_selected_channels'),
                        jws_channel_type_overrides = cfg.get('jws_channel_type_overrides'),
                    )
                    if multi:
                        # Labels are built as "<file> : <column>", so two sheets
                        # with the same column names would collide — and because
                        # spectra are stored in a dict keyed by label, the second
                        # sheet would SILENTLY OVERWRITE the first. Fold the sheet
                        # name in ("<file> [<sheet>] : <column>") right after each
                        # sheet is read, before the next one can clash with it.
                        self._tag_labels_with_sheet(work_manager, before, sheet)

                successful_imports.append(file_path)
            except Exception as e:
                logger.exception("Failed to import %r:", file_path)
                failed_imports.append((file_path, str(e)))

            # Advance the bar after the file is done
            progress.setValue(i + 1)
            QApplication.processEvents()

        # Explicitly close and release the dialog rather than relying on
        # garbage collection to get to it eventually — on Windows, a
        # QProgressDialog that showed and hid very quickly (small/fast
        # imports) can otherwise leave a stale cached bitmap behind that
        # only repaints away once something else forces a redraw (e.g.
        # refocusing the app from the taskbar). Harmless, but untidy.
        progress.close()
        progress.deleteLater()
        QApplication.processEvents()

        # --- commit results --------------------------------------------------
        if clear_first:
            if successful_imports:
                # Only now — with at least one new spectrum actually in
                # hand — replace the live data. Keep the same
                # spectrum_manager object identity rather than
                # reassigning self.spectrum_manager, since other parts of
                # the app may hold a direct reference to this instance.
                self.spectrum_manager.spectra          = work_manager.spectra
                self.spectrum_manager.id_to_label_map  = work_manager.id_to_label_map
                self.spectrum_manager.label_to_id_map  = work_manager.label_to_id_map
                self._reset_non_persistent_settings()
                self._show_import_feedback(successful_imports, failed_imports)
                self.spectra_cleared.emit()
                self.spectra_imported.emit()
            else:
                # Nothing succeeded — existing spectra are left completely
                # untouched.
                self._reset_non_persistent_settings()
                self._show_import_feedback(successful_imports, failed_imports)
        else:
            self._reset_non_persistent_settings()
            self._show_import_feedback(successful_imports, failed_imports)
            added_spectra = []
            final_labels  = set(self.spectrum_manager.spectra.keys())
            for label in final_labels - initial_labels:
                spectrum = self.spectrum_manager.spectra[label]
                added_spectra.append({
                    'label':    label,
                    'x_scale':  spectrum.x_scale,
                    'y_scale':  spectrum.y_scale,
                    'metadata': spectrum.metadata,
                })
            if added_spectra:
                self.spectra_added.emit(added_spectra)


    @staticmethod
    def _tag_labels_with_sheet(manager, labels_before: set, sheet: str) -> None:
        """Rename the spectra just added from *sheet* so their labels carry the
        sheet name, keeping sheets from overwriting one another.

        "<file> : <column>"  ->  "<file> [<sheet>] : <column>"

        A numeric suffix is appended in the (unlikely) event that even the
        tagged name is already taken, so a rename can never quietly clobber an
        existing spectrum.
        """
        if not sheet:
            return
        new_labels = [lbl for lbl in manager.spectra.keys() if lbl not in labels_before]
        for old_label in new_labels:
            if ' : ' in old_label:
                base, rest = old_label.split(' : ', 1)
                candidate = f"{base} [{sheet}] : {rest}"
            else:
                candidate = f"{old_label} [{sheet}]"
            if candidate == old_label:
                continue
            unique, n = candidate, 2
            while unique in manager.spectra:
                unique = f"{candidate} ({n})"
                n += 1
            manager.rename_spectrum(old_label, unique)

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def execute(self) -> None:
        """Import new spectra (replaces any existing spectra)."""
        self._run_import(clear_first=True)

    def execute_paths(self, file_paths: list) -> None:
        """
        Import specific files chosen somewhere other than the File menu — the
        Test-datasets menu, currently. Asks Add-or-Replace first (see
        _ask_add_or_replace), so these routes get exactly the same choice the
        File → Import data → add / new menu gives, without duplicating that
        choice inside the Import dialog itself.
        """
        clear_first = self._ask_add_or_replace('the selected dataset')
        if clear_first is None:
            return
        self._run_import(clear_first=clear_first, file_paths=file_paths)

    def execute_add(self) -> None:
        """Add spectra to the existing set."""
        self._run_import(clear_first=False)

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def clear_spectra(self) -> None:
        """Clear all spectra after user confirmation."""
        confirm = QMessageBox.question(
            self.view, "Confirm Clear",
            "Are you sure you want to clear all spectra? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.spectrum_manager.clear_spectra()
            self.spectra_cleared.emit()

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def import_snapshot(self) -> None:
        """Import an application snapshot (.snapx) file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.view, "Import Application Snapshot", "",
            "Snapshot Files (*.snapx);;All Files (*.*)"
        )

        if file_path and self.main_controller:
            try:
                self.main_controller.save_controller.load_snapshot(file_path)
                self.main_controller.view.spectrum_selection_frame.setVisible(True)

                from PyQt5.QtCore import QCoreApplication
                QCoreApplication.processEvents()

                if bool(self.main_controller.selected_spectra):
                    self.main_controller.clear_graphics_view()
                    self.main_controller.plot_spectra()

            except Exception as e:
                logger.exception("Traceback:")
                QMessageBox.critical(self.view, "Error Loading Snapshot", f"Failed: {str(e)}")
        elif not self.main_controller:
            QMessageBox.critical(self.view, "Error", "Main controller not found")

    # ------------------------------------------------------------------
    # Feedback dialog
    # ------------------------------------------------------------------

    def _show_import_feedback(self, successful_imports: list, failed_imports: list) -> None:
        parts = []

        if successful_imports:
            total_spectra = sum(
                1 for sp in self.spectrum_manager.spectra.values()
                if sp.metadata.get('file_path') in successful_imports
            )

            combos: dict = {}
            for sp in self.spectrum_manager.spectra.values():
                fp = sp.metadata.get('file_path')
                if fp not in successful_imports:
                    continue
                params  = sp.metadata.get('import_parameters', {})
                delim   = params.get('delimiter', '?')
                if delim == '\t':
                    delim = 'tab'
                elif delim == r'\s+':
                    delim = 'space'
                decimal = params.get('decimal_separator', '?')
                header  = 'header' if params.get('has_header') else 'no header'
                if params.get('row_oriented'):
                    fmt = 'row-oriented'
                elif params.get('interlaced_format'):
                    fmt = 'interlaced'
                else:
                    fmt = 'standard'
                key     = f"decimal={decimal}, delimiter={delim}, {header}, {fmt}"
                combos[key] = combos.get(key, 0) + 1

            n_files = len(successful_imports)
            parts.append(
                f"✅  {n_files} file{'s' if n_files > 1 else ''} imported  —  "
                f"{total_spectra} spectra created."
            )

            if combos:
                det_lines = [f"   {k}" for k in combos]
                parts.append("Detection:\n" + "\n".join(det_lines))

            # Duplicate-x merges (SpectrumManager._merge_duplicate_x) were
            # previously only visible in the log file, which most users
            # never open — so this could silently happen with no on-screen
            # trace at all. Surfaced here, in the same dialog every import
            # already produces, rather than a separate popup.
            dup_merged = [
                sp for sp in self.spectrum_manager.spectra.values()
                if sp.metadata.get('file_path') in successful_imports
                and 'duplicate_x_merge' in sp.metadata
            ]
            if dup_merged:
                n_spectra = len(dup_merged)
                n_points  = sum(sp.metadata['duplicate_x_merge']['n_merged'] for sp in dup_merged)
                spectrum_word = 'spectrum' if n_spectra == 1 else 'spectra'
                point_word    = 'point' if n_points == 1 else 'points'
                parts.append(
                    f"⚠️  {n_spectra} {spectrum_word} had duplicate x-values "
                    f"merged ({n_points} {point_word} averaged away). If a "
                    f"repeated x is real data for you (e.g. a forward/reverse "
                    f"sweep), the pre-merge points are kept in that spectrum's "
                    f"Metadata under 'duplicate_x_merge'."
                )

        if failed_imports:
            n_fail = len(failed_imports)
            parts.append(f"❌  {n_fail} file{'s' if n_fail > 1 else ''} failed:")
            for path, error in failed_imports:
                short = error[:280] + "…" if len(error) > 280 else error
                parts.append(f"   • {os.path.basename(path)}:\n     {short}")

        if parts:
            QMessageBox.information(
                self.view,
                "Import Results",
                "\n\n".join(parts)
            )
