# src/controllers/data_analysis/combine_spectra_controller.py

import uuid
from PyQt5.QtWidgets import QApplication, QListWidgetItem
from PyQt5.QtCore import Qt
from src.modules.data_analysis.spectra_combine_manager import CombineSpectraManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_id

logger = get_logger(__name__)


class CombineSpectraController:
    """
    Controller for the Combine Spectra operation (arithmetic combination
    of multiple spectra into one result — sum, difference, average, etc.).

    Same thin-controller pattern as every other extracted controller in
    this codebase — owns a persistent CombineSpectraManager instance and
    holds the commit logic that used to live directly inside
    OperationsController as commit_spectral_arithmetic(). This is the
    LAST of the 13 original commit_<x>() methods to be extracted out of
    OperationsController, closing out that whole series.

    Naming note: this class, this file, and the commit method below are
    all named "combine_spectra" / "CombineSpectraController" — the
    current, user-facing name for this feature — rather than the older
    "spectral_arithmetic" naming the codebase used before it was renamed
    for display purposes. The internal dispatch string is now
    "Combine Spectra" too (previously "Spectral Arithmetic", kept frozen
    in an earlier pass out of caution for saved .snapx compatibility —
    confirmed not needed while the codebase is still under active
    development, so renamed here for full consistency).
    """

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = CombineSpectraManager()

    @property
    def oc(self):
        """Shorthand for the shared OperationsController state this
        commit logic still needs — same pattern as every other extracted
        controller's oc property this session."""
        return self.controller.operations_controller

    # ------------------------------------------------------------------ #
    # Commit — moved here from                                            #
    # OperationsController.commit_spectral_arithmetic, unchanged in       #
    # behavior (dispatch string renamed to "Combine Spectra" — see class  #
    # docstring).                                                         #
    # ------------------------------------------------------------------ #

    def commit_combine_spectra(self, settings, add_as_new, selected_spectra):
        """Commit Combine Spectra directly, called by the dialog's own
        Apply / Add as New buttons rather than through the generic Run
        dispatch.

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        progress = None
        try:
            if not settings:
                return False, 'Parameters for Combine Spectra not set.'

            source_labels = settings.get('source_labels') or [s['label'] for s in selected_spectra]
            source_labels_set = set(source_labels)
            current_state = self.oc.operations_manager.get_current_spectra()
            spectra_to_process = [s for s in current_state if s['label'] in source_labels_set]

            if len(spectra_to_process) != len(source_labels_set):
                return False, (
                    'One or more source spectra could not be found.\n'
                    'Please reopen the dialog and reselect them.'
                )

            # Check x-scale lengths are consistent before attempting vstack
            lengths = {len(s['x_scale']) for s in spectra_to_process}
            if len(lengths) > 1:
                return False, (
                    f"Selected spectra have different x-axis lengths "
                    f"({', '.join(str(l) for l in sorted(lengths))}).\n"
                    "All spectra must have identical x-axes. Apply the same "
                    "Data Range / Linearization to all spectra first."
                )

            # Threshold/message based on the full current spectrum count, not
            # just the (usually small) number of sources being combined —
            # rebuilding the spectrum list afterward costs the same either
            # way, since the WHOLE list gets rebuilt regardless of how many
            # spectra fed into the combination.
            progress = self.oc._show_busy_progress(
                "Combine Spectra",
                f"Combining {len(spectra_to_process)} spectra\u2026",
                len(current_state),
            )

            # Ensure the new spectrum name is unique.
            new_name_base = settings['new_spectrum_name']
            new_name = new_name_base
            all_labels = {s['label'] for s in current_state}
            suffix = 1
            while new_name in all_labels:
                new_name = f"{new_name_base}_{suffix}"
                suffix += 1

            new_spectrum = self.manager.perform_operation(spectra_to_process, settings['operation_type'])
            new_spectrum['label'] = new_name
            # Guarantee a fresh identity regardless of how the manager
            # constructed this result internally — if it ever copies one
            # of the inputs as a template, inheriting that input's
            # unique_id would make _get_current_state_for_selected_spectra
            # treat selecting that one source as also selecting this
            # brand-new result.
            new_spectrum['metadata'] = dict(new_spectrum.get('metadata') or {})
            new_spectrum['metadata']['unique_id'] = str(uuid.uuid4())

            if add_as_new:
                # Originals are left untouched; new spectrum is appended
                # alongside everything currently in the list.
                output_spectra = current_state + [new_spectrum]
            else:
                # Replace: remove the source spectra used in the
                # calculation, append the result in their place.
                output_spectra = [s for s in current_state if s['label'] not in source_labels_set]
                output_spectra.append(new_spectrum)

            self.oc.operations_manager.apply_operation(
                "Combine Spectra",
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
                    spectra_to_process, [new_spectrum],
                    operation_name="Combine Spectra",
                    pre_state=current_state,
                )

            if progress is not None:
                progress.setLabelText("Updating spectrum list\u2026")
                QApplication.processEvents()

            # Controlled UI Update. Only ONE new spectrum is ever created
            # here (unlike operations that produce many), so the direct
            # findItems()+setSelected() below is not the per-item-in-a-loop
            # anti-pattern fixed elsewhere in this app — it's a single,
            # bounded call regardless of how large the spectrum list is.
            self.controller.original_spectra = self.oc.operations_manager.get_current_spectra()
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)
            self.controller.spectra_list_widget.blockSignals(True)
            try:
                self.controller.spectra_list_widget.clear()
                for spectrum in self.controller.original_spectra:
                    item = QListWidgetItem(spectrum['label'])
                    item.setFlags(item.flags() | Qt.ItemIsSelectable)
                    # Identity, not just display text — on_item_selection_
                    # changed() (called just below via findItems/setSelected)
                    # reads this back via Qt.UserRole to rebuild
                    # self.controller.selected_spectra by spectrum_key.
                    item.setData(Qt.UserRole, spectrum_id(spectrum))
                    self.controller.spectra_list_widget.addItem(item)
            finally:
                self.controller.spectra_list_widget.blockSignals(False)

            # Auto-select the newly created spectrum
            new_items = self.controller.spectra_list_widget.findItems(new_spectrum['label'], Qt.MatchExactly)
            if new_items:
                new_items[0].setSelected(True)
                self.controller.spectra_list_widget.setCurrentItem(new_items[0])
                self.controller.spectrum_selector.on_item_selection_changed()

            self.controller.selected_spectra = (
                spectra_to_process if add_as_new else [new_spectrum]
            )
            if progress is not None:
                progress.setLabelText("Redrawing plot\u2026")
                QApplication.processEvents()
            self.controller.plot_spectra(
                progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None
            )

            if add_as_new:
                message = 'Result spectrum added to the list. Originals are unchanged.'
            else:
                message = f"Replaced the source spectra with the combined result '{new_name}'."
            return True, message

        except Exception as e:
            return False, f'An error occurred while combining spectra: {e}'
        finally:
            if progress is not None:
                progress.close()
