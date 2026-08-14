# src/views/dialogs/visualization_analysis/band_marker_dialog.py
"""
Band Marker Manager dialog.

Allows the user to add, edit, and remove named reference lines that are
drawn on every plot. Changes take effect immediately on the current plot.

Each marker is either an 'X' marker (a vertical line at a constant x,
marking an x-value) or a 'Y' marker (a horizontal line at a constant y,
marking a y-value) — set via the Axis column / control. This is a
separate choice from "Label dir" (below), which only affects how the
label TEXT is drawn, not which axis the line itself represents.

Existing markers can be edited three ways, kept in sync with each other:

  1. Inline, directly in the table — double-click a cell. Position,
     Label, Width, Font size, and Label offset open the normal in-place
     text editor; Axis, Line style, Label dir, Color, and Visible are not
     plain text, so they open their own small picker instead (a menu, the
     color dialog, or a visibility toggle).

  2. Via the bottom row — selecting exactly one row loads its Position /
     Axis / Label / Style / Width / Font size / Label offset / Label dir
     / Color into that row and turns "Add" into "Update selected".
     Adjusting any of those fields and clicking Update applies all of
     them to the marker at once — and keeps that marker selected
     afterward, so further tweaks don't need reselecting it from the
     table again. The selection is also actively re-asserted if it ever
     transiently drops to nothing while mid-edit (e.g. from interacting
     with this dialog's own fields) — see _on_selection for why that's
     necessary. Selecting several rows at once, or clicking Cancel edit,
     ends the single-row edit instead.

  3. Bulk, for 2+ selected rows at once — selecting several rows loads
     Style / Width / Font size / Label offset / Label dir / Color / Axis
     (seeded from the first selected marker) into the bottom row and
     turns "Add" into "Update N selected". Position and Label are
     disabled here, since setting every selected marker to the identical
     position or label text wouldn't make sense — everything else
     applies to the whole batch at once, which then stays selected
     afterward for a further tweak, the same way single-row editing does.

"Label dir" controls how each marker's label is drawn: "Vertical" (the
default) reads bottom-to-top alongside the line and takes almost no
space along the line; "Horizontal" is easier to read but takes more
room and can run into a neighbouring marker if two are close together.
This applies the same way to both X and Y markers.

"Label offset" is per-marker: it sets how far down from the top of the
plot that marker's label starts, as a percentage (0-100%) of the y-axis
range (for a Y marker, this is measured from the right edge instead, by
symmetry) — raise it if that marker's label collides with a y-axis's top
tick number or scientific-notation exponent. Since it's per-marker,
different markers can use different offsets, e.g. to stack labels at
different heights when several markers sit close together. A "Label
offset from line" control (top-right) is the one remaining GLOBAL
setting — it sets the gap, in points, between a marker's line and the
start of its label, the same for every marker — raise it if a line
crosses through its own label's characters.
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox,
    QLineEdit, QComboBox, QColorDialog, QCheckBox, QMenu, QMessageBox,
    QAbstractItemView, QSizePolicy, QWidget,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

_LINESTYLES = ['--', '-', ':', '-.']
_LINESTYLE_LABELS = ['Dashed (--)', 'Solid (-)', 'Dotted (:)', 'Dash-dot (-.)']

_ORIENTATIONS = ['vertical', 'horizontal']
_ORIENTATION_LABELS = ['Vertical', 'Horizontal']

_AXES = ['x', 'y']
_AXIS_LABELS = ['X (vertical line)', 'Y (horizontal line)']
_AXIS_SHORT_LABELS = ['X', 'Y']

# Table columns
(_COL_POSITION, _COL_AXIS, _COL_LABEL, _COL_STYLE, _COL_WIDTH, _COL_FONTSIZE,
 _COL_LABEL_OFFSET, _COL_ORIENTATION, _COL_COLOR, _COL_VISIBLE) = range(10)


def _format_position(value: float) -> str:
    """Format a position value for display. Uses significant digits
    (%g-style) rather than a fixed decimal count, since the same field
    holds both typical x-values (hundreds to thousands) and small y-values
    (e.g. 0.0005) — a fixed count like '.2f' would silently round the
    latter down to 0.00. Falls back to scientific notation automatically
    for very small or very large magnitudes, which float() parses back
    just fine."""
    return f"{value:.6g}"


class BandMarkerDialog(QDialog):

    def __init__(self, parent=None, band_marker_manager=None,
                 on_change=None):
        super().__init__(parent)
        self.setWindowTitle('Band Markers')
        # No explicit setMinimumSize() here on purpose: that would override
        # Qt's own layout-computed minimum with a fixed guess, which is
        # exactly what let this dialog be resized smaller than its content
        # actually needs (causing controls to visually overlap/truncate).
        # Leaving it unset means Qt derives the true floor from the layout
        # itself, so the window simply can't be shrunk past the point where
        # something would need to overlap.
        self.resize(760, 480)
        # No WindowMinimizeButtonHint — this dialog is always modal (opened
        # via exec_()), so minimizing it would leave the whole app blocked
        # behind a taskbar entry with no visible sign anything is still
        # open — easy to mistake for a frozen app. Maximize stays available.
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        self._mgr       = band_marker_manager
        self._on_change = on_change   # callback to replot

        # Index of the marker currently loaded into the bottom row for a
        # single-row edit, or None while that row is building a brand-new
        # marker or bulk-editing several rows at once (see below).
        self._editing_index = None
        # List of marker indices currently loaded for a BULK edit (2+ rows
        # selected at once), or None/empty otherwise. Mutually exclusive
        # with _editing_index — only one of the two is ever active.
        self._editing_indices = None

        self._build_ui()
        self._populate_table()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Global toggle + label-line-gap control (label offset from top is
        # now per-marker — see the Label offset column / bottom row)
        top = QHBoxLayout()
        self._show_all_cb = QCheckBox('Show all band markers on plots')
        self._show_all_cb.setChecked(self._mgr.visible)
        self._show_all_cb.stateChanged.connect(self._toggle_all)
        top.addWidget(self._show_all_cb)
        top.addStretch()
        top.addWidget(QLabel('Label offset from line:'))
        self._label_gap_spin = QDoubleSpinBox()
        self._label_gap_spin.setRange(0.0, 30.0)
        self._label_gap_spin.setDecimals(0)
        self._label_gap_spin.setSuffix(' pt')
        self._label_gap_spin.setSingleStep(1.0)
        self._label_gap_spin.setValue(
            getattr(self._mgr, 'label_line_gap', 3.0))
        self._label_gap_spin.setToolTip(
            "Gap between a marker's line and the start of its label, in "
            "points. Increase this if the line crosses through the "
            "label's characters.")
        self._label_gap_spin.valueChanged.connect(self._on_label_gap_changed)
        top.addWidget(self._label_gap_spin)
        layout.addLayout(top)

        # Table
        self._table = QTableWidget(0, 10)
        # Qt normally renders a selected row with a dimmer "inactive"
        # highlight color the moment the table loses keyboard focus (e.g.
        # when you click into the Position field below to edit it) — even
        # though the row is, in fact, still fully selected. That dimming
        # looks enough like "it got deselected" to be genuinely confusing,
        # so force the same, fully-visible highlight color regardless of
        # focus state (the ':!active' pseudo-state targets exactly that
        # "selected but not focused" case).
        self._table.setStyleSheet("""
            QTableWidget::item:selected,
            QTableWidget::item:selected:!active {
                background-color: #3874f2;
                color: white;
            }
        """)
        self._table.setHorizontalHeaderLabels(
            ['Position', 'Axis', 'Label', 'Line style', 'Width', 'Font size',
             'Label offset (%)', 'Label dir', 'Color', 'Visible'])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for c in (0, 1, 3, 4, 5, 6, 7, 8, 9):
            self._table.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # Position / Label / Width / Font size / Label offset use the normal in-place text editor on
        # double-click. Axis / Line style / Label dir / Color / Visible
        # are flagged non-editable (see _set_row_items) and instead open
        # their own picker via cellDoubleClicked below — editing a hex
        # color or a matplotlib linestyle code as raw text isn't a good
        # idea.
        self._table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self._table.itemSelectionChanged.connect(self._on_selection)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self._table)

        # Add / update marker — split across two rows so it doesn't need
        # nearly as much total width, and doesn't force the whole dialog
        # to stay wide just to avoid this section overlapping itself.
        self._add_grp_lbl = QLabel('Add marker:')
        layout.addWidget(self._add_grp_lbl)

        id_row = QHBoxLayout()
        id_row.addWidget(QLabel('Position:'))
        # QLineEdit rather than QDoubleSpinBox: this field holds an
        # x-value (hundreds to thousands, typically) for an X marker, or
        # a y-value (e.g. -0.0005 to 0.0020) for a Y marker — a spinbox's
        # single fixed decimal count can't represent both well. At
        # decimals=2, a value like 0.0005 was silently rounded straight
        # to 0.00, making small y-values impossible to enter at all. A
        # plain text field validated on commit (see _add_or_update_marker
        # / _on_item_changed) accepts any precision, including scientific
        # notation, for either magnitude.
        self._position_edit = QLineEdit()
        self._position_edit.setText('1000.0')
        self._position_edit.setPlaceholderText('e.g. 1000 or -0.0005')
        self._position_edit.setMinimumWidth(100)
        id_row.addWidget(self._position_edit)
        id_row.addWidget(QLabel('Axis:'))
        self._axis_combo = QComboBox()
        self._axis_combo.addItems(_AXIS_LABELS)
        self._axis_combo.setMinimumWidth(150)
        self._axis_combo.setToolTip(
            "X: a vertical line marking an x-value (e.g. a band position).\n"
            "Y: a horizontal line marking a y-value (e.g. a threshold).")
        id_row.addWidget(self._axis_combo)
        id_row.addWidget(QLabel('Label:'))
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText('e.g. Phe 1004')
        self._label_edit.setMinimumWidth(160)
        id_row.addWidget(self._label_edit, 1)   # stretches to fill spare width
        layout.addLayout(id_row)

        style_row = QHBoxLayout()
        style_row.addWidget(QLabel('Style:'))
        self._style_combo = QComboBox()
        self._style_combo.addItems(_LINESTYLE_LABELS)
        self._style_combo.setMinimumWidth(110)
        style_row.addWidget(self._style_combo)
        style_row.addWidget(QLabel('Width:'))
        self._width_spin = QDoubleSpinBox()
        self._width_spin.setRange(0.1, 20.0)
        self._width_spin.setDecimals(1)
        self._width_spin.setSingleStep(0.5)
        self._width_spin.setValue(1.0)
        self._width_spin.setMinimumWidth(70)
        style_row.addWidget(self._width_spin)
        style_row.addWidget(QLabel('Font size:'))
        self._fontsize_spin = QDoubleSpinBox()
        self._fontsize_spin.setRange(1.0, 72.0)
        self._fontsize_spin.setDecimals(1)
        self._fontsize_spin.setSingleStep(1.0)
        self._fontsize_spin.setValue(7.0)
        self._fontsize_spin.setMinimumWidth(70)
        style_row.addWidget(self._fontsize_spin)
        style_row.addWidget(QLabel('Label offset:'))
        self._label_offset_spin = QDoubleSpinBox()
        self._label_offset_spin.setRange(0.0, 100.0)
        self._label_offset_spin.setDecimals(0)
        self._label_offset_spin.setSuffix(' %')
        self._label_offset_spin.setSingleStep(1.0)
        self._label_offset_spin.setValue(
            getattr(self._mgr, 'DEFAULT_LABEL_OFFSET', 0.02) * 100.0)
        self._label_offset_spin.setMinimumWidth(70)
        self._label_offset_spin.setToolTip(
            "How far down from the top of the plot this marker's label "
            "starts, as a percentage of the y-axis range (for a Y marker, "
            "this is measured from the right edge instead). 0% starts right "
            "at the edge; 100% pushes it to the opposite edge. Increase this "
            "if the label overlaps a top tick number / exponent.")
        style_row.addWidget(self._label_offset_spin)
        style_row.addWidget(QLabel('Label dir:'))
        self._orientation_combo = QComboBox()
        self._orientation_combo.addItems(_ORIENTATION_LABELS)
        self._orientation_combo.setMinimumWidth(100)
        style_row.addWidget(self._orientation_combo)
        self._color_btn = QPushButton('Color…')
        self._color_btn.setMinimumWidth(70)
        self._selected_color = '#E65100'
        self._color_btn.setStyleSheet(
            f'background-color:{self._selected_color}; color:white;')
        self._color_btn.clicked.connect(self._pick_color)
        style_row.addWidget(self._color_btn)
        style_row.addStretch()
        self._add_btn = QPushButton('Add')
        self._add_btn.setMinimumWidth(120)
        self._add_btn.clicked.connect(self._add_or_update_marker)
        style_row.addWidget(self._add_btn)
        self._cancel_edit_btn = QPushButton('Cancel edit')
        self._cancel_edit_btn.setMinimumWidth(100)
        self._cancel_edit_btn.setVisible(False)
        self._cancel_edit_btn.clicked.connect(self._cancel_edit)
        style_row.addWidget(self._cancel_edit_btn)
        layout.addLayout(style_row)

        # Action buttons
        btn_row = QHBoxLayout()
        self._remove_btn = QPushButton('Remove selected')
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self._remove_btn)
        clear_btn = QPushButton('Clear all')
        clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        help_btn = QPushButton('Help')
        help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(help_btn)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------ #
    # Table population                                                     #
    # ------------------------------------------------------------------ #

    def _populate_table(self, select_row=None):
        """Rebuild the table from the manager's current markers.

        select_row, if given, is reselected afterward — used after an
        inline edit, or after committing an Update from the bottom row,
        so the row you just touched doesn't lose its selection (and, via
        that reselection, stays loaded in the bottom "editing" row too).
        """
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for m in self._mgr.markers:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._set_row_items(row, m)
        self._table.blockSignals(False)

        if select_row is not None and 0 <= select_row < self._table.rowCount():
            self._table.selectRow(select_row)   # emits itemSelectionChanged normally
        else:
            # Row count changed while signals were blocked, so nothing
            # emitted itemSelectionChanged for the resulting (usually
            # empty) selection — refresh the bottom row explicitly.
            self._on_selection()

    def _set_row_items(self, row, m):
        """(Re)build every cell in one row from a marker dict."""
        position = m.get('position', m.get('x', 0.0))
        position_item = QTableWidgetItem(_format_position(position))
        position_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, _COL_POSITION, position_item)

        axis_label = _AXIS_SHORT_LABELS[_AXES.index(m.get('axis', 'x'))
                                         if m.get('axis', 'x') in _AXES else 0]
        axis_item = QTableWidgetItem(axis_label)
        axis_item.setTextAlignment(Qt.AlignCenter)
        axis_item.setFlags(axis_item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, _COL_AXIS, axis_item)

        self._table.setItem(row, _COL_LABEL, QTableWidgetItem(m['label']))

        style_label = _LINESTYLE_LABELS[
            _LINESTYLES.index(m['linestyle'])
            if m['linestyle'] in _LINESTYLES else 0]
        style_item = QTableWidgetItem(style_label)
        style_item.setFlags(style_item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, _COL_STYLE, style_item)

        width_item = QTableWidgetItem(f"{m.get('linewidth', 1.0):.1f}")
        width_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, _COL_WIDTH, width_item)

        fontsize_item = QTableWidgetItem(f"{m.get('fontsize', 7.0):.1f}")
        fontsize_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, _COL_FONTSIZE, fontsize_item)

        label_offset_item = QTableWidgetItem(
            f"{m.get('label_offset', 0.02) * 100.0:.0f}")
        label_offset_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, _COL_LABEL_OFFSET, label_offset_item)

        orientation_label = _ORIENTATION_LABELS[
            _ORIENTATIONS.index(m.get('orientation', 'vertical'))
            if m.get('orientation', 'vertical') in _ORIENTATIONS else 0]
        orientation_item = QTableWidgetItem(orientation_label)
        orientation_item.setTextAlignment(Qt.AlignCenter)
        orientation_item.setFlags(orientation_item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, _COL_ORIENTATION, orientation_item)

        color_item = QTableWidgetItem(m['color'])
        color_item.setBackground(QBrush(QColor(m['color'])))
        color_item.setTextAlignment(Qt.AlignCenter)
        color_item.setFlags(color_item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, _COL_COLOR, color_item)

        vis_item = QTableWidgetItem('✓' if m.get('visible', True) else '✗')
        vis_item.setTextAlignment(Qt.AlignCenter)
        vis_item.setFlags(vis_item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, _COL_VISIBLE, vis_item)

    # ------------------------------------------------------------------ #
    # Inline editing (directly in the table)                              #
    # ------------------------------------------------------------------ #

    def _on_item_changed(self, item):
        """Position / Label / Width / Font size / Label offset were edited in place (double-click, type, Enter)."""
        row, col = item.row(), item.column()
        if not (0 <= row < len(self._mgr.markers)):
            return

        if col == _COL_POSITION:
            try:
                new_position = float(item.text())
            except ValueError:
                QMessageBox.warning(self, 'Invalid position',
                                     f'"{item.text()}" is not a number.')
                self._populate_table(select_row=row)   # revert display
                return
            self._mgr.update(row, position=new_position)
            self._populate_table(select_row=row)

        elif col == _COL_LABEL:
            new_label = item.text().strip()
            if not new_label:
                m = self._mgr.markers[row]
                new_label = _format_position(m.get('position', m.get('x', 0.0)))
            self._mgr.update(row, label=new_label)
            self._populate_table(select_row=row)

        elif col == _COL_WIDTH:
            try:
                new_width = float(item.text())
                if new_width <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, 'Invalid width',
                                     f'"{item.text()}" is not a positive number.')
                self._populate_table(select_row=row)   # revert display
                return
            self._mgr.update(row, linewidth=new_width)
            self._populate_table(select_row=row)

        elif col == _COL_FONTSIZE:
            try:
                new_fontsize = float(item.text())
                if new_fontsize <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, 'Invalid font size',
                                     f'"{item.text()}" is not a positive number.')
                self._populate_table(select_row=row)   # revert display
                return
            self._mgr.update(row, fontsize=new_fontsize)
            self._populate_table(select_row=row)

        elif col == _COL_LABEL_OFFSET:
            try:
                new_pct = float(item.text())
                if not (0 <= new_pct <= 100):
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, 'Invalid label offset',
                                     f'"{item.text()}" is not a number between 0 and 100.')
                self._populate_table(select_row=row)   # revert display
                return
            self._mgr.update(row, label_offset=new_pct / 100.0)
            self._populate_table(select_row=row)

        else:
            return  # Axis / Style / Label dir / Color / Visible aren't in-place text-editable

        self._notify()

    def _on_cell_double_clicked(self, row, col):
        """Axis / Line style / Label dir / Color / Visible use their own
        picker instead of a text editor (columns are flagged non-editable
        in _set_row_items, so no built-in editor opens for them — this is
        the only handler)."""
        if not (0 <= row < len(self._mgr.markers)):
            return

        if col == _COL_AXIS:
            self._pick_axis_for_row(row)
        elif col == _COL_STYLE:
            self._pick_style_for_row(row)
        elif col == _COL_ORIENTATION:
            self._pick_orientation_for_row(row)
        elif col == _COL_COLOR:
            self._pick_color_for_row(row)
        elif col == _COL_VISIBLE:
            current = self._mgr.markers[row].get('visible', True)
            self._mgr.update(row, visible=not current)
            self._populate_table(select_row=row)
            self._notify()

    def _pick_axis_for_row(self, row):
        item = self._table.item(row, _COL_AXIS)
        menu = QMenu(self)
        for label in _AXIS_LABELS:
            menu.addAction(label)
        chosen = menu.exec_(self._table.viewport().mapToGlobal(
            self._table.visualItemRect(item).bottomLeft()))
        if chosen is None:
            return
        axis = _AXES[_AXIS_LABELS.index(chosen.text())]
        self._mgr.update(row, axis=axis)
        self._populate_table(select_row=row)
        self._notify()

    def _pick_style_for_row(self, row):
        item = self._table.item(row, _COL_STYLE)
        menu = QMenu(self)
        for label in _LINESTYLE_LABELS:
            menu.addAction(label)
        chosen = menu.exec_(self._table.viewport().mapToGlobal(
            self._table.visualItemRect(item).bottomLeft()))
        if chosen is None:
            return
        style = _LINESTYLES[_LINESTYLE_LABELS.index(chosen.text())]
        self._mgr.update(row, linestyle=style)
        self._populate_table(select_row=row)
        self._notify()

    def _pick_orientation_for_row(self, row):
        item = self._table.item(row, _COL_ORIENTATION)
        menu = QMenu(self)
        for label in _ORIENTATION_LABELS:
            menu.addAction(label)
        chosen = menu.exec_(self._table.viewport().mapToGlobal(
            self._table.visualItemRect(item).bottomLeft()))
        if chosen is None:
            return
        orientation = _ORIENTATIONS[_ORIENTATION_LABELS.index(chosen.text())]
        self._mgr.update(row, orientation=orientation)
        self._populate_table(select_row=row)
        self._notify()

    def _pick_color_for_row(self, row):
        current = self._mgr.markers[row]['color']
        color = QColorDialog.getColor(QColor(current), self)
        if color.isValid():
            self._mgr.update(row, color=color.name())
            self._populate_table(select_row=row)
            self._notify()

    # ------------------------------------------------------------------ #
    # Bottom row: Add / Update selected                                   #
    # ------------------------------------------------------------------ #

    def _toggle_all(self, state):
        self._mgr.visible = bool(state)
        self._notify()

    def _on_label_gap_changed(self, value):
        self._mgr.label_line_gap = value
        self._notify()

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._selected_color), self)
        if color.isValid():
            self._selected_color = color.name()
            self._color_btn.setStyleSheet(
                f'background-color:{self._selected_color}; color:white;')

    def _add_or_update_marker(self):
        if self._editing_indices:
            self._apply_bulk_update()
            return

        position_text = self._position_edit.text().strip()
        try:
            position = float(position_text)
        except ValueError:
            QMessageBox.warning(self, 'Invalid position',
                                 f'"{position_text}" is not a number.')
            return
        axis        = _AXES[self._axis_combo.currentIndex()]
        label       = self._label_edit.text().strip() or _format_position(position)
        style       = _LINESTYLES[self._style_combo.currentIndex()]
        width       = self._width_spin.value()
        fontsize    = self._fontsize_spin.value()
        label_offset = self._label_offset_spin.value() / 100.0
        orientation = _ORIENTATIONS[self._orientation_combo.currentIndex()]

        if self._editing_index is not None:
            target_row = self._editing_index
            self._mgr.update(target_row, position=position, axis=axis,
                              label=label, color=self._selected_color,
                              linestyle=style, linewidth=width,
                              fontsize=fontsize, label_offset=label_offset,
                              orientation=orientation)
            # Reselect the same row instead of resetting to a blank "Add"
            # state — keeps the marker loaded in this form so a second (or
            # third...) tweak doesn't require selecting it again from the
            # table each time. Reselecting fires the normal selection-
            # changed signal, which re-populates these fields with the
            # just-saved values and keeps the button on "Update selected".
            self._populate_table(select_row=target_row)
        else:
            self._mgr.add(position, label=label, color=self._selected_color,
                          linestyle=style, linewidth=width, fontsize=fontsize,
                          label_offset=label_offset, orientation=orientation, axis=axis)
            self._populate_table()
            self._reset_add_row()

        self._notify()

    def _apply_bulk_update(self):
        """Apply the bottom row's Style / Width / Font size / Label offset /
        Label dir / Color / Axis to every currently bulk-selected marker at
        once. Position and Label are never touched here (see
        _load_multi_selection_into_add_form)."""
        axis        = _AXES[self._axis_combo.currentIndex()]
        style       = _LINESTYLES[self._style_combo.currentIndex()]
        width       = self._width_spin.value()
        fontsize    = self._fontsize_spin.value()
        label_offset = self._label_offset_spin.value() / 100.0
        orientation = _ORIENTATIONS[self._orientation_combo.currentIndex()]
        color       = self._selected_color

        for row in self._editing_indices:
            self._mgr.update(row, axis=axis, color=color, linestyle=style,
                              linewidth=width, fontsize=fontsize,
                              label_offset=label_offset, orientation=orientation)

        # populate_table() with no explicit row to reselect triggers the
        # same sticky-restoration path in _on_selection() that recovers
        # from a transient empty-selection blip — reused here so the
        # whole batch stays selected and loaded afterward, ready for a
        # further bulk tweak, exactly like single-row Update selected
        # already does.
        self._populate_table()
        self._notify()

    def _cancel_edit(self):
        self._editing_index = None
        self._table.clearSelection()
        self._reset_add_row()

    def _reset_add_row(self):
        self._editing_index = None
        self._editing_indices = None
        self._add_btn.setText('Add')
        self._add_grp_lbl.setText('Add marker:')
        self._cancel_edit_btn.setVisible(False)
        self._position_edit.setEnabled(True)
        self._position_edit.setPlaceholderText('e.g. 1000 or -0.0005')
        self._label_edit.setEnabled(True)
        self._label_edit.setPlaceholderText('e.g. Phe 1004')
        self._label_edit.clear()
        self._axis_combo.setCurrentIndex(0)
        self._style_combo.setCurrentIndex(0)
        self._width_spin.setValue(1.0)
        self._fontsize_spin.setValue(7.0)
        self._label_offset_spin.setValue(
            getattr(self._mgr, 'DEFAULT_LABEL_OFFSET', 0.02) * 100.0)
        self._orientation_combo.setCurrentIndex(0)
        self._selected_color = '#E65100'
        self._color_btn.setStyleSheet(
            f'background-color:{self._selected_color}; color:white;')

    # ------------------------------------------------------------------ #
    # Row actions                                                          #
    # ------------------------------------------------------------------ #

    def _remove_selected(self):
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True)
        for r in rows:
            self._mgr.remove(r)
            if self._editing_index is not None:
                if r == self._editing_index:
                    self._reset_add_row()
                elif r < self._editing_index:
                    self._editing_index -= 1
            if self._editing_indices is not None and r in self._editing_indices:
                # Removing part of the current bulk-edit batch — simplest
                # correct behaviour is to drop the whole batch rather than
                # try to keep editing whatever's left of it.
                self._reset_add_row()
        self._populate_table(select_row=self._editing_index)
        self._remove_btn.setEnabled(False)
        self._notify()

    def _clear_all(self):
        self._mgr.clear()
        self._reset_add_row()
        self._populate_table()
        self._notify()

    def _on_selection(self):
        selected_rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        self._remove_btn.setEnabled(bool(selected_rows))

        if len(selected_rows) == 1:
            self._load_row_into_add_form(selected_rows[0])
        elif len(selected_rows) >= 2:
            self._load_multi_selection_into_add_form(selected_rows)
        else:
            # A drop to ZERO selected rows. Table selection is reported by
            # Qt as a bare count with no information about what caused the
            # change, and interacting with this dialog's OWN bottom-row
            # controls (typing in a field, opening a combo box, clicking a
            # spinbox's arrows) can transiently report an empty table
            # selection without the user ever intending to deselect
            # anything. Rather than passively leaving the row looking
            # deselected while quietly still tracking it internally,
            # actively RESELECT whatever was being edited, so what's on
            # screen always matches what "Update selected" will actually
            # apply to. Use "Cancel edit" to explicitly abandon an
            # in-progress edit instead.
            if self._editing_index is not None:
                if 0 <= self._editing_index < len(self._mgr.markers):
                    self._table.selectRow(self._editing_index)
                else:
                    self._reset_add_row()
            elif self._editing_indices:
                valid = [i for i in self._editing_indices
                         if 0 <= i < len(self._mgr.markers)]
                if valid:
                    self._select_rows(valid)
                    self._remove_btn.setEnabled(True)
                    self._load_multi_selection_into_add_form(valid)
                else:
                    self._reset_add_row()
            # else: nothing was being edited: stay in "Add" mode, no-op.

    def _select_rows(self, rows):
        """Select exactly the given rows, like selectRow() but for more
        than one row at once (selectRow() replaces the whole selection
        each time it's called, so it can't be looped to build up a
        multi-row selection). Signals are blocked during the loop —
        each individual setSelected() call would otherwise fire
        itemSelectionChanged with a partial, transiently-wrong selection —
        so callers must refresh anything that depends on the final
        selection themselves afterward."""
        self._table.blockSignals(True)
        self._table.clearSelection()
        for r in rows:
            for c in range(self._table.columnCount()):
                item = self._table.item(r, c)
                if item is not None:
                    item.setSelected(True)
        self._table.blockSignals(False)

    def _load_row_into_add_form(self, row):
        if not (0 <= row < len(self._mgr.markers)):
            return
        m = self._mgr.markers[row]
        self._editing_index = row
        self._editing_indices = None

        self._position_edit.setEnabled(True)
        self._position_edit.setPlaceholderText('e.g. 1000 or -0.0005')
        self._position_edit.setText(
            _format_position(m.get('position', m.get('x', 0.0))))
        self._label_edit.setEnabled(True)
        self._label_edit.setPlaceholderText('e.g. Phe 1004')
        axis = m.get('axis', 'x')
        self._axis_combo.setCurrentIndex(_AXES.index(axis) if axis in _AXES else 0)
        self._label_edit.setText(m['label'])
        style_label = _LINESTYLE_LABELS[
            _LINESTYLES.index(m['linestyle'])
            if m['linestyle'] in _LINESTYLES else 0]
        self._style_combo.setCurrentText(style_label)
        self._width_spin.setValue(m.get('linewidth', 1.0))
        self._fontsize_spin.setValue(m.get('fontsize', 7.0))
        self._label_offset_spin.setValue(m.get('label_offset', 0.02) * 100.0)
        orientation_label = _ORIENTATION_LABELS[
            _ORIENTATIONS.index(m.get('orientation', 'vertical'))
            if m.get('orientation', 'vertical') in _ORIENTATIONS else 0]
        self._orientation_combo.setCurrentText(orientation_label)
        self._selected_color = m['color']
        self._color_btn.setStyleSheet(
            f'background-color:{self._selected_color}; color:white;')

        self._add_btn.setText('Update selected')
        self._add_grp_lbl.setText('Edit selected marker:')
        self._cancel_edit_btn.setVisible(True)

    def _load_multi_selection_into_add_form(self, rows):
        """Load 2+ selected markers into the bottom row for a bulk edit.

        Position and Label are inherently per-marker — setting every
        selected marker to the same position, or the same label text,
        would just be confusing (or actively wrong), so those two fields
        are disabled rather than showing one arbitrarily-chosen marker's
        value as if it applied to all of them. Style, Width, Label dir,
        Color, and Axis genuinely are useful to set identically across
        several markers at once, so they stay editable, seeded from the
        first selected marker's current values as a starting point.
        """
        self._editing_index = None
        self._editing_indices = list(rows)

        self._position_edit.setEnabled(False)
        self._position_edit.setText('')
        self._position_edit.setPlaceholderText(f'{len(rows)} markers selected')
        self._label_edit.setEnabled(False)
        self._label_edit.setText('')
        self._label_edit.setPlaceholderText('(per-marker, not bulk-editable)')

        m = self._mgr.markers[rows[0]]
        axis = m.get('axis', 'x')
        self._axis_combo.setCurrentIndex(_AXES.index(axis) if axis in _AXES else 0)
        style_label = _LINESTYLE_LABELS[
            _LINESTYLES.index(m['linestyle'])
            if m['linestyle'] in _LINESTYLES else 0]
        self._style_combo.setCurrentText(style_label)
        self._width_spin.setValue(m.get('linewidth', 1.0))
        self._fontsize_spin.setValue(m.get('fontsize', 7.0))
        self._label_offset_spin.setValue(m.get('label_offset', 0.02) * 100.0)
        orientation_label = _ORIENTATION_LABELS[
            _ORIENTATIONS.index(m.get('orientation', 'vertical'))
            if m.get('orientation', 'vertical') in _ORIENTATIONS else 0]
        self._orientation_combo.setCurrentText(orientation_label)
        self._selected_color = m['color']
        self._color_btn.setStyleSheet(
            f'background-color:{self._selected_color}; color:white;')

        self._add_btn.setText(f'Update {len(rows)} selected')
        self._add_grp_lbl.setText(f'Edit {len(rows)} selected markers:')
        self._cancel_edit_btn.setVisible(True)

    def _notify(self):
        if self._on_change:
            self._on_change()

    def _show_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'band_markers')
