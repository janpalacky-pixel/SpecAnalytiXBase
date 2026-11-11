# src/views/dialogs/data_analysis/peak_fitting_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QDialogButtonBox, QLabel,
                             QWidget, QSplitter, QTableWidget, QTableWidgetItem, QScrollArea,
                             QFrame,
                             QHeaderView, QComboBox, QMessageBox, QCheckBox, QRadioButton, QDoubleSpinBox,
                             QAbstractSpinBox, QColorDialog, QAbstractItemView, QMenu, QApplication,
                             QTabWidget, QToolButton, QFileDialog, QShortcut, QSizePolicy,
                             QListWidget, QStyledItemDelegate, QStyle, QButtonGroup,
                             QStackedWidget, QTreeWidget, QTreeWidgetItem, QLineEdit)
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt, QTimer, QItemSelectionModel
from PyQt5.QtGui import QColor, QFont # Import QColor and QFont
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from src.views.plot_toolbar import NavigationToolbar   # with Save plot for publication
from matplotlib.figure import Figure
import matplotlib.pyplot as plt # Import pyplot
# matplotlib's default color cycle is hex strings on older versions but
# RGB float tuples on newer ones (e.g. matplotlib 3.11). QColor() rejects a
# bare tuple, so normalize through to_hex() everywhere a peak color is
# turned into a QColor, both when it's first assigned and when displaying
# one that may have been saved by an older/different matplotlib version.
from matplotlib.colors import to_hex as _mpl_to_hex, to_rgba
import numpy as np

from src.modules.data_analysis.peak_fitting_manager import (
    PeakFittingManager, BACKGROUNDS, BACKGROUND_NAMES, DEFAULT_BACKGROUND, background_values,
    initial_background, resolve_background)
# Import the help content functions
from src.help.peak_fitting_help import (get_peak_fitting_help_content,
                                        get_peak_fitting_help_title)
from src.help.help_window import show_help_window
from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

def _ignore_wheel(widget):
    """The mouse wheel over this drop-down list (or number box) does not
    change it: the wheel goes on to what is around it (the left part, the
    table of peaks), which scrolls - as in Map 2D and Melting Curve."""
    widget.wheelEvent = lambda event: event.ignore()


SHOWN_COLOUR = '#F57C00'               # the frame of the shown spectrum in the list


class _SelectedTextDelegate(QStyledItemDelegate):
    """Selected rows of the spectra list in the selection's own text colour
    (white on blue), not in the green / grey that marks peaks - so the
    marks never make a selected name hard to read; the green dot stays.
    The shown spectrum (whose peaks the table lists; shown_row) has an
    orange frame and bold text - also among several selected ones."""

    shown_row = -1

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if option.state & QStyle.State_Selected:
            from PyQt5.QtGui import QPalette
            option.palette.setBrush(QPalette.Text,
                                    option.palette.brush(QPalette.HighlightedText))
        if index.row() == self.shown_row:
            option.font.setBold(True)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.row() == self.shown_row:
            from PyQt5.QtGui import QPen
            painter.save()
            pen = QPen(QColor(SHOWN_COLOUR))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
            painter.restore()


ERROR_ROLE = Qt.UserRole + 1          # a fitted value with its uncertainty, as shown
TAG_ROLE = Qt.UserRole + 2            # a fixed or linked value: 'fixed', '=P1', 'P1+12.5'
COLUMN_PARAM = {2: 'center', 3: 'height', 4: 'width', 5: 'extra'}   # the table's value columns
FIXED_COLOUR, LINKED_COLOUR = '#E4E4E4', '#DDEBFA'


class _ErrorDelegate(QStyledItemDelegate):
    """The Peaks table after a fit: each fitted value shown with its
    uncertainty, rounded to it as usual in science: '3431.5 \u00b1 3.1'. The
    cell's text itself stays the full number (it is edited and read as
    such); the shown text is only drawn (ERROR_ROLE)."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        shown = index.data(ERROR_ROLE)
        if shown:
            option.text = shown
        tag = index.data(TAG_ROLE)
        if tag:
            option.text = f"[{tag}] {option.text}"     # the tag first: never cut off

    def createEditor(self, parent, option, index):
        """Center, Height, Width, Extra: only a number can be typed (e.g.
        354.5, -2, 1e-3) - letters are not accepted."""
        editor = super().createEditor(parent, option, index)
        if index.column() in COLUMN_PARAM and isinstance(editor, QLineEdit):
            from PyQt5.QtCore import QLocale
            from PyQt5.QtGui import QDoubleValidator
            validator = QDoubleValidator(editor)
            validator.setNotation(QDoubleValidator.ScientificNotation)
            locale = QLocale(QLocale.C)
            locale.setNumberOptions(QLocale.RejectGroupSeparator)
            validator.setLocale(locale)
            editor.setValidator(validator)
        return editor


class _BarScroll(QScrollArea):
    """A row of controls that scrolls sideways when there is not room for it
    (a scroll bar only then), instead of making the window wider."""

    def __init__(self, bar):
        super().__init__()
        self.bar = bar
        self.setWidget(bar)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMinimumWidth(120)
        self._fit_height()

    def _fit_height(self):
        need = self.bar.minimumSizeHint().width() > self.viewport().width()
        h = self.bar.sizeHint().height() + (
            self.horizontalScrollBar().sizeHint().height() if need else 0)
        if self.height() != h:
            self.setFixedHeight(h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()

    def minimumSizeHint(self):
        from PyQt5.QtCore import QSize
        return QSize(120, super().minimumSizeHint().height())


class PeakFittingDialog(QDialog):
    """Dialog for interactive peak fitting and deconvolution."""

    def __init__(self, parent=None, spectrum=None, current_settings=None, series=None,
                 open_data_table=None):
        super().__init__(parent)
        self.setWindowTitle("Peak Fitting & Deconvolution")
        # tooltips with the names of the options in bold (src/views/tooltips.py)
        from src.views import tooltips as _tooltips
        self.setProperty(_tooltips.RICH, True)
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
        # the background under the peaks, fitted together with them: its kind
        # (combo Background) and the fitted one of the shown fit (a dict, see
        # peak_fitting_manager.background_values; None = no background)
        self.background_kind = DEFAULT_BACKGROUND
        self.fit_background = None
        self.current_settings = current_settings or {}
        self.click_connection_id = None # To manage the click handler connection
        
        # Get the default matplotlib color cycle for new peaks
        self.colors = [_mpl_to_hex(color['color']) for color in plt.rcParams['axes.prop_cycle']]
        
        # Tracks the next color to use from the cycle
        self.peak_color_index = 0
        
        # the width of a clicked peak where no band can be measured (1/20 of
        # the x range); "fixed width" next to Add via Click: always its own
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
        # in a scroll area: the handle of the splitter can make the left part
        # narrower than its contents (a scroll bar then appears) - so it moves
        # freely also in a window that is not maximized
        left = QScrollArea()
        left.setWidget(control_panel)
        left.setWidgetResizable(True)
        left.setFrameShape(QFrame.NoFrame)
        left.setMinimumWidth(260)
        left.setMaximumWidth(1400)
        self.control_scroll = left
        splitter.addWidget(left)
        
        canvas_panel = self.create_canvas_panel()
        splitter.addWidget(canvas_panel)
        self.main_splitter = splitter
        
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
        widget.setMinimumWidth(380)          # narrower: the scroll area around it scrolls
        layout = QVBoxLayout(widget)

        # --- Peaks Table ---
        peaks_group = QGroupBox("Peaks to Fit")
        self.peaks_group = peaks_group
        peaks_layout = QVBoxLayout()
        self.peaks_table = QTableWidget()
        self.peaks_table.setColumnCount(7)
        self.peaks_table.setHorizontalHeaderLabels([" ", "Model", "Center", "Height", "Width", "Extra",
                                                    "Needed?"])
        for col, tip in ((2, "The position of the peak top (x)"),
                         (3, "The height of the peak top above the background (y)"),
                         (4, "Gaussian and Voigt: \u03c3; Lorentzian: \u03b3 (half width at half "
                             "height); Pseudo-Voigt: FWHM"),
                         (5, "Voigt: \u03b3 (the Lorentzian part); Pseudo-Voigt: \u03b7 (0 = "
                             "Gaussian, 1 = Lorentzian); empty for Gaussian and Lorentzian"),
                         (6, "Is this peak needed? (shown after Fit Peaks)\n"
                             "Each peak is left out once and the spectrum fitted again:\n"
                             "yes - without the peak the fit is clearly worse;\n"
                             "probably - without it the fit is somewhat worse;\n"
                             "no - without it the fit is just as good: the peak is not needed.")):
            if col in self.SORT_KEYS:
                tip += ("\nClick the heading: the peaks sorted by it, from the smallest\n"
                        "(again: from the largest) - of all spectra, so that Peak 1 is\n"
                        "the same band in every spectrum. Only the order changes.")
            self.peaks_table.horizontalHeaderItem(col).setToolTip(tip)
        # the value columns: their widths can be moved with the mouse (drag the
        # line between two headings; double-click it: as wide as the content);
        # until then they share the width of the table
        header = self.peaks_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self._columns_moved = False
        self._setting_columns = False
        header.sectionResized.connect(self._column_moved)
        # a click on Center, Height or Width sorts the peaks by it
        header.setSectionsClickable(True)
        try:
            header.sectionPressed.disconnect()          # (not: select the column)
        except TypeError:
            pass
        header.sectionClicked.connect(self._sort_by_column)
        self._sort_state = None                         # (column, ascending)
        self.peaks_table.viewport().installEventFilter(self)
        self.peaks_table.setItemDelegate(_ErrorDelegate(self.peaks_table))
        # Make the first column (color swatch) narrow - the values (with
        # their uncertainty after a fit) get the room
        self.peaks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.peaks_table.setColumnWidth(0, 28)
        self.peaks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        probe = QComboBox()
        probe.addItems(list(self.manager.peak_models))
        self.peaks_table.setColumnWidth(1, probe.sizeHint().width() + 4)
        
        self.peaks_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.peaks_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.peaks_table.itemSelectionChanged.connect(self._emphasize_selected_peaks)
        
        self.peaks_table.cellDoubleClicked.connect(self.on_color_cell_double_clicked)
        # right-click on a value: fix it, or link it to another peak
        self.peaks_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.peaks_table.customContextMenuRequested.connect(self._peaks_table_menu)
        self.peaks_table.setToolTip(
            "The peaks of the shown spectrum.\n"
            "Double-click: a value to edit it, the colour swatch to change the colour.\n"
            "Delete key: removes the selected rows (peaks).\n"
            "Width: \u03c3 for Gaussian and Voigt, \u03b3 for Lorentzian, the FWHM for Pseudo-Voigt.\n"
            "Extra: \u03b3 for Voigt, \u03b7 (0-1) for Pseudo-Voigt (shown only when a peak has it).\n"
            "Right-click a value: fix it (not fitted), or link it to another peak\n"
            "(the same width, a constant distance, a constant height ratio).")
        
        peaks_layout.addWidget(self.peaks_table)

        # --- Peak Controls ---
        btn_layout1 = QHBoxLayout()
        
        self.auto_detect_btn = QPushButton("Auto-Detect Peaks")
        self.auto_detect_btn.setToolTip(
            "Auto-Detect Peaks: finds the peaks of the shown spectrum and adds them\n"
            "to the table (not those already there).\n"
            "Auto-Detect Peaks \u2013 N spectra (several spectra selected in the list):\n"
            "finds the peaks of each selected spectrum, each into its own table.")
        self.auto_detect_btn.clicked.connect(self.auto_detect_peaks)
        from src.views import icons as _icons
        self.auto_detect_btn.setIcon(_icons.run_icon())

        self.interactive_add_cb = QCheckBox("Add via Click")
        self.interactive_add_cb.setToolTip(
            "When ticked, a click on the plot adds a peak there (Model Gaussian;\n"
            "its width as chosen in the drop-down list next to it).\n"
            "Choosing Zoom or Pan in the plot's toolbar switches this off;\n"
            "tick it again to add more peaks.")
        self.interactive_add_cb.stateChanged.connect(self._toggle_interactive_add)
        
        # the width of a clicked peak: from the band under the click
        # (default), or a fixed width chosen here
        self.click_width_combo = QComboBox()
        self.click_width_combo.addItem("width from the band", 'band')
        self.click_width_combo.addItem("fixed width \u03c3:", 'fixed')
        self.click_width_combo.setToolTip(
            "The width of a peak added by a click:\n"
            "Width from the band (default): the width of the band under the click -\n"
            "measured on smoothed data, so that the noise does not make it too narrow;\n"
            "a click on the side of a band gets that band's width. Where there is no\n"
            "band (flat baseline): 1/20 of the x range.\n"
            "Fixed width: every clicked peak gets the width (\u03c3) typed next to it.\n"
            "Fit Peaks changes the width anyway; it is only where the fit starts.")
        self.click_width_spin = QDoubleSpinBox()
        self.click_width_spin.setDecimals(3)
        self.click_width_spin.setRange(0.0, 1e9)
        self.click_width_spin.setToolTip(
            "Fixed width: the width (\u03c3, in x units) of every peak added by a click.")
        self.click_width_spin.setVisible(False)
        self.click_width_combo.currentIndexChanged.connect(lambda *_: self._click_width_changed())
        btn_layout1.addWidget(self.auto_detect_btn)
        btn_layout1.addWidget(self.interactive_add_cb)
        btn_layout1.addWidget(self.click_width_combo)
        btn_layout1.addWidget(self.click_width_spin)
        # each orange "?" next to what it explains: here adding peaks (and
        # the table above: editing, fixing, linking)
        btn_layout1.addWidget(self._quick_help_button('peaks'))
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
        remove_peak_btn.setToolTip(
            "Removes the peaks whose rows are selected in the table above -\n"
            "the peaks of the shown spectrum only (also: the Delete key).\n"
            "To remove a peak from several spectra: Series results, select rows, Delete.")
        remove_peak_btn.clicked.connect(self.remove_peak)
        
        clear_peaks_btn = QPushButton("Clear All Peaks")
        clear_peaks_btn.setToolTip(
            "Clear All Peaks: removes all peaks of the shown spectrum.\n"
            "Clear All Peaks \u2013 N spectra (several spectra selected in the list):\n"
            "removes all peaks of each selected spectrum, and their fits.\n"
            "Spectra that are not selected keep their peaks.")
        self.clear_peaks_btn = clear_peaks_btn
        clear_peaks_btn.clicked.connect(self.clear_peaks)
        
        btn_layout2.addWidget(remove_peak_btn); btn_layout2.addWidget(clear_peaks_btn)
        # next to Remove: the column Needed? (which peaks can be removed)
        btn_layout2.addWidget(self._quick_help_button('needed'))
        peaks_layout.addLayout(btn_layout2)
        peaks_group.setLayout(peaks_layout)
        # Peaks (as set up / fitted for the shown spectrum) and, with several
        # spectra, the results of fitting several of them - one window
        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(peaks_group, "Peaks")
        self.left_tabs.setTabToolTip(
            0, "Peaks: the table of the shown spectrum (orange frame in the list).\n"
               "Before a fit: the start values. After Fit Peaks: the fitted values.\n"
               "Change a value: it is set by hand (\u270e) until the next Fit Peaks.")
        if len(self.series) > 1:
            self.left_tabs.addTab(self._build_series_tab(), "Series results")
            self.left_tabs.setTabToolTip(
                1, "Series results: the values of all spectra selected in the list,\n"
                   "one row each - fitted (\u2713) or set by hand (\u270e).\n"
                   "The values of the shown spectrum are the same as in the tab Peaks.")
            # the orange "?" right after the two tabs (outside them): what each
            # shows - placed by hand next to the tab bar, which moves with it
            self.tabs_help = self._quick_help_button('tabs')
            self.tabs_help.setParent(self.left_tabs)
            self.left_tabs.tabBar().installEventFilter(self)
            QTimer.singleShot(0, self._place_tabs_help)
        layout.addWidget(self.left_tabs, 1)

        # --- Fitting Controls ---
        fit_group = QGroupBox("Fitting")
        fit_layout = QVBoxLayout()
        background_layout = QHBoxLayout()
        background_layout.addWidget(QLabel("Background:"))
        self.background_combo = QComboBox()
        for key, text in BACKGROUNDS:
            self.background_combo.addItem(text, key)
        self.background_combo.setCurrentIndex(self.background_combo.findData(DEFAULT_BACKGROUND))
        # wide enough for "Automatic (Linear)" (the text says what Automatic chose)
        self.background_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.background_combo.setToolTip(
            "A background under the peaks, fitted together with them (the peaks' heights and "
            "areas are then above it).\n"
            "Automatic (default): chosen for each spectrum from its data and shown in brackets -\n"
            "   None when the data come back to zero (CD spectra with bands up and down, "
            "baseline-corrected spectra),\n"
            "   Linear when they sit on an offset (e.g. raw Raman counts at 669).\n"
            "None: no background - the data go down to zero between the peaks.\n"
            "Constant: a flat line.\n"
            "Linear: a straight, possibly sloped line.")
        self.background_combo.currentIndexChanged.connect(lambda *_: self._background_chosen())
        background_layout.addWidget(self.background_combo)
        background_layout.addStretch()
        # the uncertainties: 1 (default), 2 or 3 sigma
        from src.modules.data_analysis import peak_fitting_series as pfs
        background_layout.addWidget(QLabel("\u00b1 shown as:"))
        self.sigma_combo = QComboBox()
        for k, text in pfs.SIGMAS:
            self.sigma_combo.addItem(text, k)
        self.sigma_combo.setToolTip(
            "How large the \u00b1 after the fitted values are:\n"
            "1 \u03c3 (default): the standard error - the true value lies within \u00b1 in about\n"
            "2 of 3 cases (68 %);\n"
            "2 \u03c3: in 19 of 20 cases (95 %);\n"
            "3 \u03c3: in 997 of 1000 cases (99.7 %).\n"
            "Only the shown and copied \u00b1 change, not the fit.")
        self.sigma_combo.currentIndexChanged.connect(lambda *_: self._sigmas_chosen())
        background_layout.addWidget(self.sigma_combo)
        background_layout.addWidget(self._quick_help_button('uncertainty'))
        fit_layout.addLayout(background_layout)
        constraint_layout = QHBoxLayout()
        constraint_layout.addWidget(QLabel("Amplitude Constraint:"))
        self.amplitude_combo = QComboBox()
        self.amplitude_combo.addItems(["Unrestricted", "Positive Peaks Only", "Negative Peaks Only"])
        self.amplitude_combo.setToolTip(
            "Which peaks the fit may use:\n"
            "Unrestricted (default): peaks up and down (e.g. CD spectra).\n"
            "Positive Peaks Only: only peaks up (Raman, IR absorbance, fluorescence).\n"
            "Negative Peaks Only: only peaks down.")
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
        # the "?" right after what it explains
        constraint_layout.addWidget(self._quick_help_button('fitting'))
        constraint_layout.addStretch()
        fit_layout.addLayout(constraint_layout)
        self.constraint_note = QLabel()
        self.constraint_note.setStyleSheet("color: #555;")
        self.constraint_note.setWordWrap(True)
        self.constraint_note.setVisible(False)
        fit_layout.addWidget(self.constraint_note)

        n_series = len(self.series)
        # several spectra: each fitted on its own, or all together (global fit)
        from src.modules.data_analysis import peak_fitting_global as pg
        together_layout = QHBoxLayout()
        self.together_label = QLabel("Several spectra:")
        together_layout.addWidget(self.together_label)
        self.together_combo = QComboBox()
        for key, text in pg.SHARES:
            self.together_combo.addItem(text, key)
        self.together_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.together_combo.setToolTip(
            "How several selected spectra are fitted:\n"
            "**Each on its own** (default): every spectrum from its own peaks,\n"
            "one after another.\n"
            "**Together: the same positions and widths** - one fit of all selected\n"
            "spectra: the same peak positions and widths for all, every spectrum\n"
            "its own heights and background. Much more stable for a noisy series\n"
            "(temperature, titration): positions and widths come from all spectra.\n"
            "**Together: the same widths** - each spectrum its own positions\n"
            "(bands that shift), the widths the same for all.\n"
            "Together starts from the peaks of the shown spectrum (the table).")
        self.together_combo.currentIndexChanged.connect(lambda *_: self._together_chosen())
        together_layout.addWidget(self.together_combo)
        together_help = self._quick_help_button('together')
        together_layout.addWidget(together_help)
        together_layout.addStretch()
        self.together_label.setVisible(n_series > 1)
        self.together_combo.setVisible(n_series > 1)
        together_help.setVisible(n_series > 1)
        fit_layout.addLayout(together_layout)
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
        self.copy_results_btn.setEnabled(False) # Disabled until peaks are added
        self.copy_results_btn.clicked.connect(self.copy_results_to_clipboard)
        # its text and what it copies follow the tab: Peaks - the table;
        # Series results - the rows of the spectra selected in the list
        self.left_tabs.currentChanged.connect(lambda *_: self._update_copy_results_button())

        fit_btn_layout.addWidget(self.fit_button, 2 if n_series < 2 else 1)
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
        first_row.addWidget(self.add_fit_check)
        first_row.addWidget(self._quick_help_button('output'))
        first_row.addStretch()
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

    def _click_width_fixed(self):
        """True: a clicked peak gets the fixed width (next to Add via Click)."""
        combo = getattr(self, 'click_width_combo', None)
        return combo is not None and combo.currentData() == 'fixed'

    def _click_width_changed(self):
        fixed = self._click_width_fixed()
        if fixed and self.click_width_spin.value() <= 0:
            self.click_width_spin.setValue(float(self.initial_peak_width or 1.0))
        self.click_width_spin.setVisible(fixed)

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
        
        # the row above the plot scrolls sideways when the plot is narrow (it
        # must not keep the splitter's handle from moving)
        layout.addWidget(_BarScroll(self._build_plot_bar()))
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
        h.addSpacing(8)
        h.addWidget(QLabel("Data:"))
        self.data_style_combo = QComboBox()
        self.data_style_combo.addItem("Points", 'points')
        self.data_style_combo.addItem("Line", 'line')
        self.data_style_combo.setToolTip("Show the measured data as points (default) or as a line")
        self.data_style_combo.currentIndexChanged.connect(lambda *_: self._view_changed())
        h.addWidget(self.data_style_combo)
        h.addSpacing(8)
        # "Data - background" (short: the row above the plot must stay narrow)
        self.subtract_check = QCheckBox("\u2212 background")
        self.subtract_check.setToolTip(
            "Subtract the background from the data in the plot.\n"
            "Off (default): the data as measured, the background (black dash-dot line)\n"
            "under the peaks.\n"
            "On: the background taken off the data and the fit - the peaks start from zero,\n"
            "as after a baseline correction. Only the drawing changes, not the fit or the values.")
        self.subtract_check.toggled.connect(lambda *_: self._view_changed())
        h.addWidget(self.subtract_check)
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
        combo = getattr(self, 'view_combo', None)
        if combo is not None:                        # Overlay / Waterfall / Grid as last time
            k = combo.findData(s.get('several_view', 'overlay'))
            combo.blockSignals(True)
            combo.setCurrentIndex(max(k, 0))
            combo.blockSignals(False)
        if s.get('click_width_value'):
            self.click_width_spin.setValue(float(s['click_width_value']))
        k = self.click_width_combo.findData(s.get('click_width', 'band'))
        self.click_width_combo.setCurrentIndex(max(k, 0))
        self._click_width_changed()
        k = self.output_for_combo.findData(s.get('output_for', 'all'))
        if k >= 0:
            self.output_for_combo.setCurrentIndex(k)
        for key, check in (('show_residual', self.residual_check),
                           ('show_legend', self.legend_check)):
            check.blockSignals(True)
            check.setChecked(bool(s.get(key, True)))
            check.blockSignals(False)
        k = self.sigma_combo.findData(s.get('error_sigmas', 1))
        if k >= 0:
            self.sigma_combo.blockSignals(True)
            self.sigma_combo.setCurrentIndex(k)
            self.sigma_combo.blockSignals(False)
        self.subtract_check.blockSignals(True)
        self.subtract_check.setChecked(bool(s.get('subtract_background', False)))
        self.subtract_check.blockSignals(False)
        for combo, value in ((self.data_style_combo, s.get('data_style', 'points')),
                             (self.background_combo, s.get('background', DEFAULT_BACKGROUND))):
            k = combo.findData(value)
            if k >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(k)
                combo.blockSignals(False)
        self.background_kind = self.background_combo.currentData()
        # (a background only with a real fit - see get_results 'fitted')
        self.fit_background = (s.get('fit_background') or None) if s.get('fitted', True) else None

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
            
            # Load both lists (one might be empty or None); 'fitted' False: the
            # window was closed before Fit Peaks - fit_results are then only
            # the starting peaks (for the outputs), shown as such again
            self.fit_results = (self.current_settings.get('fit_results')
                                if self.current_settings.get('fitted', True) else None)
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
        
        self._update_copy_results_button()
            
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
        k = self.together_combo.findData(s.get('together', 'each'))
        if k >= 0:
            self.together_combo.setCurrentIndex(k)
        self.set_series_view(s.get('series_view', 'peak'))
        if hasattr(self, 'match_combo'):
            self.match_combo.setCurrentIndex(1 if s.get('match_by_position') else 0)
            self.transpose_check.setChecked(bool(s.get('series_transposed')))
            self.hide_empty_check.setChecked(bool(s.get('wide_hide_empty')))
            for k, cb in self.hide_value_checks.items():
                cb.setChecked(k in (s.get('wide_columns_off') or []))
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
            self._restore_list_selection(s)
            return
        self.series_results = [dict(r, r2=(np.nan if r.get('r2') is None else r['r2']))
                               for r in results]
        self._refresh_series_table()
        k = s.get('series_index', self.current_index)
        self.show_series_spectrum(k if 0 <= k < len(self.series) else 0)
        self._restore_list_selection(s)

    def _restore_list_selection(self, s):
        """The spectra selected in the list last time (e.g. All): selected
        again - the shown spectrum stays the one shown last time."""
        rows = [r for r in (s.get('list_selection') or []) if 0 <= r < len(self.series)]
        if len(rows) > 1:
            self._select_in_list(sorted(set(rows)), notify=True)

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
        name = (str(self.series[self.current_index].get('label', '')).rsplit(' : ', 1)[-1]
                if self.series else '')
        if self.view_mode != 'one':
            where = {'grid': "A click in a small plot adds a peak to that spectrum.",
                     'waterfall': "A click adds a peak to the spectrum clicked on."}
            text = (where.get(self.view_mode, f"A click adds a peak to {name} (the spectrum framed "
                                                 "in orange in the list).")
                    if self.interactive_add_cb.isChecked() else
                    "Add via Click is off: tick it to add peaks by clicking.")
            first = {'grid': "Grid: a click in a small plot adds a peak to its spectrum; it\n"
                             "becomes the shown one (orange frame).",
                     'waterfall': "Waterfall: a click adds a peak to the spectrum whose band you\n"
                                  "click in; it becomes the shown one (orange frame)."}
            self.click_hint.setToolTip(
                first.get(self.view_mode, f"Overlay: a click adds a peak to {name}, the shown\n"
                                          "spectrum (framed in orange in the list).")
                + "\nIts height is taken from that spectrum's data under the click.\n"
                "\u25c0 \u25b6 (Alt+Left / Alt+Right) choose the shown spectrum.")
        elif self.interactive_add_cb.isChecked():
            text = "A click on the plot adds a peak (Zoom or Pan switches this off)."
        else:
            text = "Add via Click is off: tick it to add peaks by clicking."
        self.click_hint.setText(text)

    def on_canvas_click(self, event):
        """Handle clicks on the canvas to add a new peak."""
        # This handler is only connected when the "Add via Click" checkbox is checked
        if event.button != 1 or str(getattr(self.toolbar, 'mode', '') or ''):
            return
        several = self.view_mode in ('overlay', 'waterfall', 'grid')
        if several:
            # several spectra shown together: the peak goes to the shown one
            # (orange frame in the list) - in Grid to the one of the small plot,
            # in Waterfall to the one whose band was clicked (it becomes the
            # shown one); its height from that spectrum's data under the click
            r = self._clicked_spectrum(event)
            if r is None:
                return
            if r != self.current_index:
                self.make_shown(r)
        elif self.view_mode != 'one' or event.inaxes != getattr(self, 'ax_main', None):
            return
        
        center, amplitude = event.xdata, event.ydata
        if several:
            x = np.asarray(self.x_roi, dtype=float)
            order = np.argsort(x)
            amplitude = float(np.interp(center, x[order], np.asarray(self.y_roi, float)[order]))
        # the peak's height is above the background (the clicked point minus
        # it) - unless "− background" is ticked: then the plot is already
        # drawn without it and the clicked height is the peak's height
        if several or not self._subtract_background():
            amplitude -= float(background_values(self._shown_background(), [center])[0])
        
        # The width: fixed (next to Add via Click), else from the band under
        # the click (its width at half height), else 1/20 of the x range
        width = self.initial_peak_width
        if self._click_width_fixed() and self.click_width_spin.value() > 0:
            width = float(self.click_width_spin.value())
        else:
            estimate = self.manager.estimate_width(self.x_roi, self.y_roi, center)
            if estimate:
                width = estimate
        
        # a colour no other peak of this spectrum has
        new_color = self._free_color(self.peaks)
        self.peak_color_index += 1
        
        # Add the new peak to our list of initial guesses
        self.peaks.append({'model': 'Gaussian', 'center': center, 'amplitude': amplitude, 'width': width, 'extra': width, 'color': new_color})
        self._order_by_centre(self.peaks)          # in its place by position
        self._peaks_changed()
        
        # Invalidate any previous fit
        self.fit_results = None
        
        # Enable the copy button
        self._update_copy_results_button()
        
        # Refresh UI
        self.update_peaks_table()
        self.update_plot()

    def _clicked_spectrum(self, event):
        """The spectrum (its row) a click in Overlay / Waterfall / Grid is
        for, None when outside the plots."""
        if event.inaxes is None:
            return None
        if self.view_mode == 'grid':
            return getattr(self, '_grid_axes', {}).get(event.inaxes)
        if event.inaxes is not getattr(self, '_series_ax', None):
            return None
        bands = getattr(self, '_bands', None) or []
        if self.view_mode != 'waterfall' or not bands or event.ydata is None:
            return self.current_index
        y = event.ydata
        # the band (lowest to highest point of the shifted spectrum) clicked
        # in, else the nearest one
        return min(bands, key=lambda b: 0.0 if b[1] <= y <= b[2]
                   else min(abs(y - b[1]), abs(y - b[2])))[0]

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
            if self.view_mode == 'one' and len(self.x_roi):
                # y: the range of the data, not of the drawn starting peaks
                self.ax_main.set_ylim(*(getattr(self, '_y_range', None) or self._y_limits()))
            self.canvas.draw()

    SORT_KEYS = {2: 'center', 3: 'height', 4: 'width'}

    def _sort_by_column(self, col):
        """A click on the heading Center, Height or Width: the peaks sorted by
        it, ascending; a second click on the same heading: descending."""
        if col not in self.SORT_KEYS:
            return
        ascending = not (self._sort_state == (col, True))
        self._sort_state = (col, ascending)
        self.sort_peaks(self.SORT_KEYS[col], ascending)

    def sort_peaks(self, key, ascending=True, rows=None):
        """Sort the peaks of every spectrum (default: all of the series,
        whatever is selected - only the order changes, so that Peak 1 is
        the same band in all spectra of Series results) by 'center',
        'height' or 'width' (the fitted values when fitted). A fit stays a
        fit: its results are sorted the same way."""
        from src.modules.data_analysis import peak_fitting_series as pfs
        for i in range(len(self.peaks)):
            self.update_peak_from_table(i)
        if rows is None:
            rows = list(range(len(self.series))) if len(self.series) > 1 \
                else [self.current_index]
        start_key = {'center': 'center', 'height': 'amplitude', 'width': 'width'}[key]
        for k in rows:
            if k == self.current_index:
                peaks = self.peaks
            else:
                peaks = (self.own_peaks[k] if self.own_peaks is not None else None) or []
            res = self.series_results[k] if self.series_results else None
            fitted = (res['peaks'] if res and res.get('ok') and res.get('peaks')
                      and len(res['peaks']) == len(peaks) else None)
            if k == self.current_index and fitted is None and self.fit_results \
                    and len(self.fit_results) == len(peaks):
                fitted = self.fit_results
            if len(peaks) < 2:
                continue

            def value(i):
                if fitted is not None:
                    par = fitted[i]['parameters']
                    name = pfs.WIDTH_KEY.get(fitted[i]['model'], 'sigma') if key == 'width' \
                        else key
                    return float(par.get(name, 0.0))
                return float(peaks[i].get(start_key) or 0.0)
            order = sorted(range(len(peaks)), key=value, reverse=not ascending)
            if order == list(range(len(peaks))):
                continue
            peaks[:] = [peaks[i] for i in order]
            if res and res.get('ok') and res.get('peaks') and len(res['peaks']) == len(order):
                res['peaks'] = [res['peaks'][i] for i in order]
            if k == self.current_index and self.fit_results \
                    and len(self.fit_results) == len(order):
                self.fit_results = [self.fit_results[i] for i in order]
        self.update_peaks_table(from_fit_results=bool(self.fit_results))
        self._refresh_series_table()
        if self.fit_results and self.view_mode == 'one':
            self.update_plot_with_fit_results()
        else:
            self.update_plot()

    @staticmethod
    def _order_by_centre(peaks):
        """Peaks added (Auto-Detect, Add via Click, Paste): the list in order
        of position, so a new peak is in its place, not last. Only the order
        changes (colours, fixed and linked values go with their peaks)."""
        try:
            peaks.sort(key=lambda p: float(p.get('center', 0.0)))
        except (TypeError, ValueError):
            pass

    def _free_color(self, peaks):
        """The first colour of the cycle that none of `peaks` has (a peak added
        after one was removed does not repeat a colour); all used: the next."""
        used = set()
        for p in peaks:
            try:
                used.add(_mpl_to_hex(p.get('color')).lower())
            except (ValueError, TypeError):
                pass
        for c in self.colors:
            try:
                if _mpl_to_hex(c).lower() not in used:
                    return c
            except (ValueError, TypeError):
                continue
        return self.colors[len(peaks) % len(self.colors)]

    def _detect_into(self, peaks, x, y):
        """Add the peaks found in (x, y) to the list `peaks` (not those already
        there: within half a width). Returns how many were added."""
        detected = self.manager.auto_detect_peaks(np.asarray(y, dtype=float),
                                                  np.asarray(x, dtype=float),
                                                  background=self.background_kind)
        centres = [p['center'] for p in peaks]
        added = 0
        for peak in detected:
            tolerance = abs(peak['width'] * 0.5)
            if any(abs(peak['center'] - c) < tolerance for c in centres):
                continue
            peak['color'] = self._free_color(peaks)
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
                    self._order_by_centre(target)
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
            self._order_by_centre(self.peaks)
            self._peaks_changed()
        if not added:
            QMessageBox.information(self, "Auto-Detect", "No new peaks were detected.")
            return
        self.fit_results = None # Invalidate previous fit
        self._update_copy_results_button()
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

    def _peaks_changed(self, rows=None, by_hand=False):
        """The peaks of these spectra (default: the shown one) were changed:
        their fit no longer belongs to them. A value changed or a peak removed
        in a fitted spectrum (by_hand): its results become these values, "set
        by hand" (no \u00b1, the R\u00b2 of these values); otherwise (peaks
        added, pasted, cleared) it is shown as not fitted yet."""
        if not self.series_results:
            return
        changed = False
        for r in ([self.current_index] if rows is None else rows):
            res = self.series_results[r]
            if by_hand and res and res.get('ok') and self.peaks_of(r):
                self.series_results[r] = self._hand_result(r, res)
                changed = True
            elif res and not res.get('pending'):
                self.series_results[r] = {'label': str(self.series[r].get('label', '')),
                                          'ok': False, 'peaks': None, 'r2': None,
                                          'pending': True}
                changed = True
        if changed:
            self._refresh_series_table()

    def _hand_result(self, r, before):
        """Spectrum r's values set by hand (its peaks as they are now) as a
        result, with the background of its fit (`before`)."""
        from src.modules.data_analysis import peak_fitting_series as pfs
        if r == self.current_index:
            self._apply_links()
        fitted = [{'model': p['model'],
                   'parameters': self.manager.get_peak_properties(
                       p['model'], self._params_list_from_peak_guess(p)),
                   'errors': {}} for p in self.peaks_of(r)]
        sp = self.series[r]
        return pfs.hand_result(str(sp.get('label', '')), fitted, sp['x_scale'], sp['y_scale'],
                               before.get('background'), self.manager)

    def is_set_by_hand(self, k=None):
        """True when spectrum k's (default: the shown one's) results are
        values set by hand, not a fit."""
        k = self.current_index if k is None else k
        res = self.series_results[k] if self.series_results else None
        return bool(res and res.get('ok') and res.get('manual'))

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
            self._order_by_centre(peaks)
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
        self._tidy_constraints()               # links to a removed peak go
        self._peaks_changed(by_hand=True)
        
        # Invalidate the fit
        self.fit_results = None
        # Disable copy button only if the list is now empty
        self._update_copy_results_button()
        
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
        self._update_copy_results_button()
        self.peak_color_index = 0 # Reset color index
        self.update_peaks_table()
        self.update_plot()

    def _place_tabs_help(self):
        """The "?" of the tabs just to the right of the last tab."""
        b = getattr(self, 'tabs_help', None)
        if b is None:
            return
        bar = self.left_tabs.tabBar()
        last = bar.tabRect(bar.count() - 1)
        right = bar.mapTo(self.left_tabs, last.topRight())
        b.move(right.x() + 6, right.y() + max(0, (last.height() - b.height()) // 2))
        b.show()
        b.raise_()

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        if (getattr(self, 'tabs_help', None) is not None and obj is self.left_tabs.tabBar()
                and event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show)):
            QTimer.singleShot(0, self._place_tabs_help)
        if (event.type() == QEvent.Resize and hasattr(self, 'peaks_table')
                and obj is self.peaks_table.viewport()):
            self._share_columns()
        return super().eventFilter(obj, event)

    def _column_moved(self, *_):
        if not self._setting_columns:
            self._columns_moved = True          # set by hand: kept so

    def _share_columns(self):
        """Center, Height, Width (and Extra) share the width of the table
        equally, Needed? as wide as its heading - until a column is moved by
        hand."""
        t = self.peaks_table
        if self._columns_moved or t.columnCount() < 7:
            return
        cols = [c for c in (2, 3, 4, 5) if not t.isColumnHidden(c)]
        needed = max(t.horizontalHeader().sectionSizeHint(6),
                     t.fontMetrics().horizontalAdvance('not fitted') + 14)
        free = t.viewport().width() - t.columnWidth(0) - t.columnWidth(1) - needed
        if free <= 0 or not cols:
            return
        self._setting_columns = True
        try:
            for c in cols:
                t.setColumnWidth(c, max(50, free // len(cols)))
        finally:
            self._setting_columns = False

    def _set_needed_cell(self, row, peak_fit):
        """The column Needed?: yes / probably / no from the fitted peak's
        \u0394BIC ('not fitted', grey, before a fit: start values)."""
        from src.modules.data_analysis.peak_fitting_manager import needed_text
        if peak_fit is None and len(self.series) > 1 and self.is_set_by_hand():
            text, tip = 'set by hand', ("Values set by hand (changed after the fit): no \u00b1.\n"
                                        "Fit Peaks to see whether this peak is needed.")
        elif peak_fit is None:
            text, tip = 'not fitted', ''
        else:
            n_removed = sum(1 for f in (self.fit_results or []) if f.get('remove'))
            text, tip = needed_text(peak_fit.get('delta_bic'), peak_fit.get('remove'),
                                    n_removed)
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setTextAlignment(int(Qt.AlignCenter))
        if text == 'no':
            item.setForeground(QColor('#B45F06'))
        elif text in ('not fitted', 'set by hand'):
            item.setForeground(QColor('#999999'))
        item.setToolTip(tip or "Not fitted: the values are start values.\n"
                               "After Fit Peaks it says whether this peak is needed.")
        self.peaks_table.setItem(row, 6, item)

    def _set_needed_cells(self):
        """The column Needed? again (after a value was changed by hand)."""
        t = self.peaks_table
        t.blockSignals(True)
        for row in range(min(t.rowCount(), len(self.peaks))):
            self._set_needed_cell(row, None)
        t.blockSignals(False)

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

    # ------------------------------------------------------------------
    # fixed and linked values (right-click on a value in the table)
    # ------------------------------------------------------------------
    def _tidy_constraints(self, peaks=None):
        """Every peak has an id (links refer to it); links to a peak that is
        gone, or a width / extra link to a peak of another shape, are dropped
        (in `peaks`, default: the shown spectrum's)."""
        from src.modules.data_analysis.peak_fitting_manager import new_peak_id, constraint_of
        peaks = self.peaks if peaks is None else peaks
        for p in peaks:
            if not p.get('id'):
                p['id'] = new_peak_id(peaks)
        by_id = {p['id']: p for p in peaks}
        for p in peaks:
            cons = dict(p.get('constraints') or {})
            for name in list(cons):
                spec = constraint_of(p, name)
                if spec is None:
                    cons.pop(name)
                elif spec['kind'] == 'link':
                    t = by_id.get(spec.get('peak'))
                    if t is None or t is p or (name in ('width', 'extra')
                                               and t['model'] != p['model']):
                        cons.pop(name)
                if name == 'extra' and name in cons and p['model'] not in ('Voigt',
                                                                           'Pseudo-Voigt'):
                    cons.pop(name)
            if cons or p.get('constraints'):
                p['constraints'] = cons

    def _apply_links(self):
        """The linked start values follow their peak (as the fit does)."""
        from src.modules.data_analysis.peak_fitting_manager import constraint_of
        by_id = {p.get('id'): p for p in self.peaks}
        key = {'center': 'center', 'height': 'amplitude', 'width': 'width', 'extra': 'extra'}
        for _ in range(len(self.peaks)):               # chains: peak 3 = peak 2 = peak 1
            for p in self.peaks:
                for name in ('center', 'height', 'width', 'extra'):
                    spec = constraint_of(p, name)
                    if spec is None or spec['kind'] != 'link':
                        continue
                    t = by_id.get(spec['peak'])
                    if t is None or t.get(key[name]) is None:
                        continue
                    v = float(spec.get('value', 0.0 if name == 'center' else 1.0))
                    tv = float(t[key[name]])
                    p[key[name]] = tv + v if name == 'center' else (tv * v if name == 'height'
                                                                    else tv)

    def _show_linked_values(self):
        """The linked values in the table as they are now in the peaks."""
        from src.modules.data_analysis.peak_fitting_manager import constraint_of
        t = self.peaks_table
        cells = (('center', 2, 'center'), ('height', 3, 'amplitude'), ('width', 4, 'width'),
                 ('extra', 5, 'extra'))
        t.blockSignals(True)
        try:
            for row, p in enumerate(self.peaks[:t.rowCount()]):
                for name, col, key in cells:
                    spec = constraint_of(p, name)
                    item = t.item(row, col)
                    if (spec is None or spec['kind'] != 'link' or item is None
                            or p.get(key) is None):
                        continue
                    item.setText(f"{float(p[key]):.4f}")
        finally:
            t.blockSignals(False)

    def _constraint_text(self, peak, name):
        """('fixed' / '=P1' / 'P1+12.5' / 'P1×0.5', tooltip) or (None, None)."""
        from src.modules.data_analysis.peak_fitting_manager import constraint_of
        spec = constraint_of(peak, name)
        if spec is None:
            return None, None
        label = {'center': 'Center', 'height': 'Height', 'width': 'Width', 'extra': 'Extra'}[name]
        if spec['kind'] == 'fixed':
            return 'fixed', (f"{label} is fixed: kept at this value, not fitted (no \u00b1).\n"
                             "Double-click to change the value;\n"
                             "right-click > Fitted (free) to fit it again.")
        k = next((i for i, p in enumerate(self.peaks) if p.get('id') == spec['peak']), None)
        if k is None:
            return None, None
        v = float(spec.get('value', 0.0 if name == 'center' else 1.0))
        if name == 'center':
            sign = '+' if v >= 0 else '\u2212'
            tag = f"P{k + 1}{sign}{abs(v):.4g}"
            tip = f"Linked: this peak's centre is always {v:+.4g} from peak {k + 1}'s."
        elif name == 'height':
            tag = f"P{k + 1}\u00d7{v:.3g}"
            tip = f"Linked: this peak's height is always {v:.3g} \u00d7 the height of peak {k + 1}."
        else:
            tag = f"=P{k + 1}"
            tip = f"Linked: the same {label.lower()} as peak {k + 1}."
        return tag, tip + "\nRight-click > Fitted (free) to free it."

    def _constraints_note(self, row):
        """'Center fixed; Width = P1' - for Copy Results."""
        if row >= len(self.peaks):
            return ''
        parts = []
        for name in ('center', 'height', 'width', 'extra'):
            tag, _ = self._constraint_text(self.peaks[row], name)
            if tag:
                parts.append(f"{name.capitalize()} {tag}")
        return '; '.join(parts)

    def _show_constraints(self, row):
        """A fixed value grey, a linked one light blue, each with its tag;
        a linked value cannot be typed (it follows its peak)."""
        if row >= len(self.peaks):
            return
        peak = self.peaks[row]
        for col, name in COLUMN_PARAM.items():
            item = self.peaks_table.item(row, col)
            if item is None or not (item.flags() & Qt.ItemIsEnabled):
                continue
            tag, tip = self._constraint_text(peak, name)
            item.setData(TAG_ROLE, tag)
            if tag is None:
                continue
            item.setBackground(QColor(FIXED_COLOUR if tag == 'fixed' else LINKED_COLOUR))
            item.setToolTip(tip)
            if tag != 'fixed':
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)

    def set_constraint(self, rows, name, spec):
        """Fix (spec {'kind': 'fixed'}), link ({'kind': 'link', 'peak': id})
        or free (None) the value `name` of the peaks `rows`. The values shown
        in the table (after a fit the fitted ones) become the start values;
        a link keeps the present distance (centre) or ratio (height)."""
        from src.modules.data_analysis.peak_fitting_manager import follows
        for i in range(self.peaks_table.rowCount()):
            self.update_peak_from_table(i)
        self._tidy_constraints()
        by_id = {p['id']: p for p in self.peaks}
        for r in rows:
            if not 0 <= r < len(self.peaks):
                continue
            p = self.peaks[r]
            cons = dict(p.get('constraints') or {})
            if spec is None:
                cons.pop(name, None)
            elif spec['kind'] == 'fixed':
                cons[name] = {'kind': 'fixed'}
            else:
                t = by_id.get(spec['peak'])
                if t is None or t is p:
                    continue
                if follows(self.peaks, r, name, self.peaks.index(t)):
                    continue                          # t follows p: a circle
                if name == 'center':
                    value = float(p['center']) - float(t['center'])
                elif name == 'height':
                    value = (float(p['amplitude']) / float(t['amplitude'])
                             if float(t['amplitude']) != 0 else 1.0)
                else:
                    value = 1.0
                cons[name] = {'kind': 'link', 'peak': t['id'], 'value': value}
            p['constraints'] = cons
        self.fit_results = None
        self._peaks_changed()
        self._update_copy_results_button()
        self.update_peaks_table()
        self.update_plot()

    def _peaks_table_menu(self, pos):
        menu = self.peaks_constraint_menu(self.peaks_table.indexAt(pos))
        if menu is not None:
            menu.exec_(self.peaks_table.viewport().mapToGlobal(pos))

    def peaks_constraint_menu(self, index):
        """The right-click menu of a value: Fixed, Fitted, Link to peak ...,
        for Width also 'The same width for all peaks'. With several rows
        selected (the clicked one among them) it acts on all of them."""
        from PyQt5.QtWidgets import QMenu
        from src.modules.data_analysis.peak_fitting_manager import constraint_of
        row, col = index.row(), index.column()
        name = COLUMN_PARAM.get(col)
        if name is None or not 0 <= row < len(self.peaks):
            return None
        peak = self.peaks[row]
        if name == 'extra' and peak['model'] not in ('Voigt', 'Pseudo-Voigt'):
            return None
        selected = sorted({i.row() for i in self.peaks_table.selectionModel().selectedRows()})
        rows = selected if row in selected and len(selected) > 1 else [row]
        label = {'center': 'Center', 'height': 'Height', 'width': 'Width', 'extra': 'Extra'}[name]
        whose = f"peak {row + 1}" if len(rows) == 1 else f"the {len(rows)} selected peaks"
        menu = QMenu(self)
        title = menu.addAction(f"{label} of {whose}")
        title.setEnabled(False)
        spec = constraint_of(peak, name) if len(rows) == 1 else None
        fixed = menu.addAction("Fixed (kept at this value, not fitted)")
        fixed.setCheckable(True)
        fixed.setChecked(spec is not None and spec['kind'] == 'fixed')
        fixed.triggered.connect(lambda on: self.set_constraint(
            rows, name, {'kind': 'fixed'} if on else None))
        free = menu.addAction("Fitted (free)")
        free.setCheckable(True)
        free.setChecked(spec is None and all(constraint_of(self.peaks[r], name) is None
                                             for r in rows))
        free.triggered.connect(lambda *_: self.set_constraint(rows, name, None))
        targets = [k for k, p in enumerate(self.peaks) if k not in rows
                   and (name in ('center', 'height') or p['model'] == peak['model'])]
        link = menu.addMenu({'center': "Keep the distance to peak",
                             'height': "Keep the height ratio to peak",
                             'width': "The same width as peak",
                             'extra': "The same extra value as peak"}[name])
        link.setEnabled(bool(targets))
        from src.modules.data_analysis.peak_fitting_manager import follows
        for k in targets:
            t = self.peaks[k]
            if any(follows(self.peaks, r, name, k) for r in rows):
                # peak k already follows this one: a link back would be a circle
                a = link.addAction(f"Peak {k + 1} (not possible: it follows "
                                   + ("this one)" if len(rows) == 1 else "one of these)"))
                a.setEnabled(False)
                continue
            if name == 'center':
                text = f"Peak {k + 1} (now {float(peak['center']) - float(t['center']):+.4g})"
            elif name == 'height':
                ratio = (float(peak['amplitude']) / float(t['amplitude'])
                         if float(t['amplitude']) != 0 else 1.0)
                text = f"Peak {k + 1} (now \u00d7 {ratio:.3g})"
            else:
                text = f"Peak {k + 1}"
            a = link.addAction(text)
            a.setCheckable(True)
            a.setChecked(spec is not None and spec['kind'] == 'link'
                         and spec.get('peak') == t.get('id'))
            a.triggered.connect(lambda *_, t_id=t.get('id'): self.set_constraint(
                rows, name, {'kind': 'link', 'peak': t_id}))
        if name == 'width':
            same = [k for k, p in enumerate(self.peaks) if k != row
                    and p['model'] == peak['model']]
            a = menu.addAction(f"The same width for all {peak['model']} peaks (as peak {row + 1})")
            a.setEnabled(bool(same))
            a.triggered.connect(lambda *_: (self.set_constraint([row], name, None),
                                            self.set_constraint(same, name,
                                                                {'kind': 'link',
                                                                 'peak': self.peaks[row]['id']})))
        return menu

    def _clear_errors(self):
        t = self.peaks_table
        t.blockSignals(True)
        for r in range(t.rowCount()):
            for c in range(2, t.columnCount()):
                item = t.item(r, c)
                if item is not None and item.data(ERROR_ROLE):
                    item.setData(ERROR_ROLE, None)
                    item.setToolTip('')
        t.blockSignals(False)

    def _set_errors(self, row, peak_fit, cells):
        """The fitted values' uncertainties in the row (shown as '\u00b1 ...')."""
        errors = peak_fit.get('errors')
        if errors is None:                   # a fit kept from an older version
            return
        from src.modules.data_analysis.peak_fitting_manager import format_with_error
        from src.modules.data_analysis.peak_fitting_manager import constraint_of
        peak = self.peaks[row] if row < len(self.peaks) else {}
        for col, key in cells:
            item = self.peaks_table.item(row, col)
            if item is None or key is None:
                continue
            spec = constraint_of(peak, COLUMN_PARAM[col])
            if spec is not None and spec['kind'] == 'fixed':
                continue                         # not fitted: no uncertainty
            err = errors.get(key)
            try:
                value = float(item.text())
            except ValueError:
                continue
            k = self._sigmas()
            shown = format_with_error(value, err * k if err is not None else None)
            item.setData(ERROR_ROLE, shown)
            item.setToolTip(
                f"{shown}\n" + ("\u00b1 = the uncertainty of the fitted value (its standard error, 1 \u03c3):\n"
                 "measured again, the value would scatter by about this much.\n"
                 if k == 1 else
                 f"\u00b1 = {k} \u00d7 the standard error of the fitted value ({k} \u03c3,\n"
                 "see \u00b1 shown as, in the box Fitting).\n")
                + "Double-click to see or edit the full number (the \u00b1 then disappear)."
                if err is not None else
                "n/a: the fit could not tell how uncertain this value is -\n"
                "e.g. the value is at its limit, or the data do not determine it\n"
                "(two peaks at the same place).")

    def update_peaks_table(self, from_fit_results=False):
        """Populates the table either from initial guesses (self.peaks) or fit results (self.fit_results)."""
        self._tidy_constraints()
        if not (from_fit_results and self.fit_results):
            self._apply_links()
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
                _ignore_wheel(model_combo)
                self.peaks_table.setCellWidget(i, 1, model_combo)
                
                # Parameters, each with its uncertainty (drawn by _ErrorDelegate)
                self.peaks_table.setItem(i, 2, QTableWidgetItem(f"{params['center']:.4f}"))
                self.peaks_table.setItem(i, 3, QTableWidgetItem(f"{params['height']:.4f}"))
                self.peaks_table.setItem(i, 4, QTableWidgetItem(f"{params.get(width_key, 0):.4f}"))
                self._set_extra_cell(i, extra_key, params.get(extra_key) if extra_key else None)
                self._set_errors(i, peak_fit, [(2, 'center'), (3, 'height'), (4, width_key),
                                               (5, extra_key)])
                self._show_constraints(i)
                self._set_needed_cell(i, peak_fit)
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
                _ignore_wheel(model_combo)
                self.peaks_table.setCellWidget(i, 1, model_combo)
                
                # Parameters
                self.peaks_table.setItem(i, 2, QTableWidgetItem(f"{peak['center']:.4f}"))
                self.peaks_table.setItem(i, 3, QTableWidgetItem(f"{peak['amplitude']:.4f}"))
                self.peaks_table.setItem(i, 4, QTableWidgetItem(f"{abs(peak['width']):.4f}"))
                extra_key = {'Voigt': 'gamma', 'Pseudo-Voigt': 'eta'}.get(peak['model'])
                self._set_extra_cell(i, extra_key, peak.get('extra'))
                self._show_constraints(i)
                self._set_needed_cell(i, None)
        
        self.peaks_table.blockSignals(False)
        # Extra only when a peak has one (Voigt, Pseudo-Voigt): the other
        # values (with their \u00b1 and [fixed] / [= P1]) get its room
        models = [p['model'] for p in (self.fit_results if from_fit_results and self.fit_results
                                       else self.peaks)]
        self.peaks_table.setColumnHidden(5, not any(m in ('Voigt', 'Pseudo-Voigt')
                                                    for m in models))
        self._share_columns()
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
        self._peaks_changed(by_hand=True)
        self.update_peaks_table()
        self.update_plot()

    def on_table_cell_changed(self, row=-1, col=-1):
        """Fired when user edits the table. This invalidates the 'fit'.
        A value that is not a number (e.g. pasted text, an empty cell): the
        table shows the values as they were - nothing changes."""
        if col in COLUMN_PARAM:
            item = self.peaks_table.item(row, col)
            try:
                ok = item is None or np.isfinite(float(item.text()))
            except ValueError:
                ok = False
            if not ok:
                self.update_peaks_table(from_fit_results=bool(self.fit_results))
                return
        for i in range(self.peaks_table.rowCount()): 
            self.update_peak_from_table(i)
        # a linked value follows at once (peak 2 = peak 1 + 2935: peak 1 typed
        # 410 -> peak 2 3345)
        self._apply_links()
        self._show_linked_values()
        self.fit_results = None
        self._clear_errors()                # start values now: no uncertainties
        self._peaks_changed(by_hand=True)
        self._set_needed_cells()
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
        fitted_results, y_fit_total = self.manager.fit_peaks(
            self.x_roi, self.y_roi, self.peaks, amplitude_constraint=constraint,
            background=self.background_kind)
        
        if fitted_results is None:
            QMessageBox.warning(self, "Fit Failed", "The fitting algorithm could not converge.")
            self._update_copy_results_button()
            return
            
        self.fit_results = fitted_results
        from src.modules.data_analysis import peak_fitting_series as pfs
        self.fit_background = pfs.plain_background(self.manager.last_background)
        # is each peak needed? (the fit without it, compared by BIC)
        self.manager.add_peak_bic(self.x_roi, self.y_roi, fitted_results, self.peaks,
                                  constraint, self.background_kind)
        self._update_copy_results_button()
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
                'r2': r2, 'background': self.fit_background}
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
        # how the results are shown: by peak (one peak, a row per spectrum),
        # by spectrum (each spectrum with its peaks, collapsible) or all in one
        # wide table (a row per spectrum) - always the spectra selected in the list
        show = QHBoxLayout()
        show.addWidget(QLabel("Show:"))
        self.series_view_group = QButtonGroup(page)
        self.series_view_buttons = {}
        for key, text, tip in (
                ('peak', "By peak", "One peak at a time (\u25c0 \u25b6): a row per spectrum - "
                 "follow a band through the series"),
                ('spectrum', "By spectrum", "Each spectrum with its peaks (\u25b8 opens, \u25be "
                 "closes), the same columns as the table of peaks"),
                ('wide', "All in one table", "A row per spectrum with all its peaks side by side "
                 "(as Export and the Data table get them)")):
            b = QRadioButton(text)
            b.setToolTip(tip)
            self.series_view_group.addButton(b)
            self.series_view_buttons[key] = b
            show.addWidget(b)
        show.addSpacing(16)
        self.transpose_check = QCheckBox("Transposed")
        self.transpose_check.setToolTip(
            "Rows and columns swapped: one column per spectrum, one row per value\n"
            "(By peak and All in one table; By spectrum is a list of each spectrum's peaks).")
        self.transpose_check.toggled.connect(lambda *_: self._refresh_series_table())
        show.addWidget(self.transpose_check)
        show.addStretch(1)
        v.addLayout(show)
        # Peak 1, 2, ...: the rows of each spectrum's table, or matched by
        # position across the spectra (the same band = the same number)
        numbering = QHBoxLayout()
        numbering.addWidget(QLabel("Peak numbers:"))
        self.match_combo = QComboBox()
        self.match_combo.addItem("as in each table of peaks", False)
        self.match_combo.addItem("matched by position", True)
        self.match_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.match_combo.setToolTip(
            "How Peak 1, Peak 2, ... of the spectra are put side by side:\n"
            "As in each table of peaks (default): Peak 1 is the first row of each\n"
            "spectrum's table - right when all spectra have the same peaks.\n"
            "Matched by position: the peaks of all spectra are matched by where they\n"
            "are - the same band gets the same number in every spectrum, also when a\n"
            "spectrum has a peak more or less (a band split into two, a peak missing).\n"
            "A spectrum without a peak in a band: an empty row.")
        self.match_combo.currentIndexChanged.connect(lambda *_: self._match_changed())
        numbering.addWidget(self.match_combo)
        numbering.addWidget(self._quick_help_button('matching'))
        numbering.addStretch(1)
        v.addLayout(numbering)
        # Hide: (all three views) the spectra not fitted yet; values not needed
        self.hide_options = QWidget()
        wo = QHBoxLayout(self.hide_options)
        wo.setContentsMargins(0, 0, 0, 0)
        wo.addWidget(QLabel("Hide:"))
        self.hide_empty_check = QCheckBox("Spectra without values")
        self.hide_empty_check.setToolTip(
            "Spectra without values: hide the spectra not fitted yet\n"
            "(or whose fit failed), so that the fitted ones are together.\n"
            "By peak, By spectrum and All in one table; Copy copies what is shown.")
        self.hide_empty_check.toggled.connect(lambda *_: self._hide_empty_changed())
        wo.addWidget(self.hide_empty_check)
        wo.addSpacing(16)
        self.hide_value_checks = {}
        for key, text, tip in (('position', "Position", "the position (Center) of each peak"),
                               ('FWHM', "FWHM", "the full width at half height of each peak"),
                               ('height', "Height", "the height of each peak"),
                               ('area', "Area", "the area of each peak"),
                               ('\u00b1', "\u00b1", "the uncertainty after each value"),
                               ('R\u00b2', "R\u00b2", "R\u00b2 of each spectrum's fit")):
            cb = QCheckBox(text)
            cb.setToolTip(f"{text}: hide {tip}\n(in all three views and in Copy;\n"
                          "Export and the Data table always get all).")
            cb.toggled.connect(lambda *_: self._refresh_series_table())
            self.hide_value_checks[key] = cb
            wo.addWidget(cb)
        wo.addStretch(1)
        v.addWidget(self.hide_options)
        self.series_view_buttons['peak'].setChecked(True)
        self.series_view_group.buttonToggled.connect(
            lambda b, on: on and self._series_view_changed())
        self.series_peak = 0                       # the peak shown By peak (0-based)
        self.series_stack = QStackedWidget()
        by_peak = QWidget()
        bp = QVBoxLayout(by_peak)
        bp.setContentsMargins(0, 0, 0, 0)
        nav = QHBoxLayout()
        nav.addWidget(QLabel("Peak"))
        self.series_peak_prev = QToolButton()
        self.series_peak_prev.setText("\u25c0")
        self.series_peak_prev.setToolTip("The previous peak")
        self.series_peak_prev.clicked.connect(lambda: self._show_series_peak(self.series_peak - 1))
        self.series_peak_next = QToolButton()
        self.series_peak_next.setText("\u25b6")
        self.series_peak_next.setToolTip("The next peak")
        self.series_peak_next.clicked.connect(lambda: self._show_series_peak(self.series_peak + 1))
        self.series_peak_label = QLabel()
        nav.addWidget(self.series_peak_prev)
        nav.addWidget(self.series_peak_label)
        nav.addWidget(self.series_peak_next)
        nav.addStretch(1)
        bp.addLayout(nav)
        self.by_peak_table = QTableWidget(0, 0)
        self.by_peak_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.by_peak_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.by_peak_table.verticalHeader().setVisible(False)
        bp.addWidget(self.by_peak_table, 1)
        # removing peaks here: Delete or right-click (they go from the spectra)

        self.series_stack.addWidget(by_peak)
        self.by_spectrum_tree = QTreeWidget()
        self.by_spectrum_tree.setAlternatingRowColors(True)
        self.by_spectrum_tree.setUniformRowHeights(True)
        self._closed_in_tree = set()               # spectra whose peaks are folded up
        self.by_spectrum_tree.itemCollapsed.connect(
            lambda it: self._closed_in_tree.add(it.data(0, Qt.UserRole)))
        self.by_spectrum_tree.itemExpanded.connect(
            lambda it: self._closed_in_tree.discard(it.data(0, Qt.UserRole)))
        self.series_stack.addWidget(self.by_spectrum_tree)
        self.by_spectrum_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for view in (self.by_peak_table, self.by_spectrum_tree):
            view.setContextMenuPolicy(Qt.CustomContextMenu)
            view.customContextMenuRequested.connect(
                lambda pos, v=view: self._series_remove_menu(v, pos))
            QShortcut(QKeySequence.Delete, view, context=Qt.WidgetShortcut,
                      activated=lambda v=view: self.remove_series_peaks(self._series_peaks_of(v)))
        self.series_table = QTableWidget(0, 0)
        self.series_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.series_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.series_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.series_table.itemSelectionChanged.connect(self._series_selection_changed)
        self.series_stack.addWidget(self.series_table)
        v.addWidget(self.series_stack, 1)
        QShortcut(QKeySequence.Copy, self.series_table, activated=self.copy_series)
        row = QHBoxLayout()
        self.series_copy_button = QPushButton("Copy")
        self.series_copy_button.setToolTip(
            "Copy the selected rows of this table (one row per spectrum) - or, with none "
            "selected, those of all fitted spectra - ready to paste into Excel.")
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
        # copying what is shown: the button next to Fit Peaks ("Copy results")
        self.series_copy_button.setVisible(False)
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
        self.prev_button.clicked.connect(lambda: self.step_shown(-1))
        self.next_button = QToolButton()
        self.next_button.setText("▶")
        self.next_button.setFixedSize(32, 26)
        self.next_button.setStyleSheet("QToolButton { font-size: 13pt; }")
        self.next_button.clicked.connect(lambda: self.step_shown(+1))
        # Alt+Left / Alt+Right (and Alt+Up / Alt+Down, as in the list) in the
        # whole window, wherever the focus is: as the arrows
        self._step_shortcuts = []
        for keys, d in (("Alt+Left", -1), ("Alt+Right", +1), ("Alt+Up", -1), ("Alt+Down", +1)):
            sc = QShortcut(QKeySequence(keys), self, activated=lambda d=d: self.step_shown(d))
            self._step_shortcuts.append(sc)
        h.addWidget(self.prev_button)
        h.addWidget(self.next_button)
        self.current_label = QLabel()
        self.current_label.setToolTip("The spectrum whose peaks are in the tab Peaks; Fit Peaks "
                                      "fits this one")
        h.addWidget(self.current_label)
        # the "?" of the list of spectra (below): what its marks mean
        h.addWidget(self._quick_help_button('spectra-list'))
        h.addStretch(1)
        h.addSpacing(12)
        h.addWidget(QLabel("Several selected:"))
        self.view_combo = QComboBox()
        for key, text in self.SERIES_VIEWS:
            self.view_combo.addItem(text, key)
        self.view_combo.setToolTip(
            "How several spectra selected in the list are shown:\n"
            "Overlay: in one plot.\n"
            "Waterfall: each shifted up.\n"
            f"Grid: one small plot each (at most {self.GRID_MAX}).\n"
            "Data thin, fits thick (once fitted).")
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
        self.list_delegate = _SelectedTextDelegate(self.spectra_list)
        self.spectra_list.setItemDelegate(self.list_delegate)
        self.spectra_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # (what the list and its marks mean: the orange "?" above it)
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

    def _list_text(self, sp, res):
        return self._list_mark(sp, res)[0] + str(sp.get('label', '')).rsplit(' : ', 1)[-1]

    def _list_mark(self, sp, res):
        """(the mark before a spectrum's name in the list, its tooltip):
        \u2713 fitted, \u26a0 a poor fit (R\u00b2 below 0.9 and the residual clearly
        larger than the noise - pfs.poor_fit), \u270e set by hand, \u2717 failed."""
        from src.modules.data_analysis import peak_fitting_series as pfs
        if not res or res.get('pending'):
            return '', ''
        if res.get('ok') and res.get('manual'):
            return '\u270e ', "Values set by hand after the fit (no \u00b1)."
        if not res.get('ok'):
            return '\u2717 ', "The fit failed."
        poor, r2, ratio = pfs.poor_fit(res, sp.get('x_scale', []), sp.get('y_scale', []),
                                       self.manager)
        r2_text = f"R\u00b2 {r2:.3f}" if r2 is not None and np.isfinite(r2) else "R\u00b2 -"
        if poor:
            return '\u26a0 ', (f"A poor fit: {r2_text}, and the residual is "
                               + (f"{ratio:.1f} \u00d7 the noise" if ratio else "large")
                               + " - something is not described\n"
                               "(a missing peak, a wrong background). Check the residual.")
        if ratio is not None:
            return '\u2713 ', (f"Fitted: {r2_text} - low because the data are noisy; the "
                               f"residual is only\n{ratio:.1f} \u00d7 the noise, so the fit "
                               "describes everything but the noise.")
        return '\u2713 ', f"Fitted: {r2_text}."

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
        self._refresh_series_views()
        t = self.series_table
        t.blockSignals(True)
        t.clearSelection()
        model = t.selectionModel()
        across = self.transposed() and self.series_view() == 'wide'
        for r in rows:
            if across and r < t.columnCount():
                model.select(t.model().index(0, r),
                             QItemSelectionModel.Select | QItemSelectionModel.Columns)
            elif not across and r < t.rowCount():
                model.select(t.model().index(r, 0),
                             QItemSelectionModel.Select | QItemSelectionModel.Rows)
        t.blockSignals(False)
        t.viewport().update()

    def _update_nav(self, k):
        if hasattr(self, 'list_delegate'):
            self.list_delegate.shown_row = k          # the orange frame
            self.spectra_list.viewport().update()
        if hasattr(self, 'prev_button'):
            prev, nxt = self._neighbours(k)
            self.prev_button.setEnabled(prev is not None)
            self.next_button.setEnabled(nxt is not None)
            if len(self.selected_spectra()) > 1:
                self.prev_button.setToolTip("The previous of the selected spectra becomes the shown "
                                            "one\n(orange frame); all stay selected.  Alt+Left")
                self.next_button.setToolTip("The next of the selected spectra becomes the shown "
                                            "one\n(orange frame); all stay selected.  Alt+Right")
            else:
                self.prev_button.setToolTip("The previous spectrum of the series (only it is "
                                            "shown).  Alt+Left")
                self.next_button.setToolTip("The next spectrum of the series (only it is "
                                            "shown).  Alt+Right")
            name = str(self.series[k].get('label', '')).rsplit(' : ', 1)[-1]
            self.current_label.setText("<b>" + self._shorten(name) + "</b>")
            self.current_label.setToolTip(
                f"{self.series[k].get('label', '')}\nThe shown spectrum: its peaks are in the tab "
                "Peaks.")
        if hasattr(self, 'view_combo'):
            self.view_combo.setEnabled(len(self.selected_spectra()) > 1)
        self._update_fit_button()

    def _neighbours(self, k):
        """(previous, next) for the arrows: with several selected, among them;
        else in the whole series. None at an end."""
        sel = self.selected_spectra()
        rows = sel if len(sel) > 1 else range(len(self.series))
        before = [r for r in rows if r < k]
        after = [r for r in rows if r > k]
        return (before[-1] if before else None), (after[0] if after else None)

    def step_shown(self, d):
        """The arrows (Alt+Left / Alt+Right): one spectrum selected - the
        previous or next spectrum alone; several - the orange frame moves to
        the previous or next selected one, all stay selected and shown."""
        if len(self.series) < 2:
            return
        prev, nxt = self._neighbours(self.current_index)
        k = prev if d < 0 else nxt
        if k is None:
            return
        if len(self.selected_spectra()) > 1:
            self.make_shown(k)
        else:
            self.show_series_spectrum(k)

    def make_shown(self, k):
        """Spectrum k becomes the shown one (orange frame; its peaks in the
        table) while the selection stays - several spectra stay shown."""
        if k == self.current_index:
            return
        self._set_current(k)
        if hasattr(self, 'spectra_list'):
            self.spectra_list.scrollToItem(self.spectra_list.item(k))
        self._update_plot_options()
        self.update_plot()

    # ---- Series results shown By peak / By spectrum / All in one table ----
    def series_view(self):
        if not hasattr(self, 'series_view_buttons'):
            return 'wide'
        return next(k for k, b in self.series_view_buttons.items() if b.isChecked())

    def set_series_view(self, key):
        if hasattr(self, 'series_view_buttons') and key in self.series_view_buttons:
            self.series_view_buttons[key].setChecked(True)

    def _series_view_changed(self):
        view = self.series_view()
        self.series_stack.setCurrentIndex(['peak', 'spectrum', 'wide'].index(view))
        self.transpose_check.setEnabled(view != 'spectrum')
        self._refresh_series_table() if view == 'wide' else self._refresh_series_views()
        self._update_copy_results_button()

    def transposed(self):
        """True: Series results (By peak, All in one table) with one column per
        spectrum, one row per value."""
        check = getattr(self, 'transpose_check', None)
        return bool(check is not None and check.isChecked() and self.series_view() != 'spectrum')

    _VALUE_KEYS = {'position': 'position', 'Center': 'position', 'FWHM': 'FWHM',
                   'height': 'height', 'Height': 'height', 'area': 'area', 'Area': 'area'}

    def _value_shown(self, name):
        """Is this column (By peak, By spectrum: Center, Center \u00b1, ...; All
        in one table: Peak 1 position, ...) shown - not hidden by Hide:
        Position, FWHM, Height, Area, \u00b1, R\u00b2? The spectrum's name always."""
        checks = getattr(self, 'hide_value_checks', None)
        name = str(name)
        if not checks or name in ('Spectrum', 'Peak'):
            return True
        if name.startswith('R\u00b2'):
            return not checks['R\u00b2'].isChecked()
        if ' \u00b1' in name and checks['\u00b1'].isChecked():
            return False
        base = name.split(' \u00b1')[0]
        if base.startswith('Peak '):
            base = base.split(' ', 2)[-1]
        key = self._VALUE_KEYS.get(base)
        return key is None or not checks[key].isChecked()

    def _hide_empty_changed(self):
        self._refresh_series_table()
        self._update_copy_results_button()

    def _hidden_spectrum(self, k):
        """Hide spectra without values (all three views): spectrum k hidden -
        not fitted yet, or its fit failed."""
        check = getattr(self, 'hide_empty_check', None)
        res = (self.series_results or [None])[k] if self.series_results else None
        return bool(check is not None and check.isChecked() and not (res or {}).get('ok'))

    @staticmethod
    def _transpose_text(columns, data):
        """(columns, rows) with rows and columns swapped: the first column's
        values become the headings."""
        new_columns = [str(columns[0])] + [str(row[0]) for row in data]
        new_rows = [[columns[c]] + [row[c] for row in data] for c in range(1, len(columns))]
        return new_columns, new_rows

    def matched_by_position(self):
        """True: Series results match the peaks by position (Peak numbers)."""
        combo = getattr(self, 'match_combo', None)
        return bool(combo is not None and combo.currentData())

    def _view_results(self):
        """The series results as Series results show them: as they are, or
        with the peaks matched by position (pfs.match_by_position)."""
        from src.modules.data_analysis import peak_fitting_series as pfs
        if not self.series_results or not self.matched_by_position():
            return self.series_results
        return pfs.match_by_position(self.series_results)[1]

    def _original_index(self, k, j):
        """The row in spectrum k's table of the peak shown as Peak j+1 in
        Series results (None: the spectrum has no peak there)."""
        if not self.matched_by_position():
            return j
        res = (self._view_results() or [])[k] if self.series_results else None
        peaks = (res or {}).get('peaks') or []
        p = peaks[j] if res and res.get('ok') and 0 <= j < len(peaks) else None
        return None if p is None else p.get('_index')

    def _match_changed(self):
        self._refresh_series_table()
        self._update_copy_results_button()

    def _series_n_peaks(self):
        return max([0] + [len(r.get('peaks') or []) for r in (self._view_results() or [])
                          if r.get('ok')])

    def _series_view_rows(self):
        """The spectra in the views: those selected in the list (without
        those hidden by Hide spectra without values)."""
        rows = self.selected_spectra() or [self.current_index]
        return [k for k in rows if not self._hidden_spectrum(k)]

    def _show_series_peak(self, j):
        n = self._series_n_peaks()
        self.series_peak = max(0, min(j, n - 1)) if n else 0
        self._refresh_series_views()
        self._update_copy_results_button()

    @staticmethod
    def _header_text(name):
        """A '... \u00b1' column (the uncertainty of the value before it) is
        headed just '\u00b1' (or '\u00b12\u03c3') in the tables of the window -
        short; copied and exported it keeps its full name ('Center \u00b1')."""
        name = str(name)
        return name[name.rindex(' \u00b1') + 1:] if ' \u00b1' in name else name

    @staticmethod
    def _header_tip(name):
        name = str(name)
        if ' \u00b1' not in name:
            return ''
        cut = name.rindex(' \u00b1')
        k = name[cut + 2:].rstrip('\u03c3') or '1'
        return (f"\u00b1 of {name[:cut]}: its uncertainty from the fit\n"
                f"({k} \u00d7 the standard error, {k} \u03c3)")

    def _set_headers(self, table, columns):
        table.setHorizontalHeaderLabels([self._header_text(c) for c in columns])
        for c, name in enumerate(columns):
            tip = self._header_tip(name)
            if tip:
                table.horizontalHeaderItem(c).setToolTip(tip)

    @staticmethod
    def _cell(v):
        item = QTableWidgetItem()
        if isinstance(v, float) and np.isfinite(v):
            item.setData(Qt.DisplayRole, float(f'{v:.6g}'))
            item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
        elif v is not None and not isinstance(v, float):
            item.setText(str(v))
        return item

    def _short_label(self, label):
        return str(label).rsplit(' : ', 1)[-1]

    def _refresh_series_views(self):
        """By peak and By spectrum show the spectra selected in the list."""
        from src.modules.data_analysis import peak_fitting_series as pfs
        if not hasattr(self, 'by_peak_table') or self.series_results is None:
            return
        rows = self._series_view_rows()
        n = self._series_n_peaks()
        self.series_peak = max(0, min(self.series_peak, n - 1)) if n else 0
        j = self.series_peak
        # By peak
        columns, data = pfs.peaks_long(self._view_results(), rows, peak=j,
                                       sigmas=self._sigmas())
        extra = columns.index('Extra')
        no_extra = not any(row[extra] is not None for row in data)
        shown = [c for c in range(len(columns)) if columns[c] != 'Peak'
                 and not (no_extra and c in (extra, extra + 1))
                 and self._value_shown(columns[c])]
        t = self.by_peak_table
        t.clear()
        grey = QColor('#888888')
        self._by_peak_spectra = list(rows)                 # the spectrum of each row (column)
        if not self.transposed():
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
            t.verticalHeader().setVisible(False)
            t.setColumnCount(len(shown))
            self._set_headers(t, [columns[c] for c in shown])
            t.setRowCount(len(data))
            for r, row in enumerate(data):
                for c_out, c in enumerate(shown):
                    v = self._short_label(row[c]) if c == 0 else row[c]
                    item = self._cell(v)
                    if c == 0:
                        item.setToolTip(str(row[0]))
                        item.setData(Qt.UserRole + 1, rows[r])     # its spectrum (for Remove)
                    if row[2] in ('not fitted yet', 'fit failed', 'no such peak'):
                        item.setForeground(grey)
                    t.setItem(r, c_out, item)
            t.resizeColumnsToContents()
            t.resizeRowsToContents()
            t.setColumnWidth(0, min(t.columnWidth(0), 160))
        else:
            # one column per spectrum, one row per value
            t.setSelectionBehavior(QAbstractItemView.SelectColumns)
            t.verticalHeader().setVisible(True)
            values = [c for c in shown if c != 0]
            t.setColumnCount(len(data))
            t.setRowCount(len(values))
            for r, row in enumerate(data):
                head = QTableWidgetItem(self._short_label(row[0]))
                head.setToolTip(str(row[0]))
                t.setHorizontalHeaderItem(r, head)
                for i, c in enumerate(values):
                    item = self._cell(row[c])
                    if row[2] in ('not fitted yet', 'fit failed', 'no such peak'):
                        item.setForeground(grey)
                    t.setItem(i, r, item)
            for i, c in enumerate(values):
                head = QTableWidgetItem(str(columns[c]))
                head.setToolTip(self._header_tip(columns[c]) or str(columns[c]))
                t.setVerticalHeaderItem(i, head)
            t.resizeColumnsToContents()
            t.resizeRowsToContents()
        centres = [row[3] for row in data if isinstance(row[3], float)]
        where = f" (\u2248 {float(np.mean(centres)):.4g})" if centres else ""
        self.series_peak_label.setText(f"{j + 1} of {n}{where}" if n else "\u2013")
        self.series_peak_prev.setEnabled(j > 0)
        self.series_peak_next.setEnabled(j < n - 1)
        # By spectrum
        shown = self._view_results()
        columns, data = pfs.peaks_long(shown, rows, sigmas=self._sigmas())
        owners = []                                # the spectrum of each row of data
        for k in rows:
            owners += [k] * len(pfs.peaks_long(shown, [k])[1])
        tree = self.by_spectrum_tree
        tree.clear()
        tree.setColumnCount(len(columns) - 1)
        tree.setHeaderLabels(['Spectrum / peak'] + [self._header_text(c) for c in columns[2:]])
        for c, name in enumerate(columns[2:], start=1):
            tree.headerItem().setToolTip(c, self._header_tip(name))
        last = None
        for row, k in zip(data, owners):
            if last is None or last.data(0, Qt.UserRole + 1) != k:
                last = QTreeWidgetItem([self._short_label(row[0])])
                last.setData(0, Qt.UserRole, row[0])
                last.setData(0, Qt.UserRole + 1, k)
                last.setToolTip(0, str(row[0]))
                font = last.font(0)
                font.setBold(True)
                last.setFont(0, font)
                r2 = row[-1]
                if row[2] in ('not fitted yet', 'fit failed'):
                    last.setText(1, row[2])
                    last.setForeground(1, grey)
                elif self.is_set_by_hand(k):
                    last.setText(1, "\u270e set by hand")
                    last.setToolTip(1, "Values changed by hand after the fit (no \u00b1).\n"
                                       "Fit Peaks fits them again.")
                else:
                    last.setText(1, "\u2713 fitted")
                if isinstance(r2, float):
                    last.setText(len(columns) - 2, f'{r2:.4f}')
                tree.addTopLevelItem(last)
                if row[2] in ('not fitted yet', 'fit failed'):
                    continue
            child = QTreeWidgetItem([f"Peak {row[1]}", row[2]]
                                    + [(f'{v:.6g}' if isinstance(v, float) and np.isfinite(v)
                                        else '') for v in row[3:-1]])
            for c in range(2, len(columns) - 2):
                child.setTextAlignment(c, int(Qt.AlignRight | Qt.AlignVCenter))
            child.setData(0, Qt.UserRole + 1, (k, int(row[1]) - 1))   # (spectrum, peak)
            last.addChild(child)
        for i in range(tree.topLevelItemCount()):
            it = tree.topLevelItem(i)
            it.setExpanded(it.data(0, Qt.UserRole) not in self._closed_in_tree)
        no_extra = all(row[columns.index('Extra')] is None for row in data)
        extras = (columns.index('Extra'), columns.index('Extra' + pfs.pm(self._sigmas())))
        for c in range(2, len(columns)):                  # Hide: Position, FWHM, ...
            tree.setColumnHidden(c - 1, (no_extra and c in extras)
                                 or not self._value_shown(columns[c]))
        for c in range(tree.columnCount()):
            tree.resizeColumnToContents(c)
        tree.setColumnWidth(0, min(tree.columnWidth(0), 170))

    def _series_peaks_of(self, view):
        """The (spectrum, peak) pairs selected in By peak (the shown peak of
        the selected rows' spectra) or By spectrum (the selected peak rows)."""
        pairs = []
        if view is self.by_peak_table:
            across = self.transposed()
            spectra = getattr(self, '_by_peak_spectra', [])
            for r in sorted({(i.column() if across else i.row()) for i in view.selectedIndexes()}):
                if across:
                    k = spectra[r] if r < len(spectra) else None
                else:
                    item = view.item(r, 0)
                    k = item.data(Qt.UserRole + 1) if item is not None else None
                if k is None:
                    continue
                res = self.series_results[k] if self.series_results else None
                if res and res.get('ok'):
                    j = self._original_index(k, self.series_peak)
                elif self.series_peak < len(self.peaks_of(k)):
                    j = self.series_peak
                else:
                    j = None
                if j is not None:
                    pairs.append((int(k), int(j)))
        else:
            for item in view.selectedItems():
                kj = item.data(0, Qt.UserRole + 1)
                if isinstance(kj, (tuple, list)):
                    j = self._original_index(int(kj[0]), int(kj[1]))
                    if j is not None:
                        pairs.append((int(kj[0]), int(j)))
        return sorted(set(pairs))

    def _series_remove_menu(self, view, pos):
        pairs = self._series_peaks_of(view)
        menu = QMenu(self)
        if view is self.by_peak_table:
            n = len({k for k, _ in pairs})
            text = (f"Remove peak {self.series_peak + 1} from the selected spectrum"
                    + ("" if n == 1 else f"s ({n})"))
        else:
            text = "Remove the selected peak" + ("" if len(pairs) == 1 else f"s ({len(pairs)})")
        a = menu.addAction(text + "   Delete")
        a.setEnabled(bool(pairs))
        a.triggered.connect(lambda *_: self.remove_series_peaks(pairs))
        menu.exec_(view.viewport().mapToGlobal(pos))

    def remove_series_peaks(self, pairs, ask=True):
        """Remove these (spectrum, peak) pairs from the spectra's peaks (as
        Remove Selected Peak(s) on the tab Peaks): a fitted spectrum keeps the
        rest of its fitted values, "set by hand". With more than one spectrum
        a question first. Returns the spectra changed."""
        pairs = sorted(set(pairs))
        spectra = sorted({k for k, _ in pairs})
        if not spectra:
            return []
        if ask and len(spectra) > 1:
            n = len(pairs)
            what = (f"peak {pairs[0][1] + 1}" if len({j for _, j in pairs}) == 1
                    else f"{n} peaks")
            if QMessageBox.question(
                    self, "Remove peaks",
                    f"Remove {what} from {len(spectra)} spectra?\n"
                    "Their other values stay (set by hand until the next Fit Peaks).",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
                return []
        from src.modules.data_analysis import peak_fitting_series as pfs
        for i in range(len(self.peaks)):
            self.update_peak_from_table(i)
        for k in spectra:
            if k == self.current_index:
                peaks = self.peaks
            else:
                if self.own_peaks[k] is None:
                    self.own_peaks[k] = []
                peaks = self.own_peaks[k]
            res = self.series_results[k] if self.series_results else None
            fitted = (res.get('peaks') or []) if res and res.get('ok') else []
            if fitted:
                # the values shown in Series results (fitted) become its peaks
                base = (peaks if len(peaks) == len(fitted) else
                        [{'color': self.colors[i % len(self.colors)]}
                         for i in range(len(fitted))])
                peaks[:] = pfs.start_from(fitted, base)
            for j in sorted((j for kk, j in pairs if kk == k), reverse=True):
                if 0 <= j < len(peaks):
                    peaks.pop(j)
            self._tidy_constraints(peaks)
        self._peaks_changed(spectra, by_hand=True)
        if self.current_index in spectra:
            self.fit_results = None
            self.update_peaks_table()
        self._refresh_list_texts()
        self._update_copy_results_button()
        self.update_plot()
        return spectra

    def series_view_text(self):
        """What Copy results copies on the tab Series results: the view shown,
        for the spectra selected in the list."""
        from src.modules.data_analysis import peak_fitting_series as pfs
        from src.modules.data_analysis import peak_list as pl
        rows = self._series_view_rows()
        view = self.series_view()
        if view == 'wide':
            return self.copy_series(rows)
        columns, data = pfs.peaks_long(self._view_results(), rows,
                                       peak=self.series_peak if view == 'peak' else None,
                                       sigmas=self._sigmas())
        keep = [c for c, name in enumerate(columns) if self._value_shown(name)]
        columns = [columns[c] for c in keep]
        data = [[row[c] for c in keep] for row in data]
        if view == 'peak' and self.transposed():
            columns, data = self._transpose_text(columns, data)
        text = pl.rows_as_text(data, columns)
        QApplication.clipboard().setText(text)
        self.copied_rows = len(rows)
        self.copied_empty = sum(1 for r in rows if not self.series_results[r].get('ok'))
        return text

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
        if (result and result.get('ok') and not result.get('manual')
                and len(result['peaks']) == len(self.peaks)):
            self.fit_results = result['peaks']
            self.fit_background = result.get('background')
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
        """The spectra selected in All in one table (its rows - or its
        columns when transposed)."""
        if not hasattr(self, 'series_table'):
            return []
        if self.transposed() and self.series_view() == 'wide':
            return sorted({i.column() for i in self.series_table.selectedIndexes()})
        return sorted({i.row() for i in self.series_table.selectedIndexes()})

    def series_rows(self):
        """(columns, rows) of the series results (pfs.series_table)."""
        from src.modules.data_analysis import peak_fitting_series as pfs
        shown = self._view_results() or []
        n = max([0 if self.matched_by_position() else len(self.peaks)]
                + [len(r.get('peaks') or []) for r in shown if r.get('ok')])
        return pfs.series_table(shown, n, self._sigmas())

    def _refresh_series_table(self):
        from src.modules.data_analysis import peak_fitting_series as pfs
        if not hasattr(self, 'series_table') or self.series_results is None:
            return
        columns, rows = self.series_rows()
        t = self.series_table
        keep = self.selected_spectra() or self.selected_series_rows()
        transposed = self.transposed() and self.series_view() == 'wide'
        t.blockSignals(True)
        t.clear()
        t.setSelectionBehavior(QAbstractItemView.SelectColumns if transposed
                               else QAbstractItemView.SelectRows)

        def cell(v, c):
            item = QTableWidgetItem()
            if isinstance(v, float) and np.isfinite(v):
                item.setData(Qt.DisplayRole, float(f'{v:.6g}'))
                item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
            elif isinstance(v, str):
                item.setText(self._short_label(v) if c == 0 else v)
                if c == 0:
                    item.setToolTip(v)
            return item
        if not transposed:
            t.setColumnCount(len(columns))
            self._set_headers(t, columns)
            t.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, v in enumerate(row):
                    t.setItem(r, c, cell(v, c))
                # the row number: hold the mouse over it - the spectrum's name
                head = QTableWidgetItem(str(r + 1))
                head.setToolTip(str(row[0]))
                t.setVerticalHeaderItem(r, head)
                t.setRowHidden(r, self._hidden_spectrum(r))
            for c, name in enumerate(columns):
                t.setColumnHidden(c, not self._value_shown(name))
            t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        else:
            # one column per spectrum, one row per value
            t.setColumnCount(len(rows))
            t.setRowCount(len(columns) - 1)
            for r, row in enumerate(rows):
                head = QTableWidgetItem(self._short_label(row[0]))
                head.setToolTip(str(row[0]))
                t.setHorizontalHeaderItem(r, head)
                for c in range(1, len(columns)):
                    t.setItem(c - 1, r, cell(row[c], c))
                t.setColumnHidden(r, self._hidden_spectrum(r))
            for c in range(1, len(columns)):
                head = QTableWidgetItem(str(columns[c]))
                head.setToolTip(self._header_tip(columns[c]) or str(columns[c]))
                t.setVerticalHeaderItem(c - 1, head)
                t.setRowHidden(c - 1, not self._value_shown(columns[c]))
        t.resizeColumnsToContents()
        if not transposed:
            t.setColumnWidth(0, min(t.columnWidth(0), 220))
        model = t.selectionModel()
        for r in keep:
            if r < len(rows):
                model.select(t.model().index(0, r) if transposed else t.model().index(r, 0),
                             QItemSelectionModel.Select | (QItemSelectionModel.Columns
                                                           if transposed else
                                                           QItemSelectionModel.Rows))
        t.blockSignals(False)
        text = pfs.summary(self.series_results)
        if self.matched_by_position():
            bands = pfs.match_by_position(self.series_results)[0]
            text += (f" Peaks matched by position: {len(bands)} bands ("
                     + ", ".join(f"\u2248{b['center']:.4g}" for b in bands[:8])
                     + (", \u2026" if len(bands) > 8 else "") + ").")
        self.series_info.setText(text + " Shown: the spectra selected in the list beside the "
                                 "plot (All = the whole series)"
                                 + (", without those not fitted yet."
                                    if self.hide_empty_check.isChecked() else "."))
        self.series_info.setToolTip(
            "Select spectra in the list to see their results here and their fits in the plot "
            "(several: Overlay, Waterfall or Grid). A bad fit: select that spectrum alone, "
            "correct its peaks in the tab Peaks and Fit Peaks - only it is fitted again.")
        for b in (self.series_copy_button, self.series_export_button,
                  self.series_data_table_button):
            b.setEnabled(True)
        self._refresh_series_views()
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
            mark, tip = self._list_mark(self.series[k], res)
            text = mark + str(self.series[k].get('label', '')).rsplit(' : ', 1)[-1]
            self.spectra_list.item(k).setToolTip(tip)
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
        self._update_copy_results_button()
        from src.modules.data_analysis import peak_fitting_series as pfs
        has_peaks = bool(self.peaks)
        note = ''
        together = self.together() != 'each' and len(self.selected_spectra()) > 1
        if together:
            from src.modules.data_analysis import peak_fitting_global as pg
            chosen = self.selected_spectra()
            r0, template = self._global_template(chosen)
            has_peaks = bool(template)
            note = (f"All {len(chosen)} selected spectra fitted together from the peaks of "
                    f"{self._short_names([r0])}: {pg.SHARE_TEXT[self.together()]} for all, each "
                    "spectrum its own heights and background." if has_peaks else
                    "Fitting together starts from the peaks of the shown spectrum: set them "
                    "first (Auto-Detect Peaks or Add via Click).")
        elif len(self.series) > 1:
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
            if not has_peaks and len(chosen) > 1:
                note = self._no_start_text(chosen)
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
                                else f"Fit Peaks \u2013 {n} spectra together" if together
                                else f"Fit Peaks \u2013 {n} selected spectra")

    def _on_series_tab(self):
        return (hasattr(self, 'left_tabs') and self.left_tabs.currentIndex() == 1
                and len(self.series) > 1)

    def _update_copy_results_button(self):
        """Copy Results follows the tab shown: Peaks - "Copy table - <shown
        spectrum>" (the peaks table); Series results - "Copy results - N
        spectra" (the rows of the spectra selected in the list, i.e. those in
        the plot)."""
        btn = getattr(self, 'copy_results_btn', None)
        if btn is None:
            return
        if self._on_series_tab():
            n = len(self._series_view_rows())
            peak = (f"peak {self.series_peak + 1}" if self.series_view() == 'peak'
                    else "results")
            btn.setText(f"Copy {peak} \u2013 {n} spectr{'um' if n == 1 else 'a'}")
            btn.setToolTip(
                "Copy the Series results as shown (By peak, By spectrum or All in one table)\n"
                "for the spectra selected in the list - those in the plot - ready to paste\n"
                "into Excel. A spectrum not fitted yet gives an empty row\n"
                "(none with Hide: Spectra without values).")
            btn.setEnabled(self.series_results is not None)
            return
        if len(self.series) > 1:
            name = str(self.series[self.current_index].get('label', '')).rsplit(' : ', 1)[-1]
            btn.setText(f"Copy table \u2013 {self._shorten(name, 16)}")
        else:
            btn.setText("Copy Results")
        btn.setToolTip(
            "Copy the peaks table above (the shown spectrum) to the clipboard, with FWHM and "
            "area, ready to paste into Excel: the start values, or after Fit Peaks the fitted "
            "values."
            + ("\nThe results of several spectra: tab Series results." if len(self.series) > 1
               else ""))
        has_table = hasattr(self, 'peaks_table') and self.peaks_table.rowCount() > 0
        btn.setEnabled(bool(self.peaks) or has_table)

    def _no_start_text(self, chosen):
        """Several spectra selected, none with peaks (Fit Peaks greyed): what
        gives them a start - e.g. raman_13-18 selected, only raman_11 has
        peaks."""
        n = len(chosen)
        others = [k for k in range(len(self.series)) if k not in chosen and self.peaks_of(k)]
        box = "\u201cSpectra without peaks: start from the fit before them\u201d"
        if others:
            before = [k for k in others if k < min(chosen)]
            if before and self.follow_check.isChecked():
                name = self._short_names(before[-1:])
                return (f"None of the {n} selected spectra has peaks. The checkbox {box} is "
                        f"ticked \u2013 now hold Ctrl and click {name} in the list, so that it is "
                        f"selected too: the others start from its fit. (Or Auto-Detect Peaks "
                        f"\u2013 {n} spectra.)")
            name = self._short_names(before[-1:] if before else others[:1])
            text = (f"None of the {n} selected spectra has peaks. {name} has. Either click "
                    f"{name} alone, click Copy peaks of {name}, select these again and click "
                    f"Paste peaks of {name} to the selected spectra.")
            if before:
                text += (f" Or tick the checkbox {box} above, then hold Ctrl and click {name} "
                         f"in the list.")
            return text + f" Or Auto-Detect Peaks \u2013 {n} spectra."
        return (f"None of the {n} selected spectra has peaks yet: Auto-Detect Peaks – {n} "
                "spectra, or select one alone, set its peaks (Auto-Detect Peaks or Add via "
                "Click), Copy peaks, select the others and Paste peaks to the selected spectra.")

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
        if self.together() != 'each' and len(pool) > 1:
            return self._fit_together(pool)
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
                    results = pfs.fit_series_independent(spectra, starts[0], constraint, progress,
                                                         background=self.background_kind)
                else:                               # e.g. pasted: one start for all
                    results = pfs.fit_series_independent(spectra, None, constraint or
                                                         'unrestricted', progress,
                                                         starts=starts, constraints=constraints,
                                                         background=self.background_kind)
            else:                                       # some follow the fit before them
                results, used = pfs.fit_each(spectra, starts, constraint or 'unrestricted',
                                             progress, constraints=constraints,
                                             background=self.background_kind)
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
        self._update_copy_results_button()
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

    # ------------------------------------------------------------------
    # several spectra fitted together (a global fit)
    # ------------------------------------------------------------------
    def together(self):
        """'each' (default), 'positions' or 'widths' (Several spectra: ...)."""
        combo = getattr(self, 'together_combo', None)
        return (combo.currentData() if combo is not None and len(self.series) > 1
                else None) or 'each'

    def _together_chosen(self):
        if hasattr(self, 'follow_check'):
            self.follow_check.setEnabled(self.together() == 'each')
        self._update_fit_button()

    def _global_template(self, rows):
        """(row, peaks) the fit together starts from: the shown spectrum's
        peaks, else those of the first selected spectrum that has peaks."""
        if self.peaks:
            return self.current_index, self.peaks
        for r in sorted(rows):
            if self.peaks_of(r):
                return r, self.peaks_of(r)
        return None, []

    def _fit_together(self, rows):
        """Fit the spectra `rows` together (peak_fitting_global.fit_global):
        the peaks of the shown spectrum for all, the positions and widths (or
        only the widths) the same, each spectrum its own heights and
        background. The results go to Series results; every fitted spectrum
        gets its fitted peaks as its own peaks."""
        from PyQt5.QtWidgets import QProgressDialog
        from src.modules.data_analysis import peak_fitting_global as pg
        from src.modules.data_analysis import peak_fitting_series as pfs
        from src.modules.utils.progress_utils import OperationCancelled
        rows = sorted(rows)
        r0, template = self._global_template(rows)
        if not template:
            QMessageBox.information(self, "Fit Peaks",
                                    "Add the peaks first (Auto-Detect Peaks or Add via Click) on "
                                    "one spectrum: all selected spectra are fitted from them.")
            return None
        template = [dict(p) for p in template]
        spectra = [self.series[r] for r in rows]
        share = self.together()
        window = QProgressDialog(f"Fitting the {len(rows)} spectra together\u2026", "Cancel",
                                 0, 0, self)
        window.setWindowTitle("Fit Peaks")
        window.setMinimumDuration(400)

        def progress(done, total):
            QApplication.processEvents()
            if window.wasCanceled():
                raise OperationCancelled()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            results = pg.fit_global(spectra, template, share=share,
                                    amplitude_constraints=[self.constraint_of(r) for r in rows],
                                    background=self.background_kind, progress=progress,
                                    manager=self.manager)
        except OperationCancelled:
            return None
        finally:
            QApplication.restoreOverrideCursor()
            window.close()
        if not any(r['ok'] for r in results):
            QMessageBox.warning(self, "Fit Failed",
                                "The spectra could not be fitted together. Check the peaks of "
                                "the shown spectrum (fit it alone first), or fit each on its "
                                "own.")
            return None
        merged = list(self.series_results or pfs.pending(self.series))
        for r, res in zip(rows, results):
            merged[r] = res
            if res['ok'] and r != self.current_index and self.own_peaks is not None:
                # its fit becomes its peaks (shown with it, the start of a next fit)
                self.own_peaks[r] = pfs.start_from(res['peaks'], template)
        self.series_results = merged
        self._update_copy_results_button()
        self._refresh_series_table()
        if hasattr(self, 'left_tabs'):
            self.left_tabs.setCurrentIndex(1)
        if len(self.selected_spectra()) > 1:
            self._set_current(self.current_index)
            self._select_table_rows(self.selected_spectra())
            self._view_changed()
        else:
            self.show_series_spectrum(self.current_index)
        return results

    def copy_series(self, picked=None):
        """Copy the selected rows of Series results (the spectra selected in
        the list) - or, with none selected, the rows of all fitted spectra.
        `picked`: these rows (Copy results)."""
        from src.modules.data_analysis import peak_list as pl
        columns, rows = self.series_rows()
        if picked is None:
            picked = self.selected_series_rows()
        if not picked:
            picked = [k for k, r in enumerate(self.series_results or [])
                      if not r.get('pending')]
            self.copied_what = 'all fitted ones'
        else:
            self.copied_what = 'the selected ones'
        picked = [r for r in picked if not self._hidden_spectrum(r)]
        self.copied_rows = len(picked)
        self.copied_empty = sum(1 for r in picked
                                if not ((self.series_results or [])[r] or {}).get('ok'))
        # what is shown: the columns chosen, transposed when shown so
        keep = [c for c, name in enumerate(columns) if self._value_shown(name)]
        columns = [columns[c] for c in keep]
        data = [[rows[r][c] for c in keep] for r in picked]
        if self.transposed() and self.series_view() == 'wide':
            columns, data = self._transpose_text(columns, data)
        text = pl.rows_as_text(data, columns)
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
        self._series_ax = None                 # (Overlay / Waterfall: their one plot)
        self._grid_axes = {}                   # (Grid: small plot -> its spectrum)
        self._bands = []                       # (Waterfall: (row, lowest, highest))
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
                self._grid_axes[ax] = r
                sp, res = self.series[r], self._series_result(r)
                x, y = np.asarray(sp['x_scale'], float), np.asarray(sp['y_scale'], float)
                off = (background_values(res.get('background'), x)
                       if res.get('ok') and self._subtract_background() else 0.0)
                if self._data_style() == 'line':
                    ax.plot(x, y - off, '-', color='gray', lw=0.8)
                else:
                    ax.plot(x, y - off, '.', color='gray', ms=2)
                if res.get('ok'):
                    total, _ = pfs.model_curves(x, res['peaks'], self.manager,
                                                res.get('background'))
                    ax.plot(x, total - off, 'r-', lw=1.4)
                r2 = res.get('r2')
                ok = res.get('ok') and r2 is not None and np.isfinite(r2)
                failed = bool(res) and not res.get('ok') and not res.get('pending')
                shown = r == self.current_index
                if shown:
                    # the shown spectrum: an orange frame, as in the list
                    for spine in ax.spines.values():
                        spine.set_edgecolor(SHOWN_COLOUR)
                        spine.set_linewidth(2.2)
                    self._draw_start_peaks(ax, 0.0, off)
                ax.set_title((str(sp.get('label', '')).rsplit(' : ', 1)[-1])
                             + (f"  R\u00b2 {r2:.3f}" if ok else "  not fitted" if failed else ""),
                             fontsize=7, color='red' if failed else 'black',
                             fontweight='bold' if shown else 'normal')
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
                off = (background_values(res.get('background'), x)
                       if fitted and self._subtract_background() else 0.0)
                shown = r == self.current_index
                if shown:
                    shown_off = off
                drawn = y - off + k * step
                # the data as chosen in Data (points or a line); the shown
                # spectrum a little stronger
                style = (dict(linestyle='none', marker='.', ms=3 if shown else 2)
                         if self._data_style() == 'points' else dict(lw=1.3 if shown else 0.7))
                ax.plot(x, drawn, color=color, alpha=(0.45 if fitted else 0.9) if not shown else 1.0,
                        label=None if fitted else name, zorder=3 if shown else 2, **style)
                if fitted:
                    total, _ = pfs.model_curves(x, res['peaks'], self.manager,
                                                res.get('background'))
                    ax.plot(x, total - off + k * step, '-', color=color,
                            lw=3.0 if shown else 2.0, label=name, zorder=4 if shown else 2)
                finite = drawn[np.isfinite(drawn)]
                if len(finite):
                    self._bands.append((r, float(finite.min()), float(finite.max())))
            self._series_ax = ax
            if step and self.current_index in rows:
                # Waterfall: the band of the shown spectrum framed in orange
                _, lo, hi = next(b for b in self._bands if b[0] == self.current_index)
                pad = 0.04 * step
                ax.axhspan(lo - pad, hi + pad, facecolor=to_rgba(SHOWN_COLOUR, 0.08),
                           edgecolor=SHOWN_COLOUR, lw=1.2, zorder=0)
            # the starting peaks of the shown spectrum (not fitted yet), dashed -
            # so a peak added by a click is seen
            if self.current_index in rows:
                self._draw_start_peaks(ax, rows.index(self.current_index) * step, shown_off)
            any_fit = any(self._series_result(r).get('ok') for r in rows)
            ax.set_title(("Waterfall" if step else "Overlay") + f": {len(rows)} spectra"
                         + (" - data thin, fits thick" if any_fit else ""), fontsize=10)
            ax.set_xlabel("X-Axis")
            ax.set_ylabel("Intensity" + (" (shifted)" if step else ""))
            ax.grid(True, alpha=0.4)
            if len(rows) <= 20 and self.legend_check.isChecked():
                ax.legend(fontsize=7)
        self.canvas.draw()

    def _draw_start_peaks(self, ax, shift, off=0.0):
        """The starting peaks of the shown spectrum (before a fit), dashed, on
        its background guess - minus `off`, what was taken off its data in
        the drawing (\u2212 background) - and shifted up by `shift`."""
        if not self.peaks or self.fit_results:
            return
        x = np.asarray(self.x_roi, float)
        base = background_values(self._shown_background(), x) - off
        for peak in self.peaks:
            try:
                model_func, _ = self.manager.peak_models[peak['model']]
                guess = model_func(x, *self._params_list_from_peak_guess(peak))
                ax.plot(x, base + guess + shift, '--', color=peak['color'], lw=1.6, zorder=5)
            except (ValueError, TypeError, KeyError):
                pass

    def _series_result(self, r):
        """The series result of spectrum r ({} when the series is not fitted yet)."""
        return self.series_results[r] if self.series_results else {}

    def copy_results_to_clipboard(self):
        """Copy Results. Tab Peaks: the peaks table - the shown spectrum, its
        start values or (after Fit Peaks) its fitted values. Tab Series
        results: the rows of the spectra selected in the list. (One row per
        spectrum of a series: Copy in the tab Series results (copy_series)."""
        if self._on_series_tab() and self.series_results is not None:
            rows = self._series_view_rows()
            self.series_view_text()
            n, e = self.copied_rows, self.copied_empty
            spectra = f"{n} spectr{'um' if n == 1 else 'a'} ({self._short_names(rows)})"
            what = {'peak': f"Peak {self.series_peak + 1} of {spectra} was",
                    'spectrum': f"The peaks of {spectra} were",
                    'wide': f"The Series results of {spectra} were"}[self.series_view()]
            QMessageBox.information(
                self, "Results Copied",
                f"{what} copied to the clipboard as shown, ready to paste into Excel."
                + (f" {e} of them not fitted yet: empty row{'s' if e != 1 else ''}." if e else ""))
            return
        if self.peaks_table.rowCount() == 0:
            QMessageBox.warning(self, "No Results", "There are no peaks in the table to copy.")
            return

        # Create a tab-separated string for easy pasting into Excel/PowerPoint;
        # after a fit each value is followed by its uncertainty (\u00b1)
        from src.modules.data_analysis import peak_fitting_series as pfs
        fitted = (self.fit_results if self.fit_results
                  and len(self.fit_results) == self.peaks_table.rowCount() else None)
        sigmas = self._sigmas()
        header = ("Peak\t" + "\t".join(pfs.peak_columns(sigmas))   # as in the table
                  + "\tFixed / linked\n")
        lines = [header]

        def dbic(i):
            d = fitted[i].get('delta_bic') if fitted is not None else None
            return f"{d:.1f}" if d is not None else ""

        def err(i, key):
            if fitted is None or key is None:
                return ""
            e = pfs.error_of(fitted[i], key, sigmas)
            return f"{e:.6g}" if e is not None else ""

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

                width_key = pfs.WIDTH_KEY.get(model, 'sigma')
                line = (
                    f"{i + 1}\t"
                    f"{model}\t"
                    f"{center:.4f}\t{err(i, 'center')}\t"
                    f"{amplitude:.4f}\t{err(i, 'height')}\t"
                    f"{width:.4f}\t{err(i, width_key)}\t"
                    f"{extra_text}\t{err(i, extra_key)}\t"
                    f"{fwhm:.4f}\t{err(i, 'fwhm')}\t"
                    f"{area:.4f}\t{err(i, 'area')}\t"
                    f"{dbic(i)}\t"
                    f"{self._constraints_note(i)}\n"
                )
                lines.append(line)
            
            except Exception as e:
                logger.error(f"Error reading table row {i}: {e}")
                # Skip row if data is invalid
                continue
        
        n = len(lines) - 1
        bg = self.fit_background if fitted is not None else None
        if bg:
            # the background fitted with the peaks: its value at both ends
            def e(key):
                v = bg.get(key)
                return f"{v * sigmas:.6g}" if v is not None else ""
            lines.append(f"\nBackground\t{bg['kind'].capitalize()}\n"
                         f"at x\t{bg['x0']:.6g}\ty\t{bg['y0']:.6g}\t{e('y0_err')}\n"
                         f"at x\t{bg['x1']:.6g}\ty\t{bg['y1']:.6g}\t{e('y1_err')}\n")
        clipboard_text = "".join(lines)
        QApplication.clipboard().setText(clipboard_text)

        if len(self.series) > 1:
            name = str(self.series[self.current_index].get('label', '')).rsplit(' : ', 1)[-1]
            res = (self.series_results or [None] * len(self.series))[self.current_index] or {}
            what = "fitted values" if res.get('ok') else "start values, not fitted yet"
            text = (f"The {n} peak{'s' if n != 1 else ''} of the table ({name}: {what}) were "
                    "copied to the clipboard, ready to paste into Excel.\n\nOne row per "
                    "spectrum of the series: tab Series results \u203a Copy.")
        else:
            text = f"The {n} peak{'s' if n != 1 else ''} of the table were copied to the clipboard."
        QMessageBox.information(self, "Results Copied", text)    

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
        base = getattr(self, '_peak_base', 0)
        for i, (line, y) in lines.items():
            line.set_linewidth(3.0 if i in rows else 1.5)
            line.set_alpha(1.0 if (not rows or i in rows) else 0.45)
            if i in rows:
                self._peak_fills.append(self.ax_main.fill_between(
                    self.x_roi, y, base, color=line.get_color(), alpha=0.25, linewidth=0))
        self.canvas.draw_idle()

    def _sigmas(self):
        """1, 2 or 3: the \u00b1 shown are this many standard errors."""
        combo = getattr(self, 'sigma_combo', None)
        return (combo.currentData() if combo is not None else None) or 1

    def _sigmas_chosen(self):
        if self.fit_results:
            self.update_peaks_table(from_fit_results=True)
        self._refresh_series_table()

    def _subtract_background(self):
        """'Subtract background' ticked (above the plot): the data and the
        fit are drawn without the background, the peaks from zero."""
        check = getattr(self, 'subtract_check', None)
        return check is not None and check.isChecked()

    def _data_style(self):
        """'points' (default) or 'line': how the measured data are drawn."""
        combo = getattr(self, 'data_style_combo', None)
        return (combo.currentData() if combo is not None else None) or 'points'

    def _background_chosen(self):
        """Background chosen: used by the next fit, Auto-Detect and clicks;
        the starting peaks are drawn on its first guess."""
        self.background_kind = self.background_combo.currentData() or 'none'
        if self.view_mode == 'one':
            self.update_plot_with_fit_results()

    def _update_background_text(self):
        """Automatic shows what it chose for the shown spectrum: "Automatic
        (None)" or "Automatic (Linear)" - after a fit what the fit used."""
        combo = getattr(self, 'background_combo', None)
        if combo is None:
            return
        k = combo.findData('auto')
        if k < 0:
            return
        text = BACKGROUND_NAMES['auto']
        if self.background_kind == 'auto' and len(self.x_roi):
            if self.fit_results:
                used = (self.fit_background or {}).get('kind', 'none')
            else:
                used = resolve_background(self.x_roi, self.y_roi, 'auto')
            text += f" ({BACKGROUND_NAMES.get(used, used)})"
        if combo.itemText(k) != text:
            combo.setItemText(k, text)

    def _shown_background(self, y_fit_total=None):
        """The background the shown peaks sit on: the fitted one (with a
        fit), else the first guess of the chosen kind from the data."""
        if self.fit_results:
            return self.fit_background or None
        if len(self.series) > 1 and self.is_set_by_hand():
            return self.series_results[self.current_index].get('background') or None
        return initial_background(np.asarray(self.x_roi, dtype=float),
                                  np.asarray(self.y_roi, dtype=float), self.background_kind)

    def _y_limits(self, *curves, data=None):
        """The y range of the plot: the data as drawn (and the fitted curves
        given) with a margin of 5 %."""
        y = np.asarray(self.y_roi if data is None else data, dtype=float)
        parts = [y[np.isfinite(y)]]
        for curve in curves:
            f = np.asarray(curve, dtype=float)
            parts.append(f[np.isfinite(f)])
        values = np.concatenate(parts) if parts else np.array([])
        if not values.size:
            return 0.0, 1.0
        lo, hi = float(values.min()), float(values.max())
        pad = 0.05 * (hi - lo) if hi > lo else (abs(hi) * 0.05 or 1.0)
        return lo - pad, hi + pad

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
            x = np.asarray(self.x_roi, dtype=float)
            y = np.asarray(self.y_roi, dtype=float)
            # the peaks are drawn on the background (fitted, or its first guess);
            # with "Subtract background" the background is taken off the data
            # and the fit instead, and the peaks start from zero
            background = self._shown_background(y_fit_total)
            base = background_values(background, x)
            subtract = bool(background) and self._subtract_background()
            off = base if subtract else np.zeros_like(x)      # taken off what is drawn
            draw_base = base - off
            y_shown = y - off
            # the data: points (default) or a line (Data: in the bar above the plot)
            label = 'Original Data' + (' \u2212 background' if subtract else '')
            if self._data_style() == 'line':
                self.ax_main.plot(x, y_shown, '-', color='gray', label=label, lw=1)
            else:
                self.ax_main.plot(x, y_shown, 'o', color='gray', label=label, markersize=3)
            self._peak_base = draw_base
            self._shown_data = y_shown
            y_total_model = base.copy()
            shown = []                      # the fitted curves: in the y range too
            if background and not subtract:
                self.ax_main.plot(x, base, '-.', color='black', lw=1,
                                  label='Background' + ('' if self.fit_results and
                                                        y_fit_total is not None else ' (guess)'))

            if self.fit_results and y_fit_total is not None:
                # --- STATE 1: Plotting a successful FIT ---
                self.ax_main.plot(x, y_fit_total - off, 'r-', label='Total Fit', lw=2)
                y_total_model = y_fit_total
                for i, peak_fit in enumerate(self.fit_results):
                    model_name, params_dict = peak_fit['model'], peak_fit['parameters']
                    model_func, param_names = self.manager.peak_models[model_name]
                    params_for_func = self._params_list_from_result_dict(model_name, params_dict)
                    y_component = draw_base + model_func(x, *params_for_func)

                    # Use the stored stable color from self.peaks
                    color = self.peaks[i]['color']
                    line, = self.ax_main.plot(x, y_component, ':', color=color, label=f'Peak {i+1} ({model_name})')
                    self._peak_lines[i] = (line, y_component)
                    shown.append(y_component)
            else:
                # --- STATE 2: Plotting initial GUESSES ---
                for i, peak in enumerate(self.peaks):
                    try:
                        # Use the stored stable color
                        color = peak['color']
                        model_func, _ = self.manager.peak_models[peak['model']]
                        y_guess = model_func(x, *self._params_list_from_peak_guess(peak))
                        line, = self.ax_main.plot(x, draw_base + y_guess, '--', color=color)
                        self._peak_lines[i] = (line, draw_base + y_guess)
                        y_total_model = y_total_model + y_guess
                    except (ValueError, TypeError): pass

            # Plot residual (Data - Model)
            if self.ax_residual is not None:
                residual = y - y_total_model
                self.ax_residual.plot(x, residual, color='purple')
                self.ax_residual.axhline(0, color='black', linestyle='--', lw=1)
            # the y range of the data and of the fit with its peaks (e.g. two
            # fitted CD bands partly cancelling each other) - but not of the
            # starting peaks: one far too high does not squeeze the data
            # into a thin line
            if self.fit_results and y_fit_total is not None:
                shown.append(y_fit_total - off)
            self._y_range = self._y_limits(*shown, data=y_shown)
            self.ax_main.set_ylim(*self._y_range)
        else:
             # No data loaded
             self.ax_main.text(0.5, 0.5, "No data to display", transform=self.ax_main.transAxes, ha='center', va='center')

        self._update_background_text()
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
        y_fit_total = y_fit_total + background_values(self.fit_background, self.x_roi)

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
        
        # not fitted: the outputs (OK) are made from the starting peaks, on the
        # background drawn under them (its first guess)
        fitted = bool(self.fit_results)
        if fitted:
            background = self.fit_background
        else:
            from src.modules.data_analysis import peak_fitting_series as pfs
            background = pfs.plain_background(initial_background(
                np.asarray(self.x_roi, dtype=float), np.asarray(self.y_roi, dtype=float),
                self.background_kind)) if len(self.x_roi) else None
        return {
            'fit_results': results_to_return,
            'fitted': fitted,
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
            'data_style': self._data_style(),
            'error_sigmas': self._sigmas(),
            'subtract_background': self._subtract_background(),
            'click_width': 'fixed' if self._click_width_fixed() else 'band',
            'click_width_value': float(self.click_width_spin.value()),
            # the background: its kind and the one fitted with fit_results
            'background': self.background_kind,
            'fit_background': background,
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
               'series_view': self.series_view(),
               'match_by_position': self.matched_by_position(),
               'series_transposed': self.transpose_check.isChecked(),
               'wide_hide_empty': self.hide_empty_check.isChecked(),
               'wide_columns_off': [k for k, cb in self.hide_value_checks.items()
                                    if cb.isChecked()],
               'constraint_per_spectrum': self.own_constraint_check.isChecked(),
               'together': self.together(),
               'list_selection': self.selected_spectra(),
               'several_view': (self.view_combo.currentData()
                                if hasattr(self, 'view_combo') else 'overlay'),
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
    
    def showEvent(self, event):
        # the mouse wheel never changes a drop-down list (or a number box):
        # it scrolls the left part, the table or the list instead
        for widget in self.findChildren((QComboBox, QAbstractSpinBox)):
            _ignore_wheel(widget)
        super().showEvent(event)

    def closeEvent(self, event):
        """Clean up signal connections on close to prevent errors."""
        try:
            if self.click_connection_id is not None:
                self.canvas.mpl_disconnect(self.click_connection_id)
                self.click_connection_id = None
        except Exception:
            pass
        super().closeEvent(event)