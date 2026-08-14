# src/controllers/data_analysis/svd_background_controller.py

import uuid
import numpy as np
from PyQt5.QtWidgets import QApplication
from src.modules.data_analysis.svd_background_manager import SVDBackgroundManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key
from src.modules.utils.correction_history import append_correction_history

logger = get_logger(__name__)


class SVDBackgroundController:
    """Controller for SVD background correction operations."""

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = SVDBackgroundManager()

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs (operations_manager, register_copy_operation,
        current_parameters, _show_busy_progress,
        _rebuild_spectra_list_with_selection, _format_names_for_message) —
        the same shared bookkeeping every other operation's commit_<x>()
        reads and writes, kept centralized there rather than duplicated
        per-controller. Same pattern as
        SpectralCalculatorController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from OperationsController.commit_svd_background, #
    # unchanged in behavior, as part of giving every operation its own    #
    # dedicated controller instead of OperationsController holding all    #
    # of them directly (the same extraction already done for Spectral    #
    # Calculator). Internal references to OperationsController's own      #
    # state now go through self.oc instead of self directly; svd_controller #
    # (previously fetched via main_controller, since this method used to  #
    # live outside this class) is simply self now.                       #
    # ------------------------------------------------------------------ #

    def commit_svd_background(self, settings, add_as_new, selected_spectra):
        """Commit the SVD background correction operation directly, called
        by the dialog's own Apply / Add as New buttons rather than through
        the generic Run dispatch.

        apply_svd_correction() already re-computes the SVD decomposition
        from scratch and replays the baseline corrections / inversions
        from *settings* internally, so there's no need to pre-populate the
        manager's baseline state here the way the old handler did — that
        was leftover duplicate work from before apply_svd_correction became
        self-contained.

        Add as New uses suffix-style unique naming ('<label>_svd_bg',
        bumped on collision), matching Data range, Normalization,
        Interactive Subtraction, and X-axis alignment.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not selected_spectra:
            return False, 'Please select one or more spectra to apply SVD background correction.'

        if len(selected_spectra) < 2:
            return False, 'SVD background correction requires at least 2 spectra.'

        n_spectra = len(selected_spectra)
        progress = self.oc._show_busy_progress(
            "SVD Background",
            f"Applying SVD background correction to {n_spectra} spectra\u2026",
            n_spectra,
        )
        try:
            try:
                processed_spectra = self.apply_svd_correction(
                    settings, selected_spectra,
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None,
                )
            except Exception as exc:
                logger.exception('Unexpected error in SVD background correction')
                return False, f'An unexpected error occurred: {exc}'

            if not processed_spectra:
                return False, 'Failed to apply SVD background correction to any of the selected spectra.'

            total_change = sum(
                np.sum(np.abs(orig['y_scale'] - proc['y_scale']))
                for orig, proc in zip(selected_spectra, processed_spectra)
            )
            minimal_change = total_change < 1e-10

            current_state = self.oc.operations_manager.get_current_spectra()

            if add_as_new:
                # Suffix-style unique naming, matching the Data range,
                # Normalization, Interactive Subtraction, and X-axis alignment
                # commits — never reuse the source label, since "add as new"
                # appends alongside the untouched original.
                all_labels = {s['label'] for s in current_state}
                renamed = []
                for spec in processed_spectra:
                    base_name = f"{spec['label']}_svd_bg"
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
                'SVD background', settings, selected_spectra,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    selected_spectra, processed_spectra,
                    operation_name='SVD background',
                    pre_state=current_state,
                )

            # The correction has now been baked into the data — carrying the
            # old baseline points and inversion flags forward would make them
            # appear as stale artefacts the next time the dialog is used, so
            # clear them here (mirrors the cleanup the old Run-button handler
            # used to do after a successful Apply).
            if "SVD background" in self.oc.current_parameters:
                self.oc.current_parameters["SVD background"]['baseline_corrections'] = {}
                self.oc.current_parameters["SVD background"]['inverted_subspectra'] = []
            self.manager.baseline_corrections = {}
            self.manager.baseline_points = {}
            self.manager.baseline_settings = {}
            self.manager.inverted_subspectra = set()

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
                progress.setLabelText("Redrawing plot\u2026")
                QApplication.processEvents()
            try:
                self.controller.plot_spectra(
                    progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None
                )
            except Exception as exc:
                logger.error(f"Error plotting after SVD background correction: {exc}")
        finally:
            if progress is not None:
                progress.close()

        n = len(processed_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        if add_as_new:
            new_names = self.oc._format_names_for_message(s['label'] for s in processed_spectra)
            message = f'Added {n} new {noun}: {new_names}.'
        else:
            message = f'Replaced {n} {noun} with the SVD-corrected result.'
        if minimal_change:
            message += (
                f'\n\nNote: this produced minimal change to the data '
                f'(total change: {total_change:.2e}). This might be expected '
                f'depending on your correction settings.'
            )
        return True, message

    # ------------------------------------------------------------------ #
    # Public API — called from operations_controller / dialog             #
    # ------------------------------------------------------------------ #

    def apply_svd_correction(self, settings, spectra, progress_callback=None):
        """Apply SVD background correction and return corrected spectra.

        Re-computes SVD from scratch on every call so Apply is always
        deterministic regardless of live dialog state.  Inversions and
        baseline corrections stored in *settings* are replayed on the
        fresh decomposition before reconstruction.

        progress_callback : optional callable, passed straight through to
        SVDBackgroundManager.reconstruct_spectra() — see that method's
        own docstring. None (the default) — no change from before.
        """
        if not spectra:
            logger.debug("No spectra provided to SVD correction")
            return []

        try:
            logger.debug(f"SVD correction starting with {len(spectra)} spectra")

            self.manager.correction_mode     = settings.get('correction_mode', 'all_subspectra')
            self.manager.max_components      = settings.get('max_components', 10)
            self.manager.selected_subspectra = settings.get('selected_subspectra', [0, 1, 2])

            # Phase 1: fresh decomposition
            if not self.manager.compute_svd_from_spectra(spectra):
                logger.error("Failed to compute SVD")
                return spectra

            # Phase 2: restore inversions BEFORE baseline corrections
            # compute_svd_from_spectra resets U/Vt signs arbitrarily, so the
            # signs chosen in the dialog must be replayed here.
            inverted_subspectra = settings.get('inverted_subspectra', [])
            for idx in inverted_subspectra:
                if idx < self.manager.U.shape[1]:
                    self.manager.U[:, idx]           *= -1
                    self.manager.Vt[idx, :]          *= -1
                    self.manager.corrected_U[:, idx]  = self.manager.U[:, idx]
                    self.manager.inverted_subspectra.add(idx)
            if inverted_subspectra:
                logger.debug(f"Restored {len(inverted_subspectra)} inversions")

            # Phase 3: apply baseline corrections
            self.manager.baseline_corrections = {}
            self.manager.baseline_points      = {}
            self.manager.baseline_settings    = {}

            for key, data in settings.get('baseline_corrections', {}).items():
                idx        = int(key)
                points     = data.get('points', [])
                fit_type   = data.get('fit_type', 'spline')
                poly_order = data.get('poly_order', 3)

                self.manager.baseline_points[idx]   = points.copy()
                self.manager.baseline_settings[idx] = {'type': fit_type, 'order': poly_order}

                if len(points) >= 2:
                    ok = self.manager.set_baseline_correction(idx, points, fit_type, poly_order)
                    level = logger.debug if ok else logger.error
                    level(f"{'Applied' if ok else 'Failed'} baseline correction for subspectrum {idx}")

            # Phase 4: reconstruct
            corrected = self.manager.reconstruct_spectra(spectra, progress_callback=progress_callback)
            if not corrected:
                logger.error("SVD reconstruction returned no spectra")
                return spectra

            # Phase 5: build output with metadata
            result = []
            for original, corr in zip(spectra, corrected):
                out = {}
                for k, v in corr.items():
                    if k in ('x_scale', 'y_scale'):
                        out[k] = v.copy() if hasattr(v, 'copy') else np.array(v)
                    elif k == 'metadata':
                        out[k] = (v.copy() if hasattr(v, 'copy') else dict(v)) if v else {}
                    else:
                        out[k] = v
                meta = out.setdefault('metadata', {})
                # Shared, chronologically-ordered history across every
                # operation type that records one (see
                # src/modules/utils/correction_history.py) — a spectrum
                # corrected by SVD Background, then Manual Baseline, then
                # SVD Background again now shows all three in the order
                # they actually happened, tagged by which operation each
                # one was. Previously this used its own separate key
                # (svd_correction_history), disconnected from Manual
                # Baseline's own separate key (baseline_correction) — a
                # spectrum touched by both ended up with two independent
                # records with no way to tell which actually happened
                # first.
                #
                # This accumulation only happens HERE, in the actual commit
                # path — never inside SVDBackgroundManager.reconstruct_spectra()
                # itself, which is also called directly (and repeatedly, once
                # per settings tweak) by the dialog's live preview and the
                # Diagnostics button. If the history-append lived in
                # reconstruct_spectra() instead, every preview redraw would
                # silently add a fake "correction" to the record, not just
                # real applications — reconstruct_spectra() stays a pure,
                # side-effect-free computation; only a real Apply reads its
                # one-shot result and appends it here.
                new_entry = meta.pop('svd_correction', {})
                # Matched exactly against 'SVD background' — the
                # operation type string used for dialog dispatch
                # (operations_summary_dialog.py's per-spectrum lookup
                # filters on this exact string). This previously read
                # 'SVD Background' (capital B) — a silent mismatch that
                # meant NO entry from this, the one actual write site
                # for SVD Background's correction_history, was ever
                # found again: every "Per-Spectrum Detail" / "Result
                # Spectra" lookup came back with nothing, even though
                # the correction itself was applied correctly.
                meta['correction_history'] = append_correction_history(
                    original.get('metadata'), 'SVD background', new_entry
                )
                result.append(out)

            total_change = sum(
                np.sum(np.abs(o['y_scale'] - r['y_scale']))
                for o, r in zip(spectra, result)
            )
            logger.debug(f"SVD correction complete — total change: {total_change:.4e}")
            if total_change < 1e-12:
                logger.warning("SVD correction made virtually no change to the data")

            return result

        except Exception as exc:
            logger.error(f"Exception in SVD correction: {exc}")
            logger.exception("Traceback:")
            return spectra

    # ------------------------------------------------------------------ #
    # Subspectrum / component queries                                      #
    # ------------------------------------------------------------------ #

    def get_svd_components_info(self):
        """Return component info dict, or None if SVD not yet computed."""
        if self.manager.U is None:
            return None
        return {
            'n_components':           self.manager.U.shape[1],
            'explained_variance':     self.manager.explained_variance,
            'total_variance_first_5': (
                sum(self.manager.explained_variance[:5])
                if self.manager.explained_variance is not None else 0
            ),
        }

    def get_subspectrum_data(self, index, corrected=False):
        """Return (x, y) for *index*, or (None, None)."""
        if corrected:
            return self.manager.get_corrected_subspectrum(index)
        return self.manager.get_subspectrum(index)

    def get_coefficients(self, index):
        """Return the score vector for *index*, or None."""
        return self.manager.get_coefficients(index)

    # ------------------------------------------------------------------ #
    # Baseline point editing                                              #
    # ------------------------------------------------------------------ #

    def add_baseline_point(self, subspectrum_index, x, y):
        """Add a point and recalculate the baseline when ≥2 points exist."""
        if not self.manager:
            return False

        points = self.manager.get_baseline_points(subspectrum_index)
        points.append((x, y))
        self.manager.baseline_points[subspectrum_index] = points

        success = True
        if len(points) >= 2:
            cfg     = self.manager.get_baseline_settings(subspectrum_index)
            success = self.manager.set_baseline_correction(
                subspectrum_index, points, cfg['type'], cfg['order']
            )

        self._update_operations_parameters()
        return success

    def remove_baseline_point(self, subspectrum_index, x, y, tolerance=None):
        """Remove the baseline point nearest to (x, y)."""
        points = self.manager.get_baseline_points(subspectrum_index)
        if not points:
            return

        nearest = min(
            range(len(points)),
            key=lambda i: abs(points[i][0] - x) + abs(points[i][1] - y)
        )
        points.pop(nearest)

        if points:
            cfg = self.manager.get_baseline_settings(subspectrum_index)
            self.manager.set_baseline_correction(
                subspectrum_index, points, cfg['type'], cfg['order']
            )
        else:
            self.manager.clear_baseline(subspectrum_index)

        self._update_operations_parameters()

    def clear_baseline(self, subspectrum_index):
        """Remove all baseline points for *subspectrum_index*."""
        self.manager.clear_baseline(subspectrum_index)
        self._update_operations_parameters()

    def set_baseline_settings(self, subspectrum_index, fit_type, poly_order):
        """Persist fit type and polynomial order for *subspectrum_index*.

        Settings are stored even before any points exist so that
        navigating away and back restores the correct UI state.
        """
        self.manager.baseline_settings[subspectrum_index] = {
            'type':  fit_type,
            'order': poly_order,
        }
        points = self.manager.get_baseline_points(subspectrum_index)
        if points:
            self.manager.set_baseline_correction(
                subspectrum_index, points, fit_type, poly_order
            )
        self._update_operations_parameters()

    # ------------------------------------------------------------------ #
    # Misc                                                                 #
    # ------------------------------------------------------------------ #

    def get_correction_summary(self):
        return self.manager.get_correction_summary()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _update_operations_parameters(self):
        """Push the current baseline / inversion state into current_parameters."""
        if not hasattr(self.controller, 'operations_controller'):
            return
        if "SVD background" not in self.controller.operations_controller.current_parameters:
            return

        baseline_corrections = {
            idx: {
                'points':     self.manager.get_baseline_points(idx),
                'fit_type':   self.manager.get_baseline_settings(idx)['type'],
                'poly_order': self.manager.get_baseline_settings(idx)['order'],
            }
            for idx in self.manager.baseline_corrections
        }

        params = self.controller.operations_controller.current_parameters["SVD background"]
        params['baseline_corrections'] = baseline_corrections
        params['inverted_subspectra']  = list(self.manager.inverted_subspectra)
