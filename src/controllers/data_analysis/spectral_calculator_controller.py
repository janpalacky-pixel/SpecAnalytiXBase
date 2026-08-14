# src/controllers/data_analysis/spectral_calculator_controller.py

import uuid
from PyQt5.QtWidgets import QMessageBox, QListWidgetItem, QApplication
from PyQt5.QtCore import Qt

from src.modules.data_analysis.spectral_calculator_manager import SpectralCalculatorManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_id

logger = get_logger(__name__)


class SpectralCalculatorController:
    """Controller for the Spectral Calculator dialog.

    Extracted out of OperationsController's monolithic operation-dispatch
    method and its own commit_spectral_calculator() — this operation
    previously had a Manager and a Dialog but no Controller of its own,
    unlike Peak Fitting / NMF / MCR-ALS / Cluster Analysis / PCA Scores,
    all of which already have a dedicated controller bridging their
    dialog and manager. Mirrors that same shape: thin bridge holding a
    reference to main_controller, with the actual commit logic moved
    here (behavior unchanged from its previous home in
    OperationsController — only internal references to
    OperationsController's own state/methods updated to go through
    self.oc, the same way NMFController.export_components_to_main_list
    reaches OperationsController via
    self.controller.operations_controller.register_copy_operation(...)
    rather than owning that logic itself).
    """

    def __init__(self, main_controller):
        self.controller = main_controller

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs (current_parameters, last_op_settings,
        last_selection_hash, operations_manager, register_copy_operation,
        _get_current_state_for_selected_spectra, _get_selection_hash) —
        the same shared bookkeeping every other operation's commit_<x>()
        reads and writes, kept centralized there rather than duplicated
        per-controller."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Dialog                                                               #
    # ------------------------------------------------------------------ #

    def show_dialog(self):
        """Show the Spectral Calculator dialog for the current selection.
        Moved here unchanged in behavior from OperationsController's
        operation-dispatch elif-chain (previously the
        operation == "Spectral Calculator" branch)."""
        from src.views.dialogs.data_analysis.spectral_calculator_dialog import SpectralCalculatorDialog

        selected_spectra = self.oc._get_current_state_for_selected_spectra()
        current_selection_hash = self.oc._get_selection_hash(selected_spectra)

        if not selected_spectra:
            QMessageBox.warning(
                self.controller.view, "No Spectra Selected",
                "Please select at least one spectrum for the Spectral Calculator."
            )
            return

        # Only reuse the last formula/settings if this dialog was last
        # shown for this exact selection — without this guard, selecting
        # a different set of spectra would still reopen the calculator
        # pre-loaded with a formula referencing labels that may not even
        # be part of the current selection.
        last_settings = {}
        if ("Spectral Calculator" in self.oc.current_parameters and
                self.oc.last_selection_hash == current_selection_hash):
            last_settings = self.oc.last_op_settings.get("Spectral Calculator", {}).copy()

        dialog = SpectralCalculatorDialog(
            self.controller.view,
            selected_spectra=selected_spectra,
            current_settings=last_settings,
            commit_callback=self.commit_spectral_calculator,
            main_controller=self.controller,
        )
        dialog.exec_()
        # Remember the settings shown, purely so reopening the dialog for
        # the same selection starts from where it left off — Apply / Add
        # as New already committed (if at all) before this returns, via
        # commit_callback. The dialog now closes itself on a successful
        # commit (see SpectralCalculatorDialog._on_commit_clicked), so
        # get_settings() here reflects whatever was last shown, whether
        # or not a commit happened.
        settings = dialog.get_settings()
        if settings:
            settings['source_labels'] = [s['label'] for s in selected_spectra]
            self.oc.current_parameters["Spectral Calculator"] = settings.copy()
            self.oc.last_op_settings["Spectral Calculator"] = settings.copy()
            self.oc.last_selection_hash = current_selection_hash

    # ------------------------------------------------------------------ #
    # Commit                                                               #
    # ------------------------------------------------------------------ #

    def commit_spectral_calculator(self, settings, add_as_new, selected_spectra):
        """Commit the spectral calculator's formula directly, called by
        the dialog's own Apply / Add as New buttons rather than through
        the generic Run dispatch.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        progress = None
        try:
            if not settings:
                return False, 'Parameters for Spectral Calculator not set.'

            source_labels = settings.get('source_labels') or [s['label'] for s in selected_spectra]
            current_state = self.oc.operations_manager.get_current_spectra()
            spectra_to_process = [s for s in current_state if s['label'] in source_labels]

            if len(spectra_to_process) != len(source_labels):
                return False, (
                    'One or more source spectra could not be found. '
                    'Please redefine parameters.'
                )

            # Threshold/message based on the full current spectrum count, not
            # just the (usually small) number of sources in the formula —
            # rebuilding the spectrum list afterward costs the same either
            # way, since the WHOLE list gets rebuilt regardless of how many
            # spectra fed into the formula. Same reasoning as Combine
            # Spectra's own progress dialog.
            progress = self.oc._show_busy_progress(
                "Spectral Calculator",
                f"Evaluating formula for {len(spectra_to_process)} spectra\u2026",
                len(current_state),
            )

            # Evaluate formula — may produce one or several output spectra
            manager = SpectralCalculatorManager()
            new_spectra = manager.evaluate(settings['formula'], spectra_to_process)

            # Assign unique names: base name as-is for a single output,
            # base name + "_1", "_2", ... for multiple outputs. Uniqueness
            # is checked against the full current spectrum list either way.
            new_name_base = settings['new_spectrum_name']
            all_labels = {s['label'] for s in current_state}
            final_names = []
            for idx, _ in enumerate(new_spectra):
                candidate_base = new_name_base if len(new_spectra) == 1 else f"{new_name_base}_{idx + 1}"
                candidate = candidate_base
                suffix = 1
                while candidate in all_labels or candidate in final_names:
                    candidate = f"{candidate_base}_{suffix}"
                    suffix += 1
                final_names.append(candidate)

            for sp, name in zip(new_spectra, final_names):
                sp['label'] = name
                # Same reasoning as Combine Spectra — guarantee a fresh
                # identity regardless of how the manager built this result.
                sp['metadata'] = dict(sp.get('metadata') or {})
                sp['metadata']['unique_id'] = str(uuid.uuid4())

            if add_as_new:
                # Originals are left untouched; new spectra are appended
                # alongside everything currently in the list.
                output_spectra = current_state + new_spectra
            else:
                # Replace: remove the source spectra used in the formula,
                # append the result(s) in their place. Source count and
                # output count may differ (e.g. 2 sources -> 3 outputs).
                output_spectra = [s for s in current_state if s['label'] not in source_labels]
                output_spectra.extend(new_spectra)

            self.oc.operations_manager.apply_operation(
                "Spectral Calculator",
                settings,
                spectra_to_process,
                new_state_spectra=output_spectra,
            )

            if add_as_new:
                mgr = self.oc.operations_manager
                if mgr.operations_chain:
                    mgr.operations_chain.pop()
                    mgr.active_operation_index = max(-1, len(mgr.operations_chain) - 1)
                self.oc.register_copy_operation(
                    spectra_to_process, new_spectra,
                    operation_name="Spectral Calculator",
                    pre_state=current_state,
                )

            if progress is not None:
                progress.setLabelText("Updating spectrum list\u2026")
                QApplication.processEvents()

            # Update UI
            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)
            self.controller.spectra_list_widget.blockSignals(True)
            try:
                self.controller.spectra_list_widget.clear()
                for spectrum in self.controller.original_spectra:
                    item = QListWidgetItem(spectrum['label'])
                    item.setFlags(item.flags() | Qt.ItemIsSelectable)
                    item.setData(Qt.UserRole, spectrum_id(spectrum))
                    self.controller.spectra_list_widget.addItem(item)
            finally:
                self.controller.spectra_list_widget.blockSignals(False)

            # Select the new spectra (all of them, if more than one)
            self.controller.spectra_list_widget.blockSignals(True)
            try:
                for name in final_names:
                    items = self.controller.spectra_list_widget.findItems(name, Qt.MatchExactly)
                    if items:
                        items[0].setSelected(True)
            finally:
                self.controller.spectra_list_widget.blockSignals(False)
            if final_names:
                first_items = self.controller.spectra_list_widget.findItems(final_names[0], Qt.MatchExactly)
                if first_items:
                    self.controller.spectra_list_widget.setCurrentItem(first_items[0])
                self.controller.spectrum_selector.on_item_selection_changed()

            self.controller.selected_spectra = (
                spectra_to_process if add_as_new else new_spectra
            )
            if progress is not None:
                progress.setLabelText("Redrawing plot\u2026")
                QApplication.processEvents()
            self.controller.plot_spectra()

            n = len(new_spectra)
            noun = 'spectrum' if n == 1 else 'spectra'
            if add_as_new:
                message = f"{n} result {noun} added to the list. Originals are unchanged."
            else:
                message = f"Replaced the source spectra with {n} result {noun}."
            return True, message

        except Exception as e:
            return False, f'An error occurred during calculation:\n\n{e}'
        finally:
            if progress is not None:
                progress.close()
