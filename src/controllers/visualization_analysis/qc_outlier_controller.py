# src/controllers/visualization_analysis/qc_outlier_controller.py

from PyQt5.QtWidgets import QMessageBox
from src.modules.visualization_analysis.qc_outlier_manager import QCOutlierManager
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

    def run_qc_outlier_analysis(self):
        if not self.main_controller.selected_spectra:
            QMessageBox.warning(
                self.main_controller.view, "No Spectra Selected",
                "Please select the batch of spectra to check."
            )
            return

        if len(self.main_controller.selected_spectra) < 5:
            QMessageBox.warning(
                self.main_controller.view, "Insufficient Spectra",
                "Please select at least 5 spectra — QC/Outlier Detection "
                "compares each spectrum against the rest of the batch, so "
                "there needs to be a real 'batch' for anything to look "
                "unusual against."
            )
            return

        # PCA is fitted on the whole stack of y_scale values at once (no
        # per-spectrum interpolation) — same shared requirement as PLS /
        # Cluster Analysis / Kinetics Fitting.
        if not validate_common_x_axis(self.main_controller.selected_spectra,
                                       self.main_controller.view, 'QC / Outlier Detection'):
            return

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
