# src/views/dialogs/data_analysis/cosmic_ray_dialog.py
"""
Cross-spectrum cosmic ray detection dialog.

Shows a heatmap of detected outlier positions across all spectra,
allows threshold tuning, preview of detected rays, and applies removal.
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QDoubleSpinBox, QSpinBox,
    QCheckBox, QSizePolicy, QSplitter, QWidget, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QProgressDialog, QApplication, QRadioButton, QButtonGroup,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from mpl_toolkits.axes_grid1 import make_axes_locatable

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    make_display_text_delegate, compute_distinguishing_labels,
    make_shorten_names_checkbox,
)
logger = get_logger(__name__)


class CosmicRayDialog(QDialog):

    def __init__(self, parent=None, spectra=None, controller=None,
                 current_settings=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle('Cosmic Ray Detection (cross-spectrum)')
        self.setMinimumSize(960, 580)
        self.resize(1200, 720)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        self.spectra      = list(spectra or [])
        self._settings    = dict(current_settings or {})
        # CosmicRayController — owns the actual CosmicRayManager instance,
        # shared with the commit path (OperationsController.commit_cosmic_ray_removal)
        # so the detection shown here and the detection actually applied
        # are provably the same computation, not two independent ones that
        # merely usually agree. Falls back to a private controller if none
        # is given (e.g. direct/standalone use), so this dialog still works
        # on its own.
        if controller is not None:
            self.controller = controller
        else:
            from src.controllers.data_analysis.cosmic_ray_controller import CosmicRayController
            self.controller = CosmicRayController(None)
        self._flagged     = {}
        self._colorbar    = None   # tracks the heatmap's colorbar object
        self._cbar_ax     = None   # dedicated axes the colorbar always draws into
        self.result_spectra = None   # kept for backward compatibility; unused by the new commit flow
        # Bound method (OperationsController.commit_cosmic_ray_removal)
        # passed in by whatever opened this dialog, so Apply / Add as New
        # can commit the result directly, without a separate Run step.
        self.commit_callback = commit_callback

        self._build_ui()
        # Initial detection is deferred to showEvent() below, rather than
        # run here or even via a plain QTimer.singleShot(0, ...) from
        # __init__ — at this point the dialog hasn't been shown yet (exec_()
        # hasn't even started its event loop), so a 0ms timer scheduled
        # here isn't guaranteed to fire after the widget actually has its
        # final on-screen geometry. Detecting on first show, deferred by one
        # more event-loop tick, reliably runs after layout is finalized.
        self._initial_detect_pending = True

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_detect_pending:
            self._initial_detect_pending = False
            # Force any layout/resize events already queued by the show
            # itself to be processed right now, synchronously, rather than
            # hoping a single deferred call lands after them. Then detect
            # after a further short, real delay (not 0ms, which on some
            # platforms can still run before the window manager has
            # actually finished sizing the window) to give layout one more
            # chance to settle before tight_layout()/the colorbar axes are
            # computed against it.
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
            QTimer.singleShot(50, self._detect)

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _on_shorten_names_toggled(self, *_):
        # Both consumers of _display_labels_map() need an explicit poke:
        # the table's delegate is paint-only (viewport().update() is enough
        # to make it repaint with the new map), but the heatmap's y-tick
        # labels are plain matplotlib text baked in at draw time — nothing
        # about toggling this checkbox otherwise touches the canvas, so
        # without re-running _refresh_heatmap() the old labels would just
        # sit there unchanged until the next detect().
        self._refresh_heatmap()
        self._table.viewport().update()

    def _display_labels_map(self):
        """{full_label: display_label} for self.spectra — see
        label_shortening.py. Display-only (heatmap y-tick text, the
        Spectrum column's paint-only delegate); lookups elsewhere in this
        dialog stay keyed by full label."""
        if not self._shorten_names_enabled():
            return {}
        all_labels = [s.get('label', '') for s in self.spectra]
        if len(all_labels) < 2:
            return {}
        return compute_distinguishing_labels(all_labels)

    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 900])
        root.addWidget(splitter)

    def _build_left(self):
        w = QWidget()
        # setFixedWidth() used to sit here — it actively fights the
        # QSplitter above: dragging the handle right can never make this
        # panel any wider than the fixed value (nothing to give), and
        # dragging left doesn't shrink the panel's actual content either —
        # the layout inside still expects the fixed width, so anything
        # narrower just gets clipped (the Detection settings groupbox and
        # the button row disappearing, exactly as reported) rather than
        # reflowing. A min/max range lets the splitter actually resize it
        # continuously in both directions. The min is set low enough to
        # allow real shrinking; the max keeps it from eating unreasonable
        # space if dragged the other way. 300 (vs the previous 280) is
        # also enough for "Add as New" to render without being cropped —
        # that was the same fixed-width-panel problem, not a separate one:
        # four buttons (Help / Apply / Add as New / Close) in one row
        # sharing 280px minus margins didn't leave "Add as New" enough
        # room for its full label.
        w.setMinimumWidth(220)
        w.setMaximumWidth(420)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        grp = QGroupBox('Detection settings')
        gl  = QVBoxLayout(grp)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel('Threshold (Z-score):'))
        self._thresh_spin = QDoubleSpinBox()
        self._thresh_spin.setRange(1.0, 100.0)
        self._thresh_spin.setDecimals(1)
        self._thresh_spin.setSingleStep(0.5)
        self._thresh_spin.setValue(
            float(self._settings.get('threshold', 10.0)))
        self._thresh_spin.setFixedWidth(70)
        self._thresh_spin.setToolTip(
            'Modified Z-score threshold.\n'
            'Lower = more sensitive (more rays flagged).\n'
            'Higher = less sensitive (only strong rays).\n'
            'Typical range: 5–20.')
        r1.addWidget(self._thresh_spin)
        r1.addStretch()
        gl.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel('Extra points to replace, each side:'))
        self._replace_window_spin = QSpinBox()
        self._replace_window_spin.setRange(0, 10)
        self._replace_window_spin.setValue(
            int(self._settings.get('replace_window', 1)))
        self._replace_window_spin.setFixedWidth(60)
        self._replace_window_spin.setKeyboardTracking(False)
        self._replace_window_spin.setToolTip(
            'The flagged point itself is ALWAYS replaced — this setting '
            'only controls how many EXTRA points on each side also get '
            'replaced along with it.\n'
            'A cosmic ray\'s shoulders are often still visibly elevated '
            'without being anomalous enough to be individually flagged, '
            'leaving a small remnant right where the ray was if only the '
            'exact flagged point is corrected.\n'
            '0 = replace only the flagged point(s), no extra buffer on '
            'either side (can leave shoulder remnants).\n'
            '1-2 (recommended) = also smooth over those shoulders. '
            'Default: 1.'
        )
        self._replace_window_spin.valueChanged.connect(self._on_replace_window_changed)
        r2.addWidget(self._replace_window_spin)
        r2.addStretch()
        gl.addLayout(r2)

        detect_btn = QPushButton('Detect cosmic rays')
        detect_btn.clicked.connect(self._detect)
        gl.addWidget(detect_btn)

        self._status_label = QLabel('')
        self._status_label.setStyleSheet('font-size:8pt; color:#555;')
        self._status_label.setWordWrap(True)
        gl.addWidget(self._status_label)

        self._few_warn = QLabel(
            '⚠  Fewer than 30 spectra selected. Cross-spectrum detection '
            'is less reliable with small groups. Consider using '
            'single-spectrum Spike Removal instead.')
        self._few_warn.setStyleSheet(
            'background:#FFF8E1; color:#E65100; padding:6px; '
            'border-radius:3px; font-size:8pt;')
        self._few_warn.setWordWrap(True)
        self._few_warn.setVisible(len(self.spectra) < 30)
        gl.addWidget(self._few_warn)
        layout.addWidget(grp)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        help_btn = QPushButton('Help')
        help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(help_btn)
        btn_row.addStretch()

        # Apply / Add as New commit directly via commit_callback — there's
        # no separate Run step in the main window for this operation
        # anymore (see OperationsController.commit_cosmic_ray_removal).
        self.apply_button = QPushButton('Apply')
        self.apply_button.setToolTip(
            'Replace the selected spectra with their cosmic-ray-corrected result.'
        )
        self.apply_button.setStyleSheet(
            'QPushButton { background-color:#2E7D32; color:white; '
            'font-weight:bold; padding:5px 16px; border-radius:4px; }'
            'QPushButton:hover { background-color:#1B5E20; }'
        )
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        btn_row.addWidget(self.apply_button)

        self.add_as_new_button = QPushButton('Add as New')
        self.add_as_new_button.setToolTip(
            'Keep the original spectra unchanged and add the cosmic-ray-corrected '
            'results to the list under new names.'
        )
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        btn_row.addWidget(self.add_as_new_button)

        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        return w

    def _build_right(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tabs = QTabWidget()
        self._tabs.tabBar().setExpanding(False)
        # Tabs were getting visually clipped instead of either fitting or
        # scrolling — give each tab enough width for its longest label, and
        # fall back to scroll arrows rather than silently cropping text if
        # the dialog is narrower than that.
        self._tabs.setUsesScrollButtons(True)
        self._tabs.tabBar().setElideMode(Qt.ElideNone)
        self._tabs.setStyleSheet(
            "QTabBar::tab { min-width: 120px; padding: 6px 10px; }"
        )

        # Heatmap tab
        hw = QWidget()
        hl = QVBoxLayout(hw)
        hl.setContentsMargins(0, 0, 0, 0)
        self._heatmap_canvas = _PlotCanvas(hw)
        hl.addWidget(NavigationToolbar(self._heatmap_canvas, hw))
        hl.addWidget(self._heatmap_canvas)
        self._tabs.addTab(hw, 'Outlier heatmap')

        # Summary table + Spectrum preview, combined into one tab so both
        # are visible side by side instead of having to switch back and
        # forth between two separate tabs.
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.setContentsMargins(4, 4, 4, 4)

        filter_row = QHBoxLayout()
        self._filter_cb = QCheckBox('Show only spectra with flagged points')
        self._filter_cb.setChecked(True)
        self._filter_cb.stateChanged.connect(self._apply_table_filter)
        filter_row.addWidget(self._filter_cb)
        filter_row.addStretch()
        sl.addLayout(filter_row)

        preview_mode_row = QHBoxLayout()
        preview_mode_row.addWidget(QLabel('Preview:'))
        self._preview_mode_group = QButtonGroup(self)
        # "Corrected only" — added because with the original spectrum also
        # shown, a sharp spike's extreme value stretches the whole plot's
        # y-axis to fit it, flattening everything else and making it hard
        # to judge how clean the corrected result actually looks. Dropping
        # the original lets the axis rescale to the corrected data's own
        # range instead.
        for i, lbl in enumerate(['Original only', 'Original + Corrected', 'Corrected only']):
            rb = QRadioButton(lbl)
            rb.setChecked(i == 0)
            self._preview_mode_group.addButton(rb, i)
            preview_mode_row.addWidget(rb)
        self._preview_mode_group.buttonClicked.connect(self._on_table_selection)
        preview_mode_row.addStretch()
        sl.addLayout(preview_mode_row)

        sp_splitter = QSplitter(Qt.Horizontal)

        table_widget = QWidget()
        tl = QVBoxLayout(table_widget)
        tl.setContentsMargins(0, 0, 0, 0)
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(
            ['Spectrum', 'Flagged points', 'x positions'])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Display-only "shorten names" — paint-only delegate, so
        # item.text() (what the lookups in _apply_table_filter and
        # _on_table_selection read) always stays the full/original label.
        self._table.setItemDelegateForColumn(
            0, make_display_text_delegate(self._display_labels_map, parent=self._table))
        self._table.itemSelectionChanged.connect(self._on_table_selection)
        tl.addWidget(self._table)
        sp_splitter.addWidget(table_widget)

        preview_widget = QWidget()
        pvl = QVBoxLayout(preview_widget)
        pvl.setContentsMargins(0, 0, 0, 0)
        self._preview_canvas = _PlotCanvas(preview_widget)
        pvl.addWidget(NavigationToolbar(self._preview_canvas, preview_widget))
        pvl.addWidget(self._preview_canvas)
        sp_splitter.addWidget(preview_widget)

        sp_splitter.setStretchFactor(0, 1)
        sp_splitter.setStretchFactor(1, 1)
        sp_splitter.setSizes([420, 420])
        sl.addWidget(sp_splitter)

        self._tabs.addTab(sw, 'Summary && Preview')
        self._tabs.setCurrentWidget(sw)

        # Own, independent "Shorten names" toggle for this dialog — feeds
        # both the heatmap's y-tick labels and the Spectrum column's
        # paint-only delegate via the shared _display_labels_map() below.
        # Sits above the tabs (rather than inside the Summary tab's own
        # filter_row) since it applies to the Heatmap tab too.
        shorten_row = QHBoxLayout()
        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)
        shorten_row.addWidget(self.checkBox_shorten_names)
        shorten_row.addStretch()
        layout.addLayout(shorten_row)

        layout.addWidget(self._tabs)
        return w

    # ------------------------------------------------------------------ #
    # Detection                                                            #
    # ------------------------------------------------------------------ #

    def _detect(self, *_):
        thresh = self._thresh_spin.value()

        if len(self.spectra) < 2:
            self._status_label.setText(
                '⚠  Need at least 2 spectra.')
            self._status_label.setStyleSheet('font-size:8pt; color:#C62828;')
            return

        # Warn if too few spectra for reliable detection
        if len(self.spectra) < 30:
            self._few_warn.setVisible(True)
        else:
            self._few_warn.setVisible(False)

        self._flagged, error = self.controller.detect(self.spectra, threshold=thresh)
        if error:
            # Most commonly an axis mismatch — refused rather than
            # silently resampled (see CosmicRayManager._build_matrix).
            # Shown right here instead of raising, so a bad selection
            # doesn't crash the dialog — the user can adjust their
            # selection and try again without losing anything.
            self._status_label.setText(f'⚠  {error}')
            self._status_label.setStyleSheet('font-size:8pt; color:#C62828;')
            self._refresh_heatmap()
            self._table.setRowCount(0)
            return

        summary = self.controller.get_summary(self.spectra)

        n_rays  = summary['total_flagged_points']
        n_spec  = summary['spectra_with_rays']
        self._status_label.setText(
            f'{n_rays} flagged points in {n_spec} / '
            f'{len(self.spectra)} spectra  (threshold Z={thresh:.1f})'
        )
        color = '#2E7D32' if n_rays > 0 else '#555'
        self._status_label.setStyleSheet(f'font-size:8pt; color:{color};')
        self._refresh_heatmap()
        self._refresh_table(summary)

        # Select the first flagged spectrum so the preview shows something
        # useful immediately instead of staying blank until the user picks
        # a row themselves. With "show only flagged" checked by default,
        # the first VISIBLE row already IS the first flagged spectrum —
        # but search for the first row with points > 0 directly rather
        # than assuming the filter is on, so this still does the right
        # thing if the user has unchecked it.
        self._table.clearSelection()
        for row in range(self._table.rowCount()):
            lbl = self._table.item(row, 0).text() if self._table.item(row, 0) else ''
            if len(self._flagged.get(lbl, [])) > 0:
                self._table.selectRow(row)
                self._table.setFocus()
                break

    # ------------------------------------------------------------------ #
    # Heatmap of outlier Z-scores                                          #
    # ------------------------------------------------------------------ #

    def _refresh_heatmap(self):
        ax = self._heatmap_canvas.ax
        ax.clear()

        # fig.colorbar(im, ax=ax) permanently shrinks ax to make room for
        # itself, and that shrink is relative to ax's CURRENT size — so
        # calling it again on every re-detection compounds, making the
        # plot narrower each time. A dedicated axes (created once, reused
        # afterward) avoids touching ax's size at all.
        if self._cbar_ax is None:
            divider = make_axes_locatable(ax)
            self._cbar_ax = divider.append_axes('right', size='3%', pad=0.3)
        else:
            self._cbar_ax.clear()

        mgr = self.controller.manager
        # mgr._matrix/_labels are only ever updated on a SUCCESSFUL
        # detect() (see CosmicRayManager._build_matrix — it raises
        # AxisMismatchError mid-build, before ever touching self._matrix,
        # so a refused detect() leaves them exactly as they were after the
        # last successful one). If the current selection doesn't match
        # those cached labels — either nothing has been detected yet, or
        # the most recent detect() was refused and self.spectra has since
        # changed (different count and/or different spectra) — mgr._matrix
        # no longer corresponds to self.spectra at all. Plotting it anyway
        # used to crash matplotlib outright (extent/contour built from
        # len(self.spectra) against a matrix with a different row count —
        # "Length of y (51) must match number of rows in z (11)"), and even
        # with matching shapes it would silently show a stale heatmap for
        # a completely different spectra selection. Bail out the same way
        # as the "nothing detected yet" case in either situation.
        current_labels = [s['label'] for s in self.spectra]
        if not self.spectra or mgr._matrix is None or mgr._labels != current_labels:
            self._heatmap_canvas.draw_tight()
            return

        # Reuse the matrix CosmicRayManager._build_matrix() already
        # computed during detect() (see cosmic_ray_manager.py) rather than
        # rebuilding it here independently — this used to be a THIRD,
        # separate copy of the "align spectra onto a common x-grid" logic
        # (with the same np.array_equal exact-match issue the manager
        # itself used to have), which could silently drift out of sync
        # with the manager's own version.
        x_ref, matrix = mgr._x_ref, mgr._matrix

        med     = np.median(matrix, axis=0)
        mad     = np.median(np.abs(matrix - med), axis=0)
        safe_mad = np.where(mad < 1e-12, 1.0, mad)
        Z_abs   = np.abs(0.6745 * (matrix - med) / safe_mad)

        n_spec = len(self.spectra)
        x_min, x_max = float(x_ref[0]), float(x_ref[-1])

        im = ax.imshow(
            Z_abs,
            aspect='auto',
            origin='upper',
            extent=[x_min, x_max, n_spec - 0.5, -0.5],
            cmap='hot_r',
            interpolation='nearest',
            vmin=0,
            vmax=max(float(self._thresh_spin.value()) * 1.5, 1),
        )
        # Threshold contour line
        thresh = self._thresh_spin.value()
        ax.contour(
            np.linspace(x_min, x_max, Z_abs.shape[1]),
            np.arange(n_spec),
            Z_abs,
            levels=[thresh],
            colors=['cyan'],
            linewidths=0.5,
            alpha=0.7,
        )

        self._colorbar = self._heatmap_canvas.fig.colorbar(
            im, cax=self._cbar_ax, label='|Modified Z-score|')

        # Y-axis labels
        display_map = self._display_labels_map()
        if n_spec <= 30:
            ax.set_yticks(range(n_spec))
            ax.set_yticklabels(
                [display_map.get(s.get('label', str(i+1)), s.get('label', str(i+1)))[-30:]
                 for i, s in enumerate(self.spectra)],
                fontsize=max(5, 8 - max(0, n_spec - 10))
            )
        elif n_spec <= 200:
            step = max(1, n_spec // 20)
            ticks = list(range(0, n_spec, step))
            ax.set_yticks(ticks)
            ax.set_yticklabels(
                [display_map.get(self.spectra[t].get('label', str(t+1)),
                                  self.spectra[t].get('label', str(t+1)))[-20:]
                 for t in ticks],
                fontsize=7)
        else:
            step = max(1, n_spec // 10)
            ticks = list(range(0, n_spec, step))
            ax.set_yticks(ticks)
            ax.set_yticklabels([str(t+1) for t in ticks], fontsize=7)

        ax.set_xlabel('x', fontsize=10)
        ax.set_ylabel('Spectrum', fontsize=10)
        ax.set_title(
            f'|Z-score| heatmap  —  threshold={thresh:.1f}  '
            f'(cyan contour = threshold boundary)',
            fontsize=10
        )
        self._heatmap_canvas.draw_tight()

    # ------------------------------------------------------------------ #
    # Summary table                                                        #
    # ------------------------------------------------------------------ #

    def _refresh_table(self, summary):
        self._table.setRowCount(0)
        for lbl, n in summary['details'].items():
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(lbl))
            cnt_item = QTableWidgetItem(str(n))
            cnt_item.setTextAlignment(Qt.AlignCenter)
            if n > 0:
                cnt_item.setForeground(QColor('#C62828'))
            self._table.setItem(row, 1, cnt_item)
            # Show first few x positions
            indices = self._flagged.get(lbl, [])
            x_ref = np.asarray(self.spectra[0]['x_scale'], dtype=float)
            x_vals = [f'{x_ref[j]:.1f}' for j in indices[:10]]
            suffix = '…' if len(indices) > 10 else ''
            self._table.setItem(row, 2,
                QTableWidgetItem(', '.join(x_vals) + suffix))

        # Re-apply whatever the filter checkbox currently says — its own
        # stateChanged signal only fires when the CHECKBOX changes, not
        # when the table's rows get rebuilt underneath it, so without this
        # a checkbox that starts checked (or was left checked from a
        # previous detection) would show every row again after each
        # re-detection until toggled off and back on.
        self._apply_table_filter()

    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # Table interactions                                                   #
    # ------------------------------------------------------------------ #

    def _apply_table_filter(self, *_):
        """Show/hide rows based on filter checkbox."""
        show_all = not self._filter_cb.isChecked()
        for row in range(self._table.rowCount()):
            lbl = self._table.item(row, 0).text()
            n   = len(self._flagged.get(lbl, []))
            self._table.setRowHidden(row, not show_all and n == 0)

    def _on_table_selection(self):
        """Show spectrum with flagged points highlighted when row clicked."""
        rows = self._table.selectedItems()
        if not rows:
            return
        row  = self._table.currentRow()
        lbl  = self._table.item(row, 0).text() if self._table.item(row, 0) else ''
        spec = next((s for s in self.spectra if s['label'] == lbl), None)
        if spec is None:
            return

        ax = self._preview_canvas.ax
        ax.clear()
        import numpy as np
        x = np.asarray(spec['x_scale'], dtype=float)
        y = np.asarray(spec['y_scale'], dtype=float)
        indices = self._flagged.get(lbl, [])

        # 0 = Original only, 1 = Original + Corrected, 2 = Corrected only.
        # "Corrected only" exists because with the original also plotted,
        # a sharp spike's extreme value stretches the whole y-axis to fit
        # it — matplotlib autoscales to whatever's actually drawn — which
        # flattens the rest of the spectrum and makes it hard to judge how
        # clean the corrected result actually looks. Dropping the original
        # here lets the axis rescale to the corrected data's own range.
        mode = self._preview_mode_group.checkedId()
        show_original  = mode in (0, 1)
        show_corrected = mode in (1, 2)

        if show_original:
            ax.plot(x, y, color='#1565C0', lw=1.0, label='Original', zorder=2)

        x_ref = np.asarray(self.spectra[0]['x_scale'], dtype=float)
        if indices and show_original:
            # On the original: red, since these points ARE currently
            # anomalous.
            flagged_x = [x_ref[j] for j in indices if j < len(x_ref)]
            flagged_y = np.interp(flagged_x, x, y)
            ax.scatter(flagged_x, flagged_y, color='#C62828',
                       s=40, zorder=4, label=f'{len(indices)} flagged points')
            for fx in flagged_x:
                ax.axvline(fx, color='#C62828', lw=0.5, alpha=0.4)

        # Corrected result — what apply() would actually produce for this
        # spectrum with the current Replace window setting, without
        # applying anything. Lets you check for remnants (see Replace
        # window's tooltip) and adjust before committing, instead of only
        # finding out after Apply.
        if show_corrected and indices:
            window = self._replace_window_spin.value()
            preview = self.controller.manager.preview_correction(lbl, replace_window=window)
            if preview is not None:
                _, y_original, y_corrected, _ = preview
                corrected_label = 'Corrected preview' if show_original else 'Corrected result'
                ax.plot(x_ref, y_corrected, color='#2E7D32', lw=1.2,
                        linestyle='--' if show_original else '-',
                        zorder=3, label=corrected_label)
                if not show_original:
                    # Lighter markers than the "still anomalous" red used
                    # on the original — these positions were corrected,
                    # not currently flagged as a problem.
                    corrected_x = [x_ref[j] for j in indices if j < len(x_ref)]
                    corrected_y = [y_corrected[j] for j in indices if j < len(x_ref)]
                    ax.scatter(corrected_x, corrected_y, color='#757575',
                               s=25, zorder=4, marker='x',
                               label=f'{len(indices)} corrected position(s)')

        ax.set_xlabel('x', fontsize=10)
        ax.set_ylabel('Intensity', fontsize=10)
        ax.set_title(lbl[-60:], fontsize=10)
        ax.legend(fontsize=8)
        ax.grid(True, linestyle='--', alpha=0.35)
        self._preview_canvas.draw_tight()

    def _on_replace_window_changed(self, *_):
        """Refresh the corrected-result preview (if shown) when Replace
        window changes — cheap: replace_window doesn't affect detection at
        all, only which pixels get replaced, so this only needs to redraw
        the currently-selected row's preview, not re-run detection."""
        if self._preview_mode_group.checkedId() in (1, 2):
            self._on_table_selection()

    # ------------------------------------------------------------------ #
    # Apply                                                               #
    # ------------------------------------------------------------------ #

    def _on_commit_clicked(self, add_as_new):
        """Apply or Add as New — commits directly via commit_callback. No
        separate Run step: feedback (success or failure) is shown right
        here next to the buttons that triggered it, instead of in a
        disconnected main-window message box. The dialog closes itself
        once the commit succeeds.
        """
        from PyQt5.QtWidgets import QMessageBox

        if self.controller.manager._matrix is None:
            return

        if self.commit_callback is None:
            QMessageBox.critical(
                self, 'Not Available',
                'This dialog was opened without a way to apply changes. '
                'Please reopen it via Parameters.'
            )
            return

        settings = self.get_settings()

        action = ('add the cosmic-ray-corrected result as new spectra' if add_as_new
                  else 'replace the selected spectra with their cosmic-ray-corrected result')
        confirm = QMessageBox.question(
            self, 'Confirm', f'{action[0].upper() + action[1:]}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        # commit_callback (OperationsController.commit_cosmic_ray_removal)
        # does real GUI work internally — rebuilding the main spectra list,
        # replotting — so it can't safely be moved to a background thread
        # without a larger restructuring (Qt widgets aren't thread-safe).
        # This is a lighter-weight fix: an indeterminate progress dialog,
        # shown and painted BEFORE the blocking call runs, so a commit
        # touching many affected spectra doesn't just leave the UI looking
        # frozen with no feedback while it works.
        progress = QProgressDialog(
            'Applying cosmic ray removal…', None, 0, 0, self)
        progress.setWindowTitle('Please wait')
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)  # nothing to safely cancel mid-commit
        progress.show()
        QApplication.processEvents()

        try:
            success, message = self.commit_callback(settings, add_as_new, list(self.spectra))
        finally:
            progress.close()

        if success:
            QMessageBox.information(self, 'Done', message)
            self.accept()
        else:
            QMessageBox.warning(self, 'Could Not Apply', message)

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def _show_help(self):
        try:
            from src.help.cosmic_ray_help import (
                get_cosmic_ray_help_content, get_cosmic_ray_help_title)
            from src.help.help_window import show_help_window
            show_help_window(self, get_cosmic_ray_help_title(),
                             get_cosmic_ray_help_content())
        except Exception:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Help',
                                    'Help documentation is not available.')

    def get_settings(self):
        return {
            'threshold': self._thresh_spin.value(),
            'replace_window': self._replace_window_spin.value(),
        }


# ======================================================================
# Plot canvas
# ======================================================================

class _PlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(tight_layout=True)
        self.ax  = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fig.patch.set_facecolor('#ffffff')
        self.ax.set_facecolor('#ffffff')

    def draw_tight(self):
        try:
            self.fig.tight_layout()
        except Exception:
            pass
        self.draw_idle()

    def resizeEvent(self, event):
        """Keep the layout (and the colorbar's proportions, for the
        heatmap canvas) correct as the window is resized. tight_layout()
        is a one-time calculation — it's never automatically reapplied on
        resize unless something explicitly does it, which is why the plot
        used to only fill the window correctly right after a manual
        redraw (e.g. clicking Detect cosmic rays), never just from
        resizing the dialog itself.
        """
        super().resizeEvent(event)
        try:
            self.fig.tight_layout()
        except Exception:
            pass
        self.draw_idle()
