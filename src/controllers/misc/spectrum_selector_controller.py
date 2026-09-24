
# src/controllers/misc/spectrum_selector_controller.py

from PyQt5.QtCore import Qt, QObject, QEvent
from PyQt5.QtWidgets import QListWidgetItem, QListWidget, QDialog, QMessageBox, QAbstractItemView
from src.controllers.misc.rename_spectra_controller import RenameSpectraController
from src.views.dialogs.misc.spectra_selection_dialog import SpectraSelectionDialog
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key, spectrum_id
logger = get_logger(__name__)

class _ShiftClickFilter(QObject):
    """
    Event filter that gives the spectrum list Excel-style Shift+click behaviour.

    Without this, Qt's ExtendedSelection deselects everything outside the
    Shift+clicked range.  This filter intercepts Shift+left-button-press,
    extends the Qt selection from the last-clicked anchor to the target row,
    and keeps all previously selected items intact.
    """

    def __init__(self, selector):
        super().__init__(selector.controller.spectra_list_widget)
        self._sel = selector

    def eventFilter(self, obj, event):
        lw = self._sel.controller.spectra_list_widget
        if (event.type() == QEvent.MouseButtonPress
                and event.button() == Qt.LeftButton
                and event.modifiers() & Qt.ShiftModifier):
            target_item = lw.itemAt(event.pos())
            if target_item is None:
                return False
            target_row = lw.row(target_item)
            anchor     = self._sel._last_clicked_row
            if anchor < 0:
                anchor = 0

            lo, hi = min(anchor, target_row), max(anchor, target_row)

            # Extend selection: keep existing, add the range
            self._sel.is_handling_selection = True
            try:
                for row in range(lo, hi + 1):
                    lw.item(row).setSelected(True)
                    self._sel.selected_indices.add(row)
            finally:
                self._sel.is_handling_selection = False

            # Trigger the normal selection-changed logic once
            self._sel.on_item_selection_changed()
            return True   # event consumed — Qt must not process it further

        # Plain click (no Shift) — update anchor
        if (event.type() == QEvent.MouseButtonPress
                and event.button() == Qt.LeftButton
                and not (event.modifiers() & Qt.ShiftModifier)):
            target_item = lw.itemAt(event.pos())
            if target_item is not None:
                self._sel._last_clicked_row = lw.row(target_item)

        return False   # let Qt handle everything else normally


class SpectrumSelector:
    def __init__(self, main_controller, spectrum_selection_widget):
        """
        Initialize the SpectrumSelector with a reference to the main controller.
        
        Args:
            main_controller: Reference to MainController instance for accessing UI elements
            spectrum_selection_widget: Widget that contains the selection UI
        """
        self.controller = main_controller
        self.spectrum_selection_widget = spectrum_selection_widget
        self.is_batch_updating = False  # Tracks batch operations
        self.is_handling_selection = False  # Prevents recursive selection handling
        self.selected_indices = set()  # Store selected indices
        
        self._last_clicked_row = -1   # anchor for Shift+click range selection

        # ExtendedSelection: plain click = one item, Ctrl+click = toggle,
        # Shift+click = contiguous range from last anchor (Excel-style).
        self.controller.spectra_list_widget.setSelectionMode(
            QListWidget.ExtendedSelection
        )
        # Install event filter to implement Shift+click range extension
        # without deselecting the rest of the list.
        self.controller.spectra_list_widget.installEventFilter(
            _ShiftClickFilter(self)
        )
        self.update_item_style_for_selection()
        self.connect_signals()
        
    def connect_signals(self):
        """Connect UI signals related to spectrum selection and checkbox changes."""
        try:
            self.controller.spectra_list_widget.itemChanged.disconnect()
        except Exception:
            pass

        self.controller.spectra_list_widget.itemChanged.connect(self.on_spectrum_item_changed)
        self.controller.spectra_list_widget.itemSelectionChanged.connect(self.on_item_selection_changed)
        self.controller.interactive_mode_checkbox.stateChanged.connect(self.on_interactive_mode_changed)
        self.controller.refresh_plot_button.clicked.connect(self.update_plot)        
        
    def update_spectra_count_label(self):
        """Update the label showing selected/total spectra count."""
        total_items = self.controller.spectra_list_widget.count()
        selected_items = len(self.controller.spectra_list_widget.selectedItems())
        self.controller.num_label.setText(f"{selected_items}/{total_items}")
        
    def set_checkbox_states(self, interactive_update: bool, multiselection: bool):
        """
        Set the states of the Interactive Update and Multiselection checkboxes.
    
        Args:
            interactive_update (bool): Whether to check the Interactive Update checkbox.
            multiselection (bool): Whether to allow multiple selection.
        """
        self.controller.interactive_mode_checkbox.setChecked(interactive_update)

    def with_blocked_signals(self, widget, func):
        """
        Execute a function with signals temporarily blocked on a widget.
        
        Args:
            widget: Widget to block signals for
            func: Function to execute while signals are blocked
        """
        widget.blockSignals(True)
        try:
            func()
        finally:
            widget.blockSignals(False)

    def update_groupbox_states(self, enable, plot_type=None):
        """
        Enable or disable groupboxes based on the current state.
        
        Args:
            enable (bool): Whether to enable the groupboxes
            plot_type (str, optional): Current plot type
        """
        if plot_type == "Single spectrum":
            enable = True

        self.controller.view.groupBox_basic_plot_options.setEnabled(enable)
        self.controller.view.groupBox_link_axes.setEnabled(enable)

    def enforce_single_spectrum_mode(self):
        """
        Ensure the UI is in the correct state for 'Single spectrum' mode.
        """
        self.controller.interactive_mode_checkbox.setChecked(True)

    def on_spectrum_item_changed(self, item):
        """
        Handle spectrum list item changes.
        
        Args:
            item: The list widget item that changed
        """
        if self.is_batch_updating or self.is_handling_selection:
            return

        self.update_plot()
        self.update_spectra_count_label()
            
    def on_item_selection_changed(self):
        """Handle changes in item selection."""
        if self.is_handling_selection:
            return
            
        self.is_handling_selection = True
        try:
            plot_type = self.controller.view.comboBox_plot_type_choice.currentText()
            interactive_mode = self.controller.interactive_mode_checkbox.isChecked()
    
            # Get selected spectra by their PERMANENT identity
            # (metadata['unique_id'], stashed on each item as
            # Qt.UserRole data when the row was created — see
            # _key_for/spectrum_key), not by matching visible text
            # against spectrum['label']. Labels are display strings the
            # user can rename at any time; unique_id never changes — see
            # developer_guide_help.py's "Golden Rule: Spectrum Identity".
            selected_ids = {
                item.data(Qt.UserRole) for item in self.controller.spectra_list_widget.selectedItems()
            }

            # Update selected_spectra based on selected identities in the current order
            self.controller.selected_spectra = [
                spectrum for spectrum in self.controller.original_spectra
                if spectrum_key(spectrum) in selected_ids
            ]

            # Update selected indices based on identities
            self.selected_indices = {
                i for i, spectrum in enumerate(self.controller.original_spectra)
                if spectrum_key(spectrum) in selected_ids
            }
    
            if interactive_mode or plot_type == "Single spectrum":
                # Plot the currently selected spectra
                self.controller.plot_spectra()
                self.update_groupbox_states(True, plot_type)
            else:
                # In non-interactive modes, clear the view
                self.update_groupbox_states(False, plot_type)
                self.controller.clear_graphics_view()
        finally:
            self.is_handling_selection = False
            self.update_spectra_count_label()

    def on_interactive_mode_changed(self, state):
        """
        Handle changes to the interactive mode checkbox.
        
        Args:
            state: New checkbox state
        """
        interactive_mode = state == Qt.Checked
        
        self.is_handling_selection = True
        try:
            if interactive_mode:
                # Restore previous selection when switching to interactive mode
                self.controller.spectra_list_widget.clearSelection()
                for idx in self.selected_indices:
                    if idx < self.controller.spectra_list_widget.count():
                        self.controller.spectra_list_widget.item(idx).setSelected(True)
                
                # Update plot with restored selection
                self.controller.selected_spectra = [
                    self.controller.original_spectra[idx]
                    for idx in self.selected_indices
                ]
                self.controller.plot_spectra()
            else:
                # Clear plot but maintain selection
                self.controller.clear_graphics_view()

            # Update UI states
            self.update_groupbox_states(interactive_mode)
            self.controller.refresh_plot_button.setVisible(not interactive_mode)
        finally:
            self.is_handling_selection = False
            self.update_spectra_count_label()

    def update_plot(self):
        """Update the plot based on selected items."""
        if self.is_handling_selection:
            return

        selected_spectra = self.get_selected_spectra()
        self.controller.selected_spectra = selected_spectra

        if selected_spectra:
            self.controller.plot_spectra()
        else:
            self.controller.clear_graphics_view()

        self.update_spectra_count_label()

    def handle_selection_change(self, item):
        """
        Handle spectrum selection changes.
        In interactive mode, refresh selected spectra immediately.
        In non-interactive mode, clear the plot until Refresh Plot is clicked.
        
        Args:
            item: The list widget item that changed
        """
        if not self.is_batch_updating and not self.is_handling_selection:
            plot_type = self.controller.view.comboBox_plot_type_choice.currentText()

            if self.controller.interactive_mode_checkbox.isChecked():
                # Plot immediately in interactive mode
                self.plot_selected_spectra()
            else:
                # In non-interactive mode, clear the plot area and disable groupboxes
                self.controller.clear_graphics_view()
                self.update_groupbox_states(False, plot_type)  # Disable groupboxes when no interactive

    def plot_selected_spectra(self):
        """
        Plot the currently selected spectra.
        """
        if not self.is_batch_updating and not self.is_handling_selection:
            self.controller.selected_spectra = self.get_selected_spectra()
            plot_type = self.controller.view.comboBox_plot_type_choice.currentText()
    
            if self.controller.interactive_mode_checkbox.isChecked():
                self.controller.plot_spectra()
                self.update_groupbox_states(True, plot_type)
            else:
                if not self.controller.selected_spectra:
                    self.controller.clear_graphics_view()
                    self.update_groupbox_states(False, plot_type)
                else:
                    self.controller.plot_spectra()
                    self.update_groupbox_states(True, plot_type)    

    def get_selected_spectra(self):
        """
        Get the currently selected spectra in the exact order they appear in the original_spectra list.
        This maintains the order as shown in the UI, not the order of selection.
        
        Returns:
            list: List of selected spectrum dictionaries in UI display order
        """
        if not self.selected_indices:
            return []
        
        # Sort indices to maintain the order as they appear in the original_spectra list
        sorted_indices = sorted(self.selected_indices)
        
        logger.debug(f"DEBUG: get_selected_spectra called")
        logger.debug(f"DEBUG: selected_indices: {self.selected_indices}")
        logger.debug(f"DEBUG: sorted_indices: {sorted_indices}")
        logger.debug(f"DEBUG: original_spectra contains {len(self.controller.original_spectra)} spectra")
        
        # Get spectra in the correct order based on their position in original_spectra
        # Return shallow dict copies with numpy arrays independently copied so that
        # processing operations never accidentally mutate original_spectra through
        # a shared reference (the root cause of the "copy acts as alias" bug).
        selected_spectra = []
        for index in sorted_indices:
            if 0 <= index < len(self.controller.original_spectra):
                spectrum = self.controller.original_spectra[index]
                # Shallow dict copy + explicit array copies = fully independent spectrum
                sc = {}
                for key, val in spectrum.items():
                    if hasattr(val, 'copy'):   # numpy arrays
                        sc[key] = val.copy()
                    elif isinstance(val, dict):
                        sc[key] = val.copy()
                    else:
                        sc[key] = val
                selected_spectra.append(sc)
                logger.debug(f"DEBUG: Added spectrum at index {index}: {spectrum['label']}")
            else:
                logger.warning(f"DEBUG: Warning - index {index} is out of range")
        
        logger.debug(f"DEBUG: Returning {len(selected_spectra)} selected spectra in order:")
        for i, spectrum in enumerate(selected_spectra):
            logger.debug(f"DEBUG: {i+1}. {spectrum['label']}")
        
        return selected_spectra

    def update_spectrum_selection_widget(self, spectra_state):
        """
        Update the spectrum selection widget's order and selected state.

        Args:
            spectra_state (dict): Dictionary mapping spectrum identity keys
                (spectrum_key(spectrum) — metadata['unique_id'], see
                src.modules.utils.spectrum_identity) to their selection
                state. Keyed by identity rather than label so a spectrum
                that was renamed since spectra_state was captured is
                still matched correctly.
        """
        self.is_handling_selection = True
        self.controller.spectra_list_widget.blockSignals(True)

        try:
            self.controller.spectra_list_widget.clear()

            # Add items with their selection states
            for spectrum in self.controller.original_spectra:
                item = QListWidgetItem(spectrum['label'])
                item.setFlags(item.flags() | Qt.ItemIsSelectable)
                item.setData(Qt.UserRole, spectrum_id(spectrum))
                item.setSelected(spectra_state.get(spectrum_key(spectrum), False))
                self.controller.spectra_list_widget.addItem(item)
            
            # Update selected indices based on the new order
            self.selected_indices = {
                i for i in range(self.controller.spectra_list_widget.count())
                if self.controller.spectra_list_widget.item(i).isSelected()
            }
            
            # Update plot state if in interactive mode
            if self.controller.interactive_mode_checkbox.isChecked() and self.selected_indices:
                self.controller.selected_spectra = [
                    self.controller.original_spectra[idx]
                    for idx in self.selected_indices
                ]
                self.controller.plot_spectra()
        finally:
            self.is_handling_selection = False
            self.controller.spectra_list_widget.blockSignals(False)
            self.update_spectra_count_label()

    def toggle_selection_widget(self):
        """Toggle the visibility of the spectrum selection widget."""
        is_visible = not self.controller.view.spectrum_selection_frame.isVisible()
        self.controller.view.spectrum_selection_frame.setVisible(is_visible)

    def select_all_items(self):
        """Select all items in the spectra list widget."""
        self.is_handling_selection = True
        try:
            # Select all items
            self.controller.spectra_list_widget.selectAll()
            
            # Update selected indices
            self.selected_indices = set(range(self.controller.spectra_list_widget.count()))
            
            # Update plot if in interactive mode
            if self.controller.interactive_mode_checkbox.isChecked():
                self.controller.selected_spectra = [
                    self.controller.original_spectra[idx]
                    for idx in self.selected_indices
                ]
                self.controller.plot_spectra()
            else:
                self.controller.clear_graphics_view()
                
            self.update_groupbox_states(self.controller.interactive_mode_checkbox.isChecked())
        finally:
            self.is_handling_selection = False
            self.update_spectra_count_label()
    
    def unselect_all_items(self):
        """Unselect all items in the spectra list widget."""
        self.is_handling_selection = True
        try:
            # Clear all selections
            self.controller.spectra_list_widget.clearSelection()
            
            # Clear selected indices
            self.selected_indices.clear()
            
            # Clear plot and update UI
            self.controller.clear_graphics_view()
            self.controller.selected_spectra = []
            self.update_groupbox_states(False)
        finally:
            self.is_handling_selection = False
            self.update_spectra_count_label()
            
    def show_spectra_selection_dialog(self):
        """
        Show dialog for selecting spectra by index range, text search, or
        common root name.
        """
        # Get the current list of spectra
        widget = self.controller.spectra_list_widget
        total_spectra = widget.count()

        if not total_spectra:
            return

        labels = [widget.item(i).text() for i in range(total_spectra)]

        # Create and show reusable spectra selection dialog
        dialog = SpectraSelectionDialog(
            parent=self.controller.view,
            total_spectra=total_spectra,
            title="Select Spectra",
            labels=labels,
        )
        
        if dialog.exec_() == QDialog.Accepted:
            params = dialog.get_selection_parameters()
            self.apply_spectra_selection(params)

    def apply_spectra_selection(self, params):
        """
        Apply the selection based on parameters from the dialog.
        
        Args:
            params (dict): Selection parameters with keys 'indices', 'action'
        """
        indices = params['indices']
        action = params['action']
        
        self.is_handling_selection = True
        try:
            # For "select" action, clear current selection
            if action == "select":
                self.controller.spectra_list_widget.clearSelection()
                self.selected_indices.clear()

            # Apply the selection changes
            for idx in indices:
                if idx < self.controller.spectra_list_widget.count():
                    item = self.controller.spectra_list_widget.item(idx)
                    
                    if action == "select" or action == "add":
                        item.setSelected(True)
                        self.selected_indices.add(idx)
                    elif action == "remove":
                        item.setSelected(False)
                        if idx in self.selected_indices:
                            self.selected_indices.remove(idx)
            
            # Update selected spectra
            if self.controller.interactive_mode_checkbox.isChecked():
                self.controller.selected_spectra = [
                    self.controller.original_spectra[idx]
                    for idx in self.selected_indices
                ]
                if self.selected_indices:
                    self.controller.plot_spectra()
                else:
                    self.controller.clear_graphics_view()
                    
            self.update_spectra_count_label()
        finally:
            self.is_handling_selection = False

    def show_selected_spectrum_metadata(self):
        """
        Display metadata for the currently selected spectrum(s).
        Now delegates to SpectrumMetadataController.
        """
        # Lazily initialize the controller if needed
        if not hasattr(self.controller, 'spectrum_metadata_controller'):
            from src.controllers.misc.spectrum_metadata_controller import SpectrumMetadataController
            self.controller.spectrum_metadata_controller = SpectrumMetadataController(self.controller)
        
        # Let the controller handle metadata display. Passes ROW INDICES,
        # not label text — two spectra sharing a label would otherwise be
        # silently conflated by SpectrumMetadataManager's old label-based
        # lookup (see that method's docstring for the confirmed bug this
        # avoids).
        selected_items = self.controller.spectra_list_widget.selectedItems()
        selected_indices = [self.controller.spectra_list_widget.row(item) for item in selected_items]
        
        self.controller.spectrum_metadata_controller.show_metadata(selected_indices)    

    def update_item_style_for_selection(self):
        """
        Update the item style when selection mode changes.
        """
        # Always set red color for the background when selected
        self.controller.spectra_list_widget.setStyleSheet("""
            QListWidget::item:selected {
                background-color: red;
                color: white;
            }
        """)

    def show_rename_dialog(self):
        """Show dialog for renaming spectra."""
        # Get controller instance or create one
        if not hasattr(self.controller, 'rename_spectra_controller'):
            self.controller.rename_spectra_controller = RenameSpectraController(self.controller)
            
        # Show the dialog through the controller
        self.controller.rename_spectra_controller.show_dialog()
    
    def rename_spectra(self, renamed_labels):
        """
        Rename spectra according to the mapping provided
        
        Args:
            renamed_labels (dict): Dictionary mapping original labels to new labels
        """
        # Remember which items were selected
        selected_indices = self.selected_indices.copy()

        # Update original_spectra metadata and labels, recording each
        # renamed spectrum's PERMANENT identity (unique_id) alongside its
        # new label. The widget update below matches by that identity —
        # the same id already stashed on each QListWidgetItem via
        # Qt.UserRole when the row was created — rather than by matching
        # old label text, so it can't be confused by two spectra
        # momentarily sharing display text.
        id_to_new_label = {}
        for spectrum in self.controller.original_spectra:
            if spectrum['label'] in renamed_labels:
                new_label = renamed_labels[spectrum['label']]
                id_to_new_label[spectrum_id(spectrum)] = new_label
                # Update the label
                spectrum['label'] = new_label
                # Update the metadata
                if 'label' in spectrum['metadata']:
                    spectrum['metadata']['label'] = new_label

        # Block signals during update
        self.is_batch_updating = True
        self.controller.spectra_list_widget.blockSignals(True)
        try:
            # Update list widget items
            for i in range(self.controller.spectra_list_widget.count()):
                item = self.controller.spectra_list_widget.item(i)
                item_id = item.data(Qt.UserRole)
                if item_id in id_to_new_label:
                    item.setText(id_to_new_label[item_id])
        finally:
            self.controller.spectra_list_widget.blockSignals(False)
            self.is_batch_updating = False
        
        # Restore selection
        self.selected_indices = selected_indices
        self.is_handling_selection = True
        try:
            for i in range(self.controller.spectra_list_widget.count()):
                self.controller.spectra_list_widget.item(i).setSelected(i in selected_indices)
        finally:
            self.is_handling_selection = False
        
        # Update spectrum counts and refresh the plot if in interactive mode
        self.update_spectra_count_label()
        if self.controller.interactive_mode_checkbox.isChecked() and self.selected_indices:
            self.controller.plot_spectra()
            
        # Update selected_spectra with new labels
        self.controller.selected_spectra = [
            self.controller.original_spectra[idx]
            for idx in self.selected_indices
        ]
        
    def delete_selected_spectra(self):
        """Delete selected spectra from the list and update the plot."""
        # Get indices of selected items
        selected_indices = sorted([
            self.controller.spectra_list_widget.row(item)
            for item in self.controller.spectra_list_widget.selectedItems()
        ], reverse=True)  # Sort in reverse order to remove from end first
        
        if not selected_indices:
            return
        
        # Show confirmation dialog. Wording mentions the Operations
        # History undo path explicitly — deletion visibly removes
        # spectra from the list, which is worth pausing for even though
        # it's also fully reversible by jumping to the previous state.
        n = len(selected_indices)
        noun = 'spectrum' if n == 1 else 'spectra'
        confirm = QMessageBox.question(
            self.controller.view,
            "Delete Spectra",
            f"Delete {n} selected {noun}?\n\n"
            "This can be undone afterward via Operations History.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if confirm != QMessageBox.Yes:
            return
        
        # Get the labels of selected spectra for operations history
        selected_spectra = []
        for index in selected_indices:
            spectrum = self.controller.original_spectra[index]
            selected_spectra.append(spectrum)
        
        # Register removal operation with operations controller if available
        if hasattr(self.controller, 'operations_controller'):
            # Register as a "removal" operation
            self.controller.operations_controller.register_removal_operation(selected_spectra)
        
        # Remove items from original_spectra list
        for index in selected_indices:
            del self.controller.original_spectra[index]
        
        # Remove items from list widget
        for index in selected_indices:
            self.controller.spectra_list_widget.takeItem(index)
        
        # Clear selected indices
        self.selected_indices.clear()
        
        # Update the plot
        self.controller.selected_spectra = []
        if self.controller.interactive_mode_checkbox.isChecked():
            self.controller.clear_graphics_view()
        
        # Update UI elements
        self.update_spectra_count_label()
        
        # Update spinbox maximum values based on the new number of spectra
        num_of_spectra = len(self.controller.original_spectra)
        self.controller.view.number_of_rows_spinBox.setMaximum(num_of_spectra)
        self.controller.view.number_of_columns_spinBox.setMaximum(num_of_spectra)