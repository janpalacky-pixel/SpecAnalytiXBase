# src/controllers/misc/save_spectra_controller.py

from PyQt5.QtWidgets import QFileDialog, QDialog, QMessageBox, QProgressDialog, QApplication, QPushButton
from PyQt5.QtCore import Qt
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
        # Built as a QMessageBox instance (rather than the plain
        # QMessageBox.question() convenience call this used to be) so a
        # small "?" info button can be added to it -- same orange,
        # context-help convention used elsewhere in the app (e.g.
        # SpectraSelectionDialog's "About Select Spectra" button).
        # Import Snapshot has no dialog of its own to hang this on (it
        # goes straight from the File menu to a native file picker), so
        # this confirmation -- the one moment before the action actually
        # happens -- is the natural place for it.
        msg_box = QMessageBox(self.controller.view)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("Load Snapshot")
        msg_box.setText("Loading a snapshot will replace your current workspace. Continue?")
        yes_button = msg_box.addButton(QMessageBox.Yes)
        msg_box.addButton(QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)

        help_button = QPushButton('?')
        help_button.setFixedSize(24, 24)
        help_button.setStyleSheet(
            'QPushButton { background-color:#F57C00; color:white; '
            'font-weight:bold; border:none; border-radius:4px; }'
            'QPushButton:hover { background-color:#EF6C00; }')
        help_button.setToolTip('About Import Snapshot')
        msg_box.addButton(help_button, QMessageBox.HelpRole)

        # QMessageBox closes on ANY of its buttons being clicked, whatever
        # that button's role -- HelpRole does NOT exempt it from this (an
        # earlier version of this method assumed it did, based on reading
        # Qt's docs rather than actually running this dialog; it doesn't --
        # clicking "?" was closing this whole confirmation instead of just
        # showing the info, taking the still-unanswered Yes/No question
        # down with it). So instead of trying to keep this QMessageBox
        # open while one of its own buttons is clicked, treat a "help"
        # click as "show the info, then ask the same Yes/No question
        # again" -- re-executing the same QMessageBox instance is safe to
        # do any number of times.
        while True:
            msg_box.exec_()
            clicked_button = msg_box.clickedButton()
            if clicked_button is help_button:
                QMessageBox.information(
                    self.controller.view, "About Import Snapshot",
                    "A snapshot (.snapx file) is a full save of this "
                    "application's workspace: every spectrum, your whole "
                    "Operations History (including which step is currently "
                    "active), your current spectrum selection, and plot/UI "
                    "settings.\n\n"
                    "Loading one replaces everything currently open -- spectra, "
                    "history, and settings -- with what's stored in the file. "
                    "This can't be undone, so make sure anything you want to "
                    "keep from the current workspace is saved first.")
                continue
            break

        if clicked_button != yes_button:
            return False

        # Deliberately NOT clearing the plot/spectrum list here. An
        # earlier version did, right at this point, specifically so a
        # slow load wouldn't leave the OLD workspace visible while it
        # ran underneath -- but clearing spectra_list_widget turned out
        # to have a real side effect: emptying it fires
        # itemSelectionChanged (nothing is selected once every item is
        # gone), and SpectrumSelectorController's own handler for that
        # signal immediately overwrites main_controller.selected_spectra
        # with an empty list in response -- see
        # SpectrumSelectorController.on_item_selection_changed(). If the
        # load then failed before ever restoring a real selection, there
        # was no selection left to show back: the previous attempt at
        # recovering the view on failure could only ever display 0
        # spectra selected, even though the load itself never actually
        # touched that data.
        #
        # Leaving the old workspace exactly as it is until the load
        # actually succeeds avoids that failure mode entirely, and
        # matches how a regular data import already behaves (File ->
        # Import data -> new only replaces the existing spectra once at
        # least one new file has loaded -- see
        # ImportController._run_import): nothing is ever touched or
        # removed until there is something real to replace it with.
        # SaveManager.load_snapshot() below still replaces everything
        # uniformly, in one place, exactly once, whether or not anything
        # was cleared first -- so a successful load looks identical
        # either way. The confirmation above already told the user their
        # workspace is about to be replaced, so the old data staying on
        # screen under the progress dialog for a moment is expected, not
        # a sign that anything is stuck.

        # A staged progress dialog, same QProgressDialog +
        # QApplication.processEvents() pattern ImportController._run_import
        # already uses for the same reason: without pumping events, a slow
        # load (parsing + restoring a large snapshot) leaves the window
        # reporting "Not Responding" to the OS, with no indication
        # anything is actually happening.
        progress = QProgressDialog(self.controller.view)
        progress.setWindowTitle("Loading Snapshot")
        progress.setCancelButton(None)  # restoring isn't safely interruptible partway through
        # One step PAST LOAD_SNAPSHOT_STAGE_COUNT, not up to it. Stage
        # LOAD_SNAPSHOT_STAGE_COUNT ("Rendering plot...") is reported the
        # same way every other stage is: right BEFORE that stage's own
        # (potentially slow) work runs, not after. If this dialog's
        # range topped out exactly at that stage number, the bar would
        # sit at a literal 100% for however long the render actually
        # took -- looking stuck, not in progress. The true maximum is
        # only reached below, once load_snapshot() has actually returned.
        progress.setRange(0, SaveManager.LOAD_SNAPSHOT_STAGE_COUNT + 1)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)  # show immediately, even for a fast load
        # QProgressDialog auto-closes itself (via an internal reset()) the
        # instant setValue() is called with the dialog's maximum. Left at
        # the Qt default (True/True) this would fight the one-step-past
        # range above (and everything else below) -- this method already
        # closes the dialog explicitly on every exit path, so the
        # automatic behaviour is not needed here, only harmful.
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setLabelText("Reading snapshot file…")
        progress.setValue(0)
        QApplication.processEvents()

        def _report_progress(stage, label):
            progress.setValue(stage)
            progress.setLabelText(label)
            QApplication.processEvents()

        try:
            # save_manager.load_snapshot() only ever returns True or raises
            # RuntimeError (caught below) — it never returns False — and it
            # already restores AND renders the full state itself before
            # returning, so there's nothing left to do here on success beyond
            # confirming it to the user.
            self.save_manager.load_snapshot(
                self.controller, file_path, progress_callback=_report_progress
            )
        except RuntimeError as e:
            progress.close()
            QMessageBox.critical(
                self.controller.view,
                "Error Loading Snapshot",
                str(e)
            )
            return False

        # Only now, with the load actually finished, does the bar reach
        # its true 100% -- see the comment on setRange() above.
        progress.setValue(SaveManager.LOAD_SNAPSHOT_STAGE_COUNT + 1)
        # One more pump before the modal "Snapshot Loaded" box below: a
        # large Grid plot render can leave Qt with a backlog of
        # paint/layout events for the newly-built canvas that haven't
        # been serviced yet (the per-stage processEvents() calls above
        # only ran between batches of ~50 subplots each, not
        # continuously) -- flushing that backlog here means the dialog
        # that's about to appear doesn't have to fight its way through
        # it too. This does not make the render itself any faster; a
        # genuinely huge grid (thousands of subplots) is real,
        # synchronous matplotlib work, and no amount of event-pumping
        # avoids that -- it only keeps the UI able to repaint itself
        # between chunks of it.
        QApplication.processEvents()
        progress.close()
        QMessageBox.information(
            self.controller.view,
            "Snapshot Loaded",
            "Application state restored successfully."
        )
        return True
