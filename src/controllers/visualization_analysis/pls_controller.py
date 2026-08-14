# src/controllers/visualization_analysis/pls_controller.py

from PyQt5.QtWidgets import QMessageBox
from src.modules.visualization_analysis.pls_manager import PLSManager
from src.modules.utils.spectra_validation import validate_common_x_axis


class PLSController:
    """Controller for PLS regression / PLS-DA — mirrors
    ClusterAnalysisController's shape: thin, owns the manager, validates
    the selection before opening the dialog."""

    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.manager = PLSManager()
        self.dialog = None

    def run_pls_analysis(self):
        if not self.main_controller.selected_spectra:
            QMessageBox.warning(
                self.main_controller.view, "No Spectra Selected",
                "Please select spectra to build a PLS / PLS-DA model."
            )
            return

        if len(self.main_controller.selected_spectra) < 2:
            QMessageBox.warning(
                self.main_controller.view, "Insufficient Spectra",
                "Please select at least 2 spectra (a real calibration model needs "
                "several more than that — see Help)."
            )
            return

        # PLS stacks every selected spectrum into one matrix, exactly
        # like Cluster Analysis / SVD / Isosbestic Point Detection — same
        # shared, tolerance-aware check.
        if not validate_common_x_axis(self.main_controller.selected_spectra,
                                       self.main_controller.view, 'PLS / PLS-DA'):
            return

        from src.views.dialogs.visualization_analysis.pls_dialog import PLSDialog
        self.dialog = PLSDialog(
            parent=self.main_controller.view,
            controller=self,
            spectra=self.main_controller.selected_spectra,
        )
        self.dialog.exec_()

    def compute_pls(self, spectra, y_by_key, mode, n_components=None,
                     autoscale_x=True, cv_folds=None, progress_callback=None):
        return self.manager.compute_pls(
            spectra, y_by_key, mode=mode, n_components=n_components,
            autoscale_x=autoscale_x, cv_folds=cv_folds, progress_callback=progress_callback,
        )
