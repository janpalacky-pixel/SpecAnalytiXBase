# src/views/dialogs/visualization_analysis/som_dialog.py

from collections import defaultdict

import numpy as np
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                            QSpinBox, QLabel, QPushButton, QDialogButtonBox,
                            QSplitter, QWidget, QMessageBox, QComboBox,
                            QSizePolicy, QFileDialog, QDoubleSpinBox,
                            QTableWidget, QTableWidgetItem, QHeaderView,
                            QMenu, QTextEdit, QCheckBox, QProgressDialog,
                            QApplication, QRadioButton, QButtonGroup,
                            QAbstractItemView)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QCursor
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import make_shorten_names_checkbox

logger = get_logger(__name__)

# Metrics offered wherever a single scalar feature is extracted from a
# spectrum over an x-range — same vocabulary BandRatioManager itself
# understands (band_ratio_manager.py), so these strings can be dropped
# straight into a band_def dict unchanged.
_RANGE_METRICS = ['Mean', 'Integral', 'Baseline-corrected integral',
                   'Variance', 'Peak intensity', 'Peak position']
_ALL_METRICS = ['Wavelength index (raw)', 'Intensity at x'] + _RANGE_METRICS + ['Ratio of two ranges (A/B)']
_RATIO_BAND_METRICS = ['Intensity at x'] + _RANGE_METRICS
_RATIO_OPERATIONS = ['A / B', 'A - B', 'A + B', 'A only', 'B only']


def _make_help_button(tooltip, on_click):
    """Small orange '?' button that pops up detailed explanatory text on
    click — same look and role as svd_interpolation_dialog.py's
    _make_help_button (background #F57C00, same hover/pressed shades,
    24px wide). Duplicated locally rather than imported, matching how
    _ComputeWorker below is itself private to this dialog module."""
    btn = QPushButton("?")
    btn.setFixedWidth(24)
    btn.setToolTip(tooltip)
    btn.setStyleSheet(
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
    btn.clicked.connect(on_click)
    return btn


class _ComputeWorker(QThread):
    """Runs one blocking callable on a background thread and reports back
    on the GUI thread via Qt signals. Same shape as ClusterAnalysisDialog's
    own _ComputeWorker (cluster_analysis_dialog.py) — duplicated locally
    rather than imported/shared, matching how that class is itself private
    to its own dialog module."""
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal()

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self._fn()
        except Exception as e:
            self.error = e
        finally:
            self.done.emit()


class SOMCanvas(FigureCanvas):
    """Canvas for SOM visualization (U-Matrix / Hit Map / Component Plane /
    Sample Map) with interactive node/sample selection. Shape mirrors
    ClusterAnalysisCanvas (cluster_analysis_dialog.py)."""

    node_selected = pyqtSignal(int, int, list)  # row, col, member_labels

    # Golden-angle spiral jitter constant — spreads several same-node
    # samples out within a grid cell without overlap. Same formula and
    # role as MeltAnalytiX's own SOM dialog (src/gui/som_dialog.py):
    # radius = sqrt((j+0.5)/k) * 0.42, theta = j * golden_angle.
    _GOLDEN_ANGLE = np.pi * (3 - np.sqrt(5))

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(9, 8))
        super().__init__(self.fig)
        self.setParent(parent)

        self.som_controller = None
        self.visualization_mode = 'u_matrix'   # 'u_matrix', 'hit_map', 'component_plane', 'sample_map'
        self.component_feature_index = 0
        self.component_plane_settings = None   # None -> raw index mode; else a BandRatioManager-style settings dict
        self.component_plane_label = None
        self.sample_color_values = None        # per-spectrum array used to colour the Sample Map, or None
        self.sample_color_label = ''
        self.get_shorten_enabled = None

        self.interactive_mode = True
        self.highlighted_node = None
        self.click_connection_id = None
        self._sample_map_positions = []        # (x, y, label, row, col) for Sample Map click hit-testing

    def leaveEvent(self, event):
        """Deliberate override — see ClusterAnalysisCanvas.leaveEvent in
        cluster_analysis_dialog.py for the full rationale: matplotlib's own
        FigureCanvasQT.leaveEvent() unconditionally pops the global override
        cursor, which desyncs the cursor stack against the wait cursors this
        dialog pushes itself (run_som, on_viz_changed)."""
        if self.figure is not None:
            from matplotlib.backend_bases import LocationEvent
            LocationEvent("figure_leave_event", self, *self.mouseEventCoords(),
                          guiEvent=event)._process()

    def set_som_controller(self, controller):
        self.som_controller = controller

    def set_interactive_mode(self, enabled):
        self.interactive_mode = enabled
        if enabled and self.visualization_mode in ('u_matrix', 'hit_map', 'sample_map'):
            self._connect_click_handler()
        else:
            self._disconnect_click_handler()

    def _connect_click_handler(self):
        if self.click_connection_id is None:
            self.click_connection_id = self.mpl_connect('button_press_event', self._on_click)

    def _disconnect_click_handler(self):
        if self.click_connection_id is not None:
            self.mpl_disconnect(self.click_connection_id)
            self.click_connection_id = None

    def _on_click(self, event):
        if not self.interactive_mode or self.som_controller is None or event.inaxes is None:
            return
        manager = self.som_controller.manager
        if manager.hit_map is None or event.xdata is None or event.ydata is None:
            return

        if self.visualization_mode == 'sample_map':
            if not self._sample_map_positions:
                return
            best = min(
                self._sample_map_positions,
                key=lambda p: (p[0] - event.xdata) ** 2 + (p[1] - event.ydata) ** 2
            )
            if (best[0] - event.xdata) ** 2 + (best[1] - event.ydata) ** 2 > 0.35 ** 2:
                return  # click landed too far from any plotted sample point
            row, col = best[3], best[4]
        else:
            col = int(round(event.xdata))
            row = int(round(event.ydata))
            if not (0 <= row < manager.grid_rows and 0 <= col < manager.grid_cols):
                return

        members = manager.get_node_members(row, col)
        self.highlighted_node = (row, col)
        self.plot_som()
        self.node_selected.emit(row, col, members)

    def reset_highlight(self):
        self.highlighted_node = None
        self.plot_som()

    def set_visualization_mode(self, mode):
        self.visualization_mode = mode
        self.plot_som()

    def _shortened(self, labels):
        enabled = self.get_shorten_enabled() if self.get_shorten_enabled else False
        if not enabled:
            return list(labels)
        from src.modules.utils.label_shortening import compute_distinguishing_labels
        shortened = compute_distinguishing_labels(list(labels))
        return [shortened.get(lbl, lbl) for lbl in labels]

    def _draw_empty_node_hatches(self, ax, manager):
        """Shaded/hatched squares for nodes with zero assigned spectra —
        same visual convention MeltAnalytiX's own SOM dialog uses
        (edgecolor='gray', hatch='////', linewidth=0) for "no data here",
        so the two apps read the same way side by side."""
        if manager.hit_map is None:
            return
        for r in range(manager.grid_rows):
            for c in range(manager.grid_cols):
                if manager.hit_map[r, c] == 0:
                    ax.add_patch(Rectangle(
                        (c - 0.5, r - 0.5), 1, 1,
                        facecolor='none', edgecolor='gray',
                        hatch='////', linewidth=0, zorder=2
                    ))

    def plot_som(self):
        """Redraw the canvas for the current visualization_mode. Cheap
        recompute-free redraw — training itself only happens in run_som();
        switching modes here never re-trains, same instant-switch UX as
        Cluster Analysis's PCA 2D/3D/Spectra/Centroids dropdown."""
        self.fig.clear()
        manager = self.som_controller.manager if self.som_controller else None

        if manager is None or manager.hit_map is None:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Click Run SOM to train the map",
                   transform=ax.transAxes, ha='center', va='center')
            self.draw()
            return

        if self.visualization_mode == 'sample_map':
            self._plot_sample_map(manager)
            return

        ax = self.fig.add_subplot(111)

        if self.visualization_mode == 'hit_map':
            grid = manager.hit_map.astype(float)
            title = 'SOM — Hit Map (spectra per node)'
            cbar_label = 'Spectra count'
            fmt = '{:d}'
            annot = manager.hit_map
        elif self.visualization_mode == 'component_plane':
            if self.component_plane_settings is not None:
                grid = manager.get_component_plane_by_settings(self.component_plane_settings)
                label = self.component_plane_label or 'custom feature'
            else:
                idx = min(self.component_feature_index, max(0, manager.get_n_features() - 1))
                grid = manager.get_component_plane(idx)
                label = manager.get_feature_label(idx)
            title = f'SOM — Component Plane ({label})'
            cbar_label = 'Value' if self.component_plane_settings is not None else 'Weight (standardised units)'
            fmt = '{:.2f}'
            annot = None
            if grid is not None:
                grid = np.ma.masked_invalid(grid)
        else:  # u_matrix
            grid = manager.u_matrix
            title = 'SOM — U-Matrix (inter-node distance)'
            cbar_label = 'Mean distance to neighbours'
            fmt = '{:.2f}'
            annot = None

        if grid is None:
            ax.text(0.5, 0.5, "No data for this view", transform=ax.transAxes,
                   ha='center', va='center')
            self.draw()
            return

        im = ax.imshow(grid, cmap='viridis', origin='upper', aspect='equal')
        self.fig.colorbar(im, ax=ax, label=cbar_label, fraction=0.046, pad=0.04)

        if annot is not None:
            for r in range(grid.shape[0]):
                for c in range(grid.shape[1]):
                    val = annot[r, c]
                    if val:
                        ax.text(c, r, fmt.format(int(val)), ha='center', va='center',
                               color='white', fontsize=8)

        self._draw_empty_node_hatches(ax, manager)

        if self.highlighted_node is not None:
            r, c = self.highlighted_node
            ax.add_patch(Rectangle((c - 0.5, r - 0.5), 1, 1, fill=False,
                                   edgecolor='red', linewidth=2.5, zorder=4))

        if self.interactive_mode and self.visualization_mode in ('u_matrix', 'hit_map'):
            title += '\n(Click a node to see which spectra mapped there)'
        ax.set_title(title)
        ax.set_xlabel('Node column')
        ax.set_ylabel('Node row')

        self.fig.tight_layout()
        self.draw()

    def _plot_sample_map(self, manager):
        """Sample Map: every individual spectrum plotted as one point inside
        its own best-matching node's grid cell, spread out with a
        golden-angle spiral jitter so same-node samples don't overlap, and
        optionally coloured by a chosen feature. Mirrors MeltAnalytiX's own
        SOM dialog clickable coloured sample map."""
        ax = self.fig.add_subplot(111)

        node_groups = defaultdict(list)
        for i, (r, c) in enumerate(manager.bmu_indices):
            node_groups[(int(r), int(c))].append(i)

        xs, ys, colors, positions = [], [], [], []
        color_vals = self.sample_color_values
        for (r, c), idxs in node_groups.items():
            k = len(idxs)
            for j, i in enumerate(idxs):
                radius = np.sqrt((j + 0.5) / k) * 0.42
                theta = j * self._GOLDEN_ANGLE
                x = c + radius * np.cos(theta)
                y = r + radius * np.sin(theta)
                xs.append(x)
                ys.append(y)
                positions.append((x, y, manager.spectrum_labels[i], r, c))
                colors.append(color_vals[i] if color_vals is not None else 0.0)
        self._sample_map_positions = positions

        self._draw_empty_node_hatches(ax, manager)

        if xs:
            if color_vals is not None:
                sc = ax.scatter(xs, ys, c=colors, cmap='viridis', s=32,
                               edgecolors='k', linewidths=0.4, zorder=3)
                self.fig.colorbar(sc, ax=ax, label=self.sample_color_label or 'Value',
                                 fraction=0.046, pad=0.04)
            else:
                ax.scatter(xs, ys, c='#1565C0', s=32, edgecolors='k',
                          linewidths=0.4, zorder=3)

        if self.highlighted_node is not None:
            r, c = self.highlighted_node
            ax.add_patch(Rectangle((c - 0.5, r - 0.5), 1, 1, fill=False,
                                   edgecolor='red', linewidth=2.5, zorder=4))

        ax.set_xlim(-0.7, manager.grid_cols - 0.3)
        ax.set_ylim(manager.grid_rows - 0.3, -0.7)
        ax.set_xticks(range(manager.grid_cols))
        ax.set_yticks(range(manager.grid_rows))
        ax.grid(True, linestyle=':', color='gray', alpha=0.5, zorder=1)

        title = 'SOM — Sample Map (each point is one spectrum)'
        if self.interactive_mode:
            title += '\n(Click a point to see its node)'
        ax.set_title(title)
        ax.set_xlabel('Node column')
        ax.set_ylabel('Node row')

        self.fig.tight_layout()
        self.draw()


class SOMDialog(QDialog):
    """Dialog for Self-Organizing Map (SOM) analysis. Shape mirrors
    ClusterAnalysisDialog (cluster_analysis_dialog.py) — same window
    chrome, same run/progress/interact/export rhythm as every other
    Visualization tool in this app, so SOM feels behaviorally identical
    to Cluster Analysis even though the underlying algorithm differs."""

    def __init__(self, parent=None, controller=None, spectra=None):
        super().__init__(parent)
        self.controller = controller
        self.spectra = spectra
        self._som_running = False
        self._last_displayed_node = None   # (row, col, member_labels) of the node currently shown in the info panel

        self.setWindowTitle("Self-Organizing Map (SOM)")
        self.setModal(True)
        self.setMinimumSize(1020, 620)
        self.resize(1280, 760)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint)

        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
        try:
            self.setup_ui()
        finally:
            QApplication.restoreOverrideCursor()

    def showEvent(self, event):
        super().showEvent(event)
        # Defensive: clear any override cursor(s) still active once this
        # dialog is actually on screen — same fix as
        # ClusterAnalysisDialog.showEvent, for the same reason (a "please
        # wait" cursor pushed by whoever opened this modal dialog would
        # otherwise not get restored until this dialog closes).
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_layout.addWidget(main_splitter)

        control_panel = self.create_control_panel()
        main_splitter.addWidget(control_panel)

        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.setChildrenCollapsible(False)
        main_splitter.addWidget(self.right_splitter)

        canvas_panel = self.create_canvas_panel()
        self.right_splitter.addWidget(canvas_panel)

        self.info_panel_widget = self.create_info_panel()
        self.right_splitter.addWidget(self.info_panel_widget)

        main_splitter.setSizes([400, 1080])
        self.right_splitter.setSizes([700, 300])

    # ------------------------------------------------------------------ #
    # Control panel                                                       #
    # ------------------------------------------------------------------ #

    def create_control_panel(self):
        widget = QWidget()
        widget.setMinimumWidth(380)
        layout = QVBoxLayout(widget)

        layout.addWidget(self._create_training_data_group())
        layout.addWidget(self._create_training_params_group())
        layout.addWidget(self._create_visualization_group())

        # --- Run button ----------------------------------------------------
        self.run_btn = QPushButton("Run SOM")
        self.run_btn.clicked.connect(self.run_som)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 6px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #388E3C; }
            QPushButton:pressed { background-color: #1B5E20; }
        """)
        layout.addWidget(self.run_btn)

        self._stale_warning_label = QLabel(
            "⚠  Settings changed — click Run SOM to update the results below.")
        self._stale_warning_label.setStyleSheet("color: #C62828; font-size: 8pt; font-weight: bold;")
        self._stale_warning_label.setWordWrap(True)
        self._stale_warning_label.setVisible(False)
        layout.addWidget(self._stale_warning_label)

        # --- Results table ---------------------------------------------
        results_group = QGroupBox("Node Results")
        results_layout = QVBoxLayout(results_group)
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(['Row', 'Col', 'Size', 'Mean dist.'])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.cellClicked.connect(self.on_table_cell_clicked)
        results_layout.addWidget(self.results_table)
        layout.addWidget(results_group)

        # --- Export ------------------------------------------------------
        export_group = QGroupBox("Export Results")
        export_layout = QHBoxLayout(export_group)
        self.save_excel_btn = QPushButton("Save Excel...")
        self.save_excel_btn.clicked.connect(self.save_excel_results)
        self.save_excel_btn.setEnabled(False)
        self.save_excel_btn.setToolTip("Export SOM results to an Excel file with multiple sheets")
        export_layout.addWidget(self.save_excel_btn)
        self.export_csv_btn = QPushButton("Export CSV...")
        self.export_csv_btn.clicked.connect(self.show_export_menu)
        self.export_csv_btn.setEnabled(False)
        self.export_csv_btn.setToolTip("Export BMU assignments or node summary to CSV")
        export_layout.addWidget(self.export_csv_btn)
        layout.addWidget(export_group)

        layout.addStretch()

        self.button_box = QDialogButtonBox()
        self.help_button = QPushButton("Help")
        self.help_button.clicked.connect(self.show_help)
        self.button_box.addButton(self.help_button, QDialogButtonBox.HelpRole)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        self.button_box.addButton(self.close_button, QDialogButtonBox.AcceptRole)
        layout.addWidget(self.button_box)

        return widget

    def _create_training_data_group(self):
        """'Train on: Full spectrum shape' vs 'Custom features' — analogous
        to MeltAnalytiX's own SOM dialog radio_feature/radio_curve toggle
        ("Cluster by extracted features" vs "Cluster by melting-curve
        shape"), generalised here: SpecAnalytiXBase has no fixed feature
        set like Tm/van't Hoff/Hysteresis, so instead of naming specific
        features it lets you define any number of Band Ratio-style scalar
        features (peak position, band integral, intensity at x, ...) and
        trains the map on those instead of the raw spectrum shape."""
        group = QGroupBox("Training Data")
        layout = QVBoxLayout(group)

        header = QHBoxLayout()
        header.addWidget(QLabel("What should the map be trained on?"))
        header.addStretch()
        header.addWidget(_make_help_button(
            "What does 'Train on' mean?", self._show_training_data_help))
        layout.addLayout(header)

        self.radio_train_shape = QRadioButton("Full spectrum shape")
        self.radio_train_shape.setChecked(True)
        self.radio_train_features = QRadioButton("Custom features")
        self._train_mode_group = QButtonGroup(group)
        self._train_mode_group.addButton(self.radio_train_shape)
        self._train_mode_group.addButton(self.radio_train_features)
        self.radio_train_shape.toggled.connect(self._on_train_mode_toggled)
        layout.addWidget(self.radio_train_shape)
        layout.addWidget(self.radio_train_features)

        self.feature_table_widget = QWidget()
        ft_layout = QVBoxLayout(self.feature_table_widget)
        ft_layout.setContentsMargins(0, 0, 0, 0)
        self.feature_table = QTableWidget(0, 4)
        self.feature_table.setHorizontalHeaderLabels(['Name', 'Metric', 'X1', 'X2'])
        self.feature_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.feature_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.feature_table.setMaximumHeight(160)
        ft_layout.addWidget(self.feature_table)

        ft_btn_row = QHBoxLayout()
        add_feature_btn = QPushButton("Add Feature")
        add_feature_btn.clicked.connect(lambda: self._add_feature_row())
        ft_btn_row.addWidget(add_feature_btn)
        remove_feature_btn = QPushButton("Remove Selected")
        remove_feature_btn.clicked.connect(self._remove_selected_feature_rows)
        ft_btn_row.addWidget(remove_feature_btn)
        ft_layout.addLayout(ft_btn_row)

        self.feature_table_widget.setVisible(False)
        layout.addWidget(self.feature_table_widget)

        # Seed one sensible default row (full-range mean) once we know the
        # x-axis span of the actual selected spectra.
        self._default_x1, self._default_x2 = self._spectra_x_range()
        self._add_feature_row(name="Feature 1", metric="Mean",
                              x1=self._default_x1, x2=self._default_x2)

        return group

    def _spectra_x_range(self):
        if self.spectra:
            x = self.spectra[0].get('x_scale', [])
            if len(x):
                return float(min(x)), float(max(x))
        return 0.0, 1.0

    def _add_feature_row(self, name=None, metric='Mean', x1=None, x2=None):
        row = self.feature_table.rowCount()
        self.feature_table.insertRow(row)
        if x1 is None or x2 is None:
            x1, x2 = self._spectra_x_range()

        name_item = QTableWidgetItem(name or f"Feature {row + 1}")
        self.feature_table.setItem(row, 0, name_item)

        metric_combo = QComboBox()
        metric_combo.addItems(_RATIO_BAND_METRICS)
        metric_combo.setCurrentText(metric if metric in _RATIO_BAND_METRICS else 'Mean')
        self.feature_table.setCellWidget(row, 1, metric_combo)

        x1_spin = QDoubleSpinBox()
        x1_spin.setRange(-1e9, 1e9)
        x1_spin.setDecimals(3)
        x1_spin.setValue(x1)
        self.feature_table.setCellWidget(row, 2, x1_spin)

        x2_spin = QDoubleSpinBox()
        x2_spin.setRange(-1e9, 1e9)
        x2_spin.setDecimals(3)
        x2_spin.setValue(x2)
        self.feature_table.setCellWidget(row, 3, x2_spin)

    def _remove_selected_feature_rows(self):
        rows = sorted({idx.row() for idx in self.feature_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.feature_table.removeRow(r)

    def _collect_feature_defs(self):
        """Read the feature table into BandRatioManager-style band_def
        dicts (plus a 'name' key), matching what SOMManager.compute_som
        expects for train_mode='feature'."""
        defs = []
        for row in range(self.feature_table.rowCount()):
            name_item = self.feature_table.item(row, 0)
            metric_combo = self.feature_table.cellWidget(row, 1)
            x1_spin = self.feature_table.cellWidget(row, 2)
            x2_spin = self.feature_table.cellWidget(row, 3)
            if metric_combo is None or x1_spin is None or x2_spin is None:
                continue
            name = (name_item.text().strip() if name_item and name_item.text().strip()
                   else f"Feature {row + 1}")
            metric = metric_combo.currentText()
            if metric == 'Intensity at x':
                defs.append({'name': name, 'metric': metric, 'x_pos': x1_spin.value(),
                           'ranges': [], 'is_exclude': False})
            else:
                defs.append({'name': name, 'metric': metric,
                           'ranges': [[x1_spin.value(), x2_spin.value()]], 'is_exclude': False})
        return defs

    def _on_train_mode_toggled(self, checked):
        # `checked` refers to radio_train_shape; feature table is the
        # complement.
        self.feature_table_widget.setVisible(not checked)
        self._mark_results_stale()
        self._update_component_plane_controls_visibility()

    def _show_training_data_help(self):
        QMessageBox.information(
            self, "Training Data — Help",
            "<html><body style='font-family: Arial, sans-serif; font-size: 12px;'>"
            "<p><b>Full spectrum shape</b> (default) trains the map on each "
            "spectrum's complete curve, exactly like the original SOM "
            "implementation — two spectra end up on the same/neighbouring "
            "node when their overall shapes are similar.</p>"
            "<p><b>Custom features</b> instead reduces every spectrum to a "
            "short list of scalar numbers you define — e.g. a peak position, "
            "a band integral, or the intensity at one specific x-value — "
            "using the same engine as this app's standalone <i>Band Ratio / "
            "Peak Area Calculator</i> tool. The map then organises spectra by "
            "those chosen numbers instead of by full-curve shape.</p>"
            "<p>This is the SpecAnalytiXBase analogue of MeltAnalytiX's own "
            "SOM dialog toggle between <i>clustering by extracted features</i> "
            "(Tm, van't Hoff enthalpy, hysteresis, ...) and <i>clustering by "
            "melting-curve shape</i> — MeltAnalytiX can name specific "
            "melting-curve features because it only ever handles melting "
            "curves; SpecAnalytiXBase is general-purpose, so instead of a "
            "fixed feature list it lets you define your own.</p>"
            "</body></html>"
        )

    def _create_training_params_group(self):
        som_group = QGroupBox("Training Parameters")
        som_layout = QVBoxLayout(som_group)

        header = QHBoxLayout()
        header.addWidget(QLabel("Grid size, learning rate, radius, iterations"))
        header.addStretch()
        header.addWidget(_make_help_button(
            "What do these training parameters mean?", self._show_training_params_help))
        som_layout.addLayout(header)

        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("Grid rows:"))
        self.grid_rows_spin = QSpinBox()
        self.grid_rows_spin.setRange(2, 100)
        self.grid_rows_spin.setValue(5)
        self.grid_rows_spin.setKeyboardTracking(False)
        self.grid_rows_spin.valueChanged.connect(self._mark_results_stale)
        grid_row.addWidget(self.grid_rows_spin)
        grid_row.addWidget(QLabel("cols:"))
        self.grid_cols_spin = QSpinBox()
        self.grid_cols_spin.setRange(2, 100)
        self.grid_cols_spin.setValue(5)
        self.grid_cols_spin.setKeyboardTracking(False)
        self.grid_cols_spin.valueChanged.connect(self._mark_results_stale)
        grid_row.addWidget(self.grid_cols_spin)
        som_layout.addLayout(grid_row)

        lr_row = QHBoxLayout()
        lr_row.addWidget(QLabel("Learning rate start:"))
        self.lr_start_spin = QDoubleSpinBox()
        self.lr_start_spin.setRange(0.01, 5.0)
        self.lr_start_spin.setSingleStep(0.05)
        self.lr_start_spin.setValue(0.5)
        self.lr_start_spin.setKeyboardTracking(False)
        self.lr_start_spin.valueChanged.connect(self._mark_results_stale)
        lr_row.addWidget(self.lr_start_spin)
        lr_row.addWidget(QLabel("end:"))
        self.lr_end_spin = QDoubleSpinBox()
        self.lr_end_spin.setRange(0.001, 5.0)
        self.lr_end_spin.setSingleStep(0.01)
        self.lr_end_spin.setValue(0.02)
        self.lr_end_spin.setDecimals(3)
        self.lr_end_spin.setKeyboardTracking(False)
        self.lr_end_spin.valueChanged.connect(self._mark_results_stale)
        lr_row.addWidget(self.lr_end_spin)
        som_layout.addLayout(lr_row)

        radius_row = QHBoxLayout()
        radius_row.addWidget(QLabel("Neighborhood radius (end):"))
        self.radius_end_spin = QDoubleSpinBox()
        self.radius_end_spin.setRange(0.05, 10.0)
        self.radius_end_spin.setSingleStep(0.05)
        self.radius_end_spin.setValue(0.5)
        self.radius_end_spin.setKeyboardTracking(False)
        self.radius_end_spin.valueChanged.connect(self._mark_results_stale)
        radius_row.addWidget(self.radius_end_spin)
        som_layout.addLayout(radius_row)

        iter_row = QHBoxLayout()
        iter_row.addWidget(QLabel("Iterations (full passes):"))
        self.iterations_spin = QSpinBox()
        self.iterations_spin.setRange(10, 5000)
        self.iterations_spin.setSingleStep(50)
        self.iterations_spin.setValue(300)
        self.iterations_spin.setKeyboardTracking(False)
        self.iterations_spin.valueChanged.connect(self._mark_results_stale)
        iter_row.addWidget(self.iterations_spin)
        som_layout.addLayout(iter_row)

        return som_group

    def _show_training_params_help(self):
        QMessageBox.information(
            self, "Training Parameters — Help",
            "<html><body style='font-family: Arial, sans-serif; font-size: 12px;'>"
            "<p><b>Grid rows / cols</b> — size of the node grid. More nodes "
            "give finer resolution but need more spectra and more iterations "
            "to train well. A common starting point is a grid with roughly "
            "5&nbsp;&times;&nbsp;&radic;n_spectra total nodes.</p>"
            "<p><b>Learning rate start / end</b> — step size for weight "
            "updates. It decays geometrically from <i>start</i> down to "
            "<i>end</i> over training: large early updates organise the "
            "map's overall layout quickly, small late updates fine-tune it "
            "without destabilising it.</p>"
            "<p><b>Neighborhood radius (end)</b> — how many neighbouring "
            "nodes still move together late in training, in grid units. It "
            "starts at half the larger grid dimension and decays "
            "geometrically down to this value: early on, a whole "
            "neighbourhood moves toward each sample (organising topology); "
            "late in training only the winning node and its closest "
            "neighbours still move (refining local detail).</p>"
            "<p><b>Iterations (full passes)</b> — number of full passes over "
            "the reshuffled spectra. More passes converge to a more stable "
            "map, at the cost of longer training time. A fixed random seed "
            "means the same settings always reproduce the same map exactly.</p>"
            "<div style='background:#FFF3E0;border-left:4px solid #E65100;"
            "padding:8px 12px;border-radius:3px;margin-top:10px;'>"
            "<b>Why aren't these adjustable in MeltAnalytiX?</b> They exist "
            "in MeltAnalytiX's own SOM training engine too — this dialog's "
            "algorithm is ported directly from it — but MeltAnalytiX's "
            "dialog only exposes Grid rows/cols as controls and leaves "
            "learning rate, radius, and iterations at the engine's built-in "
            "defaults. SpecAnalytiXBase's dialog surfaces the full set.</div>"
            "</body></html>"
        )

    def _create_visualization_group(self):
        group = QGroupBox("Visualization")
        layout = QVBoxLayout(group)

        viz_row = QHBoxLayout()
        viz_row.addWidget(QLabel("Mode:"))
        self.viz_combo = QComboBox()
        self.viz_combo.addItems(['U-Matrix', 'Hit Map', 'Component Plane', 'Sample Map'])
        self.viz_combo.currentTextChanged.connect(self.on_viz_changed)
        viz_row.addWidget(self.viz_combo)
        layout.addLayout(viz_row)

        # --- Component Plane settings ---------------------------------
        self.cp_settings_widget = QWidget()
        cp_layout = QVBoxLayout(self.cp_settings_widget)
        cp_layout.setContentsMargins(0, 0, 0, 0)

        cp_header = QHBoxLayout()
        cp_header.addWidget(QLabel("Component Plane shows:"))
        cp_header.addStretch()
        cp_header.addWidget(_make_help_button(
            "What can the Component Plane show?", self._show_component_plane_help))
        cp_layout.addLayout(cp_header)

        self.cp_metric_combo = QComboBox()
        self.cp_metric_combo.addItems(_ALL_METRICS)
        self.cp_metric_combo.currentTextChanged.connect(self._on_component_plane_controls_changed)
        cp_layout.addWidget(self.cp_metric_combo)

        # Wavelength-index mode (backward-compatible default)
        self.component_row_widget = QWidget()
        component_row = QHBoxLayout(self.component_row_widget)
        component_row.setContentsMargins(0, 0, 0, 0)
        component_row.addWidget(QLabel("Wavelength index:"))
        self.component_index_spin = QSpinBox()
        self.component_index_spin.setRange(0, 0)
        self.component_index_spin.setKeyboardTracking(False)
        self.component_index_spin.valueChanged.connect(self._on_component_plane_controls_changed)
        component_row.addWidget(self.component_index_spin)
        cp_layout.addWidget(self.component_row_widget)

        # Feature-mode: pick which trained feature to show, by name
        self.cp_feature_row_widget = QWidget()
        feature_row = QHBoxLayout(self.cp_feature_row_widget)
        feature_row.setContentsMargins(0, 0, 0, 0)
        feature_row.addWidget(QLabel("Feature:"))
        self.cp_feature_combo = QComboBox()
        self.cp_feature_combo.currentIndexChanged.connect(self._on_component_plane_controls_changed)
        feature_row.addWidget(self.cp_feature_combo)
        cp_layout.addWidget(self.cp_feature_row_widget)

        # Intensity-at-x mode
        self.cp_xpos_row_widget = QWidget()
        xpos_row = QHBoxLayout(self.cp_xpos_row_widget)
        xpos_row.setContentsMargins(0, 0, 0, 0)
        xpos_row.addWidget(QLabel("x ="))
        self.cp_xpos_spin = QDoubleSpinBox()
        self.cp_xpos_spin.setRange(-1e9, 1e9)
        self.cp_xpos_spin.setDecimals(3)
        self.cp_xpos_spin.valueChanged.connect(self._on_component_plane_controls_changed)
        xpos_row.addWidget(self.cp_xpos_spin)
        cp_layout.addWidget(self.cp_xpos_row_widget)

        # Range-metric mode (Mean / Integral / Variance / Peak .../ ...)
        self.cp_range_row_widget = QWidget()
        range_row = QHBoxLayout(self.cp_range_row_widget)
        range_row.setContentsMargins(0, 0, 0, 0)
        range_row.addWidget(QLabel("X1:"))
        self.cp_x1_spin = QDoubleSpinBox()
        self.cp_x1_spin.setRange(-1e9, 1e9)
        self.cp_x1_spin.setDecimals(3)
        self.cp_x1_spin.valueChanged.connect(self._on_component_plane_controls_changed)
        range_row.addWidget(self.cp_x1_spin)
        range_row.addWidget(QLabel("X2:"))
        self.cp_x2_spin = QDoubleSpinBox()
        self.cp_x2_spin.setRange(-1e9, 1e9)
        self.cp_x2_spin.setDecimals(3)
        self.cp_x2_spin.valueChanged.connect(self._on_component_plane_controls_changed)
        range_row.addWidget(self.cp_x2_spin)
        cp_layout.addWidget(self.cp_range_row_widget)

        # Ratio-of-two-bands mode
        self.cp_ratio_widget = QWidget()
        ratio_layout = QVBoxLayout(self.cp_ratio_widget)
        ratio_layout.setContentsMargins(0, 0, 0, 0)
        ratio_metric_row = QHBoxLayout()
        ratio_metric_row.addWidget(QLabel("Band metric:"))
        self.cp_ratio_metric_combo = QComboBox()
        self.cp_ratio_metric_combo.addItems(_RATIO_BAND_METRICS)
        self.cp_ratio_metric_combo.currentTextChanged.connect(self._on_component_plane_controls_changed)
        ratio_metric_row.addWidget(self.cp_ratio_metric_combo)
        ratio_layout.addLayout(ratio_metric_row)

        band_a_row = QHBoxLayout()
        band_a_row.addWidget(QLabel("Band A  X1:"))
        self.cp_a_x1_spin = QDoubleSpinBox()
        self.cp_a_x1_spin.setRange(-1e9, 1e9)
        self.cp_a_x1_spin.setDecimals(3)
        self.cp_a_x1_spin.valueChanged.connect(self._on_component_plane_controls_changed)
        band_a_row.addWidget(self.cp_a_x1_spin)
        band_a_row.addWidget(QLabel("X2:"))
        self.cp_a_x2_spin = QDoubleSpinBox()
        self.cp_a_x2_spin.setRange(-1e9, 1e9)
        self.cp_a_x2_spin.setDecimals(3)
        self.cp_a_x2_spin.valueChanged.connect(self._on_component_plane_controls_changed)
        band_a_row.addWidget(self.cp_a_x2_spin)
        ratio_layout.addLayout(band_a_row)

        band_b_row = QHBoxLayout()
        band_b_row.addWidget(QLabel("Band B  X1:"))
        self.cp_b_x1_spin = QDoubleSpinBox()
        self.cp_b_x1_spin.setRange(-1e9, 1e9)
        self.cp_b_x1_spin.setDecimals(3)
        self.cp_b_x1_spin.valueChanged.connect(self._on_component_plane_controls_changed)
        band_b_row.addWidget(self.cp_b_x1_spin)
        band_b_row.addWidget(QLabel("X2:"))
        self.cp_b_x2_spin = QDoubleSpinBox()
        self.cp_b_x2_spin.setRange(-1e9, 1e9)
        self.cp_b_x2_spin.setDecimals(3)
        self.cp_b_x2_spin.valueChanged.connect(self._on_component_plane_controls_changed)
        band_b_row.addWidget(self.cp_b_x2_spin)
        ratio_layout.addLayout(band_b_row)

        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("Operation:"))
        self.cp_operation_combo = QComboBox()
        self.cp_operation_combo.addItems(_RATIO_OPERATIONS)
        self.cp_operation_combo.currentTextChanged.connect(self._on_component_plane_controls_changed)
        op_row.addWidget(self.cp_operation_combo)
        ratio_layout.addLayout(op_row)

        cp_layout.addWidget(self.cp_ratio_widget)

        layout.addWidget(self.cp_settings_widget)
        self.cp_settings_widget.setVisible(False)

        # --- Sample Map settings ---------------------------------------
        self.sample_map_settings_widget = QWidget()
        sm_layout = QHBoxLayout(self.sample_map_settings_widget)
        sm_layout.setContentsMargins(0, 0, 0, 0)
        sm_layout.addWidget(QLabel("Color by:"))
        self.sample_color_combo = QComboBox()
        self.sample_color_combo.addItem('Distance to BMU')
        self.sample_color_combo.currentTextChanged.connect(self._on_sample_color_changed)
        sm_layout.addWidget(self.sample_color_combo)
        layout.addWidget(self.sample_map_settings_widget)
        self.sample_map_settings_widget.setVisible(False)

        return group

    def _show_component_plane_help(self):
        QMessageBox.information(
            self, "Component Plane — Help",
            "<html><body style='font-family: Arial, sans-serif; font-size: 12px;'>"
            "<p>A Component Plane shows one trained value per node across "
            "the whole grid. In <b>Full spectrum shape</b> training mode you "
            "can choose what that value is:</p>"
            "<ul>"
            "<li><b>Wavelength index (raw)</b> — the node's trained weight "
            "at one wavelength/wavenumber point (standardised units). This "
            "is the original behaviour.</li>"
            "<li><b>Intensity at x</b> — the node's reconstructed prototype "
            "spectrum's intensity at one x-value you choose.</li>"
            "<li><b>Mean / Integral / Baseline-corrected integral / "
            "Variance / Peak intensity / Peak position</b> — the same "
            "metric this app's Band Ratio / Peak Area Calculator tool "
            "offers, computed over an x-range (X1&ndash;X2) on the node's "
            "prototype spectrum.</li>"
            "<li><b>Ratio of two ranges (A/B)</b> — the ratio (or "
            "difference/sum) of the same metric computed over two separate "
            "x-ranges, again on the node's prototype spectrum — e.g. the "
            "ratio of two band intensities across the map.</li>"
            "</ul>"
            "<p>A single x-value can be sensitive to noise, so the "
            "range-based metrics are usually the more robust choice.</p>"
            "<p>In <b>Custom features</b> training mode, each Component "
            "Plane already corresponds to one of your defined features, so "
            "this picker is replaced with a simple feature-name dropdown.</p>"
            "</body></html>"
        )

    # ------------------------------------------------------------------ #
    # Canvas / info panels                                                #
    # ------------------------------------------------------------------ #

    def create_canvas_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.canvas = SOMCanvas()
        self.canvas.set_som_controller(self.controller)

        # Dialog's own independent Shorten Names toggle — same convention
        # as ClusterAnalysisDialog's (off by default, not tied to the main
        # window's checkbox of the same name).
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.canvas.get_shorten_enabled = self.checkBox_shorten_names.isChecked
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)

        self.canvas.node_selected.connect(self.on_node_selected)

        self.toolbar = NavigationToolbar(self.canvas, widget)
        toolbar_row = QHBoxLayout()
        toolbar_row.addWidget(self.toolbar)
        toolbar_row.addStretch()
        toolbar_row.addWidget(self.checkBox_shorten_names)
        layout.addLayout(toolbar_row)
        layout.addWidget(self.canvas)

        return widget

    def create_info_panel(self):
        widget = QWidget()
        widget.setMaximumHeight(300)
        layout = QVBoxLayout(widget)

        self.interactive_group = QGroupBox("Interactive Selection")
        interactive_layout = QHBoxLayout(self.interactive_group)
        self.interactive_checkbox = QCheckBox("Enable Click Selection")
        self.interactive_checkbox.setChecked(True)
        self.interactive_checkbox.stateChanged.connect(self.on_interactive_changed)
        interactive_layout.addWidget(self.interactive_checkbox)
        self.reset_highlight_btn = QPushButton("Reset Highlights")
        self.reset_highlight_btn.clicked.connect(self.reset_highlights)
        interactive_layout.addWidget(self.reset_highlight_btn)
        interactive_layout.addStretch()
        layout.addWidget(self.interactive_group)

        self.node_info_group = QGroupBox("Node Information")
        info_layout = QVBoxLayout(self.node_info_group)
        self.node_info_text = QTextEdit()
        self.node_info_text.setMaximumHeight(160)
        self.node_info_text.setReadOnly(True)
        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.Monospace)
        self.node_info_text.setFont(font)
        info_layout.addWidget(self.node_info_text)

        self.show_spectra_btn = QPushButton("Show Node Spectra")
        self.show_spectra_btn.setEnabled(False)
        self.show_spectra_btn.clicked.connect(self.show_node_spectra)
        info_layout.addWidget(self.show_spectra_btn)

        layout.addWidget(self.node_info_group)

        return widget

    # ------------------------------------------------------------------ #
    # Interactive selection                                               #
    # ------------------------------------------------------------------ #

    def on_interactive_changed(self, state):
        self.canvas.set_interactive_mode(self.interactive_checkbox.isChecked())

    def reset_highlights(self):
        self.canvas.reset_highlight()
        self.node_info_text.clear()
        self._last_displayed_node = None
        self.show_spectra_btn.setEnabled(False)

    def on_node_selected(self, row, col, member_labels):
        self.display_node_info(row, col, member_labels)

    def on_table_cell_clicked(self, row_idx, column):
        item = self.results_table.item(row_idx, 0)
        col_item = self.results_table.item(row_idx, 1)
        if item is None or col_item is None:
            return
        try:
            node_row = int(item.text())
            node_col = int(col_item.text())
        except ValueError:
            return
        members = self.controller.get_node_members(node_row, node_col)
        self.canvas.highlighted_node = (node_row, node_col)
        self.canvas.plot_som()
        self.display_node_info(node_row, node_col, members)

    def display_node_info(self, row, col, member_labels):
        shortened = self.canvas._shortened(member_labels) if member_labels else []
        lines = [f"Node ({row}, {col}) — {len(member_labels)} spectrum/spectra:", ""]
        lines.extend(f"  {lbl}" for lbl in shortened)
        self.node_info_text.setPlainText("\n".join(lines))
        self._last_displayed_node = (row, col, list(member_labels))
        self.show_spectra_btn.setEnabled(bool(member_labels))

    def _on_shorten_names_toggled(self, _state):
        # Point-in-time bug fix: toggling this checkbox used to do nothing
        # to an already-displayed node's info text — it only took effect
        # the *next* time a node was clicked. Re-render the currently
        # shown node (if any) immediately, same as ClusterAnalysisDialog's
        # own _on_shorten_names_toggled.
        if self._last_displayed_node is not None:
            row, col, labels = self._last_displayed_node
            self.display_node_info(row, col, labels)

    def show_node_spectra(self):
        """Point 5: view the actual overlaid member spectra for the
        currently selected node (not just their labels), plus — in
        'shape' training mode — the node's own reconstructed prototype
        spectrum as a bold reference curve."""
        if self._last_displayed_node is None:
            return
        row, col, member_labels = self._last_displayed_node
        if not member_labels:
            return

        spectra_by_label = {s['label']: s for s in self.spectra}
        shortened = self.canvas._shortened(member_labels)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Node ({row}, {col}) — Member Spectra")
        dlg.resize(760, 580)
        layout = QVBoxLayout(dlg)

        fig = Figure(figsize=(7, 5))
        canvas = FigureCanvas(fig)
        toolbar = NavigationToolbar(canvas, dlg)
        ax = fig.add_subplot(111)

        for lbl, short_lbl in zip(member_labels, shortened):
            s = spectra_by_label.get(lbl)
            if s is None:
                continue
            ax.plot(s['x_scale'], s['y_scale'], linewidth=0.9, alpha=0.75, label=short_lbl)

        if self.controller.manager.train_mode == 'shape':
            x_proto, y_proto = self.controller.get_node_prototype_spectrum(row, col)
            if x_proto is not None:
                ax.plot(x_proto, y_proto, color='black', linewidth=2.4,
                       label='Node prototype', zorder=5)

        ax.set_title(f"Node ({row}, {col}) — {len(member_labels)} spectrum/spectra")
        ax.set_xlabel('x')
        ax.set_ylabel('Intensity')
        if len(member_labels) <= 15:
            ax.legend(fontsize=7, loc='best')
        fig.tight_layout()

        layout.addWidget(toolbar)
        layout.addWidget(canvas)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        dlg.exec_()

    # ------------------------------------------------------------------ #
    # Component Plane / Sample Map control wiring                        #
    # ------------------------------------------------------------------ #

    def _update_component_plane_controls_visibility(self):
        is_cp = self.viz_combo.currentText() == 'Component Plane'
        is_sm = self.viz_combo.currentText() == 'Sample Map'
        is_feature_mode = self.radio_train_features.isChecked()

        self.cp_settings_widget.setVisible(is_cp)
        self.sample_map_settings_widget.setVisible(is_sm)

        if not is_cp:
            return

        self.cp_metric_combo.setVisible(not is_feature_mode)
        self.cp_feature_row_widget.setVisible(is_feature_mode)
        if is_feature_mode:
            self.component_row_widget.setVisible(False)
            self.cp_xpos_row_widget.setVisible(False)
            self.cp_range_row_widget.setVisible(False)
            self.cp_ratio_widget.setVisible(False)
            return

        metric = self.cp_metric_combo.currentText()
        self.component_row_widget.setVisible(metric == 'Wavelength index (raw)')
        self.cp_xpos_row_widget.setVisible(metric == 'Intensity at x')
        self.cp_range_row_widget.setVisible(metric in _RANGE_METRICS)
        self.cp_ratio_widget.setVisible(metric == 'Ratio of two ranges (A/B)')

    def _build_component_plane_settings(self):
        """Return (settings_or_None, label) for the canvas, from whatever
        the Component Plane controls currently say. settings is None for
        the raw wavelength-index / feature-index mode (backward
        compatible — canvas falls back to manager.get_component_plane)."""
        if self.radio_train_features.isChecked():
            return None, None  # handled separately via cp_feature_combo -> component_feature_index

        metric = self.cp_metric_combo.currentText()
        if metric == 'Wavelength index (raw)':
            return None, None

        if metric == 'Intensity at x':
            band_a = {'metric': 'Intensity at x', 'x_pos': self.cp_xpos_spin.value(),
                     'ranges': [], 'is_exclude': False}
            return {'band_a': band_a, 'band_b': None, 'operation': 'A only'}, \
                   f"x = {self.cp_xpos_spin.value():g}"

        if metric in _RANGE_METRICS:
            band_a = {'metric': metric,
                     'ranges': [[self.cp_x1_spin.value(), self.cp_x2_spin.value()]],
                     'is_exclude': False}
            return {'band_a': band_a, 'band_b': None, 'operation': 'A only'}, \
                   f"{metric} [{self.cp_x1_spin.value():g}–{self.cp_x2_spin.value():g}]"

        # Ratio of two ranges (A/B)
        ratio_metric = self.cp_ratio_metric_combo.currentText()
        if ratio_metric == 'Intensity at x':
            band_a = {'metric': ratio_metric, 'x_pos': self.cp_a_x1_spin.value(),
                     'ranges': [], 'is_exclude': False}
            band_b = {'metric': ratio_metric, 'x_pos': self.cp_b_x1_spin.value(),
                     'ranges': [], 'is_exclude': False}
        else:
            band_a = {'metric': ratio_metric,
                     'ranges': [[self.cp_a_x1_spin.value(), self.cp_a_x2_spin.value()]],
                     'is_exclude': False}
            band_b = {'metric': ratio_metric,
                     'ranges': [[self.cp_b_x1_spin.value(), self.cp_b_x2_spin.value()]],
                     'is_exclude': False}
        operation = self.cp_operation_combo.currentText()
        label = f"{operation} of {ratio_metric} (A, B)"
        return {'band_a': band_a, 'band_b': band_b, 'operation': operation}, label

    def _on_component_plane_controls_changed(self, *_args):
        self._update_component_plane_controls_visibility()
        if self.viz_combo.currentText() != 'Component Plane' or self.controller.manager.hit_map is None:
            return

        if self.radio_train_features.isChecked():
            self.canvas.component_plane_settings = None
            self.canvas.component_feature_index = self.cp_feature_combo.currentIndex()
        else:
            settings, label = self._build_component_plane_settings()
            self.canvas.component_plane_settings = settings
            self.canvas.component_plane_label = label
            if settings is None:
                self.canvas.component_feature_index = self.component_index_spin.value()

        self.canvas.plot_som()

    def _on_sample_color_changed(self, *_args):
        if self.viz_combo.currentText() != 'Sample Map' or self.controller.manager.hit_map is None:
            return
        manager = self.controller.manager
        choice = self.sample_color_combo.currentText()
        if choice == 'Distance to BMU':
            self.canvas.sample_color_values = manager.per_sample_error
            self.canvas.sample_color_label = 'Distance to BMU'
        elif manager.train_mode == 'feature' and manager.feature_labels and choice in manager.feature_labels:
            idx = manager.feature_labels.index(choice)
            self.canvas.sample_color_values = manager.data_matrix[:, idx]
            self.canvas.sample_color_label = choice
        else:
            self.canvas.sample_color_values = None
            self.canvas.sample_color_label = ''
        self.canvas.plot_som()

    # ------------------------------------------------------------------ #
    # Run                                                                 #
    # ------------------------------------------------------------------ #

    def _mark_results_stale(self, *_):
        if getattr(self, '_has_run_once', False):
            self._stale_warning_label.setVisible(True)

    def on_viz_changed(self):
        mode_map = {'U-Matrix': 'u_matrix', 'Hit Map': 'hit_map',
                   'Component Plane': 'component_plane', 'Sample Map': 'sample_map'}
        current = self.viz_combo.currentText()
        self._update_component_plane_controls_visibility()
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        QApplication.processEvents()
        try:
            self.canvas.set_interactive_mode(self.interactive_checkbox.isChecked())
            self.canvas.set_visualization_mode(mode_map[current])
        finally:
            QApplication.restoreOverrideCursor()

    def run_som(self):
        if self._som_running:
            return
        self._som_running = True

        is_feature_mode = self.radio_train_features.isChecked()
        feature_defs = self._collect_feature_defs() if is_feature_mode else None
        if is_feature_mode and not feature_defs:
            QMessageBox.warning(self, "No Features Defined",
                               "Add at least one feature in the Training Data table, "
                               "or switch back to 'Full spectrum shape'.")
            self._som_running = False
            return

        params = dict(
            grid_rows=self.grid_rows_spin.value(),
            grid_cols=self.grid_cols_spin.value(),
            n_iterations=self.iterations_spin.value(),
            learning_rate_start=self.lr_start_spin.value(),
            learning_rate_end=self.lr_end_spin.value(),
            radius_end=self.radius_end_spin.value(),
            train_mode='feature' if is_feature_mode else 'shape',
            feature_defs=feature_defs,
        )

        self.run_btn.setEnabled(False)
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))

        # Determinate progress bar tracking REAL progress, not fixed stage
        # boundaries standing in for one opaque call: SOMManager._train is
        # a plain numpy loop under our control, so this bar advances one
        # tick per completed training pass (see SOMManager.compute_som's
        # progress_callback docstring for why that's possible here but not
        # for e.g. Cluster Analysis's single scikit-learn fit() call).
        self._som_progress = QProgressDialog(
            'Running SOM…', None, 0, self.iterations_spin.value() + 1, self)
        self._som_progress.setWindowModality(Qt.WindowModal)
        self._som_progress.setWindowTitle('SOM Analysis')
        self._som_progress.setMinimumDuration(0)
        self._som_progress.setCancelButton(None)
        self._som_progress.setValue(0)
        self._som_progress.show()

        self._som_worker = _ComputeWorker(None, self)
        self._som_worker._fn = lambda: self.controller.compute_som(
            self.spectra, progress_callback=self._som_worker.progress.emit, **params)
        self._som_worker.progress.connect(self._on_som_progress)
        self._som_worker.done.connect(self._on_som_computed)
        self._som_worker.start(QThread.LowPriority)

    def _on_som_progress(self, step, total_steps, label):
        if total_steps != self._som_progress.maximum():
            self._som_progress.setMaximum(total_steps)
        self._som_progress.setLabelText(label)
        self._som_progress.setValue(step)

    def _on_som_computed(self):
        try:
            if self._som_worker.error is not None:
                QMessageBox.critical(self, "SOM Error", str(self._som_worker.error))
                return

            success = self._som_worker.result
            if success:
                manager = self.controller.manager
                n_features = self.controller.get_n_features()
                self.component_index_spin.setRange(0, max(0, n_features - 1))

                self.cp_feature_combo.blockSignals(True)
                self.cp_feature_combo.clear()
                if manager.train_mode == 'feature':
                    self.cp_feature_combo.addItems(manager.feature_labels or [])
                self.cp_feature_combo.blockSignals(False)

                self.sample_color_combo.blockSignals(True)
                self.sample_color_combo.clear()
                self.sample_color_combo.addItem('Distance to BMU')
                if manager.train_mode == 'feature':
                    self.sample_color_combo.addItems(manager.feature_labels or [])
                self.sample_color_combo.blockSignals(False)
                self._on_sample_color_changed()

                self.update_results()
                self._update_component_plane_controls_visibility()
                self._on_component_plane_controls_changed()
                self.canvas.plot_som()
                self.canvas.set_interactive_mode(self.interactive_checkbox.isChecked())
                self.save_excel_btn.setEnabled(True)
                self.export_csv_btn.setEnabled(True)
                self._has_run_once = True
                self._stale_warning_label.setVisible(False)
            else:
                detail = getattr(self.controller.manager, 'last_error', None)
                QMessageBox.warning(self, "SOM Training Failed", detail or "SOM training failed.")
        finally:
            self._som_progress.close()
            self.run_btn.setEnabled(True)
            self._som_running = False
            QApplication.restoreOverrideCursor()

    def update_results(self):
        info = self.controller.get_node_info()
        self.results_table.setRowCount(len(info))
        for i, node in enumerate(info):
            self.results_table.setItem(i, 0, QTableWidgetItem(str(node['row'])))
            self.results_table.setItem(i, 1, QTableWidgetItem(str(node['col'])))
            self.results_table.setItem(i, 2, QTableWidgetItem(str(node['size'])))
            qe_text = f"{node['mean_qe']:.3f}" if node['mean_qe'] is not None else "N/A"
            self.results_table.setItem(i, 3, QTableWidgetItem(qe_text))

    # ------------------------------------------------------------------ #
    # Export                                                              #
    # ------------------------------------------------------------------ #

    def show_export_menu(self):
        menu = QMenu(self)
        detailed_action = menu.addAction("Export BMU Assignments (detailed)...")
        detailed_action.setToolTip("Export every spectrum with its assigned node")
        menu.addSeparator()
        summary_action = menu.addAction("Export Node Summary...")
        summary_action.setToolTip("Export per-node spectra counts and mean distance")
        action = menu.exec_(self.export_csv_btn.mapToGlobal(self.export_csv_btn.rect().bottomLeft()))
        if action == detailed_action:
            self.export_detailed_csv()
        elif action == summary_action:
            self.export_summary_csv()

    def export_detailed_csv(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export BMU Assignments", "som_assignments_detailed.csv", "CSV Files (*.csv)")
        if not filepath:
            return
        try:
            import pandas as pd
            manager = self.controller.manager
            df = pd.DataFrame({
                'Spectrum': manager.spectrum_labels,
                'Node_Row': manager.bmu_indices[:, 0],
                'Node_Col': manager.bmu_indices[:, 1],
            })
            df.to_csv(filepath, index=False)
            QMessageBox.information(self, "Export Successful",
                                    f"BMU assignments exported successfully!\n\nFile: {filepath}")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export assignments:\n{str(e)}")

    def export_summary_csv(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Node Summary", "som_node_summary.csv", "CSV Files (*.csv)")
        if not filepath:
            return
        try:
            import pandas as pd
            df = pd.DataFrame(self.controller.get_node_info())
            df.to_csv(filepath, index=False)
            QMessageBox.information(self, "Export Successful",
                                    f"Node summary exported successfully!\n\nFile: {filepath}")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export node summary:\n{str(e)}")

    def save_excel_results(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save SOM Analysis", "som_results.xlsx", "Excel Files (*.xlsx)")
        if filepath:
            if self.controller.manager.save_results_excel(filepath):
                QMessageBox.information(self, "Success", "Results saved successfully to Excel")
            else:
                QMessageBox.warning(self, "Error", "Failed to save results")

    def show_help(self):
        from src.help.som_help import get_som_help_content, get_som_help_title
        from src.help.help_window import show_help_window
        show_help_window(self, get_som_help_title(), get_som_help_content())
