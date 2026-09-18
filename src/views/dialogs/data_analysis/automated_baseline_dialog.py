# src/views/dialogs/data_analysis/automated_baseline_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QSlider, QLabel, QDialogButtonBox, QListWidget,
                             QWidget, QSplitter, QSizePolicy, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
                             QComboBox, QStackedWidget, QTabWidget)
from PyQt5.QtCore import Qt, pyqtSignal
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

        # Baseline Method — switches the stacked parameter panel below.
        # userData on each entry is the params['algorithm'] value used
        # throughout the manager/controller ('als' / 'airpls'), so this
        # combo is the single place that string is chosen from.
        method_group = QGroupBox("Baseline Method")
        method_layout = QVBoxLayout()
        self.method_combo = QComboBox()
        self.method_combo.addItem("ALS (Asymmetric Least Squares)", "als")
        self.method_combo.addItem("airPLS (adaptive iteratively reweighted PLS)", "airpls")
        self.method_combo.addItem("arPLS (asymmetrically reweighted PLS)", "arpls")
        self.method_combo.addItem("iarPLS (improved arPLS)", "iarpls")
        self.method_combo.addItem("asPLS (adaptive smoothness PLS)", "aspls")
        self.method_combo.addItem("drPLS (doubly reweighted PLS)", "drpls")
        self.method_combo.addItem("psalsa (peak-decay asymmetric least squares)", "psalsa")
        self.method_combo.addItem("I-ModPoly (improved modified polynomial fit)", "imodpoly")
        self.method_combo.addItem("Morphological Opening (adaptive structuring element)", "morphological")
        self.method_combo.addItem("mpls (morphological weighted PLS)", "mpls")
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        method_layout.addWidget(self.method_combo)
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
        airpls_note = QLabel(
            "airPLS usually needs a much smaller λ than ALS — use the\n"
            "preview to find a value that follows the background\n"
            "without dipping into the peaks."
        )
        airpls_note.setStyleSheet("color: gray; font-style: italic;")
        airpls_layout.addWidget(airpls_note)

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
        arpls_note = QLabel(
            "arPLS re-weights points by how far below a data-driven\n"
            "threshold their residual sits, rather than airPLS's\n"
            "exponential growth -- often a bit steadier on noisy data.\n"
            "Use the preview to compare against ALS/airPLS on your own\n"
            "spectra."
        )
        arpls_note.setStyleSheet("color: gray; font-style: italic;")
        arpls_layout.addWidget(arpls_note)

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
        iarpls_note = QLabel(
            "A fix for arPLS's known tendency to overestimate the\n"
            "baseline under small peaks in noisy data -- same λ slider,\n"
            "different internal weighting. Try this first if arPLS\n"
            "seems to sit a bit high under small peaks."
        )
        iarpls_note.setStyleSheet("color: gray; font-style: italic;")
        iarpls_layout.addWidget(iarpls_note)

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
        aspls_note = QLabel(
            "Another arPLS-style method, but the smoothness penalty\n"
            "itself adapts point-by-point to the residuals instead of\n"
            "being applied uniformly -- stiffer where the fit is\n"
            "confident, looser near features it's still unsure about."
        )
        aspls_note.setStyleSheet("color: gray; font-style: italic;")
        aspls_layout.addWidget(aspls_note)

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
        drpls_note = QLabel(
            "Higher \u03b7 lets peak regions relax more independently\n"
            "of the surrounding baseline's smoothness -- 0 behaves\n"
            "closest to arPLS, 1 relaxes the peak-region penalty\n"
            "the most."
        )
        drpls_note.setStyleSheet("color: gray; font-style: italic;")
        drpls_layout.addWidget(drpls_note)

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
        psalsa_note = QLabel(
            "Peaks are suppressed by exponential decay rather than a\n"
            "hard cutoff, which is why a higher p than ALS's still\n"
            "works well here. The decay's own peak-height scale (k)\n"
            "is set automatically from the spectrum's noise level."
        )
        psalsa_note.setStyleSheet("color: gray; font-style: italic;")
        psalsa_layout.addWidget(psalsa_note)

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
        imodpoly_note = QLabel(
            "A single low-order polynomial fit to the whole spectrum,\n"
            "with peaks iteratively rejected from the fit -- good for\n"
            "smooth, broadly-curved fluorescence backgrounds. Higher\n"
            "orders follow more background curvature but risk fitting\n"
            "into broad peaks; use the preview to check."
        )
        imodpoly_note.setStyleSheet("color: gray; font-style: italic;")
        imodpoly_layout.addWidget(imodpoly_note)

        # Morphological Opening Parameters -- deliberately no controls at
        # all. Unlike every other method here, it has no smoothness,
        # asymmetry, or order parameter to expose: the structuring
        # element it would otherwise need is grown automatically until
        # the result stops changing (see calculate_morphological_baseline).
        # This page exists only so the stack has something to show and
        # the explanatory note has somewhere to live.
        morph_params_page = QWidget()
        morph_layout = QVBoxLayout(morph_params_page)
        morph_layout.setContentsMargins(0, 0, 0, 0)
        morph_note = QLabel(
            "Fully automatic -- no parameters to tune. Repeatedly opens\n"
            "the spectrum with a growing structuring element until the\n"
            "result stops changing, then refines it to correct for\n"
            "band-shape distortion. Good for smooth backgrounds that\n"
            "don't fit a fixed polynomial order or global penalty."
        )
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
        mpls_note = QLabel(
            "Morphological opening picks a handful of trustworthy\n"
            '"anchor" points and solves ALS\'s own penalty once --\n'
            "no iterative reweighting. Anchor points always get\n"
            "weight 1-p; this slider sets everyone else's weight,\n"
            "0 by default (ignored entirely)."
        )
        mpls_note.setStyleSheet("color: gray; font-style: italic;")
        mpls_layout.addWidget(mpls_note)

        params_group = QGroupBox("Method Parameters")
        params_group_layout = QVBoxLayout()
        self.params_stack = QStackedWidget()
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

    def _on_method_changed(self, index):
        """Swap the visible parameter panel to match the selected
        algorithm (self.params_stack index mirrors self.method_combo's
        item order — see create_control_panel) and refresh the preview,
        since ALS and airPLS will generally produce a different baseline
        for the same spectrum."""
        self.params_stack.setCurrentIndex(index)
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
        return {
            'algorithm': 'als',
            'lambda': 10**(self.lam_slider.value() / 10.0),
            'p': self.p_slider.value() / 1000.0,
            'n_iter': 10,
            'fitting_ranges': flat_ranges,
            'invert_regions': self.invert_regions_checkbox.isChecked(),
        }