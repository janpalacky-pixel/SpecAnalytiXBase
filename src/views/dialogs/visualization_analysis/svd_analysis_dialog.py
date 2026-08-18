# src/views/dialogs/visualization_analysis/svd_analysis_dialog.py

import numpy as np
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, 
                            QSpinBox, QDoubleSpinBox, QLabel, QPushButton, QDialogButtonBox,QLineEdit,
                            QSplitter, QWidget, QMessageBox, QCheckBox, QComboBox, 
                            QSizePolicy, QMenu, QAction, QFileDialog, QListWidget,
                            QListWidgetItem, QRadioButton, QButtonGroup, QFrame, QTabWidget,
                            QTableWidget, QTableWidgetItem, QHeaderView, QShortcut)
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt, QTimer, QEvent, QObject, QThread, pyqtSignal
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import os
from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import compute_distinguishing_labels, make_shorten_names_checkbox
logger = get_logger(__name__)

def _svd_dialog_help_html():
    return """
    <html><head><style>
        body  { font-family: Arial, sans-serif; margin: 16px; line-height: 1.55; font-size: 13px; }
        h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
        h2    { color: #1565C0; margin-top: 18px; }
        h3    { color: #E65100; margin-top: 12px; margin-bottom: 3px; }
        .cat  { background: #f5f5f5; padding: 9px 13px; margin: 5px 0; border-radius: 5px; }
        .tip  { background: #E8F5E9; border-left: 4px solid #2E7D32; padding: 8px 12px; margin: 7px 0; }
        .note { background: #E3F2FD; border-left: 4px solid #1565C0; padding: 8px 12px; margin: 7px 0; }
        .fm   { font-family: monospace; background: #ececec; padding: 1px 4px; border-radius: 3px; }
        table { border-collapse: collapse; width: 100%; margin: 7px 0; }
        th    { background: #E3F2FD; text-align: left; padding: 5px 7px; }
        td    { border-bottom: 1px solid #e0e0e0; padding: 4px 7px; vertical-align: top; }
        ul,ol { padding-left: 18px; } li { margin: 3px 0; }
        hr    { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
    </style></head><body>

    <h1>SVD Analysis — Dialog Help</h1>

    <p>This dialog decomposes your preprocessed spectra using
    <b>Singular Value Decomposition (SVD)</b> and lets you interactively explore
    the resulting components (called <em>subspectra</em>), their contributions
    to each spectrum (coefficients), and diagnostic plots to guide reconstruction.</p>

    <div class="note">
        <b>Mathematics:</b> X = U &times; diag(s) &times; V<sup>T</sup><br>
        &bull; <b>U columns</b> = subspectra (spectral basis vectors, shape n_wavelengths &times; k)<br>
        &bull; <b>s</b> = singular values, decreasing, proportional to &radic;(variance)<br>
        &bull; <b>V rows</b> = coefficients — how much each spectrum contains each subspectrum<br>
        &bull; Implemented as <span class="fm">numpy.linalg.svd(X, full_matrices=False)</span>
    </div>

    <hr>
    <h2>View SVD Components group</h2>

    <div class="cat">
        <h3>Navigation — ◀ Prev / Next ▶ / Jump spinbox</h3>
        <p>Browse one subspectrum at a time. <b>◀ Prev</b> and <b>Next ▶</b> step by one;
        the <b>Jump</b> spinbox lets you go directly to any component number.
        The canvas shows only the navigated subspectrum (unless you also have items
        ticked in the list below).</p>
    </div>

    <div class="cat">
        <h3>Invert button</h3>
        <p>Multiplies U[:, i] and V[i, :] simultaneously by &minus;1.
        SVD sign is <em>arbitrary</em> — both signs are mathematically equivalent.
        Use Invert when a band you expect to be positive is pointing downward.</p>
    </div>

    <div class="cat">
        <h3>Select all / Unselect all</h3>
        <p>Tick or untick all components at once. Useful for a quick overview or
        for clearing the canvas before selecting a specific subset.</p>
    </div>

    <div class="cat">
        <h3>Metric display</h3>
        <p>Replaces the old Var.%/σ toggle. Choose which of the seven metrics (same set as
        the Diagnostics tab — Singular values, Eigenvalue, Explained/Cumulative variance,
        Residual error, Malinowski IND) appears next to each component in the list and on
        plot labels, plus the number format (Fixed or Scientific) and decimal precision.</p>
    </div>

    <div class="cat">
        <h3>Component list</h3>
        <p>Each row represents one SVD component (subspectrum), ordered by decreasing variance.
        Component 1 always has the largest contribution. Tick any combination to display
        them simultaneously on the canvas using the layout settings below.</p>
    </div>

    <hr>
    <h2>Plot display group</h2>

    <div class="cat">
        <h3>Layout — Row / Column</h3>
        <p>When multiple components are selected and shown separately:<br>
        &bull; <b>Row</b> — each row shows one subspectrum beside its coefficient plot.<br>
        &bull; <b>Column</b> — all subspectra across the top row, all coefficient plots
        across the bottom row.</p>
    </div>

    <div class="cat">
        <h3>Subspectra — Separate / Combined</h3>
        <p>&bull; <b>Separate</b> — each ticked subspectrum in its own axes.<br>
        &bull; <b>Combined</b> — all ticked subspectra overlaid in one axes with a legend.
        Useful for comparing spectral shapes and identifying correlated components.</p>
    </div>

    <div class="cat">
        <h3>Coefficients — Separate / Combined</h3>
        <p>Same logic for the V-row coefficient plots.<br>
        &bull; <b>Separate</b> — one axes per component.<br>
        &bull; <b>Combined</b> — overlay all coefficient vectors. Useful for spotting
        which spectra are dominated by which component.<br>
        Right-click on the canvas to switch between scatter and bar chart style
        for coefficient plots.</p>
    </div>

    <div class="cat">
        <h3>Coefficient X-axis</h3>
        <p>Coefficient plots default to plain <b>spectrum order</b> (1, 2, 3, ...).
        Switch to <b>Parameter values</b> to plot against a physical quantity that
        varies across your spectra instead — temperature, pH, time, etc. — one value
        per spectrum, in the same order the spectra were selected.</p>
        <p>Load values via <b>Load from file&hellip;</b> (one number per line; drag &amp;
        drop a text file onto the dialog works too), or <b>Enter manually&hellip;</b>
        (a spreadsheet-style table with Excel-style Fill series and copy/cut/paste).
        Click the <b>?</b> button next to the radio buttons for the full rundown.</p>
        <p><b>Values are cleared whenever SVD is recomputed</b> — a different or
        reordered spectra selection invalidates them, so reload/re-enter after
        choosing new spectra.</p>
    </div>

    <hr>
    <h2>Diagnostics tab</h2>

    <div class="cat">
        <h3>Diagnostics</h3>
        <p>A separate tab (next to Components) with three view modes:<br>
        &bull; <b>Single metric</b> — plot any one of six metrics vs component number;
        click <em>ℹ What does this metric mean?</em> for a formula + interpretation popup.<br>
        &bull; <b>Compare two metrics</b> — plot any two metrics side by side against component number,
        each point labelled by component number.<br>
        &bull; <b>Overview (all)</b> — 2&times;3 grid of all six metrics at once.</p>
        <p><b>Six metrics:</b> singular values (&sigma;), explained variance (%), cumulative
        explained (%), cumulative unexplained (%), residual error E(m), <b>Malinowski IND</b>.<br>
        <b>IND</b> has a genuine minimum — the statistically optimal number of components.<br>
        <b>E(m)</b> is monotonically decreasing — look for the elbow instead.<br>
        Quick export buttons save all metrics or the current plot to CSV.</p>
    </div>

    <hr>
    <h2>Quick selection guide</h2>
    <table>
        <tr><th>Goal</th><th>Action</th></tr>
        <tr><td>Find how many components carry real signal</td>
            <td>Residual errors → minimum of IND + singular value kink</td></tr>
        <tr><td>Browse one subspectrum at a time</td>
            <td>Use ◀ / ▶ navigation; do not tick items in list</td></tr>
        <tr><td>Compare two subspectra side by side</td>
            <td>Tick both; Subspectra: Separate; Layout: Row</td></tr>
        <tr><td>Overlay all components to compare shapes</td>
            <td>Select all; Subspectra: Combined</td></tr>
        <tr><td>See which spectra are dominated by component i</td>
            <td>Tick component i; inspect the coefficient plot (V row)</td></tr>
        <tr><td>Correct sign of a downward-pointing band</td>
            <td>Navigate to that component; click Invert</td></tr>
        <tr><td>How much variance do the first 5 components explain?</td>
            <td>Analysis Summary → header text or cumulative variance plot</td></tr>
    </table>

    <hr>
    <div class="tip">
        <b>Typical workflow:</b> Open Summary → note IND minimum (optimal N) →
        navigate first N subspectra → invert any with flipped sign →
        tick first N to display → use reconstruction pipeline with N components
        for denoising, or apply baseline correction to dominant subspectra first.
    </div>

    </body></html>
    """


class _ComputeWorker(QThread):
    """Runs a single callable on a background thread — see the equivalent
    class in nmf_dialog.py for the full rationale: a long blocking call on
    the GUI thread freezes Qt's entire event loop, including the ability
    to paint, show, or hide a progress dialog, for its whole duration.
    That's what caused the progress indicator to get stuck on screen until
    an unrelated event forced a repaint. The callable must not touch any
    Qt widgets — only pure computation is safe to run here.
    """
    done = pyqtSignal()

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self._fn()
        except Exception as exc:
            self.error = exc
        self.done.emit()


class SVDSingularValuesWindow(QDialog):
    """Window to display SVD singular values and residual errors."""
    
    def __init__(self, parent=None, svd_controller=None, show_type="both"):
        super().__init__(parent)
        self.svd_controller = svd_controller
        self.show_type = show_type
        self.use_log_scale = True
        
        if show_type == "singular":
            self.setWindowTitle("SVD Singular Values")
        elif show_type == "residual":
            self.setWindowTitle("SVD Residual Errors")
        else:
            self.setWindowTitle("SVD Singular Values and Residual Errors")
            
        self.setModal(True)
        self.resize(800, 600)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint)
        
        self.setup_ui()
        self.plot_data()
        
    def setup_ui(self):
        """Set up the window UI."""
        layout = QVBoxLayout(self)
        
        # Scale selection controls
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale:"))
        
        self.linear_radio = QCheckBox("Linear")
        self.linear_radio.stateChanged.connect(self.on_scale_changed)
        scale_layout.addWidget(self.linear_radio)
        
        self.log_radio = QCheckBox("Logarithmic")
        self.log_radio.setChecked(True)
        self.log_radio.stateChanged.connect(self.on_scale_changed)
        scale_layout.addWidget(self.log_radio)
        
        scale_layout.addStretch()
        layout.addLayout(scale_layout)
        
        # Create canvas
        self.figure = Figure(figsize=(10, 8))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        # Navigation toolbar
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.toolbar)
        
        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def on_scale_changed(self):
        """Handle scale change (linear vs logarithmic)."""
        sender = self.sender()
        if sender == self.linear_radio and self.linear_radio.isChecked():
            self.log_radio.setChecked(False)
            self.use_log_scale = False
        elif sender == self.log_radio and self.log_radio.isChecked():
            self.linear_radio.setChecked(False)
            self.use_log_scale = True
        
        self.plot_data()
    
    def plot_data(self):
        """Plot the requested data."""
        if not self.svd_controller:
            return
            
        try:
            self.figure.clear()
            
            if self.show_type == "both":
                ax1 = self.figure.add_subplot(211)
                ax2 = self.figure.add_subplot(212)
                
                # Plot singular values
                s = self.svd_controller.manager.s
                if s is not None:
                    indices = np.arange(1, len(s) + 1)
                    if self.use_log_scale:
                        ax1.semilogy(indices, s, 'bo-', markersize=6, linewidth=2)
                        ax1.set_ylabel('Singular Value (log scale)')
                    else:
                        ax1.plot(indices, s, 'bo-', markersize=6, linewidth=2)
                        ax1.set_ylabel('Singular Value')
                    ax1.set_title('Singular Values')
                    ax1.set_xlabel('Component Number')
                    ax1.grid(True, alpha=0.3)
                
                # Plot residual errors
                E = self.svd_controller.calculate_residual_errors()
                if E is not None and len(E) > 0:
                    error_indices = np.arange(1, len(E) + 1)
                    if self.use_log_scale:
                        ax2.semilogy(error_indices, E, 'ro-', markersize=6, linewidth=2)
                        ax2.set_ylabel('Residual Error (log scale)')
                    else:
                        ax2.plot(error_indices, E, 'ro-', markersize=6, linewidth=2)
                        ax2.set_ylabel('Residual Error')
                    ax2.set_title('Residual Errors')
                    ax2.set_xlabel('Component Number')
                    ax2.grid(True, alpha=0.3)
                
            elif self.show_type == "singular":
                ax = self.figure.add_subplot(111)
                s = self.svd_controller.manager.s
                if s is not None:
                    indices = np.arange(1, len(s) + 1)
                    if self.use_log_scale:
                        ax.semilogy(indices, s, 'bo-', markersize=8, linewidth=2)
                        ax.set_ylabel('Singular Value (log scale)')
                    else:
                        ax.plot(indices, s, 'bo-', markersize=8, linewidth=2)
                        ax.set_ylabel('Singular Value')
                    ax.set_title('SVD Singular Values')
                    ax.set_xlabel('Component Number')
                    ax.grid(True, alpha=0.3)
                
            elif self.show_type == "residual":
                ax = self.figure.add_subplot(111)
                E = self.svd_controller.calculate_residual_errors()
                if E is not None and len(E) > 0:
                    error_indices = np.arange(1, len(E) + 1)
                    if self.use_log_scale:
                        ax.semilogy(error_indices, E, 'ro-', markersize=8, linewidth=2)
                        ax.set_ylabel('Residual Error (log scale)')
                    else:
                        ax.plot(error_indices, E, 'ro-', markersize=8, linewidth=2)
                        ax.set_ylabel('Residual Error')
                    ax.set_title('SVD Residual Errors')
                    ax.set_xlabel('Component Number')
                    ax.grid(True, alpha=0.3)
            
            self.figure.tight_layout()
            self.canvas.draw()
            
        except Exception as e:
            logger.error(f"Error plotting SVD data: {e}")
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, f"Error plotting data:\n{str(e)}", 
                   transform=ax.transAxes, ha='center', va='center',
                   fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            self.canvas.draw()

class InteractiveSVDAnalysisCanvas(FigureCanvas):
    """Canvas for interactive SVD analysis visualization."""
    
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(12, 8))
        super().__init__(self.fig)
        self.setParent(parent)
        
        self.svd_controller = None
        self.selected_subspectra = []
        self.coefficient_plot_type = 'scatter'  # 'scatter' or 'bar'
        self.show_coefficients = True
        
        # Plot appearance settings - DEFAULT TO SEPARATE PLOTS
        self.plot_organization = 'row'  # 'row' or 'column'
        self.subspectra_mode = 'separate'  # 'combined' or 'separate'
        self.coefficients_mode = 'separate'  # 'combined' or 'separate' - CHANGED DEFAULT
        
        self.value_display_mode = 'variance'  # 'variance' or 'singular'
        self.label_provider = None  # optional callable(idx, short=False) -> str, set by the
                                     # dialog to drive subspectrum labels from the unified Metric system
        self.coefficient_label_provider = None  # same, but for coefficient ("V{n}") labels
        self.use_parameter_axis = False  # False = coefficient plots use spectrum order (1..n);
                                          # True = use manager.parameter_values when available/valid
        self.use_label_axis = False      # True = use manager.spectrum_labels (main-window order)
                                          # as the coefficient plots' x-axis tick labels
        self.get_shorten_enabled = None  # optional zero-arg callable -> bool, set by the dialog
                                          # to this dialog's OWN "Shorten names" checkbox (see
                                          # SVDAnalysisDialog.create_canvas_panel). This canvas has
                                          # no Qt widget of its own to host that checkbox — the
                                          # dialog owns it and hands down a callable rather than a
                                          # direct checkbox reference, same pattern as label_provider
                                          # / coefficient_label_provider above.

        self.setFocusPolicy(Qt.StrongFocus)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def leaveEvent(self, event):
        """Handle the mouse leaving the canvas.

        This is a deliberate override, not just inherited behavior. matplotlib's
        own FigureCanvasQT.leaveEvent() unconditionally calls
        QApplication.restoreOverrideCursor() — it assumes matplotlib itself is
        the only thing that ever pushes a global override cursor. That's not
        true here: this dialog (and possibly the code that opens it, e.g. a
        "please wait" cursor shown while this modal dialog is up) also pushes
        QApplication-wide override cursors. If the mouse happens to be over
        this canvas while one of those is active, matplotlib's leaveEvent pops
        it early, leaving the cursor stack out of sync with reality — visible
        as a "busy" cursor that lingers regardless of actual state and only
        clears the next time the mouse crosses this canvas again. Reimplement
        the same hover-leave notification without the blind cursor pop.
        """
        if self.figure is not None:
            from matplotlib.backend_bases import LocationEvent
            LocationEvent("figure_leave_event", self, *self.mouseEventCoords(),
                          guiEvent=event)._process()

    def set_value_display_mode(self, mode):
        """Set the value display mode (variance or singular values)."""
        self.value_display_mode = mode
        self.plot_selected_subspectra()        
        
    def set_plot_appearance(self, organization, subspectra_mode, coefficients_mode):
        """Set plot appearance options."""
        self.plot_organization = organization
        self.subspectra_mode = subspectra_mode
        self.coefficients_mode = coefficients_mode
        logger.debug(f"DEBUG: Plot appearance set - org: {organization}, sub: {subspectra_mode}, coeff: {coefficients_mode}")
        self.plot_selected_subspectra()
        
    def show_context_menu(self, pos):
        """Show context menu for the canvas."""
        context_menu = QMenu(self)
        
        # Toggle coefficients plot
        if self.show_coefficients:
            coeff_action = QAction("Hide Coefficients Plot", self)
        else:
            coeff_action = QAction("Show Coefficients Plot", self)
        coeff_action.triggered.connect(self.toggle_coefficients_plot)
        context_menu.addAction(coeff_action)
        
        context_menu.addSeparator()
        
        # Coefficient plot type submenu
        plot_type_menu = QMenu("Coefficient Plot Type", self)
        context_menu.addMenu(plot_type_menu)
        
        scatter_action = QAction("Scatter Plot", self)
        scatter_action.setCheckable(True)
        scatter_action.setChecked(self.coefficient_plot_type == 'scatter')
        scatter_action.triggered.connect(lambda: self.set_coefficient_plot_type('scatter'))
        plot_type_menu.addAction(scatter_action)
        
        bar_action = QAction("Bar Plot", self)
        bar_action.setCheckable(True)
        bar_action.setChecked(self.coefficient_plot_type == 'bar')
        bar_action.triggered.connect(lambda: self.set_coefficient_plot_type('bar'))
        plot_type_menu.addAction(bar_action)
        
        context_menu.exec_(self.mapToGlobal(pos))

    def toggle_coefficients_plot(self):
        """Toggle visibility of coefficients plot."""
        self.show_coefficients = not self.show_coefficients
        logger.debug(f"DEBUG: Coefficients plot visibility: {self.show_coefficients}")
        self.plot_selected_subspectra()

    def set_coefficient_plot_type(self, plot_type):
        """Set the coefficient plot type."""
        self.coefficient_plot_type = plot_type
        logger.debug(f"DEBUG: Coefficient plot type changed to: {plot_type}")
        self.plot_selected_subspectra()
        
    def set_svd_controller(self, controller):
        """Set the SVD controller for data access."""
        logger.debug(f"DEBUG: Canvas.set_svd_controller called with controller: {controller is not None}")
        self.svd_controller = controller
        logger.info(f"DEBUG: Canvas SVD controller set successfully: {self.svd_controller is not None}")

    def set_selected_subspectra(self, selected_indices):
        """Set the selected subspectra to display."""
        self.selected_subspectra = selected_indices.copy() if selected_indices else []
        logger.debug(f"DEBUG: Canvas selected subspectra: {self.selected_subspectra}")
        self.plot_selected_subspectra()


    def plot_selected_subspectra(self):
        """Plot the selected subspectra and their coefficients."""
        if not self.svd_controller or not self.selected_subspectra:
            self.fig.clear()
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Select subspectra to display", 
                   transform=ax.transAxes, ha='center', va='center', fontsize=14)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            self.draw()
            return
            
        # Clear the figure
        self.fig.clear()
        
        n_subspectra = len(self.selected_subspectra)
        colors = plt.cm.tab10(np.linspace(0, 1, n_subspectra))
        
        try:
            subspectra_combined = (self.subspectra_mode == 'combined' and n_subspectra > 1)
            coefficients_combined = (self.coefficients_mode == 'combined')
            
            if subspectra_combined:
                # COMBINED SUBSPECTRA CASES
                if not self.show_coefficients:
                    # Just combined subspectra
                    ax_sub = self.fig.add_subplot(111)
                    self._plot_combined_subspectra(ax_sub, colors)
                    
                elif coefficients_combined:
                    # Combined subspectra + Combined coefficients
                    ax_sub = self.fig.add_subplot(211)
                    ax_coeff = self.fig.add_subplot(212)
                    self._plot_combined_subspectra(ax_sub, colors)
                    self._plot_combined_coefficients(ax_coeff, colors)
                    
                else:
                    # Combined subspectra + Separate coefficients
                    self._plot_combined_subspectra_separate_coefficients(colors)
                    
            else:
                # SEPARATE SUBSPECTRA CASES
                if not self.show_coefficients:
                    # Just separate subspectra
                    self._plot_separate_subspectra_only(colors)
                    
                elif coefficients_combined:
                    # Separate subspectra + Combined coefficients
                    self._plot_separate_subspectra_combined_coefficients(colors)
                    
                else:
                    # Separate subspectra + Separate coefficients
                    self._plot_separate_subspectra_separate_coefficients(colors)
                    
        except Exception as e:
            logger.error(f"ERROR in plot_selected_subspectra: {e}")
            logger.exception("Traceback:")
            
            # Show error message on canvas
            self.fig.clear()
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, f"Error plotting data:\n{str(e)}", 
                   transform=ax.transAxes, ha='center', va='center',
                   fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
        
        # Use better spacing parameters
        self.fig.tight_layout(pad=1.5, h_pad=2.0, w_pad=1.5)
        self.draw()

    def _plot_combined_subspectra(self, ax, colors):
        """Plot all selected subspectra in a single plot."""
        for i, idx in enumerate(self.selected_subspectra):
            x, y = self.svd_controller.get_subspectrum_data(idx)
            if x is not None and y is not None:
                label = self._get_subspectrum_label(idx, short=True)
                ax.plot(x, y, color=colors[i], linewidth=1.5, label=label)
        
        ax.set_title("Combined Subspectra")
        ax.set_xlabel('Wavenumber')
        ax.set_ylabel('Intensity')
        ax.grid(True, alpha=0.3)
        ax.legend()

    def _plot_combined_subspectra_separate_coefficients(self, colors):
        """Plot combined subspectra with separate coefficients arranged by organization."""
        n_subspectra = len(self.selected_subspectra)
        
        if n_subspectra <= 4:
            # Single row layout for coefficients
            ax_sub = self.fig.add_subplot(2, 1, 1)
            self._plot_combined_subspectra(ax_sub, colors)
            
            # Separate coefficients arranged horizontally
            for i, idx in enumerate(self.selected_subspectra):
                # Both row and column should use same order as they appear in selection
                coeff_pos = i
                
                ax_coeff = self.fig.add_subplot(2, n_subspectra, n_subspectra + coeff_pos + 1)
                self._plot_single_coefficient(ax_coeff, idx, colors[i])
        else:
            # Multi-row layout for many coefficients
            n_cols = min(4, n_subspectra)
            n_rows_coeff = (n_subspectra + n_cols - 1) // n_cols
            total_rows = 1 + n_rows_coeff
            
            # Combined subspectra at top
            ax_sub = self.fig.add_subplot(total_rows, 1, 1)
            self._plot_combined_subspectra(ax_sub, colors)
            
            # Separate coefficients in grid below
            for i, idx in enumerate(self.selected_subspectra):
                if self.plot_organization == 'row':
                    coeff_row = i // n_cols
                    coeff_col = i % n_cols
                else:  # column
                    coeff_row = i // n_cols
                    coeff_col = i % n_cols
                
                subplot_idx = (coeff_row + 1) * n_cols + coeff_col + 1
                ax_coeff = self.fig.add_subplot(total_rows, n_cols, subplot_idx)
                self._plot_single_coefficient(ax_coeff, idx, colors[i])

    def _plot_separate_subspectra_only(self, colors):
        """Plot only separate subspectra with organization."""
        n_subspectra = len(self.selected_subspectra)
        n_cols = min(4, n_subspectra)
        n_rows = (n_subspectra + n_cols - 1) // n_cols
        
        for i, idx in enumerate(self.selected_subspectra):
            if self.plot_organization == 'row':
                # Row-first ordering (default matplotlib behavior)
                subplot_idx = i + 1
            else:  # column
                # Column-first ordering - fill columns first
                row = i // n_cols
                col = i % n_cols
                subplot_idx = row * n_cols + col + 1
                
            ax = self.fig.add_subplot(n_rows, n_cols, subplot_idx)
            self._plot_single_subspectrum(ax, idx, colors[i], small_plot=(n_subspectra > 1))

    def _plot_separate_subspectra_combined_coefficients(self, colors):
        """Plot separate subspectra with combined coefficients."""
        n_subspectra = len(self.selected_subspectra)
        n_cols = min(4, n_subspectra)
        n_rows_sub = (n_subspectra + n_cols - 1) // n_cols
        total_rows = n_rows_sub + 1
        
        # Plot subspectra according to organization
        for i, idx in enumerate(self.selected_subspectra):
            if self.plot_organization == 'row':
                # Row-first ordering
                subplot_idx = i + 1
            else:  # column
                # Column-first ordering
                row = i // n_cols
                col = i % n_cols
                subplot_idx = row * n_cols + col + 1
                
            ax = self.fig.add_subplot(total_rows, n_cols, subplot_idx)
            self._plot_single_subspectrum(ax, idx, colors[i], small_plot=True)
        
        # Combined coefficients at bottom - span full width
        ax_coeff = self.fig.add_subplot(total_rows, 1, total_rows)
        self._plot_combined_coefficients(ax_coeff, colors)


    def _plot_separate_subspectra_separate_coefficients(self, colors):
        """Plot separate subspectra with separate coefficients."""
        n_subspectra = len(self.selected_subspectra)
        
        if self.plot_organization == 'row':
            # Row organization: each row has subspectrum + coefficient
            for i, idx in enumerate(self.selected_subspectra):
                ax_sub = self.fig.add_subplot(n_subspectra, 2, 2*i + 1)
                self._plot_single_subspectrum(ax_sub, idx, colors[i], small_plot=True)
                
                ax_coeff = self.fig.add_subplot(n_subspectra, 2, 2*i + 2)
                self._plot_single_coefficient(ax_coeff, idx, colors[i])
        else:
            # Column organization: subspectra in top row, coefficients in bottom row
            # All subspectra and coefficients in same column positions
            for i, idx in enumerate(self.selected_subspectra):
                col_pos = i + 1
                
                # Subspectrum in top row
                ax_sub = self.fig.add_subplot(2, n_subspectra, col_pos)
                self._plot_single_subspectrum(ax_sub, idx, colors[i], small_plot=True)
                
                # Coefficient in bottom row, same column
                ax_coeff = self.fig.add_subplot(2, n_subspectra, n_subspectra + col_pos)
                self._plot_single_coefficient(ax_coeff, idx, colors[i])

    def _plot_single_subspectrum(self, ax, idx, color, small_plot=False):
        """Plot a single subspectrum."""
        x, y = self.svd_controller.get_subspectrum_data(idx)
        
        if x is not None and y is not None:
            ax.plot(x, y, color=color, linewidth=1)
            
            if small_plot:
                ax.set_title(self._get_subspectrum_label(idx, short=True), fontsize=10)
                ax.tick_params(labelsize=8)
            else:
                ax.set_title(self._get_subspectrum_label(idx, short=False))
                ax.set_xlabel('Wavenumber')
                ax.set_ylabel('Intensity')
            
            ax.grid(True, alpha=0.3)
    
    def _get_coefficient_xaxis(self, n):
        """
        Return (x_positions, xlabel, order, tick_labels) for coefficient plots.

        order is an array of indices, one per data point, that reorders
        the ORIGINAL (spectrum-order) coefficients to line up with
        x_positions — callers must index their coefficients array with
        it (coeffs[order]) before plotting, so each plotted point still
        shows the right y-value for its x-value. For plain spectrum
        order this is just 0..n-1 (already ascending, so a no-op).

        tick_labels is None unless the "Spectrum labels" mode is active,
        in which case it is a list of strings (one per data point, already
        reordered to match x_positions/order) that callers should apply via
        ax.set_xticks(x_positions); ax.set_xticklabels(tick_labels) — the
        underlying x_positions stay purely numeric (1..n) so _bar_width and
        matplotlib's bar()/plot() keep working unchanged.

        Honors the parameter-values x-axis mode when the dialog has
        switched to it AND the loaded parameter values still match the
        coefficient length n — falls back to plain spectrum order
        otherwise (e.g. right after a recompute, before new values have
        been (re)loaded).

        Parameter values are sorted ascending here purely so the plotted
        line doesn't zig-zag when the values weren't measured in order
        (e.g. a pH series like 5, 6, 7, 5, 4, 6, 7.2) — this only
        changes the order points are DRAWN in this plot; it has no
        effect on the underlying data, on Excel/text export, or on
        anything other than this one plot.

        The "Spectrum labels" mode, by contrast, deliberately does NOT
        reorder — labels are shown in the exact order spectra appear in
        the main window's list, per the user's request.
        """
        if self.use_parameter_axis and self.svd_controller is not None:
            manager = getattr(self.svd_controller, 'manager', None)
            values = getattr(manager, 'parameter_values', None) if manager else None
            if values is not None and len(values) == n:
                label = (getattr(manager, 'parameter_label', None) or 'Parameter value')
                order = np.argsort(values)
                return np.asarray(values)[order], label, order, None
        if self.use_label_axis and self.svd_controller is not None:
            manager = getattr(self.svd_controller, 'manager', None)
            labels = getattr(manager, 'spectrum_labels', None) if manager else None
            if labels is not None and len(labels) == n:
                order = np.arange(n)
                labels = list(labels)
                # Honor this dialog's OWN "Shorten names" checkbox (see
                # get_shorten_enabled above) — independent of the main
                # window's checkbox of the same name.
                if self.get_shorten_enabled is not None and self.get_shorten_enabled():
                    short_map = compute_distinguishing_labels(labels)
                    labels = [short_map.get(lbl, lbl) for lbl in labels]
                return np.arange(1, n + 1), 'Spectrum', order, labels
        # Plain spectrum order, 1-based for display (Spectrum 1, 2, 3, ...
        # rather than 0, 1, 2, ...) — already ascending, so the order is
        # just the identity.
        return np.arange(1, n + 1), 'Spectrum Index', np.arange(n), None

    def _bar_width(self, x_positions):
        """Sensible bar width for arbitrary (possibly non-uniformly spaced)
        x positions — 0.8 for the default unit-spaced spectrum-order axis,
        scaled to the tightest gap when using parameter values."""
        if len(x_positions) > 1:
            diffs = np.diff(np.sort(np.unique(np.asarray(x_positions, dtype=float))))
            diffs = diffs[diffs > 0]
            if len(diffs) > 0:
                return 0.8 * np.min(diffs)
        return 0.8

    def _plot_single_coefficient(self, ax, idx, color):
        """Plot coefficients for a single subspectrum."""
        coefficients = self.svd_controller.get_coefficients(idx)
        
        if coefficients is not None:
            x_positions, xlabel, order, tick_labels = self._get_coefficient_xaxis(len(coefficients))
            coefficients = np.asarray(coefficients)[order]

            if self.coefficient_plot_type == 'bar':
                ax.bar(x_positions, coefficients, width=self._bar_width(x_positions), alpha=0.7, color=color)
            else:
                ax.plot(x_positions, coefficients, 'o-', alpha=0.7, color=color, markersize=4)

            ax.set_title(self._get_coefficient_label(idx), fontsize=10)
            ax.set_xlabel(xlabel, fontsize=8)
            ax.tick_params(labelsize=8)
            if tick_labels is not None:
                ax.set_xticks(x_positions)
                ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=7)
            ax.grid(True, alpha=0.3)
    
    def _plot_combined_coefficients(self, ax, colors):
        """Plot combined coefficients for all selected subspectra."""
        all_coefficients = []
        legend_labels = []
        
        for i, idx in enumerate(self.selected_subspectra):
            coefficients = self.svd_controller.get_coefficients(idx)
            if coefficients is not None:
                all_coefficients.append(coefficients)
                legend_labels.append(self._get_coefficient_label(idx))
        
        if all_coefficients:
            x_positions, xlabel, order, tick_labels = self._get_coefficient_xaxis(len(all_coefficients[0]))
            all_coefficients = [np.asarray(c)[order] for c in all_coefficients]
            
            if self.coefficient_plot_type == 'bar':
                base_width = self._bar_width(x_positions)
                width = base_width / len(all_coefficients)
                for i, coeffs in enumerate(all_coefficients):
                    offset = (i - len(all_coefficients)/2 + 0.5) * width
                    ax.bar(np.asarray(x_positions) + offset, coeffs, width, 
                           alpha=0.7, color=colors[i], label=legend_labels[i])
            else:
                for i, coeffs in enumerate(all_coefficients):
                    ax.plot(x_positions, coeffs, 'o-', alpha=0.7, 
                            color=colors[i], label=legend_labels[i], markersize=4)
            
            ax.set_title("Coefficients")
            ax.set_xlabel(xlabel)
            ax.set_ylabel('Coefficient Value')
            if tick_labels is not None:
                ax.set_xticks(x_positions)
                ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=7)
            ax.grid(True, alpha=0.3)
            ax.legend()

    def _get_subspectrum_label(self, idx, short=False):
        """Get subspectrum label based on display mode."""
        if self.label_provider is not None:
            return self.label_provider(idx, short=short)
        if self.value_display_mode == 'singular':
            if (self.svd_controller.manager.s is not None and 
                idx < len(self.svd_controller.manager.s)):
                singular_val = self.svd_controller.manager.s[idx]
                if short:
                    return f"S{idx + 1} (σ={singular_val:.2e})"
                else:
                    return f"Subspectrum {idx + 1} (σ={singular_val:.4e})"
        else:
            variance = 0
            if (self.svd_controller.manager.explained_variance is not None and 
                idx < len(self.svd_controller.manager.explained_variance)):
                variance = self.svd_controller.manager.explained_variance[idx]
            if short:
                return f"S{idx + 1} ({variance:.1f}%)"
            else:
                return f"Subspectrum {idx + 1} ({variance:.3f}% variance)"
        
        return f"Subspectrum {idx + 1}"

    def _get_coefficient_label(self, idx):
        """Get coefficient label based on display mode."""
        if self.coefficient_label_provider is not None:
            return self.coefficient_label_provider(idx)
        if self.value_display_mode == 'singular':
            if (self.svd_controller.manager.s is not None and 
                idx < len(self.svd_controller.manager.s)):
                singular_val = self.svd_controller.manager.s[idx]
                return f"V{idx + 1} (σ={singular_val:.2e})"
            else:
                return f"V{idx + 1}"
        else:
            variance = 0
            if (self.svd_controller.manager.explained_variance is not None and 
                idx < len(self.svd_controller.manager.explained_variance)):
                variance = self.svd_controller.manager.explained_variance[idx]
            return f"V{idx + 1} ({variance:.1f}%)"

class SVDDiagnosticsDialog(QWidget):
    """
    Diagnostics panel for SVD analysis — embedded as a tab in
    SVDAnalysisDialog (formerly a standalone modal window, opened via a
    "Diagnostics…" button; kept the same class name and internal structure
    to minimize the size of that change).

    Metrics available
    -----------------
    sv        Singular values σᵢ
    ev        Explained variance per component (%)
    cum_ev    Cumulative explained variance (%)
    unexpl    Cumulative unexplained variance (%)
    RE        Residual error E(m)
    IND       Malinowski IND function

    Modes
    -----
    Single    Plot one metric vs component number
    Compare   Side-by-side plot of two metrics against component number
    Overview  Fixed 2×3 grid showing all six metrics at once
    """

    # ------------------------------------------------------------------ #
    # Metric catalogue — single source of truth                           #
    # ------------------------------------------------------------------ #
    METRICS = {
        'Singular values (σ)': {
            'key': 'sv',
            'color': '#1565C0',
            'marker': 'o',
            'log': True,
            'ylabel': 'σ  (log scale)',
            'ylabel_linear': 'σ',
            'title': 'Singular values',
            'tooltip': (
                'σᵢ = square root of the variance explained by component i.\n'
                'Look for a kink where the steep drop flattens — that marks the signal-to-noise boundary.\n\n'
                'Formula: X = U × diag(σ) × Vᵀ'
            ),
        },
        'Eigenvalue (σ²)': {
            'key': 'eigenvalue',
            'color': '#0D47A1',
            'marker': 'o',
            'log': True,
            'ylabel': 'Eigenvalue  (log scale)',
            'ylabel_linear': 'Eigenvalue',
            'title': 'Eigenvalues',
            'tooltip': (
                'Eigenvalue = σᵢ² — the absolute amount of variance component i\n'
                'accounts for, before converting to a percentage (Explained variance).\n\n'
                'For raw, unnormalized spectral intensities, eigenvalues commonly reach\n'
                '1e8–1e16 or beyond — this is expected, not a sign of a problem. Eigenvalue\n'
                'scales with the square of the data\'s absolute intensity scale, so it carries\n'
                'no inherent "normal" range; only its relative size across components matters.'
            ),
        },
        'Explained variance (%)': {
            'key': 'ev',
            'color': '#1976D2',
            'marker': None,   # bar chart
            'log': False,
            'ylabel': 'Explained variance (%)',
            'title': 'Explained variance per component',
            'tooltip': (
                'EV_i = σᵢ² / Σσⱼ² × 100%\n\n'
                'The fraction of total spectral variance explained by each\n'
                'individual component. Component 1 always has the largest value.\n'
                'Components beyond the signal-to-noise boundary typically each\n'
                'contribute < 1% and collectively form a flat tail.'
            ),
        },
        'Cumulative explained var. (%)': {
            'key': 'cum_ev',
            'color': '#2E7D32',
            'marker': 'o',
            'log': False,
            'ylabel': 'Cumulative explained variance (%)',
            'title': 'Cumulative explained variance',
            'tooltip': (
                'Cum_EV(N) = Σᵢ₌₁ᴺ EV_i\n\n'
                'Running total of variance explained when using the first N components.\n'
                'Threshold lines at 95% and 99% are annotated with the number of\n'
                'components required to reach them.\n'
                'Reaching 99% typically requires far fewer components than the\n'
                'total number of spectra.'
            ),
        },
        'Cumulative unexplained var. (%)': {
            'key': 'unexpl',
            'color': '#C62828',
            'marker': 'o',
            'log': False,
            'ylabel': 'Cumulative unexplained variance (%)',
            'title': 'Cumulative unexplained variance',
            'tooltip': (
                'Unexpl(N) = 100% − Cum_EV(N)\n\n'
                'The fraction of total variance NOT captured by the first N components.\n'
                'Useful for assessing how much information is lost when truncating\n'
                'the decomposition. The curve should flatten near zero once the\n'
                'signal components are included.'
            ),
        },
        'Residual error E(m)': {
            'key': 'RE',
            'color': '#E65100',
            'marker': 'o',
            'log': True,
            'ylabel': 'Residual error  (log scale)',
            'ylabel_linear': 'Residual error',
            'title': 'Residual error vs components retained',
            'tooltip': (
                'E(m) = √[ Σᵢ>m σᵢ² / ((n_pts − m − 1)(n_sp − m − 1)) ]\n\n'
                'Root-mean-square residual normalised by degrees of freedom.\n'
                'Monotonically decreasing for typical spectral data (n_pts >> n_sp).\n'
                'Look for the elbow — the point where the rate of decrease visibly flattens.\n'
                'Components to the left of the elbow carry real signal;\n'
                'those to the right add mostly noise.\n\n'
                'Log scale is recommended for finding the elbow: on a linear scale the\n'
                'first components dominate the axis and compress the rest into a narrow\n'
                'band, making the elbow invisible. Log scale gives equal visual space\n'
                'to each order of magnitude so the slope change is clearly visible.\n\n'
                'Note: has no true minimum for spectroscopic data.'
            ),
        },
        'Malinowski IND': {
            'key': 'IND',
            'color': '#6A1B9A',
            'marker': 'o',
            'log': True,
            'ylabel': 'IND  (log scale)',
            'ylabel_linear': 'IND',
            'title': 'Malinowski IND function',
            'tooltip': (
                'IND(m) = RE(m) / (n_sp − m)²\n\n'
                'where RE(m) = √[ Σᵢ>m σᵢ² / (n_pts × (n_sp − m)) ]\n\n'
                'Dividing RE by (n_sp − m)² creates a competing effect:\n'
                'as m increases the numerator (residual) decreases but the\n'
                'denominator shrinks faster in the noise regime, causing IND\n'
                'to turn upward. The MINIMUM of IND marks the statistically\n'
                'optimal number of components to retain.\n\n'
                'Reliability: IND works best when n_pts >> n_sp (ratio > 10).\n'
                'For large or nearly-square datasets (n_pts/n_sp < 5), the\n'
                'denominator shrinks too slowly and the minimum may be\n'
                'unreliable. Use visual inspection of subspectra instead.\n\n'
                'Reference: Malinowski, E.R. (2002) Factor Analysis in Chemistry,\n'
                '3rd ed., John Wiley & Sons.'
            ),
        },
    }

    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        self.controller = controller

        # Debounce timer — redraws after window resize settles
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._refresh_plot)

        self._compute_metrics()
        self._setup_ui()

        # Install resize event filter on the canvas so plot redraws when dialog is resized
        self.canvas.installEventFilter(self)

        self._refresh_plot()

    def refresh(self):
        """Re-pull metrics from the controller and redraw. As an embedded
        tab this widget is constructed once, up front — possibly before
        any SVD data exists yet — rather than lazily when a "Diagnostics…"
        button used to be clicked. Call this whenever new SVD results
        become available (mirrors what __init__ already does for the
        first-ever computation)."""
        self._compute_metrics()
        self._refresh_plot()

    # ------------------------------------------------------------------ #
    # Data preparation                                                     #
    # ------------------------------------------------------------------ #
    def eventFilter(self, obj, event):
        """Restart the debounce timer whenever the canvas is resized."""
        if obj is self.canvas and event.type() == QEvent.Resize:
            self._resize_timer.start(200)
        return False   # never consume the event

    def _compute_metrics(self):
        manager = self.controller.manager
        ev_raw = manager.explained_variance
        s_raw  = manager.s
        info   = self.controller.get_svd_components_info()
        summary = self.controller.get_analysis_summary()

        self.n_comp = info['n_components'] if info else 0
        self.n_pts  = info['n_datapoints'] if info else 0
        self.n_sp   = summary.get('n_spectra', 0)
        self.comps  = np.arange(1, self.n_comp + 1)

        self.data = {}
        self.data['sv']    = s_raw  if s_raw  is not None else np.array([])
        self.data['eigenvalue'] = (s_raw ** 2) if s_raw is not None else np.array([])
        self.data['ev']    = ev_raw if ev_raw is not None else np.array([])
        cum = np.cumsum(ev_raw) if ev_raw is not None else np.array([])
        self.data['cum_ev']  = cum
        self.data['unexpl']  = 100.0 - cum if len(cum) else np.array([])
        re = self.controller.calculate_residual_errors()
        self.data['RE'] = re if re is not None else np.array([])

        # Malinowski IND
        if s_raw is not None and self.n_sp > 1:
            eigenvalues = s_raw ** 2
            k = len(s_raw)
            IND = np.zeros(k - 1)
            for m in range(k - 1):
                res_var = np.sum(eigenvalues[m+1:])
                re_m = np.sqrt(res_var / (self.n_pts * (self.n_sp - m))) if (self.n_pts * (self.n_sp - m)) > 0 else 0
                dof = (self.n_sp - m) ** 2
                IND[m] = re_m / dof if dof > 0 else 0
            self.data['IND'] = IND
        else:
            self.data['IND'] = np.array([])

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        outer = QHBoxLayout(self)

        # ---- Left control panel ----
        left = QWidget()
        left.setFixedWidth(300)
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(8)

        # Summary box
        summary_group = QGroupBox("Summary")
        sg_layout = QVBoxLayout(summary_group)
        cum = self.data['cum_ev']
        n95 = int(np.searchsorted(cum, 95) + 1) if len(cum) else '?'
        n99 = int(np.searchsorted(cum, 99) + 1) if len(cum) else '?'
        top5  = float(np.sum(self.data['ev'][:5]))              if len(self.data['ev']) else 0
        top10 = float(np.sum(self.data['ev'][:min(10, self.n_comp)])) if len(self.data['ev']) else 0
        IND   = self.data['IND']
        ind_min_n = int(np.argmin(IND) + 1) if len(IND) > 0 else '?'
        ind_min_v = f"{IND[np.argmin(IND)]:.3g}" if len(IND) > 0 else '?'

        # IND reliability warning: unreliable when n_sp is not << n_pts
        ind_warning = ""
        if self.n_pts > 0 and self.n_sp > 0:
            ratio = self.n_pts / self.n_sp
            if ratio < 5:
                ind_warning = (
                    "<br><span style='color:#C62828;'>"
                    "<b>&#9888; IND warning:</b> n_pts/n_sp = "
                    f"{self.n_pts}/{self.n_sp} = {ratio:.1f}. "
                    "IND is unreliable when this ratio is &lt; 5 "
                    "(dataset is nearly square). "
                    "Use visual inspection of subspectra and the singular value "
                    "kink instead."
                    "</span>"
                )
            elif ratio < 10:
                ind_warning = (
                    "<br><span style='color:#E65100;'>"
                    "<b>&#9888; IND note:</b> n_pts/n_sp = "
                    f"{self.n_pts}/{self.n_sp} = {ratio:.1f}. "
                    "IND works best when n_pts &gt;&gt; n_sp (ratio &gt; 10). "
                    "Treat the IND minimum as a rough guide only."
                    "</span>"
                )

        summary_text = (
            f"<b>Components:</b> {self.n_comp}<br>"
            f"<b>Spectra:</b> {self.n_sp}<br>"
            f"<b>Wavelength pts:</b> {self.n_pts}<br>"
            f"<b>Variance top-5:</b> {top5:.1f}%<br>"
            f"<b>Variance top-10:</b> {top10:.1f}%<br>"
            f"<b>N for 95% var.:</b> {n95}<br>"
            f"<b>N for 99% var.:</b> {n99}<br>"
            f"<b>IND minimum at:</b> N={ind_min_n} (IND={ind_min_v})"
            f"{ind_warning}"
        )
        lbl = QLabel(summary_text)
        lbl.setWordWrap(True)
        sg_layout.addWidget(lbl)
        left_layout.addWidget(summary_group)

        # View mode
        mode_group = QGroupBox("View mode")
        mode_layout = QVBoxLayout(mode_group)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Single metric", "Compare two metrics", "Overview (all)"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)

        self.overview_log_cb = QCheckBox("Log scale (overview)")
        self.overview_log_cb.setChecked(False)
        self.overview_log_cb.setToolTip(
            "Force log scale on all six panels in the Overview.\n"
            "When unchecked, each panel uses its own metric's default scale\n"
            "(σ, E, IND → log; variance metrics → linear)."
        )
        self.overview_log_cb.setVisible(False)
        self.overview_log_cb.stateChanged.connect(self._refresh_plot)
        mode_layout.addWidget(self.overview_log_cb)
        left_layout.addWidget(mode_group)

        # Single metric selector
        self.single_group = QGroupBox("Metric")
        single_layout = QVBoxLayout(self.single_group)
        self.single_combo = QComboBox()
        for name in self.METRICS:
            self.single_combo.addItem(name)
        self.single_combo.currentIndexChanged.connect(self._on_single_metric_changed)
        single_layout.addWidget(self.single_combo)

        self.log_scale_cb = QCheckBox("Log scale (y-axis)")
        self.log_scale_cb.setChecked(True)   # most metrics default to log
        self.log_scale_cb.setToolTip(
            "Log scale spreads out small values so structure in the noise region is visible.\n"
            "Linear scale is easier to read for variance metrics (% values).\n"
            "The checkbox resets to the metric's default when you change metric."
        )
        self.log_scale_cb.stateChanged.connect(self._refresh_plot)
        single_layout.addWidget(self.log_scale_cb)

        self.info_btn = QPushButton("ℹ  What does this metric mean?")
        self.info_btn.clicked.connect(self._show_metric_info)
        single_layout.addWidget(self.info_btn)
        left_layout.addWidget(self.single_group)

        # Compare selectors
        self.compare_group = QGroupBox("Compare metrics (side by side)")
        compare_layout = QVBoxLayout(self.compare_group)

        compare_layout.addWidget(QLabel("Metric 1 (left):"))
        self.x_combo = QComboBox()
        for name in self.METRICS:
            self.x_combo.addItem(name)
        self.x_combo.currentIndexChanged.connect(self._on_x_metric_changed)
        compare_layout.addWidget(self.x_combo)
        self.x_log_cb = QCheckBox("Log scale (left panel)")
        self.x_log_cb.stateChanged.connect(self._refresh_plot)
        compare_layout.addWidget(self.x_log_cb)

        compare_layout.addWidget(QLabel("Metric 2 (right):"))
        self.y_combo = QComboBox()
        for name in self.METRICS:
            self.y_combo.addItem(name)
        self.y_combo.setCurrentIndex(4)  # default = RE
        self.y_combo.currentIndexChanged.connect(self._on_y_metric_changed)
        compare_layout.addWidget(self.y_combo)
        self.y_log_cb = QCheckBox("Log scale (right panel)")
        self.y_log_cb.stateChanged.connect(self._refresh_plot)
        compare_layout.addWidget(self.y_log_cb)

        self.compare_info_btn = QPushButton("ℹ  What does this comparison mean?")
        self.compare_info_btn.clicked.connect(self._show_compare_info)
        compare_layout.addWidget(self.compare_info_btn)

        self.compare_group.setVisible(False)
        left_layout.addWidget(self.compare_group)

        # Initialise per-panel log checkboxes to each metric's default
        # Block signals so setting the value doesn't trigger _refresh_plot before self.fig exists
        x_meta = self.METRICS[self.x_combo.currentText()]
        y_meta = self.METRICS[self.y_combo.currentText()]
        self.x_log_cb.blockSignals(True)
        self.x_log_cb.setChecked(x_meta['log'])
        self.x_log_cb.blockSignals(False)
        self.y_log_cb.blockSignals(True)
        self.y_log_cb.setChecked(y_meta['log'])
        self.y_log_cb.blockSignals(False)

        left_layout.addStretch()

        # Full table view
        table_group = QGroupBox("Full table")
        table_layout = QVBoxLayout(table_group)
        btn_table = QPushButton("Show all metrics (table)…")
        btn_table.setToolTip(
            "Opens all six metrics, for every component, as one table\n"
            "in a larger window — easier to scan than the plot alone."
        )
        btn_table.clicked.connect(self._show_metrics_table)
        table_layout.addWidget(btn_table)
        left_layout.addWidget(table_group)

        # Export
        export_group = QGroupBox("Quick export (CSV)")
        ex_layout = QVBoxLayout(export_group)
        btn_all = QPushButton("Export all metrics…")
        btn_all.setToolTip(
            "Saves one CSV with all metrics side-by-side:\n"
            "Component, σ, EV%, Cum_EV%, Unexpl%, RE, IND"
        )
        btn_all.clicked.connect(self._export_all)
        ex_layout.addWidget(btn_all)

        btn_cur = QPushButton("Export current plot data…")
        btn_cur.setToolTip("Saves only the data visible in the current plot")
        btn_cur.clicked.connect(self._export_current)
        ex_layout.addWidget(btn_cur)
        left_layout.addWidget(export_group)

        outer.addWidget(left)

        # ---- Right canvas panel ----
        right = QWidget()
        right_layout = QVBoxLayout(right)

        from matplotlib.figure import Figure as MplFigure
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FC
        from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NT

        self.fig = MplFigure(figsize=(11, 7))
        self.canvas = FC(self.fig)
        self.toolbar = NT(self.canvas, right)
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas)
        outer.addWidget(right)

    # ------------------------------------------------------------------ #
    # Plot rendering                                                       #
    # ------------------------------------------------------------------ #
    def _on_mode_changed(self):
        mode = self.mode_combo.currentText()
        self.single_group.setVisible(mode == "Single metric")
        self.compare_group.setVisible(mode == "Compare two metrics")
        self.overview_log_cb.setVisible(mode == "Overview (all)")
        self._refresh_plot()

    def _refresh_plot(self):
        if not hasattr(self, 'fig'):
            return
        self.fig.clear()
        mode = self.mode_combo.currentText()
        if mode == "Single metric":
            self._plot_single()
        elif mode == "Compare two metrics":
            self._plot_compare()
        else:
            self._plot_overview()
        self.fig.tight_layout(pad=1.5)
        self.canvas.draw()

    def _get_x_for_key(self, key):
        """Return the component-number x-axis appropriate for a given metric key."""
        d = self.data[key]
        return np.arange(1, len(d) + 1)

    def _plot_one(self, ax, metric_name, override_log=None):
        """Plot a single metric on the given axes."""
        meta = self.METRICS[metric_name]
        key  = meta['key']
        d    = self.data.get(key, np.array([]))
        if len(d) == 0:
            ax.text(0.5, 0.5, 'No data', transform=ax.transAxes,
                    ha='center', va='center', color='gray')
            return
        x = self._get_x_for_key(key)
        color = meta['color']
        use_log = override_log if override_log is not None else meta['log']

        if meta['marker'] is None:
            # bar chart (EV% only) — respect log scale
            ax.bar(x, d, color=color, alpha=0.85)
            if use_log:
                ax.set_yscale('log')
        else:
            if use_log:
                ax.semilogy(x, d, color=color, marker=meta['marker'],
                            ms=5, lw=1.5)
            else:
                ax.plot(x, d, color=color, marker=meta['marker'],
                        ms=5, lw=1.5)

        # Annotations for special metrics
        if key == 'cum_ev':
            cum = d
            for thresh, tc in [(95, '#2E7D32'), (99, '#E65100')]:
                idx = np.searchsorted(cum, thresh)
                if idx < len(cum):
                    ax.axhline(thresh, color=tc, ls='--', lw=1, alpha=0.7)
                    if use_log:
                        ax.text(idx + 1.3, thresh,
                                f'N={idx+1} ({thresh}%)',
                                fontsize=7, color=tc, va='center',
                                bbox=dict(boxstyle='round,pad=0.2',
                                          facecolor='white', edgecolor='none', alpha=0.85))
                    else:
                        ax.annotate(f'N={idx+1} ({thresh}%)', xy=(idx+1, thresh),
                                    xytext=(idx+2, thresh - 8),
                                    arrowprops=dict(arrowstyle='->', color=tc),
                                    fontsize=7, color=tc,
                                    bbox=dict(boxstyle='round,pad=0.2',
                                              facecolor='white', edgecolor='none', alpha=0.85))
            if not use_log:
                ax.set_ylim(0, 105)

        if key == 'IND' and len(d) > 0:
            min_idx = int(np.argmin(d))
            # Use ax.plot not ax.semilogy — the axis scale is already set by the main plot call above
            ax.plot(min_idx + 1, d[min_idx], 'k*', ms=12, zorder=5,
                    label=f'Min at N={min_idx+1}')
            ax.legend(fontsize=8)

        if key == 'RE':
            ax.text(0.97, 0.97, 'Look for the elbow',
                    transform=ax.transAxes, ha='right', va='top', fontsize=7,
                    color='#555', bbox=dict(boxstyle='round,pad=0.2',
                                            facecolor='#fffde7', alpha=0.8))

        ylabel = meta['ylabel'] if use_log else meta.get('ylabel_linear', meta['ylabel'])
        ax.set_xlabel('Component')
        ax.set_ylabel(ylabel)
        ax.set_title(meta['title'])
        ax.grid(True, alpha=0.3)

    def _plot_single(self):
        ax = self.fig.add_subplot(111)
        name = self.single_combo.currentText()
        use_log = self.log_scale_cb.isChecked()
        self._plot_one(ax, name, override_log=use_log)

    def _on_single_metric_changed(self):
        """When the metric changes, sync the checkbox to the metric's default log setting,
        then redraw. The user can override after that."""
        name = self.single_combo.currentText()
        meta = self.METRICS[name]
        self.log_scale_cb.blockSignals(True)
        self.log_scale_cb.setChecked(meta['log'])
        self.log_scale_cb.blockSignals(False)
        self._refresh_plot()

    # ------------------------------------------------------------------ #
    # Compare-mode interpretation text                                     #
    # ------------------------------------------------------------------ #
    COMPARE_HELP = {
        frozenset(['sv', 'RE']): (
            "Singular values (σ) vs Residual error E(m)\n\n"
            "• Both curves decrease as the component number increases.\n"
            "• In the σ curve: if it drops steeply for the first few components and then "
            "flattens suddenly, that flat region is the noise. "
            "The component where the steep drop ends is the boundary.\n"
            "• Check the E curve at the same component number: E should also show a change "
            "in slope there — decreasing faster before and more slowly after. "
            "If both curves show a change at the same N, that confirms N is optimal.\n"
            "• If σ flattens early but E keeps dropping noticeably, the two metrics "
            "disagree — E is still detecting residual variance that σ alone would miss. "
            "Check the IND curve for a more reliable criterion."
        ),
        frozenset(['sv', 'IND']): (
            "Singular values (σ) vs Malinowski IND\n\n"
            "This is the most informative comparison for finding the optimal N "
            "— when IND is reliable (see caveat below).\n\n"
            "• In the σ curve: look for where it transitions from steep to flat. "
            "That transition marks the signal-to-noise boundary.\n"
            "• In the IND curve: unlike σ and E which always decrease, IND has a "
            "genuine minimum — it decreases at first, reaches a lowest point, then "
            "rises again. The component at the minimum is the statistically optimal N.\n"
            "• The component where σ flattens should coincide with the IND minimum. "
            "If they agree, the result is robust.\n"
            "• After the IND minimum, IND rises because the degrees-of-freedom "
            "denominator (n_sp − m)² shrinks faster than the residual variance — "
            "adding those components is statistically unjustified even if σ is not zero.\n"
            "• Components before the IND minimum with visibly larger σ values are real signal. "
            "Components after the minimum with nearly flat σ are noise.\n\n"
            "IND RELIABILITY CAVEAT:\n"
            "IND was developed for small datasets where n_pts >> n_sp (ratio > 10).\n"
            "When n_pts/n_sp < 5 (nearly square matrix — common in UV-Vis, large "
            "spectral series), the denominator (n_sp − m)² shrinks too slowly and "
            "the IND minimum shifts to a falsely high N.\n"
            "In those cases: rely on the σ kink and visual inspection of subspectra. "
            "A warning appears in the Diagnostics summary when this condition is met."
        ),
        frozenset(['RE', 'IND']): (
            "Residual error E(m) vs Malinowski IND\n\n"
            "Both metrics are derived from the same residual variance, but IND "
            "divides by (n_sp − m)² while E divides by the full degrees of freedom.\n\n"
            "• E always decreases — the curve never turns upward.\n"
            "• IND decreases at first, reaches a minimum, then rises. "
            "The minimum is the statistically optimal N.\n"
            "• Look at where E starts flattening — the rate of decrease slows visibly. "
            "Compare that component to the IND minimum. If they coincide, the result is robust.\n"
            "• If E still drops noticeably after the IND minimum, the two criteria "
            "disagree — IND says stop, but E says there is still residual variance "
            "worth capturing. Inspect those components visually to decide.\n\n"
            "IND reliability: works best when n_pts >> n_sp. "
            "If n_pts/n_sp < 5, the IND minimum may be unreliable — see the "
            "Diagnostics summary warning."
        ),
        frozenset(['cum_ev', 'IND']): (
            "Cumulative explained variance (%) vs Malinowski IND\n\n"
            "• cum_ev is a running total that rises from 0% toward 100% as more "
            "components are added. It rises steeply for real-signal components and "
            "flattens for noise components.\n"
            "• IND has a genuine minimum at the statistically optimal N. "
            "Find that N in the IND curve, then read off the corresponding cum_ev value "
            "to see how much cumulative variance that N represents.\n"
            "• If the IND minimum falls where cum_ev has already flattened near 95–99%, "
            "the statistical and variance criteria agree.\n"
            "• If the IND minimum occurs where cum_ev is still rising steeply and has "
            "not yet reached 90%, IND may be too conservative — consider retaining "
            "additional components on scientific grounds.\n\n"
            "IND reliability: works best when n_pts >> n_sp. "
            "If n_pts/n_sp < 5, the IND minimum may be unreliable — check the "
            "Diagnostics summary warning and rely on the cum_ev elbow instead."
        ),
        frozenset(['sv', 'ev']): (
            "Singular values (σ) vs Explained variance per component (%)\n\n"
            "These two metrics are mathematically related: EV_i = σᵢ² / Σσⱼ² × 100%.\n"
            "Comparing them reveals the same information on two different scales.\n\n"
            "• The two curves will show nearly identical shapes — they cannot "
            "disagree because one is a direct transformation of the other.\n"
            "• Use this view to calibrate your intuition: see how a given σ value "
            "corresponds to a % of explained variance for the same component."
        ),
        frozenset(['sv', 'cum_ev']): (
            "Singular values (σ) vs Cumulative explained variance (%)\n\n"
            "• σ measures each component's individual contribution; cum_ev shows the "
            "running total. Together they answer: 'how much do I gain by adding one more?'\n"
            "• Each jump upward in the cum_ev curve equals the variance explained by "
            "that component, which is proportional to σᵢ². A component with large σ "
            "causes a large visible jump in cum_ev; a component with small σ barely "
            "moves the cum_ev curve.\n"
            "• Look for the component where σ drops sharply AND cum_ev flattens. "
            "That double signal confirms the noise boundary.\n"
            "• The kink in σ and the elbow in cum_ev should coincide at the optimal N."
        ),
        frozenset(['sv', 'unexpl']): (
            "Singular values (σ) vs Cumulative unexplained variance (%)\n\n"
            "• Unexplained variance = 100% − cumulative explained variance.\n"
            "• As more components are retained, both σ and unexplained variance decrease.\n"
            "• Look for a component where σ shows a sudden large drop AND unexplained "
            "variance shows a corresponding sudden large downward jump. Both happening "
            "at the same component number confirms that component carries real signal.\n"
            "• After that component, σ values typically become much smaller and decrease "
            "only gradually — and unexplained variance flattens and barely changes "
            "from one component to the next. That flat region is noise.\n"
            "• The component where σ transitions from steep to flat, and unexplained "
            "variance stops dropping noticeably, is the optimal N."
        ),
        frozenset(['ev', 'RE']): (
            "Explained variance per component (%) vs Residual error E(m)\n\n"
            "• EV shows each component's individual share of total variance. "
            "E shows the total reconstruction error when that component and all higher "
            "ones are excluded — it decreases as more components are retained.\n"
            "• The first few components typically have visibly taller EV bars, AND "
            "the E curve drops steeply at the same components. Those are real signal.\n"
            "• When the EV bars become so small they are barely visible above zero, "
            "but E is still dropping noticeably, it means many small components together "
            "still carry meaningful variance — consider keeping more than the IND minimum suggests.\n"
            "• When both the EV bars are barely visible AND E has flattened and barely "
            "changes from one component to the next, those components are noise."
        ),
        frozenset(['ev', 'IND']): (
            "Explained variance per component (%) vs Malinowski IND\n\n"
            "• EV measures individual contribution; IND measures statistical justification "
            "for including each additional component.\n"
            "• The component at the IND minimum should have a noticeably larger EV bar "
            "than the components after it. If EV is similar for N and N+1, IND may be "
            "identifying the wrong boundary.\n"
            "• Components with EV > 1% but rising IND are borderline — examine them "
            "visually before deciding to include or exclude.\n"
            "• The component where EV drops sharply should align with the IND minimum.\n\n"
            "IND reliability: works best when n_pts >> n_sp. "
            "If n_pts/n_sp < 5, the IND minimum may be unreliable."
        ),
        frozenset(['ev', 'cum_ev']): (
            "Explained variance per component (%) vs Cumulative explained variance (%)\n\n"
            "• EV is a bar chart showing each component's individual share. "
            "Tall bars = real signal. Bars barely visible above zero = noise.\n"
            "• cum_ev is a running total rising from 0% toward 100%. "
            "It rises steeply when EV bars are tall, and flattens when they are tiny.\n"
            "• The component where the EV bars transition from tall to barely visible "
            "is the same component where the cum_ev curve flattens. "
            "That is the signal-to-noise boundary.\n"
            "• The 95% and 99% threshold lines on the cum_ev curve let you read off "
            "how many components are needed to reach those benchmarks, and compare "
            "those numbers against where the EV bars become negligible."
        ),
        frozenset(['ev', 'unexpl']): (
            "Explained variance per component (%) vs Cumulative unexplained variance (%)\n\n"
            "• Each component reduces the unexplained variance by exactly its own EV.\n"
            "• The unexplained curve is therefore a mirror of the cumulative EV curve — "
            "a smooth monotone descent with no additional diagnostic value.\n"
            "• The EV bar chart and the unexplained descending line show the same "
            "information from complementary angles, making it easy to see which "
            "components make a meaningful dent in the total unexplained variance."
        ),
        frozenset(['cum_ev', 'RE']): (
            "Cumulative explained variance (%) vs Residual error E(m)\n\n"
            "• Both measure 'how much is left unexplained', but on different scales.\n"
            "• cum_ev is normalised to 100% (fraction of total variance). E(m) is "
            "normalised by degrees of freedom — it depends on the actual magnitudes.\n"
            "• A component that increases cum_ev substantially and also reduces E "
            "substantially is unambiguously real signal.\n"
            "• Divergence between the two (cum_ev plateaus but E still drops, or vice "
            "versa) indicates that the degree-of-freedom correction in E is doing "
            "significant work — worth checking that the data matrix is not rank-deficient."
        ),
        frozenset(['cum_ev', 'unexpl']): (
            "Cumulative explained variance (%) vs Cumulative unexplained variance (%)\n\n"
            "• These two metrics always sum to 100%, so one curve is always a "
            "perfect mirror of the other. There is no diagnostic information in this comparison.\n\n"
            "• Compare either of them against E(m) or IND for a more informative view."
        ),
        frozenset(['unexpl', 'RE']): (
            "Cumulative unexplained variance (%) vs Residual error E(m)\n\n"
            "• Both decrease as more components are retained, but at different rates.\n"
            "• Unexplained variance is normalised to the total variance (scale-free). "
            "E(m) is in absolute units (intensity²/degree-of-freedom).\n"
            "• If they decrease at the same rate, the data has uniform noise and the "
            "variance-based and error-based criteria will agree.\n"
            "• If E drops faster than unexplained variance in the early components, "
            "the leading components have above-average noise — check for outlier spectra.\n"
            "• If unexplained variance drops faster in the early components, the leading "
            "components are very clean and the noise is concentrated in the tail."
        ),
        frozenset(['unexpl', 'IND']): (
            "Cumulative unexplained variance (%) vs Malinowski IND\n\n"
            "• Unexplained variance shows what fraction of total information is still "
            "missing; IND shows whether including more components is statistically justified.\n"
            "• The IND minimum at N means: including component N+1 causes more "
            "statistical penalty than benefit. The unexplained variance at that N "
            "tells you the practical cost — how much information you are leaving out.\n"
            "• If unexplained variance at the IND minimum is still large (> 10%), "
            "you may want to override the IND criterion and include more components "
            "on scientific grounds.\n"
            "• This is the most useful comparison for deciding whether to follow IND "
            "strictly or keep additional components for scientific reasons.\n\n"
            "IND reliability: works best when n_pts >> n_sp. "
            "If n_pts/n_sp < 5, the IND minimum may be unreliable — the unexplained "
            "variance elbow is then a more reliable guide."
        ),
    }

    def _get_compare_help_text(self):
        x_key = self.METRICS[self.x_combo.currentText()]['key']
        y_key = self.METRICS[self.y_combo.currentText()]['key']
        pair = frozenset([x_key, y_key])
        if pair in self.COMPARE_HELP:
            return self.COMPARE_HELP[pair]
        # Generic fallback
        xn = self.x_combo.currentText()
        yn = self.y_combo.currentText()
        return (
            f"{xn} vs {yn}\n\n"
            "Both metrics are plotted side by side against component number.\n\n"
            "Look for features that align between the two plots:\n"
            "• Kinks, elbows, or sudden changes that occur at the same component N\n"
            "  in both panels confirm that N is a real signal-to-noise boundary.\n"
            "• A dashed vertical line marks the Malinowski IND minimum on both panels\n"
            "  so you can see how that criterion relates to each metric visually.\n"
            "• If the two metrics show different features at different N values,\n"
            "  inspect those components visually in the main SVD dialog."
        )

    def _show_compare_info(self):
        text = self._get_compare_help_text()
        QMessageBox.information(self, "About this comparison", text)

    def _on_x_metric_changed(self):
        if self.x_combo.currentIndex() == self.y_combo.currentIndex():
            next_idx = (self.y_combo.currentIndex() + 1) % self.y_combo.count()
            self.y_combo.blockSignals(True)
            self.y_combo.setCurrentIndex(next_idx)
            self.y_combo.blockSignals(False)
        # Sync left checkbox to new metric's default
        meta = self.METRICS[self.x_combo.currentText()]
        self.x_log_cb.blockSignals(True)
        self.x_log_cb.setChecked(meta['log'])
        self.x_log_cb.blockSignals(False)
        self._refresh_plot()

    def _on_y_metric_changed(self):
        if self.x_combo.currentIndex() == self.y_combo.currentIndex():
            next_idx = (self.x_combo.currentIndex() + 1) % self.x_combo.count()
            self.x_combo.blockSignals(True)
            self.x_combo.setCurrentIndex(next_idx)
            self.x_combo.blockSignals(False)
        # Sync right checkbox to new metric's default
        meta = self.METRICS[self.y_combo.currentText()]
        self.y_log_cb.blockSignals(True)
        self.y_log_cb.setChecked(meta['log'])
        self.y_log_cb.blockSignals(False)
        self._refresh_plot()

    def _plot_compare(self):
        self._plot_side_by_side()

    def _plot_side_by_side(self):
        x_name = self.x_combo.currentText()
        y_name = self.y_combo.currentText()
        ax1 = self.fig.add_subplot(1, 2, 1)
        ax2 = self.fig.add_subplot(1, 2, 2)
        self._plot_one(ax1, x_name, override_log=self.x_log_cb.isChecked())
        self._plot_one(ax2, y_name, override_log=self.y_log_cb.isChecked())
        if len(self.data['IND']) > 0:
            ind_min_n = int(np.argmin(self.data['IND'])) + 1
            for ax in [ax1, ax2]:
                ax.axvline(ind_min_n, color='purple', ls=':', lw=1.2, alpha=0.7,
                           label=f'IND min (N={ind_min_n})')
                ax.legend(fontsize=7)

    def _plot_overview(self):
        force_log = self.overview_log_cb.isChecked()
        names = list(self.METRICS.keys())
        for i, name in enumerate(names):
            ax = self.fig.add_subplot(2, 3, i + 1)
            self._plot_one(ax, name, override_log=True if force_log else None)

    # ------------------------------------------------------------------ #
    # Info popup                                                           #
    # ------------------------------------------------------------------ #
    def _show_metric_info(self):
        name = self.single_combo.currentText()
        meta = self.METRICS[name]
        QMessageBox.information(self, f"About: {name}", meta['tooltip'])

    # ------------------------------------------------------------------ #
    # Export                                                               #
    # ------------------------------------------------------------------ #
    def _export_csv(self, data_dict, default_name):
        import csv
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", default_name, "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(data_dict.keys())
            for row in zip(*data_dict.values()):
                w.writerow([f"{v:.10g}" if not isinstance(v, str) else v for v in row])
        QMessageBox.information(self, "Exported", f"Saved to:\n{path}")

    def _show_metrics_table(self):
        """Show all metrics, for every component, as a single table in
        a larger window — same data as Export all metrics, but for
        on-screen scanning rather than a CSV file."""
        d = self.data
        n = self.n_comp

        def pad(arr, length):
            if len(arr) == length:
                return arr
            out = np.full(length, np.nan)
            out[:len(arr)] = arr
            return out

        columns = [
            ('Component', self.comps, '{:d}'),
            ('Singular values (σ)', d['sv'] if len(d['sv']) else np.full(n, np.nan), '{:.6g}'),
            ('Eigenvalue (σ²)', d['eigenvalue'] if len(d['eigenvalue']) else np.full(n, np.nan), '{:.6g}'),
            ('Explained variance (%)', d['ev'] if len(d['ev']) else np.full(n, np.nan), '{:.4f}'),
            ('Cumulative explained var. (%)', d['cum_ev'] if len(d['cum_ev']) else np.full(n, np.nan), '{:.4f}'),
            ('Cumulative unexplained var. (%)', d['unexpl'] if len(d['unexpl']) else np.full(n, np.nan), '{:.4f}'),
            ('Residual error E(m)', pad(d['RE'], n), '{:.6g}'),
            ('Malinowski IND', pad(d['IND'], n), '{:.6g}'),
        ]

        dlg = QDialog(self)
        dlg.setWindowTitle('All SVD Metrics')
        dlg.setModal(True)
        dlg.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint)
        dlg.resize(1000, 700)
        vbox = QVBoxLayout(dlg)

        table = QTableWidget(n, len(columns))
        table.setHorizontalHeaderLabels([c[0] for c in columns])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        for col_idx, (_, values, fmt) in enumerate(columns):
            for row_idx in range(n):
                val = values[row_idx] if row_idx < len(values) else np.nan
                text = '\u2014' if (isinstance(val, float) and np.isnan(val)) else fmt.format(val)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row_idx, col_idx, item)
        vbox.addWidget(table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        export_btn = QPushButton('Export…')
        export_btn.clicked.connect(self._export_all)
        btn_row.addWidget(export_btn)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        vbox.addLayout(btn_row)

        dlg.exec_()

    def _export_all(self):
        d = self.data
        n = self.n_comp
        # RE and IND have length n-1; pad with NaN
        def pad(arr, length):
            if len(arr) == length:
                return arr
            out = np.full(length, np.nan)
            out[:len(arr)] = arr
            return out
        self._export_csv({
            'Component':            self.comps,
            'Singular_value':       d['sv']    if len(d['sv'])    else np.full(n, np.nan),
            'Eigenvalue':           d['eigenvalue'] if len(d['eigenvalue']) else np.full(n, np.nan),
            'Explained_var_pct':    d['ev']    if len(d['ev'])    else np.full(n, np.nan),
            'Cumulative_var_pct':   d['cum_ev']if len(d['cum_ev'])else np.full(n, np.nan),
            'Unexplained_var_pct':  d['unexpl']if len(d['unexpl'])else np.full(n, np.nan),
            'Residual_error':       pad(d['RE'],  n),
            'Malinowski_IND':       pad(d['IND'], n),
        }, 'svd_all_metrics.csv')

    def _export_current(self):
        mode = self.mode_combo.currentText()
        if mode == "Single metric":
            name = self.single_combo.currentText()
            key  = self.METRICS[name]['key']
            d    = self.data.get(key, np.array([]))
            x    = self._get_x_for_key(key)
            self._export_csv({'Component': x, name: d}, f'svd_{key}.csv')
        elif mode == "Compare two metrics":
            xn = self.x_combo.currentText()
            yn = self.y_combo.currentText()
            xk = self.METRICS[xn]['key']
            yk = self.METRICS[yn]['key']
            xd = self.data.get(xk, np.array([]))
            yd = self.data.get(yk, np.array([]))
            n  = min(len(xd), len(yd))
            self._export_csv({
                'Component': np.arange(1, n+1),
                xn: xd[:n], yn: yd[:n]
            }, f'svd_{xk}_vs_{yk}.csv')
        else:
            self._export_all()


class SVDAnalysisDialog(QDialog):
    """Dialog for SVD analysis visualization."""

    def __init__(self, parent=None, controller=None, spectra=None):
        super().__init__(parent)
        self.controller = controller
        self.spectra = spectra
        
        self.setWindowTitle("SVD Analysis")
        self.setModal(True)
        self.resize(1280, 760)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint)
        self.setAcceptDrops(True)  # drop a text file to load coefficient-plot parameter values
        
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        try:
            self.setup_ui()
        finally:
            QApplication.restoreOverrideCursor()
        
        self._initial_compute_pending = bool(self.controller and self.spectra)

    def showEvent(self, event):
        super().showEvent(event)

        from PyQt5.QtWidgets import QApplication

        # Defensive: clear any override cursor(s) still active once this
        # dialog is actually on screen. The real cause of the "stuck busy
        # cursor" bug is matplotlib's FigureCanvasQT.leaveEvent(), which
        # unconditionally calls QApplication.restoreOverrideCursor() whenever
        # the mouse leaves the canvas (see InteractiveSVDAnalysisCanvas.leaveEvent
        # for the full explanation, and the fix for that specific interaction).
        # But if whoever opens this dialog shows it under something like
        # QApplication.setOverrideCursor(Qt.WaitCursor) before calling
        # exec_(), that cursor won't be restored by the caller until the
        # dialog closes (exec_() blocks), so it stays active for the dialog's
        # entire lifetime regardless of whether anything is actually
        # computing. This dialog is interactive as soon as it's shown, so no
        # inherited "please wait" cursor should still be forcing a busy look.
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

        if self._initial_compute_pending:
            self._initial_compute_pending = False
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(50, self.initialize_svd)

    def setup_ui(self):
        """Set up the user interface."""
        layout = QHBoxLayout(self)

        self.main_tabs = QTabWidget()
        self.main_tabs.tabBar().setExpanding(False)
        self.main_tabs.setStyleSheet(
            "QTabBar::tab { min-width: 100px; padding: 4px 16px; }"
        )
        layout.addWidget(self.main_tabs)

        # Tab 1: Components — the original single-panel layout (control
        # panel + canvas), now living inside a tab instead of being the
        # dialog's only content.
        components_tab = QWidget()
        components_layout = QHBoxLayout(components_tab)
        components_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        components_layout.addWidget(splitter)
        
        # Left panel - Controls
        control_panel = self.create_control_panel()
        splitter.addWidget(control_panel)
        
        # Right panel - SVD visualization
        canvas_panel = self.create_canvas_panel()
        splitter.addWidget(canvas_panel)
        
        # Set initial splitter sizes (30% controls, 70% canvas)
        splitter.setSizes([450, 950])

        self.main_tabs.addTab(components_tab, "Components")

        # Tab 2: Diagnostics — previously a separate modal window opened
        # via a "Diagnostics…" button; embedded directly as a tab instead.
        # Built now (before any SVD data may exist) and refreshed via
        # self.diagnostics_panel.refresh() once computation succeeds —
        # see the success branch in run_svd_analysis (formerly where
        # show_info_btn.setEnabled(True) used to fire).
        self.diagnostics_panel = SVDDiagnosticsDialog(parent=self, controller=self.controller)
        self.main_tabs.addTab(self.diagnostics_panel, "Diagnostics")

    def create_control_panel(self):
        """Create the control panel with SVD analysis settings."""
        control_widget = QWidget()
        control_widget.setMinimumWidth(350)
        layout = QVBoxLayout(control_widget)
        layout.setSpacing(6)

        # ── 0. SVD settings ────────────────────────────────────────────
        svd_settings_group = QGroupBox("SVD settings")
        svd_settings_layout = QVBoxLayout(svd_settings_group)
        self.mean_center_cb = QCheckBox('Mean-center spectra before SVD')
        self.mean_center_cb.setChecked(False)
        self.mean_center_cb.setToolTip(
            "Subtract the mean spectrum (the average of every selected "
            "spectrum) before decomposing, so the components describe how "
            "spectra differ from each other rather than being dominated "
            "by whatever signal level they all share. Unchecked by "
            "default here to match this dialog's traditional raw-SVD "
            "convention; PCA / SVD Scores & Loadings defaults this on "
            "instead. Toggling recomputes instantly."
        )
        # stateChanged passes the new Qt.CheckState int through —
        # initialize_svd() takes no arguments, so a plain lambda discards
        # it rather than letting PyQt pass it straight through.
        self.mean_center_cb.stateChanged.connect(lambda _checked: self.initialize_svd())
        svd_settings_layout.addWidget(self.mean_center_cb)
        layout.addWidget(svd_settings_group)

        # ── 1. View SVD Components ─────────────────────────────────────
        components_group = QGroupBox("View SVD Components")
        comp_layout = QVBoxLayout(components_group)
        comp_layout.setSpacing(4)

        # Navigation row — Prev/Next adjacent, Jump label tight to spinbox
        nav_row = QHBoxLayout()
        nav_row.setSpacing(4)

        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.setToolTip("Navigate to the previous subspectrum")
        self.prev_btn.clicked.connect(self.prev_subspectrum)
        self.prev_btn.setEnabled(False)
        nav_row.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setToolTip("Navigate to the next subspectrum")
        self.next_btn.clicked.connect(self.next_subspectrum)
        self.next_btn.setEnabled(False)
        nav_row.addWidget(self.next_btn)

        nav_row.addSpacing(8)
        jump_label = QLabel("Jump:")
        jump_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        nav_row.addWidget(jump_label)
        self.subspectrum_spin = QSpinBox()
        self.subspectrum_spin.setMinimum(1)
        self.subspectrum_spin.setMaximum(1)
        self.subspectrum_spin.setFixedWidth(55)
        self.subspectrum_spin.setToolTip("Type or scroll to jump to any component number")
        self.subspectrum_spin.valueChanged.connect(self.change_subspectrum)
        self.subspectrum_spin.setEnabled(False)
        nav_row.addWidget(self.subspectrum_spin)

        nav_row.addSpacing(8)
        self.invert_btn = QPushButton("Invert")
        self.invert_btn.setToolTip(
            "Multiply this subspectrum (U column) and its coefficients (V row) by −1.\n"
            "SVD sign is arbitrary — invert when a band that should be positive points downward."
        )
        self.invert_btn.clicked.connect(self.invert_current_subspectrum)
        self.invert_btn.setEnabled(False)
        nav_row.addWidget(self.invert_btn)
        comp_layout.addLayout(nav_row)

        # Selection list with buttons
        sel_btn_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Select all")
        self.select_all_btn.setToolTip("Tick all subspectra in the list for simultaneous display")
        self.select_all_btn.clicked.connect(self.select_all_subspectra)
        self.select_all_btn.setEnabled(False)
        sel_btn_row.addWidget(self.select_all_btn)

        self.unselect_all_btn = QPushButton("Unselect all")
        self.unselect_all_btn.setToolTip("Untick all subspectra")
        self.unselect_all_btn.clicked.connect(self.unselect_all_subspectra)
        self.unselect_all_btn.setEnabled(False)
        sel_btn_row.addWidget(self.unselect_all_btn)
        comp_layout.addLayout(sel_btn_row)

        self.subspectra_list = QListWidget()
        self.subspectra_list.setToolTip(
            "Tick one or more subspectra to display them on the canvas.\n"
            "Components are ordered by decreasing variance — component 1 has the largest contribution."
        )
        self.subspectra_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.subspectra_list.itemChanged.connect(self.on_subspectra_selection_changed)
        comp_layout.addWidget(self.subspectra_list)

        components_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout.addWidget(components_group)

        # ── 2. Plot Display ────────────────────────────────────────────
        display_group = QGroupBox("Plot display")
        display_layout = QVBoxLayout(display_group)
        display_layout.setSpacing(3)

        # Organisation
        org_row = QHBoxLayout()
        org_row.addWidget(QLabel("Layout:"))
        self.org_group = QButtonGroup()
        self.row_org_radio = QRadioButton("Row")
        self.row_org_radio.setChecked(True)
        self.row_org_radio.toggled.connect(self.update_plot_appearance)
        self.org_group.addButton(self.row_org_radio)
        org_row.addWidget(self.row_org_radio)
        self.col_org_radio = QRadioButton("Column")
        self.col_org_radio.toggled.connect(self.update_plot_appearance)
        self.org_group.addButton(self.col_org_radio)
        org_row.addWidget(self.col_org_radio)
        org_row.addStretch()
        display_layout.addLayout(org_row)

        # Subspectra
        sub_row = QHBoxLayout()
        sub_row.addWidget(QLabel("Subspectra:"))
        self.sub_group = QButtonGroup()
        self.sub_separate_radio = QRadioButton("Separate")
        self.sub_separate_radio.setChecked(True)
        self.sub_separate_radio.toggled.connect(self.update_plot_appearance)
        self.sub_group.addButton(self.sub_separate_radio)
        sub_row.addWidget(self.sub_separate_radio)
        self.sub_combined_radio = QRadioButton("Combined")
        self.sub_combined_radio.toggled.connect(self.update_plot_appearance)
        self.sub_group.addButton(self.sub_combined_radio)
        sub_row.addWidget(self.sub_combined_radio)
        sub_row.addStretch()
        display_layout.addLayout(sub_row)

        # Coefficients
        coeff_row = QHBoxLayout()
        coeff_row.addWidget(QLabel("Coefficients:"))
        self.coeff_group = QButtonGroup()
        self.coeff_separate_radio = QRadioButton("Separate")
        self.coeff_separate_radio.setChecked(True)
        self.coeff_separate_radio.toggled.connect(self.update_plot_appearance)
        self.coeff_group.addButton(self.coeff_separate_radio)
        coeff_row.addWidget(self.coeff_separate_radio)
        self.coeff_combined_radio = QRadioButton("Combined")
        self.coeff_combined_radio.toggled.connect(self.update_plot_appearance)
        self.coeff_group.addButton(self.coeff_combined_radio)
        coeff_row.addWidget(self.coeff_combined_radio)
        coeff_row.addStretch()
        display_layout.addLayout(coeff_row)

        display_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(display_group)

        # ── Coefficient X-axis (spectrum order vs. custom parameter) ────
        # By default the coefficient plots use plain spectrum order
        # (1, 2, 3, ...). Many experiments instead vary a physical
        # parameter (temperature, pH, time, ...) across the spectra, one
        # value per spectrum — this lets the user swap the x-axis to that
        # parameter instead, loaded from a text file (including drag &
        # drop onto the dialog) or typed in manually.
        param_group = QGroupBox("Coefficient X-axis")
        param_layout = QVBoxLayout(param_group)
        param_layout.setSpacing(4)

        xaxis_row = QHBoxLayout()
        self.xaxis_group = QButtonGroup()
        self.xaxis_order_radio = QRadioButton("Spectrum order")
        self.xaxis_order_radio.setChecked(True)
        self.xaxis_order_radio.setToolTip(
            "Coefficient plots use 1, 2, 3, ... (the order the spectra were selected in)."
        )
        self.xaxis_order_radio.toggled.connect(self._on_xaxis_mode_changed)
        self.xaxis_group.addButton(self.xaxis_order_radio)
        xaxis_row.addWidget(self.xaxis_order_radio)

        self.xaxis_param_radio = QRadioButton("Parameter values")
        self.xaxis_param_radio.setToolTip(
            "Coefficient plots use one custom value per spectrum (e.g. temperature,\n"
            "pH, time). Load or enter the values below first."
        )
        self.xaxis_param_radio.toggled.connect(self._on_xaxis_mode_changed)
        self.xaxis_group.addButton(self.xaxis_param_radio)
        xaxis_row.addWidget(self.xaxis_param_radio)

        self.xaxis_label_radio = QRadioButton("Spectrum labels")
        self.xaxis_label_radio.setToolTip(
            "Coefficient plots show each spectrum's label on the x-axis, in the\n"
            "same order the spectra appear in the main window's list (not sorted)."
        )
        self.xaxis_label_radio.toggled.connect(self._on_xaxis_mode_changed)
        self.xaxis_group.addButton(self.xaxis_label_radio)
        xaxis_row.addWidget(self.xaxis_label_radio)
        xaxis_row.addStretch()

        self.xaxis_help_btn = QPushButton("?")
        self.xaxis_help_btn.setFixedWidth(24)
        self.xaxis_help_btn.setToolTip("Help for Coefficient X-axis")
        self.xaxis_help_btn.setStyleSheet(
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
        self.xaxis_help_btn.clicked.connect(self.show_xaxis_help)
        xaxis_row.addWidget(self.xaxis_help_btn)
        param_layout.addLayout(xaxis_row)

        # This dialog's OWN "Shorten names" toggle for the 'Spectrum labels'
        # x-axis mode above — independent of the main window's checkbox of
        # the same name (see label_shortening.make_shorten_names_checkbox).
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_changed)
        param_layout.addWidget(self.checkBox_shorten_names)

        self.param_status_label = QLabel("No parameter values loaded.")
        self.param_status_label.setWordWrap(True)
        self.param_status_label.setStyleSheet("color: #777; font-size: 11px;")
        param_layout.addWidget(self.param_status_label)

        param_btn_row = QHBoxLayout()
        self.param_load_btn = QPushButton("Load from file…")
        self.param_load_btn.setToolTip(
            "Load one parameter value per spectrum from a text file (one number\n"
            "per line, in the same order as the selected spectra).\n"
            "Tip: you can also just drag and drop the file onto this dialog."
        )
        self.param_load_btn.clicked.connect(self.load_parameter_values_from_file)
        param_btn_row.addWidget(self.param_load_btn)

        self.param_manual_btn = QPushButton("Enter manually…")
        self.param_manual_btn.setToolTip("Type or paste one parameter value per spectrum.")
        self.param_manual_btn.clicked.connect(self.enter_parameter_values_manually)
        param_btn_row.addWidget(self.param_manual_btn)

        self.param_clear_btn = QPushButton("Clear")
        self.param_clear_btn.setToolTip("Remove the loaded parameter values and revert to spectrum order.")
        self.param_clear_btn.clicked.connect(self.clear_parameter_values)
        param_btn_row.addWidget(self.param_clear_btn)
        param_layout.addLayout(param_btn_row)

        param_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(param_group)

        # ── Metric display ──────────────────────────────────────────────
        # Its own groupbox, same as PCA/SVD Scores & Loadings — keeps "View
        # SVD Components" from feeling crowded with controls that apply to
        # everything (list labels and plot labels alike), not just navigation.
        metric_group = QGroupBox("Metric display")
        mg = QVBoxLayout(metric_group)
        metric_row = QHBoxLayout()
        metric_label = QLabel("Metric:")
        metric_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        metric_row.addWidget(metric_label)
        self._svd_metric_combo = QComboBox()
        self._svd_metric_combo.addItems(list(SVDDiagnosticsDialog.METRICS.keys()))
        self._svd_metric_combo.setCurrentText('Explained variance (%)')
        self._svd_metric_combo.setToolTip(
            "Which number appears next to each subspectrum, in the list and on plot labels."
        )
        self._svd_metric_combo.currentIndexChanged.connect(self.update_value_display_mode)
        metric_row.addWidget(self._svd_metric_combo)
        mg.addLayout(metric_row)

        fmt_row = QHBoxLayout()
        fmt_label = QLabel("Format:")
        fmt_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        fmt_row.addWidget(fmt_label)
        self._svd_format_combo = QComboBox()
        self._svd_format_combo.addItems(['Fixed', 'Scientific'])
        self._svd_format_combo.currentIndexChanged.connect(self.update_value_display_mode)
        fmt_row.addWidget(self._svd_format_combo)
        decimals_label = QLabel("Decimals:")
        decimals_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        fmt_row.addWidget(decimals_label)
        self._svd_decimals_spin = QSpinBox()
        self._svd_decimals_spin.setRange(0, 6)
        self._svd_decimals_spin.setValue(3)
        self._svd_decimals_spin.setFixedWidth(45)
        self._svd_decimals_spin.valueChanged.connect(self.update_value_display_mode)
        fmt_row.addWidget(self._svd_decimals_spin)
        mg.addLayout(fmt_row)

        metric_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(metric_group)

        # Diagnostics is now its own tab (see setup_ui) rather than a
        # button that opened a separate window.

        # ── 4. Dialog buttons: Help | Save | Close ─────────────────────
        self.button_box = QDialogButtonBox()

        self.help_button = QPushButton("Help")
        self.help_button.clicked.connect(self.show_help)
        self.button_box.addButton(self.help_button, QDialogButtonBox.HelpRole)

        self.save_options_btn = QPushButton("Save…")
        self.save_options_btn.setToolTip("Save subspectra, coefficients and singular values to Excel or text")
        self.save_options_btn.clicked.connect(self.show_save_dialog)
        self.save_options_btn.setEnabled(False)
        self.button_box.addButton(self.save_options_btn, QDialogButtonBox.ApplyRole)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        self.button_box.addButton(self.close_button, QDialogButtonBox.AcceptRole)

        self.button_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.button_box)

        return control_widget

    def update_plot_appearance(self):
        """Update plot appearance based on radio button selections."""
        if not hasattr(self, 'canvas'):
            return
            
        organization = 'row' if self.row_org_radio.isChecked() else 'column'
        subspectra_mode = 'combined' if self.sub_combined_radio.isChecked() else 'separate'
        coefficients_mode = 'combined' if self.coeff_combined_radio.isChecked() else 'separate'
        
        logger.debug(f"DEBUG: update_plot_appearance - org: {organization}, sub: {subspectra_mode}, coeff: {coefficients_mode}")
        
        self.canvas.set_plot_appearance(organization, subspectra_mode, coefficients_mode)

    # ── Parameter values (coefficient X-axis) ───────────────────────────

    def _has_valid_parameter_values(self):
        """True if loaded parameter values exist and still match the
        current number of spectra (they're cleared on every recompute)."""
        if not self.controller:
            return False
        values = self.controller.get_parameter_values()
        return values is not None and len(values) == self.controller.get_n_spectra()

    def _has_valid_spectrum_labels(self):
        """True if the manager has spectrum labels recorded (from the last
        SVD computation) matching the current number of spectra."""
        if not self.controller:
            return False
        manager = getattr(self.controller, 'manager', None)
        labels = getattr(manager, 'spectrum_labels', None) if manager else None
        return labels is not None and len(labels) == self.controller.get_n_spectra()

    def _update_parameter_status_label(self):
        if not self._has_valid_parameter_values():
            self.param_status_label.setText("No parameter values loaded.")
            return
        values = self.controller.get_parameter_values()
        label = self.controller.get_parameter_label() or "Parameter"
        self.param_status_label.setText(
            f"{label}: {len(values)} value(s) loaded ({values[0]:.4g} to {values[-1]:.4g})."
        )

    def show_xaxis_help(self):
        """Detailed context help for the Coefficient X-axis feature,
        triggered by the '?' button next to the Spectrum order / Parameter
        values / Spectrum labels radios."""
        QMessageBox.information(
            self, "Coefficient X-axis — Help",
            "<html><body style='font-family: Arial, sans-serif; font-size: 12px;'>"
            "<p>Every coefficient (V) plot has an x-axis with one point per spectrum. "
            "By default that's just <b>spectrum order</b> — 1, 2, 3, ... — the position "
            "each spectrum was selected in.</p>"
            "<p><b>Parameter values</b> lets you replace that with a physical quantity "
            "that actually varies across your spectra — temperature, pH, time, "
            "concentration, etc. — so the coefficient plot shows the trend against the "
            "real variable instead of an arbitrary index.</p>"
            "<p><b>Loading values</b> (one number per spectrum, same order as selected):</p>"
            "<ul>"
            "<li><b>Load from file…</b> — a text file with one value per line. A leading "
            "index column is tolerated; the last number on each line is used.</li>"
            "<li><b>Enter manually…</b> — a table sized to your spectra. Type values, use "
            "<i>Fill series</i> (Start + Step, like Excel's fill handle), or "
            "copy/cut/paste (Ctrl+C / Ctrl+X / Ctrl+V) — including from an external "
            "spreadsheet. Select cells and press Delete to clear them.</li>"
            "<li><b>Drag and drop</b> a text file anywhere onto this dialog.</li>"
            "</ul>"
            "<p><b>Note:</b> parameter values are cleared whenever SVD is recomputed, "
            "since a new or reordered spectra selection invalidates them — you'll need "
            "to load or enter them again after that. Switching to 'Parameter values' "
            "without valid values loaded will prompt you to load or enter them first.</p>"
            "<p><b>Spectrum labels</b> shows each spectrum's name on the x-axis instead of "
            "a number — the same short/full name shown in the main window's spectra list "
            "(honoring the 'Shorten names' checkbox there), in the exact order the spectra "
            "appear in that list. Unlike 'Parameter values', these labels are never "
            "re-sorted, so the axis always matches the main window's ordering.</p>"
            "</body></html>"
        )

    def _on_xaxis_mode_changed(self):
        """Switch coefficient plots between spectrum-order, parameter-value,
        and spectrum-label x-axis."""
        if not hasattr(self, 'canvas'):
            return
        use_parameter = self.xaxis_param_radio.isChecked()
        if use_parameter and not self._has_valid_parameter_values():
            # Don't silently fall back or plot a misleading axis — the
            # user explicitly asked for parameter values, so tell them
            # what's missing instead of guessing.
            QMessageBox.information(
                self, "No Parameter Values",
                "Load or enter parameter values first (one per spectrum), then "
                "switch to 'Parameter values'."
            )
            self.xaxis_order_radio.setChecked(True)
            return
        use_labels = self.xaxis_label_radio.isChecked()
        if use_labels and not self._has_valid_spectrum_labels():
            QMessageBox.information(
                self, "No Spectrum Labels",
                "Spectrum labels aren't available for the current SVD result — "
                "recompute SVD first, then switch to 'Spectrum labels'."
            )
            self.xaxis_order_radio.setChecked(True)
            return
        self.canvas.use_parameter_axis = use_parameter
        self.canvas.use_label_axis = use_labels
        self.canvas.plot_selected_subspectra()

    def _on_shorten_names_changed(self):
        """This dialog's own "Shorten names" checkbox was toggled. Unlike a
        Qt delegate's paint-time check, the coefficient plot's x-tick
        labels are drawn once by matplotlib and have no other mechanism to
        notice this changed — force an explicit replot so toggling the
        checkbox takes visible effect immediately rather than only on the
        next unrelated redraw."""
        if not hasattr(self, 'canvas'):
            return
        self.canvas.plot_selected_subspectra()

    def _apply_parameter_values(self, values, label, source_desc):
        """Validate parameter values against the current spectra count and,
        on success, hand them to the manager and switch the coefficient
        x-axis over to them."""
        n_expected = self.controller.get_n_spectra() if self.controller else 0
        if n_expected == 0:
            QMessageBox.warning(self, "No SVD Data", "Compute SVD before loading parameter values.")
            return
        if len(values) != n_expected:
            QMessageBox.warning(
                self, "Length Mismatch",
                f"{source_desc} provided {len(values)} value(s), but this analysis has "
                f"{n_expected} spectrum/spectra. Each spectrum needs exactly one parameter "
                "value, in the same order the spectra were selected."
            )
            return
        if not self.controller.set_parameter_values(values, label=label):
            QMessageBox.warning(self, "Invalid Values", "Could not accept the parameter values provided.")
            return

        self._update_parameter_status_label()
        self.canvas.use_parameter_axis = True
        self.xaxis_param_radio.setChecked(True)  # also triggers the plot refresh via _on_xaxis_mode_changed
        self.canvas.plot_selected_subspectra()

    def load_parameter_values_from_file(self):
        """Prompt for a text file and load one parameter value per spectrum from it."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Parameter Values", "", "Text Files (*.txt *.csv *.dat);;All Files (*)"
        )
        if not filepath:
            return
        self._load_parameter_values_from_path(filepath)

    def _load_parameter_values_from_path(self, filepath):
        try:
            values = self._parse_parameter_file(filepath)
        except Exception as e:
            QMessageBox.warning(self, "Read Error", f"Could not read parameter values from file:\n{e}")
            return
        if not values:
            QMessageBox.warning(self, "Empty File", "No numeric values were found in that file.")
            return
        label = os.path.splitext(os.path.basename(filepath))[0]
        self._apply_parameter_values(values, label, f"The file '{os.path.basename(filepath)}'")

    @staticmethod
    def _parse_parameter_file(filepath):
        """
        Read one numeric value per line. Tolerates a non-numeric header
        line and comma/tab/whitespace-separated columns (e.g. an index
        column next to the value) by taking the last numeric token on
        each line, which is the common layout for exported parameter
        lists ("1  25.3").
        """
        values = []
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                tokens = line.replace(',', ' ').replace('\t', ' ').split()
                nums = []
                for tok in tokens:
                    try:
                        nums.append(float(tok))
                    except ValueError:
                        continue
                if nums:
                    values.append(nums[-1])
        return values

    def enter_parameter_values_manually(self):
        """Open a spreadsheet-style dialog to enter one parameter value per
        spectrum: a table pre-sized to the number of spectra, with an
        Excel-style 'fill series' helper (start value + step), in-table
        copy/paste/delete, and support for pasting a column copied from an
        external spreadsheet."""
        n_expected = self.controller.get_n_spectra() if self.controller else 0
        if n_expected == 0:
            QMessageBox.warning(self, "No SVD Data", "Compute SVD before entering parameter values.")
            return

        from PyQt5.QtWidgets import QApplication, QAbstractItemView

        class ParameterEntryDialog(QDialog):
            """Cancel/Escape/closing the window all route through reject(),
            so overriding it here is what makes the 'unfilled rows' warning
            catch every way of backing out, not just a dedicated Cancel
            button click."""
            def __init__(self, parent):
                super().__init__(parent)
                self.table = None  # attached once the table widget below is built
                self.n_rows = 0

            def reject(self):
                incomplete = self.table is not None and any(
                    not (self.table.item(r, 1) and self.table.item(r, 1).text().strip())
                    for r in range(self.n_rows)
                )
                if incomplete:
                    resp = QMessageBox.question(
                        self, "Incomplete Values",
                        "Not all rows have a value yet. Discard and close anyway?",
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                    )
                    if resp != QMessageBox.Yes:
                        return
                super().reject()

        spectrum_labels = getattr(self.controller.manager, 'spectrum_labels', None) or []

        dlg = ParameterEntryDialog(self)
        dlg.n_rows = n_expected
        dlg.setWindowTitle("Enter Parameter Values")
        dlg.resize(420, 540)
        vlay = QVBoxLayout(dlg)

        vlay.addWidget(QLabel(
            f"One row per spectrum ({n_expected} total), in the same order as selected. "
            "Type values directly, copy/paste within the table or from an external "
            "spreadsheet (Ctrl+C / Ctrl+V), select cells and press Delete to clear them, "
            "or use Fill series below."
        ))

        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("Axis label:"))
        label_edit = QLineEdit(self.controller.get_parameter_label() or "")
        label_edit.setPlaceholderText("e.g. Temperature (\u00b0C)")
        label_row.addWidget(label_edit)
        vlay.addLayout(label_row)

        table = QTableWidget(n_expected, 2)
        table.setHorizontalHeaderLabels(["Spectrum", "Value"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectItems)
        dlg.table = table

        existing = self.controller.get_parameter_values()
        has_existing = existing is not None and len(existing) == n_expected
        for row in range(n_expected):
            name = spectrum_labels[row] if row < len(spectrum_labels) else f"Spectrum {row + 1}"
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, name_item)
            value_text = f"{existing[row]:g}" if has_existing else ""
            table.setItem(row, 1, QTableWidgetItem(value_text))
        vlay.addWidget(table)

        # Copy selected Value cells (row order) to the clipboard, newline-separated.
        def do_copy():
            value_items = sorted(
                (it for it in table.selectedItems() if it.column() == 1),
                key=lambda it: it.row()
            )
            if not value_items:
                return
            QApplication.clipboard().setText("\n".join(it.text() for it in value_items))
        QShortcut(QKeySequence.Copy, table).activated.connect(do_copy)

        # Paste into the Value column, starting at the current/top selected
        # row — works the same whether the clipboard came from this table
        # (Ctrl+C above) or from an external spreadsheet.
        def do_paste():
            text = QApplication.clipboard().text()
            if not text:
                return
            lines = [ln for ln in text.replace('\r', '').split('\n') if ln != '']
            selected_rows = sorted(it.row() for it in table.selectedItems())
            start_row = selected_rows[0] if selected_rows else max(table.currentRow(), 0)
            for i, line in enumerate(lines):
                row = start_row + i
                if row >= n_expected:
                    break
                # Spreadsheets paste multi-column selections tab-separated;
                # take the first token as the value.
                token = line.split('\t')[0].strip()
                table.setItem(row, 1, QTableWidgetItem(token))
        QShortcut(QKeySequence.Paste, table).activated.connect(do_paste)

        # Clear all selected Value cells at once.
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

        # Fill series — Excel-style: Start, Start+Step, Start+2*Step, ...
        fill_group = QGroupBox("Fill series")
        fill_layout = QHBoxLayout(fill_group)
        fill_layout.addWidget(QLabel("Start:"))
        start_spin = QDoubleSpinBox()
        start_spin.setRange(-1e9, 1e9)
        start_spin.setDecimals(4)
        start_spin.setValue(0.0)
        fill_layout.addWidget(start_spin)

        fill_layout.addWidget(QLabel("Step:"))
        step_spin = QDoubleSpinBox()
        step_spin.setRange(-1e9, 1e9)
        step_spin.setDecimals(4)
        step_spin.setValue(1.0)
        fill_layout.addWidget(step_spin)

        fill_btn = QPushButton("Fill")
        fill_btn.setToolTip(f"Fill all {n_expected} rows: Start, Start+Step, Start+2\u00d7Step, ...")

        def do_fill():
            for row in range(n_expected):
                val = start_spin.value() + row * step_spin.value()
                table.setItem(row, 1, QTableWidgetItem(f"{val:g}"))
        fill_btn.clicked.connect(do_fill)
        fill_layout.addWidget(fill_btn)
        fill_layout.addStretch()
        vlay.addWidget(fill_group)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        vlay.addWidget(btn_box)

        if dlg.exec_() != QDialog.Accepted:
            return

        values = []
        for row in range(n_expected):
            item = table.item(row, 1)
            text = item.text().strip() if item else ""
            if not text:
                row_name = table.item(row, 0).text()
                QMessageBox.warning(self, "Missing Value", f"Row {row + 1} ({row_name}) has no value.")
                return
            try:
                values.append(float(text))
            except ValueError:
                QMessageBox.warning(self, "Invalid Value", f"'{text}' in row {row + 1} is not a number.")
                return

        label = label_edit.text().strip() or None
        self._apply_parameter_values(values, label, "The values you entered")

    def clear_parameter_values(self):
        """Discard loaded parameter values and revert to spectrum order."""
        if self.controller:
            self.controller.clear_parameter_values()
        self.xaxis_order_radio.setChecked(True)
        if hasattr(self, 'canvas'):
            self.canvas.use_parameter_axis = False
            self.canvas.use_label_axis = False
            self.canvas.plot_selected_subspectra()
        self._update_parameter_status_label()

    def dragEnterEvent(self, event):
        """Accept a dragged local file so it can be dropped to load parameter values."""
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """A text file dropped on the dialog is loaded as parameter values."""
        local_files = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not local_files:
            event.ignore()
            return
        event.acceptProposedAction()
        if not self.controller or self.controller.get_n_spectra() == 0:
            QMessageBox.warning(self, "No SVD Data", "Compute SVD before dropping a parameter-values file.")
            return
        self._load_parameter_values_from_path(local_files[0])
        
    def _get_svd_metric_value(self, idx):
        """Raw numeric value for the currently chosen Metric, at component
        idx. Reuses self.diagnostics_panel.data (already computed for the
        Diagnostics tab) for anything beyond plain sigma/variance, instead
        of recomputing residual error / IND separately."""
        metric = self._svd_metric_combo.currentText()
        manager = self.controller.manager if self.controller else None
        if metric == 'Singular values (\u03c3)':
            return manager.s[idx] if manager and manager.s is not None and idx < len(manager.s) else 0.0
        elif metric == 'Eigenvalue (\u03c3\u00b2)':
            return (manager.s[idx] ** 2) if manager and manager.s is not None and idx < len(manager.s) else 0.0
        elif metric == 'Explained variance (%)':
            ev = manager.explained_variance if manager else None
            return ev[idx] if ev is not None and idx < len(ev) else 0.0
        d = getattr(self.diagnostics_panel, 'data', {}) if hasattr(self, 'diagnostics_panel') else {}
        if metric == 'Cumulative explained var. (%)':
            arr = d.get('cum_ev', [])
            return arr[idx] if idx < len(arr) else 0.0
        elif metric == 'Cumulative unexplained var. (%)':
            arr = d.get('unexpl', [])
            return arr[idx] if idx < len(arr) else 0.0
        elif metric == 'Residual error E(m)':
            arr = d.get('RE', [])
            return arr[idx] if idx < len(arr) else float('nan')
        elif metric == 'Malinowski IND':
            arr = d.get('IND', [])
            return arr[idx] if idx < len(arr) else float('nan')
        return 0.0

    def _format_svd_metric_number(self, value):
        decimals = self._svd_decimals_spin.value()
        if self._svd_format_combo.currentText() == 'Scientific':
            return f'{value:.{decimals}e}'
        return f'{value:.{decimals}f}'

    def _get_svd_metric_label(self, idx, short=False):
        """Full label text for component idx, e.g. 'Subspectrum 3 (45.231%)'
        or, short form, 'S3 (45.231%)' — used by both the component list
        and the canvas's plot titles/legends via the label_provider hook."""
        metric = self._svd_metric_combo.currentText()
        value = self._get_svd_metric_value(idx)
        formatted = self._format_svd_metric_number(value)
        if '%' in metric:
            formatted += '%'
        prefix = f"S{idx + 1}" if short else f"Subspectrum {idx + 1}"
        return f"{prefix} ({formatted})"

    def _get_svd_metric_coefficient_label(self, idx):
        """'V{n} (value)' form, used for coefficient plot labels."""
        metric = self._svd_metric_combo.currentText()
        value = self._get_svd_metric_value(idx)
        formatted = self._format_svd_metric_number(value)
        if '%' in metric:
            formatted += '%'
        return f"V{idx + 1} ({formatted})"

    def update_value_display_mode(self):
        """Metric/Format/Decimals changed — refresh list and plots."""
        if not hasattr(self, 'canvas'):
            return
        self.canvas.label_provider = self._get_svd_metric_label
        self.canvas.coefficient_label_provider = self._get_svd_metric_coefficient_label
        self.canvas.set_value_display_mode('custom')
        self.update_subspectra_list_labels()
    
    def update_subspectra_list_labels(self):
        """Update the subspectra list with current display mode."""
        if not self.controller:
            return
            
        self.subspectra_list.blockSignals(True)
        
        try:
            # Store current selection states
            selected_items = set()
            for i in range(self.subspectra_list.count()):
                item = self.subspectra_list.item(i)
                if item.checkState() == Qt.Checked:
                    selected_items.add(i)
            
            # Update labels
            for i in range(self.subspectra_list.count()):
                item = self.subspectra_list.item(i)
                item_text = self._get_svd_metric_label(i)
                
                item.setText(item_text)
                
                # Restore selection state
                if i in selected_items:
                    item.setCheckState(Qt.Checked)
                else:
                    item.setCheckState(Qt.Unchecked)
                    
        finally:
            self.subspectra_list.blockSignals(False)

    def show_help(self):
        """Show help window."""
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'svd_analysis')

    def create_canvas_panel(self):
        """Create the canvas panel for SVD visualization."""
        canvas_widget = QWidget()
        layout = QVBoxLayout(canvas_widget)
        
        self.canvas = InteractiveSVDAnalysisCanvas()
        # Hand the canvas a callable back to this dialog's own "Shorten
        # names" checkbox (created in create_control_panel, which runs
        # before this method — see setup_ui) rather than a direct
        # checkbox reference, matching label_provider's existing pattern.
        self.canvas.get_shorten_enabled = self.checkBox_shorten_names.isChecked
        self.toolbar = NavigationToolbar(self.canvas, canvas_widget)
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        return canvas_widget
        
    def initialize_svd(self):
        """Initialize SVD with current spectra automatically. Also the
        recompute entry point when the Mean-center checkbox is toggled —
        a full recompute is required there (unlike, say, selecting which
        already-computed subspectra to display), since centering changes
        the actual U/s/Vt decomposition, not just how it's presented."""
        if not self.controller or not self.spectra:
            logger.debug("DEBUG: No controller or spectra available for SVD initialization")
            return
        if getattr(self, '_svd_running', False):
            return  # already computing — ignore a second trigger outright
        self._svd_running = True
        self.mean_center_cb.setEnabled(False)

        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtGui import QCursor
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        self._svd_progress = QProgressDialog('Computing SVD…', None, 0, 0, self)
        self._svd_progress.setWindowModality(Qt.WindowModal)
        self._svd_progress.setWindowTitle('SVD Analysis')
        self._svd_progress.setMinimumDuration(0)
        self._svd_progress.setCancelButton(None)
        self._svd_progress.show()
        # Do NOT call QApplication.processEvents() here. The actual computation
        # runs on a background QThread below, so this function returns to Qt's
        # real event loop almost immediately, which paints the progress dialog
        # on its own. Manually pumping events here was contributing to the
        # stale OS "busy" cursor overlay (see showEvent for the full story).

        mean_center = self.mean_center_cb.isChecked()
        self._svd_worker = _ComputeWorker(
            lambda: self.controller.compute_svd_analysis(self.spectra, mean_center=mean_center), self)
        self._svd_worker.done.connect(self._on_svd_computed)
        self._svd_worker.start(QThread.LowPriority)

    def _on_svd_computed(self):
        success = self._svd_worker.result
        thread_error = self._svd_worker.error

        try:
            if thread_error is not None:
                QMessageBox.critical(self, "Error", f"Error computing SVD analysis: {str(thread_error)}")
                return
            if not success:
                QMessageBox.warning(self, "SVD Error", "Failed to compute SVD. Please check that all spectra have identical x-axes.")
                return
                
            info = self.controller.get_svd_components_info()
            if not info:
                QMessageBox.warning(self, "SVD Error", "Failed to get SVD component information.")
                return
                
            # Update UI
            self.subspectrum_spin.setMaximum(info['n_components'])
            self.subspectrum_spin.setEnabled(True)
            self.prev_btn.setEnabled(True)
            self.next_btn.setEnabled(True)
            self.invert_btn.setEnabled(True)
            self.select_all_btn.setEnabled(True)
            self.unselect_all_btn.setEnabled(True)
            self.diagnostics_panel.refresh()
            # singular_values_btn, residual_errors_btn, both_plots_btn removed — now in Diagnostics tab
            self.save_options_btn.setEnabled(True)
            
            # Populate subspectra list
            self.populate_subspectra_list(info['n_components'])
            
            # Set SVD controller for canvas
            self.canvas.set_svd_controller(self.controller)
            self.canvas.label_provider = self._get_svd_metric_label
            self.canvas.coefficient_label_provider = self._get_svd_metric_coefficient_label

            # Parameter values (if any) were tied to the previous spectra
            # set and are cleared by the manager on recompute — reflect
            # that in the x-axis controls too. Spectrum labels are
            # recomputed fresh, but reset the mode to plain spectrum order
            # as well, for a consistent, predictable state after every
            # recompute.
            self.canvas.use_parameter_axis = False
            self.canvas.use_label_axis = False
            self.xaxis_order_radio.setChecked(True)
            self._update_parameter_status_label()
            
            # Select first subspectrum by default
            if self.subspectra_list.count() > 0:
                self.subspectra_list.item(0).setCheckState(Qt.Checked)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error computing SVD analysis: {str(e)}")
        finally:
            from PyQt5.QtWidgets import QApplication
            self._svd_progress.close()
            QApplication.restoreOverrideCursor()
            self._svd_running = False
            self.mean_center_cb.setEnabled(True)

    def populate_subspectra_list(self, n_components):
        """Populate the subspectra selection list."""
        self.subspectra_list.clear()
        
        for i in range(n_components):
            item_text = self._get_svd_metric_label(i)
            item = QListWidgetItem(item_text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.subspectra_list.addItem(item)

    def get_selected_subspectra_indices(self):
        """Get list of selected subspectra indices."""
        selected = []
        for i in range(self.subspectra_list.count()):
            item = self.subspectra_list.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(i)
        return selected

    def on_subspectra_selection_changed(self):
        """Handle changes in subspectra selection."""
        try:
            selected_indices = self.get_selected_subspectra_indices()
            self.canvas.set_selected_subspectra(selected_indices)
            
            if len(selected_indices) == 1:
                self.subspectrum_spin.setValue(selected_indices[0] + 1)
        except Exception as e:
            logger.error(f"ERROR in on_subspectra_selection_changed: {e}")

    def select_all_subspectra(self):
        """Select all subspectra with proper signal blocking."""
        self.subspectra_list.blockSignals(True)
        try:
            for i in range(self.subspectra_list.count()):
                self.subspectra_list.item(i).setCheckState(Qt.Checked)
        finally:
            self.subspectra_list.blockSignals(False)
        
        self.on_subspectra_selection_changed()

    def unselect_all_subspectra(self):
        """Unselect all subspectra with proper signal blocking."""
        self.subspectra_list.blockSignals(True)
        try:
            for i in range(self.subspectra_list.count()):
                self.subspectra_list.item(i).setCheckState(Qt.Unchecked)
        finally:
            self.subspectra_list.blockSignals(False)
        
        self.on_subspectra_selection_changed()

    def prev_subspectrum(self):
        """Navigate to previous subspectrum."""
        current = self.subspectrum_spin.value()
        if current > 1:
            self.subspectrum_spin.setValue(current - 1)
            
    def next_subspectrum(self):
        """Navigate to next subspectrum."""
        current = self.subspectrum_spin.value()
        if current < self.subspectrum_spin.maximum():
            self.subspectrum_spin.setValue(current + 1)
            
    def change_subspectrum(self, value):
        """Handle subspectrum change from spinbox."""
        self.subspectra_list.blockSignals(True)
        try:
            for i in range(self.subspectra_list.count()):
                self.subspectra_list.item(i).setCheckState(Qt.Unchecked)
            
            if 0 <= value - 1 < self.subspectra_list.count():
                self.subspectra_list.item(value - 1).setCheckState(Qt.Checked)
        finally:
            self.subspectra_list.blockSignals(False)
        
        self.on_subspectra_selection_changed()

    def invert_current_subspectrum(self):
        """Invert the currently selected subspectrum in the list."""
        if not self.controller:
            return
        
        # Get the currently selected (highlighted) item in the list
        current_item = self.subspectra_list.currentItem()
        if current_item is None:
            # Fallback to spinbox value if no item is selected
            current_index = self.subspectrum_spin.value() - 1
        else:
            # Get the index of the currently selected item
            current_index = self.subspectra_list.row(current_item)
        
        # Validate index
        if current_index < 0 or current_index >= self.subspectra_list.count():
            QMessageBox.warning(self, "Invalid Selection", "No valid subspectrum selected for inversion.")
            return
        
        success = self.controller.manager.invert_subspectrum(current_index)
        
        if success:
            # Update the plot if this subspectrum is in the selected list
            selected_indices = self.get_selected_subspectra_indices()
            if current_index in selected_indices:
                self.canvas.plot_selected_subspectra()
            
            # DO NOT update the spinbox - preserve current multi-plot view
            # Only navigation buttons (Previous/Next/Jump to) should change the spinbox
            
            logger.debug(f"DEBUG: Inverted subspectrum {current_index + 1}")
        else:
            QMessageBox.warning(self, "Inversion Failed", f"Failed to invert subspectrum {current_index + 1}")

    def show_svd_plot(self, plot_type):
        """Show SVD singular values and/or residual errors plot."""
        if not self.controller:
            QMessageBox.warning(self, "Error", "No SVD data available.")
            return
            
        plot_window = SVDSingularValuesWindow(self, self.controller, plot_type)
        plot_window.exec_()

    def show_save_dialog(self):
        """Show the save configuration dialog."""
        if not self.controller:
            QMessageBox.warning(self, "Error", "No SVD data available to save.")
            return

        class SVDSaveDialog(QDialog):
            """Dialog for configuring SVD analysis save options."""
            
            def __init__(self, parent=None, controller=None):
                super().__init__(parent)
                self.controller = controller
                self.save_config = {}
                
                self.setWindowTitle("Save SVD Analysis Results")
                self.setModal(True)
                self.resize(500, 400)
                
                self.setup_ui()
                
            def setup_ui(self):
                """Set up the save dialog UI."""
                layout = QVBoxLayout(self)
                
                # File format group
                format_group = QGroupBox("File Format")
                format_layout = QVBoxLayout(format_group)
                
                self.format_group = QButtonGroup()
                
                self.excel_radio = QRadioButton("Excel (.xlsx)")
                self.excel_radio.setChecked(True)
                self.format_group.addButton(self.excel_radio)
                format_layout.addWidget(self.excel_radio)
                
                self.text_radio = QRadioButton("Text/CSV")
                self.format_group.addButton(self.text_radio)
                format_layout.addWidget(self.text_radio)
                
                layout.addWidget(format_group)
                
                # Text format options (initially hidden)
                self.text_options_group = QGroupBox("Text Format Options")
                text_options_layout = QVBoxLayout(self.text_options_group)
                
                # Delimiter
                delimiter_layout = QHBoxLayout()
                delimiter_layout.addWidget(QLabel("Delimiter:"))
                
                self.delimiter_combo = QComboBox()
                self.delimiter_combo.addItems(["Tab (\\t)", "Comma (,)", "Semicolon (;)", "Space ( )"])
                self.delimiter_combo.setCurrentText("Tab (\\t)")
                delimiter_layout.addWidget(self.delimiter_combo)
                
                text_options_layout.addLayout(delimiter_layout)
                
                # Precision
                precision_layout = QHBoxLayout()
                precision_layout.addWidget(QLabel("Decimal Precision:"))
                
                self.precision_spin = QSpinBox()
                self.precision_spin.setMinimum(1)
                self.precision_spin.setMaximum(15)
                self.precision_spin.setValue(6)
                precision_layout.addWidget(self.precision_spin)
                
                text_options_layout.addLayout(precision_layout)
                
                # File organization
                self.single_file_radio = QRadioButton("Save all data in one file")
                self.single_file_radio.setChecked(True)
                text_options_layout.addWidget(self.single_file_radio)
                
                self.separate_files_radio = QRadioButton("Save data in separate files")
                text_options_layout.addWidget(self.separate_files_radio)
                
                self.text_options_group.setEnabled(False)
                layout.addWidget(self.text_options_group)
                
                # Data selection group - REMOVED "Current subspectrum only"
                data_group = QGroupBox("Data Selection")
                data_layout = QVBoxLayout(data_group)
                
                self.all_subspectra_radio = QRadioButton("All subspectra")
                self.all_subspectra_radio.setChecked(True)
                data_layout.addWidget(self.all_subspectra_radio)
                
                self.selected_subspectra_radio = QRadioButton("Selected subspectra")
                data_layout.addWidget(self.selected_subspectra_radio)
                
                layout.addWidget(data_group)

                # Include group — lets the user export just subspectra, just
                # coefficients, just metrics, or any combination, instead of
                # always getting all three bundled together.
                include_group = QGroupBox("Include")
                include_layout = QHBoxLayout(include_group)
                self.include_subspectra_cb = QCheckBox("Subspectra")
                self.include_subspectra_cb.setChecked(True)
                include_layout.addWidget(self.include_subspectra_cb)
                self.include_coefficients_cb = QCheckBox("Coefficients")
                self.include_coefficients_cb.setChecked(True)
                include_layout.addWidget(self.include_coefficients_cb)
                self.include_metrics_cb = QCheckBox("Metrics")
                self.include_metrics_cb.setChecked(True)
                include_layout.addWidget(self.include_metrics_cb)
                layout.addWidget(include_group)
                
                # File path
                path_group = QGroupBox("Output File")
                path_layout = QVBoxLayout(path_group)
                
                path_selection_layout = QHBoxLayout()
                self.path_edit = QLineEdit()
                self.path_edit.setPlaceholderText("Select output file...")
                path_selection_layout.addWidget(self.path_edit)
                
                self.browse_btn = QPushButton("Browse...")
                self.browse_btn.clicked.connect(self.browse_file)
                path_selection_layout.addWidget(self.browse_btn)
                
                path_layout.addLayout(path_selection_layout)
                layout.addWidget(path_group)
                
                # Dialog buttons
                self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                self.button_box.accepted.connect(self.accept)
                self.button_box.rejected.connect(self.reject)
                layout.addWidget(self.button_box)
                
                # Connect signals
                self.excel_radio.toggled.connect(self.on_format_changed)
                self.text_radio.toggled.connect(self.on_format_changed)
                
            def on_format_changed(self):
                """Handle format selection change."""
                is_text = self.text_radio.isChecked()
                self.text_options_group.setEnabled(is_text)
                
                # Update file extension in path if needed
                current_path = self.path_edit.text()
                if current_path:
                    base_path = os.path.splitext(current_path)[0]
                    if is_text:
                        self.path_edit.setText(base_path + ".txt")
                    else:
                        self.path_edit.setText(base_path + ".xlsx")
            
            def browse_file(self):
                """Browse for output file."""
                if self.excel_radio.isChecked():
                    file_filter = "Excel Files (*.xlsx);;All Files (*)"
                    default_name = "svd_analysis_results.xlsx"
                else:
                    file_filter = "Text Files (*.txt);;CSV Files (*.csv);;All Files (*)"
                    default_name = "svd_analysis_results.txt"
                
                file_path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save SVD Analysis Results",
                    default_name,
                    file_filter
                )
                
                if file_path:
                    self.path_edit.setText(file_path)
            
            def get_delimiter(self):
                """Get the selected delimiter."""
                delimiter_text = self.delimiter_combo.currentText()
                if "Tab" in delimiter_text:
                    return '\t'
                elif "Comma" in delimiter_text:
                    return ','
                elif "Semicolon" in delimiter_text:
                    return ';'
                elif "Space" in delimiter_text:
                    return ' '
                return '\t'
            
            def get_save_config(self):
                """Get the save configuration."""
                if not self.path_edit.text():
                    QMessageBox.warning(self, "No File Selected", "Please select an output file.")
                    return None

                if not (self.include_subspectra_cb.isChecked() or
                        self.include_coefficients_cb.isChecked() or
                        self.include_metrics_cb.isChecked()):
                    QMessageBox.warning(self, "Nothing to Export",
                                        "Select at least one of Subspectra, Coefficients, or Metrics.")
                    return None
                
                config = {
                    'file_path': self.path_edit.text(),
                    'format': 'excel' if self.excel_radio.isChecked() else 'text',
                    'include_subspectra': self.include_subspectra_cb.isChecked(),
                    'include_coefficients': self.include_coefficients_cb.isChecked(),
                    'include_metrics': self.include_metrics_cb.isChecked(),
                }
                
                if self.text_radio.isChecked():
                    config.update({
                        'delimiter': self.get_delimiter(),
                        'precision': self.precision_spin.value(),
                        'save_separate': self.separate_files_radio.isChecked()
                    })
                
                # Determine subspectra selection - SIMPLIFIED
                if self.all_subspectra_radio.isChecked():
                    config['selected_subspectra'] = None
                else:  # selected_subspectra_radio
                    config['selected_only'] = True
                
                return config
            
            def accept(self):
                """Handle OK button."""
                config = self.get_save_config()
                if config:
                    self.save_config = config
                    super().accept()
        
        save_dialog = SVDSaveDialog(self, self.controller)
        
        if save_dialog.exec_() == QDialog.Accepted:
            config = save_dialog.save_config
            self.execute_save(config)
    
    def execute_save(self, config):
        """Execute the save operation based on configuration."""
        try:
            selected_subspectra = None
            if config.get('selected_only'):
                selected_subspectra = self.get_selected_subspectra_indices()
                if not selected_subspectra:
                    QMessageBox.warning(self, "No Selection",
                                        "No subspectra selected. Please select subspectra or choose a different option.")
                    return

            file_path = config['file_path']
            include_subspectra = config.get('include_subspectra', True)
            include_coefficients = config.get('include_coefficients', True)
            include_metrics = config.get('include_metrics', True)

            # Compute Malinowski IND to pass alongside standard results
            manager = self.controller.manager
            ind_data = None
            if include_metrics and manager.s is not None and manager.U is not None:
                n_sp  = len(manager.spectrum_labels) if manager.spectrum_labels else 0
                n_pts = manager.U.shape[0]
                if n_sp > 1:
                    eigenvalues = manager.s ** 2
                    k = len(manager.s)
                    ind_data = np.zeros(k - 1)
                    for m in range(k - 1):
                        res_var = np.sum(eigenvalues[m+1:])
                        re_m = np.sqrt(res_var / (n_pts * (n_sp - m))) if (n_pts * (n_sp - m)) > 0 else 0
                        dof = (n_sp - m) ** 2
                        ind_data[m] = re_m / dof if dof > 0 else 0

            if config['format'] == 'excel':
                success = self.controller.manager.save_results_excel(
                    file_path, selected_subspectra, ind_data=ind_data,
                    include_subspectra=include_subspectra,
                    include_coefficients=include_coefficients,
                    include_metrics=include_metrics,
                )
            else:
                save_config = {
                    'base_path': file_path,
                    'delimiter': config['delimiter'],
                    'precision': config['precision'],
                    'selected_subspectra': selected_subspectra,
                    'save_separate': config['save_separate'],
                    'ind_data': ind_data,
                    'include_subspectra': include_subspectra,
                    'include_coefficients': include_coefficients,
                    'include_metrics': include_metrics,
                }
                success = self.controller.manager.save_results_text(save_config)

            if success:
                QMessageBox.information(self, "Save Successful", "SVD analysis results saved successfully!")
            else:
                QMessageBox.warning(self, "Save Failed", "Failed to save SVD analysis results.")

        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Error saving SVD analysis results:\n{str(e)}")
            logger.error(f"ERROR: Save failed: {e}")
            logger.exception("Traceback:")
    

    
    