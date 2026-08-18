# src/controllers/data_analysis/mean_centering_controller.py
"""
Controller for the Mean-Center Spectra (Dataset) operation — subtracts the
ENSEMBLE average spectrum of a selected batch from every spectrum in that
batch. Follows the same pattern as XAxisUnitConversionController /
CDUnitConversionController:
  • show_dialog()                – open the parameter dialog, persist settings
  • commit_mean_centering()      – Apply / Add as New, called by the dialog's
                                    own buttons via commit_callback
  • apply_centering_to_spectra() – delegate computation to the manager
  • update_settings()            – forward settings to the manager
"""

import uuid
from datetime import datetime

from PyQt5.QtWidgets import QApplication

from src.modules.data_analysis.mean_centering_manager import MeanCenteringManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)


class MeanCenteringController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = MeanCenteringManager()
        self._last_settings = {}

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this commit
        logic needs — same pattern as XAxisUnitConversionController.oc /
        NormalizationController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    def commit_mean_centering(self, settings, add_as_new, selected_spectra):
        """Commit mean-centering, called by the dialog's own Apply / Add
        as New buttons rather than through the generic Run dispatch.

        Unlike every other batch operation in this app, this one can
        optionally emit ONE EXTRA output — the computed ensemble mean
        spectrum itself — regardless of whether Apply or Add as New was
        chosen for the centered spectra, since there's no "original" for
        the mean spectrum to replace.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra:
            return False, 'Please select two or more spectra to mean-center.'

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "Mean-Center Spectra (Dataset)",
            f"Mean-centering {n_spectra} spectra…",
            n_spectra,
        )
        try:
            try:
                centered_spectra = self.apply_centering_to_spectra(
                    settings, selected_spectra,
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
                )
            except ValueError as exc:
                # Mismatched x-axes — a clear, actionable message from
                # MeanCenteringManager.validate_shared_x_axis, not a raw
                # traceback.
                return False, str(exc)
            except Exception as exc:
                logger.exception('Unexpected error in mean-centering')
                return False, f'An unexpected error occurred: {exc}'

            if not centered_spectra:
                return False, 'Failed to mean-center the selected spectra.'

            current_state = self.oc.operations_manager.get_current_spectra()
            all_labels = {s['label'] for s in current_state}

            # Optional extra output: the ensemble mean spectrum itself,
            # always ADDED (never "replaces" anything, since it has no
            # single source spectrum of its own).
            extra_outputs = []
            if settings.get('include_mean_spectrum'):
                mean_x, mean_y, source_labels = self.manager.get_mean_spectrum()
                if mean_x is not None:
                    base_name = f"Mean_of_{len(source_labels)}_spectra"
                    mean_name = base_name
                    bump = 1
                    while mean_name in all_labels:
                        mean_name = f'{base_name}_{bump}'
                        bump += 1
                    all_labels.add(mean_name)
                    mean_spectrum = {
                        'x_scale': mean_x.copy(),
                        'y_scale': mean_y.copy(),
                        'label': mean_name,
                        'metadata': {
                            'creation_method': 'mean_centering_ensemble_mean',
                            'source_spectra': source_labels,
                            'source_spectra_count': len(source_labels),
                            'creation_timestamp': datetime.now().isoformat(),
                            'unique_id': str(uuid.uuid4()),
                        },
                    }
                    extra_outputs.append(mean_spectrum)

            if add_as_new:
                # Suffix-style unique naming, matching X-axis Unit
                # Conversion / Normalization — never reuse the source
                # label, since "add as new" appends alongside the
                # untouched original.
                renamed = []
                for spec in centered_spectra:
                    base_name = f"{spec['label']}_meanCentered"
                    new_name = base_name
                    suffix = 1
                    while new_name in all_labels:
                        new_name = f'{base_name}_{suffix}'
                        suffix += 1
                    all_labels.add(new_name)
                    spec = dict(spec)
                    spec['label'] = new_name
                    # Give the new copy its own identity — dict(spec) is a
                    # shallow copy, so without this the copy would still
                    # share the source spectrum's unique_id, and selecting
                    # the ORIGINAL by identity later would silently sweep
                    # in this copy too (same fix as every other "Add as
                    # New" commit in this codebase).
                    spec['metadata'] = dict(spec.get('metadata') or {})
                    spec['metadata']['unique_id'] = str(uuid.uuid4())
                    renamed.append(spec)
                centered_spectra = renamed
                output_spectra = current_state + centered_spectra + extra_outputs
            else:
                centered_labels = {s['label'] for s in centered_spectra}
                output_spectra = [s for s in current_state if s['label'] not in centered_labels]
                output_spectra.extend(centered_spectra)
                output_spectra.extend(extra_outputs)

            self.oc.operations_manager.apply_operation(
                "Mean-Center Spectra (Dataset)", settings, selected_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    selected_spectra, centered_spectra + extra_outputs,
                    operation_name="Mean-Center Spectra (Dataset)",
                    pre_state=current_state,
                )

            if progress is not None:
                progress.setLabelText("Updating spectrum list…")
                QApplication.processEvents()

            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

            highlight_ids = {
                spectrum_key(s) for s in (
                    (selected_spectra if add_as_new else centered_spectra) + extra_outputs
                )
            }
            self.oc._rebuild_spectra_list_with_selection(highlight_ids)

            self.controller.selected_spectra = (
                (selected_spectra if add_as_new else centered_spectra)
            )

            if progress is not None:
                progress.setLabelText("Redrawing plot…")
                QApplication.processEvents()
            try:
                self.controller.plot_spectra(
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None
                )
            except Exception as exc:
                logger.error('Error plotting after mean-centering: %s', exc)
        finally:
            if progress is not None:
                progress.close()

        n = len(centered_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in centered_spectra)
            message = f'Added {n} new {noun}: {new_names}.'
        else:
            message = f'Replaced {n} {noun} with their mean-centered result.'
        if extra_outputs:
            message += f" Also added the ensemble mean spectrum '{extra_outputs[0]['label']}'."
        return True, message

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------
    def show_dialog(self, selected_spectra=None, commit_callback=None):
        """Open the Mean-Center Spectra (Dataset) dialog and return the
        settings shown, or None if cancelled/no valid selection."""
        from src.views.dialogs.data_analysis.mean_centering_dialog import MeanCenteringDialog
        from PyQt5.QtWidgets import QMessageBox

        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                'No spectra selected',
                'Please select two or more spectra to mean-center.'
            )
            return None

        dialog = MeanCenteringDialog(
            parent=self.controller.view,
            current_settings=dict(self._last_settings),
            controller=self.controller,
            selected_spectra=selected_spectra,
            commit_callback=commit_callback,
        )
        dialog.exec_()
        settings = dialog.get_settings()
        self._last_settings = dict(settings)
        return settings

    def show_parameters_dialog(self):
        """Convenience wrapper used by OperationsController.
        Returns True if the dialog was accepted."""
        selected = self.controller.spectrum_selector.get_selected_spectra()
        return self.show_dialog(selected) is not None

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------
    def apply_centering_to_spectra(self, settings, spectra=None, progress_callback=None):
        """Mean-center *spectra* with *settings* and return the result
        list. If *spectra* is None the currently selected spectra are
        used.

        progress_callback: optional callable, passed straight through to
        MeanCenteringManager.compute_centered_spectra(). None (the
        default) — no change from before.
        """
        if spectra is None:
            spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not spectra:
            return []

        valid_spectra = [
            s for s in spectra
            if len(s.get('x_scale', [])) > 0 and len(s.get('y_scale', [])) > 0
        ]
        if not valid_spectra:
            logger.debug("No valid (non-empty) spectra for mean-centering.")
            return []

        return self.manager.compute_centered_spectra(valid_spectra, settings, progress_callback=progress_callback)

    def update_settings(self, settings):
        self.manager.update_settings(settings)
