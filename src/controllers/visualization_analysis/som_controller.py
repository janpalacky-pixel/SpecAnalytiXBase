# src/controllers/visualization_analysis/som_controller.py

from PyQt5.QtWidgets import QMessageBox
from src.views.dialogs.visualization_analysis.som_dialog import SOMDialog
from src.modules.visualization_analysis.som_manager import SOMManager
from src.modules.utils.revision_tracking import revision_changed
from src.modules.utils.spectra_validation import validate_common_x_axis


class SOMController:
    """
    Controller for Self-Organizing Map (SOM) visualization/analysis.

    Shape mirrors ClusterAnalysisController (src/controllers/
    visualization_analysis/cluster_analysis_controller.py) — SOM is a peer
    of Cluster Analysis, PCA Scores, NMF, MCR-ALS, and SVD analysis: a
    read-only Visualization tool that trains/plots against the current
    selection and never commits new spectra to the main list. It does not
    go through OperationsController the way Melting Curve Analysis, Peak
    Fitting, Band Ratio, Reference Matching, and Isosbestic Point Detection
    do — those are spectrum-producing "Data Analysis" operations with their
    own undo history; SOM is not.
    """

    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.manager = SOMManager()
        # Compared against IncrementalOperationsManager.revision in
        # show_dialog() below, so a reopen only forgets the last result if an
        # operation actually ran meanwhile -- see revision_tracking.py.
        self._last_seen_revision = None
        self.dialog = None

    def run_som_analysis(self):
        """Run SOM analysis on the currently selected spectra."""
        if not self.main_controller.selected_spectra:
            QMessageBox.warning(
                self.main_controller.view,
                "No Spectra Selected",
                "Please select spectra to perform SOM analysis."
            )
            return

        if len(self.main_controller.selected_spectra) < 2:
            QMessageBox.warning(
                self.main_controller.view,
                "Insufficient Spectra",
                "Please select at least 2 spectra for SOM analysis."
            )
            return

        # SOM stacks every selected spectrum into one matrix, so they must
        # share an x-axis — same shared, tolerance-aware check every other
        # "combine spectra" tool in this app uses (see
        # spectra_validation.validate_common_x_axis's own docstring for why
        # a private np.array_equal check here would be both stricter than
        # necessary and a second copy of logic that already lives centrally).
        # Required regardless of training mode (shape or feature) so the
        # dialog can always fall back to plain wavelength-shape training,
        # and so "Show Node Spectra" can always overlay real member curves.
        if not validate_common_x_axis(self.main_controller.selected_spectra,
                                      self.main_controller.view,
                                      'SOM analysis'):
            return

        # Clear any previous results before opening a fresh dialog — without
        # this, a stale map trained on a previous, unrelated selection could
        # still be displayed before Run SOM is ever clicked for this one.
        should_reset, self._last_seen_revision = revision_changed(
            self.main_controller, self._last_seen_revision)
        if should_reset:
            self.manager.reset()

        self.dialog = SOMDialog(
            parent=self.main_controller.view,
            controller=self,
            spectra=self.main_controller.selected_spectra
        )
        self.dialog.exec_()

    # ------------------------------------------------------------------ #
    # Thin wrappers around the manager — keeps the dialog free of         #
    # algorithm details, same separation of concerns as                  #
    # ClusterAnalysisController.compute_clustering/get_cluster_info/etc.  #
    # ------------------------------------------------------------------ #

    def compute_som(self, spectra, **kwargs):
        """Train the SOM. kwargs: grid_rows, grid_cols, n_iterations,
        learning_rate_start, learning_rate_end, radius_end, random_seed,
        train_mode ('shape'/'feature'), feature_defs, progress_callback."""
        return self.manager.compute_som(spectra, **kwargs)

    def get_node_info(self):
        return self.manager.get_node_info()

    def get_node_members(self, row, col):
        return self.manager.get_node_members(row, col)

    def get_component_plane(self, feature_index):
        return self.manager.get_component_plane(feature_index)

    def get_component_plane_by_settings(self, settings):
        return self.manager.get_component_plane_by_settings(settings)

    def get_n_features(self):
        return self.manager.get_n_features()

    def get_feature_label(self, idx):
        return self.manager.get_feature_label(idx)

    def get_feature_labels(self):
        return self.manager.feature_labels or []

    def get_node_prototype_spectrum(self, row, col):
        return self.manager.get_node_prototype_spectrum(row, col)
