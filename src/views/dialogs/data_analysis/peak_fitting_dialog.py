# src/views/dialogs/data_analysis/peak_fitting_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QDialogButtonBox, QLabel,
                             QWidget, QSplitter, QTableWidget, QTableWidgetItem,
                             QHeaderView, QComboBox, QMessageBox, QCheckBox, QRadioButton, QDoubleSpinBox,
                             QColorDialog, QAbstractItemView, QMenu, QApplication) # Added QMenu and QApplication
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont # Import QColor and QFont
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt # Import pyplot
# matplotlib's default color cycle is hex strings on older versions but
# RGB float tuples on newer ones (e.g. matplotlib 3.11). QColor() rejects a
# bare tuple, so normalize through to_hex() everywhere a peak color is
# turned into a QColor, both when it's first assigned and when displaying
# one that may have been saved by an older/different matplotlib version.
from matplotlib.colors import to_hex as _mpl_to_hex
import numpy as np

from src.modules.data_analysis.peak_fitting_manager import PeakFittingManager
# Import the help content functions
from src.help.peak_fitting_help import (get_peak_fitting_help_content,
                                        get_peak_fitting_help_title)
from src.help.help_window import show_help_window
from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

class PeakFittingDialog(QDialog):
    """Dialog for interactive peak fitting and deconvolution."""

    def __init__(self, parent=None, spectrum=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Peak Fitting & Deconvolution")
        self.setModal(True)
        self.spectrum = spectrum
        self.manager = PeakFittingManager()
        self.peaks = []  # Stores initial guesses
        self.fit_results = None # Stores parameters from a successful fit
        self.current_settings = current_settings or {}
        self.click_connection_id = None # To manage the click handler connection
        
        # Get the default matplotlib color cycle for new peaks
        self.colors = [_mpl_to_hex(color['color']) for color in plt.rcParams['axes.prop_cycle']]
        
        # Tracks the next color to use from the cycle
        self.peak_color_index = 0
        
        # Stores the user-defined width for 'Add via Click'
        self.initial_peak_width = None

        # These will be set to the full spectrum data
        self.x_roi = np.array([])
        self.y_roi = np.array([])

        self.setMinimumSize(1200, 800)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self.setup_ui()
        self.initialize_dialog()

    def setup_ui(self):
        """Creates and arranges all UI elements for the dialog."""
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)
        
        control_panel = self.create_control_panel()
        splitter.addWidget(control_panel)
        
        canvas_panel = self.create_canvas_panel()
        splitter.addWidget(canvas_panel)
        
        splitter.setSizes([560, 750])

    def create_control_panel(self):
        """Creates the left-hand control panel with all buttons and tables."""
        widget = QWidget()
        # setFixedWidth(450) used to sit here — it actively fights the
        # QSplitter above: dragging the handle right can never make this
        # panel any wider than the fixed value (nothing to give), and
        # dragging left doesn't shrink the panel's actual content either —
        # the layout inside still expects the fixed width, so anything
        # narrower just gets clipped (matching exactly what was reported:
        # dragging left just hides the Peaks to Fit groupbox and other
        # controls instead of reflowing them). A min/max range lets the
        # splitter actually resize it continuously in both directions.
        # The default width above (560, up from 450) is also why the table
        # columns were cropped — the 6-column table (Color, Model, Center,
        # Amplitude, Width, Extra) needs more room than 450px, especially
        # since adding Voigt/Pseudo-Voigt widened it from 5 columns to 6.
        widget.setMinimumWidth(380)
        widget.setMaximumWidth(750)
        layout = QVBoxLayout(widget)

        # --- Peaks Table ---
        peaks_group = QGroupBox("Peaks to Fit")
        peaks_layout = QVBoxLayout()
        self.peaks_table = QTableWidget()
        self.peaks_table.setColumnCount(6)
        self.peaks_table.setHorizontalHeaderLabels([" ", "Model", "Center", "Amplitude", "Width", "Extra"])
        self.peaks_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Make the first column (color swatch) narrow
        self.peaks_table.setColumnWidth(0, 20)
        self.peaks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        
        self.peaks_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.peaks_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        self.peaks_table.cellDoubleClicked.connect(self.on_color_cell_double_clicked)
        self.peaks_table.setToolTip("List of peaks for fitting.\n- Double-click a color swatch (col 1) to change it.\n- Select rows and press the Delete key to remove peaks.\n- 'Width' is σ for Gaussian/Voigt, γ for Lorentzian, or the shared FWHM for Pseudo-Voigt.\n- 'Extra' applies only to Voigt (γ) and Pseudo-Voigt (η, 0-1) — shown as '—' and disabled for other models.")
        
        peaks_layout.addWidget(self.peaks_table)

        # --- Peak Controls ---
        btn_layout1 = QHBoxLayout()
        
        self.auto_detect_btn = QPushButton("Auto-Detect Peaks")
        self.auto_detect_btn.setToolTip("Automatically find peaks in the current spectrum view.\nRight-click to set initial peak width.")
        self.auto_detect_btn.clicked.connect(self.auto_detect_peaks)
        # Add context menu for setting initial parameters
        self.auto_detect_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.auto_detect_btn.customContextMenuRequested.connect(self.show_auto_detect_context_menu)
        
        self.interactive_add_cb = QCheckBox("Add via Click")
        self.interactive_add_cb.setToolTip("When checked, click on the plot to add a new peak. Disables plot navigation.")
        self.interactive_add_cb.stateChanged.connect(self._toggle_interactive_add)
        
        btn_layout1.addWidget(self.auto_detect_btn)
        btn_layout1.addWidget(self.interactive_add_cb)
        peaks_layout.addLayout(btn_layout1)

        btn_layout2 = QHBoxLayout()
        remove_peak_btn = QPushButton("Remove Selected Peak(s)")
        remove_peak_btn.setToolTip("Remove all currently selected rows from the peak list.")
        remove_peak_btn.clicked.connect(self.remove_peak)
        
        clear_peaks_btn = QPushButton("Clear All Peaks")
        clear_peaks_btn.setToolTip("Clear all peaks from the list.")
        clear_peaks_btn.clicked.connect(self.clear_peaks)
        
        btn_layout2.addWidget(remove_peak_btn); btn_layout2.addWidget(clear_peaks_btn)
        peaks_layout.addLayout(btn_layout2)
        peaks_group.setLayout(peaks_layout)
        layout.addWidget(peaks_group)

        # --- Fitting Controls ---
        fit_group = QGroupBox("Fitting")
        fit_layout = QVBoxLayout()
        constraint_layout = QHBoxLayout()
        constraint_layout.addWidget(QLabel("Amplitude Constraint:"))
        self.amplitude_combo = QComboBox()
        self.amplitude_combo.addItems(["Unrestricted", "Positive Peaks Only", "Negative Peaks Only"])
        self.amplitude_combo.setToolTip("Constrain the fitting algorithm to find only positive, only negative, or unrestricted amplitude peaks.")
        constraint_layout.addWidget(self.amplitude_combo)
        constraint_layout.addStretch() # Fixes the gap
        fit_layout.addLayout(constraint_layout)

        fit_btn_layout = QHBoxLayout()
        self.fit_button = QPushButton("Fit Peaks")
        self.fit_button.setToolTip("Run the fitting algorithm to optimize peak parameters based on the current guesses.")
        self.fit_button.clicked.connect(self.perform_fit)
        
        self.copy_results_btn = QPushButton("Copy Results")
        self.copy_results_btn.setToolTip("Copy the peak parameters currently in the table to the clipboard.")
        self.copy_results_btn.setEnabled(False) # Disabled until peaks are added
        self.copy_results_btn.clicked.connect(self.copy_results_to_clipboard)
        
        fit_btn_layout.addWidget(self.fit_button)
        fit_btn_layout.addWidget(self.copy_results_btn)
        fit_layout.addLayout(fit_btn_layout)

        fit_group.setLayout(fit_layout)
        layout.addWidget(fit_group)
        
        # --- Output Options ---
        output_group = QGroupBox("Output Options (Adds New Spectra)")
        output_layout = QVBoxLayout()
        
        self.add_fit_check = QCheckBox("Add spectrum from total fit")
        self.add_fit_check.setToolTip("Adds a new spectrum generated from the total fitted curve (sum of all peaks).")
        
        self.add_residual_check = QCheckBox("Add spectrum from residual")
        self.add_residual_check.setToolTip("Adds a new spectrum generated from the residual (Original - Total Fit).")
        
        self.add_peaks_check = QCheckBox("Add new spectra from individual peaks")
        self.add_peaks_check.setToolTip("Adds each fitted component as a new, separate spectrum.")
        
        output_layout.addWidget(self.add_fit_check)
        output_layout.addWidget(self.add_residual_check)
        output_layout.addWidget(self.add_peaks_check)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        layout.addStretch()

        # --- Dialog Buttons (OK, Cancel, Help) ---
        button_box = QDialogButtonBox()
        
        self.help_button = QPushButton("Help")
        self.help_button.setToolTip("Show help for the Peak Fitting tool.")
        self.help_button.clicked.connect(self.show_help)
        button_box.addButton(self.help_button, QDialogButtonBox.HelpRole)

        button_box.addButton(QDialogButtonBox.Ok)
        button_box.addButton(QDialogButtonBox.Cancel)
        
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(True) # OK button is always enabled
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        return widget

    def show_auto_detect_context_menu(self, pos):
        """Show context menu for the Auto-Detect Peaks button."""
        context_menu = QMenu(self)
        
        # Add action to set initial peak width
        set_width_action = context_menu.addAction("Set Initial Peak Width...")
        
        # Show the menu and get the action
        action = context_menu.exec_(self.auto_detect_btn.mapToGlobal(pos))
        
        # Handle the action
        if action == set_width_action:
            self.show_initial_params_dialog()

    def show_initial_params_dialog(self):
        """
        Show a dialog to set the initial width for new peaks.
        """
        from PyQt5.QtWidgets import QInputDialog

        # Calculate a reasonable default width if not set, based on current view
        if hasattr(self, 'ax_main') and self.toolbar.mode == '':
            xmin, xmax = self.ax_main.get_xlim()
            default_width = abs((xmax - xmin) / 20.0)
            if default_width == 0: # Failsafe
                 default_width = abs((self.x_roi[-1] - self.x_roi[0]) / 20.0)
        else:
            default_width = abs((self.x_roi[-1] - self.x_roi[0]) / 20.0)

        # Use the currently stored width if it exists, otherwise use the calculated default
        current_val = self.initial_peak_width if self.initial_peak_width is not None else default_width

        new_width, ok = QInputDialog.getDouble(
            self,
            "Initial Peak Parameters",
            "Enter initial width (σ/γ) for new peaks:",
            value=current_val,
            decimals=4,
            min=1e-6
        )

        if ok and new_width:
            self.initial_peak_width = new_width    

    def create_canvas_panel(self):
        """Creates the right-hand panel with the plot canvas and toolbar."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.figure = Figure(tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, widget)
        
        # Connect our custom 'home' function to the toolbar's home button
        home_action = self.toolbar.actions()[0] # Home button is the first action
        home_action.triggered.disconnect() # Disconnect default
        home_action.triggered.connect(self.reset_roi_to_full_spectrum) # Connect custom
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        return widget

    def initialize_dialog(self):
        """Initializes the dialog state when it is first opened."""
        # This will set data, load settings, and call update_plot
        self.reset_roi_to_full_spectrum(load_settings=True)
        # Manually trigger the 'Add via Click' checkbox state
        self._toggle_interactive_add(self.interactive_add_cb.checkState())
        # Set the color index to follow any peaks loaded from settings
        self.peak_color_index = len(self.peaks)

    def load_settings(self):
        """Loads parameters from 'current_settings' when dialog is opened."""
        # Check if any settings (fit_results or initial_peaks) exist
        if self.current_settings and (self.current_settings.get('fit_results') or self.current_settings.get('initial_peaks')):
            
            # Load both lists (one might be empty or None)
            self.fit_results = self.current_settings.get('fit_results')
            self.peaks = self.current_settings.get('initial_peaks', [])

            # Check for data integrity (e.g., from old saves)
            # If # of fitted peaks doesn't match # of initial peaks, the data is corrupt
            if self.fit_results and len(self.fit_results) != len(self.peaks):
                # Data is out of sync. Discard fit_results and only load initial_peaks.
                self.fit_results = None 
            
            if self.fit_results: 
                # Path A: Data is valid and fitted. Load fitted results.
                # Ensure every peak has a color assigned
                for i, peak in enumerate(self.peaks):
                    if 'color' not in peak:
                        peak['color'] = self.colors[i % len(self.colors)]
                self.peak_color_index = len(self.peaks)

                self.update_peaks_table(from_fit_results=True)
                self.update_plot_with_fit_results()
                
            elif self.peaks:
                # Path B: No fit_results, or they were discarded. Load initial guesses.
                for i, peak in enumerate(self.peaks):
                    if 'color' not in peak:
                        peak['color'] = self.colors[i % len(self.colors)]
                self.peak_color_index = len(self.peaks)

                self.update_peaks_table() 
                self.update_plot()
            
            else:
                # No data at all, load plot defaults
                self.update_plot()
                
        else:
            # Default case: No settings existed at all
            self.amplitude_combo.setCurrentIndex(0)
            self.update_plot()
        
        # Enable copy button if the table will have data
        has_data = bool(self.peaks or self.fit_results)
        self.copy_results_btn.setEnabled(has_data)
            
        # Load output options (checkboxes)
        output_options = self.current_settings.get('output_options', {})
        self.add_fit_check.setChecked(output_options.get('add_fit', False))
        self.add_residual_check.setChecked(output_options.get('add_residual', False))
        self.add_peaks_check.setChecked(output_options.get('add_peaks', False))
            
        # Load constraint
        constraint = self.current_settings.get('amplitude_constraint', 'unrestricted')
        if constraint == 'positive': self.amplitude_combo.setCurrentIndex(1)
        elif constraint == 'negative': self.amplitude_combo.setCurrentIndex(2)
        else: self.amplitude_combo.setCurrentIndex(0)

        # Load persistent "Add via Click" state, defaulting to True
        add_via_click_state = self.current_settings.get('add_via_click', True) 
        self.interactive_add_cb.setChecked(add_via_click_state)

    def show_help(self):
        """Show the peak fitting help window."""
        content = get_peak_fitting_help_content()
        title = get_peak_fitting_help_title()
        show_help_window(self, title, content)

    def _toggle_interactive_add(self, state):
        """Enable/disable toolbar vs. click-to-add."""
        if state == Qt.Checked:
            # Connect the click handler
            if self.click_connection_id is None:
                self.click_connection_id = self.canvas.mpl_connect('button_press_event', self.on_canvas_click)
            # Disable the toolbar
            self.toolbar.mode = '' # Deactivate any active tool
            self.toolbar.setEnabled(False)
        else:
            # Disconnect the click handler
            if self.click_connection_id is not None:
                self.canvas.mpl_disconnect(self.click_connection_id)
                self.click_connection_id = None
            # Enable the toolbar
            self.toolbar.setEnabled(True)

    def on_canvas_click(self, event):
        """Handle clicks on the canvas to add a new peak."""
        # This handler is only connected when the "Add via Click" checkbox is checked
        if event.inaxes != self.ax_main or event.button != 1:
            return
        
        center, amplitude = event.xdata, event.ydata
        
        # Use the stored initial width
        width = self.initial_peak_width
        
        # Assign the next color in the cycle
        new_color = self.colors[self.peak_color_index % len(self.colors)]
        self.peak_color_index += 1
        
        # Add the new peak to our list of initial guesses
        self.peaks.append({'model': 'Gaussian', 'center': center, 'amplitude': amplitude, 'width': width, 'extra': width, 'color': new_color})
        
        # Invalidate any previous fit
        self.fit_results = None
        
        # Enable the copy button
        self.copy_results_btn.setEnabled(True)
        
        # Refresh UI
        self.update_peaks_table()
        self.update_plot()

    def reset_roi_to_full_spectrum(self, load_settings=False):
        """
        Resets the plot view to the full spectrum.
        If load_settings is True (on init), it also loads settings.
        If called from Home button, it just resets the view without clearing peaks.
        """
        # Set internal data to full spectrum
        self.x_roi = self.spectrum['x_scale']
        self.y_roi = self.spectrum['y_scale']

        # Set a default initial width if one isn't already set
        if self.initial_peak_width is None and len(self.x_roi) > 0:
            # Default width is 1/20th of the total x-axis range
            self.initial_peak_width = abs((self.x_roi[-1] - self.x_roi[0]) / 20.0)
        elif self.initial_peak_width is None:
            self.initial_peak_width = 1.0 # Failsafe

        if load_settings:
            # This path is only for initialize_dialog
            self.load_settings() # Loads settings and peaks
        
        # Reset plot view
        if hasattr(self, 'ax_main'):
            # Autoscale the axes to show the full range
            self.ax_main.autoscale(True)
            self.ax_residual.autoscale(True)
            self.canvas.draw()

    def auto_detect_peaks(self):
        """Automatically detects peaks and adds them to the list, skipping duplicates."""
        if len(self.y_roi) < 3: return
        
        # Run detection algorithm on the full spectrum
        detected_peaks = self.manager.auto_detect_peaks(self.y_roi, self.x_roi)
        
        # Get a list of centers for peaks already in the table
        existing_centers = [p['center'] for p in self.peaks]
        new_peaks_to_add = []
        
        # Start the color cycle from where the last peak left off
        self.peak_color_index = len(self.peaks)
        
        for peak in detected_peaks:
            # Check for duplicates based on center position
            # Use a tolerance of 50% of the new peak's width
            tolerance = abs(peak['width'] * 0.5) 

            is_duplicate = False
            for existing_center in existing_centers:
                if abs(peak['center'] - existing_center) < tolerance:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                # Assign a color
                new_color = self.colors[self.peak_color_index % len(self.colors)]
                peak['color'] = new_color
                self.peak_color_index += 1
                
                new_peaks_to_add.append(peak)
                existing_centers.append(peak['center']) # Add to list to avoid duplicates within this batch

        if not new_peaks_to_add:
            QMessageBox.information(self, "Auto-Detect", "No new peaks were detected.")
            return

        self.peaks.extend(new_peaks_to_add) # Add only the new, non-duplicate peaks
        self.fit_results = None # Invalidate previous fit
        self.copy_results_btn.setEnabled(bool(self.peaks)) # Enable copy button
        self.update_peaks_table()
        self.update_plot()    

    def remove_peak(self):
        """Remove selected peaks from the table."""

        # IMPORTANT: First, save any manual edits from the table to self.peaks
        # This prevents other peaks from reverting to old values
        for i in range(self.peaks_table.rowCount()):
            self.update_peak_from_table(i)

        selected_indices = self.peaks_table.selectionModel().selectedRows()
        
        if not selected_indices:
            # Fallback to current row if no multi-selection
            current_row = self.peaks_table.currentRow()
            if current_row < 0:
                return # Nothing selected
            rows_to_remove = [current_row]
        else:
            # Get unique row indices, sorted in reverse to avoid index shifting
            rows_to_remove = sorted(list(set(index.row() for index in selected_indices)), reverse=True)

        if not rows_to_remove:
            return
        
        # Remove peaks from self.peaks list
        for row in rows_to_remove:
            if 0 <= row < len(self.peaks):
                self.peaks.pop(row)
        
        # Invalidate the fit
        self.fit_results = None
        # Disable copy button only if the list is now empty
        self.copy_results_btn.setEnabled(bool(self.peaks)) 
        
        # Refresh UI
        self.update_peaks_table() 
        self.update_plot()

    def clear_peaks(self):
        """Removes all peaks from the table."""
        self.peaks.clear()
        self.fit_results = None
        self.copy_results_btn.setEnabled(False)
        self.peak_color_index = 0 # Reset color index
        self.update_peaks_table()
        self.update_plot()

    def _set_extra_cell(self, row, extra_key, value):
        """Populate the 'Extra' column for one row — editable with a value
        for models that have a 4th parameter (extra_key is 'gamma' or
        'eta'), disabled and blank for 3-parameter models where it
        doesn't apply (extra_key is None)."""
        if extra_key is None:
            item = QTableWidgetItem("—")
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setForeground(QColor("#999999"))
        else:
            item = QTableWidgetItem(f"{value:.4f}" if value is not None else "0.5000")
        self.peaks_table.setItem(row, 5, item)

    def update_peaks_table(self, from_fit_results=False):
        """Populates the table either from initial guesses (self.peaks) or fit results (self.fit_results)."""
        self.peaks_table.blockSignals(True)
        
        if from_fit_results and self.fit_results:
            # Populate table from fit_results
            self.peaks_table.setRowCount(len(self.fit_results))
            for i, peak_fit in enumerate(self.fit_results):
                model_name = peak_fit['model']
                params = peak_fit['parameters']
                width_key = 'sigma' if model_name == 'Gaussian' else ('fwhm' if model_name == 'Pseudo-Voigt' else 'gamma' if model_name == 'Lorentzian' else 'sigma')
                extra_key = {'Voigt': 'gamma', 'Pseudo-Voigt': 'eta'}.get(model_name)
            
                # Color Swatch (from self.peaks, which has the color)
                color_hex = self.peaks[i]['color']
                color_item = QTableWidgetItem()
                color_item.setBackground(QColor(_mpl_to_hex(color_hex)))
                color_item.setFlags(color_item.flags() & ~Qt.ItemIsEditable)
                self.peaks_table.setItem(i, 0, color_item)

                # Model
                model_combo = QComboBox()
                model_combo.addItems(self.manager.peak_models.keys())
                model_combo.setCurrentText(model_name)
                model_combo.currentIndexChanged.connect(lambda _, row=i: self.on_model_combo_changed(row))
                self.peaks_table.setCellWidget(i, 1, model_combo)
                
                # Parameters
                self.peaks_table.setItem(i, 2, QTableWidgetItem(f"{params['center']:.4f}"))
                self.peaks_table.setItem(i, 3, QTableWidgetItem(f"{params['height']:.4f}"))
                self.peaks_table.setItem(i, 4, QTableWidgetItem(f"{params.get(width_key, 0):.4f}"))
                self._set_extra_cell(i, extra_key, params.get(extra_key) if extra_key else None)
        else:
            # Populate table from self.peaks (initial guesses)
            self.peaks_table.setRowCount(len(self.peaks))
        
            for i, peak in enumerate(self.peaks):
                # Color Swatch
                color_hex = peak['color']
                color_item = QTableWidgetItem()
                color_item.setBackground(QColor(_mpl_to_hex(color_hex)))
                color_item.setFlags(color_item.flags() & ~Qt.ItemIsEditable)
                self.peaks_table.setItem(i, 0, color_item)

                # Model
                model_combo = QComboBox()
                model_combo.addItems(self.manager.peak_models.keys())
                model_combo.setCurrentText(peak['model'])
                model_combo.currentIndexChanged.connect(lambda _, row=i: self.on_model_combo_changed(row))
                self.peaks_table.setCellWidget(i, 1, model_combo)
                
                # Parameters
                self.peaks_table.setItem(i, 2, QTableWidgetItem(f"{peak['center']:.4f}"))
                self.peaks_table.setItem(i, 3, QTableWidgetItem(f"{peak['amplitude']:.4f}"))
                self.peaks_table.setItem(i, 4, QTableWidgetItem(f"{abs(peak['width']):.4f}"))
                extra_key = {'Voigt': 'gamma', 'Pseudo-Voigt': 'eta'}.get(peak['model'])
                self._set_extra_cell(i, extra_key, peak.get('extra'))
        
        self.peaks_table.blockSignals(False)
        # Re-connect the cellChanged signal
        try: self.peaks_table.cellChanged.disconnect(self.on_table_cell_changed)
        except TypeError: pass
        self.peaks_table.cellChanged.connect(self.on_table_cell_changed)

    def on_model_combo_changed(self, row):
        """Fired when a row's Model dropdown changes. Unlike a plain cell
        edit, this can change whether the row's 4th parameter (Extra
        column) applies at all — e.g. switching Gaussian -> Voigt means
        that column needs to go from disabled/blank to editable with a
        real value. A full table rebuild handles that; just re-reading
        the existing cells (as on_table_cell_changed does for ordinary
        text edits) would leave the Extra column showing its old
        disabled/blank state even though the new model needs a value.
        """
        if row >= len(self.peaks):
            return
        # Capture any unsaved edits to center/amplitude/width first, so
        # they aren't lost by the table rebuild below.
        self.update_peak_from_table(row)
        new_model = self.peaks_table.cellWidget(row, 1).currentText()
        self.peaks[row]['model'] = new_model
        # Give the new model a sensible default for its 4th parameter if
        # it has one and doesn't already have a stored value from before
        # (e.g. switching Voigt -> Pseudo-Voigt -> Voigt again keeps
        # whatever gamma was there; switching from a 3-parameter model
        # for the first time gets a neutral default).
        if new_model == 'Voigt' and self.peaks[row].get('extra') is None:
            self.peaks[row]['extra'] = abs(self.peaks[row]['width'])
        elif new_model == 'Pseudo-Voigt' and self.peaks[row].get('extra') is None:
            self.peaks[row]['extra'] = 0.5
        self.fit_results = None
        self.update_peaks_table()
        self.update_plot()

    def on_table_cell_changed(self):
        """Fired when user edits the table. This invalidates the 'fit'."""
        for i in range(self.peaks_table.rowCount()): 
            self.update_peak_from_table(i)
        self.fit_results = None
        self.update_plot()

    def on_color_cell_double_clicked(self, row, column):
        """Handle double-click on the color swatch cell to open color picker."""
        if column != 0 or row >= len(self.peaks):
            return # Not the color column or invalid row

        current_color_hex = self.peaks[row]['color']
        current_color = QColor(_mpl_to_hex(current_color_hex))
        
        new_color = QColorDialog.getColor(current_color, self, "Select Peak Color")
        
        if new_color.isValid() and new_color != current_color:
            new_color_hex = new_color.name()
            # Store the new color
            self.peaks[row]['color'] = new_color_hex
            # Update the table cell
            self.peaks_table.item(row, 0).setBackground(new_color)
            # Update the plot
            self.update_plot()

    def update_peak_from_table(self, row):
        """Reads values from a table row and saves them to self.peaks."""
        try:
            if row < len(self.peaks):
                # Column indices are shifted by 1 (col 0 is color)
                model_name = self.peaks_table.cellWidget(row, 1).currentText()
                self.peaks[row]['model'] = model_name
                self.peaks[row]['center'] = float(self.peaks_table.item(row, 2).text())
                self.peaks[row]['amplitude'] = float(self.peaks_table.item(row, 3).text())
                width_val = abs(float(self.peaks_table.item(row, 4).text()))
                self.peaks[row]['width'] = width_val

                extra_key = {'Voigt': 'gamma', 'Pseudo-Voigt': 'eta'}.get(model_name)
                if extra_key is not None:
                    extra_item = self.peaks_table.item(row, 5)
                    if extra_item is not None:
                        try:
                            self.peaks[row]['extra'] = float(extra_item.text())
                        except ValueError:
                            pass  # leave whatever was there before an invalid edit
                
                # Re-set the text in the table to ensure it's formatted correctly
                self.peaks_table.blockSignals(True)
                self.peaks_table.item(row, 4).setText(f"{width_val:.4f}")
                self.peaks_table.blockSignals(False)
        except (ValueError, AttributeError, IndexError, TypeError): 
            # Catch errors if user types invalid text
            pass 

    def perform_fit(self):
        """Runs the curve_fit optimization."""
        if not self.peaks: return
        
        # Ensure self.peaks is up-to-date with table
        for i in range(len(self.peaks)): 
            self.update_peak_from_table(i)
            
        constraint_map = {0: 'unrestricted', 1: 'positive', 2: 'negative'}
        constraint = constraint_map.get(self.amplitude_combo.currentIndex())
        
        # Fit using the full spectrum data
        fitted_results, y_fit_total = self.manager.fit_peaks(self.x_roi, self.y_roi, self.peaks, amplitude_constraint=constraint)
        
        if fitted_results is None:
            QMessageBox.warning(self, "Fit Failed", "The fitting algorithm could not converge.")
            self.copy_results_btn.setEnabled(bool(self.peaks)) # Keep button enabled
            return
            
        self.fit_results = fitted_results
        self.copy_results_btn.setEnabled(True) 
        self.update_peaks_table(from_fit_results=True) # Update table with fit results
        self.update_plot(y_fit_total=y_fit_total)

    def copy_results_to_clipboard(self):
        """Formats and copies the CURRENT peak parameters from the table to the clipboard."""
        if self.peaks_table.rowCount() == 0:
            QMessageBox.warning(self, "No Results", "There are no peaks in the table to copy.")
            return

        # Create a tab-separated string for easy pasting into Excel/PowerPoint
        header = "Peak\tModel\tCenter\tHeight\tWidth (σ/γ/FWHM)\tExtra (γ/η)\tFWHM\tArea\n"
        lines = [header]

        for i in range(self.peaks_table.rowCount()):
            try:
                # Read data directly from the table
                model = self.peaks_table.cellWidget(i, 1).currentText()
                center = float(self.peaks_table.item(i, 2).text())
                amplitude = float(self.peaks_table.item(i, 3).text())
                width = float(self.peaks_table.item(i, 4).text())

                extra_key = {'Voigt': 'gamma', 'Pseudo-Voigt': 'eta'}.get(model)
                extra_text = ""
                if extra_key is not None:
                    extra_item = self.peaks_table.item(i, 5)
                    extra_val = float(extra_item.text()) if extra_item is not None else 0.5
                    extra_text = f"{extra_val:.4f}"
                    params = [amplitude, center, width, extra_val]
                else:
                    params = [amplitude, center, width]

                # Calculate FWHM and Area via the manager — the same
                # calculation used everywhere else (get_peak_properties),
                # rather than a separate, duplicated copy of the same math
                # here that only covered Gaussian/Lorentzian and silently
                # reported 0.0/0.0 for any other model.
                props = self.manager.get_peak_properties(model, params)
                fwhm = props.get('fwhm', 0.0)
                area = props.get('area', 0.0)

                line = (
                    f"{i + 1}\t"
                    f"{model}\t"
                    f"{center:.4f}\t"
                    f"{amplitude:.4f}\t"
                    f"{width:.4f}\t"
                    f"{extra_text}\t"
                    f"{fwhm:.4f}\t"
                    f"{area:.4f}\n"
                )
                lines.append(line)
            
            except Exception as e:
                logger.error(f"Error reading table row {i}: {e}")
                # Skip row if data is invalid
                continue
        
        clipboard_text = "".join(lines)
        QApplication.clipboard().setText(clipboard_text)
        
        QMessageBox.information(self, "Results Copied",
                                f"Current parameters for {len(lines) - 1} peaks copied to clipboard.")    

    def _params_list_from_result_dict(self, model_name, params_dict):
        """Build the flat [amplitude, center, width, extra?] list a model
        function needs, from a fit-result-style parameters dict (which
        uses 'height' for amplitude and a model-specific key for the
        width/extra terms — see get_peak_properties)."""
        width_key = {'Gaussian': 'sigma', 'Lorentzian': 'gamma',
                     'Voigt': 'sigma', 'Pseudo-Voigt': 'fwhm'}.get(model_name, 'sigma')
        params = [params_dict['height'], params_dict['center'], params_dict[width_key]]
        extra_key = {'Voigt': 'gamma', 'Pseudo-Voigt': 'eta'}.get(model_name)
        if extra_key is not None:
            params.append(params_dict[extra_key])
        return params

    def _params_list_from_peak_guess(self, peak):
        """Build the flat [amplitude, center, width, extra?] list a model
        function needs, from an initial-guess dict (a self.peaks entry)."""
        params = [float(peak['amplitude']), float(peak['center']), abs(float(peak['width']))]
        extra_key = {'Voigt': 'gamma', 'Pseudo-Voigt': 'eta'}.get(peak['model'])
        if extra_key is not None:
            default = 0.5 if peak['model'] == 'Pseudo-Voigt' else abs(float(peak['width']))
            params.append(float(peak.get('extra', default) if peak.get('extra') is not None else default))
        return params

    def update_plot(self, y_fit_total=None):
        """Redraws the entire plot based on the current state."""
        self.figure.clear()
        gs = self.figure.add_gridspec(2, 1, height_ratios=[3, 1])
        self.ax_main = self.figure.add_subplot(gs[0])
        self.ax_residual = self.figure.add_subplot(gs[1], sharex=self.ax_main)
        
        if len(self.x_roi) > 0:
            # Plot original data
            self.ax_main.plot(self.x_roi, self.y_roi, 'o', color='gray', label='Original Data', markersize=3)
            y_total_model = np.zeros_like(self.x_roi)
            
            if self.fit_results and y_fit_total is not None:
                # --- STATE 1: Plotting a successful FIT ---
                self.ax_main.plot(self.x_roi, y_fit_total, 'r-', label='Total Fit', lw=2)
                y_total_model = y_fit_total
                for i, peak_fit in enumerate(self.fit_results):
                    model_name, params_dict = peak_fit['model'], peak_fit['parameters']
                    model_func, param_names = self.manager.peak_models[model_name]
                    params_for_func = self._params_list_from_result_dict(model_name, params_dict)
                    y_component = model_func(self.x_roi, *params_for_func)
                    
                    # Use the stored stable color from self.peaks
                    color = self.peaks[i]['color']
                    self.ax_main.plot(self.x_roi, y_component, ':', color=color, label=f'Peak {i+1} ({model_name})')
            else:
                # --- STATE 2: Plotting initial GUESSES ---
                for i, peak in enumerate(self.peaks):
                    try:
                        # Use the stored stable color
                        color = peak['color']
                        model_func, _ = self.manager.peak_models[peak['model']]
                        y_guess = model_func(self.x_roi, *self._params_list_from_peak_guess(peak))
                        self.ax_main.plot(self.x_roi, y_guess, '--', color=color)
                        y_total_model += y_guess
                    except (ValueError, TypeError): pass

            # Plot residual (Data - Model)
            residual = self.y_roi - y_total_model
            self.ax_residual.plot(self.x_roi, residual, color='purple')
            self.ax_residual.axhline(0, color='black', linestyle='--', lw=1)
        else:
             # No data loaded
             self.ax_main.text(0.5, 0.5, "No data to display", transform=self.ax_main.transAxes, ha='center', va='center')
             self.ax_residual.text(0.5, 0.5, "", transform=self.ax_residual.transAxes, ha='center', va='center')

        self.ax_residual.set_ylabel("Residual")
        self.ax_main.set_title(f"Peak Fit for: {self.spectrum['label']}")
        self.ax_main.set_ylabel("Intensity")
        self.ax_main.legend()
        self.ax_main.grid(True, alpha=0.5)
        self.ax_residual.set_xlabel("X-Axis")
        self.ax_residual.grid(True, alpha=0.5)
        
        self.canvas.draw()
        
    def update_plot_with_fit_results(self):
        """A special plot call just for loading settings that have a fit."""
        if not self.fit_results:
            self.update_plot() # Fallback to show initial guesses
            return

        all_params = []
        model_definitions = []
        for peak_fit in self.fit_results:
            model_name = peak_fit['model']
            param_dict = peak_fit['parameters']
            param_names = self.manager.peak_models[model_name][1]
            model_definitions.append((model_name, len(param_names)))
            all_params.extend(self._params_list_from_result_dict(model_name, param_dict))
        
        if all_params:
            y_fit_total = self.manager.multi_peak_model(self.x_roi, *all_params, model_definitions=model_definitions)
        else:
            y_fit_total = np.zeros_like(self.x_roi)

        self.update_plot(y_fit_total=y_fit_total)

    def get_results(self):
        """Formats and returns all settings to be saved in the operations controller."""
        # Get constraint
        constraint_map = {0: 'unrestricted', 1: 'positive', 2: 'negative'}
        constraint = constraint_map.get(self.amplitude_combo.currentIndex())

        results_to_return = []
        if self.fit_results:
            # If a fit has been performed, use the fit_results
            results_to_return = self.fit_results
        elif self.peaks: 
            # If no fit, but initial peaks exist, pass them
            for peak_guess in self.peaks:
                params_list = self._params_list_from_peak_guess(peak_guess)
                props = self.manager.get_peak_properties(peak_guess['model'], params_list)
                width_key = {'Gaussian': 'sigma', 'Lorentzian': 'gamma',
                             'Voigt': 'sigma', 'Pseudo-Voigt': 'fwhm'}.get(peak_guess['model'], 'sigma')
                result_params = {
                    'center': peak_guess['center'], 'height': peak_guess['amplitude'],
                    'fwhm': props.get('fwhm', 0), 'area': props.get('area', 0),
                    width_key: peak_guess['width']
                }
                extra_key = {'Voigt': 'gamma', 'Pseudo-Voigt': 'eta'}.get(peak_guess['model'])
                if extra_key is not None:
                    result_params[extra_key] = props.get(extra_key, params_list[3])
                results_to_return.append({
                    'model': peak_guess['model'],
                    'parameters': result_params
                })
        
        # Get the state of the new checkboxes
        add_fit = self.add_fit_check.isChecked()
        add_residual = self.add_residual_check.isChecked()
        add_peaks = self.add_peaks_check.isChecked()
        
        # self.peaks list contains the initial guesses AND the color
        
        return {
            'fit_results': results_to_return,
            'output_options': {
                'add_fit': add_fit,
                'add_residual': add_residual,
                'add_peaks': add_peaks
            },
            'initial_peaks': self.peaks, # Save the list with colors
            'amplitude_constraint': constraint,
            'add_via_click': self.interactive_add_cb.isChecked() # Save checkbox state
        }

    def keyPressEvent(self, event):
        """Handle key presses for deleting rows."""
        if event.key() == Qt.Key_Delete and self.peaks_table.hasFocus():
            self.remove_peak()
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """Clean up signal connections on close to prevent errors."""
        try:
            if self.click_connection_id is not None:
                self.canvas.mpl_disconnect(self.click_connection_id)
                self.click_connection_id = None
        except Exception:
            pass
        super().closeEvent(event)