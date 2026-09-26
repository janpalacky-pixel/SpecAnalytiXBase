# src/controllers/data_analysis/xaxis_unit_conversion_controller.py
"""
Controller for the X-axis Unit Conversion operation — converts a
spectrum's x-axis between wavelength (nm), wavenumber (cm^-1), energy
(eV), and frequency (Hz). Follows the same pattern as
CDUnitConversionController / XAxisAlignmentController:
  • show_dialog()                   – open the parameter dialog, persist settings
  • commit_xaxis_unit_conversion()  – Apply / Add as New, called by the dialog's
                                       own buttons via commit_callback
  • apply_conversion_to_spectra()   – delegate computation to the manager
  • update_settings()               – forward settings to the manager
"""

import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.xaxis_unit_conversion_manager import (
    XAxisUnitConversionManager, UNIT_LABELS,
)
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)

# Filesystem/label-safe suffix used for "Add as New" naming, one per
# target unit — so '<label>_wavenumber', '<label>_energyEV',
# '<label>_frequencyHz', '<label>_wavelengthNm' indicate at a glance
# which axis a copied spectrum ended up on, consistent with every other
# operation's Add as New naming elsewhere in this app (e.g.
# '_baseline_corrected', '_normalized').
_SUFFIX_BY_UNIT = {
    'nm': 'wavelengthNm',
    'cm-1': 'wavenumber',
    'eV': 'energyEV',
    'Hz': 'frequencyHz',
}


class XAxisUnitConversionController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = XAxisUnitConversionManager()
        self._last_settings = {}

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic needs — same pattern as CDUnitConversionController.oc /
        XAxisAlignmentController.oc / NormalizationController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    def commit_xaxis_unit_conversion(self, settings, add_as_new, selected_spectra):
        """Commit the x-axis unit conversion, called by the dialog's own
        Apply / Add as New buttons rather than through the generic Run
        dispatch.

        Add as New uses suffix-style unique naming ('<label>_wavenumber' /
        '_energyEV' / '_frequencyHz' / '_wavelengthNm' depending on the
        chosen target unit, bumped on collision), matching every other
        refined operation in this app.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra:
            return False, 'Please select one or more spectra to apply the operation.'

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "X-axis Unit Conversion",
            f"Converting {n_spectra} spectra…",
            n_spectra,
        )
        try:
            try:
                converted_spectra = self.apply_conversion_to_spectra(
                    settings, selected_spectra,
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
                )
            except ValueError as exc:
                # x-axis values <= 0 for the chosen source unit — a clear,
                # actionable message from
                # XAxisUnitConversionManager.validate_parameters, not a
                # raw traceback.
                return False, str(exc)
            except Exception as exc:
                logger.exception('Unexpected error in x-axis unit conversion')
                return False, f'An unexpected error occurred: {exc}'

            if not converted_spectra:
                return False, 'Failed to convert any of the selected spectra.'

            suffix = _SUFFIX_BY_UNIT.get(settings.get('to_unit'), 'converted')
            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in converted_spectra:
                    base_name = f"{spec['label']}_{suffix}"
                    new_name = base_name
                    bump = 1
                    while new_name in all_labels:
                        new_name = f'{base_name}_{bump}'
                        bump += 1
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
                converted_spectra = renamed
                output_spectra = current_state + converted_spectra
            else:
                converted_labels = {s['label'] for s in converted_spectra}
                output_spectra = [s for s in current_state if s['label'] not in converted_labels]
                output_spectra.extend(converted_spectra)

            self.oc.operations_manager.apply_operation(
                'X-axis Unit Conversion', settings, selected_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    selected_spectra, converted_spectra,
                    operation_name='X-axis Unit Conversion',
                    pre_state=current_state,
                )

            if progress is not None:
                progress.setLabelText("Updating spectrum list…")
                QApplication.processEvents()

            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

            highlight_ids = {
                spectrum_key(s) for s in (selected_spectra if add_as_new else converted_spectra)
            }
            self.oc._rebuild_spectra_list_with_selection(highlight_ids)

            self.controller.selected_spectra = (
                selected_spectra if add_as_new else converted_spectra
            )

            self.oc._redraw_after_operation(progress, "x-axis unit conversion")
        finally:
            if progress is not None:
                progress.close()

        n = len(converted_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        to_label = UNIT_LABELS.get(settings.get('to_unit'), settings.get('to_unit'))
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in converted_spectra)
            message = f'Added {n} new {noun} ({to_label}): {new_names}.'
        else:
            message = f'Replaced {n} {noun} with x-axis converted to {to_label}.'
        return True, message

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------
    def show_dialog(self, selected_spectra=None, commit_callback=None):
        """Open the X-axis Unit Conversion dialog and return the settings
        shown, or None if cancelled/no valid selection."""
        from src.views.dialogs.data_analysis.xaxis_unit_conversion_dialog import XAxisUnitConversionDialog
        from PyQt5.QtWidgets import QMessageBox

        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view,
                'No spectra selected',
                'Please select one or more spectra for x-axis unit conversion.'
            )
            return None

        dialog = XAxisUnitConversionDialog(
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
    def apply_conversion_to_spectra(self, settings, spectra=None, progress_callback=None):
        """Convert *spectra* with *settings* and return the result list.
        If *spectra* is None the currently selected spectra are used.

        progress_callback: optional callable, passed straight through to
        XAxisUnitConversionManager.convert_spectra(). None (the
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
            logger.debug("No valid (non-empty) spectra for x-axis unit conversion.")
            return []

        return self.manager.convert_spectra(valid_spectra, settings, progress_callback=progress_callback)

    def update_settings(self, settings):
        self.manager.update_settings(settings)
