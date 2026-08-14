# src/views/dialogs/data_analysis/baseline_correction_dialog.py

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QPushButton, QLabel, QSpinBox,
    QSplitter, QSizePolicy, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QDialogButtonBox, QWidget,
    QGroupBox, QMenu, QAction, QRadioButton, QButtonGroup,
)
from PyQt5.QtCore import Qt, pyqtSignal
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from src.help.baseline_correction_help import (
    get_baseline_correction_help_content,
    get_baseline_correction_help_title,
)
from src.help.help_window import show_help_window
from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import make_shortened_name_delegate, make_shorten_names_checkbox

logger = get_logger(__name__)


# ======================================================================= #
#  BaselineCorrectionSummaryDialog                                          #
# ======================================================================= #

class BaselineCorrectionSummaryDialog(QDialog):
    """Read-only summary table of all baseline corrections."""

    def __init__(self, parent=None, summary=None):
        super().__init__(parent)
        self.setWindowTitle("Baseline Correction Summary")
        self.summary = summary or []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Spectrum", "Points", "Type", "Order"])
        table.setRowCount(len(self.summary))

        for i, entry in enumerate(self.summary):
            table.setItem(i, 0, QTableWidgetItem(entry.get('spectrum', '')))
            table.setItem(i, 1, QTableWidgetItem(str(entry.get('points', 0))))
            table.setItem(i, 2, QTableWidgetItem(entry.get('type', '')))
            if entry.get('type') == 'polynomial' and 'order' in entry:
                table.setItem(i, 3, QTableWidgetItem(str(entry['order'])))

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        layout.addWidget(table)

        btn = QDialogButtonBox(QDialogButtonBox.Close)
        btn.rejected.connect(self.reject)
        layout.addWidget(btn)

        self.resize(500, 300)


# ======================================================================= #
#  BaselineCorrectionDialog                                                 #
# ======================================================================= #

class BaselineCorrectionDialog(QDialog):
    """Interactive manual baseline correction dialog."""

    _TOGGLE_STYLE = """
        QPushButton {
            border: 1px solid #aaa; border-radius: 4px;
            padding: 4px 8px; background-color: #f0f0f0; color: #222;
        }
        QPushButton:checked {
            background-color: #2979ff; color: white;
            border: 1px solid #1a56cc; font-weight: bold;
        }
        QPushButton:hover:!checked {
            background-color: #dce8ff; border: 1px solid #2979ff;
        }
        QPushButton:disabled {
            background-color: #e8e8e8; color: #aaa; border: 1px solid #ccc;
        }
    """
    _CLEAR_STYLE = """
        QPushButton {
            border: 1px solid #aaa; border-radius: 4px;
            padding: 4px 8px; background-color: #f0f0f0; color: #222;
        }
        QPushButton:hover:enabled {
            background-color: #ffe0e0; border: 1px solid #cc3333; color: #cc3333;
        }
        QPushButton:disabled {
            background-color: #e8e8e8; color: #aaa; border: 1px solid #ccc;
        }
    """
    _HINT_STYLE = (
        "color: #1976D2; font-style: italic; padding: 5px;"
        " background-color: #E3F2FD; border-radius: 3px; margin: 2px;"
    )

    def __init__(self, parent=None, selected_spectra=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Manual Baseline Correction")
        self.selected_spectra        = selected_spectra or []
        self.current_spectrum        = None
        self.controller              = None   # set externally before initialize_with_controller
        self.controls_visible        = True
        self.stored_sizes            = None
        self._initialization_complete = False
        self.sort_ascending          = True
        # Bound method (OperationsController.commit_manual_baseline) passed
        # in by whatever opened this dialog, so Apply / Add as New can
        # commit the result directly, without a separate Run step.
        self.commit_callback         = commit_callback

        if not hasattr(BaselineCorrectionDialog, '_persistent_state'):
            BaselineCorrectionDialog._persistent_state = {
                'selected_row': 0,
                'view_mode':    'original',
            }

        self.setMinimumSize(800, 600)
        self.resize(1200, 800)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.WindowCloseButtonHint
            | Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)
        self.setup_ui()

    # ------------------------------------------------------------------ #
    # Initialisation                                                       #
    # ------------------------------------------------------------------ #

    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def initialize_with_controller(self):
        """Populate the dialog from the controller after it has been set."""
        if not self.controller or not self.selected_spectra:
            return

        try:
            self.spectra_list.blockSignals(True)

            if self.spectra_list.count() > 0:
                saved_row = BaselineCorrectionDialog._persistent_state.get('selected_row', 0)
                row       = min(saved_row, self.spectra_list.count() - 1)
                self.spectra_list.setCurrentRow(row)

                spectrum = (
                    self.list_to_spectra_map[row]
                    if hasattr(self, 'list_to_spectra_map') and row in self.list_to_spectra_map
                    else self.selected_spectra[row]
                )
                self.current_spectrum     = spectrum
                self.canvas.baseline_points = (
                    self.controller.get_baseline_points(spectrum).copy() or []
                )

                # Restore fit type
                fit_type = self.controller.get_fit_type(spectrum)
                self._apply_fit_type_ui(fit_type)
                self.poly_order_spin.setValue(self.controller.get_poly_order(spectrum))

                self.canvas.plot_spectrum(spectrum)

                # Restore view mode
                saved_view = BaselineCorrectionDialog._persistent_state.get('view_mode', 'original')
                self._apply_view_mode_ui(saved_view)
                self.update_view_mode()

        finally:
            self.spectra_list.blockSignals(False)

        self._initialization_complete = True
        self.canvas.enable_baseline_mode()
        self.canvas.setFocus()

    # ------------------------------------------------------------------ #
    # UI construction                                                       #
    # ------------------------------------------------------------------ #

    def setup_ui(self):
        layout   = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        splitter.addWidget(self._create_control_panel())
        splitter.addWidget(self._create_canvas_panel())
        splitter.setSizes([400, 1000])

    def _hint(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(self._HINT_STYLE)
        lbl.setWordWrap(True)
        return lbl

    def _create_control_panel(self):
        widget = QWidget()
        widget.setFixedWidth(400)
        layout = QVBoxLayout(widget)

        # ── Spectrum Navigation ─────────────────────────────────────
        nav_group  = QGroupBox("Spectrum Navigation")
        nav_layout = QVBoxLayout(nav_group)

        nav_row = QHBoxLayout()
        self.prev_btn = QPushButton("Previous")
        self.prev_btn.clicked.connect(self.prev_spectrum)
        nav_row.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.next_spectrum)
        nav_row.addWidget(self.next_btn)

        self.sort_button = QPushButton("▲")
        self.sort_button.setToolTip("Toggle sort order")
        self.sort_button.setMaximumWidth(30)
        self.sort_button.clicked.connect(self.toggle_sort_order)
        nav_row.addWidget(self.sort_button)
        nav_layout.addLayout(nav_row)

        nav_layout.addWidget(self._hint(
            "💡 Navigate between selected spectra. Each spectrum is corrected "
            "individually using its baseline points."
        ))

        self.spectra_list = QListWidget()
        self.spectra_list.setSelectionMode(QListWidget.SingleSelection)
        self.spectra_list.setStyleSheet(
            "QListWidget::item:selected { background-color: #4A7FC1; color: white; }"
        )
        self.spectra_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        # Display-only "shorten names" — this dialog's own, independent
        # checkbox (see make_shorten_names_checkbox).
        self.spectra_list.setItemDelegate(
            make_shortened_name_delegate(self.spectra_list, self._shorten_names_enabled)
        )
        nav_layout.addWidget(self.spectra_list)
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _: self.spectra_list.viewport().update()
        )
        nav_layout.addWidget(self.checkBox_shorten_names)

        nav_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout.addWidget(nav_group)

        # ── Baseline Correction ─────────────────────────────────────
        baseline_group  = QGroupBox("Baseline Correction")
        baseline_layout = QVBoxLayout(baseline_group)

        # Enable sub-group
        enable_group  = QGroupBox("Enable Baseline Correction")
        enable_layout = QVBoxLayout(enable_group)
        radio_row     = QHBoxLayout()
        self.baseline_mode_group = QButtonGroup()

        self.baseline_on_btn = QRadioButton("On")
        self.baseline_on_btn.setChecked(True)
        self.baseline_on_btn.clicked.connect(self.enable_baseline_mode)
        self.baseline_mode_group.addButton(self.baseline_on_btn)
        radio_row.addWidget(self.baseline_on_btn)

        self.baseline_off_btn = QRadioButton("Off")
        self.baseline_off_btn.clicked.connect(self.disable_baseline_mode)
        self.baseline_mode_group.addButton(self.baseline_off_btn)
        radio_row.addWidget(self.baseline_off_btn)

        enable_layout.addLayout(radio_row)
        enable_layout.addWidget(self._hint(
            "Left-click: Add point | Right-click: Remove point. "
            "Navigator toolbar is disabled during baseline correction."
        ))
        baseline_layout.addWidget(enable_group)

        # View Mode sub-group
        view_group  = QGroupBox("View Mode")
        view_layout = QVBoxLayout(view_group)
        view_layout.addWidget(self._hint(
            "💡 Select view mode for visualization. Press buttons again to rescale. "
            "Axis limits remain fixed during baseline editing."
        ))
        view_row = QHBoxLayout()
        self.view_original_btn = QPushButton("Original")
        self.view_original_btn.setCheckable(True)
        self.view_original_btn.setChecked(True)
        self.view_original_btn.clicked.connect(self.view_original)
        view_row.addWidget(self.view_original_btn)

        self.view_corrected_btn = QPushButton("Corrected")
        self.view_corrected_btn.setCheckable(True)
        self.view_corrected_btn.clicked.connect(self.view_corrected)
        view_row.addWidget(self.view_corrected_btn)

        self.view_both_btn = QPushButton("Both")
        self.view_both_btn.setCheckable(True)
        self.view_both_btn.clicked.connect(self.view_both)
        view_row.addWidget(self.view_both_btn)

        view_layout.addLayout(view_row)
        view_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        baseline_layout.addWidget(view_group)

        # Baseline Fitting sub-group
        fit_group  = QGroupBox("Baseline Fitting")
        fit_layout = QVBoxLayout(fit_group)
        fit_layout.addWidget(self._hint(
            "💡 Choose fitting method for baseline interpolation between manually placed points."
        ))
        fit_row = QHBoxLayout()
        self.baseline_spline_btn = QPushButton("Spline")
        self.baseline_spline_btn.setCheckable(True)
        self.baseline_spline_btn.setChecked(True)
        self.baseline_spline_btn.clicked.connect(self.set_baseline_spline)
        fit_row.addWidget(self.baseline_spline_btn)

        self.baseline_poly_btn = QPushButton("Poly")
        self.baseline_poly_btn.setCheckable(True)
        self.baseline_poly_btn.clicked.connect(self.set_baseline_poly)
        fit_row.addWidget(self.baseline_poly_btn)

        fit_row.addWidget(QLabel("Polynomial Order:"))
        self.poly_order_spin = QSpinBox()
        self.poly_order_spin.setRange(1, 10)
        self.poly_order_spin.setValue(5)
        self.poly_order_spin.setKeyboardTracking(False)
        self.poly_order_spin.setEnabled(False)
        self.poly_order_spin.valueChanged.connect(self.on_poly_order_changed)
        fit_row.addWidget(self.poly_order_spin)

        fit_layout.addLayout(fit_row)
        fit_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        baseline_layout.addWidget(fit_group)

        # Clear Baselines sub-group
        clear_group  = QGroupBox("Clear Baselines")
        clear_layout = QHBoxLayout(clear_group)
        self.reset_current_button = QPushButton("Current")
        self.reset_current_button.clicked.connect(self.on_reset_current)
        clear_layout.addWidget(self.reset_current_button)

        self.reset_all_button = QPushButton("All")
        self.reset_all_button.clicked.connect(self.on_reset_all)
        clear_layout.addWidget(self.reset_all_button)

        self.summary_button = QPushButton("Summary")
        self.summary_button.clicked.connect(self.on_show_summary)
        clear_layout.addWidget(self.summary_button)

        baseline_layout.addWidget(clear_group)
        baseline_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(baseline_group)

        # ── Buttons ─────────────────────────────────────────────────
        self.button_box = QDialogButtonBox()

        self.help_button = QPushButton("Help")
        self.help_button.clicked.connect(self.show_help)
        self.button_box.addButton(self.help_button, QDialogButtonBox.HelpRole)

        # Apply / Add as New commit directly via commit_callback — there's
        # no separate Run step in the main window for this operation
        # anymore (see OperationsController.commit_manual_baseline).
        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip(
            "Replace the selected spectra with their baseline-corrected result."
        )
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        self.button_box.addButton(self.apply_button, QDialogButtonBox.ActionRole)

        self.add_as_new_button = QPushButton("Add as New")
        self.add_as_new_button.setToolTip(
            "Keep the original spectra unchanged and add the baseline-corrected "
            "results to the list under new names."
        )
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        self.button_box.addButton(self.add_as_new_button, QDialogButtonBox.ActionRole)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        self.button_box.addButton(self.close_button, QDialogButtonBox.RejectRole)

        self.button_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.button_box)

        layout.setStretchFactor(nav_group,       1)
        layout.setStretchFactor(baseline_group,  0)
        layout.setStretchFactor(self.button_box, 0)

        # Styles
        for btn in (
            self.view_original_btn, self.view_corrected_btn, self.view_both_btn,
            self.baseline_spline_btn, self.baseline_poly_btn,
        ):
            btn.setStyleSheet(self._TOGGLE_STYLE)

        for btn in (self.reset_current_button, self.reset_all_button, self.summary_button):
            btn.setStyleSheet(self._CLEAR_STYLE)

        # Signals
        self.spectra_list.currentItemChanged.connect(self.on_spectrum_selected)
        self.populate_spectrum_list()

        return widget

    def _create_canvas_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.canvas = BaselinePlotCanvas(self)
        self.toolbar = NavigationToolbar(self.canvas, widget)

        self.coordinates_label = QLabel("")
        self.coordinates_label.setStyleSheet("background-color: #f0f0f0; padding: 2px;")

        layout.addWidget(self.toolbar)
        layout.addWidget(self.coordinates_label)
        layout.addWidget(self.canvas)

        self.canvas.point_added.connect(self.on_point_added)
        self.canvas.point_removed.connect(self.on_point_removed)

        return widget

    # ------------------------------------------------------------------ #
    # Navigation                                                           #
    # ------------------------------------------------------------------ #

    def prev_spectrum(self):
        r = self.spectra_list.currentRow()
        if r > 0:
            self.spectra_list.setCurrentRow(r - 1)

    def next_spectrum(self):
        r = self.spectra_list.currentRow()
        if r < self.spectra_list.count() - 1:
            self.spectra_list.setCurrentRow(r + 1)

    def toggle_sort_order(self):
        self.sort_ascending = not self.sort_ascending
        self.sort_button.setText("▲" if self.sort_ascending else "▼")
        self.sort_spectra_list()

    def sort_spectra_list(self):
        current_text = (
            self.spectra_list.currentItem().text()
            if self.spectra_list.currentItem() else None
        )
        self.spectra_list.clear()
        self.list_to_spectra_map = {}
        for i, sp in enumerate(
            sorted(self.selected_spectra, key=lambda x: x['label'].lower(),
                   reverse=not self.sort_ascending)
        ):
            self.spectra_list.addItem(sp['label'])
            self.list_to_spectra_map[i] = sp
        if current_text:
            items = self.spectra_list.findItems(current_text, Qt.MatchExactly)
            if items:
                self.spectra_list.setCurrentItem(items[0])

    def populate_spectrum_list(self):
        self.spectra_list.clear()
        self.list_to_spectra_map = {}
        for i, sp in enumerate(sorted(self.selected_spectra, key=lambda x: x['label'].lower())):
            self.spectra_list.addItem(sp['label'])
            self.list_to_spectra_map[i] = sp
        if self.spectra_list.count() > 0:
            self.spectra_list.setCurrentRow(0)

    # ------------------------------------------------------------------ #
    # Controls visibility                                                  #
    # ------------------------------------------------------------------ #

    def toggle_controls_visibility(self, visible):
        self.controls_visible = visible
        splitter = self.layout().itemAt(0).widget()
        if isinstance(splitter, QSplitter) and splitter.count() >= 2:
            splitter.widget(0).setVisible(visible)
            splitter.setSizes([400 if visible else 0, 1000])
        self.update()

    # ------------------------------------------------------------------ #
    # Baseline mode                                                        #
    # ------------------------------------------------------------------ #

    def enable_baseline_mode(self):
        self.canvas.enable_baseline_mode()
        if hasattr(self, 'toolbar'):
            self.toolbar.setEnabled(False)
            try:
                self.toolbar.mode = ''
                if hasattr(self.toolbar, '_active'):
                    self.toolbar._active = None
                self.canvas.setCursor(Qt.ArrowCursor)
                self.toolbar._update_buttons_checked()
            except Exception as exc:
                logger.error(f"Toolbar reset failed: {exc}")
                self.canvas.setCursor(Qt.ArrowCursor)
        self.canvas.setFocus()

    def disable_baseline_mode(self):
        self.canvas.disable_baseline_mode()
        if hasattr(self, 'toolbar'):
            self.toolbar.setEnabled(True)

    # ------------------------------------------------------------------ #
    # Fit type                                                             #
    # ------------------------------------------------------------------ #

    def set_baseline_spline(self):
        self.baseline_spline_btn.setChecked(True)
        self.baseline_poly_btn.setChecked(False)
        self.poly_order_spin.setEnabled(False)
        self.update_baseline_type()

    def set_baseline_poly(self):
        self.baseline_spline_btn.setChecked(False)
        self.baseline_poly_btn.setChecked(True)
        self.poly_order_spin.setEnabled(True)
        self.update_baseline_type()

    def update_baseline_type(self):
        if self.controller and self.current_spectrum:
            fit_type = 'cubic spline' if self.baseline_spline_btn.isChecked() else 'polynomial'
            self.controller.set_fit_type(self.current_spectrum, fit_type)
            if fit_type == 'polynomial':
                self.controller.set_poly_order(self.current_spectrum, self.poly_order_spin.value())
            self.update_baseline_curve()
        self.canvas.setFocus()

    def on_poly_order_changed(self, order):
        if self.controller and self.current_spectrum and self.baseline_poly_btn.isChecked():
            self.controller.set_poly_order(self.current_spectrum, order)
            self.update_baseline_curve()

    # ------------------------------------------------------------------ #
    # View mode                                                            #
    # ------------------------------------------------------------------ #

    def _apply_view_mode_ui(self, mode):
        self.view_original_btn.setChecked(mode == 'original')
        self.view_corrected_btn.setChecked(mode == 'corrected')
        self.view_both_btn.setChecked(mode == 'both')

    def _apply_fit_type_ui(self, fit_type):
        is_spline = (fit_type == 'cubic spline')
        self.baseline_spline_btn.setChecked(is_spline)
        self.baseline_poly_btn.setChecked(not is_spline)
        self.poly_order_spin.setEnabled(not is_spline)

    def view_original(self):
        self._apply_view_mode_ui('original')
        self.update_view_mode()

    def view_corrected(self):
        self._apply_view_mode_ui('corrected')
        self.update_view_mode()

    def view_both(self):
        self._apply_view_mode_ui('both')
        self.update_view_mode()

    def update_view_mode(self):
        if not self.current_spectrum or not self.controller:
            return
        baseline = self.controller.calculate_baseline(self.current_spectrum, self.current_spectrum['x_scale'])

        show_original  = self.view_original_btn.isChecked() or self.view_both_btn.isChecked()
        show_corrected = self.view_corrected_btn.isChecked() or self.view_both_btn.isChecked()
        show_baseline  = baseline is not None and (show_original or self.view_both_btn.isChecked())

        self.canvas.update_view_mode(
            show_original=show_original,
            show_corrected=show_corrected,
            show_baseline=show_baseline,
            baseline=baseline,
        )
        self.canvas.setFocus()

    def update_baseline_curve(self):
        if not self.controller or not self.current_spectrum:
            return
        baseline = self.controller.calculate_baseline(self.current_spectrum, self.current_spectrum['x_scale'])
        if baseline is not None:
            self.canvas.plot_baseline(baseline)
            self.update_view_mode()

    # ------------------------------------------------------------------ #
    # Spectrum selection                                                   #
    # ------------------------------------------------------------------ #

    def on_spectrum_selected(self, current, previous):
        if not self._initialization_complete:
            return
        if current is None:
            self.current_spectrum       = None
            self.canvas.baseline_points = []
            self.canvas.plot_spectrum(None)
            return

        row = self.spectra_list.currentRow()
        self.current_spectrum = (
            self.list_to_spectra_map.get(row)
            if hasattr(self, 'list_to_spectra_map')
            else next((s for s in self.selected_spectra if s['label'] == current.text()), None)
        )
        if not self.current_spectrum:
            return

        if self.controller:
            fit_type = self.controller.get_fit_type(self.current_spectrum)
            self._apply_fit_type_ui(fit_type)
            self.poly_order_spin.setValue(self.controller.get_poly_order(self.current_spectrum))

            self.canvas.baseline_points = []
            self.canvas.plot_spectrum(self.current_spectrum)

            pts = self.controller.get_baseline_points(self.current_spectrum)
            if pts:
                self.canvas.baseline_points = pts
                self.canvas.plot_spectrum(self.current_spectrum)
            self.update_view_mode()

    # ------------------------------------------------------------------ #
    # Point add / remove                                                   #
    # ------------------------------------------------------------------ #

    def on_point_added(self, x, y):
        if not self.controller or not self.current_spectrum:
            return
        xlim, ylim = self.canvas.axes.get_xlim(), self.canvas.axes.get_ylim()
        pts = self.controller.add_baseline_point(self.current_spectrum, x, y)
        self.canvas.update_baseline_points(pts)
        self.update_baseline_curve()
        self.canvas.axes.set_xlim(xlim)
        self.canvas.axes.set_ylim(ylim)
        self.canvas.draw()

    def on_point_removed(self, x, y):
        if not self.controller or not self.current_spectrum:
            return
        xlim, ylim = self.canvas.axes.get_xlim(), self.canvas.axes.get_ylim()
        pts = self.controller.remove_baseline_point(self.current_spectrum, x, y)
        if pts is not None:
            self.canvas.update_baseline_points(pts)
            self.update_baseline_curve()
        self.canvas.axes.set_xlim(xlim)
        self.canvas.axes.set_ylim(ylim)
        self.canvas.draw()

    # ------------------------------------------------------------------ #
    # Clear / Summary                                                      #
    # ------------------------------------------------------------------ #

    def on_reset_current(self):
        if self.controller and self.current_spectrum:
            self.controller.clear_baseline(self.current_spectrum)
            self.canvas.update_baseline_points([])
            self.canvas.plot_baseline(None)
            self.canvas.clear_corrected_spectrum()

    def on_reset_all(self):
        if not self.controller:
            return
        if QMessageBox.question(
            self, "Reset All Fits", "Are you sure you want to reset all baseline fits?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) == QMessageBox.Yes:
            self.controller.clear_all_baselines()
            if self.current_spectrum:
                self.canvas.update_baseline_points([])
                self.canvas.plot_baseline(None)
                self.canvas.clear_corrected_spectrum()
                self.update_view_mode()

    def on_show_summary(self):
        if self.controller:
            BaselineCorrectionSummaryDialog(self, self.controller.get_correction_summary()).exec_()

    # ------------------------------------------------------------------ #
    # Commit                                                               #
    # ------------------------------------------------------------------ #

    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — commits directly via commit_callback. No
        separate Run step: feedback (success or failure) is shown right
        here next to the buttons that triggered it, instead of in a
        disconnected main-window message box. The dialog closes itself
        once the commit succeeds.
        """
        if self.commit_callback is None:
            QMessageBox.critical(
                self, "Not Available",
                "This dialog was opened without a way to apply changes. "
                "Please reopen it via Parameters."
            )
            return

        action = ("add the baseline-corrected result as new spectra" if add_as_new
                  else "replace the selected spectra with their baseline-corrected result")
        confirm = QMessageBox.question(
            self, "Confirm", f"{action[0].upper() + action[1:]}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(add_as_new, list(self.selected_spectra))
        if success:
            QMessageBox.information(self, "Done", message)
            # Use close() rather than accept() so closeEvent still fires —
            # that's what persists the view-mode/selected-row UI state for
            # next time, the same way clicking Close normally does.
            self.close()
        else:
            QMessageBox.warning(self, "Could Not Apply", message)

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def show_help(self):
        show_help_window(self, get_baseline_correction_help_title(),
                         get_baseline_correction_help_content())

    # ------------------------------------------------------------------ #
    # Close                                                                #
    # ------------------------------------------------------------------ #

    def closeEvent(self, event):
        """Persist view mode and selected row, then close."""
        if self.view_corrected_btn.isChecked():
            view_mode = 'corrected'
        elif self.view_both_btn.isChecked():
            view_mode = 'both'
        else:
            view_mode = 'original'
        BaselineCorrectionDialog._persistent_state = {
            'selected_row': self.spectra_list.currentRow(),
            'view_mode':    view_mode,
        }
        event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self.canvas.setFocus()


# ======================================================================= #
#  BaselinePlotCanvas                                                       #
# ======================================================================= #

class BaselinePlotCanvas(FigureCanvas):
    """Matplotlib canvas with interactive baseline-point editing."""

    point_added   = pyqtSignal(float, float)
    point_removed = pyqtSignal(float, float)

    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig  = Figure(figsize=(width, height), dpi=dpi, tight_layout=True)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)

        self.axes.set_xlabel('X')
        self.axes.set_ylabel('Y')
        self.axes.grid(True)

        self.spectrum_data  = None
        self.baseline_points = []
        self.baseline_curve  = None
        self.corrected_line  = None
        self.baseline_mode   = False

        self.setFocusPolicy(Qt.StrongFocus)
        self.mpl_connect('button_press_event', self._on_click)
        self.mpl_connect('motion_notify_event', self._on_mouse_move)

        self.fig.patch.set_facecolor('#f0f0f0')
        self.axes.set_facecolor('#ffffff')

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.updateGeometry()

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # -- Baseline mode -------------------------------------------------- #

    def enable_baseline_mode(self):
        self.baseline_mode = True
        self.setFocus()

    def disable_baseline_mode(self):
        self.baseline_mode = False

    # -- Mouse events --------------------------------------------------- #

    def _on_click(self, event):
        if not self.baseline_mode or event.inaxes != self.axes or self.spectrum_data is None:
            return

        if event.button == 1:
            self.point_added.emit(event.xdata, event.ydata)
            return

        if event.button == 3:
            x_tol = 0.02 * (self.axes.get_xlim()[1] - self.axes.get_xlim()[0])
            y_tol = 0.05 * (self.axes.get_ylim()[1] - self.axes.get_ylim()[0])
            for px, py in self.baseline_points:
                if abs(event.xdata - px) < x_tol and abs(event.ydata - py) < y_tol:
                    self.point_removed.emit(px, py)
                    self._suppress_context_menu = True
                    return
            self._suppress_context_menu = False

    def _on_mouse_move(self, event):
        parent = self.parent()
        if hasattr(parent, 'coordinates_label'):
            parent.coordinates_label.setText(
                f"(x, y) = ({event.xdata:.6g}, {event.ydata:.6g})" if event.inaxes else ""
            )

    def _show_context_menu(self, pos):
        if getattr(self, '_suppress_context_menu', False):
            self._suppress_context_menu = False
            return

        menu   = QMenu(self)
        parent = self.parentWidget()
        while parent and not isinstance(parent, QDialog):
            parent = parent.parentWidget()

        if parent and hasattr(parent, 'toggle_controls_visibility'):
            visible = getattr(parent, 'controls_visible', True)
            action  = QAction("Show Only Spectrum" if visible else "Show Controls", self)
            action.triggered.connect(
                lambda checked, p=parent, v=visible: p.toggle_controls_visibility(not v)
            )
            menu.addAction(action)

        menu.exec_(self.mapToGlobal(pos))

    # -- Plot helpers --------------------------------------------------- #

    def plot_spectrum(self, spectrum):
        """Plot spectrum data, preserving axis limits if already set."""
        try:
            xlim, ylim = self.axes.get_xlim(), self.axes.get_ylim()
            had_limits = True
        except Exception:
            had_limits = False

        self.axes.clear()
        self.spectrum_data = spectrum

        if spectrum is None:
            self.draw()
            return

        x, y = spectrum['x_scale'], spectrum['y_scale']
        self.axes.plot(x, y, 'b-', lw=1, label="Data")

        if self.baseline_points:
            bx, by = zip(*self.baseline_points)
            self.axes.plot(bx, by, 'go', ms=8, mfc='green', alpha=0.7,
                           markeredgecolor='black', ls='')

        self.axes.set_title(f"Spectrum: {spectrum['label']}")
        self.axes.grid(True, linestyle='--', alpha=0.7)
        self.axes.legend(["Data"], loc='best')

        if had_limits:
            self.axes.set_xlim(xlim)
            self.axes.set_ylim(ylim)
        else:
            self.axes.autoscale()

        self.draw()

    def plot_baseline(self, baseline_y):
        if self.spectrum_data is None or baseline_y is None:
            return
        for line in self.axes.lines:
            if getattr(line, 'get_label', lambda: '')() == 'Baseline':
                line.remove()
        self.axes.plot(self.spectrum_data['x_scale'], baseline_y, 'g--',
                       lw=2, label='Baseline', dashes=(5, 2))
        self._refresh_legend()
        self.draw()

    def plot_corrected_spectrum(self, baseline_y):
        if self.spectrum_data is None or baseline_y is None:
            return
        x = self.spectrum_data['x_scale']
        y = self.spectrum_data['y_scale']
        for line in self.axes.lines:
            if getattr(line, 'get_label', lambda: '')() == 'Corrected':
                line.remove()
        self.axes.plot(x, y - baseline_y, 'r-', lw=1, label="Corrected")
        self._refresh_legend()
        self.draw()

    def clear_corrected_spectrum(self):
        if self.spectrum_data is None:
            return
        for line in self.axes.lines:
            if getattr(line, 'get_label', lambda: '')() == 'Corrected':
                line.remove()
        self._refresh_legend()
        self.draw()

    def update_view_mode(self, show_original=True, show_corrected=False,
                         show_baseline=False, baseline=None):
        if self.spectrum_data is None:
            return
        self.axes.clear()
        x, y = self.spectrum_data['x_scale'], self.spectrum_data['y_scale']

        if show_original:
            self.axes.plot(x, y, 'b-', lw=1, label="Data")
        if show_baseline and baseline is not None:
            self.axes.plot(x, baseline, 'g--', lw=2, label='Baseline', dashes=(5, 2))

        if show_corrected and baseline is not None:
            self.axes.plot(x, y - baseline, 'r-', lw=1, label="Corrected")
        # if self.baseline_points and (show_original or self.baseline_points):
        #     bx, by = zip(*self.baseline_points)
        #     self.axes.plot(bx, by, 'go', ms=8, mfc='green', alpha=0.7,
        #                    markeredgecolor='black', ls='')

        if self.baseline_points and show_original:
            bx, by = zip(*self.baseline_points)
            self.axes.plot(bx, by, 'go', ms=8, mfc='green', alpha=0.7,
                           markeredgecolor='black', ls='')            

        self.axes.set_title(f"Spectrum: {self.spectrum_data['label']}")
        self.axes.grid(True, linestyle='--', alpha=0.7)
        self._refresh_legend()
        self.axes.relim()
        self.axes.autoscale()
        self.draw()

    def update_baseline_points(self, points):
        xlim, ylim = self.axes.get_xlim(), self.axes.get_ylim()
        self.baseline_points = points
        self.plot_spectrum(self.spectrum_data)
        self.axes.set_xlim(xlim)
        self.axes.set_ylim(ylim)
        self.draw()
        try:
            parent = self.parent()
            if hasattr(parent, 'update_view_mode'):
                parent.update_view_mode()
        except Exception:
            pass

    def _refresh_legend(self):
        handles, labels = self.axes.get_legend_handles_labels()
        keep = [(h, l) for h, l in zip(handles, labels) if l in ("Data", "Baseline", "Corrected")]
        if keep:
            h, l = zip(*keep)
            self.axes.legend(list(h), list(l), loc='best')
