# src/controllers/data_analysis/normalization_controller.py

import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.normalization_manager import NormalizationManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)


class NormalizationController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = NormalizationManager()

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as SVDBackgroundController.oc
        / BaselineCorrectionController.oc / SpikeRemovalController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------
    # Commit — moved here from OperationsController.commit_normalization,
    # unchanged in behavior, as part of giving every operation its own
    # dedicated controller instead of OperationsController holding all
    # of them directly. Internal references to OperationsController's own
    # state now go through self.oc instead of self directly; nc
    # (previously fetched via main_controller, since this method used to
    # live outside this class) is simply self now.
    # ------------------------------------------------------------------

    def commit_normalization(self, settings, add_as_new, selected_spectra):
        """Commit normalization directly, called by the dialog's own
        Apply / Add as New buttons rather than through the generic Run
        dispatch. Add as New now uses suffix-style unique naming
        ('<label>_normalized', bumped on collision) for consistency with
        the Spectral Calculator and Interactive Subtraction, rather than
        the older '<prefix>_<label>' convention.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra:
            return False, 'No spectra selected in the main window.'

        mode = settings.get('normalization_mode')
        mode_needs_region = not (
            mode == 'reference'
            or (mode == 'msc' and not settings.get('msc_use_region', False))
        )
        if mode_needs_region and not settings.get('x_ranges'):
            return False, (
                "No normalization region has been selected.\n\n"
                "Define at least one region in the dialog first."
            )

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "Normalization",
            f"Applying normalization to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            try:
                normalized_spectra = self.apply_normalization_to_spectra(
                    settings, selected_spectra,
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
                )
            except Exception as e:
                return False, f'Error applying normalization: {e}'

            if not normalized_spectra:
                return False, 'Failed to normalize the selected spectra.'

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                # Suffix-style unique naming, matching the Spectral Calculator
                # and Interactive Subtraction — never reuse the source label,
                # since "add as new" appends alongside the untouched original.
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in normalized_spectra:
                    base_name = f"{spec['label']}_normalized"
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
                normalized_spectra = renamed
                output_spectra = current_state + normalized_spectra
            else:
                normalized_labels = {s['label'] for s in normalized_spectra}
                output_spectra = [s for s in current_state if s['label'] not in normalized_labels]
                output_spectra.extend(normalized_spectra)

            self.oc.operations_manager.apply_operation(
                "Normalization", settings, selected_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    selected_spectra, normalized_spectra,
                    operation_name="Normalization",
                    pre_state=current_state,
                )

            if progress is not None:
                progress.setLabelText("Updating spectrum list\u2026")
                QApplication.processEvents()

            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

            highlight_ids = {
                spectrum_key(s) for s in (selected_spectra if add_as_new else normalized_spectra)
            }
            self.oc._rebuild_spectra_list_with_selection(highlight_ids)

            self.controller.selected_spectra = (
                selected_spectra if add_as_new else normalized_spectra
            )
            if progress is not None:
                progress.setLabelText("Redrawing plot\u2026")
                QApplication.processEvents()
            try:
                self.controller.plot_spectra(
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None
                )
            except ValueError as e:
                logger.error(f"Error plotting after normalization: {e}")
        finally:
            if progress is not None:
                progress.close()

        n = len(normalized_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in normalized_spectra)
            message = f'Added {n} new {noun}: {new_names}.'
        else:
            message = f'Replaced {n} {noun} with the normalized result.'
        # MSC/SVD (combine multiple spectra into one matrix) and Reference
        # mode (point-wise divides against another spectrum) all require a
        # shared x-axis — a spectrum that doesn't match is left unchanged
        # rather than silently compared against unrelated wavenumbers; see
        # NormalizationManager.skipped_labels.
        if getattr(self.manager, 'skipped_labels', None):
            sn = len(self.manager.skipped_labels)
            snoun = 'spectrum' if sn == 1 else 'spectra'
            skipped_names = self.oc._format_names_for_message(self.manager.skipped_labels)
            message += (f'\n\u26a0 {sn} {snoun} left unchanged (x-axis doesn\'t match): '
                        f'{skipped_names}.')
        return True, message

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------
    def get_default_range(self):
        selected = self.controller.spectrum_selector.get_selected_spectra()
        return self.manager.get_default_range(selected)

    def show_dialog(self, selected_spectra=None):
        """Show the normalization dialog and return settings dict, or None if cancelled.

        The dialog is always pre-populated with the manager's current state so
        that previously chosen settings are visible to the user regardless of
        whether the spectra selection in the main window has changed since the
        last OK was pressed (Option 2: remember & always show last-used settings).
        """
        from src.views.dialogs.data_analysis.normalization_dialog import NormalizationDialog

        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self.controller.view,
                'No spectra selected',
                'Please select one or more spectra for normalization.'
            )
            return None

        # Use saved x_ranges when available; empty on first open so the user
        # is forced to define a region deliberately (scientific tool — no silent defaults).
        saved_ranges = list(self.manager.x_ranges)

        # Build current_settings as a complete snapshot of the manager's state.
        # Every field that the dialog reads must be present here so the UI always
        # reflects what was last saved — even after the main-window selection changes.
        current_settings = {
            'normalization_mode':        getattr(self.manager, 'normalization_mode', 'max_peak'),
            'x_ranges':                  saved_ranges,
            'is_exclude_mode':           getattr(self.manager, 'is_exclude_mode', False),
            # Legacy scalar pair — None when no ranges saved so the dialog's
            # elif fallback is skipped and no spurious 0-100 region is created.
            'x_min':                     saved_ranges[0][0]  if saved_ranges else None,
            'x_max':                     saved_ranges[-1][1] if saved_ranges else None,
            'reference_spectrum_index':  getattr(self.manager, 'reference_spectrum_index', 0),
            'snv_center':                getattr(self.manager, 'snv_center', True),
            'percentile_value':          getattr(self.manager, 'percentile_value', 95.0),
            'target_mode':                getattr(self.manager, 'target_mode', 'standard'),
            'target_value':              getattr(self.manager, 'target_value', 1.0),
        }

        dialog = NormalizationDialog(
            parent=self.controller.view,
            current_settings=current_settings,
            controller=self.controller,
            selected_spectra=selected_spectra,
            commit_callback=self.commit_normalization,
        )

        if dialog.exec_() == dialog.Accepted:
            settings = dialog.get_settings()
            self.manager.update_settings(settings)
            return settings

        return None

    def show_parameters_dialog(self):
        """Convenience wrapper used by operations_controller.
        Returns True if the dialog was accepted."""
        selected = self.controller.spectrum_selector.get_selected_spectra()
        return self.show_dialog(selected) is not None

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------
    def apply_normalization_to_spectra(self, settings, spectra=None, progress_callback=None):
        """Apply normalization with *settings* to *spectra*.

        If *spectra* is None the currently selected spectra are used
        (original behaviour preserved for callers that don't pass spectra).
        Returns a list of normalized spectrum dicts.

        progress_callback: optional callable, passed straight through to
        NormalizationManager.normalize_spectra() — see that method's own
        docstring. None (the default) — no change from before.
        """
        if spectra is None:
            spectra = self.controller.spectrum_selector.get_selected_spectra()

        if not spectra:
            return []

        valid = []
        for s in spectra:
            if len(s['x_scale']) == 0 or len(s['y_scale']) == 0:
                logger.warning(
                    f"Skipping empty spectrum '{s['label']}' "
                    f"(x: {len(s['x_scale'])}, y: {len(s['y_scale'])})"
                )
                continue

            # Deep-copy mutable arrays; share everything else
            sc = {}
            for key, val in s.items():
                if key in ('x_scale', 'y_scale', 'metadata'):
                    sc[key] = val.copy() if hasattr(val, 'copy') else val
                else:
                    sc[key] = val

            valid.append(sc)

        if not valid:
            logger.debug('No valid spectra for normalization')
            return []

        return self.manager.normalize_spectra(valid, settings, progress_callback=progress_callback)

    def update_settings(self, settings):
        self.manager.update_settings(settings)
