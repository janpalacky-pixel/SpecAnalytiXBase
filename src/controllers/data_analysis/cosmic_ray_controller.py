# src/controllers/data_analysis/cosmic_ray_controller.py

import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.cosmic_ray_manager import CosmicRayManager, AxisMismatchError
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)


class CosmicRayController:
    """
    Controller for cross-spectrum cosmic ray detection.

    Bridges CosmicRayManager (the algorithm) with the dialog and the
    OperationsController commit pipeline — mirrors SpikeRemovalController's
    role. Simpler than that one, deliberately: this operation has no
    per-spectrum manual-editing state to persist between dialog sessions
    (no accept/reject/add-a-spike bookkeeping) — just a single threshold
    value, which the dialog's own get_settings()/current_settings
    round-trip through OperationsController.current_parameters already
    handles, the same way Data Range or Normalization's settings persist.

    Before this class existed, both CosmicRayDialog and
    OperationsController.commit_cosmic_ray_removal independently created
    their own fresh CosmicRayManager() instance inline — meaning the
    detection shown in the dialog's live preview and the detection
    actually used at commit time were two entirely separate computations
    that happened to usually agree, rather than provably the same one.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = CosmicRayManager()

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as SVDBackgroundController.oc
        / BaselineCorrectionController.oc / ResolutionEnhancementController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from OperationsController.commit_cosmic_ray_removal, #
    # unchanged in behavior, as part of giving every operation its own    #
    # dedicated controller instead of OperationsController holding all    #
    # of them directly. Internal references to OperationsController's own #
    # state now go through self.oc instead of self directly; crc          #
    # (previously fetched via main_controller, since this method used to  #
    # live outside this class) is simply self now.                        #
    # ------------------------------------------------------------------ #

    def commit_cosmic_ray_removal(self, settings, add_as_new, selected_spectra):
        """Commit the Cosmic ray removal operation directly, called by the
        dialog's own Apply / Add as New buttons rather than through the
        generic Run dispatch.

        Add as New uses suffix-style unique naming ('<label>_cosmic_ray',
        bumped on collision), matching the other refined operations.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra or len(selected_spectra) < 2:
            return False, 'Cosmic ray removal requires at least 2 selected spectra.'

        threshold = settings.get('threshold', 10.0)

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "Cosmic Ray Removal",
            f"Applying cosmic ray removal to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            processed_spectra, error = self.apply_removal(
                settings, selected_spectra,
                progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
            )
            if error is not None:
                # Most commonly an axis mismatch, refused rather than silently
                # resampled (see CosmicRayManager._build_matrix) — but could
                # also be any other unexpected failure apply_removal() caught
                # and converted into a message.
                return False, f'Error applying cosmic ray removal: {error}'

            if not processed_spectra:
                return False, 'Failed to apply cosmic ray removal.'

            summary = self.get_summary(selected_spectra)
            total = summary['total_flagged_points']
            if total == 0:
                return False, (
                    'No cosmic rays were flagged with the current threshold.\n\n'
                    'Lower the threshold or check the Spectrum preview tab.'
                )

            # Only spectra that ACTUALLY had at least one point replaced count
            # as "affected" — apply_removal() returns one processed entry for
            # EVERY input spectrum regardless of whether anything was flagged
            # for it (an unaffected spectrum's entry is just an unmodified
            # copy). Using the unfiltered list here had two consequences:
            # (1) Operations History's "Affected Spectra" showed the entire
            # original selection (e.g. all 4675) instead of just the ~15
            # spectra actually corrected; (2) far more seriously, in "Add as
            # New" mode below, EVERY one of those spectra — including the
            # thousands with nothing flagged — was renamed and added as a
            # brand new spectrum, most of them exact duplicates of spectra
            # that already existed. Filtering here, once, fixes both: only
            # genuinely-corrected spectra get named/added/recorded as
            # affected; everything else in the dataset is left completely
            # alone (in Apply/replace mode, an untouched spectrum simply isn't
            # replaced at all, rather than being swapped for an unnecessary
            # identical copy).
            affected_labels = {lbl for lbl, cnt in summary['details'].items() if cnt > 0}
            processed_spectra = [s for s in processed_spectra if s['label'] in affected_labels]
            selected_spectra = [s for s in selected_spectra if s['label'] in affected_labels]

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in processed_spectra:
                    base_name = f"{spec['label']}_cosmic_ray"
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
                'Cosmic ray removal', settings, selected_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    selected_spectra, processed_spectra,
                    operation_name='Cosmic ray removal',
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
            self.oc._redraw_after_operation(progress, "cosmic ray removal")
        finally:
            if progress is not None:
                progress.close()

        n = len(processed_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in processed_spectra)
            message = f'Added {n} new {noun}: {new_names} ({total} point(s) corrected).'
        else:
            message = f'Replaced {n} {noun} — {total} point(s) corrected.'
        return True, message

    # ------------------------------------------------------------------ #
    # Dialog                                                               #
    # ------------------------------------------------------------------ #

    def show_interactive_dialog(self, spectra, current_settings=None, commit_callback=None):
        """Open the cross-spectrum cosmic ray detection dialog (modal).

        *commit_callback*, if given, is passed straight through to the
        dialog (OperationsController.commit_cosmic_ray_removal) so its own
        Apply / Add as New buttons can commit directly — there's no
        separate Run step for this operation.
        """
        from src.views.dialogs.data_analysis.cosmic_ray_dialog import CosmicRayDialog
        return CosmicRayDialog(
            parent=self.controller.view,
            spectra=spectra,
            controller=self,
            current_settings=current_settings,
            commit_callback=commit_callback,
        )

    def detect(self, spectra, threshold=None):
        """Run detection only (used by the dialog's live preview / heatmap).

        Returns (flagged_dict, error_message). error_message is None on
        success, or a user-facing string on failure (e.g. mismatched
        x-axes) — never raises, so callers can show the message directly
        without their own try/except around every call site.
        """
        try:
            flagged = self.manager.detect(spectra, threshold=threshold)
            return flagged, None
        except AxisMismatchError as exc:
            return {}, str(exc)

    # ------------------------------------------------------------------ #
    # Apply                                                                #
    # ------------------------------------------------------------------ #

    def apply_removal(self, settings, spectra, progress_callback=None):
        """Detect and replace cosmic rays.

        Returns (processed_spectra, error_message). error_message is None
        on success; processed_spectra is None on failure. Never raises —
        this is the method OperationsController.commit_cosmic_ray_removal
        calls, and it needs a clean (result, message) contract to turn
        straight into its own (success, message) return value.

        progress_callback: optional callable, passed straight through to
        CosmicRayManager.apply() — see that method's own docstring. None
        (the default) — no change from before.
        """
        threshold = settings.get('threshold', 10.0)
        replace_window = settings.get('replace_window', 0)
        try:
            processed = self.manager.apply(spectra, threshold=threshold,
                                            replace_window=replace_window,
                                            progress_callback=progress_callback)
        except AxisMismatchError as exc:
            return None, str(exc)
        except Exception as exc:
            logger.exception('Unexpected error in cosmic ray removal')
            return None, f'An unexpected error occurred: {exc}'
        return processed, None

    def get_summary(self, spectra):
        return self.manager.get_summary(spectra)
