# src/controllers/core/operations_controller.py

import uuid
from PyQt5.QtWidgets import QDialog, QMessageBox, QProgressDialog, QApplication
from src.views.dialogs.data_analysis.normalization_dialog import NormalizationDialog
from src.views.dialogs.data_analysis.operations_summary_dialog import OperationsSummaryDialog
from src.modules.data_analysis.incremental_operations_manager import IncrementalOperationsManager
from src.views.dialogs.data_analysis.savitzky_golay_dialog import SavitzkyGolayDialog
from PyQt5.QtWidgets import QListWidgetItem
from PyQt5.QtCore import Qt, QItemSelection, QItemSelectionModel
from src.modules.utils.spectrum_identity import spectrum_key, spectrum_id
from datetime import datetime
from src.views.dialogs.data_analysis.svd_background_dialog import SVDBackgroundDialog
import numpy as np
from src.views.dialogs.data_analysis.spectra_combine_dialog import CombineSpectraDialog
from src.views.dialogs.data_analysis.automated_baseline_dialog import AutomatedBaselineDialog
from src.views.dialogs.data_analysis.snip_baseline_dialog import SNIPBaselineDialog
from src.views.dialogs.visualization_analysis.band_ratio_dialog import BandRatioDialog
from src.controllers.visualization_analysis.band_ratio_controller import BandRatioController
from src.views.dialogs.visualization_analysis.reference_matching_dialog import ReferenceMatchingDialog
from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import validate_common_x_axis
logger = get_logger(__name__)

class OperationsController:
    def __init__(self, main_controller):
        self.controller = main_controller
        self.current_parameters = {}  # Store parameters for each operation
        self.operations = {
            # "Data range" intentionally NOT listed here — applied via
            # its own dialog's Apply/Add as New buttons (see
            # commit_data_range), not through this generic Run dispatch.
            # "Normalization" intentionally NOT listed here — applied via
            # its own dialog's Apply/Add as New buttons (see
            # commit_normalization), not through this generic Run dispatch.
            # "SVD Interpolation" intentionally NOT listed here — commits
            # internally via SVDInterpolationController.commit_generated_
            # spectra(), called directly from its own dialog, not through
            # this generic Run dispatch.
            # "SG-smoothing" intentionally NOT listed here — applied via
            # its own dialog's Apply/Add as New buttons (see
            # commit_sg_smoothing), not through this generic Run dispatch.
            # "Manual baseline" intentionally NOT listed here — applied via
            # its own dialog's Apply/Add as New buttons (see
            # commit_manual_baseline), not through this generic Run dispatch.
            # "SVD background" intentionally NOT listed here — applied via
            # its own dialog's Apply/Add as New buttons (see
            # commit_svd_background), not through this generic Run dispatch.
            # "Interactive subtraction" intentionally NOT listed here —
            # it's applied via its own dialog's Apply/Add as New buttons
            # (see commit_interactive_subtraction), not through this
            # generic Run dispatch. Selecting it in the dropdown and
            # clicking Configure still works, since show_parameters_dialog
            # checks the operation name directly rather than this dict.
            # "Combine Spectra" intentionally NOT listed here — applied via
            # the dialog's own Apply/Add as New buttons (see
            # CombineSpectraController.commit_combine_spectra), not
            # through this generic Run dispatch.
            # "Spectral Calculator" intentionally NOT listed here — applied
            # via its own dialog's Apply/Add as New buttons (see
            # commit_spectral_calculator), not through this generic Run dispatch.
            # "Automated Baseline" intentionally NOT listed here — applied
            # via its own dialog's Apply/Add as New buttons (see
            # commit_automated_baseline), not through this generic Run dispatch.
            # "SNIP Baseline" intentionally NOT listed here — applied via
            # its own dialog's Apply/Add as New buttons (see
            # commit_snip_baseline), not through this generic Run dispatch.
            "Band Ratio":         self.handle_band_ratio,
            "Reference Matching": self.handle_reference_matching,
            "Peak Fitting": self.handle_peak_fitting,
            "Melting Curve Analysis": self.handle_melting_curve_analysis,
            # "Spike removal" intentionally NOT listed here — applied via
            # its own dialog's Apply/Add as New buttons (see
            # commit_spike_removal), not through this generic Run dispatch.
            # "Cosmic ray removal" intentionally NOT listed here — applied
            # via its own dialog's Apply/Add as New buttons (see
            # commit_cosmic_ray_removal), not through this generic Run dispatch.
            # "Resolution enhancement" intentionally NOT listed here —
            # applied via its own dialog's Apply/Add as New buttons (see
            # commit_resolution_enhancement), not through this generic Run dispatch.
            # "X-axis alignment" intentionally NOT listed here — applied via
            # its own dialog's Apply/Add as New buttons (see
            # commit_xaxis_alignment), not through this generic Run dispatch.
            # "FFT Denoising" intentionally NOT listed here — applied via
            # its own dialog's Apply/Add as New buttons (see
            # commit_fft_denoising), not through this generic Run dispatch.
            # "CD Unit Conversion" intentionally NOT listed here — applied
            # via its own dialog's Apply/Add as New buttons (see
            # commit_cd_conversion), not through this generic Run dispatch.
        }
        self.last_selection_hash = None  # Track selection changes
        self.operations_manager = IncrementalOperationsManager()
        self.last_op_settings = {}
        
        # Add reference to main controller
        self.operations_manager._controller = main_controller
        
        # Connect the signal for baseline state changes
        if hasattr(self.operations_manager, 'baseline_state_changed'):
            self.operations_manager.baseline_state_changed.connect(self.on_baseline_state_changed)
        
        self.setup_ui()

    # Below this size, a manager call is fast enough (profiled: SG-
    # Smoothing and SNIP Baseline both complete a 1000-spectrum, 1500-
    # point batch in under 1 second) that a progress dialog would only
    # flash and vanish — more distracting than reassuring. Large,
    # slower batches (thousands of spectra, high point counts, or many
    # SNIP iterations) are exactly where "is this frozen?" becomes a
    # real question, which is what this is actually for.
    _PROGRESS_DIALOG_SPECTRA_THRESHOLD = 200

    def _show_busy_progress(self, title, message, n_spectra):
        """Show a simple indeterminate 'this may take a moment' dialog
        around a single, blocking (non-yielding) long-running call —
        e.g. a per-spectrum-loop manager method with no progress
        callback of its own to report through.

        Not animated DURING the actual computation — Qt's event loop is
        blocked for the duration of one synchronous call, the same way
        it would be for any other blocking call, so the spinner won't
        visibly spin mid-computation. It still gives real value: shown
        immediately (processEvents() below forces the initial paint
        before the blocking call starts), it confirms the app hasn't
        frozen/crashed and sets the expectation that real work is
        happening, rather than an unresponsive-looking window with no
        feedback at all — which is what every one of these commits
        showed before this. Same QProgressDialog widget already used
        elsewhere in this app (see import_controller.py's actual
        working usage) — no new dependency.

        Returns None (not shown) below the spectra-count threshold,
        where the call is fast enough that a flash-and-vanish dialog
        would be more distracting than useful. Callers must guard the
        matching close() call:

            progress = self._show_busy_progress("SNIP Baseline", "…", len(spectra))
            try:
                ...long call...
            finally:
                if progress is not None:
                    progress.close()
        """
        if n_spectra < self._PROGRESS_DIALOG_SPECTRA_THRESHOLD:
            return None

        progress = QProgressDialog(message, None, 0, 0, self.controller.view)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)  # no per-item granularity to cancel mid-way through a single call
        progress.show()
        QApplication.processEvents()
        return progress

    def _rebuild_spectra_list_with_selection(self, highlight_ids):
        """Rebuild spectra_list_widget from self.controller.original_spectra,
        highlighting every spectrum whose identity (spectrum_key(spectrum) —
        metadata['unique_id'], see src.modules.utils.spectrum_identity) is in
        highlight_ids, and keep spectrum_selector's cached selection in sync.

        Callers must build highlight_ids with spectrum_key(spectrum) — NOT
        spectrum['label'] directly — for each spectrum to highlight. Every
        call site used to build a label set instead (this parameter was
        called highlight_labels); switched to identity for the same reason
        this app's Managers already key their own persistent state by
        unique_id rather than label — see developer_guide_help.py's
        "Golden Rule: Spectrum Identity". A label match works today only
        because labels happen to be globally unique at every moment; an
        identity match doesn't rely on that invariant holding.

        Every commit_* method needs this right after an Apply/Add as New:
        the list widget has to be cleared and rebuilt (labels, indices, and
        the total spectra count may all have changed), with the newly
        affected/added spectra highlighted.

        The rebuild is wrapped in blockSignals so it doesn't fire
        itemSelectionChanged once per row while items are being added —
        that would be wasteful, and worse, would run the handler against
        partial/intermediate selection states that were never meant to
        be seen. But blocking signals means
        spectrum_selector.get_selected_spectra() — which reads
        spectrum_selector.selected_indices, a cache normally kept in sync
        by on_item_selection_changed() firing on that very signal — goes
        stale: the widget shows the right spectra highlighted, but the
        cache still reflects whatever was selected BEFORE this commit, so
        reopening any dialog that asks "what's currently selected" gets a
        wrong answer. This was a confirmed bug (found and fixed first for
        Interactive Subtraction) that turned out to be duplicated, in this
        exact same broken shape, across every operation that hand-rolled
        this rebuild inline. Recomputing selected_indices explicitly here,
        right after unblocking, is what keeps it truthful — every caller
        gets this fixed for free instead of needing its own copy of the
        fix.

        Selection is applied as ONE batched QItemSelection instead of
        calling item.setSelected(True) once per highlighted row.
        Confirmed by profiling a real session (4675 spectra): the
        per-item calls alone accounted for 83 of a ~90-second Apply —
        blockSignals() only suppresses signal EMISSION, it does nothing
        about the cost of the call itself, which independently does
        real internal Qt work on every single invocation. Building a
        QItemSelection and applying it once is a single atomic
        operation regardless of how many rows are selected — confirmed
        by direct benchmarking to be 200x+ faster at this scale, for
        both a contiguous block and a scattered selection.

        Does NOT set self.controller.selected_spectra or call
        plot_spectra() — callers already do that themselves immediately
        afterward with whatever operation-specific source list is
        correct (e.g. processed_spectra vs. source_spectra), which is not
        always simply "whatever's highlighted by label" (Add as New can
        highlight the ORIGINAL spectra's labels while wanting to plot the
        NEW ones).
        """
        widget = self.controller.spectra_list_widget
        widget.blockSignals(True)
        try:
            widget.clear()
            rows_to_select = []
            for i, spectrum in enumerate(self.controller.original_spectra):
                item = QListWidgetItem(spectrum['label'])
                item.setData(Qt.UserRole, spectrum_id(spectrum))
                item.setFlags(item.flags() | Qt.ItemIsSelectable)
                widget.addItem(item)
                if spectrum_key(spectrum) in highlight_ids:
                    rows_to_select.append(i)

            if rows_to_select:
                model = widget.model()
                selection = QItemSelection()
                for row in rows_to_select:
                    idx = model.index(row, 0)
                    selection.select(idx, idx)
                widget.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
        finally:
            widget.blockSignals(False)

        self.controller.spectrum_selector.selected_indices = {
            i for i, s in enumerate(self.controller.original_spectra)
            if spectrum_key(s) in highlight_ids
        }

        # NOTE: this used to force interactive_mode_checkbox back to
        # checked here ("every operation always redraws, so keep the
        # checkbox honest about it"). That was itself the bug: with
        # Interactive Update deliberately left off (e.g. a large 2D map,
        # to avoid redrawing thousands of spectra after every click),
        # applying ANY operation silently flipped it back on and drew
        # anyway, with no way to opt out. See _redraw_after_operation()
        # below, which every commit_* method now calls instead of calling
        # self.controller.plot_spectra() directly right after this — it
        # respects the checkbox instead of overriding it, exactly like an
        # ordinary spectrum-selection change already does.

    def _redraw_after_operation(self, progress=None, context='operation'):
        """Redraw the plot right after a commit_* operation (Apply /
        Add as New) — but ONLY if 'Interactive Update' is still checked.

        Every commit_* method used to call self.controller.plot_spectra()
        unconditionally here, and _rebuild_spectra_list_with_selection()
        then forced interactive_mode_checkbox back to checked to match —
        on the reasoning that since a redraw was about to happen
        regardless, the checkbox should stay 'honest' about it. That was
        itself the reported bug: with Interactive Update deliberately
        left off (e.g. a large 2D map, specifically to avoid redrawing
        thousands of spectra after every click), applying ANY operation
        silently re-checked it and drew anyway, with no way to opt out.

        Now this just applies the exact same rule an ordinary spectrum-
        selection change already follows (see
        spectrum_selector_controller.py's isChecked() checks): when
        unchecked, this is a no-op — self.controller.selected_spectra and
        the spectra list widget's selection are already updated by the
        caller before this is called, so nothing about the operation's
        result is lost. The user just sees it only after pressing
        'Refresh Plot', same as any other change made while Interactive
        Update is off.

        progress : the caller's QProgressDialog, or None — same object
            already passed to plot_spectra()'s progress_callback by every
            caller; used here to update its label text before drawing.
        context : short description used only in the log message if
            plot_spectra() raises (e.g. 'normalization', 'SNIP Baseline').
        """
        if not self.controller.interactive_mode_checkbox.isChecked():
            return
        if progress is not None:
            progress.setLabelText("Redrawing plot\u2026")
            QApplication.processEvents()
        try:
            self.controller.plot_spectra(
                progress_callback=(lambda: QApplication.processEvents()) if progress is not None else None
            )
        except Exception as exc:
            logger.error(f"Error plotting after {context}: {exc}")

    # commit_spectral_arithmetic moved to CombineSpectraController
    # (new file: src/controllers/data_analysis/combine_spectra_controller.py,
    # method renamed to commit_combine_spectra) as part of giving every
    # operation its own dedicated controller instead of OperationsController
    # holding all of them directly. This was the LAST of the 13 original
    # commit_<x>() methods to be extracted. See that file for the current
    # logic — the internal dispatch string was renamed to 'Combine Spectra'
    # too, matching the method/class/file rename (no .snapx backward-
    # compatibility constraint while this codebase is still under active
    # development).


    # commit_spectral_calculator moved to SpectralCalculatorController
    # (src/controllers/data_analysis/spectral_calculator_controller.py)
    # as part of giving Spectral Calculator its own dedicated controller,
    # matching Peak Fitting / NMF / MCR-ALS / Cluster Analysis / PCA
    # Scores, which already had one. See that file for the (behaviorally
    # unchanged) commit logic.

    # commit_svd_background moved to SVDBackgroundController
    # (src/controllers/data_analysis/svd_background_controller.py) as part
    # of giving every operation its own dedicated controller instead of
    # OperationsController holding all of them directly — same extraction
    # already done for Spectral Calculator. See that file for the
    # (behaviorally unchanged) commit logic.


    def on_baseline_state_changed(self, baseline_state):
        """Handle changes to baseline state when jumping between operations.

        baseline_state is keyed by unique_id (BaselineManager._key_for),
        matching the manager's own keys — see commit_manual_baseline, which
        builds this dict from bc_controller.stored_corrections. No spectrum
        lookup is needed here since the manager's methods just take that
        same key straight through.
        """
        if not baseline_state or not hasattr(self.controller, 'baseline_correction_controller'):
            # Clear baseline points when no state is available
            if hasattr(self.controller, 'baseline_correction_controller'):
                self.controller.baseline_correction_controller.manager.clear_all_baselines()
            return
        
        # Restore baseline points for each spectrum
        for key, state in baseline_state.items():
            # Get the controller
            bc_controller = self.controller.baseline_correction_controller
            
            # Clear existing points first
            bc_controller.manager.clear_baseline(key)
            
            # Set fit type and poly order
            bc_controller.manager.set_fit_type(key, state['fit_type'])
            if state['fit_type'] == 'polynomial' and 'poly_order' in state:
                bc_controller.manager.set_poly_order(key, state['poly_order'])
            
            # Add each point
            for point in state['points']:
                bc_controller.manager.add_baseline_point(key, point[0], point[1])        

    def setup_ui(self):
        """Setup the operations UI elements."""
        # Reset/rebuild the tree from its hardcoded CATEGORIES list (see
        # OperationTreeComboBox in main_window.py). Don't call addItems()
        # here — self.operations no longer mirrors what's actually
        # selectable in this combobox (it's just Band Ratio / Reference
        # Matching / Peak Fitting now, which live in the separate Analysis
        # menu, not here), and addItems() falls back to whatever's first
        # in that dict when nothing matches, which is how "Band Ratio" was
        # ending up pre-selected at startup despite never appearing in the
        # popup itself.
        self.controller.view.available_operations_comboBox.clear()
        
        # Connect signals
        self.controller.view.parameters_operations_pushButton.clicked.connect(self.show_parameters_dialog)
        self.controller.view.summary_operations_pushButton.clicked.connect(self.show_operations_summary)
        # The main window's old generic "Apply" button and "Add as new"
        # checkbox were removed — every operation reachable from
        # available_operations_comboBox now commits via its own dialog's
        # Apply / Add as New buttons instead. Band Ratio / Reference
        # Matching / Peak Fitting are unaffected: they're triggered from
        # the separate Analysis menu, not from this combobox.
        
        # Connect operation combobox change signal
        self.controller.view.available_operations_comboBox.currentTextChanged.connect(self.on_operation_changed)        
    
        # Connect to import events to initialize history
        if hasattr(self.controller.import_controller, 'spectra_imported'):
            self.controller.import_controller.spectra_imported.connect(self.initialize_history)
        
        # Connect to spectra clearing event to reset history
        if hasattr(self.controller.import_controller, 'spectra_cleared'):
            self.controller.import_controller.spectra_cleared.connect(self.reset_history)
            
        # Connect to spectra_added signal with a lambda function 
        if hasattr(self.controller.import_controller, 'spectra_added'):
            self.controller.import_controller.spectra_added.connect(
                lambda added_spectra: self._process_added_spectra(added_spectra)
            )
                
        # NOTE: previously hooked into the rename spectra controller here
        # to separately call register_renamed_labels() after every
        # rename. That's now redundant and actively harmful —
        # RenameSpectraController.apply_renamed_labels() already calls
        # register_renamed_labels() directly itself, WITH the resolved
        # unique_id for each rename. This second, hook-based call ran
        # register_renamed_labels() a SECOND time immediately afterward,
        # but without that identity info, falling back to matching by
        # label string alone — which silently undid the correct,
        # identity-aware rename that had just been applied a moment
        # earlier, by re-matching (and incorrectly renaming) whatever
        # unrelated spectrum happened to share that label in an old
        # snapshot. See _hook_into_rename_controller (removed) for the
        # full explanation if this is ever reintroduced.
    
    def _process_added_spectra(self, added_spectra):
        """Handle added spectra without affecting existing operations."""
        logger.debug(f"DEBUG: Processing {len(added_spectra)} added spectra")
        
        # Update the operations manager
        if hasattr(self, 'operations_manager'):
            self.operations_manager.add_spectra_to_original(added_spectra)
            
            # After adding spectra to the operations manager, we need to ensure
            # the operations_manager's active state is updated
            if hasattr(self.operations_manager, 'active_operation_index'):
                # Get the current active operation index
                active_index = self.operations_manager.active_operation_index
                
                # If we're at the original state, the operations_manager's original_spectra should match
                # the controller's original_spectra, but DON'T REINITIALIZE (this preserves import batches)
                if active_index < 0:
                    # Instead of reinitializing, just ensure the active_operation_index stays at -1
                    self.operations_manager.active_operation_index = -1
                else:
                    # We need to update the output_spectra of the current active operation
                    # to include the new spectra
                    if 0 <= active_index < len(self.operations_manager.operations_chain):
                        operation = self.operations_manager.operations_chain[active_index]
                        if 'output_spectra' in operation:
                            # Add the new spectra to the output_spectra of the current operation
                            operation['output_spectra'].extend(added_spectra)

            # Update our original_spectra reference in the main controller
            if hasattr(self.controller, 'original_spectra'):
                for spectrum in added_spectra:
                    # Check if it's already in original_spectra
                    if not any(s['label'] == spectrum['label'] for s in self.controller.original_spectra):
                        # Create deep copy to avoid reference issues
                        spectrum_copy = {}
                        for key, value in spectrum.items():
                            if key in ['x_scale', 'y_scale']:
                                spectrum_copy[key] = value.copy() if hasattr(value, 'copy') else value
                            elif key == 'metadata':
                                spectrum_copy[key] = value.copy() if hasattr(value, 'copy') else value
                            else:
                                spectrum_copy[key] = value

                        self.controller.original_spectra.append(spectrum_copy)
            
            # Check if spectrum_manager in import_controller needs updating
            if hasattr(self.controller, 'import_controller') and hasattr(self.controller.import_controller, 'spectrum_manager'):
                # Make sure spectrum_manager is in sync with original_spectra
                for spectrum in self.controller.original_spectra:
                    label = spectrum['label']
                    if label not in self.controller.import_controller.spectrum_manager.spectra:
                        # This is a complex task - we'd need to recreate Spectrum objects
                        # Fortunately, this should already be done by ImportController.execute_add()
                        pass
    
            # Apply ordering to the spectra (don't redraw)
            if hasattr(self.controller, 'order_spectra'):
                self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)
    
            # Update the list widget without resetting operations
            if hasattr(self.controller, 'spectra_list_widget'):
                # Block signals during update
                self.controller.spectra_list_widget.blockSignals(True)
                
                # Remember currently selected items
                selected_items = [item.text() for item in self.controller.spectra_list_widget.selectedItems()]
                
                try:
                    # Clear and repopulate the list widget
                    self.controller.spectra_list_widget.clear()
                    for spectrum in self.controller.original_spectra:
                        item = QListWidgetItem(spectrum['label'])
                        # Make sure items are selectable and checkable
                        item.setFlags(item.flags() | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                        # Identity, not just display text — see jump_to_
                        # operation_state's comment above for why this
                        # matters on every rebuild of this widget.
                        item.setData(Qt.UserRole, spectrum_id(spectrum))
                        self.controller.spectra_list_widget.addItem(item)

                        # Restore selection for previously selected items
                        if spectrum['label'] in selected_items:
                            item.setSelected(True)
                    
                    # Update spinbox maximum values
                    if hasattr(self.controller.view, 'number_of_rows_spinBox'):
                        self.controller.view.number_of_rows_spinBox.setMaximum(len(self.controller.original_spectra))
                    if hasattr(self.controller.view, 'number_of_columns_spinBox'): 
                        self.controller.view.number_of_columns_spinBox.setMaximum(len(self.controller.original_spectra))
                finally:
                    self.controller.spectra_list_widget.blockSignals(False)

                # Same bug as every commit_* operation had (see
                # _rebuild_spectra_list_with_selection): the selection
                # above was restored on the WIDGET with signals blocked,
                # so spectrum_selector.selected_indices — the cache
                # get_selected_spectra() actually reads — was never told
                # about it, and would otherwise keep pointing at whatever
                # was selected before these spectra were added.
                self.controller.spectrum_selector.selected_indices = {
                    i for i, s in enumerate(self.controller.original_spectra)
                    if s['label'] in selected_items
                }
            
            # Make the spectrum selection frame visible when spectra are added
            if hasattr(self.controller.view, 'spectrum_selection_frame'):
                self.controller.view.spectrum_selection_frame.setVisible(True)
                    
            # Reset the spectrum selector
            if hasattr(self.controller, 'spectrum_selector'):
                self.controller.spectrum_selector.is_batch_updating = True
                try:
                    # Update the selected_indices if needed
                    if hasattr(self.controller.spectrum_selector, 'selected_indices'):
                        current_indices = self.controller.spectrum_selector.selected_indices.copy()
                        
                        # Add a debug print for the selection state
                        logger.debug(f"DEBUG: Current selection indices: {current_indices}")
                    
                    # Force a new UI state for the spectrum selector
                    if hasattr(self.controller.spectrum_selector, 'update_spectra_count_label'):
                        self.controller.spectrum_selector.update_spectra_count_label()
                finally:
                    self.controller.spectrum_selector.is_batch_updating = False
                
                # Call handle_selection_change directly to ensure selection is processed
                if self.controller.spectra_list_widget.count() > 0:
                    # Get the first item
                    first_item = self.controller.spectra_list_widget.item(0)
                    # If there's a handle_selection_change method, call it
                    if hasattr(self.controller.spectrum_selector, 'handle_selection_change'):
                        self.controller.spectrum_selector.handle_selection_change(first_item)

    def initialize_history(self):
        """Initialize the operations manager with the current original spectra."""
        spectra = self.controller.original_spectra
        logger.debug(f"DEBUG: initialize_history called with {len(spectra)} spectra")
        
        if spectra:
            # Pass a copy of the list to avoid reference issues
            spectra_copy = spectra.copy()
            self.operations_manager.initialize_with_spectra(spectra_copy)
            logger.debug(f"DEBUG: History initialized with {len(spectra)} spectra")

    def reset_history(self):
        """Reset operations history when spectra are cleared."""
        self.operations_manager = IncrementalOperationsManager()
        self.current_parameters = {}
        self.last_selection_hash = None

    def _get_selection_hash(self, spectra):
        """Create a hash to identify unique selections."""
        if not spectra:
            return None
        return ','.join(sorted(spectrum['label'] for spectrum in spectra))

    def _format_names_for_message(self, names, limit=10):
        """Join *names* for a result message, truncating long lists.

        Listing every name out in full (as commit_data_range /
        commit_normalization / commit_interactive_subtraction used to do
        unconditionally) is fine for a handful of spectra, but turns into an
        unreadable wall of text in the confirmation dialog once hundreds or
        thousands of spectra are added at once. Past *limit* names, the rest
        are collapsed into a single "and N more" tail instead.
        """
        names = list(names)
        if len(names) <= limit:
            return ', '.join(names)
        shown = ', '.join(names[:limit])
        remaining = len(names) - limit
        return f"{shown}, and {remaining} more"

    # An old, fully-commented-out predecessor of show_parameters_dialog_for()
    # below used to sit here (~290 dead lines) — an early version of the
    # operation-dispatch logic, superseded but never deleted. Removed for
    # good; verified line-by-line beforehand that nothing live was mixed in.

    def show_parameters_dialog_for(self, operation_name, selected_spectra=None):
        """
        Directly open the parameters dialog for a named operation,
        bypassing the combobox.  Used by the Data Analysis panel.
        """
        # Temporarily set the operation so show_parameters_dialog picks it up
        _prev = getattr(self, '_forced_operation', None)
        self._forced_operation = operation_name
        try:
            self.show_parameters_dialog()
        finally:
            self._forced_operation = _prev

    def show_parameters_dialog(self):
        """Show the parameters dialog for the selected operation."""
        # Allow direct invocation from Data Analysis panel
        if getattr(self, '_forced_operation', None):
            operation = self._forced_operation
        else:
            operation = self.controller.view.available_operations_comboBox.currentText()

        if not operation:
            QMessageBox.information(
                self.controller.view, "No Operation Selected",
                "Please choose an operation from the dropdown first."
            )
            return

        selected_spectra = self.controller.spectrum_selector.get_selected_spectra()
        current_selection_hash = self._get_selection_hash(selected_spectra)
        
        # Special handling for baseline correction
        if operation == "Manual baseline":
            if not hasattr(self.controller, 'baseline_correction_controller'):
                from src.controllers.data_analysis.baseline_correction_controller import BaselineCorrectionController
                self.controller.baseline_correction_controller = BaselineCorrectionController(self.controller)
            # Apply / Add as New are the dialog's own buttons now, handled
            # by BaselineCorrectionController.commit_manual_baseline() —
            # there's no separate Run step in the main window for this
            # operation anymore.
            self.controller.baseline_correction_controller.show_dialog(
                commit_callback=self.controller.baseline_correction_controller.commit_manual_baseline
            )
            return
    
        # Special handling for SVD background correction
        if operation == "SVD background":
            selected_spectra = self._get_current_state_for_selected_spectra()
            logger.debug(f"DEBUG: Opening SVD background dialog for {len(selected_spectra)} selected spectra")
            
            # Check minimum number of spectra
            if len(selected_spectra) < 2:
                QMessageBox.warning(
                    self.controller.view,
                    "Insufficient Spectra",
                    "SVD background correction requires at least 2 spectra.\nPlease select more spectra."
                )
                return

            # SVD stacks the spectra into one matrix, so they must share an x-axis.
            # This used to fail INSIDE the manager ("Failed to compute SVD...") and
            # then open the dialog anyway, leaving the user to dismiss a warning and
            # then close a dialog that could never work. Refuse up front instead,
            # with the same wording every other tool uses.
            if not validate_common_x_axis(selected_spectra, self.controller.view,
                                          'SVD background correction'):
                return
            
            # Get current parameters if operation was used before
            current_settings = {}
            if operation in self.current_parameters and self.last_selection_hash == current_selection_hash:
                current_settings = self.current_parameters[operation]
                logger.debug("DEBUG: Using cached SVD settings")
            else:
                logger.debug("DEBUG: Using default SVD settings")
            
            # Create and show the dialog modally — interacting with the main
            # window while baseline points / component selection are being
            # edited was confusing, so this now blocks like the other
            # dialog-owned operations. Commit happens via the dialog's own
            # Apply / Add as New buttons, handled by SVDBackgroundController.
            # commit_svd_background(). The dialog takes a fixed
            # selected_spectra snapshot, same as every other modal dialog —
            # safe since the main window is frozen while it's open, so the
            # selection can't change underneath it.
            if not hasattr(self.controller, 'svd_background_controller'):
                from src.controllers.data_analysis.svd_background_controller import SVDBackgroundController
                self.controller.svd_background_controller = SVDBackgroundController(self.controller)
            # Strip baseline_corrections/inverted_subspectra from
            # current_settings if an operation ran meanwhile, even for
            # this SAME selection -- see
            # SVDBackgroundController.filter_stale_settings's own
            # docstring for the bug this fixes (picks silently restored
            # onto a freshly, but differently, computed SVD).
            current_settings = self.controller.svd_background_controller.filter_stale_settings(
                current_settings)
            try:
                dialog = SVDBackgroundDialog(
                    self.controller.view,
                    current_settings,
                    self.controller,
                    selected_spectra=selected_spectra,
                    commit_callback=self.controller.svd_background_controller.commit_svd_background,
                )
                
                logger.info("DEBUG: SVD dialog created, showing modally...")
                dialog.exec_()
                logger.info("DEBUG: SVD dialog closed")
                    
            except Exception as e:
                logger.error(f"ERROR: Failed to open SVD dialog: {e}")
                logger.exception("Traceback:")
                QMessageBox.critical(
                    self.controller.view,
                    "Dialog Error", 
                    f"Failed to open SVD background dialog:\n{str(e)}"
                )
            return
    
        # Special handling for Interactive Subtraction
        if operation == "Interactive subtraction":
            logger.debug(f"DEBUG: Opening interactive subtraction dialog for {len(selected_spectra)} selected spectra")
            
            # Check minimum number of spectra
            if len(selected_spectra) < 2:
                QMessageBox.warning(
                    self.controller.view,
                    "Insufficient Spectra",
                    "Interactive subtraction requires at least 2 spectra.\nPlease select more spectra."
                )
                return
            
            # Create and show the dialog (non-modal). Apply / Add as New
            # are the dialog's own buttons, handled by
            # InteractiveSubtractionController.commit_interactive_subtraction().
            try:
                isc = self.controller.interactive_subtraction_controller
                dialog = isc.show_dialog(
                    selected_spectra,
                    commit_callback=isc.commit_interactive_subtraction,
                )
                if dialog:
                    logger.info("DEBUG: Interactive subtraction dialog opened successfully")

            except Exception as e:
                logger.error(f"ERROR: Failed to open interactive subtraction dialog: {e}")
                logger.exception("Traceback:")
                QMessageBox.critical(
                    self.controller.view,
                    "Dialog Error", 
                    f"Failed to open interactive subtraction dialog:\n{str(e)}"
                )
            return
    
        if operation == "Data range":
            sc = self.controller.spectral_range_controller
            selected_spectra = self._get_current_state_for_selected_spectra()

            # Reuse whatever was last shown for this exact selection, even if
            # it was never Applied — mirrors the Normalization branch's
            # current_parameters cache, since the manager itself only updates
            # on an actual Apply / Add as New (see apply_settings_to_spectra).
            current_settings = {}
            if operation in self.current_parameters and self.last_selection_hash == current_selection_hash:
                current_settings = self.current_parameters[operation]

            # Apply / Add as New are the dialog's own buttons now, handled
            # by SpectralRangeController.commit_data_range() — there's
            # nothing left to do with this dialog's result after it
            # closes, since committing already happened inside it, if at
            # all. show_dialog still returns the settings shown, purely so
            # reopening the dialog for the same selection starts from
            # where it left off.
            settings = sc.show_dialog(
                selected_spectra,
                commit_callback=sc.commit_data_range,
                current_settings=current_settings,
            )
            if settings:
                self.current_parameters[operation] = settings
                self.last_selection_hash = current_selection_hash

        elif operation == "Normalization":
            # Use normalization controller if it exists
            nc = getattr(self.controller, 'normalization_controller', None)
            if nc is None:
                from src.controllers.data_analysis.normalization_controller import NormalizationController
                nc = NormalizationController(self.controller)
                self.controller.normalization_controller = nc

            selected_spectra = self._get_current_state_for_selected_spectra()
            if not selected_spectra:
                QMessageBox.warning(self.controller.view, "No Spectra Selected",
                                    "Please select at least one spectrum for this operation.")
                return

            # Get current parameters if operation was used before
            current_settings = {}
            if operation in self.current_parameters and self.last_selection_hash == current_selection_hash:
                current_settings = self.current_parameters[operation]

            # Create dialog with current settings and controller reference
            # for plot limits. Apply / Add as New are the dialog's own
            # buttons now, handled by
            # NormalizationController.commit_normalization() — there's
            # nothing left to do with this dialog's result after it
            # closes, since committing already happened inside it, if at all.
            dialog = NormalizationDialog(
                self.controller.view,
                current_settings,
                self.controller,
                selected_spectra=selected_spectra,
                commit_callback=nc.commit_normalization,
            )
            dialog.exec_()
            # Remember the settings shown, purely so reopening the dialog
            # for the same selection starts from where it left off.
            self.current_parameters[operation] = dialog.get_settings()
            self.last_selection_hash = current_selection_hash

        elif operation == "SVD Interpolation":
            # Lazy-create the controller, same pattern as Normalization.
            sic = getattr(self.controller, 'svd_interpolation_controller', None)
            if sic is None:
                from src.controllers.data_analysis.svd_interpolation_controller import SVDInterpolationController
                sic = SVDInterpolationController(self.controller)
                self.controller.svd_interpolation_controller = sic

            selected_spectra = self._get_current_state_for_selected_spectra()

            # No settings cache to restore here (unlike Normalization) —
            # every dialog session starts from a fresh SVD computed over
            # whatever's currently selected, since the selection itself
            # defines the SVD basis, not just a parameter of it. The
            # dialog does all committing internally via
            # SVDInterpolationController.commit_generated_spectra(), same
            # as Normalization's Apply/Add as New buttons.
            sic.show_dialog(selected_spectra)
            return

        elif operation == "X-axis alignment":
            selected_spectra = self._get_current_state_for_selected_spectra()

            if len(selected_spectra) < 2:
                QMessageBox.warning(
                    self.controller.view,
                    'Insufficient spectra',
                    'X-axis alignment requires at least 2 selected spectra.'
                )
                return

            # Lazy-create the controller
            if not hasattr(self.controller, 'xaxis_alignment_controller'):
                from src.controllers.data_analysis.xaxis_alignment_controller import XAxisAlignmentController
                self.controller.xaxis_alignment_controller = XAxisAlignmentController(self.controller)

            xac = self.controller.xaxis_alignment_controller

            # Apply / Add as New are the dialog's own buttons now, handled
            # by XAxisAlignmentController.commit_xaxis_alignment() —
            # there's nothing left to do with this dialog's result after
            # it closes, since committing already happened inside it, if
            # at all. The controller's own _last_settings cache (keyed to
            # this exact selection) remembers whatever was last shown,
            # applied or not.
            settings = xac.show_dialog(selected_spectra, commit_callback=xac.commit_xaxis_alignment)
            if settings is not None:
                self.current_parameters[operation] = settings
                self.last_selection_hash = current_selection_hash

        elif operation == "CD Unit Conversion":
            # Lazy-create the controller, same pattern as X-axis alignment.
            if not hasattr(self.controller, 'cd_unit_conversion_controller'):
                from src.controllers.data_analysis.cd_unit_conversion_controller import CDUnitConversionController
                self.controller.cd_unit_conversion_controller = CDUnitConversionController(self.controller)

            cdc = self.controller.cd_unit_conversion_controller
            selected_spectra = self._get_current_state_for_selected_spectra()

            # Apply / Add as New are the dialog's own buttons now, handled
            # by CDUnitConversionController.commit_cd_conversion() — there's
            # nothing left to do with this dialog's result after it closes,
            # since committing already happened inside it, if at all. The
            # controller's own _last_settings cache remembers whatever
            # sample parameters (path length, concentration, weight) were
            # last shown, applied or not — reused regardless of selection,
            # since every spectrum is converted independently with the
            # same shared parameters (see CDUnitConversionManager docstring).
            settings = cdc.show_dialog(selected_spectra, commit_callback=cdc.commit_cd_conversion)
            if settings is not None:
                self.current_parameters[operation] = settings
                self.last_selection_hash = current_selection_hash

        elif operation == "X-axis Unit Conversion":
            # Lazy-create the controller, same pattern as CD Unit Conversion.
            if not hasattr(self.controller, 'xaxis_unit_conversion_controller'):
                from src.controllers.data_analysis.xaxis_unit_conversion_controller import XAxisUnitConversionController
                self.controller.xaxis_unit_conversion_controller = XAxisUnitConversionController(self.controller)

            xuc = self.controller.xaxis_unit_conversion_controller
            selected_spectra = self._get_current_state_for_selected_spectra()

            # Apply / Add as New are the dialog's own buttons now, handled
            # by XAxisUnitConversionController.commit_xaxis_unit_conversion()
            # — there's nothing left to do with this dialog's result after
            # it closes, since committing already happened inside it, if
            # at all. The dialog itself warns and returns None if nothing
            # is selected (see XAxisUnitConversionController.show_dialog),
            # same as CD Unit Conversion above.
            settings = xuc.show_dialog(selected_spectra, commit_callback=xuc.commit_xaxis_unit_conversion)
            if settings is not None:
                self.current_parameters[operation] = settings
                self.last_selection_hash = current_selection_hash

        elif operation == "Mean-Center Spectra (Dataset)":
            # Lazy-create the controller, same pattern as CD/X-axis Unit
            # Conversion.
            if not hasattr(self.controller, 'mean_centering_controller'):
                from src.controllers.data_analysis.mean_centering_controller import MeanCenteringController
                self.controller.mean_centering_controller = MeanCenteringController(self.controller)

            mcc = self.controller.mean_centering_controller
            selected_spectra = self._get_current_state_for_selected_spectra()

            # Apply / Add as New are the dialog's own buttons now, handled
            # by MeanCenteringController.commit_mean_centering() — there's
            # nothing left to do with this dialog's result after it
            # closes, since committing already happened inside it, if at
            # all. The dialog itself warns and returns None if nothing is
            # selected, same as CD/X-axis Unit Conversion above.
            settings = mcc.show_dialog(selected_spectra, commit_callback=mcc.commit_mean_centering)
            if settings is not None:
                self.current_parameters[operation] = settings
                self.last_selection_hash = current_selection_hash

        elif operation == "Run Batch Pipeline":
            # Lazy-create the controller, same pattern as CD/X-axis Unit
            # Conversion. Unlike those, this dialog has no single
            # "settings" result to persist for reopening — a run picks a
            # SAVED pipeline (its own persistence, see pipeline_manager.py)
            # rather than one-off dialog state, and Apply/Add-as-New are
            # the dialog's own buttons, handled by
            # BatchPipelineController.commit_pipeline_run().
            if not hasattr(self.controller, 'batch_pipeline_controller'):
                from src.controllers.data_analysis.batch_pipeline_controller import BatchPipelineController
                self.controller.batch_pipeline_controller = BatchPipelineController(self.controller)

            selected_spectra = self._get_current_state_for_selected_spectra()
            self.controller.batch_pipeline_controller.show_run_dialog(selected_spectra)

        elif operation == "SG-smoothing":
            selected_spectra = self._get_current_state_for_selected_spectra()
            if not selected_spectra:
                QMessageBox.warning(self.controller.view, "No Spectra Selected",
                                    "Please select at least one spectrum for this operation.")
                return

            # Get current parameters if operation was used before
            current_settings = {}
            if operation in self.current_parameters and self.last_selection_hash == current_selection_hash:
                current_settings = self.current_parameters[operation]
            
            # Apply / Add as New are the dialog's own buttons now,
            # handled by SavitzkyGolayController.commit_sg_smoothing() —
            # there's nothing left to do with this dialog's result after
            # it closes, since committing already happened inside it, if
            # at all. The dialog is modal, so a fixed selected_spectra
            # snapshot taken here is safe — the main-window selection
            # can't change while it's open.
            dialog = SavitzkyGolayDialog(
                self.controller.view,
                current_settings,
                self.controller,
                selected_spectra=selected_spectra,
                commit_callback=self.controller.savitzky_golay_controller.commit_sg_smoothing,
            )
            dialog.exec_()
            settings = dialog.get_settings()
            if settings:
                self.current_parameters[operation] = settings
                self.last_selection_hash = current_selection_hash


        elif operation == "Combine Spectra":
            selected_spectra = self._get_current_state_for_selected_spectra()
            current_selection_hash = self._get_selection_hash(selected_spectra)

            num_selected = len(selected_spectra) 

            if num_selected < 2:
                QMessageBox.warning(self.controller.view, "Insufficient Spectra",
                                    "Please select at least two spectra for this operation.")
                return

            # Get a COPY of the last used settings for this operation —
            # but only if this dialog was last shown for this exact
            # selection. Without this guard, selecting a completely
            # different, unrelated set of spectra would still silently
            # reopen Combine Spectra pre-loaded with whatever name/mode
            # was used last time. Same current_parameters /
            # last_selection_hash guard every other operation in this
            # dispatcher already uses. Always keyed by the canonical
            # "Combine Spectra" string — that's the single key this settings
            # cache is always stored under below.
            last_settings = {}
            if (self.last_selection_hash == current_selection_hash and
                    "Combine Spectra" in self.current_parameters):
                last_settings = self.last_op_settings.get("Combine Spectra", {}).copy()

            # Pass the last_settings to the dialog. Apply / Add as New are
            # the dialog's own buttons now, handled by
            # CombineSpectraController.commit_combine_spectra() — exec_()
            # is called unconditionally since there's nothing left to do
            # with the result after it closes; committing already
            # happened inside the dialog, if at all.
            if not hasattr(self.controller, 'combine_spectra_controller'):
                from src.controllers.data_analysis.combine_spectra_controller import CombineSpectraController
                self.controller.combine_spectra_controller = CombineSpectraController(self.controller)
            dialog = CombineSpectraDialog(
                self.controller.view, selected_spectra, num_selected,
                current_settings=last_settings,
                commit_callback=self.controller.combine_spectra_controller.commit_combine_spectra,
                main_controller=self.controller,
            )
            dialog.exec_()
            settings = dialog.get_settings()
            if settings:
                settings['source_labels'] = [s['label'] for s in selected_spectra]
                # Always store under canonical key so commit_spectral_arithmetic finds it
                self.current_parameters["Combine Spectra"] = settings.copy()
                # Save a COPY for the next time the dialog is opened.
                self.last_op_settings["Combine Spectra"] = settings.copy()
                self.last_selection_hash = current_selection_hash

        elif operation == "FFT Denoising":
            selected_spectra = self._get_current_state_for_selected_spectra()
            if not selected_spectra:
                QMessageBox.warning(self.controller.view, "No Spectra Selected",
                                    "Please select at least one spectrum.")
                return
            if not hasattr(self.controller, 'fft_denoising_controller'):
                from src.controllers.data_analysis.fft_denoising_controller import FFTDenoisingController
                self.controller.fft_denoising_controller = FFTDenoisingController(self.controller)
            fdc = self.controller.fft_denoising_controller

            # Reuse whatever was last shown for this exact selection, even
            # if it was never Applied — mirrors Data range / Normalization's
            # current_parameters cache.
            cached_settings = None
            if operation in self.current_parameters and self.last_selection_hash == current_selection_hash:
                cached_settings = self.current_parameters[operation]

            # Apply / Add as New are the dialog's own buttons now, handled
            # by FFTDenoisingController.commit_fft_denoising() — there's
            # nothing left to do with this dialog's result after it
            # closes, since committing already happened inside it, if at all.
            settings = fdc.show_dialog(
                selected_spectra,
                commit_callback=fdc.commit_fft_denoising,
                current_settings=cached_settings,
            )
            if settings is not None:
                self.current_parameters['FFT Denoising'] = settings
                self.last_selection_hash = current_selection_hash


        elif operation == "Spectral Calculator":
            # Delegated to SpectralCalculatorController — this operation
            # now has its own dedicated controller (bridging its dialog
            # and manager) instead of embedding that logic directly in
            # this dispatch method, matching Peak Fitting / NMF / MCR-ALS
            # / Cluster Analysis / PCA Scores, which already had one.
            if not hasattr(self.controller, 'spectral_calculator_controller'):
                from src.controllers.data_analysis.spectral_calculator_controller import SpectralCalculatorController
                self.controller.spectral_calculator_controller = SpectralCalculatorController(self.controller)
            self.controller.spectral_calculator_controller.show_dialog()

        elif operation == "Automated Baseline":
            selected_spectra = self._get_current_state_for_selected_spectra()
            current_selection_hash = self._get_selection_hash(selected_spectra)
            
            if not selected_spectra:
                QMessageBox.warning(self.controller.view, "No Spectra Selected",
                                    "Please select at least one spectrum for this operation.")
                return

            # Reuse whatever was last shown for this exact selection, even
            # if it was never Applied — mirrors Data range / Normalization's
            # current_parameters cache.
            current_settings = {}
            if operation in self.current_parameters and self.last_selection_hash == current_selection_hash:
                current_settings = self.current_parameters[operation]

            # Apply / Add as New are the dialog's own buttons now, handled
            # by AutomatedBaselineController.commit_automated_baseline() —
            # there's nothing left to do with this dialog's result after
            # it closes, since committing already happened inside it, if
            # at all.
            if not hasattr(self.controller, 'automated_baseline_controller'):
                from src.controllers.data_analysis.automated_baseline_controller import AutomatedBaselineController
                self.controller.automated_baseline_controller = AutomatedBaselineController(self.controller)
            dialog = AutomatedBaselineDialog(
                self.controller.view, selected_spectra,
                current_settings=current_settings,
                commit_callback=self.controller.automated_baseline_controller.commit_automated_baseline,
                main_controller=self.controller,
            )
            dialog.exec_()
            settings = dialog.get_settings()
            if settings:
                self.current_parameters[operation] = settings
                self.last_selection_hash = current_selection_hash


        elif operation == "SNIP Baseline":
            selected_spectra = self._get_current_state_for_selected_spectra()
            current_selection_hash = self._get_selection_hash(selected_spectra)
            if not selected_spectra:
                QMessageBox.warning(self.controller.view, "No Spectra Selected",
                                    "Please select at least one spectrum for this operation.")
                return

            current_settings = {}
            if operation in self.current_parameters and self.last_selection_hash == current_selection_hash:
                current_settings = self.current_parameters[operation]

            # Apply / Add as New are the dialog's own buttons now, handled
            # by SNIPBaselineController.commit_snip_baseline() — there's
            # nothing left to do with this dialog's result after it
            # closes, since committing already happened inside it, if at all.
            if not hasattr(self.controller, 'snip_baseline_controller'):
                from src.controllers.data_analysis.snip_baseline_controller import SNIPBaselineController
                self.controller.snip_baseline_controller = SNIPBaselineController(self.controller)
            dialog = SNIPBaselineDialog(
                self.controller.view, selected_spectra,
                current_settings=current_settings,
                commit_callback=self.controller.snip_baseline_controller.commit_snip_baseline,
                main_controller=self.controller,
            )
            dialog.exec_()
            settings = dialog.get_settings()
            if settings:
                self.current_parameters[operation] = settings
                self.last_selection_hash = current_selection_hash

        elif operation == "Band Ratio":
            selected_spectra = self._get_current_state_for_selected_spectra()
            if not selected_spectra:
                QMessageBox.warning(self.controller.view, "No Spectra Selected",
                                    "Please select at least one spectrum.")
                return
            last_settings = {}
            if (operation in self.current_parameters and
                    self.last_selection_hash == current_selection_hash):
                last_settings = self.last_op_settings.get("Band Ratio", {}).copy()
            if not hasattr(self.controller, 'band_ratio_controller'):
                self.controller.band_ratio_controller = BandRatioController(self.controller)
            dialog = BandRatioDialog(self.controller.view, selected_spectra,
                                     current_settings=last_settings,
                                     controller=self.controller.band_ratio_controller)
            result = dialog.exec_()
            # Remember whatever was last configured regardless of how the
            # dialog closed (OK, Cancel, or the window's own X) -- every
            # other dialog in this app (CD/X-axis unit conversion, FFT
            # Denoising, Combine Spectra, ...) remembers settings on any
            # close, and this dialog's OK/Cancel pair is otherwise
            # confusingly inconsistent with that if only OK does it.
            # get_settings() reads straight from the dialog's own current
            # widget state, so it's just as valid to read after Cancel/X
            # as after OK.
            settings = dialog.get_settings()
            if settings:
                self.current_parameters["Band Ratio"] = settings.copy()
                self.last_op_settings["Band Ratio"]   = settings.copy()
                self.last_selection_hash = current_selection_hash
            # Actually saving the computed ratio(s) to each spectrum's
            # metadata and registering the operation in history stays
            # gated on OK specifically -- unlike CD/X-axis/FFT/Combine
            # Spectra, this dialog has no separate Apply/Add as New step;
            # OK IS its commit action, so Cancel/X must still mean "don't
            # apply this" even though settings are now remembered either
            # way. handle_band_ratio() does real work (unlike
            # handle_reference_matching(), which is an intentional no-op
            # since that tool is fully self-contained in its own dialog).
            if result == QDialog.Accepted and settings:
                self.handle_band_ratio()

        elif operation == "Isosbestic Point Detection":
            selected_spectra = self._get_current_state_for_selected_spectra()
            last_settings = {}
            if (operation in self.current_parameters and
                    self.last_selection_hash == current_selection_hash):
                last_settings = self.last_op_settings.get("Isosbestic Point Detection", {}).copy()
            if not hasattr(self.controller, 'isosbestic_point_controller'):
                from src.controllers.visualization_analysis.isosbestic_point_controller import IsosbesticPointController
                self.controller.isosbestic_point_controller = IsosbesticPointController(self.controller)
            ipc = self.controller.isosbestic_point_controller
            # Read-only analysis (see IsosbesticPointController's
            # docstring) — the dialog's own Results table + Export CSV IS
            # the deliverable, so unlike Band Ratio there's no
            # handle_...() post-step to save anything into spectra
            # metadata or Operations History. show_dialog() validates
            # selection/common-x-axis and warns the user itself if either
            # fails, and returns the settings shown so they're remembered
            # for next time, same convenience every other dispatch branch
            # provides.
            settings = ipc.show_dialog(selected_spectra, current_settings=last_settings)
            if settings is not None:
                self.current_parameters[operation] = settings.copy()
                self.last_op_settings[operation] = settings.copy()
                self.last_selection_hash = current_selection_hash

        elif operation == "Reference Matching":
            selected_spectra = self._get_current_state_for_selected_spectra()
            if not selected_spectra:
                QMessageBox.warning(self.controller.view, "No Spectra Selected",
                                    "Please select at least one spectrum.")
                return
            last_settings = {}
            if (operation in self.current_parameters and
                    self.last_selection_hash == current_selection_hash):
                last_settings = self.last_op_settings.get("Reference Matching", {}).copy()
            all_spectra = self._get_current_state_for_selected_spectra(
                use_all=True) if hasattr(self, '_get_all_spectra') else selected_spectra
            # Pass all currently loaded spectra so user can pick references internally
            all_spectra = list(self.controller.original_spectra) \
                if hasattr(self.controller, 'original_spectra') else selected_spectra
            dialog = ReferenceMatchingDialog(self.controller.view, selected_spectra,
                                             current_settings=last_settings,
                                             all_spectra=all_spectra,
                                             main_controller=self.controller)
            if dialog.exec_() == QDialog.Accepted:
                settings = dialog.get_settings()
                if settings:
                    self.current_parameters["Reference Matching"] = settings.copy()
                    self.last_op_settings["Reference Matching"]   = settings.copy()

        elif operation == "Cosmic ray removal":
            selected_spectra = self._get_current_state_for_selected_spectra()
            if not selected_spectra:
                QMessageBox.warning(self.controller.view, "No Spectra Selected",
                                    "Please select at least one spectrum for this operation.")
                return
            self._show_cosmic_ray_dialog(selected_spectra, current_selection_hash)
            return

        elif operation == "Resolution enhancement":
            selected_spectra = self._get_current_state_for_selected_spectra()

            current_settings = {}
            if operation in self.current_parameters and self.last_selection_hash == current_selection_hash:
                current_settings = self.current_parameters[operation]

            # Lazy-create the controller — mirrors the pattern used for
            # Cosmic Ray Removal. Previously this operation had no
            # controller at all: both this dialog's live preview and
            # commit_resolution_enhancement below independently created
            # their own ResolutionEnhancementManager() instance inline.
            if not hasattr(self.controller, 'resolution_enhancement_controller'):
                from src.controllers.data_analysis.resolution_enhancement_controller import (
                    ResolutionEnhancementController)
                self.controller.resolution_enhancement_controller = \
                    ResolutionEnhancementController(self.controller)
            rec = self.controller.resolution_enhancement_controller

            # Apply / Add as New are the dialog's own buttons now, handled
            # by ResolutionEnhancementController.commit_resolution_enhancement()
            # — there's nothing left to do with this dialog's result after
            # it closes, since committing already happened inside it, if at all.
            settings = rec.show_dialog(
                selected_spectra,
                current_settings=current_settings,
                commit_callback=rec.commit_resolution_enhancement,
            )
            if settings:
                self.current_parameters[operation] = settings
                self.last_selection_hash = current_selection_hash
            return
        elif operation == "Spike removal":
            selected_spectra = self._get_current_state_for_selected_spectra()
            current_selection_hash = self._get_selection_hash(selected_spectra)

            if not selected_spectra:
                QMessageBox.warning(self.controller.view, "No Spectra Selected",
                                    "Please select at least one spectrum.")
                return

            if not hasattr(self.controller, 'spike_removal_controller'):
                from src.controllers.data_analysis.spike_removal_controller import SpikeRemovalController
                self.controller.spike_removal_controller = SpikeRemovalController(self.controller)

            src = self.controller.spike_removal_controller

            # Reuse whatever was last shown for this exact selection, even
            # if it was never Applied — the dialog's closeEvent now always
            # emits its current marking (see SpikeRemovalInteractiveDialog).
            current_settings = {}
            if operation in self.current_parameters and self.last_selection_hash == current_selection_hash:
                current_settings = self.current_parameters[operation]

            try:
                dialog = src.show_interactive_dialog(
                    selected_spectra, current_settings,
                    commit_callback=src.commit_spike_removal,
                )

                def on_removal_applied(settings):
                    self.current_parameters["Spike removal"] = settings
                    self.last_selection_hash = current_selection_hash

                dialog.removal_applied.connect(on_removal_applied)
                # Apply / Add as New are the dialog's own buttons now,
                # handled by SpikeRemovalController.commit_spike_removal()
                # — there's nothing left to do with this dialog's result
                # after it closes, since committing already happened
                # inside it, if at all.
                dialog.exec_()

            except Exception as e:
                logger.error(f"ERROR: Failed to open spike removal dialog: {e}")
                logger.exception("Traceback:")
                QMessageBox.critical(
                    self.controller.view, "Dialog Error",
                    f"Failed to open spike removal dialog:\n{str(e)}"
                )
            return


        elif operation == "Peak Fitting":
            if len(selected_spectra) != 1:
                QMessageBox.warning(
                    self.controller.view, "Selection Error",
                    "Please select exactly one spectrum to perform peak fitting."
                )
                return
    
            # Only reuse the last fit's peaks/results if this dialog was
            # last shown for this exact spectrum — without this guard,
            # switching to a completely different, unrelated spectrum would
            # silently reopen Peak Fitting pre-loaded with whichever
            # spectrum was fitted previously, every single time. Same
            # current_parameters / last_selection_hash guard every other
            # operation in this dispatcher already uses.
            last_settings = {}
            if (operation in self.current_parameters and
                    self.last_selection_hash == current_selection_hash):
                last_settings = self.last_op_settings.get("Peak Fitting", {}).copy()

            if not hasattr(self.controller, 'peak_fitting_controller'):
                from src.controllers.data_analysis.peak_fitting_controller import (
                    PeakFittingController)
                self.controller.peak_fitting_controller = PeakFittingController(self.controller)
            pfc = self.controller.peak_fitting_controller

            # Strip a stale cached fit_results if an operation ran on this
            # same spectrum meanwhile, even though it's still the same
            # selection -- see PeakFittingController.filter_stale_settings's
            # own docstring for the bug this fixes (an old fit curve
            # silently redrawn over freshly, but differently, processed data).
            last_settings = pfc.filter_stale_settings(last_settings)

            dialog = pfc.show_dialog(selected_spectra[0], current_settings=last_settings)

            result = dialog.exec_()

            # Always read back and remember what's in the dialog on
            # close -- same "no OK/Cancel distinction" rule every other
            # persistent-Manager dialog in this app already follows
            # (BaselineCorrectionController.show_dialog's own "Always
            # store corrections on close", SpikeRemovalController, ...).
            # Real bug found in practice: this used to sit entirely
            # inside "if dialog.exec_() == QDialog.Accepted:", so closing
            # the dialog any other way (the window's own X button, or a
            # Cancel button that calls reject()) saved nothing at all --
            # reopening on the same spectrum showed a blank peak list,
            # even though every other dialog in this app remembers your
            # in-progress work regardless of how you closed it. OK vs.
            # Cancel/X should only decide whether the fit's OUTPUT
            # SPECTRA get created below, never whether the peaks/fit
            # picked so far are remembered for next time.
            results = dialog.get_results()

            if results and results.get('initial_peaks'):
                sanitized_results = self._sanitize_fit_results(results)

                if sanitized_results.get('fit_results'):
                    self.current_parameters[operation] = sanitized_results.copy()
                    self.last_op_settings["Peak Fitting"] = sanitized_results.copy()
                    self.last_selection_hash = current_selection_hash
                else:
                    self.current_parameters.pop(operation, None)
                    self.last_op_settings.pop("Peak Fitting", None)

                if result == QDialog.Accepted:
                    if sanitized_results.get('fit_results'):
                        # Actually execute the fit — save it to metadata and
                        # create any new spectra the output-option
                        # checkboxes (add_fit / add_residual / add_peaks)
                        # requested. Peak Fitting used to reach this via a
                        # separate "Run" click after configuring it, back
                        # when it lived in the main Spectra-processing
                        # combobox; now it's opened directly from the
                        # Analysis & Visualization menu
                        # (run_visualization_analysis ->
                        # show_parameters_dialog_for), which has no second
                        # action left to trigger handle_peak_fitting() —
                        # it was being saved into current_parameters and
                        # never actually run.
                        self.handle_peak_fitting()
                    else:
                        QMessageBox.information(
                            self.controller.view, "No Fit",
                            "No valid fit results were generated. Nothing to apply."
                        )
            else:
                self.current_parameters.pop(operation, None)
                self.last_op_settings.pop("Peak Fitting", None)

        elif operation == "Melting Curve Analysis":
            # Unlike Peak Fitting (exactly one source spectrum), a melting
            # curve is extracted from a whole SERIES of spectra (one per
            # temperature point) — so the minimum here is 2, not 1.
            if len(selected_spectra) < 2:
                QMessageBox.warning(
                    self.controller.view, "Selection Error",
                    "Please select at least two spectra (one per temperature point) "
                    "to build a melting curve."
                )
                return

            # Same reuse-only-for-the-same-selection guard as Peak Fitting —
            # switching to an unrelated set of spectra should not silently
            # reopen this dialog pre-loaded with a previous, unrelated run.
            last_settings = {}
            if (operation in self.current_parameters and
                    self.last_selection_hash == current_selection_hash):
                last_settings = self.last_op_settings.get("Melting Curve Analysis", {}).copy()

            if not hasattr(self.controller, 'melting_curve_controller'):
                from src.controllers.visualization_analysis.melting_curve_controller import (
                    MeltingCurveController)
                self.controller.melting_curve_controller = MeltingCurveController(self.controller)
            mcc = self.controller.melting_curve_controller

            dialog = mcc.show_dialog(selected_spectra, current_settings=last_settings)

            # Read back get_results() regardless of Accepted/Rejected --
            # it just reflects whatever is currently on screen (e.g. a
            # re-fit with a changed n_components), so a Cancel or the
            # window's own close button must still remember it for next
            # time, exactly like every other dialog in the app. Only the
            # actual commit (creating new spectra from the checked Output
            # Options, and recording history) stays gated on Accepted --
            # same split applied to Band Ratio earlier in this session.
            result = dialog.exec_()
            results = dialog.get_results()

            if results and results.get('curve'):
                self.current_parameters[operation] = results.copy()
                self.last_op_settings["Melting Curve Analysis"] = results.copy()
                self.last_selection_hash = current_selection_hash
            else:
                self.current_parameters.pop(operation, None)
                self.last_op_settings.pop("Melting Curve Analysis", None)

            if result == QDialog.Accepted and results and results.get('curve'):
                # Actually execute the analysis — save it to metadata and
                # create any new spectra the output-option checkboxes
                # requested. Same reasoning as Peak Fitting: this dialog
                # is opened directly from the Analysis & Visualization
                # menu/groupbox (run_visualization_analysis ->
                # show_parameters_dialog_for), which has no separate
                # "Run" step afterwards to trigger the commit.
                self.handle_melting_curve_analysis()

    def on_operation_changed(self, operation_name):
        """
        Handle changes to the selected operation in the combobox.
        Updates button text and visibility as needed.
        """
        self.controller.view.parameters_operations_pushButton.setText("Run")

    # commit_manual_baseline moved to BaselineCorrectionController
    # (src/controllers/data_analysis/baseline_correction_controller.py) as
    # part of giving every operation its own dedicated controller instead
    # of OperationsController holding all of them directly. See that file
    # for the (behaviorally unchanged) commit logic.


    # commit_automated_baseline moved to AutomatedBaselineController
    # (new file: src/controllers/data_analysis/automated_baseline_controller.py)
    # as part of giving every operation its own dedicated controller
    # instead of OperationsController holding all of them directly. See
    # that file for the (behaviorally unchanged) commit logic.


    # commit_snip_baseline moved to SNIPBaselineController
    # (new file: src/controllers/data_analysis/snip_baseline_controller.py)
    # as part of giving every operation its own dedicated controller
    # instead of OperationsController holding all of them directly. See
    # that file for the (behaviorally unchanged) commit logic. This was
    # the LAST of the 13 original commit_<x>() methods to be extracted.


    def handle_reference_matching(self):
        """Reference matching is fully handled in the dialog — no apply step needed."""
        pass

    def handle_band_ratio(self):
        """Handle the Band Ratio / Peak Area Calculator operation."""
        if "Band Ratio" not in self.current_parameters:
            return
        settings = self.current_parameters["Band Ratio"]
        selected_spectra = self._get_current_state_for_selected_spectra()
        if not selected_spectra:
            QMessageBox.warning(self.controller.view, "No Spectra Selected",
                                "Please select one or more spectra.")
            return
        try:
            import numpy as np
            if not hasattr(self.controller, 'band_ratio_controller'):
                self.controller.band_ratio_controller = BandRatioController(self.controller)
            results = self.controller.band_ratio_controller.compute_results(selected_spectra, settings)
            results_map = {r["label"]: r for r in results}
            for s in selected_spectra:
                if s["label"] in results_map:
                    r = results_map[s["label"]]
                    # Only the meaningful scalar/descriptive fields go into
                    # metadata — value_a/value_b/result, what was computed
                    # and how, and when. x_a/y_a_raw/y_a_masked/x_b/y_b_raw/
                    # y_b_masked are full preview arrays compute_results()
                    # builds for the dialog's own plot overlay; they were
                    # never meant to be saved here (the screenshot that
                    # prompted this fix showed exactly that — a Show
                    # Metadata dump full of raw intensity arrays), and they
                    # don't belong in metadata any more than a baseline
                    # correction's full y_scale would.
                    s.setdefault("metadata", {})["band_ratio"] = {
                        'value_a':   r['value_a'],
                        'value_b':   r['value_b'],
                        'result':    r['result'],
                        'operation': settings.get('operation'),
                        'band_a':    settings.get('band_a'),
                        'band_b':    settings.get('band_b'),
                        'timestamp': datetime.now().isoformat(),
                    }
            # NOTE: deliberately not registered in Operations History.
            # Band Ratio computes a derived characteristic from existing
            # spectra — it never adds, removes, or transforms spectral
            # data — so there's nothing for the history chain to "undo" by
            # jumping to a previous step. The result is still saved into
            # each spectrum's own metadata (and synced to the live list
            # below) for reference; it's just not a tracked operation.
            # Same reasoning applies to every other Analysis &
            # Visualization tool that doesn't modify the spectra list
            # (Reference Matching, SVD/PCA/NMF/Cluster Analysis) — Peak
            # Fitting and 2D Map's ROI export are the exceptions, and only
            # because they can genuinely add new spectra to the list.
            self.update_original_spectra_with_processed(selected_spectra)
            n = len(results)
            ratios = [r["result"] for r in results if r["result"] is not None]
            msg = f"Band Ratio calculated for {n} spectra."
            if ratios:
                arr = np.array(ratios)
                msg += (f"\nRatio A/B \u2014 mean: {np.mean(arr):.4g}, "
                        f"std: {np.std(arr, ddof=1 if len(arr)>1 else 0):.4g}, "
                        f"min: {np.min(arr):.4g}, max: {np.max(arr):.4g}")
            QMessageBox.information(self.controller.view, "Band Ratio Complete", msg)
        except Exception as e:
            QMessageBox.critical(self.controller.view, "Operation Error",
                                 f"Error computing band ratio: {str(e)}")

    # handle_peak_fitting's real logic moved to PeakFittingController
    # (src/controllers/data_analysis/peak_fitting_controller.py) as part
    # of giving every operation its own dedicated controller instead of
    # OperationsController holding all of them directly. Also removed a
    # long-dead, fully commented-out earlier version of this same method
    # that had been sitting here unused. This thin wrapper stays so the
    # operation-name dispatch dict above, and any other direct
    # self.handle_peak_fitting() call, keep working unchanged.
    def handle_peak_fitting(self):
        if not hasattr(self.controller, 'peak_fitting_controller'):
            from src.controllers.data_analysis.peak_fitting_controller import PeakFittingController
            self.controller.peak_fitting_controller = PeakFittingController(self.controller)
        self.controller.peak_fitting_controller.handle_peak_fitting()

    # handle_melting_curve_analysis's real logic lives in
    # MeltingCurveController (src/controllers/visualization_analysis/
    # melting_curve_controller.py) — this is just the same thin delegator
    # shape as handle_peak_fitting() above, kept here so the
    # "Melting Curve Analysis": self.handle_melting_curve_analysis entry
    # in self.operations, and the same call from show_parameters_dialog's
    # own dispatch block, keep working unchanged.
    def handle_melting_curve_analysis(self):
        if not hasattr(self.controller, 'melting_curve_controller'):
            from src.controllers.visualization_analysis.melting_curve_controller import (
                MeltingCurveController)
            self.controller.melting_curve_controller = MeltingCurveController(self.controller)
        self.controller.melting_curve_controller.handle_melting_curve_analysis()


    # Updated method for OperationsController
    
    def _get_current_state_for_selected_spectra(self):
        """
        Get the current state of only the selected spectra from the operations manager.
        Uses spectrum unique IDs (via spectrum_key(), see
        src.modules.utils.spectrum_identity) to match spectra even after renaming.

        Returns:
            List containing only the selected spectra in their current state
        """
        # Get the full current state from operations manager
        all_current_spectra = self.operations_manager.get_current_spectra()

        # Also include any spectra in controller.original_spectra that are not
        # in the chain snapshot — this covers "add as new" spectra from earlier
        # sessions that may not appear in the active chain record.
        chain_ids = {spectrum_key(s) for s in all_current_spectra}
        for s in self.controller.original_spectra:
            if spectrum_key(s) not in chain_ids:
                all_current_spectra.append(s)
                chain_ids.add(spectrum_key(s))

        # Get currently selected spectra's identity directly from each
        # item's Qt.UserRole data (the unique_id stashed there when the
        # row was created — see main_controller.py and
        # _rebuild_spectra_list_with_selection above), rather than
        # matching displayed text against spectrum['label']. This used
        # to be a two-step "match by label first (faster), unique_id
        # only as a fallback" dance despite this method's own docstring
        # already claiming to match by identity — the label check was
        # actually primary. Identity is now the only check, and it's
        # simpler than the old two-step version, not just more correct.
        selected_items = self.controller.spectra_list_widget.selectedItems()
        selected_ids = {item.data(Qt.UserRole) for item in selected_items}

        # Every "Add as New" / "Copy spectra" path assigns a fresh
        # unique_id to the new copy (see commit_*'s Add as New blocks),
        # so a shared unique_id here genuinely means "the same spectrum,
        # possibly renamed," never "a copy derived from it."
        selected_current_spectra = [
            spectrum for spectrum in all_current_spectra
            if spectrum_key(spectrum) in selected_ids
        ]

        # If we found no matching spectra but have selections, log debug info
        if not selected_current_spectra and selected_ids:
            logger.error(f"DEBUG: Failed to find selected spectra. Selected ids: {selected_ids}")
            logger.debug(f"DEBUG: Operations manager has {len(all_current_spectra)} spectra")

        # The filtering above walks all_current_spectra, whose order is
        # whatever order spectra were first inserted into the operations
        # chain (essentially import order) — that has no relationship to
        # self.controller.original_spectra's order, which the user
        # actually sees in the main spectra list and which changes
        # whenever the "reverse sorting" checkbox is toggled. Re-sort here
        # so any dialog built from this result shows spectra in the same
        # order the user sees in the main list, rather than a seemingly
        # arbitrary one.
        position_by_key = {}
        for idx, s in enumerate(self.controller.original_spectra):
            position_by_key.setdefault(spectrum_key(s), idx)

        def _display_order_key(spectrum):
            # Anything that genuinely isn't in original_spectra (shouldn't
            # normally happen) sorts after everything that is, rather than
            # raising or being dropped.
            return position_by_key.get(spectrum_key(spectrum), len(self.controller.original_spectra))

        selected_current_spectra.sort(key=_display_order_key)

        return selected_current_spectra
    
    
    def _sanitize_fit_results(self, results_dict, precision=6):
        """
        Converts numpy types in fit_results to plain Python floats
        for human-readable display in the history.
        """
        if 'fit_results' not in results_dict:
            return results_dict # No results to sanitize
            
        sanitized_results_dict = results_dict.copy()
        sanitized_fit_list = []
        
        for peak_fit in results_dict['fit_results']:
            sanitized_peak = peak_fit.copy()
            sanitized_params = {}
            
            for param, value in peak_fit.get('parameters', {}).items():
                # Convert any numpy float or python float to a rounded python float
                if isinstance(value, (np.float64, np.float32, float)):
                    sanitized_params[param] = round(float(value), precision)
                else:
                    sanitized_params[param] = value # Keep other types (e.g., strings)
                    
            sanitized_peak['parameters'] = sanitized_params
            sanitized_fit_list.append(sanitized_peak)
            
        sanitized_results_dict['fit_results'] = sanitized_fit_list
        return sanitized_results_dict    


    def _show_cosmic_ray_dialog(self, spectra, current_selection_hash):
        """Open cross-spectrum cosmic ray detection dialog."""
        from src.views.dialogs.data_analysis.cosmic_ray_dialog import CosmicRayDialog

        # Lazy-create the controller — mirrors the pattern used for every
        # other refined operation (see e.g. XAxisAlignmentController).
        # Previously this operation had no controller at all: both this
        # dialog and commit_cosmic_ray_removal below independently created
        # their own CosmicRayManager() inline.
        if not hasattr(self.controller, 'cosmic_ray_controller'):
            from src.controllers.data_analysis.cosmic_ray_controller import CosmicRayController
            self.controller.cosmic_ray_controller = CosmicRayController(self.controller)
        crc = self.controller.cosmic_ray_controller

        # Reuse whatever was last shown for this exact selection, even if
        # it was never Applied — mirrors Data range / Normalization's
        # current_parameters cache.
        current_settings = {}
        if ("Cosmic ray removal" in self.current_parameters and
                self.last_selection_hash == current_selection_hash):
            current_settings = self.current_parameters["Cosmic ray removal"]

        # Apply / Add as New are the dialog's own buttons now, handled by
        # CosmicRayController.commit_cosmic_ray_removal() — there's
        # nothing left to do with this dialog's result after it closes,
        # since committing already happened inside it, if at all.
        dialog = crc.show_interactive_dialog(
            spectra,
            current_settings=current_settings,
            commit_callback=crc.commit_cosmic_ray_removal,
        )
        dialog.exec_()
        settings = dialog.get_settings()
        if settings:
            self.current_parameters["Cosmic ray removal"] = settings
            self.last_selection_hash = current_selection_hash

    # commit_resolution_enhancement moved to ResolutionEnhancementController
    # (src/controllers/data_analysis/resolution_enhancement_controller.py) as
    # part of giving every operation its own dedicated controller instead
    # of OperationsController holding all of them directly. See that file
    # for the (behaviorally unchanged) commit logic.


    # commit_cosmic_ray_removal moved to CosmicRayController
    # (src/controllers/data_analysis/cosmic_ray_controller.py) as part
    # of giving every operation its own dedicated controller instead of
    # OperationsController holding all of them directly. See that file
    # for the (behaviorally unchanged) commit logic.


    # commit_spike_removal moved to SpikeRemovalController
    # (src/controllers/data_analysis/spike_removal_controller.py) as part
    # of giving every operation its own dedicated controller instead of
    # OperationsController holding all of them directly. See that file
    # for the (behaviorally unchanged) commit logic.


    # commit_data_range moved to SpectralRangeController
    # (src/controllers/data_analysis/spectral_range_controller.py) as part
    # of giving every operation its own dedicated controller instead of
    # OperationsController holding all of them directly. See that file
    # for the (behaviorally unchanged) commit logic.


    # commit_normalization moved to NormalizationController
    # (src/controllers/data_analysis/normalization_controller.py) as part
    # of giving every operation its own dedicated controller instead of
    # OperationsController holding all of them directly. See that file
    # for the (behaviorally unchanged) commit logic.


    # commit_sg_smoothing moved to SavitzkyGolayController
    # (src/controllers/data_analysis/savitzky_golay_controller.py) as part
    # of giving every operation its own dedicated controller instead of
    # OperationsController holding all of them directly. See that file
    # for the (behaviorally unchanged) commit logic.


    # commit_fft_denoising moved to FFTDenoisingController
    # (src/controllers/data_analysis/fft_denoising_controller.py) as part
    # of giving every operation its own dedicated controller instead of
    # OperationsController holding all of them directly. See that file
    # for the (behaviorally unchanged) commit logic.


    # commit_xaxis_alignment moved to XAxisAlignmentController
    # (src/controllers/data_analysis/xaxis_alignment_controller.py) as part
    # of giving every operation its own dedicated controller instead of
    # OperationsController holding all of them directly. See that file
    # for the (behaviorally unchanged) commit logic.


    # commit_interactive_subtraction moved to InteractiveSubtractionController
    # (src/controllers/data_analysis/interactive_subtraction_controller.py) as
    # part of giving every operation its own dedicated controller instead
    # of OperationsController holding all of them directly. See that file
    # for the (behaviorally unchanged) commit logic.


    def update_original_spectra_with_processed(self, processed_spectra):
        """Update original_spectra with processed spectra to maintain UI consistency.

        All numpy arrays are copied to ensure original_spectra never shares
        mutable data with the operations chain or with other spectra.
        """
        import numpy as np
        for spectrum in processed_spectra:
            label = spectrum['label']
            for i, orig_spectrum in enumerate(self.controller.original_spectra):
                if orig_spectrum['label'] == label:
                    for key, value in spectrum.items():
                        if key == 'label':
                            continue
                        if isinstance(value, np.ndarray):
                            self.controller.original_spectra[i][key] = value.copy()
                        elif isinstance(value, dict):
                            inner = {}
                            for k, v in value.items():
                                inner[k] = v.copy() if isinstance(v, np.ndarray) else v
                            self.controller.original_spectra[i][key] = inner
                        else:
                            self.controller.original_spectra[i][key] = value
                    break
                    
    def _update_spectrum_list_widget(self):
        """Update the spectrum list widget to show current labels."""
        current_selection = self.controller.spectrum_selector.selected_indices
        
        # Block signals during update
        self.controller.spectra_list_widget.blockSignals(True)
        try:
            # Update list widget with current labels
            for i, spectrum in enumerate(self.controller.original_spectra):
                item = self.controller.spectra_list_widget.item(i)
                if item and item.text() != spectrum['label']:
                    item.setText(spectrum['label'])
        finally:
            self.controller.spectra_list_widget.blockSignals(False)
        
        # Restore selection
        self.controller.spectrum_selector.is_handling_selection = True
        try:
            for i in range(self.controller.spectra_list_widget.count()):
                self.controller.spectra_list_widget.item(i).setSelected(i in current_selection)
        finally:
            self.controller.spectrum_selector.is_handling_selection = False
        
        # Update selection count label
        self.controller.spectrum_selector.update_spectra_count_label()
        
    def show_operations_summary(self):
        """Show the operations summary dialog."""
        dialog = OperationsSummaryDialog(
            self.controller.view,
            self.operations_manager  # Pass the new operations manager
        )
        
        # Connect signals
        dialog.operation_selected.connect(self.jump_to_operation_state)
        
        dialog.exec_()

    def jump_to_operation_state(self, index):
        """
        Jump to the state after the specified operation.
        For the incremental approach, this rebuilds the state by applying
        operations in sequence up to the specified point.
        
        Args:
            index: Index of operation to jump to (-1 for original state)
        """
        # Original State has no operation record of its own to carry a
        # fixed "affected_labels" list. Its equivalent, maintained by
        # IncrementalOperationsManager.apply_operation(), is whatever was
        # selected the last time an operation was committed while Original
        # State was still the active state — not whatever happens to be
        # selected right now, which could belong to a completely unrelated
        # later step.
        original_state_labels = set(
            getattr(self.operations_manager, 'original_state_selected_labels', [])
        )

        # Show feedback to user
        if index < 0:
            status_msg = "Restoring to original state..."
        else:
            operation = self.operations_manager.get_operation_at_index(index)
            if operation:
                op_type = operation.get('type', 'Unknown')
                status_msg = f"Jumping to {op_type} operation (index {index})..."
            else:
                status_msg = f"Jumping to operation index {index}..."
                
        if hasattr(self.controller.view, 'statusBar'):
            self.controller.view.statusBar().showMessage(status_msg, 3000)
        
        # Set the active operation in the operations manager
        spectra = self.operations_manager.set_active_operation(index)
        
        if not spectra:
            logger.warning("Warning: No spectra returned from operations manager")
            if hasattr(self.controller.view, 'statusBar'):
                self.controller.view.statusBar().showMessage("Failed to restore state - no spectra available", 3000)
            return
        
        logger.debug(f"DEBUG: Got {len(spectra)} spectra from operations manager")
        
        # Get affected labels to select in the UI
        affected_labels = []
        if index >= 0:
            operation = self.operations_manager.get_operation_at_index(index)
            if operation and 'affected_labels' in operation:
                affected_labels = operation.get('affected_labels', [])
        
        # Always completely rebuild the original_spectra and UI for consistency
        self.controller.original_spectra = spectra.copy()
        
        if hasattr(self.controller, 'order_spectra'):
            logger.debug("DEBUG: Applying current sorting to spectra list")
            self.controller.original_spectra = self.controller.order_spectra(self.controller.original_spectra)
        
        # Rebuild the spectra_list_widget
        self.controller.spectra_list_widget.blockSignals(True)
        try:
            self.controller.spectra_list_widget.clear()
            for spectrum in self.controller.original_spectra:
                item = QListWidgetItem(spectrum['label'])
                item.setFlags(item.flags() | Qt.ItemIsSelectable)
                # Every row created for this widget must carry the
                # spectrum's permanent identity as Qt.UserRole — every
                # other rebuild site (main_controller.py,
                # _rebuild_spectra_list_with_selection) does this; jumping
                # to a history step was the one rebuild path that missed
                # it, which would silently break identity-based selection
                # matching (spectrum_key/spectrum_id — see
                # developer_guide_help.py's "Golden Rule: Spectrum
                # Identity") for every row until the next full rebuild.
                item.setData(Qt.UserRole, spectrum_id(spectrum))
                self.controller.spectra_list_widget.addItem(item)
        finally:
            self.controller.spectra_list_widget.blockSignals(False)
            
        # Update maximum values for spinboxes
        self.controller.view.number_of_rows_spinBox.setMaximum(len(self.controller.original_spectra))
        self.controller.view.number_of_columns_spinBox.setMaximum(len(self.controller.original_spectra))
        
        # Select affected spectra in the list widget
        self.controller.spectrum_selector.is_batch_updating = True
        self.controller.spectra_list_widget.blockSignals(True)
        try:
            self.controller.spectra_list_widget.clearSelection()
    
            # --- START of MODIFICATION ---
            
            operation_details = self.operations_manager.get_operation_at_index(index)
            op_type = (operation_details or {}).get('type', '')
            
            # Special selection logic for Combine Spectra (Spectral
            # Arithmetic) and Spectral Calculator — for these, we want to
            # select the newly CREATED result spectrum/spectra, not
            # whatever's in affected_labels (which is the SOURCE spectra
            # for both of these — see commit_spectral_arithmetic /
            # commit_spectral_calculator's apply_operation() calls, both
            # pass spectra_to_process as the third arg). Was previously
            # exact-match ('type') == 'Combine Spectra', so it never
            # matched the '(add as new)' suffix — same dispatch bug found
            # and fixed throughout operations_summary_dialog.py this
            # audit, just in a second location. Even with that fixed to
            # .startswith(), reading operation_details['parameters']
            # ['new_spectrum_name'] would still KeyError in Add as New
            # mode, since that record's 'parameters' is register_copy_
            # operation()'s generic dict (copied_count/source_labels/
            # copy_labels), which has no 'new_spectrum_name' key at all —
            # see _resolve_created_result_labels for the fix covering
            # both issues, plus Spectral Calculator, which this block
            # never handled in any mode before now.
            if operation_details and (op_type.startswith('Combine Spectra')
                                       or op_type.startswith('Spectral Calculator')):
                for label in self._resolve_created_result_labels(operation_details):
                    items = self.controller.spectra_list_widget.findItems(label, Qt.MatchExactly)
                    if items:
                        items[0].setSelected(True)
            
            # Original logic for all other operations
            elif index >= 0 and affected_labels:
                for i in range(self.controller.spectra_list_widget.count()):
                    item = self.controller.spectra_list_widget.item(i)
                    if item.text() in affected_labels:
                        item.setSelected(True)

            # Original State has no operation-specific "affected" subset of
            # its own — restore whatever was selected the last time an
            # operation was committed while it was still active (matching
            # by label), rather than selecting everything or leaving the
            # selection empty.
            elif index < 0:
                for i in range(self.controller.spectra_list_widget.count()):
                    item = self.controller.spectra_list_widget.item(i)
                    if item.text() in original_state_labels:
                        item.setSelected(True)
    
            # --- END of MODIFICATION ---
            
            # Update selected_indices in the spectrum selector
            self.controller.spectrum_selector.selected_indices = {
                i for i in range(self.controller.spectra_list_widget.count())
                if self.controller.spectra_list_widget.item(i).isSelected()
            }
            
            # Update selected_spectra
            self.controller.selected_spectra = [
                self.controller.original_spectra[i] for i in self.controller.spectrum_selector.selected_indices
            ]
            
            # Draw the selected spectra
            if self.controller.selected_spectra:
                # Respect Interactive Update instead of overriding it —
                # see _redraw_after_operation()'s docstring for why the
                # previous "force it back to checked" behavior was itself
                # a bug, not a feature.
                self._redraw_after_operation(context='jumping to a history step')
            else:
                self.controller.clear_graphics_view()
        finally:
            self.controller.spectra_list_widget.blockSignals(False)
            self.controller.spectrum_selector.is_batch_updating = False
            
        # Update the count label
        self.controller.spectrum_selector.update_spectra_count_label()
        
        # If we're going to the original state, reset all controllers
        if index < 0:
            # Reset spectral range controller
            sc = self.controller.spectral_range_controller
            sc.current_ranges = []
            sc.is_exclude_mode = True
            sc.x_step = 1.0
            sc.x_min = None
            sc.x_max = None
            sc.apply_linearization = False
            
            if hasattr(sc, 'manager'):
                sc.manager.spectrum_ranges = {}
                sc.manager.spectrum_exclude_modes = {}
                sc.manager.spectrum_x_steps = {}
                sc.manager.spectrum_x_mins = {}
                sc.manager.spectrum_x_maxs = {}
                sc.manager.current_ranges = []
                sc.manager.is_exclude_mode = True
                sc.manager.x_step = 1.0
                sc.manager.x_min = None
                sc.manager.x_max = None
                sc.manager.apply_linearization = False
            
            nc = getattr(self.controller, 'normalization_controller', None)
            if nc and hasattr(nc, 'manager'):
                nc.manager.normalization_mode = "max_peak"
                nc.manager.x_ranges = []
                nc.manager.is_exclude_mode = False
            
            self.current_parameters = {}
        else:
            # We're jumping to a specific operation
            operation = self.operations_manager.get_operation_at_index(index)
            if operation:
                op_type = operation['type']
                params = operation['parameters']
                
                if op_type != 'removal':
                    self.current_parameters[op_type] = params
                
                if op_type == "Data range":
                    sc = self.controller.spectral_range_controller
                    sc.current_ranges = params.get('ranges', [])
                    sc.is_exclude_mode = params.get('is_exclude_mode', True)
                    sc.x_step = params.get('x_step', 1.0)
                    sc.x_min = params.get('x_min')
                    sc.x_max = params.get('x_max')
                    sc.apply_linearization = params.get('apply_linearization', False)
                    
                    if hasattr(sc, 'manager'):
                        sc.manager.current_ranges = params.get('ranges', [])
                        sc.manager.is_exclude_mode = params.get('is_exclude_mode', True)
                        sc.manager.x_step = params.get('x_step', 1.0)
                        sc.manager.x_min = params.get('x_min')
                        sc.manager.x_max = params.get('x_max')
                        sc.manager.apply_linearization = params.get('apply_linearization', False)
                    
                elif op_type == "Normalization":
                    nc = getattr(self.controller, 'normalization_controller', None)
                    if nc and hasattr(nc, 'manager'):
                        nc.manager.update_settings(params)
        
        if hasattr(self.controller.spectrum_selector, 'update_spectra_count_label'):
            self.controller.spectrum_selector.update_spectra_count_label()
            
        if hasattr(self.controller.view, 'statusBar'):
            if index < 0:
                self.controller.view.statusBar().showMessage("Restored to original state", 3000)
            else:
                operation = self.operations_manager.get_operation_at_index(index)
                if operation:
                    op_type = operation.get('type', 'Unknown')
                    self.controller.view.statusBar().showMessage(f"Jumped to {op_type} operation (index {index})", 3000)
        
        if index < 0:
            logger.info("Restored to original state (before any operations)")
        else:
            operation = self.operations_manager.get_operation_at_index(index)
            if operation:
                logger.debug(f"Jumped to operation: {operation['type']} (operations after this point will be discarded if a new operation is applied)")


    def register_removal_operation(self, removed_spectra):
        """
        Register the removal of spectra as an operation in the operations history.
        
        Args:
            removed_spectra: List of spectra dictionaries that are being removed
        """
        if not removed_spectra:
            return
        
        # If we jumped back to the original state (-1), we should clear all operations
        if self.operations_manager.active_operation_index == -1 and len(self.operations_manager.operations_chain) > 0:
            logger.debug("DEBUG: Jumping from original state - clearing all operations")
            self.operations_manager.operations_chain = []
        # If we're not at the end of the chain, remove all operations after active_operation_index
        elif (self.operations_manager.active_operation_index >= 0 and 
              self.operations_manager.active_operation_index < len(self.operations_manager.operations_chain) - 1):
            logger.debug(f"DEBUG: Removing operations after index {self.operations_manager.active_operation_index}")
            self.operations_manager.operations_chain = self.operations_manager.operations_chain[:self.operations_manager.active_operation_index + 1]
        
        # Get the current state - includes ALL spectra
        current_state = self.operations_manager.get_current_spectra()
        
        # Extract the labels of removed spectra
        removed_labels = [spectrum['label'] for spectrum in removed_spectra]
        
        # Create a complete spectra list that combines:
        # 1. The current state without the removed spectra
        complete_output_spectra = []
        for spectrum in current_state:
            if spectrum['label'] not in removed_labels:
                complete_output_spectra.append(spectrum)
        
        # Create operation record
        timestamp = datetime.now().isoformat()
        operation_record = {
            'type': "removal",
            'timestamp': timestamp,
            'parameters': {"removed_spectra_count": len(removed_spectra)},
            'affected_labels': removed_labels,  # Store which spectra were removed
            'output_spectra': complete_output_spectra,  # Store complete state after removal
            'removed_spectra': removed_spectra  # Store the actual removed spectra
        }
        
        # Add to operations chain
        self.operations_manager.operations_chain.append(operation_record)
        self.operations_manager.active_operation_index = len(self.operations_manager.operations_chain) - 1
        
        logger.debug(f"DEBUG: Registered removal of {len(removed_spectra)} spectra as operation")

    def _resolve_created_result_labels(self, operation_details):
        """Resolve the label(s) of the spectrum/spectra actually CREATED
        by a Combine Spectra or Spectral Calculator
        operation — used to select the right thing after jumping to that
        step in Operations History (see the call site above).

        Three cases, in order of how directly the answer is available:
        1. Add as New mode (either operation): operation_details
           ['parameters'] is register_copy_operation()'s generic dict —
           'copy_labels' IS exactly the created spectra's current labels,
           no ambiguity.
        2. Combine Spectra, Apply/Replace mode: operation_details
           ['parameters'] is the operation's own original settings dict,
           which has 'new_spectrum_name' (a single, fixed name).
        3. Spectral Calculator, Apply/Replace mode: neither of the above
           — there's no single fixed name recorded anywhere in
           parameters (multiple outputs are possible, and their final
           names after collision-avoidance are only decided inside
           commit_spectral_calculator, never written back to params).
           Falls back to matching each output spectrum's own
           correction_history against this operation's actual source
           set — the same detection principle
           OperationParametersDialog._get_created_results_data (in
           operations_summary_dialog.py) uses for the Parameters
           display, just without the Qt table-building around it.
        """
        params = operation_details.get('parameters') or {}
        if 'copy_labels' in params:
            return list(params['copy_labels'])
        if 'new_spectrum_name' in params:
            return [params['new_spectrum_name']]

        source_labels = set(operation_details.get('affected_labels') or [])
        op_type = operation_details.get('type', '')
        tag = 'Spectral Calculator' if op_type.startswith('Spectral Calculator') else 'Combine Spectra'
        results = []
        for s in operation_details.get('output_spectra') or []:
            history = ((s.get('metadata') or {}).get('correction_history') or [])
            for entry in reversed(history):
                if entry.get('operation') == tag and set(entry.get('source_spectra', [])) == source_labels:
                    results.append(s['label'])
                    break
        return results

    def register_copy_operation(self, copied_spectra, new_spectra,
                                operation_name=None, pre_state=None):
        """Register copying of spectra as an operation in the operations history.

        Args:
            copied_spectra:  List of original spectrum dicts that were copied
            new_spectra:     List of new spectrum dicts (the copies)
            operation_name:  Display name for the history entry.  When supplied
                             the record type is '<operation_name> (add as new)';
                             when None it falls back to 'copy' (plain duplication).
            pre_state:       Optional — the current spectra state, if the
                             caller already has it in hand (every commit_<x>()
                             method does: it computes current_state before
                             calling apply_operation(), and by the time this
                             runs — right after that same apply_operation()
                             call, in "Add as New" mode — that state hasn't
                             changed). get_current_spectra() does a full
                             manual deep-copy of every spectrum (all arrays
                             + metadata) on every call; without this, that
                             entire pass was being paid for AGAIN here, for
                             data the caller had already computed and
                             already safely copied moments earlier. Falls
                             back to calling get_current_spectra() (the
                             original behavior) when not provided, for
                             callers that don't have it precomputed (e.g.
                             NMFController/MCRALSController's export
                             methods).
        """
        if not new_spectra:
            return

        # Capture pre-addition state FIRST so that navigating back to Original
        # (index=-1) or any earlier step correctly excludes the copies.
        # operations_manager.original_spectra must NOT be modified — it is the
        # permanent baseline that "Original state" always returns.
        pre_state = list(pre_state) if pre_state is not None else list(self.operations_manager.get_current_spectra())

        # Truncate chain if not at end
        if self.operations_manager.active_operation_index == -1 and len(self.operations_manager.operations_chain) > 0:
            self.operations_manager.operations_chain = []
        elif (self.operations_manager.active_operation_index >= 0 and
              self.operations_manager.active_operation_index < len(self.operations_manager.operations_chain) - 1):
            self.operations_manager.operations_chain = \
                self.operations_manager.operations_chain[:self.operations_manager.active_operation_index + 1]

        # Build post-state explicitly from pre_state + copies
        #
        # Was copy.deepcopy(s) for each spectrum — confirmed by direct
        # profiling to be 10-18x slower than the targeted copy below, once
        # a spectrum's metadata['correction_history'] has any entries
        # (i.e. after ANY prior operation — the common case, not an edge
        # case). deepcopy recursively walks and reconstructs every nested
        # object via Python's generic copy protocol, including numpy
        # arrays (which it doesn't special-case the way ndarray.copy()
        # does) and the entire correction_history list, which only grows
        # as more operations are applied to the same spectrum over a
        # session. Nothing here needs a FULL recursive copy — x_scale/
        # y_scale need independent arrays (mutating one operation's
        # output must not affect another's), and metadata needs its own
        # dict so a later append_correction_history() on one doesn't
        # silently mutate the other's — but deeper nested values (each
        # individual correction_history entry's own dict, its own point
        # lists, etc.) are never mutated in place anywhere in this
        # codebase; they're always replaced wholesale (see
        # correction_history.py's append_correction_history, which
        # builds a new list rather than mutating entries in it), so
        # sharing THOSE references is safe.
        post_state = pre_state + [
            {
                **{k: (v.copy() if hasattr(v, 'copy') else v) for k, v in s.items() if k != 'metadata'},
                'metadata': {
                    **dict(s.get('metadata') or {}),
                    # dict(...) above is still only a SHALLOW copy — a
                    # nested mutable value like correction_history would
                    # otherwise stay the SAME list object shared across
                    # every copy in new_spectra. Nothing in this codebase
                    # currently mutates that list in place (see
                    # correction_history.py's append_correction_history,
                    # which always builds and reassigns a fresh list) —
                    # but relying on that holding forever, rather than
                    # actually guaranteeing independence here, is exactly
                    # the kind of fragile assumption this file exists to
                    # remove elsewhere.
                    **({'correction_history': list((s.get('metadata') or {}).get('correction_history', []))}
                       if 'correction_history' in (s.get('metadata') or {}) else {}),
                },
            }
            for s in new_spectra
        ]

        record_type = (f"{operation_name} (add as new)"
                       if operation_name else "copy")

        timestamp = datetime.now().isoformat()
        operation_record = {
            'type': record_type,
            'timestamp': timestamp,
            'parameters': {
                'copied_count': len(copied_spectra),
                'source_labels': [s['label'] for s in copied_spectra],
                'copy_labels': [s['label'] for s in new_spectra],
            },
            'affected_labels': [s['label'] for s in copied_spectra],
            'output_spectra': post_state,
        }

        self.operations_manager.operations_chain.append(operation_record)
        self.operations_manager.active_operation_index = len(self.operations_manager.operations_chain) - 1

        logger.debug(f"DEBUG: Registered '{record_type}' of {len(copied_spectra)} spectra as operation")

    def handle_added_spectra(self, added_spectra):
        
        # Update the operations manager
        if hasattr(self, 'operations_manager'):
            self.operations_manager.add_spectra_to_original(added_spectra)
            
            # Update our original_spectra reference in the main controller
            # This is needed to ensure the UI reflects the newly added spectra
            if hasattr(self.controller, 'original_spectra'):
                for spectrum in added_spectra:
                    # Check if it's already in original_spectra
                    if not any(s['label'] == spectrum['label'] for s in self.controller.original_spectra):
                        # Create deep copy to avoid reference issues
                        spectrum_copy = {}
                        for key, value in spectrum.items():
                            if key in ['x_scale', 'y_scale']:
                                spectrum_copy[key] = value.copy() if hasattr(value, 'copy') else value
                            elif key == 'metadata':
                                spectrum_copy[key] = value.copy() if hasattr(value, 'copy') else value
                            else:
                                spectrum_copy[key] = value
                                
                        self.controller.original_spectra.append(spectrum_copy)
    
            # Redraw the plot with all spectra. Deliberately NOT touching
            # interactive_mode_checkbox here like the other unconditional
            # plot_spectra() call sites: newly imported spectra aren't
            # auto-selected, so with the checkbox off this redraw has
            # nothing new to show (selected_spectra is unaffected by an
            # import) — no visible inconsistency to fix.
            if hasattr(self.controller, 'plot_spectra'):
                self.controller.plot_spectra()