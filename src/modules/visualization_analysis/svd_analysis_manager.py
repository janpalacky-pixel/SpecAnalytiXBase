# src/modules/visualization_analysis/svd_analysis_manager.py

import numpy as np
import os
from datetime import datetime
import pandas as pd
from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

class SVDAnalysisManager:
    """Business logic for SVD analysis visualization operations on spectra."""
    
    def __init__(self):
        # SVD components (computed once per analysis)
        self.U = None
        self.s = None
        self.Vt = None
        self.x_axis = None
        self.explained_variance = None
        self.spectrum_labels = None
        self.inverted_subspectra = set()  # Track inverted subspectra
        # Optional per-spectrum parameter values (e.g. temperature, pH, time)
        # used as an alternative x-axis for coefficient plots instead of
        # plain spectrum order (1, 2, 3, ...).
        self.parameter_values = None
        self.parameter_label = None
        self.mean_spectrum = None      # per-wavelength mean subtracted before SVD, or None
        self.mean_centered = False     # whether the last compute used mean-centering
        self.data_matrix = None        # (n_wl x n_spectra) the EXACT matrix that was
                                        # decomposed (post mean-centering, pre-SVD) --
                                        # kept for later reuse by
                                        # compute_bootstrap_uncertainty() (see
                                        # NMFManager.X_nn / MCRALSManager.D for the
                                        # identical idea). Since this manager keeps the
                                        # FULL-RANK decomposition (no n_components
                                        # truncation, unlike PcaScoresManager), this is
                                        # what lets bootstrap treat any user-chosen
                                        # n_components as the "signal" rank without
                                        # needing to re-run SVD from spectra.
        self.bootstrap_result = None   # set by SVDAnalysisController.
                                        # compute_bootstrap_uncertainty()
        self.last_error = None         # specific reason if compute_svd_from_spectra()
                                        # or compute_bootstrap_uncertainty() fails

    def compute_svd_from_spectra(self, spectra, mean_center=False):
        """
        Compute SVD from input spectra using standard numpy SVD.

        Args:
            spectra: List of spectrum dictionaries with 'x_scale', 'y_scale', 'label'
            mean_center: if True, subtract the mean spectrum (average of
                every input spectrum, per wavelength) before decomposing —
                see the identical parameter on SVDBackgroundManager.
                compute_svd_from_spectra for the full rationale and the
                verified numbers behind it. Default False preserves this
                method's original (uncentered) behavior.

        Returns:
            bool: True if SVD computation was successful
        """
        if not spectra:
            logger.debug("DEBUG: No spectra provided for SVD computation")
            return False
            
        try:
            logger.debug(f"DEBUG: Computing SVD from {len(spectra)} spectra")
            
            # Extract x and y data from spectra
            x_scales = [spectrum['x_scale'] for spectrum in spectra]
            y_scales = [spectrum['y_scale'] for spectrum in spectra]
            
            logger.debug(f"DEBUG: First spectrum x-axis length: {len(x_scales[0])}")
            logger.debug(f"DEBUG: First spectrum y-axis length: {len(y_scales[0])}")
            
            # Check if all spectra have the same x-axis
            first_x = x_scales[0]
            for i, x in enumerate(x_scales):
                if not np.array_equal(x, first_x):
                    logger.error(f"ERROR: Spectrum {i} has different x-axis than spectrum 0")
                    logger.debug(f"DEBUG: Spectrum 0 x-range: {first_x[0]:.3f} to {first_x[-1]:.3f}")
                    logger.debug(f"DEBUG: Spectrum {i} x-range: {x[0]:.3f} to {x[-1]:.3f}")
                    return False
                    
            logger.debug("DEBUG: All spectra have identical x-axes")
            
            # Construct data matrix (wavelengths x spectra)
            self.x_axis = first_x
            data_matrix = np.column_stack(y_scales)

            logger.debug(f"DEBUG: Data matrix shape: {data_matrix.shape}")

            # Store spectrum labels
            self.spectrum_labels = [spectrum['label'] for spectrum in spectra]

            self.mean_centered = bool(mean_center)
            if self.mean_centered:
                self.mean_spectrum = data_matrix.mean(axis=1)
                data_matrix = data_matrix - self.mean_spectrum[:, np.newaxis]
            else:
                self.mean_spectrum = None

            # Kept for compute_bootstrap_uncertainty() -- the EXACT matrix
            # about to be decomposed (see this manager's own
            # self.data_matrix docstring in __init__).
            self.data_matrix = data_matrix

            # Compute SVD using standard numpy approach
            logger.debug("DEBUG: Running numpy SVD...")
            self.U, self.s, self.Vt = np.linalg.svd(data_matrix, full_matrices=False)
            
            logger.debug(f"DEBUG: SVD complete - U: {self.U.shape}, s: {self.s.shape}, Vt: {self.Vt.shape}")
            
            # Calculate explained variance
            self.explained_variance = (self.s**2) / np.sum(self.s**2) * 100
            
            logger.debug(f"DEBUG: First 5 explained variances: {self.explained_variance[:5]}")
            
            # Reset inversion state
            self.inverted_subspectra = set()

            # Reset parameter values — they were validated against the
            # previous spectra count/order and can't be assumed to still
            # apply after a fresh computation.
            self.parameter_values = None
            self.parameter_label = None

            # A successful fit means self.U/s/Vt just changed (new spectra
            # or mean-centering setting) -- any bootstrap_result computed
            # for the PREVIOUS decomposition no longer corresponds to
            # what's loaded now and must not be redrawn against it. Same
            # bug class NMFManager.compute() guards against -- see its own
            # comment there.
            self.bootstrap_result = None
            self.last_error = None

            logger.info("DEBUG: SVD computation successful")
            return True
            
        except Exception as e:
            logger.error(f"ERROR: SVD computation failed: {e}")
            logger.exception("Traceback:")
            return False

    def invert_subspectrum(self, subspectrum_index):
        """
        Invert a subspectrum by multiplying U and Vt by -1.
        
        Args:
            subspectrum_index: Index of subspectrum to invert
            
        Returns:
            bool: True if inversion was successful
        """
        if self.U is None or subspectrum_index >= self.U.shape[1]:
            return False
            
        # Update inversion tracking
        if subspectrum_index in self.inverted_subspectra:
            self.inverted_subspectra.remove(subspectrum_index)
        else:
            self.inverted_subspectra.add(subspectrum_index)
        
        # Invert the subspectrum and coefficients
        self.U[:, subspectrum_index] *= -1
        self.Vt[subspectrum_index, :] *= -1

        # A manually-flipped component invalidates any existing bootstrap
        # band computed against the OLD orientation (the band's U_lower/
        # U_upper etc. were sign-aligned to that orientation) -- clear
        # rather than risk drawing a band upside-down relative to the
        # curve it's supposed to be shading. Re-running Bootstrap
        # Uncertainty afterward aligns against the new orientation fine.
        self.bootstrap_result = None

        logger.debug(f"DEBUG: Inverted subspectrum {subspectrum_index}, currently inverted: {self.inverted_subspectra}")
        return True

    def get_subspectrum(self, index):
        """Get subspectrum by index."""
        if self.U is None or index >= self.U.shape[1]:
            return None, None
        return self.x_axis, self.U[:, index]
    
    def get_coefficients(self, index):
        """Get coefficients for specific subspectrum."""
        if self.Vt is None or index >= self.Vt.shape[0]:
            return None
        return self.Vt[index, :]
    
    def get_selected_subspectra_data(self, selected_indices):
        """
        Get data for multiple selected subspectra.
        
        Args:
            selected_indices: List of subspectrum indices
            
        Returns:
            dict: Dictionary with subspectra and coefficients data
        """
        if self.U is None or not selected_indices:
            return None
            
        data = {
            'x_axis': self.x_axis,
            'subspectra': {},
            'coefficients': {},
            'spectrum_labels': self.spectrum_labels
        }
        
        for idx in selected_indices:
            if 0 <= idx < self.U.shape[1]:
                data['subspectra'][f'Subspectrum_{idx+1}'] = self.U[:, idx]
                data['coefficients'][f'Coefficients_{idx+1}'] = self.Vt[idx, :]
                
        return data
    
    def get_n_components(self):
        """Get number of components."""
        if self.U is None:
            return 0
        return self.U.shape[1]
    
    def get_n_datapoints(self):
        """Get number of data points."""
        if self.U is None:
            return 0
        return self.U.shape[0]

    def get_n_spectra(self):
        """Get number of input spectra (= length of each coefficient vector)."""
        if self.Vt is None:
            return 0
        return self.Vt.shape[1]

    def set_parameter_values(self, values, label=None):
        """
        Set custom per-spectrum parameter values (e.g. temperature, pH,
        time) to use as the x-axis for coefficient plots instead of plain
        spectrum order.

        Args:
            values: sequence of numeric values, one per spectrum, in the
                same order the spectra were selected
            label: optional axis label, e.g. "Temperature (\u00b0C)"

        Returns:
            bool: True if the values were valid and accepted
        """
        if self.Vt is None:
            return False

        n_expected = self.Vt.shape[1]
        try:
            arr = np.asarray(values, dtype=float)
        except (TypeError, ValueError):
            return False

        if arr.ndim != 1 or len(arr) != n_expected or n_expected == 0:
            return False

        self.parameter_values = arr
        self.parameter_label = label
        logger.debug(f"DEBUG: Parameter values set ({len(arr)} values, label={label!r})")
        return True

    def clear_parameter_values(self):
        """Discard custom parameter values, reverting to spectrum order."""
        self.parameter_values = None
        self.parameter_label = None

    def get_parameter_values(self):
        """Get the custom parameter values, or None if not set."""
        return self.parameter_values
    
    def get_analysis_summary(self):
        """Get a summary of SVD analysis."""
        if self.U is None:
            return {"status": "No SVD computed"}
        
        summary = {
            "status": "SVD computed",
            "n_subspectra": self.U.shape[1],
            "n_datapoints": self.U.shape[0],
            "n_spectra": len(self.spectrum_labels) if self.spectrum_labels else 0,
            "explained_variance_first_5": self.explained_variance[:5].tolist() if self.explained_variance is not None else [],
            "spectrum_labels": self.spectrum_labels if self.spectrum_labels else [],
            "inverted_subspectra": list(self.inverted_subspectra)
        }
        
        return summary
    
    def calculate_residual_errors(self):
        """Calculate residual errors based on MATLAB faktorka.m implementation."""
        if self.s is None or self.U is None:
            return None
            
        num_of_spectra = self.U.shape[1]
        num_of_spec_points = self.U.shape[0]
        
        if num_of_spectra == 1:
            return np.array([0])
        
        PCA_eigen = self.s**2
        num_of_scores = len(self.s)
        
        E = np.zeros(num_of_scores - 1)
        for m in range(num_of_scores - 1):
            expr_1 = np.sum(PCA_eigen) - np.sum(PCA_eigen[:m+1])
            expr_2 = (num_of_spec_points - m - 1) * (num_of_spectra - m - 1)
            if expr_2 > 0:
                E[m] = np.sqrt(expr_1 / expr_2)
            else:
                E[m] = 0
                
        return E
    
    def _autofit_excel_columns(self, writer, sheet_name, df):
        """Widen each column enough to show its full header on first
        open. Based on header length rather than the full rendered width
        of every value (which would overshoot for raw float precision) —
        the main complaint this fixes is headers getting clipped, and a
        sensible minimum width keeps numeric columns readable too."""
        from openpyxl.utils import get_column_letter
        worksheet = writer.sheets[sheet_name]
        for i, col in enumerate(df.columns):
            width = max(len(str(col)) + 2, 10)
            worksheet.column_dimensions[get_column_letter(i + 1)].width = width

    def save_results_excel(self, filepath, selected_subspectra=None, ind_data=None,
                            include_subspectra=True, include_coefficients=True, include_metrics=True):
        """
        Save SVD analysis results to Excel file with separate worksheets.
        Includes Malinowski IND values when ind_data is provided.
        Each data category (subspectra/coefficients/metrics) can be
        selectively excluded via the include_* flags — all included by
        default.
        """
        if self.U is None:
            raise ValueError("No SVD data available to save")

        try:
            if selected_subspectra is None:
                subspectra_to_save = list(range(self.U.shape[1]))
            else:
                subspectra_to_save = selected_subspectra

            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # Subspectra worksheet
                if include_subspectra:
                    subspectra_data = {'x_axis': self.x_axis}
                    for idx in subspectra_to_save:
                        if idx < self.U.shape[1]:
                            subspectra_data[f'Subspectrum_{idx+1}'] = self.U[:, idx]
                    subspectra_df = pd.DataFrame(subspectra_data)
                    subspectra_df.to_excel(writer, sheet_name='Subspectra', index=False)
                    self._autofit_excel_columns(writer, 'Subspectra', subspectra_df)

                # Coefficients worksheet
                if include_coefficients:
                    coefficients_data = {'Spectrum': self.spectrum_labels}
                    if (self.parameter_values is not None
                            and len(self.parameter_values) == len(self.spectrum_labels)):
                        coefficients_data[self.parameter_label or 'Parameter value'] = self.parameter_values
                    for idx in subspectra_to_save:
                        if idx < self.Vt.shape[0]:
                            coefficients_data[f'Coeff_{idx+1}'] = self.Vt[idx, :]
                    coefficients_df = pd.DataFrame(coefficients_data)
                    coefficients_df.to_excel(writer, sheet_name='Coefficients', index=False)
                    self._autofit_excel_columns(writer, 'Coefficients', coefficients_df)

                # Singular values, residual errors, IND worksheet
                if include_metrics:
                    n = len(self.s)
                    cumev = np.cumsum(self.explained_variance) if self.explained_variance is not None else np.zeros(n)
                    sv_data = {
                        'Component':             list(range(1, n + 1)),
                        'Singular_value':        self.s,
                        'Explained_variance_pct': self.explained_variance if self.explained_variance is not None else [0] * n,
                        'Cumulative_variance_pct': cumev,
                        'Unexplained_variance_pct': 100.0 - cumev,
                    }

                    residual_errors = self.calculate_residual_errors()
                    if residual_errors is not None:
                        padded_re = list(residual_errors) + [np.nan]
                        sv_data['Residual_error'] = padded_re[:n]

                    if ind_data is not None:
                        padded_ind = list(ind_data) + [np.nan]
                        sv_data['Malinowski_IND'] = padded_ind[:n]

                    sv_df = pd.DataFrame(sv_data)
                    sv_df.to_excel(writer, sheet_name='Metrics', index=False)
                    self._autofit_excel_columns(writer, 'Metrics', sv_df)

            return True

        except Exception as e:
            logger.error(f"Error saving SVD results to Excel: {e}")
            return False
    
    def save_results_text(self, save_config):
        """
        Save SVD analysis results to text files based on configuration.
        
        Args:
            save_config: Dictionary with save configuration
            
        Returns:
            bool: True if save was successful
        """
        if self.U is None:
            raise ValueError("No SVD data available to save")
        
        try:
            base_path = save_config['base_path']
            delimiter = save_config.get('delimiter', '\t')
            precision = save_config.get('precision', 6)
            selected_subspectra = save_config.get('selected_subspectra', None)
            save_separate = save_config.get('save_separate', False)
            # The caller already computes Malinowski IND and passes it here,
            # but it was previously never read — Excel export included it,
            # text export silently dropped it.
            ind_data = save_config.get('ind_data', None)
            include_subspectra = save_config.get('include_subspectra', True)
            include_coefficients = save_config.get('include_coefficients', True)
            include_metrics = save_config.get('include_metrics', True)
            
            # Determine which subspectra to save
            if selected_subspectra is None:
                subspectra_to_save = list(range(self.U.shape[1]))
            else:
                subspectra_to_save = selected_subspectra
            
            if save_separate:
                # Save separate files
                success = self._save_separate_text_files(
                    base_path, subspectra_to_save, delimiter, precision, ind_data,
                    include_subspectra, include_coefficients, include_metrics)
            else:
                # Save all in one file
                success = self._save_combined_text_file(
                    base_path, subspectra_to_save, delimiter, precision, ind_data,
                    include_subspectra, include_coefficients, include_metrics)
            
            return success
            
        except Exception as e:
            logger.error(f"Error saving SVD results: {e}")
            return False
    
    def _save_separate_text_files(self, base_path, subspectra_indices, delimiter, precision, ind_data=None,
                                   include_subspectra=True, include_coefficients=True, include_metrics=True):
        """Save data to separate text files."""
        base_name = os.path.splitext(base_path)[0]
        
        # Save subspectra
        if include_subspectra:
            subspectra_data = {'x_axis': self.x_axis}
            for idx in subspectra_indices:
                if idx < self.U.shape[1]:
                    subspectra_data[f'Subspectrum_{idx+1}'] = self.U[:, idx]
            
            subspectra_df = pd.DataFrame(subspectra_data)
            subspectra_df.to_csv(f"{base_name}_subspectra.txt", sep=delimiter, index=False, 
                               float_format=f'%.{precision}f')
        
        # Save coefficients
        if include_coefficients:
            coefficients_data = {'Spectrum': self.spectrum_labels}
            if (self.parameter_values is not None
                    and len(self.parameter_values) == len(self.spectrum_labels)):
                coefficients_data[self.parameter_label or 'Parameter value'] = self.parameter_values
            for idx in subspectra_indices:
                if idx < self.Vt.shape[0]:
                    coefficients_data[f'Coeff_{idx+1}'] = self.Vt[idx, :]
            
            coefficients_df = pd.DataFrame(coefficients_data)
            coefficients_df.to_csv(f"{base_name}_coefficients.txt", sep=delimiter, index=False,
                                 float_format=f'%.{precision}f')
        
        # Save singular values and residual errors
        if include_metrics:
            sv_data = {
                'Component': list(range(1, len(self.s) + 1)),
                'Singular_Value': self.s,
                'Explained_Variance_%': self.explained_variance if self.explained_variance is not None else [0] * len(self.s)
            }
            
            residual_errors = self.calculate_residual_errors()
            if residual_errors is not None:
                padded_residuals = list(residual_errors) + [np.nan]
                sv_data['Residual_Error'] = padded_residuals[:len(self.s)]

            if ind_data is not None:
                padded_ind = list(ind_data) + [np.nan]
                sv_data['Malinowski_IND'] = padded_ind[:len(self.s)]
            
            sv_df = pd.DataFrame(sv_data)
            sv_df.to_csv(f"{base_name}_singular_values_residuals.txt", sep=delimiter, index=False,
                        float_format=f'%.{precision}f')
        
        return True
    
    def _save_combined_text_file(self, filepath, subspectra_indices, delimiter, precision, ind_data=None,
                                  include_subspectra=True, include_coefficients=True, include_metrics=True):
        """Save all data to a single text file."""
        format_str = f'%.{precision}f'
        with open(filepath, 'w') as f:
            # Write subspectra section
            if include_subspectra:
                f.write("# Subspectra\n")
                headers = ["x_axis"]
                for idx in subspectra_indices:
                    if idx < self.U.shape[1]:
                        headers.append(f"Subspectrum_{idx+1}")
                
                f.write(delimiter.join(headers) + "\n")
                
                for i in range(len(self.x_axis)):
                    row = [format_str % self.x_axis[i]]
                    for idx in subspectra_indices:
                        if idx < self.U.shape[1]:
                            row.append(format_str % self.U[i, idx])
                    f.write(delimiter.join(row) + "\n")
            
            # Write coefficients section
            if include_coefficients:
                f.write("\n# Coefficients\n")
                has_params = (self.parameter_values is not None
                              and len(self.parameter_values) == len(self.spectrum_labels))
                coeff_headers = ["Spectrum"]
                if has_params:
                    coeff_headers.append(self.parameter_label or "Parameter value")
                for idx in subspectra_indices:
                    coeff_headers.append(f"Coeff_{idx+1}")
                f.write(delimiter.join(coeff_headers) + "\n")
                
                for i, label in enumerate(self.spectrum_labels):
                    row = [label]
                    if has_params:
                        row.append(format_str % self.parameter_values[i])
                    for idx in subspectra_indices:
                        if idx < self.Vt.shape[0]:
                            row.append(format_str % self.Vt[idx, i])
                    f.write(delimiter.join(row) + "\n")
            
            # Write singular values and residual errors
            if include_metrics:
                f.write("\n# Singular Values and Residual Errors\n")
                sv_headers = ["Component", "Singular_Value", "Explained_Variance_%", "Residual_Error"]
                if ind_data is not None:
                    sv_headers.append("Malinowski_IND")
                f.write(delimiter.join(sv_headers) + "\n")
                
                residual_errors = self.calculate_residual_errors()
                for i, s_val in enumerate(self.s):
                    variance = self.explained_variance[i] if self.explained_variance is not None else 0
                    residual = residual_errors[i] if residual_errors is not None and i < len(residual_errors) else ''
                    residual_str = format_str % residual if residual != '' else 'N/A'
                    
                    row = [str(i+1), format_str % s_val, format_str % variance, residual_str]
                    if ind_data is not None:
                        ind_val = ind_data[i] if i < len(ind_data) else ''
                        row.append(format_str % ind_val if ind_val != '' else 'N/A')
                    f.write(delimiter.join(row) + "\n")
        
        return True
        
        return True