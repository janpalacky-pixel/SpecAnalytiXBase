# src/views/dialogs/data_analysis/automated_baseline_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QSlider, QLabel, QDialogButtonBox, QListWidget,
                             QWidget, QSplitter, QSizePolicy, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
                             QComboBox, QStackedWidget, QTabWidget, QFrame,
                             QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator,
                             QAbstractItemView, QApplication, QMessageBox, QSpinBox)
from PyQt5.QtCore import Qt, pyqtSignal, QEvent
from PyQt5.QtGui import QFont
import os
import time
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import numpy as np

from src.modules.data_analysis.automated_baseline_manager import AutomatedBaselineManager
from src.modules.data_analysis.baseline_region_presets import REGION_PRESET_CATEGORIES, find_preset
from src.help.automated_baseline_help import (get_automated_baseline_help_content,
                                              get_automated_baseline_help_title)
from src.help.help_window import show_help_window
from src.modules.utils.label_shortening import make_shortened_name_delegate, make_shorten_names_checkbox


BASELINE_METHOD_INFO = {
    'als': {
        'label': 'ALS (Asymmetric Least Squares)',
        'info': (
            "The classic Eilers/Boelens asymmetric least squares baseline: "
            "iteratively refits a smooth curve -- controlled by the "
            "Smoothness (\u03bb) slider, a curvature penalty -- while "
            "down-weighting points that sit above the fit by a factor of "
            "1-p (the Asymmetry slider). Most of the other ALS-family "
            "methods below are refinements of this same idea -- start "
            "here if you're not sure which one to pick."
        ),
    },
    'airpls': {
        'label': 'airPLS (adaptive iteratively reweighted PLS)',
        'info': (
            "airPLS usually needs a much smaller \u03bb than ALS -- use "
            "the preview to find a value that follows the background "
            "without dipping into the peaks. It has no asymmetry "
            "parameter of its own: its weighting is derived adaptively "
            "from the residuals each iteration, rather than a fixed p."
        ),
    },
    'arpls': {
        'label': 'arPLS (asymmetrically reweighted PLS)',
        'info': (
            "arPLS re-weights points by how far below a data-driven "
            "threshold their residual sits, rather than airPLS's "
            "exponential growth -- often a bit steadier on noisy data. "
            "Use the preview to compare against ALS/airPLS on your own "
            "spectra."
        ),
    },
    'iarpls': {
        'label': 'iarPLS (improved arPLS)',
        'info': (
            "A fix for arPLS's known tendency to overestimate the "
            "baseline under small peaks in noisy data -- same \u03bb "
            "slider, different internal weighting. Try this first if "
            "arPLS seems to sit a bit high under small peaks."
        ),
    },
    'aspls': {
        'label': 'asPLS (adaptive smoothness PLS)',
        'info': (
            "Another arPLS-style method, but the smoothness penalty "
            "itself adapts point-by-point to the residuals instead of "
            "being applied uniformly -- stiffer where the fit is "
            "confident, looser near features it's still unsure about."
        ),
    },
    'drpls': {
        'label': 'drPLS (doubly reweighted PLS)',
        'info': (
            "Higher \u03b7 (Peak Relaxation) lets peak regions relax "
            "more independently of the surrounding baseline's "
            "smoothness -- 0 behaves closest to arPLS, 1 relaxes the "
            "peak-region penalty the most."
        ),
    },
    'psalsa': {
        'label': 'psalsa (peak-decay asymmetric least squares)',
        'info': (
            "Peaks are suppressed by exponential decay rather than a "
            "hard cutoff, which is why a higher p than ALS's still "
            "works well here. The decay's own peak-height scale (k) is "
            "set automatically from the spectrum's noise level."
        ),
    },
    'imodpoly': {
        'label': 'I-ModPoly (improved modified polynomial fit)',
        'info': (
            "A single low-order polynomial fit to the whole spectrum, "
            "with peaks iteratively rejected from the fit -- good for "
            "smooth, broadly-curved fluorescence backgrounds. Higher "
            "orders follow more background curvature but risk fitting "
            "into broad peaks; use the preview to check."
        ),
    },
    'morphological': {
        'label': 'Morphological Opening (adaptive structuring element)',
        'info': (
            "Fully automatic -- no parameters to tune. Repeatedly opens "
            "the spectrum with a growing structuring element until the "
            "result stops changing, then refines it to correct for "
            "band-shape distortion. Good for smooth backgrounds that "
            "don't fit a fixed polynomial order or global penalty."
        ),
    },
    'mpls': {
        'label': 'mpls (morphological weighted PLS)',
        'info': (
            "Morphological opening picks a handful of trustworthy "
            "\"anchor\" points and solves ALS's own penalty once -- no "
            "iterative reweighting. Anchor points always get weight "
            "1-p; the Non-Anchor Weight slider sets everyone else's "
            "weight, 0 by default (ignored entirely)."
        ),
    },
    'mollification': {
        'label': 'Morphology + Mollification (Koch/Suhr; Chen/Xu/Broderick)',
        'info': (
            "Fully automatic -- no parameters to tune. Each pass takes "
            "the smaller of the raw spectrum and the average of a "
            "morphological closing/opening of the current baseline "
            "estimate, then smooths that with a fixed \"mollifier\" "
            "kernel, repeating until the result stops changing. Good "
            "when a background's morphology already makes the baseline "
            "fairly obvious, without an iterative-reweighting or "
            "single-solve method's own assumptions."
        ),
    },
    'mpspline': {
        'label': 'mpspline (morphology-based penalized spline)',
        'info': (
            "Like mpls, morphology picks a handful of trustworthy "
            "\"anchor\" points and fits once -- no iterative "
            "reweighting. Here the fit is a cubic penalized spline "
            "(fewer effective degrees of freedom than mpls's own "
            "point-by-point solve) rather than a direct Whittaker "
            "smoother. Anchor points always get weight 1-p; the "
            "Non-Anchor Weight slider sets everyone else's weight, 0 by "
            "default."
        ),
    },
    'jbcd': {
        'label': 'jbcd (joint baseline-correction and denoising)',
        'info': (
            "Jointly solves for a smooth baseline AND a denoised "
            "spectrum, rather than picking anchor points from "
            "morphology and fitting once. \u03b1 pulls the baseline "
            "toward the morphological opening; \u03b2 caps how "
            "strongly the baseline is smoothed as the fit anneals. "
            "Slower than the other morphology-family methods, but "
            "doesn't depend on picking good anchor points."
        ),
    },
}

class _MethodTreeCombo(QWidget):
    """Categorised dropdown for "Baseline Method".

    Eleven methods in one flat QComboBox made the list hard to scan and
    easy to under-scroll (see the "Morphology + Mollification" visibility
    report this replaced) -- picking a method now means scanning within
    a small family rather than a flat list of eleven similar-sounding
    names. Visually and mechanically modelled on
    main_window.OperationTreeComboBox (the same button + Qt.Popup +
    QTreeWidget pattern, the same styling, the same category-header-is-
    not-selectable / outside-click-closes / follows-the-window behaviour)
    so the app has one consistent "hierarchical dropdown" feel, but kept
    as its own small class here rather than reusing or subclassing
    OperationTreeComboBox: that class's public surface
    (currentText()/currentTextChanged/addItems()/clear()) is tailored to
    OperationsController's plain-text menu and has no notion of a
    per-item data key, whereas everything in this dialog --
    apply_correction() dispatch, load_settings()/get_settings(), the
    Operations Summary table, the test suite -- already selects and
    restores algorithms by their short key ('als', 'mpls', ...), never
    by display string. Reusing OperationTreeComboBox here would mean
    either bolting a data-key concept onto a class the main menu also
    depends on (regression risk there) or re-plumbing this whole dialog
    around display text instead (regression risk here). A local class
    exposing the slice of QComboBox's own API this dialog actually uses
    -- addItem(text, data, category), count(), currentData(),
    currentIndex(), setCurrentIndex(index), itemData(index),
    findData(value), and a currentIndexChanged(int) signal -- means
    _on_method_changed/load_settings/get_settings needed no logic
    changes at all beyond grouping the addItem calls by family; only
    create_control_panel's construction of the widget changed.

    Category headers exist only inside the popup's QTreeWidget -- they
    are not entries in self._items, so the index space handed to
    currentIndexChanged/currentData/itemData is exactly the eleven
    algorithms in the same order as before, with no renumbering needed
    anywhere else in this file (in particular self.params_stack's index
    still mirrors this widget's index 1:1, same as when it was a plain
    QComboBox -- see _on_method_changed).
    """

    currentIndexChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []  # [{'text': str, 'data': object, 'category': str|None}, ...]
        self._current_index = -1
        self._popup_closed_at = 0.0
        self._build_widget()
        self._build_popup()

    # ------------------------------------------------------------------ #
    # Construction                                                        #
    # ------------------------------------------------------------------ #

    def _build_widget(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._button = QPushButton(self)
        self._button.setCursor(Qt.PointingHandCursor)
        self._button.setSizePolicy(QSizePolicy(QSizePolicy.Expanding,
                                               QSizePolicy.Fixed))
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
        # Qt.Popup: always above parent, closes on outside click, correct
        # z-order -- same rationale as OperationTreeComboBox._build_popup.
        self._popup = QFrame(self.window(), Qt.Popup | Qt.FramelessWindowHint)
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
        self._tree.setFocusPolicy(Qt.NoFocus)
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

        self._popup.installEventFilter(self)
        self._tree.installEventFilter(self)
        top = self.window()
        if top is not None:
            top.installEventFilter(self)

    # ------------------------------------------------------------------ #
    # Population -- QComboBox-compatible API                              #
    # ------------------------------------------------------------------ #

    def addItem(self, text, data=None, category=None):
        self._items.append({'text': text, 'data': data, 'category': category})
        if self._current_index == -1:
            self._current_index = 0
        self._rebuild_tree()
        self._update_button_text()

    def count(self):
        return len(self._items)

    def itemData(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]['data']
        return None

    def findData(self, value):
        for i, entry in enumerate(self._items):
            if entry['data'] == value:
                return i
        return -1

    def currentIndex(self):
        return self._current_index

    def currentData(self):
        return self.itemData(self._current_index)

    def setCurrentIndex(self, index):
        if not (0 <= index < len(self._items)) or index == self._current_index:
            return
        self._current_index = index
        self._update_button_text()
        self.currentIndexChanged.emit(index)

    def _rebuild_tree(self):
        self._tree.clear()
        bold = QFont()
        bold.setBold(True)
        category_items = {}
        for i, entry in enumerate(self._items):
            cat_name = entry['category']
            if cat_name is None:
                parent = self._tree
            else:
                cat_item = category_items.get(cat_name)
                if cat_item is None:
                    cat_item = QTreeWidgetItem(self._tree, [cat_name])
                    cat_item.setFont(0, bold)
                    # Category rows: enabled but NOT selectable, same as
                    # OperationTreeComboBox's own category headers.
                    cat_item.setFlags(Qt.ItemIsEnabled)
                    cat_item.setExpanded(True)
                    category_items[cat_name] = cat_item
                parent = cat_item
            leaf = QTreeWidgetItem(parent, [entry['text']])
            leaf.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            leaf.setData(0, Qt.UserRole, i)
        self._tree.expandAll()

    # ------------------------------------------------------------------ #
    # Popup show / hide (same mechanics as OperationTreeComboBox)         #
    # ------------------------------------------------------------------ #

    def _toggle_popup(self):
        if self._popup.isVisible():
            self._close_popup()
            return
        # Same click-vs-deactivate race guard as OperationTreeComboBox.
        if time.monotonic() - self._popup_closed_at < 0.25:
            return
        self._open_popup()

    def _open_popup(self):
        width = max(self._button.width(), 260)
        row_h = max(self._tree.sizeHintForRow(0), 20) if self._tree.topLevelItemCount() else 20
        n_categories = len({e['category'] for e in self._items if e['category']})
        n_rows = len(self._items) + n_categories
        height = min(n_rows * row_h + 8, 340)
        self._popup.setFixedSize(width, height)

        btn_bottom_left = self._button.mapToGlobal(self._button.rect().bottomLeft())
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            y = btn_bottom_left.y()
            if y + height > screen.bottom():
                y = self._button.mapToGlobal(self._button.rect().topLeft()).y() - height
            btn_bottom_left.setY(y)
        except Exception:
            pass

        self._popup.move(btn_bottom_left)
        self._popup.show()
        self._popup.raise_()
        self._sync_tree_selection()

    def _close_popup(self):
        self._popup.hide()
        self._popup_closed_at = time.monotonic()

    def _reposition_popup(self):
        if not self._popup.isVisible():
            return
        btn_bottom_left = self._button.mapToGlobal(self._button.rect().bottomLeft())
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            y = btn_bottom_left.y()
            if y + self._popup.height() > screen.bottom():
                y = self._button.mapToGlobal(self._button.rect().topLeft()).y() - self._popup.height()
            btn_bottom_left.setY(y)
        except Exception:
            pass
        self._popup.move(btn_bottom_left)

    def _sync_tree_selection(self):
        if not (0 <= self._current_index < len(self._items)):
            return
        it = QTreeWidgetItemIterator(self._tree, QTreeWidgetItemIterator.Selectable)
        while it.value():
            item = it.value()
            if item.data(0, Qt.UserRole) == self._current_index:
                self._tree.setCurrentItem(item)
                return
            it += 1

    # ------------------------------------------------------------------ #
    # Event handling                                                       #
    # ------------------------------------------------------------------ #

    def eventFilter(self, obj, event):
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
            # Category header: toggle expand/collapse, same as
            # OperationTreeComboBox.
            item.setExpanded(not item.isExpanded())
            return
        self._close_popup()
        index = item.data(0, Qt.UserRole)
        if index is not None:
            self.setCurrentIndex(index)

    def _update_button_text(self):
        arrow = "  ▾"
        if 0 <= self._current_index < len(self._items):
            label = self._items[self._current_index]['text']
        else:
            label = "Select method..."
        self._button.setText(label + arrow)


class _CurrentPageStackedWidget(QStackedWidget):
    """A QStackedWidget sizes itself to the LARGEST of all its pages
    by default, even while showing a much smaller one -- Qt computes
    sizeHint()/minimumSizeHint() as the max across every page it holds,
    not just the current one. That's why "Method Parameters" used to
    reserve empty vertical space sized for whichever baseline method
    has the most sliders (e.g. JBCD or drPLS, with two sliders each),
    regardless of which method is actually selected (e.g. airPLS, with
    just one). Overriding
    both hints to consider only the CURRENTLY VISIBLE page, and asking
    the layout to recompute (updateGeometry()) whenever the page
    changes via currentChanged (see create_control_panel below), makes
    the groupbox shrink-wrap to whichever method is actually showing.
    """

    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return w.minimumSizeHint() if w is not None else super().minimumSizeHint()


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

        # Draw shaded regions. self.ax.clear() above already removed
        # every previous span (Axes.clear() detaches all its child
        # artists) — this used to ALSO call span.remove() on each one
        # afterward, which was harmless on some matplotlib versions but
        # raises "NotImplementedError: cannot remove artist" on others,
        # since that artist's parent axes reference is already gone by
        # this point. Reproduces on stock (pre-airPLS) code too: draw a
        # second exclusion box in one preview session and it crashes.
        # Only the Python-side bookkeeping list needs clearing here.
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
        self.setWindowTitle("Automated Baseline Correction")
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

        # Load method (algorithm) — switches the stacked parameter panel
        # and, via its currentIndexChanged handler, updates window state;
        # set this first so the lambda restore below lands on the right
        # slider (ALS's and airPLS's lambda sliders are independent, see
        # create_control_panel).
        algorithm = self.current_settings.get('algorithm', 'als')
        method_index = self.method_combo.findData(algorithm)
        if method_index != -1:
            self.method_combo.setCurrentIndex(method_index)

        # Load lambda (smoothness) — ALS
        lam_val = self.current_settings.get('lambda', 1e6) if algorithm == 'als' else 1e6
        slider_lam_val = int(np.clip(10 * np.log10(lam_val), self.lam_slider.minimum(), self.lam_slider.maximum()))
        self.lam_slider.setValue(slider_lam_val)

        # Load p (asymmetry) — ALS only
        p_val = self.current_settings.get('p', 0.01)
        slider_p_val = int(np.clip(p_val * 1000, self.p_slider.minimum(), self.p_slider.maximum()))
        self.p_slider.setValue(slider_p_val)

        # Load lambda (smoothness) — airPLS, independent slider/range
        # from ALS's (see create_control_panel for why airPLS needs a
        # much smaller default).
        airpls_lam_val = self.current_settings.get('lambda', 200.0) if algorithm == 'airpls' else 200.0
        slider_airpls_lam_val = int(np.clip(
            10 * np.log10(airpls_lam_val), self.airpls_lam_slider.minimum(), self.airpls_lam_slider.maximum()))
        self.airpls_lam_slider.setValue(slider_airpls_lam_val)

        # Load lambda (smoothness) — arPLS, its own slider again but on
        # ALS's scale (see create_control_panel for why).
        arpls_lam_val = self.current_settings.get('lambda', 1e5) if algorithm == 'arpls' else 1e5
        slider_arpls_lam_val = int(np.clip(
            10 * np.log10(arpls_lam_val), self.arpls_lam_slider.minimum(), self.arpls_lam_slider.maximum()))
        self.arpls_lam_slider.setValue(slider_arpls_lam_val)

        # Load lambda (smoothness) -- iarPLS, same scale as arPLS's own
        # slider (see create_control_panel).
        iarpls_lam_val = self.current_settings.get('lambda', 1e5) if algorithm == 'iarpls' else 1e5
        slider_iarpls_lam_val = int(np.clip(
            10 * np.log10(iarpls_lam_val), self.iarpls_lam_slider.minimum(), self.iarpls_lam_slider.maximum()))
        self.iarpls_lam_slider.setValue(slider_iarpls_lam_val)

        # Load lambda (smoothness) -- asPLS, its own slider on ALS's
        # scale (see create_control_panel). No separate control for the
        # adaptive alpha weighting -- it isn't user-tunable.
        aspls_lam_val = self.current_settings.get('lambda', 1e6) if algorithm == 'aspls' else 1e6
        slider_aspls_lam_val = int(np.clip(
            10 * np.log10(aspls_lam_val), self.aspls_lam_slider.minimum(), self.aspls_lam_slider.maximum()))
        self.aspls_lam_slider.setValue(slider_aspls_lam_val)

        # Load lambda (smoothness) and eta (peak relaxation) -- drPLS,
        # its own sliders: lambda on arPLS's scale (see
        # create_control_panel), eta on its own 0-1 range.
        drpls_lam_val = self.current_settings.get('lambda', 1e5) if algorithm == 'drpls' else 1e5
        slider_drpls_lam_val = int(np.clip(
            10 * np.log10(drpls_lam_val), self.drpls_lam_slider.minimum(), self.drpls_lam_slider.maximum()))
        self.drpls_lam_slider.setValue(slider_drpls_lam_val)
        drpls_eta_val = self.current_settings.get('eta', 0.5) if algorithm == 'drpls' else 0.5
        slider_drpls_eta_val = int(np.clip(
            drpls_eta_val * 100, self.drpls_eta_slider.minimum(), self.drpls_eta_slider.maximum()))
        self.drpls_eta_slider.setValue(slider_drpls_eta_val)

        # Load lambda (smoothness) and p (asymmetry) -- psalsa, its own
        # sliders again: lambda on ALS's scale (see create_control_panel),
        # p on its own 0.01-0.99 range since psalsa's natural p (0.5)
        # sits far outside ALS's own p slider's range.
        psalsa_lam_val = self.current_settings.get('lambda', 1e6) if algorithm == 'psalsa' else 1e6
        slider_psalsa_lam_val = int(np.clip(
            10 * np.log10(psalsa_lam_val), self.psalsa_lam_slider.minimum(), self.psalsa_lam_slider.maximum()))
        self.psalsa_lam_slider.setValue(slider_psalsa_lam_val)
        psalsa_p_val = self.current_settings.get('p', 0.5) if algorithm == 'psalsa' else 0.5
        slider_psalsa_p_val = int(np.clip(
            psalsa_p_val * 100, self.psalsa_p_slider.minimum(), self.psalsa_p_slider.maximum()))
        self.psalsa_p_slider.setValue(slider_psalsa_p_val)

        # Load polynomial order -- I-ModPoly, no log-scale slider needed
        # since it's a plain small integer, not a smoothness magnitude.
        poly_order_val = self.current_settings.get('poly_order', 5) if algorithm == 'imodpoly' else 5
        self.imodpoly_order_slider.setValue(int(np.clip(
            poly_order_val, self.imodpoly_order_slider.minimum(), self.imodpoly_order_slider.maximum())))

        # Load mpls's own lambda/p -- p defaults to 0.0 here, not
        # ALS/psalsa's defaults, since it means something different
        # (see the params-page comment above).
        mpls_lam_val = self.current_settings.get('lambda', 1e6) if algorithm == 'mpls' else 1e6
        slider_mpls_lam_val = int(np.clip(
            10 * np.log10(mpls_lam_val), self.mpls_lam_slider.minimum(), self.mpls_lam_slider.maximum()))
        self.mpls_lam_slider.setValue(slider_mpls_lam_val)
        mpls_p_val = self.current_settings.get('p', 0.0) if algorithm == 'mpls' else 0.0
        slider_mpls_p_val = int(np.clip(
            mpls_p_val * 100, self.mpls_p_slider.minimum(), self.mpls_p_slider.maximum()))
        self.mpls_p_slider.setValue(slider_mpls_p_val)

        # Load mpspline's own lambda/p -- same p convention as mpls
        # (see BASELINE_METHOD_INFO['mpspline'], shown via the Method
        # Info button), but a different lambda default/scale since
        # mpspline penalizes spline coefficients, not the data grid
        # (see calculate_mpspline_baseline).
        mpspline_lam_val = self.current_settings.get('lambda', 1e4) if algorithm == 'mpspline' else 1e4
        slider_mpspline_lam_val = int(np.clip(
            10 * np.log10(mpspline_lam_val), self.mpspline_lam_slider.minimum(), self.mpspline_lam_slider.maximum()))
        self.mpspline_lam_slider.setValue(slider_mpspline_lam_val)
        mpspline_p_val = self.current_settings.get('p', 0.0) if algorithm == 'mpspline' else 0.0
        slider_mpspline_p_val = int(np.clip(
            mpspline_p_val * 100, self.mpspline_p_slider.minimum(), self.mpspline_p_slider.maximum()))
        self.mpspline_p_slider.setValue(slider_mpspline_p_val)

        # Load jbcd's own alpha/beta -- unlike every lambda/p pair
        # above, these aren't shared with any other algorithm's
        # convention (see calculate_jbcd_baseline's docstring).
        jbcd_alpha_val = self.current_settings.get('alpha', 0.1) if algorithm == 'jbcd' else 0.1
        slider_jbcd_alpha_val = int(np.clip(
            jbcd_alpha_val * 100, self.jbcd_alpha_slider.minimum(), self.jbcd_alpha_slider.maximum()))
        self.jbcd_alpha_slider.setValue(slider_jbcd_alpha_val)
        jbcd_beta_val = self.current_settings.get('beta', 10.0) if algorithm == 'jbcd' else 10.0
        slider_jbcd_beta_val = int(np.clip(
            jbcd_beta_val, self.jbcd_beta_slider.minimum(), self.jbcd_beta_slider.maximum()))
        self.jbcd_beta_slider.setValue(slider_jbcd_beta_val)

        # Load fitting ranges and update the table. current_settings
        # stores plain (start, end) pairs (see get_settings) with no
        # record of which came from a preset checkbox versus a manual
        # drag — reconstruct that by matching each pair's exact value
        # against every known preset's range (presets always contribute
        # their exact, unmodified range, so this is a safe exact-value
        # match, not a fuzzy one). Anything that doesn't match is
        # treated as manually drawn.
        saved_ranges = self.current_settings.get('fitting_ranges', [])
        self.fitting_ranges = [self._range_entry_from_saved(start, end) for start, end in saved_ranges]
        self.update_range_table()
        self._resync_preset_checkboxes_from_ranges()

        # Load invert regions checkbox state
        invert_state = self.current_settings.get('invert_regions', False)
        self.invert_regions_checkbox.setChecked(invert_state)

        # Load processing mode / workers (settings saved before this
        # option existed simply keep the Automatic default).
        mode_index = self.processing_mode_combo.findData(
            self.current_settings.get('processing_mode', 'auto'))
        self.processing_mode_combo.setCurrentIndex(max(0, mode_index))
        self.max_workers_spin.setValue(int(self.current_settings.get('max_workers', 0) or 0))

    def create_control_panel(self):
        widget = QWidget()
        widget.setFixedWidth(400)
        layout = QVBoxLayout(widget)

        # Spectra List for Preview
        spectra_group = QGroupBox("Preview Spectrum")
        spectra_layout = QVBoxLayout()
        self.spectra_list = QListWidget()
        # Expanding (rather than the default Preferred) so this list -- not
        # empty space -- is what grows when other groupboxes in this panel
        # need less vertical room than the layout has available (see the
        # spectra_group stretch factor below, and _CurrentPageStackedWidget's
        # docstring for where that freed room usually comes from).
        self.spectra_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        # Stretch factor 1: every other groupbox in this panel takes
        # exactly its own sizeHint (stretch 0), so this is the one that
        # absorbs whatever vertical space they don't need.
        layout.addWidget(spectra_group, 1)

        # Baseline Method — switches the stacked parameter panel below.
        # userData on each entry is the params['algorithm'] value used
        # throughout the manager/controller ('als' / 'airpls'), so this
        # combo is the single place that string is chosen from.
        method_group = QGroupBox("Baseline Method")
        method_layout = QVBoxLayout()
        self.method_combo = _MethodTreeCombo()
        _ALS_FAMILY = "ALS / Whittaker-smoothing family"
        _POLY_FAMILY = "Polynomial"
        _MORPH_FAMILY = "Morphological family"
        # Labels come from BASELINE_METHOD_INFO (declared above this
        # class) so the dropdown text and the Method Info popup can never
        # drift apart -- see that dict's own docstring comment.
        _M = BASELINE_METHOD_INFO
        self.method_combo.addItem(_M['als']['label'], 'als', _ALS_FAMILY)
        self.method_combo.addItem(_M['airpls']['label'], 'airpls', _ALS_FAMILY)
        self.method_combo.addItem(_M['arpls']['label'], 'arpls', _ALS_FAMILY)
        self.method_combo.addItem(_M['iarpls']['label'], 'iarpls', _ALS_FAMILY)
        self.method_combo.addItem(_M['aspls']['label'], 'aspls', _ALS_FAMILY)
        self.method_combo.addItem(_M['drpls']['label'], 'drpls', _ALS_FAMILY)
        self.method_combo.addItem(_M['psalsa']['label'], 'psalsa', _ALS_FAMILY)
        self.method_combo.addItem(_M['imodpoly']['label'], 'imodpoly', _POLY_FAMILY)
        self.method_combo.addItem(_M['morphological']['label'], 'morphological', _MORPH_FAMILY)
        self.method_combo.addItem(_M['mpls']['label'], 'mpls', _MORPH_FAMILY)
        self.method_combo.addItem(_M['mollification']['label'], 'mollification', _MORPH_FAMILY)
        self.method_combo.addItem(_M['mpspline']['label'], 'mpspline', _MORPH_FAMILY)
        self.method_combo.addItem(_M['jbcd']['label'], 'jbcd', _MORPH_FAMILY)
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        method_layout.addWidget(self.method_combo)

        # "? Method info" -- same pattern as NormalizationDialog's own
        # button: the description that used to sit as a fixed, always-
        # visible QLabel inside each method's params page (wasting
        # vertical space for whichever method's note happened to be
        # longest) now shows on demand instead, for whichever method is
        # currently selected in the combo above.
        self.method_info_button = QPushButton('? Method info')
        self.method_info_button.setToolTip('Show a description of the selected baseline method')
        self.method_info_button.setStyleSheet(
            'QPushButton {'
            '  background-color: #F57C00;'
            '  color: white;'
            '  border: none;'
            '  border-radius: 4px;'
            '  padding: 3px 8px;'
            '  font-weight: bold;'
            '}'
            'QPushButton:hover { background-color: #E65100; }'
        )
        self.method_info_button.clicked.connect(self._show_method_info)
        method_layout.addWidget(self.method_info_button, alignment=Qt.AlignRight)

        method_group.setLayout(method_layout)
        layout.addWidget(method_group)

        # ALS Parameters
        als_params_page = QWidget()
        params_layout = QVBoxLayout(als_params_page)
        params_layout.setContentsMargins(0, 0, 0, 0)
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

        # airPLS Parameters — its own lambda slider/range, independent of
        # ALS's above. airPLS has no asymmetry parameter: its weighting
        # is derived adaptively from the residuals each iteration (see
        # calculate_airpls_baseline). It also typically needs a MUCH
        # smaller lambda than ALS for a comparable fit — ALS's penalty is
        # a second-difference (curvature) penalty, while airPLS's is a
        # first-difference penalty here, which is far more aggressive at
        # flattening broad features at the same nominal lambda value.
        # Default 200 / range ~1e1-1e6 reflects that; use the live
        # preview to tune it for your own data, same as ALS's slider.
        airpls_params_page = QWidget()
        airpls_layout = QVBoxLayout(airpls_params_page)
        airpls_layout.setContentsMargins(0, 0, 0, 0)
        airpls_lam_label = QLabel("Smoothness (λ): 2e2.0")
        self.airpls_lam_slider = QSlider(Qt.Horizontal)
        self.airpls_lam_slider.setRange(10, 60)
        self.airpls_lam_slider.setValue(23)  # 10*log10(200) rounded
        self.airpls_lam_slider.valueChanged.connect(
            lambda v: airpls_lam_label.setText(f"Smoothness (λ): {10**(v/10.0):.3g}"))
        self.airpls_lam_slider.valueChanged.connect(self.update_preview)
        airpls_layout.addWidget(airpls_lam_label); airpls_layout.addWidget(self.airpls_lam_slider)

        # arPLS Parameters -- its own lambda slider, but on ALS's scale
        # (range 20-90 -> 1e2-1e9), not airPLS's much smaller one: arPLS
        # uses the same second-order difference penalty as ALS, unlike
        # airPLS's first-order penalty here, so it needs a comparable
        # lambda magnitude to ALS for a similar-strength fit (see
        # calculate_arpls_baseline's docstring). No asymmetry parameter,
        # same as airPLS -- the weighting is derived adaptively from the
        # residuals each iteration.
        arpls_params_page = QWidget()
        arpls_layout = QVBoxLayout(arpls_params_page)
        arpls_layout.setContentsMargins(0, 0, 0, 0)
        arpls_lam_label = QLabel("Smoothness (λ): 1e5.0")
        self.arpls_lam_slider = QSlider(Qt.Horizontal)
        self.arpls_lam_slider.setRange(20, 90)
        self.arpls_lam_slider.setValue(50)  # 10*log10(1e5)
        self.arpls_lam_slider.valueChanged.connect(
            lambda v: arpls_lam_label.setText(f"Smoothness (λ): 1e{v/10:.1f}"))
        self.arpls_lam_slider.valueChanged.connect(self.update_preview)
        arpls_layout.addWidget(arpls_lam_label); arpls_layout.addWidget(self.arpls_lam_slider)

        # iarPLS Parameters -- its own lambda slider, same scale as
        # arPLS's (arPLS's second-order-penalty solver, unchanged): the
        # improvement over arPLS here is entirely in the per-iteration
        # weight formula (see calculate_iarpls_baseline), not the
        # smoothness penalty, so the slider itself is identical in
        # range/behavior to arPLS's own.
        iarpls_params_page = QWidget()
        iarpls_layout = QVBoxLayout(iarpls_params_page)
        iarpls_layout.setContentsMargins(0, 0, 0, 0)
        iarpls_lam_label = QLabel("Smoothness (λ): 1e5.0")
        self.iarpls_lam_slider = QSlider(Qt.Horizontal)
        self.iarpls_lam_slider.setRange(20, 90)
        self.iarpls_lam_slider.setValue(50)  # 10*log10(1e5)
        self.iarpls_lam_slider.valueChanged.connect(
            lambda v: iarpls_lam_label.setText(f"Smoothness (λ): 1e{v/10:.1f}"))
        self.iarpls_lam_slider.valueChanged.connect(self.update_preview)
        iarpls_layout.addWidget(iarpls_lam_label); iarpls_layout.addWidget(self.iarpls_lam_slider)

        # asPLS Parameters -- its own λ slider, same scale as arPLS's
        # (same second-order-penalty family): the adaptive part (the
        # per-point alpha weighting) has no slider of its own -- it's
        # recomputed automatically from the residuals each iteration,
        # not something the user tunes directly (see
        # calculate_aspls_baseline).
        aspls_params_page = QWidget()
        aspls_layout = QVBoxLayout(aspls_params_page)
        aspls_layout.setContentsMargins(0, 0, 0, 0)
        aspls_lam_label = QLabel("Smoothness (\u03bb): 1e6.0")
        self.aspls_lam_slider = QSlider(Qt.Horizontal)
        self.aspls_lam_slider.setRange(20, 90)
        self.aspls_lam_slider.setValue(60)  # 10*log10(1e6)
        self.aspls_lam_slider.valueChanged.connect(
            lambda v: aspls_lam_label.setText(f"Smoothness (\u03bb): 1e{v/10:.1f}"))
        self.aspls_lam_slider.valueChanged.connect(self.update_preview)
        aspls_layout.addWidget(aspls_lam_label); aspls_layout.addWidget(self.aspls_lam_slider)

        # drPLS Parameters -- its own λ slider on arPLS's scale, plus a
        # second slider for eta (0-1): how much the smoothness penalty
        # relaxes under high-weight (peak) regions, on top of an
        # unweighted first-order penalty term with no slider of its own
        # (see calculate_drpls_baseline).
        drpls_params_page = QWidget()
        drpls_layout = QVBoxLayout(drpls_params_page)
        drpls_layout.setContentsMargins(0, 0, 0, 0)
        drpls_lam_label = QLabel("Smoothness (\u03bb): 1e5.0")
        self.drpls_lam_slider = QSlider(Qt.Horizontal)
        self.drpls_lam_slider.setRange(20, 90)
        self.drpls_lam_slider.setValue(50)  # 10*log10(1e5)
        self.drpls_lam_slider.valueChanged.connect(
            lambda v: drpls_lam_label.setText(f"Smoothness (\u03bb): 1e{v/10:.1f}"))
        self.drpls_lam_slider.valueChanged.connect(self.update_preview)
        drpls_layout.addWidget(drpls_lam_label); drpls_layout.addWidget(self.drpls_lam_slider)

        drpls_eta_label = QLabel("Peak Relaxation (\u03b7): 0.50")
        self.drpls_eta_slider = QSlider(Qt.Horizontal)
        self.drpls_eta_slider.setRange(0, 100)
        self.drpls_eta_slider.setValue(50)
        self.drpls_eta_slider.valueChanged.connect(
            lambda v: drpls_eta_label.setText(f"Peak Relaxation (\u03b7): {v/100:.2f}"))
        self.drpls_eta_slider.valueChanged.connect(self.update_preview)
        drpls_layout.addWidget(drpls_eta_label); drpls_layout.addWidget(self.drpls_eta_slider)

        # psalsa Parameters -- its own λ slider on ALS's scale (same
        # second-order-penalty solver, same range/default as the ALS
        # slider above), plus its own Asymmetry (p) slider -- unlike
        # airPLS/arPLS/iarPLS, psalsa's weighting still uses p the way
        # ALS's does, just with an exponential decay above the fit
        # instead of ALS's hard split, which is what lets its natural p
        # sit much higher than ALS's own (0.5 vs. 0.01) -- see
        # calculate_psalsa_baseline.
        psalsa_params_page = QWidget()
        psalsa_layout = QVBoxLayout(psalsa_params_page)
        psalsa_layout.setContentsMargins(0, 0, 0, 0)
        psalsa_lam_label = QLabel("Smoothness (\u03bb): 1e6.0")
        self.psalsa_lam_slider = QSlider(Qt.Horizontal)
        self.psalsa_lam_slider.setRange(20, 90)
        self.psalsa_lam_slider.setValue(60)  # 10*log10(1e6)
        self.psalsa_lam_slider.valueChanged.connect(
            lambda v: psalsa_lam_label.setText(f"Smoothness (\u03bb): 1e{v/10:.1f}"))
        self.psalsa_lam_slider.valueChanged.connect(self.update_preview)
        psalsa_layout.addWidget(psalsa_lam_label); psalsa_layout.addWidget(self.psalsa_lam_slider)

        psalsa_p_label = QLabel("Asymmetry (p): 0.50")
        self.psalsa_p_slider = QSlider(Qt.Horizontal)
        self.psalsa_p_slider.setRange(1, 99)
        self.psalsa_p_slider.setValue(50)
        self.psalsa_p_slider.valueChanged.connect(
            lambda v: psalsa_p_label.setText(f"Asymmetry (p): {v/100:.2f}"))
        self.psalsa_p_slider.valueChanged.connect(self.update_preview)
        psalsa_layout.addWidget(psalsa_p_label); psalsa_layout.addWidget(self.psalsa_p_slider)

        # I-ModPoly Parameters -- a single polynomial order, not a
        # lambda: I-ModPoly fits one global low-order polynomial rather
        # than a locally-penalized smooth curve, so it isn't part of the
        # Whittaker family above and has no smoothness/asymmetry slider
        # at all (see calculate_imodpoly_baseline). Iteration count and
        # the 5% convergence threshold are fixed internally, same as
        # airPLS/arPLS's iteration counts above.
        imodpoly_params_page = QWidget()
        imodpoly_layout = QVBoxLayout(imodpoly_params_page)
        imodpoly_layout.setContentsMargins(0, 0, 0, 0)
        imodpoly_order_label = QLabel("Polynomial Order: 5")
        self.imodpoly_order_slider = QSlider(Qt.Horizontal)
        self.imodpoly_order_slider.setRange(1, 12)
        self.imodpoly_order_slider.setValue(5)
        self.imodpoly_order_slider.valueChanged.connect(
            lambda v: imodpoly_order_label.setText(f"Polynomial Order: {v}"))
        self.imodpoly_order_slider.valueChanged.connect(self.update_preview)
        imodpoly_layout.addWidget(imodpoly_order_label); imodpoly_layout.addWidget(self.imodpoly_order_slider)

        # Morphological Opening Parameters -- deliberately no controls at
        # all. Unlike every other method here, it has no smoothness,
        # asymmetry, or order parameter to expose: the structuring
        # element it would otherwise need is grown automatically until
        # the result stops changing (see calculate_morphological_baseline).
        # The full explanation lives in BASELINE_METHOD_INFO, behind the
        # Method Info button -- this page just needs a short pointer to
        # it so an empty-looking panel doesn't read as broken.
        morph_params_page = QWidget()
        morph_layout = QVBoxLayout(morph_params_page)
        morph_layout.setContentsMargins(0, 0, 0, 0)
        morph_note = QLabel("No adjustable parameters for this method -- see Method Info.")
        morph_note.setStyleSheet("color: gray; font-style: italic;")
        morph_layout.addWidget(morph_note)
        morph_layout.addStretch()

        # mpls Parameters -- its own Smoothness (lambda) slider on ALS's
        # scale (default 1e6, single weighted solve, not iterative), and
        # its own Asymmetry (p) slider -- a different quantity than
        # ALS/psalsa's p: it's the weight given to every point NOT
        # identified as a morphological anchor, so 0.00 (fully trusting
        # the anchors, fully ignoring everything else) is the default,
        # not psalsa's 0.5.
        mpls_params_page = QWidget()
        mpls_layout = QVBoxLayout(mpls_params_page)
        mpls_layout.setContentsMargins(0, 0, 0, 0)
        mpls_lam_label = QLabel("Smoothness (λ): 1e6.0")
        self.mpls_lam_slider = QSlider(Qt.Horizontal)
        self.mpls_lam_slider.setRange(20, 90)
        self.mpls_lam_slider.setValue(60)  # 10*log10(1e6)
        self.mpls_lam_slider.valueChanged.connect(
            lambda v: mpls_lam_label.setText(f"Smoothness (λ): 1e{v/10:.1f}"))
        self.mpls_lam_slider.valueChanged.connect(self.update_preview)
        mpls_layout.addWidget(mpls_lam_label); mpls_layout.addWidget(self.mpls_lam_slider)

        mpls_p_label = QLabel("Non-Anchor Weight (p): 0.00")
        self.mpls_p_slider = QSlider(Qt.Horizontal)
        self.mpls_p_slider.setRange(0, 99)
        self.mpls_p_slider.setValue(0)
        self.mpls_p_slider.valueChanged.connect(
            lambda v: mpls_p_label.setText(f"Non-Anchor Weight (p): {v/100:.2f}"))
        self.mpls_p_slider.valueChanged.connect(self.update_preview)
        mpls_layout.addWidget(mpls_p_label); mpls_layout.addWidget(self.mpls_p_slider)

        # Morphology + Mollification Parameters -- fully parameter-free,
        # same spirit as Morphological Opening's own page: the
        # structuring-element window is grown automatically the same
        # way, and the mollifier-kernel smoothing / convergence check
        # are fixed internally (see calculate_mollification_baseline).
        mollification_params_page = QWidget()
        mollification_layout = QVBoxLayout(mollification_params_page)
        mollification_layout.setContentsMargins(0, 0, 0, 0)
        mollification_note = QLabel("No adjustable parameters for this method -- see Method Info.")
        mollification_note.setStyleSheet("color: gray; font-style: italic;")
        mollification_layout.addWidget(mollification_note)
        mollification_layout.addStretch()

        # mpspline Parameters -- same two-slider shape as mpls's own page
        # (Smoothness (lambda) + Non-Anchor Weight (p)), since mpspline is
        # mpls with the Whittaker solve swapped for a penalized spline fit
        # (see calculate_mpspline_baseline). num_knots/spline_degree/
        # diff_order stay at their calculate_mpspline_baseline defaults --
        # not exposed here, same reasoning as lam_smooth (see that
        # method's docstring).
        mpspline_params_page = QWidget()
        mpspline_layout = QVBoxLayout(mpspline_params_page)
        mpspline_layout.setContentsMargins(0, 0, 0, 0)
        mpspline_lam_label = QLabel("Smoothness (λ): 1e4.0")
        self.mpspline_lam_slider = QSlider(Qt.Horizontal)
        self.mpspline_lam_slider.setRange(20, 90)
        self.mpspline_lam_slider.setValue(40)  # 10*log10(1e4)
        self.mpspline_lam_slider.valueChanged.connect(
            lambda v: mpspline_lam_label.setText(f"Smoothness (λ): 1e{v/10:.1f}"))
        self.mpspline_lam_slider.valueChanged.connect(self.update_preview)
        mpspline_layout.addWidget(mpspline_lam_label); mpspline_layout.addWidget(self.mpspline_lam_slider)

        mpspline_p_label = QLabel("Non-Anchor Weight (p): 0.00")
        self.mpspline_p_slider = QSlider(Qt.Horizontal)
        self.mpspline_p_slider.setRange(0, 99)
        self.mpspline_p_slider.setValue(0)
        self.mpspline_p_slider.valueChanged.connect(
            lambda v: mpspline_p_label.setText(f"Non-Anchor Weight (p): {v/100:.2f}"))
        self.mpspline_p_slider.valueChanged.connect(self.update_preview)
        mpspline_layout.addWidget(mpspline_p_label); mpspline_layout.addWidget(self.mpspline_p_slider)


        # jbcd Parameters -- unlike every other morphology-family method
        # here, jbcd doesn't use morphology to pick anchor points at all;
        # it solves a joint energy function for baseline + denoised
        # spectrum together (see calculate_jbcd_baseline). Only 2 of the
        # reference's nominal 3 regularization weights are exposed --
        # testing found the third (and the fixed annealing ratios) only
        # change how fast the fit converges, not the converged baseline
        # itself (see that method's own docstring for the full reasoning).
        jbcd_params_page = QWidget()
        jbcd_layout = QVBoxLayout(jbcd_params_page)
        jbcd_layout.setContentsMargins(0, 0, 0, 0)
        jbcd_alpha_label = QLabel("Baseline Fidelity to Opening (α): 0.10")
        self.jbcd_alpha_slider = QSlider(Qt.Horizontal)
        self.jbcd_alpha_slider.setRange(1, 100)
        self.jbcd_alpha_slider.setValue(10)  # 0.10
        self.jbcd_alpha_slider.valueChanged.connect(
            lambda v: jbcd_alpha_label.setText(f"Baseline Fidelity to Opening (α): {v/100:.2f}"))
        self.jbcd_alpha_slider.valueChanged.connect(self.update_preview)
        jbcd_layout.addWidget(jbcd_alpha_label); jbcd_layout.addWidget(self.jbcd_alpha_slider)

        jbcd_beta_label = QLabel("Baseline Smoothness Ceiling (β): 10.0")
        self.jbcd_beta_slider = QSlider(Qt.Horizontal)
        self.jbcd_beta_slider.setRange(1, 100)
        self.jbcd_beta_slider.setValue(10)  # 10.0
        self.jbcd_beta_slider.valueChanged.connect(
            lambda v: jbcd_beta_label.setText(f"Baseline Smoothness Ceiling (β): {float(v):.1f}"))
        self.jbcd_beta_slider.valueChanged.connect(self.update_preview)
        jbcd_layout.addWidget(jbcd_beta_label); jbcd_layout.addWidget(self.jbcd_beta_slider)

        params_group = QGroupBox("Method Parameters")
        params_group_layout = QVBoxLayout()
        self.params_stack = _CurrentPageStackedWidget()
        self.params_stack.addWidget(als_params_page)       # index 0 == 'als'
        self.params_stack.addWidget(airpls_params_page)    # index 1 == 'airpls'
        self.params_stack.addWidget(arpls_params_page)     # index 2 == 'arpls'
        self.params_stack.addWidget(iarpls_params_page)    # index 3 == 'iarpls'
        self.params_stack.addWidget(aspls_params_page)     # index 4 == 'aspls'
        self.params_stack.addWidget(drpls_params_page)     # index 5 == 'drpls'
        self.params_stack.addWidget(psalsa_params_page)    # index 6 == 'psalsa'
        self.params_stack.addWidget(imodpoly_params_page)  # index 7 == 'imodpoly'
        self.params_stack.addWidget(morph_params_page)     # index 8 == 'morphological'
        self.params_stack.addWidget(mpls_params_page)      # index 9 == 'mpls'
        self.params_stack.addWidget(mollification_params_page)  # index 10 == 'mollification'
        self.params_stack.addWidget(mpspline_params_page)      # index 11 == 'mpspline'
        self.params_stack.addWidget(jbcd_params_page)          # index 12 == 'jbcd'
        # _CurrentPageStackedWidget only overrides the *hints* -- Qt still
        # needs to be told to re-read them each time the visible page
        # changes, or the groupbox keeps whatever size it last settled on.
        self.params_stack.currentChanged.connect(lambda _index: self.params_stack.updateGeometry())
        params_group_layout.addWidget(self.params_stack)
        params_group.setLayout(params_group_layout)
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

        # Region Shortcuts — one-click presets, grouped into tabs by
        # category (see baseline_region_presets.py), that just add a row
        # to the ranges table below — exactly as if that range had been
        # dragged on the plot by hand. They carry no special exclusion
        # behavior of their own: once added, a preset region follows
        # Invert Regions like any manually drawn one, and checking
        # several at once — even across different tabs — adds each of
        # their ranges (additive, not mutually exclusive). Tabs (rather
        # than stacking a group box per category) keep this panel a
        # fixed height as more categories get added later.
        self.preset_checkboxes = {}
        shortcuts_group = QGroupBox("Region Shortcuts")
        shortcuts_group_layout = QVBoxLayout()
        shortcuts_tabs = QTabWidget()
        for category, presets in REGION_PRESET_CATEGORIES.items():
            category_page = QWidget()
            category_layout = QVBoxLayout(category_page)
            for preset in presets:
                checkbox = QCheckBox(preset['label'])
                if preset.get('tooltip'):
                    checkbox.setToolTip(preset['tooltip'])
                checkbox.stateChanged.connect(
                    lambda _state, key=preset['key'], cb=checkbox: self._on_preset_toggled(key, cb.isChecked())
                )
                category_layout.addWidget(checkbox)
                self.preset_checkboxes[preset['key']] = checkbox
            category_layout.addStretch()
            shortcuts_tabs.addTab(category_page, category)
        shortcuts_group_layout.addWidget(shortcuts_tabs)
        shortcuts_group.setLayout(shortcuts_group_layout)
        regions_layout.addWidget(shortcuts_group)

        self.range_table = QTableWidget()
        self.range_table.setColumnCount(3); self.range_table.setHorizontalHeaderLabels(['From', 'To', 'Source'])
        self.range_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        regions_layout.addWidget(self.range_table)
        
        btn_layout = QHBoxLayout()
        remove_btn = QPushButton("Remove Selected"); remove_btn.clicked.connect(self.remove_range)
        clear_btn = QPushButton("Clear All"); clear_btn.clicked.connect(self.clear_ranges)
        btn_layout.addWidget(remove_btn); btn_layout.addWidget(clear_btn)
        regions_layout.addLayout(btn_layout)
        regions_group.setLayout(regions_layout)
        layout.addWidget(regions_group)

        # Processing -- how Apply / Add as New compute the baselines. The
        # numbers are identical in every mode; only the speed differs.
        # Keeping the choice visible lets the user compare serial against
        # parallel, or switch parallel off if it ever misbehaves.
        processing_group = QGroupBox("Processing")
        processing_layout = QHBoxLayout(processing_group)
        processing_layout.addWidget(QLabel("Mode:"))
        self.processing_mode_combo = QComboBox()
        self.processing_mode_combo.addItem("Automatic (recommended)", 'auto')
        self.processing_mode_combo.addItem("Serial (one core)", 'serial')
        self.processing_mode_combo.addItem("Parallel (several cores)", 'parallel')
        self.processing_mode_combo.setToolTip(
            "How Apply / Add as New compute the baselines. The result is the "
            "same in every mode; only the speed differs.\n\n"
            "Automatic: times the first few spectra and uses several cores only "
            "when the rest of the job is long enough to pay for starting them "
            "(large maps, slow methods such as mpspline or jbcd).\n"
            "Serial: one spectrum after another, on one core.\n"
            "Parallel: always several worker processes. Use it to compare "
            "speed, or choose Serial if you suspect a problem with it.")
        processing_layout.addWidget(self.processing_mode_combo, 1)
        processing_layout.addWidget(QLabel("Workers:"))
        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(0, max(1, os.cpu_count() or 1))
        from src.modules.utils.parallel_utils import describe_worker_limits, safe_worker_count
        self.max_workers_spin.setSpecialValueText(f"Auto ({safe_worker_count()})")
        self.max_workers_spin.setToolTip(
            "Number of worker processes for parallel processing.\n"
            "Auto uses one less than the number of CPU cores, limited by the "
            "memory that is free right now (about 200 MB per worker).\n"
            f"Right now on this computer: {describe_worker_limits()}.\n"
            "A number you type is limited to the CPU cores only, so only raise it "
            "if you know there is enough free memory.")
        processing_layout.addWidget(self.max_workers_spin)
        self.processing_mode_combo.currentIndexChanged.connect(
            lambda _i: self.max_workers_spin.setEnabled(
                self.processing_mode_combo.currentData() != 'serial'))
        layout.addWidget(processing_group)

        # No trailing addStretch() here: spectra_group's stretch factor
        # (see above) is what should absorb any leftover vertical space,
        # not a spacer between Fitting Regions and the button row.

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

    def _on_method_changed(self, index):
        """Swap the visible parameter panel to match the selected
        algorithm (self.params_stack index mirrors self.method_combo's
        item order — see create_control_panel; _MethodTreeCombo's
        category headers exist only in its popup and are not items, so
        this stays a plain 1:1 mapping) and refresh the preview, since
        ALS and airPLS will generally produce a different baseline for
        the same spectrum."""
        self.params_stack.setCurrentIndex(index)
        self.update_preview()

    def _show_method_info(self):
        """Show a popup with the description of the currently selected
        baseline method -- see BASELINE_METHOD_INFO (module level, above
        _MethodTreeCombo) and the "? Method info" button in
        create_control_panel."""
        key = self.method_combo.currentData()
        meta = BASELINE_METHOD_INFO.get(key)
        if not meta:
            return
        QMessageBox.information(
            self, meta['label'],
            f"<b>{meta['label']}</b><br><br>{meta['info']}"
        )

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

    def _range_entry(self, start, end, source='manual'):
        """A row of self.fitting_ranges: a (start, end) pair plus where
        it came from — 'manual' for a plot drag, or a preset's key (see
        baseline_region_presets.py) for a Region Shortcuts checkbox.
        Only the (start, end) pair ever reaches the manager — see
        get_settings, which flattens this back to plain tuples."""
        return {'range': [start, end], 'source': source}

    def _range_entry_from_saved(self, start, end):
        """Used by load_settings to rebuild self.fitting_ranges from a
        previously saved settings dict, which only stores plain (start,
        end) pairs (see get_settings) — no memory of which preset, if
        any, added a given row. Matches by exact value against every
        known preset's range; see load_settings for why exact matching
        is safe here."""
        preset = self._find_preset_by_range(start, end)
        return self._range_entry(start, end, source=preset['key'] if preset else 'manual')

    def _find_preset_by_range(self, start, end):
        for presets in REGION_PRESET_CATEGORIES.values():
            for preset in presets:
                if tuple(preset['range']) == (start, end):
                    return preset
        return None

    def _preset_source_label(self, key):
        """Source column text for a preset-added row — falls back to the
        raw key if the preset that added it was since renamed/removed
        (e.g. a settings dict saved by an older version of this dialog)."""
        preset = find_preset(key)
        return preset['short_label'] if preset else key

    def add_range(self, x_min, x_max):
        start, end = sorted((x_min, x_max))
        self.fitting_ranges.append(self._range_entry(start, end))
        self.update_range_table()
        self.update_preview()

    def remove_range(self):
        selected_rows = sorted(list(set(item.row() for item in self.range_table.selectedItems())), reverse=True)
        removed_sources = []
        for row in selected_rows:
            removed_sources.append(self.fitting_ranges[row]['source'])
            del self.fitting_ranges[row]
        # A removed row might have come from a checked preset — uncheck
        # it so the Region Shortcuts panel doesn't keep claiming a range
        # that's no longer in the table (see _sync_preset_checkboxes).
        self._sync_preset_checkboxes(removed_sources)
        self.update_range_table()
        self.update_preview()

    def clear_ranges(self):
        removed_sources = [entry['source'] for entry in self.fitting_ranges]
        self.fitting_ranges.clear()
        self._sync_preset_checkboxes(removed_sources)
        self.update_range_table()
        self.update_preview()

    def _sync_preset_checkboxes(self, sources):
        """Uncheck any preset checkbox whose row was just removed from
        the table directly (Remove Selected / Clear All), rather than by
        unchecking the box itself. Signals are blocked while doing this
        so it doesn't loop back into _on_preset_toggled and try to
        remove an already-removed row."""
        for source in sources:
            checkbox = self.preset_checkboxes.get(source)
            if checkbox is not None and checkbox.isChecked():
                checkbox.blockSignals(True)
                checkbox.setChecked(False)
                checkbox.blockSignals(False)

    def _resync_preset_checkboxes_from_ranges(self):
        """Called after load_settings rebuilds self.fitting_ranges, so a
        reopened dialog shows its Region Shortcuts checkboxes checked
        exactly where a matching preset range is already in the table."""
        active_sources = {entry['source'] for entry in self.fitting_ranges}
        for key, checkbox in self.preset_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(key in active_sources)
            checkbox.blockSignals(False)

    def _on_preset_toggled(self, key, checked):
        """A Region Shortcuts checkbox was clicked — add or remove that
        preset's range as a normal row in self.fitting_ranges. This is
        the whole of what a preset does: it never reaches the manager
        as anything other than a (start, end) pair (see get_settings),
        so it obeys Invert Regions exactly like a manually drawn range."""
        if checked:
            preset = find_preset(key)
            if preset is None:
                return
            start, end = preset['range']
            self.fitting_ranges.append(self._range_entry(start, end, source=key))
        else:
            self.fitting_ranges = [e for e in self.fitting_ranges if e['source'] != key]
        self.update_range_table()
        self.update_preview()

    def update_range_table(self):
        self.range_table.setRowCount(len(self.fitting_ranges))
        for i, entry in enumerate(self.fitting_ranges):
            start, end = entry['range']
            source = entry['source']
            source_label = "Manual" if source == 'manual' else self._preset_source_label(source)
            self.range_table.setItem(i, 0, QTableWidgetItem(f"{start:.2f}"))
            self.range_table.setItem(i, 1, QTableWidgetItem(f"{end:.2f}"))
            self.range_table.setItem(i, 2, QTableWidgetItem(source_label))

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

        if settings['algorithm'] == 'airpls':
            baseline = self.manager.calculate_airpls_baseline(
                y, lam=settings['lambda'], porder=1, itermax=settings['n_iter'], exclude_indices=exclude_mask)
        elif settings['algorithm'] == 'arpls':
            baseline = self.manager.calculate_arpls_baseline(
                y, lam=settings['lambda'], itermax=settings['n_iter'], exclude_indices=exclude_mask)
        elif settings['algorithm'] == 'iarpls':
            baseline = self.manager.calculate_iarpls_baseline(
                y, lam=settings['lambda'], itermax=settings['n_iter'], exclude_indices=exclude_mask)
        elif settings['algorithm'] == 'aspls':
            baseline = self.manager.calculate_aspls_baseline(
                y, lam=settings['lambda'], itermax=settings['n_iter'], exclude_indices=exclude_mask)
        elif settings['algorithm'] == 'drpls':
            baseline = self.manager.calculate_drpls_baseline(
                y, lam=settings['lambda'], eta=settings['eta'], itermax=settings['n_iter'], exclude_indices=exclude_mask)
        elif settings['algorithm'] == 'psalsa':
            baseline = self.manager.calculate_psalsa_baseline(
                y, lam=settings['lambda'], p=settings['p'], itermax=settings['n_iter'], exclude_indices=exclude_mask)
        elif settings['algorithm'] == 'imodpoly':
            baseline = self.manager.calculate_imodpoly_baseline(
                x, y, poly_order=settings['poly_order'], itermax=settings['n_iter'], exclude_indices=exclude_mask)
        elif settings['algorithm'] == 'morphological':
            baseline = self.manager.calculate_morphological_baseline(
                y, itermax=settings['n_iter'], exclude_indices=exclude_mask)
        elif settings['algorithm'] == 'mpls':
            baseline = self.manager.calculate_mpls_baseline(
                y, lam=settings['lambda'], p=settings['p'], itermax=settings['n_iter'], exclude_indices=exclude_mask)
        elif settings['algorithm'] == 'mollification':
            baseline = self.manager.calculate_mollification_baseline(
                y, itermax=settings['n_iter'], exclude_indices=exclude_mask)
        elif settings['algorithm'] == 'mpspline':
            baseline = self.manager.calculate_mpspline_baseline(
                y, lam=settings['lambda'], p=settings['p'], itermax=settings['n_iter'], exclude_indices=exclude_mask)
        elif settings['algorithm'] == 'jbcd':
            baseline = self.manager.calculate_jbcd_baseline(
                y, alpha=settings['alpha'], beta=settings['beta'], itermax=settings['n_iter'], exclude_indices=exclude_mask)
        else:
            baseline = self.manager.calculate_als_baseline(
                y, lam=settings['lambda'], p=settings['p'], exclude_indices=exclude_mask)
        
        display_label = self._display_label(spectrum)
        # settings['fitting_ranges'] is already the flattened (start, end)
        # list from get_settings — includes any preset-added ranges (e.g.
        # the water band), so they're shaded on the plot exactly like a
        # manually drawn range instead of only affecting the fit silently.
        plot_ranges = settings['fitting_ranges']
        if baseline is not None and not np.isnan(baseline).all():
            corrected = y - baseline
            self.canvas.update_plot(spectrum, baseline, corrected, plot_ranges, settings['invert_regions'],
                                     display_label=display_label)
        else:
            # If baseline fails, show only original data
            self.canvas.update_plot(spectrum, None, None, plot_ranges, settings['invert_regions'],
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
        settings = self._algorithm_settings()
        settings['processing_mode'] = self.processing_mode_combo.currentData()
        settings['max_workers'] = self.max_workers_spin.value()
        return settings

    def _algorithm_settings(self):
        algorithm = self.method_combo.currentData()
        # Flatten to plain (start, end) tuples — the manager (and its
        # tests, and the correction-history metadata) only ever deal in
        # ranges, never in where a range came from. A preset-added range
        # is indistinguishable from a manually drawn one from here on.
        flat_ranges = [tuple(entry['range']) for entry in self.fitting_ranges]
        if algorithm == 'airpls':
            return {
                'algorithm': 'airpls',
                'lambda': 10**(self.airpls_lam_slider.value() / 10.0),
                'n_iter': 20,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        if algorithm == 'arpls':
            return {
                'algorithm': 'arpls',
                'lambda': 10**(self.arpls_lam_slider.value() / 10.0),
                'n_iter': 50,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        if algorithm == 'iarpls':
            return {
                'algorithm': 'iarpls',
                'lambda': 10**(self.iarpls_lam_slider.value() / 10.0),
                'n_iter': 100,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        if algorithm == 'aspls':
            return {
                'algorithm': 'aspls',
                'lambda': 10**(self.aspls_lam_slider.value() / 10.0),
                'n_iter': 100,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        if algorithm == 'drpls':
            return {
                'algorithm': 'drpls',
                'lambda': 10**(self.drpls_lam_slider.value() / 10.0),
                'eta': self.drpls_eta_slider.value() / 100.0,
                'n_iter': 50,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        if algorithm == 'psalsa':
            return {
                'algorithm': 'psalsa',
                'lambda': 10**(self.psalsa_lam_slider.value() / 10.0),
                'p': self.psalsa_p_slider.value() / 100.0,
                'n_iter': 50,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        if algorithm == 'imodpoly':
            return {
                'algorithm': 'imodpoly',
                'poly_order': self.imodpoly_order_slider.value(),
                'n_iter': 100,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        if algorithm == 'morphological':
            return {
                'algorithm': 'morphological',
                'n_iter': 300,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        if algorithm == 'mpls':
            return {
                'algorithm': 'mpls',
                'lambda': 10**(self.mpls_lam_slider.value() / 10.0),
                'p': self.mpls_p_slider.value() / 100.0,
                'n_iter': 300,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        if algorithm == 'mollification':
            return {
                'algorithm': 'mollification',
                'n_iter': 200,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        if algorithm == 'mpspline':
            return {
                'algorithm': 'mpspline',
                'lambda': 10**(self.mpspline_lam_slider.value() / 10.0),
                'p': self.mpspline_p_slider.value() / 100.0,
                'n_iter': 300,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        if algorithm == 'jbcd':
            return {
                'algorithm': 'jbcd',
                'alpha': self.jbcd_alpha_slider.value() / 100.0,
                'beta': float(self.jbcd_beta_slider.value()),
                'n_iter': 300,
                'fitting_ranges': flat_ranges,
                'invert_regions': self.invert_regions_checkbox.isChecked(),
            }
        return {
            'algorithm': 'als',
            'lambda': 10**(self.lam_slider.value() / 10.0),
            'p': self.p_slider.value() / 1000.0,
            'n_iter': 10,
            'fitting_ranges': flat_ranges,
            'invert_regions': self.invert_regions_checkbox.isChecked(),
        }