# src/controllers/visualization_analysis/pca_scores_controller.py

import numpy as np
from PyQt5.QtWidgets import QMessageBox
from src.modules.visualization_analysis.pca_scores_manager import PcaScoresManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import validate_common_x_axis
logger = get_logger(__name__)


class PcaScoresController:
    """Controller for the PCA / SVD Scores & Loadings dialog. Mirrors
    SVDAnalysisController's shape — same show_dialog x-axis validation, same
    thin pass-through methods to the manager, same try/except-and-log
    wrapping around the two save methods."""

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = PcaScoresManager()
        self.dialog = None

    def compute_svd_analysis(self, spectra, n_components, mean_center=True):
        """Compute PCA/SVD from spectra. Pure computation — safe to call
        from the dialog's background QThread.

        Returns:
            bool: True if the computation succeeded.
        """
        if not spectra:
            logger.debug("DEBUG: No spectra provided to PCA/SVD analysis")
            return False
        try:
            return self.manager.compute_svd(spectra, n_components, mean_center=mean_center)
        except Exception as e:
            logger.error(f"ERROR: Exception in PCA/SVD analysis: {e}")
            logger.exception("Traceback:")
            return False

    def get_n_components(self):
        return self.manager.get_n_components()

    def get_n_datapoints(self):
        return self.manager.get_n_datapoints()

    def get_n_spectra(self):
        return self.manager.get_n_spectra()

    def hotelling_t2(self, pc_indices):
        return self.manager.hotelling_t2(pc_indices)

    def get_metric_values(self, metric_name):
        return self.manager.get_metric_values(metric_name)

    def save_results_excel(self, filepath, labels, include_scores=True,
                            include_loadings=True, include_variance=True):
        """
        Save PCA/SVD results to an Excel file.

        Returns:
            bool: True if save was successful
        """
        try:
            return self.manager.save_results_excel(
                filepath, labels, include_scores, include_loadings, include_variance)
        except Exception as e:
            logger.error(f"ERROR: Excel save failed: {e}")
            return False

    def save_results_text(self, save_config):
        """
        Save PCA/SVD results to text/CSV file(s).

        Returns:
            bool: True if save was successful
        """
        try:
            return self.manager.save_results_text(save_config)
        except Exception as e:
            logger.error(f"ERROR: Text save failed: {e}")
            return False

    def show_dialog(self):
        """Show the PCA / SVD Scores & Loadings dialog — ported from
        main_controller._show_pca_scores_dialog, which called
        PcaScoresDialog(...).exec_() directly. exec_() blocks the caller
        until the dialog closes regardless of the dialog's own setModal()
        flag (PcaScoresDialog never calls it), so despite appearances this
        dialog was already being shown modally, same as SVD Analysis and
        Cluster Analysis — kept exactly as-is here rather than switched to
        .show(), to avoid silently changing existing behavior."""
        selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                "No Spectra Selected",
                "Please select spectra before opening PCA / SVD Scores & Loadings."
            )
            return

        if len(selected_spectra) < 2:
            QMessageBox.warning(
                self.controller.view, "Insufficient Spectra",
                "PCA / SVD Scores & Loadings requires at least 2 spectra.\n"
                "Please select more spectra."
            )
            return

        # PCA/SVD stacks the spectra into one matrix, so every row must be
        # sampled at the same x. Uses the shared validator (see
        # spectra_validation) rather than a private comparison, so the message
        # and — more importantly — the float tolerance are identical to every
        # other tool. The old inline check used np.allclose's DEFAULT rtol of
        # 1e-5, which on a 1000 cm-1 axis is a tolerance of 0.01 cm-1: loose
        # enough to accept genuinely different grids as "the same".
        if not validate_common_x_axis(selected_spectra, self.controller.view,
                                      'PCA / SVD Scores & Loadings'):
            return

        # Reset previous results before opening a fresh dialog for a new
        # selection — same reasoning as ClusterAnalysisController: without
        # this, a stale result from a previous, unrelated selection could
        # still be read before the first SVD computation for this
        # selection finishes.
        self.manager.reset()

        # Only reuse the last shown settings if this dialog was last opened
        # for this exact selection — ported verbatim from
        # main_controller._show_pca_scores_dialog, which reused
        # operations_controller's current_parameters / last_op_settings /
        # last_selection_hash bookkeeping (the same place every other
        # operation's "remember on close" settings live) rather than a
        # separate cache of its own.
        oc = self.controller.operations_controller
        current_selection_hash = oc._get_selection_hash(selected_spectra)
        last_settings = {}
        if ("PCA Scores" in oc.current_parameters and
                oc.last_selection_hash == current_selection_hash):
            last_settings = oc.last_op_settings.get("PCA Scores", {}).copy()

        from src.views.dialogs.visualization_analysis.pca_scores_dialog import PcaScoresDialog
        self.dialog = PcaScoresDialog(
            parent=self.controller.view,
            controller=self,
            spectra=selected_spectra,
            current_settings=last_settings,
        )
        self.dialog.exec_()

        # Remember whatever the dialog was last showing — even if the user
        # just closed it without exporting anything — same "remember on
        # close" pattern as Data Range, Baseline Correction, and FFT
        # Denoising, so reopening for the SAME selection picks up where
        # they left off instead of resetting every time.
        settings = self.dialog.get_settings()
        if settings:
            oc.current_parameters["PCA Scores"] = settings.copy()
            oc.last_op_settings["PCA Scores"]   = settings.copy()
            oc.last_selection_hash = current_selection_hash
        self.dialog = None
