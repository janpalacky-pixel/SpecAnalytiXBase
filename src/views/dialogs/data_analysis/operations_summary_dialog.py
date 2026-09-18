# src/views/dialogs/data_analysis/operations_summary_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QListWidget, QListWidgetItem, 
                           QPushButton, QHBoxLayout, QDialogButtonBox, QLabel,
                           QMessageBox, QWidget, QTableWidget, QTableWidgetItem, QHeaderView, 
                           QFrame, QFileDialog, QTabWidget, QMenu, QApplication, QAbstractItemView)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QBrush,QCursor
import numpy as np
from datetime import datetime
import pandas as pd
import re
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectrum_identity import spectrum_key
logger = get_logger(__name__)

# Internal operation-type strings the rest of this file dispatches on
# (unchanged everywhere else — every .startswith() check, every
# correction_history tag match) vs. what's actually shown to the user —
# kept as a translation table used only where text is displayed, since
# the internal string is also relied on for dispatch outside this file
# (operations_controller.py, main_controller.py menu bindings). Only add
# an entry here if the internal name would otherwise be confusing/wrong
# to show verbatim — most operation names are already fine as-is.
_OPERATION_DISPLAY_NAME_OVERRIDES = {
    # (empty — "Spectral Arithmetic" used to need translating to
    # "Combine Spectra" here; the internal dispatch string itself was
    # renamed instead, so there's nothing left to override.)
}


def _display_name_for_operation(operation_name):
    """Return the user-facing name for operation_name, translating the
    (possibly suffixed, e.g. '... (add as new)') internal name via
    _OPERATION_DISPLAY_NAME_OVERRIDES where one applies, unchanged
    otherwise."""
    if not operation_name:
        return operation_name
    for internal, display in _OPERATION_DISPLAY_NAME_OVERRIDES.items():
        if operation_name.startswith(internal):
            return display + operation_name[len(internal):]
    return operation_name

class SpectraListDialog(QDialog):
    """Dialog showing a list of spectra used in an operation."""
    
    def __init__(self, operation_name, spectra_list, parent=None, operations_manager=None, operation_index=None):
        super().__init__(parent)
        self.operation_name = operation_name  # Store operation_name properly
        self.setWindowTitle(f"Spectra Information: {operation_name}")
        self.spectra_list = spectra_list
        self.operations_manager = operations_manager
        self.operation_index = operation_index
        self.resize(800, 500)  # Wider to accommodate more columns
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Add title label with appropriate text based on whether it's original state
        if self.operation_name == "Original State":
            title_label = QLabel("Available spectra in original data:")
        elif "removal" in self.operation_name.lower():  # Check if it's a removal operation
            # Both operations this covers (Cosmic ray removal, Spike
            # removal) remove SPIKES from spectra -- they don't remove
            # spectra themselves. "The following spectra were removed"
            # said the opposite of what actually happened.
            title_label = QLabel("Spikes were removed from the following spectra:")

        else:
            title_label = QLabel("The following spectra were used in this operation:")
        
        title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(title_label)
        
        # Get all spectra data
        if self.operation_name == "Original State" and self.operations_manager:
            # Original State genuinely has multiple groups to switch
            # between -- "All Spectra" alongside each import batch -- so a
            # tab widget earns its place here.
            self.tabs = QTabWidget()
            layout.addWidget(self.tabs)
            self._create_import_batch_tabs()
        else:
            # A single operation's affected-spectra view only ever has ONE
            # group to show. Wrapping it in a QTabWidget just for a single,
            # always-selected "All Spectra" tab added a tab bar with
            # nothing to actually switch between -- and cropped, since the
            # tab's width wasn't wide enough for its own label. Show the
            # table directly in the layout instead; no tabs needed.
            spectra_data = self._get_spectra_data()
            table_widget = self._build_spectra_table_widget(spectra_data)
            layout.addWidget(table_widget)
        
        # Add close button
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _get_original_spectra_data(self):
        """Get data from original spectra in operations manager."""
        result = {}
        
        if self.operations_manager and hasattr(self.operations_manager, 'original_spectra'):
            for spectrum in self.operations_manager.original_spectra:
                if 'label' in spectrum:
                    result[spectrum['label']] = spectrum
        
        return result
    
    def _get_spectra_data(self):
        """Get full spectrum data from operations manager if available."""
        if not self.operations_manager or self.operation_index is None:
            return None
            
        operation = self.operations_manager.get_operation_at_index(self.operation_index)
        if not operation:
            return None
        
        # Special handling for removal operations - show the removed spectra
        if operation.get('type') == 'removal' and 'removed_spectra' in operation:
            result = {}
            for spectrum in operation.get('removed_spectra', []):
                if 'label' in spectrum:
                    result[spectrum['label']] = spectrum
            return result if result else None
            
        # Normal handling for other operations (existing code)
        result = {}
        
        # First try input_spectra (for older operations)
        input_spectra = operation.get('input_spectra', [])
        for spectrum in input_spectra:
            if 'label' in spectrum:
                result[spectrum['label']] = spectrum
        
        # Then check output_spectra
        output_spectra = operation.get('output_spectra', [])
        affected_labels = operation.get('affected_labels', [])
        
        for spectrum in output_spectra:
            if 'label' in spectrum and spectrum['label'] in affected_labels:
                # Only include affected spectra from output
                result[spectrum['label']] = spectrum
        
        return result if result else None        


    def _create_import_batch_tabs(self):
        """Create tabs for each import batch."""
        # Get original spectra data
        spectra_data = self._get_original_spectra_data()
        
        # Debug import batches
        if hasattr(self.operations_manager, 'import_batches'):
            logger.debug(f"DEBUG: Found {len(self.operations_manager.import_batches)} import batches")
            for i, batch in enumerate(self.operations_manager.import_batches):
                logger.debug(f"DEBUG: Batch {i+1} has {len(batch.get('spectra_labels', []))} spectra")
        else:
            logger.debug("DEBUG: No import_batches property found in operations_manager")
        
        # If no import batches are tracked, show all in one tab
        if not hasattr(self.operations_manager, 'import_batches') or not self.operations_manager.import_batches:
            logger.debug("DEBUG: No batches found, showing all spectra in one tab")
            self._create_spectra_table("All Spectra", spectra_data)
            return
        
        # Create an "All Spectra" tab first
        self._create_spectra_table("All Spectra", spectra_data)
        
        # Create a tab for each import batch
        for i, batch in enumerate(self.operations_manager.import_batches):
            batch_spectra = {}
            for label in batch.get('spectra_labels', []):
                if label in spectra_data:
                    batch_spectra[label] = spectra_data[label]
            
            # Format timestamp for tab name
            timestamp = batch.get('timestamp', '')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    tab_name = f"Batch {i+1}: {dt.strftime('%Y-%m-%d %H:%M')}"
                except:
                    tab_name = f"Batch {i+1}"
            else:
                tab_name = f"Batch {i+1}"
            
            logger.debug(f"DEBUG: Creating tab '{tab_name}' with {len(batch_spectra)} spectra")
            self._create_spectra_table(tab_name, batch_spectra)
    
    def _create_spectra_table(self, tab_name, spectra_data):
        """Build a table of spectra and add it as a new tab in self.tabs
        (multi-tab case — see _create_import_batch_tabs)."""
        tab = self._build_spectra_table_widget(spectra_data)
        self.tabs.addTab(tab, tab_name)

    def _build_spectra_table_widget(self, spectra_data):
        """Build and return the actual table widget, without adding it to
        any tab widget. Shared by _create_spectra_table (multi-tab case)
        and setup_ui's single-group case (no tabs at all)."""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        
        # Create table for better organization
        table = QTableWidget()
        table.setColumnCount(6)  # More columns for additional info
        table.setHorizontalHeaderLabels([
            "Spectrum Name", "Points", "X Min", "X Max", "Avg Step", "Step Variance"
        ])
        
        # Get the list of removed spectra labels in the current state
        removed_labels = set()
        if self.operation_name == "Original State" and self.operations_manager and hasattr(self.operations_manager, 'active_operation_index'):
            active_index = self.operations_manager.active_operation_index
            if active_index >= 0:
                current_state_spectra = self.operations_manager.get_current_spectra()
                current_labels = {s['label'] for s in current_state_spectra}
                original_labels = {s['label'] for s in self.operations_manager.original_spectra}
                removed_labels = original_labels - current_labels
        
        # Populate table
        if spectra_data:
            table.setRowCount(len(spectra_data))
            
            for i, (spectrum_name, spectrum_data) in enumerate(spectra_data.items()):
                # Spectrum Name
                item = QTableWidgetItem(spectrum_name)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                
                # Highlight removed spectra in red
                if spectrum_name in removed_labels:
                    item.setBackground(QBrush(QColor(255, 200, 200)))  # Light red
                    item.setToolTip("This spectrum has been removed in the current state")
                
                table.setItem(i, 0, item)
                
                # Points Count
                points = len(spectrum_data.get('x_scale', []))
                item = QTableWidgetItem(str(points))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i, 1, item)
                
                # Calculate statistics
                x_scale = spectrum_data.get('x_scale', [])
                if len(x_scale) > 1:
                    # X Min
                    x_min = min(x_scale)
                    item = QTableWidgetItem(f"{x_min:.6g}")
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    table.setItem(i, 2, item)
                    
                    # X Max
                    x_max = max(x_scale)
                    item = QTableWidgetItem(f"{x_max:.6g}")
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    table.setItem(i, 3, item)
                    
                    if len(x_scale) > 1:
                        # Avg Step
                        diffs = np.diff(x_scale)
                        avg_step = np.mean(np.abs(diffs))
                        item = QTableWidgetItem(f"{avg_step:.6g}")
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        table.setItem(i, 4, item)
                        
                        # Step Variance
                        variance = np.var(diffs)
                        item = QTableWidgetItem(f"{variance:.6g}")
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        # Highlight high variance
                        if variance > 0.1 * avg_step:
                            item.setBackground(QBrush(QColor(255, 255, 150)))  # Light yellow
                        table.setItem(i, 5, item)
                    else:
                        # N/A for step and variance if only one point
                        for col in range(4, 6):
                            item = QTableWidgetItem("N/A")
                            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                            table.setItem(i, col, item)
                else:
                    # N/A for all stats if no x values
                    for col in range(2, 6):
                        item = QTableWidgetItem("N/A")
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        table.setItem(i, col, item)
        else:
            # Simple list display for empty data
            table.setRowCount(1)
            item = QTableWidgetItem("No spectra available")
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(0, 0, item)
            for col in range(1, 6):
                item = QTableWidgetItem("")
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(0, col, item)
        
        # Adjust column widths
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Spectrum name gets extra space
        for col in range(1, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        
        # Enable sorting
        table.setSortingEnabled(True)
        # Sort by spectrum name initially
        table.sortByColumn(0, Qt.AscendingOrder)
        
        tab_layout.addWidget(table)
        return tab

class OperationParametersDialog(QDialog):
    """Dialog for displaying detailed parameters of an operation."""

    def __init__(self, operation_name, operation_index, parameters, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Parameters for {_display_name_for_operation(operation_name)}")
        self.operation_name = operation_name
        self.operation_index = operation_index
        self.parameters = parameters
        self.parent = parent  # Store parent for calling methods
        self.operations_manager = None  # Will be initialized in setup_ui
        self.resize(650, 450)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Get operations manager from parent if available
        if hasattr(self.parent, 'operations_manager'):
            self.operations_manager = self.parent.operations_manager
        
        # Add title label
        title_label = QLabel(
            f"Parameters for Operation #{self.operation_index + 1}: "
            f"{_display_name_for_operation(self.operation_name)}"
        )
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)
        
        # Create table for parameters
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Parameter", "Value"])
        # Long list/dict values are rendered one item per line (see
        # _format_value_for_display) instead of Python's raw repr, so word
        # wrap + per-row auto-height (below) display them as readable rows
        # rather than one giant string that only fits if the dialog itself
        # is stretched very wide.
        self.table.setWordWrap(True)
        
        # Populate parameters table
        if isinstance(self.parameters, dict):
            # Special handling for different operations
            if self.operation_name.startswith("Manual baseline"):
                self.setup_baseline_parameters()
            elif self.operation_name.startswith("SG-smoothing"):
                self.setup_sg_parameters()
            elif self.operation_name.startswith("Cosmic ray removal"):
                self.setup_cosmic_ray_parameters()
            elif self.operation_name.startswith("Normalization"):
                self.setup_normalization_parameters()
            elif self.operation_name.startswith("SVD background"):
                self.setup_svd_background_parameters()
            elif self.operation_name.startswith("Combine Spectra"):
                self.setup_combine_spectra_parameters()
            elif self.operation_name.startswith("Spectral Calculator"):
                self.setup_spectral_calculator_parameters()
            elif self.operation_name.startswith("NMF"):
                self.setup_nmf_parameters()
            elif self.operation_name.startswith("MCR-ALS"):
                self.setup_mcr_als_parameters()
            elif self.operation_name.startswith("Automated Baseline"):
                self.setup_automated_baseline_parameters()
            elif self.operation_name.startswith("SNIP Baseline"):
                self.setup_snip_baseline_parameters()
            elif self.operation_name.startswith("Resolution enhancement"):
                self.setup_resolution_enhancement_parameters()
            elif self.operation_name.startswith("Spike removal"):
                self.setup_spike_removal_parameters()
            elif self.operation_name.startswith("Data range"):
                self.setup_data_range_parameters()
            elif self.operation_name.startswith("FFT Denoising"):
                self.setup_fft_denoising_parameters()
            elif self.operation_name.startswith("X-axis alignment"):
                self.setup_xaxis_alignment_parameters()
            elif self.operation_name.startswith("Interactive subtraction"):
                self.setup_interactive_subtraction_parameters()
            elif self.operation_name.startswith("CD Unit Conversion"):
                self.setup_cd_unit_conversion_parameters()
            elif self.operation_name.startswith("Peak Fitting"):
                self.setup_peak_fitting_parameters()
            elif (isinstance(self.parameters, dict) and
                  set(self.parameters.keys()) == {'copied_count', 'source_labels', 'copy_labels'}):
                self.setup_copy_operation_parameters()
            else:
                # Standard parameter display for other operations
                self.setup_standard_parameters()
        else:
            # If parameters is not a dict, just display it as a string
            self.table.setRowCount(1)
            
            # Non-editable items
            param_item = QTableWidgetItem("Parameters")
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(0, 0, param_item)
            
            value_item = QTableWidgetItem(self._format_value_for_display(self.parameters))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(0, 1, value_item)
        
        # Connect cell click handler for clickable values
        self.table.cellClicked.connect(self.handle_cell_click)
        
        # Adjust column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)

        # Grow each row to fit its (possibly multi-line) value instead of
        # clipping it to a single line's height. Also re-run this once the
        # dialog is actually shown: the Value column's real width (it's
        # Stretch-resized) isn't known until then, and word-wrapped line
        # counts depend on it.
        self.table.resizeRowsToContents()

        layout.addWidget(self.table)
        
        # For baseline operation, add the action buttons in a separate area
        if self.operation_name.startswith("Manual baseline"):
            self.add_baseline_action_buttons()
        
        # Add close button
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _get_baseline_corrections_data(self):
        """Return the {spectrum_key: {'type':..., 'points':..., 'order':...,
        'label':...}} dict used by setup_baseline_parameters(),
        add_baseline_action_buttons(), and show_baseline_points_dialog().

        Keyed by spectrum_key() (unique_id), not label — a 'label' field
        is still included on each entry for display, but is never used as
        a lookup key anywhere downstream. See get_corrections_info() in
        baseline_correction_controller.py, which this mirrors.

        In Apply mode self.parameters already carries this directly —
        it's the 'corrections' key commit_manual_baseline() writes into
        the operation's own params. In Add as New mode, though, the
        record actually sitting in the chain by the time this dialog
        opens is register_copy_operation()'s generic one (just
        copied_count/source_labels/copy_labels) — the original Manual
        baseline params, 'corrections' included, were popped off and
        never reach here, which is exactly why this was showing
        empty/wrong data.

        Rebuilt instead from each new copy's own correction_history,
        using the same output_spectra + source-to-copy label remapping
        as show_normalization_details_dialog / show_cosmic_ray_details_
        dialog, then keyed back to the SOURCE label so callers keep
        seeing the same keys as before. Matched exactly against
        'Manual baseline' — the operation type string used for dialog
        dispatch (deliberately kept identical; this used to differ in
        case, a latent footgun since unified).

        'points' here is built from the entry's 'point_coordinates' field
        (the actual (x, y) list) rather than left as the bare point
        COUNT correction_history otherwise carries. Without this,
        show_baseline_points_dialog's own int-vs-list handling would take
        its int branch and fall back to
        self.operations_manager.get_baseline_points() — which reads a
        'baseline_state' snapshot attached to the ORIGINAL "Manual
        baseline" operation record, discarded in Add as New mode when
        that record is popped and replaced by register_copy_operation()'s
        generic one. Confirmed: that fallback was silently returning
        nothing, showing "Point Count: 0" / "No baseline points defined"
        for every spectrum despite the fit type and count displaying
        correctly (those came from the OTHER fields on this same entry).
        """
        if 'corrections' in self.parameters:
            return self.parameters.get('corrections', {})

        corrections = {}
        if not (self.operations_manager and self.operation_index >= 0):
            return corrections

        operation = self.operations_manager.get_operation_at_index(self.operation_index)
        if not operation:
            return corrections

        params = operation.get('parameters') or {}
        src_labels = params.get('source_labels') or []
        copy_labels = params.get('copy_labels') or []
        source_to_copy_label = (
            dict(zip(src_labels, copy_labels))
            if len(src_labels) == len(copy_labels) else {}
        )

        label_to_spectrum = {s['label']: s for s in operation.get('output_spectra', [])}

        for label in src_labels:
            lookup_label = source_to_copy_label.get(label, label)
            spectrum = label_to_spectrum.get(lookup_label)
            history = ((spectrum or {}).get('metadata') or {}).get('correction_history', [])
            entry = next((e for e in reversed(history) if e.get('operation') == 'Manual baseline'), None)
            if entry:
                entry_fields = {k: v for k, v in entry.items() if k in ('type', 'order')}
                # Prefer the real coordinate list over the bare count —
                # see docstring above for why the count-only fallback is
                # unusable in Add as New mode.
                if 'point_coordinates' in entry:
                    entry_fields['points'] = entry['point_coordinates']
                elif 'points' in entry:
                    entry_fields['points'] = entry['points']
                if entry_fields and spectrum is not None:
                    entry_fields['label'] = spectrum.get('label', label)
                    corrections[spectrum_key(spectrum)] = entry_fields

        return corrections

    def add_baseline_action_buttons(self):
        """Add action buttons for baseline operation."""
        corrections_data = self._get_baseline_corrections_data()
        
        # Create button layout
        action_layout = QHBoxLayout()
        
        use_points_button = QPushButton("Use These Points")
        use_points_button.setToolTip(
            "Jump back to the state right before this baseline correction, "
            "and preload these points so you can tweak them instead of "
            "starting from scratch"
        )
        use_points_button.clicked.connect(lambda: self.use_baseline_points(corrections_data))
        
        export_button = QPushButton("Export")
        export_button.setToolTip("Export baseline points to clipboard or file")
        export_button.clicked.connect(lambda: self.export_baseline_points(corrections_data))
        
        action_layout.addWidget(use_points_button)
        action_layout.addWidget(export_button)
        action_layout.addStretch()  # Push buttons to the left
        
        # Add a separator line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        
        # Add to main layout
        self.layout().addSpacing(10)
        self.layout().addWidget(line)
        self.layout().addLayout(action_layout)
    
    def setup_standard_parameters(self):
        """Set up standard parameters display."""
        params_list = list(self.parameters.items())
        self.table.setRowCount(len(params_list))
        
        for row, (key, value) in enumerate(params_list):
            # Parameter name - non-editable
            param_item = QTableWidgetItem(str(key))
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, param_item)
            
            # Parameter value - human-readable, one item per line for
            # lists/dicts rather than Python's raw repr.
            value_item = QTableWidgetItem(self._format_value_for_display(value))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, value_item)

        self.table.resizeRowsToContents()

    def setup_peak_fitting_parameters(self):
        """Set up parameters table for Peak Fitting.

        Previously fell through to setup_standard_parameters(), which has
        no special handling for a list of per-peak dicts — each peak came
        out as one line of raw Python dict repr
        ("{'model': 'Gaussian', 'parameters': {'height': 0.038, ...}}"),
        exactly as unreadable as the SVD Background / SNIP Baseline
        tables were before those got the same treatment. Now: a proper
        one-row-per-peak table (Peak #, Model, Center, Height, Width,
        FWHM, Area), plus which output options were selected shown once
        as plain text above it, not repeated per peak.
        """
        fit_results = self.parameters.get('fit_results') or []
        output_options = self.parameters.get('output_options') or {}

        rows = []
        for i, peak in enumerate(fit_results):
            model = peak.get('model', '?')
            p = peak.get('parameters', {}) or {}
            width_key = 'sigma' if model == 'Gaussian' else 'gamma'
            rows.append({
                'peak_num': i + 1,
                'model': model,
                'center': p.get('center'),
                'height': p.get('height'),
                'width': p.get(width_key),
                'width_label': width_key,
                'fwhm': p.get('fwhm'),
                'area': p.get('area'),
            })

        selected_options = [
            label for key, label in [
                ('add_fit', 'Total fit'),
                ('add_residual', 'Residual'),
                ('add_peaks', 'Individual peaks'),
            ] if output_options.get(key)
        ]
        options_text = (
            ', '.join(selected_options) if selected_options
            else '(none — analysis only, no output spectra created)'
        )

        self.table.setRowCount(1)

        options_item = QTableWidgetItem("Output spectra created")
        options_item.setFlags(options_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(0, 0, options_item)
        options_value_item = QTableWidgetItem(options_text)
        options_value_item.setFlags(options_value_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(0, 1, options_value_item)

        if rows:
            param_item = QTableWidgetItem("Fitted Peaks")
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setRowCount(2)
            self.table.setItem(1, 0, param_item)
            value_item = QTableWidgetItem("Click to view fitted peak parameters")
            value_item.setForeground(QBrush(QColor(0, 0, 255)))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            value_item.setData(Qt.UserRole, rows)
            self.table.setItem(1, 1, value_item)

        self.table.resizeRowsToContents()

    def show_peak_fitting_details_dialog(self, rows):
        """Show the per-peak fitted-parameters table (Peak #, Model,
        Center, Height, Width, FWHM, Area) — replaces the raw dict-repr
        dump that used to show one peak's full Python dict per line."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Fitted Peaks for Operation #{self.operation_index + 1}")
        dialog.resize(680, 420)
        layout = QVBoxLayout(dialog)

        title_label = QLabel("Fitted peak parameters")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        columns = ['Peak #', 'Model', 'Center', 'Height', 'Width', 'FWHM', 'Area']
        table = QTableWidget()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for c in [0, 2, 3, 4, 5, 6]:
            table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)

        def fmt(v):
            return f"{v:.6g}" if isinstance(v, (int, float)) else str(v)

        table.setRowCount(len(rows))
        for r, entry in enumerate(rows):
            peak_item = QTableWidgetItem()
            peak_item.setData(Qt.DisplayRole, entry['peak_num'])
            peak_item.setFlags(peak_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 0, peak_item)

            model_item = QTableWidgetItem(entry['model'])
            model_item.setFlags(model_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 1, model_item)

            center_item = QTableWidgetItem(fmt(entry['center']))
            center_item.setFlags(center_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 2, center_item)

            height_item = QTableWidgetItem(fmt(entry['height']))
            height_item.setFlags(height_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 3, height_item)

            width_text = f"{fmt(entry['width'])} ({entry['width_label']})"
            width_item = QTableWidgetItem(width_text)
            width_item.setFlags(width_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 4, width_item)

            fwhm_item = QTableWidgetItem(fmt(entry['fwhm']))
            fwhm_item.setFlags(fwhm_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 5, fwhm_item)

            area_item = QTableWidgetItem(fmt(entry['area']))
            area_item.setFlags(area_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 6, area_item)

        layout.addWidget(table)

        button_row = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setToolTip("Copy the table above as tab-separated text")
        copy_btn.clicked.connect(lambda: self._copy_table_to_clipboard(table))
        button_row.addWidget(copy_btn)
        button_row.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        button_row.addWidget(button_box)
        layout.addLayout(button_row)

        dialog.exec_()

    def setup_copy_operation_parameters(self):
        """Set up parameters table for the generic 'copy operation' record
        shape (copied_count/source_labels/copy_labels) written by
        register_copy_operation() — used by operations with no dedicated
        parameters display of their own, currently 2D Map's ROI/cluster
        export and plain 'Copy spectra'. (Operations that DO have their
        own setup_<x>_parameters() — SVD Background, NMF, MCR-ALS, etc. —
        never reach here even for their own "(add as new)" records, since
        the dispatch above matches by name prefix regardless of that
        suffix.)

        Confirmed real complaint: source_labels and copy_labels were
        shown as two full, separately-scrollable lists of the same
        length, each one systematically derivable from the other (every
        copy is the matching source with a fixed prefix/suffix) — reading
        them meant visually cross-referencing two parallel lists by
        position. When the two lists correspond 1:1 (true for every
        currently-affected caller), this now shows ONE combined
        "Source → New Name" table instead, one row per pair.
        copied_count is dropped entirely — it's just len(source_labels),
        already implied by the row count.
        """
        source_labels = self.parameters.get('source_labels') or []
        copy_labels = self.parameters.get('copy_labels') or []

        self.table.setRowCount(1)
        param_item = QTableWidgetItem("Spectra Created")
        param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(0, 0, param_item)

        if len(source_labels) == len(copy_labels) and source_labels:
            value_item = QTableWidgetItem("Click to view source \u2192 new name pairs")
            value_item.setForeground(QBrush(QColor(0, 0, 255)))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            value_item.setData(Qt.UserRole, list(zip(source_labels, copy_labels)))
            self.table.setItem(0, 1, value_item)
        else:
            # Counts genuinely differ (shouldn't happen for any current
            # caller, but the shape check above is structural, not
            # semantic — fall back to showing both lists plainly rather
            # than silently dropping information a future caller might
            # actually need both halves of.
            text = (
                f"{len(copy_labels)} new spectra from {len(source_labels)} source spectra:\n"
                f"Sources: {self._format_value_for_display(source_labels)}\n"
                f"New names: {self._format_value_for_display(copy_labels)}"
            )
            value_item = QTableWidgetItem(text)
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(0, 1, value_item)

        self.table.resizeRowsToContents()

    def show_copy_operation_pairs_dialog(self, pairs):
        """Show the Source \u2192 New Name table for a generic copy
        operation — see setup_copy_operation_parameters for the full
        reasoning."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Spectra Created for Operation #{self.operation_index + 1}")
        dialog.resize(560, 420)
        layout = QVBoxLayout(dialog)

        title_label = QLabel("Source spectrum \u2192 new spectrum")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        columns = ['Source', 'New Name']
        table = QTableWidget()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        table.setRowCount(len(pairs))
        for r, (source, copy) in enumerate(pairs):
            source_item = QTableWidgetItem(source)
            source_item.setFlags(source_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 0, source_item)

            copy_item = QTableWidgetItem(copy)
            copy_item.setFlags(copy_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 1, copy_item)

        layout.addWidget(table)

        button_row = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setToolTip("Copy the table above as tab-separated text")
        copy_btn.clicked.connect(lambda: self._copy_table_to_clipboard(table))
        button_row.addWidget(copy_btn)
        button_row.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        button_row.addWidget(button_box)
        layout.addLayout(button_row)

        dialog.exec_()

    def setup_baseline_parameters(self):
        """Set up parameters table for baseline operations."""
        # Extract corrections data
        corrections = self._get_baseline_corrections_data()
        
        # Create a table with baseline related parameters - just one row
        self.table.setRowCount(1)
        
        # Row 1: Baseline Points
        param_item = QTableWidgetItem("Baseline Points")
        param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(0, 0, param_item)
        
        value_item = QTableWidgetItem("Click to view baseline points")
        value_item.setForeground(QBrush(QColor(0, 0, 255)))  # Blue text for clickable
        value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
        value_item.setData(Qt.UserRole, corrections)
        self.table.setItem(0, 1, value_item)
        
    def setup_cosmic_ray_parameters(self):
        """Set up parameters table for Cosmic ray removal — global settings
        (threshold, replace_window) shown directly, per-spectrum detail
        (which x-positions were flagged/replaced for THIS spectrum) behind
        a clickable row, the same pattern as setup_baseline_parameters."""
        params_list = list(self.parameters.items())
        self.table.setRowCount(len(params_list) + 1)

        for row, (key, value) in enumerate(params_list):
            param_item = QTableWidgetItem(str(key))
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, param_item)

            value_item = QTableWidgetItem(self._format_value_for_display(value))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, value_item)

        detail_row = len(params_list)
        param_item = QTableWidgetItem("Per-Spectrum Detail")
        param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 0, param_item)

        value_item = QTableWidgetItem("Click to view flagged/replaced points per spectrum")
        value_item.setForeground(QBrush(QColor(0, 0, 255)))
        value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 1, value_item)

    def setup_normalization_parameters(self):
        """Set up parameters table for Normalization — global settings
        (mode, regions, target scaling, etc.) shown directly, per-spectrum
        detail (the specific factor/region actually used for THIS
        spectrum) behind a clickable row — suppressed if Mode/X Ranges/
        Factor/Reference Index turn out identical for every spectrum
        (confirmed real complaint for the same pattern elsewhere: a
        detail popup that only repeats what's already shown above it)."""
        self._setup_standard_parameters_with_detail_row(
            "Per-Spectrum Detail", "Click to view the factor/settings used per spectrum",
            operation_tag='Normalization',
            entry_keys=['mode', 'x_ranges', 'factor', 'reference_spectrum_index'])

    def setup_svd_background_parameters(self):
        """Set up parameters table for SVD Background.

        Confirmed real complaints, addressed here:
        - 'correction_mode' (all_subspectra / selected / first_n) is just
          which GUI shortcut button was used to build the selection —
          not mutually exclusive in any meaningful sense (e.g. "First N"
          can produce exactly the same selection "Only corrected" would
          have), and tells you nothing 'selected_subspectra' itself
          doesn't already say more precisely. Dropped entirely.
        - 'inverted_subspectra' isn't a correction at all — SVD is only
          unique up to sign, so using a subspectrum as-is or sign-flipped
          are equally valid choices with no meaningful "which is
          correct". Dropped entirely.
        - 'selected_subspectra' (which components) and
          'baseline_corrections' (which of those got a baseline fit, and
          how) are two views of the SAME underlying thing — which
          subspectrum, corrected how — and were previously shown as two
          separate, hard-to-cross-reference blobs (a bare list of
          indices, and a separate text dump). Combined into ONE table,
          1-indexed for display (was 0-indexed, i.e. Python-internal
          numbering with no meaning to the user), one row per selected
          subspectrum, showing directly whether THAT one has a baseline
          correction and what it is — this was also silently broken
          before this fix: the humanizer checked settings key
          'selected_spectra', but the real key is 'selected_subspectra',
          so it never matched and the raw list was always shown as-is
          regardless of the earlier "fix".

        This subspectra/baseline-correction detail is a completely
        different thing from 'Per-Spectrum Detail' below it — SVD
        settings describe how the correction was BUILT (from how many
        components, with which of them baseline-corrected); Per-Spectrum
        Detail describes what it did to each actual SAMPLE spectrum
        (which of those same components were used to reconstruct it, and
        the before/after change). Two separate clickable rows, kept
        clearly named as such rather than merged into one.

        Settings are shown from self.parameters as-is even in Add as New
        mode (where that's the generic register_copy_operation() dict
        instead) — same accepted tradeoff as Normalization: there's no
        real "batch-wide setting" to recover once the original operation
        record has been popped, and the per-spectrum data (the part that
        actually matters) is sourced correctly regardless, from each
        spectrum's own correction_history.
        """
        subspectra_rows = self._get_svd_subspectra_table_data(self.parameters)
        show_subspectra_row = bool(subspectra_rows)

        entry_keys = ['original_mean', 'corrected_mean',
                      'max_absolute_change', 'relative_mean_change']
        show_per_spectrum_row = self._has_varying_per_spectrum_data('SVD background', entry_keys)

        n_rows = (1 if show_subspectra_row else 0) + (1 if show_per_spectrum_row else 0)
        self.table.setRowCount(n_rows)
        row = 0

        if show_subspectra_row:
            param_item = QTableWidgetItem("Subspectra Detail")
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, param_item)
            value_item = QTableWidgetItem("Click to view which subspectra were used and baseline-corrected")
            value_item.setForeground(QBrush(QColor(0, 0, 255)))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, value_item)
            row += 1

        if show_per_spectrum_row:
            param_item = QTableWidgetItem("Per-Spectrum Detail")
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, param_item)
            value_item = QTableWidgetItem("Click to view the subspectra/change metrics used per spectrum")
            value_item.setForeground(QBrush(QColor(0, 0, 255)))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, value_item)

    @staticmethod
    def _get_svd_subspectra_table_data(parameters):
        """Build one row per selected subspectrum: 1-indexed subspectrum
        number, whether it has a baseline correction, and if so its fit
        type / polynomial order / point count. Returns [] if there's
        nothing to show (e.g. no subspectra selected at all).

        Purely a settings-level view (from self.parameters directly) —
        unlike the per-spectrum reconstruction table, there's no
        per-subspectrum correction_history to fall back on, since a
        "subspectrum" isn't a spectrum in the main list and never gets
        its own history entries.
        """
        if not isinstance(parameters, dict):
            return []

        selected = parameters.get('selected_subspectra')
        if not selected:
            return []

        corrections = parameters.get('baseline_corrections') or {}
        # Keys may arrive as int or str depending on how the settings
        # dict was serialized/round-tripped — normalize once.
        corrections_by_idx = {}
        for k, v in corrections.items():
            try:
                corrections_by_idx[int(k)] = v or {}
            except (TypeError, ValueError):
                continue

        rows = []
        for idx in sorted(selected):
            info = corrections_by_idx.get(idx)
            if info:
                fit_type = info.get('fit_type', info.get('type', '?'))
                order = info.get('poly_order', info.get('order'))
                points = info.get('points') or []
                n_points = len(points) if hasattr(points, '__len__') else None
                rows.append({
                    'subs_num': idx + 1,
                    'baseline_corr': True,
                    'fit_type': fit_type,
                    'order': order if fit_type == 'poly' or fit_type == 'polynomial' else None,
                    'n_points': n_points,
                })
            else:
                rows.append({
                    'subs_num': idx + 1,
                    'baseline_corr': False,
                    'fit_type': None,
                    'order': None,
                    'n_points': None,
                })
        return rows

    def show_svd_subspectra_details_dialog(self):
        """Show the per-subspectrum table: which components were
        selected, and which of those have a baseline correction, with
        its fit type / order / point count — see
        _get_svd_subspectra_table_data for the full reasoning."""
        rows = self._get_svd_subspectra_table_data(self.parameters)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Subspectra Detail for Operation #{self.operation_index + 1}")
        dialog.resize(520, 420)
        layout = QVBoxLayout(dialog)

        title_label = QLabel("Subspectra used, and their baseline corrections")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        columns = ['Subs #', 'Baseline-Corr', 'Fit', 'Order', '#N']
        table = QTableWidget()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(columns)):
            table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)

        table.setRowCount(len(rows))
        for r, entry in enumerate(rows):
            subs_item = QTableWidgetItem()
            subs_item.setData(Qt.DisplayRole, entry['subs_num'])
            subs_item.setFlags(subs_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 0, subs_item)

            # 'o' / 'x' text, matching the convention requested, plus a
            # colored background as a secondary, at-a-glance cue —
            # neither depends on the other for someone who can't
            # distinguish the colors, or who copies the table as text.
            corr_item = QTableWidgetItem('o' if entry['baseline_corr'] else 'x')
            corr_item.setFlags(corr_item.flags() & ~Qt.ItemIsEditable)
            corr_item.setTextAlignment(Qt.AlignCenter)
            if entry['baseline_corr']:
                corr_item.setBackground(QBrush(QColor(210, 230, 255)))
            else:
                corr_item.setBackground(QBrush(QColor(255, 220, 220)))
            table.setItem(r, 1, corr_item)

            fit_text = entry['fit_type'] if entry['baseline_corr'] else 'x'
            fit_item = QTableWidgetItem(str(fit_text))
            fit_item.setFlags(fit_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 2, fit_item)

            order_text = entry['order'] if entry['order'] is not None else 'x'
            order_item = QTableWidgetItem(str(order_text))
            order_item.setFlags(order_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 3, order_item)

            n_text = entry['n_points'] if entry['n_points'] is not None else 'x'
            n_item = QTableWidgetItem(str(n_text))
            n_item.setFlags(n_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 4, n_item)

        layout.addWidget(table)

        button_row = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setToolTip("Copy the table above as tab-separated text")
        copy_btn.clicked.connect(lambda: self._copy_table_to_clipboard(table))
        button_row.addWidget(copy_btn)
        button_row.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        button_row.addWidget(button_box)
        layout.addLayout(button_row)

        dialog.exec_()

    @staticmethod
    def _humanize_svd_background_params(parameters):
        """Translate SVD Background's raw settings dict into a display-
        only, human-readable version — does not touch the original
        dict, which the Add as New / re-apply machinery may still need
        verbatim.

        - 'selected_spectra': a bare list of subspectrum INDICES (not
          spectrum labels — these are components of the SVD
          decomposition) shown one per table row before; now a single
          compact summary line.
        - 'baseline_corrections': previously dumped every single (x, y)
          coordinate pair for every corrected subspectrum verbatim —
          genuinely unreadable at any real point count. Now one line per
          corrected subspectrum: index, fit type, order, point COUNT
          (not the coordinates themselves — nobody reads raw baseline
          anchor coordinates from a settings table; the actual shape is
          visible in the plot when the correction was made).
        - 'inverted_subspectra': dropped entirely when empty (a
          '(none)' row added nothing) — shown as a compact index list
          when there actually are some.

        NOTE: no longer called by setup_svd_background_parameters —
        correction_mode/selected_subspectra/baseline_corrections/
        inverted_subspectra are no longer shown as flat key-value rows
        at all (see that method's docstring for the redesign). Left in
        place only in case anything else still references it; safe to
        remove outright if nothing does.
        """
        if not isinstance(parameters, dict):
            return parameters

        display = dict(parameters)

        if 'selected_spectra' in display:
            indices = display['selected_spectra']
            if isinstance(indices, (list, tuple)) and indices:
                idx_sorted = sorted(indices)
                contiguous = idx_sorted == list(range(idx_sorted[0], idx_sorted[-1] + 1))
                display['selected_spectra'] = (
                    f"{len(idx_sorted)} subspectra (indices {idx_sorted[0]}\u2013{idx_sorted[-1]})"
                    if contiguous else
                    f"{len(idx_sorted)} subspectra: {', '.join(str(i) for i in idx_sorted)}"
                )
            elif not indices:
                display['selected_spectra'] = "(none)"

        if 'baseline_corrections' in display:
            corrections = display['baseline_corrections']
            if isinstance(corrections, dict) and corrections:
                lines = []
                for idx in sorted(corrections.keys()):
                    info = corrections[idx] or {}
                    fit_type = info.get('fit_type', info.get('type', '?'))
                    order = info.get('poly_order', info.get('order'))
                    points = info.get('points') or []
                    n_points = len(points) if hasattr(points, '__len__') else '?'
                    order_text = f", order {order}" if order is not None else ""
                    lines.append(f"#{idx}: {fit_type}{order_text}, {n_points} points")
                display['baseline_corrections'] = "\n".join(lines)
            else:
                display['baseline_corrections'] = "(none)"

        if 'inverted_subspectra' in display:
            inverted = display['inverted_subspectra']
            if not inverted:
                del display['inverted_subspectra']
            elif isinstance(inverted, (list, tuple)):
                display['inverted_subspectra'] = ', '.join(str(i) for i in sorted(inverted))

        return display

    def _get_svd_background_per_spectrum_data(self):
        """Build a {label: {'subspectra_used_for_reconstruction':..., ...}}
        dict, one entry per spectrum, read from each spectrum's own
        correction_history rather than self.parameters — correct in both
        Apply and Add as New modes, same approach as
        _get_sg_per_spectrum_data (see that method's docstring for why
        this doesn't need to special-case Apply mode: with no remapping
        needed there, the source-to-copy dict is simply empty and label
        lookup falls back to itself).

        Matched exactly against 'SVD background' — the operation type
        string used for dialog dispatch (deliberately kept identical;
        this used to differ in case, a latent footgun since unified).
        """
        data = {}
        if not (self.operations_manager and self.operation_index >= 0):
            return data

        operation = self.operations_manager.get_operation_at_index(self.operation_index)
        if not operation:
            return data

        affected_labels = operation.get('affected_labels') or []
        params = operation.get('parameters') or {}
        src_labels = params.get('source_labels') or affected_labels
        copy_labels = params.get('copy_labels')
        source_to_copy_label = (
            dict(zip(src_labels, copy_labels))
            if copy_labels and len(src_labels) == len(copy_labels) else {}
        )

        label_to_spectrum = {s['label']: s for s in operation.get('output_spectra', [])}

        entry_fields = (
            'subspectra_used_for_reconstruction', 'total_subspectra_available',
            'baseline_corrected_subspectra', 'original_mean', 'corrected_mean',
            'max_absolute_change', 'relative_mean_change',
        )
        for label in src_labels:
            lookup_label = source_to_copy_label.get(label, label)
            spectrum = label_to_spectrum.get(lookup_label)
            history = ((spectrum or {}).get('metadata') or {}).get('correction_history', [])
            entry = next((e for e in reversed(history) if e.get('operation') == 'SVD background'), None)
            if entry:
                data[label] = {k: v for k, v in entry.items() if k in entry_fields}

        return data

    def show_svd_background_details_dialog(self):
        """Show per-spectrum SVD Background detail — delegates to the
        shared smart renderer (show_per_spectrum_details_dialog).

        Only the genuinely per-SAMPLE-spectrum metrics (before/after
        change) are shown here. 'Subspectra Used', 'Total Available',
        and 'Baseline-Corrected Subspectra' used to be included too —
        confirmed by direct observation (not just theory) to be
        IDENTICAL for every spectrum in a batch, every time: SVD
        reconstruction applies the same selected/corrected subspectra to
        every sample spectrum, so there's nothing sample-specific about
        which components were used. That made this dialog show a long
        "Same for all N spectra" wall of raw subspectrum-index lists
        before the actual per-spectrum table even started — and it
        duplicated exactly what the separate 'Subspectra Detail' row (see
        setup_svd_background_parameters) already shows properly, as a
        real table. Dropped here entirely rather than just moved to a
        'same for all' summary line, since Subspectra Detail already
        covers it."""
        self.show_per_spectrum_details_dialog(
            'SVD background', 'Reconstruction / change metrics by spectrum',
            ['Spectrum', 'Original Mean', 'Corrected Mean', 'Max Abs Change', 'Relative Mean Change'],
            ['original_mean', 'corrected_mean', 'max_absolute_change', 'relative_mean_change'],
        )

    def _get_created_results_data(self, operation_tag):
        """Return a list of {'label':..., <entry fields>} dicts, one per
        RESULT spectrum this operation created — used for Combine Spectra
        and Spectral Calculator, which are fundamentally many-to-one /
        many-to-many (multiple SOURCE spectra combine into one or more
        NEW result spectra), unlike every other operation in this file
        which is one-to-one (each input spectrum becomes one output).

        Because of that shape, the usual source-label -> copy-label zip
        remapping used elsewhere doesn't apply here: 'source_labels' in
        the generic register_copy_operation() record has one entry per
        SOURCE (possibly many), while 'copy_labels' has one entry per
        RESULT (possibly a different count) — zip() would silently pair
        the wrong things up, or (for Combine Spectra's usual N sources ->
        1 result case) produce nothing at all once N != 1.

        Instead, this searches output_spectra for whichever spectra carry
        a correction_history entry tagged operation_tag whose own
        'source_spectra' list is a SUBSET of this operation's
        affected_labels (the actual sources selected/processed) —
        correct regardless of mode, since affected_labels is the SOURCE
        list in both Apply and Add as New modes here (apply_operation's
        third argument is spectra_to_process, the sources, in both
        commit_spectral_arithmetic and commit_spectral_calculator;
        register_copy_operation's 'affected_labels' is built from that
        same copied_spectra list).

        Subset, not exact equality: confirmed bug — Spectral Calculator's
        'source_spectra' is only the labels the FORMULA actually
        references (spectral_calculator_manager.py's evaluate() builds
        this from which labels literally appear in the formula text),
        which is very often a real subset of everything selected (e.g.
        5 spectra selected, formula only uses 2 of them) — normal usage,
        not an edge case. Exact-equality here meant the Result Spectra
        table came back completely empty whenever a formula didn't use
        every single selected spectrum. Combine Spectra's 'source_spectra'
        always uses every source (average/sum can't do otherwise), so
        subset and exact-equality agree there — this fix only changes
        behavior for the case that was actually broken.
        """
        results = []
        if not (self.operations_manager and self.operation_index >= 0):
            return results

        try:
            operation = self.operations_manager.get_operation_at_index(self.operation_index)
        except (IndexError, KeyError):
            return results
        if not operation:
            return results

        source_labels = set(operation.get('affected_labels') or [])
        if not source_labels:
            return results

        for spectrum in operation.get('output_spectra', []):
            history = ((spectrum.get('metadata') or {}).get('correction_history') or [])
            entry = next(
                (e for e in reversed(history)
                 if e.get('operation') == operation_tag
                 and e.get('source_spectra')
                 and set(e.get('source_spectra', [])).issubset(source_labels)),
                None
            )
            if entry:
                result_entry = {'label': spectrum['label']}
                result_entry.update({k: v for k, v in entry.items() if k not in ('operation', 'timestamp')})
                results.append(result_entry)

        return results

    def show_created_results_dialog(self, operation_tag, dialog_title, columns, entry_keys):
        """Show the RESULT spectra this operation created (see
        _get_created_results_data for why this differs from every other
        operation's per-INPUT-spectrum detail table). Shared by Combine
        Spectra and Spectral Calculator.

        Same smart constant/varying split as show_per_spectrum_details_
        dialog — confirmed real complaint for Spectral Calculator
        specifically: a formula producing several outputs (e.g.
        '[expr1, expr2, expr3]') writes the SAME formula, source
        spectra, source count, and output count into every single
        output's correction_history entry — repeating that same long
        formula text in every table row added nothing beyond showing it
        once. Only 'Output Index' (and the result's own label) actually
        differs row to row for a single Calculator run, so that's the
        only thing that stays in the table; everything else becomes a
        one-time summary above it, the same as every other operation's
        detail dialog now does.
        """
        results_data = self._get_created_results_data(operation_tag)
        results_by_label = {entry.get('label', f'#{i}'): entry for i, entry in enumerate(results_data)}
        constant_fields, varying_keys = self._split_constant_and_varying_fields(
            results_by_label, entry_keys)
        key_to_label = dict(zip(entry_keys, columns[1:]))

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{dialog_title} for Operation #{self.operation_index + 1}")

        layout = QVBoxLayout(dialog)

        title_label = QLabel(dialog_title)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        if constant_fields:
            n = len(results_data)
            same_label = QLabel(f"Same for all {n} result spectra:" if n != 1
                                 else "Same for the result spectrum:")
            same_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
            layout.addWidget(same_label)

            settings_text = "\n".join(
                f"{key_to_label.get(k, k)}: {self._format_value_for_display(v)}"
                for k, v in constant_fields.items()
            )
            settings_value = QLabel(settings_text)
            settings_value.setWordWrap(True)
            settings_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            settings_value.setStyleSheet("padding: 4px 0 8px 8px;")
            layout.addWidget(settings_value)

        table = None
        if varying_keys:
            varying_label = QLabel(
                "Varies by result spectrum:" if constant_fields else "Result spectra:"
            )
            varying_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
            layout.addWidget(varying_label)

            table_columns = [columns[0]] + [key_to_label.get(k, k) for k in varying_keys]
            table = QTableWidget()
            table.setColumnCount(len(table_columns))
            table.setHorizontalHeaderLabels(table_columns)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSortingEnabled(True)
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            for c in range(1, len(table_columns)):
                table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)

            table.setRowCount(len(results_data))
            for row, result_entry in enumerate(results_data):
                label_item = QTableWidgetItem(result_entry.get('label', ''))
                label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, 0, label_item)

                for c, key in enumerate(varying_keys, start=1):
                    text = self._format_value_for_display(result_entry[key]) if key in result_entry else ""
                    item = QTableWidgetItem(text)
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    table.setItem(row, c, item)

            layout.addWidget(table)
        elif not results_data:
            layout.addWidget(QLabel("No result spectrum information available"))
        else:
            # Every result spectrum has identical values for every field
            # (e.g. a single-output run) — list them by name so it's
            # still clear what was actually created, without a table
            # that would only ever have one meaningfully-different
            # column (the label) alongside repeated everything-else.
            names = ", ".join(e.get('label', '') for e in results_data)
            layout.addWidget(QLabel(f"Result spectrum: {names}"))

        button_row = QHBoxLayout()
        if table is not None:
            copy_btn = QPushButton("Copy to Clipboard")
            copy_btn.setToolTip("Copy the table above as tab-separated text")
            copy_btn.clicked.connect(lambda: self._copy_table_to_clipboard(table))
            button_row.addWidget(copy_btn)
        button_row.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        button_row.addWidget(button_box)
        layout.addLayout(button_row)

        dialog.resize(700, 420 if table is not None else 220)
        dialog.exec_()

    def setup_combine_spectra_parameters(self):
        """Set up parameters table for Combine Spectra (dispatch string
        renamed to match the display name — see
        _OPERATION_DISPLAY_NAME_OVERRIDES). Global settings shown directly
        (harmless as the generic copy-operation dict in Add as New mode,
        same accepted tradeoff as Normalization/SVD Background), plus
        the result spectrum's own info shown INLINE in this same table
        — unlike Spectral Calculator, Combine Spectra always produces
        exactly one result (average/sum of the sources), so a separate
        clickable popup for what would only ever be a single row added
        an extra click for no benefit. Uses the same
        _get_created_results_data lookup Spectral Calculator's popup
        uses, just rendered as extra rows here instead of a dialog."""
        params_list = list(self.parameters.items())

        result_rows = []
        results = self._get_created_results_data('Combine Spectra')
        if results:
            # Always exactly one, per the operation's own design — see
            # docstring above — but iterate defensively rather than
            # assuming index [0] in case that ever changes.
            for result_entry in results:
                result_rows.append(('Result Spectrum', result_entry.get('label', '')))
                if 'operation_type' in result_entry:
                    result_rows.append(('Combination Type', result_entry['operation_type']))
                if 'source_spectra' in result_entry:
                    result_rows.append(('Source Spectra', result_entry['source_spectra']))
                if 'source_spectra_count' in result_entry:
                    result_rows.append(('Source Count', result_entry['source_spectra_count']))
        else:
            result_rows.append(('Result Spectrum', 'No record found'))

        all_rows = params_list + result_rows
        self.table.setRowCount(len(all_rows))

        for row, (key, value) in enumerate(all_rows):
            param_item = QTableWidgetItem(str(key))
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, param_item)

            value_item = QTableWidgetItem(self._format_value_for_display(value))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, value_item)

    def setup_spectral_calculator_parameters(self):
        """Set up parameters table for Spectral Calculator — same shape
        as setup_combine_spectra_parameters (many sources -> one or
        more results), see that method's and _get_created_results_data's
        docstrings."""
        params_list = list(self.parameters.items())
        self.table.setRowCount(len(params_list) + 1)

        for row, (key, value) in enumerate(params_list):
            param_item = QTableWidgetItem(str(key))
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, param_item)

            value_item = QTableWidgetItem(self._format_value_for_display(value))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, value_item)

        detail_row = len(params_list)
        param_item = QTableWidgetItem("Result Spectra")
        param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 0, param_item)

        value_item = QTableWidgetItem("Click to view the result spectra, formula, and sources")
        value_item.setForeground(QBrush(QColor(0, 0, 255)))
        value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 1, value_item)

    def setup_nmf_parameters(self):
        """Set up parameters table for NMF. Always reaches this dialog
        via register_copy_operation() (NMFController.export_components_
        to_main_list has no separate non-'add as new' path at all — every
        export is a copy-style operation), so self.parameters is always
        the generic copied_count/source_labels/copy_labels dict — shown
        as-is, same accepted tradeoff as every other operation here.
        Same many-sources-to-multiple-results shape as Combine Spectra /
        Spectral Calculator (the resolved components ARE the results),
        so reuses that same 'Result Spectra' pattern rather than a
        per-input-spectrum table — see _get_created_results_data's
        docstring."""
        params_list = list(self.parameters.items())
        self.table.setRowCount(len(params_list) + 1)

        for row, (key, value) in enumerate(params_list):
            param_item = QTableWidgetItem(str(key))
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, param_item)

            value_item = QTableWidgetItem(self._format_value_for_display(value))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, value_item)

        detail_row = len(params_list)
        param_item = QTableWidgetItem("Result Spectra")
        param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 0, param_item)

        value_item = QTableWidgetItem("Click to view the resolved components and fit quality")
        value_item.setForeground(QBrush(QColor(0, 0, 255)))
        value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 1, value_item)

    def setup_mcr_als_parameters(self):
        """Set up parameters table for MCR-ALS — same shape and same
        reasoning as setup_nmf_parameters."""
        params_list = list(self.parameters.items())
        self.table.setRowCount(len(params_list) + 1)

        for row, (key, value) in enumerate(params_list):
            param_item = QTableWidgetItem(str(key))
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, param_item)

            value_item = QTableWidgetItem(self._format_value_for_display(value))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, value_item)

        detail_row = len(params_list)
        param_item = QTableWidgetItem("Result Spectra")
        param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 0, param_item)

        value_item = QTableWidgetItem("Click to view the resolved components and fit quality")
        value_item.setForeground(QBrush(QColor(0, 0, 255)))
        value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 1, value_item)

    def _get_per_spectrum_data(self, operation_tag, entry_keys=None):
        """Generic per-spectrum reconstruction shared by every one-to-one
        operation's Per-Spectrum Detail feature (Automated Baseline, SNIP
        Baseline, Resolution Enhancement, Data Range, FFT Denoising,
        X-axis Alignment, Interactive Subtraction, Spike Removal) — the
        same output_spectra + source-to-copy label remapping approach as
        _get_svd_background_per_spectrum_data / _get_sg_per_spectrum_data
        (see those docstrings for why this is correct, unmodified, in
        both Apply and Add as New modes).
        """
        data = {}
        if not (self.operations_manager and self.operation_index >= 0):
            return data

        try:
            operation = self.operations_manager.get_operation_at_index(self.operation_index)
        except (IndexError, KeyError):
            return data
        if not operation:
            return data

        affected_labels = operation.get('affected_labels') or []
        params = operation.get('parameters') or {}
        src_labels = params.get('source_labels') or affected_labels
        copy_labels = params.get('copy_labels')
        source_to_copy_label = (
            dict(zip(src_labels, copy_labels))
            if copy_labels and len(src_labels) == len(copy_labels) else {}
        )

        label_to_spectrum = {s['label']: s for s in operation.get('output_spectra', [])}

        for label in src_labels:
            lookup_label = source_to_copy_label.get(label, label)
            spectrum = label_to_spectrum.get(lookup_label)
            history = ((spectrum or {}).get('metadata') or {}).get('correction_history', [])
            entry = next((e for e in reversed(history) if e.get('operation') == operation_tag), None)
            if entry:
                if entry_keys:
                    data[label] = {k: v for k, v in entry.items() if k in entry_keys}
                else:
                    data[label] = {k: v for k, v in entry.items() if k not in ('operation', 'timestamp')}

        return data

    def _split_constant_and_varying_fields(self, per_spectrum_data, entry_keys):
        """Given {label: {field: value, ...}} (from _get_per_spectrum_data)
        and the full candidate field list, split into:
          - constant_fields: {field: value} for every field whose value
            is IDENTICAL across every spectrum that has a record at all
            (spectra with no record don't count against this — only
            compared among spectra that DO have data).
          - varying_keys: fields (in entry_keys order) where at least
            two spectra disagree, or one has the field and another
            doesn't.
        A field only one spectrum has data for is trivially constant —
        nothing to differ against.
        """
        constant_fields = {}
        varying_keys = []
        for key in entry_keys:
            values = []
            any_missing = False
            for entry in per_spectrum_data.values():
                if not entry:
                    continue
                if key in entry:
                    values.append(entry[key])
                else:
                    any_missing = True
            if not values:
                continue
            first = values[0]
            if not any_missing and all(v == first for v in values[1:]):
                constant_fields[key] = first
            else:
                varying_keys.append(key)
        return constant_fields, varying_keys

    def show_per_spectrum_details_dialog(self, operation_tag, dialog_title, columns, entry_keys):
        """Per-spectrum detail dialog for operations whose settings are
        often (sometimes always) identical across every affected
        spectrum — SNIP Baseline, SG-Smoothing, Normalization, FFT
        Denoising, Automated Baseline, Data Range, Resolution
        Enhancement, X-axis Alignment, Interactive Subtraction all use
        this. Confirmed real complaint: showing a full table with
        several columns holding the exact same value in every single
        row added nothing beyond what the settings already said once —
        genuinely redundant, not just cosmetically so, for any
        operation whose settings don't actually vary per spectrum
        (SNIP Baseline / SG-Smoothing in particular: their settings are
        frequently IDENTICAL for every spectrum in a batch, since
        there's usually no per-spectrum reason for them to differ).

        Fields that are the same for every spectrum are shown ONCE, as
        plain settings text, instead of being repeated in every table
        row. Only fields that actually DIFFER between at least two
        spectra become table columns — for an operation like SNIP
        Baseline where NOTHING varies, this means no table at all, just
        the settings. 'Spectrum' itself is always shown (in the
        settings text, as a spectrum count, when there's no table) so
        it's still clear what this actually applied to.

        columns[0] is always the 'Spectrum' column header (kept for
        call-site compatibility with the previous fixed-table version —
        every existing show_<x>_details_dialog call already provides
        this); columns[1:] / entry_keys are candidate per-spectrum
        fields, split into constant vs. varying here.
        """
        per_spectrum_data = self._get_per_spectrum_data(operation_tag, entry_keys)
        key_to_label = dict(zip(entry_keys, columns[1:]))
        constant_fields, varying_keys = self._split_constant_and_varying_fields(
            per_spectrum_data, entry_keys)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{dialog_title} for Operation #{self.operation_index + 1}")

        layout = QVBoxLayout(dialog)

        title_label = QLabel(dialog_title)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        n_spectra = len([1 for entry in per_spectrum_data.values() if entry])
        n_total = len(per_spectrum_data)

        if constant_fields:
            same_label = QLabel(
                f"Same for all {n_spectra} spectrum{'s' if n_spectra != 1 else ''}:"
                if n_spectra == n_total else
                f"Same for the {n_spectra} of {n_total} spectra with a record:"
            )
            same_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
            layout.addWidget(same_label)

            settings_text = "\n".join(
                f"{key_to_label.get(k, k)}: {self._format_value_for_display(v)}"
                for k, v in constant_fields.items()
            )
            settings_value = QLabel(settings_text)
            settings_value.setWordWrap(True)
            settings_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            settings_value.setStyleSheet("padding: 4px 0 8px 8px;")
            layout.addWidget(settings_value)

        table = None
        if varying_keys:
            varying_label = QLabel(
                "Varies by spectrum:" if constant_fields else "Settings by spectrum:"
            )
            varying_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
            layout.addWidget(varying_label)

            table_columns = [columns[0]] + [key_to_label.get(k, k) for k in varying_keys]
            table = QTableWidget()
            table.setColumnCount(len(table_columns))
            table.setHorizontalHeaderLabels(table_columns)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSortingEnabled(True)
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            for c in range(1, len(table_columns)):
                table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)

            sorted_labels = sorted(per_spectrum_data.keys())
            table.setRowCount(len(sorted_labels))
            for row, label in enumerate(sorted_labels):
                entry = per_spectrum_data.get(label) or {}

                label_item = QTableWidgetItem(label)
                label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, 0, label_item)

                if not entry:
                    no_record_item = QTableWidgetItem("No record found")
                    no_record_item.setFlags(no_record_item.flags() & ~Qt.ItemIsEditable)
                    no_record_item.setForeground(QBrush(QColor(150, 150, 150)))
                    table.setItem(row, 1, no_record_item)
                    for c in range(2, len(table_columns)):
                        blank_item = QTableWidgetItem("")
                        blank_item.setFlags(blank_item.flags() & ~Qt.ItemIsEditable)
                        table.setItem(row, c, blank_item)
                    continue

                for c, key in enumerate(varying_keys, start=1):
                    text = self._format_value_for_display(entry[key]) if key in entry else ""
                    item = QTableWidgetItem(text)
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    table.setItem(row, c, item)

            layout.addWidget(table)
        elif not constant_fields:
            layout.addWidget(QLabel("No affected spectra information available"))
        else:
            layout.addWidget(QLabel(
                "These settings are identical for every spectrum — "
                "nothing else differs per spectrum."
            ))

        button_row = QHBoxLayout()
        if table is not None:
            copy_btn = QPushButton("Copy to Clipboard")
            copy_btn.setToolTip("Copy the table above as tab-separated text")
            copy_btn.clicked.connect(lambda: self._copy_table_to_clipboard(table))
            button_row.addWidget(copy_btn)
        button_row.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        button_row.addWidget(button_box)
        layout.addLayout(button_row)

        dialog.resize(700, 420 if table is not None else 220)
        dialog.exec_()

    @staticmethod
    def _copy_table_to_clipboard(table):
        """Copy a QTableWidget's visible contents (headers + all rows,
        respecting the current sort order) as tab-separated text —
        pasteable directly into Excel/a text editor. Shared by every
        per-spectrum detail dialog's Copy to Clipboard button."""
        headers = [table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else ''
                   for c in range(table.columnCount())]
        lines = ['\t'.join(headers)]
        for row in range(table.rowCount()):
            lines.append('\t'.join(
                table.item(row, c).text() if table.item(row, c) else ''
                for c in range(table.columnCount())
            ))
        QApplication.clipboard().setText('\n'.join(lines))

    def _has_varying_per_spectrum_data(self, operation_tag, entry_keys):
        """Return True if at least one field in entry_keys genuinely
        differs across the affected spectra for this operation — used
        to decide whether a 'Per-Spectrum Detail' row is worth showing
        at all.

        When every field is identical for every spectrum, clicking
        through to the detail popup only ever repeats what's already
        shown in THIS SAME parameters table, one screen up — confirmed
        real complaint (SNIP Baseline's popup literally repeated
        n_iter/decreasing/transform/smooth_window, all already visible
        in the main table before the click). Suppressing the row
        entirely in that case avoids the redundant extra click.

        Returns True (i.e. still show the row) when per_spectrum_data
        comes back completely EMPTY, rather than False — an empty
        result usually means something's actually wrong (a data lookup
        bug), not that there's nothing to show, and hiding the row
        would silently mask that instead of leaving it visible/
        debuggable via the popup's own 'No affected spectra information
        available' message.
        """
        per_spectrum_data = self._get_per_spectrum_data(operation_tag, entry_keys)
        if not per_spectrum_data:
            return True
        _, varying_keys = self._split_constant_and_varying_fields(per_spectrum_data, entry_keys)
        return bool(varying_keys)

    def _setup_standard_parameters_with_detail_row(self, detail_row_label, detail_click_text,
                                                     params_override=None, operation_tag=None,
                                                     entry_keys=None):
        """Shared body for a standard one-to-one operation's parameters
        table: global settings shown directly (self.parameters, as-is
        even in Add as New mode — same accepted tradeoff as Normalization
        /SVD Background/SG-Smoothing), plus one clickable detail row —
        omitted entirely when operation_tag/entry_keys are given and
        _has_varying_per_spectrum_data says nothing would actually differ
        (see that method's docstring).

        params_override lets a caller substitute a display-only version
        of the settings dict (e.g. with internal UUID keys translated to
        readable spectrum labels) without altering self.parameters
        itself, which other code may still need in its original,
        machine-usable form."""
        params_list = list((params_override if params_override is not None else self.parameters).items())

        show_detail_row = True
        if operation_tag is not None and entry_keys is not None:
            show_detail_row = self._has_varying_per_spectrum_data(operation_tag, entry_keys)

        self.table.setRowCount(len(params_list) + (1 if show_detail_row else 0))

        for row, (key, value) in enumerate(params_list):
            param_item = QTableWidgetItem(str(key))
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, param_item)

            value_item = QTableWidgetItem(self._format_value_for_display(value))
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, value_item)

        if not show_detail_row:
            return

        detail_row = len(params_list)
        param_item = QTableWidgetItem(detail_row_label)
        param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 0, param_item)

        value_item = QTableWidgetItem(detail_click_text)
        value_item.setForeground(QBrush(QColor(0, 0, 255)))
        value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 1, value_item)

    def setup_automated_baseline_parameters(self):
        """Parameters table for Automated Baseline (ALS, airPLS, arPLS,
        iarPLS, asPLS, drPLS, psalsa, I-ModPoly, Morphological Opening, or
        mpls — see the 'algorithm' entry; 'p' applies to ALS, psalsa and
        mpls (a different quantity in each case — see
        calculate_mpls_baseline for mpls's own meaning), 'eta' only to
        drPLS, 'poly_order' only to I-ModPoly, and Morphological Opening
        has neither (it's fully parameter-free) — each blank on any row
        it doesn't apply to, same as any other key missing from a given
        entry)."""
        self._setup_standard_parameters_with_detail_row(
            "Per-Spectrum Detail", "Click to view the baseline result used per spectrum",
            operation_tag='Automated Baseline',
            entry_keys=['success', 'algorithm', 'lambda', 'p', 'eta', 'poly_order',
                        'iterations', 'fitting_ranges', 'inverted_regions'])

    def show_automated_baseline_details_dialog(self):
        self.show_per_spectrum_details_dialog(
            'Automated Baseline', 'Baseline result by spectrum',
            ['Spectrum', 'Success', 'Algorithm', 'Lambda', 'P', 'Eta', 'Poly Order',
             'Iterations', 'Fitting Ranges', 'Inverted Regions'],
            ['success', 'algorithm', 'lambda', 'p', 'eta', 'poly_order', 'iterations',
             'fitting_ranges', 'inverted_regions'],
        )

    def setup_snip_baseline_parameters(self):
        """Parameters table for SNIP Baseline."""
        self._setup_standard_parameters_with_detail_row(
            "Per-Spectrum Detail", "Click to view the SNIP settings used per spectrum",
            operation_tag='SNIP Baseline',
            entry_keys=['skipped', 'n_iter', 'decreasing', 'smooth_window', 'transform'])

    def show_snip_baseline_details_dialog(self):
        self.show_per_spectrum_details_dialog(
            'SNIP Baseline', 'SNIP settings by spectrum',
            ['Spectrum', 'Skipped', 'Iterations', 'Decreasing', 'Smooth Window', 'Transform'],
            ['skipped', 'n_iter', 'decreasing', 'smooth_window', 'transform'],
        )

    def setup_resolution_enhancement_parameters(self):
        """Parameters table for Resolution Enhancement."""
        self._setup_standard_parameters_with_detail_row(
            "Per-Spectrum Detail", "Click to view the enhancement result used per spectrum",
            operation_tag='Resolution enhancement',
            entry_keys=['irf_sigma', 'snr', 'success'])

    def show_resolution_enhancement_details_dialog(self):
        self.show_per_spectrum_details_dialog(
            'Resolution enhancement', 'Enhancement result by spectrum',
            ['Spectrum', 'IRF Sigma', 'SNR', 'Success'],
            ['irf_sigma', 'snr', 'success'],
        )

    def setup_data_range_parameters(self):
        """Parameters table for Data Range."""
        self._setup_standard_parameters_with_detail_row(
            "Per-Spectrum Detail", "Click to view the range/settings applied per spectrum",
            operation_tag='Data range',
            entry_keys=['ranges', 'exclude_mode', 'linearization_step', 'x_min', 'x_max'])

    def show_data_range_details_dialog(self):
        self.show_per_spectrum_details_dialog(
            'Data range', 'Range/settings applied by spectrum',
            ['Spectrum', 'Ranges', 'Exclude Mode', 'Linearization Step', 'X Min', 'X Max'],
            ['ranges', 'exclude_mode', 'linearization_step', 'x_min', 'x_max'],
        )

    def setup_fft_denoising_parameters(self):
        """Parameters table for FFT Denoising."""
        self._setup_standard_parameters_with_detail_row(
            "Per-Spectrum Detail", "Click to view the filter settings used per spectrum",
            operation_tag='FFT Denoising',
            entry_keys=['stop_bands', 'low_cutoff', 'high_cutoff', 'window'])

    def show_fft_denoising_details_dialog(self):
        self.show_per_spectrum_details_dialog(
            'FFT Denoising', 'Filter settings by spectrum',
            ['Spectrum', 'Stop Bands', 'Low Cutoff', 'High Cutoff', 'Window'],
            ['stop_bands', 'low_cutoff', 'high_cutoff', 'window'],
        )

    def setup_cd_unit_conversion_parameters(self):
        """Parameters table for CD Unit Conversion. self.parameters is the
        raw settings dict the dialog produced, which includes a
        'per_spectrum' sub-dict keyed by internal spectrum unique_id —
        exactly the kind of raw, UUID-keyed blob every other per-spectrum
        operation here avoids showing directly (see
        setup_interactive_subtraction_parameters). It's dropped from the
        displayed settings entirely; the real per-row values (path
        length, concentration, molecular weight, residue/nucleotide
        count) are reconstructed from each spectrum's own
        correction_history entry instead, the same generic mechanism
        Automated Baseline/SNIP Baseline/X-axis Alignment/Interactive
        Subtraction all use — which resolves back to spectrum LABELS
        automatically, never raw unique_ids.

        Deliberately does NOT pass operation_tag/entry_keys to
        _setup_standard_parameters_with_detail_row (which would suppress
        the 'Per-Spectrum Detail' row whenever every spectrum's values
        happen to be identical). path_length_cm/concentration_value/
        molecular_weight/num_residues are genuine per-sample measurement
        INPUTS the user typed in for each spectrum — real documentation
        of what was used for that spectrum's conversion — not incidental
        settings like SNIP Baseline's n_iter. They're worth showing even
        when, by coincidence, every spectrum in a batch used the same
        path length/concentration (e.g. a single-concentration series
        varying only in path length, or vice versa). Same reasoning as
        setup_spike_removal_parameters below.

        'output_type' and 'ellipticity_convention' are also translated
        from their internal constant strings (e.g. 'delta_a',
        'mean_residue') to the same human-readable text shown elsewhere
        in this operation's own UI/success messages, rather than leaving
        the raw enum value for the user to decode."""
        from src.modules.data_analysis.cd_unit_conversion_manager import CDUnitConversionManager as _CDMgr

        display_params = {k: v for k, v in self.parameters.items() if k != 'per_spectrum'}
        if 'output_type' in display_params:
            name, unit = _CDMgr.OUTPUT_LABELS.get(
                display_params['output_type'], (display_params['output_type'], '')
            )
            display_params['output_type'] = f"{name} [{unit}]" if unit else name
        if 'ellipticity_convention' in display_params:
            display_params['ellipticity_convention'] = {
                _CDMgr.CONVENTION_MOLECULAR: 'Molecular (whole molecule)',
                _CDMgr.CONVENTION_MEAN_RESIDUE: 'Mean-residue / mean-nucleotide',
            }.get(display_params['ellipticity_convention'], display_params['ellipticity_convention'])

        self._setup_standard_parameters_with_detail_row(
            "Per-Spectrum Detail",
            "Click to view the concentration/path length/residues used per spectrum",
            params_override=display_params)

    def show_cd_unit_conversion_details_dialog(self):
        # Concentration's unit isn't fixed (M / mM / µM / mg/mL, chosen
        # once for the whole batch — see cd_unit_conversion_dialog.py) so
        # the column header shows whichever unit was actually used,
        # instead of a bare "Concentration" that leaves the reader to
        # guess. Molecular weight's unit (g/mol) is always the same, so
        # it's just spelled out directly, matching the dialog's own table
        # header ("Molecular weight (g/mol)").
        unit = (self.parameters or {}).get('concentration_unit', '')
        concentration_label = f'Concentration ({unit})' if unit else 'Concentration'
        self.show_per_spectrum_details_dialog(
            'CD Unit Conversion', 'Sample parameters by spectrum',
            ['Spectrum', 'Path Length (cm)', concentration_label, 'Molecular Weight (g/mol)',
             'Number of Residues'],
            ['path_length_cm', 'concentration_value', 'molecular_weight', 'num_residues'],
        )

    def setup_xaxis_alignment_parameters(self):
        """Parameters table for X-axis Alignment."""
        self._setup_standard_parameters_with_detail_row(
            "Per-Spectrum Detail", "Click to view the shift applied per spectrum",
            operation_tag='X-axis alignment',
            entry_keys=['is_reference', 'shift', 'reference_label', 'interpolation_method'])

    def show_xaxis_alignment_details_dialog(self):
        self.show_per_spectrum_details_dialog(
            'X-axis alignment', 'Shift applied by spectrum',
            ['Spectrum', 'Is Reference', 'Shift', 'Reference Label', 'Interpolation Method'],
            ['is_reference', 'shift', 'reference_label', 'interpolation_method'],
        )

    def _humanize_stored_factors(self, stored_factors):
        """Translate stored_factors' internal (minuend_unique_id,
        subtrahend_unique_id) tuple keys into readable
        'minuend_label -> subtrahend_label' strings for display.

        The raw keys are UUIDs (InteractiveSubtractionManager._key_for)
        — necessary internally so a rename between selecting and
        committing can't disconnect a spectrum from its own factor, but
        meaningless shown as-is to a user (confirmed: this is genuinely
        confusing in practice, not just theoretically). Resolved via this
        operation's own output_spectra, the same source every other
        per-spectrum lookup in this file already uses — not a new lookup
        mechanism. A unique_id with no match (e.g. a file-loaded
        subtrahend never added to the main spectrum list, so it never
        appears in output_spectra) falls back to showing the raw id
        rather than silently dropping the entry.
        """
        id_to_label = {}
        if self.operations_manager and self.operation_index >= 0:
            operation = self.operations_manager.get_operation_at_index(self.operation_index)
            if operation:
                for s in operation.get('output_spectra', []):
                    uid = (s.get('metadata') or {}).get('unique_id')
                    if uid:
                        id_to_label[uid] = s['label']

        readable = {}
        for key, factor in stored_factors.items():
            if isinstance(key, tuple) and len(key) == 2:
                minuend_label = id_to_label.get(key[0], key[0])
                subtrahend_label = id_to_label.get(key[1], key[1])
                readable[f"{minuend_label} \u2192 {subtrahend_label}"] = factor
            else:
                readable[str(key)] = factor
        return readable

    def setup_interactive_subtraction_parameters(self):
        """Parameters table for Interactive Subtraction. stored_factors'
        UUID keys are translated to readable spectrum labels before
        display — see _humanize_stored_factors."""
        display_params = dict(self.parameters)
        if isinstance(display_params.get('stored_factors'), dict):
            display_params['stored_factors'] = self._humanize_stored_factors(display_params['stored_factors'])
        self._setup_standard_parameters_with_detail_row(
            "Per-Spectrum Detail", "Click to view the subtraction factor used per spectrum",
            params_override=display_params,
            operation_tag='Interactive subtraction',
            entry_keys=['subtrahend_label', 'subtraction_factor', 'subtracted'])

    def show_interactive_subtraction_details_dialog(self):
        self.show_per_spectrum_details_dialog(
            'Interactive subtraction', 'Subtraction factor by spectrum',
            ['Spectrum', 'Subtrahend Label', 'Subtraction Factor', 'Subtracted'],
            ['subtrahend_label', 'subtraction_factor', 'subtracted'],
        )

    def setup_spike_removal_parameters(self):
        """Parameters table for Spike Removal — variable-length list of
        removed indices per spectrum (like Manual Baseline's points, not
        a short fixed set of scalars), so uses 'Per-Spectrum Detail' with
        a master-detail dialog (show_spike_removal_details_dialog) rather
        than the single-table pattern used by every other standard
        operation here. Doesn't pass operation_tag/entry_keys to suppress
        the row the way the others do — even when every spectrum has the
        SAME spike COUNT, the actual flagged INDICES are real per-
        spectrum information not shown anywhere else, unlike the other
        operations here where 'identical settings' really does mean
        'nothing left to show'.

        self.parameters here is the raw settings dict built by
        SpikeRemovalInteractiveDialog.get_settings() — it carries
        'effective_spikes' (every spectrum's full removed-index list) and
        'half_window_map' (every spectrum's per-spectrum half-window)
        alongside the two actual global settings ('threshold',
        'half_window'). Showing that dict as-is (the old behavior) dumped
        those two per-spectrum maps as raw table rows — exactly the
        unreadable index-list/half_window_map table the user reported.
        params_override strips it down to the two global settings plus a
        one-line summary; the real per-spectrum data is what the detail
        row below already exists to show."""
        effective_spikes = self.parameters.get('effective_spikes', {})
        total_spikes = sum(len(v) for v in effective_spikes.values())
        n_affected = sum(1 for v in effective_spikes.values() if v)
        half_window_map = self.parameters.get('half_window_map', {})
        distinct_hw = set(half_window_map.values())
        half_window_display = (
            next(iter(distinct_hw)) if len(distinct_hw) <= 1
            else f"{self.parameters.get('half_window')} (varies by spectrum — see detail below)"
        )
        display_params = {
            'threshold': self.parameters.get('threshold'),
            'half_window': half_window_display,
            'spikes_removed': total_spikes,
            'spectra_affected': n_affected,
        }
        self._setup_standard_parameters_with_detail_row(
            "Per-Spectrum Detail", "Click to view the spikes removed per spectrum",
            params_override=display_params)

    def show_spike_removal_details_dialog(self):
        """Master-detail table: summary (spike count per spectrum) plus a
        detail panel showing the specific removed indices for whichever
        spectrum is selected — same pattern as show_cosmic_ray_details_dialog
        (that method's docstring covers the output_spectra + label
        remapping reasoning shared here)."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Spike Removal Detail for Operation #{self.operation_index + 1}")
        dialog.resize(650, 500)

        layout = QVBoxLayout(dialog)

        title_label = QLabel("Spikes removed by spectrum")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        per_spectrum_data = self._get_per_spectrum_data('Spike removal')

        columns = ['Spectrum', 'Spike Count']
        summary_table = QTableWidget()
        summary_table.setColumnCount(len(columns))
        summary_table.setHorizontalHeaderLabels(columns)
        summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        summary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        summary_table.setSortingEnabled(True)
        summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        summary_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        sorted_labels = sorted(per_spectrum_data.keys())
        summary_table.setRowCount(len(sorted_labels))
        for row, label in enumerate(sorted_labels):
            entry = per_spectrum_data.get(label) or {}
            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            summary_table.setItem(row, 0, label_item)

            count_item = QTableWidgetItem(str(entry.get('spike_count', 0)))
            count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
            summary_table.setItem(row, 1, count_item)

        layout.addWidget(summary_table, stretch=1)

        indices_label = QLabel("Removed spikes (select a spectrum above):")
        indices_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(indices_label)

        # Two columns — pixel index AND x-scale position — same pairing
        # Cosmic Ray Removal's own detail view shows for the same reason:
        # the raw index alone only makes sense if you also know the axis.
        # See SpikeRemovalController.apply_interactive_removal /
        # SpikeRemovalManager._remove_from_spectra for where
        # 'spike_x_indices' / 'spike_x_positions' are written.
        indices_table = QTableWidget()
        indices_table.setColumnCount(2)
        indices_table.setHorizontalHeaderLabels(["Pixel Index", "x position"])
        indices_table.setEditTriggers(QTableWidget.NoEditTriggers)
        indices_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        indices_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(indices_table, stretch=1)

        def _on_summary_row_selected():
            rows = {idx.row() for idx in summary_table.selectedIndexes()}
            if not rows:
                indices_table.setRowCount(0)
                return
            row = next(iter(rows))
            label_item = summary_table.item(row, 0)
            label = label_item.text() if label_item else None
            entry = per_spectrum_data.get(label) or {}
            # 'spike_indices_removed' was this entry's field name before
            # spike removal's metadata bug fix (see
            # SpikeRemovalController.apply_interactive_removal) — renamed
            # to 'spike_x_indices' (paired with the new 'spike_x_positions')
            # to match Cosmic Ray Removal's naming. Falls back to the old
            # key too so a correction_history entry recorded by an older
            # version of the app (before this fix) still displays instead
            # of silently showing nothing.
            pixel_indices = entry.get('spike_x_indices', entry.get('spike_indices_removed', []))
            x_positions = entry.get('spike_x_positions', [])
            n = max(len(pixel_indices), len(x_positions))
            indices_table.setRowCount(n)
            for i in range(n):
                idx_item = QTableWidgetItem(
                    str(pixel_indices[i]) if i < len(pixel_indices) else "")
                idx_item.setFlags(idx_item.flags() & ~Qt.ItemIsEditable)
                indices_table.setItem(i, 0, idx_item)
                x_item = QTableWidgetItem(
                    self._format_value_for_display(x_positions[i]) if i < len(x_positions) else "")
                x_item.setFlags(x_item.flags() & ~Qt.ItemIsEditable)
                indices_table.setItem(i, 1, x_item)

        summary_table.itemSelectionChanged.connect(_on_summary_row_selected)
        if summary_table.rowCount() > 0:
            summary_table.selectRow(0)
            _on_summary_row_selected()

        if summary_table.rowCount() == 0:
            layout.addWidget(QLabel("No spike removal information available"))

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.exec_()

    def _get_sg_per_spectrum_data(self):
        """Build a {label: {'window_length':..., 'polyorder':..., ...}}
        dict, one entry per spectrum actually affected by this SG-
        Smoothing operation, read from each spectrum's own
        correction_history rather than self.parameters.

        Unlike setup_baseline_parameters()'s fix, this doesn't special-
        case Apply vs Add as New — self.parameters (the settings dict)
        was always only ever a single set of global settings, never a
        reliable per-spectrum record even in Apply mode, since a
        spectrum with too few points silently gets a SMALLER window (see
        apply_sg_filter's "Using smaller window" fallback) and a custom
        delta only applies to whichever specific spectra had one. Always
        reconstructing from output_spectra + label remapping (same
        approach as show_normalization_details_dialog /
        show_cosmic_ray_details_dialog) is correct in both modes — in
        Apply mode there's simply no remapping to do (source label ==
        lookup label), which the empty/no-op dict handles for free.

        Matched exactly against 'SG-smoothing' — the operation type
        string used for dialog dispatch (deliberately kept identical;
        this used to differ in case, a latent footgun since unified).
        """
        data = {}
        if not (self.operations_manager and self.operation_index >= 0):
            return data

        operation = self.operations_manager.get_operation_at_index(self.operation_index)
        if not operation:
            return data

        affected_labels = operation.get('affected_labels') or []
        params = operation.get('parameters') or {}
        src_labels = params.get('source_labels') or affected_labels
        copy_labels = params.get('copy_labels')
        source_to_copy_label = (
            dict(zip(src_labels, copy_labels))
            if copy_labels and len(src_labels) == len(copy_labels) else {}
        )

        label_to_spectrum = {s['label']: s for s in operation.get('output_spectra', [])}

        for label in src_labels:
            lookup_label = source_to_copy_label.get(label, label)
            spectrum = label_to_spectrum.get(lookup_label)
            history = ((spectrum or {}).get('metadata') or {}).get('correction_history', [])
            entry = next((e for e in reversed(history) if e.get('operation') == 'SG-smoothing'), None)
            if entry:
                data[label] = {k: v for k, v in entry.items()
                               if k in ('window_length', 'polyorder', 'deriv_order',
                                        'delta', 'delta_source', 'mode')}

        return data

    def setup_sg_parameters(self):
        """Set up parameters table for SG-smoothing operations."""
        params_to_display = {}
        delta_values = None
        
        # Check both potential parameter names
        if 'delta_values' in self.parameters:
            delta_values = self.parameters['delta_values']
            # Make a copy without delta_values for regular display
            params_to_display = {k: v for k, v in self.parameters.items() if k != 'delta_values'}
        elif 'individual_delta_values' in self.parameters:
            delta_values = self.parameters['individual_delta_values']
            # Make a copy without individual_delta_values for regular display
            params_to_display = {k: v for k, v in self.parameters.items() if k != 'individual_delta_values'}
        else:
            params_to_display = self.parameters

        # Only add the clickable delta_values row when there's actually
        # something behind it. self.parameters is the generic copy-
        # operation dict in Add as New mode (no delta_values/
        # individual_delta_values key at all) — showing the row
        # regardless used to open onto nothing. The new Per-Spectrum
        # Detail row below covers this data correctly in every mode
        # anyway, so this row is now just a convenience when the info
        # happens to be directly available.
        if delta_values:
            params_to_display['delta_values'] = "Click to view values"
        
        # Display parameters
        params_list = list(params_to_display.items())
        self.table.setRowCount(len(params_list))
        
        for row, (key, value) in enumerate(params_list):
            # Parameter name
            param_item = QTableWidgetItem(str(key))
            param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, param_item)
            
            # Parameter value
            if key == 'delta_values':
                value_item = QTableWidgetItem("Click to view all delta values")
                value_item.setForeground(QBrush(QColor(0, 0, 255)))  # Blue text
                value_item.setData(Qt.UserRole, delta_values)
            else:
                value_item = QTableWidgetItem(self._format_value_for_display(value))
                
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, value_item)

        # Per-Spectrum Detail row — the actual window/poly/deriv/delta/mode
        # used for EACH spectrum, correctly sourced in both Apply and Add
        # as New modes (see _get_sg_per_spectrum_data), same pattern as
        # Cosmic Ray Removal / Normalization. Suppressed if nothing
        # actually varies per spectrum (confirmed real complaint: SG-
        # Smoothing's settings are frequently identical for an entire
        # batch, making the popup a pure repeat of the rows above it).
        sg_entry_keys = ['window_length', 'polyorder', 'deriv_order', 'delta', 'delta_source', 'mode']
        if not self._has_varying_per_spectrum_data('SG-smoothing', sg_entry_keys):
            self.table.resizeRowsToContents()
            return

        detail_row = len(params_list)
        self.table.setRowCount(len(params_list) + 1)
        param_item = QTableWidgetItem("Per-Spectrum Detail")
        param_item.setFlags(param_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 0, param_item)

        value_item = QTableWidgetItem("Click to view the settings used per spectrum")
        value_item.setForeground(QBrush(QColor(0, 0, 255)))
        value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(detail_row, 1, value_item)

        self.table.resizeRowsToContents()
    
    def showEvent(self, event):
        """Re-run row-height sizing once the dialog has its real layout —
        resizeRowsToContents() called during setup_ui() sees the Value
        column's pre-layout (often too-narrow) width, since that column
        is Stretch-resized and only reaches its final width once the
        dialog is actually shown."""
        super().showEvent(event)
        self.table.resizeRowsToContents()

    def _format_value_for_display(self, value):
        """Render a parameter value in a human-readable, multi-line form
        instead of Python's raw list/dict repr (e.g. "['a', 'b', 'c']"),
        so a long list of e.g. spectrum labels reads as one item per row
        instead of one hard-to-scan string that only fits by stretching
        the dialog very wide. Row height is grown to fit via
        resizeRowsToContents() (see setup_ui/showEvent), and the table
        itself scrolls, so this works for any number of items.
        """
        if isinstance(value, dict):
            if not value:
                return "(none)"
            return "\n".join(
                f"{k}: {self._format_value_for_display(v)}" for k, v in value.items()
            )

        if isinstance(value, (list, tuple, set)):
            items = list(value)
            if not items:
                return "(none)"
            if all(isinstance(item, (list, tuple)) and len(item) == 2 for item in items):
                # Likely a list of [start, end] ranges — one per line,
                # same compact "[a-b]" form used before, just no longer
                # all crammed onto a single comma-separated line.
                return "\n".join(f"[{r[0]}-{r[1]}]" for r in items)
            return "\n".join(str(item) for item in items)

        return str(value)

    def handle_cell_click(self, row, column):
        """Handle clicks on table cells."""
        if column == 1:  # Value column
            # Get the parameter name from column 0
            param_name_item = self.table.item(row, 0)
            param_name = param_name_item.text() if param_name_item else ""
            
            # Get the value item
            value_item = self.table.item(row, 1)
            if not value_item:
                return
                
            # Handle specific clickable items
            if param_name == "delta_values" and "Click to view" in value_item.text():
                self.show_delta_values_table()
            elif param_name == "Baseline Points" and "Click to view" in value_item.text():
                corrections_data = value_item.data(Qt.UserRole)
                self.show_baseline_points_dialog(corrections_data)
            elif (param_name == "Fitted Peaks" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("Peak Fitting")):
                rows = value_item.data(Qt.UserRole)
                self.show_peak_fitting_details_dialog(rows)
            elif param_name == "Spectra Created" and "Click to view" in value_item.text():
                pairs = value_item.data(Qt.UserRole)
                self.show_copy_operation_pairs_dialog(pairs)
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("Cosmic ray removal")):
                self.show_cosmic_ray_details_dialog()
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("Normalization")):
                self.show_normalization_details_dialog()
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("SG-smoothing")):
                self.show_sg_smoothing_details_dialog()
            elif (param_name == "Subspectra Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("SVD background")):
                self.show_svd_subspectra_details_dialog()
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("SVD background")):
                self.show_svd_background_details_dialog()
            elif (param_name == "Result Spectra" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("Spectral Calculator")):
                self.show_created_results_dialog(
                    'Spectral Calculator', 'Result spectra, formula, and sources',
                    ['Result Spectrum', 'Formula', 'Source Spectra', 'Source Count', 'Output Index', 'Output Count'],
                    ['formula', 'source_spectra', 'source_spectra_count', 'output_index', 'output_count'],
                )
            elif (param_name == "Result Spectra" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("NMF")):
                self.show_created_results_dialog(
                    'NMF', 'Resolved components and fit quality',
                    ['Result Spectrum', 'Component #', 'Explained Var. (%)', 'Reconstruction Error',
                     'Lack of Fit (%)', 'Iterations', 'Converged', 'References Fixed'],
                    ['component_index', 'explained_variance', 'reconstruction_error',
                     'lof', 'iterations_used', 'converged', 'references_fixed'],
                )
            elif (param_name == "Result Spectra" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("MCR-ALS")):
                self.show_created_results_dialog(
                    'MCR-ALS', 'Resolved components and fit quality',
                    ['Result Spectrum', 'Component #', 'Explained Var. (%)',
                     'Lack of Fit (%)', 'Iterations', 'Converged', 'References Fixed'],
                    ['component_index', 'explained_variance',
                     'lof', 'iterations_used', 'converged', 'references_fixed'],
                )
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("Automated Baseline")):
                self.show_automated_baseline_details_dialog()
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("SNIP Baseline")):
                self.show_snip_baseline_details_dialog()
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("Resolution enhancement")):
                self.show_resolution_enhancement_details_dialog()
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("Spike removal")):
                self.show_spike_removal_details_dialog()
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("Data range")):
                self.show_data_range_details_dialog()
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("FFT Denoising")):
                self.show_fft_denoising_details_dialog()
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("X-axis alignment")):
                self.show_xaxis_alignment_details_dialog()
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("Interactive subtraction")):
                self.show_interactive_subtraction_details_dialog()
            elif (param_name == "Per-Spectrum Detail" and "Click to view" in value_item.text()
                  and self.operation_name.startswith("CD Unit Conversion")):
                self.show_cd_unit_conversion_details_dialog()

    def use_baseline_points(self, corrections_data):
        """
        Store the baseline points for future use when opening the baseline correction dialog.

        These points were fit against the spectrum DATA as it existed
        right before this baseline operation ran — not against whatever
        state happens to be active right now. Applying them on top of,
        say, normalized or derivative data makes no sense; the points
        were never fit to those y-values. "Use These Points" only has a
        well-defined meaning as "tweak the old points instead of
        starting from scratch when redoing this same baseline
        correction" — which requires actually being back on that
        pre-operation state. So this jumps there first, via the same
        signal the History window's own "Jump to Selected State" /
        "Restore Original State" buttons use (self.parent is the
        OperationsSummaryDialog that owns operation_selected, connected
        to OperationsController.jump_to_operation_state — see
        show_operations_summary()). index - 1 is "the state right before
        this operation", which is Original State (-1) if this was the
        very first operation.

        corrections_data is keyed by spectrum_key() (unique_id) — see
        _get_baseline_corrections_data() / get_corrections_info() — so
        there is no name-matching step here at all anymore; each key IS
        already the identity BaselinePointsStorage should file the
        points under. The jump above exists purely for the semantic
        reason in the paragraph before this one (showing you the right
        DATA to redo the correction against), not to make an identity
        lookup succeed.
        """
        if self.parent is not None and hasattr(self.parent, 'operation_selected'):
            self.parent.operation_selected.emit(self.operation_index - 1)
            # The jump above changes operations_manager.active_operation_index,
            # but the History window (self.parent) built its list once at
            # __init__ and has no other reason to know it just went stale —
            # its own "Jump to Selected State" button never hits this case
            # because it closes the whole window immediately after jumping
            # (see _handle_jump's self.accept()). This dialog doesn't close
            # its parent, so it has to explicitly ask it to redraw instead,
            # or the ACTIVE badge stays on the operation you jumped FROM
            # until the window is closed and reopened.
            if hasattr(self.parent, 'load_operations'):
                self.parent.load_operations()

        try:
            # Get the singleton storage
            storage = BaselinePointsStorage.get_instance()

            # Clear existing stored points
            storage.clear()

            # Load points from corrections_data into storage
            loaded_points_count = 0

            for storage_key, correction_info in corrections_data.items():
                if isinstance(correction_info, dict):
                    # Get fit type
                    fit_type = None
                    if 'type' in correction_info:
                        fit_type = correction_info['type']
                    
                    # Get polynomial order if applicable
                    poly_order = None
                    if correction_info.get('type') == 'polynomial' and 'order' in correction_info:
                        poly_order = correction_info['order']
                    
                    # Get and store points - handle both cases where points is a list or int
                    if 'points' in correction_info:
                        points_data = correction_info['points']
                        if isinstance(points_data, list):
                            # Direct list of points
                            points = []
                            for point in points_data:
                                if isinstance(point, (list, tuple)) and len(point) >= 2:
                                    points.append((point[0], point[1]))
                                    loaded_points_count += 1
                            
                            if points:
                                storage.store_points(storage_key, points, fit_type, poly_order)
                        
                        elif isinstance(points_data, int) and hasattr(self, 'operations_manager'):
                            # Try to get actual points from the operations manager
                            try:
                                actual_points = self.operations_manager.get_baseline_points(
                                    self.operation_index, storage_key)
                                if actual_points:
                                    points = []
                                    for point in actual_points:
                                        if isinstance(point, (list, tuple)) and len(point) >= 2:
                                            points.append((point[0], point[1]))
                                            loaded_points_count += 1
                                    
                                    if points:
                                        storage.store_points(storage_key, points, fit_type, poly_order)
                            except Exception as e:
                                logger.error(f"Error getting baseline points from operations manager: {e}")
            
            # Force the has_stored_points flag to True
            storage.has_stored_points = True
            
            # Notify user that points have been stored for future use
            QMessageBox.information(
                self,
                "Baseline Points Stored",
                f"Jumped back to the state right before this baseline correction, and loaded "
                f"{loaded_points_count} baseline points for {len(corrections_data)} spectra.\n\n"
                f"These points will be available the next time you open the Baseline Correction dialog."
            )
        
        except Exception as e:
            import traceback
            logger.error(f"Error in use_baseline_points: {e}")
            logger.debug("<traceback>")
            QMessageBox.warning(self, "Error", f"Failed to load baseline points: {str(e)}")

    def export_baseline_points(self, corrections_data):
        """Export baseline points to clipboard, text file, or Excel file."""
        # Create export menu with more options
        menu = QMenu(self)
        to_clipboard = menu.addAction("Copy to Clipboard")
        to_text_file = menu.addAction("Save to Text File")
        to_excel = menu.addAction("Save to Excel File")
        
        action = menu.exec_(QCursor.pos())
        
        if action == to_clipboard:
            self._export_to_clipboard(corrections_data)
        elif action == to_text_file:
            self._export_to_text_file(corrections_data)
        elif action == to_excel:
            self._export_to_excel(corrections_data)
    
    def _export_to_clipboard(self, corrections_data):
        """Export baseline points to clipboard."""
        # Format the data
        text = self._format_baseline_data(corrections_data)
        
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        
        QMessageBox.information(self, "Export Complete", "Baseline points copied to clipboard.")
    
    def _export_to_text_file(self, corrections_data):
        """Export baseline points to a text file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Baseline Points", "", "Text Files (*.txt);;All Files (*)"
        )
        
        if not file_path:
            return
        
        # Format the data
        text = self._format_baseline_data(corrections_data)
        
        # Write to file
        try:
            with open(file_path, 'w') as f:
                f.write(text)
            QMessageBox.information(self, "Export Complete", f"Baseline points saved to {file_path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to save file: {str(e)}")

    def _export_to_excel(self, corrections_data):
        """Export baseline points to an Excel file."""
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Baseline Points", "", "Excel Files (*.xlsx);;All Files (*)"
        )
        
        if not file_path:
            return
        
        # Ensure file has .xlsx extension
        if not file_path.lower().endswith('.xlsx'):
            file_path += '.xlsx'
        
        try:
            # First, gather all data to make sure we have at least one sheet with data
            metadata = []
            points_data_by_spectrum = {}
            
            for spectrum, info in corrections_data.items():
                if isinstance(info, dict):
                    # Add to metadata. corrections_data is keyed by
                    # spectrum_key() (unique_id) — 'Spectrum' is a display
                    # column, so it shows the human-readable label instead
                    # of the raw id, while lookups below keep using
                    # `spectrum` (the id) itself.
                    row = {
                        'Spectrum': info.get('label', spectrum),
                        'Fit Type': info.get('type', 'Unknown'),
                    }
                    
                    # Add polynomial order if applicable
                    if info.get('type') == 'polynomial' and 'order' in info:
                        row['Polynomial Order'] = info['order']
                    else:
                        row['Polynomial Order'] = None
                    
                    # Try to get actual points
                    actual_points = []
                    points_count = 0
                    
                    # First check if we have points in the info dictionary
                    if 'points' in info:
                        points_data = info['points']
                        # Check if points is a list of coordinates or just a count
                        if isinstance(points_data, list):
                            actual_points = points_data
                            points_count = len(points_data)
                        elif isinstance(points_data, int):
                            points_count = points_data
                            # It's just a count, try to get actual points from operations manager
                            if self.operations_manager and hasattr(self.operations_manager, 'get_baseline_points'):
                                try:
                                    actual_points = self.operations_manager.get_baseline_points(
                                        self.operation_index, spectrum)
                                except Exception as e:
                                    logger.error(f"Error getting baseline points: {e}")
                    
                    # If still no points, check if we can get them directly from the controller.
                    # bc_controller.get_baseline_points() now expects a full
                    # spectrum dict (it resolves the spectrum's identity
                    # key internally) — but only a label string is
                    # available at this point in the export loop, so call
                    # the manager's own method directly instead, which is
                    # generic and just takes whatever key string it's given.
                    if not actual_points and self.operations_manager and hasattr(self.operations_manager, '_controller'):
                        controller = self.operations_manager._controller
                        if hasattr(controller, 'baseline_correction_controller'):
                            bc_controller = controller.baseline_correction_controller
                            if hasattr(bc_controller, 'manager'):
                                try:
                                    actual_points = bc_controller.manager.get_baseline_points(spectrum)
                                    if actual_points:
                                        points_count = len(actual_points)
                                except Exception as e:
                                    logger.error(f"Error getting baseline points from controller: {e}")
                    
                    # Add points count to metadata
                    row['Points Count'] = points_count
                    metadata.append(row)
                    
                    # If we have actual points, add to points_data_by_spectrum
                    if actual_points:
                        spectrum_points = []
                        for i, point in enumerate(actual_points):
                            if isinstance(point, (list, tuple)) and len(point) >= 2:
                                spectrum_points.append({
                                    'Point': i+1,
                                    'X': point[0],
                                    'Y': point[1]
                                })
                        
                        if spectrum_points:
                            # Keyed by the display label here (only used
                            # below for Excel sheet names), not spectrum_key.
                            points_data_by_spectrum[info.get('label', spectrum)] = spectrum_points
            
            # Make sure we have at least some data to write
            if not metadata and not points_data_by_spectrum:
                QMessageBox.warning(
                    self, "No Data", 
                    "No baseline data found to export."
                )
                return
            
            # Function to sanitize sheet name for Excel
            def sanitize_sheet_name(name):
                # Replace characters that Excel doesn't allow in sheet names
                # Excel doesn't allow: [ ] * ? : / \
                name = re.sub(r'[\[\]*?:/\\]', '_', name)
                
                # Excel sheet names can't exceed 31 characters
                if len(name) > 31:
                    name = name[:28] + '...'
                    
                # Ensure sheet name doesn't start or end with a space
                name = name.strip()
                
                # Sheet name can't be empty
                if not name:
                    name = "Sheet"
                    
                return name
            
            # Now write the data to Excel
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                # Write metadata sheet
                if metadata:
                    metadata_df = pd.DataFrame(metadata)
                    metadata_df.to_excel(writer, sheet_name='Metadata', index=False)
                
                # Create a summary sheet if we don't have any points data
                if not points_data_by_spectrum:
                    # Create a summary sheet with just spectrum names and message
                    summary_data = []
                    for spectrum, info in corrections_data.items():
                        summary_data.append({
                            'Spectrum': info.get('label', spectrum) if isinstance(info, dict) else spectrum,
                            'Message': "Baseline points coordinates are not available"
                        })
                    
                    if summary_data:
                        summary_df = pd.DataFrame(summary_data)
                        summary_df.to_excel(writer, sheet_name='Summary', index=False)
                
                # Write points data sheets
                for spectrum, points in points_data_by_spectrum.items():
                    if points:
                        # Create safe sheet name
                        sheet_name = sanitize_sheet_name(spectrum)
                        
                        # Check for duplicate sheet names
                        base_name = sheet_name
                        count = 1
                        while sheet_name in writer.sheets:
                            sheet_name = f"{base_name}_{count}"
                            if len(sheet_name) > 31:  # Ensure it's still within Excel's limit
                                sheet_name = f"{base_name[:24]}_{count}"
                            count += 1
                        
                        # Write points to their own sheet
                        points_df = pd.DataFrame(points)
                        points_df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            QMessageBox.information(self, "Export Complete", f"Baseline points saved to Excel file {file_path}")
        except Exception as e:
            import traceback
            logger.error(f"Error exporting to Excel: {e}")
            logger.debug("<traceback>")
            QMessageBox.warning(self, "Export Error", f"Failed to save Excel file: {str(e)}")

    def _format_baseline_data(self, corrections_data):
        """Format baseline data for export with X,Y coordinates."""
        lines = ["Baseline Points Data", "===================", ""]
        
        for spectrum, info in corrections_data.items():
            lines.append(f"Spectrum: {info.get('label', spectrum) if isinstance(info, dict) else spectrum}")

            if isinstance(info, dict):
                # Add fit type
                fit_type = info.get('type', 'Unknown')
                lines.append(f"Fit Type: {fit_type}")
                
                # Add polynomial order if applicable
                if fit_type == 'polynomial' and 'order' in info:
                    lines.append(f"Polynomial Order: {info['order']}")
                
                # Try to get actual points coordinates
                actual_points = []
                
                # First check if we have points in the info dictionary
                if 'points' in info:
                    points_data = info['points']
                    # Check if points is a list of coordinates or just a count
                    if isinstance(points_data, list):
                        actual_points = points_data
                    elif isinstance(points_data, int):
                        # It's just a count, try to get actual points from operations manager
                        if self.operations_manager and hasattr(self.operations_manager, 'get_baseline_points'):
                            try:
                                actual_points = self.operations_manager.get_baseline_points(
                                    self.operation_index, spectrum)
                            except Exception as e:
                                logger.error(f"Error getting baseline points: {e}")
                
                # If still no points, check if we can get them directly from the controller.
                # As above, call the manager directly (key-agnostic) rather
                # than the controller wrapper, since only a label string
                # is available here, not a full spectrum dict.
                if not actual_points and self.operations_manager and hasattr(self.operations_manager, '_controller'):
                    controller = self.operations_manager._controller
                    if hasattr(controller, 'baseline_correction_controller'):
                        bc_controller = controller.baseline_correction_controller
                        if hasattr(bc_controller, 'manager'):
                            try:
                                actual_points = bc_controller.manager.get_baseline_points(spectrum)
                            except Exception as e:
                                logger.error(f"Error getting baseline points from controller: {e}")
                
                # Add points with X,Y coordinates if available
                if actual_points:
                    lines.append("\nPoints (X, Y):")
                    for i, point in enumerate(actual_points):
                        if isinstance(point, (list, tuple)) and len(point) >= 2:
                            lines.append(f"{i+1}. ({point[0]:.6g}, {point[1]:.6g})")
                else:
                    # Just show that we have points but no coordinates
                    points_count = 0
                    if isinstance(info['points'], int):
                        points_count = info['points']
                    
                    if points_count > 0:
                        lines.append(f"\nThis spectrum has {points_count} baseline points, but the coordinates are not available.")
                
            lines.append("\n" + "-" * 40 + "\n")
        
        return "\n".join(lines)

    def show_delta_values_table(self):
        """Show a table of all delta values used for smoothing."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Delta Values for {self.operation_name} #{self.operation_index + 1}")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        
        # Add title label
        title_label = QLabel(f"Delta values used for {self.operation_name}")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)
        
        # Add explanatory text
        info_label = QLabel("These are the actual delta values applied to each spectrum during smoothing.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Create table widget
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Spectrum", "Delta Value"])
        
        # Get the actual delta values from the operation record
        all_delta_values = {}
        custom_values = {}
        affected_labels = []
        
        # Get custom delta values if available
        value_item = self.table.item(self.table.findItems("delta_values", Qt.MatchExactly)[0].row(), 1)
        if value_item and value_item.data(Qt.UserRole):
            custom_values = value_item.data(Qt.UserRole)
        
        # Try to get the operation record to extract all delta values
        if self.operations_manager:
            operation = self.operations_manager.get_operation_at_index(self.operation_index)
            if operation:
                # Get affected_labels
                affected_labels = operation.get('affected_labels', [])
                
                # Extract delta values from output_spectra
                output_spectra = operation.get('output_spectra', [])
                for spectrum in output_spectra:
                    if 'label' in spectrum and 'sg_filter_info' in spectrum:
                        label = spectrum['label']
                        if label in affected_labels:  # Only include affected spectra
                            sg_info = spectrum['sg_filter_info']
                            if 'delta' in sg_info:
                                all_delta_values[label] = sg_info['delta']
        
        # If we have actual delta values, display them
        if all_delta_values:
            table.setRowCount(len(affected_labels))
            for i, label in enumerate(sorted(affected_labels)):
                # Spectrum name
                spectrum_item = QTableWidgetItem(label)
                spectrum_item.setFlags(spectrum_item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i, 0, spectrum_item)
                
                # Delta value
                delta = all_delta_values.get(label, 1.0)  # Use 1.0 as default if not found
                delta_item = QTableWidgetItem(f"{delta:.6g}")
                delta_item.setFlags(delta_item.flags() & ~Qt.ItemIsEditable)
                
                # Highlight custom values
                if label in custom_values:
                    delta_item.setBackground(QBrush(QColor(230, 255, 230)))  # Light green
                    delta_item.setToolTip("Custom delta value")
                else:
                    delta_item.setToolTip("Default delta value (1.0)")
                
                table.setItem(i, 1, delta_item)
        elif affected_labels:
            # If we have affected labels but no delta values, show with default delta
            table.setRowCount(len(affected_labels))
            for i, label in enumerate(sorted(affected_labels)):
                # Spectrum name
                spectrum_item = QTableWidgetItem(label)
                spectrum_item.setFlags(spectrum_item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i, 0, spectrum_item)
                
                # Delta value - use custom if available, otherwise default
                if label in custom_values:
                    delta = custom_values[label]
                    delta_item = QTableWidgetItem(f"{delta:.6g}")
                    delta_item.setBackground(QBrush(QColor(230, 255, 230)))  # Light green
                    delta_item.setToolTip("Custom delta value")
                else:
                    delta = 1.0  # Default delta
                    delta_item = QTableWidgetItem(f"{delta:.6g}")
                    delta_item.setToolTip("Default delta value (1.0)")
                
                delta_item.setFlags(delta_item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i, 1, delta_item)
        else:
            # Fallback: Just show a message that no delta values were found
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem("No delta values found"))
            item = QTableWidgetItem("No delta information available for this operation")
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(0, 1, item)
        
        # Set column widths
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Spectrum name
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Delta value
        
        # Enable sorting
        table.setSortingEnabled(True)
        
        layout.addWidget(table)
        
        # Add close button
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.exec_()

    def show_baseline_points_dialog(self, corrections_data):
        """Show a per-spectrum summary table (fit type, point count) for
        every spectrum with baseline correction data, with a detail panel
        showing the specific baseline points for whichever spectrum is
        selected.

        A master-detail layout rather than one tab per spectrum — tabs
        don't scale (baseline-correcting 200 spectra would need 200 tabs
        crowded into one tab bar), while the summary table scales to
        hundreds of rows via ordinary scrolling and sorts by any column.
        Same pattern as show_cosmic_ray_details_dialog's redesign, for the
        same reason; only the data-fetching (corrections_data /
        get_baseline_points, not spectrum metadata) is unchanged from
        before.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Baseline Points for {self.operation_name} #{self.operation_index + 1}")
        dialog.resize(700, 550)

        layout = QVBoxLayout(dialog)

        title_label = QLabel(f"Baseline points used for {self.operation_name}")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        # Get complete list of affected spectra from operation if available.
        # affected_labels is just label strings (a display-only field on
        # the operation record) — resolve each to its spectrum_key() via
        # this same operation's own output_spectra, so it can be merged
        # with corrections_data (already keyed by spectrum_key) into one
        # consistent identity space instead of mixing ids and labels in
        # the same set.
        affected_labels = []
        key_to_label = {
            key: (info.get('label', key) if isinstance(info, dict) else key)
            for key, info in corrections_data.items()
        }
        label_to_key = {}
        if self.operations_manager and self.operation_index >= 0:
            operation = self.operations_manager.get_operation_at_index(self.operation_index)
            if operation and 'affected_labels' in operation:
                affected_labels = operation['affected_labels']
            label_to_key = {
                s.get('label'): spectrum_key(s)
                for s in (operation or {}).get('output_spectra', [])
            }

        # If operation is original state, get all available spectra
        if self.operation_name == "Original State" and self.operations_manager:
            affected_labels = [s['label'] for s in self.operations_manager.original_spectra]
            label_to_key = {
                s['label']: spectrum_key(s) for s in self.operations_manager.original_spectra
            }

        # Create a combined list of spectra to include, as identity keys
        spectra_to_show = set(corrections_data.keys())
        for label in affected_labels:
            key = label_to_key.get(label, label)
            spectra_to_show.add(key)
            key_to_label.setdefault(key, label)

        # Resolve every spectrum's fit info and points up front so both
        # the summary table and the detail panel's row-click handler can
        # share it without re-fetching each time a row is clicked.
        info_by_spectrum = {}
        points_by_spectrum = {}
        for spectrum in spectra_to_show:
            info = corrections_data.get(spectrum) if isinstance(corrections_data.get(spectrum), dict) else None
            info_by_spectrum[spectrum] = info

            points = []
            if info and 'points' in info:
                points_data = info['points']
                if isinstance(points_data, list):
                    points = points_data
                elif isinstance(points_data, int) and self.operations_manager:
                    try:
                        points = self.operations_manager.get_baseline_points(self.operation_index, spectrum) or []
                    except Exception:
                        points = []
            points_by_spectrum[spectrum] = points

        columns = ['Spectrum', 'Fit Type', 'Polynomial Order', 'Point Count']
        summary_table = QTableWidget()
        summary_table.setColumnCount(len(columns))
        summary_table.setHorizontalHeaderLabels(columns)
        summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        summary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        summary_table.setSortingEnabled(True)
        summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(columns)):
            summary_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)

        # Sort by display label (case-insensitive), not by the raw
        # identity key — sorting by unique_id would order rows by a
        # meaningless string instead of the spectrum name a person reads.
        sorted_spectra = sorted(spectra_to_show, key=lambda k: key_to_label.get(k, k).lower())
        summary_table.setRowCount(len(sorted_spectra))
        for row, spectrum in enumerate(sorted_spectra):
            info = info_by_spectrum.get(spectrum)
            points = points_by_spectrum.get(spectrum)

            label_item = QTableWidgetItem(key_to_label.get(spectrum, spectrum))
            # Identity key stashed as Qt.UserRole — see _on_summary_row_
            # selected below, which reads this back instead of the
            # displayed text, same pattern as the main spectra list.
            label_item.setData(Qt.UserRole, spectrum)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            summary_table.setItem(row, 0, label_item)

            fit_type = info.get('type', '') if info else ''
            if not info:
                fit_type_item = QTableWidgetItem("No baseline correction applied")
                fit_type_item.setForeground(QBrush(QColor(150, 150, 150)))
            else:
                fit_type_item = QTableWidgetItem(str(fit_type))
            fit_type_item.setFlags(fit_type_item.flags() & ~Qt.ItemIsEditable)
            summary_table.setItem(row, 1, fit_type_item)

            order_text = str(info.get('order', '')) if (info and fit_type == 'polynomial' and 'order' in info) else ''
            order_item = QTableWidgetItem(order_text)
            order_item.setFlags(order_item.flags() & ~Qt.ItemIsEditable)
            summary_table.setItem(row, 2, order_item)

            count_item = QTableWidgetItem(str(len(points)) if points else '0')
            count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
            summary_table.setItem(row, 3, count_item)

        layout.addWidget(summary_table, stretch=1)

        # --- Detail panel: baseline points for whichever row is selected ---
        points_label = QLabel("Baseline points (select a spectrum above):")
        points_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(points_label)

        points_table = QTableWidget()
        points_table.setColumnCount(3)
        points_table.setHorizontalHeaderLabels(["Point #", "X", "Y"])
        points_table.setEditTriggers(QTableWidget.NoEditTriggers)
        points_table.setSortingEnabled(True)
        points_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        points_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        points_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(points_table, stretch=1)

        export_row = QHBoxLayout()
        export_button = QPushButton("Export selected spectrum's points")
        export_button.setEnabled(False)
        export_row.addStretch()
        export_row.addWidget(export_button)
        layout.addLayout(export_row)

        def _on_summary_row_selected():
            rows = {idx.row() for idx in summary_table.selectedIndexes()}
            if not rows:
                points_table.setRowCount(0)
                export_button.setEnabled(False)
                return
            row = next(iter(rows))
            label_item = summary_table.item(row, 0)
            spectrum = label_item.data(Qt.UserRole) if label_item else None
            points = points_by_spectrum.get(spectrum) or []

            points_table.setSortingEnabled(False)
            if points:
                points_table.setRowCount(len(points))
                for i, point in enumerate(points):
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        item = QTableWidgetItem(str(i + 1))
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        points_table.setItem(i, 0, item)
                        x_item = QTableWidgetItem(f"{point[0]:.6g}")
                        x_item.setFlags(x_item.flags() & ~Qt.ItemIsEditable)
                        points_table.setItem(i, 1, x_item)
                        y_item = QTableWidgetItem(f"{point[1]:.6g}")
                        y_item.setFlags(y_item.flags() & ~Qt.ItemIsEditable)
                        points_table.setItem(i, 2, y_item)
            else:
                points_table.setRowCount(1)
                msg = "No baseline points defined for this spectrum"
                info_item = QTableWidgetItem(msg)
                info_item.setFlags(info_item.flags() & ~Qt.ItemIsEditable)
                points_table.setItem(0, 0, info_item)
                points_table.setSpan(0, 0, 1, 3)
            points_table.setSortingEnabled(True)

            export_button.setEnabled(bool(points))
            try:
                export_button.clicked.disconnect()
            except TypeError:
                pass  # nothing connected yet (first selection)
            if points:
                display_name = key_to_label.get(spectrum, spectrum)
                export_button.clicked.connect(
                    lambda checked=False, s=display_name, pts=points: self._export_spectrum_points(s, pts))

        summary_table.itemSelectionChanged.connect(_on_summary_row_selected)
        if summary_table.rowCount() > 0:
            summary_table.selectRow(0)
            _on_summary_row_selected()

        if summary_table.rowCount() == 0:
            layout.addWidget(QLabel("No baseline points information available"))

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.exec_()

    def show_cosmic_ray_details_dialog(self):
        """Show a per-spectrum summary table (points flagged/replaced,
        settings) for every spectrum affected by this Cosmic ray removal
        operation, with a detail panel showing the specific flagged
        x-positions for whichever spectrum is selected.

        A master-detail layout rather than one tab per spectrum — tabs
        don't scale (cosmic ray removal over 200 spectra would need 200
        tabs crowded into one tab bar), while the summary table scales to
        hundreds of rows via ordinary scrolling and sorts by any column.
        The detail (potentially many flagged x-positions per spectrum,
        unlike Normalization's single scalar factor) doesn't fit cleanly
        into one table cell, so it stays in a separate panel showing only
        the currently-selected spectrum's positions rather than needing a
        sub-table for all of them at once.

        Unlike baseline points (stored directly in the operation's own
        parameters dict), per-spectrum cosmic-ray detail lives in each
        spectrum's OWN metadata (metadata['correction_history'] — see
        CosmicRayManager.apply / correction_history.py), because that
        history is shared across every operation type that records one
        (SVD Background, Manual Baseline, Cosmic ray removal) and
        interleaves entries from all of them in the order they actually
        happened. This looks up each affected spectrum by label in THIS
        operation's own operation['output_spectra'] — the snapshot every
        operation record already stores of exactly what its spectra
        looked like right after it ran (same field used elsewhere in this
        app, e.g. Map2DController.send_spectra_to_main_list) — and takes
        the LATEST 'Cosmic Ray Removal' entry in its history.

        This was previously looked up via
        self.operations_manager.original_spectra instead, on the
        assumption that it was the live, up-to-date spectrum list —
        confirmed wrong in practice (every tab showed "no record found"),
        since it doesn't reliably carry this operation's own metadata.
        output_spectra is guaranteed to, since it's this exact operation's
        own recorded output.

        Known limitation: if the SAME spectrum went through Cosmic ray
        removal more than once, this always shows the most recent
        application's numbers — even when opened from Parameters for an
        OLDER operation instance in the chain — rather than precisely the
        entry that specific historical operation produced. Correctly
        disambiguating that would need matching against the operation's
        own recorded timestamp, which isn't threaded through this lookup
        path today.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Cosmic Ray Removal Detail for Operation #{self.operation_index + 1}")
        dialog.resize(700, 550)

        layout = QVBoxLayout(dialog)

        title_label = QLabel("Flagged / replaced points by spectrum")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        operation = None
        affected_spectra = []
        source_to_copy_label = {}
        if self.operations_manager and self.operation_index >= 0:
            operation = self.operations_manager.get_operation_at_index(self.operation_index)
            if operation and 'affected_labels' in operation:
                affected_spectra = operation['affected_labels']
            # "Add as New" mode doesn't go through the normal commit path's
            # own apply_operation() call at all — that record gets popped
            # and replaced by register_copy_operation() instead (see
            # commit_cosmic_ray_removal), whose affected_labels are the
            # SOURCE spectra (the ones the user actually selected), not the
            # new copies. The correction_history metadata only exists on
            # the NEW copy (e.g. "<label>_cosmic_ray") — the source was
            # never touched in this mode — and both the source and the
            # copy are present in the same output_spectra list (built as
            # pre_state + copies), so looking up by the source label finds
            # the wrong (untouched) spectrum every time. source_labels and
            # copy_labels are recorded in lockstep, same order, so this
            # rebuilds the correspondence between them.
            params = (operation or {}).get('parameters') or {}
            src_labels = params.get('source_labels')
            copy_labels = params.get('copy_labels')
            if src_labels and copy_labels and len(src_labels) == len(copy_labels):
                source_to_copy_label = dict(zip(src_labels, copy_labels))

        # Look up each spectrum from THIS operation's own output_spectra
        # snapshot — the spectra exactly as they existed right after this
        # operation ran, metadata included — not
        # self.operations_manager.original_spectra, which doesn't
        # reliably reflect that (confirmed: every tab was showing "no
        # record found" before this fix). output_spectra is the same
        # field every operation record already stores for history
        # navigation (see e.g. Map2DController.send_spectra_to_main_list
        # and operations_controller.py's own use of it elsewhere).
        label_to_spectrum = {}
        if operation and 'output_spectra' in operation:
            label_to_spectrum = {s['label']: s for s in operation['output_spectra']}

        # Resolve every spectrum's entry up front so both the summary
        # table and the detail panel's row-click handler can share it
        # without re-doing the label lookup each time a row is clicked.
        entries_by_label = {}
        for label in affected_spectra:
            lookup_label = source_to_copy_label.get(label, label)
            spectrum = label_to_spectrum.get(lookup_label)
            history = ((spectrum or {}).get('metadata') or {}).get('correction_history', [])
            entry = next((e for e in reversed(history)
                         if e.get('operation') == 'Cosmic Ray Removal'), None)
            entries_by_label[label] = entry

        columns = ['Spectrum', 'Points Flagged', 'Points Replaced', 'Replace Window', 'Threshold']
        entry_keys = ['points_flagged', 'points_replaced', 'replace_window', 'threshold']

        summary_table = QTableWidget()
        summary_table.setColumnCount(len(columns))
        summary_table.setHorizontalHeaderLabels(columns)
        summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        summary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        summary_table.setSortingEnabled(True)
        summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(columns)):
            summary_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)

        sorted_labels = sorted(affected_spectra)
        summary_table.setRowCount(len(sorted_labels))
        for row, label in enumerate(sorted_labels):
            entry = entries_by_label.get(label)

            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            summary_table.setItem(row, 0, label_item)

            if entry is None:
                no_record_item = QTableWidgetItem("No record found")
                no_record_item.setFlags(no_record_item.flags() & ~Qt.ItemIsEditable)
                no_record_item.setForeground(QBrush(QColor(150, 150, 150)))
                summary_table.setItem(row, 1, no_record_item)
                for c in range(2, len(columns)):
                    blank_item = QTableWidgetItem("")
                    blank_item.setFlags(blank_item.flags() & ~Qt.ItemIsEditable)
                    summary_table.setItem(row, c, blank_item)
                continue

            for c, key in enumerate(entry_keys, start=1):
                text = self._format_value_for_display(entry[key]) if key in entry else ""
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                summary_table.setItem(row, c, item)

        layout.addWidget(summary_table, stretch=1)

        # --- Detail panel: flagged x-positions for whichever row is selected ---
        positions_label = QLabel("Flagged x-positions (select a spectrum above):")
        positions_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(positions_label)

        positions_table = QTableWidget()
        positions_table.setColumnCount(2)
        positions_table.setHorizontalHeaderLabels(["Point #", "x position"])
        positions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        positions_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        positions_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(positions_table, stretch=1)

        def _on_summary_row_selected():
            rows = {idx.row() for idx in summary_table.selectedIndexes()}
            if not rows:
                positions_table.setRowCount(0)
                return
            row = next(iter(rows))
            label_item = summary_table.item(row, 0)
            label = label_item.text() if label_item else None
            entry = entries_by_label.get(label)
            x_positions = (entry or {}).get('flagged_x_positions', [])
            positions_table.setRowCount(len(x_positions))
            for i, x in enumerate(x_positions):
                idx_item = QTableWidgetItem(str(i + 1))
                idx_item.setFlags(idx_item.flags() & ~Qt.ItemIsEditable)
                positions_table.setItem(i, 0, idx_item)
                x_item = QTableWidgetItem(self._format_value_for_display(x))
                x_item.setFlags(x_item.flags() & ~Qt.ItemIsEditable)
                positions_table.setItem(i, 1, x_item)

        summary_table.itemSelectionChanged.connect(_on_summary_row_selected)
        if summary_table.rowCount() > 0:
            summary_table.selectRow(0)
            _on_summary_row_selected()

        if summary_table.rowCount() == 0:
            layout.addWidget(QLabel("No affected spectra information available"))

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.exec_()

    def show_normalization_details_dialog(self):
        """Show per-spectrum Normalization detail — delegates to the
        shared smart renderer (show_per_spectrum_details_dialog), which
        only tables fields that actually differ between spectra (Mode
        and X Ranges are typically the SAME for every spectrum in a
        batch; only Factor genuinely varies per spectrum) instead of
        repeating every column in every row. See that method's docstring
        for the reasoning — this used to be a standalone implementation
        duplicating _get_per_spectrum_data's own output_spectra +
        label-remapping logic; now shares it, same as every other
        one-to-one operation's detail dialog.
        """
        self.show_per_spectrum_details_dialog(
            'Normalization', 'Factor / settings used by spectrum',
            ['Spectrum', 'Mode', 'X Ranges', 'Factor', 'Reference Index'],
            ['mode', 'x_ranges', 'factor', 'reference_spectrum_index'],
        )

    def show_sg_smoothing_details_dialog(self):
        """Show per-spectrum SG-Smoothing detail — delegates to the
        shared smart renderer (show_per_spectrum_details_dialog), which
        only tables fields that actually differ between spectra. For
        SG-Smoothing specifically this is often ALL of them (Window
        Length, Poly Order, Deriv Order, Delta, Delta Source, Mode are
        frequently identical across an entire batch, since there's
        usually no per-spectrum reason for them to differ) — confirmed
        real complaint, addressed the same way as every other one-to-one
        operation's detail dialog now shares.
        """
        self.show_per_spectrum_details_dialog(
            'SG-smoothing', 'Settings used by spectrum',
            ['Spectrum', 'Window Length', 'Poly Order', 'Deriv Order', 'Delta', 'Delta Source', 'Mode'],
            ['window_length', 'polyorder', 'deriv_order', 'delta', 'delta_source', 'mode'],
        )

    def _export_spectrum_points(self, spectrum_name, points):
        """Export points for a specific spectrum."""
        if not points:
            QMessageBox.information(self, "No Points", f"No baseline points to export for {spectrum_name}")
            return
        
        menu = QMenu(self)
        to_clipboard = menu.addAction("Copy to Clipboard")
        to_file = menu.addAction("Save to File")
        
        action = menu.exec_(QCursor.pos())
        
        if action == to_clipboard:
            text = f"Baseline Points for {spectrum_name}\n"
            text += "==========================\n\n"
            text += "Point\tX\tY\n"
            text += "-----\t-----\t-----\n"
            
            for i, point in enumerate(points):
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    text += f"{i+1}\t{point[0]:.6g}\t{point[1]:.6g}\n"
            
            # Copy to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            
            QMessageBox.information(self, "Export Complete", f"Baseline points for {spectrum_name} copied to clipboard.")
        
        elif action == to_file:
            file_path, _ = QFileDialog.getSaveFileName(
                self, f"Save Baseline Points for {spectrum_name}", "", "Text Files (*.txt);;All Files (*)"
            )
            
            if not file_path:
                return
            
            try:
                with open(file_path, 'w') as f:
                    f.write(f"Baseline Points for {spectrum_name}\n")
                    f.write("==========================\n\n")
                    f.write("Point\tX\tY\n")
                    f.write("-----\t-----\t-----\n")
                    
                    for i, point in enumerate(points):
                        if isinstance(point, (list, tuple)) and len(point) >= 2:
                            f.write(f"{i+1}\t{point[0]:.6g}\t{point[1]:.6g}\n")
                
                QMessageBox.information(self, "Export Complete", f"Baseline points saved to {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "Export Error", f"Failed to save file: {str(e)}")

class OperationItemWidget(QFrame):
    """Custom widget for displaying an operation in the history list."""
    
    def __init__(self, operation_index, operation_type, timestamp, affected_count, 
                 is_active=False, parent=None):
        super().__init__(parent)
        self.operation_index = operation_index
        self.operation_type = operation_type
        self.timestamp = timestamp
        self.affected_count = affected_count
        self.is_active = is_active
        self.is_selected = False
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        
        # Main info layout
        main_info = QHBoxLayout()
        
        # Operation number and type with larger font
        op_label = QLabel(f"#{self.operation_index + 1}: {_display_name_for_operation(self.operation_type)}")
        font = op_label.font()
        font.setPointSize(font.pointSize() + 1)
        font.setBold(True)
        op_label.setFont(font)
        
        # Apply different text color based on active state — background is
        # handled separately by _apply_frame_style() so it can also account
        # for selection state.
        if self.is_active:
            op_label.setStyleSheet("color: #006400;") # Dark green for text
        
        main_info.addWidget(op_label)
        main_info.addStretch()
        
        # Add active indicator
        if self.is_active:
            active_label = QLabel("ACTIVE")
            active_label.setStyleSheet("color: #006400; font-weight: bold;")
            main_info.addWidget(active_label)
        
        layout.addLayout(main_info)
        
        # Metadata layout
        meta_layout = QHBoxLayout()
        meta_layout.setContentsMargins(10, 0, 0, 0)
        
        # Applied date/time
        time_label = QLabel(f"Applied: {self.timestamp}")
        time_label.setStyleSheet("color: #555555; font-size: 11px;")
        meta_layout.addWidget(time_label)
        
        meta_layout.addStretch()
        
        # Show affected spectra count with clearer wording
        if self.affected_count > 0:
            affected_text = f"Operation affected {self.affected_count} spectra"
        else:
            affected_text = "No spectra affected"
            
        spectra_count = QLabel(affected_text)
        spectra_count.setStyleSheet("color: #555555; font-size: 11px;")
        meta_layout.addWidget(spectra_count)
        
        layout.addLayout(meta_layout)

        # Buttons layout
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 5, 0, 0)
        
        self.spectra_button = QPushButton("Spectra List")
        self.spectra_button.setMaximumWidth(100)
        
        # Only show Parameters button for non-removal operations
        if self.operation_type != "removal":
            self.parameters_button = QPushButton("Parameters")
            self.parameters_button.setMaximumWidth(100)        
        
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.spectra_button)
        
        # Only add the Parameters button if it exists
        if hasattr(self, 'parameters_button'):
            buttons_layout.addWidget(self.parameters_button)        

        layout.addLayout(buttons_layout)

        self._apply_frame_style()

    def _apply_frame_style(self):
        """Background reflects ACTIVE state; border reflects whether this
        row is the one currently selected (the candidate to jump to).
        These are independent — a row can be active, selected, both, or
        neither — and a custom QFrame like this one paints over the list
        widget's own selection highlighting, so without this there'd be no
        visual feedback at all for which row you've clicked.
        """
        bg = "#E0F7E0" if self.is_active else "#F5F5F5"
        border = "2px solid #1565C0" if self.is_selected else "2px solid transparent"
        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border: {border}; border-radius: 4px; }}"
        )

    def set_selected(self, selected):
        """Toggle the 'selected to jump to' highlight border."""
        if self.is_selected != selected:
            self.is_selected = selected
            self._apply_frame_style()

class OriginalStateWidget(QFrame):
    """Widget for displaying the original state in the history list."""
    
    def __init__(self, num_spectra, is_active=False, parent=None):
        super().__init__(parent)
        self.num_spectra = num_spectra
        self.is_active = is_active
        self.is_selected = False
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        
        # Main info layout
        main_info = QHBoxLayout()
        
        # Original state label with larger font
        op_label = QLabel("#0: Original State")
        font = op_label.font()
        font.setPointSize(font.pointSize() + 1)
        font.setBold(True)
        op_label.setFont(font)
        op_label.setStyleSheet("color: #006400;" if self.is_active else "color: #0D47A1;")
        
        main_info.addWidget(op_label)
        main_info.addStretch()

        # Add active indicator — matches OperationItemWidget, so jumping
        # back to Original State is shown the same way as jumping to any
        # other step instead of just silently losing the ACTIVE badge.
        if self.is_active:
            active_label = QLabel("ACTIVE")
            active_label.setStyleSheet("color: #006400; font-weight: bold;")
            main_info.addWidget(active_label)
        
        layout.addLayout(main_info)
        
        # Spectra count
        meta_layout = QHBoxLayout()
        meta_layout.setContentsMargins(10, 0, 0, 0)
        
        spectra_count = QLabel(f"Contains {self.num_spectra} spectra")
        spectra_count.setStyleSheet("color: #555555; font-size: 11px;")
        meta_layout.addWidget(spectra_count)
        
        layout.addLayout(meta_layout)
        
        # Buttons layout
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 5, 0, 0)
        
        self.spectra_button = QPushButton("Spectra List")
        self.spectra_button.setMaximumWidth(100)
        
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.spectra_button)
        
        layout.addLayout(buttons_layout)

        self._apply_frame_style()

    def _apply_frame_style(self):
        """Background reflects ACTIVE state; border reflects whether this
        row is the one currently selected (the candidate to jump to) — see
        OperationItemWidget._apply_frame_style for why both are needed.
        """
        bg = "#E0F7E0" if self.is_active else "#E3F2FD"
        border = "2px solid #1565C0" if self.is_selected else "2px solid transparent"
        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border: {border}; border-radius: 4px; }}"
        )

    def set_selected(self, selected):
        """Toggle the 'selected to jump to' highlight border."""
        if self.is_selected != selected:
            self.is_selected = selected
            self._apply_frame_style()

class OperationsSummaryDialog(QDialog):
    """Dialog for displaying and managing operations history."""
    
    # Signal emitted when an operation is selected to be restored
    operation_selected = pyqtSignal(int)
    
    def __init__(self, parent=None, operations_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Operations History")
        self.setModal(True)
        
        # Set window flags to allow maximize/minimize buttons
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)        
        
        self.operations_manager = operations_manager
        self.resize(700, 500)  # Set default size
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Add header label
        header_label = QLabel("Operations History (Incremental Chain)")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # Add info label
        info_label = QLabel(
            "Operations are applied incrementally, with each operation building on the previous one. "
            "Select an operation to jump to that state."
        )
        info_label.setStyleSheet("color: #1565C0;")  # Blue color for info
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Add warning label
        warning_label = QLabel(
            "If you apply a new operation after jumping to a previous state, "
            "all operations that were originally after this point will be discarded."
        )
        warning_label.setStyleSheet("color: #D32F2F;")  # Red color for warning
        warning_label.setAlignment(Qt.AlignCenter)
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)
        
        # Create list widget for operations
        self.operations_list = QListWidget()
        self.operations_list.setSelectionMode(QListWidget.SingleSelection)
        self.operations_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
            }
            QListWidget::item {
                border-bottom: 1px solid #D0D3DA;
                padding: 0px;
            }
            QListWidget::item:selected {
                background-color: #BBDEFB;
                color: black;
            }
        """)
        layout.addWidget(self.operations_list)
        
        # Add action buttons
        button_layout = QHBoxLayout()
        
        # Jump to selected state button
        self.jump_button = QPushButton("Jump to Selected State")
        self.jump_button.setToolTip("Restore to the selected operation state")
        self.jump_button.setEnabled(False)  # Initially disabled
        button_layout.addWidget(self.jump_button)

        # Add Save Parameters button
        self.save_params_button = QPushButton("Save Parameters to File")
        self.save_params_button.setToolTip("Save all operation parameters to a text file")
        button_layout.addWidget(self.save_params_button)

        # Save as Pipeline — captures a checked subset of this session's
        # committed operations (in order) into a named, reusable pipeline
        # that can be replayed later on any spectra selection. See
        # batch_pipeline_help.py for the full picture; this button is the
        # primary entry point (also reachable from the main Operations
        # menu without opening this dialog first).
        self.save_pipeline_button = QPushButton("Save as Pipeline...")
        self.save_pipeline_button.setToolTip(
            "Capture some or all of these operations into a named, reusable pipeline"
        )
        self.save_pipeline_button.clicked.connect(self._save_as_pipeline)
        button_layout.addWidget(self.save_pipeline_button)

        layout.addLayout(button_layout)
        
        # Add dialog buttons
        bottom_layout = QHBoxLayout()
        help_btn = QPushButton("Help")
        help_btn.setToolTip("How does the Operations History work?")
        help_btn.clicked.connect(self._show_help)
        bottom_layout.addWidget(help_btn)
        bottom_layout.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        bottom_layout.addWidget(button_box)
        layout.addLayout(bottom_layout)
        
        # Connect signals
        self.operations_list.itemSelectionChanged.connect(self._handle_selection_change)
        self.jump_button.clicked.connect(self._handle_jump)
        self.save_params_button.clicked.connect(self._save_parameters_to_file)
        button_box.rejected.connect(self.reject)
        
        # Load operations
        self.load_operations()

    def _show_help(self):
        """Show help for the Operations History dialog."""
        from src.help.help_window import show_help_window
        title = "Operations History — Help"
        content = """
        <html><head><style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2 { color: #1976D2; margin-top: 20px; }
            .tip  { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .warn { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; margin: 8px 0; }
            ul { padding-left: 22px; } li { margin: 4px 0; }
        </style></head><body>
        <h1>Operations History</h1>

        <h2>What is the Operations History?</h2>
        <p>Every time you click <strong>Apply</strong> in the Spectra Processing panel,
        a new entry is added to the Operations History. The history records the complete
        chain of processing steps in the order they were applied, together with their
        parameters and the spectra they affected.</p>

        <p>The history is <strong>incremental</strong>: each operation builds on the
        result of all previous ones. The currently active state (the result of all
        applied operations so far) is shown with a green <em>ACTIVE</em> badge.</p>

        <h2>Jumping to a Previous State</h2>
        <p>Click any entry in the list and then click <strong>Jump to Selected State</strong>
        to restore the data to how it looked immediately after that operation was applied.
        This is the primary way to undo one or more operations.</p>

        <div class="warn">
            <strong>Important — no branches:</strong> if you jump back to an earlier
            state and then click Apply for a new operation, <em>all operations that
            originally came after the jumped-to state are permanently discarded</em>.
            The history becomes a straight line again from the jumped-to point forward.
            Save a snapshot (File → Save snapshot) before jumping if you want to
            preserve the original chain.
        </div>

        <div class="tip">
            <strong>Tip:</strong> use snapshots for major checkpoints and the Operations
            History for fine-grained step-by-step review and undo within a session.
        </div>

        <h2>Buttons Inside Each Entry</h2>
        <ul>
            <li><strong>Spectra List:</strong> shows which spectra were processed by
                this operation.</li>
            <li><strong>Parameters:</strong> shows the exact settings used (normalization
                region, smoothing window, formula, etc.).</li>
        </ul>

        <h2>Save Parameters to File</h2>
        <p>Exports the full operation chain with all parameters to a text file.
        Useful for method documentation and reproducibility reporting.</p>

        <h2>State #0 — Original State</h2>
        <p>The first entry always represents the data as originally imported, before
        any processing. Jumping to #0 restores the raw data. You cannot delete this
        entry.</p>
        </body></html>
        """
        show_help_window(self, title, content)

    def _show_operation_spectra(self, operation_index):
        """Show spectra affected by an operation."""
        if not self.operations_manager:
            return
            
        operation = self.operations_manager.get_operation_at_index(operation_index)
        if not operation:
            return
        
        # Get affected labels directly from the operation record
        affected_labels = operation.get('affected_labels', [])
        
        # If no affected_labels found, try to extract them from output_spectra
        if not affected_labels and 'output_spectra' in operation:
            affected_labels = [spectrum.get('label', f"Spectrum {i+1}") 
                              for i, spectrum in enumerate(operation.get('output_spectra', []))]
        
        title = f"Affected Spectra for {_display_name_for_operation(operation.get('type', 'Operation'))} #{operation_index + 1}"
        
        # Show in a dialog - pass operations_manager and index for more detailed info
        if affected_labels:
            dialog = SpectraListDialog(
                title, 
                affected_labels, 
                self,
                self.operations_manager,
                operation_index
            )
            dialog.exec_()
        else:
            QMessageBox.information(
                self,
                title,
                "No spectra information available."
            )

    def _show_original_spectra(self):
        """Show the list of original spectra."""
        if not self.operations_manager:
            return
                
        # Get the original spectra
        spectra = self.operations_manager.original_spectra
        
        # Get spectra labels
        spectra_labels = [s.get('label', f"Spectrum {i+1}") for i, s in enumerate(spectra)]
        
        # Show in a dialog with operations manager reference
        if spectra_labels:
            dialog = SpectraListDialog(
                "Original State", 
                spectra_labels, 
                self,
                self.operations_manager,  # Pass operations_manager 
                -1  # Use -1 as the special index for original state
            )
            dialog.exec_()
        else:
            QMessageBox.information(
                self,
                "Original Spectra",
                "No original spectra information available."
            )

    def _show_operation_parameters(self, operation_index):
        """Show the parameters for an operation."""
        if not self.operations_manager:
            return
            
        operation = self.operations_manager.get_operation_at_index(operation_index)
        if not operation:
            return
            
        # Get operation details
        operation_type = operation.get('type', 'Operation')
        parameters = operation.get('parameters', {})
        
        # Check if we need to show delta values table for SG-smoothing
        if operation_type.startswith("SG-smoothing") and hasattr(self.operations_manager, 'get_sg_delta_values_table'):
            delta_table = self.operations_manager.get_sg_delta_values_table(operation_index)
            if delta_table:
                self._show_sg_delta_values_table(operation_type, operation_index, delta_table)
                return
        
        # Otherwise, show standard parameters dialog
        dialog = OperationParametersDialog(operation_type, operation_index, parameters, self)
        dialog.exec_()

    def _show_sg_delta_values_table(self, operation_type, operation_index, table_data):
        """Show a table of Savitzky-Golay delta values."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Delta Values for {operation_type} #{operation_index + 1}")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        # Add title label
        title_label = QLabel(f"Custom delta values for operation #{operation_index + 1}: {operation_type}")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)
        
        # Create table widget
        table = QTableWidget()
        table.setColumnCount(len(table_data['headers']))
        table.setHorizontalHeaderLabels(table_data['headers'])
        
        # Add data rows
        table.setRowCount(len(table_data['rows']))
        for i, row in enumerate(table_data['rows']):
            for j, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # Make read-only
                table.setItem(i, j, item)
        
        # Set column widths
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Spectrum name
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Delta value
        
        # Enable sorting
        table.setSortingEnabled(True)
        
        layout.addWidget(table)
        
        # Add close button
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.exec_()

    def _save_parameters_to_file(self):
        """Save operation parameters to a text file."""
        if not self.operations_manager:
            QMessageBox.warning(
                self, 
                "Warning", 
                "No operations history available to save."
            )
            return
        
        # Open file dialog to get save location
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save Operations Parameters",
            "",
            "Text Files (*.txt);;All Files (*)"
        )
        
        if file_name:
            # Ensure file has .txt extension
            if not file_name.lower().endswith('.txt'):
                file_name += '.txt'
                
            # Save parameters using the history manager
            success = self.operations_manager.save_parameters_to_file(file_name)
            
            if success:
                QMessageBox.information(
                    self,
                    "Success",
                    f"Operation parameters successfully saved to {file_name}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Failed to save operation parameters to {file_name}"
                )

    def _save_as_pipeline(self):
        """Open the Save-as-Pipeline dialog, seeded with this session's
        committed operations chain (operations_manager.operations_chain)
        — see batch_pipeline_help.py for what a pipeline is and which
        operations can be included."""
        if not self.operations_manager or not self.operations_manager.operations_chain:
            QMessageBox.warning(
                self, "No operations to save",
                "No operations have been applied yet this session."
            )
            return

        from src.views.dialogs.data_analysis.batch_pipeline_save_dialog import BatchPipelineSaveDialog
        from src.modules.misc.pipeline_manager import PipelineManager

        dialog = BatchPipelineSaveDialog(
            parent=self,
            operations_chain=list(self.operations_manager.operations_chain),
            pipeline_manager=PipelineManager(),
        )
        dialog.exec_()

    def load_operations(self):
        """Load operations from the manager with improved UI."""
        if not self.operations_manager:
            return
        
        # Clear current list
        self.operations_list.clear()
        
        # First add original state item
        original_item = QListWidgetItem()
        original_is_active = (getattr(self.operations_manager, 'active_operation_index', -1) == -1)
        original_widget = OriginalStateWidget(
            len(self.operations_manager.original_spectra), is_active=original_is_active
        )
        original_widget.spectra_button.clicked.connect(self._show_original_spectra)
        
        original_item.setSizeHint(original_widget.sizeHint())
        self.operations_list.addItem(original_item)
        self.operations_list.setItemWidget(original_item, original_widget)
        
        # Get operations from manager
        operations_chain = getattr(self.operations_manager, 'operations_chain', [])
        
        # Add each operation to the list with improved UI
        for i, operation in enumerate(operations_chain):
            # Get operation details
            op_type = operation.get('type', 'Operation')
            timestamp = operation.get('timestamp', '')
            affected_labels = operation.get('affected_labels', [])
            properties_provided = operation.get('properties_provided', set())
            
            # Format timestamp for display
            if timestamp:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp)
                    formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    formatted_time = timestamp
            else:
                formatted_time = "Unknown time"
            
            # Check if this operation is active
            is_active = (i == self.operations_manager.active_operation_index)
            
            # Create custom widget for the item
            item = QListWidgetItem()
            item_widget = OperationItemWidget(
                i, op_type, formatted_time,
                len(affected_labels),
                is_active
            )
            
            # Connect button signals - check if the button exists first
            item_widget.spectra_button.clicked.connect(lambda checked, idx=i: self._show_operation_spectra(idx))
            
            # Only connect parameters button if it exists (not for removal operations)
            if hasattr(item_widget, 'parameters_button'):
                item_widget.parameters_button.clicked.connect(lambda checked, idx=i: self._show_operation_parameters(idx))
            
            item.setSizeHint(item_widget.sizeHint())
            self.operations_list.addItem(item)
            self.operations_list.setItemWidget(item, item_widget)

    def _handle_selection_change(self):
        """Handle changes in selection of operations list."""
        selected_items = self.operations_list.selectedItems()
        selected_rows = {self.operations_list.row(it) for it in selected_items}

        # Highlight whichever row is currently selected (the candidate to
        # jump to) with a blue border. Each row is a custom widget that
        # paints over the list widget's own selection background, so
        # without this there's no visual feedback for which row you've
        # actually clicked, as opposed to which one is ACTIVE.
        for i in range(self.operations_list.count()):
            widget = self.operations_list.itemWidget(self.operations_list.item(i))
            if widget is not None and hasattr(widget, 'set_selected'):
                widget.set_selected(i in selected_rows)

        if not selected_items:
            self.jump_button.setEnabled(False)
            return
        
        selected_index = self.operations_list.row(selected_items[0])
        
        # If original state (index 0) is selected, use -1 as the operation index
        operation_index = selected_index - 1  # Adjust for original state item
        
        # Always enable the jump button
        self.jump_button.setEnabled(True)
    
    def _handle_jump(self):
        """Handle jump button click."""
        selected_items = self.operations_list.selectedItems()
        if not selected_items:
            return
        
        # Get the index of the selected item
        selected_index = self.operations_list.row(selected_items[0])
        
        # Adjust for original state item
        operation_index = selected_index - 1
        
        # Confirm with user if jumping back would discard operations
        if operation_index < self.operations_manager.active_operation_index:
            confirm = QMessageBox.question(
                self,
                "Confirm Jump",
                "This will discard all operations after the selected one. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if confirm != QMessageBox.Yes:
                return
        
        # Emit signal with selected index
        self.operation_selected.emit(operation_index)
        self.accept()
    
    def _handle_restore_original(self):
        """Handle restore original button click."""
        # Confirm with user if there are operations
        if self.operations_manager and getattr(self.operations_manager, 'operations_chain', []):
            confirm = QMessageBox.question(
                self,
                "Confirm Restore Original",
                "This will discard all operations and restore the original state. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if confirm != QMessageBox.Yes:
                return
        
        # Emit signal with -1 to indicate original state
        self.operation_selected.emit(-1)
        self.accept()
   
class BaselinePointsStorage:
    """Singleton class to store baseline points between operations.

    Keyed by spectrum_key() (unique_id), not by label — see use_baseline_
    points() above, which resolves each historical label to its current
    spectrum's unique_id before storing, and _load_stored_points() in
    baseline_correction_controller.py, which reads it back the same way.
    This keeps the cache valid even if the spectrum gets renamed between
    "Use These Points" and reopening the Baseline Correction dialog.
    """

    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = BaselinePointsStorage()
        return cls._instance
    
    def __init__(self):
        """Initialize empty storage."""
        self.points = {}
        self.fit_types = {}
        self.poly_orders = {}
        self.has_stored_points = False
    
    def clear(self):
        """Clear all stored points."""
        self.points.clear()
        self.fit_types.clear()
        self.poly_orders.clear()
        self.has_stored_points = False
    
    def store_points(self, key, points, fit_type=None, poly_order=None):
        """Store points for a spectrum, keyed by spectrum_key() (unique_id)."""
        self.points[key] = points
        if fit_type:
            self.fit_types[key] = fit_type
        if poly_order is not None:
            self.poly_orders[key] = poly_order
        self.has_stored_points = True
        
        