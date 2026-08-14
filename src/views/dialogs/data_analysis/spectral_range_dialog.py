# src/views/dialogs/data_analysis/spectral_range_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QRadioButton,
                           QPushButton, QDialogButtonBox, QButtonGroup, QCheckBox, QLabel, 
                           QLineEdit, QGroupBox, QMessageBox, QSplitter, QWidget, QSizePolicy,
                           QListWidget, QListWidgetItem)
from PyQt5.QtGui import QDoubleValidator
from PyQt5.QtCore import Qt, pyqtSignal
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import make_shortened_name_delegate, make_shorten_names_checkbox
logger = get_logger(__name__)

class RangeDisplayDialog(QDialog):
    def __init__(self, ranges, spectrum_label, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Ranges for {spectrum_label}")
        self.setModal(True)
        self.ranges = ranges
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(['From', 'To'])
        
        # Populate table
        self.table.setRowCount(len(self.ranges))
        for i, (start, end) in enumerate(self.ranges):
            self.table.setItem(i, 0, QTableWidgetItem(f"{start:.6f}"))
            self.table.setItem(i, 1, QTableWidgetItem(f"{end:.6f}"))
        
        # Adjust column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        
        layout.addWidget(self.table)
        
        # Add close button
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

class SpectralRangePlotCanvas(FigureCanvas):
    range_selected = pyqtSignal(float, float)
    
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, tight_layout=True)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)
        
        self.axes.set_xlabel('X')
        self.axes.set_ylabel('Intensity')
        self.axes.grid(True)
        
        self.spectra_data = []
        self.range_spans = []  # Store multiple range spans
        self.legend_visible = True

        # Set externally by the dialog right after the NavigationToolbar is
        # created (see create_canvas_panel). Used to suppress click-drag
        # range selection while the toolbar's own Pan or Zoom tool is
        # active, since both are bound to the same left-mouse-drag gesture
        # and would otherwise both fire on every drag.
        self.toolbar = None
        
        # Range selection state
        self.selecting_range = False
        self.selection_start = None
        
        self.mpl_connect('button_press_event', self.on_click)
        self.mpl_connect('button_release_event', self.on_release)
        self.mpl_connect('motion_notify_event', self.on_mouse_move)
        
        self.fig.patch.set_facecolor('#f0f0f0')
        self.axes.set_facecolor('#ffffff')
        
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.updateGeometry()

    def _toolbar_navigation_active(self):
        """True while the NavigationToolbar's Pan or Zoom tool is engaged.
        NavigationToolbar2.mode is '' when neither is active, and a
        non-empty string (e.g. 'pan/zoom' or 'zoom rect') while one is."""
        return bool(self.toolbar is not None and self.toolbar.mode)
    
    def on_click(self, event):
        if event.inaxes != self.axes or not self.spectra_data:
            return
        if self._toolbar_navigation_active():
            # Let the toolbar's own Pan/Zoom handle this drag instead of
            # starting a range selection at the same time.
            return
        
        if event.button == 1:  # Left click
            # Start new selection
            self.selecting_range = True
            self.selection_start = event.xdata
    
    def on_release(self, event):
        if self._toolbar_navigation_active():
            self.selecting_range = False
            self.selection_start = None
            return

        if event.inaxes != self.axes or not self.spectra_data:
            self.selecting_range = False
            return
        
        if self.selecting_range and self.selection_start is not None:
            # Complete selection
            x_start = self.selection_start
            x_end = event.xdata
            
            x_min = min(x_start, x_end)
            x_max = max(x_start, x_end)
            
            if abs(x_max - x_min) > 1e-6:
                self.range_selected.emit(x_min, x_max)
        
        # Reset state
        self.selecting_range = False
        self.selection_start = None
    
    def on_mouse_move(self, event):
        if event.inaxes:
            parent = self.parent()
            if hasattr(parent, 'coordinates_label'):
                parent.coordinates_label.setText(f"(x, y) = ({event.xdata:.6g}, {event.ydata:.6g})")
        else:
            parent = self.parent()
            if hasattr(parent, 'coordinates_label'):
                parent.coordinates_label.setText("")
    
    def plot_spectra(self, spectra_list):
        self.axes.clear()
        self.spectra_data = spectra_list
        
        if not spectra_list:
            return
        
        colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']
        
        plotted_count = 0
        x_data_all = []
        
        for i, spectrum in enumerate(spectra_list):
            x = spectrum.get('x_scale', [])
            y = spectrum.get('y_scale', [])
            label = spectrum.get('label', f'Spectrum_{i}')
            
            if len(x) == 0 or len(y) == 0:
                continue
            
            try:
                x = np.asarray(x, dtype=float)
                y = np.asarray(y, dtype=float)
                
                color = colors[i % len(colors)]
                self.axes.plot(x, y, color=color, lw=1, label=label, alpha=0.8)
                plotted_count += 1
                
                x_data_all.extend(x)
                
            except Exception as e:
                continue
        
        if plotted_count == 0:
            self.axes.text(0.5, 0.5, 'No valid spectra to display', 
                          transform=self.axes.transAxes, ha='center', va='center',
                          fontsize=12, color='red')
        else:
            if len(spectra_list) == 1:
                self.axes.set_title(f"Spectrum: {spectra_list[0].get('label', 'Unknown')}")
            else:
                self.axes.set_title(f"Selected Spectra ({plotted_count} spectra)")
                
            self.axes.set_xlabel('X')
            self.axes.set_ylabel('Intensity')
            self.axes.grid(True, linestyle='--', alpha=0.7)
            
            if plotted_count > 1 and self.legend_visible:
                self.axes.legend(loc='best', fontsize='small')
            
            if x_data_all:
                x_min = np.min(x_data_all)
                x_max = np.max(x_data_all)
                padding = (x_max - x_min) * 0.02
                self.axes.set_xlim(x_min - padding, x_max + padding)
            
            self.axes.autoscale(axis='y')
            
        self.draw()

        # Re-baseline the toolbar's Home/Back/Forward stack to the view we
        # just drew. Without this, NavigationToolbar2 keeps treating the
        # very first plotted view (from when the toolbar was constructed)
        # as "home", so clicking Home after switching to a different
        # spectrum jumps back to that stale, unrelated view instead of
        # resetting the currently displayed spectrum/spectra.
        if self.toolbar is not None:
            self.toolbar.update()
    
    def set_legend_visible(self, visible):
        """Control legend visibility."""
        self.legend_visible = visible
        
        # Get current legend and remove it
        legend = self.axes.get_legend()
        if legend:
            legend.remove()
        
        # Add legend back if visible and we have multiple spectra
        if visible and len(self.spectra_data) > 1:
            self.axes.legend(loc='best', fontsize='small')
            
        self.draw()
    
    def update_range_display(self, ranges, is_exclude=False):
        """Update the display of all defined ranges.

        Include mode (is_exclude=False): spans shaded green.
        Exclude mode (is_exclude=True):  spans shaded red.
        """
        if not self.spectra_data:
            return

        # Clear existing range spans
        for span in self.range_spans:
            span.remove()
        self.range_spans.clear()

        color = '#d62728' if is_exclude else '#2ca02c'   # red=exclude, green=include

        # Add new range spans
        for x_min, x_max in ranges:
            if x_min < x_max:
                span = self.axes.axvspan(x_min, x_max, alpha=0.20, color=color)
                self.range_spans.append(span)

        self.draw()

class SpectralRangeDialog(QDialog):
    def __init__(self, parent=None, current_ranges=None, is_exclude_mode=False,
                 x_step=1.0, apply_linearization=False, x_min=None, x_max=None,
                 ranges_differ=False, steps_differ=False, limits_differ=False,
                 controller=None, selected_spectra=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Define Spectral Range")
        self.setModal(True)
        self.current_ranges = current_ranges or []
        self.is_exclude_mode = is_exclude_mode
        self.x_step = x_step
        self.x_min = x_min
        self.x_max = x_max
        self.ranges_differ = ranges_differ
        self.steps_differ = steps_differ
        self.limits_differ = limits_differ
        self.default_x_min = None  # Will be set by setup_reset_buttons
        self.default_x_max = None  # Will be set by setup_reset_buttons
        self.apply_linearization = apply_linearization
        self.spectral_range_controller = None
        self.controller = controller
        # Bound method (OperationsController.commit_data_range) passed in
        # by whatever opened this dialog, so Apply / Add as New can commit
        # the result directly, without a separate Run step.
        self.commit_callback = commit_callback

        # When a range in ranges_list_widget is selected, its bounds are
        # loaded into the From/To fields and this tracks which row is
        # being edited, so "Add" (relabeled "Update") updates that entry
        # in place instead of appending a duplicate.
        # None means "not currently editing an existing range" — same
        # pattern used by normalization_dialog.py's region editing.
        self._editing_range_row = None

        logger.debug(f"DEBUG: SpectralRangeDialog __init__ called")
        logger.debug(f"DEBUG: controller passed: {controller is not None}")
        logger.debug(f"DEBUG: selected_spectra passed: {selected_spectra is not None}")
        
        # Get spectra data for plotting - ENHANCED LOGIC
        if selected_spectra is not None:
            self.selected_spectra = selected_spectra
            logger.debug(f"DEBUG: Using provided selected_spectra: {len(selected_spectra)} spectra")
        elif controller is not None and hasattr(controller, 'spectrum_selector'):
            logger.debug(f"DEBUG: Getting spectra from controller.spectrum_selector")
            self.selected_spectra = controller.spectrum_selector.get_selected_spectra()
            logger.debug(f"DEBUG: Got {len(self.selected_spectra)} spectra from controller")
        elif controller is not None and hasattr(controller, 'selected_spectra'):
            logger.debug(f"DEBUG: Getting spectra from controller.selected_spectra")
            self.selected_spectra = controller.selected_spectra
            logger.debug(f"DEBUG: Got {len(self.selected_spectra)} spectra from controller.selected_spectra")
        elif controller is not None and hasattr(controller, 'original_spectra'):
            logger.debug(f"DEBUG: Getting spectra from controller.original_spectra")
            self.selected_spectra = controller.original_spectra
            logger.debug(f"DEBUG: Got {len(self.selected_spectra)} spectra from controller.original_spectra")
        else:
            logger.debug(f"DEBUG: No spectra source found, using empty list")
            self.selected_spectra = []
        
        logger.debug(f"DEBUG: Final selected_spectra count: {len(self.selected_spectra)}")
        
        self.setMinimumSize(900, 600)
        self.resize(1200, 800)
        
        # Set proper window flags: maximize and close only — minimize isn't
        # useful for a modal dialog and was disabled to match the other
        # refined operation dialogs.
        self.setWindowFlags(
            Qt.Dialog | 
            Qt.WindowCloseButtonHint | 
            Qt.WindowMaximizeButtonHint
        )
        
        # Enable resize grip for better user experience
        self.setSizeGripEnabled(True)
        
        self.setup_ui()
        
        # Initialize after UI is set up
        logger.debug(f"DEBUG: About to call initialize_dialog with {len(self.selected_spectra)} spectra")
        if self.selected_spectra:
            self.initialize_dialog()
        else:
            logger.debug("DEBUG: No spectra to initialize dialog with")

    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def initialize_dialog(self):
        """Initialize dialog with spectra selection and plotting."""
        logger.debug(f"DEBUG: initialize_dialog called with {len(self.selected_spectra)} spectra")
        
        if not self.selected_spectra:
            logger.debug("DEBUG: No spectra available for plotting")
            return
            
        self.populate_spectrum_list()
        
        # Select only the FIRST spectrum by default (like normalization dialog)
        if self.spectra_list.count() > 0:
            logger.debug(f"DEBUG: Selecting first spectrum from {self.spectra_list.count()} available")
            self.spectra_list.item(0).setSelected(True)
            self.on_spectrum_selection_changed()  # This will plot the first spectrum
        else:
            logger.debug("DEBUG: No items in spectra list")

    def setup_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)

        # Create control panel (left side)
        control_panel = self.create_control_panel()
        splitter.addWidget(control_panel)

        # Create canvas panel (right side)
        canvas_panel = self.create_canvas_panel()
        splitter.addWidget(canvas_panel)

        # Set splitter sizes - control panel smaller than plot
        splitter.setSizes([400, 800])

    def create_control_panel(self):
        control_widget = QWidget()
        # setFixedWidth(400) used to sit here — it actively fights the
        # QSplitter above: dragging the handle can never actually resize
        # this panel since Qt won't violate a fixed width. A min/max range
        # lets the splitter actually resize it (same fix already applied
        # to Normalization, Cosmic Ray Removal, X-axis Alignment, and Peak
        # Fitting's dialogs).
        control_widget.setMinimumWidth(340)
        control_widget.setMaximumWidth(700)
        layout = QVBoxLayout(control_widget)
        
        # Spectra Selection Group (similar to normalization dialog)
        spectra_group = QGroupBox("Selected Spectra")
        spectra_layout = QVBoxLayout(spectra_group)
        
        # Add informative message
        info_label = QLabel("💡 Selection is for viewing convenience only. Processing applies to all spectra loaded in the dialog.")
        info_label.setStyleSheet("color: #1976D2; font-style: italic; padding: 5px; background-color: #E3F2FD; border-radius: 3px; margin: 2px;")
        info_label.setWordWrap(True)
        spectra_layout.addWidget(info_label)
        
        header_layout = QHBoxLayout()
        spectra_label = QLabel("Selected:")
        header_layout.addWidget(spectra_label)
        
        self.sort_button = QPushButton("▲")
        self.sort_button.setToolTip("Toggle sort order")
        self.sort_button.setMaximumWidth(30)
        self.sort_button.clicked.connect(self.toggle_sort_order)
        header_layout.addWidget(self.sort_button)
        header_layout.addStretch()
        
        spectra_layout.addLayout(header_layout)
        
        from PyQt5.QtWidgets import QListWidget
        self.spectra_list = QListWidget()
        self.spectra_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.spectra_list.setStyleSheet("""
            QListWidget::item:selected {
                background-color: #4A7FC1;
                color: white;
            }
        """)
        self.spectra_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        # Display-only "shorten names" — item.text() (what selection
        # matching in on_spectrum_selection_changed reads) is untouched
        # by this paint-only delegate.
        self.spectra_list.setItemDelegate(
            make_shortened_name_delegate(self.spectra_list, self._shorten_names_enabled)
        )
        spectra_layout.addWidget(self.spectra_list)

        self.sort_ascending = True
        
        selection_buttons_layout = QHBoxLayout()
        
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(self.select_all_spectra)
        selection_buttons_layout.addWidget(self.select_all_button)
        
        self.unselect_all_button = QPushButton("Unselect All")
        self.unselect_all_button.clicked.connect(self.unselect_all_spectra)
        selection_buttons_layout.addWidget(self.unselect_all_button)
        
        # Add Show legend checkbox — hidden by default (many spectra clutter the legend)
        self.hide_legend_checkbox = QCheckBox("Show legend")
        self.hide_legend_checkbox.setChecked(False)
        self.hide_legend_checkbox.stateChanged.connect(self.on_legend_visibility_changed)
        selection_buttons_layout.addWidget(self.hide_legend_checkbox)

        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _: self.spectra_list.viewport().update()
        )
        selection_buttons_layout.addWidget(self.checkBox_shorten_names)

        spectra_layout.addLayout(selection_buttons_layout)
        self.spectra_list.itemSelectionChanged.connect(self.on_spectrum_selection_changed)
        layout.addWidget(spectra_group)
        
        # Add linearization options group
        linearization_group = QGroupBox("X-Scale Linearization")
        linearization_layout = QVBoxLayout()
        
        # Add warning label if steps differ
        if self.steps_differ:
            step_warning = QLabel(
                "Selected spectra have different linearization steps. "
                "Defining a new step will apply to all selected spectra."
            )
            step_warning.setStyleSheet("color: #4CAF50;")  # Green color
            step_warning.setWordWrap(True)
            linearization_layout.addWidget(step_warning)
        
        # Checkbox for applying linearization
        self.apply_linearization_cb = QCheckBox("Apply linearization")
        self.apply_linearization_cb.setChecked(self.apply_linearization)
        linearization_layout.addWidget(self.apply_linearization_cb)
        
        # X-step input with numeric validator
        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("X-step:"))
        self.x_step_edit = QLineEdit()
        self.x_step_edit.setValidator(QDoubleValidator())
        self.x_step_edit.setText(str(self.x_step))
        self.x_step_edit.setEnabled(self.apply_linearization)
        step_layout.addWidget(self.x_step_edit)
        linearization_layout.addLayout(step_layout)
        
        linearization_group.setLayout(linearization_layout)
        layout.addWidget(linearization_group)
        
        # Add x-scale range group
        range_group = QGroupBox("X-Scale Range")
        range_layout = QVBoxLayout()
        
        # Add warning label if limits differ
        if self.limits_differ:
            limits_warning = QLabel(
                "Selected spectra have different x-scale limits. "
                "Defining a new x-scale range will apply to all selected spectra."
            )
            limits_warning.setStyleSheet("color: #4CAF50;")  # Green color
            limits_warning.setWordWrap(True)
            range_layout.addWidget(limits_warning)
        
        # X-min input with reset button
        xmin_layout = QHBoxLayout()
        xmin_layout.addWidget(QLabel("X-min:"))
        self.x_min_edit = QLineEdit()
        self.x_min_edit.setValidator(QDoubleValidator())
        if self.x_min is not None:
            self.x_min_edit.setText(str(self.x_min))
        self.x_min_reset = QPushButton("Reset")
        self.x_min_reset.setToolTip("Reset to common intersection of selected spectra (or full combined range if they don't overlap)")
        xmin_layout.addWidget(self.x_min_edit)
        xmin_layout.addWidget(self.x_min_reset)
        range_layout.addLayout(xmin_layout)
        
        # X-max input with reset button
        xmax_layout = QHBoxLayout()
        xmax_layout.addWidget(QLabel("X-max:"))
        self.x_max_edit = QLineEdit()
        self.x_max_edit.setValidator(QDoubleValidator())
        if self.x_max is not None:
            self.x_max_edit.setText(str(self.x_max))
        self.x_max_reset = QPushButton("Reset")
        self.x_max_reset.setToolTip("Reset to common intersection of selected spectra (or full combined range if they don't overlap)")
        xmax_layout.addWidget(self.x_max_edit)
        xmax_layout.addWidget(self.x_max_reset)
        range_layout.addLayout(xmax_layout)
        
        range_group.setLayout(range_layout)
        layout.addWidget(range_group)

        # Add mode selection
        mode_group = QGroupBox("Range Mode")
        mode_layout = QVBoxLayout()
        
        mode_group_buttons = QButtonGroup(self)
        button_layout = QHBoxLayout()
        
        self.include_radio = QRadioButton("Include Ranges")
        self.exclude_radio = QRadioButton("Exclude Ranges")
        self.include_radio.setChecked(not self.is_exclude_mode)
        self.exclude_radio.setChecked(self.is_exclude_mode)
        
        mode_group_buttons.addButton(self.include_radio)
        mode_group_buttons.addButton(self.exclude_radio)

        self.include_radio.toggled.connect(self.update_plot_ranges)
        
        button_layout.addWidget(self.include_radio)
        button_layout.addWidget(self.exclude_radio)
        mode_layout.addLayout(button_layout)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        # Add warning label if ranges differ
        if self.ranges_differ:
            warning_label = QLabel(
                "Selected spectra have different ranges defined. "
                "Defining new ranges will apply to all selected spectra."
            )
            warning_label.setStyleSheet("color: #4CAF50;")  # Green color
            warning_label.setWordWrap(True)
            layout.addWidget(warning_label)
        
        # Create interval input — spinbox + list approach (no table)
        table_group = QGroupBox("Defined Ranges")
        table_layout = QVBoxLayout()
        table_layout.setSpacing(4)
        table_layout.setContentsMargins(6, 6, 6, 6)

        # Info label — keep it tight
        info_label = QLabel("\u2192 Click and drag on the plot to select ranges, or enter values manually below.")
        info_label.setStyleSheet(
            "color: #1976D2; font-style: italic; padding: 2px 4px; "
            "background-color: #E3F2FD; border-radius: 3px;"
        )
        info_label.setWordWrap(True)
        info_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        table_layout.addWidget(info_label)

        # Ranges list widget — expands to fill available space
        from PyQt5.QtWidgets import QListWidget
        self.ranges_list_widget = QListWidget()
        # ExtendedSelection so Ctrl/Shift-click can select several ranges
        # at once for bulk removal (see remove_selected_row). Editing a
        # single range (populating From/To, switching Add -> Update)
        # only activates when exactly one row is selected — see
        # _on_range_item_selected.
        self.ranges_list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.ranges_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ranges_list_widget.setToolTip(
            "Defined ranges — select a row to edit its values below.\n"
            "Ctrl/Shift-click to select more than one for Remove."
        )
        self.ranges_list_widget.itemSelectionChanged.connect(self._on_range_item_selected)
        table_layout.addWidget(self.ranges_list_widget, stretch=1)

        # Manual entry row — "From" / "To", consistent with the Band
        # Ratio / 2D map range dialog. The two values don't need to be
        # entered in any particular order; see _add_interval_manual() below.
        entry_row = QHBoxLayout()
        entry_row.addWidget(QLabel("From:"))
        self.range_from_edit = QLineEdit()
        self.range_from_edit.setValidator(QDoubleValidator())
        self.range_from_edit.setPlaceholderText("e.g. 800")
        entry_row.addWidget(self.range_from_edit)
        entry_row.addWidget(QLabel("To:"))
        self.range_to_edit = QLineEdit()
        self.range_to_edit.setValidator(QDoubleValidator())
        self.range_to_edit.setPlaceholderText("e.g. 1800")
        entry_row.addWidget(self.range_to_edit)
        table_layout.addLayout(entry_row)

        # Buttons
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add")
        self.add_button.setToolTip("Add the From/To values above as a new range (in either order).\n"
                                   "Drag on the plot to add ranges without using this button.")
        button_layout.addWidget(self.add_button)
        # Cancel edit sits right next to Add/Update — while editing, this
        # is the button you actually reach for, not something at the far
        # end of the row past Remove. Only shown while a range is
        # selected (i.e. while add_button reads "Update"). QListWidget
        # does not reliably clear its selection when clicking empty space
        # below the items, so an explicit way out of edit mode is needed
        # rather than relying on it.
        self.cancel_edit_button = QPushButton("Cancel edit")
        self.cancel_edit_button.setToolTip("Deselect the range and go back to adding a new one.")
        self.cancel_edit_button.setVisible(False)
        button_layout.addWidget(self.cancel_edit_button)
        # Only one removal control — Remove (with Ctrl/Shift-click
        # multi-select) covers both single- and select-all-then-remove
        # cases, so a separate "Clear All" that does the same thing has
        # been dropped (matches the FFT denoising dialog's stop-bands list).
        self.remove_button = QPushButton("Remove")
        self.remove_button.setToolTip(
            "Remove the selected range(s).\nCtrl/Shift-click ranges in the list to select more than one,\n"
            "or Ctrl+A in the list to select all of them."
        )
        button_layout.addWidget(self.remove_button)

        # Small orange "?" button — short context help, same style as the
        # Legend "?" button next to the main window's plot controls.
        self.ranges_help_button = QPushButton("?")
        self.ranges_help_button.setFixedWidth(24)
        self.ranges_help_button.setToolTip(
            "Quick help for adding, editing and removing ranges."
        )
        self.ranges_help_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #F57C00;"
            "  color: white;"
            "  border: none;"
            "  border-radius: 4px;"
            "  font-weight: bold;"
            "  padding: 2px;"
            "}"
            "QPushButton:hover { background-color: #E65100; }"
            "QPushButton:pressed { background-color: #BF360C; }"
        )
        self.ranges_help_button.clicked.connect(self._show_ranges_quick_help)
        button_layout.addWidget(self.ranges_help_button)
        table_layout.addLayout(button_layout)

        table_group.setLayout(table_layout)
        table_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout.addWidget(table_group, stretch=1)
        
        # Add button layout: Help on the left, Apply / Add as New / Close
        # on the right — these commit directly via commit_callback instead
        # of going through QDialog's accept(), since there's no separate
        # Run step for this operation in the main window any more (see
        # OperationsController.commit_data_range).
        dialog_button_layout = QHBoxLayout()

        # Add help button
        self.help_button = QPushButton("Help")
        self.help_button.setAutoDefault(False)
        self.help_button.setDefault(False)
        self.help_button.clicked.connect(self.show_help)
        dialog_button_layout.addWidget(self.help_button)

        dialog_button_layout.addStretch()

        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip(
            "Replace the selected spectra with the range-restricted result."
        )
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        dialog_button_layout.addWidget(self.apply_button)

        self.add_as_new_button = QPushButton("Add as New")
        self.add_as_new_button.setToolTip(
            "Keep the original spectra unchanged and add the range-restricted "
            "results to the list under new names."
        )
        self.add_as_new_button.setAutoDefault(False)
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        dialog_button_layout.addWidget(self.add_as_new_button)

        self.close_button = QPushButton("Close")
        self.close_button.setAutoDefault(False)
        self.close_button.clicked.connect(self.reject)
        dialog_button_layout.addWidget(self.close_button)

        layout.addLayout(dialog_button_layout)
        
        # Connect signals
        self.add_button.clicked.connect(self._add_interval_manual)
        self.remove_button.clicked.connect(self.remove_selected_row)
        self.cancel_edit_button.clicked.connect(self._cancel_range_edit)
        self.apply_linearization_cb.stateChanged.connect(self._handle_linearization_state)
        
        # Initialize plot and populate spectra list - this will be done in initialize_dialog()
        
        return control_widget
    
    def create_canvas_panel(self):
        canvas_widget = QWidget()
        layout = QVBoxLayout(canvas_widget)
        
        # Create matplotlib canvas
        self.canvas = SpectralRangePlotCanvas(self)
        self.toolbar = NavigationToolbar(self.canvas, canvas_widget)
        # Give the canvas a reference to its own toolbar — see
        # SpectralRangePlotCanvas._toolbar_navigation_active() and
        # plot_spectra() for why.
        self.canvas.toolbar = self.toolbar
        
        # Add helpful instruction label above the plot
        instruction_label = QLabel("💡 Click and drag on the plot to select spectral ranges. Selected ranges will be added to the table automatically.")
        instruction_label.setStyleSheet(
            "color: #1976D2; font-style: italic; padding: 5px; "
            "background-color: #E3F2FD; border-radius: 3px; margin: 2px;"
        )
        instruction_label.setAlignment(Qt.AlignCenter)
        instruction_label.setWordWrap(True)
        
        # Coordinates label
        self.coordinates_label = QLabel("")
        self.coordinates_label.setStyleSheet("background-color: #f0f0f0; padding: 2px;")
        
        layout.addWidget(self.toolbar)
        layout.addWidget(instruction_label)
        layout.addWidget(self.coordinates_label)
        layout.addWidget(self.canvas)
        
        # Connect range selection signal
        self.canvas.range_selected.connect(self.on_range_selected)
        
        return canvas_widget
    
    def populate_spectrum_list(self):
        """Populate the spectra list widget."""
        logger.debug(f"DEBUG: populate_spectrum_list called with {len(self.selected_spectra)} spectra")
        
        self.spectra_list.clear()
        self.list_to_spectra_map = {}
        
        sorted_spectra = sorted(self.selected_spectra, key=lambda x: x.get('label', 'Unknown'))
        
        for i, spectrum in enumerate(sorted_spectra):
            label = spectrum.get('label', f'Spectrum_{i}')
            logger.debug(f"DEBUG: Adding spectrum {i}: {label}")
            from PyQt5.QtWidgets import QListWidgetItem
            item = QListWidgetItem(label)
            self.spectra_list.addItem(item)
            self.list_to_spectra_map[i] = spectrum
            
        logger.debug(f"DEBUG: Added {self.spectra_list.count()} items to spectra list")
    
    def select_all_spectra(self):
        """Select all spectra in the list."""
        self.spectra_list.blockSignals(True)
        try:
            for i in range(self.spectra_list.count()):
                item = self.spectra_list.item(i)
                item.setSelected(True)
        finally:
            self.spectra_list.blockSignals(False)
        
        self.on_spectrum_selection_changed()
    
    def unselect_all_spectra(self):
        """Unselect all spectra in the list."""
        self.spectra_list.blockSignals(True)
        try:
            for i in range(self.spectra_list.count()):
                item = self.spectra_list.item(i)
                item.setSelected(False)
        finally:
            self.spectra_list.blockSignals(False)
        
        self.on_spectrum_selection_changed()
    
    def toggle_sort_order(self):
        """Toggle the sort order of spectra list."""
        self.sort_ascending = not self.sort_ascending
        self.sort_button.setText("▲" if self.sort_ascending else "▼")
        self.sort_spectra_list()
    
    def sort_spectra_list(self):
        """Sort the spectra list."""
        selected_labels = [item.text() for item in self.spectra_list.selectedItems()]
        
        self.spectra_list.clear()
        self.list_to_spectra_map = {}
        
        sorted_spectra = sorted(
            self.selected_spectra, 
            key=lambda x: x.get('label', 'Unknown'),
            reverse=not self.sort_ascending
        )
        
        for index, spectrum in enumerate(sorted_spectra):
            label = spectrum.get('label', f'Spectrum_{index}')
            from PyQt5.QtWidgets import QListWidgetItem
            item = QListWidgetItem(label)
            self.spectra_list.addItem(item)
            self.list_to_spectra_map[index] = spectrum
            
            if label in selected_labels:
                item.setSelected(True)
    
    def on_spectrum_selection_changed(self):
        """Handle spectrum selection changes and update plot."""
        logger.debug("DEBUG: on_spectrum_selection_changed called")
        selected_items = self.spectra_list.selectedItems()
        logger.debug(f"DEBUG: {len(selected_items)} items selected")
        
        selected_spectra = []
        for item in selected_items:
            label = item.text()
            logger.debug(f"DEBUG: Looking for spectrum with label: {label}")
            for i, mapped_spectrum in self.list_to_spectra_map.items():
                if mapped_spectrum.get('label') == label:
                    selected_spectra.append(mapped_spectrum)
                    logger.debug(f"DEBUG: Found matching spectrum: {label}")
                    # Debug spectrum data
                    x_data = mapped_spectrum.get('x_scale', [])
                    y_data = mapped_spectrum.get('y_scale', [])
                    logger.debug(f"DEBUG: Spectrum data - x: {len(x_data)} points, y: {len(y_data)} points")
                    if len(x_data) > 0:
                        logger.debug(f"DEBUG: X range: {min(x_data):.3f} to {max(x_data):.3f}")
                    if len(y_data) > 0:
                        logger.debug(f"DEBUG: Y range: {min(y_data):.3f} to {max(y_data):.3f}")
                    break
        
        logger.debug(f"DEBUG: Total selected spectra for plotting: {len(selected_spectra)}")
        
        # Update plot with selected spectra
        if selected_spectra:
            logger.debug("DEBUG: Calling canvas.plot_spectra()")
            self.canvas.plot_spectra(selected_spectra)
            # Update range display if ranges are defined
            ranges = self.get_ranges()
            if ranges:
                logger.debug(f"DEBUG: Updating range display with {len(ranges)} ranges")
                self.canvas.update_range_display(ranges, is_exclude=self.exclude_radio.isChecked())
        else:
            logger.debug("DEBUG: No spectra to plot, clearing canvas")
            self.canvas.plot_spectra([])
        
        # Apply current legend visibility setting
        self.canvas.set_legend_visible(self.hide_legend_checkbox.isChecked())
    
    def on_legend_visibility_changed(self, state):
        """Handle legend visibility checkbox change."""
        self.canvas.set_legend_visible(state == Qt.Checked)
    
    def on_range_selected(self, x_min, x_max):
        """Handle range selection from plot canvas — add immediately, no button press needed."""
        if x_max <= x_min:
            return
        x0, x1 = round(x_min, 4), round(x_max, 4)
        # Mirror values into the manual entry fields so the user can see what was captured
        self.range_from_edit.setText(str(x0))
        self.range_to_edit.setText(str(x1))
        # Dragging always adds a brand-new range, never edits an existing
        # one in place — exit edit mode first so a stale _editing_range_row
        # from a previously selected range can't get silently overwritten.
        self._exit_range_edit_mode()
        self._append_range(x0, x1)

    def _add_interval_manual(self):
        """Add interval from the manual From / To entry fields — or,
        if a range is currently selected in ranges_list_widget
        (self._editing_range_row set by _on_range_item_selected), update
        that range in place instead. The button itself is relabeled
        "Update" while editing, so this single slot covers both cases.

        The two limits can be entered in either order — they're normalized
        (smaller, larger) here rather than requiring From < To, since
        which physical boundary the user thinks of as "first" has no real
        meaning for the range itself.
        """
        try:
            a = float(self.range_from_edit.text())
            b = float(self.range_to_edit.text())
        except ValueError:
            return
        x0, x1 = min(a, b), max(a, b)
        if x1 <= x0:
            return
        row = self._editing_range_row
        if row is not None and 0 <= row < self.ranges_list_widget.count():
            self._update_range_at(row, x0, x1)
        else:
            self._append_range(x0, x1)

    def _update_range_at(self, row, x0, x1):
        """Update the range at `row` in place with (x0, x1), same exact-
        value storage convention as _append_range (see its docstring).

        If (x0, x1) exactly matches another existing range, that range is
        selected instead of creating a duplicate — same behavior as
        _append_range and as the Band Ratio / 2D map range dialog."""
        for i in range(self.ranges_list_widget.count()):
            if i == row:
                continue
            stored = self.ranges_list_widget.item(i).data(Qt.UserRole)
            if stored is not None and abs(stored[0] - x0) < 1e-12 and abs(stored[1] - x1) < 1e-12:
                self.ranges_list_widget.setCurrentRow(i)
                return
        label = f"{x0:.6g} – {x1:.6g}"
        item = self.ranges_list_widget.item(row)
        item.setText(label)
        item.setData(Qt.UserRole, (x0, x1))
        self.update_plot_ranges()

    def _append_range(self, x0, x1):
        """Internal: add (x0, x1) to the list and refresh.

        The exact values are stored via item.setData(Qt.UserRole, ...) —
        the visible text is a rounded label for readability only (4
        significant figures) and must never be parsed back as the source
        of truth. It used to be: get_ranges() re-parsed this same rounded
        text, so a range typed as 1000.654321 - 1800.123456 was silently
        applied as 1001 - 1800. The duplicate-avoidance check below
        compares the exact stored values for the same reason — comparing
        rounded labels could treat two genuinely different ranges as
        duplicates just because they rounded to the same display text.

        Adding a range that exactly matches an existing one selects that
        existing row instead of creating a copy.
        """
        for i in range(self.ranges_list_widget.count()):
            stored = self.ranges_list_widget.item(i).data(Qt.UserRole)
            if stored is not None and abs(stored[0] - x0) < 1e-12 and abs(stored[1] - x1) < 1e-12:
                self.ranges_list_widget.setCurrentRow(i)
                return
        label = f"{x0:.6g} \u2013 {x1:.6g}"
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, (x0, x1))
        self.ranges_list_widget.addItem(item)
        self.update_plot_ranges()

    def _on_range_item_selected(self):
        """Populate the From / To fields when a range row is selected,
        and switch "Add" into "Update" mode (with a "Cancel edit" button
        appearing alongside it).

        Editing only activates when EXACTLY one range is selected — with
        several selected (for bulk Remove) there's no single range for
        From/To/Update to mean anything about.

        Reads the exact stored values (Qt.UserRole), not the rounded
        display text — otherwise re-selecting a range to tweak it would
        silently start from an already-rounded number instead of what was
        actually applied.
        """
        items = self.ranges_list_widget.selectedItems()
        if len(items) != 1:
            self._exit_range_edit_mode()
            return
        row = self.ranges_list_widget.row(items[0])
        stored = items[0].data(Qt.UserRole)
        if stored is not None:
            self.range_from_edit.setText(str(stored[0]))
            self.range_to_edit.setText(str(stored[1]))
        else:
            # Defensive fallback for any item that somehow lacks stored data
            # (e.g. constructed by older/external code before this fix).
            text = items[0].text()
            try:
                parts = text.split('\u2013')
                self.range_from_edit.setText(parts[0].strip())
                self.range_to_edit.setText(parts[1].strip())
            except (IndexError, ValueError):
                pass
        self._editing_range_row = row
        self.add_button.setText('Update')
        self.add_button.setToolTip(
            'Update the selected range with the From / To values above.'
        )
        self.cancel_edit_button.setVisible(True)

    def _cancel_range_edit(self):
        """Explicitly leave edit mode without removing or changing the
        selected range \u2014 used by the 'Cancel edit' button, since clicking
        empty space in the list does not reliably clear its selection."""
        self.ranges_list_widget.clearSelection()
        self._exit_range_edit_mode()

    def _exit_range_edit_mode(self):
        self._editing_range_row = None
        self.add_button.setText('Add')
        self.add_button.setToolTip(
            "Add the From/To values above as a new range (in either order).\n"
            "Drag on the plot to add ranges without using this button."
        )
        self.cancel_edit_button.setVisible(False)

    def _show_ranges_quick_help(self):
        """Short popup covering the add/edit/remove workflow for this list —
        the full Help button opens the whole dialog's help page, this is
        the quick version right next to the buttons it explains."""
        QMessageBox.information(
            self,
            "Quick help — ranges",
            "<b>Add a range</b> by typing From/To and clicking Add, or by "
            "dragging directly on the plot.<br><br>"
            "<b>Edit a range</b> by selecting it in the list — the From/To "
            "fields fill in and Add becomes Update. Click Update to save "
            "your changes, or Cancel edit to leave without changing "
            "anything.<br><br>"
            "<b>Remove ranges</b> by selecting one or more (Ctrl/Shift-click, "
            "or Ctrl+A for all) and clicking Remove.<br><br>"
            "Adding or updating to values that exactly match an existing "
            "range selects that range instead of creating a duplicate."
        )

    def update_plot_ranges(self):
        """Update the plot to show all defined ranges with the correct colour."""
        ranges = self.get_ranges()
        is_exclude = self.exclude_radio.isChecked()
        self.canvas.update_range_display(ranges, is_exclude=is_exclude)

    def load_existing_ranges(self):
        """Load existing ranges into the list widget."""
        for start, end in self.current_ranges:
            self._append_range(start, end)
        self.update_plot_ranges()

    def add_row(self, start=None, end=None):
        """Backward-compatible: add a range programmatically."""
        if start is not None and end is not None:
            try:
                self._append_range(float(start), float(end))
            except (ValueError, TypeError):
                pass

    def remove_selected_row(self):
        """Remove the selected range(s) from the list — select all rows
        (Ctrl+A in the list, or Ctrl/Shift-click) first to clear everything
        at once; there is no separate "Clear All" button."""
        for item in self.ranges_list_widget.selectedItems():
            self.ranges_list_widget.takeItem(self.ranges_list_widget.row(item))
        self._exit_range_edit_mode()
        self.update_plot_ranges()

    def get_ranges(self):
        """Return list of [start, end] pairs, read from each item's exact
        stored values (Qt.UserRole) — NOT from its display text, which is
        deliberately rounded for readability and must never be treated as
        the source of truth (see _append_range)."""
        ranges = []
        for i in range(self.ranges_list_widget.count()):
            item = self.ranges_list_widget.item(i)
            stored = item.data(Qt.UserRole)
            if stored is not None:
                ranges.append([float(stored[0]), float(stored[1])])
                continue
            # Defensive fallback for any item lacking stored data.
            text = item.text()
            try:
                parts = text.split('\u2013')
                ranges.append([float(parts[0].strip()), float(parts[1].strip())])
            except (IndexError, ValueError):
                continue
        return ranges

    def setup_reset_buttons(self, default_x_min, default_x_max):
        """Set up reset button functionality with default values."""
        self.default_x_min = default_x_min
        self.default_x_max = default_x_max

        def reset_x_min():
            if self.default_x_min is not None:
                self.x_min_edit.setText(str(self.default_x_min))

        def reset_x_max():
            if self.default_x_max is not None:
                self.x_max_edit.setText(str(self.default_x_max))

        self.x_min_reset.clicked.connect(reset_x_min)
        self.x_max_reset.clicked.connect(reset_x_max)

    def _handle_linearization_state(self, state):
        """Handle enabling/disabling of dependent widgets based on linearization state."""
        is_enabled = state == Qt.Checked
        self.x_step_edit.setEnabled(is_enabled)

    def show_help(self):
        """Show help dialog when help button is clicked."""
        try:
            from src.help.data_range_help import (
                get_data_range_help_content,
                get_data_range_help_title
            )
            from src.help.help_window import show_help_window
            content = get_data_range_help_content()
            title = get_data_range_help_title()
            show_help_window(self, title, content)
        except Exception as e:
            logger.debug(f"Could not show help: {e}")
            QMessageBox.information(self, "Help",
                                    "Help documentation is not available at this time.")

    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — validates that there's something to apply,
        then commits directly via commit_callback. No separate Run step:
        feedback (success or failure) is shown right here next to the
        buttons that triggered it, instead of in a disconnected main-window
        message box. The dialog closes itself once the commit succeeds.
        """
        settings = self.get_settings()
        if settings is None:
            QMessageBox.warning(
                self, "Invalid Values",
                "Please check the X-axis limits and linearization step — "
                "they must be valid numbers."
            )
            return

        if (not settings['ranges'] and settings['x_min'] is None
                and settings['x_max'] is None and not settings['apply_linearization']):
            QMessageBox.warning(
                self, "Nothing to Apply",
                "Define at least one range, set an X-axis limit, or enable "
                "linearization before applying."
            )
            return

        if self.commit_callback is None:
            QMessageBox.critical(
                self, "Not Available",
                "This dialog was opened without a way to apply changes. "
                "Please reopen it via Configure."
            )
            return

        if not self.selected_spectra:
            QMessageBox.warning(
                self, "No Spectra Selected",
                "Please select one or more spectra in the main window first."
            )
            return

        action = ('add the range-restricted result as new spectra' if add_as_new
                  else 'replace the selected spectra with their range-restricted result')
        confirm = QMessageBox.question(
            self, 'Confirm', f'{action[0].upper() + action[1:]}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(settings, add_as_new, list(self.selected_spectra))
        if success:
            QMessageBox.information(self, 'Done', message)
            self.accept()
        else:
            QMessageBox.warning(self, 'Could Not Apply', message)

    def get_settings(self):
        """Get all settings from the dialog."""
        try:
            x_step = float(self.x_step_edit.text()) if self.x_step_edit.text() else self.x_step
            x_min = float(self.x_min_edit.text()) if self.x_min_edit.text() else None
            x_max = float(self.x_max_edit.text()) if self.x_max_edit.text() else None
        except ValueError:
            return None

        return {
            'ranges': self.get_ranges(),
            'is_exclude_mode': self.exclude_radio.isChecked(),
            'apply_linearization': self.apply_linearization_cb.isChecked(),
            'x_step': x_step,
            'x_min': x_min,
            'x_max': x_max
        }
    
    def showEvent(self, event):
        """Initialize the dialog when it's first shown."""
        super().showEvent(event)
        # Load existing ranges after the dialog is fully set up
        if not hasattr(self, '_ranges_loaded'):
            self.load_existing_ranges()
            self._ranges_loaded = True