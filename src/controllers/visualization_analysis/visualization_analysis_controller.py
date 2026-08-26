# src/controllers/visualization_analysis/visualization_analysis_controller.py

from PyQt5.QtWidgets import QMessageBox
from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

class VisualizationAnalysisController:
    """Controller for handling different visualization analysis methods."""
    
    def __init__(self, main_controller):
        """
        Initialize the VisualizationAnalysisController.
        
        Args:
            main_controller: Reference to the main application controller
        """
        self.controller = main_controller
        
        # Initialize specific analysis controllers lazily
        self._svd_analysis_controller = None
        self._cluster_analysis_controller = None
        self._pls_controller = None
        self._kinetics_controller = None
        self._qc_outlier_controller = None
        self._som_controller = None

    @property
    def svd_analysis_controller(self):
        """Lazy initialization of SVD analysis controller."""
        if self._svd_analysis_controller is None:
            from src.controllers.visualization_analysis.svd_analysis_controller import SVDAnalysisController
            self._svd_analysis_controller = SVDAnalysisController(self.controller)
        return self._svd_analysis_controller

    @property
    def cluster_analysis_controller(self):
        """Lazy initialization of cluster analysis controller."""
        if self._cluster_analysis_controller is None:
            from src.controllers.visualization_analysis.cluster_analysis_controller import ClusterAnalysisController
            self._cluster_analysis_controller = ClusterAnalysisController(self.controller)
        return self._cluster_analysis_controller

    @property
    def pls_controller(self):
        """Lazy initialization of PLS / PLS-DA controller."""
        if self._pls_controller is None:
            from src.controllers.visualization_analysis.pls_controller import PLSController
            self._pls_controller = PLSController(self.controller)
        return self._pls_controller

    @property
    def kinetics_controller(self):
        """Lazy initialization of Kinetics Fitting controller."""
        if self._kinetics_controller is None:
            from src.controllers.visualization_analysis.kinetics_controller import KineticsController
            self._kinetics_controller = KineticsController(self.controller)
        return self._kinetics_controller

    @property
    def qc_outlier_controller(self):
        """Lazy initialization of QC / Outlier Detection controller."""
        if self._qc_outlier_controller is None:
            from src.controllers.visualization_analysis.qc_outlier_controller import QCOutlierController
            self._qc_outlier_controller = QCOutlierController(self.controller)
        return self._qc_outlier_controller

    @property
    def som_controller(self):
        """Lazy initialization of SOM controller."""
        if self._som_controller is None:
            from src.controllers.visualization_analysis.som_controller import SOMController
            self._som_controller = SOMController(self.controller)
        return self._som_controller

    def run_visualization_analysis(self, method):
        """
        Run the specified visualization analysis method.
        
        Args:
            method: String specifying the analysis method ('SVD analysis', 'Cluster analysis')
        """
        # Check if spectra are selected
        selected_spectra = self.controller.spectrum_selector.get_selected_spectra()
        
        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                "No Spectra Selected", 
                "Please select spectra before running visualization analysis."
            )
            return
            
        logger.debug(f"DEBUG: Running visualization analysis: {method}")
        
        if method == "SVD analysis":
            self.run_svd_analysis()
        elif method == "Cluster analysis":
            self.run_cluster_analysis()
        elif method == "PLS / PLS-DA":
            self.run_pls_analysis()
        elif method == "Kinetics Fitting":
            self.run_kinetics_analysis()
        elif method == "QC / Outlier Detection":
            self.run_qc_outlier_analysis()
        elif method == "SOM":
            self.run_som_analysis()
        else:
            QMessageBox.warning(
                self.controller.view,
                "Unknown Method", 
                f"Unknown visualization analysis method: {method}"
            )
    
    def run_svd_analysis(self):
        """Run SVD analysis visualization."""
        try:
            self.svd_analysis_controller.show_dialog()
        except Exception as e:
            QMessageBox.critical(
                self.controller.view,
                "SVD Analysis Error", 
                f"Error running SVD analysis:\n{str(e)}"
            )
            logger.error(f"ERROR: SVD analysis failed: {e}")
            logger.exception("Traceback:")
    
    def run_cluster_analysis(self):
        """Run cluster analysis visualization."""
        try:
            self.cluster_analysis_controller.run_cluster_analysis()
        except Exception as e:
            QMessageBox.critical(
                self.controller.view,
                "Cluster Analysis Error",
                f"Error running cluster analysis:\n{str(e)}"
            )
            logger.error(f"ERROR: Cluster analysis failed: {e}")
            logger.exception("Traceback:")

    def run_pls_analysis(self):
        """Run PLS / PLS-DA analysis."""
        try:
            self.pls_controller.run_pls_analysis()
        except Exception as e:
            QMessageBox.critical(
                self.controller.view,
                "PLS / PLS-DA Error",
                f"Error running PLS / PLS-DA analysis:\n{str(e)}"
            )
            logger.error(f"ERROR: PLS analysis failed: {e}")
            logger.exception("Traceback:")

    def run_kinetics_analysis(self):
        """Run Kinetics Fitting analysis."""
        try:
            self.kinetics_controller.run_kinetics_analysis()
        except Exception as e:
            QMessageBox.critical(
                self.controller.view,
                "Kinetics Fitting Error",
                f"Error running Kinetics Fitting analysis:\n{str(e)}"
            )
            logger.error(f"ERROR: Kinetics Fitting analysis failed: {e}")
            logger.exception("Traceback:")

    def run_qc_outlier_analysis(self):
        """Run QC / Outlier Detection."""
        try:
            self.qc_outlier_controller.run_qc_outlier_analysis()
        except Exception as e:
            QMessageBox.critical(
                self.controller.view,
                "QC / Outlier Detection Error",
                f"Error running QC / Outlier Detection:\n{str(e)}"
            )
            logger.error(f"ERROR: QC / Outlier Detection failed: {e}")
            logger.exception("Traceback:")

    def run_som_analysis(self):
        """Run SOM (Self-Organizing Map) analysis."""
        try:
            self.som_controller.run_som_analysis()
        except Exception as e:
            QMessageBox.critical(
                self.controller.view,
                "SOM Error",
                f"Error running SOM analysis:\n{str(e)}"
            )
            logger.error(f"ERROR: SOM analysis failed: {e}")
            logger.exception("Traceback:")