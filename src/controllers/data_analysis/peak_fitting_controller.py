# src/controllers/data_analysis/peak_fitting_controller.py

import uuid
from PyQt5.QtWidgets import QMessageBox
from src.modules.data_analysis.peak_fitting_manager import PeakFittingManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.revision_tracking import revision_changed

logger = get_logger(__name__)


class PeakFittingController:
    """
    Controller for peak fitting / deconvolution.

    Bridges PeakFittingManager (the algorithm) with the dialog and owns
    handle_peak_fitting() directly — same shape as every other extracted
    controller in this codebase (SVDBackgroundController,
    BaselineCorrectionController, etc.), using the shared self.oc property
    to reach OperationsController's own state (operations_manager,
    update_original_spectra_with_processed, _rebuild_spectra_list_with_selection).

    An earlier version of this docstring argued handle_peak_fitting()
    should stay in OperationsController because its logic was "tightly
    coupled to OperationsController's own state and widgets" — that
    reasoning predates the self.oc pattern, which was subsequently proven
    to handle exactly this coupling cleanly across 13 other operations'
    own extractions. Revisited and moved here for full consistency,
    which also surfaced a real, previously-unnoticed bug: the old
    in-place list rebuild used a hand-rolled per-item
    item.setSelected(True) loop — the same anti-pattern confirmed
    elsewhere in this app (Map2D, the ROI viewer, the main spectra-list
    rebuild itself) to cost real, measurable time at scale. Now routed
    through the shared, already-fixed _rebuild_spectra_list_with_selection
    helper instead.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = PeakFittingManager()
        self._last_seen_revision = None

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as every other extracted
        controller's oc property this session."""
        return self.controller.operations_controller

    def filter_stale_settings(self, current_settings):
        """Called by OperationsController right before constructing the
        Peak Fitting dialog, on the settings dict it's about to pass in
        as current_settings.

        Bug found in practice: OperationsController's settings cache
        (last_op_settings["Peak Fitting"]) is keyed only by whether the
        selected SPECTRUM is the same as last time (label-based
        _get_selection_hash) -- it has no idea whether that spectrum's
        own y-data changed since (e.g. a baseline correction or
        smoothing operation ran on it in between two Peak Fitting
        sessions). But this settings dict isn't just parameters here --
        it carries the previous session's actual COMPUTED fit_results,
        and PeakFittingDialog.load_settings() restores them and
        immediately redraws that old fit curve on open
        (update_plot_with_fit_results()), with no re-fit and no warning,
        as if it were still a valid fit of the spectrum now shown. Strip
        exactly the computed/picked key -- not initial_peaks (just x/color
        guesses, harmless to keep) or output_options/amplitude_constraint/
        add_via_click (genuine settings) -- whenever an operation ran
        since we last trusted it. Same pattern as
        SVDBackgroundController.filter_stale_settings and
        XAxisAlignmentController.show_dialog's revision check."""
        should_reset, self._last_seen_revision = revision_changed(
            self.controller, self._last_seen_revision)
        if should_reset and current_settings:
            current_settings = dict(current_settings)
            current_settings.pop('fit_results', None)
        return current_settings

    def _note_own_commit(self):
        """Resync _last_seen_revision to whatever apply_operation() (in
        handle_peak_fitting, called just before this) just bumped
        IncrementalOperationsManager.revision to.

        Real bug found in practice, fixed here: filter_stale_settings()
        only runs once, when the dialog is about to OPEN -- it has no
        way to know that closing THIS dialog (with an output option
        checked, so handle_peak_fitting() actually commits a new
        operation) is about to bump revision too. Without this resync,
        the very next time Peak Fitting reopened, filter_stale_settings
        saw "revision changed since last time" and stripped the
        fit_results it had just saved into last_op_settings -- mistaking
        this fit's own commit for an unrelated operation that ran on the
        spectrum meanwhile (the case filter_stale_settings genuinely
        needs to catch). Calling this right after our own commit keeps
        that distinction correct: an operation that runs AFTER this
        still bumps revision again and is still caught next time; this
        one, already accounted for, is not."""
        _, self._last_seen_revision = revision_changed(
            self.controller, self._last_seen_revision)

    # ------------------------------------------------------------------ #
    # Commit — moved here from OperationsController.handle_peak_fitting,  #
    # behaviorally unchanged EXCEPT for the setSelected() fix noted in    #
    # the class docstring above.                                          #
    # ------------------------------------------------------------------ #

    def handle_peak_fitting(self):
        """
        Handles the peak fitting operation.
        1. If any Output Options are checked, creates the corresponding new
           spectra (total fit, residual, individual peaks) and adds them to
           the main list — the original spectrum is never modified.
        2. If no Output Options are checked, nothing is saved at all (see
           class docstring for why fitting itself never touches the
           original spectrum's own metadata).
        3. Checks for duplicate names and adds a suffix if a name already exists.
        """
        if "Peak Fitting" not in self.oc.current_parameters:
            QMessageBox.warning(self.controller.view, "No Parameters", "Peak fitting parameters have not been set.")
            return

        settings = self.oc.current_parameters["Peak Fitting"]
        fit_results = settings.get('fit_results')
        output_options = settings.get('output_options', {})  # Get the dict of booleans

        if not fit_results:
            QMessageBox.information(self.controller.view, "No Fit Data",
                                    "No peaks were defined or fitted. Operation cancelled.")
            return

        # One shared identifier for every spectrum derived from THIS fit —
        # same reasoning as NMF/MCR-ALS's own run_id: without this, there's
        # no way to tell from a spectrum's own metadata that e.g. an
        # individual peak, the total fit, and the residual all came from
        # the SAME fitting operation, versus two separate fits that
        # happened to touch the same original spectrum at different times.
        fit_run_id = str(uuid.uuid4())

        selected_spectra = self.oc._get_current_state_for_selected_spectra()
        original_spectrum = selected_spectra[0]

        current_state = self.oc.operations_manager.get_current_spectra()

        # --- Helper function for finding unique names ---
        def find_unique_name(base_name, all_labels):
            """Checks for a name; if it exists, adds a suffix like _2, _3, etc."""
            new_name = base_name
            suffix = 2
            while new_name in all_labels:
                new_name = f"{base_name}_{suffix}"
                suffix += 1
            return new_name

        # Get all current labels to check against
        all_current_labels = {s['label'] for s in current_state}
        # --- End helper function ---

        # Locate the original spectrum in the current state — needed below
        # to build affected_spectra_for_history in the metadata-only case,
        # and as the base for every derived spectrum's x_scale/y_scale.
        spectrum_to_modify = None
        for s in current_state:
            if s['label'] == original_spectrum['label']:
                spectrum_to_modify = s
                break

        if not spectrum_to_modify:
             QMessageBox.warning(self.controller.view, "State Error", "Original spectrum not found in current state.")
             return

        # No metadata is written to the original spectrum here — Peak
        # Fitting never changes its data (x_scale/y_scale are untouched),
        # so nothing should persist onto it just for having been
        # analyzed. The fit results only become part of any spectrum's
        # metadata when that spectrum is actually CREATED from them (the
        # fit/residual/individual-peak options below), each tagged with
        # its own correction_history entry describing exactly how it was
        # produced — not stapled onto the untouched source.

        # List to hold newly created spectra
        new_spectra_to_add = []

        # --- 2. Check for optional new spectra ---
        manager = self.manager

        # Pre-calculate the total fit ONLY if needed
        total_fit_full = None

        if output_options.get('add_fit') or output_options.get('add_residual') or output_options.get('add_peaks'):
            total_fit_full = self.compute_total_fit_curve(original_spectrum['x_scale'], fit_results)

        # Option: Add total fit
        if output_options.get('add_fit') and total_fit_full is not None:
            # Built fresh, matching how individual peaks are already
            # built below — not by copying every key from
            # original_spectrum. That used to carry over the ORIGINAL
            # spectrum's entire import metadata (file path, import
            # parameters, column index, etc.) onto a spectrum that was
            # never actually imported from anywhere; it was computed
            # from a fit. Confirmed reachable and confusing in practice:
            # the Metadata viewer showed "File Path: ...xlsx" and
            # "Import Parameters" for a curve that only exists as a
            # mathematical sum of fitted peaks.
            fit_spectrum = {
                'x_scale': original_spectrum['x_scale'].copy(),
                'y_scale': total_fit_full,
                'label': "",  # set below
                'metadata': {},
            }

            base_label = f"{original_spectrum['label']}_fit"
            fit_spectrum['label'] = find_unique_name(base_label, all_current_labels)
            all_current_labels.add(fit_spectrum['label'])  # Add to set to check against

            # Give the new copy its own identity. Without this it
            # silently shares the source spectrum's unique_id (dict(spec)
            # is a shallow copy, and metadata is the SAME dict object as
            # the source's unless replaced here) — meaning selecting the
            # ORIGINAL by label later would also sweep in this copy via
            # the ID-based matching fallback in
            # _get_current_state_for_selected_spectra(), silently
            # re-processing spectra that were never actually selected.
            fit_spectrum['metadata'] = dict(fit_spectrum.get('metadata') or {})
            fit_spectrum['metadata']['unique_id'] = str(uuid.uuid4())
            # Describes how this spectrum was created — same convention
            # every other spectrum-creating operation in this app follows
            # (Combine Spectra, NMF, MCR-ALS, 2D Map export). n_peaks/
            # source_spectrum here, not the raw fit_results — that's
            # already recorded per-peak below on the individual peak
            # spectra where it's the actual defining parameter; here it
            # would just be a redundant repeat of the same numbers.
            fit_spectrum['metadata']['correction_history'] = append_correction_history(
                None, 'Peak Fitting (total fit)',
                {'fit_run_id': fit_run_id, 'source_spectrum': original_spectrum['label'], 'n_peaks': len(fit_results)}
            )

            new_spectra_to_add.append(fit_spectrum)

        # Option: Add residual
        if output_options.get('add_residual') and total_fit_full is not None:
            # Built fresh — same reasoning as fit_spectrum above.
            residual_spectrum = {
                'x_scale': original_spectrum['x_scale'].copy(),
                'y_scale': original_spectrum['y_scale'] - total_fit_full,
                'label': "",  # set below
                'metadata': {},
            }

            base_label = f"{original_spectrum['label']}_residual"
            residual_spectrum['label'] = find_unique_name(base_label, all_current_labels)
            all_current_labels.add(residual_spectrum['label'])  # Add to set

            # Same fresh-identity fix as fit_spectrum above — same bug,
            # same reasoning.
            residual_spectrum['metadata'] = dict(residual_spectrum.get('metadata') or {})
            residual_spectrum['metadata']['unique_id'] = str(uuid.uuid4())
            residual_spectrum['metadata']['correction_history'] = append_correction_history(
                None, 'Peak Fitting (residual)',
                {'fit_run_id': fit_run_id, 'source_spectrum': original_spectrum['label'], 'n_peaks': len(fit_results)}
            )

            new_spectra_to_add.append(residual_spectrum)

        # Option: Add individual peaks
        if output_options.get('add_peaks'):
            individual_curves = self.compute_individual_peak_curves(
                original_spectrum['x_scale'], fit_results)
            for i, new_y in enumerate(individual_curves):
                peak_fit = fit_results[i]
                model_name = peak_fit['model']
                param_dict = peak_fit['parameters']
                width_key = 'sigma' if model_name == 'Gaussian' else 'gamma'
                new_peak_spectrum = {
                    'x_scale': original_spectrum['x_scale'].copy(),
                    'y_scale': new_y,
                    'label': "",  # Will be set below
                    # unique_id added below — this dict is built fresh
                    # (not copied from original_spectrum), so unlike
                    # fit_spectrum/residual_spectrum above, there was no
                    # id to inherit by accident, but it also never got one
                    # of its own — meaning every individual peak spectrum
                    # was identified purely by label, the fragile fallback
                    # every other per-spectrum key in this app explicitly
                    # avoids relying on (labels can collide across import
                    # sessions or after a rename).
                    'metadata': {}
                }
                new_peak_spectrum['metadata']['correction_history'] = append_correction_history(
                    None, 'Peak Fitting (individual peak)',
                    {
                        'fit_run_id': fit_run_id,
                        'source_spectrum': original_spectrum['label'],
                        'peak_index': i + 1,
                        'model': model_name,
                        'height': param_dict['height'],
                        'center': param_dict['center'],
                        width_key: param_dict[width_key],
                    }
                )

                # Zero-padded so these sort correctly in the main window's
                # spectrum list — "peak_10" used to sort alphabetically
                # before "peak_2", since plain string comparison doesn't
                # know these are numbers. Width is at least 2 digits (matching
                # the requested "_peak_01, _peak_02, ..." convention) but
                # grows automatically for >99 peaks so sorting stays correct
                # at any count, not just the common case.
                peak_num_width = max(2, len(str(len(individual_curves))))
                base_label = f"{original_spectrum['label']}_peak_{i+1:0{peak_num_width}d}"
                new_peak_spectrum['label'] = find_unique_name(base_label, all_current_labels)
                all_current_labels.add(new_peak_spectrum['label'])  # Add to set
                new_peak_spectrum['metadata']['unique_id'] = str(uuid.uuid4())

                new_spectra_to_add.append(new_peak_spectrum)

        # --- Register Operation — only when new spectra were actually
        # created. Operations History tracks changes to the spectra
        # themselves (additions, removals, data transformations); a
        # pure analysis with no output spectra requested changes
        # nothing about any spectrum, so there's genuinely nothing to
        # register here or persist anywhere — matches Band Ratio, which
        # never modifies the spectra list at all either.
        if not new_spectra_to_add:
            QMessageBox.information(
                self.controller.view, "Peak Fit Complete",
                "Fit computed, but nothing was saved — no output spectra were "
                "requested. Check one of the output options (total fit, "
                "residual, or individual peaks) to keep the result."
            )
            return

        affected_spectra_for_history = [spectrum_to_modify]

        # The new state is the old state PLUS any new spectra
        output_spectra = current_state + new_spectra_to_add

        self.oc.operations_manager.apply_operation(
            "Peak Fitting",
            settings,
            affected_spectra_for_history,
            new_state_spectra=output_spectra
        )

        # apply_operation() above just bumped
        # IncrementalOperationsManager.revision -- resync our own
        # bookkeeping to it right now (see _note_own_commit's docstring).
        self._note_own_commit()

        # --- 4. Update UI --- batch selection via the shared, already-fixed
        # helper — see class docstring above for the bug this replaced.
        # order_spectra() was missing here entirely (present in every
        # other operation's own UI-update step) — without it, the new
        # fit/residual/individual-peak spectra were simply appended at
        # the end of the raw list, ignoring whatever sort order the main
        # window was actually set to.
        self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
        self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)
        new_ids = {spectrum_key(s) for s in new_spectra_to_add}
        self.oc._rebuild_spectra_list_with_selection(new_ids)

        self.controller.spectrum_selector.on_item_selection_changed()
        QMessageBox.information(self.controller.view, "Peak Fit Complete",
                                f"{len(new_spectra_to_add)} new spectra were added from the fit.")

    # ------------------------------------------------------------------ #
    # Dialog                                                               #
    # ------------------------------------------------------------------ #

    def show_dialog(self, spectrum, current_settings=None):
        """Construct (but do not exec) the Peak Fitting dialog for a single
        spectrum. Returns the QDialog instance — the caller runs it and
        reads back get_results(), matching how this dialog already works
        (no commit_callback / Apply-Add as New pattern here; OK simply
        closes the dialog and the caller decides what to do with the
        results, same as before this refactor)."""
        from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
        return PeakFittingDialog(
            self.controller.view if self.controller else None,
            spectrum=spectrum,
            current_settings=current_settings,
        )

    # ------------------------------------------------------------------ #
    # Pure computation                                                     #
    # ------------------------------------------------------------------ #

    def flatten_fit_params(self, fit_results):
        """Return (model_definitions, all_params) from a fit_results list
        — the same flat-parameter-list shape multi_peak_model() expects.
        Shared by compute_total_fit_curve() and
        compute_individual_peak_curves() so both build this from the
        SAME logic rather than two independent copies of the same
        height/center/width-key unpacking."""
        model_definitions = []
        all_params = []
        for peak_fit in fit_results:
            model_name = peak_fit['model']
            param_names = self.manager.peak_models[model_name][1]
            model_definitions.append((model_name, len(param_names)))
            param_dict = peak_fit['parameters']
            width_key = 'sigma' if model_name == 'Gaussian' else 'gamma'
            all_params.extend([param_dict['height'], param_dict['center'], param_dict[width_key]])
        return model_definitions, all_params

    def compute_total_fit_curve(self, x_scale, fit_results):
        """Return the summed model curve (sum of every fitted peak) over
        x_scale, or None if fit_results is empty. Pure computation, no
        side effects — used for the optional 'Add spectrum from total
        fit' / 'Add spectrum from residual' output options."""
        if not fit_results:
            return None
        model_definitions, all_params = self.flatten_fit_params(fit_results)
        if not all_params:
            return None
        return self.manager.multi_peak_model(x_scale, *all_params, model_definitions=model_definitions)

    def compute_individual_peak_curves(self, x_scale, fit_results):
        """Return a list of y-curves, one per fitted peak in fit_results
        (same order), each the isolated contribution of that single peak
        alone. Used for the optional 'Add new spectra from individual
        peaks' output option."""
        if not fit_results:
            return []
        model_definitions, all_params = self.flatten_fit_params(fit_results)
        curves = []
        param_index = 0
        for model_name, num_params in model_definitions:
            model_func, _ = self.manager.peak_models[model_name]
            params_for_func = all_params[param_index: param_index + num_params]
            param_index += num_params
            curves.append(model_func(x_scale, *params_for_func))
        return curves
