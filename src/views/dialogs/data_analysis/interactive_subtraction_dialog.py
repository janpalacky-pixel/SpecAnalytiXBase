# src/views/dialogs/data_analysis/interactive_subtraction_dialog.py
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QDoubleSpinBox, QSpinBox, QSlider,
                             QLabel, QListWidget, QComboBox,
                             QWidget, QSizePolicy, QCheckBox, QListWidgetItem,
                             QMessageBox, QGridLayout, QFileDialog, QAbstractItemView,
                             QDialogButtonBox, QToolButton)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import uuid
import numpy as np
from scipy.interpolate import interp1d
from math import ceil
from src.modules.data_analysis.interactive_subtraction_manager import (
    InteractiveSubtractionManager, AxisMismatchError)
from src.modules.utils.spectra_validation import axes_match
from src.modules.utils.label_shortening import (
    make_shortened_name_delegate, make_shorten_names_checkbox)


class _MultiSpectrumPickerDialog(QDialog):
    """Small dialog for choosing one or more spectra from a file that
    contains several. Each one chosen becomes its own separate subtrahend
    list entry, the same as importing a single-spectrum file would."""

    def __init__(self, parent, labels):
        super().__init__(parent)
        self.setWindowTitle('Choose Spectra')
        layout = QVBoxLayout(self)

        info = QLabel(
            'This file contains several spectra. Select one or more to use '
            'as separate subtrahends:'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.addItems(labels)
        self.list_widget.item(0).setSelected(True)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        select_all_btn = QPushButton('Select all')
        select_all_btn.clicked.connect(self.list_widget.selectAll)
        btn_row.addWidget(select_all_btn)
        clear_btn = QPushButton('Clear')
        clear_btn.clicked.connect(self.list_widget.clearSelection)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_rows(self):
        return [self.list_widget.row(item) for item in self.list_widget.selectedItems()]


class InteractiveSubtractionDialog(QDialog):
    subtraction_applied = pyqtSignal(dict)
    # Emitted whenever stored_factors changes so the controller can persist it
    factors_updated = pyqtSignal(dict)
    # Emitted whenever a subtrahend is loaded from an external file, so the
    # controller can persist it the same way as stored_factors — kept local
    # to this dialog/controller session, never added to the main spectrum
    # list, but remembered across dialog close/reopen.
    file_subtrahends_updated = pyqtSignal(list)

    def __init__(self, parent=None, selected_spectra=None, controller=None,
                 stored_factors=None, file_subtrahends=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle('Spectra subtraction')
        self.setModal(True)

        self.selected_spectra = selected_spectra or []
        self.controller = controller
        # Bound method (commit_interactive_subtraction) passed in directly
        # by whatever opened this dialog, so Apply / Add as New can commit
        # the result right here without going through a separate signal
        # and a disconnected main-window confirmation step.
        self.commit_callback = commit_callback

        # Restore persisted factors from the manager (label-pair keyed)
        self.stored_factors: dict = stored_factors or {}

        # Subtrahends loaded from an external file rather than chosen from
        # the main window's selection. Kept separate from selected_spectra
        # (never added to the main spectrum list) but combined with it via
        # _subtrahend_pool() wherever the subtrahend list is built or
        # indexed, so the rest of the dialog's logic doesn't need to know
        # the difference. Restored from the controller so they survive
        # dialog close/reopen, the same way stored_factors does.
        self.file_subtrahends: list = list(file_subtrahends or [])

        # Internal state
        self.minuend_index = 0
        self.subtrahend_index = 1 if len(self.selected_spectra) > 1 else 0
        self.subtraction_factor = 1.0
        self.slider_mapping = None
        self.autoscale_y = True
        self.y_lim_difference = None
        self.x_lim_full_range = None

        # Stateless helper for the axis check + subtraction math shared with
        # the manager — NOT the same object as the controller's persistent
        # manager (this dialog never owned that instance; it only needs the
        # pure computation methods, called fresh each time). Using this
        # instead of a private interp1d/allclose copy is what keeps
        # update_plot/estimate_and_set_initial_factor from silently
        # reimplementing (and silently getting wrong) the same axis check.
        self._calc = InteractiveSubtractionManager()

        self.resize(1450, 900)
        self.setWindowFlags(
            Qt.Dialog |
            Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)
        self.setup_ui()

        # Qt's default behavior: pressing Enter/Return in a spinbox or line
        # edit both commits that field's value AND propagates the keypress
        # to trigger whichever button in the dialog Qt has picked as the
        # "auto-default" button — by design, so Enter can submit a form.
        # This dialog has a dozen buttons and none of them opted out, so
        # e.g. typing a new Center value and pressing Enter would silently
        # ALSO click "Set as center" right after, which promptly overwrote
        # the value just typed with the (stale) current factor. None of
        # this dialog's actions should ever fire just because the user
        # pressed Enter somewhere else — every one of them is meant to be
        # an explicit click (this includes Apply / Add as New, where an
        # accidental Enter-triggered commit would be worse than a reverted
        # spinbox).
        from PyQt5.QtWidgets import QPushButton
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)

        if self.selected_spectra:
            self.initialize_dialog()

    def _subtrahend_pool(self):
        """Every spectrum that can act as a subtrahend: the spectra
        selected in the main window, plus any loaded from an external
        file for this dialog session. subtrahend_index indexes into this
        combined sequence, not into selected_spectra alone."""
        return self.selected_spectra + self.file_subtrahends

    # =================================================================
    # UI construction
    # =================================================================
    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self.create_plot_panel(), stretch=3)
        main_layout.addWidget(self.create_control_panel(), stretch=1)

    def create_plot_panel(self):
        plot_widget = QWidget()
        layout = QVBoxLayout(plot_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.figure = Figure(figsize=(10, 7), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, plot_widget)

        self.ax_spectra = self.figure.add_subplot(211)
        self.ax_difference = self.figure.add_subplot(212, sharex=self.ax_spectra)

        for ax in (self.ax_spectra, self.ax_difference):
            ax.set_ylabel('Intensity', fontsize=13)
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis='both', labelsize=11)
        self.ax_difference.set_xlabel('X', fontsize=13)

        # Slider row
        slider_layout = QHBoxLayout()
        self.factor_slider = QSlider(Qt.Horizontal)
        self.factor_slider.setMinimum(1)
        self.factor_slider.setMaximum(1001)
        self.factor_slider.setValue(501)
        self.factor_slider.valueChanged.connect(self.on_slider_changed)
        slider_layout.addWidget(self.factor_slider)

        self.factor_label = QLabel('1.00000')
        self.factor_label.setStyleSheet(
            'color: #3A6AAF; font-weight: bold; font-size: 13pt;'
        )
        self.factor_label.setMinimumWidth(100)
        self.factor_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider_layout.addWidget(self.factor_label)

        # Bottom controls
        controls_h = QHBoxLayout()
        controls_h.addWidget(self.create_factor_specification_group(), 2)
        controls_h.addWidget(self.create_axis_limits_group(), 1)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        layout.addLayout(slider_layout)
        layout.addLayout(controls_h)
        return plot_widget

    def create_factor_specification_group(self):
        group = QGroupBox('Subtraction factor specification')
        layout = QGridLayout()
        layout.setSpacing(6)
        layout.setHorizontalSpacing(4)
        # Labels fixed, spinboxes stretch, small gap between the two pairs
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)

        # Center
        center_label = QLabel('Center')
        self.center_spinbox = QDoubleSpinBox()
        self.center_spinbox.setRange(-1e6, 1e6)
        self.center_spinbox.setDecimals(5)
        self.center_spinbox.setValue(1.0)
        # Without this, every digit typed (not just Enter/focus-loss/arrow
        # clicks) fires valueChanged -> on_range_params_changed ->
        # update_plot, so typing "1000" redraws on "1", "10", "100", "1000".
        self.center_spinbox.setKeyboardTracking(False)
        self.center_spinbox.valueChanged.connect(self.on_range_params_changed)
        layout.addWidget(center_label, 0, 0)
        layout.addWidget(self.center_spinbox, 0, 1)

        # Half-width
        half_label = QLabel('Half-width')
        self.half_spinbox = QDoubleSpinBox()
        self.half_spinbox.setRange(1e-6, 1e6)
        self.half_spinbox.setDecimals(5)
        self.half_spinbox.setValue(1.0)
        self.half_spinbox.setKeyboardTracking(False)
        self.half_spinbox.valueChanged.connect(self.on_range_params_changed)
        layout.addWidget(half_label, 1, 0)
        layout.addWidget(self.half_spinbox, 1, 1)

        # Number of points
        points_label = QLabel('# of points')
        self.points_spinbox = QSpinBox()
        self.points_spinbox.setRange(2, 10000)
        self.points_spinbox.setValue(1001)
        self.points_spinbox.setKeyboardTracking(False)
        self.points_spinbox.valueChanged.connect(self.on_range_params_changed)
        layout.addWidget(points_label, 0, 2)
        layout.addWidget(self.points_spinbox, 0, 3)

        # Set factor button — centres the range on the current factor
        self.set_factor_button = QPushButton('Set as center')
        self.set_factor_button.setToolTip(
            'Move the slider center to the current factor value'
        )
        self.set_factor_button.clicked.connect(self.on_set_factor_clicked)
        layout.addWidget(self.set_factor_button, 1, 2, 1, 2)

        group.setLayout(layout)
        return group

    def create_axis_limits_group(self):
        group = QGroupBox('Y axis limits for difference spectrum')
        layout = QGridLayout()

        self.autoscale_y_checkbox = QCheckBox('Autoscale y')
        self.autoscale_y_checkbox.setChecked(True)
        self.autoscale_y_checkbox.stateChanged.connect(self.on_autoscale_y_changed)

        self.rescale_y_button = QPushButton('Rescale y')
        self.rescale_y_button.clicked.connect(self.on_rescale_y_clicked)
        self.rescale_y_button.setVisible(False)

        self.hide_toolbar_checkbox = QCheckBox('Hide toolbar')
        self.hide_toolbar_checkbox.stateChanged.connect(self.on_hide_toolbar_changed)

        layout.addWidget(self.autoscale_y_checkbox, 0, 0)
        layout.addWidget(self.rescale_y_button, 0, 1)
        layout.addWidget(self.hide_toolbar_checkbox, 0, 2)
        group.setLayout(layout)
        return group

    def create_control_panel(self):
        control_widget = QWidget()
        control_widget.setMaximumWidth(350)
        layout = QVBoxLayout(control_widget)

        # One-time notice when this dialog opens with factors already
        # restored from an earlier session (see
        # InteractiveSubtractionController.show_dialog's docstring) — self.
        # stored_factors reflects whatever was passed into __init__, before
        # anything in THIS session has changed it. Without this, "Show
        # info" quietly already having entries the moment the dialog opens
        # looks like something went wrong rather than an intentional
        # convenience.
        if self.stored_factors:
            n = len(self.stored_factors)
            noun = 'factor' if n == 1 else 'factors'
            restore_notice = QLabel(
                f'ℹ Restored {n} previously stored subtraction {noun} for '
                f'this selection, from earlier in this session (see Show '
                f'info). Not left over from a different selection — those '
                f'are always cleared automatically.'
            )
            restore_notice.setWordWrap(True)
            restore_notice.setStyleSheet(
                'color: #2C3E6B; font-size: 8pt; font-style: italic; '
                'padding: 4px 6px; background-color: #EEF2F8; '
                'border: 1px solid #C9D6EA; border-radius: 4px;'
            )
            layout.addWidget(restore_notice)

        self.prev_factor_button = QPushButton('Restore factor')
        self.prev_factor_button.setToolTip(
            'Restore the previously stored subtraction factor for the active minuend'
        )
        self.prev_factor_button.setEnabled(False)
        self.prev_factor_button.clicked.connect(self.on_prev_factor_clicked)

        self.show_info_button = QPushButton('Show info')
        self.show_info_button.clicked.connect(self.on_show_info_clicked)

        self.help_button = QPushButton('Help')
        self.help_button.clicked.connect(self.on_help_clicked)

        # Minuend list — select one or more rows (click, Ctrl/Shift-click,
        # or All/Clear below) to choose which spectra Update will commit
        # the current subtrahend and factor to. Which one of the selected
        # rows is actually previewed/adjusted via the slider is a
        # separate, explicit choice — see the "Preview" combo box below —
        # since Qt's own "current item" can't represent both "selected
        # for the operation" and "currently previewed" once they need to
        # diverge (e.g. picking the middle one of five selected rows).
        # This dialog's own, independent "shorten names" toggle — feeds
        # both the minuend and subtrahend list delegates below, so it
        # sits above both rather than tucked under either one.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _: (self.minuend_list.viewport().update(),
                       self.subtrahend_list.viewport().update())
        )
        layout.addWidget(self.checkBox_shorten_names)

        minuend_label = QLabel('Minuend')
        minuend_label.setStyleSheet('color: #3A6AAF; font-weight: bold;')
        self.minuend_list = QListWidget()
        self.minuend_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.minuend_list.setStyleSheet(
            'QListWidget::item:selected { background-color: #4A7FC1; color: white; }'
        )
        # Display-only "shorten names" — item.text() (what selection
        # tracking above reads) is untouched by this paint-only delegate.
        self.minuend_list.setItemDelegate(
            make_shortened_name_delegate(self.minuend_list, self._shorten_names_enabled)
        )
        self.minuend_list.itemSelectionChanged.connect(self._on_minuend_selection_changed)
        layout.addWidget(minuend_label)
        layout.addWidget(self.minuend_list, 1)

        # Preview picker — which one of the currently selected minuends
        # drives the slider, the plot, and the factor shown below. Always
        # a member of the selection above; when exactly one row is
        # selected this has only one entry, so the choice is unambiguous.
        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel('Preview:'))
        self.preview_combo = QComboBox()
        self.preview_combo.currentIndexChanged.connect(self._on_preview_combo_changed)
        preview_row.addWidget(self.preview_combo, 1)
        layout.addLayout(preview_row)

        # All / Clear + help, directly below the Minuend list (no
        # separate "Specify minuends" box — selecting rows above already
        # is the act of specifying minuends).
        minuend_btns_row = QHBoxLayout()
        target_help_btn = QToolButton()
        target_help_btn.setText('?')
        target_help_btn.setToolTip('What does this do?')
        target_help_btn.setFixedSize(20, 20)
        target_help_btn.clicked.connect(self.on_target_group_help_clicked)
        minuend_btns_row.addWidget(target_help_btn)
        self.all_button = QPushButton('All')
        self.clear_button = QPushButton('Clear')
        self.all_button.clicked.connect(self.on_select_all_targets)
        self.clear_button.clicked.connect(self.on_clear_all_targets)
        minuend_btns_row.addWidget(self.all_button)
        minuend_btns_row.addWidget(self.clear_button)
        layout.addLayout(minuend_btns_row)

        # Commit section — separate from minuend selection above, since
        # Update acts on the current subtrahend and factor, not on which
        # minuends are selected. The summary label always names exactly
        # what Update is about to do. There used to be a separate Reset
        # button here too, scoped to whatever happened to be selected in
        # the minuend list above — easy to lose track of relative to
        # "Show info" / "Clear all stored factors", which lived in a
        # different window entirely. Removal is now done from inside Show
        # info instead, where you can see exactly which stored factor(s)
        # you're about to remove.
        commit_group = QGroupBox('Commit')
        commit_layout = QVBoxLayout()

        update_layout = QHBoxLayout()
        self.update_button = QPushButton('Update')
        self.update_button.clicked.connect(self.on_update_clicked)
        update_layout.addWidget(self.update_button)
        commit_layout.addLayout(update_layout)

        info_row = QHBoxLayout()
        info_row.addWidget(self.prev_factor_button)
        info_row.addWidget(self.show_info_button)
        commit_layout.addLayout(info_row)

        # Subtrahend list
        subtrahend_label = QLabel('Subtrahend')
        subtrahend_label.setStyleSheet('color: #C0392B; font-weight: bold;')
        self.subtrahend_list = QListWidget()
        self.subtrahend_list.setSelectionMode(QListWidget.SingleSelection)
        self.subtrahend_list.setStyleSheet(
            'QListWidget::item:selected { background-color: #C0392B; color: white; }'
        )
        # Display-only "shorten names" — see minuend_list above.
        self.subtrahend_list.setItemDelegate(
            make_shortened_name_delegate(self.subtrahend_list, self._shorten_names_enabled)
        )
        self.subtrahend_list.currentItemChanged.connect(self.on_subtrahend_changed)
        layout.addWidget(subtrahend_label)
        layout.addWidget(self.subtrahend_list, 1)

        self.import_subtrahend_button = QPushButton('Import from file\u2026')
        self.import_subtrahend_button.setToolTip(
            'Load a spectrum from a file to use as the subtrahend. Stays local '
            'to this dialog \u2014 it is not added to the main spectrum list \u2014 '
            'but is remembered if you reopen this dialog later.'
        )
        self.import_subtrahend_button.clicked.connect(self.on_import_subtrahend_clicked)
        layout.addWidget(self.import_subtrahend_button)

        # Summary label — shows what will actually be subtracted and with what factor
        self.operation_summary_label = QLabel()
        self.operation_summary_label.setWordWrap(True)
        self.operation_summary_label.setStyleSheet(
            'color: #2C3E6B; font-style: italic; font-size: 8pt; '
            'padding: 3px 2px; background-color: #EEF2F8; border-radius: 3px;'
        )
        commit_layout.addWidget(self.operation_summary_label)

        commit_group.setLayout(commit_layout)
        layout.addWidget(commit_group)

        layout.addStretch()

        # Apply / Add as New — this dialog's own commit actions. Apply
        # replaces the affected minuends in place; Add as New leaves the
        # originals untouched and appends the results under new, unique
        # names instead (never reusing the source label, which previously
        # caused two spectra to silently share one name).
        apply_row = QHBoxLayout()
        self.apply_button = QPushButton('Apply')
        self.apply_button.setToolTip(
            'Replace the minuend spectra that have a stored subtraction factor '
            '(see Show info) with their subtracted result.'
        )
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        self.add_as_new_button = QPushButton('Add as New')
        self.add_as_new_button.setToolTip(
            'Keep the original minuend spectra unchanged and add the subtracted '
            'results to the list under new names.'
        )
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        apply_row.addWidget(self.apply_button)
        apply_row.addWidget(self.add_as_new_button)
        layout.addLayout(apply_row)

        # Closing this dialog does not undo anything already committed via
        # Update — it only dismisses the window, the same as the window's
        # own close button. Settings (stored factors, file subtrahends)
        # persist via the controller regardless of how this dialog closes.
        close_row = QHBoxLayout()
        close_row.addStretch()
        self.help_button.setFixedWidth(90)
        close_row.addWidget(self.help_button)
        self.close_button = QPushButton('Close')
        self.close_button.setFixedWidth(90)
        self.close_button.clicked.connect(self.close)
        close_row.addWidget(self.close_button)
        layout.addLayout(close_row)

        return control_widget

    # =================================================================
    # Initialisation
    # =================================================================
    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def initialize_dialog(self):
        for i, spectrum in enumerate(self.selected_spectra):
            label = spectrum.get('label', f'Spectrum_{i}')
            self.subtrahend_list.addItem(QListWidgetItem(label))

        # Any subtrahends loaded from a file in a previous session of this
        # same dialog/controller are restored here, tagged the same way a
        # freshly-loaded one is (see _add_file_subtrahend_item).
        for spectrum in self.file_subtrahends:
            self._add_file_subtrahend_item(spectrum)

        if len(self.selected_spectra) > 1:
            self.subtrahend_list.setCurrentRow(1)
            self.subtrahend_index = 1

        self._refresh_minuend_list()
        self._restore_or_estimate_factor()
        self.update_plot()

        if self.x_lim_full_range is None:
            self.x_lim_full_range = self.ax_difference.get_xlim()

    def _add_file_subtrahend_item(self, spectrum):
        """Add one file-loaded spectrum's row to the subtrahend list,
        visually tagged so it's clear it isn't one of the main-window
        selected spectra."""
        label = spectrum.get('label', 'Imported spectrum')
        item = QListWidgetItem(f'\U0001F4C1 {label}')
        item.setToolTip(f'Loaded from file, local to this dialog: {label}')
        self.subtrahend_list.addItem(item)

    def _refresh_minuend_list(self):
        """Rebuild the Minuend list, excluding the current subtrahend.

        A spectrum cannot be its own subtrahend, so it's left out here to
        avoid that confusion. Selection is preserved by label across the
        rebuild; if the row that becomes the new subtrahend was selected,
        it's simply dropped from the selection, same as everything else
        about it disappearing from this list.
        """
        s_key = self._key_for(self._subtrahend_pool()[self.subtrahend_index])
        previously_selected = {
            item.text() for item in self.minuend_list.selectedItems()
        } if self.minuend_list.count() else set()

        self.minuend_list.blockSignals(True)
        self.minuend_list.clear()
        for i, spectrum in enumerate(self.selected_spectra):
            label = spectrum.get('label', f'Spectrum_{i}')
            # Compare by identity key, not label text — a file-loaded
            # subtrahend and a main-window spectrum could otherwise share a
            # label (before the unique_id fix above) or two main-window
            # spectra could coincidentally be compared by stale label text,
            # wrongly excluding the wrong spectrum from being a minuend.
            if self._key_for(spectrum) != s_key:
                self.minuend_list.addItem(QListWidgetItem(label))

        any_selected = False
        for row in range(self.minuend_list.count()):
            item = self.minuend_list.item(row)
            if item.text() in previously_selected:
                item.setSelected(True)
                any_selected = True

        if not any_selected and self.minuend_list.count():
            # Nothing survived the rebuild (the only previously-selected
            # row just became the subtrahend) — default to the first row
            # so there's always something to preview, same fallback used
            # everywhere else a selection can't be empty.
            self.minuend_list.item(0).setSelected(True)

        self.minuend_list.blockSignals(False)

        # Selection changes made above were signal-blocked, so the
        # preview combo needs an explicit rebuild now.
        self._on_minuend_selection_changed()

    @staticmethod
    def _key_for(spectrum):
        return InteractiveSubtractionManager._key_for(spectrum)

    def _pair_key(self):
        """Return the (minuend_key, subtrahend_key) key for stored_factors —
        see InteractiveSubtractionManager._key_for. Not label-based, so a
        rename elsewhere doesn't disconnect an already-stored factor from
        its spectrum."""
        m = self.selected_spectra[self.minuend_index]
        s = self._subtrahend_pool()[self.subtrahend_index]
        return (self._key_for(m), self._key_for(s))

    def _restore_or_estimate_factor(self):
        """Restore a previously stored factor if available, otherwise estimate via SVD."""
        key = self._pair_key()
        if key in self.stored_factors:
            factor = self.stored_factors[key]
            self._set_slider_to_factor(factor)
        else:
            self.estimate_and_set_initial_factor()
        # Always refresh the button's enabled state for the pair now
        # being looked at — previously this only happened in the "factor
        # found" branch above, so the button stayed enabled from a
        # PREVIOUS pair even after navigating to a pair with no stored
        # factor at all.
        self._update_prev_factor_button()

    def _set_slider_to_factor(self, factor):
        """Centre the range on the given factor and position the slider there."""
        half = max(abs(factor) * 0.5, 1.0)
        self.center_spinbox.blockSignals(True)
        self.half_spinbox.blockSignals(True)
        self.center_spinbox.setValue(factor)
        self.half_spinbox.setValue(half)
        self.center_spinbox.blockSignals(False)
        self.half_spinbox.blockSignals(False)
        # Rebuild mapping and position slider at centre (= the factor)
        lim1 = factor - half
        lim2 = factor + half
        n = self.points_spinbox.value()
        self.slider_mapping = interp1d([1, n], [lim1, lim2])
        mid = ceil(n / 2)
        self.factor_slider.blockSignals(True)
        self.factor_slider.setValue(mid)
        self.factor_slider.blockSignals(False)
        self.subtraction_factor = factor
        self.factor_label.setText(f'{factor:.5f}')

    def _update_operation_summary(self):
        """Update the summary label showing what will be subtracted from what."""
        if not self.selected_spectra:
            return
        s_label = self._subtrahend_pool()[self.subtrahend_index].get('label', '?')
        factor = self.subtraction_factor
        selected_items = self.minuend_list.selectedItems()
        n_sel = len(selected_items)

        preview_label = None
        if 0 <= self.minuend_index < len(self.selected_spectra):
            preview_label = self.selected_spectra[self.minuend_index].get('label', '?')

        if n_sel == 0:
            text = f'Select minuend(s) above, then press Update.\nSubtrahend: {s_label}  ×  {factor:.5f}'
        elif n_sel == 1:
            m_label = selected_items[0].text()
            text = f'Will compute:  {m_label}  −  {factor:.5f} × {s_label}'
        elif n_sel <= 4:
            # Small enough to name each one — naming the actual minuends
            # is the whole point of this label, so don't collapse to a
            # bare count unless there are genuinely too many to read.
            m_labels = ', '.join(item.text() for item in selected_items)
            preview_note = f'\n(Factor shown is from previewing  {preview_label}.)' if preview_label else ''
            text = (
                f'Will compute, for each of  {m_labels}:\n'
                f'(that spectrum)  −  {factor:.5f} × {s_label}{preview_note}'
            )
        else:
            first_two = ', '.join(item.text() for item in selected_items[:2])
            preview_note = f'\n(Factor shown is from previewing  {preview_label}.)' if preview_label else ''
            text = (
                f'Will compute, for {n_sel} spectra ({first_two}, \u2026):\n'
                f'(each spectrum)  −  {factor:.5f} × {s_label}{preview_note}'
            )
        self.operation_summary_label.setText(text)

    def _update_prev_factor_button(self):
        """Enable/disable the Restore factor button based on stored state."""
        key = self._pair_key()
        has = key in self.stored_factors
        self.prev_factor_button.setEnabled(has)
        self.prev_factor_button.setStyleSheet(
            'color: #3A6AAF; font-weight: bold;' if has else ''
        )

    # =================================================================
    # Factor estimation
    # =================================================================
    def estimate_and_set_initial_factor(self):
        if len(self.selected_spectra) < 2:
            return

        minuend = self.selected_spectra[self.minuend_index]
        subtrahend = self._subtrahend_pool()[self.subtrahend_index]

        try:
            factor = self._calc.estimate_initial_factor(minuend, subtrahend)
        except AxisMismatchError:
            # Nothing to estimate — update_plot() (called right after this
            # by every caller) will show the mismatch state and disable
            # the controls. Leave the spinboxes as they are rather than
            # guessing a number for a pair that can't be computed at all.
            return

        self.center_spinbox.blockSignals(True)
        self.half_spinbox.blockSignals(True)
        self.center_spinbox.setValue(factor)
        self.half_spinbox.setValue(max(abs(factor) * 0.5, 1.0))
        self.center_spinbox.blockSignals(False)
        self.half_spinbox.blockSignals(False)
        self.update_slider_mapping()

    def update_slider_mapping(self):
        """Rebuild slider mapping from center and half-width, reset to center."""
        lim1 = self._lim1()
        lim2 = self._lim2()
        n = self.points_spinbox.value()
        self.factor_slider.blockSignals(True)
        self.factor_slider.setRange(1, n)
        self.slider_mapping = interp1d([1, n], [lim1, lim2])
        mid = ceil(n / 2)
        self.factor_slider.setValue(mid)
        self.factor_slider.blockSignals(False)
        self.subtraction_factor = float(self.slider_mapping(mid))
        self.factor_label.setText(f'{self.subtraction_factor:.5f}')

    def _lim1(self):
        return self.center_spinbox.value() - self.half_spinbox.value()

    def _lim2(self):
        return self.center_spinbox.value() + self.half_spinbox.value()

    # =================================================================
    # Slot handlers
    # =================================================================
    def on_range_params_changed(self):
        """Center, half-width, or # of points changed — rebuild, preserve factor."""
        lim1 = self._lim1()
        lim2 = self._lim2()
        n = self.points_spinbox.value()
        if lim2 <= lim1 or n < 2:
            return
        self.slider_mapping = interp1d([1, n], [lim1, lim2])
        self.factor_slider.blockSignals(True)
        self.factor_slider.setRange(1, n)
        factor = self.subtraction_factor
        if lim1 <= factor <= lim2:
            pos = 1 + (factor - lim1) / (lim2 - lim1) * (n - 1)
            pos = int(max(1, min(n, round(pos))))
        elif factor < lim1:
            pos = 1
        else:
            pos = n
        self.factor_slider.setValue(pos)
        self.factor_slider.blockSignals(False)
        # Keep subtraction_factor in sync with wherever the slider actually
        # ended up. Previously this was left stale: setValue() above is
        # signal-blocked (so it doesn't fire on_slider_changed), and
        # nothing else updated it — so subtraction_factor stayed pinned to
        # whatever it was before Center/half-width/points were touched.
        # That's mostly invisible when the old factor is still within the
        # new range (the position solved for above already IS that same
        # factor), but when it gets clamped to an edge (e.g. narrowing the
        # range, or moving Center away from the current factor), the
        # factor silently stopped matching what the slider/spinboxes
        # showed — including "Set as center" reading back a number that no
        # longer matched anything on screen.
        self.subtraction_factor = float(self.slider_mapping(pos))
        self.factor_label.setText(f'{self.subtraction_factor:.5f}')
        self.update_plot()

    def on_limits_changed(self):
        self.on_range_params_changed()

    def on_slider_changed(self, value):
        if self.slider_mapping is None:
            return
        self.subtraction_factor = float(self.slider_mapping(value))
        self.factor_label.setText(f'{self.subtraction_factor:.5f}')
        self.update_plot()

    def on_slider_released(self):
        pass

    def on_set_factor_clicked(self):
        """Set current factor as new center, keeping half-width unchanged."""
        self.center_spinbox.setValue(self.subtraction_factor)



    def _on_minuend_selection_changed(self):
        """Called whenever the set of selected minuends changes. Rebuilds
        the Preview combo to list exactly the currently selected rows,
        preserving the current preview choice by label if it's still
        selected, otherwise defaulting to the first selected row."""
        prev_preview_label = self.preview_combo.currentText() or None

        selected_labels = [item.text() for item in self.minuend_list.selectedItems()]

        self.preview_combo.blockSignals(True)
        self.preview_combo.clear()
        self.preview_combo.addItems(selected_labels)

        if prev_preview_label in selected_labels:
            self.preview_combo.setCurrentText(prev_preview_label)
        elif selected_labels:
            self.preview_combo.setCurrentIndex(0)
        self.preview_combo.blockSignals(False)

        self._sync_minuend_index_from_combo()
        self._restore_or_estimate_factor()
        self.update_plot()

    def _sync_minuend_index_from_combo(self):
        """Resolve the Preview combo's current text back to an index into
        selected_spectra, without triggering the combo's own change signal."""
        label = self.preview_combo.currentText()
        if not label:
            return
        try:
            self.minuend_index = next(
                i for i, s in enumerate(self.selected_spectra)
                if s.get('label', '') == label
            )
        except StopIteration:
            pass

    def _on_preview_combo_changed(self, _index):
        """Called when the user explicitly picks a different spectrum to
        preview from among the currently selected minuends — independent
        of which rows are selected, so picking the middle one of several
        selected rows is always possible."""
        self._sync_minuend_index_from_combo()
        self._restore_or_estimate_factor()
        self.update_plot()

    def on_subtrahend_changed(self, current=None, previous=None):
        self.subtrahend_index = self.subtrahend_list.currentRow()
        self._refresh_minuend_list()
        self._restore_or_estimate_factor()
        self.update_plot()
        if 0 <= self.subtrahend_index < len(self._subtrahend_pool()) and self.selected_spectra:
            self._check_subtrahend_overlap(self._subtrahend_pool()[self.subtrahend_index])

    def on_import_subtrahend_clicked(self):
        """Load one or more spectra from a file to use as subtrahends.

        Uses the same pure file-reading function as the main Import
        feature (read_table_data), but does not touch the main spectrum
        manager — loaded spectra stay local to this dialog and are never
        added to the main spectrum list. If the file contains more than
        one spectrum, a multi-select picker lets the user choose any
        number of them, each becoming its own separate subtrahend.
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Import Subtrahend From File', '',
            'Spectrum Files (*.txt *.csv *.dat *.xlsx *.xls *.xlsm);;All Files (*.*)'
        )
        if not file_path:
            return

        try:
            from src.modules.data_io.table_data_converter import read_table_data
            spectra_from_file = read_table_data(file_path)
        except Exception as e:
            QMessageBox.critical(
                self, 'Import Error',
                f'Could not read a spectrum from this file:\n{e}'
            )
            return

        if not spectra_from_file:
            QMessageBox.warning(
                self, 'Import Error',
                'No spectra were found in the selected file.'
            )
            return

        if len(spectra_from_file) == 1:
            chosen_list = [spectra_from_file[0]]
        else:
            labels = [s.get('label', f'Spectrum {i}') for i, s in enumerate(spectra_from_file)]
            picker = _MultiSpectrumPickerDialog(self, labels)
            if picker.exec_() != QDialog.Accepted:
                return
            rows = picker.selected_rows()
            if not rows:
                return
            chosen_list = [spectra_from_file[i] for i in rows]

        existing_labels = {s.get('label', '') for s in self.file_subtrahends}
        added = []
        for chosen in chosen_list:
            # Avoid a confusing duplicate label if one with the same name
            # was already imported earlier in this dialog session.
            base_label = chosen.get('label', 'Imported spectrum')
            label = base_label
            suffix = 1
            while label in existing_labels:
                label = f'{base_label}_{suffix}'
                suffix += 1
            existing_labels.add(label)
            chosen['label'] = label

            # File-loaded spectra never go through the main import flow
            # (spectrum_manager), so they don't get a unique_id there. Give
            # them one here explicitly, rather than letting _key_for() fall
            # back to the label. Without this, a file subtrahend whose label
            # happens to match a main-window spectrum's label would collide
            # under the SAME stored_factors key as that unrelated spectrum —
            # apply_subtraction_to_spectra's by_key.setdefault() would then
            # silently resolve the stored factor to the wrong spectrum
            # entirely (see InteractiveSubtractionController.apply_subtraction_to_spectra).
            chosen.setdefault('metadata', {})
            chosen['metadata'].setdefault('unique_id', str(uuid.uuid4()))

            self.file_subtrahends.append(chosen)
            self._add_file_subtrahend_item(chosen)
            added.append(chosen)

        self.file_subtrahends_updated.emit(list(self.file_subtrahends))

        # Select the last-added subtrahend immediately. on_subtrahend_changed
        # checks it against the current minuend's x-axis and offers to
        # align if needed.
        new_row = self.subtrahend_list.count() - 1
        self.subtrahend_list.setCurrentRow(new_row)
        self.on_subtrahend_changed()

    def _check_subtrahend_overlap(self, subtrahend):
        """Offer to align a file-loaded subtrahend when its x-axis doesn't
        match the current minuend's — or remove it if the user doesn't
        want to align it, since an unaligned mismatched subtrahend can't
        be used for anything (no preview, no estimate, Update refuses it).
        Keeping it around unusable just means being asked about it again
        every time it's selected, including after closing and reopening
        the dialog (file_subtrahends persists across reopens; a "remember
        I said no" flag living only on this dialog instance would not).
        Removing it is the only choice that's actually remembered.

        This does NOT decide whether the pair can be used in the
        meantime — that's a hard refusal enforced independently in
        update_plot / estimate_and_set_initial_factor / on_update_clicked
        via the same axes_match rule used here. This prompt fires on ANY
        axis mismatch, not just a poor-overlap heuristic: even a
        subtrahend that fully overlaps the minuend's range but on a
        different grid can't be subtracted point-by-point without
        interpolation, and that interpolation must be an explicit,
        visible choice, never an implicit one."""
        if not self.selected_spectra:
            return
        minuend = self.selected_spectra[self.minuend_index]
        mx = minuend['x_scale']
        sx = subtrahend['x_scale']

        if axes_match(mx, sx):
            return  # already a match — nothing to offer

        m_lo, m_hi = float(np.min(mx)), float(np.max(mx))
        s_lo, s_hi = float(np.min(sx)), float(np.max(sx))
        m_label = minuend.get('label', '?')
        s_label = subtrahend.get('label', '?')

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle('X-Axis Mismatch')
        msg.setText(
            f"Minuend '{m_label}' and subtrahend '{s_label}' have different x-axes:\n\n"
            f"  Minuend '{m_label}':     {m_lo:.4g}\u2013{m_hi:.4g}, {mx.size} points\n"
            f"  Subtrahend '{s_label}':  {s_lo:.4g}\u2013{s_hi:.4g}, {sx.size} points"
        )
        msg.setInformativeText(
            'Interactive Subtraction is point-by-point and cannot compute '
            'anything for this pair until the axes match — no preview, no '
            'auto-factor estimate, and Update will refuse to store a factor '
            "for it. If both spectra represent the same x quantity (e.g. "
            "both Raman), aligning the subtrahend onto the minuend's x-axis "
            'makes it usable.\n\n'
            'If these are genuinely different techniques (e.g. CD vs. Raman), '
            "there is nothing meaningful to align — remove this subtrahend "
            'below (you can always re-import the file later), or use the '
            'Data Range operation on the source file first if the two '
            'really should share an axis.'
        )
        align_btn = msg.addButton('Align to Minuend X-Axis', QMessageBox.AcceptRole)
        remove_btn = msg.addButton('Remove This Subtrahend', QMessageBox.DestructiveRole)
        msg.exec_()

        if msg.clickedButton() is align_btn:
            self._align_subtrahend_to_minuend(subtrahend, minuend)
        elif msg.clickedButton() is remove_btn:
            self._remove_file_subtrahend(subtrahend)

    def _remove_file_subtrahend(self, subtrahend):
        """Drop a file-loaded subtrahend the user declined to align. Also
        removes its row from subtrahend_list and, if it was the active
        selection, falls back to a usable subtrahend so the dialog isn't
        left pointing at a row that no longer exists.

        Looked up by identity KEY (_key_for), not list.index()/equality.
        list.index() on a list of spectrum dicts is fragile: Python's
        equality check for `list.index` only skips calling dict.__eq__ when
        the two objects are the exact same instance (an internal identity
        shortcut). If that shortcut doesn't apply for any reason, dict
        equality falls through to comparing the x_scale/y_scale numpy
        arrays with `==`, which raises "truth value of an array... is
        ambiguous" — and the previous version of this method caught that
        under a bare `except ValueError: return`, silently doing nothing.
        Matching by key sidesteps the whole problem: it's a simple string
        comparison, never touches array data, and can't raise.

        subtrahend_list.currentItemChanged is connected to
        on_subtrahend_changed, so removing the current row would otherwise
        fire that handler immediately with whatever row Qt auto-selects —
        before this method has decided what the fallback should be. Signals
        are blocked around the mutation so on_subtrahend_changed runs
        exactly once, deliberately, at the end.
        """
        target_key = self._key_for(subtrahend)
        list_index = next(
            (i for i, s in enumerate(self.file_subtrahends)
             if self._key_for(s) == target_key),
            None
        )
        if list_index is None:
            return
        row = len(self.selected_spectra) + list_index
        was_selected = (self.subtrahend_index == row)

        self.file_subtrahends.pop(list_index)
        self.subtrahend_list.blockSignals(True)
        self.subtrahend_list.takeItem(row)
        self.subtrahend_list.blockSignals(False)
        self.file_subtrahends_updated.emit(list(self.file_subtrahends))

        if was_selected:
            # Fall back to the first available subtrahend, same default
            # used when the dialog first opens.
            self.subtrahend_index = 0 if self._subtrahend_pool() else None
            if self.subtrahend_index is not None:
                self.subtrahend_list.blockSignals(True)
                self.subtrahend_list.setCurrentRow(self.subtrahend_index)
                self.subtrahend_list.blockSignals(False)
            self.on_subtrahend_changed()
        elif self.subtrahend_index is not None and row < self.subtrahend_index:
            # A row before the current selection was removed — shift the
            # index so it still points at the same spectrum. The widget's
            # own current row shifted automatically along with it (no
            # signal needed since the selected item itself didn't change).
            self.subtrahend_index -= 1

    def _align_subtrahend_to_minuend(self, subtrahend, minuend):
        """Interpolate a file-loaded subtrahend onto the minuend's x-axis
        in place, replacing its x_scale/y_scale. This is a one-time local
        alignment for use within this dialog — it does not run the main
        application's 'Data Range' / linearization operation, and does
        not touch the main spectrum list."""
        mx = minuend['x_scale']
        sx, sy = subtrahend['x_scale'], subtrahend['y_scale']
        new_sy = interp1d(sx, sy, kind='linear', bounds_error=False, fill_value=0.0)(mx)
        subtrahend['x_scale'] = mx.copy()
        subtrahend['y_scale'] = new_sy
        self.file_subtrahends_updated.emit(list(self.file_subtrahends))
        self.update_plot()

    def on_target_group_help_clicked(self):
        QMessageBox.information(
            self, 'Specify Minuends',
            'Update commits the current subtrahend and factor for every '
            'spectrum selected in the Minuend list above.\n\n'
            'Click a row to select it, Ctrl+click or Shift+click to select '
            'more than one, or use the All / Clear buttons.\n\n'
            "The 'Preview' box below the list is a separate choice: it "
            'lets you pick exactly which one of the selected spectra '
            'drives the slider and the plot, since that can be different '
            'from "all the spectra I want this factor applied to" once '
            'more than one row is selected.\n\n'
            "The same spectrum can't be picked for both subtrahend and "
            'minuend, since a spectrum cannot be subtracted from itself.'
        )

    def on_select_all_targets(self):
        for i in range(self.minuend_list.count()):
            self.minuend_list.item(i).setSelected(True)

    def on_clear_all_targets(self):
        """Deselect every row except the one currently being previewed —
        a fully empty selection would leave Update with nothing to act
        on, and the previewed row is always a sensible default to keep."""
        preview_label = self.preview_combo.currentText()
        for i in range(self.minuend_list.count()):
            item = self.minuend_list.item(i)
            item.setSelected(item.text() == preview_label)

    def on_prev_factor_clicked(self):
        key = self._pair_key()
        if key in self.stored_factors:
            factor = self.stored_factors[key]
            self._set_slider_to_factor(factor)
            self.update_plot()

    def on_autoscale_y_changed(self, state):
        self.autoscale_y = state == Qt.Checked
        self.rescale_y_button.setVisible(not self.autoscale_y)
        if not self.autoscale_y:
            self.y_lim_difference = self.ax_difference.get_ylim()
        else:
            self.y_lim_difference = None
            self.update_plot()

    def on_rescale_y_clicked(self):
        self.y_lim_difference = None
        self.update_plot()
        self.y_lim_difference = self.ax_difference.get_ylim()

    def on_hide_toolbar_changed(self, state):
        self.toolbar.setVisible(state != Qt.Checked)

    def on_update_clicked(self):
        """Store the current factor and emit signal for Run to pick up."""
        selected_labels = {item.text() for item in self.minuend_list.selectedItems()}
        minuend_indices = [
            i for i, s in enumerate(self.selected_spectra)
            if s.get('label', '') in selected_labels
        ]

        if not minuend_indices:
            QMessageBox.warning(self, 'No Selection',
                                'Please select at least one spectrum.')
            return

        s_subtrahend = self._subtrahend_pool()[self.subtrahend_index]

        # All selected_spectra are guaranteed to share one x-axis (the
        # controller refuses to even open this dialog otherwise), so
        # checking the subtrahend against just one of the targeted
        # minuends is sufficient to know whether it matches all of them.
        # This is the actual enforcement point: a mismatched factor must
        # never enter stored_factors, since that's the dict
        # apply_subtraction_to_spectra later applies without re-checking
        # anything about how it was arrived at.
        representative_minuend = self.selected_spectra[minuend_indices[0]]
        if not axes_match(representative_minuend['x_scale'], s_subtrahend['x_scale']):
            QMessageBox.warning(
                self, "Can't Store Factor",
                "This subtrahend's x-axis doesn't match the selected "
                "minuend(s), so there is nothing valid to store. Use "
                '\u201cAlign to Minuend X-Axis\u201d or choose a different '
                'subtrahend first.'
            )
            return

        s_key = self._key_for(s_subtrahend)
        for idx in minuend_indices:
            minuend = self.selected_spectra[idx]
            m_key = self._key_for(minuend)
            # Each minuend has exactly ONE stored subtrahend at a time —
            # this is a one-to-one "subtract spectrum X from spectrum Y"
            # relationship, not a chain of several. Remove any
            # previously-stored subtrahend for this minuend first, so
            # picking a different reference spectrum and clicking Update
            # REPLACES the earlier choice instead of accumulating
            # alongside it. Without this, re-trying a few candidate
            # subtrahends against the same minuend while looking for the
            # best factor silently left every earlier attempt still
            # stored too — all of which would otherwise still be applied
            # together later.
            for key in list(self.stored_factors.keys()):
                if key[0] == m_key:
                    del self.stored_factors[key]
            self.stored_factors[(m_key, s_key)] = self.subtraction_factor

        self.factors_updated.emit(dict(self.stored_factors))
        self._update_prev_factor_button()

        settings = {
            'minuend_indices': minuend_indices,
            'subtrahend_index': self.subtrahend_index,
            'subtraction_factor': self.subtraction_factor,
            # Apply / Add as New read self.stored_factors directly when
            # committing (see _on_commit_clicked), so this dict and the
            # signal below are no longer load-bearing for that — kept for
            # any other code that might want to observe "a factor was
            # just committed" via this signal.
            'stored_factors': dict(self.stored_factors),
        }
        self.subtraction_applied.emit(settings)

        QMessageBox.information(
            self, 'Subtraction updated',
            f'Factor {self.subtraction_factor:.5f} stored for '
            f'{len(minuend_indices)} spectrum/spectra.'
        )

    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — commits every stored (minuend, subtrahend,
        factor) triple directly via commit_callback, exactly what 'Show
        info' displays. No separate Run button, no generic main-window
        confirmation prompt: this dialog owns the action end to end, so
        feedback (including 'nothing to apply') always appears right
        here, next to the buttons that triggered it. The dialog closes
        itself once the commit succeeds.
        """
        if self.commit_callback is None:
            QMessageBox.critical(
                self, 'Not Available',
                'This dialog was opened without a way to apply changes. '
                'Please reopen it via Parameters.'
            )
            return

        if not self.stored_factors:
            QMessageBox.warning(
                self, 'Nothing to Apply',
                "No subtraction factors have been committed yet. Select one or "
                "more minuends above and click Update first — 'Show info' lists "
                "everything that's currently stored."
            )
            return

        action = 'add as new spectra' if add_as_new else 'replace the affected spectra'
        confirm = QMessageBox.question(
            self, 'Confirm',
            f"Apply the stored subtraction(s) shown in 'Show info' and {action}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(
            dict(self.stored_factors), add_as_new, list(self.selected_spectra)
        )
        if success:
            QMessageBox.information(self, 'Done', message)
            self.accept()
        else:
            QMessageBox.warning(self, 'Nothing to Apply', message)

    def on_show_info_clicked(self):
        """Show a summary table of all stored subtraction factors — and,
        since this is the only place that shows the full picture, the
        only place factors get removed from too. Select one or more rows
        and click "Remove Selected" to delete just those; "Select All" +
        "Remove Selected" replaces what the old "Clear all stored
        factors" button did. This replaces the dialog's old separate
        Reset button (scoped to whatever happened to be selected in the
        minuend list elsewhere, easy to lose track of relative to what
        this table shows) — removal now always happens with the actual
        rows you're removing visible right in front of you.
        """
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView

        info_dialog = QDialog(self)
        info_dialog.setWindowTitle('Subtraction info')
        info_dialog.resize(700, 350)
        layout = QVBoxLayout(info_dialog)

        instructions = QLabel(
            'Select one or more rows, then click "Remove Selected" to delete '
            'just those stored factors.'
        )
        instructions.setStyleSheet('color: #666; font-size: 9pt;')
        layout.addWidget(instructions)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(['Minuend', 'Subtrahend', 'Factor'])
        table.setRowCount(len(self.stored_factors))
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # stored_factors is keyed by unique_id (see _pair_key), not label —
        # resolve back to each spectrum's CURRENT label for display, so a
        # rename since the factor was stored shows up immediately rather
        # than a raw id (or a stale name).
        key_to_label = {
            self._key_for(s): s.get('label', '')
            for s in self.selected_spectra + self.file_subtrahends
        }

        # Keep the actual (m_key, s_key) dict key for each row, in the
        # SAME order rows are populated below — this is how "which rows
        # are selected" gets mapped back to "which dict entries to
        # remove", since the table only ever shows resolved labels, not
        # the underlying keys.
        row_keys = list(self.stored_factors.keys())

        for row, (m_key, s_key) in enumerate(row_keys):
            factor = self.stored_factors[(m_key, s_key)]
            table.setItem(row, 0, QTableWidgetItem(key_to_label.get(m_key, m_key)))
            table.setItem(row, 1, QTableWidgetItem(key_to_label.get(s_key, s_key)))
            table.setItem(row, 2, QTableWidgetItem(f'{factor:.6f}'))

        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(table)

        btn_row = QHBoxLayout()
        select_all_btn = QPushButton('Select All')
        select_all_btn.setToolTip('Select every row (then Remove Selected to clear everything)')
        select_all_btn.clicked.connect(table.selectAll)

        remove_btn = QPushButton('Remove Selected')
        remove_btn.setToolTip('Remove the stored subtraction factor(s) for the selected row(s)')

        def _remove_selected():
            selected_rows = sorted({
                idx.row() for idx in table.selectionModel().selectedRows()
            })
            if not selected_rows:
                QMessageBox.warning(
                    info_dialog, 'No Selection',
                    'Select one or more rows first.'
                )
                return

            n = len(selected_rows)
            noun = 'factor' if n == 1 else 'factors'
            confirm = QMessageBox.question(
                info_dialog, 'Confirm Removal',
                f'Remove the selected {n} stored subtraction {noun}? '
                f'This cannot be undone from here.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return

            for row in selected_rows:
                self.stored_factors.pop(row_keys[row], None)

            self.factors_updated.emit(dict(self.stored_factors))
            self._update_prev_factor_button()
            info_dialog.close()

        remove_btn.clicked.connect(_remove_selected)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(info_dialog.close)
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        info_dialog.exec_()

    def on_help_clicked(self):
        try:
            from src.help.interactive_subtraction_help import (
                get_interactive_subtraction_help_content,
                get_interactive_subtraction_help_title,
            )
            from src.help.help_window import show_help_window
            show_help_window(self,
                             get_interactive_subtraction_help_title(),
                             get_interactive_subtraction_help_content())
        except Exception as e:
            QMessageBox.information(self, 'Help',
                                    'Help documentation is not available.')

    # =================================================================
    # Plot
    # =================================================================
    def _set_controls_enabled(self, enabled):
        """Disable everything that would compute or store a factor for the
        current pair while its axes don't match, so there's no path to a
        stored factor for a pair that was never actually previewable."""
        for widget in (self.factor_slider, self.center_spinbox,
                       self.half_spinbox, self.points_spinbox,
                       self.set_factor_button, self.update_button):
            widget.setEnabled(enabled)
        # prev_factor_button has its own enabled logic tied to whether a
        # factor is already stored for this pair (_update_prev_factor_button)
        # — leave it alone here so restoring an old factor still works even
        # while the live axes happen to mismatch.

    def update_plot(self):
        if not self.selected_spectra or self.minuend_index is None \
                or self.subtrahend_index is None:
            return

        # Preserve zoom
        current_xlim = None
        try:
            xlim = self.ax_difference.get_xlim()
            if xlim != (0.0, 1.0):
                current_xlim = xlim
        except Exception:
            pass

        minuend = self.selected_spectra[self.minuend_index]
        subtrahend = self._subtrahend_pool()[self.subtrahend_index]

        self.ax_spectra.clear()
        self.ax_difference.clear()

        try:
            x, my, scaled, diff = self._calc.preview_difference(
                minuend, subtrahend, self.subtraction_factor)
        except AxisMismatchError as e:
            # Refuse — no interpolation, no zero-fill, no computation at
            # all. This is the only place update_plot can still get here
            # with a mismatched pair: selected_spectra are guaranteed to
            # share an axis by the controller's guard before the dialog
            # ever opens, so a mismatch can only involve a file-loaded
            # subtrahend.
            for ax in (self.ax_spectra, self.ax_difference):
                ax.text(0.5, 0.5, "Can't preview — x-axes don't match.\n"
                        "Use \u201cAlign to Minuend X-Axis\u201d or pick a "
                        "different subtrahend.",
                        ha='center', va='center', transform=ax.transAxes,
                        fontsize=11, color='#C0392B', wrap=True)
                ax.set_xticks([])
                ax.set_yticks([])
            self.canvas.draw()
            self._set_controls_enabled(False)
            self.operation_summary_label.setText(str(e))
            return

        self._set_controls_enabled(True)

        self.ax_spectra.plot(x, my, '-', color='#2D6DB5', label='minuend', linewidth=1.5)
        self.ax_spectra.plot(x, scaled, '-', color='#C0392B',
                             label='factor × subtrahend', linewidth=1.5)
        self.ax_spectra.set_ylabel('Intensity', fontsize=13)
        self.ax_spectra.grid(True, alpha=0.3)
        self.ax_spectra.legend(fontsize=11)
        self.ax_spectra.tick_params(labelsize=11)

        self.ax_difference.plot(x, diff, '-', color='#27AE60',
                                label='difference', linewidth=1.5)
        self.ax_difference.set_xlabel('X', fontsize=13)
        self.ax_difference.set_ylabel('Intensity', fontsize=13)
        self.ax_difference.grid(True, alpha=0.3)
        self.ax_difference.legend(fontsize=11)
        self.ax_difference.tick_params(labelsize=11)

        if current_xlim is not None:
            self.ax_spectra.set_xlim(current_xlim)
            self.ax_difference.set_xlim(current_xlim)

        if not self.autoscale_y and self.y_lim_difference is not None:
            self.ax_difference.set_ylim(self.y_lim_difference)

        self.canvas.draw()
        self._update_operation_summary()

    # =================================================================
    # Settings (for operations_controller)
    # =================================================================
    def get_settings(self):
        selected_labels = {item.text() for item in self.minuend_list.selectedItems()}
        minuend_indices = [
            i for i, s in enumerate(self.selected_spectra)
            if s.get('label', '') in selected_labels
        ]

        return {
            'minuend_indices': minuend_indices,
            'subtrahend_index': self.subtrahend_index,
            'subtraction_factor': self.subtraction_factor,
            # The actual source of truth for Apply/Run: every committed
            # (minuend_label, subtrahend_label) -> factor triple, exactly
            # what "Show info" displays. minuend_indices/subtrahend_index/
            # subtraction_factor above only reflect whatever happens to be
            # selected in the dialog right now (kept for dialog-reopen
            # convenience), and are not what gets applied.
            'stored_factors': dict(self.stored_factors),
        }
