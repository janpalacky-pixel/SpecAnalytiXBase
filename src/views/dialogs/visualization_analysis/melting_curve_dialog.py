# src/views/dialogs/visualization_analysis/melting_curve_dialog.py

import re
import os
import hashlib
import numpy as np

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QDialogButtonBox, QLabel,
                             QWidget, QSplitter, QTableWidget, QTableWidgetItem,
                             QHeaderView, QComboBox, QMessageBox, QCheckBox,
                             QDoubleSpinBox, QSpinBox, QLineEdit, QAbstractItemView,
                             QScrollArea, QFrame, QSlider, QFileDialog, QApplication,
                             QRadioButton, QListWidget, QListWidgetItem, QInputDialog,
                             QAbstractSpinBox, QToolButton, QMenu, QPlainTextEdit,
                             QStyledItemDelegate, QAbstractItemDelegate)
from PyQt5.QtCore import Qt, QTimer, QEvent
from PyQt5.QtGui import QKeySequence, QBrush, QColor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — registers the 'projection=3d' used
                                         # by show_fit_summary's 3D scatter option

from src.modules.visualization_analysis.melting_curve_manager import (
    MeltingCurveManager, ARRHENIUS_CONFIDENCE_R2_THRESHOLD,
    SIGMOID_CONFIDENCE_R2_THRESHOLD, EDGE_TOLERANCE_ABSOLUTE_FRACTION)
from src.help.melting_curve_help import (get_melting_curve_help_content,
                                         get_melting_curve_help_title)
from src.help.help_window import show_help_window
from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    make_display_text_delegate, make_shorten_names_checkbox, shorten_spectra_labels,
)
logger = get_logger(__name__)

# Developer/debugging tool: shows "Compare to Known Values..." in Sigmoid
# Fit, which checks a fit against this app's own bundled synthetic test
# datasets' known true values. Genuinely useful while developing or
# debugging this feature, but not something an end user analyzing real
# experimental data (which has no "known answer") has any use for — set
# this back to True to bring the button back for development; the
# underlying compare_fit_to_known_values() method and everything it needs
# stays in the code either way, just not exposed in the UI when False.
_SHOW_DEVELOPER_TOOLS = False

# Matches every signed/unsigned float or int found in a spectrum label,
# e.g. "sample_25C" -> [25], "r-2,4-blok ... pokus : 10" -> [-2, 4, 10].
# Used only to seed a reasonable starting guess for each spectrum's
# temperature in the editable table below — never trusted as the final
# value.
_NUMBER_RE = re.compile(r'-?\d+\.?\d*')


class _EnterCommitDelegate(QStyledItemDelegate):
    """Item delegate that keeps Enter/Return, while editing a table
    cell, from propagating past the edit itself to the dialog's default
    OK button and closing the whole dialog — the same well-known Qt
    trap _prevent_enter_from_closing_dialog handles for ordinary spin
    boxes and line edits. A table cell's editor doesn't have that same
    fix available: it's a fresh widget Qt creates only once editing
    actually starts, not one of the static widgets already present (and
    findable via findChildren) when this dialog first sets up its
    Enter-key guards.

    Qt calls a delegate's own eventFilter() for every event sent to an
    editor it created, which is exactly the hook needed here: catch
    Enter/Return, commit the edit and close the editor exactly the way
    Qt's own default handling would, then report the event as already
    handled so it goes no further — instead of letting Qt's default
    behavior process it AND then also let it propagate up to the
    dialog afterward."""

    def eventFilter(self, editor, event):
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QAbstractItemDelegate.NoHint)
            return True
        return super().eventFilter(editor, event)


class _NumericTableWidgetItem(QTableWidgetItem):
    """A QTableWidgetItem that sorts by numeric value instead of Qt's
    default lexicographic text comparison ("10" sorting before "2").

    QTableWidgetItem.setData(Qt.EditRole, some_float) looks like the
    documented way to do this, but doesn't actually work in PyQt5 —
    EditRole and DisplayRole share the same internal text storage for
    this class, so the float silently comes back as a string on the next
    read (confirmed directly: item.data(Qt.EditRole) returns a Python
    str, not a float, even right after setting it to one). Overriding
    __lt__ — what QTableWidget's native column-header sorting actually
    calls — is the reliable way to get numeric ordering instead.
    """

    def __lt__(self, other):
        try:
            return float(self.text()) < float(other.text())
        except (ValueError, TypeError):
            return super().__lt__(other)


class MeltingCurveDialog(QDialog):
    """Dialog for extracting a thermal melting curve from a series of
    spectra (one signal value per spectrum, read at a chosen x-value) and
    analyzing it: linear-baseline normalization, Arrhenius-based
    thermodynamic parameters (deltaH, deltaS), and multi-sigmoid (up to 4
    components) deconvolution of multiphasic transitions.

    Structural pattern (control panel + canvas splitter, Output Options
    driving what gets saved, Help/OK/Cancel button box) mirrors
    PeakFittingDialog (src/views/dialogs/data_analysis/peak_fitting_dialog.py)
    — the one this integration was modeled on. The main structural
    difference: Peak Fitting's "source" is one spectrum already on the
    x/y axes it fits; this dialog's source is a whole SET of spectra that
    first have to be collapsed into one (temperature, signal) curve before
    any of the same fit/normalize/output-options machinery applies.
    """

    # Resolution of the baseline-boundary sliders (integer steps mapped
    # onto a temperature range) — 2000 gives sub-0.1-degree precision
    # across a typical ~100-200 degree range without needing float
    # sliders (Qt has none built in).
    _SLIDER_STEPS = 2000

    def __init__(self, parent=None, selected_spectra=None, current_settings=None, saved_fits=None,
                 main_controller=None):
        super().__init__(parent)
        self.setWindowTitle("Melting Curve Analysis")
        self.setModal(True)
        self.selected_spectra = selected_spectra or []
        self.manager = MeltingCurveManager()
        self.current_settings = current_settings or {}
        # Kept for other uses; the temps_table's "Spectrum" column display
        # now reads its own local checkBox_shorten_names instead (see
        # _shorten_names_enabled/_display_labels_map).
        self.main_controller = main_controller

        self.curve = None                # extracted {'x_temperature','y_raw',...}
        self.normalization_result = None  # manager.normalize_melting_curve() output
        self.x_trans = None       # manager.compute_median_crossing_temperature() output
        self.fit_result = None           # manager.fit_sigmoid_model() output
        self._automatic_fit_result = None  # manager.fit_automatic() output, Method="Automatic"
                                          # (Santoro-Bolen) only — None in every other mode.
                                          # normalization_result/x_trans/fit_result above are
                                          # ALSO populated from this in Automatic mode (its
                                          # 'norm'/'Tm_crossing'/'sigmoid_fit' — same shapes
                                          # normalize_melting_curve/compute_median_crossing_
                                          # temperature/fit_sigmoid_model return) so every
                                          # other part of this dialog (plotting, thermo table,
                                          # Fit Details, output spectra) reads them exactly the
                                          # same way regardless of which mode produced them.
                                          # This field itself is kept only for the reliability
                                          # banner and the auto-selected component count.
        self._fit_is_preview = False     # True when fit_result came from _rebuild_fit_from_current_table
                                          # (no curve_fit optimization run), not a real Fit click
        self.component_thermodynamics = None  # manager.compute_component_thermodynamics() output
        self._initial_guesses = []       # pre-fit guesses shown/edited in fit_results_table:
                                          # list of {'factor','midpoint','width'}, empty once a
                                          # real fit exists (table then shows FITTED results instead)
        self._populating_guess_table = False  # re-entrancy guard for itemChanged while we
                                              # populate the table ourselves
        self._original_temperatures = {}  # label -> originally-guessed value; see
                                          # populate_temps_table / revert_to_original_temperatures
        self._external_curve_path = None  # currently selected "From file" source path, if any
        self._external_sheet_names = []   # sheet names of the current Excel file, if any
        self._pending_svd_diagnostics = None  # set by _gather_curve_from_spectra_svd just
                                              # before _finalize_curve reads/clears it
        self._suppress_auto_update = False  # re-entrancy/bulk-op guard for the real-time
                                            # curve rebuild — see _auto_update_curve and
                                            # _on_table_cell_edited

        # A single mutable dict (shared with, and owned by, the
        # MeltingCurveController that created this dialog — see
        # MeltingCurveController.__init__ / show_dialog) holding every
        # fit the user has explicitly chosen to keep with "Save Current
        # Fit", name -> snapshot (same shape as get_results()). Because
        # it's the SAME dict object the controller holds (not a copy),
        # anything saved here is still there the next time this dialog is
        # opened, even for a different spectra selection — the controller
        # instance itself persists for the life of the app session.
        self.saved_fits = saved_fits if saved_fits is not None else {}

        self.ax_main = None              # set by update_plot(); used by the
                                          # interactive 'b'-key baseline picker
        self.key_connection_id = None    # canvas 'key_press_event' connection

        self._slider_domain = (0.0, 1.0)          # (t_lo, t_hi) the 4 baseline
                                                    # sliders currently map onto
        self._syncing_baseline_controls = False    # re-entrancy guard for the
                                                    # slider<->spin two-way sync
        self._baseline_update_timer = QTimer(self)  # debounces live redraws
        self._baseline_update_timer.setSingleShot(True)
        self._baseline_update_timer.timeout.connect(self._live_baseline_update)
        self._baseline_defaults_set = False        # see _finalize_curve

        self.setMinimumSize(1250, 820)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self.setup_ui()
        self.initialize_dialog()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def setup_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        # Wider than Qt's thin default (a few px) — the toolbar's Home/
        # Pan/Zoom buttons sit right at the canvas panel's left edge (see
        # create_canvas_panel), and a handle that narrow makes it easy to
        # miss the drag and land on one of those buttons instead,
        # silently toggling pan/zoom mode or resetting the view without
        # ever meaning to touch either.
        splitter.setHandleWidth(8)
        layout.addWidget(splitter)

        splitter.addWidget(self.create_control_panel())
        splitter.addWidget(self.create_canvas_panel())
        splitter.setSizes([620, 700])

    def create_control_panel(self):
        outer = QWidget()
        outer.setMinimumWidth(420)
        outer.setMaximumWidth(820)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer_layout.addWidget(scroll)

        widget = QWidget()
        scroll.setWidget(widget)
        layout = QVBoxLayout(widget)

        layout.addWidget(self._build_source_group())
        layout.addWidget(self._build_extraction_group())
        layout.addWidget(self._build_normalization_group())
        layout.addWidget(self._build_fit_group())
        layout.addWidget(self._build_output_group())
        layout.addWidget(self._build_saved_fits_group())
        layout.addStretch()

        # --- Dialog Buttons (OK, Cancel, Help) ---
        button_box = QDialogButtonBox()
        self.help_button = QPushButton("Help")
        self.help_button.setToolTip("Show help for the Melting Curve Analysis tool.")
        self.help_button.clicked.connect(self.show_help)
        button_box.addButton(self.help_button, QDialogButtonBox.HelpRole)
        button_box.addButton(QDialogButtonBox.Ok)
        button_box.addButton(QDialogButtonBox.Cancel)
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(True)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        outer_layout.addWidget(button_box)

        return outer

    def _build_saved_fits_group(self):
        group = QGroupBox("Saved Fits")
        v = QVBoxLayout()

        header_row = QHBoxLayout()
        self.saved_fits_toggle_btn = QPushButton("\u25b6 Keep results here to compare across sessions")
        self.saved_fits_toggle_btn.setFlat(True)
        self.saved_fits_toggle_btn.setStyleSheet(
            "QPushButton { text-align: left; border: none; font-weight: bold; }")
        self.saved_fits_toggle_btn.setToolTip("Click to show/hide the saved-fits list and its buttons.")
        self.saved_fits_toggle_btn.clicked.connect(self._toggle_saved_fits_section)
        header_row.addWidget(self.saved_fits_toggle_btn)
        header_row.addStretch()
        header_row.addWidget(self._make_help_button(
            "Saved Fits",
            "This dialog always works on ONE melting curve at a time — extract, "
            "normalize, fit, exactly as usual. \"Saved Fits\" is a separate, "
            "lightweight container for keeping a copy of a finished result "
            "around for comparison, independent of that single active curve.\n\n"
            "\"Save Current Fit\" snapshots everything about the curve you're "
            "working on right now (extraction, normalization, fit, "
            "thermodynamics) under a name you choose. It does NOT save any "
            "spectra — that's still only ever done via Output Options + OK, "
            "exactly as before.\n\n"
            "Saved fits persist even after closing and reopening this dialog "
            "(they're kept for as long as the app stays open — closing the "
            "whole application clears them, same as everything else that isn't "
            "saved as an actual spectrum).\n\n"
            "\"Rename\" renames the selected saved fit. The checkbox next to "
            "each saved fit controls whether it's included "
            "the next time you click \"Show Summary\" — uncheck any you want to "
            "leave out without deleting them. \"Remove Selected\"/\"Remove All\" "
            "delete entries from the container entirely."))
        v.addLayout(header_row)

        self.saved_fits_content_widget = QWidget()
        content_v = QVBoxLayout(self.saved_fits_content_widget)
        content_v.setContentsMargins(0, 0, 0, 0)

        self.saved_fits_list = QListWidget()
        self.saved_fits_list.setMaximumHeight(110)
        self.saved_fits_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.saved_fits_list.setToolTip(
            "Checkbox: include in Show Summary.\nClick to select for Remove Selected.")
        content_v.addWidget(self.saved_fits_list)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save Current Fit")
        save_btn.setToolTip("Snapshot the curve you're currently working on into this container.")
        save_btn.clicked.connect(self.save_current_fit)
        # Same accent color as Extract Curve/Fit — another key "primary
        # action" button in this workflow.
        save_btn.setStyleSheet(
            "QPushButton { background-color: #4a90d9; color: white; font-weight: bold; "
            "padding: 4px 12px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #5b9ee0; }"
            "QPushButton:pressed { background-color: #3d7fc4; }")
        btn_row.addWidget(save_btn)
        rename_btn = QPushButton("Rename")
        rename_btn.setToolTip(
            "Rename the selected saved fit(s) — or all of them if none\n"
            "are selected. Opens a table you can edit or paste into.")
        rename_btn.clicked.connect(self.rename_selected_fits)
        btn_row.addWidget(rename_btn)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_selected_fits)
        btn_row.addWidget(remove_btn)
        remove_all_btn = QPushButton("Remove All")
        remove_all_btn.clicked.connect(self.remove_all_fits)
        btn_row.addWidget(remove_all_btn)
        summary_btn = QPushButton("Show Summary")
        summary_btn.setToolTip("List every CHECKED saved fit's key results together.")
        summary_btn.clicked.connect(self.show_fit_summary)
        btn_row.addWidget(summary_btn)
        overlay_btn = QPushButton("Show Overlay Plot")
        overlay_btn.setToolTip(
            "Plot every CHECKED saved fit's normalized curve and sigmoid fit\n"
            "superimposed on one set of axes, color-coded — see shape\n"
            "differences directly, not just the numbers in Show Summary.")
        overlay_btn.clicked.connect(self.show_fit_overlay)
        btn_row.addWidget(overlay_btn)
        content_v.addLayout(btn_row)

        v.addWidget(self.saved_fits_content_widget)
        self.saved_fits_content_widget.setVisible(False)  # collapsed by default to save space

        group.setLayout(v)
        return group

    def _toggle_saved_fits_section(self):
        visible = not self.saved_fits_content_widget.isVisible()
        self.saved_fits_content_widget.setVisible(visible)
        self.saved_fits_toggle_btn.setText(
            ("\u25bc" if visible else "\u25b6") + " Keep results here to compare across sessions")

    def _build_source_group(self):
        group = QGroupBox("Curve Data (Temperature / Signal)")
        v = QVBoxLayout()

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Double-click a cell to edit it."))
        header_row.addStretch()
        self.show_spectrum_names_check = QCheckBox("Show spectrum names")
        self.show_spectrum_names_check.setChecked(True)
        self.show_spectrum_names_check.setToolTip(
            "Only meaningful in \"From spectra\" mode — the Spectrum\n"
            "column is always blank when a curve is loaded from a file.")
        self.show_spectrum_names_check.stateChanged.connect(self._on_show_spectrum_names_toggled)
        header_row.addWidget(self.show_spectrum_names_check)
        # Display-only "shorten names" toggle — this dialog's own,
        # independent on/off state (see label_shortening.py's
        # make_shorten_names_checkbox), unrelated to the main window's
        # checkbox and always starting unchecked.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _state: self.temps_table.viewport().update())
        header_row.addWidget(self.checkBox_shorten_names)
        reset_btn = QPushButton("Reset")
        reset_btn.setMaximumWidth(55)
        reset_btn.setToolTip(
            "Restore every X (Temperature) value to what it was originally\n"
            "guessed as when this dialog was first opened, discarding\n"
            "any edits made since (asks for confirmation first).")
        reset_btn.clicked.connect(self.revert_to_original_temperatures)
        header_row.addWidget(reset_btn)
        header_row.addWidget(self._make_help_button(
            "Curve Data (Temperature / Signal)",
            "One row per data point of the melting curve: <b>X</b> is the "
            "temperature, <b>Y</b> is the signal at that temperature. Double-click "
            "a cell to edit it directly.\n\n"
            "In \"From spectra\" mode (see Curve Extraction below): one row per "
            "selected spectrum. X is pre-filled by guessing from each spectrum's "
            "label (never trusted as final — always check it); Y is filled in "
            "automatically whenever you click Extract Curve, reading the signal at "
            "the chosen X position from each spectrum. The Spectrum column shows "
            "which row belongs to which spectrum — uncheck \"Show spectrum names\" "
            "to hide it if you don't need it.\n\n"
            "In \"From file\" mode: clicking Extract Curve replaces the table's "
            "rows entirely with whatever (temperature, signal) pairs were loaded "
            "from the file — there's no Spectrum column to show there.\n\n"
            "Excel-like copy/paste is supported on X and Y: select one or more "
            "cells and press Ctrl+C to copy them (tab/newline-separated, pastes "
            "straight into a spreadsheet), Ctrl+X to cut (copy, then clear), or "
            "Delete/Backspace to just clear them. Select a starting cell and press "
            "Ctrl+V to paste a column of values copied from Excel or a text file — "
            "one value per row, filling downward from the selected cell.\n\n"
            "Click a column header to sort by that column — click again to "
            "reverse the direction.\n\n"
            "\"Reset\" restores every X (Temperature) value to what it was "
            "originally guessed as when this dialog was first opened, discarding "
            "any edits made since (with a confirmation first)."))
        v.addLayout(header_row)

        self.temps_table = QTableWidget()
        self.temps_table.setColumnCount(3)
        self.temps_table.setHorizontalHeaderLabels(["Spectrum", "X (Temperature)", "Y (Signal)"])
        self.temps_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.temps_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.temps_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.temps_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.temps_table.setSelectionMode(QAbstractItemView.ContiguousSelection)
        self.temps_table.setItemDelegate(_EnterCommitDelegate(self.temps_table))
        self.temps_table.setToolTip(
            "Ctrl+C copy, Ctrl+X cut, Ctrl+V paste, Delete clears (e.g. from Excel).\n"
            "Click a column header to sort by it (click again to reverse).")
        self.temps_table.installEventFilter(self)
        self.temps_table.itemChanged.connect(self._on_table_cell_edited)
        self.temps_table.setMinimumHeight(140)
        self.temps_table.setMaximumHeight(220)
        # Native click-to-sort on column headers — standard Qt behavior,
        # toggling ascending/descending on repeated clicks, with a sort-
        # indicator arrow drawn in the header automatically. Columns 1/2
        # sort numerically (not alphabetically) because every item placed
        # in them also carries a float in its EditRole — see
        # _numeric_item(). Bulk-write methods that fill many rows in a
        # fixed order (populate_temps_table, paste, etc.) briefly disable
        # this around their loop, since a live re-sort mid-populate would
        # otherwise scramble which row corresponds to which spectrum.
        self.temps_table.setSortingEnabled(True)
        # Paint-only — item.text() in column 0 stays the full label
        # (relied on for the label->row lookup in load_settings' cache-
        # restore path), only what's painted on screen is shortened.
        self.temps_table.setItemDelegateForColumn(
            0, make_display_text_delegate(self._display_labels_map, parent=self.temps_table))
        v.addWidget(self.temps_table)

        group.setLayout(v)
        return group

    # ------------------------------------------------------------------ #
    # Shorten names (this dialog's own independent checkbox — see        #
    # _build_source_group; no longer tied to the main window's)          #
    # ------------------------------------------------------------------ #

    def _shorten_names_enabled(self) -> bool:
        return self.checkBox_shorten_names.isChecked()

    def _display_labels_map(self) -> dict:
        """{full_label: display_label} for self.selected_spectra, honoring
        the shorten-names checkbox — identity map when disabled. Display
        only; every identity/lookup use in this dialog (label_to_row,
        source_labels, y_by_label, etc.) reads item.text() or
        spec['label'] directly and is untouched by this."""
        return shorten_spectra_labels(self.selected_spectra, self._shorten_names_enabled())

    def _numeric_item(self, value, editable=True):
        """A table cell for the X/Y columns that sorts numerically (see
        _NumericTableWidgetItem) rather than alphabetically as a plain
        QTableWidgetItem would."""
        item = _NumericTableWidgetItem(f"{value:g}")
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def eventFilter(self, obj, event):
        """Ctrl+C / Ctrl+X / Ctrl+V / Delete on the temperature table — see
        _copy_temps_selection / _cut_temps_selection / _paste_temps_selection
        / _clear_temps_selection. Installed on temps_table itself (not the
        whole dialog) so it only intercepts key presses while that table
        actually has focus. Also handles the same shortcuts on the bulk
        Rename Saved Fits dialog's table (self._rename_table, only set
        while that dialog is open) — see rename_selected_fits."""
        if obj is self.temps_table and event.type() == event.KeyPress:
            if event.matches(QKeySequence.Copy):
                self._copy_temps_selection()
                return True
            if event.matches(QKeySequence.Cut):
                self._cut_temps_selection()
                return True
            if event.matches(QKeySequence.Paste):
                self._paste_temps_selection()
                return True
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self._clear_temps_selection()
                return True
        if (getattr(self, '_rename_table', None) is obj and event.type() == event.KeyPress):
            if event.matches(QKeySequence.Copy):
                self._copy_rename_selection()
                return True
            if event.matches(QKeySequence.Cut):
                self._copy_rename_selection()
                self._clear_rename_selection()
                return True
            if event.matches(QKeySequence.Paste):
                self._paste_rename_selection()
                return True
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self._clear_rename_selection()
                return True
        return super().eventFilter(obj, event)

    def _copy_rename_selection(self):
        rows = sorted({idx.row() for idx in self._rename_table.selectedIndexes()})
        lines = [self._rename_table.item(r, 1).text() if self._rename_table.item(r, 1) else ""
                for r in rows]
        QApplication.clipboard().setText("\n".join(lines))

    def _clear_rename_selection(self):
        rows = sorted({idx.row() for idx in self._rename_table.selectedIndexes()})
        for r in rows:
            self._rename_table.setItem(r, 1, QTableWidgetItem(""))

    def _paste_rename_selection(self):
        text = QApplication.clipboard().text()
        if not text:
            return
        values = [line.split('\t')[0] for line in text.splitlines()]
        rows = sorted({idx.row() for idx in self._rename_table.selectedIndexes()})
        start_row = rows[0] if rows else self._rename_table.currentRow()
        if start_row < 0:
            start_row = 0
        n_rows = self._rename_table.rowCount()
        for offset, val in enumerate(values):
            row = start_row + offset
            if row >= n_rows:
                break
            self._rename_table.setItem(row, 1, QTableWidgetItem(val.strip()))

    def _selected_temp_cells(self):
        """(row, col) pairs touched by the current selection, restricted
        to columns 1 (X/Temperature) and 2 (Y/Signal) — column 0
        (Spectrum) is never editable, so copy/cut/paste/clear silently
        ignore it even if it happens to be part of a dragged selection."""
        return sorted((idx.row(), idx.column()) for idx in self.temps_table.selectedIndexes()
                     if idx.column() in (1, 2))

    def _copy_temps_selection(self):
        """Copy the selected X/Y cells to the clipboard as a tab/newline-
        separated block — pastes straight into Excel, or back into this
        same table (or another one) via Ctrl+V. A selection spanning just
        one column copies a single column of values, same as before;
        spanning both X and Y copies a proper two-column block."""
        cells = self._selected_temp_cells()
        if not cells:
            return
        rows = sorted({r for r, c in cells})
        cols = sorted({c for r, c in cells})
        lines = []
        for r in rows:
            parts = [self.temps_table.item(r, c).text() if self.temps_table.item(r, c) else ""
                    for c in cols]
            lines.append("\t".join(parts))
        QApplication.clipboard().setText("\n".join(lines))

    def _cut_temps_selection(self):
        """Ctrl+X: copy the selection (see _copy_temps_selection), then
        clear it — same as Excel's cut."""
        self._copy_temps_selection()
        self._clear_temps_selection()

    def _clear_temps_selection(self):
        """Delete/Backspace (or the second half of Cut): clear the
        selected X/Y cells. Left blank rather than e.g. reset to a
        guessed default — an empty cell is an obvious, unambiguous
        "needs a value" state, and _read_temperatures() already refuses
        to extract with a clear message if X is left blank."""
        self._suppress_auto_update = True
        for r, c in self._selected_temp_cells():
            self.temps_table.setItem(r, c, QTableWidgetItem(""))
        self._suppress_auto_update = False
        self._auto_update_curve()

    def _paste_temps_selection(self):
        """Paste a tab/newline-separated block of values (e.g. copied
        from Excel, or from _copy_temps_selection above) into the table,
        starting at the current/first-selected cell and filling downward
        (and rightward, for a 2-column paste) — stops at the table's
        edges. A single-column paste only ever touches the column it
        started in; a two-column paste fills X then Y."""
        text = QApplication.clipboard().text()
        if not text:
            return
        rows_of_values = [line.split('\t') for line in text.splitlines() if line.strip() != ""]
        if not rows_of_values:
            return
        cells = self._selected_temp_cells()
        if cells:
            start_row, start_col = cells[0]
        else:
            start_row = self.temps_table.currentRow()
            start_col = self.temps_table.currentColumn()
        if start_row < 0:
            start_row = 0
        if start_col not in (1, 2):
            start_col = 1
        self._fill_curve_data_from(start_row, start_col, rows_of_values)

    def _fill_curve_data_from(self, start_row, start_col, rows_of_values):
        """Shared fill logic for paste: write rows_of_values (each a list
        of 1-2 tab-split strings) into the table starting at
        (start_row, start_col), filling down and — for rows with more
        than one value — rightward too (X then Y), skipping non-numeric
        values (warning once, at the end, listing which cells were
        skipped rather than aborting the whole paste over one bad
        value). Never writes past column 2 (Y) or row/column 0."""
        n_rows = self.temps_table.rowCount()
        skipped = []
        # Sorting MUST be off for the whole loop, not just per-cell — with
        # it on, writing into the currently-sorted column could re-sort
        # the table between iterations, so "row start_row + offset" would
        # stop meaning the same thing partway through the paste. Same
        # reasoning for suppressing the real-time update until the whole
        # paste has landed, rather than once per cell.
        self._suppress_auto_update = True
        self.temps_table.setSortingEnabled(False)
        for offset, values in enumerate(rows_of_values):
            row = start_row + offset
            if row >= n_rows:
                break
            for col_offset, raw in enumerate(values):
                col = start_col + col_offset
                if col > 2:
                    break
                raw = raw.strip()
                if raw == "":
                    continue
                try:
                    val = float(raw)
                    if not np.isfinite(val):
                        raise ValueError
                except ValueError:
                    skipped.append((row + 1, col))
                    continue
                self.temps_table.setItem(row, col, self._numeric_item(val))
        self.temps_table.setSortingEnabled(True)
        self._suppress_auto_update = False
        self._auto_update_curve()
        if skipped:
            rows_txt = ", ".join(str(r) for r, c in skipped)
            QMessageBox.warning(
                self, "Some Values Skipped",
                f"Row(s) {rows_txt} had a non-numeric value and were left unchanged.")

    def _build_extraction_group(self):
        group = QGroupBox("Curve Extraction")
        v = QVBoxLayout()

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Source:"))
        self.source_spectra_radio = QRadioButton("From spectra")
        self.source_spectra_radio.setChecked(True)
        self.source_file_radio = QRadioButton("From file")
        self.source_spectra_radio.toggled.connect(self._on_source_mode_changed)
        source_row.addWidget(self.source_spectra_radio)
        source_row.addWidget(self.source_file_radio)
        source_row.addWidget(self._make_help_button(
            "Curve Extraction \u2014 Source",
            "\"From spectra\" (default): build the melting curve by reading one "
            "signal value from each selected spectrum at X, as described below.\n\n"
            "\"From file\": skip spectra entirely and load an already-built melting "
            "curve \u2014 temperature and signal pairs \u2014 directly from a text or Excel "
            "file. Useful if you already processed the curve elsewhere, or "
            "received it from someone else.\n\n"
            "Expected file format: two columns, Temperature then Signal. Plain "
            "text files (.txt/.csv/.dat) can be comma-, tab-, or whitespace-"
            "separated; an optional header row (non-numeric first line) is "
            "detected and skipped automatically. Excel files (.xlsx/.xls) use "
            "the first two columns of the first sheet the same way.\n\n"
            "You can switch between the two sources at any time \u2014 the curve "
            "rebuilds automatically under whichever is currently selected. "
            "Whatever curve/fit is currently shown resets when you switch, or "
            "when X, the Averaging window, or Sheet changes, and rebuilds under "
            "the new settings right away."))
        source_row.addSpacing(16)
        source_row.addWidget(QLabel("Curve name:"))
        self.curve_name_edit = QLineEdit("melting_curve")
        source_row.addWidget(self.curve_name_edit)
        source_row.addStretch()
        v.addLayout(source_row)

        # Each of these three rows is only relevant to one source (or, for
        # the Sheet row, only to Excel files within "From file") -- wrapped
        # in its own container widget so the whole row can be hidden as a
        # unit via _on_source_mode_changed, rather than just grayed out.
        self.file_row_widget = QWidget()
        file_row = QHBoxLayout(self.file_row_widget)
        file_row.setContentsMargins(0, 0, 0, 0)
        self.external_file_edit = QLineEdit()
        self.external_file_edit.setReadOnly(True)
        self.external_file_edit.setPlaceholderText("No file selected")
        file_row.addWidget(self.external_file_edit)
        self.browse_file_btn = QPushButton("Browse...")
        self.browse_file_btn.clicked.connect(self.browse_external_curve_file)
        file_row.addWidget(self.browse_file_btn)
        v.addWidget(self.file_row_widget)
        self.file_row_widget.setVisible(False)

        self.sheet_row_widget = QWidget()
        sheet_row = QHBoxLayout(self.sheet_row_widget)
        sheet_row.setContentsMargins(0, 0, 0, 0)
        sheet_row.addWidget(QLabel("Sheet:"))
        self.sheet_combo = QComboBox()
        self.sheet_combo.setToolTip(
            "Which sheet's curve to load \u2014 an Excel workbook can hold\n"
            "one melting curve per sheet.")
        self.sheet_combo.currentIndexChanged.connect(self._on_extraction_params_changed)
        sheet_row.addWidget(self.sheet_combo, stretch=1)
        v.addWidget(self.sheet_row_widget)
        self.sheet_row_widget.setVisible(False)

        self.extraction_method_row_widget = QWidget()
        method_row = QHBoxLayout(self.extraction_method_row_widget)
        method_row.setContentsMargins(0, 0, 0, 0)
        method_row.addWidget(QLabel("Method:"))
        self.extraction_method_combo = QComboBox()
        self.extraction_method_combo.addItems(["Extract signal at X", "SVD (generalized curve)"])
        self.extraction_method_combo.setToolTip(
            "Extract signal at X: read one signal value from each spectrum at a chosen\n"
            "x position (below) — the original approach.\n\n"
            "SVD (generalized curve): build the melting curve from the whole measured\n"
            "spectral range at once via SVD, the same approach MeltAnalytiX uses — no\n"
            "single x position to pick. Click ? for details.")
        self.extraction_method_combo.currentIndexChanged.connect(self._on_extraction_method_changed)
        method_row.addWidget(self.extraction_method_combo)
        method_row.addWidget(self._make_help_button(
            "Extraction method — Extract signal at X / SVD",
            "Two ways to turn the selected spectra into one melting curve (temperature "
            "vs. signal), only relevant in \"From spectra\" mode:\n\n"
            "\"Extract signal at X\" (default, this app's original approach): reads one "
            "signal value from each spectrum at a single, chosen x position (wavelength/"
            "wavenumber), optionally averaged over a small window around it. Simple and "
            "transparent, but sensitive to noise or an isosbestic point sitting exactly "
            "at that one x position, and requires picking a representative x by hand.\n\n"
            "\"SVD (generalized curve)\": ported from this app's sister tool MeltAnalytiX "
            "and matching the convention SpecAnalytiXBase's own SVD Analysis tool uses. "
            "Instead of one x position, this decomposes the WHOLE (wavelength x spectrum) "
            "matrix via SVD and uses the first singular component's own across-spectrum "
            "trajectory as the melting curve — a summary of how the entire spectral "
            "shape changes, not just one point on it. By default each wavelength's row is "
            "mean-centered (its own across-spectrum average subtracted) before the SVD "
            "runs — uncentered SVD's first component tends to just reproduce the plain "
            "per-spectrum average instead of the real transition shape (uncheck "
            "\"Mean-center\" only to compare against that original, uncentered behavior).\n\n"
            "Requires every selected spectrum to share the exact same x-axis grid (same "
            "wavelengths/wavenumbers) — if they don't, extraction fails with a message "
            "naming the mismatched spectrum; re-sample/crop onto a common grid first, or "
            "use \"Extract signal at X\" instead, which has no such requirement.\n\n"
            "Everything downstream — Normalization, Sigmoid Fit, Automatic mode, Output "
            "Options — works exactly the same regardless of which extraction method built "
            "the curve; only how the raw (temperature, signal) curve itself is built "
            "differs."))
        method_row.addStretch()
        v.addWidget(self.extraction_method_row_widget)

        self.xvalue_row_widget = QWidget()
        row1 = QHBoxLayout(self.xvalue_row_widget)
        row1.setContentsMargins(0, 0, 0, 0)
        row1.addWidget(QLabel("Extract signal at X ="))
        self.x_value_spin = QDoubleSpinBox()
        self.x_value_spin.setDecimals(4)
        self.x_value_spin.setRange(-1e9, 1e9)
        self.x_value_spin.setMaximumWidth(110)
        self.x_value_spin.setKeyboardTracking(False)
        self.x_value_spin.setToolTip(
            "The x-axis position (e.g. wavenumber) to read one y-value\n"
            "from each spectrum, building the melting curve — updates\n"
            "in real time as you change it (Enter / click elsewhere /\n"
            "the arrows, not per keystroke while typing).\n"
            "Uses linear interpolation.")
        self.x_value_spin.valueChanged.connect(self._on_extraction_params_changed)
        row1.addWidget(self.x_value_spin)
        row1.addSpacing(16)
        row1.addWidget(QLabel("Averaging window +/-"))
        self.window_spin = QDoubleSpinBox()
        self.window_spin.setDecimals(4)
        self.window_spin.setRange(0.0, 1e9)
        self.window_spin.setMaximumWidth(110)
        self.window_spin.setKeyboardTracking(False)
        self.window_spin.setToolTip(
            "Optional: average all points within this distance of X\n"
            "instead of a single interpolated point.\n"
            "0 = interpolate exactly at X.")
        self.window_spin.valueChanged.connect(self._on_extraction_params_changed)
        row1.addWidget(self.window_spin)
        row1.addStretch()
        v.addWidget(self.xvalue_row_widget)

        self.svd_options_row_widget = QWidget()
        svd_row = QHBoxLayout(self.svd_options_row_widget)
        svd_row.setContentsMargins(0, 0, 0, 0)
        self.svd_center_check = QCheckBox("Mean-center each wavelength before SVD")
        self.svd_center_check.setChecked(True)
        self.svd_center_check.setToolTip(
            "Recommended default (matches MeltAnalytiX). Subtracts each wavelength's\n"
            "own across-spectrum mean before the SVD runs — without this, the first\n"
            "component tends to just reproduce the plain per-spectrum average rather\n"
            "than the real transition shape. Uncheck only to compare against the\n"
            "original, uncentered behavior.")
        self.svd_center_check.stateChanged.connect(self._on_extraction_params_changed)
        svd_row.addWidget(self.svd_center_check)
        svd_row.addStretch()
        v.addWidget(self.svd_options_row_widget)
        self.svd_options_row_widget.setVisible(False)

        self.svd_diagnostics_label = QLabel("")
        self.svd_diagnostics_label.setWordWrap(True)
        self.svd_diagnostics_label.setVisible(False)
        v.addWidget(self.svd_diagnostics_label)

        group.setLayout(v)
        return group


    def _build_normalization_group(self):
        group = QGroupBox("Normalization (linear baselines)")
        v = QVBoxLayout()

        row0 = QHBoxLayout()
        row0.addWidget(QLabel("Method:"))
        self.norm_combo = QComboBox()
        self.norm_combo.addItems(["None", "Zero order (constant)", "First order (linear)",
                                  "Automatic (Santoro-Bolen fit)"])
        self.norm_combo.setCurrentIndex(2)
        self.norm_combo.setToolTip(
            "None/Zero order/First order: this app's original manual workflow — you "
            "choose the Low-T/High-T baseline regions below (by dragging the sliders, "
            "editing the spin boxes, or the 'b' key), each fit independently as its own "
            "straight line (or constant, for Zero order).\n\n"
            "Automatic (Santoro-Bolen fit): a new, opt-in mode that fits both baselines "
            "AND the transition(s) together in one joint regression against the raw "
            "curve, choosing the transition midpoint(s) and the number of components "
            "(1-4) itself — no baseline windows or component count to set by hand. "
            "Click ? for details. Manual stays the default; switch back to it at any "
            "time with no loss of your baseline region settings.")
        self.norm_combo.currentIndexChanged.connect(self._on_norm_method_changed)
        row0.addWidget(self.norm_combo)
        row0.addWidget(self._make_help_button(
            "Automatic (Santoro-Bolen fit) mode",
            "Ported from this app's sister tool MeltAnalytiX, where the same joint "
            "fit replaced an older two-stage \"search for where the baseline windows "
            "are, then fit a straight line to each\" pipeline.\n\n"
            "Instead of you choosing Low-T/High-T baseline windows and a component "
            "count, Automatic mode fits the native-state baseline, the denatured-"
            "state baseline, AND the transition(s) themselves all in ONE simultaneous "
            "nonlinear regression against the raw curve — a two-state (or, for a "
            "genuinely multiphasic curve, shared-baseline multi-state) model. The "
            "number of components (1-4) is chosen automatically via BIC (a standard "
            "statistical test for \"is one more transition actually justified by the "
            "data\"), walked up one at a time and warm-started from the smaller fit's "
            "own answer, and is only adopted when it doesn't make the resulting van't "
            "Hoff/Arrhenius fit or the baseline's own tracking of the data at the "
            "curve's edges meaningfully worse — plain BIC alone can be fooled by a "
            "smooth extra component absorbing structured noise rather than a genuine "
            "additional transition.\n\n"
            "The Low-T/High-T region controls and the Components spinner are disabled "
            "in this mode (Automatic determines both) but still show the fitted "
            "result's own descriptive extents/count. A banner above the plot reports "
            "whether Automatic mode found a fit at all, and — separately — whether "
            "that fit passes the same reliability checks (Arrhenius R^2, sigmoid-fit "
            "R^2, Tm falling inside both the measured range and the actual fit "
            "window, baselines not crossing near the transition, and the baseline "
            "tracking the data closely at both edges) MeltAnalytiX itself uses to "
            "flag a run as trustworthy or not. A rejected or low-confidence result "
            "is exactly when to switch back to Manual mode and set the baseline "
            "windows yourself — Automatic mode never silently falls back to a "
            "different heuristic on its own."))
        row0.addSpacing(16)
        row0.addWidget(QLabel("Threshold (span):"))
        self.span_spin = QDoubleSpinBox()
        self.span_spin.setRange(0.5, 0.999)
        self.span_spin.setSingleStep(0.01)
        self.span_spin.setValue(0.95)
        self.span_spin.setMaximumWidth(90)
        self.span_spin.setToolTip(
            "For the Arrhenius-based per-component thermodynamics under\n"
            "Sigmoid Fit below — keeps points where the normalized signal\n"
            "is between (1-threshold) and threshold, discarding points\n"
            "near either baseline where ln(K) diverges toward\n"
            "+/-infinity — the Arrhenius relationship (ln(K) linear in\n"
            "1/T) only holds LOCALLY, near the transition; points close\n"
            "to either baseline have very large |ln(K)| and would\n"
            "dominate/distort a straight-line fit through pure numerical\n"
            "sensitivity, not real signal. Points kept for the fit are\n"
            "shown in red on the normalized-curve plot below. Doesn't\n"
            "affect the sigmoid SHAPE fit itself — only the Arrhenius\n"
            "calculations derived from it.\n\n"
            "Noisy data needs more attention here: a single noisy outlier\n"
            "near a baseline gets hugely amplified once transformed into\n"
            "ln(K) (the log diverges fastest exactly there), and can pull\n"
            "an entire regression line off course even though it's just\n"
            "one bad point. Tightening the threshold by even a few\n"
            "percent to exclude it can noticeably change the result —\n"
            "if deltaH/deltaS/Tm seem to shift a lot for a small threshold\n"
            "change, check the per-component Arrhenius plot for a lone\n"
            "point sitting far from the rest of the trend, rather than\n"
            "assuming the fit itself is unstable.")
        self.span_spin.valueChanged.connect(self._on_span_changed)
        row0.addWidget(self.span_spin)
        row0.addWidget(self._make_help_button(
            "Threshold (span)",
            "The Arrhenius relationship (ln(K) linear in 1/T) only holds LOCALLY, "
            "near the transition itself — not across the whole curve. Close to "
            "either baseline, A_corr approaches 0 or 1, so K approaches 0 or "
            "infinity and ln(K) diverges to large positive/negative values; those "
            "points would dominate a straight-line fit through sheer numerical "
            "sensitivity, not real signal, and bias the result.\n\n"
            "Threshold keeps only points where the normalized signal is between "
            "(1-threshold) and threshold — the points actually used are shown in "
            "red on the normalized-curve plot — restricting the fit to the region "
            "where the linear approximation is actually valid.\n\n"
            "Lives here, in Normalization, since it's really part of preparing the "
            "curve before any Arrhenius-based analysis runs, similar in spirit to "
            "the baseline settings below it — rather than belonging to Sigmoid "
            "Fit's own guesses/fitting logic specifically. It governs the "
            "per-component Arrhenius calculations under Sigmoid Fit below "
            "(available for any component count), and stays live as you change "
            "it, whether or not a fit has been run yet.\n\n"
            "IMPORTANT — this does NOT affect the sigmoid SHAPE fit itself "
            "(the midpoint/width numbers in the \"Starting guesses / fit results\" "
            "table under Sigmoid Fit): that fit always uses every point, since it "
            "needs the full curve shape including the baseline regions to resolve "
            "properly. Threshold only restricts which points feed the DERIVED "
            "Arrhenius/thermodynamics calculations (Tm, deltaH, deltaS — shown in "
            "the collapsible thermodynamics table, a completely different table "
            "from the fit's own midpoint/width). Changing it will never move the "
            "sigmoid fit's own numbers, only the thermodynamics ones.\n\n"
            "WHY NOISY DATA NEEDS MORE ATTENTION HERE: noisier spectra tend to give "
            "noisier low-T/high-T baseline estimates, which in turn makes stray "
            "outlier points more likely to show up on the normalized transition "
            "curve. Those outliers get hugely AMPLIFIED once transformed into "
            "ln(K) — the transform diverges fastest exactly near the baselines, so "
            "a single bad point there can dominate and skew an entire regression "
            "line, even though visually it looked like just one point out of many "
            "on the normalized curve itself. If deltaH/deltaS/Tm shift by a "
            "surprising amount for a small Threshold change (e.g. 0.95 to 0.94), "
            "that's usually a sign one or two outlier points were just included or "
            "excluded — check the per-component Arrhenius plot for a point sitting "
            "noticeably off the trend the others follow, rather than assuming the "
            "underlying fit is unstable. This is exactly why Threshold is "
            "adjustable rather than fixed: the \"right\" span genuinely depends on "
            "how clean the data is."))
        row0.addStretch()
        v.addLayout(row0)

        show_row = QHBoxLayout()
        self.show_original_check = QCheckBox("Show original curve")
        self.show_original_check.setChecked(True)
        self.show_original_check.setToolTip(
            "Checked by default. If you uncheck this, baseline picking\n"
            "(the 'b' key) and the toolbar's Home/zoom/pan stop working,\n"
            "since they act on this panel specifically.")
        self.show_original_check.stateChanged.connect(self._on_plot_visibility_toggled)
        self.show_normalized_check = QCheckBox("Show normalized curve")
        self.show_normalized_check.setChecked(True)
        self.show_normalized_check.stateChanged.connect(self._on_plot_visibility_toggled)
        show_row.addWidget(self.show_original_check)
        show_row.addWidget(self.show_normalized_check)

        self.invert_display_check = QCheckBox("Invert display (1\u21920)")
        self.invert_display_check.setToolTip(
            "Display only — flips which end of the y-axis is up, so the\n"
            "curve trace looks like it descends (matching a raw curve\n"
            "whose signal falls with temperature), the same way many\n"
            "people are used to seeing melting curves plotted.\n\n"
            "Doesn't change any underlying data: the fit, Arrhenius\n"
            "calculation, and every reported number keep using the same\n"
            "0-at-low-T / 1-at-high-T convention regardless of this\n"
            "setting — only the picture flips, not the math.")
        self.invert_display_check.stateChanged.connect(self._on_plot_visibility_toggled)
        show_row.addWidget(self.invert_display_check)

        self.pick_baseline_check = QCheckBox("Pick baselines interactively")
        self.pick_baseline_check.setChecked(True)
        self.pick_baseline_check.setToolTip("Click ? for how this works.")
        show_row.addWidget(self.pick_baseline_check)
        show_row.addWidget(self._make_help_button(
            "Picking baselines interactively on the plot",
            "When checked: click the plot once to give it keyboard focus, use the "
            "toolbar's zoom (magnifying glass) or pan tool to frame a baseline region, "
            "then press the 'b' key.\n\n"
            "The framed x-range is captured as the Low-T or High-T baseline region, "
            "whichever it's nearer to (by temperature). Repeat for the other region — "
            "each press of 'b' resets the view back to the full curve automatically, "
            "so there's no need to press the Home button in between."))
        show_row.addStretch()
        v.addLayout(show_row)

        # Text is rebuilt each time by _update_baseline_cross_warning (see
        # perform_normalization) \u2014 this initial text is only a placeholder
        # until the first normalization runs, since the real message
        # needs the actual excluded-point count for THIS curve.
        self.baseline_cross_warning = QLabel(
            "\u26a0 Low-T and High-T baselines cross within this curve's own range \u2014 "
            "normalization is dividing by a near-zero number close to the crossing "
            "point, causing the huge/meaningless excursions you'll see there. Try "
            "narrower or better-placed baseline regions.")
        self.baseline_cross_warning.setWordWrap(True)
        self.baseline_cross_warning.setStyleSheet(
            "color: #b45309; background-color: #fff3cd; padding: 4px; border-radius: 3px;")
        self.baseline_cross_warning.setVisible(False)
        v.addWidget(self.baseline_cross_warning)

        # Automatic (Santoro-Bolen) mode's own status banner — hidden
        # outside that mode. Text/color set by _update_automatic_fit_banner:
        # red (fit rejected outright), amber (fit found but didn't pass
        # every reliability gate), or green (fit found and reliable).
        self.automatic_fit_banner = QLabel("")
        self.automatic_fit_banner.setWordWrap(True)
        self.automatic_fit_banner.setVisible(False)
        v.addWidget(self.automatic_fit_banner)

        v.addWidget(self._bound_label("Low-T region"))
        self.low_min_spin, self.low_min_slider = self._build_bound_row(v, "min")
        self.low_max_spin, self.low_max_slider = self._build_bound_row(v, "max")

        v.addWidget(self._bound_label("High-T region"))
        self.high_min_spin, self.high_min_slider = self._build_bound_row(v, "min")
        self.high_max_spin, self.high_max_slider = self._build_bound_row(v, "max")

        # Wire slider <-> spin box live sync — dragging a slider updates
        # its spin box (and vice versa when typing), and either one
        # schedules a debounced live recompute/redraw. See
        # _sync_spin_from_slider / _sync_slider_from_spin /
        # _schedule_live_baseline_update below for the full mechanism
        # (mirrors the interactive slider-driven baseline adjustment the
        # original thermoanalysis prototype had).
        for spin, slider in ((self.low_min_spin, self.low_min_slider),
                             (self.low_max_spin, self.low_max_slider),
                             (self.high_min_spin, self.high_min_slider),
                             (self.high_max_spin, self.high_max_slider)):
            slider.valueChanged.connect(
                lambda v, s=spin, sl=slider: self._sync_spin_from_slider(s, sl, v))
            spin.valueChanged.connect(
                lambda v, s=spin, sl=slider: self._sync_slider_from_spin(s, sl, v))

        # Enforce min <= max for each region — without this, dragging the
        # "min" slider/spin past "max" (or vice versa) silently inverts
        # the pair (exactly the "High-T Min=114.44 > Max=95.09" state
        # reported), which is both meaningless (a region can't have its
        # min above its max) and was leaving the sliders looking "stuck"
        # afterward. Implemented by nudging the OTHER spin's VALUE (not
        # its allowed range via setMinimum/setMaximum — that was tried
        # first, but permanently narrows each spin's [t_min, t_max] range
        # based on whatever transient value the other one had at setup
        # time, which is exactly what corrupted high_min_spin down to a
        # single-point range during extraction). Pushing the other
        # boundary's value along instead is standard two-handle-range-
        # slider behavior, keeps each spin's true [t_min, t_max] domain
        # (set in perform_extraction) untouched, and re-syncs that spin's
        # own slider automatically through the normal valueChanged path
        # above — no separate "keep orientation" toggle needed, since
        # inversion is simply not reachable in the first place.
        self.low_min_spin.valueChanged.connect(
            lambda v: self.low_max_spin.setValue(v) if v > self.low_max_spin.value() else None)
        self.low_max_spin.valueChanged.connect(
            lambda v: self.low_min_spin.setValue(v) if v < self.low_min_spin.value() else None)
        self.high_min_spin.valueChanged.connect(
            lambda v: self.high_max_spin.setValue(v) if v > self.high_max_spin.value() else None)
        self.high_max_spin.valueChanged.connect(
            lambda v: self.high_min_spin.setValue(v) if v < self.high_min_spin.value() else None)

        # No "Apply Normalization" button — redundant now that the method
        # combo, sliders, spin boxes, and the 'b'-key picker all already
        # trigger perform_normalization() live (see _on_norm_method_changed,
        # _sync_*_from_*, on_canvas_key_press). The method itself is still
        # used internally by all of those.

        group.setLayout(v)
        return group

    @staticmethod
    def _bound_label(text):
        label = QLabel(f"<b>{text}</b>")
        return label

    def _make_help_button(self, title, text):
        """Small circular orange '?' button — same idea as the context-help
        buttons in SpecAnalytiXBase's main window — that pops up a plain
        QMessageBox with the full explanation. Used in place of a tooltip
        for anything too long to read comfortably as a single hover-line
        (Qt tooltips don't wrap long plain text); short tooltips stay as
        tooltips, just manually wrapped onto a few lines with '\\n'."""
        btn = QPushButton("?")
        btn.setFixedSize(20, 20)
        btn.setStyleSheet(
            "QPushButton { background-color: #FF8C00; color: white; border-radius: 10px; "
            "font-weight: bold; padding: 0px; }"
            "QPushButton:hover { background-color: #FFA500; }")
        btn.setToolTip(f"About: {title}")
        btn.clicked.connect(lambda: QMessageBox.information(self, title, text))
        return btn

    def _build_bound_row(self, parent_layout, name):
        """Build one 'label + spin box + slider' row for a single baseline
        boundary (e.g. Low-T min) and add it to parent_layout. Returns
        (spin, slider) — the two widgets stay in sync with each other via
        the connections made by the caller (_build_normalization_group),
        and both drive the same live plot update."""
        row = QHBoxLayout()
        row.addWidget(QLabel(name.capitalize() + ":"))
        spin = QDoubleSpinBox()
        spin.setRange(-1e6, 1e6)
        spin.setDecimals(3)
        row.addWidget(spin)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, self._SLIDER_STEPS)
        slider.setToolTip("Drag to adjust this\nboundary in real time.")
        row.addWidget(slider, stretch=1)
        parent_layout.addLayout(row)
        return spin, slider

    def _build_fit_group(self):
        group = QGroupBox("Sigmoid Fit (1-4 components)")
        v = QVBoxLayout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Components:"))
        self.n_components_spin = QSpinBox()
        self.n_components_spin.setRange(1, 4)
        self.n_components_spin.setValue(1)
        self.n_components_spin.setMaximumWidth(50)
        self.n_components_spin.valueChanged.connect(self._on_n_components_changed)
        row1.addWidget(self.n_components_spin)
        row1.addSpacing(8)
        row1.addWidget(QLabel("Shape:"))
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(list(self.manager.sigmoid_shapes.keys()))
        self.shape_combo.setMaximumWidth(120)
        self.shape_combo.currentIndexChanged.connect(self._on_n_components_changed)
        row1.addWidget(self.shape_combo)
        row1.addSpacing(12)
        self.auto_detect_btn = QPushButton("Auto-detect Transitions")
        self.auto_detect_btn.setToolTip(
            "Estimate initial midpoints from peaks in the curve's derivative\n"
            "and show them directly as the starting guesses below —\n"
            "edit any cell before clicking Fit if needed.")
        self.auto_detect_btn.clicked.connect(self.perform_auto_detect)
        row1.addWidget(self.auto_detect_btn)
        self.fit_btn = QPushButton("Fit")
        self.fit_btn.clicked.connect(self.perform_fit)
        # Same accent color as Extract Curve — the other key "primary
        # action" button in this workflow.
        self.fit_btn.setStyleSheet(
            "QPushButton { background-color: #4a90d9; color: white; font-weight: bold; "
            "padding: 4px 12px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #5b9ee0; }"
            "QPushButton:pressed { background-color: #3d7fc4; }")
        row1.addWidget(self.fit_btn)
        row1.addSpacing(12)
        self.fit_details_btn = QToolButton()
        self.fit_details_btn.setText("Fit Details")
        self.fit_details_btn.setPopupMode(QToolButton.InstantPopup)
        self.fit_details_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        # QToolButton's dropdown arrow is drawn inside the button's own
        # content rect by default, not in reserved extra space — without
        # this, it overlaps the last letter or two of the text instead
        # of sitting cleanly to its right.
        self.fit_details_btn.setStyleSheet(
            "QToolButton { padding-right: 16px; }"
            "QToolButton::menu-indicator { subcontrol-position: right center; "
            "subcontrol-origin: padding; right: 2px; }")
        self.fit_details_btn.setToolTip(
            "A full text report of the current fit (per-component\n"
            "fraction/midpoint/width, deltaH/deltaS/Tm, quality) —\n"
            "view it, copy it to the clipboard, or save it to a file.")
        fit_details_menu = QMenu(self.fit_details_btn)
        fit_details_menu.addAction("Show...", self.show_fit_details)
        fit_details_menu.addAction("Copy to Clipboard", self.copy_fit_details)
        fit_details_menu.addAction("Save to File...", self.save_fit_details)
        # Same shared PDF report used by every other analysis dialog's
        # "Export PDF" button (Kinetics Fitting, QC/Outlier Detection,
        # PLS/PLS-DA, Isosbestic Point Detection, Band Ratio, Reference
        # Matching) — folded into this existing Fit Details dropdown
        # rather than a whole new button row, since this dialog already
        # has a dedicated affordance for exporting the fit report and a
        # PDF version is really the same content (see
        # _build_fit_report_text) plus the plot and results table.
        fit_details_menu.addAction("Export PDF Report...", self.export_pdf_report)
        self.fit_details_btn.setMenu(fit_details_menu)
        row1.addWidget(self.fit_details_btn)
        row1.addStretch()
        v.addLayout(row1)

        options_row = QHBoxLayout()
        self._sigmoid_options_row = options_row  # Show component fits/residual checkboxes join this same row further down
        v.addLayout(options_row)

        table_header_row = QHBoxLayout()
        self.guesses_table_toggle_btn = QPushButton("\u25bc Starting guesses / fit results")
        self.guesses_table_toggle_btn.setFlat(True)
        self.guesses_table_toggle_btn.setStyleSheet(
            "QPushButton { text-align: left; border: none; font-weight: bold; }")
        self.guesses_table_toggle_btn.setToolTip("Click to show/hide this table.")
        self.guesses_table_toggle_btn.clicked.connect(self._toggle_guesses_table)
        table_header_row.addWidget(self.guesses_table_toggle_btn)
        table_header_row.addStretch()
        table_header_row.addWidget(self._make_help_button(
            "Sigmoid Fit — the guesses table",
            "Before fitting: this table shows the current starting guesses "
            "(evenly-spaced defaults, or whatever Auto-detect Transitions last "
            "estimated) — double-click any Fraction/Midpoint/Width cell to edit it "
            "directly. The dashed preview curves on the plot update live as you "
            "type.\n\n"
            "Changing Components or Shape resets the table back to fresh "
            "evenly-spaced defaults, since a previous fit or set of guesses for a "
            "different component count no longer applies.\n\n"
            "After a successful fit: the same table switches to showing the "
            "fitted results instead (read-only preview) until you change "
            "Components/Shape again — each value shown as \"value \u00b1 error\" "
            "(standard error, 1 std, straight from the fit's own covariance "
            "matrix) where available. This says how well-determined that "
            "component's SHAPE is (where the transition is, how sharp it is) — a "
            "different, independent notion of uncertainty from the deltaH/deltaS/"
            "Tm errors in the thermodynamics table below, which come from the "
            "Arrhenius regression instead."))
        v.addLayout(table_header_row)

        self.fit_results_table = QTableWidget()
        self.fit_results_table.setColumnCount(4)
        self.fit_results_table.setHorizontalHeaderLabels(["#", "Fraction", "Midpoint", "Width"])
        self.fit_results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fit_results_table.setToolTip("Click ? above for details.")
        self.fit_results_table.setItemDelegate(_EnterCommitDelegate(self.fit_results_table))
        self.fit_results_table.itemChanged.connect(self._on_guess_table_edited)
        v.addWidget(self.fit_results_table)
        # Expanded/visible by default — no explicit setVisible(True) call
        # needed (a QTableWidget is already visible by default when
        # created). A call here used to fire while this table was still
        # unparented (this whole panel isn't attached to the dialog yet
        # at this point in construction), which made Qt briefly treat it
        # as its own top-level window — the cause of the "flashing
        # dialog" bug. Left as a comment as a warning not to re-add it.

        self.fit_quality_label = QLabel("R^2: -    RMSD: -")
        v.addWidget(self.fit_quality_label)

        if _SHOW_DEVELOPER_TOOLS:
            compare_btn = QPushButton("Compare to Known Values...")
            compare_btn.setToolTip(
                "For this app's own bundled synthetic test datasets (Help ->\n"
                "Test datasets -> Synthetic -> Melting curve) — picks an .xlsx\n"
                "with an \"Info\" sheet and compares the current fit's Tm/\n"
                "deltaH/deltaS/factor against the known true values it was\n"
                "generated from. Not meaningful for real experimental data,\n"
                "which has no \"known answer\" to compare against.")
            compare_btn.clicked.connect(self.compare_fit_to_known_values)
            options_row.addWidget(compare_btn)

        thermo_toggle_row = QHBoxLayout()
        self.thermo_table_toggle_btn = QPushButton("\u25b6 Thermodynamic parameters (per component)")
        self.thermo_table_toggle_btn.setFlat(True)
        self.thermo_table_toggle_btn.setStyleSheet(
            "QPushButton { text-align: left; border: none; font-weight: bold; }")
        self.thermo_table_toggle_btn.setToolTip(
            "Click to show/hide deltaH, deltaS, Tm, and deltaG for each\n"
            "fitted transition individually (only available after Fit).")
        self.thermo_table_toggle_btn.clicked.connect(self._toggle_thermo_table)
        thermo_toggle_row.addWidget(self.thermo_table_toggle_btn)
        thermo_toggle_row.addStretch()
        thermo_toggle_row.addWidget(QLabel("Ref. T for deltaG:"))
        self.thermo_ref_temp_spin = QDoubleSpinBox()
        self.thermo_ref_temp_spin.setRange(-50.0, 150.0)
        self.thermo_ref_temp_spin.setValue(37.0)
        self.thermo_ref_temp_spin.setSuffix(" \u00b0C")
        self.thermo_ref_temp_spin.setMaximumWidth(90)
        self.thermo_ref_temp_spin.setToolTip(
            "deltaG = deltaH - T\u00d7deltaS, evaluated at this temperature\n"
            "(default 37\u00b0C, physiological temperature).")
        self.thermo_ref_temp_spin.valueChanged.connect(self._populate_thermo_table)
        thermo_toggle_row.addWidget(self.thermo_ref_temp_spin)
        v.addLayout(thermo_toggle_row)

        self.thermo_table = QTableWidget()
        self.thermo_table.setColumnCount(5)
        self.thermo_table.setHorizontalHeaderLabels(
            ["#", "Tm [C]", "deltaH [kJ/mol]", "deltaS [J/mol/K]", "deltaG [kJ/mol]"])
        self.thermo_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.thermo_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.thermo_table.setMaximumHeight(140)
        self.thermo_table.setToolTip(
            "Text color matches each component's color on the plot.\n"
            "\u00b1 shown where a standard-error estimate is available (3+ points).")
        self.thermo_table.setVisible(False)
        v.addWidget(self.thermo_table)

        self.show_component_fits_check = QCheckBox("Show component fits && Arrhenius plots")
        self.show_component_fits_check.setChecked(True)
        self.show_component_fits_check.setToolTip("Click ? for details.")
        self._sigmoid_options_row.addWidget(self.show_component_fits_check)
        self._sigmoid_options_row.addWidget(self._make_help_button(
            "Per-component Arrhenius plots",
            "After fitting, show each component's own isolated curve — real data "
            "with every OTHER component's contribution removed and renormalized "
            "back to a standalone 0-1 transition, alongside its ideal fitted model "
            "curve and a dotted line at its own Tm — and its own Arrhenius plot / "
            "deltaH, deltaS, Tm, below the main plots.\n\n"
            "This is the multi-transition generalization of the single Arrhenius "
            "plot above, applied to each decomposed component in turn. A "
            "component's own deltaH/deltaS, especially for closely-spaced or "
            "heavily overlapping transitions, is intrinsically an approximation — "
            "Tm is generally recovered much more reliably."))
        self.show_component_fits_check.stateChanged.connect(self._on_plot_visibility_toggled)

        self.show_residual_check = QCheckBox("Show residual")
        self.show_residual_check.setChecked(True)
        self.show_residual_check.stateChanged.connect(self._on_plot_visibility_toggled)
        self._sigmoid_options_row.addWidget(self.show_residual_check)
        self._sigmoid_options_row.addStretch()

        group.setLayout(v)
        return group

    def _build_output_group(self):
        group = QGroupBox("Output Options (Adds New Spectra)")
        v = QVBoxLayout()

        header_row = QHBoxLayout()
        self.output_toggle_btn = QPushButton("\u25b6 Nothing is saved unless at least one is checked")
        self.output_toggle_btn.setFlat(True)
        self.output_toggle_btn.setStyleSheet(
            "QPushButton { text-align: left; border: none; font-weight: bold; }")
        self.output_toggle_btn.setToolTip("Click to show/hide the Output Options checkboxes.")
        self.output_toggle_btn.clicked.connect(self._toggle_output_section)
        header_row.addWidget(self.output_toggle_btn)
        header_row.addStretch()
        v.addLayout(header_row)

        self.output_content_widget = QWidget()
        content_v = QVBoxLayout(self.output_content_widget)
        content_v.setContentsMargins(0, 0, 0, 0)

        self.add_raw_check = QCheckBox("Add extracted (raw) curve")
        self.add_norm_check = QCheckBox("Add normalized curve")
        self.add_baselines_check = QCheckBox("Add low/high-T baseline curves")
        self.add_fit_check = QCheckBox("Add total fit curve")
        self.add_residual_check = QCheckBox("Add residual")
        self.add_components_check = QCheckBox("Add individual transition components")

        for cb in (self.add_raw_check, self.add_norm_check, self.add_baselines_check,
                  self.add_fit_check, self.add_residual_check, self.add_components_check):
            content_v.addWidget(cb)
        # None checked by default — this dialog's main purpose is the
        # ANALYSIS (the numbers), not necessarily saving new spectra every
        # time; plenty of workflows just want to inspect a fit and close
        # without adding anything to the main spectra list.

        v.addWidget(self.output_content_widget)
        # Collapsed by default, matching Saved Fits' same default state —
        # click the toggle to expand ("show options") when actually
        # needed, rather than leaving this section's checkboxes taking up
        # space every time by default.
        self.output_content_widget.setVisible(False)

        group.setLayout(v)
        return group

    def _toggle_output_section(self):
        visible = not self.output_content_widget.isVisible()
        self.output_content_widget.setVisible(visible)
        self.output_toggle_btn.setText(
            ("\u25bc" if visible else "\u25b6") + " Nothing is saved unless at least one is checked")

    def create_canvas_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        # Parent this to `widget` IMMEDIATELY, before anything else runs.
        # A QWidget with no parent is, by Qt's own rules, a top-level
        # window in its own right — matplotlib's FigureCanvas doesn't
        # take a parent via its own constructor, so without this line the
        # canvas sat unparented for ~30 lines of setup code (building the
        # toolbar, connecting signals, overriding the Home button) before
        # finally being added to this layout below. That's a real window
        # of time where, if anything in that setup code caused Qt to
        # process paint/show events, the canvas could flash on screen as
        # its own small, blank top-level window before being properly
        # embedded here — matching a "dialog flashes and disappears"
        # symptom specific to this dialog, since it's the only one that
        # builds and holds a matplotlib canvas this way.
        self.canvas.setParent(widget)
        # ClickFocus so the canvas only grabs keyboard focus once the user
        # actually clicks it (e.g. to zoom/pan) — not merely on hover —
        # matching how the rest of this dialog's spinboxes/table already
        # expect click-to-focus, and required for the canvas to receive
        # the 'b' key press at all (see on_canvas_key_press below).
        self.canvas.setFocusPolicy(Qt.ClickFocus)
        self.key_connection_id = self.canvas.mpl_connect(
            'key_press_event', self.on_canvas_key_press)
        self.toolbar = NavigationToolbar(self.canvas, widget)
        # The default Home button doesn't work reliably here: update_plot()
        # calls figure.clear() and creates brand-new Axes on essentially
        # every interaction (baseline slider drags, picks, fits, ...),
        # which desyncs NavigationToolbar2's internal home/back/forward
        # view stack from the Axes that actually exist by the time Home is
        # clicked. Overriding it to just redraw at the full data range
        # sidesteps that entirely — same fix, same reasoning, as
        # PeakFittingDialog's own Home button override.
        home_action = self.toolbar.actions()[0]
        home_action.triggered.disconnect()
        home_action.triggered.connect(self.reset_view_to_full)
        home_action.setToolTip(
            "Reset the view to the full curve.\n"
            "Tip: click the plot, zoom/pan to frame a baseline region,\n"
            "then press 'b' to capture it as the nearer baseline\n"
            "(Normalization panel).")
        self.toolbar.setContentsMargins(0, 0, 0, 0)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, stretch=1)
        return widget

    # ------------------------------------------------------------------ #
    # Initialization / settings persistence                               #
    # ------------------------------------------------------------------ #

    def initialize_dialog(self):
        self._suppress_auto_update = True
        self._init_x_value_range()
        self._suppress_auto_update = False
        self.populate_temps_table()
        self._populate_saved_fits_list()
        self.load_settings()
        self.update_plot()
        self._disable_wheel_scrolling()
        self._prevent_enter_from_closing_dialog()

    def _disable_wheel_scrolling(self, root=None):
        """Scrolling the mouse wheel over the control panel should always
        scroll the panel — not silently change whatever spinbox,
        combobox, or slider the cursor happens to be sitting on. Qt's
        surprising default is that these widgets respond to the wheel
        even without being focused or clicked, which made it genuinely
        unclear which value had just changed while trying to scroll past
        one. Finds every such widget under root (defaults to this dialog
        itself; also called on the Show Summary window for its own
        property combos) and makes it ignore wheel events instead, so
        they bubble up to whichever ancestor actually handles scrolling
        rather than being consumed here."""
        if root is None:
            root = self
        for widget in root.findChildren((QAbstractSpinBox, QComboBox, QSlider)):
            widget.wheelEvent = lambda event: event.ignore()

    def _prevent_enter_from_closing_dialog(self, root=None):
        """Pressing Enter/Return in a spin box or text field should just
        commit whatever you typed there — not ALSO propagate up and
        trigger the dialog's default OK button, closing the ENTIRE
        dialog. This is a well-known Qt trap: an editable widget's own
        keyPressEvent handles Return (committing the value, firing
        valueChanged/editingFinished) but by default still lets the
        event propagate afterward, and a QDialog with a default button
        (which QDialogButtonBox sets up automatically) treats any
        unclaimed Return keypress anywhere inside it as "click OK".

        Wraps every spin box and line edit under root (defaults to this
        dialog; also usable for the Show Summary window) so the widget's
        own handling still runs completely normally first — the value
        still commits exactly the same way — but the event is marked
        accepted afterward so it stops there instead of closing anything.
        """
        if root is None:
            root = self
        for widget in root.findChildren((QAbstractSpinBox, QLineEdit)):
            if getattr(widget, '_enter_key_guarded', False):
                continue  # don't double-wrap if this is called more than once
            original_handler = widget.keyPressEvent

            def guarded_handler(event, _orig=original_handler):
                _orig(event)
                if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    event.accept()

            widget.keyPressEvent = guarded_handler
            widget._enter_key_guarded = True

    def _init_x_value_range(self):
        x_mins, x_maxs = [], []
        for spec in self.selected_spectra:
            x = np.asarray(spec['x_scale'], dtype=float)
            if x.size:
                x_mins.append(np.nanmin(x)); x_maxs.append(np.nanmax(x))
        if x_mins:
            lo, hi = max(x_mins), min(x_maxs)  # overlap region is safest default
            if lo > hi:  # spectra don't overlap; fall back to the widest range
                lo, hi = min(x_mins), max(x_maxs)
            self.x_value_spin.setValue((lo + hi) / 2.0)

    def populate_temps_table(self):
        self._suppress_auto_update = True
        self.temps_table.setSortingEnabled(False)
        self.temps_table.setRowCount(len(self.selected_spectra))

        # Look at ALL labels together first, so the guess can prefer
        # whichever number actually varies across the batch (a real
        # temperature series) over one that's identical on every row (a
        # shared sample/block ID that merely happens to contain a digit,
        # e.g. "r-2,4-blok" repeated on every spectrum). See
        # _pick_varying_number_position() for the full reasoning.
        all_numbers = [_NUMBER_RE.findall(spec.get('label', '')) for spec in self.selected_spectra]
        varying_position = self._pick_varying_number_position(all_numbers)

        # Captured once, here, before load_settings() (called right after
        # this in initialize_dialog) can overwrite the displayed values
        # from a previous run's cached settings — so "original" always
        # means "as guessed from the spectra themselves when this dialog
        # was first opened", regardless of anything restored or edited
        # afterward. Used by revert_to_original_temperatures().
        self._original_temperatures = {}

        for row, spec in enumerate(self.selected_spectra):
            label = spec.get('label', f'spectrum_{row}')
            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            self.temps_table.setItem(row, 0, label_item)

            guess = self._guess_temperature(spec, row, all_numbers[row], varying_position)
            self.temps_table.setItem(row, 1, self._numeric_item(guess))
            self._original_temperatures[label] = guess

            # Y (Signal) starts blank — filled in per row automatically
            # by the real-time update as soon as there's enough to work
            # with (see _auto_update_curve).
            self.temps_table.setItem(row, 2, QTableWidgetItem(""))
        self.temps_table.setSortingEnabled(True)
        self._suppress_auto_update = False
        self._auto_update_curve()

    def _on_show_spectrum_names_toggled(self, state):
        self.temps_table.setColumnHidden(0, not self.show_spectrum_names_check.isChecked())

    def revert_to_original_temperatures(self):
        """Restore every Temperature cell to its originally-guessed value
        (from _original_temperatures, captured in populate_temps_table
        when this dialog was first opened) — discards any edits, pastes,
        or restored-from-settings values in between. Confirms first,
        since this can throw away real manual corrections."""
        if not self._original_temperatures:
            return
        reply = QMessageBox.question(
            self, "Revert to Original Temperatures",
            "This replaces every Temperature value with the originally-guessed "
            "value from when this dialog was first opened, discarding any edits "
            "made since (including anything restored from a previous run).\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._suppress_auto_update = True
        self.temps_table.setSortingEnabled(False)
        for row in range(self.temps_table.rowCount()):
            label = self.temps_table.item(row, 0).text()
            if label in self._original_temperatures:
                self.temps_table.setItem(row, 1, self._numeric_item(self._original_temperatures[label]))
        self.temps_table.setSortingEnabled(True)
        self._suppress_auto_update = False
        self._auto_update_curve()

    def _pick_varying_number_position(self, all_numbers):
        """Given the list of number-strings extracted from every selected
        label (same order as self.selected_spectra), return the index of
        the RIGHTMOST numeric position that is present in every label AND
        does not have the exact same value on every row — i.e. the
        position most likely to be a genuinely per-spectrum quantity
        (a temperature, a run number, ...) rather than a fixed or
        per-FILE identifier that's merely repeated or shared.

        Deliberately scans right-to-left, not left-to-right: trailing
        numbers are more likely to be per-spectrum (matching the same
        preference _guess_temperature's own fallback chain already uses).
        A LEADING number can vary too without being remotely temperature-
        like — e.g. if spectra from more than one file end up selected
        together, a leading number that encodes something like "how many
        transitions this file models" genuinely differs from file to
        file, but picking THAT as "the varying position" would read a
        per-file identifier as if it were each spectrum's own
        temperature. Preferring the rightmost match avoids that trap in
        the overwhelmingly common case (temperature as the trailing
        number) without needing to know anything about where the labels
        actually came from.

        Returns None if every label is missing numbers, or every shared
        position is constant (nothing to prefer over "last number in the
        label").
        """
        if not all_numbers or any(len(nums) == 0 for nums in all_numbers):
            return None
        min_count = min(len(nums) for nums in all_numbers)
        for pos in range(min_count - 1, -1, -1):
            values_at_pos = {nums[pos] for nums in all_numbers}
            if len(values_at_pos) > 1:
                return pos
        return None

    def _guess_temperature(self, spec, fallback_index, numbers_in_label=None, varying_position=None):
        """Seed a starting temperature guess, preferring (in order):
        1. The number at `varying_position` (the position that actually
           differs across the whole selected batch — see
           _pick_varying_number_position), if this label has one there.
        2. The LAST number in the label (trailing numbers are more often
           a per-spectrum index/temperature than a leading one that's part
           of a shared sample name, e.g. "sample_25C").
        3. Any existing 'temperature' metadata on the spectrum.
        4. The spectrum's position in the selection order.
        Always user-editable afterwards in the table — this is only a
        starting point, never trusted as the final value."""
        if numbers_in_label is None:
            numbers_in_label = _NUMBER_RE.findall(spec.get('label', ''))

        if varying_position is not None and varying_position < len(numbers_in_label):
            try:
                return float(numbers_in_label[varying_position])
            except ValueError:
                pass

        if numbers_in_label:
            try:
                return float(numbers_in_label[-1])
            except ValueError:
                pass

        existing_temp = (spec.get('metadata') or {}).get('temperature')
        if existing_temp is not None:
            try:
                return float(existing_temp)
            except (TypeError, ValueError):
                pass
        return float(fallback_index)

    def _compute_spectra_fingerprint(self):
        """A fast, stable fingerprint of self.selected_spectra's actual
        data (labels + x/y values) — used to detect whether the
        underlying spectra genuinely changed since a previous session's
        cached results were saved. Re-opening this dialog for the exact
        same, unmodified selection can then restore the cached curve/
        fit instantly instead of re-running extraction, normalization,
        and a full sigmoid curve_fit optimization from scratch every
        single time — the noticeable delay on reopen was exactly that
        recompute, done unconditionally even when nothing had changed.
        If any spectrum was edited outside this dialog (e.g. a baseline
        correction applied afterward) the fingerprint changes and the
        normal full recompute runs instead, exactly as before."""
        h = hashlib.md5()
        for spec in self.selected_spectra:
            h.update(str(spec.get('label', '')).encode('utf-8', errors='replace'))
            x = spec.get('x_scale')
            y = spec.get('y_scale')
            if x is not None:
                h.update(np.asarray(x, dtype=float).tobytes())
            if y is not None:
                h.update(np.asarray(y, dtype=float).tobytes())
        return h.hexdigest()

    def _try_fast_restore_from_cache(self, cs):
        """If the cached results' spectra fingerprint matches the
        CURRENT selection's fingerprint, restore the cached curve/
        normalization/fit/thermodynamics artifacts directly instead of
        recomputing them. Returns True if the fast restore succeeded
        (nothing else needs to run), False if the fingerprint is
        missing (e.g. a cache saved before this existed) or doesn't
        match — in which case the caller falls back to the normal full
        recompute path."""
        cached_fp = cs.get('spectra_fingerprint')
        curve_payload = cs.get('curve')
        if not cached_fp or not curve_payload or cached_fp != self._compute_spectra_fingerprint():
            return False

        curve_payload = dict(curve_payload)
        self.normalization_result = curve_payload.pop('normalization_result', None)
        self.curve = curve_payload
        self._update_svd_diagnostics_label(self.curve.get('svd_diagnostics'))
        self.x_trans = cs.get('x_trans')
        self.fit_result = cs.get('fit_result')
        self.component_thermodynamics = cs.get('component_thermodynamics')
        self._automatic_fit_result = cs.get('automatic_fit_result')
        self._initial_guesses = []
        self._fit_is_preview = False  # a cached fit_result is always a real, completed fit
        self._baseline_defaults_set = True  # cached ranges are already meaningful, don't override them

        is_automatic = cs.get('normalization', {}).get('method') == 'automatic'
        self._set_automatic_mode_enabled(is_automatic)
        self._update_automatic_fit_banner(self._automatic_fit_result if is_automatic else None)
        if is_automatic and self._automatic_fit_result and self._automatic_fit_result.get('success'):
            self._update_baseline_cross_warning(self._automatic_fit_result['norm'])

        # The table's Y column (and, in "From file" mode, every row) is
        # normally filled in as a side effect of actually running
        # extraction — since that's exactly what this skips, fill it in
        # directly from the restored curve so the table still matches
        # what's plotted. Matched by label where possible; if the arrays
        # don't line up 1:1 for some reason (e.g. an edge case in how a
        # very old cache handled duplicate-temperature averaging), skip
        # this part gracefully — the plot/numbers restored above are the
        # important part, a stale table is a cosmetic-only fallback.
        try:
            labels = self.curve.get('source_labels', [])
            temps = self.curve['x_temperature']
            ys = self.curve['y_raw']
            if len(labels) == len(temps) == len(ys):
                if self.source_spectra_radio.isChecked():
                    label_to_row = {self.temps_table.item(r, 0).text(): r
                                   for r in range(self.temps_table.rowCount())}
                    self._suppress_auto_update = True
                    for label, t, y in zip(labels, temps, ys):
                        row = label_to_row.get(label)
                        if row is not None:
                            self.temps_table.setItem(row, 1, self._numeric_item(t))
                            self.temps_table.setItem(row, 2, self._numeric_item(y))
                    self._suppress_auto_update = False
                else:
                    self._suppress_auto_update = True
                    self.temps_table.setRowCount(len(temps))
                    for row, (t, y) in enumerate(zip(temps, ys)):
                        self.temps_table.setItem(row, 1, self._numeric_item(t))
                        self.temps_table.setItem(row, 2, self._numeric_item(y))
                    self._suppress_auto_update = False
        except (KeyError, TypeError):
            pass

        if self.fit_result is not None:
            self._populate_fit_results_table()
            q = self.fit_result['quality']
            self.fit_quality_label.setText(f"R^2: {q['r_squared']:.4f}    RMSD: {q['rmsd']:.4g}")
        return True

    def load_settings(self):
        """Restore a previous run's settings/results when re-opening the
        dialog for the same selection (current_settings passed in by
        OperationsController — same cache-and-reuse pattern as Peak
        Fitting's current_settings)."""
        cs = self.current_settings
        if not cs:
            return

        prev_suppress = self._suppress_auto_update
        self._suppress_auto_update = True
        try:
            temp_map = cs.get('temperatures', {})
            for row in range(self.temps_table.rowCount()):
                label = self.temps_table.item(row, 0).text()
                if label in temp_map:
                    self.temps_table.item(row, 1).setText(f"{temp_map[label]:g}")

            if cs.get('curve', {}).get('x_value') is not None:
                self.x_value_spin.setValue(cs['curve']['x_value'])
            if cs.get('window') is not None:
                self.window_spin.setValue(cs['window'])
            if cs.get('curve_name'):
                self.curve_name_edit.setText(cs['curve_name'])

            if cs.get('extraction_method') == 'svd':
                self.extraction_method_combo.setCurrentIndex(1)
            else:
                self.extraction_method_combo.setCurrentIndex(0)
            if cs.get('svd_center') is not None:
                self.svd_center_check.setChecked(cs['svd_center'])

            if cs.get('source_mode') == 'file' and cs.get('external_file_path'):
                self._external_curve_path = cs['external_file_path']
                self.external_file_edit.setText(self._external_curve_path)
                self._refresh_sheet_list()
                if cs.get('sheet_name'):
                    idx = self.sheet_combo.findText(cs['sheet_name'])
                    if idx >= 0:
                        self.sheet_combo.setCurrentIndex(idx)
                self.source_file_radio.setChecked(True)
            else:
                self.source_spectra_radio.setChecked(True)

            norm = cs.get('normalization')
            if norm:
                idx = {'none': 0, 'zero': 1, 'first': 2, 'automatic': 3}.get(norm.get('method'), 2)
                self.norm_combo.setCurrentIndex(idx)
                self._set_automatic_mode_enabled(idx == 3)
                if norm.get('low_range'):
                    self.low_min_spin.setValue(norm['low_range'][0])
                    self.low_max_spin.setValue(norm['low_range'][1])
                if norm.get('high_range'):
                    self.high_min_spin.setValue(norm['high_range'][0])
                    self.high_max_spin.setValue(norm['high_range'][1])

            if cs.get('span') is not None:
                self.span_spin.setValue(cs['span'])

            fit_settings = cs.get('fit_settings')
            if fit_settings:
                self.n_components_spin.setValue(fit_settings.get('n_components', 1))
                shape_idx = self.shape_combo.findText(fit_settings.get('shape_name', 'Logistic'))
                if shape_idx >= 0:
                    self.shape_combo.setCurrentIndex(shape_idx)

            output_options = cs.get('output_options', {})
            self.add_raw_check.setChecked(output_options.get('add_raw_curve', False))
            self.add_norm_check.setChecked(output_options.get('add_normalized_curve', False))
            self.add_baselines_check.setChecked(output_options.get('add_baselines', False))
            self.add_fit_check.setChecked(output_options.get('add_fit', False))
            self.add_residual_check.setChecked(output_options.get('add_residual', False))
            self.add_components_check.setChecked(output_options.get('add_components', False))
        finally:
            self._suppress_auto_update = prev_suppress

        # Re-run the pipeline as far as it previously got, so re-opening
        # the dialog shows the same state it was left in rather than a
        # blank plot — UNLESS the underlying spectra are byte-for-byte
        # identical to when this cache was saved, in which case restore
        # the cached curve/fit directly instead (see
        # _try_fast_restore_from_cache) rather than expensively
        # recomputing something that would come out identical anyway.
        # Everything above runs with live recomputation suppressed —
        # these widget values are about to be superseded by exactly this
        # block, so nothing above needed to trigger its own (redundant,
        # immediately-discarded) preview rebuild.
        if cs.get('curve') and not self._try_fast_restore_from_cache(cs):
            self.perform_extraction(silent=True)
            method = cs.get('normalization', {}).get('method') if cs.get('normalization') else None
            if method == 'automatic':
                self.perform_automatic_fit(silent=True)
            else:
                if cs.get('normalization') and method != 'none':
                    self.perform_normalization(silent=True)
                if cs.get('fit_result'):
                    self.perform_fit(silent=True)

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _read_temperatures(self, rows=None):
        """Parse the Temperature column for the given row indices
        (default: every row), rejecting anything that isn't a finite
        number. Explicitly checks np.isfinite() rather than just
        catching ValueError from float() — Python's float() happily
        parses the literal text "nan" or "inf" without raising, which
        matters if a cell ever ends up holding that text (e.g. typed or
        pasted directly). Without this check, a single bad/non-numeric
        temperature could silently turn into NaN and propagate through
        curve extraction, corrupting every downstream min/max/range
        computation (the reported "Extract Curve shows nothing" symptom)
        instead of being caught here with a clear
        message."""
        if rows is None:
            rows = range(self.temps_table.rowCount())
        temps = []
        for row in rows:
            try:
                temp = float(self.temps_table.item(row, 1).text())
            except (ValueError, AttributeError):
                temp = float('nan')
            if not np.isfinite(temp):
                QMessageBox.warning(self, "Invalid Temperature",
                                    f"Row {row + 1} has an invalid (non-numeric) temperature "
                                    "value. Fix it before extracting.")
                return None
            temps.append(temp)
        return temps

    def reset_view_to_full(self):
        """Handler for the toolbar's Home button (see create_canvas_panel
        for why the default Home is overridden). Just redraws — update_plot()
        always frames the view on the full curve range (see its own
        set_xlim() call), so this is all Home needs to do."""
        self.update_plot()

    def _reset_curve_state(self):
        """Clear every piece of derived state (extracted curve, fit,
        normalization, thermodynamics) and the fit-guesses table — used
        when switching source mode, since a curve/fit built under the
        OTHER source is meaningless once the source changes; the user
        re-runs Extract Curve to rebuild under the new one rather than
        this dialog ever showing stale results from before the switch."""
        self.curve = None
        self.normalization_result = None
        self.x_trans = None
        self.fit_result = None
        self.component_thermodynamics = None
        self._initial_guesses = []
        self.fit_results_table.setRowCount(0)
        self.fit_quality_label.setText("R^2: -    RMSD: -")
        self._baseline_defaults_set = False
        self._pending_svd_diagnostics = None
        self.svd_diagnostics_label.setVisible(False)

    def _on_source_mode_changed(self, spectra_checked):
        """Toggled when either radio button changes (connected to the
        'From spectra' radio's toggled signal, so spectra_checked=True
        means that one just became checked). Hides whichever rows don't
        apply to the now-inactive source entirely (not just grays them
        out), and — since a curve/fit/table built under the OTHER source
        is meaningless once the source changes — resets everything and
        then re-extracts under the new source automatically, rather than
        this dialog silently continuing to show stale results from
        before the switch, or requiring an explicit action to rebuild."""
        is_svd_method = self.extraction_method_combo.currentIndex() == 1
        self.extraction_method_row_widget.setVisible(spectra_checked)
        self.xvalue_row_widget.setVisible(spectra_checked and not is_svd_method)
        self.svd_options_row_widget.setVisible(spectra_checked and is_svd_method)
        if not spectra_checked:
            self.svd_diagnostics_label.setVisible(False)
        self.file_row_widget.setVisible(not spectra_checked)
        is_excel = bool(self._external_curve_path) and \
            os.path.splitext(self._external_curve_path)[1].lower() in ('.xlsx', '.xls')
        self.sheet_row_widget.setVisible(not spectra_checked and is_excel)

        # The Spectrum column / "Show spectrum names" checkbox are
        # meaningless in "From file" mode (no spectra are involved at
        # all) — hidden entirely there, not just left showing blanks.
        self.show_spectrum_names_check.setVisible(spectra_checked)
        self.temps_table.setColumnHidden(
            0, not spectra_checked or not self.show_spectrum_names_check.isChecked())

        self._reset_curve_state()
        if spectra_checked:
            self.populate_temps_table()  # this already ends with _auto_update_curve()
        else:
            self.temps_table.setRowCount(0)
            self.update_plot()
            # If a file was already picked earlier in this session (e.g.
            # switching From file -> From spectra -> From file again),
            # reload it automatically rather than leaving a blank
            # "Extract a curve to begin" placeholder with no button left
            # to fix it. Only when a path already exists, though — don't
            # pop up a file browser unprompted on a first-time switch to
            # "From file" with nothing picked yet; Browse... is right
            # there for that.
            if self._external_curve_path:
                self._auto_update_curve()

    def _on_extraction_method_changed(self, index):
        """Extract-at-X vs SVD chosen — toggles which row of controls is
        visible and, since the two build a curve completely differently,
        resets and re-extracts under the new method right away (same
        "no stale results left showing" policy as _on_source_mode_changed)."""
        is_svd = (index == 1)
        spectra_checked = self.source_spectra_radio.isChecked()
        self.xvalue_row_widget.setVisible(spectra_checked and not is_svd)
        self.svd_options_row_widget.setVisible(spectra_checked and is_svd)
        self.svd_diagnostics_label.setVisible(False)
        self._reset_curve_state()
        if spectra_checked:
            self._auto_update_curve()

    def _on_extraction_params_changed(self, *_args):
        """X, the Averaging window, or Sheet changed — whatever curve/fit
        is currently shown was built under the OLD value and no longer
        matches, so it's rebuilt automatically under the new one right
        away, same as any other real-time control in this dialog (the
        baseline sliders, Method, etc.)."""
        self._auto_update_curve()

    def _on_table_cell_edited(self, item):
        """A cell in the Curve Data table was hand-edited (double-click,
        type, Enter — NOT a bulk operation, which suppresses this via
        _suppress_auto_update and calls _auto_update_curve itself once
        at the end instead). Rebuilds the curve directly from the
        table's current contents rather than re-extracting from spectra
        or reloading from a file — either of THOSE would silently
        overwrite the very edit that just happened."""
        if self._suppress_auto_update:
            return
        self._rebuild_curve_from_table()

    def _auto_update_curve(self, *_args):
        """The real-time equivalent of the old "Extract Curve" button —
        called on every change that should rebuild the curve from its
        SOURCE (spectra or file), as opposed to _rebuild_curve_from_table
        which rebuilds from whatever's already sitting in the table
        without touching the source. Guarded against re-entrancy: this
        calls perform_extraction(), which — in "From spectra" mode —
        itself writes Y values back into the table, which would
        otherwise immediately re-trigger _on_table_cell_edited and
        recurse.
        """
        if self._suppress_auto_update:
            return
        self._suppress_auto_update = True
        try:
            self.perform_extraction(silent=False)
        finally:
            self._suppress_auto_update = False

    def _rebuild_curve_from_table(self, silent=False):
        """Rebuild self.curve directly from whatever's currently in the
        X/Y columns of the Curve Data table, without re-extracting from
        spectra or reloading from a file. Used for individual cell edits
        — those are corrections to data that's already there, not a
        request to throw the table away and rebuild it from scratch
        (which is exactly what would silently undo the edit, especially
        in "From file" mode where the table IS the loaded file's data —
        re-reading the file would just overwrite the correction the user
        was making). Tolerates blank/mid-edit cells by skipping them
        rather than erroring — a cell can be transiently empty while
        being typed into.
        """
        temps, y_values = [], []
        for row in range(self.temps_table.rowCount()):
            x_item = self.temps_table.item(row, 1)
            y_item = self.temps_table.item(row, 2)
            try:
                t = float(x_item.text()) if x_item and x_item.text().strip() else None
                y = float(y_item.text()) if y_item and y_item.text().strip() else None
            except ValueError:
                continue
            if t is None or y is None or not (np.isfinite(t) and np.isfinite(y)):
                continue
            temps.append(t)
            y_values.append(y)

        if len(temps) < 2:
            return  # not enough valid rows yet to build a curve

        if self.source_spectra_radio.isChecked():
            source_labels = [s['label'] for s in self.selected_spectra]
            x_value = (None if self.extraction_method_combo.currentIndex() == 1
                      else self.x_value_spin.value())
        else:
            source_labels = self.curve['source_labels'] if self.curve else []
            x_value = None

        self._suppress_auto_update = True
        try:
            self._finalize_curve(np.array(temps), np.array(y_values), source_labels,
                                 [], x_value, silent=silent)
        finally:
            self._suppress_auto_update = False

    def browse_external_curve_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Melting Curve File", "",
            "Curve files (*.txt *.csv *.dat *.xlsx *.xls);;"
            "Text files (*.txt *.csv *.dat);;Excel files (*.xlsx *.xls);;All files (*)")
        if not path:
            return
        self._external_curve_path = path
        self.external_file_edit.setText(path)
        self._refresh_sheet_list()
        self._on_extraction_params_changed()

    def _refresh_sheet_list(self):
        """(Re)populate the Sheet combo from the currently selected
        file's sheet names — an Excel workbook can hold one melting
        curve per sheet; pick the one to load. The whole Sheet row is
        hidden entirely for non-Excel files (nothing to pick)."""
        is_excel = bool(self._external_curve_path) and \
            os.path.splitext(self._external_curve_path)[1].lower() in ('.xlsx', '.xls')
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        self._external_sheet_names = []
        if is_excel:
            try:
                import pandas as pd
                self._external_sheet_names = pd.ExcelFile(self._external_curve_path).sheet_names
                self.sheet_combo.addItems(self._external_sheet_names)
            except Exception as e:
                QMessageBox.warning(self, "Could Not Read Sheets",
                                    f"Could not list sheets in {self._external_curve_path}:\n{e}")
                is_excel = False
        self.sheet_combo.blockSignals(False)
        self.sheet_row_widget.setVisible(is_excel and self.source_file_radio.isChecked())

    def _load_curve_from_file(self, path, sheet_name=None):
        """Load (temperature, signal) pairs from a text or Excel file —
        two columns, an optional non-numeric header row auto-detected and
        skipped. Returns (temps, y_values) as numpy arrays, or raises
        ValueError/RuntimeError with a message suitable for showing
        directly to the user."""
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.xlsx', '.xls'):
            return self._load_curve_from_excel(path, sheet_name=sheet_name)
        return self._load_curve_from_text(path)

    def _load_curve_from_text(self, path):
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            raw_lines = f.readlines()

        def _is_number(s):
            try:
                float(s)
                return True
            except ValueError:
                return False

        rows = []
        for line in raw_lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            tokens = None
            for delim in (',', '\t'):
                parts = [p.strip() for p in line.split(delim) if p.strip() != '']
                if len(parts) >= 2:
                    tokens = parts
                    break
            if tokens is None:
                tokens = line.split()
            if len(tokens) >= 2:
                rows.append(tokens[:2])

        if not rows:
            raise ValueError("No two-column numeric data found in the file.")
        if not (_is_number(rows[0][0]) and _is_number(rows[0][1])):
            rows = rows[1:]  # first row looks like a text header — skip it

        temps, ys = [], []
        for t_txt, y_txt in rows:
            if not (_is_number(t_txt) and _is_number(y_txt)):
                continue
            t, y = float(t_txt), float(y_txt)
            if np.isfinite(t) and np.isfinite(y):
                temps.append(t)
                ys.append(y)

        if len(temps) < 2:
            raise ValueError("Fewer than 2 valid (temperature, signal) rows were found.")
        return np.array(temps), np.array(ys)

    def _load_curve_from_excel(self, path, sheet_name=None):
        try:
            import pandas as pd
        except ImportError:
            raise RuntimeError(
                "Reading .xlsx/.xls files requires the 'pandas' and 'openpyxl' packages, "
                "which aren't available in this installation. Save the curve as a "
                ".txt/.csv file instead.")

        df = pd.read_excel(path, sheet_name=sheet_name if sheet_name else 0, header=None)
        if df.shape[1] < 2 or df.shape[0] < 1:
            raise ValueError("Expected at least two columns of data.")

        col0, col1 = df.iloc[:, 0], df.iloc[:, 1]
        start_row = 0
        try:
            float(col0.iloc[0])
            float(col1.iloc[0])
        except (ValueError, TypeError):
            start_row = 1  # first row looks like a text header — skip it

        temps = pd.to_numeric(col0.iloc[start_row:], errors='coerce').to_numpy(dtype=float)
        ys = pd.to_numeric(col1.iloc[start_row:], errors='coerce').to_numpy(dtype=float)
        mask = np.isfinite(temps) & np.isfinite(ys)
        temps, ys = temps[mask], ys[mask]

        if len(temps) < 2:
            raise ValueError("Fewer than 2 valid (temperature, signal) rows were found.")
        return temps, ys

    def _gather_curve_from_spectra(self, silent=False):
        """'From spectra' source: read the X (Temperature) column and
        extract one Y (signal) value per spectrum at X, writing the
        result back into the table's Y column so it's visible there too.

        Matches each row to its spectrum BY LABEL (column 0), not by row
        index — the table can be sorted by X/Y via its column headers
        (setSortingEnabled(True)), so row order no longer necessarily
        matches self.selected_spectra's own order by the time this runs."""
        # A prior "From file" extraction rebuilds the table to match the
        # file's own row count, which can leave it out of sync with
        # self.selected_spectra if the source is then switched back to
        # "From spectra" — rebuild from the spectra themselves first if
        # so, rather than reading/writing rows that no longer correspond
        # to any real spectrum.
        if self.temps_table.rowCount() != len(self.selected_spectra):
            self.populate_temps_table()

        temps = self._read_temperatures()
        if temps is None:
            return None

        if self.extraction_method_combo.currentIndex() == 1:
            return self._gather_curve_from_spectra_svd(temps, silent=silent)

        x_value = self.x_value_spin.value()
        window = self.window_spin.value()
        y_values_batch, out_of_range = self.manager.extract_curve_from_spectra(
            self.selected_spectra, x_value, window=window)
        y_by_label = {s['label']: y for s, y in zip(self.selected_spectra, y_values_batch)}

        self.temps_table.setSortingEnabled(False)
        row_y, source_labels = [], []
        prev_suppress = self._suppress_auto_update
        self._suppress_auto_update = True
        try:
            for row in range(self.temps_table.rowCount()):
                label = self.temps_table.item(row, 0).text()
                y_val = y_by_label.get(label, float('nan'))
                self.temps_table.setItem(row, 2, self._numeric_item(y_val))
                row_y.append(y_val)
                source_labels.append(label)
        finally:
            self._suppress_auto_update = prev_suppress
        self.temps_table.setSortingEnabled(True)

        return (np.array(temps, dtype=float), np.array(row_y, dtype=float),
               source_labels, out_of_range, x_value)

    def _gather_curve_from_spectra_svd(self, temps, silent=False):
        """'From spectra' + SVD extraction method: build the melting
        curve from the first (by default mean-centered) SVD component's
        own across-spectrum trajectory instead of one signal value at a
        chosen X — see MeltingCurveManager.extract_curve_svd_from_spectra's
        docstring. Mirrors _gather_curve_from_spectra's own table-filling
        and return shape so _finalize_curve/perform_extraction don't need
        to know or care which extraction method actually ran."""
        center = self.svd_center_check.isChecked()
        try:
            y_values_batch, diagnostics = self.manager.extract_curve_svd_from_spectra(
                self.selected_spectra, center=center)
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "SVD Extraction Failed", str(e))
            return None
        y_by_label = {s['label']: y for s, y in zip(self.selected_spectra, y_values_batch)}

        self.temps_table.setSortingEnabled(False)
        row_y, source_labels = [], []
        prev_suppress = self._suppress_auto_update
        self._suppress_auto_update = True
        try:
            for row in range(self.temps_table.rowCount()):
                label = self.temps_table.item(row, 0).text()
                y_val = y_by_label.get(label, float('nan'))
                self.temps_table.setItem(row, 2, self._numeric_item(y_val))
                row_y.append(y_val)
                source_labels.append(label)
        finally:
            self._suppress_auto_update = prev_suppress
        self.temps_table.setSortingEnabled(True)

        self._pending_svd_diagnostics = diagnostics
        return (np.array(temps, dtype=float), np.array(row_y, dtype=float),
               source_labels, [], None)

    def _gather_curve_from_file(self, silent=False):
        """'From file' source: load an already-built (temperature, signal)
        curve directly from an external file (optionally one sheet of a
        multi-sheet Excel workbook), bypassing spectra entirely — then
        replace the table's rows with exactly these (X, Y) pairs (no
        Spectrum column content, since no spectra were involved). Prompts
        for a file via Browse if none has been picked yet (skipped in
        silent/programmatic-restore mode, where there's no user present
        to prompt)."""
        if not self._external_curve_path:
            if silent:
                return None
            self.browse_external_curve_file()
            if not self._external_curve_path:
                return None
        sheet_name = self.sheet_combo.currentText() if self._external_sheet_names else None
        try:
            temps, y_values = self._load_curve_from_file(self._external_curve_path, sheet_name=sheet_name)
        except Exception as e:
            if not silent:
                QMessageBox.warning(
                    self, "Could Not Read File",
                    f"Could not read a melting curve from:\n{self._external_curve_path}\n\n{e}")
            return None

        self.temps_table.setSortingEnabled(False)
        self.temps_table.setRowCount(len(temps))
        prev_suppress = self._suppress_auto_update
        self._suppress_auto_update = True
        try:
            for row, (t, y) in enumerate(zip(temps, y_values)):
                item0 = QTableWidgetItem("")
                item0.setFlags(item0.flags() & ~Qt.ItemIsEditable)
                self.temps_table.setItem(row, 0, item0)
                self.temps_table.setItem(row, 1, self._numeric_item(t))
                self.temps_table.setItem(row, 2, self._numeric_item(y))
        finally:
            self._suppress_auto_update = prev_suppress
        self.temps_table.setSortingEnabled(True)

        # No real spectra were involved — this label is purely
        # informational (recorded in the resulting spectra's metadata),
        # not something MeltingCurveController expects to match against
        # an actual spectrum in the main list.
        file_desc = os.path.basename(self._external_curve_path)
        if sheet_name:
            file_desc += f" [{sheet_name}]"
        source_labels = [f"<external file: {file_desc}>"]
        return temps, y_values, source_labels, [], None

    # ------------------------------------------------------------------ #
    # Saved Fits container                                                #
    # ------------------------------------------------------------------ #

    def save_current_fit(self):
        """Snapshot the curve currently being worked on (extraction,
        normalization, fit, thermodynamics — same shape as get_results())
        into the shared Saved Fits container under a name you choose.
        Does NOT save any spectra — only Output Options + OK do that."""
        if self.curve is None:
            QMessageBox.information(self, "Nothing to Save",
                                    "Extract a curve first.")
            return
        default_name = self.curve_name_edit.text() or "melting_curve"
        name = default_name
        suffix = 2
        while name in self.saved_fits:
            name = f"{default_name}_{suffix}"
            suffix += 1
        name, ok = QInputDialog.getText(self, "Save Current Fit", "Name:", text=name)
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.saved_fits:
            reply = QMessageBox.question(
                self, "Name In Use", f"'{name}' already exists in Saved Fits. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        snap = self.get_results()
        snap['sheet_name'] = self.sheet_combo.currentText() if self._external_sheet_names else None
        self.saved_fits[name] = snap
        self._populate_saved_fits_list()

    def _populate_saved_fits_list(self):
        """(Re)build the Saved Fits list widget from self.saved_fits —
        called on dialog init (so fits saved in a previous session/dialog
        instance already show up) and after any save/remove. Preserves
        which existing entries the user had explicitly unchecked (tracks
        UNCHECKED names specifically, not checked ones — a brand-new name
        that was never in the list before must default to checked, and
        checking membership in a "was checked" set can't tell "genuinely
        new" apart from "was unchecked")."""
        previously_unchecked = {self.saved_fits_list.item(i).text()
                                for i in range(self.saved_fits_list.count())
                                if self.saved_fits_list.item(i).checkState() == Qt.Unchecked}
        self.saved_fits_list.clear()
        for name in self.saved_fits.keys():
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if name in previously_unchecked else Qt.Checked)
            self.saved_fits_list.addItem(item)

    def rename_selected_fits(self):
        """Bulk-rename dialog for Saved Fits — same idea as
        SpecAnalytiXBase's own rename dialog: a two-column table (current
        name, read-only; new name, editable) with Excel-like Ctrl+C/X/V/
        Delete on the New Name column, so a whole batch of names can be
        retyped, or pasted in from a spreadsheet, in one go rather than
        one QInputDialog prompt per fit. Renames every saved fit if none
        are selected in the list; otherwise just the selected ones."""
        selected = self.saved_fits_list.selectedItems()
        names = ([item.text() for item in selected] if selected
                else list(self.saved_fits.keys()))
        if not names:
            QMessageBox.information(self, "No Saved Fits", "There are no saved fits to rename.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Rename Saved Fits")
        dlg.resize(480, 420)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(
            "Edit the New Name column, then click OK. Ctrl+C/Ctrl+X/Ctrl+V/Delete "
            "work here the same as in the Curve Data table (paste a column copied "
            "from Excel to rename several at once)."))

        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Current Name", "New Name"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        table.setSelectionMode(QAbstractItemView.ContiguousSelection)
        table.setRowCount(len(names))
        for i, name in enumerate(names):
            old_item = QTableWidgetItem(name)
            old_item.setFlags(old_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(i, 0, old_item)
            table.setItem(i, 1, QTableWidgetItem(name))
        layout.addWidget(table)

        self._rename_table = table
        table.installEventFilter(self)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        try:
            if dlg.exec_() != QDialog.Accepted:
                return

            new_names = []
            for i, old_name in enumerate(names):
                item = table.item(i, 1)
                new_name = (item.text().strip() if item else "") or old_name
                new_names.append(new_name)

            # Validate as a batch before changing anything: no blanks,
            # no duplicates within the new names themselves, and no
            # collisions with a fit NOT being renamed in this batch.
            being_renamed = set(names)
            others = set(self.saved_fits.keys()) - being_renamed
            seen = set()
            for old_name, new_name in zip(names, new_names):
                if new_name in others:
                    QMessageBox.warning(self, "Name In Use",
                                        f"'{new_name}' already exists and isn't part of "
                                        "this rename batch.")
                    return
                if new_name in seen and new_name != old_name:
                    QMessageBox.warning(self, "Duplicate Name",
                                        f"'{new_name}' is used more than once in this batch.")
                    return
                seen.add(new_name)

            renamed_count = 0
            for old_name, new_name in zip(names, new_names):
                if new_name != old_name:
                    self.saved_fits[new_name] = self.saved_fits.pop(old_name)
                    renamed_count += 1
            if renamed_count:
                self._populate_saved_fits_list()
        finally:
            self._rename_table = None

    def remove_selected_fits(self):
        items = self.saved_fits_list.selectedItems()
        if not items:
            QMessageBox.information(self, "No Fits Selected",
                                    "Select one or more entries in the list above first.")
            return
        names = [item.text() for item in items]
        reply = QMessageBox.question(
            self, "Remove Selected Fits",
            f"Remove {len(names)} saved fit(s)? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for name in names:
            self.saved_fits.pop(name, None)
        self._populate_saved_fits_list()

    def remove_all_fits(self):
        if not self.saved_fits:
            return
        reply = QMessageBox.question(
            self, "Remove All Fits",
            f"Remove all {len(self.saved_fits)} saved fit(s)? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.saved_fits.clear()
        self._populate_saved_fits_list()

    def _compute_span_at(self, snap, tm):
        """The total signal change across a transition on the ORIGINAL
        (un-normalized) scale — |baseline_high(Tm) - baseline_low(Tm)| —
        matching the original prototype's "span" quantity (the vertical
        bracket in its own baseline-normalization reference figure).
        None if no baseline was ever fitted for this curve, or Tm/
        midpoint is unknown."""
        if tm is None:
            return None
        curve = snap.get('curve')
        if not curve:
            return None
        norm_result = curve.get('normalization_result')
        if not norm_result:
            return None
        coeffs_low = norm_result.get('coeffs_low')
        coeffs_high = norm_result.get('coeffs_high')
        if coeffs_low is None or coeffs_high is None:
            return None
        baseline_low_at_tm = float(np.polyval(coeffs_low, tm))
        baseline_high_at_tm = float(np.polyval(coeffs_high, tm))
        return abs(baseline_high_at_tm - baseline_low_at_tm)

    def _extract_summary_rows(self, name, snap):
        """Flatten one saved fit's snapshot into 0+ row-dicts for the
        Summary table/chart — one row per fitted sigmoid component if a
        fit was run, or one mostly-empty row if there's nothing to show
        yet (no fit has ever been run for that saved entry)."""
        base = {'fit': name, 'component': '-', 'fraction': None, 'midpoint': None,
               'width': None, 'deltaH': None, 'deltaS': None, 'Tm': None, 'span': None,
               'deltaH_err': None, 'deltaS_err': None, 'Tm_err': None,
               'r_squared': None, 'rmsd': None, 'n_components': None,
               'source': '-', 'normalization': '-'}
        if not snap or not snap.get('curve'):
            return [base]

        source_desc = 'file' if snap.get('source_mode') == 'file' else 'spectra'
        if snap.get('sheet_name'):
            source_desc += f" [{snap['sheet_name']}]"
        norm = snap.get('normalization')
        method_names = {'none': 'None', 'zero': 'Zero order', 'first': 'First order'}
        norm_desc = method_names.get(norm.get('method'), '?') if norm else 'None'
        base['source'] = source_desc
        base['normalization'] = norm_desc

        fit_result = snap.get('fit_result')
        if not fit_result:
            return [base]

        q = fit_result['quality']
        comp_thermo = snap.get('component_thermodynamics') or []
        rows = []
        for i, p in enumerate(fit_result['components']['params']):
            th = (comp_thermo[i]['thermodynamics']
                 if i < len(comp_thermo) and comp_thermo[i].get('thermodynamics') else None)
            tm_value = th['Tm'] if th else p['midpoint']
            row = dict(base)
            row.update({
                'component': i + 1, 'fraction': p['factor'],
                'midpoint': p['midpoint'], 'width': p['lambda_'],
                'deltaH': th['deltaH'] / 1000 if th else None,
                'deltaS': th['deltaS'] if th else None,
                'Tm': th['Tm'] if th else None,
                'span': self._compute_span_at(snap, tm_value),
                'deltaH_err': (th.get('deltaH_err') / 1000
                              if th and th.get('deltaH_err') is not None else None),
                'deltaS_err': th.get('deltaS_err') if th else None,
                'Tm_err': th.get('Tm_err') if th else None,
                'r_squared': q['r_squared'], 'rmsd': q['rmsd'],
                'n_components': fit_result['n_components'],
            })
            rows.append(row)
        return rows

    def show_fit_overlay(self):
        """Plot every CHECKED saved fit's normalized curve (or raw curve,
        if it was never normalized) and its total sigmoid fit line
        superimposed on ONE set of axes, each fit in its own consistent
        color with a legend — a direct visual complement to Show
        Summary's numbers, for spotting shape differences (width,
        sharpness, how many transitions) that a table of Tm/deltaH/deltaS
        alone doesn't show."""
        names = [self.saved_fits_list.item(i).text()
                 for i in range(self.saved_fits_list.count())
                 if self.saved_fits_list.item(i).checkState() == Qt.Checked]
        if not names:
            QMessageBox.information(self, "No Fits Checked",
                                    "Check one or more saved fits in the list above first.")
            return

        palette = ['tab:blue', 'tab:purple', 'tab:brown', 'tab:cyan', 'tab:orange',
                  'tab:green', 'tab:red', 'tab:pink', 'tab:gray', 'tab:olive']
        fit_colors = {name: palette[i % len(palette)] for i, name in enumerate(names)}

        dlg = QDialog(self)
        dlg.setWindowTitle("Saved Fits Overlay")
        dlg.resize(800, 600)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(
            "Every checked saved fit's normalized curve and sigmoid fit, superimposed."))

        show_data_check = QCheckBox("Show data points")
        show_data_check.setChecked(True)
        show_fit_check = QCheckBox("Show fit lines")
        show_fit_check.setChecked(True)
        opts_row = QHBoxLayout()
        opts_row.addWidget(show_data_check)
        opts_row.addWidget(show_fit_check)
        opts_row.addStretch()
        layout.addLayout(opts_row)

        figure = Figure(constrained_layout=True)
        canvas = FigureCanvas(figure)
        layout.addWidget(canvas)
        toolbar = NavigationToolbar(canvas, dlg)
        layout.addWidget(toolbar)

        def _redraw():
            figure.clear()
            ax = figure.add_subplot(111)
            any_plotted = False
            for name in names:
                snap = self.saved_fits.get(name)
                if not snap or not snap.get('curve'):
                    continue
                x = np.asarray(snap['curve']['x_temperature'], dtype=float)
                norm_result = snap['curve'].get('normalization_result')
                y = (np.asarray(norm_result['y_norm'], dtype=float) if norm_result is not None
                    else np.asarray(snap['curve']['y_raw'], dtype=float))
                color = fit_colors[name]
                if show_data_check.isChecked():
                    ax.plot(x, y, 'o', color=color, markersize=4, alpha=0.6, label=name)
                    any_plotted = True
                fit_result = snap.get('fit_result')
                if show_fit_check.isChecked() and fit_result is not None:
                    order = np.argsort(x)
                    ax.plot(x[order], np.asarray(fit_result['y_fit'])[order], '-',
                           color=color, lw=2,
                           label=None if show_data_check.isChecked() else name)
                    any_plotted = True
            if any_plotted:
                ax.set_xlabel("Temperature")
                ax.set_ylabel("Normalized signal (0-1)")
                ax.grid(True, alpha=0.4)
                ax.legend(fontsize=8)
            else:
                ax.text(0.5, 0.5, "Nothing to show — check \"Show data points\" or\n"
                       "\"Show fit lines\", or verify the checked fits have curves.",
                       transform=ax.transAxes, ha='center', va='center')
            canvas.draw()

        show_data_check.stateChanged.connect(_redraw)
        show_fit_check.stateChanged.connect(_redraw)
        _redraw()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        self._disable_wheel_scrolling(root=dlg)
        self._prevent_enter_from_closing_dialog(root=dlg)
        dlg.exec_()

    def show_fit_summary(self):
        """A genuinely comprehensive comparison across every CHECKED saved
        fit: a full table (one row per fitted component, every quantity
        the app tracks) plus a bar chart comparing a chosen property
        across all of them — lets the user pick which fits to include
        (uncheck any to leave out without deleting them) without needing
        the currently active curve to be involved at all."""
        names = [self.saved_fits_list.item(i).text()
                 for i in range(self.saved_fits_list.count())
                 if self.saved_fits_list.item(i).checkState() == Qt.Checked]
        if not names:
            QMessageBox.information(self, "No Fits Checked",
                                    "Check one or more saved fits in the list above first.")
            return

        all_rows = []
        for name in names:
            all_rows.extend(self._extract_summary_rows(name, self.saved_fits.get(name)))

        columns = [
            ('Fit', 'fit'), ('Comp.', 'component'), ('Fraction', 'fraction'),
            ('Tm [C]', 'Tm'), ('deltaH [kJ/mol]', 'deltaH'), ('deltaS [J/mol/K]', 'deltaS'),
            ('Width', 'width'), ('Span', 'span'), ('R^2', 'r_squared'), ('RMSD', 'rmsd'),
            ('N comp.', 'n_components'), ('Source', 'source'), ('Normalization', 'normalization'),
        ]

        def _fmt(val):
            if val is None:
                return '-'
            if isinstance(val, float):
                return f"{val:.4g}"
            return str(val)

        dlg = QDialog(self)
        dlg.setWindowTitle("Saved Fits Summary")
        dlg.resize(950, 680)
        layout = QVBoxLayout(dlg)

        table = QTableWidget()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels([c[0] for c in columns])
        table.setRowCount(len(all_rows))
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSortingEnabled(True)
        for r, row in enumerate(all_rows):
            for c, (_, key) in enumerate(columns):
                table.setItem(r, c, QTableWidgetItem(_fmt(row.get(key))))
        table.resizeColumnsToContents()
        table.setMaximumHeight(260)
        layout.addWidget(table)

        chart_props = [('Tm [C]', 'Tm'), ('deltaH [kJ/mol]', 'deltaH'), ('deltaS [J/mol/K]', 'deltaS'),
                       ('Fraction', 'fraction'), ('Width', 'width'), ('Span', 'span'),
                       ('R^2', 'r_squared'), ('RMSD', 'rmsd')]
        palette = ['tab:blue', 'tab:purple', 'tab:brown', 'tab:cyan', 'tab:orange',
                  'tab:green', 'tab:red', 'tab:pink', 'tab:gray', 'tab:olive']
        fit_colors = {name: palette[i % len(palette)] for i, name in enumerate(names)}
        # Fixed per-component colors (not per-fit) for the "grouped by
        # component" bar plot — matches the original prototype's own
        # convention (component 1 red, 2 green, 3 blue, 4 magenta).
        component_colors = {1: 'red', 2: 'green', 3: 'blue', 4: 'magenta'}

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Plot type:"))
        plot_type_combo = QComboBox()
        plot_type_combo.addItems(["Bar (1 property)", "Bar (grouped by component)",
                                  "Line & points (1 property)", "Points with mean/std band",
                                  "Scatter (2 properties)", "Scatter (3D, 3 properties)"])
        type_row.addWidget(plot_type_combo)
        type_row.addSpacing(16)
        prop_x_label = QLabel("Property:")
        type_row.addWidget(prop_x_label)
        prop_x_combo = QComboBox()
        type_row.addWidget(prop_x_combo)
        prop_y_label = QLabel("Y:")
        prop_y_combo = QComboBox()
        prop_z_label = QLabel("Z:")
        prop_z_combo = QComboBox()
        for combo in (prop_x_combo, prop_y_combo, prop_z_combo):
            for label, key in chart_props:
                combo.addItem(label, key)
        prop_y_combo.setCurrentIndex(1)
        prop_z_combo.setCurrentIndex(2)
        for w in (prop_y_label, prop_y_combo, prop_z_label, prop_z_combo):
            type_row.addWidget(w)
        type_row.addStretch()
        show_mean_std_check = QCheckBox("Show mean/std region (2D, per component)")
        show_mean_std_check.setToolTip(
            "Only applies to \"Scatter (2 properties)\": for each component\n"
            "number present, shades the mean\u00b1std rectangle across both axes\n"
            "and draws dashed crosshairs at the means — same idea as the\n"
            "1D mean/std band, extended to two properties at once, so you\n"
            "can see how far each point sits from its group's average in\n"
            "both dimensions simultaneously.")
        type_row.addWidget(show_mean_std_check)
        sort_by_value_check = QCheckBox("Sort by value")
        sort_by_value_check.setToolTip(
            "For Bar / Line & points / mean-std band: order points along\n"
            "the x-axis by ascending property value instead of the order\n"
            "fits were saved in — e.g. select Tm and check this to line\n"
            "every sample's transition up from lowest to highest\n"
            "temperature, an easy way to compare \"the 1st transition\"\n"
            "across samples once components are grouped this way.")
        type_row.addWidget(sort_by_value_check)
        layout.addLayout(type_row)

        figure = Figure(constrained_layout=True)
        canvas = FigureCanvas(figure)
        canvas.setMinimumHeight(320)
        layout.addWidget(canvas)

        def _update_property_controls():
            # 0=bar by fit, 1=bar by component, 2=line & points,
            # 3=points w/ mean/std band, 4=2D scatter, 5=3D scatter
            mode = plot_type_combo.currentIndex()
            prop_x_label.setText("Property:" if mode <= 3 else "X:")
            prop_y_label.setVisible(mode >= 4)
            prop_y_combo.setVisible(mode >= 4)
            prop_z_label.setVisible(mode == 5)
            prop_z_combo.setVisible(mode == 5)
            # Each of these only actually does anything for specific plot
            # types — grayed out otherwise, so it's never silently unclear
            # whether toggling one has any effect in the current mode.
            show_mean_std_check.setEnabled(mode == 4)
            sort_by_value_check.setEnabled(mode in (0, 2, 3))

        def _points_for(key):
            """(fit_name, component_label, value) for every row with a
            non-missing value of this property — sorted by ascending
            value if "Sort by value" is checked, otherwise in save order."""
            pts = []
            for row in all_rows:
                val = row.get(key)
                if val is None:
                    continue
                comp_txt = f"c{row['component']}" if row['component'] not in ('-', None) else ""
                pts.append((row['fit'], comp_txt, val))
            if sort_by_value_check.isChecked():
                pts.sort(key=lambda p: p[2])
            return pts

        def _redraw_chart():
            mode = plot_type_combo.currentIndex()
            figure.clear()

            if mode == 0:
                # One bar per row, colored by which FIT it came from —
                # good for comparing overall results across fits/samples.
                key = prop_x_combo.currentData()
                pts = _points_for(key)
                ax = figure.add_subplot(111)
                if pts:
                    labels = [f"{f}{(' ' + c) if c else ''}" for f, c, v in pts]
                    values = [v for f, c, v in pts]
                    colors = [fit_colors.get(f, 'tab:blue') for f, c, v in pts]
                    ax.bar(range(len(values)), values, color=colors)
                    ax.set_xticks(range(len(values)))
                    ax.set_xticklabels(labels, rotation=30, ha='right', fontsize=8)
                    ax.set_ylabel(prop_x_combo.currentText())
                    ax.grid(True, axis='y', alpha=0.4)
                else:
                    ax.text(0.5, 0.5, "No data for this property", transform=ax.transAxes,
                            ha='center', va='center')

            elif mode == 1:
                # One group of bars PER FIT, one bar per component within
                # each group, colored consistently BY COMPONENT NUMBER
                # (not by fit) — matches the original prototype's own
                # convention and its "bar plot for both fractions" style:
                # lets you compare e.g. "how big was component 1 across
                # every sample" at a glance, with each component's value
                # labeled on its bar.
                key = prop_x_combo.currentData()
                ax = figure.add_subplot(111)
                fit_comp_values = {}
                max_comp = 0
                for name in names:
                    comp_vals = {}
                    for r in all_rows:
                        if r['fit'] != name or r['component'] in ('-', None):
                            continue
                        val = r.get(key)
                        if val is None:
                            continue
                        comp_vals[r['component']] = val
                        max_comp = max(max_comp, r['component'])
                    fit_comp_values[name] = comp_vals
                if max_comp > 0:
                    n_fits = len(names)
                    width = 0.8 / max_comp
                    x_positions = np.arange(n_fits)
                    for comp_idx in range(1, max_comp + 1):
                        offset = (comp_idx - (max_comp + 1) / 2) * width
                        bar_x, bar_y = [], []
                        for i, name in enumerate(names):
                            val = fit_comp_values[name].get(comp_idx)
                            if val is None:
                                continue
                            bar_x.append(x_positions[i] + offset)
                            bar_y.append(val)
                        if not bar_x:
                            continue
                        color = component_colors.get(comp_idx, palette[(comp_idx - 1) % len(palette)])
                        bars = ax.bar(bar_x, bar_y, width=width, color=color,
                                      label=f'Component {comp_idx}')
                        ax.bar_label(bars, fmt='%.3g', fontsize=6, padding=1)
                    ax.set_xticks(x_positions)
                    ax.set_xticklabels(names, rotation=30, ha='right', fontsize=8)
                    ax.set_ylabel(prop_x_combo.currentText())
                    ax.legend(fontsize=7)
                    ax.grid(True, axis='y', alpha=0.4)
                else:
                    ax.text(0.5, 0.5, "No per-component data for this property\n"
                            "(need at least one multi-transition fit)",
                            transform=ax.transAxes, ha='center', va='center')

            elif mode == 2:
                # One connected line+points series per fit (its own
                # components in x-order), plus one more line & points
                # series joining every OTHER fit's values for the same
                # component index — same "line & points vs sample" style
                # as the original prototype's own span/enthalpy examples.
                key = prop_x_combo.currentData()
                ax = figure.add_subplot(111)
                pts = _points_for(key)
                if pts:
                    labels = [f"{f}{(' ' + c) if c else ''}" for f, c, v in pts]
                    values = [v for f, c, v in pts]
                    colors = [fit_colors.get(f, 'tab:blue') for f, c, v in pts]
                    xs = range(len(values))
                    ax.plot(xs, values, '--', color='lightgray', lw=1, zorder=1)
                    ax.scatter(xs, values, color=colors, s=60, zorder=2)
                    ax.set_xticks(list(xs))
                    ax.set_xticklabels(labels, rotation=30, ha='right', fontsize=8)
                    ax.set_ylabel(prop_x_combo.currentText())
                    ax.grid(True, alpha=0.4)
                else:
                    ax.text(0.5, 0.5, "No data for this property", transform=ax.transAxes,
                            ha='center', va='center')

            elif mode == 3:
                # Every point for the chosen property plotted against its
                # position in the list, with a dashed mean line and a
                # shaded +/-1 standard deviation band behind them — same
                # idea as the original prototype's "mean line" / "standard
                # deviation" reference figure, useful for spotting outliers
                # at a glance across every checked fit/component.
                key = prop_x_combo.currentData()
                ax = figure.add_subplot(111)
                pts = _points_for(key)
                if pts:
                    labels = [f"{f}{(' ' + c) if c else ''}" for f, c, v in pts]
                    values = np.array([v for f, c, v in pts], dtype=float)
                    colors = [fit_colors.get(f, 'tab:blue') for f, c, v in pts]
                    xs = np.arange(len(values))
                    mean_val = float(np.mean(values))
                    std_val = float(np.std(values))
                    ax.axhspan(mean_val - std_val, mean_val + std_val, color='tab:red', alpha=0.15)
                    ax.axhline(mean_val, color='tab:red', linestyle='--', lw=1.3, label='Mean')
                    ax.scatter(xs, values, color=colors, s=60, zorder=3)
                    ax.set_xticks(list(xs))
                    ax.set_xticklabels(labels, rotation=30, ha='right', fontsize=8)
                    ax.set_ylabel(prop_x_combo.currentText())
                    ax.legend(fontsize=7)
                    ax.grid(True, alpha=0.4)
                else:
                    ax.text(0.5, 0.5, "No data for this property", transform=ax.transAxes,
                            ha='center', va='center')

            elif mode == 4:
                key_x, key_y = prop_x_combo.currentData(), prop_y_combo.currentData()
                err_key_x = error_key_for(key_x)
                err_key_y = error_key_for(key_y)
                ax = figure.add_subplot(111)
                any_points = False

                mean_std_handles = []
                if show_mean_std_check.isChecked():
                    # Group by COMPONENT NUMBER across every checked fit
                    # (not by fit) — e.g. every fit's "component 1" forms
                    # one group, "component 2" forms another — matching
                    # the reference layout where each transition gets its
                    # own colored mean/std box across the whole sample set.
                    by_component = {}
                    for r in all_rows:
                        if r.get(key_x) is None or r.get(key_y) is None:
                            continue
                        comp = r['component'] if r['component'] not in ('-', None) else 0
                        by_component.setdefault(comp, []).append((r[key_x], r[key_y]))
                    for comp, pts in by_component.items():
                        if len(pts) < 2:
                            continue  # a single point has no meaningful std
                        xs_g = np.array([p[0] for p in pts], dtype=float)
                        ys_g = np.array([p[1] for p in pts], dtype=float)
                        mx, my = float(xs_g.mean()), float(ys_g.mean())
                        sx, sy = float(xs_g.std()), float(ys_g.std())
                        color = (component_colors.get(comp, 'gray') if comp
                                else 'gray')
                        ax.axvspan(mx - sx, mx + sx, color=color, alpha=0.12, zorder=0)
                        ax.axhspan(my - sy, my + sy, color=color, alpha=0.12, zorder=0)
                        ax.axvline(mx, color=color, linestyle='--', lw=1, alpha=0.6, zorder=1)
                        ax.axhline(my, color=color, linestyle='--', lw=1, alpha=0.6, zorder=1)
                        # A legend entry per group is the only way to know
                        # which color means which component — the shading
                        # alone doesn't say that anywhere on the plot.
                        comp_label = f"Component {comp} mean\u00b1std" if comp else "Ungrouped mean\u00b1std"
                        mean_std_handles.append(Patch(facecolor=color, alpha=0.3, label=comp_label))

                for name in names:
                    fit_rows = [r for r in all_rows
                               if r['fit'] == name and r.get(key_x) is not None and r.get(key_y) is not None]
                    if not fit_rows:
                        continue
                    any_points = True
                    xs = [r[key_x] for r in fit_rows]
                    ys = [r[key_y] for r in fit_rows]
                    xerr = ([r.get(err_key_x) for r in fit_rows] if err_key_x else None)
                    yerr = ([r.get(err_key_y) for r in fit_rows] if err_key_y else None)
                    # errorbar can't take a None inside its err array — drop
                    # to no-error-bar for this series if any point's err is
                    # actually missing (e.g. only 2 Arrhenius points).
                    if xerr and any(v is None for v in xerr):
                        xerr = None
                    if yerr and any(v is None for v in yerr):
                        yerr = None
                    ax.errorbar(xs, ys, xerr=xerr, yerr=yerr, fmt='o', color=fit_colors[name],
                               label=name, markersize=7, capsize=3, elinewidth=1, zorder=2)
                    for r in fit_rows:
                        label = r['fit']
                        if r['component'] not in ('-', None):
                            label += f" c{r['component']}"
                        ax.annotate(label, (r[key_x], r[key_y]), fontsize=6.5,
                                   xytext=(5, 4), textcoords='offset points')
                if any_points:
                    ax.set_xlabel(prop_x_combo.currentText())
                    ax.set_ylabel(prop_y_combo.currentText())
                    ax.grid(True, alpha=0.4)
                    handles, labels_ = ax.get_legend_handles_labels()
                    ax.legend(handles=handles + mean_std_handles,
                             labels=labels_ + [h.get_label() for h in mean_std_handles],
                             fontsize=7)
                else:
                    ax.text(0.5, 0.5, "No data for these properties", transform=ax.transAxes,
                            ha='center', va='center')

            else:
                key_x, key_y, key_z = (prop_x_combo.currentData(), prop_y_combo.currentData(),
                                       prop_z_combo.currentData())
                ax = figure.add_subplot(111, projection='3d')
                any_points = False
                for name in names:
                    fit_rows = [r for r in all_rows if r['fit'] == name]
                    pts3 = [(r[key_x], r[key_y], r[key_z], r) for r in fit_rows
                           if r.get(key_x) is not None and r.get(key_y) is not None
                           and r.get(key_z) is not None]
                    if not pts3:
                        continue
                    any_points = True
                    xs, ys, zs, rs = zip(*pts3)
                    ax.scatter(xs, ys, zs, color=fit_colors[name], label=name, s=50)
                    for x_, y_, z_, r in zip(xs, ys, zs, rs):
                        label = r['fit']
                        if r['component'] not in ('-', None):
                            label += f" c{r['component']}"
                        ax.text(x_, y_, z_, label, fontsize=6.5)
                if any_points:
                    ax.set_xlabel(prop_x_combo.currentText(), fontsize=8)
                    ax.set_ylabel(prop_y_combo.currentText(), fontsize=8)
                    ax.set_zlabel(prop_z_combo.currentText(), fontsize=8)
                    ax.legend(fontsize=7)
                else:
                    ax.text2D(0.5, 0.5, "No data for these properties", transform=ax.transAxes,
                             ha='center', va='center')

            canvas.draw()

        def error_key_for(prop_key):
            """Property -> its standard-error field name, for the ones
            that actually have one (Tm/deltaH/deltaS, from the Arrhenius
            regression) — Fraction/Width/Span/R^2/RMSD don't have a
            defined uncertainty in this model, so None for those."""
            return {'Tm': 'Tm_err', 'deltaH': 'deltaH_err', 'deltaS': 'deltaS_err'}.get(prop_key)

        plot_type_combo.currentIndexChanged.connect(_update_property_controls)
        plot_type_combo.currentIndexChanged.connect(_redraw_chart)
        prop_x_combo.currentIndexChanged.connect(_redraw_chart)
        prop_y_combo.currentIndexChanged.connect(_redraw_chart)
        prop_z_combo.currentIndexChanged.connect(_redraw_chart)
        show_mean_std_check.stateChanged.connect(_redraw_chart)
        sort_by_value_check.stateChanged.connect(_redraw_chart)
        _update_property_controls()
        _redraw_chart()

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy Table")

        def _copy_table():
            lines = ["\t".join(c[0] for c in columns)]
            for row in all_rows:
                lines.append("\t".join(_fmt(row.get(key)) for _, key in columns))
            QApplication.clipboard().setText("\n".join(lines))

        copy_btn.clicked.connect(_copy_table)
        btn_row.addWidget(copy_btn)
        save_btn = QPushButton("Save as CSV...")

        def _save_csv():
            path, _ = QFileDialog.getSaveFileName(
                dlg, "Save Summary", "saved_fits_summary.csv", "CSV files (*.csv);;All files (*)")
            if not path:
                return
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(",".join(c[0] for c in columns) + "\n")
                    for row in all_rows:
                        f.write(",".join(_fmt(row.get(key)) for _, key in columns) + "\n")
            except OSError as e:
                QMessageBox.warning(dlg, "Save Failed", f"Could not save to {path}:\n{e}")

        save_btn.clicked.connect(_save_csv)
        btn_row.addWidget(save_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        self._disable_wheel_scrolling(root=dlg)
        self._prevent_enter_from_closing_dialog(root=dlg)
        dlg.exec_()


    def perform_extraction(self, silent=False):
        if self.source_file_radio.isChecked():
            gathered = self._gather_curve_from_file(silent=silent)
        else:
            gathered = self._gather_curve_from_spectra(silent=silent)
        if gathered is None:
            return
        temps, y_values, source_labels, out_of_range, x_value = gathered
        if len(temps) < 2:
            # Nothing meaningful to build yet (e.g. real-time update
            # firing before there's enough data — an empty/near-empty
            # selection, or a table not populated yet). Not an error;
            # just nothing to do until there's at least 2 points.
            return
        self._finalize_curve(temps, y_values, source_labels, out_of_range, x_value, silent=silent)

    def _finalize_curve(self, temps, y_values, source_labels, out_of_range, x_value, silent=False):
        """Shared tail for both extraction sources: duplicate-temperature
        detection/averaging, building self.curve, and resetting/
        reconfiguring everything downstream (fit state, baseline slider
        ranges/defaults, normalization)."""
        temps_arr = np.asarray(temps, dtype=float)
        unique_temps, inverse, counts = np.unique(temps_arr, return_inverse=True, return_counts=True)
        # np.unique() already returns unique_temps sorted ascending.
        has_duplicates = np.any(counts > 1)

        if has_duplicates and not silent:
            # A melting curve needs exactly one signal value per
            # temperature — extraction/normalization/fitting all treat
            # temperature as the unique independent variable, so two rows
            # sharing one temperature aren't something the model can
            # represent as two distinct points. Rather than just refusing
            # or silently guessing, offer to average them into one point
            # per temperature, but only after explicitly telling the user
            # which values are affected.
            dup_desc = ", ".join(f"{t:g} (x{c})" for t, c in zip(unique_temps, counts) if c > 1)
            reply = QMessageBox.question(
                self, "Duplicate Temperatures Found",
                "These temperature value(s) appear more than once:\n\n"
                f"{dup_desc}\n\n"
                "A melting curve needs one signal value per temperature. Average "
                "the signal for each duplicated temperature into a single point?\n\n"
                "Choose No to cancel so you can fix the source data instead.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        # Average duplicate-temperature rows' extracted signal into one
        # point each (a no-op when there are no duplicates — every group
        # then has exactly one member, so "averaging" it is just itself).
        # In silent mode (settings restore) this happens without prompting
        # since there's no user present to ask.
        x_sorted = unique_temps
        y_sorted = np.array([y_values[inverse == i].mean() for i in range(len(unique_temps))])

        svd_diagnostics = self._pending_svd_diagnostics
        self._pending_svd_diagnostics = None
        self.curve = {
            'x_temperature': x_sorted,
            'y_raw': y_sorted,
            'x_value': x_value,
            'source_labels': source_labels,
            'svd_diagnostics': svd_diagnostics,
        }
        self._update_svd_diagnostics_label(svd_diagnostics)
        # Reset anything downstream — a new extraction invalidates any
        # previous normalization/fit.
        self.normalization_result = None
        self.x_trans = None
        self.fit_result = None
        self.component_thermodynamics = None
        self.fit_results_table.setRowCount(0)
        self.fit_quality_label.setText("R^2: -    RMSD: -")
        self._reset_initial_guesses()

        t_min, t_max = float(x_sorted.min()), float(x_sorted.max())

        # A baseline region can't logically extend beyond the actual
        # measured temperature range, so the spin boxes' allowed range is
        # set to exactly [t_min, t_max] here — BEFORE the defaults below
        # are applied, so a shrinking/shifting range on a later
        # re-extraction can never clamp a default that's still perfectly
        # valid for the OLD range but happens to be outside the spin's
        # stale bounds from before.
        for spin in (self.low_min_spin, self.low_max_spin,
                    self.high_min_spin, self.high_max_spin):
            spin.setRange(t_min, t_max)

        # Default the baseline regions to the outer ~15% of the temperature
        # span, only the first time (don't clobber a user's own choice on
        # every re-extraction). Uses an explicit flag rather than checking
        # for a "0, 0" sentinel value — the setRange() call just above can
        # itself clamp a leftover 0.0 up to the new t_min, which would
        # otherwise make this look like "already customized" and silently
        # skip applying any default at all.
        span = t_max - t_min if t_max > t_min else 1.0
        if not self._baseline_defaults_set:
            self.low_min_spin.setValue(t_min)
            self.low_max_spin.setValue(t_min + 0.15 * span)
            self.high_min_spin.setValue(t_max - 0.15 * span)
            self.high_max_spin.setValue(t_max)
            self._baseline_defaults_set = True

        if out_of_range and not silent:
            QMessageBox.warning(
                self, "X Value Out of Range",
                "The chosen X value falls outside the x-axis range of these spectra "
                "(interpolation was clamped to the nearest edge value):\n\n"
                + ", ".join(out_of_range[:15]) + ("..." if len(out_of_range) > 15 else ""))

        self._configure_baseline_sliders()

        # Recompute normalization synchronously (if a method is selected)
        # rather than leaving it to happen as a side effect of the
        # baseline-defaults value-changed chain above — that chain only
        # ever fires the first time a given curve is extracted, so on
        # every subsequent re-extraction (same X value or a new one)
        # normalization_result would otherwise stay stale/None even
        # though the Method combo still shows e.g. "First order (linear)"
        # selected. That mismatch (a method shown as active but not
        # actually applied yet) was the direct cause of the reported
        # "uncheck both curve panels, Extract Curve again, re-check them"
        # bug: the guess-preview curve ended up drawn on the Original
        # (raw-scale) panel because normalization genuinely hadn't run.
        if self.norm_combo.currentIndex() != 0:
            self._run_current_normalization(silent=True)
        else:
            self.update_plot()

    def _update_svd_diagnostics_label(self, svd_diagnostics):
        """Show/hide svd_diagnostics_label from an SVD extraction's own
        diagnostics dict (None for any curve not built via SVD — the
        label is simply hidden then, same as the Automatic-mode banner
        outside Automatic mode)."""
        if not svd_diagnostics:
            self.svd_diagnostics_label.setVisible(False)
            return
        pc1 = svd_diagnostics.get('explained_variance_pc1')
        pc2 = svd_diagnostics.get('explained_variance_pc2')
        wl_range = svd_diagnostics.get('wavelength_range')
        text = "SVD extraction: "
        if pc1 is not None and np.isfinite(pc1):
            text += f"PC1 explains {pc1 * 100:.1f}% of variance"
        if pc2 is not None and np.isfinite(pc2):
            text += f", PC2 {pc2 * 100:.1f}%"
        if wl_range:
            text += f" (x-axis range used: {wl_range[0]:.2f} to {wl_range[1]:.2f})"
        self.svd_diagnostics_label.setText(text)
        self.svd_diagnostics_label.setVisible(True)

    def on_canvas_key_press(self, event):
        """Interactive baseline picking: zoom/pan the plot to frame a
        region, then press 'b' to capture the currently-visible x-range
        as a baseline region — same "zoom, press 'b', repeat for the
        other baseline" workflow as the original thermoanalysis
        prototype. Whichever of Low-T / High-T region the framed range's
        center is nearer to (by temperature, not by folded/unfolded
        state — see normalize_melting_curve()'s docstring for why those
        aren't assumed to correspond to low/high temperature) is the one
        that gets updated, so re-picking one baseline never disturbs the
        other.

        Deliberately does NOT try to restore the just-picked zoomed view
        afterward (an earlier version did) — update_plot() resets to the
        full curve on every redraw, which turns out to be the more
        convenient behavior here: no separate Home-button press is
        needed between picking the two regions.
        """
        if event.key not in ('b', 'B'):
            return
        if not self.pick_baseline_check.isChecked():
            return
        if self.curve is None or self.ax_main is None:
            return
        if self.norm_combo.currentIndex() == 3:
            # Automatic mode picks its own baseline regions — nothing
            # for interactive picking to do here.
            return

        x_lo, x_hi = self.ax_main.get_xlim()
        if x_lo > x_hi:
            x_lo, x_hi = x_hi, x_lo
        center = (x_lo + x_hi) / 2.0

        t_median = float(np.median(self.curve['x_temperature']))
        if center <= t_median:
            self.low_min_spin.setValue(x_lo)
            self.low_max_spin.setValue(x_hi)
            target = "Low-T"
        else:
            self.high_min_spin.setValue(x_lo)
            self.high_max_spin.setValue(x_hi)
            target = "High-T"
        logger.debug(f"on_canvas_key_press: captured {target} baseline region "
                    f"[{x_lo:.4g}, {x_hi:.4g}]")

        # Give immediate visual feedback: if a normalization method is
        # already selected, recompute it with the newly picked region so
        # the shaded baseline bands and normalized curve update live,
        # same as pressing "Apply Normalization" manually would.
        if self.norm_combo.currentIndex() != 0:
            self.perform_normalization(silent=True)
        else:
            self.update_plot()

    # ------------------------------------------------------------------ #
    # Real-time baseline sliders                                          #
    # ------------------------------------------------------------------ #

    def _configure_baseline_sliders(self):
        """(Re)compute the sliders' temperature domain from the freshly
        extracted curve, and snap all four handles to match whatever is
        currently in the spin boxes. Called after every extraction (fresh
        or restored from a previous run's settings) so the sliders track
        the curve even if the temperature range changed."""
        if self.curve is None:
            return
        t_min = float(self.curve['x_temperature'].min())
        t_max = float(self.curve['x_temperature'].max())
        # Exactly the data range — no padding beyond it. A baseline
        # region is a range of actual data points to fit, so letting the
        # slider (or spin box; see perform_extraction's setRange call)
        # reach past the measured temperatures never made sense, and was
        # how the reported "High-T Min=114.44 > Max=95.09" (both well
        # past this dataset's real ~5-99 range) state was reached.
        self._slider_domain = (t_min, t_max)

        self._syncing_baseline_controls = True
        try:
            for spin, slider in (
                (self.low_min_spin, self.low_min_slider),
                (self.low_max_spin, self.low_max_slider),
                (self.high_min_spin, self.high_min_slider),
                (self.high_max_spin, self.high_max_slider),
            ):
                slider.setValue(self._temp_to_slider(spin.value()))
        finally:
            self._syncing_baseline_controls = False

    def _temp_to_slider(self, temp):
        lo, hi = self._slider_domain
        if hi <= lo:
            return 0
        frac = (temp - lo) / (hi - lo)
        frac = min(max(frac, 0.0), 1.0)
        return int(round(frac * self._SLIDER_STEPS))

    def _slider_to_temp(self, value):
        lo, hi = self._slider_domain
        return lo + (value / self._SLIDER_STEPS) * (hi - lo)

    def _sync_spin_from_slider(self, spin, slider, slider_value):
        """Slider moved (by the user dragging it) -> update its paired
        spin box, then schedule a live redraw. Guarded against re-entrancy
        since spin.setValue() below fires the spin's own valueChanged,
        which is connected to _sync_slider_from_spin (suppressed by the
        guard while this is running).

        After setting the spin box, the slider is explicitly repositioned
        to match whatever the spin box actually ended up holding — NOT
        assumed to still match slider_value. The spin box's value can get
        silently clamped (by its own [t_min, t_max] range, or by the
        min<=max cross-constraint with its paired min/max spin box — see
        _build_normalization_group), and since the nested valueChanged
        that would normally re-sync the slider is suppressed by the guard
        above, skipping this step left the slider showing a raw dragged
        position that no longer matched its own spin box at all — the
        reported "sliders stop working" symptom (every subsequent drag
        computed a delta from that stale, out-of-sync position)."""
        if self._syncing_baseline_controls:
            return
        self._syncing_baseline_controls = True
        try:
            spin.setValue(self._slider_to_temp(slider_value))
            slider.setValue(self._temp_to_slider(spin.value()))
        finally:
            self._syncing_baseline_controls = False
        self._schedule_live_baseline_update()

    def _sync_slider_from_spin(self, spin, slider, spin_value):
        """Spin box changed (typed, or set programmatically by extraction
        defaults / the 'b'-key picker / restored settings / the
        min<=max cross-constraint) -> move its paired slider handle to
        match, then schedule a live redraw. Same re-entrancy guard as
        _sync_spin_from_slider. spin_value is already authoritative here
        (it's what the spin box itself just settled on), so there's no
        equivalent clamping round-trip needed in this direction."""
        if self._syncing_baseline_controls:
            return
        self._syncing_baseline_controls = True
        try:
            slider.setValue(self._temp_to_slider(spin_value))
        finally:
            self._syncing_baseline_controls = False
        self._schedule_live_baseline_update()

    def _schedule_live_baseline_update(self):
        """Debounce baseline-boundary changes (a slider drag fires many
        valueChanged events per second) into one redraw roughly every
        30 ms — real-time-feeling without recomputing/redrawing on every
        single intermediate value."""
        if self.curve is None:
            return
        self._baseline_update_timer.start(30)

    def _live_baseline_update(self):
        if self.norm_combo.currentIndex() != 0:
            self._run_current_normalization(silent=True)
        else:
            self.update_plot()

    def _on_norm_method_changed(self, index):
        """Switching the normalization method (None / Zero order / First
        order / Automatic) takes effect immediately, same as dragging a
        slider — matches this dialog's "everything above the plot is
        live" feel rather than requiring an extra "Apply" click just to
        see a method change."""
        is_automatic = (index == 3)
        self._set_automatic_mode_enabled(is_automatic)
        if is_automatic:
            self.perform_automatic_fit(silent=False)
        elif index == 0:
            self.normalization_result = None
            self.x_trans = None
            self._automatic_fit_result = None
            self.automatic_fit_banner.setVisible(False)
            self.update_plot()
        else:
            self._automatic_fit_result = None
            self.automatic_fit_banner.setVisible(False)
            self.perform_normalization(silent=True)

    def _run_current_normalization(self, silent=True):
        """Dispatch to whichever baseline/fit pipeline the Method combo
        currently selects — the ordinary per-window normalize (None/Zero
        order/First order, via perform_normalization) or the new
        Automatic joint Santoro-Bolen fit (perform_automatic_fit). Shared
        by every place that used to call perform_normalization()
        unconditionally whenever a method other than None was selected
        (a fresh extraction, and restoring a previous run's settings) so
        Automatic mode is picked up there too without duplicating this
        dispatch."""
        if self.norm_combo.currentIndex() == 3:
            self.perform_automatic_fit(silent=silent)
        else:
            self.perform_normalization(silent=silent)

    def _set_automatic_mode_enabled(self, is_automatic):
        """Automatic mode determines the baseline regions AND the
        component count itself — the manual baseline sliders/spin boxes,
        the Components spinner, Auto-detect Transitions, and the guesses/
        fit-results table's editability all belong to the Manual
        workflow specifically, so they're disabled (not hidden — their
        values still update to show what Automatic actually settled on,
        so switching back to Manual starts from a sensible place) rather
        than removed. The Fit button and Shape combo stay enabled: Fit
        simply re-runs the automatic pipeline on demand in this mode
        (e.g. after changing Shape), which needs no special-casing since
        perform_automatic_fit is idempotent for unchanged inputs."""
        for w in (self.low_min_spin, self.low_max_spin, self.high_min_spin, self.high_max_spin,
                 self.low_min_slider, self.low_max_slider, self.high_min_slider, self.high_max_slider,
                 self.n_components_spin, self.auto_detect_btn):
            w.setEnabled(not is_automatic)
        self.fit_results_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers if is_automatic else QAbstractItemView.DoubleClicked)

    def _on_span_changed(self, value):
        """Live-preview which points the threshold would keep for the
        Arrhenius fit (drawn in red on the normalized-curve plot) as the
        spinbox changes — cheap (no fit involved), so no debouncing
        needed, unlike the baseline sliders. Also refreshes each
        component's own Arrhenius/thermodynamics if a multi-transition
        fit already exists, since they use this same threshold.

        In Automatic mode, the whole joint fit + Arrhenius + reliability
        verdict is re-run instead: unlike Manual mode (where the sigmoid
        SHAPE fit and the Arrhenius span are fully independent — see
        perform_fit's own docstring note), Automatic mode's reliability
        gates (Arrhenius R^2, Tm_in_fit_range) are themselves computed
        AT this span, so a span change can change the verdict, not just
        which points are highlighted."""
        if self.norm_combo.currentIndex() == 3:
            if self._automatic_fit_result is not None:
                self.perform_automatic_fit(silent=True)
        elif self.normalization_result is not None:
            self._recompute_component_thermodynamics()
            self.update_plot()

    def perform_normalization(self, silent=False):
        if self.curve is None:
            if not silent:
                QMessageBox.information(self, "No Curve", "Extract a curve first.")
            return

        method_idx = self.norm_combo.currentIndex()
        if method_idx == 0:
            self.normalization_result = None
            self.x_trans = None
            self.baseline_cross_warning.setVisible(False)
            self.update_plot()
            return
        order = 0 if method_idx == 1 else 1

        low_range = (self.low_min_spin.value(), self.low_max_spin.value())
        high_range = (self.high_min_spin.value(), self.high_max_spin.value())

        result = self.manager.normalize_melting_curve(
            self.curve['x_temperature'], self.curve['y_raw'], low_range, high_range, order=order)

        if result is None:
            if not silent:
                QMessageBox.warning(self, "Normalization Failed",
                                    "No data points fall inside one or both baseline regions. "
                                    "Widen the Low-T / High-T ranges.")
            return

        self.normalization_result = result
        self._update_baseline_cross_warning(result)
        self.x_trans = self.manager.compute_median_crossing_temperature(
            self.curve['x_temperature'], self.curve['y_raw'],
            result['baseline_low'], result['baseline_high'])
        # Re-run each component's Arrhenius/thermodynamics against the
        # NEW unstable_mask whenever a fit already exists and baseline
        # regions change (dragging a slider, editing the spin boxes, or
        # switching normalization method/order) — otherwise the
        # thermodynamics table would keep showing values computed
        # against the OLD (possibly unstable) normalization until the
        # user happened to touch Span or re-run Fit. No-op if there's no
        # fit yet (see _recompute_component_thermodynamics).
        self._recompute_component_thermodynamics()
        self.update_plot()

    def _update_baseline_cross_warning(self, result):
        """Show/hide and fill in baseline_cross_warning's text from this
        normalization's own 'unstable_mask' — visible whenever at least
        one point is unstable (a strict superset of 'baselines_cross':
        two baselines that come CLOSE without technically crossing are
        just as unstable, see normalize_melting_curve's docstring), with
        the actual excluded-point count so it's clear this isn't merely
        a cosmetic warning — those points are genuinely left out of every
        Arrhenius/van't Hoff fit from here on (see
        _recompute_component_thermodynamics's exclude_mask)."""
        unstable_mask = result.get('unstable_mask')
        n_unstable = int(np.sum(unstable_mask)) if unstable_mask is not None else 0
        if n_unstable == 0:
            self.baseline_cross_warning.setVisible(False)
            return
        point_word = 'point' if n_unstable == 1 else 'points'
        self.baseline_cross_warning.setText(
            f"⚠ Low-T and High-T baseline fits cross (or nearly cross) within "
            f"this curve's own range — {n_unstable} nearby {point_word} excluded "
            f"from the van't Hoff/Arrhenius fit as unreliable (normalization was "
            f"dividing by a near-zero number there). This is often a sign the "
            f"shaded baseline region(s) don't actually capture a flat plateau — "
            f"worth checking visually, not just trusting the numbers. Try "
            f"narrower or better-placed baseline regions.")
        self.baseline_cross_warning.setVisible(True)

    # ------------------------------------------------------------------ #
    # Automatic (Santoro-Bolen) mode                                       #
    # ------------------------------------------------------------------ #

    def perform_automatic_fit(self, silent=False):
        """Automatic mode's counterpart to perform_normalization() +
        perform_fit() combined — see MeltingCurveManager.fit_automatic's
        own docstring for the full joint-fit/model-selection/reliability
        pipeline this runs. Populates normalization_result/x_trans/
        fit_result from the SAME dict shapes normalize_melting_curve/
        compute_median_crossing_temperature/fit_sigmoid_model already
        produce in Manual mode, so every other part of this dialog
        (plotting, the thermodynamics table, Fit Details, Compare to
        Known Values, and the output spectra the controller builds on
        OK) reads an Automatic-mode result exactly the same way, with no
        special-casing needed anywhere else."""
        if self.curve is None:
            if not silent:
                QMessageBox.information(self, "No Curve", "Extract a curve first.")
            return

        x = self.curve['x_temperature']
        y = self.curve['y_raw']
        shape_name = self.shape_combo.currentText()

        result = self.manager.fit_automatic(x, y, shape_name=shape_name,
                                            arrhenius_span=self.span_spin.value())
        self._automatic_fit_result = result
        self._update_automatic_fit_banner(result)

        if not result['success']:
            self.normalization_result = None
            self.x_trans = None
            self.fit_result = None
            self.component_thermodynamics = None
            self.fit_results_table.setRowCount(0)
            self.fit_quality_label.setText("R^2: -    RMSD: -")
            self.baseline_cross_warning.setVisible(False)
            if not silent:
                QMessageBox.warning(self, "Automatic Fit Unavailable", result['reason'])
            self.update_plot()
            return

        self.normalization_result = result['norm']
        self.x_trans = result['Tm_crossing']
        self.fit_result = result['sigmoid_fit']  # None only if the (rare) normalized-
                                                  # space re-fit itself failed even
                                                  # though the raw-curve joint fit
                                                  # succeeded — everything else above
                                                  # (baselines, Tm_crossing, thermo)
                                                  # still stands on its own in that case.
        self._fit_is_preview = False
        self._initial_guesses = []
        self._update_baseline_cross_warning(result['norm'])

        # Reflect what Automatic actually settled on in the (disabled)
        # Components spinner and the (disabled, view-only) baseline spin
        # boxes — blocked from re-triggering their own valueChanged
        # handlers (_on_n_components_changed would otherwise discard the
        # very fit_result just set above via _reset_initial_guesses, and
        # the baseline spins' handlers would kick off a live-baseline-
        # update recompute using the OLD, manual code path).
        global_fit = result['global_fit']
        self.n_components_spin.blockSignals(True)
        self.n_components_spin.setValue(global_fit['n_components'])
        self.n_components_spin.blockSignals(False)
        if result['low_range'] is not None and result['high_range'] is not None:
            for spin, val in ((self.low_min_spin, result['low_range'][0]),
                             (self.low_max_spin, result['low_range'][1]),
                             (self.high_min_spin, result['high_range'][0]),
                             (self.high_max_spin, result['high_range'][1])):
                spin.blockSignals(True)
                spin.setValue(val)
                spin.blockSignals(False)
            self._configure_baseline_sliders()

        if self.fit_result is not None:
            self._populate_fit_results_table()
            q = self.fit_result['quality']
            self.fit_quality_label.setText(f"R^2: {q['r_squared']:.4f}    RMSD: {q['rmsd']:.4g}")
        else:
            self.fit_results_table.setRowCount(0)
            self.fit_quality_label.setText("R^2: -    RMSD: - (normalized-space re-fit failed)")

        self._recompute_component_thermodynamics()
        self.update_plot()

    def _update_automatic_fit_banner(self, result):
        """Fill in and show/hide automatic_fit_banner from fit_automatic's
        own result — red when it was rejected outright (result['reason']
        explains why), amber when a fit was found but failed one or more
        of the 6 reliability gates (named individually, with their actual
        values, so the user can judge for themselves rather than trusting
        a bare yes/no), green when it passed all of them."""
        if result is None:
            self.automatic_fit_banner.setVisible(False)
            return

        if not result['success']:
            self.automatic_fit_banner.setText(f"✗ {result['reason']}")
            self.automatic_fit_banner.setStyleSheet(
                "color: #7f1d1d; background-color: #fee2e2; padding: 4px; border-radius: 3px;")
            self.automatic_fit_banner.setVisible(True)
            return

        gates = result['reliability_gates']
        n = result['global_fit']['n_components']
        if result['reliable']:
            r2 = result['arrhenius_r_squared']
            self.automatic_fit_banner.setText(
                f"✓ Automatic fit: {n} component(s), Arrhenius R²="
                f"{r2:.4f} — passes every reliability check below.")
            self.automatic_fit_banner.setStyleSheet(
                "color: #14532d; background-color: #dcfce7; padding: 4px; border-radius: 3px;")
            self.automatic_fit_banner.setVisible(True)
            return

        gate_labels = {
            'arrhenius_r_squared_ok':
                f"Arrhenius R² = {result['arrhenius_r_squared']:.4f} "
                f"(need ≥ {ARRHENIUS_CONFIDENCE_R2_THRESHOLD:.2f})"
                if result['arrhenius_r_squared'] is not None else "Arrhenius R² unavailable",
            'tm_in_measured_range': "Tm falls outside the measured temperature range",
            'no_baseline_crossing_near_transition':
                "the Low-T/High-T baselines cross near the transition itself",
            'tm_in_fit_range': "Tm falls outside the actual van't Hoff fit window",
            'sigmoid_r_squared_ok':
                (f"sigmoid-fit R² = {result['sigmoid_r_squared']:.4f} "
                 f"(need ≥ {SIGMOID_CONFIDENCE_R2_THRESHOLD:.2f})"
                 if result['sigmoid_r_squared'] is not None else "sigmoid-fit R² unavailable"),
            'edge_error_ok':
                (f"the fitted baseline misses the data by "
                 f"{result['edge_error_fraction'] * 100:.0f}% of the curve's amplitude at an edge "
                 f"(limit {EDGE_TOLERANCE_ABSOLUTE_FRACTION * 100:.0f}%)"
                 if result['edge_error_fraction'] is not None else "edge tracking unavailable"),
        }
        failed = [gate_labels[k] for k, ok in gates.items() if not ok]
        self.automatic_fit_banner.setText(
            f"⚠ Automatic fit found ({n} component(s)) but did not pass every "
            f"reliability check — treat these numbers with caution, or switch to Manual "
            f"mode: " + "; ".join(failed) + ".")
        self.automatic_fit_banner.setStyleSheet(
            "color: #b45309; background-color: #fff3cd; padding: 4px; border-radius: 3px;")
        self.automatic_fit_banner.setVisible(True)

    def _on_plot_visibility_toggled(self, state):
        if self.curve is not None:
            self.update_plot()

    # Same colors update_plot() uses for each component's own panel
    # (tab:blue, tab:purple, tab:brown, tab:cyan) — kept as one shared
    # constant so the plot and this table can never drift apart.
    _COMPONENT_COLORS = ['#1f77b4', '#9467bd', '#8c564b', '#17becf']

    def _toggle_thermo_table(self):
        visible = not self.thermo_table.isVisible()
        self.thermo_table.setVisible(visible)
        self.thermo_table_toggle_btn.setText(
            ("\u25bc" if visible else "\u25b6") + " Thermodynamic parameters (per component)")

    def _toggle_guesses_table(self):
        visible = not self.fit_results_table.isVisible()
        self.fit_results_table.setVisible(visible)
        self.guesses_table_toggle_btn.setText(
            ("\u25bc" if visible else "\u25b6") + " Starting guesses / fit results")

    @staticmethod
    def _size_table_for_rows(table, n_rows, max_rows=4):
        """Set a table's height to fit exactly its current row count (up
        to max_rows, the most this app's components/thermodynamics
        tables ever have) so every row is visible without needing to
        scroll — while still capping the height for a currently-smaller
        row count, rather than always reserving space for the maximum.
        n_rows=0 shows just the header (an empty table still needs a
        visible home to click back into)."""
        header_h = table.horizontalHeader().height()
        row_h = table.verticalHeader().defaultSectionSize()
        frame = 2 * table.frameWidth()
        shown_rows = max(1, min(n_rows, max_rows)) if n_rows == 0 else min(n_rows, max_rows)
        height = header_h + row_h * shown_rows + frame + 2
        table.setMinimumHeight(height)
        table.setMaximumHeight(height)

    def _populate_thermo_table(self):
        """(Re)fill the collapsible per-component thermodynamics table —
        Tm, deltaH, deltaS (with standard-error estimates where
        available), and deltaG at the chosen reference temperature — one
        row per fitted component, text colored to match that
        component's color on the plot. Safe to call anytime (clears
        itself if there's no fit)."""
        self.thermo_table.setRowCount(0)
        if not self.component_thermodynamics:
            self._size_table_for_rows(self.thermo_table, 0)
            return
        ref_t = self.thermo_ref_temp_spin.value()
        self.thermo_table.setRowCount(len(self.component_thermodynamics))
        self._size_table_for_rows(self.thermo_table, len(self.component_thermodynamics))

        def fmt(val, err, decimals=2):
            if val is None:
                return "-"
            if err is not None:
                return f"{val:.{decimals}f} \u00b1 {err:.{decimals}f}"
            return f"{val:.{decimals}f}"

        for i, comp in enumerate(self.component_thermodynamics):
            th = comp.get('thermodynamics')
            color = self._COMPONENT_COLORS[i % len(self._COMPONENT_COLORS)]
            if th:
                tm_txt = fmt(th['Tm'], th.get('Tm_err'))
                dh_err = th.get('deltaH_err')
                dh_txt = fmt(th['deltaH'] / 1000, dh_err / 1000 if dh_err is not None else None)
                ds_txt = fmt(th['deltaS'], th.get('deltaS_err'))
                dg = self.manager.compute_delta_g(th['deltaH'], th['deltaS'], ref_t)
                dg_txt = fmt(dg / 1000 if dg is not None else None, None)
            else:
                tm_txt = dh_txt = ds_txt = dg_txt = "-"
            for col, text in enumerate([str(i + 1), tm_txt, dh_txt, ds_txt, dg_txt]):
                item = QTableWidgetItem(text)
                item.setForeground(QBrush(QColor(color)))
                self.thermo_table.setItem(i, col, item)

    def _recompute_component_thermodynamics(self):
        """(Re)compute each fitted sigmoid component's own Arrhenius plot
        and thermodynamic parameters — see
        MeltingCurveManager.compute_component_thermodynamics, which uses
        each component's REAL reconstructed data (matching exactly what
        gets plotted), not a theoretical noise-free curve — using the
        latter would make this a circular restatement of the fit's own
        parameters rather than an independent check. No-op if there's no
        fit yet."""
        if self.fit_result is None:
            self.component_thermodynamics = None
            return
        y_measured = (self.normalization_result['y_norm']
                     if self.normalization_result is not None else self.curve['y_raw'])
        # Points flagged unstable by the SAME normalization that produced
        # y_measured — see normalize_melting_curve's 'unstable_mask' doc
        # and the baseline_cross_warning label below — are excluded from
        # every component's own Arrhenius/van't Hoff regression, not just
        # filtered by the ordinary span threshold. Without this, a point
        # sitting near a low-T/high-T baseline crossing can have a
        # spurious-but-finite y_norm that passes the span filter
        # undetected and silently distorts deltaH/Tm by an order of
        # magnitude — confirmed on real data.
        exclude_mask = (self.normalization_result.get('unstable_mask')
                        if self.normalization_result is not None else None)
        self.component_thermodynamics = self.manager.compute_component_thermodynamics(
            self.curve['x_temperature'], y_measured, self.fit_result['y_fit'],
            self.fit_result['components']['params'],
            self.fit_result['shape_name'], span=self.span_spin.value(),
            exclude_mask=exclude_mask)

    def _default_initial_guesses(self, n):
        """Evenly-spaced default starting guesses for n components: equal
        1/n fractions, midpoints spread across the curve's temperature
        range, and a shared default width (1/10th of the range) — same
        defaults fit_sigmoid_model itself falls back to when no guesses
        are given, just made visible/editable up front instead of
        hidden inside the fit call."""
        if self.curve is None:
            return []
        x = self.curve['x_temperature']
        x_min, x_max = float(x.min()), float(x.max())
        span = x_max - x_min if x_max > x_min else 1.0
        width = max(span / 10.0, 1e-6)
        mids = np.linspace(x_min, x_max, n + 2)[1:-1]
        return [{'factor': 1.0 / n, 'midpoint': float(m), 'width': width} for m in mids]

    def _reset_initial_guesses(self):
        """Discard any existing fit/guesses and populate the table with
        fresh evenly-spaced defaults for the current component count —
        called on a new extraction and whenever Components/Shape changes,
        since a fit or set of guesses for a different component count no
        longer applies."""
        self.fit_result = None
        self.component_thermodynamics = None
        self.fit_quality_label.setText("R^2: -    RMSD: -")
        n = self.n_components_spin.value()
        self._initial_guesses = self._default_initial_guesses(n)
        self._populate_guesses_table(self._initial_guesses)
        self._rebuild_fit_from_current_table()

    def _on_n_components_changed(self, _value):
        if self._suppress_auto_update:
            return
        if self.curve is None:
            return
        if self.norm_combo.currentIndex() == 3:
            # Automatic mode: Components is disabled/view-only (Automatic
            # picks it), but Shape is still live and also wired to this
            # same slot — a Shape change here means re-run the whole
            # joint fit with the new shape, not reset to manual guesses.
            if self._automatic_fit_result is not None:
                self.perform_automatic_fit(silent=True)
            return
        self._reset_initial_guesses()
        self.update_plot()

    def _populate_guesses_table(self, guesses):
        """Fill fit_results_table with pre-fit initial guesses — editable
        (unlike the '#' index column), distinguished from a post-fit
        results table only by self._initial_guesses being non-empty."""
        self._populating_guess_table = True
        try:
            self.fit_results_table.setRowCount(len(guesses))
            self._size_table_for_rows(self.fit_results_table, len(guesses))
            for i, g in enumerate(guesses):
                idx_item = QTableWidgetItem(str(i + 1))
                idx_item.setFlags(idx_item.flags() & ~Qt.ItemIsEditable)
                self.fit_results_table.setItem(i, 0, idx_item)
                self.fit_results_table.setItem(i, 1, QTableWidgetItem(f"{g['factor']:.3f}"))
                self.fit_results_table.setItem(i, 2, QTableWidgetItem(f"{g['midpoint']:.3f}"))
                self.fit_results_table.setItem(i, 3, QTableWidgetItem(f"{g['width']:.3f}"))
        finally:
            self._populating_guess_table = False

    def _read_guesses_from_table(self):
        """Parse the table's current Fraction/Midpoint/Width columns back
        into the same list-of-dicts shape _default_initial_guesses
        returns — used both to keep self._initial_guesses in sync with
        user edits (_on_guess_table_edited) and to feed Fit with whatever
        is currently shown, including any hand-edited values. Tolerant
        of the "value \u00b1 error" format _populate_fit_results_table shows
        after a fit — only the value before "\u00b1" is used as a guess,
        the standard error itself was never meant to be re-parsed as a
        starting point. Returns None if any row has invalid (non-numeric)
        content."""
        def parse_value(text):
            return float(text.split('\u00b1')[0].strip())

        guesses = []
        for row in range(self.fit_results_table.rowCount()):
            try:
                factor = parse_value(self.fit_results_table.item(row, 1).text())
                midpoint = parse_value(self.fit_results_table.item(row, 2).text())
                width = parse_value(self.fit_results_table.item(row, 3).text())
            except (ValueError, AttributeError):
                return None
            guesses.append({'factor': factor, 'midpoint': midpoint, 'width': width})
        return guesses

    def _rebuild_fit_from_current_table(self):
        """Rebuild self.fit_result and self.component_thermodynamics
        directly from whatever's currently in the guesses/fit-results
        table — evenly-spaced defaults, Auto-detect's estimate, or
        hand-edited values — using the same manager functions a real
        Fit uses (sigmoid_sum_model, get_sigmoid_components,
        estimate_fit_quality, compute_component_thermodynamics), just
        skipping the curve_fit OPTIMIZATION step, since here the
        parameters are being specified directly rather than searched
        for. This is what keeps the plot, the per-component
        thermodynamics table, and the per-component detail panels all
        showing the SAME current values consistently, live, as you
        type — rather than the thermodynamics table only ever
        reflecting the last real optimizer run (or staying empty
        entirely before one has happened).

        Marks the result as a preview (self._fit_is_preview = True) so
        the quality label can say so — clicking Fit always replaces
        this with a genuine optimizer result (and its real parameter
        uncertainties, which a preview reconstruction has no way to
        provide). No-op if there's no curve yet or the table's content
        can't be parsed as numbers."""
        if self.curve is None:
            return
        guesses = self._read_guesses_from_table()
        if not guesses:
            return

        x = self.curve['x_temperature']
        y = (self.normalization_result['y_norm'] if self.normalization_result is not None
            else self.curve['y_raw'])
        n = len(guesses)
        shape_name = self.shape_combo.currentText()
        shape_func = self.manager.sigmoid_shapes.get(shape_name)
        if shape_func is None:
            return

        factors = [g['factor'] for g in guesses]
        total = sum(factors)
        if total <= 0:
            return
        factors = [f / total for f in factors]  # renormalize to sum to 1, same convention as a real fit
        popt = list(factors[:-1]) if n > 1 else []
        for g in guesses:
            popt.extend([g['midpoint'], max(g['width'], 1e-6)])

        try:
            y_fit = self.manager.sigmoid_sum_model(x, *popt, n_components=n, shape_func=shape_func)
            components = self.manager.get_sigmoid_components(x, popt, n, shape_func)
            quality = self.manager.estimate_fit_quality(y, y_fit, popt)
        except (ValueError, FloatingPointError):
            return

        self.fit_result = {'params': np.array(popt), 'y_fit': y_fit, 'components': components,
                          'quality': quality, 'n_components': n, 'shape_name': shape_name,
                          'constrained': False}
        self._fit_is_preview = True
        self._recompute_component_thermodynamics()
        q = quality
        self.fit_quality_label.setText(
            f"R^2: {q['r_squared']:.4f}    RMSD: {q['rmsd']:.4g}    (preview — click Fit to optimize)")
        self._populate_thermo_table()

    def _on_guess_table_edited(self, item):
        """User hand-edited a Fraction/Midpoint/Width cell — whether the
        table was showing pre-fit guesses or a previous fit's results,
        any edit is now treated as a live preview: rebuilds the plot's
        preview curves AND the per-component thermodynamics table from
        exactly what's now in the table (see
        _rebuild_fit_from_current_table), not just the plot on its own.
        No-op only while we're populating the table ourselves
        (_populating_guess_table guard) — editing is never blocked just
        because a real fit result already exists."""
        if self._populating_guess_table:
            return
        guesses = self._read_guesses_from_table()
        if guesses is not None:
            self._initial_guesses = guesses
            self._rebuild_fit_from_current_table()
            self.update_plot()

    def perform_auto_detect(self):
        if self.curve is None:
            QMessageBox.information(self, "No Curve", "Extract a curve first.")
            return
        y = self.normalization_result['y_norm'] if self.normalization_result is not None else self.curve['y_raw']
        n = self.n_components_spin.value()
        mids = self.manager.auto_detect_transitions(self.curve['x_temperature'], y, n_components=n)

        # Show the detected midpoints directly as the new starting guesses
        # in the table (default width/equal fractions) — not just named in
        # a message box — so they're immediately visible, editable, and
        # already what Fit will use.
        defaults = self._default_initial_guesses(n)
        for g, mid in zip(defaults, sorted(mids)):
            g['midpoint'] = float(mid)
        self._initial_guesses = defaults
        self._populate_guesses_table(self._initial_guesses)
        self._rebuild_fit_from_current_table()
        self.update_plot()

    def perform_fit(self, silent=False):
        if self.curve is None:
            if not silent:
                QMessageBox.information(self, "No Curve", "Extract a curve first.")
            return

        y = self.normalization_result['y_norm'] if self.normalization_result is not None else self.curve['y_raw']
        x = self.curve['x_temperature']
        n = self.n_components_spin.value()
        shape_name = self.shape_combo.currentText()

        # The sigmoid model's component factors always sum to 1 and each
        # shape function saturates within [0, 1] — so its total output
        # range is structurally confined to roughly [0, 1] too. Fitting
        # un-normalized data only makes sense if that data is ALREADY
        # close to a 0-1 scale (e.g. a curve loaded "From file" that was
        # normalized elsewhere first); typical raw absorbance/intensity
        # data with a real scale and sloped baselines cannot be
        # represented by this model at all, no matter how good the
        # starting guesses are. Warn once, up front, rather than let the
        # fit just silently fail or converge to something meaningless.
        if self.normalization_result is None and not silent:
            y_min, y_max = float(np.nanmin(y)), float(np.nanmax(y))
            if y_min < -0.25 or y_max > 1.25 or (y_max - y_min) < 0.3:
                reply = QMessageBox.question(
                    self, "Unnormalized Data",
                    f"No normalization is applied (Method: None), but this curve's signal "
                    f"ranges from {y_min:.3g} to {y_max:.3g} — not close to 0-1.\n\n"
                    "The sigmoid fit model's components always sum to a total between 0 "
                    "and 1, so it can only usefully fit data that's already on roughly "
                    "that scale (e.g. a curve that was normalized before being loaded "
                    "\"From file\"). Fitting this data as-is will likely fail to converge "
                    "or give a meaningless result.\n\n"
                    "Fit anyway?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply != QMessageBox.Yes:
                    return

        # Whatever is currently in the table (auto-detected, evenly-spaced
        # defaults, or hand-edited) drives the fit's starting point.
        guesses = self._read_guesses_from_table()
        if guesses is not None and len(guesses) == n:
            midpoint_guesses = [g['midpoint'] for g in guesses]
            width_guesses = [g['width'] for g in guesses]
            factor_guesses = [g['factor'] for g in guesses]
        else:
            midpoint_guesses = width_guesses = factor_guesses = None

        result = self.manager.fit_sigmoid_model(
            x, y, n_components=n, shape_name=shape_name,
            midpoint_guesses=midpoint_guesses, width_guess=width_guesses,
            factor_guesses=factor_guesses)

        if result is None:
            if not silent:
                QMessageBox.warning(self, "Fit Failed",
                                    "The sigmoid fit did not converge. Try Auto-detect Transitions "
                                    "first, use fewer components, edit the starting guesses in the "
                                    "table to be closer to the real transitions, or normalize the "
                                    "curve.")
            return

        self.fit_result = result
        self._fit_is_preview = False
        self._initial_guesses = []  # table now shows fit results, not guesses
        self._populate_fit_results_table()
        q = result['quality']
        quality_text = f"R^2: {q['r_squared']:.4f}    RMSD: {q['rmsd']:.4g}"

        self.fit_quality_label.setText(quality_text)
        self._recompute_component_thermodynamics()
        self.update_plot()

        # A negative factor means the fit found a "phantom" component
        # contributing a purely NEGATIVE amount rather than a real
        # population fraction (which can only be 0-1) — mathematically
        # possible here once there are 3+ components (the last factor is
        # only 1 minus the OTHERS, which individually can each reach 1
        # without their SUM being constrained to <=1), but not something
        # any real independent two-state transition can do. A factor
        # collapsed to essentially zero is a related but different
        # symptom — the optimizer effectively gave up on that component
        # rather than finding it a genuine role. Both usually mean the
        # curve doesn't actually match this tool's assumption of
        # independent, non-interacting transitions — e.g. one species
        # genuinely converting into another (population transferred
        # between them, not each population changing in parallel) —
        # even though curve_fit will still report a high R^2 for the
        # numerical fit itself.
        if not silent:
            params = result['components']['params']
            negative_factors = [i + 1 for i, p in enumerate(params) if p['factor'] < 0]
            degenerate_factors = [i + 1 for i, p in enumerate(params)
                                  if 0 <= p['factor'] < 0.01 and (i + 1) not in negative_factors]
            if negative_factors or degenerate_factors:
                lines = []
                if negative_factors:
                    lines.append(f"Component(s) {', '.join(str(i) for i in negative_factors)} "
                                "have a NEGATIVE fraction — mathematically possible for this fit "
                                "(3+ components only), but not something a real population "
                                "fraction can be (always 0 to 1).")
                if degenerate_factors:
                    lines.append(f"Component(s) {', '.join(str(i) for i in degenerate_factors)} "
                                "collapsed to essentially zero — the fit couldn't find a "
                                "meaningful role for them.")
                QMessageBox.warning(
                    self, "Unphysical Fit Result",
                    "\n\n".join(lines) + "\n\n"
                    "This usually means the curve doesn't actually match this tool's "
                    "assumption of independent, non-interacting transitions — e.g. one "
                    "species genuinely converting into another (population transferred "
                    "between them) rather than several populations each changing in "
                    "parallel. The R^2 above can still look good even though the "
                    "decomposition itself isn't physically meaningful; treat this fit's "
                    "per-component numbers with real caution.")

    def _populate_fit_results_table(self):
        params = self.fit_result['components']['params']
        self._populating_guess_table = True
        try:
            self.fit_results_table.setRowCount(len(params))
            self._size_table_for_rows(self.fit_results_table, len(params))

            def make_item(val, err, decimals=3):
                # Plain, bare value only — this needs to stay directly
                # hand-editable (typing over "10.702" is unambiguous;
                # typing over "10.702 +/- 0.647" invites accidentally
                # leaving stray text behind) and stay parseable as a
                # live-preview input the moment it's edited. The
                # standard error, when available, goes in the tooltip
                # instead of the cell text, so it's still one hover
                # away without getting in the way of editing.
                item = QTableWidgetItem(f"{val:.{decimals}f}")
                if err is not None:
                    item.setToolTip(f"\u00b1 {err:.{decimals}f} (standard error)")
                return item

            for i, p in enumerate(params):
                idx_item = QTableWidgetItem(str(i + 1))
                idx_item.setFlags(idx_item.flags() & ~Qt.ItemIsEditable)
                self.fit_results_table.setItem(i, 0, idx_item)
                self.fit_results_table.setItem(
                    i, 1, make_item(p['factor'], p.get('factor_err')))
                self.fit_results_table.setItem(
                    i, 2, make_item(p['midpoint'], p.get('midpoint_err')))
                self.fit_results_table.setItem(
                    i, 3, make_item(p['lambda_'], p.get('lambda_err')))
        finally:
            self._populating_guess_table = False

    # ------------------------------------------------------------------ #
    # Fit report (Copy/Save Fit Details)                                   #
    # ------------------------------------------------------------------ #

    def _build_fit_report_text(self):
        """Assemble a full plain-text report of the current fit: curve
        identification, extraction/normalization settings, per-component
        fraction/midpoint/width plus (if computed) deltaH/deltaS/Tm, and
        overall fit quality — everything needed to record or hand off a
        result without needing to save spectra for it. Returns None if
        there's no fit yet."""
        if self.fit_result is None or self.curve is None:
            return None

        lines = ["Melting Curve Analysis - Fit Report", ""]
        lines.append(f"Curve name: {self.curve_name_edit.text()}")
        if self.curve.get('svd_diagnostics'):
            svd = self.curve['svd_diagnostics']
            pc1 = svd.get('explained_variance_pc1')
            extra = (f", PC1 explained variance = {pc1 * 100:.1f}%"
                    if pc1 is not None and np.isfinite(pc1) else "")
            lines.append(f"Extraction method: SVD (generalized curve){extra}")
        else:
            lines.append(f"Extracted at X = {self.curve.get('x_value')}")
        t = self.curve['x_temperature']
        lines.append(f"Temperature range: {t.min():.2f} to {t.max():.2f} "
                     f"(degrees, {len(t)} points after averaging any duplicates)")

        norm_method = {0: 'None', 1: 'Zero order (constant)', 2: 'First order (linear)',
                      3: 'Automatic (Santoro-Bolen fit)'}.get(self.norm_combo.currentIndex(), '?')
        lines.append(f"Normalization: {norm_method}")
        if self.normalization_result is not None:
            lines.append(f"  Low-T region:  [{self.low_min_spin.value():.3f}, {self.low_max_spin.value():.3f}]"
                        + (" (descriptive)" if self.norm_combo.currentIndex() == 3 else ""))
            lines.append(f"  High-T region: [{self.high_min_spin.value():.3f}, {self.high_max_spin.value():.3f}]"
                        + (" (descriptive)" if self.norm_combo.currentIndex() == 3 else ""))
            if self.norm_combo.currentIndex() == 3 and self._automatic_fit_result is not None:
                lines.append(f"  Reliable (automatic): {self._automatic_fit_result.get('reliable')}")

        lines.append(f"Sigmoid shape: {self.fit_result['shape_name']}, "
                     f"Components: {self.fit_result['n_components']}")
        q = self.fit_result['quality']
        lines.append(f"Overall fit quality: R^2 = {q['r_squared']:.5f}, RMSD = {q['rmsd']:.5g}")
        lines.append("")

        comp_params = self.fit_result['components']['params']
        for i, p in enumerate(comp_params):
            if p.get('midpoint_err') is not None:
                lines.append(
                    f"Component {i + 1}: fraction = {p['factor']:.4f} +/- {p['factor_err']:.4f}, "
                    f"midpoint = {p['midpoint']:.4f} +/- {p['midpoint_err']:.4f}, "
                    f"width = {p['lambda_']:.4f} +/- {p['lambda_err']:.4f}")
            else:
                lines.append(f"Component {i + 1}: fraction = {p['factor']:.4f}, "
                            f"midpoint = {p['midpoint']:.4f}, width = {p['lambda_']:.4f}")
            if self.component_thermodynamics and i < len(self.component_thermodynamics):
                th = self.component_thermodynamics[i]['thermodynamics']
                if th is not None:
                    tm_txt = f"{th['Tm']:.2f}" if th['Tm'] is not None else "n/a"
                    lines.append(f"  Arrhenius: deltaH = {th['deltaH']/1000:.2f} kJ/mol, "
                                f"deltaS = {th['deltaS']:.2f} J/mol/K, Tm = {tm_txt}")
                else:
                    lines.append("  Arrhenius: not enough points for the current threshold")

        return "\n".join(lines)

    def show_fit_details(self):
        """Preview the same text report Copy/Save use, in a small
        read-only dialog with its own Copy/Save buttons — the "Show"
        option folded into the same Fit Details control rather than a
        separate always-visible button, to keep this row compact."""
        text = self._build_fit_report_text()
        if text is None:
            QMessageBox.information(self, "No Fit Yet", "Run Fit first.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Fit Details")
        dlg.resize(560, 480)
        layout = QVBoxLayout(dlg)
        text_edit = QPlainTextEdit()
        text_edit.setPlainText(text)
        text_edit.setReadOnly(True)
        text_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(text_edit)
        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(text))
        btn_row.addWidget(copy_btn)
        save_btn = QPushButton("Save to File...")
        save_btn.clicked.connect(self.save_fit_details)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        self._disable_wheel_scrolling(root=dlg)
        self._prevent_enter_from_closing_dialog(root=dlg)
        dlg.exec_()

    def copy_fit_details(self):
        text = self._build_fit_report_text()
        if text is None:
            QMessageBox.information(self, "No Fit Yet", "Run Fit first.")
            return
        QApplication.clipboard().setText(text)

    def save_fit_details(self):
        text = self._build_fit_report_text()
        if text is None:
            QMessageBox.information(self, "No Fit Yet", "Run Fit first.")
            return
        default_name = f"{self.curve_name_edit.text() or 'melting_curve'}_fit_report.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Fit Report", default_name, "Text files (*.txt);;All files (*)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
        except OSError as e:
            QMessageBox.warning(self, "Save Failed", f"Could not save to {path}:\n{e}")

    def export_pdf_report(self):
        """Export a PDF report for the current fit: a title/settings page
        (the same content Show/Copy/Save Details already produce via
        _build_fit_report_text — curve identification, extraction/
        normalization settings, per-component fraction/midpoint/width,
        deltaH/deltaS/Tm where computed, and overall fit quality), the
        current plot exactly as shown, and the fit-results table.

        Uses the same shared pdf_report_utils.export_report_pdf() every
        other analysis dialog's Export PDF button already uses — see its
        module docstring for why the plot is rasterized rather than
        embedded live. Requires a fit to exist first, same as the other
        three Fit Details actions above."""
        text = self._build_fit_report_text()
        if text is None:
            QMessageBox.information(self, "No Fit Yet", "Run Fit first.")
            return
        default_name = f"{self.curve_name_edit.text() or 'melting_curve'}_report.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report", default_name, "PDF files (*.pdf)")
        if not path:
            return

        # _build_fit_report_text always starts with a
        # "Melting Curve Analysis - Fit Report" heading line followed by
        # a blank line (see its own first statement) — the PDF's own
        # title (set below) already covers that, so those first two
        # lines are dropped here to avoid repeating it as the first
        # Settings line.
        report_lines = text.split('\n')[2:]

        headers = [self.fit_results_table.horizontalHeaderItem(c).text()
                  for c in range(self.fit_results_table.columnCount())]
        rows = []
        for r in range(self.fit_results_table.rowCount()):
            rows.append([
                self.fit_results_table.item(r, c).text() if self.fit_results_table.item(r, c) else ''
                for c in range(self.fit_results_table.columnCount())
            ])
        # Source spectra only meaningful in "From spectra" mode — "From
        # file" curves weren't built from any of this app's own spectra.
        labels = [s.get('label', '') for s in self.selected_spectra] \
            if self.source_spectra_radio.isChecked() else []

        try:
            from src.modules.utils.pdf_report_utils import export_report_pdf
            export_report_pdf(
                path,
                f"Melting Curve Analysis — {self.curve_name_edit.text() or 'melting_curve'}",
                meta_lines=report_lines, figure=self.figure,
                table_headers=headers, table_rows=rows, source_labels=labels)
        except Exception as exc:
            logger.exception("Melting Curve Analysis: PDF export failed")
            QMessageBox.warning(self, 'Export failed', str(exc))

    def compare_fit_to_known_values(self):
        """Compare the current fit's per-component Tm (sigmoid midpoint)
        and Arrhenius deltaH/deltaS/Tm against the KNOWN true values
        recorded in one of this app's own synthetic test datasets'
        "Info" sheet — a quick sanity check of the tool against a curve
        whose real answer is already known, rather than reading numbers
        off a report and eyeballing them against the Info sheet by
        hand."""
        if self.fit_result is None:
            QMessageBox.information(self, "No Fit Yet", "Run Fit first.")
            return

        default_dir = ""
        if self._external_curve_path:
            default_dir = os.path.dirname(self._external_curve_path)
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a Synthetic Test Dataset (.xlsx with an Info sheet)",
            default_dir, "Excel files (*.xlsx *.xls);;All files (*)")
        if not path:
            return

        truth = self.manager.parse_ground_truth_info_sheet(path)
        if not truth:
            QMessageBox.warning(
                self, "No Known Values Found",
                f"'{os.path.basename(path)}' doesn't have an \"Info\" sheet with "
                "per-transition true values in the format this app's own bundled "
                "synthetic test datasets use (Help -> Test datasets -> Synthetic -> "
                "Melting curve). This only works for those files.")
            return
        truth = sorted(truth, key=lambda t: t.get('Tm', float('inf')))

        fit_comps = self.fit_result['components']['params']  # already sorted by midpoint
        comp_thermo = self.component_thermodynamics or []

        dlg = QDialog(self)
        dlg.setWindowTitle("Compare Fit to Known Values")
        dlg.resize(760, 320)
        layout = QVBoxLayout(dlg)
        n_note = ""
        if len(fit_comps) != len(truth):
            n_note = (f"  (Note: fit has {len(fit_comps)} component(s), the known "
                     f"answer has {len(truth)} — comparing the first "
                     f"{min(len(fit_comps), len(truth))} of each, matched by ascending Tm.)")
        layout.addWidget(QLabel(f"Source: {os.path.basename(path)}{n_note}"))

        table = QTableWidget()
        headers = ["#", "True Tm [C]", "Fit Tm [C]", "\u0394", "True dH [kJ/mol]",
                  "Fit dH [kJ/mol]", "\u0394", "True dS [J/mol/K]", "Fit dS [J/mol/K]",
                  "\u0394", "True Fraction", "Fit Fraction", "\u0394"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        n_rows = min(len(fit_comps), len(truth))
        table.setRowCount(n_rows)

        def fmt(v, decimals=2):
            return "-" if v is None else f"{v:.{decimals}f}"

        for i in range(n_rows):
            t = truth[i]
            fit_p = fit_comps[i]
            th = (comp_thermo[i]['thermodynamics']
                 if i < len(comp_thermo) and comp_thermo[i].get('thermodynamics') else None)

            true_tm = t.get('Tm')
            fit_tm = fit_p['midpoint']
            true_dh = t.get('deltaH') / 1000 if t.get('deltaH') is not None else None
            fit_dh = th['deltaH'] / 1000 if th else None
            true_ds = t.get('deltaS')
            fit_ds = th['deltaS'] if th else None
            true_frac = t.get('factor')
            fit_frac = fit_p['factor']

            def diff(a, b, decimals=2):
                return "-" if a is None or b is None else f"{b - a:+.{decimals}f}"

            row_vals = [
                str(i + 1), fmt(true_tm), fmt(fit_tm), diff(true_tm, fit_tm),
                fmt(true_dh), fmt(fit_dh), diff(true_dh, fit_dh),
                fmt(true_ds), fmt(fit_ds), diff(true_ds, fit_ds),
                fmt(true_frac, 3), fmt(fit_frac, 3), diff(true_frac, fit_frac, 3),
            ]
            for col, val in enumerate(row_vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i, col, item)
        table.resizeColumnsToContents()
        layout.addWidget(table)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        self._disable_wheel_scrolling(root=dlg)
        self._prevent_enter_from_closing_dialog(root=dlg)
        dlg.exec_()

    # ------------------------------------------------------------------ #
    # Plotting                                                             #
    # ------------------------------------------------------------------ #

    def update_plot(self):
        self._populate_thermo_table()
        self.figure.clear()

        if self.curve is None:
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, "Extract a curve to begin", transform=ax.transAxes,
                    ha='center', va='center')
            self.ax_main = None
            self.canvas.draw()
            return

        x = self.curve['x_temperature']
        have_norm = self.normalization_result is not None
        show_orig_panel = self.show_original_check.isChecked()
        show_norm_panel = have_norm and self.show_normalized_check.isChecked()
        show_curve_row = show_orig_panel or show_norm_panel
        show_residual = self.fit_result is not None and self.show_residual_check.isChecked()
        show_components = (self.fit_result is not None and self.component_thermodynamics is not None
                           and self.show_component_fits_check.isChecked())
        n_components = self.fit_result['n_components'] if show_components else 0

        n_rows = int(show_curve_row) + int(show_residual) + n_components
        if n_rows == 0:
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, "Nothing selected to display\n(check a Show ... option)",
                    transform=ax.transAxes, ha='center', va='center')
            self.ax_main = None
            self.canvas.draw()
            return

        height_ratios = ([3] * int(show_curve_row) + [1] * int(show_residual)
                         + [1.5] * n_components)
        # Tight spacing throughout — hspace/wspace here are minimums under
        # constrained_layout, with the actual pads set right below;
        # both kept small so multiple stacked rows don't accumulate
        # visible gaps between them.
        gs = self.figure.add_gridspec(n_rows, 2, height_ratios=height_ratios,
                                      wspace=0.05, hspace=0.12)
        self.figure.set_constrained_layout_pads(w_pad=0.015, h_pad=0.01, wspace=0.01, hspace=0.015)

        x_min, x_max = float(x.min()), float(x.max())
        x_pad = (x_max - x_min) * 0.03 if x_max > x_min else 1.0

        row_idx = 0
        ax_orig = ax_norm = None
        if show_curve_row:
            # Two side-by-side panels when both are wanted (matching the
            # original thermoanalysis prototype's layout); one wide panel
            # when only one is — the "one or more, according to selection"
            # behavior.
            if show_orig_panel and show_norm_panel:
                ax_orig = self.figure.add_subplot(gs[row_idx, 0])
                ax_norm = self.figure.add_subplot(gs[row_idx, 1])
            elif show_orig_panel:
                ax_orig = self.figure.add_subplot(gs[row_idx, :])
            else:
                ax_norm = self.figure.add_subplot(gs[row_idx, :])
            row_idx += 1

        # Baseline picking (on_canvas_key_press), the Home button
        # (reset_view_to_full), and the sliders' live shading all act on
        # the Original-curve panel — if it's hidden, that interaction is
        # simply unavailable (there's nothing to click/zoom on).
        self.ax_main = ax_orig

        # --- Original curve panel: raw data + baseline regions/lines ---
        if ax_orig is not None:
            if self.norm_combo.currentIndex() != 0:
                low_lo, low_hi = sorted((self.low_min_spin.value(), self.low_max_spin.value()))
                high_lo, high_hi = sorted((self.high_min_spin.value(), self.high_max_spin.value()))
                if low_hi > low_lo:
                    ax_orig.axvspan(low_lo, low_hi, color='tab:orange', alpha=0.15,
                                    label='Low-T baseline region')
                if high_hi > high_lo:
                    ax_orig.axvspan(high_lo, high_hi, color='tab:green', alpha=0.15,
                                    label='High-T baseline region')

            ax_orig.plot(x, self.curve['y_raw'], 'o', color='gray', markersize=4, label='Raw data')
            if have_norm:
                ax_orig.plot(x, self.normalization_result['baseline_low'], '--', color='tab:orange',
                            lw=1.3, label='Low-T baseline')
                ax_orig.plot(x, self.normalization_result['baseline_high'], '--', color='tab:green',
                            lw=1.3, label='High-T baseline')
                if self.x_trans is not None:
                    ax_orig.axvline(self.x_trans, color='black', linestyle=':', lw=1, alpha=0.7)

            ax_orig.set_ylabel("Signal")
            title = "Original curve"
            if have_norm and self.x_trans is not None:
                title += f"\nX_trans = {self.x_trans:.2f}"
            ax_orig.set_title(title, fontsize=10)
            ax_orig.grid(True, alpha=0.4)
            # Always frame on the actual curve's temperature range — NOT
            # matplotlib's autoscale, which would otherwise stretch the
            # view out to include however wide the baseline-region shading
            # currently is. This is also what makes the Home button
            # (reset_view_to_full) meaningful — it just calls
            # update_plot(), which always lands back here.
            ax_orig.set_xlim(x_min - x_pad, x_max + x_pad)
            ax_orig.set_xlabel("Temperature")
            ax_orig.legend(fontsize=7)

        # y_plot_source: whichever curve the fit was actually computed
        # against (see perform_fit) — needed below for the residual, and
        # ax_fit_target: whichever panel that same curve is drawn on (may
        # be None if that panel is hidden, in which case the fit/guess
        # overlay is simply skipped — still fully visible via the
        # dedicated residual/component rows below regardless).
        y_plot_source = self.normalization_result['y_norm'] if have_norm else self.curve['y_raw']
        ax_fit_target = ax_norm if have_norm else ax_orig

        # --- Normalized curve panel: threshold-selected points in red ---
        if ax_norm is not None and have_norm:
            y_norm = self.normalization_result['y_norm']
            threshold = self.span_spin.value()
            # unstable_mask points are excluded from the Arrhenius/van't
            # Hoff fit unconditionally (see
            # normalize_melting_curve/transform_xy_for_arrhenius'
            # exclude_mask) — regardless of whether their y_norm happens
            # to fall inside the span. Shown as a THIRD category here
            # (not folded into the plain threshold-excluded gray) so it's
            # visible on the plot itself which points are gone because
            # they're outside span vs. because normalization was
            # dividing by a near-zero number there — a 'red = selected'
            # point that's actually unstable would otherwise look like
            # it's still part of the fit when it isn't.
            unstable_mask = self.normalization_result.get('unstable_mask')
            if unstable_mask is None:
                unstable_mask = np.zeros_like(y_norm, dtype=bool)
            with np.errstate(invalid='ignore'):
                in_span = (y_norm >= 1 - threshold) & (y_norm <= threshold)
            selected = in_span & ~unstable_mask
            excluded_span = ~in_span & ~unstable_mask
            if np.any(excluded_span):
                ax_norm.plot(x[excluded_span], y_norm[excluded_span], 'o', color='lightgray',
                            markersize=4, label='Excluded (threshold)')
            if np.any(unstable_mask):
                ax_norm.plot(x[unstable_mask], y_norm[unstable_mask], 'o', color='orange',
                            markersize=4, label='Excluded (unstable baseline)')
            if np.any(selected):
                ax_norm.plot(x[selected], y_norm[selected], 'o', color='red',
                            markersize=4, label='Selected (threshold)')
            ax_norm.axhline(threshold, color='red', linestyle=':', lw=1, alpha=0.6)
            ax_norm.axhline(1 - threshold, color='red', linestyle=':', lw=1, alpha=0.6)

            ax_norm.set_ylabel("Normalized signal (0-1)")
            ax_norm.set_title("Normalized curve")
            ax_norm.grid(True, alpha=0.4)
            ax_norm.set_xlim(x_min - x_pad, x_max + x_pad)
            ax_norm.set_xlabel("Temperature")
            if self.invert_display_check.isChecked():
                # Purely a display flip — the y-axis direction is
                # reversed (1 drawn at the bottom, 0 at the top), so the
                # curve TRACE appears to descend like a raw curve whose
                # signal falls with temperature would. Nothing about the
                # underlying y_norm data, the fit, or the Arrhenius
                # calculation changes — they all keep using the standard
                # 0-at-low-T/1-at-high-T convention regardless of this
                # setting, so there's no risk of silently changing what
                # gets fitted just because the plot looks different.
                ax_norm.invert_yaxis()
            if ax_orig is not None:
                ax_norm.yaxis.set_label_position('right')
                ax_norm.yaxis.tick_right()

        if ax_fit_target is not None:
            if self.fit_result is not None:
                ax_fit_target.plot(x, self.fit_result['y_fit'], 'r-', lw=2, label='Total fit')
                colors = ['tab:blue', 'tab:purple', 'tab:brown', 'tab:cyan']
                for i, comp in enumerate(self.fit_result['components']['components']):
                    ax_fit_target.plot(x, comp, ':', color=colors[i % len(colors)], label=f'Component {i + 1}')
            elif self._initial_guesses:
                # Preview of the CURRENT starting guesses (from Auto-detect
                # Transitions, evenly-spaced defaults, or hand-edited table
                # values) before a fit has actually been run — same
                # "guesses vs. fit results" dual plotting state
                # PeakFittingDialog uses.
                shape_func = self.manager.sigmoid_shapes[self.shape_combo.currentText()]
                colors = ['tab:blue', 'tab:purple', 'tab:brown', 'tab:cyan']
                total_guess = np.zeros_like(x)
                for i, g in enumerate(self._initial_guesses):
                    comp_curve = g['factor'] * shape_func((x - g['midpoint']) / g['width'])
                    total_guess += comp_curve
                    ax_fit_target.plot(x, comp_curve, ':', color=colors[i % len(colors)],
                                       alpha=0.7, label=f'Guess {i + 1}')
                ax_fit_target.plot(x, total_guess, '--', color='black', lw=1.5, alpha=0.7,
                                   label='Guess (sum)')

        if ax_norm is not None:
            ax_norm.legend(fontsize=7)
        elif ax_fit_target is not None and ax_fit_target is not ax_orig:
            ax_fit_target.legend(fontsize=7)

        if show_residual:
            ax_res = self.figure.add_subplot(gs[row_idx, :],
                                             sharex=ax_fit_target if ax_fit_target is not None else None)
            residual = np.asarray(y_plot_source) - np.asarray(self.fit_result['y_fit'])
            ax_res.plot(x, residual, color='purple')
            ax_res.axhline(0, color='black', linestyle='--', lw=1)
            ax_res.set_ylabel("Residual")
            ax_res.set_xlabel("Temperature")
            ax_res.grid(True, alpha=0.4)
            row_idx += 1

        # --- Per-component fit + Arrhenius rows — the generalization of
        # the single Arrhenius plot to each individual transition of a
        # multi-sigmoid fit (see MeltingCurveManager.
        # compute_component_thermodynamics and more_transitions.png for
        # the reasoning/reference layout). One row per component: left =
        # that component's own isolated curve (real data reconstructed by
        # removing every OTHER component's contribution from the total
        # fit, then renormalizing by this component's own factor, plotted
        # alongside its ideal noise-free model curve) with a vertical
        # dotted line at its own Tm; right = that component's own
        # Arrhenius plot. y_local_data comes straight from
        # component_thermodynamics — the exact same reconstructed data
        # its own Arrhenius fit used, not a second independent
        # computation of the same thing that could quietly drift out of
        # sync with it.
        if show_components:
            colors = ['tab:blue', 'tab:purple', 'tab:brown', 'tab:cyan']
            comp_params = self.fit_result['components']['params']

            for i, (params_i, comp_thermo) in enumerate(zip(comp_params, self.component_thermodynamics)):
                color = colors[i % len(colors)]
                y_pure = comp_thermo['y_pure']
                y_local_data = comp_thermo['y_local_data']

                ax_comp = self.figure.add_subplot(gs[row_idx, 0])
                ax_comp.plot(x, y_local_data, 'o', color='gray', markersize=3, label='Data (reconstructed)')
                ax_comp.plot(x, y_pure, '-', color=color, lw=2, label='Component model')
                thermo_i = comp_thermo['thermodynamics']
                if thermo_i is not None and thermo_i['Tm'] is not None:
                    ax_comp.axvline(thermo_i['Tm'], color=color, linestyle=':', lw=1.3)
                    tm_txt = f"{thermo_i['Tm']:.1f}"
                    dh_txt = f"{thermo_i['deltaH']/1000:.1f}"
                    ds_txt = f"{thermo_i['deltaS']:.1f}"
                else:
                    tm_txt = dh_txt = ds_txt = "n/a"
                ax_comp.set_title(f"Component {i + 1}: dH={dh_txt} kJ/mol, dS={ds_txt} J/mol/K, Tm={tm_txt}",
                                  fontsize=8)
                ax_comp.set_ylabel("0-1 norm.")
                ax_comp.set_xlabel("Temperature")
                ax_comp.set_xlim(x_min - x_pad, x_max + x_pad)
                ax_comp.grid(True, alpha=0.4)
                ax_comp.legend(fontsize=6)

                ax_comp_arr = self.figure.add_subplot(gs[row_idx, 1])
                arr_i = comp_thermo['arrhenius']
                if arr_i is not None:
                    ax_comp_arr.plot(arr_i['x_arr'], arr_i['y_arr'], 'o', color=color, markersize=4)
                    if thermo_i is not None:
                        x_fit_i = np.linspace(arr_i['x_arr'].min(), arr_i['x_arr'].max(), 50)
                        ax_comp_arr.plot(x_fit_i, np.polyval(thermo_i['coeffs'], x_fit_i),
                                        '-', color='black', lw=1.3)
                else:
                    ax_comp_arr.text(0.5, 0.5, "Not enough points\nfor this threshold",
                                     transform=ax_comp_arr.transAxes, ha='center', va='center', fontsize=8)
                ax_comp_arr.set_xlabel("1 / T [1/K]")
                ax_comp_arr.set_ylabel("ln(K)")
                ax_comp_arr.set_title(f"Component {i + 1} Arrhenius", fontsize=8)
                ax_comp_arr.grid(True, alpha=0.4)

                row_idx += 1

        self.canvas.draw()

    # ------------------------------------------------------------------ #
    # Results / help                                                       #
    # ------------------------------------------------------------------ #

    def get_results(self):
        """Formats and returns all settings to be saved / committed by
        MeltingCurveController — same role as PeakFittingDialog.get_results()."""
        temp_map = {}
        for row in range(self.temps_table.rowCount()):
            label = self.temps_table.item(row, 0).text()
            try:
                temp_map[label] = float(self.temps_table.item(row, 1).text())
            except (ValueError, AttributeError):
                pass

        method_idx = self.norm_combo.currentIndex()
        method = {0: 'none', 1: 'zero', 2: 'first', 3: 'automatic'}[method_idx]
        normalization = {
            'method': method,
            'low_range': (self.low_min_spin.value(), self.low_max_spin.value()),
            'high_range': (self.high_min_spin.value(), self.high_max_spin.value()),
        }

        curve_payload = None
        if self.curve is not None:
            curve_payload = dict(self.curve)
            curve_payload['normalization_result'] = self.normalization_result

        output_options = {
            'add_raw_curve': self.add_raw_check.isChecked(),
            'add_normalized_curve': self.add_norm_check.isChecked(),
            'add_baselines': self.add_baselines_check.isChecked(),
            'add_fit': self.add_fit_check.isChecked(),
            'add_residual': self.add_residual_check.isChecked(),
            'add_components': self.add_components_check.isChecked(),
        }

        return {
            'temperatures': temp_map,
            'source_labels': self.curve['source_labels'] if self.curve else
                             [s['label'] for s in self.selected_spectra],
            'curve_name': self.curve_name_edit.text(),
            'extraction_method': 'svd' if self.extraction_method_combo.currentIndex() == 1 else 'signal_at_x',
            'svd_center': self.svd_center_check.isChecked(),
            'window': self.window_spin.value(),
            'curve': curve_payload,
            'normalization': normalization,
            'span': self.span_spin.value(),
            'x_trans': self.x_trans,
            'fit_settings': {
                'n_components': self.n_components_spin.value(),
                'shape_name': self.shape_combo.currentText(),
            },
            'fit_result': self.fit_result,
            'automatic_fit_result': self._automatic_fit_result,
            'component_thermodynamics': self.component_thermodynamics,
            'output_options': output_options,
            'source_mode': 'file' if self.source_file_radio.isChecked() else 'spectra',
            'external_file_path': self._external_curve_path,
            'sheet_name': self.sheet_combo.currentText() if self._external_sheet_names else None,
            'spectra_fingerprint': self._compute_spectra_fingerprint(),
        }

    def show_help(self):
        content = get_melting_curve_help_content()
        title = get_melting_curve_help_title()
        show_help_window(self, title, content)

    def closeEvent(self, event):
        """Clean up the canvas key-press connection on close — same
        reasoning/pattern as PeakFittingDialog's closeEvent."""
        try:
            if self.key_connection_id is not None:
                self.canvas.mpl_disconnect(self.key_connection_id)
                self.key_connection_id = None
        except Exception:
            pass
        super().closeEvent(event)
