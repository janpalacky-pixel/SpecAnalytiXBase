# src/views/dialogs/data_analysis/normalization_dialog.py

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QRadioButton, QPushButton, QDoubleSpinBox, QLabel, QButtonGroup,
    QCheckBox, QFrame, QListWidget, QWidget, QSplitter, QSizePolicy,
    QListWidgetItem, QTabWidget, QScrollArea, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QApplication, QAbstractItemView,
    QLineEdit,
)
from PyQt5.QtGui import QDoubleValidator
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    make_shortened_name_delegate, compute_distinguishing_labels, make_shorten_names_checkbox,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Quick-reference popup for the region controls — same self-contained
# QTextBrowser-popup pattern as the Band Ratio / 2D map "Define Spectral
# Range" dialog's own "?" button (src/views/dialogs/visualization_analysis/
# spectral_range_dialog.py's _HELP_TEXT), not the full Help window.
# ---------------------------------------------------------------------------
_REGION_HELP_TEXT = """<html><head><style>
body { font-family: Arial, sans-serif; font-size: 12px; margin: 12px; line-height: 1.5; }
h2   { color: #1565C0; margin-top: 10px; }
h3   { color: #E65100; margin-top: 8px; margin-bottom: 2px; }
.tip { background:#E8F5E9; border-left:4px solid #2E7D32; padding:6px 10px; margin:6px 0; }
</style></head><body>

<h2>Normalization Region — Quick Guide</h2>

<h3>Adding regions</h3>
<ul>
  <li><b>Draw on plot:</b> click and drag on the spectrum plot to add a region.</li>
  <li><b>Type values:</b> enter From / To and click <b>Add region</b>.</li>
  <li><b>Full range</b> fills From/To with the entire data range — it does not
      add a region by itself, click Add region afterwards if that's what you want.</li>
</ul>

<h3>Editing a region</h3>
<ul>
  <li>Click a region in the list — the From / To fields are populated with its
      values, and <b>Add region</b> becomes <b>Update</b>.</li>
  <li>Edit the fields and click <b>Update</b> to change that region in place.</li>
  <li><b>Cancel edit</b>, right next to Update, deselects the region and goes
      back to adding a new one without changing anything.</li>
  <li>Adding or updating a region to values that exactly match another region
      already in the list is not allowed — the existing one is selected instead
      of creating a duplicate.</li>
</ul>

<h3>Removing regions</h3>
<ul>
  <li>Click a region, or Ctrl/Shift-click several (or Ctrl+A for all), then
      click <b>Remove</b> to delete them.</li>
</ul>

<h3>Include vs Exclude</h3>
<ul>
  <li><b>Include regions:</b> the normalization coefficient is computed using
      ONLY the listed regions.</li>
  <li><b>Exclude regions:</b> the coefficient is computed from the full
      spectrum MINUS the listed regions (e.g. to avoid a fluorescence band).</li>
</ul>

<div class="tip">
  <b>Tip:</b> Presets let you save a named region set and reload it later or
  on a different dataset — see the orange "?" next to the Preset controls
  below for details on those.
</div>
</body></html>"""


# ---------------------------------------------------------------------------
# Method definitions — single source of truth used by the dialog and help
# ---------------------------------------------------------------------------
METHODS = {
    # ---- Intensity normalization ----------------------------------------
    'max_peak': {
        'label': 'Peak intensity',
        'formula': 'I / I\u2098\u2090\u02e3 (region)',
        'tab': 'Intensity',
        'info': (
            'Divides every spectrum by its maximum intensity within the '
            'selected region(s). The result is applied to the full spectrum. '
            'Use when comparing relative peak heights between spectra measured '
            'under different laser powers or integration times.'
        ),
    },
    'unit_area': {
        'label': 'Area (integral)',
        'formula': 'I / \u222bI dx (region)',
        'tab': 'Intensity',
        'info': (
            'Divides by the integrated area under the curve within the selected '
            'region(s). Preserves spectral shape perfectly. '
            'Ideal for quantitative peak-ratio studies or composition analysis.'
        ),
    },
    'vector': {
        'label': 'Vector norm (L2)',
        'formula': 'I / \u2016I\u2016\u2082 (region)',
        'tab': 'Intensity',
        'info': (
            'Divides by the Euclidean (L2) norm computed over the selected '
            'region(s). Good general-purpose choice for removing laser power '
            'drift or detector sensitivity differences while preserving spectral shape.'
        ),
    },
    'quantile': {
        'label': 'Robust peak (Nth pct.)',
        'formula': 'I / P\u2099(I) (region)',
        'tab': 'Intensity',
        'info': (
            'Divides by the Nth percentile of intensities in the selected region '
            '(default N\u202f=\u202f95). Less sensitive to noise spikes or cosmic rays '
            'than peak intensity — the percentile threshold filters out isolated outliers. '
            'Adjust N below: lower values are more conservative (ignore more of the top).'
        ),
    },
    'top_mean': {
        'label': 'Mean of top N%',
        'formula': 'I / mean(I \u2265 P\u2099) (region)',
        'tab': 'Intensity',
        'info': (
            'Takes all points in the selected region that lie at or above the Nth percentile '
            'and divides by their mean. '
            'Unlike the percentile method (which picks a single threshold value), '
            'this averages the actual peak-top points — giving a better estimate of true '
            'peak intensity for broad or flat-topped bands. '
            'Uses the same N as "Robust peak". '
            'Example: N\u202f=\u202f95 averages the top 5\u202f% of points in the region.'
        ),
    },
    'min_max': {
        'label': 'Min-max [0, 1]',
        'formula': '(I \u2212 I\u2098\u1d62\u207f) / (I\u2098\u2090\u02e3 \u2212 I\u2098\u1d62\u207f) (region)',
        'tab': 'Intensity',
        'info': (
            'Rescales the spectrum so that the minimum of the selected region maps to 0 '
            'and the maximum maps to 1. The same shift and scale are applied to the full '
            'spectrum. Useful for shape comparison when absolute intensity is irrelevant. '
            'Note: unlike peak-intensity or area normalization the result depends on both '
            'the minimum and maximum of the region, so it is sensitive to baseline offsets \u2014 '
            'apply baseline correction first for best results.'
        ),
    },
    'offset_correction': {
        'label': 'Offset correction',
        'formula': 'I \u2212 mean(I) (region)',
        'tab': 'Intensity',
        'info': (
            'Subtracts the mean intensity of the selected region from the entire spectrum. '
            'Use a spectral region where the signal should be zero (e.g. 320\u2013330\u202fnm '
            'for CD or absorption spectra). '
            'This zeros the baseline without any scaling, preserving absolute intensity '
            'differences between spectra. '
            'Typical workflow: define a region in the silent/flat part of the spectrum, '
            'apply to all spectra in the dataset.'
        ),
    },
    'reference': {
        'label': 'Reference spectrum',
        'formula': 'I / I\u1d3f\u1d49\u1da0 (point-wise)',
        'tab': 'Intensity',
        'info': (
            'Divides each spectrum point-wise by a chosen reference spectrum. '
            'Useful for ratio spectroscopy (e.g. dividing by a blank or '
            'background measurement) or for removing systematic instrument response.'
        ),
    },
    # ---- Scatter correction --------------------------------------------
    'snv': {
        'label': 'Scatter corr. (SNV)',
        'formula': '(I \u2212 \u03bc) / \u03c3 (region)',
        'tab': 'Scatter correction',
        'info': (
            'Standard Normal Variate — mean-centres each spectrum and divides '
            'by its standard deviation, both computed over the selected region(s). '
            'Removes multiplicative scatter and baseline offset simultaneously. '
            'The standard choice for diffuse-reflectance NIR and solid-sample Raman.'
        ),
    },
    'msc': {
        'label': 'Scatter corr. (MSC)',
        'formula': '(I \u2212 a) / b vs. I\u0305',
        'tab': 'Scatter correction',
        'info': (
            'Multiplicative Scatter Correction — fits each spectrum to the mean '
            'spectrum by linear regression and corrects for the slope (b) and '
            'offset (a). Physically more rigorous than SNV when a consistent '
            'reference exists. Recommended for powder or turbid-liquid samples. '
            'By default the fit uses the whole spectrum; check "Fit regression '
            'within region only" to restrict it to the selected region instead.'
        ),
    },
    'svd': {
        'label': 'SVD factor norm.',
        'formula': 'I / |V\u2081| (first PC)',
        'tab': 'Intensity',
        'info': (
            'Uses the first principal component loadings (via SVD) as '
            'normalization factors across the whole batch of spectra. '
            'Identifies and corrects for the dominant systematic variance '
            'pattern — useful for instrumental drift or sample thickness '
            'variation across a large dataset. The selected region is used '
            'as a mask before the decomposition, so it does affect the result.'
        ),
    },
}

# Tab order for the UI
TAB_ORDER = ['Intensity', 'Scatter correction']

# Methods for which a "target value" multiplier makes sense — all of them
# compute the normalized result as (signal / single_factor); subtractive or
# statistical methods (snv, msc, offset_correction, ...) are excluded.
# 'svd' is also excluded even though it lives under the Intensity tab and is
# a single-factor division too: its factor is already centred around 1 by
# construction (|V1 / mean(V1)|), so a separate "target value" multiplier
# would not have the same intuitive meaning it has for the methods below.
# 'reference' is excluded for a different reason: it's a point-wise ratio
# against another spectrum, not a single-factor division at all.
RATIO_BASED_MODES = ('max_peak', 'unit_area', 'vector', 'quantile', 'top_mean')


class CollapsibleSection(QWidget):
    """
    A QGroupBox-styled section with a clickable header that expands or
    collapses its content. Used for sections that are set once and rarely
    revisited (e.g. spectrum selection, region definitions) so the control
    panel doesn't force constant scrolling when every section is expanded.

    The content widget is created by the caller and added via setContentWidget;
    this class only handles the toggle chrome, not the actual fields.
    """

    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Frame gives the same bordered, rounded look as a QGroupBox
        self._frame = QFrame()
        self._frame.setStyleSheet(
            'QFrame { border: 1px solid #BDBDBD; border-radius: 6px; '
            'background-color: transparent; }'
        )
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        self._toggle_btn = QPushButton(f'\u25be  {title}')
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(expanded)
        self._toggle_btn.setStyleSheet(
            'QPushButton {'
            '  text-align: left;'
            '  border: none;'
            '  border-bottom: 1px solid #BDBDBD;'
            '  border-top-left-radius: 6px;'
            '  border-top-right-radius: 6px;'
            '  padding: 8px 10px;'
            '  font-weight: bold;'
            '  background-color: #ECEFF1;'
            '  color: #263238;'
            '}'
            'QPushButton:hover { background-color: #CFD8DC; }'
        )
        self._toggle_btn.clicked.connect(self._on_toggled)
        frame_layout.addWidget(self._toggle_btn)

        self._content_holder = QVBoxLayout()
        self._content_holder.setContentsMargins(8, 8, 8, 8)
        frame_layout.addLayout(self._content_holder)

        outer.addWidget(self._frame)

        self._content_widget = None
        self._update_arrow()

    def setContentWidget(self, widget: QWidget):
        """Set the widget shown inside the section (e.g. the existing groupbox's content)."""
        self._content_widget = widget
        self._content_holder.addWidget(widget)
        widget.setVisible(self._toggle_btn.isChecked())

    def _on_toggled(self):
        if self._content_widget is not None:
            self._content_widget.setVisible(self._toggle_btn.isChecked())
        self._update_arrow()

    def _update_arrow(self):
        title = self._toggle_btn.text().split('  ', 1)[-1]
        arrow = '\u25bc' if self._toggle_btn.isChecked() else '\u25b6'
        self._toggle_btn.setText(f'{arrow}  {title}')


class NormalizationDialog(QDialog):
    def __init__(self, parent=None, current_settings=None, controller=None,
                 selected_spectra=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle('Normalization')
        self.setModal(True)
        self.current_settings = current_settings or {}
        self.controller = controller
        # Bound method (OperationsController.commit_normalization) passed
        # in by whatever opened this dialog, so Apply / Add as New can
        # commit the result directly, without a separate Run step.
        self.commit_callback = commit_callback

        if selected_spectra is not None:
            self.selected_spectra = selected_spectra
        elif controller is not None and hasattr(controller, 'spectrum_selector'):
            self.selected_spectra = controller.spectrum_selector.get_selected_spectra()
        else:
            self.selected_spectra = []

        self._initialization_complete = False
        self.sort_ascending = True
        self._last_normalized_all: list = []   # cache for the Save panel

        # Debounce timer for the live preview: rapid-fire changes (typing in a
        # spinbox, dragging on the canvas) restart this timer instead of
        # recomputing immediately on every single change. The actual
        # recompute (_do_update_preview) only runs once the user pauses for
        # 250ms, which keeps the UI responsive for slower modes
        # (mean_relative, svd) on larger datasets.
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._do_update_preview)

        # Track multiple normalization regions as list of (x_min, x_max)
        # Initialise from current_settings (new or legacy format)
        self._regions: list = []
        if 'x_ranges' in self.current_settings and self.current_settings['x_ranges']:
            self._regions = list(self.current_settings['x_ranges'])
        elif 'x_min' in self.current_settings and 'x_max' in self.current_settings:
            x0 = self.current_settings.get('x_min')
            x1 = self.current_settings.get('x_max')
            if x0 is not None and x1 is not None:
                self._regions = [(float(x0), float(x1))]

        # When a single region in regions_list is selected, its bounds are
        # loaded into the From/To spinboxes and this tracks which row is
        # being edited, so the "Add region" button (relabeled "Update
        # selected") updates that entry in place instead of appending a new
        # one. None means "not currently editing an existing region".
        self._editing_region_row = None

        self.setMinimumSize(850, 650)
        self.resize(1250, 880)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)
        self._setup_ui()

        if self.selected_spectra:
            self._initialize_dialog()

    # =================================================================
    # UI construction
    # =================================================================
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)
        splitter.addWidget(self._create_control_panel())
        splitter.addWidget(self._create_canvas_panel())
        splitter.setSizes([420, 830])

    def _create_control_panel(self):
        outer_widget = QWidget()
        # setFixedWidth(420) used to sit here — it actively fights the
        # QSplitter above: dragging the handle right can never make this
        # panel any wider than the fixed value, and dragging left doesn't
        # shrink the panel's actual content either, so it just clips
        # instead of reflowing. A min/max range lets the splitter actually
        # resize it continuously in both directions, same fix already
        # applied to Cosmic Ray Removal, X-axis Alignment, and Peak
        # Fitting's dialogs.
        outer_widget.setMinimumWidth(340)
        outer_widget.setMaximumWidth(700)
        outer_layout = QVBoxLayout(outer_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # "Selected spectra" starts expanded so the user can see at a
        # glance which spectra are about to be normalized; it's still
        # collapsible for anyone who wants the space back once they've
        # checked it. "Normalization region(s)" is something the user
        # defines and checks often, so it also stays expanded by default.
        # "Normalization method" and "Result scaling" are what the user
        # actively interacts with, so they stay as plain always-visible
        # groupboxes (unchanged).
        spectra_section = CollapsibleSection(
            'Selected spectra (preview only)', expanded=True
        )
        spectra_section.setContentWidget(self._build_spectra_group())
        layout.addWidget(spectra_section)

        layout.addWidget(self._build_method_group())

        regions_section = CollapsibleSection('Normalization region(s)', expanded=True)
        regions_section.setContentWidget(self._build_regions_group())
        layout.addWidget(regions_section)

        layout.addStretch()
        scroll.setWidget(widget)
        outer_layout.addWidget(scroll)

        # Buttons stay outside the scroll area so they're always visible
        btn_row = QHBoxLayout()
        self.help_button = QPushButton('Help')
        self.help_button.setAutoDefault(False)
        self.help_button.setDefault(False)
        btn_row.addWidget(self.help_button)
        btn_row.addStretch()
        self.apply_button = QPushButton('Apply')
        self.apply_button.setToolTip(
            'Replace the selected spectra with their normalized result.'
        )
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        btn_row.addWidget(self.apply_button)
        self.add_as_new_button = QPushButton('Add as New')
        self.add_as_new_button.setToolTip(
            'Keep the original spectra unchanged and add the normalized '
            'results to the list under new names.'
        )
        self.add_as_new_button.setAutoDefault(False)
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        btn_row.addWidget(self.add_as_new_button)
        self.close_button = QPushButton('Close')
        self.close_button.setAutoDefault(False)
        self.close_button.clicked.connect(self.reject)
        btn_row.addWidget(self.close_button)
        outer_layout.addLayout(btn_row)
        return outer_widget

    # ---- Spectra list --------------------------------------------------
    def _build_spectra_group(self):
        # No title here — CollapsibleSection's header already shows
        # "Selected spectra", so a second QGroupBox title would duplicate it.
        group = QGroupBox()
        group.setStyleSheet('QGroupBox { border: none; }')
        layout = QVBoxLayout(group)

        info_label = QLabel(
            '💡 This selection is for preview only. '
            'Normalization applies to all spectra loaded in the dialog.'
        )
        info_label.setStyleSheet(
            'color: #1976D2; font-style: italic; padding: 5px; '
            'background-color: #E3F2FD; border-radius: 3px; margin: 2px;'
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel('Spectra:'))
        self.sort_button = QPushButton('\u25b2')
        self.sort_button.setMaximumWidth(30)
        self.sort_button.setToolTip('Toggle sort order')
        self.sort_button.clicked.connect(self._toggle_sort)
        hdr.addWidget(self.sort_button)
        hdr.addStretch()
        layout.addLayout(hdr)

        self.spectra_list = QListWidget()
        self.spectra_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.spectra_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        # Display-only "shorten names" — item.text() (what selection
        # matching throughout this dialog reads) is untouched by this
        # paint-only delegate.
        self.spectra_list.setItemDelegate(
            make_shortened_name_delegate(self.spectra_list, self._shorten_names_enabled)
        )
        layout.addWidget(self.spectra_list)

        btn_row = QHBoxLayout()
        for label, slot in [('Select all', self._select_all), ('Clear', self._unselect_all)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        self.show_legend_cb = QCheckBox('Show legend')
        self.show_legend_cb.setChecked(False)   # hidden by default
        self.show_legend_cb.stateChanged.connect(self._on_legend_visibility_changed)
        btn_row.addWidget(self.show_legend_cb)

        # This dialog's OWN, independent Shorten Names toggle — not tied to
        # the main window's shared checkbox of the same name (see
        # make_shorten_names_checkbox docstring). Off by default.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)
        btn_row.addWidget(self.checkBox_shorten_names)

        layout.addLayout(btn_row)

        self.spectra_list.itemSelectionChanged.connect(self._on_spectrum_selection_changed)
        return group

    # ---- Method tabs ---------------------------------------------------
    def _build_method_group(self):
        group = QGroupBox('Normalization method')
        layout = QVBoxLayout(group)

        self.mode_button_group = QButtonGroup(self)
        self._radio_map: dict = {}   # mode_key -> QRadioButton

        self.method_tabs = QTabWidget()
        self.method_tabs.setUsesScrollButtons(False)
        self.method_tabs.tabBar().setElideMode(Qt.ElideNone)
        self.method_tabs.tabBar().setExpanding(True)
        self.method_tabs.setStyleSheet(
            'QTabBar::tab { padding: 4px 8px; min-width: 120px; }'
        )

        self.method_info_button = QPushButton('? Method info')
        self.method_info_button.setToolTip('Show a description of the selected method')
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

        btn_id = 0
        for tab_name in TAB_ORDER:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            # Tall enough to show all methods in the largest category
            # ("Intensity" has 8 entries) without an internal scrollbar.
            scroll.setMinimumHeight(260)
            scroll.setFrameShape(QFrame.NoFrame)
            container = QWidget()
            tab_layout = QVBoxLayout(container)
            tab_layout.setSpacing(6)
            tab_layout.setContentsMargins(4, 6, 4, 6)

            for mode_key, meta in METHODS.items():
                if meta['tab'] != tab_name:
                    continue
                radio = QRadioButton(f"{meta['label']}    {meta['formula']}")
                radio.setToolTip(meta['info'])
                self.mode_button_group.addButton(radio, btn_id)
                self._radio_map[mode_key] = radio
                tab_layout.addWidget(radio)
                btn_id += 1

            tab_layout.addStretch()
            scroll.setWidget(container)
            self.method_tabs.addTab(scroll, tab_name)

        self.mode_button_group.buttonClicked.connect(self._on_method_changed)
        layout.addWidget(self.method_tabs)
        layout.addWidget(self.method_info_button, alignment=Qt.AlignRight)

        # Reference spectrum selector (shown only for 'reference' mode)
        self.ref_row = QWidget()
        ref_layout = QHBoxLayout(self.ref_row)
        ref_layout.setContentsMargins(0, 0, 0, 0)
        ref_layout.addWidget(QLabel('Reference spectrum:'))
        # A dropdown of actual spectrum labels removes any ambiguity about
        # which spectrum "#3" refers to, especially after sorting. The
        # underlying settings/manager still use a 0-based Python list index
        # internally — the combobox's currentIndex() already IS that index,
        # so no offset conversion is needed here (unlike the old spinbox).
        self.ref_index_combo = QComboBox()
        self.ref_index_combo.setToolTip(
            'The spectrum used as the reference for point-wise division. '
            'Listed in the order spectra were loaded into the dialog.'
        )
        ref_layout.addWidget(self.ref_index_combo, stretch=1)
        self.ref_row.setVisible(False)
        layout.addWidget(self.ref_row)

        # Percentile parameter row — shown for 'quantile' and 'top_mean' modes
        self.pct_row = QWidget()
        pct_layout = QHBoxLayout(self.pct_row)
        pct_layout.setContentsMargins(0, 0, 0, 0)
        pct_layout.addWidget(QLabel('Percentile N:'))
        self.percentile_spinbox = self._make_spinbox(
            1.0, 99.9,
            float(self.current_settings.get('percentile_value', 95.0)),
            decimals=1,
        )
        self.percentile_spinbox.setToolTip(
            'Percentile threshold used by "Robust peak" and "Mean of top N%".\n'
            'Default 95 means the top 5% of intensities in the region are used.\n'
            'Lower values are more conservative (tolerate noisier data).'
        )
        pct_layout.addWidget(self.percentile_spinbox)
        pct_layout.addWidget(QLabel('(1–99.9)'))
        pct_layout.addStretch()
        self.pct_row.setVisible(False)
        layout.addWidget(self.pct_row)

        # MSC region-fit toggle — shown only for 'msc' mode. By default MSC
        # fits its regression over the whole spectrum (classical
        # formulation); checking this restricts the fit to the defined
        # normalization region instead (e.g. a known scatter-only window).
        # Either way the correction is applied to the full spectrum.
        self.msc_row = QWidget()
        msc_layout = QHBoxLayout(self.msc_row)
        msc_layout.setContentsMargins(0, 0, 0, 0)
        self.msc_use_region_cb = QCheckBox('Fit regression within region only')
        self.msc_use_region_cb.setChecked(
            bool(self.current_settings.get('msc_use_region', False))
        )
        self.msc_use_region_cb.setToolTip(
            'Unchecked (default): the regression is fit using the whole spectrum, '
            'the classical MSC formulation.\n'
            'Checked: the regression is fit using only the defined normalization '
            'region (e.g. a known scatter-only, signal-free window), excluding real '
            'absorption peaks from the fit. The correction is still applied to the '
            'full spectrum either way.'
        )
        msc_layout.addWidget(self.msc_use_region_cb)
        msc_layout.addStretch()
        self.msc_row.setVisible(False)
        layout.addWidget(self.msc_row)

        # Target scaling group — shown for all ratio-based modes. Three
        # mutually exclusive modes for how the normalized result is scaled.
        self.target_row = QGroupBox('Result scaling')
        target_outer_layout = QVBoxLayout(self.target_row)
        target_outer_layout.setContentsMargins(10, 10, 10, 10)
        target_outer_layout.setSpacing(8)

        target_layout = QVBoxLayout()
        target_layout.setContentsMargins(4, 0, 0, 0)
        target_layout.setSpacing(6)
        target_outer_layout.addLayout(target_layout)

        self.target_mode_group = QButtonGroup(self)

        standard_row = QHBoxLayout()
        self.target_standard_radio = QRadioButton('Standard')
        self.target_standard_radio.setToolTip(
            'Each spectrum is divided by its own computed factor (peak value, '
            'area, norm, percentile, etc.) with no further scaling.\n'
            'For Peak intensity the result is exactly 1.0 at the maximum. '
            'For Area and Vector norm the result is NOT near 1.0 \u2014 it depends '
            'on your x-axis units and intensity scale.\n'
            'This is the standard/default behaviour for each method.'
        )
        self.target_mode_group.addButton(self.target_standard_radio, 0)
        standard_row.addWidget(self.target_standard_radio)
        standard_row.addStretch()

        self.target_info_button = QPushButton('?')
        self.target_info_button.setFixedWidth(24)
        self.target_info_button.setToolTip('Explain the result scaling options')
        self.target_info_button.setStyleSheet(
            'QPushButton {'
            '  background-color: #F57C00;'
            '  color: white;'
            '  border: none;'
            '  border-radius: 4px;'
            '  font-weight: bold;'
            '}'
            'QPushButton:hover { background-color: #E65100; }'
        )
        self.target_info_button.clicked.connect(self._show_target_scaling_info)
        standard_row.addWidget(self.target_info_button)
        target_layout.addLayout(standard_row)

        self.target_mean_relative_radio = QRadioButton('Keep original scale')
        self.target_mean_relative_radio.setToolTip(
            'Spectra are still corrected relative to each other, but the '
            'absolute scale stays close to the original data instead of\n'
            'being forced to 1.0. Example: if the per-spectrum factors are '
            '100, 95, 105, the results will be \u22481.00, \u22480.95, \u22481.05\n'
            '(relative to the group mean of 100) instead of exactly 1.00 each. '
            'Useful when your data has a familiar natural scale\n'
            '(e.g. absorbance around 0.7, Raman counts around 10000) that '
            'you want preserved after normalization.\n'
            'Computed across ALL spectra being normalized, not just the ones shown in preview.'
        )
        self.target_mode_group.addButton(self.target_mean_relative_radio, 1)
        target_layout.addWidget(self.target_mean_relative_radio)

        custom_row = QHBoxLayout()
        custom_row.setSpacing(8)
        self.target_custom_radio = QRadioButton('Custom target:')
        self.target_custom_radio.setToolTip(
            'Multiply the standard result by a value you specify, e.g. 0.7 or 10000.\n'
            'For Peak intensity / Robust peak / Mean of top N% the standard result '
            'is already \u22481.0, so this sets the new target directly.\n'
            'For Area / Vector norm the standard result is not near 1.0, so this '
            'value becomes the new effective target for the chosen factor.'
        )
        self.target_mode_group.addButton(self.target_custom_radio, 2)
        custom_row.addWidget(self.target_custom_radio)

        self.target_value_spinbox = self._make_spinbox(
            1e-6, 1e9,
            float(self.current_settings.get('target_value', 1.0)),
            decimals=4,
        )
        self.target_value_spinbox.setMinimumWidth(110)
        self.target_value_spinbox.setEnabled(False)
        custom_row.addWidget(self.target_value_spinbox, stretch=1)
        target_layout.addLayout(custom_row)

        # Restore saved target mode (default 'standard')
        saved_target_mode = self.current_settings.get('target_mode', 'standard')
        if saved_target_mode == 'mean_relative':
            self.target_mean_relative_radio.setChecked(True)
        elif saved_target_mode == 'custom':
            self.target_custom_radio.setChecked(True)
            self.target_value_spinbox.setEnabled(True)
        else:
            self.target_standard_radio.setChecked(True)

        self.target_mode_group.buttonClicked.connect(self._on_target_mode_changed)

        self.target_row.setVisible(False)
        layout.addWidget(self.target_row)

        return group

    # ---- Regions group -------------------------------------------------
    def _build_regions_group(self):
        # No title here — CollapsibleSection's header already shows
        # "Normalization region(s)", so a second QGroupBox title would duplicate it.
        group = QGroupBox()
        group.setStyleSheet('QGroupBox { border: none; }')
        group.setToolTip(
            'One or more spectral regions used to compute the normalization '
            'coefficient. The coefficient is applied to the full spectrum.\n\n'
            'Include mode: coefficient computed from the selected regions only.\n'
            'Exclude mode: coefficient computed from everything EXCEPT the selected regions.\n\n'
            'Click and drag on the plot to add a region, or use the controls below.'
        )
        layout = QVBoxLayout(group)

        # Include / Exclude mode toggle
        mode_row = QHBoxLayout()
        self._include_exclude_group = QButtonGroup(self)
        self._include_radio = QRadioButton('Include regions')
        self._include_radio.setToolTip(
            'Compute the normalization coefficient using ONLY the selected regions.'
        )
        self._exclude_radio = QRadioButton('Exclude regions')
        self._exclude_radio.setToolTip(
            'Compute the normalization coefficient from the full spectrum '
            'MINUS the selected regions (e.g. to avoid a fluorescence band).'
        )
        self._include_exclude_group.addButton(self._include_radio, 0)
        self._include_exclude_group.addButton(self._exclude_radio, 1)
        self._include_radio.setChecked(True)   # default
        mode_row.addWidget(self._include_radio)
        mode_row.addWidget(self._exclude_radio)
        mode_row.addStretch()

        # Small round "?" — quick reminder of how to add/edit/remove
        # regions, right next to the controls it explains, same style and
        # pattern as the Band Ratio / 2D map "Define Spectral Range"
        # dialog's own help button (a self-contained popup, not the full
        # Help window opened by the dialog's main Help button).
        region_help_btn = QPushButton('?')
        region_help_btn.setFixedWidth(32)
        region_help_btn.setFixedHeight(24)
        region_help_btn.setToolTip('Quick help for defining regions')
        region_help_btn.setStyleSheet(
            'QPushButton { font-weight:bold; border-radius:11px; '
            'background:#1565C0; color:white; }'
            'QPushButton:hover { background:#1976D2; }'
        )
        region_help_btn.clicked.connect(self._show_region_quick_help)
        mode_row.addWidget(region_help_btn)
        layout.addLayout(mode_row)

        # Restore saved mode if present
        if self.current_settings.get('is_exclude_mode', False):
            self._exclude_radio.setChecked(True)

        # Update canvas shading when mode changes
        self._include_exclude_group.buttonClicked.connect(self._refresh_canvas_spans)
        self._include_exclude_group.buttonClicked.connect(self._update_preview)

        # Region list — ExtendedSelection so Ctrl/Shift-click can select
        # several regions at once for bulk removal (see _remove_region).
        # Editing a single region (populating From/To, switching Add ->
        # Update) only activates when exactly one row is selected
        # — see _on_region_selected.
        self.regions_list = QListWidget()
        self.regions_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.regions_list.setMaximumHeight(80)
        self.regions_list.setToolTip(
            'Active normalization regions — Ctrl/Shift-click to select more than one for Remove.'
        )
        layout.addWidget(self.regions_list)

        # Add-region controls — labelled From/To (like the Band Ratio /
        # 2D map "Define Spectral Range" dialog) rather than X-min/X-max:
        # what matters here is the range itself, not which end is
        # nominally the "min". Plain QLineEdit + QDoubleValidator, same
        # pattern (and variable-naming caveat) as that dialog's From/To
        # fields — the widget variable names keep their original
        # x_min_spinbox/x_max_spinbox names since they're referenced by
        # that name throughout the rest of this file, even though they're
        # text fields now, not spin boxes.
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel('From:'))
        self.x_min_spinbox = QLineEdit()
        self.x_min_spinbox.setValidator(QDoubleValidator())
        self.x_min_spinbox.setPlaceholderText('e.g. 800')
        add_row.addWidget(self.x_min_spinbox)
        add_row.addWidget(QLabel('To:'))
        self.x_max_spinbox = QLineEdit()
        self.x_max_spinbox.setValidator(QDoubleValidator())
        self.x_max_spinbox.setPlaceholderText('e.g. 1800')
        add_row.addWidget(self.x_max_spinbox)
        # Full range sits on the same row as From/To since it just fills
        # those two fields — keeping it here instead of down with
        # Add/Remove makes that relationship obvious.
        full_range_btn = QPushButton('Full range')
        full_range_btn.setToolTip(
            'Reset From/To above to the full data range — does not add a region.\n'
            'Click Add region afterwards if you actually want a full-range region.'
        )
        full_range_btn.clicked.connect(self._set_full_range)
        add_row.addWidget(full_range_btn)
        layout.addLayout(add_row)

        action_row = QHBoxLayout()
        self.add_region_btn = QPushButton('Add region')
        self.add_region_btn.setToolTip(
            'Add the From / To values entered above as a new region.\n'
            'Drag on the plot to add regions without using this button.'
        )
        self.add_region_btn.clicked.connect(self._add_region)
        action_row.addWidget(self.add_region_btn)

        # Cancel edit sits right next to Add/Update — while editing, this
        # is the button you actually reach for, not something at the far
        # end of the row past Remove. Only shown while a region is
        # selected (i.e. while add_region_btn reads "Update"). Qt's
        # QListWidget does NOT clear its selection when you click empty
        # space below the items — that only clears the visual highlight
        # on some platforms/styles, not reliably here — so an explicit way
        # out of edit mode is needed rather than relying on clicking away.
        self.cancel_region_edit_btn = QPushButton('Cancel edit')
        self.cancel_region_edit_btn.setToolTip(
            'Deselect the region and go back to adding a new one.'
        )
        self.cancel_region_edit_btn.setVisible(False)
        self.cancel_region_edit_btn.clicked.connect(self._cancel_region_edit)
        action_row.addWidget(self.cancel_region_edit_btn)

        remove_btn = QPushButton('Remove')
        remove_btn.setToolTip(
            'Remove the selected region(s).\nCtrl/Shift-click regions in the list to select more than one.'
        )
        remove_btn.clicked.connect(self._remove_region)
        action_row.addWidget(remove_btn)

        layout.addLayout(action_row)

        # Thin separator so the region controls above (Add/Update, Cancel
        # edit, Remove) read as visually distinct from the preset controls
        # below (Preset, Load, Save as…, Delete) — they operate on
        # different things (the current region list vs. named presets on
        # disk) even though they sit right next to each other.
        region_preset_sep = QFrame()
        region_preset_sep.setFrameShape(QFrame.HLine)
        region_preset_sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(region_preset_sep)

        # --- Region presets: save the current region set under a name and
        # reload it later, or on a different dataset with the same kind of
        # samples (e.g. "CD silent region", "Raman fingerprint area"). Saved
        # to disk via NormalizationManager so they persist across dialog
        # sessions and application restarts.
        preset_row = QHBoxLayout()
        preset_label = QLabel('Preset:')
        preset_label.setStyleSheet('border: none; background: transparent; font-weight: normal;')
        preset_row.addWidget(preset_label)
        self.preset_combo = QComboBox()
        self.preset_combo.setToolTip('Saved region presets')
        preset_row.addWidget(self.preset_combo, stretch=1)

        load_preset_btn = QPushButton('Load')
        load_preset_btn.setToolTip('Replace the current regions with the selected preset.')
        load_preset_btn.clicked.connect(self._load_region_preset)
        preset_row.addWidget(load_preset_btn)

        save_preset_btn = QPushButton('Save as\u2026')
        save_preset_btn.setToolTip('Save the current regions under a new or existing name.')
        save_preset_btn.clicked.connect(self._save_region_preset)
        preset_row.addWidget(save_preset_btn)

        delete_preset_btn = QPushButton('Delete')
        delete_preset_btn.setToolTip('Delete the selected preset.')
        delete_preset_btn.clicked.connect(self._delete_region_preset)
        preset_row.addWidget(delete_preset_btn)

        preset_info_btn = QPushButton('?')
        preset_info_btn.setFixedWidth(24)
        preset_info_btn.setToolTip('Explain region presets')
        preset_info_btn.setStyleSheet(
            'QPushButton {'
            '  background-color: #F57C00;'
            '  color: white;'
            '  border: none;'
            '  border-radius: 4px;'
            '  font-weight: bold;'
            '}'
            'QPushButton:hover { background-color: #E65100; }'
        )
        preset_info_btn.clicked.connect(self._show_preset_info)
        preset_row.addWidget(preset_info_btn)

        layout.addLayout(preset_row)
        self._refresh_preset_combo()

        self.regions_list.itemSelectionChanged.connect(self._on_region_selected)

        return group

    # ---- Canvas panel --------------------------------------------------
    def _create_canvas_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.canvas_tabs = QTabWidget()
        self.canvas_tabs.setUsesScrollButtons(False)
        self.canvas_tabs.tabBar().setElideMode(Qt.ElideNone)
        self.canvas_tabs.setStyleSheet(
            'QTabBar::tab { padding: 4px 16px; min-width: 160px; }'
        )

        # --- Raw tab: original spectra + region selection (existing behaviour) ---
        raw_tab = QWidget()
        raw_layout = QVBoxLayout(raw_tab)

        self.canvas = NormalizationPlotCanvas(self)
        self.toolbar = NavigationToolbar(self.canvas, raw_tab)

        hint = QLabel(
            '\u2714 Click and drag on the plot to define a normalization region, '
            'then click \u201cAdd region\u201d — or enter From / To manually.'
        )
        hint.setStyleSheet(
            'color: #1976D2; font-style: italic; padding: 4px; '
            'background-color: #E3F2FD; border-radius: 3px;'
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)

        self.coordinates_label = QLabel('')
        self.coordinates_label.setStyleSheet('background-color: #f0f0f0; padding: 2px;')

        raw_layout.addWidget(self.toolbar)
        raw_layout.addWidget(hint)
        raw_layout.addWidget(self.coordinates_label)
        raw_layout.addWidget(self.canvas)

        self.canvas.range_selected.connect(self._on_canvas_range_selected)

        # --- Preview tab: live result of applying the current settings -----------
        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)

        self.preview_canvas = NormalizationPlotCanvas(self)
        self.preview_toolbar = NavigationToolbar(self.preview_canvas, preview_tab)

        self.show_preview_regions_cb = QCheckBox('Show shaded regions')
        self.show_preview_regions_cb.setChecked(True)
        self.show_preview_regions_cb.setToolTip(
            'Show or hide the selected normalization region(s) as shaded '
            'areas on this preview plot, mirroring the Raw tab.'
        )
        self.show_preview_regions_cb.stateChanged.connect(self._refresh_canvas_spans)

        preview_toolbar_row = QHBoxLayout()
        preview_toolbar_row.addWidget(self.preview_toolbar)
        preview_toolbar_row.addStretch()
        preview_toolbar_row.addWidget(self.show_preview_regions_cb)

        preview_hint = QLabel(
            '\U0001F441 Live preview of the normalized result for the spectra '
            'selected in the list, using the current method and settings.'
        )
        preview_hint.setStyleSheet(
            'color: #2E7D32; font-style: italic; padding: 4px; '
            'background-color: #E8F5E9; border-radius: 3px;'
        )
        preview_hint.setAlignment(Qt.AlignCenter)
        preview_hint.setWordWrap(True)

        preview_layout.addLayout(preview_toolbar_row)
        preview_layout.addWidget(preview_hint)
        preview_layout.addWidget(self.preview_canvas)

        # --- Per-spectrum factor table: shows the raw computed factor (peak,
        # area, norm, percentile...) for each spectrum, with outliers
        # highlighted. Only meaningful for RATIO_BASED_MODES — hidden for
        # SNV/MSC/SVD/reference/offset_correction where there is no single
        # per-spectrum scalar factor to show. Collapsed by default since
        # it's a diagnostic aid, not something needed on every normalization.
        self.factor_table_section = CollapsibleSection(
            'Per-spectrum factors', expanded=False
        )
        factor_table_widget = QWidget()
        factor_table_layout = QVBoxLayout(factor_table_widget)
        factor_table_layout.setContentsMargins(0, 0, 0, 0)

        factor_hint = QLabel(
            'Shows the raw factor each spectrum is divided by (before any '
            'result scaling). Rows highlighted in orange deviate by more '
            'than 3 standard deviations from the mean \u2014 check these '
            'spectra for cosmic ray spikes, baseline issues, or other '
            'problems before trusting the normalization.'
        )
        factor_hint.setWordWrap(True)
        factor_hint.setStyleSheet('color: #555; font-size: 9pt;')
        factor_table_layout.addWidget(factor_hint)

        self.factor_table = QTableWidget()
        self.factor_table.setColumnCount(3)
        self.factor_table.setHorizontalHeaderLabels(['Spectrum', 'Factor', 'Deviation'])
        self.factor_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.factor_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.factor_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.factor_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.factor_table.setMaximumHeight(180)
        factor_table_layout.addWidget(self.factor_table)

        self.factor_table_section.setContentWidget(factor_table_widget)
        preview_layout.addWidget(self.factor_table_section)

        # --- Save: exports whatever is checked/selected in the "Selected
        # spectra" listbox at the top of the dialog. That list already
        # doubles as a viewing-convenience selector and a save selector —
        # no need for a second, separate list duplicating the same spectra.
        save_btn_row = QHBoxLayout()
        save_btn_row.addStretch()
        self.save_selected_btn = QPushButton('Save selected spectra\u2026')
        self.save_selected_btn.setToolTip(
            'Exports the normalized result for the spectra currently selected '
            'in the "Selected spectra" list, using this dialog\u2019s current '
            'method and result-scaling settings.'
        )
        self.save_selected_btn.setStyleSheet(
            'QPushButton {'
            '  background-color: #2E7D32;'
            '  color: white;'
            '  border: none;'
            '  border-radius: 4px;'
            '  padding: 4px 12px;'
            '  font-weight: bold;'
            '}'
            'QPushButton:hover { background-color: #1B5E20; }'
        )
        self.save_selected_btn.clicked.connect(self._save_normalized_spectra)
        save_btn_row.addWidget(self.save_selected_btn)
        preview_layout.addLayout(save_btn_row)

        self.canvas_tabs.addTab(raw_tab, 'Raw')
        self.canvas_tabs.addTab(preview_tab, 'Preview (normalized)')

        layout.addWidget(self.canvas_tabs)
        return widget

    # =================================================================
    # Initialisation
    # =================================================================
    def _initialize_dialog(self):
        self._populate_spectrum_list()
        self._populate_reference_combo()
        self._set_initial_method()
        self._refresh_regions_list()
        self._on_method_changed()
        self._initialization_complete = True

        if self.spectra_list.count() > 0:
            self.spectra_list.item(0).setSelected(True)
            self._on_spectrum_selection_changed()

        self.help_button.clicked.connect(self._show_help)

        # Live preview — recompute whenever a parameter that affects the
        # normalized result changes.
        self.target_value_spinbox.valueChanged.connect(self._update_preview)
        self.percentile_spinbox.valueChanged.connect(self._update_preview)
        self.ref_index_combo.currentIndexChanged.connect(self._update_preview)
        self.msc_use_region_cb.stateChanged.connect(self._update_preview)
            
    def _populate_spectrum_list(self):
        self.spectra_list.clear()
        self._list_to_spectra = {}
        spectra = sorted(self.selected_spectra, key=lambda x: x.get('label', ''))
        if not self.sort_ascending:
            spectra = list(reversed(spectra))
        for i, s in enumerate(spectra):
            item = QListWidgetItem(s.get('label', f'Spectrum_{i}'))
            self.spectra_list.addItem(item)
            self._list_to_spectra[i] = s   # index → spectrum, matches list order            

    def _populate_reference_combo(self):
        """
        Populate the reference-spectrum dropdown from self.selected_spectra
        in its ORIGINAL (unsorted) order — this is the same order the manager
        receives and indexes into (spectra[reference_spectrum_index]), so the
        combobox's currentIndex() can be used directly as the 0-based index
        without any offset conversion. Sorting the spectra_list display does
        NOT affect this combobox or its underlying index mapping.
        """
        self.ref_index_combo.clear()
        for i, s in enumerate(self.selected_spectra):
            label = s.get('label', f'Spectrum_{i}')
            self.ref_index_combo.addItem(f'{i + 1}. {label}')

        saved_index = int(self.current_settings.get('reference_spectrum_index', 0))
        if 0 <= saved_index < self.ref_index_combo.count():
            self.ref_index_combo.setCurrentIndex(saved_index)
        elif self.ref_index_combo.count() > 0:
            self.ref_index_combo.setCurrentIndex(0)

    def _set_initial_method(self):
        mode = self.current_settings.get('normalization_mode', 'max_peak')
        if mode not in self._radio_map:
            mode = 'max_peak'
        radio = self._radio_map[mode]
        radio.setChecked(True)

        # Switch to the correct tab
        meta = METHODS.get(mode)
        if meta:
            tab_name = meta['tab']
            for i in range(self.method_tabs.count()):
                if self.method_tabs.tabText(i) == tab_name:
                    self.method_tabs.setCurrentIndex(i)
                    break

    # =================================================================
    # Region management
    # =================================================================
    def _refresh_regions_list(self, select_row=None):
        """
        Rebuild the region list from self._regions.

        If select_row is given, that row is reselected afterwards (sticky
        selection after an in-place update, so further edits don't require
        reselecting). Otherwise the list ends up with no selection, which
        \u2014 via _on_region_selected \u2014 resets the Add/Update button back to
        "Add region".
        """
        self.regions_list.clear()
        for (x0, x1) in self._regions:
            self.regions_list.addItem(f'{x0:.4g} \u2013 {x1:.4g}')
        if select_row is not None and 0 <= select_row < self.regions_list.count():
            self.regions_list.setCurrentRow(select_row)
        else:
            # QListWidget.clear() doesn't reliably re-emit itemSelectionChanged,
            # so explicitly drop out of edit mode rather than relying on that.
            self._exit_region_edit_mode()
        self._refresh_canvas_spans()
        self._update_preview()

    def _refresh_canvas_spans(self, _=None):
        is_exclude = hasattr(self, '_exclude_radio') and self._exclude_radio.isChecked()
        if hasattr(self, 'canvas'):
            self.canvas.update_regions(self._regions, is_exclude=is_exclude)
        # Preview tab mirrors the same shaded regions as Raw, gated by its own
        # "Show shaded regions" checkbox (defaults on). preview_canvas.plot_spectra()
        # / show_message() both call axes.clear(), which wipes any previously
        # drawn spans — so this also needs re-calling after every preview
        # redraw (see _do_update_preview), not just when the region list itself
        # changes.
        if hasattr(self, 'preview_canvas') and hasattr(self, 'show_preview_regions_cb'):
            regions_to_show = self._regions if self.show_preview_regions_cb.isChecked() else []
            self.preview_canvas.update_regions(regions_to_show, is_exclude=is_exclude)

    def _add_region(self):
        """
        Add the From/To values above as a new region — or, if a region
        is currently selected in regions_list (self._editing_region_row set
        by _on_region_selected), update that region in place instead. The
        button itself is relabeled "Update" while editing, so this
        single slot covers both cases.
        """
        try:
            x0 = float(self.x_min_spinbox.text())
            x1 = float(self.x_max_spinbox.text())
        except ValueError:
            return
        if x1 <= x0:
            return
        if self._editing_region_row is not None and 0 <= self._editing_region_row < len(self._regions):
            row = self._editing_region_row
            # Avoid exact duplicates: updating to values that already
            # match a DIFFERENT existing region would create a duplicate —
            # select that region instead of creating one.
            other_regions = self._regions[:row] + self._regions[row + 1:]
            if (x0, x1) in other_regions:
                self._refresh_regions_list(select_row=self._regions.index((x0, x1)))
                return
            self._regions[row] = (x0, x1)
            self._refresh_regions_list(select_row=row)
        else:
            # Avoid exact duplicates
            if (x0, x1) not in self._regions:
                self._regions.append((x0, x1))
            else:
                self._refresh_regions_list(select_row=self._regions.index((x0, x1)))
                return
            self._refresh_regions_list()

    def _remove_region(self):
        """Remove every currently-selected region — Ctrl/Shift-click in
        the list first to remove more than one at a time."""
        rows = sorted({self.regions_list.row(it) for it in self.regions_list.selectedItems()}, reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self._regions):
                self._regions.pop(row)
        self._refresh_regions_list()

    def _on_region_selected(self):
        """
        Selecting a region loads its bounds into the From/To fields and
        switches the Add button into "Update" mode (with a "Cancel edit"
        button appearing alongside it). Deselecting (or the list being
        rebuilt with nothing reselected) switches back to "Add region".

        Reads selectedItems() rather than currentRow(): QListWidget keeps
        its internal "current item" pointed at the last row even after the
        row is no longer part of the actual (highlighted) selection, so
        currentRow() alone is not a reliable "is a region selected?" check.
        Note that clicking empty space below the list does NOT clear the
        selection here — that's exactly why an explicit "Cancel edit"
        button exists instead of relying on that.
        """
        selected = self.regions_list.selectedItems()
        row = self.regions_list.row(selected[0]) if len(selected) == 1 else -1
        if 0 <= row < len(self._regions):
            x0, x1 = self._regions[row]
            self.x_min_spinbox.setText(str(x0))
            self.x_max_spinbox.setText(str(x1))
            self._editing_region_row = row
            self.add_region_btn.setText('Update')
            self.add_region_btn.setToolTip(
                'Update the selected region with the From / To values above.'
            )
            self.cancel_region_edit_btn.setVisible(True)
        else:
            self._exit_region_edit_mode()

    def _cancel_region_edit(self):
        """Explicitly leave edit mode without removing or changing the
        selected region — used by the 'Cancel edit' button, since clicking
        empty space in regions_list does not clear its selection."""
        self.regions_list.clearSelection()
        self._exit_region_edit_mode()

    def _exit_region_edit_mode(self):
        self._editing_region_row = None
        self.add_region_btn.setText('Add region')
        self.add_region_btn.setToolTip(
            'Add the From / To values entered above as a new region.\n'
            'Drag on the plot to add regions without using this button.'
        )
        self.cancel_region_edit_btn.setVisible(False)

    def _on_canvas_range_selected(self, x_min, x_max):
        """Called when user drags on the canvas — add region immediately."""
        if x_max <= x_min:
            return
        x0, x1 = round(x_min, 4), round(x_max, 4)
        # Update the From/To fields so the user can see what was captured
        self.x_min_spinbox.setText(str(x0))
        self.x_max_spinbox.setText(str(x1))
        # Auto-add to the regions list (no need to press "Add region")
        if (x0, x1) not in self._regions:
            self._regions.append((x0, x1))
        self._refresh_regions_list()

    def _set_full_range(self):
        """Reset the From/To fields to the full data range, ready to click
        Add if a full-range region is actually wanted. This only fills the
        fields — it does NOT add or replace anything in the regions list,
        so it can't accidentally wipe out regions you've already defined."""
        if not self.selected_spectra:
            return
        x_mins, x_maxs = [], []
        for s in self.selected_spectra:
            x = s.get('x_scale', [])
            if len(x) > 0:
                x_mins.append(float(np.min(x)))
                x_maxs.append(float(np.max(x)))
        if x_mins:
            x0, x1 = min(x_mins), max(x_maxs)
            self.x_min_spinbox.setText(str(x0))
            self.x_max_spinbox.setText(str(x1))

    # ---- Region presets --------------------------------------------------
    def _refresh_preset_combo(self):
        """Reload the preset dropdown from disk."""
        from src.modules.data_analysis.normalization_manager import NormalizationManager
        current_text = self.preset_combo.currentText() if self.preset_combo.count() else ''
        self.preset_combo.clear()
        presets = NormalizationManager.list_region_presets()
        self.preset_combo.addItems(sorted(presets.keys()))
        if current_text:
            idx = self.preset_combo.findText(current_text)
            if idx >= 0:
                self.preset_combo.setCurrentIndex(idx)

    def _load_region_preset(self):
        from src.modules.data_analysis.normalization_manager import NormalizationManager
        name = self.preset_combo.currentText()
        if not name:
            return
        presets = NormalizationManager.list_region_presets()
        regions = presets.get(name)
        if regions is None:
            return
        self._regions = list(regions)
        self._refresh_regions_list()

    def _save_region_preset(self):
        from PyQt5.QtWidgets import QInputDialog, QMessageBox
        from src.modules.data_analysis.normalization_manager import NormalizationManager

        if not self._regions:
            QMessageBox.warning(
                self, 'No regions defined',
                'Define at least one region before saving a preset.'
            )
            return

        default_name = self.preset_combo.currentText()
        name, ok = QInputDialog.getText(
            self, 'Save Region Preset', 'Preset name:', text=default_name
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        existing = NormalizationManager.list_region_presets()
        if name in existing:
            confirm = QMessageBox.question(
                self, 'Overwrite Preset',
                f'A preset named "{name}" already exists. Overwrite it?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return

        NormalizationManager.save_region_preset(name, self._regions)
        self._refresh_preset_combo()
        idx = self.preset_combo.findText(name)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)

    def _delete_region_preset(self):
        from PyQt5.QtWidgets import QMessageBox
        from src.modules.data_analysis.normalization_manager import NormalizationManager

        name = self.preset_combo.currentText()
        if not name:
            return
        confirm = QMessageBox.question(
            self, 'Delete Preset',
            f'Delete the preset "{name}"? This cannot be undone.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        NormalizationManager.delete_region_preset(name)
        self._refresh_preset_combo()

    def _show_preset_info(self):
        """Show a popup explaining how region presets work."""
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self, 'Region Presets',
            '<b>What presets are</b><br>'
            'A named, saved set of normalization regions you can reload later, '
            'on a different dataset, or in a future session. Saved to a file in '
            'your user profile, so they persist across dialog sessions and '
            'application restarts \u2014 not tied to any one project.<br><br>'
            '<b>Typical workflow</b><br>'
            '1. Define regions as usual (drag on the plot or use From/To + '
            'Add region).<br>'
            '2. Click <b>Save as\u2026</b> and type a name (e.g. "CD silent region"). '
            'This adds it to the dropdown.<br>'
            '3. Later, pick the name from the dropdown and click <b>Load</b> to '
            'replace the current regions with that preset.<br>'
            '4. Click <b>Delete</b> to permanently remove the selected preset.<br><br>'
            '<b>The empty box next to "Preset:"</b><br>'
            'That is the dropdown itself \u2014 it shows empty until at least one '
            'preset has been saved. It is not a separate text field; it lists '
            'every saved preset name once you start saving them.'
        )

    def _show_region_quick_help(self):
        """Self-contained quick-reference popup for defining regions —
        same pattern as the Band Ratio / 2D map "Define Spectral Range"
        dialog's own "?" button (a small popup right next to the controls
        it explains, not the full Help window opened by this dialog's main
        Help button)."""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle('Normalization Region — Help')
        dlg.resize(480, 460)
        lay = QVBoxLayout(dlg)
        tb = QTextBrowser()
        tb.setHtml(_REGION_HELP_TEXT)
        tb.setOpenExternalLinks(True)
        lay.addWidget(tb)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        dlg.exec_()

    # =================================================================
    # Method selection
    # =================================================================
    def _on_method_changed(self, _button=None):
        mode = self._current_mode()
        self.ref_row.setVisible(mode == 'reference')
        self.pct_row.setVisible(mode in ('quantile', 'top_mean'))
        self.msc_row.setVisible(mode == 'msc')
        self.target_row.setVisible(mode in RATIO_BASED_MODES)
        self._update_preview()

    def _show_method_info(self):
        """Show a popup with the description of the currently selected method."""
        mode = self._current_mode()
        meta = METHODS.get(mode)
        if not meta:
            return
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            meta['label'],
            f"<b>{meta['label']}</b>&nbsp;&nbsp;{meta['formula']}<br><br>{meta['info']}"
        )

    def _show_target_scaling_info(self):
        """Show a popup explaining the three result-scaling options."""
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            'Result scaling',
            '<b>Standard</b><br>'
            'Each spectrum is divided by its own factor (peak, area, norm, '
            'percentile, etc.) with no further scaling. For Peak intensity '
            'the result is exactly 1.0 at the maximum; for Area / Vector norm '
            'the result is NOT near 1.0 \u2014 it depends on your data\u2019s units.<br><br>'
            '<b>Keep original scale (relative to mean)</b><br>'
            'Spectra are still corrected relative to each other, but the '
            'absolute scale stays close to the original data instead of '
            'being forced to a fixed value. Example: if the per-spectrum '
            'factors are 100, 95, 105, the results become \u22481.00, \u22480.95, '
            '\u22481.05 \u00d7 100 \u2248 100, 95, 105 \u2014 i.e. the same relative '
            'correction, but on the original scale. Useful when your data has '
            'a familiar natural magnitude (e.g. absorbance around 0.7, Raman '
            'counts around 10000) that you want preserved. Computed across '
            'ALL spectra being normalized, not just the ones shown in preview.<br><br>'
            '<b>Custom target value</b><br>'
            'Multiply the standard result by a value you specify, e.g. 0.7 or 10000.'
        )

    def _on_target_mode_changed(self, _button=None):
        """Enable the custom target spinbox only when 'Custom target value' is selected."""
        self.target_value_spinbox.setEnabled(self.target_custom_radio.isChecked())
        self._update_preview()

    def _current_target_mode(self):
        if self.target_mean_relative_radio.isChecked():
            return 'mean_relative'
        if self.target_custom_radio.isChecked():
            return 'custom'
        return 'standard'

    def _current_mode(self):
        checked = self.mode_button_group.checkedButton()
        if checked is None:
            return 'vector'
        for key, radio in self._radio_map.items():
            if radio is checked:
                return key
        return 'vector'

    # =================================================================
    # Spectra list helpers
    # =================================================================
    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _on_shorten_names_toggled(self, _state=None):
        """Refresh everything this dialog's own Shorten Names checkbox
        affects: the spectra list's paint-only delegate (repaints on the
        next event loop pass regardless, but an explicit viewport update
        makes the toggle feel instant) and the Raw/Preview canvases' legend
        text, which is baked into display_labels at plot time rather than
        painted live, so both need an explicit redraw to pick up the
        change."""
        self.spectra_list.viewport().update()
        if self._initialization_complete:
            self._on_spectrum_selection_changed()
            self._do_update_preview()

    def _display_labels_map(self):
        """{full_label: display_label} for self.selected_spectra — see
        label_shortening.py. Legend/title text only."""
        if not self._shorten_names_enabled():
            return {}
        all_labels = [s.get('label', '') for s in self.selected_spectra]
        if len(all_labels) < 2:
            return {}
        return compute_distinguishing_labels(all_labels)

    def _on_spectrum_selection_changed(self):
        if not self._initialization_complete:
            return
        selected_labels = {item.text() for item in self.spectra_list.selectedItems()}
        selected = [s for s in self._list_to_spectra.values()
                    if s.get('label') in selected_labels]
        self.canvas.plot_spectra(selected if selected else [], display_labels=self._display_labels_map())
        self._refresh_canvas_spans()
        self.canvas.set_legend_visible(self.show_legend_cb.isChecked())
        self._update_preview()

    def _update_preview(self, *_args):
        """
        Request a preview recompute, debounced by 250ms so rapid changes
        (typing, dragging) don't trigger a recompute on every single event.
        """
        if not self._initialization_complete or not hasattr(self, 'preview_canvas'):
            return
        self._preview_timer.start()  # restarts if already running

    def _do_update_preview(self):
        """
        Recompute the normalized result and redraw the Preview tab.

        Important: for 'mean_relative' target mode the cross-spectrum mean
        factor must be computed from ALL spectra loaded in the dialog
        (self.selected_spectra) — exactly as it will be when Apply runs —
        not just the subset currently selected for viewing. Otherwise the
        preview would show a different (wrong) scale than the real result.
        We therefore always normalize the full dataset, then only plot the
        subset that's selected in the list.

        The full normalized result is cached in self._last_normalized_all so
        Save can export it without recomputing.

        A wait cursor is shown for the duration of the recompute. For small
        datasets this is too brief to notice; for SVD, MSC, or "Keep original
        scale" on a large number of spectra — all of which must process the
        whole dataset, not just the previewed subset — it gives visible
        feedback that something is happening rather than appearing frozen.
        """
        if not hasattr(self, 'preview_canvas'):
            return

        selected_labels = {item.text() for item in self.spectra_list.selectedItems()}

        if not self.selected_spectra:
            self.preview_canvas.plot_spectra([])
            self._refresh_canvas_spans()
            self._last_normalized_all = []
            self._refresh_factor_table([], None)
            return

        # Don't compute or show a "normalized" result before any region has
        # been defined — UNLESS the current method genuinely doesn't use a
        # region at all (Reference spectrum, always; MSC, only when its
        # "fit within region" checkbox is unchecked, i.e. the default
        # whole-spectrum fit). For every other method, the manager treats
        # "no region" as "use the whole spectrum" as a permissive fallback,
        # but showing that silently in the Preview tab looks like a real
        # result when nothing has actually been configured yet.
        current_mode = self._current_mode()
        mode_needs_region = not (
            current_mode == 'reference'
            or (current_mode == 'msc' and not self.msc_use_region_cb.isChecked())
        )
        if mode_needs_region and not self._regions:
            self.preview_canvas.plot_spectra([])
            self._last_normalized_all = []
            self._refresh_factor_table([], None)
            self.preview_canvas.show_message(
                'Define at least one normalization region (drag on the plot, or\n'
                'click "Full range" then "Add region") to see a preview here.'
            )
            self._refresh_canvas_spans()
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            from src.modules.data_analysis.normalization_manager import NormalizationManager
            scratch_manager = NormalizationManager()
            settings = self.get_settings()
            scratch_manager.update_settings(settings)

            try:
                normalized_all = scratch_manager.normalize_spectra(self.selected_spectra, settings)
            except Exception as e:
                logger.debug(f'Preview computation failed: {e}')
                self.preview_canvas.plot_spectra([])
                self._refresh_canvas_spans()
                self._last_normalized_all = []
                self._refresh_factor_table([], None)
                return

            self._last_normalized_all = normalized_all
            self._refresh_factor_table(normalized_all, scratch_manager)

            normalized_subset = [s for s in normalized_all if s.get('label') in selected_labels]

            self.preview_canvas.plot_spectra(normalized_subset, display_labels=self._display_labels_map())
            self.preview_canvas.set_legend_visible(self.show_legend_cb.isChecked())
            self._refresh_canvas_spans()
        finally:
            QApplication.restoreOverrideCursor()

    def _refresh_factor_table(self, normalized_all: list, manager) -> None:
        """
        Populate the per-spectrum factor table from normalization_info,
        showing every spectrum's deviation from the batch mean (in standard
        deviations) and highlighting rows flagged as outliers by the
        manager (|z-score| > 3).

        Reads either 'factor' (RATIO_BASED_MODES: Peak intensity, Area,
        Vector norm, Robust peak, Mean of top N%) or 'svd_factor' (SVD
        factor normalization) — both are a single per-spectrum scalar
        suitable for outlier checking, just stored under different keys
        because SVD's factor isn't part of RATIO_BASED_MODES / result
        scaling. Hidden entirely for modes with no single per-spectrum
        scalar factor: SNV (per-spectrum mean+std, no shared batch factor),
        MSC (2-parameter regression per spectrum, not one scalar),
        Reference spectrum (point-wise ratio), Offset correction, Min-max.
        """
        if not hasattr(self, 'factor_table'):
            return

        self.factor_table.setRowCount(0)

        factors_by_index: dict = {}
        labels_by_index: dict = {}
        for idx, sp in enumerate(normalized_all):
            info = sp.get('normalization_info', {})
            factor = info.get('factor', info.get('svd_factor'))
            if factor is not None:
                factors_by_index[idx] = factor
                labels_by_index[idx] = sp.get('label', f'Spectrum_{idx}')

        has_factors = bool(factors_by_index)
        self.factor_table_section.setVisible(has_factors)
        if not has_factors:
            return

        # zscores covers every spectrum; outliers is the subset of zscores
        # (by index) whose |z| exceeds the 3-sigma threshold -- used only
        # to decide which rows get the orange highlight. Both come back
        # empty with fewer than 3 spectra or when all factors are
        # identical (std = 0), since a z-score isn't meaningful either way.
        zscores = manager.get_factor_zscores(factors_by_index) if manager else {}
        outliers = manager.get_factor_outliers(factors_by_index) if manager else {}

        self.factor_table.setRowCount(len(factors_by_index))
        for row, idx in enumerate(sorted(factors_by_index.keys())):
            label = labels_by_index[idx]
            factor = factors_by_index[idx]

            label_item = QTableWidgetItem(label)
            factor_item = QTableWidgetItem(f'{factor:.6g}')
            z = zscores.get(idx)
            dev_item = QTableWidgetItem(f'{z:+.2f}\u03c3' if z is not None else '\u2014')

            if idx in outliers:
                from PyQt5.QtGui import QColor
                highlight = QColor('#FFE0B2')   # light orange
                for item in (label_item, factor_item, dev_item):
                    item.setBackground(highlight)

            self.factor_table.setItem(row, 0, label_item)
            self.factor_table.setItem(row, 1, factor_item)
            self.factor_table.setItem(row, 2, dev_item)

    def _on_legend_visibility_changed(self, state):
        self.canvas.set_legend_visible(state == Qt.Checked)

    # =================================================================
    # Save
    # =================================================================
    def _save_normalized_spectra(self):
        """
        Export the normalized result for the spectra currently selected in
        the "Selected spectra" list at the top of the dialog — the same list
        used for viewing convenience — using the existing save pipeline
        (SaveOptionsDialog + SaveManager), the same one used by File > Save
        in the main window. No changes are made to that pipeline; we simply
        call it directly with our own spectrum list instead of going through
        SaveController.execute(), which gathers spectra from the main
        window's selection rather than this dialog's normalized preview.
        """
        selected_labels = {item.text() for item in self.spectra_list.selectedItems()}

        if not selected_labels:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, 'No spectra selected',
                'Please select at least one spectrum in the "Selected spectra" '
                'list to save.'
            )
            return

        to_save = [s for s in self._last_normalized_all if s.get('label') in selected_labels]
        if not to_save:
            return

        from src.views.dialogs.misc.save_spectra_dialog import SaveOptionsDialog
        from src.modules.misc.save_spectra_manager import SaveManager
        from PyQt5.QtWidgets import QFileDialog, QMessageBox

        # Snapshot format saves the whole application state, not a spectrum
        # list — irrelevant here, so it's hidden for this save flow.
        dialog = SaveOptionsDialog(self)
        dialog.setWindowTitle('Save Normalized Spectra')
        dialog.fmt_snapshot.setVisible(False)

        if dialog.exec_() != QDialog.Accepted:
            return

        settings = dialog.get_settings()
        save_manager = SaveManager()

        if settings['mode'] == 'table':
            if settings['use_common_scale'] and not save_manager.validate_common_scale(to_save):
                QMessageBox.warning(
                    self, 'Scale Mismatch',
                    'Selected spectra have different x-scales.\n'
                    'Cannot use the common x-scale option.\n\n'
                    "Uncheck 'Use common x-scale' to save with individual x-scales."
                )
                return

            ext = '.xlsx' if settings['format'] == 'excel' else '.txt'
            file_filter = (
                'Excel Files (*.xlsx);;All Files (*.*)' if settings['format'] == 'excel'
                else 'Text Files (*.txt);;CSV Files (*.csv);;All Files (*.*)'
            )
            file_path, _ = QFileDialog.getSaveFileName(
                self, 'Save Normalized Spectra', '', file_filter
            )
            if not file_path:
                return
            import os
            root, current_ext = os.path.splitext(file_path)
            if not current_ext:
                file_path = root + ext

            try:
                save_manager.save_table(to_save, file_path, settings)
                QMessageBox.information(
                    self, 'Save Successful',
                    f'Saved {len(to_save)} normalized spectra to:\n{file_path}'
                )
            except Exception as e:
                logger.exception('Normalized table save failed')
                QMessageBox.critical(self, 'Save Error', f'Failed to save spectra:\n{e}')

        else:  # individual files
            directory = QFileDialog.getExistingDirectory(
                self, 'Select Directory for Individual Files'
            )
            if not directory:
                return

            try:
                saved_files = save_manager.save_individual(to_save, directory, settings)
                QMessageBox.information(
                    self, 'Save Successful',
                    f'Saved {len(saved_files)} files to:\n{directory}'
                )
            except Exception as e:
                logger.exception('Normalized individual save failed')
                QMessageBox.critical(self, 'Save Error', f'Failed to save files:\n{e}')

    def _select_all(self):
        self.spectra_list.blockSignals(True)
        for i in range(self.spectra_list.count()):
            self.spectra_list.item(i).setSelected(True)
        self.spectra_list.blockSignals(False)
        if self._initialization_complete:
            self._on_spectrum_selection_changed()

    def _unselect_all(self):
        self.spectra_list.blockSignals(True)
        for i in range(self.spectra_list.count()):
            self.spectra_list.item(i).setSelected(False)
        self.spectra_list.blockSignals(False)
        if self._initialization_complete:
            self._on_spectrum_selection_changed()

    def _toggle_sort(self):
        self.sort_ascending = not self.sort_ascending
        self.sort_button.setText('\u25b2' if self.sort_ascending else '\u25bc')
        selected_labels = {item.text() for item in self.spectra_list.selectedItems()}
        self._populate_spectrum_list()
        for i in range(self.spectra_list.count()):
            if self.spectra_list.item(i).text() in selected_labels:
                self.spectra_list.item(i).setSelected(True)

    # =================================================================
    # Settings
    # =================================================================
    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — validates the region requirement (same
        check the old OK button used), then commits directly via
        commit_callback. No separate Run step: feedback (success or
        failure) is shown right here next to the buttons that triggered
        it, instead of in a disconnected main-window message box. The
        dialog closes itself once the commit succeeds.
        """
        current_mode = self._current_mode()
        mode_needs_region = not (
            current_mode == 'reference'
            or (current_mode == 'msc' and not self.msc_use_region_cb.isChecked())
        )
        if mode_needs_region and not self._regions:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                'No normalization region',
                'Please define at least one normalization region before applying.\n\n'
                'Drag on the plot to select a region and click "Add region", '
                'or click "Full range" to fill From/To with the entire spectrum '
                'and then click "Add region".'
            )
            return

        from PyQt5.QtWidgets import QMessageBox
        if self.commit_callback is None:
            QMessageBox.critical(
                self, 'Not Available',
                'This dialog was opened without a way to apply changes. '
                'Please reopen it via Parameters.'
            )
            return

        if not self.selected_spectra:
            QMessageBox.warning(
                self, 'No Spectra Selected',
                'Please select one or more spectra in the main window first.'
            )
            return

        action = 'add the normalized result as new spectra' if add_as_new else 'replace the selected spectra with their normalized result'
        confirm = QMessageBox.question(
            self, 'Confirm', f'{action[0].upper() + action[1:]}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        settings = self.get_settings()
        success, message = self.commit_callback(settings, add_as_new, list(self.selected_spectra))
        if success:
            QMessageBox.information(self, 'Done', message)
            self.accept()
        else:
            QMessageBox.warning(self, 'Could Not Apply', message)

    def get_settings(self):
        mode = self._current_mode()
        regions = list(self._regions)
        is_exclude = self._exclude_radio.isChecked()

        settings = {
            'normalization_mode': mode,
            'x_ranges': regions,
            'is_exclude_mode': is_exclude,
            'x_min': regions[0][0] if regions else None,
            'x_max': regions[-1][1] if regions else None,
            'reference_spectrum_index': self.ref_index_combo.currentIndex(),
            'percentile_value': float(self.percentile_spinbox.value()),
            'msc_use_region': self.msc_use_region_cb.isChecked(),
            'target_mode': self._current_target_mode(),
            'target_value': float(self.target_value_spinbox.value()),
        }
        return settings

    # =================================================================
    # Help
    # =================================================================
    def _show_help(self):
        try:
            from src.help.normalization_help import get_normalization_help_content, get_normalization_help_title
            from src.help.help_window import show_help_window
            show_help_window(self, get_normalization_help_title(), get_normalization_help_content())
        except Exception as e:
            logger.debug(f'Could not show help: {e}')
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Help', 'Help documentation is not available at this time.')

    # =================================================================
    # Utility
    # =================================================================
    @staticmethod
    def _make_spinbox(min_val, max_val, default, decimals=4):
        if decimals == 0:
            from PyQt5.QtWidgets import QSpinBox
            sb = QSpinBox()
            sb.setRange(int(min_val), int(max_val))
            sb.setValue(int(default))
        else:
            sb = QDoubleSpinBox()
            sb.setRange(min_val, max_val)
            sb.setDecimals(decimals)
            sb.setValue(default)
        return sb


# ======================================================================
# Plot canvas
# ======================================================================
class NormalizationPlotCanvas(FigureCanvas):
    range_selected = pyqtSignal(float, float)

    def __init__(self, parent=None):
        self.fig = Figure(tight_layout=True)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)

        self.axes.set_xlabel('X')
        self.axes.set_ylabel('Intensity')
        self.axes.grid(True)

        self.spectra_data = []
        self._region_spans = []
        self.legend_visible = True

        self._selecting = False
        self._sel_start = None

        self.mpl_connect('button_press_event', self._on_click)
        self.mpl_connect('button_release_event', self._on_release)
        self.mpl_connect('motion_notify_event', self._on_mouse_move)

        self.fig.patch.set_facecolor('#f0f0f0')
        self.axes.set_facecolor('#ffffff')
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def _on_click(self, event):
        if event.inaxes != self.axes or not self.spectra_data:
            return
        if event.button == 1:
            self._selecting = True
            self._sel_start = event.xdata

    def _on_release(self, event):
        if event.inaxes != self.axes and self._selecting:
            self._selecting = False
            return
        if self._selecting and self._sel_start is not None and event.xdata is not None:
            x_min = min(self._sel_start, event.xdata)
            x_max = max(self._sel_start, event.xdata)
            if abs(x_max - x_min) > 1e-6:
                self.range_selected.emit(x_min, x_max)
        self._selecting = False
        self._sel_start = None

    def _on_mouse_move(self, event):
        parent = self.parent()
        if event.inaxes and hasattr(parent, 'coordinates_label'):
            parent.coordinates_label.setText(f'(x, y) = ({event.xdata:.6g}, {event.ydata:.6g})')
        elif hasattr(parent, 'coordinates_label'):
            parent.coordinates_label.setText('')

    def plot_spectra(self, spectra_list, display_labels=None):
        """display_labels: optional {full_label: display_label} map (see
        label_shortening.py) — legend/title text only."""
        display_labels = display_labels or {}
        self.axes.clear()
        self.spectra_data = spectra_list
        self._region_spans = []

        if not spectra_list:
            self.draw()
            return

        colors = ['#1f77b4', '#d62728', '#2ca02c', '#ff7f0e',
                  '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        x_all = []
        plotted = 0
        for i, s in enumerate(spectra_list):
            x = np.asarray(s.get('x_scale', []), dtype=float)
            y = np.asarray(s.get('y_scale', []), dtype=float)
            if len(x) == 0 or len(y) == 0:
                continue
            full_label = s.get('label', f'Spectrum_{i}')
            self.axes.plot(x, y, color=colors[i % len(colors)],
                           lw=1, label=display_labels.get(full_label, full_label), alpha=0.85)
            x_all.extend(x)
            plotted += 1

        if plotted == 0:
            self.axes.text(0.5, 0.5, 'No valid spectra', transform=self.axes.transAxes,
                           ha='center', va='center', color='red')
        else:
            n = len(spectra_list)
            if n == 1:
                first_label = spectra_list[0].get('label', '')
                title = display_labels.get(first_label, first_label)
            else:
                title = f'{plotted} spectra'
            self.axes.set_title(title)
            self.axes.set_xlabel('X')
            self.axes.set_ylabel('Intensity')
            self.axes.grid(True, linestyle='--', alpha=0.6)
            if plotted > 1 and self.legend_visible:
                self.axes.legend(loc='best', fontsize='small')
            if x_all:
                xlo, xhi = np.min(x_all), np.max(x_all)
                pad = (xhi - xlo) * 0.02
                self.axes.set_xlim(xlo - pad, xhi + pad)
            self.axes.autoscale(axis='y')

        self.draw()

    def show_message(self, message: str):
        """Clear the canvas and show a centered placeholder message instead
        of any spectra — used when there's nothing meaningful to preview yet
        (e.g. no normalization region defined)."""
        self.axes.clear()
        self.spectra_data = []
        self.axes.text(0.5, 0.5, message, transform=self.axes.transAxes,
                       ha='center', va='center', color='#1976D2', fontsize=10,
                       wrap=True)
        self.axes.set_xticks([])
        self.axes.set_yticks([])
        self.draw()

    def update_regions(self, regions: list, is_exclude: bool = False):
        """Redraw all region spans.

        Include mode (is_exclude=False): selected regions shaded green.
        Exclude mode (is_exclude=True): selected regions shaded red
            (they will be excluded from the normalization coefficient).
        """
        for span in self._region_spans:
            try:
                span.remove()
            except Exception:
                pass
        self._region_spans = []

        color = '#d62728' if is_exclude else '#2ca02c'  # red=exclude, green=include
        alpha = 0.20

        for x0, x1 in regions:
            if x1 > x0:
                span = self.axes.axvspan(x0, x1, alpha=alpha, color=color)
                self._region_spans.append(span)

        self.draw()

    def set_legend_visible(self, visible):
        self.legend_visible = visible
        legend = self.axes.get_legend()
        if legend:
            legend.remove()
        if visible and len(self.spectra_data) > 1:
            self.axes.legend(loc='best', fontsize='small')
        self.draw()
