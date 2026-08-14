# src/views/dialogs/data_analysis/savitzky_golay_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
                           QPushButton, QSpinBox, QDialogButtonBox, QLabel, QComboBox, QTableWidget,
                           QTableWidgetItem, QHeaderView, QLineEdit, QMessageBox )
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDoubleValidator, QBrush, QColor
import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.data_analysis.savitzky_golay_manager import SavitzkyGolayManager
logger = get_logger(__name__)

class DeltaSettingsDialog(QDialog):
    """Dialog for setting individual delta values for each spectrum."""
    
    def __init__(self, parent=None, spectra=None, current_delta_values=None):
        super().__init__(parent)
        self.setWindowTitle("Delta Settings for Individual Spectra")
        self.setModal(True)
        self.resize(600, 400)
        self.spectra = spectra or []
        self.delta_values = current_delta_values or {}  # Use existing values if provided
        self.estimated_values = {}  # Store estimated values for reset function
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Add information label
        info_label = QLabel(
            "Set custom delta values for each spectrum. Delta should ideally match "
            "the spacing between consecutive x-axis points. The estimated value "
            "is calculated as the median difference between points."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Create table for delta values
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Spectrum", "Estimated Delta", "Variance", "Custom Delta"])
        
        # Set column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        # Populate table
        self.populate_table()
        
        # Connect cell changed signal for validation
        self.table.cellChanged.connect(self.validate_delta_cell)
        
        layout.addWidget(self.table)
        
        # Add buttons for reset and set all
        button_layout = QHBoxLayout()
        
        self.reset_defaults_button = QPushButton("Reset to Estimated Values")
        self.reset_defaults_button.setToolTip("Reset all custom delta values to their estimated values")
        self.reset_defaults_button.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(self.reset_defaults_button)
        
        self.set_all_button = QPushButton("Set All Values To...")
        self.set_all_button.setToolTip("Set all custom delta values to a single value")
        self.set_all_button.clicked.connect(self.set_all_values)
        button_layout.addWidget(self.set_all_button)
        
        layout.addLayout(button_layout)
        
        # Add dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def populate_table(self):
        """Populate the table with spectrum data."""
        if not self.spectra:
            return
            
        self.table.setRowCount(len(self.spectra))
        
        # Temporarily block signals during population to avoid validation calls
        self.table.blockSignals(True)
        
        for i, spectrum in enumerate(self.spectra):
            # Spectrum name
            name_item = QTableWidgetItem(spectrum['label'])
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)  # Make read-only
            self.table.setItem(i, 0, name_item)
            
            # Calculate statistics for this spectrum
            x_scale = spectrum['x_scale']
            if len(x_scale) >= 2:
                diffs = np.diff(x_scale)
                median_diff = np.median(np.abs(diffs))
                variance = np.var(diffs)
                
                # Store estimated value for reset function
                self.estimated_values[spectrum['label']] = median_diff
                
                # Estimated delta (read-only)
                estimated_item = QTableWidgetItem(f"{median_diff:.6g}")
                estimated_item.setFlags(estimated_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, 1, estimated_item)
                
                # Variance (read-only)
                variance_item = QTableWidgetItem(f"{variance:.6g}")
                variance_item.setFlags(variance_item.flags() & ~Qt.ItemIsEditable)
                # Highlight high variance with yellow background
                if variance > 0.01 * median_diff:
                    variance_item.setBackground(QBrush(QColor(255, 255, 150)))  # Light yellow
                self.table.setItem(i, 2, variance_item)
                
                # Custom delta (editable) - use existing value if available
                if spectrum['label'] in self.delta_values:
                    custom_value = self.delta_values[spectrum['label']]
                    custom_item = QTableWidgetItem(f"{custom_value:.6g}")
                else:
                    custom_item = QTableWidgetItem(f"{median_diff:.6g}")
                self.table.setItem(i, 3, custom_item)
            else:
                # Not enough points for statistics
                for col in range(1, 4):
                    item = QTableWidgetItem("N/A")
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(i, col, item)
        
        # Restore signals
        self.table.blockSignals(False)
    
    def validate_delta_cell(self, row, column):
        """Validate that delta values are numeric."""
        # Only check the Custom Delta column (column 3)
        if column == 3:
            item = self.table.item(row, column)
            if item:
                text = item.text()
                try:
                    # Try to convert to float
                    value = float(text)
                    # Format with 6 significant digits
                    item.setText(f"{value:.6g}")
                    # Clear any previous error styling
                    item.setBackground(QBrush())
                    item.setToolTip("")
                except ValueError:
                    # If not a valid number, set background to light red
                    item.setBackground(QBrush(QColor(255, 200, 200)))  # Light red
                    # Show a tooltip
                    item.setToolTip("Not a valid number")
    
    def reset_to_defaults(self):
        """Reset all custom delta values to their estimated values."""
        # Temporarily block signals
        self.table.blockSignals(True)
        try:
            for i in range(self.table.rowCount()):
                spectrum_name = self.table.item(i, 0).text()
                if spectrum_name in self.estimated_values:
                    estimated_value = self.estimated_values[spectrum_name]
                    # Create new item with estimated value
                    custom_item = QTableWidgetItem(f"{estimated_value:.6g}")
                    self.table.setItem(i, 3, custom_item)
        finally:
            # Restore signals
            self.table.blockSignals(False)
            
        QMessageBox.information(
            self,
            "Reset Complete",
            "All custom delta values have been reset to their estimated values."
        )
    
    def set_all_values(self):
        """Set all custom delta values to a single value using a line edit with validation."""
        # Create a custom dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Set All Delta Values")
        dialog.setModal(True)
        
        # Create layout
        layout = QVBoxLayout(dialog)
        
        # Add label
        label = QLabel("Enter delta value to use for all spectra:")
        layout.addWidget(label)
        
        # Add line edit with validator
        line_edit = QLineEdit("1.0")  # Default value
        validator = QDoubleValidator(0.0001, 1000.0, 6)  # Min, max, decimals
        validator.setNotation(QDoubleValidator.StandardNotation)
        line_edit.setValidator(validator)
        layout.addWidget(line_edit)
        
        # Add buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # Show dialog
        if dialog.exec_() == QDialog.Accepted:
            try:
                value = float(line_edit.text())
                
                # Temporarily block signals
                self.table.blockSignals(True)
                try:
                    for i in range(self.table.rowCount()):
                        # Only set value for rows that have valid data
                        if self.table.item(i, 1).text() != "N/A":
                            self.table.setItem(i, 3, QTableWidgetItem(f"{value:.6g}"))
                finally:
                    # Restore signals
                    self.table.blockSignals(False)
                    
                QMessageBox.information(
                    self,
                    "Values Updated",
                    f"All custom delta values have been set to {value:.6g}."
                )
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid Value",
                    "Please enter a valid number."
                )
    
    def get_delta_values(self):
        """Get custom delta values for each spectrum."""
        delta_values = {}
        
        for i in range(self.table.rowCount()):
            spectrum_name = self.table.item(i, 0).text()
            custom_delta_item = self.table.item(i, 3)
            
            if custom_delta_item and custom_delta_item.text() != "N/A":
                try:
                    delta = float(custom_delta_item.text())
                    delta_values[spectrum_name] = delta
                except ValueError:
                    # Use estimated value if conversion fails
                    estimated_item = self.table.item(i, 1)
                    if estimated_item and estimated_item.text() != "N/A":
                        try:
                            delta = float(estimated_item.text())
                            delta_values[spectrum_name] = delta
                        except ValueError:
                            pass
        
        return delta_values

class SavitzkyGolayDialog(QDialog):
    def __init__(self, parent=None, current_settings=None, controller=None,
                 selected_spectra=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Savitzky-Golay Filter Settings")
        self.setModal(True)
        self.current_settings = current_settings or {}
        self.controller = controller
        # Fixed snapshot of the spectra to filter, taken when the dialog
        # opened — safe because this dialog is modal, so the main window's
        # selection can't change underneath it while it's open.
        self.selected_spectra = list(selected_spectra or [])
        # Bound method (OperationsController.commit_sg_smoothing) passed in
        # by whatever opened this dialog, so Apply / Add as New can commit
        # the result directly, without a separate Run step.
        self.commit_callback = commit_callback
        
        # Initialize delta values from current settings if available
        if 'individual_delta_values' in self.current_settings:
            self.delta_values = self.current_settings['individual_delta_values']
        else:
            self.delta_values = {}
            
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Main parameter group
        param_group = QGroupBox("Filter Parameters")
        param_layout = QFormLayout()
        
        # Window length spinbox (must be odd)
        self.window_length_spinbox = QSpinBox()
        self.window_length_spinbox.setRange(3, 101)  # Reasonable range for SG filter
        self.window_length_spinbox.setSingleStep(2)  # Increment by 2 to keep odd values
        self.window_length_spinbox.setKeyboardTracking(False)
        # Set default value from settings or use 11
        default_window = self.current_settings.get('window_length', 11)
        # Ensure default is odd
        if default_window % 2 == 0:
            default_window += 1
        self.window_length_spinbox.setValue(default_window)
        
        # Force window length to be odd
        self.window_length_spinbox.valueChanged.connect(self._ensure_odd_window)
        
        param_layout.addRow("Window Length:", self.window_length_spinbox)
        
        # Polynomial order spinbox
        self.polyorder_spinbox = QSpinBox()
        self.polyorder_spinbox.setRange(1, 10)  # Reasonable range for polynomial order
        self.polyorder_spinbox.setValue(self.current_settings.get('polyorder', 3))
        self.polyorder_spinbox.setKeyboardTracking(False)
        param_layout.addRow("Polynomial Order:", self.polyorder_spinbox)
        
        # Connect for validation
        self.window_length_spinbox.valueChanged.connect(self._validate_polyorder)
        self.polyorder_spinbox.valueChanged.connect(self._validate_polyorder)
        
        # Add derivative settings
        deriv_group = QGroupBox("Derivative Settings")
        deriv_layout = QFormLayout()
        
        # Derivative order spinbox
        self.deriv_order_spinbox = QSpinBox()
        self.deriv_order_spinbox.setRange(0, 5)  # 0 = smoothing only, higher = derivatives
        self.deriv_order_spinbox.setValue(self.current_settings.get('deriv_order', 0))
        self.deriv_order_spinbox.setKeyboardTracking(False)
        deriv_layout.addRow("Derivative Order:", self.deriv_order_spinbox)
        
        # Connect for validation
        self.polyorder_spinbox.valueChanged.connect(self._validate_deriv_order)
        self.deriv_order_spinbox.valueChanged.connect(self._validate_deriv_order)
        
        # Add button for individual delta settings
        self.individual_delta_button = QPushButton("Set Individual Delta Values...")
        self.individual_delta_button.setToolTip("Set custom delta values for each spectrum")
        self.individual_delta_button.clicked.connect(self._show_individual_delta_dialog)
        deriv_layout.addRow("Delta Values:", self.individual_delta_button)
        
        # Edge handling mode dropdown
        self.mode_combo = QComboBox()
        modes = ['interp', 'constant', 'nearest', 'mirror', 'wrap']
        self.mode_combo.addItems(modes)
        current_mode = self.current_settings.get('mode', 'interp')
        if current_mode in modes:
            self.mode_combo.setCurrentText(current_mode)
        deriv_layout.addRow("Edge Mode:", self.mode_combo)
        
        # Set layouts for parameter groups
        param_group.setLayout(param_layout)
        deriv_group.setLayout(deriv_layout)
        
        # Add groups to main layout
        layout.addWidget(param_group)
        layout.addWidget(deriv_group)
        
        # Add info text
        info_label = QLabel(
            "Note: Savitzky-Golay filtering is a method of data smoothing based on local least-squares\n"
            "polynomial approximation. Increasing the window length increases smoothing. The polynomial\n"
            "order must be less than the window length. Derivative order = 0 performs smoothing only."
        )
        info_label.setStyleSheet("color: #1565C0;")  # Blue color
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)
        
        # Add delta info text
        delta_info = QLabel(
            "Delta is the spacing between points. For derivatives, it affects the scale of the result.\n"
            "For accurate differentiation, it should match the actual spacing in your data.\n"
            "Use 'Set Individual Delta Values' to customize delta for each spectrum."
        )
        delta_info.setStyleSheet("color: #1565C0;")  # Blue color
        delta_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(delta_info)
        
        # Show current status of individual delta values
        delta_status = QLabel()
        if self.delta_values:
            delta_status.setText(f"Custom delta values set for {len(self.delta_values)} spectra")
            delta_status.setStyleSheet("color: #388E3C;")  # Green color
        else:
            delta_status.setText("No custom delta values set")
            delta_status.setStyleSheet("color: #9E9E9E;")  # Gray color
        delta_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(delta_status)
        
        # Add button layout with help button (same style as normalization dialog)
        button_layout = QHBoxLayout()
        
        # Add help button
        self.help_button = QPushButton("Help")
        self.help_button.setAutoDefault(False)
        self.help_button.setDefault(False)
        self.help_button.clicked.connect(self.show_help)
        button_layout.addWidget(self.help_button)

        button_layout.addStretch()

        # Apply / Add as New commit directly via commit_callback — there's
        # no separate Run step in the main window for this operation
        # anymore (see OperationsController.commit_sg_smoothing).
        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip(
            "Replace the selected spectra with their smoothed result."
        )
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        button_layout.addWidget(self.apply_button)

        self.add_as_new_button = QPushButton("Add as New")
        self.add_as_new_button.setToolTip(
            "Keep the original spectra unchanged and add the smoothed "
            "results to the list under new names."
        )
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        button_layout.addWidget(self.add_as_new_button)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        # Initial validation
        self._validate_polyorder()
        self._validate_deriv_order()
    
    def _ensure_odd_window(self, value):
        """Ensure window length is always odd."""
        if value % 2 == 0:
            self.window_length_spinbox.setValue(value + 1)
    
    def _validate_polyorder(self):
        """Ensure polynomial order is less than window length."""
        window_length = self.window_length_spinbox.value()
        poly_max = window_length - 1
        
        # Update polyorder max value
        self.polyorder_spinbox.setMaximum(poly_max)
        
        # If current value exceeds max, reduce it
        if self.polyorder_spinbox.value() > poly_max:
            self.polyorder_spinbox.setValue(poly_max)
    
    def _validate_deriv_order(self):
        """Ensure derivative order is <= polynomial order."""
        polyorder = self.polyorder_spinbox.value()
        
        # Update derivative order max value
        self.deriv_order_spinbox.setMaximum(polyorder)
        
        # If current value exceeds max, reduce it
        if self.deriv_order_spinbox.value() > polyorder:
            self.deriv_order_spinbox.setValue(polyorder)

    def _show_individual_delta_dialog(self):
        """Show dialog for setting individual delta values.

        main_controller.sg_delta_values is the long-lived store — it has
        no selection-hash gate at all (it's meant to survive across
        different selections, that's the whole point), so it's kept keyed
        by unique_id (see SavitzkyGolayManager._key_for), not label.
        Without that, a rename would orphan a spectrum's custom delta value,
        and a re-imported spectrum that happens to reuse an old label
        would silently inherit someone else's. DeltaSettingsDialog itself
        stays label-based — it's a one-shot snapshot for this single
        sub-dialog session, so that's safe — this method is the seam that
        translates in both directions.
        """
        if not hasattr(self, 'controller') or not self.controller:
            return
                
        selected_spectra = self.controller.spectrum_selector.get_selected_spectra()
        if not selected_spectra:
            QMessageBox.information(
                self,
                "No Spectra Selected",
                "Please select at least one spectrum."
            )
            return
        
        # Get persistent delta values from the controller
        if not hasattr(self.controller, 'sg_delta_values'):
            self.controller.sg_delta_values = {}

        # Prune entries for spectra that no longer exist at all — otherwise
        # a newly imported spectrum that happens to reuse an old label
        # would be compared against stale, unrelated leftover values.
        if hasattr(self.controller, 'original_spectra'):
            current_keys = {SavitzkyGolayManager._key_for(s) for s in self.controller.original_spectra}
            for key in list(self.controller.sg_delta_values.keys()):
                if key not in current_keys:
                    del self.controller.sg_delta_values[key]

        # Resolve the persistent (key-based) store back to labels for
        # display in DeltaSettingsDialog, restricted to spectra actually
        # in this selection.
        key_to_label = {SavitzkyGolayManager._key_for(s): s['label'] for s in selected_spectra}
        controller_values_by_label = {
            key_to_label[k]: v for k, v in self.controller.sg_delta_values.items()
            if k in key_to_label
        }

        # Combine existing values from both sources
        # Priority: 1) dialog values, 2) controller values
        combined_values = {}
        combined_values.update(controller_values_by_label)  # Start with controller values
        combined_values.update(self.delta_values)  # Override with current dialog values
        
        # Pass the combined values to the dialog
        dialog = DeltaSettingsDialog(self, selected_spectra, combined_values)
        if dialog.exec_():
            # Store the custom delta values both locally and in controller
            new_values = dialog.get_delta_values()   # label-keyed
            self.delta_values = new_values
            
            # Translate back to unique_id-based keys before writing into
            # the persistent store.
            label_to_key = {s['label']: SavitzkyGolayManager._key_for(s) for s in selected_spectra}
            for label, value in new_values.items():
                key = label_to_key.get(label)
                if key is not None:
                    self.controller.sg_delta_values[key] = value
            
            # Update status label
            for child in self.children():
                if isinstance(child, QLabel) and child.text().startswith(("Custom delta values", "No custom delta")):
                    if self.delta_values:
                        child.setText(f"Custom delta values set for {len(self.delta_values)} spectra")
                        child.setStyleSheet("color: #388E3C;")  # Green color
                    else:
                        child.setText("No custom delta values set")
                        child.setStyleSheet("color: #9E9E9E;")  # Gray color
    
    def show_help(self):
        """Show help dialog when help button is clicked."""
        try:
            from src.help.sg_smoothing_help import (
                get_sg_smoothing_help_content,
                get_sg_smoothing_help_title
            )
            from src.help.help_window import show_help_window
            
            content = get_sg_smoothing_help_content()
            title = get_sg_smoothing_help_title()
            show_help_window(self, title, content)
        except Exception as e:
            logger.debug(f"Could not show help: {e}")
            QMessageBox.information(self, "Help", 
                                  "Help documentation is not available at this time.")
    
    # And modify the get_settings method to use the term "delta_values" instead of "individual_delta_values"
    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — commits directly via commit_callback. No
        separate Run step: feedback (success or failure) is shown right
        here next to the buttons that triggered it, instead of in a
        disconnected main-window message box. The dialog closes itself
        once the commit succeeds.
        """
        if self.commit_callback is None:
            QMessageBox.critical(
                self, "Not Available",
                "This dialog was opened without a way to apply changes. "
                "Please reopen it via Parameters."
            )
            return

        settings = self.get_settings()

        action = ("add the smoothed result as new spectra" if add_as_new
                  else "replace the selected spectra with their smoothed result")
        confirm = QMessageBox.question(
            self, "Confirm", f"{action[0].upper() + action[1:]}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(settings, add_as_new, list(self.selected_spectra))
        if success:
            QMessageBox.information(self, "Done", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Could Not Apply", message)

    def get_settings(self):
        """Get all settings from the dialog."""
        settings = {
            'window_length': self.window_length_spinbox.value(),
            'polyorder': self.polyorder_spinbox.value(),
            'deriv_order': self.deriv_order_spinbox.value(),
            'mode': self.mode_combo.currentText(),
            'delta_values': self.delta_values  # Changed from 'individual_delta_values'
        }
        
        # Add default delta (1.0) for backward compatibility
        settings['delta'] = 1.0
        
        return settings