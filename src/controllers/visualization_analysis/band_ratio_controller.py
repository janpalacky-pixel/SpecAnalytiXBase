# src/controllers/visualization_analysis/band_ratio_controller.py

from src.modules.visualization_analysis.band_ratio_manager import BandRatioManager
from PyQt5.QtWidgets import QMessageBox
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)


class BandRatioController:
    """
    Controller for the Band Ratio / Peak Area Calculator.

    Follows the same thin-controller pattern as SVDAnalysisController /
    ResolutionEnhancementController / CosmicRayController: owns a
    BandRatioManager instance, delegates all computation to it, and
    handles dialog creation / validation.

    Before this class existed, BandRatioDialog created its own fresh
    BandRatioManager() instance directly inline, inside _calculate() —
    the same "dialog owns its own throwaway manager" gap those other
    controllers were specifically created to close (see their own
    docstrings). Purely visualization/calculation — no spectra are ever
    added to the main list here, so unlike Map2DController there's no
    identity/unique_id or Operations History concern to bring in; the
    fix is just giving this one manager instance a proper home instead
    of recreating it on every Calculate click.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = BandRatioManager()

    # ------------------------------------------------------------------ #
    # Public API used by the dialog                                        #
    # ------------------------------------------------------------------ #

    def compute_results(self, spectra, settings):
        """Delegate to manager; return the list of per-spectrum result dicts."""
        return self.manager.compute_results(spectra, settings)

    # ------------------------------------------------------------------ #
    # Dialog launcher                                                       #
    # ------------------------------------------------------------------ #

    def show_dialog(self, selected_spectra=None, current_settings=None):
        """Show the Band Ratio / Peak Area Calculator dialog."""
        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                "No Spectra Selected",
                "Please select spectra before opening the Band Ratio / Peak Area Calculator.",
            )
            return

        from src.views.dialogs.visualization_analysis.band_ratio_dialog import BandRatioDialog

        dialog = BandRatioDialog(
            parent=self.controller.view,
            controller=self,
            selected_spectra=selected_spectra,
            current_settings=current_settings,
        )
        dialog.exec_()
