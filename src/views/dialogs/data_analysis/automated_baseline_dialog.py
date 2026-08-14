# src/views/dialogs/data_analysis/automated_baseline_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QSlider, QLabel, QDialogButtonBox, QListWidget,
                             QWidget, QSplitter, QSizePolicy, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox)
from PyQt5.QtCore import Qt, pyqtSignal
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import numpy as np

from src.modules.data_analysis.automated_baseline_manager import AutomatedBaselineManager
from src.help.automated_baseline_help import (get_automated_baseline_help_content,
                                              get_automated_baseline_help_title)
from src.help.help_window import show_help_window
from src.modules.utils.label_shortening import make_shortened_name_delegate, make_shorten_names_checkbox

class AutomatedBaselineCanvas(FigureCanvas):
    """Canvas for plotting and selecting exclusion ranges."""
    range_selected = pyqtSignal(float, float)

    def __init__(self, parent=None):
        self.fig = Figure(tight_layout=True)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.parent = parent
        self.range_spans = []
        self.selecting_range = False
        self.selection_start = None
        self.mpl_connect('button_press_event', self.on_click)
        self.mpl_connect('button_release_event', self.on_release)

    def on_click(self, event):
        if event.inaxes != self.ax or self.parent.toolbar.mode != '':
            return
        if event.button == 1:
            self.selecting_range = True
            self.selection_start = event.xdata

    def on_release(self, event):
        if self.selecting_range and self.selection_start is not None:
            x_min = min(self.selection_start, event.xdata)
            x_max = max(self.selection_start, event.xdata)
            self.range_selected.emit(x_min, x_max)
        self.selecting_range = False
        self.selection_start = None

    def update_plot(self, spectrum, baseline, corrected, ranges, invert_regions, display_label=None):
        self.ax.clear()

        # Plot original data
        if spectrum:
            self.ax.plot(spectrum['x_scale'], spectrum['y_scale'], label='Original Data', color='gray')

        # Plot baseline and corrected data only if they are valid
        if baseline is not None and not np.isnan(baseline).all():
            self.ax.plot(spectrum['x_scale'], baseline, label='Calculated Baseline', color='red', linestyle='--')
        if corrected is not None and not np.isnan(corrected).all():
            self.ax.plot(spectrum['x_scale'], corrected, label='Corrected Data', color='blue')

        # Draw shaded regions
        for span in self.range_spans:
            span.remove()
        self.range_spans.clear()
        if spectrum:
            x_full_range = self.ax.get_xlim() # Use current plot limits for shading
            if invert_regions:
                # Shade everything EXCEPT the selected ranges
                sorted_ranges = sorted(ranges)
                current_pos = x_full_range[0]
                for start, end in sorted_ranges:
                    if current_pos < start:
                        self.range_spans.append(self.ax.axvspan(current_pos, start, alpha=0.2, color='red'))
                    current_pos = end
                if current_pos < x_full_range[1]:
                    self.range_spans.append(self.ax.axvspan(current_pos, x_full_range[1], alpha=0.2, color='red'))
            else:
                # Shade the selected ranges themselves
                for start, end in ranges:
                    self.range_spans.append(self.ax.axvspan(start, end, alpha=0.2, color='red'))

        title_label = (display_label or spectrum.get('label')) if spectrum else None
        self.ax.set_title(f"Preview: {title_label}" if spectrum else "Preview")
        self.ax.set_xlabel("X-Axis")
        self.ax.set_ylabel("Intensity")
        self.ax.legend()
        self.ax.grid(True, linestyle='--', alpha=0.6)
        self.draw()


class AutomatedBaselineDialog(QDialog):
    """Dialog for interactive automated baseline correction."""

    def __init__(self, parent=None, selected_spectra=None, current_settings=None, commit_callback=None,
                 main_controller=None):
        super().__init__(parent)
        self.setWindowTitle("Automated Baseline Correction (ALS)")
        self.setModal(True)
        self._main_controller = main_controller
        self.selected_spectra = selected_spectra or []
        self.current_spectrum_index = 0
        self.manager = AutomatedBaselineManager()
        self.fitting_ranges = []
        self.current_settings = current_settings or {} # Store the settings
        # Bound method (OperationsController.commit_automated_baseline) passed
        # in by whatever opened this dialog, so Apply / Add as New can commit
        # the result directly, without a separate Run step.
        self.commit_callback = commit_callback

        self.setMinimumSize(900, 700)
        self.resize(1200, 800)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.setSizeGripEnabled(True)

        self.setup_ui()
        if self.selected_spectra:
            self.initialize_dialog()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        control_panel = self.create_control_panel()
        splitter.addWidget(control_panel)
        
        canvas_panel = self.create_canvas_panel()
        splitter.addWidget(canvas_panel)
        
        splitter.setSizes([400, 800])
  
    def load_settings(self):
        """Load settings into the UI controls when the dialog opens."""
        if not self.current_settings:
            return
    
        # Load lambda (smoothness)
        lam_val = self.current_settings.get('lambda', 1e6)
        slider_lam_val = int(np.clip(10 * np.log10(lam_val), self.lam_slider.minimum(), self.lam_slider.maximum()))
        self.lam_slider.setValue(slider_lam_val)
    
        # Load p (asymmetry)
        p_val = self.current_settings.get('p', 0.01)
        slider_p_val = int(np.clip(p_val * 1000, self.p_slider.minimum(), self.p_slider.maximum()))
        self.p_slider.setValue(slider_p_val)
    
        # Load fitting ranges and update the table
        self.fitting_ranges = self.current_settings.get('fitting_ranges', [])
        self.update_range_table()
    
        # Load invert regions checkbox state
        invert_state = self.current_settings.get('invert_regions', False)
        self.invert_regions_checkbox.setChecked(invert_state)        

    def create_control_panel(self):
        widget = QWidget()
        widget.setFixedWidth(400)
        layout = QVBoxLayout(widget)

        # Spectra List for Preview
        spectra_group = QGroupBox("Preview Spectrum")
        spectra_layout = QVBoxLayout()
        self.spectra_list = QListWidget()
        self.spectra_list.addItems([s['label'] for s in self.selected_spectra])
        # Display-only "shorten names" — selection is read back
        # positionally (see on_spectrum_selected's .row(item)), never by
        # matching this list's displayed text, so paint-only shortening
        # is safe here.
        self.spectra_list.setItemDelegate(
            make_shortened_name_delegate(self.spectra_list, self._shorten_names_enabled)
        )
        self.spectra_list.itemClicked.connect(self.on_spectrum_selected)
        spectra_layout.addWidget(self.spectra_list)
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _: self.spectra_list.viewport().update()
        )
        spectra_layout.addWidget(self.checkBox_shorten_names)
        spectra_group.setLayout(spectra_layout)
        layout.addWidget(spectra_group)

        # ALS Parameters
        params_group = QGroupBox("ALS Parameters")
        params_layout = QVBoxLayout()
        lam_label = QLabel("Smoothness (λ): 1e6.0")
        self.lam_slider = QSlider(Qt.Horizontal); self.lam_slider.setRange(20, 90); self.lam_slider.setValue(60)
        self.lam_slider.valueChanged.connect(lambda v: lam_label.setText(f"Smoothness (λ): 1e{v/10:.1f}"))
        self.lam_slider.valueChanged.connect(self.update_preview)
        params_layout.addWidget(lam_label); params_layout.addWidget(self.lam_slider)

        p_label = QLabel("Asymmetry (p): 0.010")
        self.p_slider = QSlider(Qt.Horizontal); self.p_slider.setRange(1, 100); self.p_slider.setValue(10)
        self.p_slider.valueChanged.connect(lambda v: p_label.setText(f"Asymmetry (p): {v/1000:.3f}"))
        self.p_slider.valueChanged.connect(self.update_preview)
        params_layout.addWidget(p_label); params_layout.addWidget(self.p_slider)
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # Fitting Regions
        regions_group = QGroupBox("Fitting Regions")
        regions_layout = QVBoxLayout()
        
        self.invert_regions_checkbox = QCheckBox("Invert Regions (Fit ONLY within selected regions)")
        self.invert_regions_checkbox.setToolTip("Check this to define the good baseline regions instead of the bad peak regions.")
        self.invert_regions_checkbox.stateChanged.connect(self.update_preview)
        regions_layout.addWidget(self.invert_regions_checkbox)

        self.region_label = QLabel("Drag on plot to define regions to EXCLUDE from fitting.")
        regions_layout.addWidget(self.region_label)
        self.invert_regions_checkbox.stateChanged.connect(
            lambda: self.region_label.setText("Drag on plot to define regions to INCLUDE in fitting." if self.invert_regions_checkbox.isChecked() else "Drag on plot to define regions to EXCLUDE from fitting.")
        )
        
        self.range_table = QTableWidget()
        self.range_table.setColumnCount(2); self.range_table.setHorizontalHeaderLabels(['From', 'To'])
        self.range_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        regions_layout.addWidget(self.range_table)
        
        btn_layout = QHBoxLayout()
        remove_btn = QPushButton("Remove Selected"); remove_btn.clicked.connect(self.remove_range)
        clear_btn = QPushButton("Clear All"); clear_btn.clicked.connect(self.clear_ranges)
        btn_layout.addWidget(remove_btn); btn_layout.addWidget(clear_btn)
        regions_layout.addLayout(btn_layout)
        regions_group.setLayout(regions_layout)
        layout.addWidget(regions_group)

        layout.addStretch()

        # Dialog Buttons — Apply / Add as New commit directly via
        # commit_callback, there's no separate Run step in the main window
        # for this operation anymore (see OperationsController.commit_automated_baseline).
        button_box = QDialogButtonBox()
        help_button = QPushButton("Help")
        button_box.addButton(help_button, QDialogButtonBox.HelpRole)
        help_button.clicked.connect(self.show_help)

        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip(
            "Replace the selected spectra with their baseline-corrected result."
        )
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        button_box.addButton(self.apply_button, QDialogButtonBox.ActionRole)

        self.add_as_new_button = QPushButton("Add as New")
        self.add_as_new_button.setToolTip(
            "Keep the original spectra unchanged and add the baseline-corrected "
            "results to the list under new names."
        )
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        button_box.addButton(self.add_as_new_button, QDialogButtonBox.ActionRole)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        button_box.addButton(self.close_button, QDialogButtonBox.RejectRole)
        layout.addWidget(button_box)
        
        return widget

    def create_canvas_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.canvas = AutomatedBaselineCanvas(self)
        self.toolbar = NavigationToolbar(self.canvas, widget)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        self.canvas.range_selected.connect(self.add_range)
        return widget

    def initialize_dialog(self):
        self.spectra_list.setCurrentRow(0)
        self.load_settings() 
        self.update_preview()
        
    def show_help(self):
        content = get_automated_baseline_help_content()
        title = get_automated_baseline_help_title()
        show_help_window(self, title, content)

    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _display_label(self, spectrum):
        """Display-only "shorten names" lookup for the preview plot title
        (see label_shortening.py). Grouped across self.selected_spectra,
        same population as the spectra_list above."""
        label = spectrum.get('label', '?')
        if not self._shorten_names_enabled():
            return label
        all_labels = [s.get('label', '') for s in self.selected_spectra]
        if len(all_labels) < 2:
            return label
        from src.modules.utils.label_shortening import compute_distinguishing_labels
        return compute_distinguishing_labels(all_labels).get(label, label)

    def on_spectrum_selected(self, item):
        self.current_spectrum_index = self.spectra_list.row(item)
        self.update_preview()

    def add_range(self, x_min, x_max):
        self.fitting_ranges.append(sorted((x_min, x_max)))
        self.update_range_table()
        self.update_preview()
    
    def remove_range(self):
        selected_rows = sorted(list(set(item.row() for item in self.range_table.selectedItems())), reverse=True)
        for row in selected_rows:
            del self.fitting_ranges[row]
        self.update_range_table()
        self.update_preview()

    def clear_ranges(self):
        self.fitting_ranges.clear()
        self.update_range_table()
        self.update_preview()

    def update_range_table(self):
        self.range_table.setRowCount(len(self.fitting_ranges))
        for i, (start, end) in enumerate(self.fitting_ranges):
            self.range_table.setItem(i, 0, QTableWidgetItem(f"{start:.2f}"))
            self.range_table.setItem(i, 1, QTableWidgetItem(f"{end:.2f}"))

    def update_preview(self):
        if not self.selected_spectra: return
        spectrum = self.selected_spectra[self.current_spectrum_index]
        settings = self.get_settings()
        
        x, y = spectrum['x_scale'], spectrum['y_scale']
        
        region_mask = np.zeros_like(x, dtype=bool)
        if settings['fitting_ranges']:
            for start, end in settings['fitting_ranges']:
                region_mask |= (x >= start) & (x <= end)
        
        exclude_mask = ~region_mask if settings['invert_regions'] else region_mask
        
        baseline = self.manager.calculate_als_baseline(y, lam=settings['lambda'], p=settings['p'], exclude_indices=exclude_mask)
        
        display_label = self._display_label(spectrum)
        if baseline is not None and not np.isnan(baseline).all():
            corrected = y - baseline
            self.canvas.update_plot(spectrum, baseline, corrected, self.fitting_ranges, settings['invert_regions'],
                                     display_label=display_label)
        else:
            # If baseline fails, show only original data
            self.canvas.update_plot(spectrum, None, None, self.fitting_ranges, settings['invert_regions'],
                                     display_label=display_label)


    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — commits directly via commit_callback. No
        separate Run step: feedback (success or failure) is shown right
        here next to the buttons that triggered it, instead of in a
        disconnected main-window message box. The dialog closes itself
        once the commit succeeds.
        """
        from PyQt5.QtWidgets import QMessageBox

        if self.commit_callback is None:
            QMessageBox.critical(
                self, "Not Available",
                "This dialog was opened without a way to apply changes. "
                "Please reopen it via Parameters."
            )
            return

        settings = self.get_settings()

        action = ("add the baseline-corrected result as new spectra" if add_as_new
                  else "replace the selected spectra with their baseline-corrected result")
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
        return {
            'lambda': 10**(self.lam_slider.value() / 10.0),
            'p': self.p_slider.value() / 1000.0,
            'n_iter': 10,
            'fitting_ranges': self.fitting_ranges,
            'invert_regions': self.invert_regions_checkbox.isChecked()
        }