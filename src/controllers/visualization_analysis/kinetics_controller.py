# src/controllers/visualization_analysis/kinetics_controller.py

from PyQt5.QtWidgets import QMessageBox
from src.modules.visualization_analysis.kinetics_manager import KineticsManager
from src.modules.utils.spectra_validation import validate_common_x_axis


class KineticsController:
    """Controller for time-course Kinetics Fitting (single-wavelength
    multi-exponential fitting, or global analysis with one shared set of
    rate constants across every wavelength) — mirrors PLSController's
    shape: thin, owns the manager, validates the selection before opening
    the dialog. Read-only analysis tool, like PLS/PLS-DA and Isosbestic
    Point Detection: it never adds, removes, or transforms spectral data,
    so there's no Apply/Add-as-New commit step and nothing is written to
    Operations History."""

    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.manager = KineticsManager()
        self.dialog = None

    def run_kinetics_analysis(self):
        if not self.main_controller.selected_spectra:
            QMessageBox.warning(
                self.main_controller.view, "No Spectra Selected",
                "Please select the time-series spectra to fit."
            )
            return

        if len(self.main_controller.selected_spectra) < 4:
            QMessageBox.warning(
                self.main_controller.view, "Insufficient Spectra",
                "Please select at least 4 spectra (one per time point) — a "
                "real kinetic fit needs several more than that to pin down "
                "even a single exponential component reliably."
            )
            return

        # Global analysis stacks every selected spectrum's y_scale directly
        # into one matrix (no per-spectrum interpolation, unlike the
        # single-wavelength extraction) — same requirement, and same
        # shared check, as PLS / Cluster Analysis / Isosbestic Point
        # Detection. Required up front for the whole dialog (not just
        # when Global mode is chosen) so switching modes inside an
        # already-open dialog never hits a surprise mismatch.
        if not validate_common_x_axis(self.main_controller.selected_spectra,
                                       self.main_controller.view, 'Kinetics Fitting'):
            return

        from src.views.dialogs.visualization_analysis.kinetics_fitting_dialog import KineticsFittingDialog
        self.dialog = KineticsFittingDialog(
            parent=self.main_controller.view,
            controller=self,
            spectra=self.main_controller.selected_spectra,
        )
        self.dialog.exec_()

    # ------------------------------------------------------------------ #
    # Pure computation helpers (thin wrappers around the manager, kept    #
    # here so the dialog stays free of algorithm details — same           #
    # separation of concerns as PLSController.compute_pls).               #
    # ------------------------------------------------------------------ #

    def extract_curve(self, spectra, x_value, window=0.0):
        return self.manager.extract_curve_from_spectra(spectra, x_value, window=window)

    def fit_single_wavelength(self, t, y, n_components, k_guesses=None,
                              amplitude_guesses=None, offset_guess=None):
        return self.manager.fit_exponential_model(
            t, y, n_components, k_guesses=k_guesses,
            amplitude_guesses=amplitude_guesses, offset_guess=offset_guess)

    def auto_rate_guesses(self, t, n_components):
        return self.manager.auto_detect_rate_guesses(t, n_components)

    def fit_global(self, spectra, times, n_components, k_guesses=None, include_offset=True):
        t_sorted, x_wavelengths, D, order = self.manager.build_data_matrix(spectra, times)
        result = self.manager.fit_global_model(
            t_sorted, x_wavelengths, D, n_components,
            k_guesses=k_guesses, include_offset=include_offset)
        if result is not None:
            result['D'] = D
            result['sort_order'] = order
        return result
