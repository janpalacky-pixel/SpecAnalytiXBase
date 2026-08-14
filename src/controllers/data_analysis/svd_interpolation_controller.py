# src/controllers/data_analysis/svd_interpolation_controller.py

import uuid
from PyQt5.QtWidgets import QMessageBox
from src.modules.data_analysis.svd_interpolation_manager import SVDInterpolationManager
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.spectra_validation import validate_common_x_axis
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)


class SVDInterpolationController:
    """Controller for the SVD Interpolation operation (Data Manipulation).
    Structured the same way as NormalizationController: the manager holds
    pure computation, this controller bridges it with the dialog and owns
    the commit logic directly, using the shared self.oc property to reach
    OperationsController's own state.

    Unlike Normalization (and most Data Manipulation operations), this
    operation has no 'replace' mode — it only ever ADDS new spectra
    alongside the untouched sources, since the whole point is generating
    spectra that were never actually measured. In that respect its commit
    logic is closer to MeltingCurveController.handle_melting_curve_analysis
    than to commit_normalization's Apply/Add-as-New pair.
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = SVDInterpolationManager()

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this commit
        logic needs — same pattern as NormalizationController.oc /
        BaselineCorrectionController.oc."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------
    def show_dialog(self, selected_spectra=None):
        """Show the SVD Interpolation dialog. Returns None always — unlike
        Normalization's show_dialog, there's no settings dict for
        OperationsController to cache and reuse, since every dialog
        session starts from a fresh SVD computation over whatever's
        currently selected (the source spectra set defines the SVD basis
        itself, not just a parameter of it)."""
        from src.views.dialogs.data_analysis.svd_interpolation_dialog import SVDInterpolationDialog

        if selected_spectra is None:
            selected_spectra = self.controller.spectrum_selector.get_selected_spectra()

        if len(selected_spectra) < 2:
            QMessageBox.warning(
                self.controller.view, "Not Enough Spectra",
                "SVD Interpolation needs at least 2 spectra, measured at different "
                "values of some parameter (e.g. temperature), to fit a curve through."
            )
            return None

        if not validate_common_x_axis(selected_spectra, self.controller.view,
                                       tool_name="SVD Interpolation"):
            return None

        dialog = SVDInterpolationDialog(
            parent=self.controller.view,
            controller=self,
            spectra=selected_spectra,
        )
        dialog.exec_()
        return None

    def show_parameters_dialog(self):
        """Convenience wrapper used by operations_controller."""
        selected = self.controller.spectrum_selector.get_selected_spectra()
        return self.show_dialog(selected) is not None

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    def commit_generated_spectra(self, new_spectra, source_labels, settings, add_as_new=True):
        """Add newly generated spectra to the main spectrum list.

        add_as_new=True  (default, unchanged from before this parameter
            existed): the measured source spectra are left untouched;
            the interpolated spectra are appended alongside them under
            their own generated names. Registered as an "add as new"
            -style copy operation for provenance, same convention
            commit_normalization uses in its own add_as_new branch.

        add_as_new=False ("Apply"): the measured spectra that fed the
            SVD basis (source_labels) are REMOVED from the spectrum list
            and replaced by the newly interpolated ones — matching how
            every other operation's plain "Apply" button works (see
            commit_normalization, SpikeRemovalController.
            commit_spike_removal), even though this operation's
            source-to-output relationship isn't 1:1 like theirs (N
            measured spectra in, M interpolated spectra out at the
            requested target values) — "replace" here means "swap the
            measured set for the interpolated set", not "each source
            becomes one output".

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback, same convention as commit_normalization.
        """
        if not new_spectra:
            return False, 'No spectra were generated.'

        current_state = self.oc.operations_manager.get_current_spectra()
        source_spectra = [s for s in current_state if s['label'] in set(source_labels)]

        all_labels = {s['label'] for s in current_state}
        run_id = str(uuid.uuid4())
        finished = []
        for spec in new_spectra:
            base_name = spec['label']
            new_name = base_name
            suffix = 2
            while new_name in all_labels:
                new_name = f'{base_name}_{suffix}'
                suffix += 1
            all_labels.add(new_name)

            spec = dict(spec)
            spec['label'] = new_name
            spec['metadata'] = dict(spec.get('metadata') or {})
            spec['metadata']['unique_id'] = str(uuid.uuid4())
            # Pop the transient per-spectrum generation info
            # SVDInterpolationManager.generate_spectra attached (which
            # target value, which components, which fit type each used)
            # and fold it into this one correction_history entry — see
            # the long comment on that key's construction for why this
            # is popped rather than kept as its own separate metadata
            # section. Every spectrum from the same run shares run_id and
            # source_spectra, but target_value/components_used/fit_types
            # are specific to THIS spectrum.
            target_info = spec['metadata'].pop('svd_interpolation_target', {})
            spec['metadata']['correction_history'] = append_correction_history(
                None, 'SVD Interpolation',
                {'run_id': run_id, 'source_spectra': list(source_labels), **target_info}
            )
            finished.append(spec)

        if add_as_new:
            output_spectra = current_state + finished
        else:
            # Apply — drop the measured spectra that fed the SVD basis,
            # keep everything else untouched, add the interpolated set
            # in their place. Same label-based filtering
            # commit_normalization's non-add_as_new branch uses, just
            # keyed on source_labels instead of the (here, nonexistent)
            # 1:1 output label match.
            source_label_set = set(source_labels)
            output_spectra = [s for s in current_state if s['label'] not in source_label_set]
            output_spectra.extend(finished)

        self.oc.operations_manager.apply_operation(
            "SVD Interpolation", settings, source_spectra,
            new_state_spectra=output_spectra,
        )

        if add_as_new:
            # This operation never modifies existing spectra in Add as
            # New mode — it only ever adds new ones — so register it as
            # an "add as new"-style copy entry rather than a plain
            # modification, same convention commit_normalization uses in
            # its add_as_new branch.
            mgr = self.oc.operations_manager
            if mgr.operations_chain:
                mgr.operations_chain.pop()
                mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
            self.oc.register_copy_operation(
                source_spectra, finished,
                operation_name="SVD Interpolation",
                pre_state=current_state,
            )

        self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
        self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

        new_ids = {spectrum_key(s) for s in finished}
        self.oc._rebuild_spectra_list_with_selection(new_ids)

        self.controller.selected_spectra = finished
        try:
            self.controller.plot_spectra()
        except ValueError as e:
            logger.error(f"Error plotting after SVD Interpolation: {e}")

        n = len(finished)
        noun = 'spectrum' if n == 1 else 'spectra'
        names = self.oc._format_names_for_message(s['label'] for s in finished)
        if add_as_new:
            return True, f'Generated {n} new {noun}: {names}.'
        return True, f'Replaced {len(source_spectra)} source spectrum/spectra with {n} interpolated {noun}: {names}.'
