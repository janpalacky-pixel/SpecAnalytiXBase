# src/controllers/visualization_analysis/pca_scores_controller.py

import numpy as np
from PyQt5.QtWidgets import QMessageBox
from src.modules.visualization_analysis.pca_scores_manager import PcaScoresManager
from src.modules.utils.revision_tracking import revision_changed
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
        # Compared against IncrementalOperationsManager.revision in
        # show_dialog() below, so a reopen only forgets the last result if an
        # operation actually ran meanwhile -- see revision_tracking.py.
        self._last_seen_revision = None
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

    def compute_bootstrap_uncertainty(self, reference_manager, n_resamples,
                                       confidence_level, random_state=None,
                                       progress_callback=None,
                                       cancel_check=None):
        """Residual bootstrap for this dialog's own loadings (U) and
        scores (Vt). Direct port of SVDAnalysisController's identically-
        named method (see its docstring for the full method and the sign-
        ambiguity reasoning -- exactly the same issue applies here, for
        the same underlying reason: PCA/SVD's component sign is only
        defined up to +/-1). Simpler than that version in exactly one way:
        this manager already fixes "how many components are signal" at
        compute time (self.manager.compute_svd's own n_components,
        reference_manager.U.shape[1]) rather than needing it as a separate
        bootstrap-time choice, so there is no equivalent of
        SVDAnalysisController.suggest_bootstrap_n_components() to call
        first -- one fewer prompt than SVD Analysis's own version, exactly
        the "PCA Scores & Loadings is the easy one" case.

        reference_manager must already hold a successful fit (.U/.s/.Vt/
        .data_matrix all set, i.e. self.manager right after
        compute_svd() returned True). progress_callback(b, n_resamples),
        if given, is called before each replicate; cancel_check(), if
        given, is checked before each replicate and stops early when it
        returns True.

        Returns a dict with U_lower/U_upper/Vt_lower/Vt_upper (pointwise
        percentile bounds), U_samples/Vt_samples (raw, sign-aligned
        per-replicate arrays), n_resamples_requested/n_resamples_used/
        n_failed, and confidence_level -- or None if reference_manager
        isn't fitted yet, or every replicate failed. On success, also
        stored on reference_manager.bootstrap_result.
        """
        ref = reference_manager
        if ref.U is None or ref.s is None or ref.Vt is None or ref.data_matrix is None:
            ref.last_error = (
                "Run PCA / SVD successfully before requesting bootstrap "
                "uncertainty.")
            return None

        n_components = ref.U.shape[1]
        X0 = ref.data_matrix           # (n_wl x n_spectra), full (untruncated)
        U0, s0, Vt0 = ref.U, ref.s, ref.Vt
        n_spectra = X0.shape[1]

        recon = U0 @ np.diag(s0) @ Vt0
        residuals = X0 - recon
        rng = np.random.RandomState(random_state)

        U_samples, Vt_samples = [], []
        n_failed = 0
        first_failure_reason = None
        for b in range(n_resamples):
            if cancel_check is not None and cancel_check():
                break
            if progress_callback is not None:
                progress_callback(b, n_resamples)
            col_idx = rng.randint(0, n_spectra, size=n_spectra)
            X_b = recon + residuals[:, col_idx]
            try:
                U_b, s_b, Vt_b = np.linalg.svd(X_b, full_matrices=False)
                U_b = U_b[:, :n_components].copy()
                Vt_b = Vt_b[:n_components, :].copy()

                # Sign alignment -- see SVDAnalysisController.
                # compute_bootstrap_uncertainty's docstring for the full
                # reasoning. Tested against U0 (n_wl-length, less noisy
                # than Vt0's n_spectra-length row); U and Vt for a given
                # component always flip together.
                for j in range(n_components):
                    if np.dot(U_b[:, j], U0[:, j]) < 0:
                        U_b[:, j] *= -1
                        Vt_b[j, :] *= -1

                U_samples.append(U_b)
                Vt_samples.append(Vt_b)
            except np.linalg.LinAlgError as e:
                n_failed += 1
                if first_failure_reason is None:
                    first_failure_reason = str(e)

        if not U_samples:
            ref.last_error = (
                f"All {n_resamples} bootstrap resamples failed to fit."
                + (f"\n\nFirst failure: {first_failure_reason}"
                   if first_failure_reason else ""))
            return None

        U_arr = np.array(U_samples)
        Vt_arr = np.array(Vt_samples)
        alpha = 1.0 - confidence_level
        lo_pct, hi_pct = 100.0 * alpha / 2.0, 100.0 * (1.0 - alpha / 2.0)
        result = {
            'U_lower': np.percentile(U_arr, lo_pct, axis=0),
            'U_upper': np.percentile(U_arr, hi_pct, axis=0),
            'Vt_lower': np.percentile(Vt_arr, lo_pct, axis=0),
            'Vt_upper': np.percentile(Vt_arr, hi_pct, axis=0),
            'U_samples': U_arr,
            'Vt_samples': Vt_arr,
            'n_resamples_requested': n_resamples,
            'n_resamples_used': len(U_samples),
            'n_failed': n_failed,
            'confidence_level': confidence_level,
        }
        ref.bootstrap_result = result
        ref.last_error = None
        return result

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
        should_reset, self._last_seen_revision = revision_changed(
            self.controller, self._last_seen_revision)
        if should_reset:
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
