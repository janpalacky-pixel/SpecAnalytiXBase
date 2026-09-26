# src/views/main_window.py

from PyQt5.QtWidgets import (QMainWindow, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout,
                             QFrame, QGroupBox,
                            QComboBox, QPushButton, QLabel, QSpinBox, QCheckBox, 
                            QDoubleSpinBox, QGraphicsView, QMenuBar, QMenu, QAction, QSizePolicy,
                            QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator,
                            QApplication, QAbstractItemView, QSplitter)
from PyQt5.QtCore import QRect, pyqtSignal, Qt, QEvent, QTimer
from PyQt5.QtGui import QIcon, QFont
import os
import time
from src.modules.utils.resource_path import resource_path



# ----------------------------------------------------------------------
# Synthetic test datasets shipped in resources/test_data/synthetic/.
# (group, menu label, filename). The group only controls where separators
# fall in the menu. Every workbook has a "Spectra" sheet (what gets
# imported) plus Pure_components / Concentrations / Ground_truth / Info
# sheets holding the known truth to check the analysis against.
# ----------------------------------------------------------------------
# Measured (experimental) datasets shipped in resources/test_data/real/.
# (menu label, filename). Empty by default — the app ships no measured data.
REAL_TEST_DATASETS = [

    ('CD spectra of TBA oligo', 'CD_spectra_TBA.txt'),
    ('Raman DNA conc. dep.', 'Raman_DNA_conc_dep.txt'),

]

# 2D spectral maps specifically — grouped in their own "2D maps" submenu
# (under Real (measured)) rather than mixed flat in with the two series
# above, and kept in resources/test_data/real/2D map/ so they don't
# collide with any other real dataset sharing a similar name. Paths are
# forward-slash here for readability; open_real_dataset() below splits
# on '/' so this is OS-path-safe on Windows too.
REAL_TEST_DATASETS_2D_MAPS = [
    ('Chlorella (WITec 2D map, 25×25)', '2D map/Chlorella.mat'),
    ('Gefionella (WITec 2D map, 30×40)', '2D map/Gefionella.mat'),
    ('Klebsormidium (WITec 2D map, 35×35)', '2D map/Klebsormidium.mat'),
    ('Microchloropsis (WITec 2D map, 20×40)', '2D map/Microchloropsis.mat'),
]

# Real-data 2D maps too large to keep in the git repository (several are
# 100+ MB — over or right at GitHub's 100 MB per-file limit). Shipped
# instead as assets on a GitHub Release; Help -> Test datasets ->
# Real (measured) -> "Download large test datasets..." fetches whichever
# of these the user picks into resources/test_data/real/. See
# resources/test_data/real/README.md for how this is set up and how to
# add more.
LARGE_TEST_DATASETS_OWNER_REPO   = 'janpalacky-pixel/SpecAnalytiXBase'
LARGE_TEST_DATASETS_RELEASE_TAG  = 'test-data-v1'
LARGE_TEST_DATASETS = [
    ('Bigelowiella (WITec 2D map)',    'Bigelowiella.mat'),
    ('Cryptomonas (WITec 2D map)',     'Cryptomonas.mat'),
    ('Eimeria (WITec 2D map)',         'Eimeria.mat'),
    ('Glenodinium (WITec 2D map)',     'Glenodinium.mat'),
    ('Naegleria (WITec 2D map)',       'Naegleria.mat'),
    ('Penium (WITec 2D map)',          'Penium.mat'),
    ('Raman data for 2D map (85x55)',  'Raman_2D_map_85x55.txt'),
    ('Schizochytrium (WITec 2D map)',  'Schizochytrium.mat'),
    ('Tetraselmis (WITec 2D map)',     'Tetraselmis.mat'),
]

SYNTHETIC_TEST_DATASETS = [
    ('raman', 'Raman — 2 components, clean',  'raman_2comp_clean.xlsx'),
    ('raman', 'Raman — 2 components, noisy',  'raman_2comp_noisy.xlsx'),
    ('raman', 'Raman — 3 components, clean',  'raman_3comp_clean.xlsx'),
    ('raman', 'Raman — 3 components, noisy',  'raman_3comp_noisy.xlsx'),
    ('raman', 'Raman — 4 components, clean',  'raman_4comp_clean.xlsx'),
    ('raman', 'Raman — 4 components, noisy',  'raman_4comp_noisy.xlsx'),

    ('uvvis', 'UV/Vis — 2 components, clean', 'uvvis_2comp_clean.xlsx'),
    ('uvvis', 'UV/Vis — 2 components, noisy', 'uvvis_2comp_noisy.xlsx'),
    ('uvvis', 'UV/Vis — 3 components, clean', 'uvvis_3comp_clean.xlsx'),
    ('uvvis', 'UV/Vis — 3 components, noisy', 'uvvis_3comp_noisy.xlsx'),

    ('cd',    'CD (signed) — 2 components, clean', 'cd_2comp_clean.xlsx'),
    ('cd',    'CD (signed) — 2 components, noisy', 'cd_2comp_noisy.xlsx'),
    ('cd',    'CD (signed) — 3 components, clean', 'cd_3comp_clean.xlsx'),
    ('cd',    'CD (signed) — 3 components, noisy', 'cd_3comp_noisy.xlsx'),

    ('roa',   'ROA/VCD (signed) — 2 components, clean', 'roa_2comp_clean.xlsx'),
    ('roa',   'ROA/VCD (signed) — 2 components, noisy', 'roa_2comp_noisy.xlsx'),
    ('roa',   'ROA/VCD (signed) — 3 components, clean', 'roa_3comp_clean.xlsx'),
    ('roa',   'ROA/VCD (signed) — 3 components, noisy', 'roa_3comp_noisy.xlsx'),

    ('closed', 'Closed system (DNA melting) — 2 components, clean',
     'closed_dna_melting_2comp_clean.xlsx'),
    ('closed', 'Closed system (DNA melting) — 2 components, noisy',
     'closed_dna_melting_2comp_noisy.xlsx'),
    ('closed', 'Closed system (DNA melting) — 3 components, clean',
     'closed_dna_melting_3comp_clean.xlsx'),
    ('closed', 'Closed system (DNA melting) — 3 components, noisy',
     'closed_dna_melting_3comp_noisy.xlsx'),

    # For the Melting Curve Analysis tool (Analysis && Visualization ->
    # Data Analysis -> Melting Curve Analysis): each workbook is a series
    # of single-band absorption spectra, one per temperature point, whose
    # band height traces 1-3 independent two-state (van't Hoff) thermal
    # transitions plus linear low-/high-T baselines. Extract the melting
    # curve at X=295 (see each workbook's Info sheet for the true
    # Tm/deltaH/deltaS/factor per transition, to compare a fit against).
    ('melting', 'Melting curve — 1 transition, clean',  'melting_1trans_clean.xlsx'),
    ('melting', 'Melting curve — 1 transition, noisy',  'melting_1trans_noisy.xlsx'),
    ('melting', 'Melting curve — 2 transitions, clean', 'melting_2trans_clean.xlsx'),
    ('melting', 'Melting curve — 2 transitions, noisy', 'melting_2trans_noisy.xlsx'),
    ('melting', 'Melting curve — 3 transitions, clean', 'melting_3trans_clean.xlsx'),
    ('melting', 'Melting curve — 3 transitions, noisy', 'melting_3trans_noisy.xlsx'),

    # For the PLS / PLS-DA tool (Analysis && Visualization -> Visualization ->
    # PLS / PLS-DA): each workbook's Spectra sheet is a mix of "calibration"
    # spectra (known reference value) and "unknown" spectra to predict. See
    # each workbook's own Info/Calibration_values/Answer_key sheets for the
    # values to type into the PLS calibration table, and the true answer to
    # check your prediction against afterwards.
    ('pls', 'PLS regression — protein concentration demo', 'pls_regression_protein_concentration_demo.xlsx'),
    ('pls', 'PLS-DA classification — sample type A/B demo', 'pls_da_sample_type_classification_demo.xlsx'),

    # For the Kinetics Fitting tool (Analysis && Visualization -> Visualization
    # -> Kinetics Fitting): each workbook's Spectra sheet is a time series;
    # see its own Time_values/Info sheets for the time per spectrum (already
    # auto-guessed correctly from the labels) and the true rate constant(s).
    ('kinetics', 'Kinetics — single-exponential decay demo', 'kinetics_single_exponential_decay_demo.xlsx'),
    ('kinetics', 'Kinetics — global analysis, two-step demo', 'kinetics_global_two_step_demo.xlsx'),

    # For the QC / Outlier Detection tool (Analysis && Visualization ->
    # Visualization -> QC / Outlier Detection): a batch of normal spectra
    # plus 3 deliberately planted problem spectra (labels starting with
    # PLANTED_) — see its own Info sheet for the full story and which
    # diagnostic each planted spectrum is expected to flag on.
    ('qc', 'QC — spectral batch with planted outliers demo', 'qc_outlier_planted_outliers_demo.xlsx'),

    # For the X-Axis Alignment tool (Spectra Processing -> Data Manipulation
    # -> X-Axis Alignment): 32 spectra sharing the same bands but each
    # shifted by a different, known amount along x — pick any one as the
    # Reference and align the rest, or compare the recovered shifts against
    # the ones actually introduced.
    ('xaxis', 'X axis alignment demo', 'x_axis_alignment_demo_data.txt'),

    # For the Self-Organizing Map tool (Analysis && Visualization ->
    # Visualization -> SOM): two multi-class illustrations of how a SOM
    # organizes spectra — a sharp-fingerprint Raman-like set and a broad-
    # band UV/Vis absorption-like set, each with several distinct classes
    # plus a "blend" class that should land between them on the trained
    # map. See each workbook's own Ground_truth/Info sheets for the known
    # class per spectrum and a step-by-step walkthrough.
    ('som', 'SOM — Raman multi-class demo (240 spectra)', 'som_raman_multiclass_demo.xlsx'),
    ('som', 'SOM — UV/Vis multi-class demo (250 spectra)', 'som_uvvis_multiclass_demo.xlsx'),
]

class OperationTreeComboBox(QWidget):
    """
    Drop-in replacement for QComboBox that shows a categorised QTreeWidget
    popup.  Exposes the same interface used by OperationsController so that
    file requires zero changes:
        • .currentText()             – active leaf operation name
        • .currentTextChanged        – pyqtSignal(str)
        • .clear() / .addItems()     – compatibility shims
    """

    currentTextChanged = pyqtSignal(str)

    CATEGORIES = [
        ("Baseline Correction", [
            "Manual baseline",
            "Automated Baseline",
            "SNIP Baseline",
            "SVD background",
        ]),
        ("Smoothing", [
            "SG-smoothing",
            "FFT Denoising",
        ]),
        ("Data Manipulation", [
            "Data range",
            "Combine Spectra",
            "Interactive subtraction",
            "X-axis alignment",
            "SVD Interpolation",
        ]),
        ("Axis & Unit Conversion", [
            "Spectral Calculator",
            "Normalization",
            "CD Unit Conversion",
            "X-axis Unit Conversion",
            "Mean-Center Spectra (Dataset)",
        ]),
        ("Spike Removal", [
            "Spike removal",
            "Cosmic ray removal",
        ]),
        ("Resolution", [
            "Resolution enhancement",
        ]),
        ("Batch Pipeline", [
            "Run Batch Pipeline",
        ]),
    ]

    # ------------------------------------------------------------------ #
    # Construction                                                         #
    # ------------------------------------------------------------------ #

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_text = ""
        self._popup_open = False
        self._popup_closed_at = 0.0
        self._build_widget()
        self._build_popup()
        self._populate_tree()

    def _build_widget(self):
        """Build the collapsed combobox-like button."""
        from PyQt5.QtWidgets import QHBoxLayout

        # Fix the height to exactly match a QComboBox on this platform
        hint_cb = QComboBox(self)
        combo_h = hint_cb.sizeHint().height()
        hint_cb.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._button = QPushButton(self)
        self._button.setCursor(Qt.PointingHandCursor)
        self._button.setSizePolicy(QSizePolicy(QSizePolicy.Expanding,
                                               QSizePolicy.Fixed))
        # Style: left-aligned text + a ▼ arrow glyph on the right
        self._button.setStyleSheet(
            "QPushButton {"
            "  text-align: left;"
            "  padding: 4px 6px 4px 6px;"
            "  border: 1px solid #B0B8C8;"
            "  border-radius: 4px;"
            "  background-color: #FFFFFF;"
            "  color: #2C3E6B;"
            "}"
            "QPushButton:hover { border-color: #7A9CC8; background-color: #E8EFF8; }"
            "QPushButton:pressed { background-color: #D0DDF0; }"
        )
        self._update_button_text()
        self._button.clicked.connect(self._toggle_popup)
        layout.addWidget(self._button)

    def _build_popup(self):
        """Build the floating tree popup (created once, shown/hidden on demand)."""
        from PyQt5.QtWidgets import QVBoxLayout

        # Qt.Popup: always above parent, closes on outside click, correct z-order.
        # Parented to the top-level window so it stays above the app but goes
        # behind other applications when the app loses focus.
        self._popup = QFrame(
            self.window(),
            Qt.Popup | Qt.FramelessWindowHint
        )
        self._popup.setFrameShape(QFrame.StyledPanel)
        self._popup.setFrameShadow(QFrame.Raised)

        pop_layout = QVBoxLayout(self._popup)
        pop_layout.setContentsMargins(2, 2, 2, 2)
        pop_layout.setSpacing(0)

        self._tree = QTreeWidget(self._popup)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tree.setFocusPolicy(Qt.NoFocus)   # keep focus on button
        self._tree.setFrameShape(QFrame.NoFrame)
        self._tree.setStyleSheet(
            "QTreeWidget { background-color: #FFFFFF; }"
            "QTreeWidget::item { padding: 3px; color: #2C3E6B; }"
            "QTreeWidget::item:selected { "
            "  background-color: #E3EAF4; "
            "  color: #1A1A2E; "
            "}"
            "QTreeWidget::item:hover { background-color: #F0F4FA; }"
        )
        self._tree.itemClicked.connect(self._on_item_clicked)
        pop_layout.addWidget(self._tree)

        # Install event filter so we can close popup on focus-out
        self._popup.installEventFilter(self)
        self._tree.installEventFilter(self)
        
        # Track main-window moves so the popup follows
        top = self.window()
        if top is not None:
            top.installEventFilter(self)        
        

    def _populate_tree(self):
        """Fill the QTreeWidget from CATEGORIES."""
        self._tree.clear()
        bold = QFont()
        bold.setBold(True)

        for cat_name, ops in self.CATEGORIES:
            cat_item = QTreeWidgetItem(self._tree, [cat_name])
            cat_item.setFont(0, bold)
            # Category rows: enabled but NOT selectable
            cat_item.setFlags(Qt.ItemIsEnabled)
            cat_item.setExpanded(True)
            for op_name in ops:
                op_item = QTreeWidgetItem(cat_item, [op_name])
                op_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        self._tree.expandAll()

    # ------------------------------------------------------------------ #
    # Popup show / hide                                                    #
    # ------------------------------------------------------------------ #

    def _toggle_popup(self):
        if self._popup.isVisible():
            self._close_popup()
            return
        # Guard against a classic Qt.Popup race: clicking the toggle
        # button WHILE the popup is open can make the popup lose window
        # activation and auto-close (see eventFilter's WindowDeactivate
        # branch below) before this SAME click's `clicked` signal even
        # fires — so by the time this method runs, isVisible() already
        # reads False even though the user's intent was "close it", not
        # "open it right back up". That race is what produced the
        # flash: close, then immediately reopen, from one single click.
        # A short time-window guard is the robust fix here rather than
        # trying to precisely order press/release events against the
        # popup's own deactivation, which is fragile and platform-
        # dependent: if the popup closed within the last 250ms, treat
        # this click as the tail end of that same close, not a fresh
        # request to open.
        if time.monotonic() - self._popup_closed_at < 0.25:
            return
        self._open_popup()

    def _open_popup(self):
        # Width = button width (at least 160 px)
        width = max(self._button.width(), 160)

        # Height: one row per leaf + one per category header, capped at 300 px
        row_h = max(self._tree.sizeHintForRow(0), 20)
        n_rows = sum(1 + len(ops) for _, ops in self.CATEGORIES)
        height = min(n_rows * row_h + 8, 300)

        self._popup.setFixedSize(width, height)

        # Position: directly below the button, in global screen coords
        btn_bottom_left = self._button.mapToGlobal(
            self._button.rect().bottomLeft()
        )

        # Guard: don't go below the screen bottom
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            y = btn_bottom_left.y()
            if y + height > screen.bottom():
                # flip above the button
                y = self._button.mapToGlobal(
                    self._button.rect().topLeft()
                ).y() - height
            btn_bottom_left.setY(y)
        except Exception:
            pass

        self._popup.move(btn_bottom_left)
        self._popup.show()
        self._popup.raise_()

        # Highlight the currently selected operation
        if self._current_text:
            self._sync_tree_selection()

        self._popup_open = True

    def _close_popup(self):
        self._popup.hide()
        self._popup_open = False
        self._popup_closed_at = time.monotonic()
        
    def _reposition_popup(self):
            """Move the popup to stay below the button after the window moves."""
            if not self._popup.isVisible():
                return
            btn_bottom_left = self._button.mapToGlobal(self._button.rect().bottomLeft())
            try:
                screen = QApplication.primaryScreen().availableGeometry()
                y = btn_bottom_left.y()
                if y + self._popup.height() > screen.bottom():
                    y = self._button.mapToGlobal(
                        self._button.rect().topLeft()
                    ).y() - self._popup.height()
                btn_bottom_left.setY(y)
            except Exception:
                pass
            self._popup.move(btn_bottom_left)      


    def _sync_tree_selection(self):
        """Highlight the tree item that matches _current_text."""
        it = QTreeWidgetItemIterator(self._tree, QTreeWidgetItemIterator.Selectable)
        while it.value():
            if it.value().text(0) == self._current_text:
                self._tree.setCurrentItem(it.value())
                return
            it += 1

    # ------------------------------------------------------------------ #
    # Event handling                                                       #
    # ------------------------------------------------------------------ #

    def eventFilter(self, obj, event):
        """Close popup on focus-out; reposition it when the main window moves;
        close it when the main window is minimized."""
        if event.type() == QEvent.WindowDeactivate and obj is self._popup:
            self._close_popup()
        elif event.type() == QEvent.Move and obj is self.window():
            self._reposition_popup()
        elif event.type() == QEvent.WindowStateChange and obj is self.window():
            if self.window().isMinimized():
                self._close_popup()
        return super().eventFilter(obj, event)

    def _on_item_clicked(self, item, _col):
        if not (item.flags() & Qt.ItemIsSelectable):
            # Category header: toggle expand/collapse
            item.setExpanded(not item.isExpanded())
            return
        self._close_popup()
        self._set_current(item.text(0))

    # ------------------------------------------------------------------ #
    # Internal state                                                       #
    # ------------------------------------------------------------------ #

    def _set_current(self, text):
        changed = (text != self._current_text)
        self._current_text = text
        self._update_button_text()
        if changed:
            self.currentTextChanged.emit(text)

    def _update_button_text(self):
        arrow = "  ▼"
        label = self._current_text if self._current_text else "Select operation…"
        self._button.setText(label + arrow)

    # ------------------------------------------------------------------ #
    # Public QComboBox-compatible API                                      #
    # ------------------------------------------------------------------ #

    def currentText(self):
        return self._current_text

    def clear(self):
        """Reset selection and rebuild the tree (mirrors QComboBox.clear)."""
        self._current_text = ""
        self._update_button_text()
        self._populate_tree()

    def addItems(self, items):
        """
        Called by OperationsController with dict_keys of operation names.
        The tree is already built from CATEGORIES; we just select the first
        matching leaf as the default, then rebuild the tree to be safe.
        """
        self._populate_tree()
        if not items:
            return
        items_set = set(items)
        for _cat, ops in self.CATEGORIES:
            for op in ops:
                if op in items_set:
                    self._set_current(op)
                    return
        # Fallback
        first = next(iter(items), None)
        if first:
            self._set_current(first)


class AnalysisTreeComboBox(OperationTreeComboBox):
    """
    Tree combobox for the Spectra Analysis & Visualization groupbox.
    Same visual style as OperationTreeComboBox but with analysis categories.
    """
    CATEGORIES = [
        ("Visualization", [
            "SVD analysis",
            "PCA Scores & Loadings",
            "NMF",
            "MCR-ALS",
            "Cluster analysis",
            "SOM",
            "2D map",
            "2D Correlation",
            "PLS / PLS-DA",
        ]),
        ("Data Analysis", [
            "Peak Fitting",
            "Band Ratio",
            "Reference Matching",
            "Melting Curve Analysis",
            "Isosbestic Point Detection",
            "Kinetics Fitting",
            "QC / Outlier Detection",
        ]),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        # Set default so "Select operation…" placeholder is never shown
        self._current_text = "SVD analysis"
        self._update_button_text()


class MainWindow(QMainWindow):
    # Emitted when the user drops one or more supported spectrum files
    # onto the window. Deliberately a signal rather than MainWindow
    # calling into the controller directly — the view doesn't hold a
    # controller reference (see __init__ below), matching the pattern
    # already used for menu actions like actionImport_Snapshot, which
    # ImportController connects to rather than MainWindow invoking it.
    files_dropped = pyqtSignal(list)

    def __init__(self, controller):
        super().__init__()
        
        # Store the controller reference for later use
        # self.controller = controller
        
        # Set up the UI directly without using generated files
        self.setup_ui()
        
        # Initialize UI components
        self.init_ui()

        self._splitter_sizes_applied = False

        # Accept files dragged onto the window from the OS file manager —
        # see dragEnterEvent/dropEvent below.
        self.setAcceptDrops(True)

    def _droppable_paths(self, mime_data) -> list:
        """
        Return the local FILE paths in *mime_data* (directories excluded),
        or [] if none / not a file drag.

        Used to filter down to _DROPPABLE_EXTENSIONS, silently swallowing —
        no error, nothing added, nothing shown — any file whose extension
        this app didn't already recognize by name, however good the data
        inside actually was. That's the same "ignore it, content be
        damned" problem fixed for typed import at
        SpectrumManager.SUPPORTED_EXTENSIONS (see _sniff_numeric_text
        there). Now every dropped file is accepted here and handed to the
        same import pipeline; a file with an unrecognized extension gets
        the same content-sniff-then-ask treatment any other unrecognized-
        extension file gets once it reaches load_spectrum_from_file,
        instead of vanishing before the app even looked at it. A file
        that's neither a recognized nor numeric-looking format still ends
        up rejected — just with a clear reason in the Import Results
        dialog instead of silent, unexplained non-import.
        """
        if not mime_data.hasUrls():
            return []
        paths = [u.toLocalFile() for u in mime_data.urls() if u.isLocalFile()]
        return [p for p in paths if os.path.isfile(p)]

    def dragEnterEvent(self, event):
        if self._droppable_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = self._droppable_paths(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
        else:
            event.ignore()

    def showEvent(self, event):
        super().showEvent(event)
        # setSizes() in setup_ui() runs before this window has its final
        # on-screen geometry, so the 220/640 split gets computed against
        # whatever placeholder size the splitter happened to report at
        # that moment, not the window's real size — which is why it only
        # ever looked right after maximizing forced Qt to recalculate
        # everything. A plain QTimer.singleShot(0, ...) here turned out
        # not to be enough on its own (same as the cosmic ray heatmap
        # fix earlier) — flushing already-queued events synchronously
        # first, then using a small real delay rather than 0ms, is more
        # reliably "after layout has actually settled."
        if not self._splitter_sizes_applied:
            self._splitter_sizes_applied = True
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
            QTimer.singleShot(50, lambda: self.main_splitter.setSizes([340, 640]))

    def setup_ui(self):
        """Set up the user interface directly in Python code."""
        self.setObjectName("MainWindow")
        # 862x584 was too small for the right panel's actual content (4
        # groupboxes side by side plus the plot area) — below that
        # threshold Qt had to squeeze something to make it fit, which is
        # what was distorting the splitter's intended proportions until
        # the window was manually resized past it.
        self.resize(1500, 850)
        
        # Central widget
        self.centralwidget = QWidget(self)
        self.centralwidget.setObjectName("centralwidget")
        self.setCentralWidget(self.centralwidget)
        
        # Main grid layout
        self.gridLayout_8 = QGridLayout(self.centralwidget)
        self.gridLayout_8.setObjectName("gridLayout_8")
        
        # Spectrum selection frame
        self.spectrum_selection_frame = QFrame(self.centralwidget)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.spectrum_selection_frame.sizePolicy().hasHeightForWidth())
        self.spectrum_selection_frame.setSizePolicy(sizePolicy)
        self.spectrum_selection_frame.setFrameShape(QFrame.StyledPanel)
        self.spectrum_selection_frame.setFrameShadow(QFrame.Raised)
        self.spectrum_selection_frame.setObjectName("spectrum_selection_frame")
        # Timing-independent safety net: a hard minimum width means the
        # splitter has a sane size to anchor the left pane to from the
        # very start, regardless of exactly when the deferred setSizes()
        # call in showEvent() actually fires.
        self.spectrum_selection_frame.setMinimumWidth(340)

        # Main content grid layout
        self.gridLayout_7 = QGridLayout()
        self.gridLayout_7.setObjectName("gridLayout_7")
        
        # Graphics view (main plot area)
        self.graphicsView = QGraphicsView(self.centralwidget)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.graphicsView.sizePolicy().hasHeightForWidth())
        self.graphicsView.setSizePolicy(sizePolicy)
        self.graphicsView.setObjectName("graphicsView")
        self.gridLayout_7.addWidget(self.graphicsView, 0, 0, 1, 4)
        
        # Basic plot options group
        self.groupBox_basic_plot_options = QGroupBox(self.centralwidget)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_basic_plot_options.sizePolicy().hasHeightForWidth())
        self.groupBox_basic_plot_options.setSizePolicy(sizePolicy)
        self.groupBox_basic_plot_options.setObjectName("groupBox_basic_plot_options")
        self.groupBox_basic_plot_options.setTitle("Basic plot options")
        
        self.gridLayout_4 = QGridLayout(self.groupBox_basic_plot_options)
        self.gridLayout_4.setObjectName("gridLayout_4")
        
        # Rows and columns layout
        self.gridLayout = QGridLayout()
        self.gridLayout.setObjectName("gridLayout")
        
        # Number of rows
        self.number_of_rows_label = QLabel(self.groupBox_basic_plot_options)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.number_of_rows_label.sizePolicy().hasHeightForWidth())
        self.number_of_rows_label.setSizePolicy(sizePolicy)
        self.number_of_rows_label.setObjectName("number_of_rows_label")
        self.number_of_rows_label.setText("nrow")
        self.gridLayout.addWidget(self.number_of_rows_label, 0, 0, 1, 1)
        
        self.number_of_rows_spinBox = QSpinBox(self.groupBox_basic_plot_options)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.number_of_rows_spinBox.sizePolicy().hasHeightForWidth())
        self.number_of_rows_spinBox.setSizePolicy(sizePolicy)
        self.number_of_rows_spinBox.setMinimum(1)
        self.number_of_rows_spinBox.setMaximum(100)
        self.number_of_rows_spinBox.setMinimumWidth(60)
        self.number_of_rows_spinBox.setObjectName("number_of_rows_spinBox")
        self.gridLayout.addWidget(self.number_of_rows_spinBox, 0, 1, 1, 1)
        
        # Number of columns
        self.number_of_columns_label = QLabel(self.groupBox_basic_plot_options)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.number_of_columns_label.sizePolicy().hasHeightForWidth())
        self.number_of_columns_label.setSizePolicy(sizePolicy)
        self.number_of_columns_label.setObjectName("number_of_columns_label")
        self.number_of_columns_label.setText("ncol")
        self.gridLayout.addWidget(self.number_of_columns_label, 1, 0, 1, 1)
        
        self.number_of_columns_spinBox = QSpinBox(self.groupBox_basic_plot_options)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.number_of_columns_spinBox.sizePolicy().hasHeightForWidth())
        self.number_of_columns_spinBox.setSizePolicy(sizePolicy)
        self.number_of_columns_spinBox.setMinimum(1)
        self.number_of_columns_spinBox.setMaximum(100)
        self.number_of_columns_spinBox.setMinimumWidth(60)
        self.number_of_columns_spinBox.setObjectName("number_of_columns_spinBox")
        self.gridLayout.addWidget(self.number_of_columns_spinBox, 1, 1, 1, 1)
        
        # Waterfall offset controls (shown only for Waterfall plot)
        self.waterfall_offset_label = QLabel(self.groupBox_basic_plot_options)
        self.waterfall_offset_label.setObjectName("waterfall_offset_label")
        self.waterfall_offset_label.setText("Offset")
        self.waterfall_offset_label.setToolTip(
            'Y offset between consecutive spectra. '
            '0 = auto (10 % of the max intensity range).'
        )
        self.gridLayout.addWidget(self.waterfall_offset_label, 2, 0, 1, 1)

        self.waterfall_offset_spinBox = QDoubleSpinBox(self.groupBox_basic_plot_options)
        self.waterfall_offset_spinBox.setObjectName("waterfall_offset_spinBox")
        self.waterfall_offset_spinBox.setRange(0.0, 1e9)
        self.waterfall_offset_spinBox.setDecimals(4)
        self.waterfall_offset_spinBox.setValue(0.0)
        self.waterfall_offset_spinBox.setMinimumWidth(60)
        self.waterfall_offset_spinBox.setSpecialValueText("auto")
        self.waterfall_offset_spinBox.setSingleStep(0.01)
        self.waterfall_offset_spinBox.setToolTip(
            'Y offset between consecutive spectra. '
            "Set to 0 (shown as 'auto') for automatic scaling."
        )
        self.gridLayout.addWidget(self.waterfall_offset_spinBox, 2, 1, 1, 1)

        # Mean ± SD: show individual spectra
        self.mean_sd_show_individual_checkBox = QCheckBox(self.groupBox_basic_plot_options)
        self.mean_sd_show_individual_checkBox.setObjectName("mean_sd_show_individual_checkBox")
        self.mean_sd_show_individual_checkBox.setText("Show individual spectra")
        self.mean_sd_show_individual_checkBox.setChecked(True)
        self.mean_sd_show_individual_checkBox.setToolTip(
            'Overlay individual spectra as thin faded lines under the mean.'
        )
        self.gridLayout.addWidget(self.mean_sd_show_individual_checkBox, 3, 0, 1, 2)

        # Difference plot: reference selector
        self.difference_reference_label = QLabel(self.groupBox_basic_plot_options)
        self.difference_reference_label.setObjectName("difference_reference_label")
        self.difference_reference_label.setText("Reference")
        self.difference_reference_label.setToolTip(
            'Reference for difference plot. Mean = subtract group mean.'
        )
        self.gridLayout.addWidget(self.difference_reference_label, 4, 0, 1, 1)

        self.difference_reference_comboBox = QComboBox(self.groupBox_basic_plot_options)
        self.difference_reference_comboBox.setObjectName("difference_reference_comboBox")
        self.difference_reference_comboBox.setToolTip(
            'Choose the reference for the difference plot.'
        )
        self.gridLayout.addWidget(self.difference_reference_comboBox, 4, 1, 1, 1)

        self.difference_show_ref_checkBox = QCheckBox(self.groupBox_basic_plot_options)
        self.difference_show_ref_checkBox.setObjectName("difference_show_ref_checkBox")
        self.difference_show_ref_checkBox.setText("Show\nreference")
        self.difference_show_ref_checkBox.setChecked(False)
        self.difference_show_ref_checkBox.setVisible(False)
        self.gridLayout.addWidget(self.difference_show_ref_checkBox, 4, 2, 1, 1)

        # Heatmap controls
        self.heatmap_colormap_label = QLabel(self.groupBox_basic_plot_options)
        self.heatmap_colormap_label.setObjectName("heatmap_colormap_label")
        self.heatmap_colormap_label.setText("Colormap")
        self.heatmap_colormap_label.setVisible(False)
        self.gridLayout.addWidget(self.heatmap_colormap_label, 5, 0, 1, 1)

        self.heatmap_colormap_comboBox = QComboBox(self.groupBox_basic_plot_options)
        self.heatmap_colormap_comboBox.setObjectName("heatmap_colormap_comboBox")
        self.heatmap_colormap_comboBox.addItems([
            "viridis", "plasma", "inferno", "magma", "cividis",
            "hot", "coolwarm", "RdBu_r", "seismic"
        ])
        self.heatmap_colormap_comboBox.setVisible(False)
        self.gridLayout.addWidget(self.heatmap_colormap_comboBox, 5, 1, 1, 1)

        self.heatmap_interpolation_label = QLabel(self.groupBox_basic_plot_options)
        self.heatmap_interpolation_label.setObjectName("heatmap_interpolation_label")
        self.heatmap_interpolation_label.setText("Interpolation")
        self.heatmap_interpolation_label.setVisible(False)
        self.gridLayout.addWidget(self.heatmap_interpolation_label, 6, 0, 1, 1)

        self.heatmap_interpolation_comboBox = QComboBox(self.groupBox_basic_plot_options)
        self.heatmap_interpolation_comboBox.setObjectName("heatmap_interpolation_comboBox")
        self.heatmap_interpolation_comboBox.addItems([
            "nearest", "bilinear", "bicubic", "lanczos", "spline16"
        ])
        self.heatmap_interpolation_comboBox.setVisible(False)
        self.gridLayout.addWidget(self.heatmap_interpolation_comboBox, 6, 1, 1, 1)

        self.band_markers_btn = QPushButton(self.groupBox_basic_plot_options)
        self.band_markers_btn.setObjectName("band_markers_btn")
        self.band_markers_btn.setText("Band markers…")
        self.band_markers_btn.setToolTip(
            "Manage named vertical lines drawn on all plots")
        self.gridLayout.addWidget(self.band_markers_btn, 7, 0, 1, 2)

        self.gridLayout_4.addLayout(self.gridLayout, 0, 1, 1, 1)
        
        # X and Y scale layout
        self.gridLayout_2 = QGridLayout()
        self.gridLayout_2.setObjectName("gridLayout_2")
        
        # X scale
        self.x_scale_label = QLabel(self.groupBox_basic_plot_options)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.x_scale_label.sizePolicy().hasHeightForWidth())
        self.x_scale_label.setSizePolicy(sizePolicy)
        self.x_scale_label.setObjectName("x_scale_label")
        self.x_scale_label.setText("X-scale")
        self.gridLayout_2.addWidget(self.x_scale_label, 0, 0, 1, 1)
        
        self.x_scale_comboBox = QComboBox(self.groupBox_basic_plot_options)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.x_scale_comboBox.sizePolicy().hasHeightForWidth())
        self.x_scale_comboBox.setSizePolicy(sizePolicy)
        self.x_scale_comboBox.setObjectName("x_scale_comboBox")
        self.gridLayout_2.addWidget(self.x_scale_comboBox, 0, 1, 1, 1)
        
        # Y scale
        self.y_scale_label = QLabel(self.groupBox_basic_plot_options)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.y_scale_label.sizePolicy().hasHeightForWidth())
        self.y_scale_label.setSizePolicy(sizePolicy)
        self.y_scale_label.setObjectName("y_scale_label")
        self.y_scale_label.setText("Y-scale")
        self.gridLayout_2.addWidget(self.y_scale_label, 1, 0, 1, 1)
        
        self.y_scale_comboBox = QComboBox(self.groupBox_basic_plot_options)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.y_scale_comboBox.sizePolicy().hasHeightForWidth())
        self.y_scale_comboBox.setSizePolicy(sizePolicy)
        self.y_scale_comboBox.setObjectName("y_scale_comboBox")
        self.gridLayout_2.addWidget(self.y_scale_comboBox, 1, 1, 1, 1)
        
        self.gridLayout_4.addLayout(self.gridLayout_2, 0, 2, 1, 1)
        
        # Plot type and options — automatic line colors sits below the
        # dropdown rather than beside it, trading unused vertical space
        # (this column is usually much shorter than the mode-specific one
        # next to it) for horizontal space saved.
        self.gridLayout_3 = QGridLayout()
        self.gridLayout_3.setObjectName("gridLayout_3")
        
        # Plot type choice
        self.comboBox_plot_type_choice = QComboBox(self.groupBox_basic_plot_options)
        self.comboBox_plot_type_choice.setObjectName("comboBox_plot_type_choice")
        self.comboBox_plot_type_choice.addItem("option 1")
        self.comboBox_plot_type_choice.addItem("option2")
        self.gridLayout_3.addWidget(self.comboBox_plot_type_choice, 0, 0, 1, 1)
        
        # Automatic line colors checkbox
        self.automatic_line_colors_checkBox = QCheckBox(self.groupBox_basic_plot_options)
        self.automatic_line_colors_checkBox.setObjectName("automatic_line_colors_checkBox")
        self.automatic_line_colors_checkBox.setText("automatic line colors")
        self.gridLayout_3.addWidget(self.automatic_line_colors_checkBox, 1, 0, 1, 1)
        
        self.gridLayout_4.addLayout(self.gridLayout_3, 0, 0, 1, 1)
        self.gridLayout_7.addWidget(self.groupBox_basic_plot_options, 1, 0, 1, 1)
        
        # Link axes group
        self.groupBox_link_axes = QGroupBox(self.centralwidget)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_link_axes.sizePolicy().hasHeightForWidth())
        self.groupBox_link_axes.setSizePolicy(sizePolicy)
        self.groupBox_link_axes.setObjectName("groupBox_link_axes")
        self.groupBox_link_axes.setTitle("Link axes")
        
        self.gridLayout_6 = QGridLayout(self.groupBox_link_axes)
        self.gridLayout_6.setObjectName("gridLayout_6")
        
        # Link X axes checkbox
        self.link_x_axes_checkBox = QCheckBox(self.groupBox_link_axes)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.link_x_axes_checkBox.sizePolicy().hasHeightForWidth())
        self.link_x_axes_checkBox.setSizePolicy(sizePolicy)
        self.link_x_axes_checkBox.setObjectName("link_x_axes_checkBox")
        self.link_x_axes_checkBox.setText("Link x-axes")
        self.gridLayout_6.addWidget(self.link_x_axes_checkBox, 0, 0, 1, 1)
        
        # Link Y axes checkbox
        self.link_y_axes_checkBox = QCheckBox(self.groupBox_link_axes)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.link_y_axes_checkBox.sizePolicy().hasHeightForWidth())
        self.link_y_axes_checkBox.setSizePolicy(sizePolicy)
        self.link_y_axes_checkBox.setObjectName("link_y_axes_checkBox")
        self.link_y_axes_checkBox.setText("Link y-axes")
        self.gridLayout_6.addWidget(self.link_y_axes_checkBox, 0, 1, 1, 1)
        
        # X axes linking combo
        self.comboBox_linking_x_axes = QComboBox(self.groupBox_link_axes)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.comboBox_linking_x_axes.sizePolicy().hasHeightForWidth())
        self.comboBox_linking_x_axes.setSizePolicy(sizePolicy)
        self.comboBox_linking_x_axes.setObjectName("comboBox_linking_x_axes")
        self.gridLayout_6.addWidget(self.comboBox_linking_x_axes, 1, 0, 1, 1)
        
        # Y axes linking combo
        self.comboBox_linking_y_axes = QComboBox(self.groupBox_link_axes)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.comboBox_linking_y_axes.sizePolicy().hasHeightForWidth())
        self.comboBox_linking_y_axes.setSizePolicy(sizePolicy)
        self.comboBox_linking_y_axes.setObjectName("comboBox_linking_y_axes")
        self.gridLayout_6.addWidget(self.comboBox_linking_y_axes, 1, 1, 1, 1)
        
        self.gridLayout_7.addWidget(self.groupBox_link_axes, 1, 1, 1, 1)
        
        # Spectra Analysis & Visualisation group
        self.groupBox_spectra_visualization = QGroupBox(self.centralwidget)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_spectra_visualization.sizePolicy().hasHeightForWidth())
        self.groupBox_spectra_visualization.setSizePolicy(sizePolicy)
        self.groupBox_spectra_visualization.setObjectName("groupBox_spectra_visualization")
        self.groupBox_spectra_visualization.setTitle("Spectra Analysis && Visualization")

        _viz_layout = QVBoxLayout(self.groupBox_spectra_visualization)
        _viz_layout.setContentsMargins(8, 8, 8, 8)
        _viz_layout.setSpacing(4)

        # Reuse the same OperationTreeComboBox for consistent look & feel
        self.visualization_method_comboBox = AnalysisTreeComboBox(
            self.groupBox_spectra_visualization
        )
        self.visualization_method_comboBox.setObjectName("visualization_method_comboBox")

        _viz_layout.addWidget(self.visualization_method_comboBox)

        self.run_visualization_pushButton = QPushButton("Run")
        self.run_visualization_pushButton.setObjectName("run_visualization_pushButton")
        _viz_layout.addWidget(self.run_visualization_pushButton)

        self.gridLayout_7.addWidget(self.groupBox_spectra_visualization, 1, 2, 1, 1)
        
        # Operations group (renamed to Spectra Processing)
        self.groupBox_operations = QGroupBox(self.centralwidget)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_operations.sizePolicy().hasHeightForWidth())
        self.groupBox_operations.setSizePolicy(sizePolicy)
        self.groupBox_operations.setObjectName("groupBox_operations")
        self.groupBox_operations.setTitle("Spectra Processing")  # RENAMED from "Operations"
        
        self.gridLayout_9 = QGridLayout(self.groupBox_operations)
        self.gridLayout_9.setObjectName("gridLayout_9")
        
        # Available operations — grouped tree selector
        self.available_operations_comboBox = OperationTreeComboBox(self.groupBox_operations)
        self.available_operations_comboBox.setObjectName("available_operations_comboBox")
        self.gridLayout_9.addWidget(self.available_operations_comboBox, 1, 0, 1, 1)
        
        # Run button (opens the operation's own Configure/Apply dialog)
        self.parameters_operations_pushButton = QPushButton(self.groupBox_operations)
        self.parameters_operations_pushButton.setObjectName("parameters_operations_pushButton")
        self.parameters_operations_pushButton.setText("Run")
        self.parameters_operations_pushButton.setToolTip(
            "Open the settings dialog for the selected operation"
        )
        self.gridLayout_9.addWidget(self.parameters_operations_pushButton, 2, 0, 1, 1)
        
        # History button
        self.summary_operations_pushButton = QPushButton(self.groupBox_operations)
        self.summary_operations_pushButton.setObjectName("summary_operations_pushButton")
        self.summary_operations_pushButton.setText("History")
        self.summary_operations_pushButton.setToolTip(
            "View a summary of all operations applied in the current session"
        )
        self.gridLayout_9.addWidget(self.summary_operations_pushButton, 2, 1, 1, 1)

        # Help button — opens the User Guide pipeline section
        self.help_operations_pushButton = QPushButton(self.groupBox_operations)
        self.help_operations_pushButton.setObjectName("help_operations_pushButton")
        self.help_operations_pushButton.setText("?")
        self.help_operations_pushButton.setFixedWidth(28)
        self.help_operations_pushButton.setToolTip(
            "Open the User Guide — Processing Pipeline section"
        )
        self.gridLayout_9.addWidget(self.help_operations_pushButton, 1, 1, 1, 1)

        self.gridLayout_7.addWidget(self.groupBox_operations, 1, 3, 1, 1)  # MOVED to column 3

        # --- Splitter: spectrum list (left) | plot + controls (right) ---
        self.main_splitter = QSplitter(Qt.Horizontal, self.centralwidget)
        self.main_splitter.setObjectName("main_splitter")
        self.main_splitter.setChildrenCollapsible(False)

        # Left pane: the spectrum selection frame (unchanged widget)
        self.main_splitter.addWidget(self.spectrum_selection_frame)

        # Right pane: wrap gridLayout_7 in a plain container widget
        self._right_panel = QWidget(self.centralwidget)
        self._right_panel.setObjectName("right_panel_widget")
        self._right_panel.setLayout(self.gridLayout_7)
        self.main_splitter.addWidget(self._right_panel)

        # Left pane keeps its natural width; right pane takes all extra space
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([340, 640])

        # Place the splitter in the top-level grid (spans both original columns)
        self.gridLayout_8.addWidget(self.main_splitter, 0, 0, 1, 2)
        
        # Menu bar
        self.menuBar = QMenuBar(self)
        self.menuBar.setGeometry(QRect(0, 0, 862, 21))
        self.menuBar.setObjectName("menuBar")
        self.setMenuBar(self.menuBar)
        
        # File menu
        self.menuFile = QMenu(self.menuBar)
        self.menuFile.setObjectName("menuFile")
        self.menuFile.setTitle("File")
        
        # Import submenu
        self.menuImport = QMenu(self.menuFile)
        self.menuImport.setObjectName("menuImport")
        self.menuImport.setTitle("Import data")
        
        # Process menu
        self.menuProcess = QMenu(self.menuBar)
        self.menuProcess.setObjectName("menuProcess")
        self.menuProcess.setTitle("Process")
        
        # View menu
        self.menuView = QMenu(self.menuBar)
        self.menuView.setObjectName("menuView")
        self.menuView.setTitle("View")

        # Spectra processing menu — mirrors the Spectra Processing groupbox
        # tree combobox (OperationTreeComboBox.CATEGORIES), providing an
        # alternative way to open any operation's settings dialog directly
        # from the main menu bar, the same way Analysis & Visualization
        # already does for its own groupbox below.
        self.menuSpectraProcessingOps = QMenu(self.menuBar)
        self.menuSpectraProcessingOps.setObjectName("menuSpectraProcessingOps")
        self.menuSpectraProcessingOps.setTitle("Spectra processing")

        # Baseline Correction submenu
        self.menuOpsBaselineCorrection = QMenu(self.menuSpectraProcessingOps)
        self.menuOpsBaselineCorrection.setObjectName("menuOpsBaselineCorrection")
        self.menuOpsBaselineCorrection.setTitle("Baseline Correction")

        self.actionMenuOpsManualBaseline = QAction(self)
        self.actionMenuOpsManualBaseline.setObjectName("actionMenuOpsManualBaseline")
        self.actionMenuOpsManualBaseline.setText("Manual baseline")

        self.actionMenuOpsAutomatedBaseline = QAction(self)
        self.actionMenuOpsAutomatedBaseline.setObjectName("actionMenuOpsAutomatedBaseline")
        self.actionMenuOpsAutomatedBaseline.setText("Automated Baseline")

        self.actionMenuOpsSNIPBaseline = QAction(self)
        self.actionMenuOpsSNIPBaseline.setObjectName("actionMenuOpsSNIPBaseline")
        self.actionMenuOpsSNIPBaseline.setText("SNIP Baseline")

        self.actionMenuOpsSVDBackground = QAction(self)
        self.actionMenuOpsSVDBackground.setObjectName("actionMenuOpsSVDBackground")
        self.actionMenuOpsSVDBackground.setText("SVD background")

        self.menuOpsBaselineCorrection.addAction(self.actionMenuOpsManualBaseline)
        self.menuOpsBaselineCorrection.addAction(self.actionMenuOpsAutomatedBaseline)
        self.menuOpsBaselineCorrection.addAction(self.actionMenuOpsSNIPBaseline)
        self.menuOpsBaselineCorrection.addAction(self.actionMenuOpsSVDBackground)

        # Smoothing submenu
        self.menuOpsSmoothing = QMenu(self.menuSpectraProcessingOps)
        self.menuOpsSmoothing.setObjectName("menuOpsSmoothing")
        self.menuOpsSmoothing.setTitle("Smoothing")

        self.actionMenuOpsSGSmoothing = QAction(self)
        self.actionMenuOpsSGSmoothing.setObjectName("actionMenuOpsSGSmoothing")
        self.actionMenuOpsSGSmoothing.setText("SG-smoothing")

        self.actionMenuOpsFFTDenoising = QAction(self)
        self.actionMenuOpsFFTDenoising.setObjectName("actionMenuOpsFFTDenoising")
        self.actionMenuOpsFFTDenoising.setText("FFT Denoising")

        self.menuOpsSmoothing.addAction(self.actionMenuOpsSGSmoothing)
        self.menuOpsSmoothing.addAction(self.actionMenuOpsFFTDenoising)

        # Data Manipulation submenu
        self.menuOpsDataManipulation = QMenu(self.menuSpectraProcessingOps)
        self.menuOpsDataManipulation.setObjectName("menuOpsDataManipulation")
        self.menuOpsDataManipulation.setTitle("Data Manipulation")

        self.actionMenuOpsDataRange = QAction(self)
        self.actionMenuOpsDataRange.setObjectName("actionMenuOpsDataRange")
        self.actionMenuOpsDataRange.setText("Data range")

        self.actionMenuOpsCombineSpectra = QAction(self)
        self.actionMenuOpsCombineSpectra.setObjectName("actionMenuOpsCombineSpectra")
        self.actionMenuOpsCombineSpectra.setText("Combine Spectra")

        self.actionMenuOpsInteractiveSubtraction = QAction(self)
        self.actionMenuOpsInteractiveSubtraction.setObjectName("actionMenuOpsInteractiveSubtraction")
        self.actionMenuOpsInteractiveSubtraction.setText("Interactive subtraction")

        self.actionMenuOpsXAxisAlignment = QAction(self)
        self.actionMenuOpsXAxisAlignment.setObjectName("actionMenuOpsXAxisAlignment")
        self.actionMenuOpsXAxisAlignment.setText("X-axis alignment")

        self.actionMenuOpsSVDInterpolation = QAction(self)
        self.actionMenuOpsSVDInterpolation.setObjectName("actionMenuOpsSVDInterpolation")
        self.actionMenuOpsSVDInterpolation.setText("SVD Interpolation")

        self.menuOpsDataManipulation.addAction(self.actionMenuOpsDataRange)
        self.menuOpsDataManipulation.addAction(self.actionMenuOpsCombineSpectra)
        self.menuOpsDataManipulation.addAction(self.actionMenuOpsInteractiveSubtraction)
        self.menuOpsDataManipulation.addAction(self.actionMenuOpsXAxisAlignment)
        self.menuOpsDataManipulation.addAction(self.actionMenuOpsSVDInterpolation)

        # Axis & Unit Conversion submenu — operations that convert or
        # rescale the values on an axis (x or y) into different units,
        # rather than removing/adding data points or correcting shape
        # (that's Data Manipulation) or the baseline/smoothing/spike
        # categories. Grouped together since users reach for them for a
        # related reason: "my data isn't in the units/scale I need yet."
        self.menuOpsAxisUnitConversion = QMenu(self.menuSpectraProcessingOps)
        self.menuOpsAxisUnitConversion.setObjectName("menuOpsAxisUnitConversion")
        self.menuOpsAxisUnitConversion.setTitle("Axis && Unit Conversion")

        self.actionMenuOpsSpectralCalculator = QAction(self)
        self.actionMenuOpsSpectralCalculator.setObjectName("actionMenuOpsSpectralCalculator")
        self.actionMenuOpsSpectralCalculator.setText("Spectral Calculator")

        self.actionMenuOpsNormalization = QAction(self)
        self.actionMenuOpsNormalization.setObjectName("actionMenuOpsNormalization")
        self.actionMenuOpsNormalization.setText("Normalization")

        self.actionMenuOpsCDUnitConversion = QAction(self)
        self.actionMenuOpsCDUnitConversion.setObjectName("actionMenuOpsCDUnitConversion")
        self.actionMenuOpsCDUnitConversion.setText("CD Unit Conversion")

        self.actionMenuOpsXAxisUnitConversion = QAction(self)
        self.actionMenuOpsXAxisUnitConversion.setObjectName("actionMenuOpsXAxisUnitConversion")
        self.actionMenuOpsXAxisUnitConversion.setText("X-axis Unit Conversion")

        self.actionMenuOpsMeanCentering = QAction(self)
        self.actionMenuOpsMeanCentering.setObjectName("actionMenuOpsMeanCentering")
        self.actionMenuOpsMeanCentering.setText("Mean-Center Spectra (Dataset)")

        self.menuOpsAxisUnitConversion.addAction(self.actionMenuOpsSpectralCalculator)
        self.menuOpsAxisUnitConversion.addAction(self.actionMenuOpsNormalization)
        self.menuOpsAxisUnitConversion.addAction(self.actionMenuOpsCDUnitConversion)
        self.menuOpsAxisUnitConversion.addAction(self.actionMenuOpsXAxisUnitConversion)
        self.menuOpsAxisUnitConversion.addAction(self.actionMenuOpsMeanCentering)

        # Spike Removal submenu
        self.menuOpsSpikeRemoval = QMenu(self.menuSpectraProcessingOps)
        self.menuOpsSpikeRemoval.setObjectName("menuOpsSpikeRemoval")
        self.menuOpsSpikeRemoval.setTitle("Spike Removal")

        self.actionMenuOpsSpikeRemoval = QAction(self)
        self.actionMenuOpsSpikeRemoval.setObjectName("actionMenuOpsSpikeRemoval")
        self.actionMenuOpsSpikeRemoval.setText("Spike removal")

        self.actionMenuOpsCosmicRayRemoval = QAction(self)
        self.actionMenuOpsCosmicRayRemoval.setObjectName("actionMenuOpsCosmicRayRemoval")
        self.actionMenuOpsCosmicRayRemoval.setText("Cosmic ray removal")

        self.menuOpsSpikeRemoval.addAction(self.actionMenuOpsSpikeRemoval)
        self.menuOpsSpikeRemoval.addAction(self.actionMenuOpsCosmicRayRemoval)

        # Resolution submenu
        self.menuOpsResolution = QMenu(self.menuSpectraProcessingOps)
        self.menuOpsResolution.setObjectName("menuOpsResolution")
        self.menuOpsResolution.setTitle("Resolution")

        self.actionMenuOpsResolutionEnhancement = QAction(self)
        self.actionMenuOpsResolutionEnhancement.setObjectName("actionMenuOpsResolutionEnhancement")
        self.actionMenuOpsResolutionEnhancement.setText("Resolution enhancement")

        self.menuOpsResolution.addAction(self.actionMenuOpsResolutionEnhancement)

        # Batch Pipeline submenu — a named, reusable sequence of the
        # operations above, captured once and replayed on any selection
        # (see batch_pipeline_help.py). Deliberately its own category
        # rather than folded into Data Manipulation: it operates on a
        # different level (a pipeline runs several of the OTHER
        # categories' operations in sequence), not a transform of its own.
        self.menuOpsBatchPipeline = QMenu(self.menuSpectraProcessingOps)
        self.menuOpsBatchPipeline.setObjectName("menuOpsBatchPipeline")
        self.menuOpsBatchPipeline.setTitle("Batch Pipeline")

        self.actionMenuOpsRunBatchPipeline = QAction(self)
        self.actionMenuOpsRunBatchPipeline.setObjectName("actionMenuOpsRunBatchPipeline")
        self.actionMenuOpsRunBatchPipeline.setText("Run Pipeline...")

        self.actionMenuOpsSaveBatchPipeline = QAction(self)
        self.actionMenuOpsSaveBatchPipeline.setObjectName("actionMenuOpsSaveBatchPipeline")
        self.actionMenuOpsSaveBatchPipeline.setText("Save as Pipeline...")

        self.menuOpsBatchPipeline.addAction(self.actionMenuOpsRunBatchPipeline)
        self.menuOpsBatchPipeline.addAction(self.actionMenuOpsSaveBatchPipeline)

        self.menuSpectraProcessingOps.addMenu(self.menuOpsBaselineCorrection)
        self.menuSpectraProcessingOps.addMenu(self.menuOpsSmoothing)
        self.menuSpectraProcessingOps.addMenu(self.menuOpsDataManipulation)
        self.menuSpectraProcessingOps.addMenu(self.menuOpsAxisUnitConversion)
        self.menuSpectraProcessingOps.addMenu(self.menuOpsSpikeRemoval)
        self.menuSpectraProcessingOps.addMenu(self.menuOpsResolution)
        self.menuSpectraProcessingOps.addMenu(self.menuOpsBatchPipeline)

        # Analysis && Visualization menu — mirrors the Spectra Analysis &
        # Visualization groupbox tree combobox, available from the main menu bar
        self.menuAnalysisVisualization = QMenu(self.menuBar)
        self.menuAnalysisVisualization.setObjectName("menuAnalysisVisualization")
        self.menuAnalysisVisualization.setTitle("Analysis && Visualization")

        # Visualization submenu
        self.menuAnalysisVisualizationViz = QMenu(self.menuAnalysisVisualization)
        self.menuAnalysisVisualizationViz.setObjectName("menuAnalysisVisualizationViz")
        self.menuAnalysisVisualizationViz.setTitle("Visualization")

        self.actionMenuSVDAnalysis = QAction(self)
        self.actionMenuSVDAnalysis.setObjectName("actionMenuSVDAnalysis")
        self.actionMenuSVDAnalysis.setText("SVD analysis")

        self.actionMenuPCAScores = QAction(self)
        self.actionMenuPCAScores.setObjectName("actionMenuPCAScores")
        self.actionMenuPCAScores.setText("PCA Scores && Loadings")

        self.actionMenuNMF = QAction(self)
        self.actionMenuNMF.setObjectName("actionMenuNMF")
        self.actionMenuNMF.setText("NMF")

        self.actionMenuMCRALS = QAction(self)
        self.actionMenuMCRALS.setObjectName("actionMenuMCRALS")
        self.actionMenuMCRALS.setText("MCR-ALS")

        self.actionMenuClusterAnalysis = QAction(self)
        self.actionMenuClusterAnalysis.setObjectName("actionMenuClusterAnalysis")
        self.actionMenuClusterAnalysis.setText("Cluster analysis")

        self.actionMenuSOM = QAction(self)
        self.actionMenuSOM.setObjectName("actionMenuSOM")
        self.actionMenuSOM.setText("SOM")

        self.actionMenu2DMap = QAction(self)
        self.actionMenu2DMap.setObjectName("actionMenu2DMap")
        self.actionMenu2DMap.setText("2D map")

        self.actionMenu2DCorrelation = QAction(self)
        self.actionMenu2DCorrelation.setObjectName("actionMenu2DCorrelation")
        self.actionMenu2DCorrelation.setText("2D Correlation")

        self.actionMenuPLS = QAction(self)
        self.actionMenuPLS.setObjectName("actionMenuPLS")
        self.actionMenuPLS.setText("PLS / PLS-DA")

        self.menuAnalysisVisualizationViz.addAction(self.actionMenuSVDAnalysis)
        self.menuAnalysisVisualizationViz.addAction(self.actionMenuPCAScores)
        self.menuAnalysisVisualizationViz.addAction(self.actionMenuNMF)
        self.menuAnalysisVisualizationViz.addAction(self.actionMenuMCRALS)
        self.menuAnalysisVisualizationViz.addAction(self.actionMenuClusterAnalysis)
        self.menuAnalysisVisualizationViz.addAction(self.actionMenuSOM)
        self.menuAnalysisVisualizationViz.addAction(self.actionMenu2DMap)
        self.menuAnalysisVisualizationViz.addAction(self.actionMenu2DCorrelation)
        self.menuAnalysisVisualizationViz.addAction(self.actionMenuPLS)

        # Data Analysis submenu
        self.menuAnalysisVisualizationData = QMenu(self.menuAnalysisVisualization)
        self.menuAnalysisVisualizationData.setObjectName("menuAnalysisVisualizationData")
        self.menuAnalysisVisualizationData.setTitle("Data Analysis")

        self.actionMenuPeakFitting = QAction(self)
        self.actionMenuPeakFitting.setObjectName("actionMenuPeakFitting")
        self.actionMenuPeakFitting.setText("Peak Fitting")

        self.actionMenuBandRatio = QAction(self)
        self.actionMenuBandRatio.setObjectName("actionMenuBandRatio")
        self.actionMenuBandRatio.setText("Band Ratio")

        self.actionMenuReferenceMatching = QAction(self)
        self.actionMenuReferenceMatching.setObjectName("actionMenuReferenceMatching")
        self.actionMenuReferenceMatching.setText("Reference Matching")

        self.actionMenuMeltingCurve = QAction(self)
        self.actionMenuMeltingCurve.setObjectName("actionMenuMeltingCurve")
        self.actionMenuMeltingCurve.setText("Melting Curve Analysis")

        self.actionMenuIsosbesticPoint = QAction(self)
        self.actionMenuIsosbesticPoint.setObjectName("actionMenuIsosbesticPoint")
        self.actionMenuIsosbesticPoint.setText("Isosbestic Point Detection")

        self.actionMenuKineticsFitting = QAction(self)
        self.actionMenuKineticsFitting.setObjectName("actionMenuKineticsFitting")
        self.actionMenuKineticsFitting.setText("Kinetics Fitting")

        self.actionMenuQCOutlier = QAction(self)
        self.actionMenuQCOutlier.setObjectName("actionMenuQCOutlier")
        self.actionMenuQCOutlier.setText("QC / Outlier Detection")

        self.menuAnalysisVisualizationData.addAction(self.actionMenuPeakFitting)
        self.menuAnalysisVisualizationData.addAction(self.actionMenuBandRatio)
        self.menuAnalysisVisualizationData.addAction(self.actionMenuReferenceMatching)
        self.menuAnalysisVisualizationData.addAction(self.actionMenuMeltingCurve)
        self.menuAnalysisVisualizationData.addAction(self.actionMenuIsosbesticPoint)
        self.menuAnalysisVisualizationData.addAction(self.actionMenuKineticsFitting)
        self.menuAnalysisVisualizationData.addAction(self.actionMenuQCOutlier)

        self.menuAnalysisVisualization.addMenu(self.menuAnalysisVisualizationViz)
        self.menuAnalysisVisualization.addMenu(self.menuAnalysisVisualizationData)

        # Help menu
        self.menuHelp = QMenu(self.menuBar)
        self.menuHelp.setObjectName("menuHelp")
        self.menuHelp.setTitle("Help")
        
        # Create "Spectra Processing" submenu for Help — mirrors the pipeline tree
        self.menuSpectraProcessing = QMenu(self.menuHelp)
        self.menuSpectraProcessing.setObjectName("menuSpectraProcessing")
        self.menuSpectraProcessing.setTitle("Spectra Processing")

        # Baseline Correction submenu
        self.menuHelpBaselineCorrection = QMenu(self.menuSpectraProcessing)
        self.menuHelpBaselineCorrection.setObjectName("menuHelpBaselineCorrection")
        self.menuHelpBaselineCorrection.setTitle("Baseline Correction")

        # Smoothing submenu
        self.menuHelpSmoothing = QMenu(self.menuSpectraProcessing)
        self.menuHelpSmoothing.setObjectName("menuHelpSmoothing")
        self.menuHelpSmoothing.setTitle("Smoothing")

        # Data Manipulation submenu
        self.menuHelpDataManipulation = QMenu(self.menuSpectraProcessing)
        self.menuHelpDataManipulation.setObjectName("menuHelpDataManipulation")
        self.menuHelpDataManipulation.setTitle("Data Manipulation")

        # Axis & Unit Conversion submenu — mirrors menuOpsAxisUnitConversion.
        self.menuHelpAxisUnitConversion = QMenu(self.menuSpectraProcessing)
        self.menuHelpAxisUnitConversion.setObjectName("menuHelpAxisUnitConversion")
        self.menuHelpAxisUnitConversion.setTitle("Axis && Unit Conversion")

        # Analysis submenu
        self.menuHelpAnalysis = QMenu(self.menuSpectraProcessing)
        self.menuHelpAnalysis.setObjectName("menuHelpAnalysis")
        self.menuHelpAnalysis.setTitle("Analysis")

        self.menuHelpResolution = QMenu(self.menuSpectraProcessing)
        self.menuHelpResolution.setObjectName("menuHelpResolution")
        self.menuHelpResolution.setTitle("Resolution")

        # Batch Pipeline submenu — mirrors menuOpsBatchPipeline.
        self.menuHelpBatchPipeline = QMenu(self.menuSpectraProcessing)
        self.menuHelpBatchPipeline.setObjectName("menuHelpBatchPipeline")
        self.menuHelpBatchPipeline.setTitle("Batch Pipeline")

        # User guide help
        self.actionUserGuide = QAction(self)
        self.actionUserGuide.setObjectName("actionUserGuide")
        self.actionUserGuide.setText("User Guide")

        # Quick Start — short single-page orientation (workflow, import,
        # every processing/analysis operation's help linked from one table,
        # save, test datasets, contact), for anyone who wants a fast
        # starting point instead of the full User Guide.
        self.actionQuickStart = QAction(self)
        self.actionQuickStart.setObjectName("actionQuickStart")
        self.actionQuickStart.setText("Quick Start")

        # Installation — how to get/run the application itself (installer,
        # from source, building your own installer), as opposed to how to
        # use it once it's running.
        self.actionInstallationHelp = QAction(self)
        self.actionInstallationHelp.setObjectName("actionInstallationHelp")
        self.actionInstallationHelp.setText("Installation")

        # Developer guide help — codebase architecture/conventions, for
        # anyone reading or extending the source rather than just using
        # the application.
        self.actionDeveloperGuide = QAction(self)
        self.actionDeveloperGuide.setObjectName("actionDeveloperGuide")
        self.actionDeveloperGuide.setText("Developer Guide")
 
        # Operations help actions
        self.actionDataRangeHelp = QAction(self)
        self.actionDataRangeHelp.setObjectName("actionDataRangeHelp")
        self.actionDataRangeHelp.setText("Data Range")
        
        self.actionNormalizationHelp = QAction(self)
        self.actionNormalizationHelp.setObjectName("actionNormalizationHelp")
        self.actionNormalizationHelp.setText("Normalization")

        self.actionXAxisAlignmentHelp = QAction(self)
        self.actionXAxisAlignmentHelp.setObjectName("actionXAxisAlignmentHelp")
        self.actionXAxisAlignmentHelp.setText("X-Axis Alignment")

        self.actionSVDInterpolationHelp = QAction(self)
        self.actionSVDInterpolationHelp.setObjectName("actionSVDInterpolationHelp")
        self.actionSVDInterpolationHelp.setText("SVD Interpolation")

        self.actionCDUnitConversionHelp = QAction(self)
        self.actionCDUnitConversionHelp.setObjectName("actionCDUnitConversionHelp")
        self.actionCDUnitConversionHelp.setText("CD Unit Conversion")

        self.actionXAxisUnitConversionHelp = QAction(self)
        self.actionXAxisUnitConversionHelp.setObjectName("actionXAxisUnitConversionHelp")
        self.actionXAxisUnitConversionHelp.setText("X-axis Unit Conversion")

        self.actionMeanCenteringHelp = QAction(self)
        self.actionMeanCenteringHelp.setObjectName("actionMeanCenteringHelp")
        self.actionMeanCenteringHelp.setText("Mean-Center Spectra (Dataset)")

        self.actionSpikeRemovalHelp = QAction(self)
        self.actionSpikeRemovalHelp.setObjectName("actionSpikeRemovalHelp")
        self.actionSpikeRemovalHelp.setText("Spike Removal")

        self.actionBatchPipelineHelp = QAction(self)
        self.actionBatchPipelineHelp.setObjectName("actionBatchPipelineHelp")
        self.actionBatchPipelineHelp.setText("Batch Pipeline")

        self.actionSGSmoothingHelp = QAction(self)
        self.actionSGSmoothingHelp.setObjectName("actionSGSmoothingHelp")
        self.actionSGSmoothingHelp.setText("SG-Smoothing")
        
        self.actionSpectralCalculatorHelp = QAction(self)
        self.actionSpectralCalculatorHelp.setObjectName("actionSpectralCalculatorHelp")
        self.actionSpectralCalculatorHelp.setText("Spectral Calculator")

        self.actionFFTDenoisingHelp = QAction(self)
        self.actionFFTDenoisingHelp.setObjectName("actionFFTDenoisingHelp")
        self.actionFFTDenoisingHelp.setText("FFT Denoising")

        self.actionManualBaselineHelp = QAction(self)
        self.actionManualBaselineHelp.setObjectName("actionManualBaselineHelp")
        self.actionManualBaselineHelp.setText("Manual Baseline")
        
        self.actionSVDBackgroundHelp = QAction(self)
        self.actionSVDBackgroundHelp.setObjectName("actionSVDBackgroundHelp")
        self.actionSVDBackgroundHelp.setText("SVD Background")

        self.actionInteractiveSubtractionHelp = QAction(self)
        self.actionInteractiveSubtractionHelp.setObjectName("actionInteractiveSubtractionHelp")
        self.actionInteractiveSubtractionHelp.setText("Interactive Subtraction")
        
        self.actionCombineSpectraHelp = QAction(self)
        self.actionCombineSpectraHelp.setObjectName("actionCombineSpectraHelp")
        self.actionCombineSpectraHelp.setText("Combine Spectra") 
        
        self.actionAutomatedBaselineHelp = QAction(self)
        self.actionAutomatedBaselineHelp.setObjectName("actionAutomatedBaselineHelp")
        self.actionAutomatedBaselineHelp.setText("Automated Baseline")

        self.actionSNIPBaselineHelp = QAction(self)
        self.actionSNIPBaselineHelp.setObjectName("actionSNIPBaselineHelp")
        self.actionSNIPBaselineHelp.setText("SNIP Baseline")  
        
        self.actionPeakFittingHelp = QAction(self)
        self.actionPeakFittingHelp.setObjectName("actionPeakFittingHelp")
        self.actionPeakFittingHelp.setText("Peak Fitting")

        self.actionBandRatioHelp = QAction(self)
        self.actionBandRatioHelp.setObjectName("actionBandRatioHelp")
        self.actionBandRatioHelp.setText("Band Ratio")

        self.actionReferenceMatchingHelp = QAction(self)
        self.actionReferenceMatchingHelp.setObjectName("actionReferenceMatchingHelp")
        self.actionReferenceMatchingHelp.setText("Reference Matching")

        self.actionReferenceMatchingHelpViz = QAction(self)
        self.actionReferenceMatchingHelpViz.setObjectName("actionReferenceMatchingHelpViz")
        self.actionReferenceMatchingHelpViz.setText("Reference Matching")

        self.actionMeltingCurveHelp = QAction(self)
        self.actionMeltingCurveHelp.setObjectName("actionMeltingCurveHelp")
        self.actionMeltingCurveHelp.setText("Melting Curve Analysis")

        self.actionIsosbesticPointHelp = QAction(self)
        self.actionIsosbesticPointHelp.setObjectName("actionIsosbesticPointHelp")
        self.actionIsosbesticPointHelp.setText("Isosbestic Point Detection")

        self.actionKineticsFittingHelp = QAction(self)
        self.actionKineticsFittingHelp.setObjectName("actionKineticsFittingHelp")
        self.actionKineticsFittingHelp.setText("Kinetics Fitting")

        self.actionQCOutlierHelp = QAction(self)
        self.actionQCOutlierHelp.setObjectName("actionQCOutlierHelp")
        self.actionQCOutlierHelp.setText("QC / Outlier Detection")

        self.actionPcaScoresHelp = QAction(self)
        self.actionPcaScoresHelp.setObjectName("actionPcaScoresHelp")
        self.actionPcaScoresHelp.setText("PCA Scores & Loadings")

        self.actionNMFHelp = QAction(self)
        self.actionNMFHelp.setObjectName("actionNMFHelp")
        self.actionNMFHelp.setText("NMF")

        self.actionMCRALSHelp = QAction(self)
        self.actionMCRALSHelp.setObjectName("actionMCRALSHelp")
        self.actionMCRALSHelp.setText("MCR-ALS")

        self.actionCosmicRayHelp = QAction(self)
        self.actionCosmicRayHelp.setObjectName("actionCosmicRayHelp")
        self.actionCosmicRayHelp.setText("Cosmic Ray Removal")

        self.actionResolutionHelp = QAction(self)
        self.actionResolutionHelp.setObjectName("actionResolutionHelp")
        self.actionResolutionHelp.setText("Resolution Enhancement")

        # Spectra Visualization submenu
        self.menuHelpVisualization = QMenu(self.menuHelp)
        self.menuHelpVisualization.setObjectName("menuHelpVisualization")
        self.menuHelpVisualization.setTitle("Spectra Analysis && Visualization")

        self.menuHelpVizVisualization = QMenu(self.menuHelpVisualization)
        self.menuHelpVizVisualization.setObjectName("menuHelpVizVisualization")
        self.menuHelpVizVisualization.setTitle("Visualization")

        self.menuHelpVizDataAnalysis = QMenu(self.menuHelpVisualization)
        self.menuHelpVizDataAnalysis.setObjectName("menuHelpVizDataAnalysis")
        self.menuHelpVizDataAnalysis.setTitle("Data Analysis")

        # Test datasets — synthetic benchmark files shipped with the app under
        # resources/test_data/synthetic/. Each action opens one dataset's
        # Spectra sheet straight into the application, so a user can try
        # MCR-ALS / NMF against data whose TRUE components and concentrations
        # are known (the other sheets of each workbook hold that ground truth).
        # Actions are generated from SYNTHETIC_TEST_DATASETS rather than
        # hand-declared, so adding a dataset means adding one line there.
        self.menuHelpTestDatasets = QMenu(self.menuHelp)
        self.menuHelpTestDatasets.setObjectName("menuHelpTestDatasets")
        self.menuHelpTestDatasets.setTitle("Test datasets")

        self.menuHelpTestDatasetsSynthetic = QMenu(self.menuHelpTestDatasets)
        self.menuHelpTestDatasetsSynthetic.setObjectName("menuHelpTestDatasetsSynthetic")
        self.menuHelpTestDatasetsSynthetic.setTitle("Synthetic")

        # Each distinct group (see SYNTHETIC_TEST_DATASETS's first tuple
        # element) becomes its own submenu, rather than one long flat list
        # separated only by dividers — the flat version had grown to ~30
        # entries, making it hard to scan for one spectroscopy type. The
        # group key -> submenu title mapping mirrors the descriptive
        # prefix each group's own labels already used before this change.
        _SYNTHETIC_GROUP_TITLES = {
            'raman':   'Raman',
            'uvvis':   'UV/Vis',
            'cd':      'CD (signed)',
            'roa':     'ROA/VCD (signed)',
            'closed':  'Closed system (DNA melting)',
            'melting': 'Melting curve',
            'pls':     'PLS / PLS-DA',
            'kinetics': 'Kinetics Fitting',
            'qc':      'QC / Outlier Detection',
            'xaxis':   'X-Axis Alignment',
            'som':     'Self-Organizing Map (SOM)',
        }

        # label -> filename; the controller resolves the folder and imports it.
        self.synthetic_dataset_actions = {}
        self._synthetic_group_menus = {}
        for _group, _label, _fname in SYNTHETIC_TEST_DATASETS:
            _group_menu = self._synthetic_group_menus.get(_group)
            if _group_menu is None:
                _group_menu = QMenu(self.menuHelpTestDatasetsSynthetic)
                _group_menu.setObjectName(f"menuHelpTestDatasetsSynthetic_{_group}")
                _group_menu.setTitle(_SYNTHETIC_GROUP_TITLES.get(_group, _group.title()))
                self.menuHelpTestDatasetsSynthetic.addMenu(_group_menu)
                self._synthetic_group_menus[_group] = _group_menu
            _act = QAction(self)
            _act.setObjectName(f"actionSyntheticDataset_{_fname.replace('.', '_')}")
            _act.setText(_label)
            _sheet_note = " (Spectra sheet)" if _fname.lower().endswith(('.xlsx', '.xls', '.xlsm')) else ""
            _act.setToolTip(f"Open {_fname}{_sheet_note} in the application")
            _group_menu.addAction(_act)
            self.synthetic_dataset_actions[_fname] = _act

        # "Real" — measured (experimental) datasets, as opposed to the
        # synthetic ones whose ground truth is known by construction. Kept as a
        # sibling of Synthetic so the distinction stays obvious: with real data
        # the true components are NOT known, so nothing here can be checked
        # against a ground truth. Currently a placeholder; drop .xlsx files into
        # resources/test_data/real/ and list them in REAL_TEST_DATASETS.
        self.menuHelpTestDatasetsReal = QMenu(self.menuHelpTestDatasets)
        self.menuHelpTestDatasetsReal.setObjectName("menuHelpTestDatasetsReal")
        self.menuHelpTestDatasetsReal.setTitle("Real (measured)")

        self.real_dataset_actions = {}
        for _label, _fname in REAL_TEST_DATASETS:
            _act = QAction(self)
            _act.setObjectName(f"actionRealDataset_{_fname.replace('.', '_')}")
            _act.setText(_label)
            _act.setToolTip(f"Open {_fname} in the application")
            self.menuHelpTestDatasetsReal.addAction(_act)
            self.real_dataset_actions[_fname] = _act

        if not REAL_TEST_DATASETS:
            _none = QAction(self)
            _none.setText("(no measured datasets installed)")
            _none.setEnabled(False)
            self.menuHelpTestDatasetsReal.addAction(_none)

        # "2D maps" — its own submenu of Real (measured), since a spatial
        # map needs to be opened as a whole (2D Map dialog reads its
        # row/col geometry from every spectrum, see Map2DDialog), unlike
        # the two single-series datasets above.
        self.menuHelpTestDatasets2DMaps = QMenu(self.menuHelpTestDatasetsReal)
        self.menuHelpTestDatasets2DMaps.setObjectName("menuHelpTestDatasets2DMaps")
        self.menuHelpTestDatasets2DMaps.setTitle("2D maps")
        for _label, _fname in REAL_TEST_DATASETS_2D_MAPS:
            _act = QAction(self)
            _act.setObjectName(f"actionRealDataset_{_fname.replace('/', '_').replace('.', '_')}")
            _act.setText(_label)
            _act.setToolTip(f"Open {_fname} in the application")
            self.menuHelpTestDatasets2DMaps.addAction(_act)
            self.real_dataset_actions[_fname] = _act
        self.menuHelpTestDatasetsReal.addMenu(self.menuHelpTestDatasets2DMaps)

        self.actionOpenRealFolder = QAction(self)
        self.actionOpenRealFolder.setObjectName("actionOpenRealFolder")
        self.actionOpenRealFolder.setText("Open datasets folder…")
        self.menuHelpTestDatasetsReal.addSeparator()
        self.menuHelpTestDatasetsReal.addAction(self.actionOpenRealFolder)

        self.actionDownloadLargeDatasets = QAction(self)
        self.actionDownloadLargeDatasets.setObjectName("actionDownloadLargeDatasets")
        self.actionDownloadLargeDatasets.setText("Download large test datasets…")
        self.actionDownloadLargeDatasets.setToolTip(
            "Fetch additional real-data 2D maps too large to ship in the "
            "git repository (available when running from source)."
        )
        self.menuHelpTestDatasetsReal.addAction(self.actionDownloadLargeDatasets)

        self.menuHelpTestDatasets.addAction(self.menuHelpTestDatasetsSynthetic.menuAction())
        self.menuHelpTestDatasets.addAction(self.menuHelpTestDatasetsReal.menuAction())

        # Reveal the folder itself, for the ground-truth sheets / README.
        self.actionOpenSyntheticFolder = QAction(self)
        self.actionOpenSyntheticFolder.setObjectName("actionOpenSyntheticFolder")
        self.actionOpenSyntheticFolder.setText("Open datasets folder…")
        self.menuHelpTestDatasetsSynthetic.addSeparator()
        self.menuHelpTestDatasetsSynthetic.addAction(self.actionOpenSyntheticFolder)

        self.actionSVDAnalysisHelp = QAction(self)
        self.actionSVDAnalysisHelp.setObjectName("actionSVDAnalysisHelp")
        self.actionSVDAnalysisHelp.setText("SVD Analysis")

        self.actionClusterAnalysisHelp = QAction(self)
        self.actionClusterAnalysisHelp.setObjectName("actionClusterAnalysisHelp")
        self.actionClusterAnalysisHelp.setText("Cluster Analysis")

        self.actionSOMHelp = QAction(self)
        self.actionSOMHelp.setObjectName("actionSOMHelp")
        self.actionSOMHelp.setText("SOM")

        self.actionPLSHelp = QAction(self)
        self.actionPLSHelp.setObjectName("actionPLSHelp")
        self.actionPLSHelp.setText("PLS / PLS-DA")


        self.action2DMapHelp = QAction(self)
        self.action2DMapHelp.setObjectName("action2DMapHelp")
        self.action2DMapHelp.setText("2D Map")        

        self.action2DCorrelationHelp = QAction(self)
        self.action2DCorrelationHelp.setObjectName("action2DCorrelationHelp")
        self.action2DCorrelationHelp.setText("2D Correlation")

        # Existing help actions
        self.actionOur_Group = QAction(self)
        self.actionOur_Group.setObjectName("actionOur_Group")
        self.actionOur_Group.setText("Our Group")
        
        self.actionOur_Institute = QAction(self)
        self.actionOur_Institute.setObjectName("actionOur_Institute")
        self.actionOur_Institute.setText("Our Institute")

        # License — GPL-3.0. Links to the formal LICENSE file, the
        # plain-language installer_assets/license.txt, and the Developer
        # Guide's licensing-intent section.
        self.actionLicense = QAction(self)
        self.actionLicense.setObjectName("actionLicense")
        self.actionLicense.setText("License")

        # Other existing actions
        self.actionSave = QAction(self)
        self.actionSave.setObjectName("actionSave")
        self.actionSave.setText("Save")
        
        self.actionImport_new = QAction(self)
        self.actionImport_new.setObjectName("actionImport_new")
        self.actionImport_new.setText("new")
        
        self.actionImport_add = QAction(self)
        self.actionImport_add.setObjectName("actionImport_add")
        self.actionImport_add.setText("add")

        self.actionImport_Snapshot = QAction(self)
        self.actionImport_Snapshot.setObjectName("actionImport_Snapshot")
        self.actionImport_Snapshot.setText("Import Snapshot")
        
        # Baseline Correction submenu
        self.menuHelpBaselineCorrection.addAction(self.actionManualBaselineHelp)
        self.menuHelpBaselineCorrection.addAction(self.actionAutomatedBaselineHelp)
        self.menuHelpBaselineCorrection.addAction(self.actionSNIPBaselineHelp)
        self.menuHelpBaselineCorrection.addAction(self.actionSVDBackgroundHelp)

        # Smoothing submenu
        self.menuHelpSmoothing.addAction(self.actionSGSmoothingHelp)
        self.menuHelpSmoothing.addAction(self.actionFFTDenoisingHelp)

        # Data Manipulation submenu
        self.menuHelpDataManipulation.addAction(self.actionDataRangeHelp)
        self.menuHelpDataManipulation.addAction(self.actionCombineSpectraHelp)
        self.menuHelpDataManipulation.addAction(self.actionInteractiveSubtractionHelp)
        self.menuHelpDataManipulation.addAction(self.actionXAxisAlignmentHelp)
        self.menuHelpDataManipulation.addAction(self.actionSVDInterpolationHelp)

        self.menuHelpAxisUnitConversion.addAction(self.actionSpectralCalculatorHelp)
        self.menuHelpAxisUnitConversion.addAction(self.actionNormalizationHelp)
        self.menuHelpAxisUnitConversion.addAction(self.actionCDUnitConversionHelp)
        self.menuHelpAxisUnitConversion.addAction(self.actionXAxisUnitConversionHelp)
        self.menuHelpAxisUnitConversion.addAction(self.actionMeanCenteringHelp)

        # Spike Removal — own submenu matching the CATEGORIES tree
        self.menuHelpSpikeRemoval = QMenu(self.menuSpectraProcessing)
        self.menuHelpSpikeRemoval.setObjectName("menuHelpSpikeRemoval")
        self.menuHelpSpikeRemoval.setTitle("Spike Removal")
        self.menuHelpSpikeRemoval.addAction(self.actionSpikeRemovalHelp)

        # Analysis submenu
        # Analysis submenu: Peak Fitting, Band Ratio, Reference Matching, Melting Curve Analysis
        self.menuHelpAnalysis.addAction(self.actionPeakFittingHelp)
        self.menuHelpAnalysis.addAction(self.actionBandRatioHelp)
        self.menuHelpAnalysis.addAction(self.actionReferenceMatchingHelp)
        self.menuHelpAnalysis.addAction(self.actionMeltingCurveHelp)
        self.menuHelpAnalysis.addAction(self.actionIsosbesticPointHelp)
        self.menuHelpAnalysis.addAction(self.actionKineticsFittingHelp)
        self.menuHelpAnalysis.addAction(self.actionQCOutlierHelp)
        # Spike Removal submenu
        self.menuHelpSpikeRemoval.addAction(self.actionCosmicRayHelp)
        # Resolution submenu
        self.menuHelpResolution.addAction(self.actionResolutionHelp)
        # Batch Pipeline submenu
        self.menuHelpBatchPipeline.addAction(self.actionBatchPipelineHelp)
        # Visualization submenu: SVD, PCA, NMF, MCR-ALS, Cluster, 2D Map, 2D Correlation
        self.menuHelpVizVisualization.addAction(self.actionSVDAnalysisHelp)
        self.menuHelpVizVisualization.addAction(self.actionPcaScoresHelp)
        self.menuHelpVizVisualization.addAction(self.actionNMFHelp)
        self.menuHelpVizVisualization.addAction(self.actionMCRALSHelp)
        self.menuHelpVizVisualization.addAction(self.actionClusterAnalysisHelp)
        self.menuHelpVizVisualization.addAction(self.actionSOMHelp)
        self.menuHelpVizVisualization.addAction(self.action2DMapHelp)
        self.menuHelpVizVisualization.addAction(self.action2DCorrelationHelp)
        self.menuHelpVizVisualization.addAction(self.actionPLSHelp)
        # Data Analysis submenu: Peak Fitting, Band Ratio, Reference Matching, Melting Curve Analysis
        self.menuHelpVizDataAnalysis.addAction(self.actionPeakFittingHelp)
        self.menuHelpVizDataAnalysis.addAction(self.actionBandRatioHelp)
        self.menuHelpVizDataAnalysis.addAction(self.actionReferenceMatchingHelpViz)
        self.menuHelpVizDataAnalysis.addAction(self.actionMeltingCurveHelp)
        self.menuHelpVizDataAnalysis.addAction(self.actionIsosbesticPointHelp)
        self.menuHelpVizDataAnalysis.addAction(self.actionKineticsFittingHelp)
        self.menuHelpVizDataAnalysis.addAction(self.actionQCOutlierHelp)

        # Assemble Spectra Processing menu
        self.menuSpectraProcessing.addAction(self.menuHelpBaselineCorrection.menuAction())
        self.menuSpectraProcessing.addAction(self.menuHelpSmoothing.menuAction())
        self.menuSpectraProcessing.addAction(self.menuHelpDataManipulation.menuAction())
        self.menuSpectraProcessing.addAction(self.menuHelpAxisUnitConversion.menuAction())
        self.menuSpectraProcessing.addAction(self.menuHelpSpikeRemoval.menuAction())
        self.menuSpectraProcessing.addAction(self.menuHelpResolution.menuAction())
        self.menuSpectraProcessing.addAction(self.menuHelpBatchPipeline.menuAction())

        # Spectra Visualization submenu
        # Add submenus to visualization menu
        self.menuHelpVisualization.addAction(self.menuHelpVizVisualization.menuAction())
        self.menuHelpVisualization.addAction(self.menuHelpVizDataAnalysis.menuAction())

        # Assemble Help menu
        self.menuHelp.addAction(self.actionUserGuide)
        self.menuHelp.addAction(self.actionQuickStart)
        self.menuHelp.addAction(self.actionInstallationHelp)
        self.menuHelp.addAction(self.actionDeveloperGuide)
        self.menuHelp.addSeparator()
        self.menuHelp.addAction(self.menuSpectraProcessing.menuAction())
        self.menuHelp.addAction(self.menuHelpVisualization.menuAction())
        self.menuHelp.addAction(self.menuHelpTestDatasets.menuAction())
        self.menuHelp.addSeparator()
        self.menuHelp.addAction(self.actionOur_Group)
        self.menuHelp.addAction(self.actionOur_Institute)
        self.menuHelp.addSeparator()
        self.menuHelp.addAction(self.actionLicense)

        # Add actions to other menus
        self.menuImport.addAction(self.actionImport_new)
        self.menuImport.addAction(self.actionImport_add)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.menuImport.menuAction())
        self.menuFile.addAction(self.actionImport_Snapshot)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionSave)
        
        # Add menus to menu bar
        self.menuBar.addAction(self.menuFile.menuAction())
        self.menuBar.addAction(self.menuView.menuAction())
        self.menuBar.addAction(self.menuSpectraProcessingOps.menuAction())
        self.menuBar.addAction(self.menuAnalysisVisualization.menuAction())
        self.menuBar.addAction(self.menuHelp.menuAction())


    def init_ui(self):
        """Initialize UI components with window title and icon."""
        self.setWindowTitle("SpecAnalytiXBase")
        icon_path = resource_path(os.path.join('resources', 'icons', 'app_icon.ico'))
        self.setWindowIcon(QIcon(icon_path))