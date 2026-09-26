
# src/controllers/data_analysis/spectral_range_controller.py

import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.spectral_range_manager import SpectralRangeManager
from src.modules.data_analysis.spectrum_utils import SpectrumStatisticsCalculator
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key
import numpy as np

logger = get_logger(__name__)

class SpectralRangeController:
    def __init__(self, main_controller):
        """
        Initialize the SpectralRangeController.
        
        Args:
            main_controller: Reference to MainController instance
        """
        self.controller = main_controller
        self.manager = SpectralRangeManager()
        self.last_selection_hash = None  # Track selection changes
        self.stats_calculator = SpectrumStatisticsCalculator(self.manager)

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as SVDBackgroundController.oc
        / BaselineCorrectionController.oc / SNIPBaselineController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from OperationsController.commit_data_range,    #
    # unchanged in behavior, as part of giving every operation its own    #
    # dedicated controller instead of OperationsController holding all    #
    # of them directly. Internal references to OperationsController's own #
    # state now go through self.oc instead of self directly; sc           #
    # (previously fetched via main_controller, since this method used to  #
    # live outside this class) is simply self now.                        #
    # ------------------------------------------------------------------ #

    def commit_data_range(self, settings, add_as_new, selected_spectra):
        """Commit the Data range operation directly, called by the
        dialog's own Apply / Add as New buttons rather than through the
        generic Run dispatch. Add as New uses suffix-style unique naming
        ('<label>_range', bumped on collision), matching Normalization
        and Interactive Subtraction, rather than the older generic
        '<prefix>_<label>' convention used by the old, now-removed,
        generic add-as-new helper.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra:
            return False, 'No spectra selected in the main window.'

        has_ranges = bool(settings.get('ranges'))
        has_limits = settings.get('x_min') is not None and settings.get('x_max') is not None
        if not has_ranges and not has_limits and not settings.get('apply_linearization'):
            return False, (
                "Nothing to apply.\n\n"
                "Define at least one range, set an X-axis limit, or enable "
                "linearization first."
            )

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "Data Range",
            f"Applying data range to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            try:
                processed_spectra = self.apply_settings_to_spectra(settings, selected_spectra)
            except Exception as e:
                return False, f'Error applying data range: {e}'

            if not processed_spectra:
                return False, (
                    'Failed to process the selected spectra — the chosen range '
                    'may exclude all data points.'
                )

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                # Suffix-style unique naming, matching the Normalization and
                # Interactive Subtraction commits — never reuse the source
                # label, since "add as new" appends alongside the untouched
                # original.
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in processed_spectra:
                    base_name = f"{spec['label']}_range"
                    new_name = base_name
                    suffix = 1
                    while new_name in all_labels:
                        new_name = f'{base_name}_{suffix}'
                        suffix += 1
                    all_labels.add(new_name)
                    spec = dict(spec)
                    spec['label'] = new_name
                    # Give the new copy its own identity. Without this it
                    # silently shares the source spectrum's unique_id (dict(spec)
                    # is a shallow copy, and metadata is the SAME dict object as
                    # the source's unless replaced here) — meaning selecting the
                    # ORIGINAL by label later would also sweep in this copy via
                    # the ID-based matching fallback in
                    # _get_current_state_for_selected_spectra(), silently
                    # re-processing spectra that were never actually selected.
                    spec['metadata'] = dict(spec.get('metadata') or {})
                    spec['metadata']['unique_id'] = str(uuid.uuid4())
                    renamed.append(spec)
                processed_spectra = renamed
                output_spectra = current_state + processed_spectra
            else:
                processed_labels = {s['label'] for s in processed_spectra}
                output_spectra = [s for s in current_state if s['label'] not in processed_labels]
                output_spectra.extend(processed_spectra)

            self.oc.operations_manager.apply_operation(
                "Data range", settings, selected_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    selected_spectra, processed_spectra,
                    operation_name="Data range",
                    pre_state=current_state,
                )

            if progress is not None:
                progress.setLabelText("Updating spectrum list\u2026")
                QApplication.processEvents()

            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

            highlight_ids = {
                spectrum_key(s) for s in (selected_spectra if add_as_new else processed_spectra)
            }
            self.oc._rebuild_spectra_list_with_selection(highlight_ids)

            self.controller.selected_spectra = (
                selected_spectra if add_as_new else processed_spectra
            )
            self.oc._redraw_after_operation(progress, "data range")
        finally:
            if progress is not None:
                progress.close()

        n = len(processed_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in processed_spectra)
            message = f'Added {n} new {noun}: {new_names}.'
        else:
            message = f'Replaced {n} {noun} with the range-restricted result.'
        return True, message


    def _get_selection_hash(self, spectra):
        """Create a hash to identify unique selections."""
        if not spectra:
            return None
        return ','.join(sorted(spectrum['label'] for spectrum in spectra))
        
    def get_default_range(self):
        """Get default x_min and x_max from selected spectra."""
        selected_spectra = self.controller.spectrum_selector.get_selected_spectra()
        return self.manager.get_default_range(selected_spectra)
    
    def _have_identical_settings(self, spectra):
        """Check if all selected spectra have identical settings."""
        return self.manager.have_identical_settings(spectra)
        
    def get_spectrum_settings(self, spectrum):
        """Get all settings for a specific spectrum."""
        return self.manager.get_spectrum_settings(spectrum)
    
    def apply_ranges_to_spectra(self, input_spectra=None):
        """
        Apply the current range/linearization/limit settings to spectra.

        Args:
            input_spectra: Optional list of spectra to process. If None, uses
                           the main window's current selection.

        Returns:
            List of processed spectra (new, independent copies).

        All the actual range/linearization/limit math lives in exactly one
        place now — SpectralRangeManager.apply_ranges_to_spectra — rather
        than being duplicated here. This method used to carry its own full
        second copy of that logic, which behaved subtly differently from
        the manager's copy (e.g. only the manager's version mutated its
        input spectra in place) and could drift further out of sync over
        time. See the Data Range audit.
        """
        if input_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()
        else:
            selected_spectra = input_spectra

        return self.manager.apply_ranges_to_spectra(selected_spectra)

    def show_dialog(self, selected_spectra=None, commit_callback=None, current_settings=None):
        """Show the spectral range dialog pre-populated with the last settings shown.

        *current_settings*, if given (a dict shaped like get_settings()'s return
        value), takes priority over the manager's committed state for
        pre-population. This matters because the manager only updates when
        Apply / Add as New actually runs (see apply_settings_to_spectra) —
        without this, settings tweaked in the dialog but never committed (the
        user just clicked Close) would be forgotten the next time the dialog
        opens, unlike Normalization, whose current_parameters cache in
        OperationsController plays the same role. Falls back to the manager's
        state when no cache is available yet (e.g. the very first open).

        *commit_callback*, if given, is passed straight through to the dialog
        (OperationsController.commit_data_range) so its own Apply / Add as New
        buttons can commit directly — there's no separate Run step for this
        operation any more. Apply / Add as New no longer map to QDialog's
        accept/reject, so this method always returns whatever get_settings()
        reports once the dialog closes (via Close or the window's close box),
        purely so the caller can remember what was last shown.
        """
        from src.views.dialogs.data_analysis.spectral_range_dialog import SpectralRangeDialog

        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self.controller.view,
                'No spectra selected',
                'Please select one or more spectra to define the data range.'
            )
            return None

        default_x_min, default_x_max = self.get_default_range()

        # Prune settings left behind by spectra that no longer exist —
        # otherwise a newly imported spectrum that happens to reuse an old
        # label would be compared against stale, unrelated leftover
        # settings (see prune_to_current_spectra docstring).
        self.manager.prune_to_current_spectra(self.controller.original_spectra)

        # Check per-spectrum consistency for UI hints (differ warnings)
        (identical_all, identical_ranges, common_ranges,
         identical_modes, common_mode,
         identical_steps, common_step,
         identical_limits, common_x_min, common_x_max) = self._have_identical_settings(selected_spectra)

        if current_settings:
            current_ranges = list(current_settings.get('ranges', []))
            is_exclude_mode = current_settings.get('is_exclude_mode', False)
            x_step = current_settings.get('x_step', 1.0)
            apply_linearization = current_settings.get('apply_linearization', False)
            x_min = current_settings.get('x_min')
            x_max = current_settings.get('x_max')
        else:
            current_ranges = list(self.manager.current_ranges)
            is_exclude_mode = self.manager.is_exclude_mode
            x_step = self.manager.x_step
            apply_linearization = self.manager.apply_linearization
            x_min = self.manager.x_min
            x_max = self.manager.x_max

        dialog = SpectralRangeDialog(
            self.controller.view,
            current_ranges=current_ranges,
            is_exclude_mode=is_exclude_mode,
            x_step=x_step,
            apply_linearization=apply_linearization,
            x_min=x_min,
            x_max=x_max,
            ranges_differ=not identical_ranges and len(selected_spectra) > 0,
            steps_differ=not identical_steps and len(selected_spectra) > 0,
            limits_differ=not identical_limits and len(selected_spectra) > 0,
            controller=self.controller,
            selected_spectra=selected_spectra,
            commit_callback=commit_callback,
        )
        dialog.spectral_range_controller = self
        dialog.setup_reset_buttons(default_x_min, default_x_max)

        # Apply / Add as New commit directly via commit_callback (see
        # SpectralRangeDialog._on_commit_clicked) instead of going through
        # QDialog's accept(). Close maps to reject(). Either way, just run
        # the dialog and report back whatever settings it was last showing.
        dialog.exec_()
        return dialog.get_settings()

    def apply_settings_to_spectra(self, settings, spectra):
        """Apply *settings* (as returned by SpectralRangeDialog.get_settings())
        directly to *spectra*, independent of whatever the manager happened to
        hold before this call — mirrors NormalizationController's
        apply_normalization_to_spectra() so each commit from the dialog's own
        Apply / Add as New buttons is self-contained.

        *spectra* are not mutated; a list of processed spectrum dicts is
        returned (or [] if *spectra* is empty).
        """
        if not spectra:
            return []

        self.manager.update_settings(settings)

        # apply_ranges_to_spectra() reads the per-spectrum range/step/mode
        # overrides below (falling back to the manager's just-updated common
        # values), so every spectrum in this commit gets the exact same
        # settings just shown in the dialog.
        ranges = list(self.manager.current_ranges)
        for spectrum in spectra:
            key = self.manager._key_for(spectrum)
            self.manager.spectrum_ranges[key] = list(ranges)
            self.manager.spectrum_exclude_modes[key] = self.manager.is_exclude_mode
            self.manager.spectrum_x_steps[key] = self.manager.x_step
            self.manager.spectrum_x_mins[key] = self.manager.x_min
            self.manager.spectrum_x_maxs[key] = self.manager.x_max

        return self.apply_ranges_to_spectra(spectra)

    def update_settings(self, settings):
        """Update settings in the manager."""
        self.manager.update_settings(settings)

    # Property accessors to maintain compatibility with existing code
    @property
    def current_ranges(self):
        return self.manager.current_ranges
        
    @current_ranges.setter
    def current_ranges(self, value):
        self.manager.current_ranges = value
        
    @property
    def is_exclude_mode(self):
        return self.manager.is_exclude_mode
        
    @is_exclude_mode.setter
    def is_exclude_mode(self, value):
        self.manager.is_exclude_mode = value
        
    @property
    def x_step(self):
        return self.manager.x_step
        
    @x_step.setter
    def x_step(self, value):
        self.manager.x_step = value
        
    @property
    def x_min(self):
        return self.manager.x_min
        
    @x_min.setter
    def x_min(self, value):
        self.manager.x_min = value
        
    @property
    def x_max(self):
        return self.manager.x_max
        
    @x_max.setter
    def x_max(self, value):
        self.manager.x_max = value
        
    @property
    def apply_linearization(self):
        return self.manager.apply_linearization
        
    @apply_linearization.setter
    def apply_linearization(self, value):
        self.manager.apply_linearization = value
        
    @property
    def spectrum_ranges(self):
        return self.manager.spectrum_ranges
        
    @property
    def spectrum_exclude_modes(self):
        return self.manager.spectrum_exclude_modes
        
    @property
    def spectrum_x_steps(self):
        return self.manager.spectrum_x_steps
        
    @property
    def spectrum_x_mins(self):
        return self.manager.spectrum_x_mins
        
    @property
    def spectrum_x_maxs(self):
        return self.manager.spectrum_x_maxs