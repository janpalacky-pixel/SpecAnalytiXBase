# src/controllers/visualization_analysis/two_d_correlation_controller.py

from PyQt5.QtWidgets import QMessageBox
from src.modules.visualization_analysis.two_d_correlation_manager import TwoDCorrelationManager
from src.modules.utils.revision_tracking import revision_changed
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import validate_at_most_two_axis_groups
logger = get_logger(__name__)


class TwoDCorrelationController:
    """Controller for 2D Correlation (2D-COS) visualization operations.
    Mirrors SVDAnalysisController's shape."""

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = TwoDCorrelationManager()
        # Compared against IncrementalOperationsManager.revision in
        # show_dialog() below, so a reopen only forgets the last result if an
        # operation actually ran meanwhile -- see revision_tracking.py.
        self._last_seen_revision = None
        self.dialog = None

    def compute_analysis(self, spectra, reference='mean', reference_index=None,
                          perturbation_values=None, perturbation_label=None):
        """
        Compute the 2D correlation spectra. Pure computation — safe to
        call from the dialog's background QThread.

        Returns:
            bool: True if the computation succeeded.
        """
        if not spectra:
            logger.debug("DEBUG: No spectra provided to 2D correlation analysis")
            return False
        try:
            return self.manager.compute(
                spectra, reference=reference, reference_index=reference_index,
                perturbation_values=perturbation_values, perturbation_label=perturbation_label)
        except Exception as e:
            logger.error(f"ERROR: Exception in 2D correlation analysis: {e}")
            logger.exception("Traceback:")
            return False

    def compute_hetero_analysis(self, spectra_x, spectra_y, reference_x='mean', reference_y='mean'):
        """
        Compute hetero (cross-dataset) 2D correlation. Pure computation —
        safe to call from the dialog's background QThread.

        Returns:
            bool: True if the computation succeeded.
        """
        if not spectra_x or not spectra_y:
            logger.debug("DEBUG: No spectra provided to hetero 2D correlation analysis")
            return False
        try:
            return self.manager.compute_hetero(
                spectra_x, spectra_y, reference_x=reference_x, reference_y=reference_y)
        except Exception as e:
            logger.error(f"ERROR: Exception in hetero 2D correlation analysis: {e}")
            logger.exception("Traceback:")
            return False

    def get_n_points(self):
        return self.manager.get_n_points()

    def get_n_spectra(self):
        return self.manager.get_n_spectra()

    def save_snapshot(self, filepath, x_axis, synchronous, asynchronous, desc=''):
        """
        Save an A/B comparison snapshot to a file.

        Returns:
            bool: True if save was successful
        """
        try:
            self.manager.save_snapshot_file(filepath, x_axis, synchronous, asynchronous, desc)
            return True
        except Exception as e:
            logger.error(f"ERROR: Snapshot save failed: {e}")
            return False

    def load_snapshot(self, filepath):
        """
        Load a previously saved A/B comparison snapshot.

        Returns:
            dict or None: {'x_axis','synchronous','asynchronous','desc'}, or
                None if the file couldn't be read.
        """
        try:
            return self.manager.load_snapshot_file(filepath)
        except Exception as e:
            logger.error(f"ERROR: Snapshot load failed: {e}")
            return None

    def save_results_excel(self, filepath, include_synchronous=True,
                            include_asynchronous=True, include_dynamic=True):
        """
        Save 2D correlation results to an Excel file.

        Returns:
            bool: True if save was successful
        """
        try:
            return self.manager.save_results_excel(
                filepath, include_synchronous, include_asynchronous, include_dynamic)
        except Exception as e:
            logger.error(f"ERROR: Excel save failed: {e}")
            return False

    def save_results_text(self, save_config):
        """
        Save 2D correlation results to text/CSV file(s).

        Returns:
            bool: True if save was successful
        """
        try:
            return self.manager.save_results_text(save_config)
        except Exception as e:
            logger.error(f"ERROR: Text save failed: {e}")
            return False

    def show_dialog(self):
        """Show the 2D Correlation dialog. Same validation shape as
        SVDAnalysisController.show_dialog(), with one deliberate
        difference: it no longer requires every selected spectrum to share
        one identical x-axis. That check used to run here, before the
        dialog even opened, but it would incorrectly block the legitimate
        hetero-COS workflow (see the dialog's "Hetero 2D Correlation" mode),
        which needs a mixed selection — e.g. some IR spectra and some Raman
        spectra together, to be split into Dataset X / Dataset Y inside the
        dialog. Axis-consistency is still fully checked, just later and
        per-mode: TwoDCorrelationManager.compute() requires all spectra to
        match for standard (homo) mode, and compute_hetero() requires each
        of Dataset X and Dataset Y to be internally consistent (but not to
        match each other) for hetero mode."""
        selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                "No Spectra Selected",
                "Please select spectra before opening 2D Correlation."
            )
            return

        if len(selected_spectra) < 3:
            QMessageBox.warning(
                self.controller.view, "Insufficient Spectra",
                "2D Correlation requires at least 3 spectra — the "
                "asynchronous (Hilbert-Noda) transform needs enough points "
                "to distinguish a real out-of-phase signal from noise.\n"
                "Please select more spectra."
            )
            return

        # 2D-COS is the ONE combining method that legitimately accepts a mixed
        # selection: hetero-COS correlates two different datasets against each
        # other (IR vs Raman, say), so Dataset X and Dataset Y must each be
        # internally consistent but must NOT match each other. A blanket
        # "all spectra share one x-axis" guard would wrongly block that, which is
        # why it was removed from here.
        #
        # But THREE or more different axes cannot work in any mode — homo needs
        # one group, hetero needs exactly two — so that case is refused up front
        # instead of opening a dialog that can never produce a result.
        if not validate_at_most_two_axis_groups(selected_spectra,
                                                self.controller.view,
                                                '2D Correlation'):
            return

        # Reset previous results before opening a fresh dialog for a new
        # selection — same reasoning as the other visualization-analysis
        # controllers: without this, a stale result from a previous,
        # unrelated selection could still be read before the first
        # computation for this selection finishes.
        should_reset, self._last_seen_revision = revision_changed(
            self.controller, self._last_seen_revision)
        if should_reset:
            self.manager.reset()

        from src.views.dialogs.visualization_analysis.two_d_correlation_dialog import TwoDCorrelationDialog
        self.dialog = TwoDCorrelationDialog(
            parent=self.controller.view,
            controller=self,
            spectra=selected_spectra,
        )
        self.dialog.exec_()
        self.dialog = None
