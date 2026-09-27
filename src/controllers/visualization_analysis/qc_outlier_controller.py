# src/controllers/visualization_analysis/qc_outlier_controller.py

from PyQt5.QtWidgets import QMessageBox
from src.modules.visualization_analysis.qc_outlier_manager import QCOutlierManager
from src.modules.utils.revision_tracking import selection_or_revision_changed
from src.modules.utils.spectra_validation import validate_common_x_axis


class QCOutlierController:
    """Controller for PCA-based QC / Outlier Detection — mirrors
    KineticsController's/PLSController's shape: thin, owns the manager,
    validates the selection before opening the dialog. Read-only analysis
    tool: it never adds, removes, or transforms spectral data, so there's
    no Apply/Add-as-New commit step and nothing is written to Operations
    History."""

    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.manager = QCOutlierManager()
        self.dialog = None
        # Compared against IncrementalOperationsManager.revision in
        # run_qc_outlier_analysis() below, so a reopen only forgets the
        # last result if an operation actually ran meanwhile -- see
        # revision_tracking.py. QCOutlierController previously never
        # reset self.manager at all, so a stale PCA/outlier result from a
        # completely different, previous selection could still be read
        # before this dialog's first computation for the new selection
        # finished -- the same "never forget" bug 2D Map originally had.
        self._last_seen_revision = None
        # QC/Outlier's PCA/t2/Q results are computed from the WHOLE
        # selection at once and read directly by the dialog (e.g.
        # switching tabs before anything is (re-)computed for THIS
        # selection), so a plain, unrelated selection change needs to
        # reset this too, not just an operation running -- see
        # revision_tracking.py's own docstring.
        self._last_selection_hash = None

    def validate_selection(self, spectra):
        """Cheap, purely local pre-check that there's a real "batch" to
        check -- no spectra, or fewer than 5. Split out from
        run_qc_outlier_analysis so the SAME check can be called by
        MainController.run_visualization_analysis BEFORE it sets its
        wait cursor, not just from inside here after it. Without this,
        clicking QC / Outlier Detection with too few spectra selected hit
        this warning while the caller's Qt.WaitCursor override was still
        active -- the warning box itself was correct, but it appeared
        with the spinning "busy" cursor still on screen over it, exactly
        the bug run_visualization_analysis's own comment already
        describes and fixed for a mismatched x-axis, just not for this
        selection-count check too. Returns True if the selection is
        usable, showing the appropriate warning and returning False
        otherwise -- also called defensively at the top of
        run_qc_outlier_analysis() itself, in case that is ever invoked
        directly without going through the menu dispatch."""
        if not spectra:
            QMessageBox.warning(
                self.main_controller.view, "No Spectra Selected",
                "Please select the batch of spectra to check."
            )
            return False

        if len(spectra) < 5:
            QMessageBox.warning(
                self.main_controller.view, "Insufficient Spectra",
                "Please select at least 5 spectra — QC/Outlier Detection "
                "compares each spectrum against the rest of the batch, so "
                "there needs to be a real 'batch' for anything to look "
                "unusual against."
            )
            return False

        return True

    def run_qc_outlier_analysis(self):
        if not self.validate_selection(self.main_controller.selected_spectra):
            return

        # PCA is fitted on the whole stack of y_scale values at once (no
        # per-spectrum interpolation) — same shared requirement as PLS /
        # Cluster Analysis / Kinetics Fitting.
        if not validate_common_x_axis(self.main_controller.selected_spectra,
                                       self.main_controller.view, 'QC / Outlier Detection'):
            return

        should_reset, self._last_selection_hash, self._last_seen_revision = \
            selection_or_revision_changed(
                self.main_controller, self.main_controller.selected_spectra,
                self._last_selection_hash, self._last_seen_revision)
        if should_reset:
            self.manager.reset()

        from src.views.dialogs.visualization_analysis.qc_outlier_dialog import QCOutlierDialog
        self.dialog = QCOutlierDialog(
            parent=self.main_controller.view,
            controller=self,
            spectra=self.main_controller.selected_spectra,
        )
        self.dialog.exec_()

    # ------------------------------------------------------------------ #
    # Pure computation helper (thin wrapper around the manager, kept here #
    # so the dialog stays free of algorithm details — same separation of  #
    # concerns as PLSController.compute_pls / KineticsController.fit_*).  #
    # ------------------------------------------------------------------ #

    def compute_qc(self, spectra, n_components=None, variance_threshold=0.95, alpha=0.05):
        ok = self.manager.compute(spectra, n_components=n_components,
                                  variance_threshold=variance_threshold, alpha=alpha)
        return ok, self.manager.last_error
