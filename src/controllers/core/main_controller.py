
# src/controllers/core/main_controller.py
import re
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QCheckBox,
    QListWidget, QListWidgetItem, QPushButton, QMenu, QLabel, QSizePolicy,
    QShortcut, QApplication, QMessageBox, QToolButton, QStyledItemDelegate
)
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt, QPoint

from src.views.main_window import MainWindow
from src.controllers.data_io.import_controller import ImportController
from src.controllers.misc.save_spectra_controller import SaveController
from src.controllers.utils.webpage_controller import WebpageController
from src.controllers.misc.spectrum_selector_controller import SpectrumSelector
from src.controllers.core.operations_controller import OperationsController
from src.controllers.data_analysis.peak_detection_controller import PeakDetectionController
from src.controllers.data_analysis.spectral_range_controller import SpectralRangeController
from src.controllers.visualization.grid_properties_controller import GridPropertiesController
from src.controllers.misc.import_settings_controller import ImportSettingsController
from src.controllers.visualization.axis_properties_controller import AxisPropertiesController
from src.controllers.visualization.custom_plot_properties_controller import CustomPlotPropertiesController
from src.modules.visualization.plotting import grid_plot_mode, overlay_plot_mode, waterfall_plot_mode, mean_sd_plot_mode, difference_plot_mode, heatmap_plot_mode
from src.modules.visualization.band_marker_manager import BandMarkerManager
# from src.modules.resource_path import resource_path
from src.modules.visualization.custom_plot_properties_manager import CustomPlotPropertiesManager
from src.controllers.visualization.legend_properties_controller import LegendPropertiesController
from src.controllers.visualization.constrained_layout_controller import ConstrainedLayoutController
from src.modules.visualization.external_figure import create_external_figure
from src.controllers.misc.spectrum_metadata_controller import SpectrumMetadataController
from src.controllers.data_analysis.normalization_controller import NormalizationController
from src.controllers.data_analysis.svd_interpolation_controller import SVDInterpolationController
from src.controllers.data_analysis.savitzky_golay_controller import SavitzkyGolayController
from src.controllers.visualization_analysis.visualization_analysis_controller import VisualizationAnalysisController
from src.controllers.visualization_analysis.cluster_analysis_controller import ClusterAnalysisController
from src.controllers.visualization_analysis.pca_scores_controller import PcaScoresController
from src.controllers.visualization_analysis.nmf_controller import NMFController
from src.controllers.visualization_analysis.mcr_als_controller import MCRALSController
from src.controllers.visualization_analysis.two_d_correlation_controller import TwoDCorrelationController
from src.controllers.visualization_analysis.map2d_controller import Map2DController
from src.controllers.data_analysis.interactive_subtraction_controller import InteractiveSubtractionController


# import os
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import validate_common_x_axis
from src.modules.utils.spectrum_identity import spectrum_key, spectrum_id
from src.modules.utils.label_shortening import compute_distinguishing_labels, shorten_spectra_labels
logger = get_logger(__name__)


class _SpectraListWidget(QListWidget):
    """QListWidget that doesn't let a right-click change the current
    selection. By default, Qt's mousePressEvent handling treats a
    right-click the same as a left-click for selection purposes — so
    right-clicking anywhere except exactly on an already-selected item
    silently collapses a multi-selection down to just the clicked item,
    *before* the context menu even opens. Selection should only ever
    change from a deliberate left-click.
    """
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton and self.selectedItems():
            # Preserve whatever's already selected — don't let a
            # right-click collapse an existing multi-selection down to
            # just the clicked item before the context menu even opens.
            # If nothing is selected yet, fall through to normal handling
            # so right-clicking an item selects it, a reasonable default.
            return
        super().mousePressEvent(event)


class _DistinguishingNameDelegate(QStyledItemDelegate):
    """
    Item delegate for the spectra list widget that DISPLAYS only each
    item's distinguishing part (see
    src/modules/utils/label_shortening.py's compute_distinguishing_labels,
    the shared implementation used by every other "shorten names" caller
    in the app — plot legends, Cluster Analysis, 2D Correlation,
    Reference Matching, and the operation dialogs) instead of its full
    label — purely cosmetic.

    Overriding initStyleOption() rather than paint() is deliberate: Qt's
    default QStyledItemDelegate.paint() reads whatever text
    initStyleOption() put into the style option, so replacing just that
    text here means selection highlighting, hover state, fonts, and
    everything else about how the row is drawn stays exactly as it would
    be without this delegate — only the text itself changes.

    Critically, this NEVER touches the underlying model data —
    item.text() on every item in the list still returns the full,
    original label, unchanged, and item.data(Qt.UserRole) still returns
    the spectrum's unique_id. Selection tracking, sort-order restoration,
    and every operation controller's "which spectra are selected" check
    all key off Qt.UserRole (see spectrum_identity.py's spectrum_key /
    spectrum_id and developer_guide_help.py's "Golden Rule: Spectrum
    Identity"), not off this displayed text, so this delegate touching
    only the paint step is a matter of keeping concerns separate rather
    than a load-bearing requirement. Toggling the "shorten names"
    checkbox needs nothing beyond switching this delegate in and
    repainting.
    """
    def __init__(self, list_widget, parent=None):
        super().__init__(parent)
        self._list_widget = list_widget
        self._cache_key = None
        self._cache = {}

    def _shortened_map(self):
        labels = tuple(
            item.text()
            for item in (self._list_widget.item(i) for i in range(self._list_widget.count()))
            if item is not None
        )
        if labels != self._cache_key:
            self._cache = compute_distinguishing_labels(list(labels))
            self._cache_key = labels
        return self._cache

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # try/except is deliberate and load-bearing here, not defensive
        # decoration -- see the identical guard (and full explanation) in
        # label_shortening.py's make_shortened_name_delegate /
        # make_display_text_delegate. initStyleOption() is a Qt virtual
        # method override called directly by Qt's C++ paint machinery;
        # PyQt5's documented behavior for an unhandled Python exception
        # raised inside it is to abort() the ENTIRE application (SIGABRT)
        # -- no error dialog, no traceback without an attached console.
        # This delegate is installed on the MAIN spectra list widget and
        # repaints on every import, so any exception here (e.g. a
        # momentarily inconsistent item count mid-populate, or an edge
        # case in compute_distinguishing_labels) would silently kill the
        # whole app immediately after importing data -- matching a real
        # confirmed report of exactly that: "no matter which data/
        # spectra I choose, it always crashes" right after an Excel
        # import, no dialog, no traceback. This was the one copy of the
        # delegate that hadn't been hardened yet (see the module
        # docstring in label_shortening.py noting this is a separately
        # maintained duplicate of that shared pattern).
        try:
            full_text = option.text
            option.text = self._shortened_map().get(full_text, full_text)
        except Exception:
            pass


class MainController(QMainWindow):
    def __init__(self):
        super().__init__()
        self.view = MainWindow(controller=self)  # Initialize the main window view.

        # Add spectrum selection control
        self.spectrum_selection_widget = self.create_spectrum_selection_widget()
        self.view.spectrum_selection_frame.setLayout(QVBoxLayout())
        self.view.spectrum_selection_frame.layout().addWidget(self.spectrum_selection_widget)
        self.view.spectrum_selection_frame.setVisible(False)

        # Initialize controllers, atributes, UI
        self.setup_controllers()
        self.initialize_attributes()
        self.initialize_ui()

        # Connect signals & slots
        self.connect_signals()

    def setup_controllers(self):
        """Initialize sub-controllers."""
        self.import_controller = ImportController(self.view, self)
        self.import_controller.spectra_cleared.connect(self.reset_plot_state)
        self.save_controller = SaveController(self)
        self.webpage_controller = WebpageController()
        self.spectrum_selector = SpectrumSelector(self, self.spectrum_selection_widget)
        self.peak_detection_controller = PeakDetectionController(self)
        self.custom_plot_properties_manager = CustomPlotPropertiesManager(self)
        self.spectral_range_controller = SpectralRangeController(self) 
        self.normalization_controller = NormalizationController(self)  # Add normalization controller
        self.svd_interpolation_controller = SVDInterpolationController(self)
        self.operations_controller = OperationsController(self)  
        self.legend_properties_controller = LegendPropertiesController(self)
        self.grid_properties_controller = GridPropertiesController(self)
        self.import_settings_controller = ImportSettingsController(self)
        self.axis_properties_controller = AxisPropertiesController(self)
        self.custom_plot_properties_controller = CustomPlotPropertiesController(self)
        self.constrained_layout_controller = ConstrainedLayoutController(self)
        self.spectrum_metadata_controller = SpectrumMetadataController(self)
        self.savitzky_golay_controller = SavitzkyGolayController(self)
        self.visualization_analysis_controller = VisualizationAnalysisController(self)
        self.cluster_analysis_controller = ClusterAnalysisController(self)
        self.pca_scores_controller = PcaScoresController(self)
        self.nmf_controller = NMFController(self)
        self.mcr_als_controller = MCRALSController(self)
        self.two_d_correlation_controller = TwoDCorrelationController(self)
        self.map2d_controller = Map2DController(self)
        self.interactive_subtraction_controller = InteractiveSubtractionController(self)
        
    def reset_plot_state(self):
        """Reset all plot-related state when spectra are cleared."""
        
        self.selected_spectra = []  # Clear selected spectra
        self.original_spectra = []  # Clear original spectra
        self.custom_plot_properties_manager.spectrum_properties = {}  # Reset plot properties
        self.clear_graphics_view()  # Clear the plot
        
        # Reset UI elements
        self.spectra_list_widget.clear()
        self.view.number_of_rows_spinBox.setValue(1)
        self.view.number_of_columns_spinBox.setValue(1)
        
        # Reset other plot-related attributes as needed
        self.view.x_scale_comboBox.setCurrentText("linear")
        self.view.y_scale_comboBox.setCurrentText("linear")        

    def create_spectrum_selection_widget(self):
        """
        Create a widget for spectrum selection with checkboxes and additional controls.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        layout.addLayout(self.create_num_label_row())
        layout.addWidget(self.create_spectra_list_widget())
        layout.addLayout(self.create_select_buttons_layout())
        layout.addLayout(self.create_spectra_actions_layout())
        layout.addLayout(self.create_interactive_controls())

        return widget
    
    def create_num_label_row(self):
        """Row directly above the spectra list: the selection counter,
        plus the Reverse sorting checkbox. Reverse sorting used to live
        in Basic plot options, but it controls how *this list* is
        ordered, not how the plot itself looks — moved here to sit next
        to the thing it actually affects."""
        layout = QHBoxLayout()
        layout.addWidget(self.create_num_label())

        self.checkBox_reverse_order = QCheckBox("reverse sorting")
        self.checkBox_reverse_order.setObjectName("checkBox_reverse_order")
        layout.addWidget(self.checkBox_reverse_order)

        # Purely cosmetic: shows each item's DISTINGUISHING part only
        # (see label_shortening.compute_distinguishing_labels) — the underlying spectrum
        # labels this list actually tracks (selection, sort order, every
        # operation that reads item.text()) are completely unaffected.
        # Off by default — full names are the safer default; this is an
        # opt-in convenience for a batch of long, similarly-prefixed
        # names (e.g. many spectra imported from the same file, or
        # several "Add" imports sharing a naming convention).
        self.checkBox_shorten_names = QCheckBox("shorten names")
        self.checkBox_shorten_names.setObjectName("checkBox_shorten_names")
        self.checkBox_shorten_names.setToolTip(
            "When checked, each spectrum's list entry shows only the "
            "part of its name that differs from every other spectrum "
            "currently in the list — any text shared by ALL of them "
            "(e.g. a common '<file> : ' lead-in from importing several "
            "columns of the same file) is hidden here, purely to keep "
            "long entries readable. Nothing about the spectrum's actual "
            "name changes — this only affects how it's displayed in "
            "this list."
        )
        layout.addWidget(self.checkBox_shorten_names)

        # Small ? button — same orange style as the plot controls help
        # button near the Legend button — explains what these two
        # checkboxes actually do, since neither is self-explanatory from
        # its label alone.
        self.sort_shorten_help_button = QPushButton("?")
        self.sort_shorten_help_button.setFixedWidth(24)
        self.sort_shorten_help_button.setToolTip(
            "Explain reverse sorting and shorten names"
        )
        self.sort_shorten_help_button.setStyleSheet(
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
        self.sort_shorten_help_button.clicked.connect(self._show_sort_shorten_help)
        layout.addWidget(self.sort_shorten_help_button)

        layout.addStretch(1)

        return layout

    def _show_sort_shorten_help(self):
        """Show a popup explaining reverse sorting and shorten names."""
        QMessageBox.information(
            self.view,
            'Sorting & Display',
            '<b>Reverse sorting</b><br>'
            'Reverses the order spectra appear in this list (and wherever '
            'else that order is used, e.g. plot legend order). It does not '
            'change any spectrum’s data or name — only the order the '
            'list is displayed in.<br><br>'
            '<b>Shorten names</b><br>'
            'When checked, each spectrum’s list entry shows only the '
            'part of its name that differs from every other spectrum '
            'currently in the list — any text shared by ALL of them (e.g. '
            'a common file-name prefix from importing several columns of '
            'the same file) is hidden here, purely to keep long entries '
            'readable. This is purely cosmetic: the spectrum’s actual '
            'name is unchanged, and every operation that reads a '
            'spectrum’s name (selection, saving, exporting, etc.) '
            'still uses the full original name. This same checkbox also '
            'controls shortened-name display in several analysis dialogs '
            'that expose their own "Shorten Names" option.'
        )
    
    def create_num_label(self):
        self.num_label = QLabel("Num:")
        self.num_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return self.num_label
    
    def create_spectra_list_widget(self):
        self.spectra_list_widget = _SpectraListWidget()

        # Setup context menu
        self.spectra_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.spectra_list_widget.customContextMenuRequested.connect(self.show_spectra_list_context_menu)

        # "shorten names" support (see checkBox_shorten_names) — swapped
        # in/out of the widget's item delegate by toggle_shorten_names.
        # Kept as the widget's own default delegate object (rather than
        # None) so switching back is just "restore this same instance",
        # not "guess what Qt's built-in default would have been".
        self._default_item_delegate = self.spectra_list_widget.itemDelegate()
        self._shorten_names_delegate = _DistinguishingNameDelegate(self.spectra_list_widget)

        return self.spectra_list_widget

    def toggle_shorten_names(self, *_):
        """Handler for checkBox_shorten_names — swap the spectra list's
        item delegate and repaint. See _DistinguishingNameDelegate for
        why this is the only thing needed for the list widget itself: it
        reads the list's current item text on every paint, so it needs no
        separate 'refresh when spectra change' hook anywhere else in the
        app.

        The main plot's legend/axis text is different: it's baked into
        actual matplotlib Text objects at plot time (via display_labels in
        _plot_spectra_impl), not repainted live like the list widget, so
        toggling the checkbox alone wouldn't change an already-drawn plot.
        Explicitly replot here so the currently shown plot updates right
        away, regardless of the Interactive Update setting — this is a
        direct, one-off user action, not a rapid-selection-change scenario
        Interactive Update is meant to throttle."""
        checked = self.checkBox_shorten_names.isChecked()
        self.spectra_list_widget.setItemDelegate(
            self._shorten_names_delegate if checked else self._default_item_delegate
        )
        self.spectra_list_widget.viewport().update()
        self.plot_spectra()

    def show_spectra_list_context_menu(self, position):
        """Show context menu for the spectra list widget."""
        context_menu = QMenu()
        
        # Add previous buttons as menu actions
        show_metadata_action = context_menu.addAction("Show Metadata")
        context_menu.addSeparator()
        
        # Create submenu for plot properties
        plot_properties_menu = QMenu("Plot Properties", context_menu)
        context_menu.addMenu(plot_properties_menu)           
        
        # Add actions to the plot properties submenu
        show_info_action = plot_properties_menu.addAction("Show Info")
        plot_properties_menu.addSeparator()
        set_properties_action = plot_properties_menu.addAction("Modify")
        reset_properties_action = plot_properties_menu.addAction("Reset to default")
        context_menu.addSeparator()
        select_all_action = context_menu.addAction("Select All")
        unselect_all_action = context_menu.addAction("Unselect All")
        select_range_action = context_menu.addAction("Select spectra")

        context_menu.addSeparator()
        rename_action = context_menu.addAction("Rename")
        copy_action = context_menu.addAction("Copy spectra")
        copy_action.setToolTip("Create copies of the selected spectra with a _copy suffix")
        context_menu.addSeparator()
        delete_action = context_menu.addAction("Delete spectra")

        # Get the global position for the menu
        global_pos = self.spectra_list_widget.mapToGlobal(position)
        
        # Get currently selected items, resolved to spectrum dicts by
        # identity (Qt.UserRole unique_id) rather than by label text —
        # see CustomPlotPropertiesManager's class docstring.
        selected_spectra = self._selected_spectra_by_identity()


        # Show menu and handle actions
        action = context_menu.exec_(global_pos)
        
        if action == show_metadata_action:
            self.spectrum_selector.show_selected_spectrum_metadata()
            
        elif action == show_info_action:
            self.custom_plot_properties_manager.show_properties_table(selected_spectra)

        elif action == set_properties_action:
            self.custom_plot_properties_controller.show_dialog()

        elif action == reset_properties_action:
            self.custom_plot_properties_manager.reset_selected_properties(selected_spectra)
            
        elif action == select_all_action:
            self.spectrum_selector.select_all_items()
        
        elif action == unselect_all_action:
            self.spectrum_selector.unselect_all_items() 
            
        elif action == select_range_action:
            self.spectrum_selector.show_spectra_selection_dialog()  

        elif action == rename_action:
            self.spectrum_selector.show_rename_dialog()

        elif action == copy_action:
            self._copy_selected_spectra()

        elif action == delete_action:
            self.spectrum_selector.delete_selected_spectra()

    def _copy_selected_spectra(self):
        """Create copies of the selected spectra, append them to the list,
        and register the operation in the history (same as deletion)."""
        import uuid
        from src.modules.utils.correction_history import append_correction_history
        selected = self.spectrum_selector.get_selected_spectra()
        if not selected:
            return

        existing_labels = {s['label'] for s in self.original_spectra}
        new_spectra = []

        for spectrum in selected:
            base_name = spectrum['label'] + '_copy'
            new_name = base_name
            counter = 2
            while new_name in existing_labels or new_name in {s['label'] for s in new_spectra}:
                new_name = f"{base_name}_{counter}"
                counter += 1

            # Built fresh — NOT copy.deepcopy(spectrum), which inherited
            # the ENTIRE original spectrum's metadata (file path, column
            # index, import parameters, etc.), meaningless for a copy
            # that was never separately imported from anywhere. Same fix
            # as Peak Fitting's fit/residual spectra; see
            # PeakFittingController for the full reasoning. Only
            # x_scale/y_scale carry over; metadata starts empty and gets
            # exactly what's relevant: a fresh identity and a
            # correction_history entry recording which spectrum this is
            # a copy of — previously missing entirely, so a copy's
            # metadata gave no indication it was ever copied from
            # anything.
            new_spectrum = {
                'label': new_name,
                'x_scale': spectrum['x_scale'].copy(),
                'y_scale': spectrum['y_scale'].copy(),
                'metadata': {
                    'unique_id': str(uuid.uuid4()),
                    'correction_history': append_correction_history(
                        None, 'Copy', {'source_spectrum': spectrum['label']}
                    ),
                },
            }

            new_spectra.append(new_spectrum)
            existing_labels.add(new_name)

        if not new_spectra:
            return

        # Register in operations history
        if hasattr(self, 'operations_controller'):
            self.operations_controller.register_copy_operation(selected, new_spectra)

        # Append, then sort and rebuild the list widget from scratch —
        # matching the same order_spectra() + rebuild pattern every
        # Add-as-New commit method already uses. Without this, copies
        # were just appended at the end regardless of the selected sort
        # order (Alphabetical / Time created / Time modified), unlike
        # every other "add new spectra" path in the app.
        self.original_spectra.extend(new_spectra)
        self.original_spectra = self.order_spectra(self.original_spectra)

        # Identity (unique_id), not label — a copy's SOURCE spectrum
        # keeps its own identity untouched by this operation, so this is
        # actually safe to match by label too in this one spot, but
        # unique_id is used for consistency with every other selection-
        # restoration site in this file (see spectrum_identity.py).
        source_ids = {spectrum_key(s) for s in selected}
        from PyQt5.QtWidgets import QListWidgetItem
        from PyQt5.QtCore import Qt, QItemSelection, QItemSelectionModel
        self.spectra_list_widget.blockSignals(True)
        try:
            self.spectra_list_widget.clear()
            rows_to_select = []
            for i, spectrum in enumerate(self.original_spectra):
                item = QListWidgetItem(spectrum['label'])
                item.setData(Qt.UserRole, spectrum_id(spectrum))
                item.setFlags(item.flags() | Qt.ItemIsSelectable)
                self.spectra_list_widget.addItem(item)
                # Keep the originals selected, not the new copies —
                # consistent with what every Add-as-New commit does.
                if spectrum_key(spectrum) in source_ids:
                    rows_to_select.append(i)
            # Batch selection — same confirmed anti-pattern fixed
            # elsewhere in this app (Map2D, Peak Fitting, Rename, the
            # main spectra-list rebuild helper): calling
            # item.setSelected(True) once per row in a loop costs real,
            # measurable time at scale (83 of a ~90-second operation at
            # ~4675 items, confirmed by direct profiling) — a large copy
            # batch could hit the same cost here.
            if rows_to_select:
                model = self.spectra_list_widget.model()
                selection = QItemSelection()
                for row in rows_to_select:
                    idx = model.index(row, 0)
                    selection.select(idx, idx)
                self.spectra_list_widget.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
        finally:
            self.spectra_list_widget.blockSignals(False)

        # Update count label and spinbox maximums
        self.spectrum_selector.update_spectra_count_label()
        num = len(self.original_spectra)
        self.view.number_of_rows_spinBox.setMaximum(num)
        self.view.number_of_columns_spinBox.setMaximum(num)

    def add_new_spectra(self, new_spectra, select_new=True):
        """Append newly-created spectra (e.g. resolved NMF/MCR-ALS
        components) to the main spectrum list and rebuild the list widget.

        Generalizes _copy_selected_spectra's extend + order_spectra +
        rebuild pattern for any caller adding genuinely new, computed
        spectra rather than copies of existing ones — e.g. NMFController /
        MCRALSController exporting resolved pure-component spectra, the
        same idea as Peak Fitting's "Add new spectra from individual
        peaks". Unlike the copy case, the newly added spectra are selected
        afterward (select_new=True default) rather than the originals,
        since the point of exporting a result is usually to look at or use
        it immediately.
        """
        if not new_spectra:
            return

        self.original_spectra.extend(new_spectra)
        self.original_spectra = self.order_spectra(self.original_spectra)

        new_ids = {spectrum_key(s) for s in new_spectra}
        from PyQt5.QtWidgets import QListWidgetItem
        from PyQt5.QtCore import Qt
        self.spectra_list_widget.blockSignals(True)
        try:
            self.spectra_list_widget.clear()
            for spectrum in self.original_spectra:
                item = QListWidgetItem(spectrum['label'])
                item.setData(Qt.UserRole, spectrum_id(spectrum))
                item.setFlags(item.flags() | Qt.ItemIsSelectable)
                self.spectra_list_widget.addItem(item)
                if select_new and spectrum_key(spectrum) in new_ids:
                    item.setSelected(True)
        finally:
            self.spectra_list_widget.blockSignals(False)

        self.spectrum_selector.update_spectra_count_label()
        num = len(self.original_spectra)
        self.view.number_of_rows_spinBox.setMaximum(num)
        self.view.number_of_columns_spinBox.setMaximum(num)

    def create_interactive_controls(self):
        layout = QHBoxLayout()
        self.interactive_mode_checkbox = QCheckBox("Interactive Update")
        self.interactive_mode_checkbox.setChecked(True)  # Default to checked
        layout.addWidget(self.interactive_mode_checkbox)
        
        self.refresh_plot_button = QPushButton("Refresh Plot")
        self.refresh_plot_button.setVisible(False)  # Initially hidden since interactive mode is on
        layout.addWidget(self.refresh_plot_button)

        self.legend_properties_button = QPushButton("\u2630 Legend")
        self.legend_properties_button.setToolTip(
            "Show / hide the legend and configure its appearance.\n"
            "Tip: disable the legend when plotting many spectra to improve performance."
        )
        self.legend_properties_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #3A6AAF;"
            "  color: white;"
            "  border: none;"
            "  border-radius: 4px;"
            "  padding: 3px 10px;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover { background-color: #2D5A9E; }"
            "QPushButton:pressed { background-color: #1E4080; }"
        )
        self.legend_properties_button.clicked.connect(
            lambda: self.legend_properties_controller.show_dialog()
        )
        layout.addWidget(self.legend_properties_button)

        # Small ? button — opens the help window at the Interactive Update / Legend section
        self.plot_controls_help_button = QPushButton("?")
        self.plot_controls_help_button.setFixedWidth(24)
        self.plot_controls_help_button.setToolTip(
            "Why use Interactive Update?\nWhen to enable or disable the Legend?"
        )
        self.plot_controls_help_button.setStyleSheet(
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
        self.plot_controls_help_button.clicked.connect(self._show_plot_controls_help)
        layout.addWidget(self.plot_controls_help_button)

        return layout

    def _show_plot_controls_help(self):
        """Open the help window at the Interactive Update / Legend section."""
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'plot_controls')
    
    def create_select_buttons_layout(self):
        layout = QHBoxLayout()
        
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(lambda: self.spectrum_selector.select_all_items())
        layout.addWidget(self.select_all_button)
    
        self.unselect_all_button = QPushButton("Unselect All")
        self.unselect_all_button.clicked.connect(lambda: self.spectrum_selector.unselect_all_items())
        layout.addWidget(self.unselect_all_button)

        self.select_spectra_button = QPushButton("Select spectra")
        self.select_spectra_button.setToolTip(
            "Select spectra by range, pattern, or other criteria"
        )
        self.select_spectra_button.clicked.connect(lambda: self.spectrum_selector.show_spectra_selection_dialog())
        layout.addWidget(self.select_spectra_button)
    
        return layout

    def create_spectra_actions_layout(self):
        """Rename / Show Metadata / Plot Properties — Copy and Delete used
        to be buttons here too, but now that both have keyboard shortcuts
        (Ctrl+C/Ctrl+V for copy, Ctrl+D/Delete for delete — see
        __init__'s shortcut wiring), Show Metadata and Plot Properties
        take their place instead, since those two were previously only
        reachable via the right-click context menu."""
        layout = QHBoxLayout()

        self.rename_spectra_button = QPushButton("Rename")
        self.rename_spectra_button.clicked.connect(lambda: self.spectrum_selector.show_rename_dialog())
        layout.addWidget(self.rename_spectra_button)

        self.metadata_button = QPushButton("Show Metadata")
        self.metadata_button.clicked.connect(lambda: self.spectrum_selector.show_selected_spectrum_metadata())
        layout.addWidget(self.metadata_button)

        # A dropdown button offering all 3 Plot Properties actions from
        # the context menu's own submenu (Show Info / Modify / Reset to
        # default) — a plain QPushButton could only ever trigger one of
        # them, so this uses the same InstantPopup pattern as Map2D's
        # own session menu button: clicking it always shows the menu,
        # there's no separate "main" action vs. "more" arrow to click
        # through first.
        self.plot_properties_button = QToolButton()
        self.plot_properties_button.setText("Plot Properties")
        self.plot_properties_button.setToolTip(
            "Show, modify, or reset plot properties (colour, line style) for the selected spectra."
        )
        self.plot_properties_button.setPopupMode(QToolButton.InstantPopup)
        # Without this, Qt draws the dropdown arrow directly on top of
        # the button's own text instead of reserving space for it —
        # padding-right pushes the text left enough to leave the arrow
        # room of its own.
        self.plot_properties_button.setStyleSheet(
            "QToolButton { padding-right: 18px; } "
            "QToolButton::menu-indicator { subcontrol-position: right center; right: 4px; }"
        )

        plot_properties_menu = QMenu(self.plot_properties_button)
        show_info_action = plot_properties_menu.addAction("Show Info")
        show_info_action.triggered.connect(self._show_plot_properties_info)
        plot_properties_menu.addSeparator()
        modify_action = plot_properties_menu.addAction("Modify")
        modify_action.triggered.connect(lambda: self.custom_plot_properties_controller.show_dialog())
        reset_action = plot_properties_menu.addAction("Reset to default")
        reset_action.triggered.connect(self._reset_selected_plot_properties)
        self.plot_properties_button.setMenu(plot_properties_menu)

        layout.addWidget(self.plot_properties_button)

        return layout

    def _selected_spectra_by_identity(self):
        """Resolve the list widget's current selection to spectrum dicts
        by identity (Qt.UserRole unique_id), not by label text — see
        CustomPlotPropertiesManager's class docstring."""
        selected_ids = {item.data(Qt.UserRole) for item in self.spectra_list_widget.selectedItems()}
        return [
            spectrum for spectrum in self.original_spectra
            if spectrum_key(spectrum) in selected_ids
        ]

    def _show_plot_properties_info(self):
        """Same action as the context menu's Plot Properties -> Show
        Info — computes the current selection fresh at click time,
        rather than capturing a stale list at button-construction time."""
        selected_spectra = self._selected_spectra_by_identity()
        self.custom_plot_properties_manager.show_properties_table(selected_spectra)

    def _reset_selected_plot_properties(self):
        """Same action as the context menu's Plot Properties -> Reset to
        default — see _show_plot_properties_info for why the selection
        is computed fresh here rather than passed in at construction."""
        selected_spectra = self._selected_spectra_by_identity()
        self.custom_plot_properties_manager.reset_selected_properties(selected_spectra)

    def initialize_attributes(self):
        """
        Initialize class attributes.
        """
        self.plotter = None
        self.static_canvas = None
        self.static_toolbar = None
        # Despite the name, this is NOT a frozen copy of the untouched
        # import -- it's the full list of spectra currently in memory,
        # and it gets overwritten as you go (e.g. after running an
        # operation, this holds the PROCESSED result, not the raw data).
        # The actual untouched, never-changed baseline used for undo/redo
        # is operations_manager.original_spectra (see
        # incremental_operations_manager.py) -- a separate attribute that,
        # confusingly, happens to share this same name.
        self.original_spectra = []  # List to store original imported spectra
        self.selected_spectra = []  # List to store currently selected spectra
        
        # Settings for plot appearance
        self.use_automatic_line_colors = True  # Default to enabled
        self.use_default_points = False  # Default to disabled        
    
        # Initialize import settings with defaults (CLEANED UP)
        self.import_settings = {
            'delimiter': None,  # Auto-detect
            'decimal_separator': None,  # Auto-detect
            'header': None,  # Auto-detect
            'zero_padding': 4,
            'analyze_rows': 20,
            'interlaced_format': False
        }        
        self.sg_delta_values = {}  # For storing delta values across different selections (Savitzky-Golay smoothing)
        self.band_marker_manager = BandMarkerManager()
        
    def initialize_ui(self):
        """
        Setup UI elements and layout.
        """
        # Configure the graphics view
        self.graphics_layout = QVBoxLayout(self.view.graphicsView)
        self.graphics_layout.setContentsMargins(0, 0, 0, 0)
        self.view.graphicsView.setLayout(self.graphics_layout)

        # Configure dropdowns and defaults
        self.view.comboBox_plot_type_choice.clear()
        self.view.comboBox_plot_type_choice.addItems(["Single spectrum","Overlay plot","Grid plot","Waterfall plot","Mean ± SD","Difference","Heatmap"])
        self.view.comboBox_plot_type_choice.setCurrentText("Overlay plot")

        self.view.comboBox_linking_x_axes.addItems(["all", "row", "col"])
        self.view.comboBox_linking_x_axes.setCurrentText("all")
        
        self.view.comboBox_linking_y_axes.addItems(["all", "row", "col"])
        self.view.comboBox_linking_y_axes.setCurrentText("all")
        
        # Set automatic line colors checkbox to checked by default
        self.view.automatic_line_colors_checkBox.setChecked(True)
        
        self.use_automatic_line_colors = True  # Default to enabled

        # Set visibility of plot-type-specific controls
        self.toggle_grid_controls(self.view.comboBox_plot_type_choice.currentText() == "Grid plot")
        self.toggle_link_axes_controls(self.view.comboBox_plot_type_choice.currentText() == "Grid plot")
        self.toggle_waterfall_controls(False)
        self.toggle_mean_sd_controls(False)
        self.toggle_difference_controls(False)
        self.toggle_heatmap_controls(False)

        # Band markers button
        self.view.band_markers_btn.clicked.connect(self._show_band_marker_dialog)
        
        # Peak detection settings (these are the default values, you can adjust as needed)
        self.peak_threshold = 0.5
        self.peak_prominence = 0.1
        self.peak_distance = 0.05
        self.peak_detection_mode = "Positive"  # Default to detecting positive peaks
        self.peak_font_size = 10
        self.peak_rotation = 0
        self.peak_decimals = 2
        self.peak_number_format = "fixed"
        self.peak_format_type = "X value only" # "X value only" or "Both"
        self.show_labels = True       
 
        # Initialize grid settings with UI values
        self.grid_settings = {
            'rows': 1,
            'columns': 1
        }
        
        self.view.x_scale_comboBox.addItems(["linear", "log", "symlog", "logit"])
        self.view.x_scale_comboBox.setCurrentText("linear")
        
        self.view.y_scale_comboBox.addItems(["linear", "log", "symlog", "logit"])
        self.view.y_scale_comboBox.setCurrentText("linear")  

        # Add keyboard shortcuts for spectra list widget
        select_all_shortcut = QShortcut(QKeySequence("Ctrl+A"), self.spectra_list_widget)
        select_all_shortcut.activated.connect(self.spectrum_selector.select_all_items)
        
        unselect_all_shortcut = QShortcut(QKeySequence("Ctrl+U"), self.spectra_list_widget)
        unselect_all_shortcut.activated.connect(self.spectrum_selector.unselect_all_items)

        # Ctrl+C / Ctrl+V both trigger Copy Spectra directly. Unlike text,
        # copying a spectrum is a single atomic action — the duplicate is
        # created immediately, with no separate "paste destination" step,
        # so there's no real clipboard state to hold between the two
        # keystrokes. Both are wired to the same action so the shortcut
        # works regardless of which one habit reaches for first.
        copy_spectra_shortcut_c = QShortcut(QKeySequence("Ctrl+C"), self.spectra_list_widget)
        copy_spectra_shortcut_c.activated.connect(self._copy_selected_spectra)

        copy_spectra_shortcut_v = QShortcut(QKeySequence("Ctrl+V"), self.spectra_list_widget)
        copy_spectra_shortcut_v.activated.connect(self._copy_selected_spectra)

        # Ctrl+D and the Delete key both trigger Delete Spectra directly —
        # spectrum_selector.delete_selected_spectra() already asks for
        # confirmation internally (see spectrum_selector_controller.py),
        # so both shortcuts naturally inherit that same confirmation with
        # nothing extra needed here.
        delete_spectra_shortcut_ctrl_d = QShortcut(QKeySequence("Ctrl+D"), self.spectra_list_widget)
        delete_spectra_shortcut_ctrl_d.activated.connect(lambda: self.spectrum_selector.delete_selected_spectra())

        delete_spectra_shortcut_del = QShortcut(QKeySequence("Delete"), self.spectra_list_widget)
        delete_spectra_shortcut_del.activated.connect(lambda: self.spectrum_selector.delete_selected_spectra())

        self._apply_stylesheet()

    def _apply_stylesheet(self):
        """Apply a coherent light academic stylesheet to the entire application."""
        self.view.setStyleSheet("""
            /* ── Main window background ── */
            QMainWindow, QWidget {
                background-color: #F4F5F7;
                color: #1A1A2E;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 9pt;
            }

            /* ── Menu bar ── */
            QMenuBar {
                background-color: #FFFFFF;
                border-bottom: 1px solid #D0D3DA;
                padding: 2px;
            }
            QMenuBar::item:selected {
                background-color: #E3EAF4;
                border-radius: 3px;
            }
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #C8CDD6;
            }
            QMenu::item:selected {
                background-color: #E3EAF4;
            }

            /* ── Group boxes ── */
            QGroupBox {
                background-color: #FFFFFF;
                border: 1px solid #D0D3DA;
                border-radius: 5px;
                margin-top: 8px;
                padding-top: 6px;
                font-weight: bold;
                font-size: 8.5pt;
                color: #3A4A6B;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                left: 8px;
                color: #3A4A6B;
            }

            /* ── Frames ── */
            QFrame[frameShape="4"],
            QFrame[frameShape="5"] {
                border: 1px solid #D0D3DA;
                border-radius: 4px;
                background-color: #FFFFFF;
            }

            /* ── Spectra list ── */
            QListWidget {
                background-color: #FFFFFF;
                border: 1px solid #C8CDD6;
                border-radius: 4px;
                alternate-background-color: #F8F9FB;
                selection-background-color: #4A7FC1;
                selection-color: #FFFFFF;
                outline: none;
            }
            QListWidget::item {
                padding: 2px 4px;
                border-radius: 2px;
            }
            QListWidget::item:hover {
                background-color: #E8EFF8;
            }
            QListWidget::item:selected {
                background-color: #4A7FC1;
                color: #FFFFFF;
            }

            /* ── Buttons ── */
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #B0B8C8;
                border-radius: 4px;
                padding: 3px 10px;
                color: #2C3E6B;
                min-height: 22px;
            }
            QPushButton:hover {
                background-color: #E8EFF8;
                border-color: #7A9CC8;
            }
            QPushButton:pressed {
                background-color: #D0DDF0;
                border-color: #4A7FC1;
            }
            QPushButton:disabled {
                color: #A0A8B8;
                border-color: #D0D3DA;
                background-color: #F0F1F3;
            }

            /* ── Checkboxes ── */
            QCheckBox {
                spacing: 6px;
                color: #2C3E6B;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #B0B8C8;
                border-radius: 3px;
                background-color: #FFFFFF;
            }
            QCheckBox::indicator:checked {
                background-color: #4A7FC1;
                border-color: #3A6AAF;
            }
            QCheckBox::indicator:hover {
                border-color: #7A9CC8;
            }

            /* ── ComboBoxes ── */
            QComboBox {
                background-color: #FFFFFF;
                border: 1px solid #B0B8C8;
                border-radius: 4px;
                padding: 2px 6px;
                color: #2C3E6B;
                min-height: 22px;
            }
            QComboBox:hover {
                border-color: #7A9CC8;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox QAbstractItemView {
                background-color: #FFFFFF;
                border: 1px solid #C8CDD6;
                selection-background-color: #E3EAF4;
                selection-color: #1A1A2E;
            }

            /* ── SpinBoxes ── */
            QSpinBox, QDoubleSpinBox {
                background-color: #FFFFFF;
                border: 1px solid #B0B8C8;
                border-radius: 4px;
                padding: 2px 4px;
                color: #2C3E6B;
            }
            QSpinBox:hover, QDoubleSpinBox:hover {
                border-color: #7A9CC8;
            }

            /* ── Labels ── */
            QLabel {
                color: #2C3E6B;
                background-color: transparent;
            }

            /* ── Scrollbars ── */
            QScrollBar:vertical {
                background: #F0F1F3;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #B0B8C8;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #7A9CC8;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                height: 0px;
            }
            QScrollBar:horizontal {
                background: #F0F1F3;
                height: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal {
                background: #B0B8C8;
                border-radius: 5px;
                min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #7A9CC8;
            }

            /* ── Tab widget ── */
            QTabWidget::pane {
                border: 1px solid #D0D3DA;
                border-radius: 4px;
                background-color: #FFFFFF;
            }
            QTabBar::tab {
                background-color: #ECEEF2;
                border: 1px solid #D0D3DA;
                border-bottom: none;
                border-radius: 4px 4px 0 0;
                padding: 4px 12px;
                color: #3A4A6B;
            }
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #1A1A2E;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background-color: #E3EAF4;
            }

            /* ── Toolbar area ── */
            QToolBar, QToolButton {
                background-color: #F4F5F7;
                border: none;
            }
        """)
        
    def open_external_figure(self):
        """Open the current plot in a new external matplotlib window."""
        create_external_figure(self)        

    def show(self):
        """
        Show the main window.
        """
        self.view.show()        
    def toggle_grid_controls(self, is_visible):
        """Toggle visibility of grid-specific UI controls."""
        self.view.number_of_rows_spinBox.setVisible(is_visible)
        self.view.number_of_columns_spinBox.setVisible(is_visible)
        self.view.number_of_rows_label.setVisible(is_visible)
        self.view.number_of_columns_label.setVisible(is_visible)

    def toggle_link_axes_controls(self, is_visible):
        """Toggle visibility of the Link axes groupbox (relevant only for Grid plot)."""
        self.view.groupBox_link_axes.setVisible(is_visible)

    def toggle_waterfall_controls(self, is_visible):
        """Toggle visibility of waterfall-specific UI controls."""
        self.view.waterfall_offset_spinBox.setVisible(is_visible)
        self.view.waterfall_offset_label.setVisible(is_visible)

    def toggle_mean_sd_controls(self, is_visible):
        """Toggle visibility of Mean ± SD-specific UI controls."""
        self.view.mean_sd_show_individual_checkBox.setVisible(is_visible)

    def toggle_heatmap_controls(self, is_visible):
        """Toggle visibility of Heatmap-specific controls."""
        self.view.heatmap_colormap_comboBox.setVisible(is_visible)
        self.view.heatmap_colormap_label.setVisible(is_visible)
        self.view.heatmap_interpolation_comboBox.setVisible(is_visible)
        self.view.heatmap_interpolation_label.setVisible(is_visible)

    def toggle_difference_controls(self, is_visible):
        """Toggle visibility of Difference plot controls."""
        self.view.difference_reference_label.setVisible(is_visible)
        self.view.difference_reference_comboBox.setVisible(is_visible)
        self.view.difference_show_ref_checkBox.setVisible(is_visible)

    def connect_signals(self):
        """
        Connect UI signals to their respective controller methods.
        """
        # Menu actions
        self.view.actionImport_new.triggered.connect(self.import_controller.execute)
        self.view.actionImport_add.triggered.connect(self.import_controller.execute_add)
        # NOT a direct .connect(self.save_controller.execute): QAction.triggered
        # emits a bool ("checked" state). save_controller.execute(spectra=None)
        # has a parameter in that same position, so PyQt was silently filling
        # `spectra` with that bool on every Save click — False is not None, so
        # `selected_spectra` became `False` (truthy-falsy but not a list)
        # regardless of what was actually selected, which is what broke Save
        # unconditionally. The lambda absorbs the bool so execute() always
        # runs with spectra=None, its intended default (i.e. "use the current
        # selection").
        self.view.actionSave.triggered.connect(lambda checked=False: self.save_controller.execute())
    
        # Connect the menu actions to the WebpageController
        self.view.actionOur_Group.triggered.connect(lambda: self.webpage_controller.open_url("https://www.ibp.cz/cs/vyzkum/oddeleni/biofyzika-nukleovych-kyselin/vyzkum"))
        self.view.actionOur_Institute.triggered.connect(lambda: self.webpage_controller.open_url("https://www.ibp.cz/cs/"))
    
        # Connect help menu signals
        self.connect_help_menu_signals()
    
        # UI signals
        self.view.number_of_rows_spinBox.valueChanged.connect(self.update_grid_layout)
        self.view.number_of_columns_spinBox.valueChanged.connect(self.update_grid_layout)
        self.view.waterfall_offset_spinBox.valueChanged.connect(self.plot_spectra)
        self.view.mean_sd_show_individual_checkBox.stateChanged.connect(self.plot_spectra)
        self.view.heatmap_colormap_comboBox.currentIndexChanged.connect(self.plot_spectra)
        self.view.difference_show_ref_checkBox.stateChanged.connect(self.plot_spectra)
        self.view.heatmap_interpolation_comboBox.currentIndexChanged.connect(self.plot_spectra)
        self.view.difference_reference_comboBox.currentIndexChanged.connect(self.plot_spectra)
        self.view.heatmap_colormap_comboBox.currentIndexChanged.connect(self.plot_spectra)
        self.view.difference_show_ref_checkBox.stateChanged.connect(self.plot_spectra)
        self.view.heatmap_interpolation_comboBox.currentIndexChanged.connect(self.plot_spectra)
        self.view.comboBox_plot_type_choice.currentIndexChanged.connect(self.change_plot_type)
        self.checkBox_reverse_order.stateChanged.connect(self.update_spectra_order_and_redraw_plot)
        self.checkBox_shorten_names.stateChanged.connect(self.toggle_shorten_names)
    
        # Connect the close event
        self.view.closeEvent = self.closeEvent
    
        # Signal to handle spectra import
        self.import_controller.spectra_imported.connect(self.display_imported_spectra)
    
        # Add menu action to toggle spectrum selection
        self.view.actionToggle_Spectrum_Selection = self.view.menuView.addAction("Toggle Spectrum Selection")
        self.view.actionToggle_Spectrum_Selection.triggered.connect(self.spectrum_selector.toggle_selection_widget)
    
        # Connect spectrum list widget
        self.spectra_list_widget.itemChanged.connect(self.spectrum_selector.handle_selection_change)
    
        # Add signals for axis linking checkboxes and comboboxes 
        self.view.link_x_axes_checkBox.stateChanged.connect(self.plot_spectra)
        self.view.link_y_axes_checkBox.stateChanged.connect(self.plot_spectra)
        self.view.comboBox_linking_x_axes.currentIndexChanged.connect(self.plot_spectra)
        self.view.comboBox_linking_y_axes.currentIndexChanged.connect(self.plot_spectra)
    
        # Connect spectrum list widget selection change for single spectrum mode
        self.spectra_list_widget.itemSelectionChanged.connect(self.handle_single_spectrum_selection)
        
        # refresh plot
        self.refresh_plot_button.clicked.connect(self.spectrum_selector.plot_selected_spectra)
    
        self.view.x_scale_comboBox.currentIndexChanged.connect(self.plot_spectra)
        self.view.y_scale_comboBox.currentIndexChanged.connect(self.plot_spectra)
        
        self.view.automatic_line_colors_checkBox.stateChanged.connect(self.toggle_automatic_line_colors)
        
        # NOTE: QPushButton.clicked emits a bool 'checked' argument. Connecting
        # it directly to run_visualization_analysis(method_name=None) would pass
        # that bool as method_name, breaking the dispatch (method_name becomes
        # False instead of staying None). The lambda discards it explicitly.
        self.view.run_visualization_pushButton.clicked.connect(
            lambda: self.run_visualization_analysis())
        self.connect_analysis_visualization_menu_signals()
        self.connect_spectra_processing_menu_signals()

    def connect_spectra_processing_menu_signals(self):
        """Wire the main-menu 'Spectra processing' actions to the same
        dispatch logic used by the Spectra Processing groupbox — an
        alternative way to open any operation's settings dialog directly,
        bypassing the dropdown, the same way the Analysis & Visualization
        menu already does for its own groupbox."""
        oc = self.operations_controller
        # Baseline Correction
        self.view.actionMenuOpsManualBaseline.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Manual baseline"))
        self.view.actionMenuOpsAutomatedBaseline.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Automated Baseline"))
        self.view.actionMenuOpsSNIPBaseline.triggered.connect(
            lambda: oc.show_parameters_dialog_for("SNIP Baseline"))
        self.view.actionMenuOpsSVDBackground.triggered.connect(
            lambda: oc.show_parameters_dialog_for("SVD background"))
        # Smoothing
        self.view.actionMenuOpsSGSmoothing.triggered.connect(
            lambda: oc.show_parameters_dialog_for("SG-smoothing"))
        self.view.actionMenuOpsFFTDenoising.triggered.connect(
            lambda: oc.show_parameters_dialog_for("FFT Denoising"))
        # Data Manipulation
        self.view.actionMenuOpsDataRange.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Data range"))
        self.view.actionMenuOpsCombineSpectra.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Combine Spectra"))
        self.view.actionMenuOpsSpectralCalculator.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Spectral Calculator"))
        self.view.actionMenuOpsInteractiveSubtraction.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Interactive subtraction"))
        self.view.actionMenuOpsNormalization.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Normalization"))
        self.view.actionMenuOpsXAxisAlignment.triggered.connect(
            lambda: oc.show_parameters_dialog_for("X-axis alignment"))
        self.view.actionMenuOpsSVDInterpolation.triggered.connect(
            lambda: oc.show_parameters_dialog_for("SVD Interpolation"))
        self.view.actionMenuOpsCDUnitConversion.triggered.connect(
            lambda: oc.show_parameters_dialog_for("CD Unit Conversion"))
        self.view.actionMenuOpsXAxisUnitConversion.triggered.connect(
            lambda: oc.show_parameters_dialog_for("X-axis Unit Conversion"))
        self.view.actionMenuOpsMeanCentering.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Mean-Center Spectra (Dataset)"))
        # Batch Pipeline
        self.view.actionMenuOpsRunBatchPipeline.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Run Batch Pipeline"))
        self.view.actionMenuOpsSaveBatchPipeline.triggered.connect(
            self.show_save_batch_pipeline_dialog)
        # Spike Removal
        self.view.actionMenuOpsSpikeRemoval.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Spike removal"))
        self.view.actionMenuOpsCosmicRayRemoval.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Cosmic ray removal"))
        # Resolution
        self.view.actionMenuOpsResolutionEnhancement.triggered.connect(
            lambda: oc.show_parameters_dialog_for("Resolution enhancement"))

    def connect_analysis_visualization_menu_signals(self):
        """Wire the main-menu 'Analysis && Visualization' actions to the same
        dispatch logic used by the Spectra Analysis & Visualization groupbox."""
        self.view.actionMenuSVDAnalysis.triggered.connect(
            lambda: self.run_visualization_analysis("SVD analysis"))
        self.view.actionMenuPCAScores.triggered.connect(
            lambda: self.run_visualization_analysis("PCA Scores & Loadings"))
        self.view.actionMenuNMF.triggered.connect(
            lambda: self.run_visualization_analysis("NMF"))
        self.view.actionMenuMCRALS.triggered.connect(
            lambda: self.run_visualization_analysis("MCR-ALS"))
        self.view.actionMenuClusterAnalysis.triggered.connect(
            lambda: self.run_visualization_analysis("Cluster analysis"))
        self.view.actionMenuPLS.triggered.connect(
            lambda: self.run_visualization_analysis("PLS / PLS-DA"))
        self.view.actionMenu2DMap.triggered.connect(
            lambda: self.run_visualization_analysis("2D map"))
        self.view.actionMenu2DCorrelation.triggered.connect(
            lambda: self.run_visualization_analysis("2D Correlation"))
        self.view.actionMenuPeakFitting.triggered.connect(
            lambda: self.run_visualization_analysis("Peak Fitting"))
        self.view.actionMenuBandRatio.triggered.connect(
            lambda: self.run_visualization_analysis("Band Ratio"))
        self.view.actionMenuReferenceMatching.triggered.connect(
            lambda: self.run_visualization_analysis("Reference Matching"))
        self.view.actionMenuMeltingCurve.triggered.connect(
            lambda: self.run_visualization_analysis("Melting Curve Analysis"))
        self.view.actionMenuIsosbesticPoint.triggered.connect(
            lambda: self.run_visualization_analysis("Isosbestic Point Detection"))
        self.view.actionMenuKineticsFitting.triggered.connect(
            lambda: self.run_visualization_analysis("Kinetics Fitting"))
        self.view.actionMenuQCOutlier.triggered.connect(
            lambda: self.run_visualization_analysis("QC / Outlier Detection"))
        self.view.actionMenuSOM.triggered.connect(
            lambda: self.run_visualization_analysis("SOM"))

    def run_visualization_analysis(self, method_name=None):
        """
        Run the selected method from the Spectra Analysis & Visualisation groupbox,
        or — if method_name is given — from the main menu 'Analysis && Visualization'.
        Both paths converge here so behaviour is always identical.
        """
        raw = method_name if method_name is not None else \
            self.view.visualization_method_comboBox.currentText().strip()
        selected_spectra = self.spectrum_selector.get_selected_spectra()

        if not selected_spectra:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self.view, "No Spectra Selected",
                                "Please select one or more spectra.")
            return

        # Data Analysis items — route through operations_controller
        if raw in ("Peak Fitting", "Band Ratio", "Reference Matching", "Melting Curve Analysis",
                   "Isosbestic Point Detection"):
            self.operations_controller.show_parameters_dialog_for(raw, selected_spectra)
            return

        # Visualisation items — existing path
        if raw == "2D map":
            self.map2d_controller.show_dialog()
        elif raw == "PCA Scores & Loadings":
            self.pca_scores_controller.show_dialog()
        elif raw == "NMF":
            self.nmf_controller.show_dialog(selected_spectra)
        elif raw == "MCR-ALS":
            self.mcr_als_controller.show_dialog(selected_spectra)
        elif raw == "2D Correlation":
            self.two_d_correlation_controller.show_dialog()
        else:
            # Covers SVD analysis, Cluster analysis, and any other method
            # dispatched generically below — these run their computation
            # synchronously before showing results, so a wait cursor gives
            # visible feedback instead of an apparently-frozen UI while
            # processing a large number of spectra.
            #
            # The common-x-axis check runs FIRST, BEFORE the wait cursor is set.
            # These methods stack the spectra into one matrix, so they already
            # refuse when the axes differ — but the refusal used to happen inside
            # the wrapped call, i.e. while the wait cursor was active, so the
            # warning box appeared with a spinning "busy" cursor over it, as if
            # something were still being computed. Nothing is: the method never
            # started. Validating up front means the warning is shown with a
            # normal cursor, and the wait cursor is only ever set when work is
            # genuinely about to happen.
            if not validate_common_x_axis(selected_spectra, self.view, raw):
                return

            QApplication.setOverrideCursor(Qt.WaitCursor)
            QApplication.processEvents()
            try:
                self.visualization_analysis_controller.run_visualization_analysis(raw)
            finally:
                QApplication.restoreOverrideCursor()


    def connect_help_menu_signals(self):
        """Connect help menu signals to their handlers."""
        
        # Connect operations help actions
        self.view.actionDataRangeHelp.triggered.connect(self.show_data_range_help)
        self.view.actionNormalizationHelp.triggered.connect(self.show_normalization_help)
        self.view.actionSVDInterpolationHelp.triggered.connect(self.show_svd_interpolation_help)
        self.view.actionSGSmoothingHelp.triggered.connect(self.show_sg_smoothing_help)
        self.view.actionManualBaselineHelp.triggered.connect(self.show_manual_baseline_help)
        self.view.actionSVDBackgroundHelp.triggered.connect(self.show_svd_background_help)
        self.view.actionUserGuide.triggered.connect(self.show_user_guide_help)
        self.view.actionQuickStart.triggered.connect(self.show_quick_start_help)
        self.view.actionInstallationHelp.triggered.connect(self.show_installation_help)
        self.view.actionDeveloperGuide.triggered.connect(self.show_developer_guide_help)
        self.view.actionLicense.triggered.connect(self.show_license_help)
        self.view.help_operations_pushButton.clicked.connect(self.show_user_guide_help)
        self.view.actionInteractiveSubtractionHelp.triggered.connect(self.show_interactive_subtraction_help)
        self.view.actionCombineSpectraHelp.triggered.connect(self.show_combine_spectra_help)
        self.view.actionAutomatedBaselineHelp.triggered.connect(self.show_automated_baseline_help)
        self.view.actionSNIPBaselineHelp.triggered.connect(self.show_snip_baseline_help)
        self.view.actionBandRatioHelp.triggered.connect(self.show_band_ratio_help)
        self.view.actionFFTDenoisingHelp.triggered.connect(self.show_fft_denoising_help)
        self.view.actionXAxisAlignmentHelp.triggered.connect(self.show_x_axis_alignment_help)
        self.view.actionCDUnitConversionHelp.triggered.connect(self.show_cd_unit_conversion_help)
        self.view.actionXAxisUnitConversionHelp.triggered.connect(self.show_xaxis_unit_conversion_help)
        self.view.actionMeanCenteringHelp.triggered.connect(self.show_mean_centering_help)
        self.view.actionBatchPipelineHelp.triggered.connect(self.show_batch_pipeline_help)
        self.view.actionSpectralCalculatorHelp.triggered.connect(self.show_spectral_calculator_help)
        self.view.actionReferenceMatchingHelp.triggered.connect(self.show_reference_matching_help)
        self.view.actionReferenceMatchingHelpViz.triggered.connect(self.show_reference_matching_help)
        self.view.actionPcaScoresHelp.triggered.connect(self.show_pca_scores_help)
        self.view.actionNMFHelp.triggered.connect(self.show_nmf_help)
        self.view.actionMCRALSHelp.triggered.connect(self.show_mcr_als_help)
        self.view.actionCosmicRayHelp.triggered.connect(self.show_cosmic_ray_help)
        self.view.actionResolutionHelp.triggered.connect(self.show_resolution_help)
        self.view.actionPeakFittingHelp.triggered.connect(self.show_peak_fitting_help)
        self.view.actionMeltingCurveHelp.triggered.connect(self.show_melting_curve_help)
        self.view.actionIsosbesticPointHelp.triggered.connect(self.show_isosbestic_point_help)
        self.view.actionKineticsFittingHelp.triggered.connect(self.show_kinetics_fitting_help)
        self.view.actionQCOutlierHelp.triggered.connect(self.show_qc_outlier_help)
        self.view.actionSpikeRemovalHelp.triggered.connect(self.show_spike_removal_help)
        self.view.actionSVDAnalysisHelp.triggered.connect(self.show_svd_analysis_help)
        self.view.actionClusterAnalysisHelp.triggered.connect(self.show_cluster_analysis_help)
        self.view.actionSOMHelp.triggered.connect(self.show_som_help)
        self.view.action2DMapHelp.triggered.connect(self.show_2d_map_help)
        self.view.action2DCorrelationHelp.triggered.connect(self.show_2d_correlation_help)
        self.view.actionPLSHelp.triggered.connect(self.show_pls_help)

        # Test datasets → Synthetic. Each action opens one shipped benchmark
        # workbook straight into the app (see open_synthetic_dataset).
        for _fname, _action in getattr(self.view, 'synthetic_dataset_actions', {}).items():
            _action.triggered.connect(
                lambda _checked=False, fn=_fname: self.open_synthetic_dataset(fn))
        if hasattr(self.view, 'actionOpenSyntheticFolder'):
            self.view.actionOpenSyntheticFolder.triggered.connect(
                self.open_synthetic_datasets_folder)
        for _fname, _action in getattr(self.view, 'real_dataset_actions', {}).items():
            _action.triggered.connect(
                lambda _checked=False, fn=_fname: self.open_real_dataset(fn))
        if hasattr(self.view, 'actionOpenRealFolder'):
            self.view.actionOpenRealFolder.triggered.connect(
                self.open_real_datasets_folder)
        if hasattr(self.view, 'actionDownloadLargeDatasets'):
            self.view.actionDownloadLargeDatasets.triggered.connect(
                self.open_large_dataset_downloader)

    # ------------------------------------------------------------------
    # Synthetic test datasets  (Help → Spectra Analysis & Visualization →
    # Test datasets → Synthetic)
    # ------------------------------------------------------------------

    def _test_datasets_dir(self, kind='synthetic'):
        """<app root>/resources/test_data/<kind>/  (kind: 'synthetic' | 'real')."""
        import sys, os
        base = getattr(sys, '_MEIPASS', None)
        if base is None:
            base = os.path.abspath(os.path.join(
                os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
        return os.path.join(base, 'resources', 'test_data', kind)

    def open_real_dataset(self, filename):
        """Open one shipped MEASURED dataset. Unlike the synthetic ones, real
        data has no known ground truth to check the analysis against.

        filename may be a forward-slash relative path (e.g. entries under
        REAL_TEST_DATASETS_2D_MAPS look like '2D map/Chlorella.mat') — split
        on '/' rather than os.path.join()-ing the whole string directly, so
        this resolves correctly on Windows too.
        """
        import os
        from PyQt5.QtWidgets import QMessageBox
        path = os.path.join(self._test_datasets_dir('real'), *filename.split('/'))
        if not os.path.exists(path):
            QMessageBox.warning(self.view, 'Test dataset not found',
                                f'Could not find:\n{path}')
            return
        try:
            self.import_controller.execute_paths([path])
        except Exception as e:
            logger.exception('Failed to open real test dataset:')
            QMessageBox.critical(self.view, 'Error', f'Could not open {filename}:\n{e}')

    def open_real_datasets_folder(self):
        self._reveal_folder(self._test_datasets_dir('real'))

    def open_large_dataset_downloader(self):
        """Open the dialog for fetching real-data 2D maps too large to
        ship in the git repository, hosted as GitHub Release assets
        instead (see LARGE_TEST_DATASETS in main_window.py)."""
        from src.views.main_window import (
            LARGE_TEST_DATASETS, LARGE_TEST_DATASETS_OWNER_REPO,
            LARGE_TEST_DATASETS_RELEASE_TAG,
        )
        from src.views.dialogs.misc.dataset_download_dialog import DatasetDownloadDialog

        base_url = (
            f"https://github.com/{LARGE_TEST_DATASETS_OWNER_REPO}"
            f"/releases/download/{LARGE_TEST_DATASETS_RELEASE_TAG}"
        )
        dlg = DatasetDownloadDialog(
            self.view, LARGE_TEST_DATASETS, self._test_datasets_dir('real'), base_url)
        dlg.exec_()

    def _reveal_folder(self, folder):
        import os
        from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl
        if not os.path.isdir(folder):
            QMessageBox.warning(self.view, 'Folder not found',
                                f'Could not find:\n{folder}')
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _synthetic_datasets_dir(self):
        """Folder holding the shipped synthetic benchmark workbooks:
        <app root>/resources/test_data/synthetic/. Resolved relative to this
        source file so it works when run from source, and via sys._MEIPASS
        when running from a PyInstaller bundle (where resources/ is unpacked
        into the temporary bundle dir)."""
        import sys, os
        base = getattr(sys, '_MEIPASS', None)
        if base is None:
            # src/controllers/core/main_controller.py -> up three levels
            base = os.path.abspath(os.path.join(
                os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
        return os.path.join(base, 'resources', 'test_data', 'synthetic')

    def open_synthetic_dataset(self, filename):
        """Open one shipped synthetic dataset in the application.

        The workbook's first sheet is 'Spectra' (the mixture spectra); the
        importer's default sheet selection already picks that one up. The
        remaining sheets (Pure_components / Concentrations / Ground_truth /
        Info) hold the known truth to compare the analysis against — open the
        file in Excel to see them.

        The file is routed through the normal Import dialog (pre-filled with
        this path) rather than being loaded silently, so the user sees, and can
        adjust, exactly the same import settings as for any other file — and
        so it ADDS to the current spectra rather than silently discarding them.
        """
        import os
        from PyQt5.QtWidgets import QMessageBox
        path = os.path.join(self._synthetic_datasets_dir(), filename)
        if not os.path.exists(path):
            QMessageBox.warning(
                self.view, 'Test dataset not found',
                f'Could not find:\n{path}\n\n'
                'The synthetic test datasets should live in\n'
                'resources/test_data/synthetic/ inside the application folder.')
            return
        try:
            # execute_paths asks Add-or-Replace first (only when spectra are
            # already loaded), so opening a test dataset offers the same choice
            # as File → Import data → add / new.
            self.import_controller.execute_paths([path])
        except Exception as e:
            logger.exception('Failed to open synthetic test dataset:')
            QMessageBox.critical(self.view, 'Error',
                                 f'Could not open {filename}:\n{e}')

    def open_synthetic_datasets_folder(self):
        """Reveal the synthetic-datasets folder in the OS file manager, so the
        ground-truth sheets and the README are easy to get at."""
        import os
        from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl
        folder = self._synthetic_datasets_dir()
        if not os.path.isdir(folder):
            QMessageBox.warning(
                self.view, 'Folder not found',
                f'Could not find:\n{folder}')
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def show_peak_fitting_help(self):
        """Show help for peak fitting operation."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'peak_fitting')

    def show_melting_curve_help(self):
        """Show help for melting curve analysis operation."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'melting_curve')

    def show_isosbestic_point_help(self):
        """Show help for Isosbestic/Isodichroic Point Detection."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'isosbestic_point')

    def show_kinetics_fitting_help(self):
        """Show help for Kinetics Fitting."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'kinetics_fitting')

    def show_qc_outlier_help(self):
        """Show help for QC / Outlier Detection."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'qc_outlier')

    def show_spike_removal_help(self):
        """Show help for spike removal."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'spike_removal')

    def _show_band_marker_dialog(self):
        """Open the Band Marker Manager dialog."""
        if not hasattr(self, 'band_marker_controller'):
            from src.controllers.visualization.band_marker_controller import (
                BandMarkerController)
            self.band_marker_controller = BandMarkerController(self)
        self.band_marker_controller.show_dialog()

    def show_resolution_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'resolution')

    def show_fft_denoising_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'fft_denoising')

    def show_x_axis_alignment_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'xaxis_alignment')

    def show_cd_unit_conversion_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'cd_unit_conversion')

    def show_xaxis_unit_conversion_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'xaxis_unit_conversion')

    def show_mean_centering_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'mean_centering')

    def show_batch_pipeline_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'batch_pipeline')

    def show_save_batch_pipeline_dialog(self):
        """Menu-bar entry point for "Save as Pipeline..." — the same
        action also reachable from the Operations History dialog's own
        button (see operations_summary_dialog.py), offered here too so
        it doesn't require opening Operations History first."""
        if not hasattr(self, 'batch_pipeline_controller'):
            from src.controllers.data_analysis.batch_pipeline_controller import BatchPipelineController
            self.batch_pipeline_controller = BatchPipelineController(self)
        self.batch_pipeline_controller.show_save_dialog(
            operations_manager=self.operations_controller.operations_manager)

    def show_svd_interpolation_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'svd_interpolation')

    def show_spectral_calculator_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'spectral_calculator')

    def show_cosmic_ray_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'cosmic_ray')

    def show_nmf_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'nmf')

    def show_mcr_als_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'mcr_als')

    def show_pca_scores_help(self):
        """Show help for PCA Scores & Loadings."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'pca_scores')

    def show_svd_analysis_help(self):
        """Show help for SVD analysis."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'svd_analysis')

    def show_cluster_analysis_help(self):
        """Show help for cluster analysis."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'cluster_analysis')

    def show_som_help(self):
        """Show help for SOM (Self-Organizing Map) analysis."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'som')

    def show_pls_help(self):
        """Show help for PLS / PLS-DA."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'pls')

    def show_automated_baseline_help(self):
        """Show help for automated baseline correction."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'automated_baseline')

    def show_reference_matching_help(self):
        """Show help for Reference Library Matching."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'reference_matching')

    def show_band_ratio_help(self):
        """Show help for Band Ratio / Peak Area Calculator."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'band_ratio')

    def show_snip_baseline_help(self):
        """Show help for SNIP baseline correction."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'snip_baseline')

    def show_combine_spectra_help(self):
        """Show help for spectral arithmetic operation."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'combine_spectra')

    def show_user_guide_help(self):
        """Show comprehensive user guide."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'user_guide')

    def show_quick_start_help(self):
        """Show the short single-page Quick Start orientation — basic
        workflow, import, every processing/analysis operation's help
        linked from one table, save, test datasets, contact."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'quick_start')

    def show_installation_help(self):
        """Show the Installation page — how to get/run the application
        itself (installer, from source, building your own installer)."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'installation')

    def show_developer_guide_help(self):
        """Show the developer guide: codebase architecture and conventions
        for anyone reading or extending the source."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'developer_guide')

    def show_license_help(self):
        """Show the License page: GPL-3.0 summary and links to the formal
        LICENSE file, the installer's plain-language license.txt, and the
        Developer Guide's licensing-intent section."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'license')

    def show_data_range_help(self):
        """Show help for data range operation."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'data_range')

    def show_normalization_help(self):
        """Show help for normalization operation."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'normalization')

    def show_sg_smoothing_help(self):
        """Show help for SG-smoothing operation."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'sg_smoothing')

    def show_manual_baseline_help(self):
        """Show help for manual baseline correction operation."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'manual_baseline')

    def show_svd_background_help(self):
        """Show help for SVD background correction operation."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'svd_background')

    def show_interactive_subtraction_help(self):
        """Show help for interactive subtraction operation."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'interactive_subtraction')

    def show_2d_map_help(self):
        """Show help for the 2D Map tool."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'map2d')

    def show_2d_correlation_help(self):
        """Show help for 2D Correlation."""
        from src.help.help_window import open_help_topic
        open_help_topic(self.view, 'two_d_correlation')
        
    def toggle_automatic_line_colors(self, state):
        """
        Toggle the automatic line colors feature based on checkbox state.
        """
        self.use_automatic_line_colors = (state == Qt.Checked)
        self.plot_spectra()  # Redraw with the new setting        

    def handle_single_spectrum_selection(self):
        """
        Handle spectrum selection changes specifically for Single spectrum mode.
        """
        plot_type = self.view.comboBox_plot_type_choice.currentText()
        
        # Only plot if in Single spectrum mode
        if plot_type == "Single spectrum":
            self.plot_spectra()

    def change_plot_type(self):
        """
        Handles changes to the plot type selection and updates the UI accordingly.
        """
        plot_type = self.view.comboBox_plot_type_choice.currentText()
        is_single_spectrum_mode = (plot_type == "Single spectrum")

        # Update selection mode
        if not is_single_spectrum_mode:
            self.spectra_list_widget.setSelectionMode(QListWidget.MultiSelection)
        else:
            self.spectra_list_widget.setSelectionMode(QListWidget.SingleSelection)
            # Switching to Single spectrum mode should show exactly one
            # spectrum, not whatever multi-selection was active before —
            # setSelectionMode() alone doesn't retroactively trim an
            # existing multi-selection, so do it explicitly: clear it and
            # select the first item instead.
            self.spectra_list_widget.clearSelection()
            if self.spectra_list_widget.count() > 0:
                first_item = self.spectra_list_widget.item(0)
                self.spectra_list_widget.setCurrentItem(first_item)
                first_item.setSelected(True)
        
        # Toggle plot-type-specific controls
        self.toggle_grid_controls(plot_type == "Grid plot")
        self.toggle_link_axes_controls(plot_type == "Grid plot")
        self.toggle_waterfall_controls(plot_type == "Waterfall plot")
        self.toggle_mean_sd_controls(plot_type == "Mean ± SD")
        self.toggle_difference_controls(plot_type == "Difference")
        self.toggle_heatmap_controls(plot_type == "Heatmap")
        if plot_type == "Difference":
            self._update_difference_reference_combobox()
        
        # Plot the spectra
        self.plot_spectra()

    def update_grid_layout(self):
        """
        Updates the grid plot layout dynamically when the spinbox values change.
        """
        
        # Store the new values in grid_settings
        self.grid_settings['rows'] = self.view.number_of_rows_spinBox.value()
        self.grid_settings['columns'] = self.view.number_of_columns_spinBox.value()
        
        # if self.interactive_mode_checkbox.isChecked():
        #     self.plot_spectra()
        self.plot_spectra()

    def clear_graphics_view(self):
        """
        Clears all widgets from the graphics view layout.
        """
        for i in reversed(range(self.graphics_layout.count())):
            widget = self.graphics_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)

    def import_spectra(self):
        """
        Prepare the spectra data, extracting relevant information and storing it in self.original_spectra.
        Uses global import settings when loading spectra.
        """
        
        # Get the current import settings
        settings = self.import_settings
        
        # Pass the settings to the spectrum manager for loading (CLEANED UP - removed legacy parameters)
        self.import_controller.spectrum_manager.current_settings = {
            'delimiter': settings['delimiter'],
            'decimal_separator': settings['decimal_separator'],
            'header': settings['header'],
            'zero_padding': settings['zero_padding'],
            'analyze_rows': settings['analyze_rows'],
            'interlaced_format': settings['interlaced_format']
        }
    
        spectrum_names = list(self.import_controller.spectrum_manager.spectra.keys())
        logger.debug("import_spectra: Found %d spectrum names", len(spectrum_names))
    
        spectra = []
        for name in spectrum_names:
            spectrum = self.import_controller.spectrum_manager.get_spectrum(name)
            if spectrum is None:
                logger.warning("import_spectra: spectrum %r is None", name)
                continue
                
            x_scale = spectrum.x_scale
            label = name
    
            spectra.append({
                'x_scale': x_scale,
                'y_scale': spectrum.y_scale,
                'label': label,
                'metadata': spectrum.metadata
            })
            # logger.debug("import_spectra: Added spectrum %r with %d points", label, len(x_scale))
    
        logger.debug("import_spectra: Returning %d spectra", len(spectra))
        return spectra

    def _update_difference_reference_combobox(self):
        """Populate the difference reference combobox with currently selected spectrum labels."""
        cb = self.view.difference_reference_comboBox
        cb.blockSignals(True)
        current = cb.currentText()
        cb.clear()
        cb.addItem("Mean")
        for s in (self.selected_spectra or self.original_spectra):
            cb.addItem(s["label"])
        # Restore previous selection if still valid
        idx = cb.findText(current)
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        cb.blockSignals(False)

    def plot_spectra(self, progress_callback=None):
        """
        Handles the actual plotting of spectra for both grid, overlay, and single spectrum plot types.
        Shows a wait cursor for the duration so the user knows rendering is in progress.

        progress_callback: optional callable, passed straight through to
        overlay_plot_mode/grid_plot_mode — see that function's own
        docstring. A caller showing a progress dialog around a call to
        plot_spectra() (e.g. after a batch operation on thousands of
        spectra) can pass e.g. `lambda: QApplication.processEvents()` here
        so the dialog's busy animation actually animates while this runs,
        instead of the Qt event loop being frozen for the whole duration of
        this one call. None (the default) — ordinary calls to
        plot_spectra() elsewhere in the app don't need this and are
        unaffected.
        """
        if not self.selected_spectra:
            self.clear_graphics_view()
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()  # make the cursor change visible immediately
        try:
            self._plot_spectra_impl(progress_callback=progress_callback)
        finally:
            QApplication.restoreOverrideCursor()

    def _plot_spectra_impl(self, progress_callback=None):
        """Internal plotting implementation — always called via plot_spectra()."""
        # Get current scale settings
        x_scale = self.view.x_scale_comboBox.currentText()
        y_scale = self.view.y_scale_comboBox.currentText()
    
        self.clear_graphics_view()
        plot_widget = QWidget()
        plot_type = self.view.comboBox_plot_type_choice.currentText()
        self.toggle_grid_controls(plot_type == "Grid plot")
        self.toggle_link_axes_controls(plot_type == "Grid plot")
        if plot_type == "Difference":
            self._update_difference_reference_combobox()
    
        # Create a copy of selected spectra to avoid modifying original data
        plot_spectra = self.selected_spectra.copy()
        
        plot_settings = self.custom_plot_properties_manager.spectrum_properties
        use_automatic_line_colors = self.use_automatic_line_colors
        use_default_points = self.use_default_points

        # Legend text only — mirrors the main spectra list's "shorten
        # names" checkbox (see label_shortening.py). Everything else
        # (plot_settings lookups, difference-plot reference matching,
        # the underlying spectrum dicts) still uses full/original labels.
        display_labels = shorten_spectra_labels(
            plot_spectra, self.checkBox_shorten_names.isChecked()
        )

        if plot_type == "Grid plot":

            # Use the stored grid settings
            nrows = self.grid_settings['rows']
            ncols = self.grid_settings['columns']

            # nrows = self.view.number_of_rows_spinBox.value()
            # ncols = self.view.number_of_columns_spinBox.value()
    
            if self.view.link_x_axes_checkBox.isChecked():
                link_x_axes_direction = self.view.comboBox_linking_x_axes.currentText()
            else:
                link_x_axes_direction = "none"
    
            if self.view.link_y_axes_checkBox.isChecked():
                link_y_axes_direction = self.view.comboBox_linking_y_axes.currentText()
            else:
                link_y_axes_direction = "none"           
    
            self.static_canvas, self.static_toolbar = grid_plot_mode(plot_widget,
                                                                     plot_spectra,
                                                                     nrows=nrows,
                                                                     ncols=ncols,
                                                                     link_x_axes_direction = link_x_axes_direction,
                                                                     link_y_axes_direction = link_y_axes_direction,
                                                                     plot_settings = plot_settings, 
                                                                     use_automatic_line_colors = use_automatic_line_colors,
                                                                     use_default_points = use_default_points,
                                                                     x_scale=x_scale,
                                                                     y_scale=y_scale,
                                                                     grid_manager=self.grid_manager,
                                                                     legend_manager=self.legend_manager,
                                                                     axis_manager=self.axis_manager,
                                                                     constrained_layout_manager=self.constrained_layout_manager,
                                                                     band_marker_manager=self.band_marker_manager,
                                                                     progress_callback=progress_callback,
                                                                     display_labels=display_labels,
            )

        elif plot_type == "Overlay plot":
            self.static_canvas, self.static_toolbar = overlay_plot_mode(plot_widget,
                                                                        plot_spectra,
                                                                        plot_settings = plot_settings,
                                                                        use_automatic_line_colors = use_automatic_line_colors,
                                                                        use_default_points = use_default_points,
                                                                        x_scale=x_scale,
                                                                        y_scale=y_scale,
                                                                        grid_manager=self.grid_manager,
                                                                        legend_manager=self.legend_manager,
                                                                        axis_manager=self.axis_manager,
                                                                        constrained_layout_manager=self.constrained_layout_manager,
                                                                        band_marker_manager=self.band_marker_manager,
                                                                        progress_callback=progress_callback,
                                                                        display_labels=display_labels,
                                                                        )
    
        elif plot_type == "Waterfall plot":
            offset = self.view.waterfall_offset_spinBox.value()  # 0 = auto
            self.static_canvas, self.static_toolbar = waterfall_plot_mode(
                plot_widget,
                plot_spectra,
                offset=offset if offset > 0 else None,
                plot_settings=plot_settings,
                use_automatic_line_colors=use_automatic_line_colors,
                x_scale=x_scale,
                y_scale=y_scale,
                legend_manager=self.legend_manager,
                axis_manager=self.axis_manager,
                band_marker_manager=self.band_marker_manager,
                display_labels=display_labels,
            )

        elif plot_type == "Mean ± SD":
            show_individual = self.view.mean_sd_show_individual_checkBox.isChecked()
            self.static_canvas, self.static_toolbar = mean_sd_plot_mode(
                plot_widget,
                plot_spectra,
                show_individual=show_individual,
                plot_settings=plot_settings,
                use_automatic_line_colors=use_automatic_line_colors,
                x_scale=x_scale,
                y_scale=y_scale,
                legend_manager=self.legend_manager,
                axis_manager=self.axis_manager,
                band_marker_manager=self.band_marker_manager,
            )

        elif plot_type == "Difference":
            ref_label = self.view.difference_reference_comboBox.currentText()
            hide_ref  = not self.view.difference_show_ref_checkBox.isChecked()
            self.static_canvas, self.static_toolbar = difference_plot_mode(
                plot_widget,
                plot_spectra,
                ref_label=ref_label,
                hide_reference=hide_ref,
                plot_settings=plot_settings,
                use_automatic_line_colors=use_automatic_line_colors,
                x_scale=x_scale,
                y_scale=y_scale,
                legend_manager=self.legend_manager,
                axis_manager=self.axis_manager,
                band_marker_manager=self.band_marker_manager,
                display_labels=display_labels,
            )

        elif plot_type == "Heatmap":
            colormap       = self.view.heatmap_colormap_comboBox.currentText()
            interpolation  = self.view.heatmap_interpolation_comboBox.currentText()
            self.static_canvas, self.static_toolbar = heatmap_plot_mode(
                plot_widget,
                plot_spectra,
                colormap=colormap,
                interpolation=interpolation,
                legend_manager=self.legend_manager,
                axis_manager=self.axis_manager,
                band_marker_manager=self.band_marker_manager,
                display_labels=display_labels,
            )

        elif plot_type == "Single spectrum":
            # Ensure only one spectrum is selected in single spectrum mode
            selected_items = self.spectra_list_widget.selectedItems()
            if selected_items:
                # Get the index of the selected item
                selected_index = self.spectra_list_widget.row(selected_items[0])
                
                # Create a list with just the single selected spectrum
                single_spectrum = [self.original_spectra[selected_index]]

                # Plot the single spectrum
                self.static_canvas, self.static_toolbar = overlay_plot_mode(plot_widget,
                                                                            single_spectrum,
                                                                            plot_settings = plot_settings,
                                                                            use_automatic_line_colors = use_automatic_line_colors,
                                                                            use_default_points = use_default_points,
                                                                            x_scale=x_scale,
                                                                            y_scale=y_scale,
                                                                            grid_manager=self.grid_manager,
                                                                            legend_manager=self.legend_manager,
                                                                            axis_manager=self.axis_manager,
                                                                            constrained_layout_manager=self.constrained_layout_manager,
                                                                            band_marker_manager=self.band_marker_manager,
                                                                            display_labels=display_labels,
                                                                            )

        # Set up the context menu for the canvas
        self.static_canvas.mpl_connect('button_press_event', self.handle_mouse_click)  

        # fig = self.static_canvas.figure
        # # fig.set_constrained_layout_pads(w_pad=0.1, h_pad=0.1, hspace=0.05, wspace=0.05)
        # fig.tight_layout(pad=1.05)  # 5% padding around the subplot elements

        self.graphics_layout.addWidget(plot_widget)

    def handle_mouse_click(self, event):
        """Handle mouse clicks on the canvas."""
        if event.button == 3:  # Right click
            self.show_context_menu(event)

    def show_context_menu(self, event):
        """Show the context menu with peak detection options."""
        context_menu = QMenu(self)
        
        # Add peak detection actions
        detect_peaks_action = context_menu.addAction("Detect Peaks")
        clear_peaks_action = context_menu.addAction("Clear Peaks")

        # Add separator and plot properties action
        context_menu.addSeparator()
        legend_properties_action = context_menu.addAction("Legend")
        
        # Add separator and grid action
        context_menu.addSeparator()
        grid_properties_action = context_menu.addAction("Grid")
        
        # Add separator and layout properties action
        context_menu.addSeparator()
        layout_properties_action = context_menu.addAction("Layout Properties")        

        # Add separator and axis properties action
        context_menu.addSeparator()
        axis_properties_action = context_menu.addAction("Axis properties")  
        
        # Add separator and automatic line colors option
        context_menu.addSeparator()
        automatic_line_colors_action = context_menu.addAction("Automatic Line Colors")
        automatic_line_colors_action.setCheckable(True)
        automatic_line_colors_action.setChecked(self.use_automatic_line_colors)  
        
        default_points_action = context_menu.addAction("Default Points")
        default_points_action.setCheckable(True)
        default_points_action.setChecked(self.use_default_points)        
        
        # Add separator and new figure action
        context_menu.addSeparator()
        new_figure_action = context_menu.addAction("Open in New Window")        

        # Convert matplotlib event coordinates to global screen coordinates
        canvas = self.static_canvas
        point = canvas.mapToGlobal(canvas.geometry().topLeft())
        x_offset = point.x() + event.x
        y_offset = point.y() + canvas.height() - event.y
        
        # Show the context menu at the calculated position
        action = context_menu.exec_(QPoint(int(x_offset), int(y_offset)))
        
        if action == detect_peaks_action:
            self.detect_peaks_dialog()
        elif action == clear_peaks_action:
            self.peak_detection_controller.clear_peaks()
            # self.plot_spectra()
        elif action == legend_properties_action:
            self.legend_properties_controller.show_dialog()
        elif action == grid_properties_action:
            self.grid_properties_controller.show_dialog()
        elif action == axis_properties_action:
            self.axis_properties_controller.show_dialog() 
        elif action == layout_properties_action:
            self.constrained_layout_controller.show_dialog()
        elif action == new_figure_action:
            self.open_external_figure()
        elif action == automatic_line_colors_action:
            # Toggle the checkbox state and update the plot
            self.use_automatic_line_colors = automatic_line_colors_action.isChecked()
            
            # Block signals temporarily to avoid triggering the event twice
            self.view.automatic_line_colors_checkBox.blockSignals(True)
            self.view.automatic_line_colors_checkBox.setChecked(self.use_automatic_line_colors)
            self.view.automatic_line_colors_checkBox.blockSignals(False)            
 
            self.plot_spectra() 
        elif action == default_points_action:
            # Update the state and redraw the plot
            self.use_default_points = default_points_action.isChecked()
            self.plot_spectra()            

    def detect_peaks_dialog(self):
        self.peak_detection_controller.show_dialog()

    def display_imported_spectra(self):
        """
        Displays the imported spectra based on the current plot type.
        Ensures spectra are ordered and UI is updated.
        """
        
        self.original_spectra = self.import_spectra()
        self.original_spectra = self.order_spectra(self.original_spectra)
        
        # Block signals during population
        self.spectra_list_widget.blockSignals(True)
        
        # Populate spectrum selection list
        self.spectra_list_widget.clear()
        for spectrum in self.original_spectra:
            item = QListWidgetItem(spectrum['label'])
            item.setData(Qt.UserRole, spectrum_id(spectrum))
            item.setFlags(item.flags() | Qt.ItemIsSelectable)
            self.spectra_list_widget.addItem(item)

        # Restore signals
        self.spectra_list_widget.blockSignals(False)            
    
        num_of_spectra = len(self.original_spectra)
        # Update spinbox maximum values based on the number of spectra
        self.view.number_of_rows_spinBox.setMaximum(num_of_spectra)
        self.view.number_of_columns_spinBox.setMaximum(num_of_spectra)
        
        # Clear the view since no spectra are selected initially
        self.clear_graphics_view()
        self.view.spectrum_selection_frame.setVisible(True)  # show spectra panel
        
        # Initialize an empty selection in the spectrum selector
        self.spectrum_selector.selected_indices.clear()
        self.spectrum_selector.update_spectra_count_label()
        self._update_difference_reference_combobox()
        
        # Initialize history with original spectra
        if hasattr(self, 'operations_controller'):
            logger.debug("Calling initialize_history with %d spectra", len(self.original_spectra))
            self.operations_controller.initialize_history()        

        # Apply any existing range restrictions after display is complete
        if self.spectral_range_controller.current_ranges:
            self.spectral_range_controller.apply_ranges_to_spectra()        

    def update_spectra_order_and_redraw_plot(self):
        """
        Updates spectra ordering and redraws the plot while preserving selected states.
        """
        # Store the currently selected spectra's PERMANENT identity
        # (unique_id, via each item's Qt.UserRole data) rather than their
        # display text — see spectrum_identity.py / developer_guide_help
        # "Golden Rule: Spectrum Identity". A label match here would be
        # exactly the kind of stale-key risk that section warns about.
        selected_ids = {item.data(Qt.UserRole) for item in self.spectra_list_widget.selectedItems()}

        # Re-order the original spectra
        self.original_spectra = self.order_spectra(self.original_spectra)

        # Update selected_spectra to maintain the same order as original_spectra
        self.selected_spectra = [
            spectrum for spectrum in self.original_spectra
            if spectrum_key(spectrum) in selected_ids
        ]

        # Block signals during update
        self.spectra_list_widget.blockSignals(True)
        try:
            # Clear and repopulate the list widget
            self.spectra_list_widget.clear()
            for spectrum in self.original_spectra:
                item = QListWidgetItem(spectrum['label'])
                item.setData(Qt.UserRole, spectrum_id(spectrum))
                item.setFlags(item.flags() | Qt.ItemIsSelectable)
                self.spectra_list_widget.addItem(item)

                # Set selection state
                if spectrum_key(spectrum) in selected_ids:
                    item.setSelected(True)

            # Update the spectrum_selector's selected_indices
            self.spectrum_selector.selected_indices = {
                i for i in range(self.spectra_list_widget.count())
                if self.spectra_list_widget.item(i).data(Qt.UserRole) in selected_ids
            }

            # Update the plot if we're in interactive mode
            if self.interactive_mode_checkbox.isChecked():
                if selected_ids:
                    self.plot_spectra()
                else:
                    self.clear_graphics_view()
        finally:
            self.spectra_list_widget.blockSignals(False)
            self.spectrum_selector.update_spectra_count_label()

    # Digit run, with an optional leading '-' — but ONLY treated as a
    # minus sign when it's not glued onto a preceding letter/digit. That
    # distinguishes a genuine negative number ("T=-5.00C", '-' preceded by
    # '=') from a hyphen used as a separator ("sample-1", '-' preceded by
    # 'e'). Without this, "sample-1" vs "sample-10" would misorder ("-1" >
    # "-10" as signed integers), and that hyphen-as-separator pattern is
    # far more common in spectrum labels than an actual negative value —
    # so the lookbehind protects the common case while still fixing the
    # negative-temperature case when it does show up.
    _NATSORT_CHUNK_RE = re.compile(r'((?<![A-Za-z0-9])-?\d+)')

    @classmethod
    def _natural_sort_key(cls, label):
        """Split a label into alternating text/number chunks so that
        embedded numbers sort numerically instead of lexicographically —
        e.g. "T=8.60" before "T=79.70" before "T=80.70", not "T=79.70" <
        "T=8.60" < "T=80.70" the way a plain string sort would order them
        (a real case seen with SpecOrd-imported melting curves: their
        labels embed an unpadded temperature like "...run3_heating
        T=8.60C", and every "default order" view in the app — SVD/NMF/
        MCR-ALS concentration profiles, SVD background correction, etc. —
        is just whatever order original_spectra ends up in here).

        Each chunk is tagged (0, int) for a number or (1, str) for text,
        so two labels can always be compared even when their chunk
        patterns differ in length or type at some position: the leading
        0/1 tag never compares an int to a str (Python 3 raises on that),
        it just decides text-sorts-after-number-at-that-position and lets
        the tuple comparison move on. Chunks stop at whole digit runs
        (not full floats), so "8" vs "79" vs "80" compare as integers and
        the literal "." / fractional part after them still fall out
        correctly as their own numeric chunk.
        """
        return tuple(
            (0, int(chunk)) if re.fullmatch(r'-?\d+', chunk) else (1, chunk.lower())
            for chunk in cls._NATSORT_CHUNK_RE.split(label) if chunk != ''
        )

    def order_spectra(self, spectra):
        """
        Sort spectra by label using natural (numeric-aware) order,
        optionally reversed.
        """
        # Safety check - return empty list if spectra is None
        if spectra is None:
            logger.warning("DEBUG order_spectra: Warning - spectra is None, returning empty list")
            return []

        if not spectra:
            logger.warning("DEBUG order_spectra: Warning - spectra is empty, returning empty list")
            return []

        reverse = self.checkBox_reverse_order.isChecked()

        logger.debug("order_spectra: Ordering %d spectra (natural order), reverse=%s", len(spectra), reverse)

        try:
            # Natural sort: embedded numbers (temperature, run index, etc.)
            # compare numerically instead of character-by-character, so
            # "T=8.60" sorts before "T=79.70" before "T=80.70" instead of
            # interleaving on the leading digit. See _natural_sort_key.
            sorted_spectra = sorted(spectra, key=lambda s: self._natural_sort_key(s['label']), reverse=reverse)
            logger.debug("order_spectra: Successfully sorted %d spectra", len(sorted_spectra))
            return sorted_spectra
        except Exception as e:
            logger.error("order_spectra: Error sorting spectra: %s", e)
            return spectra  # Return original list if sorting fails
        
    def closeEvent(self, event):
        """
        Confirm before actually closing, then handle cleanup.

        The confirmation lives here rather than on MainWindow's own
        closeEvent because line ~958 (self.view.closeEvent =
        self.closeEvent) monkey-patches THIS method directly onto the
        view instance — an instance attribute always takes priority over
        a class method in Python, so MainWindow.closeEvent would never
        actually run no matter what it does; this is the one Qt calls.

        Qt's default quitOnLastWindowClosed behavior only quits the
        application once the *last* visible top-level window closes. Any
        independent, non-modal window still open at this point (2D
        Spectral Map, SVD preview windows, etc.) means the app never
        actually exits — the main window disappears, but that orphaned
        window has no path back to a clean shutdown, and just hangs there
        with nothing left to close it. Explicitly closing everything else
        first guarantees the whole application actually exits.
        """
        from PyQt5.QtWidgets import QApplication, QMessageBox

        reply = QMessageBox.question(
            self.view, "Close SpecAnalytiXBase",
            "Are you sure you want to close the application?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            event.ignore()
            return

        # Excluding self (MainController), not just self.view, matters:
        # MainController is ALSO a QMainWindow — constructed but never
        # shown (see show(), which only ever calls self.view.show()) —
        # and Qt's topLevelWidgets() counts it regardless of visibility.
        # Without this, widget.close() would eventually reach self,
        # triggering THIS SAME closeEvent a second time recursively —
        # exactly what caused the confirmation to appear twice.
        for widget in QApplication.topLevelWidgets():
            if widget is not self.view and widget is not self:
                try:
                    widget.close()
                except Exception:
                    pass
        event.accept() 