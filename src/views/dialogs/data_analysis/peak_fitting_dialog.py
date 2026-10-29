# src/views/dialogs/data_analysis/peak_fitting_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QDialogButtonBox, QLabel,
                             QWidget, QSplitter, QTableWidget, QTableWidgetItem,
                             QHeaderView, QComboBox, QMessageBox, QCheckBox, QRadioButton, QDoubleSpinBox,
                             QColorDialog, QAbstractItemView, QMenu, QApplication,
                             QTabWidget, QToolButton, QFileDialog, QShortcut, QSizePolicy,
                             QListWidget, QStyledItemDelegate, QStyle)
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt, QTimer, QItemSelectionModel
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

class _SelectedTextDelegate(QStyledItemDelegate):
    """Selected rows of the spectra list in the selection's own text colour
    (white on blue), not in the green / grey that marks peaks - so the
    marks never make a selected name hard to read; the green dot stays."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if option.state & QStyle.State_Selected:
            from PyQt5.QtGui import QPalette
            option.palette.setBrush(QPalette.Text,
                                    option.palette.brush(QPalette.HighlightedText))


class PeakFittingDialog(QDialog):
    """Dialog for interactive peak fitting and deconvolution."""

    def __init__(self, parent=None, spectrum=None, current_settings=None, series=None,
                 open_data_table=None):
        super().__init__(parent)
        self.setWindowTitle("Peak Fitting & Deconvolution")
        self.setModal(True)
        self.spectrum = spectrum
        # A series: the spectra selected in the main window (this one among
        # them) and open_data_table(parent, spectra, columns) for its results
        self.series = list(series or [])
        self.open_data_table = open_data_table
        self.series_results = None      # one result per spectrum of the series (fit_all_selected)
        # with several spectra every spectrum has its own peaks: own_peaks[k]
        # (the shown spectrum's are self.peaks); Auto-Detect, Copy to selected
        # and Fit Peaks act on the spectra selected in the list
        self.own_peaks = [[] for _ in self.series] if len(self.series) > 1 else None
        self.peaks_clipboard = None     # Copy peaks: (the spectrum's short name, its peaks)
        # the Amplitude Constraint: one for all spectra (global_constraint), or
        # with 'Each spectrum its own' ticked own_constraints[k] (None = the global one)
        self.global_constraint = 'unrestricted'
        self.own_constraints = [None] * len(self.series) if len(self.series) > 1 else None
        self.view_mode = 'one'          # the plot: 'one', 'overlay', 'waterfall', 'grid'
        self.current_index = 0          # the shown spectrum's place in the series
        for k, sp in enumerate(self.series):
            if sp is spectrum or (spectrum is not None and sp.get('label') == spectrum.get('label')):
                self.current_index = k
                break
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
        self.width_set_by_user = False  # the width of clicked peaks: from the band unless set

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
        self.peaks_group = peaks_group
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
        self.peaks_table.itemSelectionChanged.connect(self._emphasize_selected_peaks)
        
        self.peaks_table.cellDoubleClicked.connect(self.on_color_cell_double_clicked)
        self.peaks_table.setToolTip("List of peaks for fitting.\n- Double-click a color swatch (col 1) to change it.\n- Select rows and press the Delete key to remove peaks.\n- 'Width' is σ for Gaussian/Voigt, γ for Lorentzian, or the shared FWHM for Pseudo-Voigt.\n- 'Extra' applies only to Voigt (γ) and Pseudo-Voigt (η, 0-1) — shown as '—' and disabled for other models.")
        
        peaks_layout.addWidget(self.peaks_table)

        # --- Peak Controls ---
        btn_layout1 = QHBoxLayout()
        
        self.auto_detect_btn = QPushButton("Auto-Detect Peaks")
        self.auto_detect_btn.setToolTip("Automatically find peaks in the current spectrum view.\nRight-click to set initial peak width.")
        self.auto_detect_btn.clicked.connect(self.auto_detect_peaks)
        from src.views import icons as _icons
        self.auto_detect_btn.setIcon(_icons.run_icon())
        # Add context menu for setting initial parameters
        self.auto_detect_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.auto_detect_btn.customContextMenuRequested.connect(self.show_auto_detect_context_menu)
        
        self.interactive_add_cb = QCheckBox("Add via Click")
        self.interactive_add_cb.setToolTip(
            "When ticked, a click on the plot adds a peak there (its width from the band under "
            "the click).\nChoosing Zoom or Pan in the plot's toolbar switches this off; tick it "
            "again to add more peaks.")
        self.interactive_add_cb.stateChanged.connect(self._toggle_interactive_add)
        
        btn_layout1.addWidget(self.auto_detect_btn)
        btn_layout1.addWidget(self.interactive_add_cb)
        peaks_layout.addLayout(btn_layout1)

        if len(self.series) > 1:
            copy_row = QHBoxLayout()
            self.copy_peaks_button = QPushButton("Copy peaks")
            self.copy_peaks_button.setAutoDefault(False)
            self.copy_peaks_button.clicked.connect(lambda: self.copy_peaks())
            self.paste_peaks_button = QPushButton("Paste peaks to the selected spectra")
            self.paste_peaks_button.setAutoDefault(False)
            self.paste_peaks_button.clicked.connect(lambda: self.paste_peaks_to_selected())
            from src.views import icons as _icons
            self.copy_peaks_button.setIcon(_icons.copy_icon())
            copy_row.addWidget(self.copy_peaks_button, 2)
            copy_row.addWidget(self.paste_peaks_button, 3)
            copy_row.addWidget(self._quick_help_button('peaks-mode'))
            peaks_layout.addLayout(copy_row)

        btn_layout2 = QHBoxLayout()
        remove_peak_btn = QPushButton("Remove Selected Peak(s)")
        remove_peak_btn.setToolTip("Remove all currently selected rows from the peak list.")
        remove_peak_btn.clicked.connect(self.remove_peak)
        
        clear_peaks_btn = QPushButton("Clear All Peaks")
        clear_peaks_btn.setToolTip("Clear all peaks of the shown spectrum - with several spectra "
                                   "selected in the list, of all of them (and their fits).")
        self.clear_peaks_btn = clear_peaks_btn
        clear_peaks_btn.clicked.connect(self.clear_peaks)
        
        btn_layout2.addWidget(remove_peak_btn); btn_layout2.addWidget(clear_peaks_btn)
        btn_layout2.addWidget(self._quick_help_button('peaks'))
        peaks_layout.addLayout(btn_layout2)
        peaks_group.setLayout(peaks_layout)
        # Peaks (as set up / fitted for the shown spectrum) and, with several
        # spectra, the results of fitting several of them - one window
        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(peaks_group, "Peaks")
        if len(self.series) > 1:
            self.left_tabs.addTab(self._build_series_tab(), "Series results")
        layout.addWidget(self.left_tabs, 1)

        # --- Fitting Controls ---
        fit_group = QGroupBox("Fitting")
        fit_layout = QVBoxLayout()
        constraint_layout = QHBoxLayout()
        constraint_layout.addWidget(QLabel("Amplitude Constraint:"))
        self.amplitude_combo = QComboBox()
        self.amplitude_combo.addItems(["Unrestricted", "Positive Peaks Only", "Negative Peaks Only"])
        self.amplitude_combo.setToolTip("Constrain the fitting algorithm to find only positive, only negative, or unrestricted amplitude peaks.")
        self.amplitude_combo.currentIndexChanged.connect(lambda *_: self._constraint_chosen())
        constraint_layout.addWidget(self.amplitude_combo)
        self.own_constraint_check = QCheckBox("Each spectrum its own")
        self.own_constraint_check.setToolTip(
            "Off (default): one Amplitude Constraint for all spectra.\n"
            "On: the constraint chosen applies to the spectra selected in the list - e.g. select "
            "the Raman spectra and choose Positive Peaks Only, then the CD spectra and choose "
            "Unrestricted. The list shows (+) for Positive and (\u2212) for Negative.")
        self.own_constraint_check.toggled.connect(lambda *_: self._own_constraint_toggled())
        self.own_constraint_check.setVisible(len(self.series) > 1)
        constraint_layout.addWidget(self.own_constraint_check)
        constraint_layout.addStretch() # Fixes the gap
        constraint_layout.addWidget(self._quick_help_button('fitting'))
        fit_layout.addLayout(constraint_layout)
        self.constraint_note = QLabel()
        self.constraint_note.setStyleSheet("color: #555;")
        self.constraint_note.setWordWrap(True)
        self.constraint_note.setVisible(False)
        fit_layout.addWidget(self.constraint_note)

        n_series = len(self.series)
        self.follow_check = QCheckBox("Spectra without peaks: start from the fit before them "
                                      "(a band shifting along a series)")
        self.follow_check.setToolTip(
            "Off (default): only spectra with their own peaks are fitted; the others are left "
            "out.\nOn: a selected spectrum without peaks starts from the fit of the selected "
            "spectrum before it (in the order of the list) - set the peaks on the first spectrum "
            "of a series only, select All, Fit Peaks: a band that shifts along the series is "
            "followed. Only for spectra of the same kind!")
        self.follow_check.toggled.connect(lambda *_: self._update_fit_button())
        self.follow_check.setVisible(n_series > 1)
        fit_layout.addWidget(self.follow_check)

        # ONE fit button: it fits the spectra selected in the list beside the
        # plot - one (the shown one) or several (a series)
        fit_btn_layout = QHBoxLayout()
        self.fit_button = QPushButton("Fit Peaks")
        from src.views import icons
        self.fit_button.setIcon(icons.run_icon())       # its own icon: the text changes
        self.fit_button.setToolTip(
            "Fit the peaks of the table to the shown spectrum." if n_series < 2 else
            "Fit the spectra selected in the list beside the plot: one, or several "
            "(Ctrl/Shift+click, or All). Each starts from its own peaks; spectra without peaks "
            "are left out - unless 'Spectra without peaks: start from the fit before them' is "
            "ticked. The results of several go to the tab Series results.")
        self.fit_button.clicked.connect(lambda: self.fit_selected())

        self.copy_results_btn = QPushButton("Copy Results")
        self.copy_results_btn.setToolTip("Copy the peak parameters currently in the table to the clipboard.")
        self.copy_results_btn.setEnabled(False) # Disabled until peaks are added
        self.copy_results_btn.clicked.connect(self.copy_results_to_clipboard)

        fit_btn_layout.addWidget(self.fit_button, 2)
        fit_btn_layout.addWidget(self.copy_results_btn, 1)
        if n_series > 1:
            fit_btn_layout.addWidget(self._quick_help_button('series'))
        fit_layout.addLayout(fit_btn_layout)
        # what to do first, while there is nothing to fit
        self.no_peaks_hint = QLabel(self.NO_PEAKS_TEXT)
        self.no_peaks_hint.setWordWrap(True)
        self.no_peaks_hint.setStyleSheet("color: #B45F06;")
        fit_layout.addWidget(self.no_peaks_hint)
        self.select_hint = QLabel("Fit Peaks fits the spectra selected in the list beside the "
                                  "plot \u2013 select them first (All = the whole series).")
        self.select_hint.setWordWrap(True)
        self.select_hint.setStyleSheet("color: #555;")
        self.select_hint.setVisible(len(self.series) > 1)
        fit_layout.addWidget(self.select_hint)

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
        
        first_row = QHBoxLayout()
        first_row.addWidget(self.add_fit_check, 1)
        first_row.addWidget(self._quick_help_button('output'))
        output_layout.addLayout(first_row)
        output_layout.addWidget(self.add_residual_check)
        output_layout.addWidget(self.add_peaks_check)
        # with a series: for which spectra
        for_row = QHBoxLayout()
        for_row.addWidget(QLabel("Add for:"))
        self.output_for_combo = QComboBox()
        self.output_for_combo.addItem("all fitted spectra", 'all')
        self.output_for_combo.addItem("the fitted spectra selected in the list", 'selected')
        self.output_for_combo.setToolTip(
            "Which spectra of the series get the new spectra on OK: every fitted one, or only "
            "the fitted ones selected in the list beside the plot.")
        self.output_for_combo.currentIndexChanged.connect(lambda *_: self._update_output_for())
        for_row.addWidget(self.output_for_combo, 1)
        self.output_for_widget = QWidget()
        self.output_for_widget.setLayout(for_row)
        for_row.setContentsMargins(0, 0, 0, 0)
        self.output_for_widget.setVisible(len(self.series) > 1)
        output_layout.addWidget(self.output_for_widget)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

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
            self.width_set_by_user = True

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
        
        layout.addWidget(self._build_plot_bar())
        tool_row = QHBoxLayout()
        # the toolbar keeps all its buttons (no ">>" when the plot is narrow);
        # the hint beside it wraps instead
        self.toolbar.setMinimumWidth(self.toolbar.sizeHint().width())
        tool_row.addWidget(self.toolbar)
        self.click_hint = QLabel()
        self.click_hint.setStyleSheet("color: #555;")
        self.click_hint.setWordWrap(True)
        self.click_hint.setMinimumWidth(60)
        tool_row.addWidget(self.click_hint, 1)
        self._connect_toolbar_modes()
        if len(self.series) > 1:
            # a series: the list of its spectra beside the plot (select one or
            # several to show, as in the main window)
            split = QSplitter(Qt.Horizontal)
            split.setChildrenCollapsible(False)
            split.addWidget(self._build_spectra_panel())
            plot = QWidget()
            pv = QVBoxLayout(plot)
            pv.setContentsMargins(0, 0, 0, 0)
            pv.addLayout(tool_row)
            pv.addWidget(self.canvas, 1)
            split.addWidget(plot)
            split.setStretchFactor(1, 1)
            split.setSizes([220, 800])
            layout.addWidget(split, 1)
            return widget
        layout.addLayout(tool_row)
        layout.addWidget(self.canvas, 1)                # the plot takes all the free height
        return widget

    def _build_plot_bar(self):
        """One row above the plot: for a series Spectra, ◀ ▶ and View; always the
        check boxes Residual and Legend (both shown by default)."""
        bar = self._build_navigation() if len(self.series) > 1 else QWidget()
        h = bar.layout() or QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch(0 if len(self.series) > 1 else 1)
        self.residual_check = QCheckBox("Residual")
        self.residual_check.setToolTip("Show the residual (data minus fit) under the plot")
        self.legend_check = QCheckBox("Legend")
        self.legend_check.setToolTip("Show the legend (it can be long with many peaks)")
        for c in (self.residual_check, self.legend_check):
            c.setChecked(True)
            c.toggled.connect(lambda *_: self._view_changed())
            h.addSpacing(8)
            h.addWidget(c)
        h.addSpacing(6)
        h.addWidget(self._quick_help_button('view'))
        bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        return bar

    # ------------------------------------------------------------------
    # the orange "?" buttons: short help next to each part of the window
    # ------------------------------------------------------------------
    def _quick_help_button(self, key):
        from src.help.peak_fitting_quick_help import QUICK_HELP
        title = QUICK_HELP[key][0]
        b = QPushButton("?")
        b.setFixedWidth(24)
        b.setAutoDefault(False)
        b.setToolTip(title)
        b.setStyleSheet(
            "QPushButton { background-color: #F57C00; color: white; border: none;"
            " border-radius: 4px; font-weight: bold; padding: 2px; }"
            "QPushButton:hover { background-color: #E65100; }"
            "QPushButton:pressed { background-color: #BF360C; }")
        b.clicked.connect(lambda: self.show_quick_help(key))
        if not hasattr(self, 'quick_help_buttons'):
            self.quick_help_buttons = {}
        self.quick_help_buttons[key] = b
        return b

    def show_quick_help(self, key, run=True):
        """The short help of one part of the window; Full help… opens that
        section of the Peak Fitting help."""
        from src.help.peak_fitting_quick_help import QUICK_HELP
        title, anchor, html = QUICK_HELP[key]
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setTextFormat(Qt.RichText)
        box.setText(html)
        full = box.addButton("Full help\u2026", QMessageBox.HelpRole)
        box.addButton(QMessageBox.Close)
        if not run:
            return box
        box.exec_()
        if box.clickedButton() is full:
            from src.help.help_window import open_help_topic
            open_help_topic(self, 'peak_fitting', anchor)
        return box

    def _load_plot_options(self):
        s = self.current_settings or {}
        k = self.output_for_combo.findData(s.get('output_for', 'all'))
        if k >= 0:
            self.output_for_combo.setCurrentIndex(k)
        for key, check in (('show_residual', self.residual_check),
                           ('show_legend', self.legend_check)):
            check.blockSignals(True)
            check.setChecked(bool(s.get(key, True)))
            check.blockSignals(False)

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
        self._load_plot_options()
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
        self.global_constraint = constraint if constraint in self.CONSTRAINTS else 'unrestricted'
        self._setting_combo = True
        self.amplitude_combo.setCurrentIndex(self.CONSTRAINTS.index(self.global_constraint))
        self._setting_combo = False

        # Load persistent "Add via Click" state, defaulting to True
        add_via_click_state = self.current_settings.get('add_via_click', True) 
        self.interactive_add_cb.setChecked(add_via_click_state)
        self._load_series_settings()

    def _load_series_settings(self):
        """The series results of the last time, when the window is opened again
        for the same spectra (the caller drops them when an operation has
        changed the spectra meanwhile)."""
        s = self.current_settings or {}
        results = s.get('series_results')
        labels = [str(sp.get('label', '')) for sp in self.series]
        if len(self.series) < 2 or s.get('series_labels') != labels:
            return
        self.follow_check.setChecked(bool(s.get('follow_fit_before', False)))
        own_c = s.get('own_constraints')
        if own_c and len(own_c) == len(self.series):
            self.own_constraints = [c if c in self.CONSTRAINTS else None for c in own_c]
        self.own_constraint_check.setChecked(bool(s.get('constraint_per_spectrum', False)))
        own = s.get('own_peaks')
        if own and len(own) == len(self.series):
            self.own_peaks = [list(lst or []) for lst in own]
            self.own_peaks[self.current_index] = self.peaks
        if not results or len(results) != len(labels):
            # no series results: the spectrum shown last time, with its fit
            k = s.get('series_index', self.current_index)
            if 0 <= k < len(self.series) and s.get('spectrum_label') == labels[k] \
                    and k != self.current_index:
                self.current_index = k
                self.spectrum = self.series[k]
                self.x_roi, self.y_roi = self.spectrum['x_scale'], self.spectrum['y_scale']
                self._select_in_list([k])
                self._update_nav(k)
                self.update_plot_with_fit_results()
            return
        self.series_results = [dict(r, r2=(np.nan if r.get('r2') is None else r['r2']))
                               for r in results]
        self._refresh_series_table()
        k = s.get('series_index', self.current_index)
        self.show_series_spectrum(k if 0 <= k < len(self.series) else 0)

    def show_help(self):
        """Show the peak fitting help window."""
        content = get_peak_fitting_help_content()
        title = get_peak_fitting_help_title()
        show_help_window(self, title, content)

    def _toggle_interactive_add(self, state):
        """Add via Click on: a click on the plot adds a peak, and Zoom/Pan of
        the toolbar are switched off. Choosing Zoom or Pan switches Add via
        Click off (_toolbar_mode_changed) - the toolbar is always usable."""
        if state == Qt.Checked:
            if self.click_connection_id is None:
                self.click_connection_id = self.canvas.mpl_connect('button_press_event', self.on_canvas_click)
            mode = str(getattr(self.toolbar, 'mode', '') or '')
            if 'pan' in mode:
                self.toolbar.pan()                      # the same call switches it off
            elif 'zoom' in mode:
                self.toolbar.zoom()
        else:
            if self.click_connection_id is not None:
                self.canvas.mpl_disconnect(self.click_connection_id)
                self.click_connection_id = None
        self.toolbar.setEnabled(True)
        self._update_click_hint()

    def _connect_toolbar_modes(self):
        """Zoom or Pan chosen in the toolbar: Add via Click goes off."""
        actions = getattr(self.toolbar, '_actions', {}) or {}
        for name in ('pan', 'zoom'):
            action = actions.get(name)
            if action is not None:
                action.toggled.connect(self._toolbar_mode_changed)

    def _toolbar_mode_changed(self, on):
        if on and self.interactive_add_cb.isChecked():
            self.interactive_add_cb.setChecked(False)
        self._update_click_hint()

    def _update_click_hint(self):
        if not hasattr(self, 'click_hint'):
            return
        if self.view_mode != 'one':
            text = ""
        elif self.interactive_add_cb.isChecked():
            text = "A click on the plot adds a peak (Zoom or Pan switches this off)."
        else:
            text = "Add via Click is off: tick it to add peaks by clicking."
        self.click_hint.setText(text)

    def on_canvas_click(self, event):
        """Handle clicks on the canvas to add a new peak."""
        # This handler is only connected when the "Add via Click" checkbox is checked
        if self.view_mode != 'one' or event.inaxes != getattr(self, 'ax_main', None) \
                or event.button != 1 or str(getattr(self.toolbar, 'mode', '') or ''):
            return
        
        center, amplitude = event.xdata, event.ydata
        
        # The width: as set (right-click Auto-Detect Peaks), else from the
        # band under the click (its half-height width), else the default
        width = self.initial_peak_width
        if not self.width_set_by_user:
            estimate = self.manager.estimate_width(self.x_roi, self.y_roi, center)
            if estimate:
                width = estimate
        
        # Assign the next color in the cycle
        new_color = self.colors[self.peak_color_index % len(self.colors)]
        self.peak_color_index += 1
        
        # Add the new peak to our list of initial guesses
        self.peaks.append({'model': 'Gaussian', 'center': center, 'amplitude': amplitude, 'width': width, 'extra': width, 'color': new_color})
        self._peaks_changed()
        
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
            if getattr(self, 'ax_residual', None) is not None:
                self.ax_residual.autoscale(True)
            self.canvas.draw()

    def _detect_into(self, peaks, x, y):
        """Add the peaks found in (x, y) to the list `peaks` (not those already
        there: within half a width). Returns how many were added."""
        detected = self.manager.auto_detect_peaks(np.asarray(y, dtype=float),
                                                  np.asarray(x, dtype=float))
        centres = [p['center'] for p in peaks]
        added = 0
        for peak in detected:
            tolerance = abs(peak['width'] * 0.5)
            if any(abs(peak['center'] - c) < tolerance for c in centres):
                continue
            peak['color'] = self.colors[len(peaks) % len(self.colors)]
            peaks.append(peak)
            centres.append(peak['center'])
            added += 1
        return added

    def auto_detect_peaks(self):
        """Find the peaks of the shown spectrum and add them to the list (not
        those already there). Each spectrum its own peaks, several selected:
        the peaks of each selected spectrum, into its own list."""
        if len(self.y_roi) < 3: return
        rows = self.selected_spectra() if len(self.series) > 1 else []
        if len(rows) > 1:
            for i in range(len(self.peaks)):
                self.update_peak_from_table(i)
            added = 0
            for r in rows:
                if r == self.current_index:
                    target = self.peaks
                else:
                    if self.own_peaks[r] is None:
                        self.own_peaks[r] = []
                    target = self.own_peaks[r]
                sp = self.series[r]
                n = self._detect_into(target, sp['x_scale'], sp['y_scale'])
                if n:
                    self._peaks_changed([r])
                added += n
            if not added:
                QMessageBox.information(self, "Auto-Detect", "No new peaks were detected.")
                return
            self.fit_results = None
            self.update_peaks_table()
            self.update_plot()
            return
        added = self._detect_into(self.peaks, self.x_roi, self.y_roi)
        self.peak_color_index = len(self.peaks)
        if added:
            self._peaks_changed()
        if not added:
            QMessageBox.information(self, "Auto-Detect", "No new peaks were detected.")
            return
        self.fit_results = None # Invalidate previous fit
        self.copy_results_btn.setEnabled(bool(self.peaks)) # Enable copy button
        self.update_peaks_table()
        self.update_plot()

    # ------------------------------------------------------------------
    # the same peaks for all spectra, or each spectrum its own
    # ------------------------------------------------------------------
    def peaks_of(self, k):
        """The peaks of spectrum k: the shared list, or k's own list."""
        if self.own_peaks is None or k == self.current_index:
            return self.peaks
        return self.own_peaks[k] or []

    def _peaks_changed(self, rows=None):
        """The peaks of these spectra (default: the shown one) were changed by
        hand: their fit no longer belongs to them - shown as not fitted yet."""
        if not self.series_results:
            return
        changed = False
        for r in ([self.current_index] if rows is None else rows):
            res = self.series_results[r]
            if res and not res.get('pending'):
                self.series_results[r] = {'label': str(self.series[r].get('label', '')),
                                          'ok': False, 'peaks': None, 'r2': None,
                                          'pending': True}
                changed = True
        if changed:
            self._refresh_series_table()

    def copy_peaks(self):
        """Remember the shown spectrum's peaks (Copy peaks) - to paste them to
        other spectra (Paste peaks to the selected spectra)."""
        import copy
        for i in range(len(self.peaks)):
            self.update_peak_from_table(i)
        if not self.peaks:
            return None
        name = str(self.series[self.current_index].get('label', '')).rsplit(' : ', 1)[-1]
        self.peaks_clipboard = (name, copy.deepcopy(self.peaks))
        self._update_peaks_title()
        return name

    def paste_peaks_to_selected(self, rows=None):
        """The copied peaks become the peaks of the selected spectra (rows),
        replacing theirs. Returns the rows."""
        import copy
        if not self.peaks_clipboard:
            return []
        rows = self.selected_spectra() if rows is None else list(rows)
        for r in rows:
            peaks = copy.deepcopy(self.peaks_clipboard[1])
            if r == self.current_index:
                self.peaks[:] = peaks
            else:
                self.own_peaks[r] = peaks
        self._peaks_changed(rows)
        if self.current_index in rows:
            self.fit_results = None
            self.update_peaks_table()
            self.update_plot()
        self._update_fit_button()
        return rows

    def copy_peaks_to_selected(self):
        """Copy the shown spectrum's peaks and paste them to the other selected
        spectra. Returns those rows."""
        if self.copy_peaks() is None:
            return []
        return self.paste_peaks_to_selected(
            [r for r in self.selected_spectra() if r != self.current_index])

    def _update_peaks_title(self):
        if not hasattr(self, 'peaks_group'):
            return
        if len(self.series) > 1:
            name = str(self.series[self.current_index].get('label', '')).rsplit(' : ', 1)[-1]
            self.peaks_group.setTitle(f"Peaks of {self._shorten(name)} (the shown spectrum)")
        else:
            self.peaks_group.setTitle("Peaks to Fit")
        if hasattr(self, 'copy_peaks_button'):
            name = str(self.series[self.current_index].get('label', '')).rsplit(' : ', 1)[-1]
            self.copy_peaks_button.setText(f"Copy peaks of {name}")
            self.copy_peaks_button.setEnabled(bool(self.peaks))
            self.copy_peaks_button.setToolTip(
                f"Remember the peaks of {name} (this table), to paste them to other spectra."
                + ("" if self.peaks else f"\n\n{name} has no peaks yet - add some first."))
            rows = self.selected_spectra()
            clip = self.peaks_clipboard
            if clip:
                self.paste_peaks_button.setText(
                    f"Paste peaks of {clip[0]} to the selected spectra ({len(rows)})")
            else:
                self.paste_peaks_button.setText("Paste peaks to the selected spectra")
            self.paste_peaks_button.setEnabled(bool(clip) and bool(rows))
            self.paste_peaks_button.setToolTip(
                "The copied peaks become the peaks of the spectra selected in the list - "
                "replacing theirs. For a series of similar spectra: set up the peaks on one, "
                "Copy peaks, select the others (All), Paste, then Fit Peaks."
                + ("\n\nFirst Copy peaks of a spectrum." if not clip else ""))
        if hasattr(self, 'auto_detect_btn'):
            rows = self.selected_spectra() if len(self.series) > 1 else []
            self.auto_detect_btn.setText(
                f"Auto-Detect Peaks \u2013 {len(rows)} spectra" if len(rows) > 1
                else "Auto-Detect Peaks")
            if hasattr(self, 'clear_peaks_btn'):
                self.clear_peaks_btn.setText(
                    f"Clear All Peaks \u2013 {len(rows)} spectra" if len(rows) > 1
                    else "Clear All Peaks")

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
        self._peaks_changed()
        
        # Invalidate the fit
        self.fit_results = None
        # Disable copy button only if the list is now empty
        self.copy_results_btn.setEnabled(bool(self.peaks)) 
        
        # Refresh UI
        self.update_peaks_table() 
        self.update_plot()

    def clear_peaks(self):
        """Removes all peaks of the shown spectrum - with several spectra
        selected, of all the selected ones (Clear All Peaks - N spectra)."""
        rows = self.selected_spectra() if len(self.series) > 1 else []
        for r in rows:
            if r != self.current_index:
                self.own_peaks[r] = []
        self.peaks.clear()
        self._peaks_changed(sorted(set(rows) | {self.current_index})
                            if len(self.series) > 1 else None)
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
        # the old Model drop-downs: hidden at once (Qt deletes a replaced cell
        # widget only later; until then it showed in the top-left corner)
        for r in range(self.peaks_table.rowCount()):
            old = self.peaks_table.cellWidget(r, 1)
            if old is not None:
                self.peaks_table.removeCellWidget(r, 1)
                old.hide()
                old.deleteLater()
        
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
        self._update_fit_button()

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
        self._peaks_changed()
        self.update_peaks_table()
        self.update_plot()

    def on_table_cell_changed(self):
        """Fired when user edits the table. This invalidates the 'fit'."""
        for i in range(self.peaks_table.rowCount()): 
            self.update_peak_from_table(i)
        self.fit_results = None
        self._peaks_changed()
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
            
        constraint = self.constraint_of()

        # Fit using the full spectrum data
        fitted_results, y_fit_total = self.manager.fit_peaks(self.x_roi, self.y_roi, self.peaks, amplitude_constraint=constraint)
        
        if fitted_results is None:
            QMessageBox.warning(self, "Fit Failed", "The fitting algorithm could not converge.")
            self.copy_results_btn.setEnabled(bool(self.peaks)) # Keep button enabled
            return
            
        self.fit_results = fitted_results
        self.copy_results_btn.setEnabled(True) 
        self.update_peaks_table(from_fit_results=True) # Update table with fit results
        if self.series_results is None and len(self.series) > 1:
            # the first fit in the series: kept for this spectrum (the others not yet)
            from src.modules.data_analysis import peak_fitting_series as pfs
            self.series_results = pfs.pending(self.series)
        if self.series_results is not None:              # a (re)fit of one spectrum of the series
            y = np.asarray(self.y_roi, dtype=float)
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            r2 = 1.0 - float(np.sum((y - y_fit_total) ** 2)) / ss_tot if ss_tot > 0 else np.nan
            self.series_results[self.current_index] = {
                'label': self.spectrum.get('label', ''), 'ok': True, 'peaks': fitted_results,
                'r2': r2}
            self._refresh_series_table()
        self.update_plot(y_fit_total=y_fit_total)

    # ------------------------------------------------------------------
    # A series: several spectra fitted in this window
    # ------------------------------------------------------------------
    SERIES_VIEWS = [('overlay', "Overlay"), ('waterfall', "Waterfall"), ('grid', "Grid")]
    GRID_MAX = 16

    def _build_series_tab(self):
        """The tab Series results: one row per spectrum (position, FWHM, height,
        area of each peak, R²); a click on a row shows that spectrum."""
        page = QWidget()
        v = QVBoxLayout(page)
        self.series_info = QLabel("Set up and fit the peaks on the shown spectrum (tab Peaks), "
                                  "then select the spectra in the list beside the plot (All for "
                                  "the whole series) and click Fit Peaks. The results come here: "
                                  "one row per spectrum; click a row to see its fit.")
        self.series_info.setWordWrap(True)
        v.addWidget(self.series_info)
        self.series_table = QTableWidget(0, 0)
        self.series_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.series_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.series_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.series_table.itemSelectionChanged.connect(self._series_selection_changed)
        v.addWidget(self.series_table, 1)
        QShortcut(QKeySequence.Copy, self.series_table, activated=self.copy_series)
        row = QHBoxLayout()
        self.series_copy_button = QPushButton("Copy")
        self.series_copy_button.setToolTip("Copy the selected rows (or the whole table) for Excel")
        self.series_copy_button.clicked.connect(lambda: self.copy_series())
        self.series_export_button = QPushButton("Export…")
        self.series_export_button.clicked.connect(lambda: self.export_series())
        self.series_data_table_button = QPushButton("Open in the Data table")
        self.series_data_table_button.setToolTip(
            "The Data table (tab Values per spectrum) with these columns (p1, p2, …) next to the "
            "values stored with the spectra: compute with them or plot e.g. a position against "
            "the temperature")
        self.series_data_table_button.clicked.connect(lambda: self.series_to_data_table())
        self.series_data_table_button.setVisible(self.open_data_table is not None)
        for b in (self.series_copy_button, self.series_export_button,
                  self.series_data_table_button):
            b.setAutoDefault(False)
            b.setEnabled(False)
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self._quick_help_button('series-results'))
        v.addLayout(row)
        return page

    def _build_navigation(self):
        """Above the plot: the spectra list on/off, ◀ ▶ (one spectrum after
        another), the shown spectrum, and View for several selected spectra."""
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        self.list_button = QToolButton()
        self.list_button.setText("Spectra")
        self.list_button.setCheckable(True)
        self.list_button.setChecked(True)
        self.list_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.list_button.setArrowType(Qt.LeftArrow)
        self.list_button.setToolTip("Show or hide the list of the spectra of the series")
        self.list_button.toggled.connect(self._toggle_spectra_list)
        h.addWidget(self.list_button)
        h.addSpacing(8)
        self.prev_button = QToolButton()
        self.prev_button.setText("◀")
        self.prev_button.setFixedSize(32, 26)
        self.prev_button.setStyleSheet("QToolButton { font-size: 13pt; }")
        self.prev_button.setToolTip("The previous spectrum of the series (only it is shown)")
        self.prev_button.clicked.connect(lambda: self.show_series_spectrum(self.current_index - 1))
        self.next_button = QToolButton()
        self.next_button.setText("▶")
        self.next_button.setFixedSize(32, 26)
        self.next_button.setStyleSheet("QToolButton { font-size: 13pt; }")
        self.next_button.setToolTip("The next spectrum of the series (only it is shown)")
        self.next_button.clicked.connect(lambda: self.show_series_spectrum(self.current_index + 1))
        h.addWidget(self.prev_button)
        h.addWidget(self.next_button)
        self.current_label = QLabel()
        self.current_label.setToolTip("The spectrum whose peaks are in the tab Peaks; Fit Peaks "
                                      "fits this one")
        h.addWidget(self.current_label, 1)
        h.addSpacing(12)
        h.addWidget(QLabel("Several selected:"))
        self.view_combo = QComboBox()
        for key, text in self.SERIES_VIEWS:
            self.view_combo.addItem(text, key)
        self.view_combo.setToolTip(
            "How several spectra selected in the list are shown:\n"
            "Overlay - in one plot; Waterfall - each shifted up; Grid - one small plot each "
            f"(at most {self.GRID_MAX}).\nData thin, fits thick (once fitted).")
        self.view_combo.currentIndexChanged.connect(lambda *_: self._view_changed())
        h.addWidget(self.view_combo)
        return bar

    def _build_spectra_panel(self):
        """The spectra of the series, as in the main window: select one to see
        (and correct) its fit, several (Ctrl/Shift+click) to see them together."""
        self.spectra_panel = QWidget()
        v = QVBoxLayout(self.spectra_panel)
        v.setContentsMargins(0, 0, 0, 0)
        self.spectra_list = QListWidget()
        self.spectra_list.setItemDelegate(_SelectedTextDelegate(self.spectra_list))
        self.spectra_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.spectra_list.setToolTip(
            "One spectrum selected: its data, fit, single peaks and residual.\n"
            "Several selected (Ctrl/Shift+click): shown together - see 'Several selected'.\n"
            "Green dot (green bold text): the spectrum has peaks to fit; grey: no peaks yet.\n"
            "\u26a0 a poor fit (R\u00b2 below 0.9).\n"
            "✓ fitted, ✗ the fit failed.")
        for sp in self.series:
            self.spectra_list.addItem(self._list_text(sp, None))
        self.spectra_list.setCurrentRow(self.current_index)
        self.spectra_list.itemSelectionChanged.connect(self._list_selection_changed)
        v.addWidget(self.spectra_list, 1)
        row = QHBoxLayout()
        self.list_all_button = QPushButton("All")
        self.list_all_button.setToolTip("Select all spectra")
        self.list_all_button.clicked.connect(lambda: self._select_in_list(range(len(self.series)),
                                                                          notify=True))
        self.list_fitted_button = QPushButton("Fitted")
        self.list_fitted_button.setToolTip("Select the fitted spectra")
        self.list_fitted_button.clicked.connect(lambda: self._select_in_list(
            [k for k, r in enumerate(self.series_results or []) if r.get('ok')], notify=True))
        for b in (self.list_all_button, self.list_fitted_button):
            b.setAutoDefault(False)
            row.addWidget(b)
        v.addLayout(row)
        self.spectra_panel.setMinimumWidth(150)
        self._update_nav(self.current_index)
        return self.spectra_panel

    @staticmethod
    def _list_text(sp, res):
        POOR = 0.9                      # R² below this: the fit is marked ⚠
        if not res or res.get('pending'):
            mark = ''
        elif not res.get('ok'):
            mark = '\u2717 '
        else:
            r2 = res.get('r2')
            mark = '\u26a0 ' if r2 is not None and np.isfinite(r2) and r2 < POOR else '\u2713 '

        return mark + str(sp.get('label', '')).rsplit(' : ', 1)[-1]

    def _toggle_spectra_list(self, shown):
        self.spectra_panel.setVisible(shown)
        self.list_button.setArrowType(Qt.LeftArrow if shown else Qt.RightArrow)

    def selected_spectra(self):
        """The rows selected in the spectra list (sorted)."""
        if not hasattr(self, 'spectra_list'):
            return []
        return sorted(self.spectra_list.row(i) for i in self.spectra_list.selectedItems())

    def _select_in_list(self, rows, notify=False):
        """Select these rows in the spectra list and in Series results."""
        rows = list(rows)
        if hasattr(self, 'spectra_list'):
            lst = self.spectra_list
            lst.blockSignals(True)
            lst.clearSelection()
            for r in rows:
                lst.item(r).setSelected(True)
            if len(rows) == 1:
                lst.setCurrentRow(rows[0], QItemSelectionModel.Select)
                lst.scrollToItem(lst.item(rows[0]))
            lst.blockSignals(False)
        self._select_table_rows(rows)
        if notify:
            self._list_selection_changed()

    def _select_table_rows(self, rows):
        if not hasattr(self, 'series_table') or self.series_results is None:
            return
        t = self.series_table
        t.blockSignals(True)
        t.clearSelection()
        model = t.selectionModel()
        for r in rows:
            if r < t.rowCount():
                model.select(t.model().index(r, 0),
                             QItemSelectionModel.Select | QItemSelectionModel.Rows)
        t.blockSignals(False)
        t.viewport().update()

    def _update_nav(self, k):
        if hasattr(self, 'prev_button'):
            self.prev_button.setEnabled(k > 0)
            self.next_button.setEnabled(k < len(self.series) - 1)
            name = str(self.series[k].get('label', '')).rsplit(' : ', 1)[-1]
            self.current_label.setText("<b>" + self._shorten(name) + "</b>")
            self.current_label.setToolTip(
                f"{self.series[k].get('label', '')}\nThe shown spectrum: its peaks are in the tab "
                "Peaks.")
        if hasattr(self, 'view_combo'):
            self.view_combo.setEnabled(len(self.selected_spectra()) > 1)
        self._update_fit_button()

    def _list_selection_changed(self):
        """One spectrum selected: it alone (with its fit); several: together."""
        rows = self.selected_spectra()
        self._select_table_rows(rows)
        if len(rows) == 1:
            self.show_series_spectrum(rows[0])
            return
        # several: the shown spectrum (whose peaks the table shows) stays the
        # same - only selecting one spectrum alone shows another one
        self._update_nav(self.current_index)
        self._view_changed()

    def _series_selection_changed(self):
        """Rows selected in Series results: the same spectra selected in the list."""
        rows = self.selected_series_rows()
        if rows:
            self._select_in_list(rows, notify=True)

    def _view_changed(self):
        several = len(self.selected_spectra()) > 1
        self.view_mode = ((self.view_combo.currentData() if hasattr(self, 'view_combo') else None)
                          or 'overlay') if several else 'one'
        if hasattr(self, 'view_combo'):
            self.view_combo.setEnabled(several)
        self._update_plot_options()
        if self.view_mode == 'one':
            self.update_plot_with_fit_results()
        else:
            self.update_plot()

    def _update_plot_options(self):
        """Residual only for one spectrum; Legend also in Overlay and
        Waterfall, not in Grid (each small plot has its name as title)."""
        if hasattr(self, 'residual_check'):
            self.residual_check.setEnabled(self.view_mode == 'one')
            self.legend_check.setEnabled(self.view_mode in ('one', 'overlay', 'waterfall'))
            self.residual_check.setToolTip(
                "Show the residual (data minus fit) under the plot" if self.view_mode == 'one'
                else "The residual is shown for one spectrum only (select one in the list)")
            self.legend_check.setToolTip(
                "Show the legend (it can be long with many peaks)" if self.view_mode != 'grid'
                else "In Grid each small plot has the spectrum's name as its title")
        self._update_click_hint()
        self._update_output_for()
        self._update_fit_button()

    def _update_output_for(self):
        """The counts in Add for, and which spectra get the outputs."""
        if not hasattr(self, 'output_for_combo') or len(self.series) < 2:
            return
        res = self.series_results or []
        fitted = [k for k, r in enumerate(res) if r.get('ok')]
        chosen = [k for k in self.selected_spectra() if k in fitted]
        self.output_for_combo.setItemText(0, f"all fitted spectra ({len(fitted)})")
        self.output_for_combo.setItemText(
            1, f"the fitted spectra selected in the list ({len(chosen)})")

    def output_spectra(self):
        """The rows of the series that get the output spectra on OK (fitted)."""
        res = self.series_results or []
        fitted = [k for k, r in enumerate(res) if r.get('ok')]
        if self.output_for_combo.currentData() == 'selected':
            return [k for k in self.selected_spectra() if k in fitted]
        return fitted

    def _set_current(self, k):
        """Spectrum k becomes the shown one (the tab Peaks lists its fit)."""
        for i in range(len(self.peaks)):
            self.update_peak_from_table(i)
        if self.own_peaks is not None:
            self.own_peaks[self.current_index] = self.peaks
            if self.own_peaks[k] is None:
                self.own_peaks[k] = []
            self.peaks = self.own_peaks[k]
        self.current_index = k
        self.spectrum = self.series[k]
        self.x_roi = self.spectrum['x_scale']
        self.y_roi = self.spectrum['y_scale']
        result = self.series_results[k] if self.series_results else None
        if result and result.get('ok') and len(result['peaks']) == len(self.peaks):
            self.fit_results = result['peaks']
            self.update_peaks_table(from_fit_results=True)
        else:
            self.fit_results = None
            self.update_peaks_table()
        self._update_nav(k)

    def show_series_spectrum(self, k):
        """Show spectrum k of the series alone: its data, and its fit when it
        has one (the tab Peaks then lists its fitted values). The peaks set
        up stay the same for all spectra."""
        if not self.series or not 0 <= k < len(self.series):
            return
        self._set_current(k)
        if self.selected_spectra() != [k]:
            self._select_in_list([k])
        self._update_nav(k)
        self.view_mode = 'one'
        self._update_plot_options()
        if hasattr(self, 'ax_main'):
            self.ax_main.autoscale(True)
        self.update_plot_with_fit_results()

    def selected_series_rows(self):
        if not hasattr(self, 'series_table'):
            return []
        return sorted({i.row() for i in self.series_table.selectedIndexes()})

    def series_rows(self):
        """(columns, rows) of the series results (pfs.series_table)."""
        from src.modules.data_analysis import peak_fitting_series as pfs
        n = max([len(self.peaks)] + [len(r.get('peaks') or []) for r in (self.series_results or [])
                                     if r.get('ok')])
        return pfs.series_table(self.series_results or [], n)

    def _refresh_series_table(self):
        from src.modules.data_analysis import peak_fitting_series as pfs
        if not hasattr(self, 'series_table') or self.series_results is None:
            return
        columns, rows = self.series_rows()
        t = self.series_table
        keep = self.selected_spectra() or self.selected_series_rows()
        t.blockSignals(True)
        t.clear()
        t.setColumnCount(len(columns))
        t.setHorizontalHeaderLabels(columns)
        t.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                item = QTableWidgetItem()
                if isinstance(v, float) and np.isfinite(v):
                    item.setData(Qt.DisplayRole, float(f'{v:.6g}'))
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                elif isinstance(v, str):
                    item.setText(v)
                t.setItem(r, c, item)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        t.resizeColumnsToContents()
        t.setColumnWidth(0, min(t.columnWidth(0), 220))
        for r in keep:
            if r < len(rows):
                t.selectRow(r)
        t.blockSignals(False)
        self.series_info.setText(pfs.summary(self.series_results) + " Click a row (or a spectrum "
                                 "in the list beside the plot) to see its fit; select several to "
                                 "see them together (Overlay, Waterfall or Grid). A bad fit: "
                                 "correct the peaks in the tab Peaks and Fit Peaks - only that "
                                 "spectrum is fitted again.")
        for b in (self.series_copy_button, self.series_export_button,
                  self.series_data_table_button):
            b.setEnabled(True)
        self._update_output_for()
        if hasattr(self, 'spectra_list'):
            self._refresh_list_texts()

    def series_start(self):
        """The starting peaks of the series: the fitted peaks of the shown
        spectrum if it has been fitted, else the peaks as set up."""
        from src.modules.data_analysis import peak_fitting_series as pfs
        for i in range(len(self.peaks)):
            self.update_peak_from_table(i)
        if self.fit_results and len(self.fit_results) == len(self.peaks):
            return pfs.start_from(self.fit_results, self.peaks)
        return [dict(p) for p in self.peaks]

    @staticmethod
    def _shorten(text, at_most=32):
        """A long name cut to `at_most` characters with '…' (shown in full in
        the tooltip)."""
        text = str(text)
        return text if len(text) <= at_most else text[:at_most].rstrip() + '\u2026'

    def _short_names(self, rows, at_most=4):
        names = [self._shorten(str(self.series[r].get('label', '')).rsplit(' : ', 1)[-1], 20)
                 for r in rows]
        return ', '.join(names[:at_most]) + (f" and {len(names) - at_most} more"
                                             if len(names) > at_most else '')

    HAS_PEAKS_COLOR = '#2E7D32'          # green: the spectrum has peaks to fit

    def _dot_icon(self, on):
        from PyQt5.QtGui import QIcon, QPixmap, QPainter
        key = '_dot_on' if on else '_dot_off'
        if not hasattr(self, key):
            pix = QPixmap(12, 12)
            pix.fill(Qt.transparent)
            if on:
                p = QPainter(pix)
                p.setRenderHint(QPainter.Antialiasing)
                p.setBrush(QColor(self.HAS_PEAKS_COLOR))
                p.setPen(QColor('white'))
                p.drawEllipse(1, 1, 10, 10)
                p.end()
            icon = QIcon(pix)
            icon.addPixmap(pix, QIcon.Selected)          # the same full dot when selected
            setattr(self, key, icon)
        return getattr(self, key)

    def _mark_spectra_with_peaks(self):
        """In the list: a green dot (also seen when selected) and green bold
        text for spectra with peaks, grey text for those without (and
        ✓ / ⚠ / ✗ for the fit)."""
        if not hasattr(self, 'spectra_list'):
            return
        for k in range(self.spectra_list.count()):
            item = self.spectra_list.item(k)
            has = bool(self.peaks_of(k))
            item.setIcon(self._dot_icon(has))
            item.setForeground(QColor(self.HAS_PEAKS_COLOR) if has else QColor('#9E9E9E'))
            f = item.font()
            f.setBold(has)
            item.setFont(f)

    NO_PEAKS_TEXT = ("No peaks to fit yet: click Auto-Detect Peaks, or tick Add via Click and "
                     "click on the top of each band in the plot.")

    CONSTRAINTS = ['unrestricted', 'positive', 'negative']   # the combo's items 0, 1, 2
    CONSTRAINT_NAMES = {'unrestricted': "Unrestricted", 'positive': "Positive Peaks Only",
                        'negative': "Negative Peaks Only"}

    def constraint_of(self, k=None):
        """The Amplitude Constraint of spectrum k (default: the shown one)."""
        if (self.own_constraints is not None and self.own_constraint_check.isChecked()):
            k = self.current_index if k is None else k
            if self.own_constraints[k] is not None:
                return self.own_constraints[k]
        return self.global_constraint

    def _constraint_chosen(self):
        """The combo was changed: for all spectra, or - each spectrum its own -
        for the spectra selected in the list."""
        if getattr(self, '_setting_combo', False):
            return
        k = self.amplitude_combo.currentIndex()
        if not 0 <= k < 3:
            return                                      # "— mixed —" chosen: nothing
        value = self.CONSTRAINTS[k]
        if self.own_constraints is not None and self.own_constraint_check.isChecked():
            for r in (self.selected_spectra() or [self.current_index]):
                self.own_constraints[r] = value
        else:
            self.global_constraint = value
        self._show_constraint()

    def _own_constraint_toggled(self):
        self._show_constraint()

    def _show_constraint(self):
        """The combo shows the constraint of the selected spectra ("— mixed —"
        when they differ); the list marks (+) / (−) with own constraints."""
        if not hasattr(self, 'amplitude_combo'):
            return
        own = self.own_constraints is not None and self.own_constraint_check.isChecked()
        rows = (self.selected_spectra() or [self.current_index]) if own else []
        values = sorted({self.constraint_of(r) for r in rows}) if own else [self.global_constraint]
        self._setting_combo = True
        try:
            if self.amplitude_combo.count() > 3:
                self.amplitude_combo.removeItem(3)
            if len(values) == 1:
                self.amplitude_combo.setCurrentIndex(self.CONSTRAINTS.index(values[0]))
            else:
                self.amplitude_combo.addItem("\u2014 mixed \u2014")
                self.amplitude_combo.setCurrentIndex(3)
        finally:
            self._setting_combo = False
        if hasattr(self, 'constraint_note'):
            if own and len(values) > 1:
                counts = {v: sum(self.constraint_of(r) == v for r in rows) for v in values}
                self.constraint_note.setText(
                    "The selected spectra have different constraints: " + ", ".join(
                        f"{n} {self.CONSTRAINT_NAMES[v]}" for v, n in counts.items())
                    + ". Choosing one sets it for all of them.")
            elif own:
                self.constraint_note.setText(
                    f"Each spectrum its own: the constraint applies to the {len(rows)} selected "
                    f"spectr{'um' if len(rows) == 1 else 'a'}.")
            self.constraint_note.setVisible(own)
        self._refresh_list_texts()

    def _refresh_list_texts(self):
        if not hasattr(self, 'spectra_list'):
            return
        own = self.own_constraints is not None and self.own_constraint_check.isChecked()
        for k in range(self.spectra_list.count()):
            res = self.series_results[k] if self.series_results else None
            text = self._list_text(self.series[k], res)
            if own:
                text += {'positive': '  (+)', 'negative': '  (\u2212)'}.get(self.constraint_of(k), '')
            self.spectra_list.item(k).setText(text)

    def _fit_plan(self, rows):
        """How each of these spectra (in the order of the list) is fitted:
        'own' - from its own peaks; 'chain' - it has none: from the fit of
        the spectrum before it (only with 'Spectra without peaks: start from
        the fit before them' ticked); 'left out' - otherwise."""
        plan, before = [], False
        follow = hasattr(self, 'follow_check') and self.follow_check.isChecked()
        for r in sorted(rows):
            if self.peaks_of(r):
                plan.append((r, 'own'))
                before = True
            elif before and follow:
                plan.append((r, 'chain'))
            else:
                plan.append((r, 'left out'))
        return plan

    def _chain_start(self, r):
        """The start of 'the previous spectrum's result': the peaks (or the
        fit) of the first spectrum fitted, r."""
        if r == self.current_index:
            return self.series_start()
        return [dict(p) for p in self.peaks_of(r)]

    def _update_fit_button(self):
        """The fit button says how many spectra it fits (the selected ones);
        without peaks it is greyed and a line says what to do first."""
        if not hasattr(self, 'fit_button'):
            return
        from src.modules.data_analysis import peak_fitting_series as pfs
        has_peaks = bool(self.peaks)
        note = ''
        if len(self.series) > 1:
            chosen = self.selected_spectra() or [self.current_index]
            plan = self._fit_plan(chosen)
            has_peaks = any(how != 'left out' for _, how in plan)
            chained = [r for r, how in plan if how == 'chain']
            left = [r for r, how in plan if how == 'left out']
            parts = []
            if chained and has_peaks:
                parts.append(f"No peaks of their own: {self._short_names(chained)} \u2013 each "
                             "starts from the fit of the selected spectrum before it.")
            if left and has_peaks:
                if self.follow_check.isChecked():
                    parts.append(f"Left out (no peaks, no fit before them): "
                                 f"{self._short_names(left)}.")
                else:
                    parts.append(f"Left out (no peaks): {self._short_names(left)}.")
            note = ' '.join(parts)
        self.fit_button.setEnabled(has_peaks)
        self._update_peaks_title()
        if len(self.series) > 1:
            self._show_constraint()
        self._mark_spectra_with_peaks()
        if hasattr(self, 'no_peaks_hint'):
            self.no_peaks_hint.setText(note or self.NO_PEAKS_TEXT)
            self.no_peaks_hint.setVisible(not has_peaks or bool(note))
        if len(self.series) < 2:
            return
        n = max(len(self.selected_spectra()), 1)
        self.fit_button.setText("Fit Peaks \u2013 1 spectrum" if n == 1
                                else f"Fit Peaks \u2013 {n} selected spectra")

    def fit_selected(self):
        """The fit button: the shown spectrum alone, or - with several
        selected in the list - all of them (fit_all_selected)."""
        rows = self.selected_spectra() if len(self.series) > 1 else []
        if len(rows) > 1:
            return self.fit_all_selected(rows=rows)
        return self.perform_fit()

    def fit_all_selected(self, rows=None):
        """Fit several spectra of the series (rows; all when None), in the
        order of the list: each from its own peaks; a spectrum without peaks
        is left out - or, with follow_check ticked, starts from the fit of the
        spectrum before it (so peaks set on the first spectrum only follow
        bands that shift along a series). When all have
        their own peaks they are fitted independently, on several processor
        cores. The results go to the tab Series results; spectra not fitted
        now keep theirs. Returns the new results (None if nothing could be
        fitted or it was cancelled)."""
        from PyQt5.QtWidgets import QProgressDialog
        from src.modules.data_analysis import peak_fitting_series as pfs
        from src.modules.utils.progress_utils import OperationCancelled
        for i in range(len(self.peaks)):
            self.update_peak_from_table(i)
        pool = list(range(len(self.series))) if rows is None else rows
        plan = [(r, how) for r, how in self._fit_plan(pool) if how != 'left out']
        if not plan:
            QMessageBox.information(self, "Fit Peaks",
                                    "Add the peaks first (Auto-Detect Peaks or Add via Click), "
                                    "ideally fit them on one spectrum, then fit the others.")
            return None
        rows = [r for r, _ in plan]
        spectra = [self.series[r] for r in rows]
        starts = [(self._chain_start(r) if how == 'own' else None) for r, how in plan]
        constraints = [self.constraint_of(r) for r in rows]
        constraint = constraints[0] if len(set(constraints)) == 1 else None
        progress_window = QProgressDialog("Fitting the spectra\u2026", "Cancel", 0,
                                          len(spectra), self)
        progress_window.setWindowTitle("Fit Peaks")
        progress_window.setMinimumDuration(400)

        def progress(done, total):
            progress_window.setValue(done)
            QApplication.processEvents()
            if progress_window.wasCanceled():
                raise OperationCancelled()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if all(st is not None for st in starts):  # all their own: independent
                if constraint is not None and all(st == starts[0] for st in starts):
                    results = pfs.fit_series_independent(spectra, starts[0], constraint, progress)
                else:                               # e.g. pasted: one start for all
                    results = pfs.fit_series_independent(spectra, None, constraint or
                                                         'unrestricted', progress,
                                                         starts=starts, constraints=constraints)
            else:                                       # some follow the fit before them
                results, used = pfs.fit_each(spectra, starts, constraint or 'unrestricted',
                                             progress, constraints=constraints)
        except OperationCancelled:
            return None
        finally:
            QApplication.restoreOverrideCursor()
            progress_window.close()
        merged = list(self.series_results or pfs.pending(self.series))
        for k, (r, res) in enumerate(zip(rows, results)):
            merged[r] = res
            if res['ok'] and starts[k] is None and r != self.current_index:
                # it had no peaks: its fit becomes its peaks (shown with it, and
                # the start of a next fit)
                self.own_peaks[r] = pfs.start_from(res['peaks'], used[k])
        self.series_results = merged
        self.copy_results_btn.setEnabled(True)
        self._refresh_series_table()
        if hasattr(self, 'left_tabs'):
            self.left_tabs.setCurrentIndex(1)
        if len(self.selected_spectra()) > 1:            # several shown: keep them, now fitted
            self._set_current(self.current_index)
            self._select_table_rows(self.selected_spectra())
            self._view_changed()
        else:
            self.show_series_spectrum(self.current_index)
        return results

    def copy_series(self):
        """Copy the selected rows of Series results (the spectra selected in
        the list) - or, with none selected, the rows of all fitted spectra."""
        from src.modules.data_analysis import peak_list as pl
        columns, rows = self.series_rows()
        picked = self.selected_series_rows()
        if not picked:
            picked = [k for k, r in enumerate(self.series_results or [])
                      if not r.get('pending')]
            self.copied_what = 'all fitted ones'
        else:
            self.copied_what = 'the selected ones'
        self.copied_rows = len(picked)
        text = pl.rows_as_text([rows[r] for r in picked], columns)
        QApplication.clipboard().setText(text)
        return text

    def export_series(self, path=None):
        from src.modules.data_analysis import peak_list as pl
        if path is None:
            path, chosen = QFileDialog.getSaveFileName(
                self, "Export the series", "peak_fit_series.xlsx",
                "Excel (*.xlsx);;CSV (*.csv);;Text, tab-separated (*.txt)")
            if not path:
                return None
            if '.' not in path.replace('\\', '/').split('/')[-1]:
                path += {'CSV': '.csv', 'Text': '.txt'}.get(chosen.split(' ')[0], '.xlsx')
        columns, rows = self.series_rows()
        try:
            pl.export(rows, path, columns)
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"The table could not be saved:\n\n{exc}")
            return None
        return path

    def series_to_data_table(self):
        if self.open_data_table is None or self.series_results is None:
            return None
        columns, rows = self.series_rows()
        items = [(title, [row[c] for row in rows]) for c, title in enumerate(columns) if c > 0]
        return self.open_data_table(self, self.series, items)

    def _draw_series_view(self):
        """Overlay / Waterfall / Grid: the fitted spectra of the series (the
        selected rows of Series results, or all) - data and fit."""
        from src.modules.data_analysis import peak_fitting_series as pfs
        self.figure.clear()
        rows = self.selected_spectra()
        if len(rows) < 2:
            rows = list(range(len(self.series)))
        note = ''
        if self.view_mode == 'grid' and len(rows) > self.GRID_MAX:
            note = f" (the first {self.GRID_MAX} of {len(rows)}; select rows to choose)"
            rows = rows[:self.GRID_MAX]
        colors = plt.rcParams['axes.prop_cycle'].by_key().get('color', ['C0'])
        if self.view_mode == 'grid':
            n = len(rows)
            cols = int(np.ceil(np.sqrt(n)))
            nrows = int(np.ceil(n / cols))
            for k, r in enumerate(rows):
                ax = self.figure.add_subplot(nrows, cols, k + 1)
                sp, res = self.series[r], self._series_result(r)
                x, y = np.asarray(sp['x_scale'], float), np.asarray(sp['y_scale'], float)
                ax.plot(x, y, '.', color='gray', ms=2)
                if res.get('ok'):
                    total, _ = pfs.model_curves(x, res['peaks'], self.manager)
                    ax.plot(x, total, 'r-', lw=1.4)
                r2 = res.get('r2')
                ok = res.get('ok') and r2 is not None and np.isfinite(r2)
                failed = bool(res) and not res.get('ok') and not res.get('pending')
                ax.set_title((str(sp.get('label', '')).rsplit(' : ', 1)[-1])
                             + (f"  R\u00b2 {r2:.3f}" if ok else "  not fitted" if failed else ""),
                             fontsize=7, color='red' if failed else 'black')
                ax.tick_params(labelsize=6)
            self.figure.suptitle(f"Grid: {n} spectra, data (grey)"
                                 + (" and fit (red)" if any(self._series_result(r).get('ok')
                                                            for r in rows) else "") + note,
                                 fontsize=9)
        else:
            ax = self.figure.add_subplot(111)
            spans = [np.ptp(np.asarray(self.series[r]['y_scale'], float)) for r in rows]
            step = 1.1 * (max(spans) if spans else 1.0) if self.view_mode == 'waterfall' else 0.0
            for k, r in enumerate(rows):
                sp, res = self.series[r], self._series_result(r)
                x, y = np.asarray(sp['x_scale'], float), np.asarray(sp['y_scale'], float)
                color = colors[k % len(colors)]
                name = str(sp.get('label', '')).rsplit(' : ', 1)[-1]
                fitted = bool(res.get('ok'))
                ax.plot(x, y + k * step, '-', color=color, lw=0.7,
                        alpha=0.45 if fitted else 0.9, label=None if fitted else name)
                if fitted:
                    total, _ = pfs.model_curves(x, res['peaks'], self.manager)
                    ax.plot(x, total + k * step, '-', color=color, lw=2.0, label=name)
            any_fit = any(self._series_result(r).get('ok') for r in rows)
            ax.set_title(("Waterfall" if step else "Overlay") + f": {len(rows)} spectra"
                         + (" - data thin, fits thick" if any_fit else ""), fontsize=10)
            ax.set_xlabel("X-Axis")
            ax.set_ylabel("Intensity" + (" (shifted)" if step else ""))
            ax.grid(True, alpha=0.4)
            if len(rows) <= 20 and self.legend_check.isChecked():
                ax.legend(fontsize=7)
        self.canvas.draw()

    def _series_result(self, r):
        """The series result of spectrum r ({} when the series is not fitted yet)."""
        return self.series_results[r] if self.series_results else {}

    def copy_results_to_clipboard(self):
        """Copies the results: with series results the whole series table (one
        row per spectrum), else the CURRENT peak parameters of the table."""
        if self.series_results is not None:
            self.copy_series()
            n = self.copied_rows
            QMessageBox.information(self, "Results Copied",
                                    f"The series results of {n} spectr{'a' if n != 1 else 'um'} "
                                    f"({self.copied_what}) were copied to the clipboard - one "
                                    "row per spectrum, ready to paste into Excel.")
            return
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
        """Redraws the plot: the shown spectrum, or - with series results -
        several spectra (Overlay, Waterfall, Grid)."""
        if self.view_mode != 'one' and len(self.series) > 1:
            self._draw_series_view()
            return
        self._draw_one(y_fit_total)

    def _emphasize_selected_peaks(self):
        """The peaks selected in the table: drawn thick and filled in the plot
        (the others thin) - to see which peak a row is."""
        lines = getattr(self, '_peak_lines', {})
        if not lines or self.view_mode != 'one':
            return
        rows = {i.row() for i in self.peaks_table.selectionModel().selectedRows()}
        for poly in getattr(self, '_peak_fills', []):
            try:
                poly.remove()
            except (ValueError, NotImplementedError):
                pass
        self._peak_fills = []
        for i, (line, y) in lines.items():
            line.set_linewidth(3.0 if i in rows else 1.5)
            line.set_alpha(1.0 if (not rows or i in rows) else 0.45)
            if i in rows:
                self._peak_fills.append(self.ax_main.fill_between(
                    self.x_roi, y, 0, color=line.get_color(), alpha=0.25, linewidth=0))
        self.canvas.draw_idle()

    def _draw_one(self, y_fit_total=None):
        """The shown spectrum: data, fit or guesses, single peaks, residual."""
        self._peak_lines = {}
        self._peak_fills = []
        self.figure.clear()
        show_residual = not hasattr(self, 'residual_check') or self.residual_check.isChecked()
        if show_residual:
            gs = self.figure.add_gridspec(2, 1, height_ratios=[3, 1])
            self.ax_main = self.figure.add_subplot(gs[0])
            self.ax_residual = self.figure.add_subplot(gs[1], sharex=self.ax_main)
        else:
            self.ax_main = self.figure.add_subplot(111)
            self.ax_residual = None
        
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
                    line, = self.ax_main.plot(self.x_roi, y_component, ':', color=color, label=f'Peak {i+1} ({model_name})')
                    self._peak_lines[i] = (line, y_component)
            else:
                # --- STATE 2: Plotting initial GUESSES ---
                for i, peak in enumerate(self.peaks):
                    try:
                        # Use the stored stable color
                        color = peak['color']
                        model_func, _ = self.manager.peak_models[peak['model']]
                        y_guess = model_func(self.x_roi, *self._params_list_from_peak_guess(peak))
                        line, = self.ax_main.plot(self.x_roi, y_guess, '--', color=color)
                        self._peak_lines[i] = (line, y_guess)
                        y_total_model += y_guess
                    except (ValueError, TypeError): pass

            # Plot residual (Data - Model)
            if self.ax_residual is not None:
                residual = self.y_roi - y_total_model
                self.ax_residual.plot(self.x_roi, residual, color='purple')
                self.ax_residual.axhline(0, color='black', linestyle='--', lw=1)
        else:
             # No data loaded
             self.ax_main.text(0.5, 0.5, "No data to display", transform=self.ax_main.transAxes, ha='center', va='center')

        self.ax_main.set_title(f"Peak Fit for: {self.spectrum['label']}")
        self.ax_main.set_ylabel("Intensity")
        if not hasattr(self, 'legend_check') or self.legend_check.isChecked():
            self.ax_main.legend()
        self.ax_main.grid(True, alpha=0.5)
        bottom = self.ax_residual if self.ax_residual is not None else self.ax_main
        if self.ax_residual is not None:
            self.ax_residual.set_ylabel("Residual")
            self.ax_residual.grid(True, alpha=0.5)
        bottom.set_xlabel("X-Axis")
        self._emphasize_selected_peaks()
        
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
        constraint = self.global_constraint               # one for all (own ones: below)

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
            'add_via_click': self.interactive_add_cb.isChecked(), # Save checkbox state
            'output_for': self.output_for_combo.currentData(),
            'output_labels': ([str(self.series[k].get('label', '')) for k in self.output_spectra()]
                              if len(self.series) > 1 and self.series_results else None),
            'show_residual': self.residual_check.isChecked(),
            'show_legend': self.legend_check.isChecked(),
            # the shown spectrum (its fit is fit_results) and the series results
            'spectrum_label': (self.spectrum or {}).get('label'),
            **self._series_settings(),
        }

    def _series_settings(self):
        from src.modules.data_analysis import peak_fitting_series as pfs
        if len(self.series) < 2:
            return {}
        out = {'series_labels': [str(sp.get('label', '')) for sp in self.series],
               'series_index': self.current_index,
               'follow_fit_before': self.follow_check.isChecked(),
               'constraint_per_spectrum': self.own_constraint_check.isChecked(),
               'own_constraints': list(self.own_constraints)}
        if self.own_peaks is not None:
            own = list(self.own_peaks)
            own[self.current_index] = self.peaks
            out['own_peaks'] = [[{k: (float(v) if isinstance(v, (np.floating, float, int))
                                      and not isinstance(v, bool) else v)
                                  for k, v in p.items()} for p in (lst or [])] for lst in own]
        if self.series_results is not None:
            out['series_results'] = pfs.plain(self.series_results)
        return out

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