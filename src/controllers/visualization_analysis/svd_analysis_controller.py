# src/controllers/visualization_analysis/svd_analysis_controller.py

import numpy as np
from src.modules.visualization_analysis.svd_analysis_manager import SVDAnalysisManager
from PyQt5.QtWidgets import QMessageBox
from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

class SVDAnalysisController:
    """Controller for SVD analysis visualization operations."""
    
    def __init__(self, main_controller):
        """
        Initialize the SVDAnalysisController.
        
        Args:
            main_controller: Reference to the main application controller
        """
        self.controller = main_controller
        self.manager = SVDAnalysisManager()
        
    def compute_svd_analysis(self, spectra, mean_center=False):
        """
        Compute SVD analysis from spectra.

        Args:
            spectra: List of spectrum dictionaries to analyze
            mean_center: if True, subtract the mean spectrum before
                decomposing — see SVDAnalysisManager.compute_svd_from_spectra's
                docstring. Default False keeps this dialog's traditional
                raw-SVD convention (PCA / SVD Scores & Loadings defaults
                this on instead — see PcaScoresController).

        Returns:
            bool: True if SVD analysis was successful
        """
        if not spectra:
            logger.debug("DEBUG: No spectra provided to SVD analysis")
            return False

        try:
            logger.debug(f"DEBUG: SVD analysis starting with {len(spectra)} spectra")

            # Compute SVD from the input spectra
            logger.debug("DEBUG: Computing SVD from input spectra...")
            if not self.manager.compute_svd_from_spectra(spectra, mean_center=mean_center):
                logger.error("ERROR: Failed to compute SVD")
                return False
            
            logger.info("DEBUG: SVD analysis computed successfully")
            return True
            
        except Exception as e:
            logger.error(f"ERROR: Exception in SVD analysis: {e}")
            logger.exception("Traceback:")
            return False
    
    def get_svd_components_info(self):
        """
        Get information about SVD components for display.
        
        Returns:
            dict: Information about SVD components
        """
        if self.manager.U is None:
            return None
            
        return {
            'n_components': self.manager.U.shape[1],
            'n_datapoints': self.manager.U.shape[0],
            'explained_variance': self.manager.explained_variance,
            'total_variance_first_5': sum(self.manager.explained_variance[:5]) if self.manager.explained_variance is not None else 0
        }
    
    def get_subspectrum_data(self, index):
        """
        Get subspectrum data for visualization.
        
        Args:
            index: Index of subspectrum
            
        Returns:
            tuple: (x_axis, y_values) or (None, None)
        """
        return self.manager.get_subspectrum(index)
    
    def get_coefficients(self, index):
        """
        Get coefficients for a subspectrum.
        
        Args:
            index: Index of subspectrum
            
        Returns:
            numpy.ndarray: Coefficients or None
        """
        return self.manager.get_coefficients(index)
    
    def get_selected_subspectra_data(self, selected_indices):
        """
        Get data for multiple selected subspectra.
        
        Args:
            selected_indices: List of subspectrum indices
            
        Returns:
            dict: Dictionary with subspectra and coefficients data
        """
        return self.manager.get_selected_subspectra_data(selected_indices)
    
    def invert_subspectrum(self, subspectrum_index):
        """
        Invert a subspectrum.
        
        Args:
            subspectrum_index: Index of subspectrum to invert
            
        Returns:
            bool: True if inversion was successful
        """
        return self.manager.invert_subspectrum(subspectrum_index)

    def suggest_bootstrap_n_components(self, target_cumulative_variance=95.0):
        """Suggest a default "how many components are signal" cutoff for
        the Bootstrap Uncertainty prompt below: the fewest leading
        components whose cumulative explained_variance reaches
        target_cumulative_variance percent, clamped to at least 1 and at
        most the total number of components available. Purely a UI
        convenience (a reasonable pre-filled value, not a statistical
        requirement) -- the user can always type a different number.

        Returns:
            int, or 0 if no SVD has been computed yet.
        """
        ev = self.manager.explained_variance
        if ev is None or len(ev) == 0:
            return 0
        cumulative = np.cumsum(ev)
        over = np.nonzero(cumulative >= target_cumulative_variance)[0]
        n = int(over[0]) + 1 if len(over) else len(ev)
        return max(1, min(n, len(ev)))

    def compute_bootstrap_uncertainty(self, reference_manager, n_components,
                                       n_resamples, confidence_level,
                                       random_state=None,
                                       progress_callback=None,
                                       cancel_check=None):
        """Residual bootstrap for SVD's own subspectra (U) and coefficients
        (Vt) -- the same method NMFController/MCRALSController use (see the
        Developer Guide's "SVD Analysis / PCA Bootstrap Uncertainty"
        section for the full reasoning), with the one thing genuinely
        different for a plain SVD: sign. NMF and MCR-ALS pin sign down
        structurally (non-negativity), but a bare SVD has no such
        constraint -- np.linalg.svd is free to return EITHER sign for any
        given component's U column/Vt row (a component and its exact
        negation reconstruct the data identically), and a resampled
        replicate has no reason to land on the same sign as the reference
        by chance. Left uncorrected, this would make the bootstrap band
        for a component that happens to flip sign on some replicates
        balloon out to cover both the reference's curve AND its mirror
        image -- meaningless. Every replicate below is explicitly
        sign-aligned to the reference (see the aligning step in the loop)
        before being folded into the percentile band -- this is the direct
        analogue of the user-facing "invert" feature (self.manager.
        invert_subspectrum / self.manager.inverted_subspectra) that already
        exists precisely because SVD components have this same sign
        ambiguity; bootstrap alignment and manual "invert" are two
        instances of the identical underlying problem.

        Unlike NMF/MCR-ALS, this needs no warm-started refit and no
        iterative solver at all -- SVD is an exact, deterministic
        decomposition (no local optima to drift into), so every replicate
        is just a fresh plain np.linalg.svd call. This is the sense in
        which SVD's bootstrap really is simpler to implement than NMF's or
        MCR-ALS's: no compute_trial(), no init/max_iter, no "does the warm
        start actually converge back" question -- only the sign check.

        reference_manager must already hold a successful full-rank
        decomposition (.U/.s/.Vt/.data_matrix all set, i.e. self.manager
        right after compute_svd_from_spectra() returned True).
        n_components: how many of the reference's already-computed leading
        components to treat as "signal" -- the reconstruction from just
        these is what defines the residual that gets resampled (see
        suggest_bootstrap_n_components() for a reasonable default). Unlike
        NMF/MCR-ALS, this is NOT the parameter the original decomposition
        was run with (this manager always computes the full rank) -- it
        only decides where bootstrap draws the signal/noise line, and can
        be changed and re-run without recomputing the SVD itself.
        progress_callback(b, n_resamples), if given, is called before each
        replicate; cancel_check(), if given, is checked before each
        replicate and stops early (partial results from however many
        replicates completed are still used) when it returns True.

        Returns a dict with U_lower/U_upper/Vt_lower/Vt_upper (pointwise
        percentile bounds, shaped like U[:, :n_components]/
        Vt[:n_components, :]), U_samples/Vt_samples (the raw, already
        sign-aligned per-replicate arrays), n_components,
        n_resamples_requested/n_resamples_used/n_failed, and
        confidence_level -- or None if reference_manager isn't decomposed
        yet, n_components is out of range, or every replicate failed. On
        success, also stored on reference_manager.bootstrap_result.
        """
        ref = reference_manager
        if ref.U is None or ref.s is None or ref.Vt is None or ref.data_matrix is None:
            ref.last_error = (
                "Run SVD analysis successfully before requesting bootstrap "
                "uncertainty.")
            return None

        max_components = ref.U.shape[1]
        if n_components < 1 or n_components > max_components:
            ref.last_error = (
                f"Number of signal components must be between 1 and "
                f"{max_components}.")
            return None

        X0 = ref.data_matrix                          # (n_wl x n_spectra)
        U0 = ref.U[:, :n_components]                   # (n_wl x k)
        s0 = ref.s[:n_components]
        Vt0 = ref.Vt[:n_components, :]                 # (k x n_spectra)
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

                # Sign alignment (see this method's own docstring): SVD
                # gives no guarantee a resampled replicate's component j
                # comes out the same sign as the reference's. Test against
                # U0 (the full n_wl-length column) rather than Vt0 (only
                # n_spectra long) -- more samples means a less noisy sign
                # decision, particularly with few spectra selected. U and
                # Vt for a given component always flip together (their
                # product is what must stay invariant), so both get
                # flipped here, never just one.
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

        U_arr = np.array(U_samples)     # (B_ok, n_wl, k)
        Vt_arr = np.array(Vt_samples)   # (B_ok, k, n_spectra)
        alpha = 1.0 - confidence_level
        lo_pct, hi_pct = 100.0 * alpha / 2.0, 100.0 * (1.0 - alpha / 2.0)
        result = {
            'U_lower': np.percentile(U_arr, lo_pct, axis=0),
            'U_upper': np.percentile(U_arr, hi_pct, axis=0),
            'Vt_lower': np.percentile(Vt_arr, lo_pct, axis=0),
            'Vt_upper': np.percentile(Vt_arr, hi_pct, axis=0),
            'U_samples': U_arr,
            'Vt_samples': Vt_arr,
            'n_components': n_components,
            'n_resamples_requested': n_resamples,
            'n_resamples_used': len(U_samples),
            'n_failed': n_failed,
            'confidence_level': confidence_level,
        }
        ref.bootstrap_result = result
        ref.last_error = None
        return result

    def get_analysis_summary(self):
        """
        Get a summary of the current SVD analysis.
        
        Returns:
            dict: Summary information
        """
        return self.manager.get_analysis_summary()

    def get_n_spectra(self):
        """
        Get the number of input spectra (= required length for parameter values).

        Returns:
            int: Number of spectra
        """
        return self.manager.get_n_spectra()

    def set_parameter_values(self, values, label=None):
        """
        Set custom per-spectrum parameter values (e.g. temperature, pH, time)
        to use as the x-axis for coefficient plots.

        Args:
            values: sequence of numeric values, one per spectrum
            label: optional axis label

        Returns:
            bool: True if the values were valid and accepted
        """
        return self.manager.set_parameter_values(values, label=label)

    def clear_parameter_values(self):
        """Discard custom parameter values, reverting to spectrum order."""
        self.manager.clear_parameter_values()

    def get_parameter_values(self):
        """
        Get the custom parameter values.

        Returns:
            numpy.ndarray or None
        """
        return self.manager.get_parameter_values()

    def get_parameter_label(self):
        """
        Get the axis label associated with the custom parameter values.

        Returns:
            str or None
        """
        return self.manager.parameter_label
    
    def calculate_residual_errors(self):
        """
        Calculate residual errors for display.
        
        Returns:
            numpy.ndarray: Residual errors or None
        """
        return self.manager.calculate_residual_errors()
    
    def save_results_excel(self, filepath, selected_subspectra=None):
        """
        Save SVD analysis results to Excel file.
        
        Args:
            filepath: Path to save file
            selected_subspectra: List of subspectra indices to save (None = all)
            
        Returns:
            bool: True if save was successful
        """
        try:
            success = self.manager.save_results_excel(filepath, selected_subspectra)
            return success
        except Exception as e:
            logger.error(f"ERROR: Excel save failed: {e}")
            return False
    
    def save_results_text(self, save_config):
        """
        Save SVD analysis results to text files.
        
        Args:
            save_config: Dictionary with save configuration
            
        Returns:
            bool: True if save was successful
        """
        try:
            success = self.manager.save_results_text(save_config)
            return success
        except Exception as e:
            logger.error(f"ERROR: Text save failed: {e}")
            return False
    
    def show_dialog(self):
        """Show the SVD analysis dialog."""
        # Get selected spectra
        selected_spectra = self.controller.spectrum_selector.get_selected_spectra()
        
        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                "No Spectra Selected", 
                "Please select spectra before opening SVD analysis."
            )
            return

        # SVD requires every spectrum to share an identical x-axis. Checking
        # this here (before the dialog even opens) instead of after means
        # opening the dialog and then failing inside it — the dialog used
        # to open first and only then show "Failed to compute SVD", which
        # was an unnecessary extra step once the outcome was already certain.
        import numpy as np
        first_x = np.asarray(selected_spectra[0]['x_scale'], dtype=float)
        for spectrum in selected_spectra[1:]:
            x = np.asarray(spectrum['x_scale'], dtype=float)
            if len(x) != len(first_x) or not np.allclose(x, first_x, rtol=1e-7, atol=1e-9):
                QMessageBox.warning(
                    self.controller.view,
                    "Incompatible Spectra",
                    "Cannot perform SVD analysis: spectra have different x-axes.\n\n"
                    f"First spectrum ('{selected_spectra[0]['label']}'): {len(first_x)} points "
                    f"({first_x[0]:.4g} to {first_x[-1]:.4g})\n"
                    f"Spectrum '{spectrum['label']}': {len(x)} points "
                    f"({x[0]:.4g} to {x[-1]:.4g})\n\n"
                    "Please select only spectra with identical x-axes."
                )
                return
            
        # Import the dialog here to avoid circular imports
        from src.views.dialogs.visualization_analysis.svd_analysis_dialog import SVDAnalysisDialog
        
        # Create and show the dialog
        dialog = SVDAnalysisDialog(
            parent=self.controller.view,
            controller=self,
            spectra=selected_spectra
        )
        dialog.exec_()