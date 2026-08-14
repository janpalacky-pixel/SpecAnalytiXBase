
# src/views/dialogs/misc/rename_spectra_dialog.py
from PyQt5.QtWidgets import (QDialog, QTableWidget, QTableWidgetItem, QVBoxLayout,
                            QHeaderView, QMenu, QInputDialog, QMessageBox,
                            QPushButton, QHBoxLayout, QApplication, QAbstractItemView,
                            QShortcut)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from src.views.dialogs.misc.spectra_selection_dialog import SpectraSelectionDialog
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)

class RenameSpectraDialog(QDialog):
    def __init__(self, parent=None, spectra_labels=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Rename Spectra")
        self.resize(500, 400)
        self.spectra_labels = spectra_labels or []
        self.parent = parent
        # Bound method (RenameSpectraController.commit_rename) passed in by
        # whatever opened this dialog, so Apply / Add as New can commit the
        # rename directly — same commit_callback pattern used by every other
        # refined operation (see SavitzkyGolayDialog).
        self.commit_callback = commit_callback

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create table widget
        self.table = QTableWidget(len(self.spectra_labels), 2)
        self.table.setHorizontalHeaderLabels(["Original Label", "New Label"])
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        # Set selection style to match spectrum selector (red background)
        self.table.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: red;
                color: white;
            }
        """)

        # Extended/by-cell selection is what makes multi-cell copy/paste
        # meaningful — matches the SVD analysis "Enter manually..." table.
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)

        # Temporarily disable sorting while populating
        self.table.setSortingEnabled(False)
        
        # Populate table
        for i, label in enumerate(self.spectra_labels):
            # Original label (non-editable)
            original_item = QTableWidgetItem(label)
            original_item.setFlags(original_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, original_item)
            
            # New label (editable, populated with original label initially)
            new_item = QTableWidgetItem(label)
            self.table.setItem(i, 1, new_item)
        
        # Re-enable sorting after populating
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        
        # Adjust column widths
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        # Excel-like copy/cut/paste/delete for the New Label column — same
        # shortcuts and behavior as the SVD analysis "Enter manually..."
        # table, except values here are arbitrary strings rather than
        # numbers, so pasted text is used as-is with no numeric parsing.
        self._install_clipboard_shortcuts()

        # Add selection buttons
        buttons_layout = QHBoxLayout()
        
        # Select all button
        select_all_button = QPushButton("Select All")
        select_all_button.clicked.connect(self.select_all_rows)
        buttons_layout.addWidget(select_all_button)
        
        # Deselect all button
        deselect_all_button = QPushButton("Deselect All")
        deselect_all_button.clicked.connect(self.deselect_all_rows)
        buttons_layout.addWidget(deselect_all_button)
        
        # Select spectra button
        select_spectra_button = QPushButton("Select Spectra...")
        select_spectra_button.clicked.connect(self.show_spectra_selection_dialog)
        buttons_layout.addWidget(select_spectra_button)
        
        layout.addLayout(buttons_layout)

        # Apply / Add as New commit directly via commit_callback — same
        # pattern as every other refined operation (see
        # SavitzkyGolayDialog / OperationsController.commit_sg_smoothing).
        # There's no separate "Run then confirm elsewhere" step: feedback
        # is shown right here, and the dialog closes itself only once the
        # commit actually succeeds.
        commit_buttons_layout = QHBoxLayout()
        commit_buttons_layout.addStretch()

        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Rename the spectra in place.")
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        commit_buttons_layout.addWidget(self.apply_button)

        self.add_as_new_button = QPushButton("Add as New")
        self.add_as_new_button.setToolTip(
            "Keep the original spectra unchanged and add renamed copies "
            "to the list under the new names."
        )
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        commit_buttons_layout.addWidget(self.add_as_new_button)

        self.help_button = QPushButton("Help")
        self.help_button.clicked.connect(self._show_help)
        commit_buttons_layout.addWidget(self.help_button)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        commit_buttons_layout.addWidget(self.close_button)

        layout.addLayout(commit_buttons_layout)

        self.setLayout(layout)

    def _install_clipboard_shortcuts(self):
        """Excel-style copy/cut/paste/delete for the New Label column
        (column 1), mirroring the SVD analysis manual-entry table."""
        table = self.table

        # Copy selected New Label cells (row order) to the clipboard,
        # newline-separated.
        def do_copy():
            value_items = sorted(
                (it for it in table.selectedItems() if it.column() == 1),
                key=lambda it: it.row()
            )
            if not value_items:
                return
            QApplication.clipboard().setText("\n".join(it.text() for it in value_items))
        QShortcut(QKeySequence.Copy, table).activated.connect(do_copy)

        # Paste into the New Label column, starting at the current/top
        # selected row — works the same whether the clipboard came from
        # this table (Ctrl+C above) or from an external spreadsheet. Any
        # string is accepted here (unlike the SVD parameter table, which
        # is numbers-only).
        def do_paste():
            text = QApplication.clipboard().text()
            if not text:
                return
            lines = [ln for ln in text.replace('\r', '').split('\n') if ln != '']
            selected_rows = sorted(it.row() for it in table.selectedItems())
            start_row = selected_rows[0] if selected_rows else max(table.currentRow(), 0)
            for i, line in enumerate(lines):
                row = start_row + i
                if row >= table.rowCount():
                    break
                # Spreadsheets paste multi-column selections tab-separated;
                # take the first token as the new label.
                token = line.split('\t')[0].strip()
                table.setItem(row, 1, QTableWidgetItem(token))
        QShortcut(QKeySequence.Paste, table).activated.connect(do_paste)

        # Clear all selected New Label cells at once.
        def do_delete():
            for it in table.selectedItems():
                if it.column() == 1:
                    it.setText("")
        QShortcut(QKeySequence.Delete, table).activated.connect(do_delete)

        # Cut = copy then clear, same as Excel/Word.
        def do_cut():
            do_copy()
            do_delete()
        QShortcut(QKeySequence.Cut, table).activated.connect(do_cut)

    def select_all_rows(self):
        """Select all rows in the table."""
        self.table.selectAll()
    
    def deselect_all_rows(self):
        """Deselect all rows in the table."""
        self.table.clearSelection()
    
    def show_spectra_selection_dialog(self):
        """Show the spectra selection dialog."""
        total_spectra = self.table.rowCount()
        if total_spectra == 0:
            return
            
        dialog = SpectraSelectionDialog(
            parent=self,
            total_spectra=total_spectra,
            title="Select Spectra for Renaming"
        )
        
        if dialog.exec_() == QDialog.Accepted:
            params = dialog.get_selection_parameters()
            self.apply_selection(params)
    
    def apply_selection(self, params):
        """Apply the selection based on parameters from the dialog."""
        start = params['start']
        end = params['end']
        step = params['step']
        action = params['action']
        
        # Get indices in the range with the specified step
        indices = range(start, end + 1, step)
        
        # Clear current selection first if this is a new selection
        if action == "select":
            self.table.clearSelection()
        
        # Apply the selection action
        for i in indices:
            if i < self.table.rowCount():
                # Calculate selection state based on action
                should_select = (action in ["select", "add"])
                
                # For "remove" action, we deselect items
                if action == "remove":
                    # Only deselect if it was previously selected
                    if self.table.item(i, 0).isSelected() or self.table.item(i, 1).isSelected():
                        self.table.item(i, 0).setSelected(False)
                        self.table.item(i, 1).setSelected(False)
                else:
                    # For "select" or "add", select both columns in the row
                    self.table.item(i, 0).setSelected(should_select)
                    self.table.item(i, 1).setSelected(should_select)

    def show_context_menu(self, position):
        """Show context menu for selected items in the table"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            return
            
        # Get selected indices (rows)
        selected_rows = set()
        for item in selected_items:
            selected_rows.add(item.row())
        
        # Create context menu
        menu = QMenu()
        add_prefix_action = menu.addAction("Add Prefix...")
        add_suffix_action = menu.addAction("Add Suffix...")
        menu.addSeparator()
        sequential_rename_action = menu.addAction("Sequential Rename...")
        replace_text_action = menu.addAction("Replace Text...")
        
        # Show menu and handle actions
        action = menu.exec_(self.table.viewport().mapToGlobal(position))
        
        if action == add_prefix_action:
            self.add_prefix(selected_rows)
        elif action == add_suffix_action:
            self.add_suffix(selected_rows)
        elif action == sequential_rename_action:
            self.sequential_rename(selected_rows)
        elif action == replace_text_action:
            self.replace_text(selected_rows)
    
    def add_prefix(self, selected_rows):
        """Add a prefix to selected items"""
        prefix, ok = QInputDialog.getText(self, "Add Prefix", "Enter prefix to add:")
        if ok and prefix:
            for row in selected_rows:
                current_text = self.table.item(row, 1).text()
                self.table.item(row, 1).setText(prefix + current_text)
    
    def add_suffix(self, selected_rows):
        """Add a suffix to selected items"""
        suffix, ok = QInputDialog.getText(self, "Add Suffix", "Enter suffix to add:")
        if ok and suffix:
            for row in selected_rows:
                current_text = self.table.item(row, 1).text()
                self.table.item(row, 1).setText(current_text + suffix)
    
    def sequential_rename(self, selected_rows):
        """Rename items sequentially using a pattern"""
        pattern, ok = QInputDialog.getText(
            self, 
            "Sequential Rename", 
            "Enter pattern with # for number\n(e.g., 'sample_#' becomes 'sample_1', 'sample_2', etc.)"
        )
        
        if not ok or not pattern:
            return
            
        if '#' not in pattern:
            QMessageBox.warning(
                self,
                "Invalid Pattern",
                "Pattern must contain # to be replaced with numbers"
            )
            return
        
        # Sort the selected rows to maintain order
        sorted_rows = sorted(selected_rows)
        
        # Ask for starting number and padding
        start_num, ok = QInputDialog.getInt(
            self, 
            "Starting Number", 
            "Enter starting number:",
            value=1,
            min=0,
            max=9999
        )
        if not ok:
            return
            
        padding, ok = QInputDialog.getInt(
            self, 
            "Number Padding", 
            "Enter number of digits (padding with zeros):",
            value=1,
            min=1,
            max=10
        )
        if not ok:
            return
        
        # Apply sequential numbering
        for i, row in enumerate(sorted_rows):
            num = start_num + i
            num_str = str(num).zfill(padding)
            new_name = pattern.replace('#', num_str)
            self.table.item(row, 1).setText(new_name)
    
    def replace_text(self, selected_rows):
        """Replace text in selected items"""
        find_text, ok = QInputDialog.getText(self, "Replace Text", "Text to find:")
        if not ok:
            return
            
        replace_text, ok = QInputDialog.getText(self, "Replace Text", "Replace with:")
        if not ok:
            return
        
        replacements_made = 0
        for row in selected_rows:
            current_text = self.table.item(row, 1).text()
            if find_text in current_text:
                new_text = current_text.replace(find_text, replace_text)
                self.table.item(row, 1).setText(new_text)
                replacements_made += 1
        
        if replacements_made == 0:
            QMessageBox.information(
                self,
                "No Replacements",
                f"Text '{find_text}' not found in any selected items."
            )

    def get_renamed_labels(self, add_as_new=False):
        """
        Get dictionary mapping original labels to new labels, validating
        against the rows visible in this dialog only. (The commit
        callback repeats a fuller check against every spectrum in the
        app, including any outside this dialog's subset — see
        RenameSpectraController.commit_rename.)

        Args:
            add_as_new: Which set of resulting labels must be
                collision-free.
                - False (Apply / replace in place): a renamed row's old
                  label goes away, so only "new labels" and "labels of
                  untouched rows" need to be distinct from each other.
                - True (Add as New): every row's ORIGINAL label keeps
                  existing regardless of whether it's renamed, and each
                  renamed row additionally produces a new spectrum under
                  its new label — so original labels (all of them) and
                  new labels (from renamed rows) all need to be distinct
                  from each other.

        Returns:
            Dictionary of {original_label: new_label} (only rows whose
            label actually changed) or None if validation fails.
        """
        rows = []
        for i in range(self.table.rowCount()):
            original_label = self.table.item(i, 0).text()
            new_label = self.table.item(i, 1).text().strip()

            # Check for empty labels
            if not new_label:
                QMessageBox.warning(self, "Invalid Label", "Labels cannot be empty.")
                return None

            rows.append((original_label, new_label))

        # Build the set of labels that will exist, among this dialog's own
        # rows, after the operation — evaluated as if the whole batch were
        # applied at once (not one rename at a time), so a genuine swap
        # (e.g. Alpha <-> Beta in the same action) isn't falsely blocked.
        final_labels = []
        for original_label, new_label in rows:
            changed = original_label != new_label
            if add_as_new:
                # The original spectrum persists unchanged either way.
                final_labels.append(original_label)
                if changed:
                    final_labels.append(new_label)
            else:
                # Replace-in-place: the row ends up under new_label,
                # whether or not it was actually changed.
                final_labels.append(new_label)

        counts = {}
        for label in final_labels:
            counts[label] = counts.get(label, 0) + 1
        colliding = sorted(label for label, n in counts.items() if n > 1)

        if colliding:
            names = "', '".join(colliding)
            QMessageBox.warning(
                self,
                "Duplicate Name",
                f"The name(s) '{names}' would be used by more than one spectrum. "
                f"Each spectrum must have a unique name."
            )
            return None

        # Confirmed real bug this guards against: apply_renamed_labels
        # (both this dialog's own commit path and RenameSpectraManager's)
        # match spectra to rename purely by CURRENT LABEL TEXT — the same
        # "labels aren't stable/unique identifiers" issue this app's own
        # _key_for() convention exists everywhere else to avoid (see e.g.
        # SpikeRemovalManager, XAxisAlignmentManager). If two DIFFERENT
        # spectra share the same current label (a real, reachable case —
        # e.g. two separate import sessions producing the same filename-
        # derived label), this dialog still shows them as two separate
        # rows (built per-index, not per-unique-label) and happily lets
        # the user type two DIFFERENT new names for them. But the
        # {original_label: new_label} dict below can only hold ONE
        # mapping per original_label — the second row's entry silently
        # overwrites the first's in this dict comprehension. Downstream,
        # apply_renamed_labels() then matches EVERY spectrum whose current
        # label equals that key — so BOTH spectra would be renamed to
        # whichever new name survived, not just the one the user actually
        # intended for it. The existing 'Duplicate Name' check above does
        # NOT catch this — it validates the resulting NEW labels for
        # collisions, not the original ones, so two distinct, valid new
        # names for two same-labeled spectra sail straight through it.
        #
        # Refused outright here rather than silently losing/misapplying a
        # rename, matching this dialog's existing philosophy for the
        # 'Duplicate Name' case above — same kind of unsafe-to-proceed
        # situation, same response.
        original_label_counts = {}
        for original_label, _ in rows:
            original_label_counts[original_label] = original_label_counts.get(original_label, 0) + 1
        ambiguous_originals = sorted(
            label for label, n in original_label_counts.items() if n > 1
        )
        if ambiguous_originals:
            names = "', '".join(ambiguous_originals)
            QMessageBox.warning(
                self,
                "Ambiguous Original Name",
                f"'{names}' is the current name of more than one spectrum "
                f"in this list. Renaming can't tell them apart by name "
                f"alone, so applying different new names to each here "
                f"isn't safe \u2014 it could rename the wrong one, or lose "
                f"one of the changes entirely.\n\n"
                f"Please rename these spectra one at a time (so only one "
                f"of them is open in this dialog at once), or give them "
                f"distinct names through another route first."
            )
            return None

        result = {
            original_label: new_label
            for original_label, new_label in rows
            if original_label != new_label
        }
        return result

    def _show_help(self):
        """Open the Rename Spectra help dialog."""
        try:
            from src.help.rename_help import (
                get_rename_help_title,
                get_rename_help_content,
            )
            from src.help.help_window import show_help_window
            show_help_window(
                self,
                get_rename_help_title(),
                get_rename_help_content(),
            )
        except Exception as exc:
            logger.error("Failed to open help: %s", exc, exc_info=True)
            QMessageBox.information(self, "Help",
                                    "Help content could not be loaded.")

    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — commits directly via commit_callback. No
        separate OK/accept step: feedback (success or failure) is shown
        right here next to the buttons that triggered it. The dialog
        closes itself once the commit succeeds.
        """
        if self.commit_callback is None:
            QMessageBox.critical(
                self, "Not Available",
                "This dialog was opened without a way to apply changes."
            )
            return

        renamed_labels = self.get_renamed_labels(add_as_new=add_as_new)
        if renamed_labels is None:
            return

        if not renamed_labels:
            QMessageBox.information(self, "No Changes", "No labels were changed.")
            return

        action = ("add renamed copies as new spectra" if add_as_new
                  else "rename the selected spectra")
        confirm = QMessageBox.question(
            self, "Confirm", f"{action[0].upper() + action[1:]}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(renamed_labels, add_as_new)
        if success:
            QMessageBox.information(self, "Done", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Could Not Apply", message)