# src/controllers/misc/save_spectra_controller.py

from PyQt5.QtWidgets import QFileDialog, QDialog, QMessageBox, QVBoxLayout, QLabel, QPushButton
from src.views.dialogs.misc.save_spectra_dialog import SaveOptionsDialog
from src.modules.misc.save_spectra_manager import SaveManager
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)

# File extension for each format
_FORMAT_EXTENSIONS = {
    'text':     ['.txt', '.csv'],   # first entry is the default
    'excel':    ['.xlsx'],
    'spc':      ['.spc'],
    'snapshot': ['.snapx'],
}

# File picker filter for each format
_FORMAT_FILTERS = {
    'text':     "Text Files (*.txt);;CSV Files (*.csv);;All Files (*.*)",
    'excel':    "Excel Files (*.xlsx);;All Files (*.*)",
    'spc':      "GRAMS Files (*.spc);;All Files (*.*)",
    'snapshot': "Snapshot Files (*.snapx);;All Files (*.*)",
}


def _ensure_extension(file_path: str, fmt: str) -> str:
    """
    Append the default extension for *fmt* if *file_path* has no extension
    or an extension not recognised for this format.
    """
    import os
    root, ext = os.path.splitext(file_path)
    expected = _FORMAT_EXTENSIONS.get(fmt, [])
    if not ext or ext.lower() not in expected:
        file_path = root + expected[0]
    return file_path


class SaveController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.save_manager = SaveManager()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def execute(self, spectra=None):
        """Execute the save operation.

        spectra: optional explicit list of spectrum dicts to save instead
        of the main window's current selection — e.g. SVD Interpolation's
        preview spectra, which aren't part of the main spectrum list (and
        may never be, if the user only wants a file, not an Add as New).
        Default behavior (spectra=None) is unchanged: saves whatever's
        currently selected in the main window, same as always.
        """
        selected_spectra = spectra if spectra is not None else self.get_selected_spectra_in_order()

        if not selected_spectra and not self.show_snapshot_option():
            QMessageBox.warning(
                self.controller.view,
                "No Selection",
                "No spectra selected to save."
            )
            return

        dialog = SaveOptionsDialog(self.controller.view, allow_snapshot=(spectra is None))
        if dialog.exec_() != QDialog.Accepted:
            return

        settings = dialog.get_settings()
        fmt = settings['format']

        if fmt == 'snapshot':
            self._save_snapshot(settings)
            return

        # show_snapshot_option() above only guards against there being NO
        # spectra anywhere in the app — it deliberately stays permissive
        # so Snapshot format remains reachable even with nothing selected
        # (a snapshot saves the whole workspace, not the selection). That
        # means a real "nothing is selected" case can still reach here
        # for Text/Excel format, where selected_spectra IS what's about
        # to be saved. Catch it here, before the file picker even opens,
        # with the same clear message — rather than letting it fall
        # through to SaveManager, which would raise a bare "No spectra to
        # save" ValueError that surfaces as a confusing Save Error dialog.
        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                "No Selection",
                "No spectra selected to save.\n\n"
                "Select spectra in the list first, or choose Snapshot "
                "format to save the whole workspace regardless of "
                "selection."
            )
            return

        if settings['mode'] == 'table':
            self._save_table(selected_spectra, settings)
        else:
            self._save_individual(selected_spectra, settings)

    # ------------------------------------------------------------------
    # Snapshot save
    # ------------------------------------------------------------------

    def _save_snapshot(self, settings: dict):
        file_path, _ = QFileDialog.getSaveFileName(
            self.controller.view,
            "Save Application Snapshot",
            "",
            _FORMAT_FILTERS['snapshot'],
        )
        if not file_path:
            return

        file_path = _ensure_extension(file_path, 'snapshot')

        success = self.save_manager.save_snapshot(self.controller, file_path)
        if success:
            QMessageBox.information(
                self.controller.view,
                "Snapshot Saved",
                f"Application state saved to:\n{file_path}"
            )
        else:
            QMessageBox.critical(
                self.controller.view,
                "Save Error",
                f"Failed to save snapshot to:\n{file_path}"
            )

    # ------------------------------------------------------------------
    # Table save
    # ------------------------------------------------------------------

    def _save_table(self, selected_spectra: list, settings: dict):
        fmt = settings['format']

        if settings['use_common_scale']:
            if not self.save_manager.validate_common_scale(selected_spectra):
                QMessageBox.warning(
                    self.controller.view,
                    "Scale Mismatch",
                    "Selected spectra have different x-scales.\n"
                    "Cannot use the common x-scale option.\n\n"
                    "Uncheck 'Use common x-scale' to save with individual x-scales."
                )
                return

        file_path, _ = QFileDialog.getSaveFileName(
            self.controller.view,
            "Save Spectra",
            "",
            _FORMAT_FILTERS[fmt],
        )
        if not file_path:
            return

        file_path = _ensure_extension(file_path, fmt)

        try:
            self.save_manager.save_table(selected_spectra, file_path, settings)
            QMessageBox.information(
                self.controller.view,
                "Save Successful",
                f"Saved {len(selected_spectra)} spectra to:\n{file_path}"
            )
        except Exception as e:
            logger.exception("Table save failed")
            QMessageBox.critical(
                self.controller.view,
                "Save Error",
                f"Failed to save spectra:\n{str(e)}"
            )

    # ------------------------------------------------------------------
    # Individual files save
    # ------------------------------------------------------------------

    def _save_individual(self, selected_spectra: list, settings: dict):
        directory = QFileDialog.getExistingDirectory(
            self.controller.view,
            "Select Directory for Individual Files"
        )
        if not directory:
            return

        try:
            saved_files = self.save_manager.save_individual(
                selected_spectra, directory, settings
            )
            QMessageBox.information(
                self.controller.view,
                "Save Successful",
                f"Saved {len(saved_files)} files to:\n{directory}"
            )
        except Exception as e:
            logger.exception("Individual save failed")
            QMessageBox.critical(
                self.controller.view,
                "Save Error",
                f"Failed to save files:\n{str(e)}"
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_selected_spectra_in_order(self) -> list:
        """Return selected spectra in the order they appear in the UI."""
        selected_indices = self.controller.spectrum_selector.selected_indices
        if not selected_indices:
            return []
        return [
            self.controller.original_spectra[i]
            for i in sorted(selected_indices)
            if 0 <= i < len(self.controller.original_spectra)
        ]

    def show_snapshot_option(self) -> bool:
        """Return True if saving is allowed even with no spectra selected."""
        if hasattr(self.controller, 'operations_controller'):
            op = self.controller.operations_controller
            if hasattr(op, 'operations_manager'):
                if len(op.operations_manager.operations_chain) > 0:
                    return True
        return bool(self.controller.original_spectra)

    def load_snapshot(self, file_path: str) -> bool:
        """Load a snapshot file and restore application state."""
        confirm = QMessageBox.question(
            self.controller.view,
            "Load Snapshot",
            "Loading a snapshot will replace your current workspace. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return False

        try:
            success = self.save_manager.load_snapshot(self.controller, file_path)
        except RuntimeError as e:
            QMessageBox.critical(
                self.controller.view,
                "Error Loading Snapshot",
                str(e)
            )
            return False

        if success:
            class _SnapshotLoadedDialog(QDialog):
                def __init__(self, parent, controller):
                    super().__init__(parent)
                    self.controller = controller
                    self.setWindowTitle("Snapshot Loaded")
                    layout = QVBoxLayout(self)
                    layout.addWidget(QLabel("Application state restored successfully."))
                    btn = QPushButton("OK")
                    btn.clicked.connect(self.accept)
                    layout.addWidget(btn)

                def closeEvent(self, event):
                    super().closeEvent(event)
                    if hasattr(self.controller, 'plot_spectra'):
                        self.controller.plot_spectra()

            _SnapshotLoadedDialog(self.controller.view, self.controller).exec_()
            return True

        return False
