
# src/controllers/misc/rename_spectra_controller.py
import copy as _copy
import uuid
from collections import Counter

from PyQt5.QtWidgets import QMessageBox, QListWidgetItem
from PyQt5.QtCore import Qt, QItemSelection, QItemSelectionModel
from src.views.dialogs.misc.rename_spectra_dialog import RenameSpectraDialog
from src.modules.misc.rename_spectra_manager import RenameSpectraManager
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_id
from src.modules.utils.correction_history import append_correction_history
logger = get_logger(__name__)

class RenameSpectraController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = RenameSpectraManager()
        
    def show_dialog(self):
        """Show dialog for renaming spectra."""
        if not self.controller.original_spectra:
            return False
        
        # Get selected labels if any, or all labels if none selected
        selected_items = self.controller.spectra_list_widget.selectedItems()
        
        if selected_items:
            # Use only the selected spectra labels
            labels = [item.text() for item in selected_items]
        else:
            # Use all spectra labels
            labels = [spectrum['label'] for spectrum in self.controller.original_spectra]
        
        # Apply / Add as New are the dialog's own buttons now (see
        # commit_rename) — there's nothing left to do with this dialog's
        # result after it closes, since committing already happened
        # inside it, if at all.
        dialog = RenameSpectraDialog(self.controller.view, labels, commit_callback=self.commit_rename)
        dialog.exec_()
        return True

    def commit_rename(self, renamed_labels, add_as_new):
        """Apply or Add-as-New commit for the Rename dialog's own Apply /
        Add as New buttons — same commit_callback pattern used by every
        other refined operation (see
        OperationsController.commit_sg_smoothing).

        Returns (success: bool, message: str) so the dialog can show its
        own inline feedback.
        """
        if not renamed_labels:
            return False, "No labels were changed."

        if add_as_new:
            return self._commit_rename_as_new(renamed_labels)

        # Replace-in-place: renaming spectra that already appear in
        # earlier operations-history steps doesn't retroactively touch
        # those steps (see apply_renamed_labels below, which registers
        # the rename as a new forward-only step) but can still look
        # confusing to a user paging back through history, so warn up
        # front rather than silently doing it.
        if hasattr(self.controller, 'operations_controller') and \
           hasattr(self.controller.operations_controller, 'operations_manager') and \
           self.controller.operations_controller.operations_manager.operations_chain:

            confirm = QMessageBox.question(
                self.controller.view,
                "Rename Spectra",
                "Renaming spectra may affect the operations history. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return False, "Rename cancelled."

        success, error = self.apply_renamed_labels(renamed_labels)
        if not success:
            return False, error or "The rename could not be applied."

        n = len(renamed_labels)
        noun = 'spectrum' if n == 1 else 'spectra'
        return True, f"Renamed {n} {noun}."

    def apply_renamed_labels(self, renamed_labels):
        """Rename spectra in place and update UI.

        Returns (success: bool, error_message: str or None).
        """
        if not renamed_labels:
            return False, "No labels were changed."
            
        # Check for duplicate names BEFORE applying any changes — every
        # rename in this batch is evaluated as if applied simultaneously,
        # not one at a time against the list's current (pre-rename)
        # labels. A one-at-a-time check incorrectly blocks a genuine
        # swap (e.g. Alpha <-> Beta in the same action): at the moment
        # the first rename is checked, its target name still looks
        # "taken" by the very spectrum that the second rename is about
        # to move out of the way. Only a name that more than one
        # spectrum would still be left holding, after every rename in
        # the batch is accounted for, is a real collision.
        if hasattr(self.controller, 'spectra_list_widget'):
            list_widget = self.controller.spectra_list_widget
            current_labels = [
                list_widget.item(i).text()
                for i in range(list_widget.count())
                if list_widget.item(i)
            ]

            final_labels = [renamed_labels.get(label, label) for label in current_labels]

            counts = Counter(final_labels)
            colliding = sorted({label for label, n in counts.items() if n > 1})

            if colliding:
                names = "', '".join(colliding)
                return False, (
                    f"The name(s) '{names}' would be used by more than one "
                    f"spectrum after this rename. Each spectrum must have a "
                    f"unique name."
                )
                
        # Remember which items were selected — by label, not index. A
        # rename changes a spectrum's alphabetical position, so the list
        # gets rebuilt from scratch below; stale index positions from
        # before that rebuild wouldn't point at the same spectra anymore.
        selected_indices = self.controller.spectrum_selector.selected_indices.copy()
        selected_labels_before = {
            self.controller.original_spectra[i]['label']
            for i in selected_indices
            if i < len(self.controller.original_spectra)
        }
        # Carry selection through the rename itself: a selected spectrum
        # that just got renamed should still count as selected, under
        # its new name.
        selected_labels_after = {
            renamed_labels.get(label, label) for label in selected_labels_before
        }
        
        # Apply renamed labels to spectra using the manager
        changes_made = self.manager.apply_renamed_labels(self.controller.original_spectra, renamed_labels)
        
        # If the spectrum manager has unique IDs, update its internal mappings
        if hasattr(self.controller.import_controller, 'spectrum_manager'):
            sm = self.controller.import_controller.spectrum_manager
            
            # Resolve every (unique_id, old_label, new_label, spectrum)
            # tuple BEFORE mutating anything, then apply in two phases —
            # remove all old-label entries, then write all new-label
            # entries. Doing this one rename at a time instead would let
            # a swap or rotation clobber an entry that hasn't been
            # processed yet: e.g. writing Alpha's spectrum into
            # sm.spectra['Beta'] before the real Beta spectrum has itself
            # been moved out of that key, silently losing it.
            updates = []
            for old_label, new_label in renamed_labels.items():
                unique_id = sm.label_to_id_map.get(old_label)
                if unique_id:
                    updates.append((unique_id, old_label, new_label, sm.spectra.get(old_label)))

            for unique_id, old_label, new_label, spectrum in updates:
                sm.label_to_id_map.pop(old_label, None)
                sm.spectra.pop(old_label, None)

            for unique_id, old_label, new_label, spectrum in updates:
                sm.id_to_label_map[unique_id] = new_label
                sm.label_to_id_map[new_label] = unique_id
                if spectrum is not None:
                    sm.spectra[new_label] = spectrum
                    # Update metadata
                    if hasattr(spectrum, 'metadata') and 'spectrum_name' in spectrum.metadata:
                        spectrum.metadata['spectrum_name'] = new_label
        
        # Register this rename as a new, forward-only step in Operations
        # History — exactly like any other operation. This never reaches
        # backward to touch any earlier snapshot; old steps simply keep
        # showing whatever name was true at that point in time. Simpler
        # and safer than retroactively rewriting history, which is what
        # this used to do via register_renamed_labels() (removed).
        if hasattr(self.controller, 'operations_controller') and \
           hasattr(self.controller.operations_controller, 'operations_manager'):
            om = self.controller.operations_controller.operations_manager

            # Build the new state from the operations manager's own
            # current spectra (a fresh deep copy) and apply the same
            # renames to it, rather than reusing
            # self.controller.original_spectra directly — consistent
            # with how every other commit_* function constructs a new
            # step's output_spectra.
            current_state = om.get_current_spectra()
            # Reuse the SAME tracked manager method used for the live
            # UI-facing rename above, rather than a second, independent
            # rename-application loop. This second loop used to just do
            # spectrum['label'] = renamed_labels[...] directly, with NO
            # correction_history tracking at all — harmless as long as
            # current_state happened to be the SAME objects as
            # self.controller.original_spectra, but current_state comes
            # fresh from the operations manager's own stored snapshots,
            # which become DIFFERENT objects the moment any other
            # operation (SG-Smoothing, Manual Baseline, etc.) runs in
            # between two renames — that operation builds its own
            # independent copies. From that point on, this was renaming
            # a completely different, untracked set of objects than the
            # ones the tracked call above ever touched — confirmed to be
            # exactly why a rename's history entry silently disappeared
            # whenever another operation happened in between two renames.
            affected_spectra = [s for s in current_state if s['label'] in renamed_labels]
            if affected_spectra:
                self.manager.apply_renamed_labels(current_state, renamed_labels)

            if affected_spectra:
                om.apply_operation(
                    'Rename', {'renames': dict(renamed_labels)},
                    affected_spectra, new_state_spectra=current_state
                )
        
        # Re-sort and rebuild the list widget from scratch — a rename can
        # change a spectrum's alphabetical position, so just updating
        # each item's text in place (the old behavior) left the list out
        # of order until something else happened to trigger a resort,
        # unlike Copy/Add as New, which already resort immediately.
        self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)
        
        self.controller.spectrum_selector.is_batch_updating = True
        self.controller.spectra_list_widget.blockSignals(True)
        try:
            self.controller.spectra_list_widget.clear()
            rows_to_select = []
            for i, spectrum in enumerate(self.controller.original_spectra):
                item = QListWidgetItem(spectrum['label'])
                item.setFlags(item.flags() | Qt.ItemIsSelectable)
                item.setData(Qt.UserRole, spectrum_id(spectrum))
                self.controller.spectra_list_widget.addItem(item)
                if spectrum['label'] in selected_labels_after:
                    rows_to_select.append(i)
            # Batch selection — same fix as the confirmed anti-pattern
            # found elsewhere in this app (Map2D, Peak Fitting, the main
            # spectra-list rebuild): calling item.setSelected(True) once
            # per row in a loop has a real, measurable per-call cost that
            # scales with how many rows are being selected — confirmed
            # to cost 83 of a ~90-second operation at ~4675 items
            # elsewhere. A batch rename can plausibly select many rows
            # here too, so this gets the same one-shot fix rather than
            # re-introducing that per-item cost in a new spot.
            if rows_to_select:
                widget = self.controller.spectra_list_widget
                model = widget.model()
                selection = QItemSelection()
                for row in rows_to_select:
                    idx = model.index(row, 0)
                    selection.select(idx, idx)
                widget.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
        finally:
            self.controller.spectra_list_widget.blockSignals(False)
            self.controller.spectrum_selector.is_batch_updating = False
        
        # Resync selected_indices from the rebuilt (and now differently
        # ordered) list, by label rather than the stale positions
        # captured before the rebuild.
        selected_indices = {
            i for i, spectrum in enumerate(self.controller.original_spectra)
            if spectrum['label'] in selected_labels_after
        }
        self.controller.spectrum_selector.selected_indices = selected_indices
        
        # Update spectrum counts and refresh the plot if in interactive mode
        self.controller.spectrum_selector.update_spectra_count_label()
        if self.controller.interactive_mode_checkbox.isChecked() and selected_indices:
            self.controller.selected_spectra = [
                self.controller.original_spectra[idx]
                for idx in selected_indices
            ]
            self.controller.plot_spectra()
                
        # Update selected_spectra with new labels
        self.controller.selected_spectra = [
            self.controller.original_spectra[idx]
            for idx in selected_indices
        ]
        
        return changes_made, None

    def _commit_rename_as_new(self, renamed_labels):
        """Keep the original spectra unchanged and add renamed copies as
        new spectra, using the exact names typed into the dialog's New
        Label column — unlike every other 'Add as New' operation (e.g.
        commit_sg_smoothing), which auto-suffixes the original label,
        here the user-provided name IS the new spectrum's label, so no
        suffixing happens.

        Returns (success: bool, message: str).
        """
        # Full current label set from the live list widget, not just the
        # (possibly smaller) subset shown in the dialog, so the collision
        # check also catches a new label clashing with a spectrum outside
        # that subset.
        list_widget = self.controller.spectra_list_widget
        current_labels = {
            list_widget.item(i).text()
            for i in range(list_widget.count())
            if list_widget.item(i)
        }

        new_labels = list(renamed_labels.values())
        counts = Counter(new_labels)
        colliding = sorted({
            label for label in new_labels
            if counts[label] > 1 or label in current_labels
        })
        if colliding:
            names = "', '".join(colliding)
            return False, (
                f"The name(s) '{names}' are already in use or duplicated "
                f"within this rename. Each spectrum must have a unique name."
            )

        # Build the new spectra fresh under their new labels, each with a
        # fresh identity — NOT copy.deepcopy(source), which inherited the
        # ENTIRE original spectrum's metadata (file path, column index,
        # import parameters, etc.), meaningless for a spectrum that was
        # never separately imported from anywhere. Same fix as Peak
        # Fitting's fit/residual spectra and Copy Spectra; see
        # PeakFittingController for the full reasoning. Only
        # x_scale/y_scale carry over; metadata starts empty and gets
        # exactly what's relevant: a fresh identity and the
        # previous_label/new_label correction_history entry below, which
        # already correctly identifies which spectrum this is a renamed
        # copy of.
        source_by_label = {s['label']: s for s in self.controller.original_spectra}
        new_spectra = []
        copied_spectra = []
        for old_label, new_label in renamed_labels.items():
            source = source_by_label.get(old_label)
            if source is None:
                continue
            spec = {
                'label': new_label,
                'x_scale': source['x_scale'].copy(),
                'y_scale': source['y_scale'].copy(),
                'metadata': {'unique_id': str(uuid.uuid4())},
            }
            # Same previous-name tracking as the in-place rename path
            # (RenameSpectraManager.apply_renamed_labels) — see that
            # method for the full reasoning.
            spec['metadata']['correction_history'] = append_correction_history(
                spec['metadata'], 'Rename',
                {'previous_label': old_label, 'new_label': new_label}
            )
            new_spectra.append(spec)
            copied_spectra.append(source)

        if not new_spectra:
            return False, "No matching spectra were found to copy."

        # Register in Operations History as 'Rename (add as new)', reusing
        # the same forward-only, non-retroactive helper as every other
        # Add-as-New operation. This also updates the operations
        # manager's own current-spectra state, which is what
        # self.controller.original_spectra is resynced from below.
        if hasattr(self.controller, 'operations_controller'):
            self.controller.operations_controller.register_copy_operation(
                copied_spectra, new_spectra, operation_name='Rename'
            )
            self.controller.original_spectra = \
                self.controller.operations_controller.operations_manager.get_current_spectra()
        else:
            self.controller.original_spectra = (
                self.controller.original_spectra + [_copy.deepcopy(s) for s in new_spectra]
            )
        self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)

        # Mirror into the spectrum manager, same as import does for newly
        # added spectra, so the new copies are addressable by
        # label/unique_id just like any other spectrum.
        if hasattr(self.controller.import_controller, 'spectrum_manager'):
            sm = self.controller.import_controller.spectrum_manager
            from src.modules.core.spectrum_manager import Spectrum
            for spec in new_spectra:
                sm.spectra[spec['label']] = Spectrum(
                    x_scale=spec['x_scale'], y_scale=spec['y_scale'],
                    metadata=dict(spec['metadata'])
                )
                uid = spec['metadata']['unique_id']
                sm.id_to_label_map[uid] = spec['label']
                sm.label_to_id_map[spec['label']] = uid

        # Rebuild the list widget and select the newly added spectra.
        new_labels_set = set(renamed_labels.values())
        self.controller.spectrum_selector.is_batch_updating = True
        self.controller.spectra_list_widget.blockSignals(True)
        try:
            self.controller.spectra_list_widget.clear()
            rows_to_select = []
            for i, spectrum in enumerate(self.controller.original_spectra):
                item = QListWidgetItem(spectrum['label'])
                item.setFlags(item.flags() | Qt.ItemIsSelectable)
                item.setData(Qt.UserRole, spectrum_id(spectrum))
                self.controller.spectra_list_widget.addItem(item)
                if spectrum['label'] in new_labels_set:
                    rows_to_select.append(i)
            # Batch selection — same fix as above; see that comment for
            # the full reasoning.
            if rows_to_select:
                widget = self.controller.spectra_list_widget
                model = widget.model()
                selection = QItemSelection()
                for row in rows_to_select:
                    idx = model.index(row, 0)
                    selection.select(idx, idx)
                widget.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
        finally:
            self.controller.spectra_list_widget.blockSignals(False)
            self.controller.spectrum_selector.is_batch_updating = False

        selected_indices = {
            i for i, spectrum in enumerate(self.controller.original_spectra)
            if spectrum['label'] in new_labels_set
        }
        self.controller.spectrum_selector.selected_indices = selected_indices
        self.controller.spectrum_selector.update_spectra_count_label()

        self.controller.selected_spectra = [
            self.controller.original_spectra[idx] for idx in selected_indices
        ]
        if self.controller.interactive_mode_checkbox.isChecked():
            self.controller.plot_spectra()

        n = len(new_spectra)
        noun = 'spectrum' if n == 1 else 'spectra'
        new_names = self.controller.operations_controller._format_names_for_message(
            sorted(new_labels_set)
        ) if hasattr(self.controller, 'operations_controller') and \
            hasattr(self.controller.operations_controller, '_format_names_for_message') \
            else ", ".join(sorted(new_labels_set))
        return True, f"Added {n} new {noun}: {new_names}."
