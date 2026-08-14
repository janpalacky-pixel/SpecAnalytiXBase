# src/controllers/data_analysis/snip_baseline_controller.py

import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.snip_baseline_manager import SNIPBaselineManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)


class SNIPBaselineController:
    """
    Controller for the SNIP Baseline correction operation.

    Same thin-controller pattern as every other extracted controller in
    this codebase — owns a persistent SNIPBaselineManager instance and
    holds the commit logic that used to live directly inside
    OperationsController.commit_snip_baseline. This operation previously
    had no dedicated controller at all: the dialog and the Run dispatch
    both created a fresh SNIPBaselineManager() inline on every call.
    SNIPBaselineManager has no persistent per-call state that would make
    reusing one instance across calls unsafe — apply_correction() resets
    its own skipped_labels at the start of every call (and __init__ sets
    the same starting value) — so a single owned instance is behaviorally
    identical to the previous "fresh instance every time" approach, just
    consistent with how every other operation in this app is structured.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = SNIPBaselineManager()

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as SVDBackgroundController.oc
        / BaselineCorrectionController.oc / AutomatedBaselineController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from OperationsController.commit_snip_baseline, #
    # unchanged in behavior, as part of giving every operation its own    #
    # dedicated controller instead of OperationsController holding all    #
    # of them directly. This was the last of the 13 original commit_<x>() #
    # methods still living in OperationsController.                       #
    # ------------------------------------------------------------------ #

    def commit_snip_baseline(self, settings, add_as_new, selected_spectra):
        """Commit the SNIP Baseline operation directly, called by the
        dialog's own Apply / Add as New buttons rather than through the
        generic Run dispatch.

        Add as New uses suffix-style unique naming ('<label>_baseline_snip',
        bumped on collision), matching the other refined operations.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra:
            return False, 'Please select one or more spectra to apply SNIP baseline correction.'

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "SNIP Baseline",
            f"Applying SNIP baseline correction to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            try:
                processed_spectra = self.manager.apply_correction(
                    selected_spectra, settings,
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
                )
            except Exception as exc:
                return False, f'Error applying SNIP baseline correction: {exc}'

            if not processed_spectra:
                return False, 'Failed to apply SNIP baseline correction.'

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in processed_spectra:
                    base_name = f"{spec['label']}_baseline_snip"
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
                'SNIP Baseline', settings, selected_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    selected_spectra, processed_spectra,
                    operation_name='SNIP Baseline',
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

            if progress is not None:
                # Now the dominant cost, since the fixes above — redrawing
                # is genuinely the slow part left, not an implementation
                # bug the way the previous per-item selection cost was.
                progress.setLabelText("Redrawing plot\u2026")
                QApplication.processEvents()
            try:
                self.controller.plot_spectra(
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None
                )
            except Exception as exc:
                logger.error(f"Error plotting after SNIP baseline correction: {exc}")
        finally:
            if progress is not None:
                progress.close()

        n = len(processed_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in processed_spectra)
            message = f'Added {n} new {noun}: {new_names}.'
        else:
            message = f'Replaced {n} {noun} with the baseline-corrected result.'
        # apply_correction() silently leaves any spectrum with fewer than 3
        # points unchanged (SNIP can't run on it at all) while still
        # counting it in n above — same fix as commit_automated_baseline.
        if self.manager.skipped_labels:
            sn = len(self.manager.skipped_labels)
            snoun = 'spectrum' if sn == 1 else 'spectra'
            skipped_names = self.oc._format_names_for_message(self.manager.skipped_labels)
            message += (f'\n\u26a0 {sn} {snoun} skipped (too few data points, left '
                        f'unchanged): {skipped_names}.')
        return True, message
