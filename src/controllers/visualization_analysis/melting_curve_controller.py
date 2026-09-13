# src/controllers/visualization_analysis/melting_curve_controller.py

import uuid
import numpy as np
from PyQt5.QtWidgets import QMessageBox

from src.modules.visualization_analysis.melting_curve_manager import MeltingCurveManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key
from src.modules.utils.correction_history import append_correction_history

logger = get_logger(__name__)


class MeltingCurveController:
    """
    Controller for thermal melting-curve analysis.

    Shape mirrors PeakFittingController (src/controllers/data_analysis/
    peak_fitting_controller.py, the pattern this integration was built
    from): the manager holds pure computation, this controller bridges it
    with the dialog and owns handle_melting_curve_analysis() directly,
    using the shared self.oc property to reach OperationsController's own
    state (operations_manager, _get_current_state_for_selected_spectra,
    _rebuild_spectra_list_with_selection).

    The one structural difference from Peak Fitting: Peak Fitting always
    has exactly ONE source spectrum. Melting Curve Analysis has MANY
    source spectra (one per temperature point) that collapse into ONE
    extracted curve — so "the original spectrum" below is instead "the
    list of source spectra", and every new spectrum this creates uses the
    extracted temperature axis (not any single source spectrum's
    x_scale).

    This controller also owns the "Saved Fits" container
    (self.saved_fits) — a plain dict (name -> settings snapshot, same
    shape MeltingCurveDialog.get_results() returns) that the dialog reads
    and writes directly (passed in by reference in show_dialog()). It's
    purely a comparison/bookkeeping aid for the user, populated only via
    the dialog's "Save Current Fit" button — it plays NO role in what OK
    actually commits as new spectra, which is still always just the one
    curve currently being worked on. Because this controller instance is
    created once and reused for the life of the app session (see
    OperationsController.handle_melting_curve_analysis's
    hasattr(...)/lazy-construct pattern), the container survives closing
    and reopening the dialog, even for a different spectra selection.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = MeltingCurveManager()
        self.saved_fits = {}

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic needs — same pattern as PeakFittingController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Dialog                                                               #
    # ------------------------------------------------------------------ #

    def show_dialog(self, selected_spectra, current_settings=None):
        """Construct (but do not exec) the Melting Curve Analysis dialog
        for a set of selected spectra. Returns the QDialog instance — the
        caller runs it and reads back get_results()."""
        from src.views.dialogs.visualization_analysis.melting_curve_dialog import MeltingCurveDialog
        return MeltingCurveDialog(
            self.controller.view if self.controller else None,
            selected_spectra=selected_spectra,
            current_settings=current_settings,
            saved_fits=self.saved_fits,
            main_controller=self.controller,
        )

    # ------------------------------------------------------------------ #
    # Commit                                                               #
    # ------------------------------------------------------------------ #

    def handle_melting_curve_analysis(self):
        """
        Handles the melting curve analysis operation.
        1. If any Output Options are checked, creates the corresponding new
           spectra (extracted curve, normalized curve, baselines, fit
           curve, residual, individual sigmoid components) and adds them
           to the main list — the source spectra are never modified.
        2. If no Output Options are checked, nothing is saved at all —
           same "analysis, not a spectrum-modifying operation" convention
           Peak Fitting follows.
        3. Checks for duplicate names and adds a suffix if a name already
           exists.
        """
        if "Melting Curve Analysis" not in self.oc.current_parameters:
            QMessageBox.warning(self.controller.view, "No Parameters",
                                "Melting curve analysis parameters have not been set.")
            return

        settings = self.oc.current_parameters["Melting Curve Analysis"]
        curve = settings.get('curve')
        output_options = settings.get('output_options', {})

        if not curve or curve.get('x_temperature') is None:
            QMessageBox.information(self.controller.view, "No Curve Data",
                                    "No melting curve was extracted. Operation cancelled.")
            return

        # One shared identifier for every spectrum derived from THIS
        # analysis — same reasoning as Peak Fitting's fit_run_id: lets a
        # spectrum's own metadata show which other spectra came from the
        # SAME analysis run.
        run_id = str(uuid.uuid4())

        source_labels = settings.get('source_labels', [])
        curve_name = settings.get('curve_name') or "melting_curve"

        current_state = self.oc.operations_manager.get_current_spectra()

        def find_unique_name(base_name, all_labels):
            new_name = base_name
            suffix = 2
            while new_name in all_labels:
                new_name = f"{base_name}_{suffix}"
                suffix += 1
            return new_name

        all_current_labels = {s['label'] for s in current_state}

        # Spectra actually present in the current state that fed this
        # analysis — used for Operations History, same role as
        # affected_spectra_for_history in Peak Fitting.
        affected_spectra_for_history = [
            s for s in current_state if s['label'] in set(source_labels)
        ]

        x_temperature = np.asarray(curve['x_temperature'], dtype=float)
        new_spectra_to_add = []

        def make_spectrum(y, suffix, extra_history_fields, operation_label):
            spec = {
                'x_scale': x_temperature.copy(),
                'y_scale': np.asarray(y, dtype=float),
                'label': "",
                'metadata': {},
            }
            base_label = f"{curve_name}_{suffix}"
            spec['label'] = find_unique_name(base_label, all_current_labels)
            all_current_labels.add(spec['label'])
            spec['metadata']['unique_id'] = str(uuid.uuid4())
            fields = {'run_id': run_id, 'source_spectra': list(source_labels)}
            fields.update(extra_history_fields)
            spec['metadata']['correction_history'] = append_correction_history(
                None, operation_label, fields)
            return spec

        # --- Raw extracted curve ---
        if output_options.get('add_raw_curve'):
            raw_extra = {'x_value': curve.get('x_value')}
            if curve.get('svd_diagnostics'):
                raw_extra['svd_diagnostics'] = curve['svd_diagnostics']
            new_spectra_to_add.append(make_spectrum(
                curve['y_raw'], "raw",
                raw_extra,
                'Melting Curve Analysis (extracted curve)'))

        normalization = settings.get('normalization')
        norm_result = curve.get('normalization_result')

        # --- Normalized curve + baselines ---
        if output_options.get('add_normalized_curve') and norm_result is not None:
            new_spectra_to_add.append(make_spectrum(
                norm_result['y_norm'], "normalized",
                {'normalization': normalization},
                'Melting Curve Analysis (normalized curve)'))

        if output_options.get('add_baselines') and norm_result is not None:
            new_spectra_to_add.append(make_spectrum(
                norm_result['baseline_low'], "baseline_low",
                {'normalization': normalization},
                'Melting Curve Analysis (low-T baseline)'))
            new_spectra_to_add.append(make_spectrum(
                norm_result['baseline_high'], "baseline_high",
                {'normalization': normalization},
                'Melting Curve Analysis (high-T baseline)'))

        fit_result = settings.get('fit_result')

        # --- Total fit + residual ---
        if fit_result is not None:
            y_source = norm_result['y_norm'] if norm_result is not None else curve['y_raw']

            if output_options.get('add_fit'):
                new_spectra_to_add.append(make_spectrum(
                    fit_result['y_fit'], "fit",
                    {
                        'n_components': fit_result['n_components'],
                        'shape_name': fit_result['shape_name'],
                        'quality': fit_result['quality'],
                        'thermodynamics': settings.get('thermodynamics'),
                    },
                    'Melting Curve Analysis (total fit)'))

            if output_options.get('add_residual'):
                residual = np.asarray(y_source, dtype=float) - np.asarray(fit_result['y_fit'], dtype=float)
                new_spectra_to_add.append(make_spectrum(
                    residual, "residual",
                    {'n_components': fit_result['n_components']},
                    'Melting Curve Analysis (residual)'))

            if output_options.get('add_components'):
                components = fit_result['components']['components']
                comp_params = fit_result['components']['params']
                comp_thermo = settings.get('component_thermodynamics') or []
                n_width = max(2, len(str(len(components))))
                for i, (comp_y, comp_p) in enumerate(zip(components, comp_params)):
                    extra = {
                        'component_index': i + 1,
                        'factor': comp_p['factor'],
                        'midpoint': comp_p['midpoint'],
                        'lambda_': comp_p['lambda_'],
                    }
                    if i < len(comp_thermo) and comp_thermo[i].get('thermodynamics'):
                        extra['thermodynamics'] = comp_thermo[i]['thermodynamics']
                    new_spectra_to_add.append(make_spectrum(
                        comp_y, f"component_{i + 1:0{n_width}d}",
                        extra,
                        'Melting Curve Analysis (individual transition)'))

        if not new_spectra_to_add:
            QMessageBox.information(
                self.controller.view, "Melting Curve Analysis Complete",
                "Analysis computed, but nothing was saved — no output spectra were "
                "requested. Check one of the output options to keep the result."
            )
            return

        output_spectra = current_state + new_spectra_to_add

        self.oc.operations_manager.apply_operation(
            "Melting Curve Analysis",
            settings,
            affected_spectra_for_history,
            new_state_spectra=output_spectra
        )

        self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
        self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)
        new_ids = {spectrum_key(s) for s in new_spectra_to_add}
        self.oc._rebuild_spectra_list_with_selection(new_ids)

        self.controller.spectrum_selector.on_item_selection_changed()
        QMessageBox.information(
            self.controller.view, "Melting Curve Analysis Complete",
            f"{len(new_spectra_to_add)} new spectra were added from the analysis.")

    # ------------------------------------------------------------------ #
    # Pure computation helpers (thin wrappers around the manager, kept   #
    # here — not in the dialog — so the dialog stays free of algorithm    #
    # details, same separation of concerns as PeakFittingController's    #
    # compute_total_fit_curve / compute_individual_peak_curves).          #
    # ------------------------------------------------------------------ #

    def extract_curve(self, selected_spectra, temperatures, x_value, window=0.0):
        """Extract (temperature, y) pairs from selected_spectra at
        x_value, sorted by ascending temperature. Returns a dict with
        'x_temperature', 'y_raw', 'x_value', 'out_of_range_labels',
        'source_labels' (in the SAME sorted order as the curve arrays)."""
        y_values, out_of_range = self.manager.extract_curve_from_spectra(
            selected_spectra, x_value, window=window)

        temperatures = np.asarray(temperatures, dtype=float)
        order = np.argsort(temperatures)
        labels = [selected_spectra[i]['label'] for i in order]

        return {
            'x_temperature': temperatures[order],
            'y_raw': y_values[order],
            'x_value': x_value,
            'out_of_range_labels': out_of_range,
            'source_labels': labels,
        }

    def extract_curve_svd(self, selected_spectra, temperatures, center=True):
        """SVD counterpart to extract_curve \u2014 see
        MeltingCurveManager.extract_curve_svd_from_spectra's docstring
        for the method itself. Returns the SAME dict shape extract_curve
        does (so any caller of either can treat the result identically),
        with 'x_value' always None (no single x position applies) and an
        added 'svd_diagnostics' entry."""
        y_values, diagnostics = self.manager.extract_curve_svd_from_spectra(
            selected_spectra, center=center)

        temperatures = np.asarray(temperatures, dtype=float)
        order = np.argsort(temperatures)
        labels = [selected_spectra[i]['label'] for i in order]

        return {
            'x_temperature': temperatures[order],
            'y_raw': y_values[order],
            'x_value': None,
            'out_of_range_labels': [],
            'source_labels': labels,
            'svd_diagnostics': diagnostics,
        }
