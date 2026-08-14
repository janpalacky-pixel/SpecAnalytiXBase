# src/controllers/visualization_analysis/isosbestic_point_controller.py

from src.modules.visualization_analysis.isosbestic_point_manager import IsosbesticPointManager
from src.modules.utils.spectra_validation import validate_common_x_axis
from PyQt5.QtWidgets import QMessageBox
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)


class IsosbesticPointController:
    """
    Controller for Isosbestic/Isodichroic Point Detection.

    Same thin-controller pattern as BandRatioController: owns one
    IsosbesticPointManager instance, delegates all computation to it,
    handles dialog creation/validation. Purely read-only analysis — no
    spectra are ever added, removed, or transformed, so (like Band
    Ratio) there's no Operations History entry and no Apply/Add-as-New
    step; the dialog's Results table + Export CSV IS the deliverable.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = IsosbesticPointManager()

    # ------------------------------------------------------------------ #
    # Public API used by the dialog                                        #
    # ------------------------------------------------------------------ #

    def compute_results(self, spectra, settings):
        """Delegate to manager; return the results dict (or raise ValueError
        with a user-facing message, which the dialog catches and displays)."""
        return self.manager.compute_results(spectra, settings)

    # ------------------------------------------------------------------ #
    # Dialog launcher                                                       #
    # ------------------------------------------------------------------ #

    def show_dialog(self, selected_spectra=None, current_settings=None):
        """Show the Isosbestic/Isodichroic Point Detection dialog."""
        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                "No Spectra Selected",
                "Please select spectra before opening Isosbestic/Isodichroic Point Detection.",
            )
            return

        # All spectra combined into one matrix — same requirement as
        # SVD/PCA/Cluster/MCR-ALS/NMF, checked up front (before opening
        # the dialog) so the user sees one clear message instead of an
        # empty dialog or a per-recompute error.
        if not validate_common_x_axis(
            selected_spectra, self.controller.view,
            tool_name='Isosbestic/Isodichroic Point Detection'
        ):
            return

        from src.views.dialogs.visualization_analysis.isosbestic_point_dialog import IsosbesticPointDialog

        dialog = IsosbesticPointDialog(
            parent=self.controller.view,
            controller=self,
            selected_spectra=selected_spectra,
            current_settings=current_settings,
        )
        dialog.exec_()
        # Read-only analysis (see class docstring) — OK and Cancel both
        # just close the dialog, no commit step either way. Still return
        # the settings shown so the caller can remember them for next
        # time the dialog is reopened, same convenience every other
        # operation's dispatch branch provides.
        return dialog.get_settings()
