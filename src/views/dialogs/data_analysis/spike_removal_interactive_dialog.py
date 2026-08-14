# src/views/dialogs/data_analysis/spike_removal_interactive_dialog.py

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QDoubleSpinBox,
    QSpinBox, QWidget, QSizePolicy, QMessageBox, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from src.modules.utils.label_shortening import make_shortened_name_delegate, make_shorten_names_checkbox


class SpikeRemovalInteractiveDialog(QDialog):
    """
    Dialog for interactive spike removal.

    Workflow
    --------
    1. Global auto-detection runs on all spectra using the global threshold
       and half-window when the dialog opens.
    2. Navigate through spectra with Prev / Next or the list.
    3. For the current spectrum, adjust threshold/half-window individually
       and click "Re-detect this spectrum" to override the global detection.
    4. Click on red (auto) markers to reject them (grey = skip removal).
    5. Click on a clean point to add a manual spike (orange).
    6. Click Apply or Add as New — commits directly via commit_callback.

    Signals
    -------
    removal_applied(dict)   emitted on close (whether or not anything was
                             committed) so the controller can remember the
                             current marking for the next time this dialog
                             opens for the same spectra.
    """

    removal_applied = pyqtSignal(dict)

    def __init__(self, parent=None, spectra=None, controller=None,
                 current_settings=None, saved_state=None, commit_callback=None):
        super().__init__(parent)
        self.controller   = controller
        self.spectra      = spectra or []
        self._settings    = current_settings or {}
        self._current_idx = 0
        self._click_conn  = None
        self._committed   = False
        # Bound method (OperationsController.commit_spike_removal) passed in
        # by whatever opened this dialog, so Apply / Add as New can commit
        # the result directly, without a separate Run step.
        self.commit_callback = commit_callback

        from src.modules.data_analysis.spike_removal_manager import SpikeRemovalManager
        self.manager = SpikeRemovalManager()

        # Per-spectrum threshold/half-window overrides: {label: (threshold, half_window)}
        self._per_spectrum_params = {}

        # This dialog's own, independent "shorten names" checkbox (see
        # _setup_ui) — no longer tied to the main window's shared one.
        self._shorten_names_enabled = lambda: self.checkBox_shorten_names.isChecked()

        self.setWindowTitle("Spike Removal")
        self.setModal(True)
        self.resize(1080, 700)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self._setup_ui()

        # Restore previous spike state if provided, otherwise run fresh detection
        if saved_state and (saved_state.get('auto_detected') or
                            saved_state.get('manual_extra')):
            self._restore_saved_state(saved_state)
        else:
            self._run_global_detect()

        self._update_spectrum_list()
        self._plot_current()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        outer = QHBoxLayout(self)
        outer.setSpacing(6)

        # ── Left panel ─────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(290)
        ll = QVBoxLayout(left)
        ll.setSpacing(6)

        # Global auto-detection
        glob_group = QGroupBox("Global auto-detection")
        gg = QVBoxLayout(glob_group)

        thr_row = QHBoxLayout()
        thr_row.addWidget(QLabel("Threshold:"))
        self.global_thr = QDoubleSpinBox()
        self.global_thr.setRange(1.0, 50.0)
        self.global_thr.setDecimals(1)
        self.global_thr.setSingleStep(0.5)
        self.global_thr.setValue(self._settings.get('threshold', 7.0))
        self.global_thr.setFixedWidth(65)
        self.global_thr.setToolTip(
            "Modified Z-score threshold applied to all spectra.\n"
            "Lower = more detections. Typical range: 5–15."
        )
        thr_row.addWidget(self.global_thr)
        thr_row.addStretch()
        gg.addLayout(thr_row)

        hw_row = QHBoxLayout()
        hw_row.addWidget(QLabel("Half-window:"))
        self.global_hw = QSpinBox()
        self.global_hw.setRange(1, 20)
        self.global_hw.setValue(self._settings.get('half_window', 2))
        self.global_hw.setFixedWidth(55)
        self.global_hw.setToolTip(
            "Points on each side of a spike centre to replace.\n"
            "Increase if spikes are wider than 1–2 points."
        )
        hw_row.addWidget(self.global_hw)
        hw_row.addStretch()
        gg.addLayout(hw_row)

        redetect_all_btn = QPushButton("Re-detect all spectra")
        redetect_all_btn.setToolTip(
            "Re-run detection with these parameters on every spectrum.\n"
            "Clears all per-spectrum overrides, manual additions and rejections."
        )
        redetect_all_btn.clicked.connect(self._on_redetect_all)
        gg.addWidget(redetect_all_btn)
        ll.addWidget(glob_group)

        # Per-spectrum override
        spec_group = QGroupBox("This spectrum — override")
        sg = QVBoxLayout(spec_group)

        sthr_row = QHBoxLayout()
        sthr_row.addWidget(QLabel("Threshold:"))
        self.spec_thr = QDoubleSpinBox()
        self.spec_thr.setRange(1.0, 50.0)
        self.spec_thr.setDecimals(1)
        self.spec_thr.setSingleStep(0.5)
        self.spec_thr.setValue(self._settings.get('threshold', 7.0))
        self.spec_thr.setFixedWidth(65)
        self.spec_thr.setToolTip("Threshold used only for the current spectrum.")
        sthr_row.addWidget(self.spec_thr)
        sthr_row.addStretch()
        sg.addLayout(sthr_row)

        shw_row = QHBoxLayout()
        shw_row.addWidget(QLabel("Half-window:"))
        self.spec_hw = QSpinBox()
        self.spec_hw.setRange(1, 20)
        self.spec_hw.setValue(self._settings.get('half_window', 2))
        self.spec_hw.setFixedWidth(55)
        self.spec_hw.setToolTip("Half-window used only for the current spectrum.")
        shw_row.addWidget(self.spec_hw)
        shw_row.addStretch()
        sg.addLayout(shw_row)

        redetect_one_btn = QPushButton("Re-detect this spectrum")
        redetect_one_btn.setToolTip(
            "Re-run detection on the current spectrum only, using the\n"
            "threshold and half-window values above.\n"
            "Manual additions and rejections for this spectrum are cleared."
        )
        redetect_one_btn.clicked.connect(self._on_redetect_one)
        sg.addWidget(redetect_one_btn)
        ll.addWidget(spec_group)

        # Spectrum list
        list_group = QGroupBox("Spectra")
        lg = QVBoxLayout(list_group)
        # Display-only "shorten names" toggle — this dialog's own,
        # independent on/off state (see label_shortening.py's
        # make_shorten_names_checkbox), unrelated to the main window's
        # checkbox and always starting unchecked.
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _state: self.spectrum_list.viewport().update())
        lg.addWidget(self.checkBox_shorten_names)
        self.spectrum_list = QListWidget()
        # Display-only "shorten names" — navigation is positional
        # (currentRowChanged), never by matching displayed text.
        self.spectrum_list.setItemDelegate(
            make_shortened_name_delegate(self.spectrum_list, self._shorten_names_enabled)
        )
        self.spectrum_list.currentRowChanged.connect(self._on_list_row_changed)
        lg.addWidget(self.spectrum_list)
        list_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        ll.addWidget(list_group)

        # Navigation buttons
        nav_row = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.clicked.connect(self._go_prev)
        nav_row.addWidget(self.prev_btn)
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self._go_next)
        nav_row.addWidget(self.next_btn)
        ll.addLayout(nav_row)


        # Spike editing mode toggle
        self.edit_mode_btn = QPushButton("🖊  Spike editing: OFF")
        self.edit_mode_btn.setCheckable(True)
        self.edit_mode_btn.setChecked(False)
        self.edit_mode_btn.setToolTip(
            "Toggle spike editing mode.\n"
            "When ON: clicking modifies spikes; zoom/pan is preserved between edits.\n"
            "When OFF: toolbar pan and zoom work normally."
        )
        self.edit_mode_btn.toggled.connect(self._on_edit_mode_toggled)
        ll.addWidget(self.edit_mode_btn)

        self.show_points_cb = QCheckBox("Show data points")
        self.show_points_cb.setChecked(False)
        self.show_points_cb.setToolTip(
            "Show individual data points on the spectrum line.\n"
            "Useful for seeing exactly where spike markers are placed."
        )
        self.show_points_cb.stateChanged.connect(lambda: self._plot_current(preserve_limits=True))
        ll.addWidget(self.show_points_cb)

        instr = QLabel(
            "<b>Edit mode ON:</b><br>"
            "Left-click orange ▲ → remove/exclude spike.<br>"
            "Left-click spectrum → add manual spike (orange ▲).<br>"
            "<i>Zoom/pan are preserved between spike edits.</i>"
        )
        instr.setWordWrap(True)
        instr.setStyleSheet("font-size: 11px; color: #555;")
        ll.addWidget(instr)

        # Spike summary for current spectrum
        self.spike_info = QLabel("")
        self.spike_info.setWordWrap(True)
        ll.addWidget(self.spike_info)

        # Use QDialogButtonBox for correct platform button layout
        from PyQt5.QtWidgets import QDialogButtonBox
        btn_box = QDialogButtonBox()
        help_btn = QPushButton("Help")
        help_btn.clicked.connect(self._show_help)
        btn_box.addButton(help_btn, QDialogButtonBox.HelpRole)

        # Apply / Add as New commit directly via commit_callback — there's
        # no separate Run step in the main window for this operation
        # anymore (see OperationsController.commit_spike_removal).
        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip(
            "Replace the selected spectra with their despiked result."
        )
        self.apply_button.setStyleSheet(
            "QPushButton { background: #2E7D32; color: white; "
            "font-weight: bold; padding: 5px; border-radius: 3px; }"
            "QPushButton:hover { background: #388E3C; }"
        )
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        btn_box.addButton(self.apply_button, QDialogButtonBox.ActionRole)

        self.add_as_new_button = QPushButton("Add as New")
        self.add_as_new_button.setToolTip(
            "Keep the original spectra unchanged and add the despiked "
            "results to the list under new names."
        )
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        btn_box.addButton(self.add_as_new_button, QDialogButtonBox.ActionRole)

        close_btn = QPushButton("Close")
        # IMPORTANT: connect to self.close, not self.reject. In Qt,
        # QDialog.reject()/accept() call done()->hide() directly and do
        # NOT go through close()/closeEvent() — only self.close() or the
        # native window-close action do. removal_applied (the signal that
        # persists the current marking for next time, see closeEvent below)
        # is only emitted from closeEvent, so connecting this button to
        # reject() would silently mean nothing is ever remembered when the
        # user clicks Close — confirmed empirically, this was firing on
        # neither the old nor the new code. self.close() still leaves the
        # dialog's result() as Rejected (0, the default), so this changes
        # nothing else about how callers see this dialog being dismissed.
        close_btn.clicked.connect(self.close)
        btn_box.addButton(close_btn, QDialogButtonBox.RejectRole)
        ll.addWidget(btn_box)

        outer.addWidget(left)

        # ── Right canvas ───────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)

        self.fig = Figure(figsize=(10, 6))
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar(self.canvas, right)
        rl.addWidget(self.toolbar)
        rl.addWidget(self.canvas)
        outer.addWidget(right)


    # ------------------------------------------------------------------ #
    # Detection                                                            #
    # ------------------------------------------------------------------ #

    def _on_edit_mode_toggled(self, checked):
        if checked:
            # Deactivate any active toolbar mode so clicks aren't consumed by pan/zoom
            if self.toolbar.mode != '':
                self.toolbar.mode = ''
                self.canvas.toolbar.zoom()   # toggle off by calling again
            self.edit_mode_btn.setText("🖊  Spike editing: ON")
            self.edit_mode_btn.setStyleSheet(
                "QPushButton { background: #E65100; color: white; "
                "font-weight: bold; border-radius: 3px; padding: 4px; }"
            )
        else:
            self.edit_mode_btn.setText("🖊  Spike editing: OFF")
            self.edit_mode_btn.setStyleSheet("")

    # ------------------------------------------------------------------ #
    # Detection                                                            #
    # ------------------------------------------------------------------ #

    def _restore_saved_state(self, saved_state):
        """Restore previously defined spike selections into the manager.
        On reopen, treat everything that was marked for removal as manual_extra
        (orange) so the user sees a clean consistent state — all spikes orange,
        no grey, regardless of how they were originally detected."""
        # Rebuild effective spikes from previous session
        prev_auto     = {k: list(v) for k, v in saved_state.get('auto_detected', {}).items()}
        prev_manual   = {k: list(v) for k, v in saved_state.get('manual_extra', {}).items()}
        prev_rejected = {k: set(v)  for k, v in saved_state.get('rejected', {}).items()}

        # Combine everything that WAS going to be removed into manual_extra
        all_labels = set(prev_auto) | set(prev_manual)
        for label in all_labels:
            auto_set    = set(prev_auto.get(label, []))
            manual_set  = set(prev_manual.get(label, []))
            rejected_set = prev_rejected.get(label, set())
            effective   = (auto_set - rejected_set) | manual_set
            if effective:
                self.manager.manual_extra[label] = sorted(effective)
        # No auto_detected, no rejected — clean slate visually

    def _run_global_detect(self):
        """Detect spikes on all spectra using global parameters."""
        self.manager.reset_all()
        self._per_spectrum_params.clear()
        self.manager.detect_spikes(
            self.spectra,
            threshold=self.global_thr.value(),
            half_window=self.global_hw.value(),
        )

    def _on_redetect_all(self):
        self._run_global_detect()
        self._update_spectrum_list()
        self._plot_current()

    def _on_redetect_one(self):
        """Re-detect spikes for the current spectrum only."""
        if not self.spectra:
            return
        spectrum = self.spectra[self._current_idx]
        label    = spectrum['label']

        thr = self.spec_thr.value()
        hw  = self.spec_hw.value()
        self._per_spectrum_params[label] = (thr, hw)

        # Clear existing state for this spectrum
        self.manager.reset_for_spectrum(label)

        # Re-detect with per-spectrum parameters
        from src.modules.data_analysis.spike_removal_manager import SpikeRemovalManager
        tmp = SpikeRemovalManager()
        result = tmp.detect_spikes([spectrum], threshold=thr, half_window=hw)
        self.manager.auto_detected[label] = result.get(label, [])

        self._update_spectrum_list()
        self._plot_current()

    # ------------------------------------------------------------------ #
    # Navigation                                                           #
    # ------------------------------------------------------------------ #

    def _go_prev(self):
        if self._current_idx > 0:
            self._current_idx -= 1
            self.spectrum_list.blockSignals(True)
            self.spectrum_list.setCurrentRow(self._current_idx)
            self.spectrum_list.blockSignals(False)
            self._sync_per_spectrum_spinboxes()
            self._plot_current()

    def _go_next(self):
        if self._current_idx < len(self.spectra) - 1:
            self._current_idx += 1
            self.spectrum_list.blockSignals(True)
            self.spectrum_list.setCurrentRow(self._current_idx)
            self.spectrum_list.blockSignals(False)
            self._sync_per_spectrum_spinboxes()
            self._plot_current()

    def _on_list_row_changed(self, row):
        if 0 <= row < len(self.spectra):
            self._current_idx = row
            self._sync_per_spectrum_spinboxes()
            self._plot_current()

    def _sync_per_spectrum_spinboxes(self):
        """Set per-spectrum spinboxes to the override for the current spectrum,
        or fall back to the global values."""
        label = self.spectra[self._current_idx]['label']
        thr, hw = self._per_spectrum_params.get(
            label, (self.global_thr.value(), self.global_hw.value())
        )
        self.spec_thr.blockSignals(True)
        self.spec_hw.blockSignals(True)
        self.spec_thr.setValue(thr)
        self.spec_hw.setValue(hw)
        self.spec_thr.blockSignals(False)
        self.spec_hw.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Spectrum list                                                        #
    # ------------------------------------------------------------------ #

    def _update_spectrum_list(self):
        self.spectrum_list.blockSignals(True)
        self.spectrum_list.clear()
        for spectrum in self.spectra:
            label = spectrum['label']
            n     = len(self.manager.get_effective_spikes(label))
            has_override = label in self._per_spectrum_params
            suffix = ' *' if has_override else ''
            text  = f"{label}  [{n} spike{'s' if n != 1 else ''}]{suffix}"
            item  = QListWidgetItem(text)
            if n > 0:
                item.setForeground(Qt.red)
            self.spectrum_list.addItem(item)
        self.spectrum_list.blockSignals(False)
        if self.spectra:
            self.spectrum_list.setCurrentRow(self._current_idx)

    # ------------------------------------------------------------------ #
    # Canvas                                                               #
    # ------------------------------------------------------------------ #

    def _plot_current(self, preserve_limits=False):
        if not self.spectra:
            return

        # Disconnect previous click handler safely
        if self._click_conn is not None:
            try:
                self.canvas.mpl_disconnect(self._click_conn)
            except Exception:
                pass
            self._click_conn = None

        spectrum  = self.spectra[self._current_idx]
        label     = spectrum['label']
        x         = np.asarray(spectrum['x_scale'])
        y         = np.asarray(spectrum['y_scale'])

        auto      = set(self.manager.auto_detected.get(label, []))
        rejected  = self.manager.rejected.get(label, set())
        manual    = set(self.manager.manual_extra.get(label, []))
        effective = self.manager.get_effective_spikes(label)
        has_override = label in self._per_spectrum_params
        title_suffix = ' [custom threshold]' if has_override else ''

        # Reuse axes so the toolbar's navigation stack (Home) is preserved.
        # fig.clear() destroys the stack; ax.cla() keeps it.
        if self.fig.axes:
            ax = self.fig.axes[0]
            saved_xlim = ax.get_xlim() if preserve_limits else None
            saved_ylim = ax.get_ylim() if preserve_limits else None
            ax.cla()
        else:
            ax = self.fig.add_subplot(111)
            saved_xlim = saved_ylim = None

        marker = 'o' if self.show_points_cb.isChecked() else None
        ms     = 3   if self.show_points_cb.isChecked() else None
        ax.plot(x, y, color='steelblue', lw=1.2, label='Spectrum', zorder=2,
                marker=marker, markersize=ms, markerfacecolor='steelblue')

        # All spikes marked for removal shown in the same colour
        will_remove = (auto - rejected) | manual
        if will_remove:
            xi = [x[i] for i in sorted(will_remove) if i < len(x)]
            yi = [y[i] for i in sorted(will_remove) if i < len(y)]
            ax.scatter(xi, yi, color='darkorange', s=90, zorder=5,
                       marker='^', label='Marked for removal')

        ax.set_title(
            f"{label}  —  {len(effective)} spike(s) marked for removal{title_suffix}"
        )
        ax.set_xlabel('x')
        ax.set_ylabel('Intensity')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        self.fig.tight_layout()

        if saved_xlim is not None:
            ax.set_xlim(saved_xlim)
            ax.set_ylim(saved_ylim)

        self.canvas.draw()

        will_remove_n = len(effective)
        excluded_n   = len(rejected)
        self.spike_info.setText(
            f"<b>{label}</b><br>"
            f"Marked for removal: <b>{will_remove_n}</b><br>"
            f"Excluded from removal: {excluded_n}"
        )

        item = self.spectrum_list.item(self._current_idx)
        if item:
            suffix = ' *' if has_override else ''
            n = len(effective)
            item.setText(f"{label}  [{n} spike{'s' if n != 1 else ''}]{suffix}")
            item.setForeground(Qt.red if n > 0 else Qt.black)

        self._click_conn = self.canvas.mpl_connect(
            'button_press_event', self._on_canvas_click
        )

    def _on_canvas_click(self, event):
        """Add/reject spikes by clicking on the canvas.
        Only active when spike editing mode is ON."""
        if not self.edit_mode_btn.isChecked():
            return
        if event.inaxes is None or event.xdata is None:
            return

        spectrum    = self.spectra[self._current_idx]
        label       = spectrum['label']
        x           = np.asarray(spectrum['x_scale'])
        y           = np.asarray(spectrum['y_scale'])
        nearest_idx = int(np.argmin(np.abs(x - event.xdata)))

        auto     = set(self.manager.auto_detected.get(label, []))
        rejected = self.manager.rejected.get(label, set())
        manual   = set(self.manager.manual_extra.get(label, []))

        # Use pixel distance from the click to each marker.
        # This naturally handles any zoom level — the tolerance is always
        # the same number of pixels on screen regardless of data units.
        ax = event.inaxes
        PIXEL_TOL = 15   # pixels — generous enough to click, tight enough to distinguish

        def pixel_dist(idx):
            """Screen distance in pixels from the click to data point idx."""
            if idx < 0 or idx >= len(x):
                return 1e9
            xi, yi = ax.transData.transform((x[idx], y[idx]))
            return ((xi - event.x) ** 2 + (yi - event.y) ** 2) ** 0.5

        hit_auto   = [a for a in auto   if pixel_dist(a) <= PIXEL_TOL]
        hit_manual = [m for m in manual if pixel_dist(m) <= PIXEL_TOL]
        hit_any_orange = hit_auto + [m for m in hit_manual if m not in hit_auto]

        if event.button == 1:   # left click
            if hit_any_orange:
                best = min(hit_any_orange, key=pixel_dist)
                if best in manual:
                    # Manual spike — remove it
                    self.manager.remove_manual_spike(label, best)
                else:
                    # Auto-detected spike — remove it from auto_detected
                    # entirely (not just rejected) so it's gone outright
                    # rather than shown as a grey "rejected" marker.
                    auto_list = self.manager.auto_detected.get(label, [])
                    if best in auto_list:
                        auto_list.remove(best)
                    self.manager.rejected.get(label, set()).discard(best)
            else:
                # No orange marker nearby — add one if space is clear
                nearby_any = [m for m in manual if pixel_dist(m) <= PIXEL_TOL]
                nearby_auto = [a for a in auto if pixel_dist(a) <= PIXEL_TOL and a not in rejected]
                if not nearby_any and not nearby_auto:
                    self.manager.add_manual_spike(label, nearest_idx)

        self._plot_current(preserve_limits=True)

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def _show_help(self):
        from src.help.spike_removal_help import (
            get_spike_removal_help_content,
            get_spike_removal_help_title,
        )
        from src.help.help_window import show_help_window
        show_help_window(self, get_spike_removal_help_title(),
                         get_spike_removal_help_content())

    # ------------------------------------------------------------------ #
    # OK                                                                   #
    # ------------------------------------------------------------------ #

    def get_settings(self):
        """Build the settings dict from the current spike marking. Pure
        data — no dialogs, no side effects — so it's safe to call from
        closeEvent as well as from the commit path.
        """
        half_window_map = {}
        for s in self.spectra:
            label = s['label']
            _, hw = self._per_spectrum_params.get(
                label, (self.global_thr.value(), self.global_hw.value())
            )
            half_window_map[label] = hw

        return {
            'threshold':   self.global_thr.value(),
            'half_window': self.global_hw.value(),
            'mode':        'interactive',
            'effective_spikes': {
                s['label']: self.manager.get_effective_spikes(s['label'])
                for s in self.spectra
            },
            'half_window_map': half_window_map,
        }

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

        settings = self.get_settings()

        action = ("add the despiked result as new spectra" if add_as_new
                  else "replace the selected spectra with their despiked result")
        confirm = QMessageBox.question(
            self, "Confirm", f"{action[0].upper() + action[1:]}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(settings, add_as_new, list(self.spectra))
        if success:
            QMessageBox.information(self, "Done", message)
            # Skip the closeEvent's "remember for next time" sync below —
            # commit_spike_removal already reset the persisted detection
            # state, since it's now baked into the corrected data.
            self._committed = True
            self.close()
        else:
            QMessageBox.warning(self, "Could Not Apply", message)

    def closeEvent(self, event):
        """Remember the current marking for next time, even if nothing was
        ever committed — unless we just committed successfully, in which
        case commit_spike_removal already reset the persisted state and
        re-emitting the (now stale) marking here would undo that.
        """
        if not self._committed:
            self.removal_applied.emit(self.get_settings())
        event.accept()

