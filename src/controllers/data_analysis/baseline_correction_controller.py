# src/controllers/data_analysis/baseline_correction_controller.py

import uuid
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.baseline_manager import BaselineManager
from src.views.dialogs.data_analysis.baseline_correction_dialog import BaselineCorrectionDialog
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key
from src.modules.utils.progress_utils import notify_progress

logger = get_logger(__name__)


class BaselineCorrectionController:
    """Controller for manual baseline correction."""

    def __init__(self, main_controller):
        self.controller         = main_controller
        self.manager            = BaselineManager()
        self.dialog             = None
        self.stored_corrections = {}
        self.operation_applied  = False

        # Reset baselines when new data is imported
        if hasattr(main_controller, 'import_controller'):
            ic = main_controller.import_controller
            if hasattr(ic, 'spectra_imported'):
                ic.spectra_imported.connect(self.reset_all_baselines)

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs (operations_manager, register_copy_operation,
        _show_busy_progress, _rebuild_spectra_list_with_selection,
        _format_names_for_message) — same pattern as
        SVDBackgroundController.oc / SpectralCalculatorController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from OperationsController.commit_manual_baseline, #
    # unchanged in behavior, as part of giving every operation its own    #
    # dedicated controller instead of OperationsController holding all    #
    # of them directly. Internal references to OperationsController's own #
    # state now go through self.oc instead of self directly; bc_controller #
    # (previously fetched via main_controller, since this method used to  #
    # live outside this class) is simply self now.                        #
    # ------------------------------------------------------------------ #

    def commit_manual_baseline(self, add_as_new, selected_spectra):
        """Commit the Manual baseline operation directly, called by the
        dialog's own Apply / Add as New buttons rather than through the
        generic Run dispatch.

        Unlike the settings-dict-driven operations, baseline points are
        kept directly in this controller's own manager (a long-lived
        singleton), so there's no separate "current_settings" cache to
        manage here — the manager IS the persisted state, already
        live-updated on every point add/remove.

        Add as New uses suffix-style unique naming ('<label>_baseline',
        bumped on collision). Only spectra that actually had baseline
        points defined are included in the result — selected spectra with
        no points are left untouched, rather than padding Add as New with
        identical duplicates.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        self.store_corrections()  # ensure the snapshot reflects the live manager state

        # self.manager is a single shared object for the whole session, not
        # scoped to any one operation — it can still hold entries left over
        # from elsewhere (e.g. points restored when jumping to a different
        # history step). Restrict to keys that are actually part of *this*
        # operation's selection, so a stale entry for some other spectrum
        # never leaks into what gets recorded here. Keyed by unique_id
        # (BaselineManager._key_for), not label — a rename between
        # selecting and committing must not disconnect a spectrum from its
        # own just-placed points, and an unrelated spectrum that happens to
        # share an old label must not silently inherit them either.
        selected_keys = {self.manager._key_for(s) for s in selected_spectra}
        affected_keys = {
            key for key, corr in self.stored_corrections.items()
            if corr['points'] and key in selected_keys
        }
        if not affected_keys:
            return False, (
                "No baseline points have been defined for any of the selected "
                "spectra.\n\nLeft-click on the plot to add at least 2 points "
                "for the spectrum you want to correct."
            )

        n_spectra = len(affected_keys)
        progress = self.oc._show_busy_progress(
            "Manual Baseline",
            f"Applying baseline correction to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            try:
                processed_spectra = self.apply_stored_corrections(
                    selected_spectra,
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
                )
            except Exception as exc:
                return False, f'Error applying baseline correction: {exc}'

            # Only spectra that actually had baseline points defined are
            # meaningfully "corrected" — keep the rest out of the result so Add
            # as New doesn't duplicate untouched spectra under new names.
            processed_spectra = [
                s for s in processed_spectra
                if self.manager._key_for(s) in affected_keys
            ]
            if not processed_spectra:
                return False, 'No baseline corrections were applied.'

            # Keep a reference to the actually-corrected spectra under their
            # ORIGINAL labels, before the Add as New branch below renames them
            # — register_copy_operation() needs this to correctly report which
            # spectra were copied FROM, not the full original selection.
            corrected_spectra = list(processed_spectra)

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in processed_spectra:
                    base_name = f"{spec['label']}_baseline"
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

            # Resolve back to each spectrum's current label for the
            # human-readable 'corrections' summary stored in params — display
            # only, not used as a lookup key anywhere downstream.
            params = {
                'corrections': self.get_corrections_info(selected_spectra, keys=affected_keys)
            }

            # Snapshot of points/fit-settings per spectrum, used by
            # IncrementalOperationsManager to restore baseline points when the
            # user jumps back to this step in the operation history. Keyed by
            # unique_id, matching BaselineManager's own keys, so
            # on_baseline_state_changed round-trips correctly even if a
            # spectrum gets renamed in between.
            baseline_state = {
                key: {
                    'points': corr['points'],
                    'type':   corr['fit_type'],
                    'order':  corr['poly_order'],
                }
                for key, corr in self.stored_corrections.items()
                if key in affected_keys
            }

            self.oc.operations_manager.apply_operation(
                # affected_spectra is processed_spectra (only the ones that
                # actually had baseline points and got corrected), not
                # selected_spectra (the full original selection). This is what
                # the Operations History "Spectra List" and the "Baseline
                # Points" viewer's tabs are built from — using the full
                # selection here was showing every selected spectrum, even
                # ones that were never touched because they had zero baseline
                # points defined, as if the operation had affected them too.
                'Manual baseline', params, processed_spectra,
                new_state_spectra=output_spectra,
                baseline_state=baseline_state,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    corrected_spectra, processed_spectra,
                    operation_name='Manual baseline',
                    pre_state=current_state,
                )

            # The correction has now been baked into the data — clear baseline
            # points so they don't reappear as stale artefacts next time,
            # mirroring the cleanup the old Run-button handler used to do.
            for key in list(self.manager.baseline_points.keys()):
                self.manager.clear_baseline(key)
            self.stored_corrections = {}
            self.operation_applied = True

            if progress is not None:
                progress.setLabelText("Updating spectrum list\u2026")
                QApplication.processEvents()

            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

            # Highlight only the spectra actually corrected — corrected_spectra
            # for Add as New (original labels, since register_copy_operation
            # already accounts for the rename), processed_spectra otherwise.
            # Using the full selected_spectra here had the same bug as the
            # Operations History entries: every selected spectrum would get
            # highlighted, not just the ones that actually had a baseline
            # applied.
            highlight_ids = {
                spectrum_key(s) for s in (corrected_spectra if add_as_new else processed_spectra)
            }
            self.oc._rebuild_spectra_list_with_selection(highlight_ids)

            self.controller.selected_spectra = (
                corrected_spectra if add_as_new else processed_spectra
            )
            self.oc._redraw_after_operation(progress, "manual baseline correction")
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
        return True, message

    # ------------------------------------------------------------------ #
    # Reset                                                                #
    # ------------------------------------------------------------------ #

    def reset_all_baselines(self):
        """Reset all baselines when new data is imported."""
        logger.debug("Resetting all baselines due to new data import")
        self.manager.clear_all_baselines()
        self.stored_corrections = {}
        self.operation_applied  = False

    # ------------------------------------------------------------------ #
    # Dialog                                                               #
    # ------------------------------------------------------------------ #

    def show_dialog(self, commit_callback=None):
        """Open the baseline correction dialog and store corrections on close."""
        from PyQt5.QtWidgets import QMessageBox

        if not self.controller:
            QMessageBox.warning(None, "Error", "No controller available for baseline correction.")
            return False

        if not hasattr(self.controller, 'spectrum_selector'):
            QMessageBox.warning(
                getattr(self.controller, 'view', None),
                "Error", "Controller is missing spectrum_selector component.",
            )
            return False

        selected_spectra = self.controller.spectrum_selector.get_selected_spectra()
        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view, "No Spectra Selected",
                "Please select one or more spectra to perform baseline correction.",
            )
            return False

        # Prune settings left behind by spectra that no longer exist —
        # otherwise a newly imported spectrum that happens to reuse an old
        # label would be compared against stale, unrelated leftover points
        # (see BaselineManager.prune_to_current_spectra docstring).
        self.manager.prune_to_current_spectra(self.controller.original_spectra)

        # If operation was previously applied, clear stale baseline points
        if self.operation_applied:
            logger.debug("Operation was previously applied — resetting baseline points")
            for sp in selected_spectra:
                self.manager.clear_baseline(self.manager._key_for(sp))
            self.operation_applied = False

        # Load points from "Use These Points" feature if available
        self._load_stored_points(selected_spectra)

        # Create and show the dialog
        self.dialog = BaselineCorrectionDialog(
            self.controller.view, selected_spectra, commit_callback=commit_callback
        )
        self.dialog.controller = self
        if hasattr(self.dialog, 'initialize_with_controller'):
            self.dialog.initialize_with_controller()

        self.dialog.exec_()

        # Always store corrections on close — no OK/Cancel distinction
        self.store_corrections()
        return True

    def _load_stored_points(self, selected_spectra):
        """Load baseline points from the global BaselinePointsStorage if present.

        BaselinePointsStorage is keyed by spectrum_key() (unique_id) —
        use_baseline_points() in operations_summary_dialog.py resolves
        each historical label to the current spectrum's unique_id before
        storing, so matching here by identity (self.manager._key_for(sp),
        the same unique_id) survives any rename that happened in between.
        """
        try:
            from src.views.dialogs.data_analysis.operations_summary_dialog import BaselinePointsStorage
        except ImportError:
            return

        storage = BaselinePointsStorage.get_instance()
        if not storage.has_stored_points:
            return

        loaded = 0
        for sp in selected_spectra:
            key = self.manager._key_for(sp)
            if key in storage.fit_types:
                self.manager.set_fit_type(key, storage.fit_types[key])
                if storage.fit_types[key] == 'polynomial' and key in storage.poly_orders:
                    self.manager.set_poly_order(key, storage.poly_orders[key])
            if key in storage.points:
                self.manager.clear_baseline(key)
                for x, y in storage.points[key]:
                    self.manager.add_baseline_point(key, x, y)
                    loaded += 1

                # add_baseline_point() only records the raw (x, y)
                # coordinates — self.manager.correction_info[key] (what
                # get_correction_summary() / the Summary button reads)
                # only gets filled in as a SIDE EFFECT of actually fitting
                # a baseline curve, normally triggered by the dialog's own
                # preview when the user clicks that spectrum. Since these
                # points were just loaded programmatically, nothing has
                # triggered that yet — so without this, the Summary
                # button shows nothing for this spectrum until the user
                # happens to select it first. Running the fit now (same
                # call the preview path makes) keeps the Summary accurate
                # from the moment the dialog opens.
                try:
                    self.manager.calculate_baseline(key, sp['x_scale'])
                except Exception:
                    pass

        logger.info(f"Loaded {loaded} stored baseline points")
        storage.has_stored_points = False

    # ------------------------------------------------------------------ #
    # Corrections storage                                                  #
    # ------------------------------------------------------------------ #

    def store_corrections(self):
        """Snapshot current baseline points and settings for later Apply.

        self.manager's dicts are keyed by unique_id (see
        BaselineManager._key_for), so iterating its own keys here keeps
        stored_corrections keyed the same way automatically — no spectrum
        lookup needed.
        """
        self.stored_corrections = {}
        for key in self.manager.baseline_points:
            points = self.manager.get_baseline_points(key)
            if not points:
                continue
            fit_type  = self.manager.get_fit_type(key)
            poly_order = self.manager.get_poly_order(key) if fit_type == 'polynomial' else None
            self.stored_corrections[key] = {
                'points':     points,
                'fit_type':   fit_type,
                'poly_order': poly_order,
            }

    def get_corrections_info(self, spectra=None, keys=None):
        """Return a summary dict of stored corrections (for parameters storage).

        Keyed by spectrum_key() (unique_id) — self.stored_corrections
        already is, so this just passes that identity straight through
        instead of converting it to a label. See developer_guide_help.py's
        "Golden Rule: Spectrum Identity" for why: a label-keyed record is
        a point-in-time snapshot that goes stale the moment the spectrum
        is renamed, which is exactly what made "Use These Points" able to
        silently fail to find its own data after a rename. Each entry
        still carries a 'label' field for display purposes (e.g. table
        headers, exported text) — that's the only thing labels are for
        here now.

        Args:
            spectra: Optional list of spectra used to attach each entry's
                CURRENT label (display only — never used as a lookup key).
                Falls back to the raw key if no match is found.
            keys: Optional iterable restricting the result to just these
                keys (e.g. the keys actually affected by a given commit).
        """
        key_to_label = {}
        if spectra:
            key_to_label = {self.manager._key_for(s): s.get('label', '') for s in spectra}

        info = {}
        for key, corr in self.stored_corrections.items():
            if keys is not None and key not in keys:
                continue
            info[key] = {
                'points': len(corr['points']),
                'type': corr['fit_type'],
                'label': key_to_label.get(key, key),
            }
            if corr['poly_order'] is not None:
                info[key]['order'] = corr['poly_order']
        return info

    def apply_stored_corrections(self, spectra, progress_callback=None):
        """Apply stored baseline corrections and return corrected spectra.

        Returns an empty list if no corrections were actually applied.

        progress_callback: optional callable, invoked every 50 spectra
            during the loop below — see SNIPBaselineManager.apply_correction
            for the full reasoning; same hook/contract. None (the
            default) — no change from before.
        """
        if not self.stored_corrections:
            return []

        self.manager.clear_all_baselines()

        corrected_spectra = []
        has_corrections   = False

        for i, sp in enumerate(spectra):
            notify_progress(progress_callback, i)
            # Deep-copy the spectrum to avoid mutating the original
            copy = {}
            for k, v in sp.items():
                if k in ('x_scale', 'y_scale', 'metadata'):
                    copy[k] = v.copy() if hasattr(v, 'copy') else v
                else:
                    copy[k] = v

            key  = self.manager._key_for(sp)
            corr = self.stored_corrections.get(key)

            if corr and corr['points']:
                for px, py in corr['points']:
                    self.manager.add_baseline_point(key, px, py)
                self.manager.set_fit_type(key, corr['fit_type'])
                if corr['poly_order'] is not None:
                    self.manager.set_poly_order(key, corr['poly_order'])
                try:
                    corrected_spectra.append(self.manager.apply_baseline_correction(copy))
                    has_corrections = True
                except Exception as exc:
                    logger.error(f"Error applying baseline correction to {sp.get('label')}: {exc}")
                    corrected_spectra.append(copy)
            else:
                corrected_spectra.append(copy)

        self.operation_applied = True
        return corrected_spectra if has_corrections else []

    # ------------------------------------------------------------------ #
    # Delegated manager operations                                         #
    # ------------------------------------------------------------------ #

    def add_baseline_point(self, spectrum, x, y):
        return self.manager.add_baseline_point(self.manager._key_for(spectrum), x, y)

    def remove_baseline_point(self, spectrum, x, y):
        return self.manager.remove_baseline_point(self.manager._key_for(spectrum), x, y)

    def get_baseline_points(self, spectrum):
        return self.manager.get_baseline_points(self.manager._key_for(spectrum))

    def get_fit_type(self, spectrum):
        return self.manager.get_fit_type(self.manager._key_for(spectrum))

    def set_fit_type(self, spectrum, fit_type):
        self.manager.set_fit_type(self.manager._key_for(spectrum), fit_type)

    def get_poly_order(self, spectrum):
        return self.manager.get_poly_order(self.manager._key_for(spectrum))

    def set_poly_order(self, spectrum, order):
        self.manager.set_poly_order(self.manager._key_for(spectrum), order)

    def clear_baseline(self, spectrum):
        self.manager.clear_baseline(self.manager._key_for(spectrum))

    def clear_all_baselines(self):
        self.manager.clear_all_baselines()

    def calculate_baseline(self, spectrum, x_values):
        return self.manager.calculate_baseline(self.manager._key_for(spectrum), x_values)

    def get_correction_summary(self):
        # Resolve keys back to each spectrum's CURRENT label using every
        # spectrum currently loaded, not just the selection for this dialog
        # session, since correction_info may hold entries for spectra
        # touched in an earlier selection too.
        spectra = getattr(self.controller, 'original_spectra', None)
        return self.manager.get_correction_summary(spectra)
