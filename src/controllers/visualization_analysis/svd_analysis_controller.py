# src/controllers/visualization_analysis/svd_analysis_controller.py

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
        
    def compute_svd_analysis(self, spectra):
        """
        Compute SVD analysis from spectra.
        
        Args:
            spectra: List of spectrum dictionaries to analyze
            
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
            if not self.manager.compute_svd_from_spectra(spectra):
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