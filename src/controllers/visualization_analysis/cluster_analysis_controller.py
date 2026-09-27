# src/controllers/visualization_analysis/cluster_analysis_controller.py

from PyQt5.QtWidgets import QMessageBox
from src.views.dialogs.visualization_analysis.cluster_analysis_dialog import ClusterAnalysisDialog
from src.modules.visualization_analysis.cluster_analysis_manager import ClusterAnalysisManager
from src.modules.utils.revision_tracking import selection_or_revision_changed
from src.modules.utils.spectra_validation import validate_common_x_axis

class ClusterAnalysisController:
    """Controller for cluster analysis visualization operations."""
    
    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.manager = ClusterAnalysisManager()
        # Compared against IncrementalOperationsManager.revision AND the
        # current selection in run_cluster_analysis() below -- unlike a
        # per-spectrum-keyed cache, cluster_labels is computed from the
        # WHOLE selection at once and read directly by the dialog (e.g.
        # switching straight to PCA 3D before Run Clustering is ever
        # clicked), so a plain, unrelated selection change needs to reset
        # this too, not just an operation running -- see
        # revision_tracking.py's own docstring for the concrete bug.
        self._last_seen_revision = None
        self._last_selection_hash = None
        self.dialog = None
    
    def run_cluster_analysis(self):
        """Run cluster analysis on selected spectra."""
        # Get selected spectra from main controller
        if not self.main_controller.selected_spectra:
            QMessageBox.warning(
                self.main_controller.view,
                "No Spectra Selected",
                "Please select spectra to perform cluster analysis."
            )
            return
        
        if len(self.main_controller.selected_spectra) < 2:
            QMessageBox.warning(
                self.main_controller.view,
                "Insufficient Spectra",
                "Please select at least 2 spectra for cluster analysis."
            )
            return
        
        # Cluster analysis stacks every selected spectrum into one matrix,
        # so they must share an x-axis. Uses the shared, tolerance-aware
        # check (spectra_validation.validate_common_x_axis) rather than a
        # private np.array_equal loop — that used to live here as its own
        # copy of this same validation, using exact equality instead of
        # the same tolerance every other "combines spectra" operation in
        # this app uses. Two problems with that: (1) it could reject
        # spectra that are physically identical but differ in float
        # round-off (e.g. an axis rebuilt via Data Range linearisation),
        # and (2) it was a second, independently-written copy of a check
        # that already exists centrally — this manager (see
        # ClusterAnalysisManager.compute_clustering) had its OWN third
        # copy of the same np.array_equal check, so a future change to
        # the tolerance/wording would have had to be made in two places
        # to stay consistent, and it wasn't.
        if not validate_common_x_axis(self.main_controller.selected_spectra,
                                      self.main_controller.view,
                                      'cluster analysis'):
            return
        
        # Clear any previous results before opening a fresh dialog —
        # without this, a stale result from a previous (possibly
        # completely unrelated) set of spectra could still be displayed
        # (e.g. switching straight to PCA 3D) before Run Clustering is
        # ever clicked for this selection.
        should_reset, self._last_selection_hash, self._last_seen_revision = \
            selection_or_revision_changed(
                self.main_controller, self.main_controller.selected_spectra,
                self._last_selection_hash, self._last_seen_revision)
        if should_reset:
            self.manager.reset()

        # Create and show dialog
        self.dialog = ClusterAnalysisDialog(
            parent=self.main_controller.view,
            controller=self,
            spectra=self.main_controller.selected_spectra
        )
        self.dialog.exec_()
    
    def compute_clustering(self, spectra, method, n_clusters, progress_callback=None, **kwargs):
        """Compute clustering with specified parameters."""
        return self.manager.compute_clustering(
            spectra, method, n_clusters, progress_callback=progress_callback, **kwargs)
    
    def get_cluster_info(self):
        """Get clustering information."""
        return self.manager.get_cluster_info()
    
    def get_cluster_members(self, cluster_id):
        """Get members of a specific cluster."""
        return self.manager.get_cluster_members(cluster_id)
    
    def get_cluster_centroid(self, cluster_id):
        """Get centroid spectrum for a cluster."""
        return self.manager.get_cluster_centroid(cluster_id)
    
    def get_pca_data(self):
        """Get PCA transformed data."""
        if self.manager.pca_components is None:
            return None
        return {
            'components': self.manager.pca_components,
            'explained_variance': self.manager.explained_variance_ratio,
            'labels': self.manager.cluster_labels,
            'spectrum_labels': self.manager.spectrum_labels
        }
    
    def compute_elbow_curve(self, spectra, max_clusters=10, progress_callback=None):
        """Compute elbow curve data."""
        return self.manager.compute_elbow_curve(spectra, max_clusters, progress_callback=progress_callback)    
    
    
    
    