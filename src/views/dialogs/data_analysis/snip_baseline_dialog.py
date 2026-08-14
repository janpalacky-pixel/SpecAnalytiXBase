# src/views/dialogs/data_analysis/snip_baseline_dialog.py
"""
SNIP Baseline Correction dialog.

Left panel  — settings + spectrum list
Right panel — live preview (original / baseline / corrected)
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QSpinBox, QCheckBox, QLabel, QPushButton, QListWidget,
    QSizePolicy, QSplitter, QWidget, QButtonGroup, QRadioButton,
)
from PyQt5.QtCore import Qt, QTimer

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import (
    make_shortened_name_delegate, compute_distinguishing_labels, make_shorten_names_checkbox,
)

logger = get_logger(__name__)


class SNIPBaselineDialog(QDialog):

    def __init__(self, parent=None, selected_spectra=None, current_settings=None, commit_callback=None,
                 main_controller=None):
        super().__init__(parent)
        self.setWindowTitle('SNIP Baseline Correction')
        self.setMinimumSize(980, 620)
        self.resize(1200, 760)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        self._main_controller = main_controller
        self.selected_spectra = list(selected_spectra or [])
        self._settings        = dict(current_settings or {})
        self._preview_idx     = 0
        # Bound method (OperationsController.commit_snip_baseline) passed in
        # by whatever opened this dialog, so Apply / Add as New can commit
        # the result directly, without a separate Run step.
        self.commit_callback  = commit_callback

        # 250 ms debounce so spinners don't redraw on every tick
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._refresh)

        self._init_complete = False
        self._build_ui()
        self._populate_list()
        self._populate_from_settings(self._settings)
        self._init_complete = True
        self._refresh()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QHBoxLayout(self)
        hsplit = QSplitter(Qt.Horizontal)
        hsplit.addWidget(self._build_left())
        hsplit.addWidget(self._build_right())
        hsplit.setStretchFactor(0, 0)
        hsplit.setStretchFactor(1, 1)
        hsplit.setSizes([320, 880])
        root.addWidget(hsplit)

    # ── Left panel ──────────────────────────────────────────────────────

    def _build_left(self):
        w = QWidget()
        w.setFixedWidth(320)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        layout.addWidget(self._build_spectra_group())
        layout.addWidget(self._build_params_group())
        layout.addStretch()

        btn_row = QHBoxLayout()
        help_btn = QPushButton('Help')
        help_btn.setAutoDefault(False)
        help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(help_btn)

        btn_row.addStretch()

        # Apply / Add as New / Close commit directly via commit_callback —
        # there's no separate Run step in the main window for this
        # operation anymore (see OperationsController.commit_snip_baseline).
        self.apply_button = QPushButton('Apply')
        self.apply_button.setToolTip(
            'Replace the selected spectra with their baseline-corrected result.'
        )
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        btn_row.addWidget(self.apply_button)

        self.add_as_new_button = QPushButton('Add as New')
        self.add_as_new_button.setToolTip(
            'Keep the original spectra unchanged and add the baseline-corrected '
            'results to the list under new names.'
        )
        self.add_as_new_button.setAutoDefault(False)
        self.add_as_new_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=True))
        btn_row.addWidget(self.add_as_new_button)

        self.close_button = QPushButton('Close')
        self.close_button.setAutoDefault(False)
        self.close_button.clicked.connect(self.reject)
        btn_row.addWidget(self.close_button)
        layout.addLayout(btn_row)
        return w

    def _build_spectra_group(self):
        group = QGroupBox('Selected spectra')
        layout = QVBoxLayout(group)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel('Navigator:'))
        self._prev_btn = QPushButton('◀')
        self._prev_btn.setMaximumWidth(28)
        self._prev_btn.clicked.connect(self._prev)
        hdr.addWidget(self._prev_btn)
        self._nav_lbl = QLabel('1 / 1')
        self._nav_lbl.setAlignment(Qt.AlignCenter)
        self._nav_lbl.setMinimumWidth(50)
        hdr.addWidget(self._nav_lbl)
        self._next_btn = QPushButton('▶')
        self._next_btn.setMaximumWidth(28)
        self._next_btn.clicked.connect(self._next)
        hdr.addWidget(self._next_btn)
        layout.addLayout(hdr)

        self._list = QListWidget()
        self._list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        # Display-only "shorten names" — selection is positional
        # (currentRowChanged), never by matching displayed text.
        self._list.setItemDelegate(
            make_shortened_name_delegate(self._list, self._shorten_names_enabled)
        )
        self._list.currentRowChanged.connect(self._on_list_row_changed)
        layout.addWidget(self._list)

        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(self._on_shorten_names_toggled)
        layout.addWidget(self.checkBox_shorten_names)
        return group

    def _build_params_group(self):
        group = QGroupBox('SNIP parameters')
        form = QFormLayout(group)

        self._n_iter_spin = QSpinBox()
        self._n_iter_spin.setRange(1, 1000)
        self._n_iter_spin.setValue(100)
        self._n_iter_spin.setToolTip(
            'Number of clipping iterations.\n'
            'More iterations → wider, smoother baseline.\n'
            'Typical range: 20–200. Default: 100.'
        )
        self._n_iter_spin.valueChanged.connect(self._schedule)
        form.addRow('Iterations:', self._n_iter_spin)

        self._decreasing_cb = QCheckBox('Decreasing window order')
        self._decreasing_cb.setChecked(True)
        self._decreasing_cb.setToolTip(
            'Process windows from large to small (recommended).\n'
            'Gives a smoother, more conservative baseline.'
        )
        self._decreasing_cb.stateChanged.connect(self._schedule)
        form.addRow(self._decreasing_cb)

        self._transform_cb = QCheckBox('Variance-stabilising transform (√)')
        self._transform_cb.setChecked(True)
        self._transform_cb.setToolTip(
            'Apply sqrt(y + 3/8) before clipping and invert afterwards.\n'
            'Recommended for shot-noise-limited spectra (Raman, XRF).\n'
            'Uncheck for already-linearised or log-scale data.'
        )
        self._transform_cb.stateChanged.connect(self._schedule)
        form.addRow(self._transform_cb)

        self._smooth_spin = QSpinBox()
        self._smooth_spin.setRange(0, 20)
        self._smooth_spin.setValue(0)
        self._smooth_spin.setSpecialValueText('off')
        self._smooth_spin.setToolTip(
            'Half-window for optional moving-average pre-smoothing.\n'
            '0 = off (recommended). Increase only if the signal has\n'
            'very high frequency noise before the baseline is estimated.'
        )
        self._smooth_spin.valueChanged.connect(self._schedule)
        form.addRow('Pre-smooth half-window:', self._smooth_spin)

        return group

    # ── Right panel ─────────────────────────────────────────────────────

    def _build_right(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # View mode toggle
        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel('View:'))
        self._view_mode = QButtonGroup(self)
        for i, lbl in enumerate(['Subplots', 'Overlay']):
            rb = QRadioButton(lbl)
            rb.setChecked(i == 0)
            self._view_mode.addButton(rb, i)
            ctrl_row.addWidget(rb)
        self._view_mode.buttonClicked.connect(self._schedule)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        self._canvas = _PreviewCanvas(w)
        layout.addWidget(NavigationToolbar(self._canvas, w))
        layout.addWidget(self._canvas)
        return w

    # ------------------------------------------------------------------ #
    # List & navigator                                                     #
    # ------------------------------------------------------------------ #

    def _populate_list(self):
        self._list.blockSignals(True)
        self._list.clear()
        for s in self.selected_spectra:
            self._list.addItem(s['label'])
        self._list.blockSignals(False)
        if self.selected_spectra:
            self._list.setCurrentRow(0)

    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _on_shorten_names_toggled(self, *_):
        self._list.viewport().update()
        self._schedule()

    def _display_label(self, label):
        """Display-only "shorten names" lookup (see label_shortening.py),
        grouped across self.selected_spectra."""
        if not self._shorten_names_enabled():
            return label
        all_labels = [s.get('label', '') for s in self.selected_spectra]
        if len(all_labels) < 2:
            return label
        return compute_distinguishing_labels(all_labels).get(label, label)

    def _on_list_row_changed(self, row):
        if row >= 0:
            self._preview_idx = row
            self._update_nav()
            if self._init_complete:
                self._schedule()

    def _prev(self):
        if self._preview_idx > 0:
            self._preview_idx -= 1
            self._list.setCurrentRow(self._preview_idx)

    def _next(self):
        if self._preview_idx < len(self.selected_spectra) - 1:
            self._preview_idx += 1
            self._list.setCurrentRow(self._preview_idx)

    def _update_nav(self):
        n = len(self.selected_spectra)
        i = self._preview_idx
        self._nav_lbl.setText(f'{i + 1} / {n}')
        self._prev_btn.setEnabled(i > 0)
        self._next_btn.setEnabled(i < n - 1)

    # ------------------------------------------------------------------ #
    # Preview                                                              #
    # ------------------------------------------------------------------ #

    def _schedule(self, *_):
        if self._init_complete:
            self._timer.start()

    def _refresh(self):
        if not self.selected_spectra:
            return
        idx = max(0, min(self._preview_idx, len(self.selected_spectra) - 1))
        s   = self.selected_spectra[idx]
        x   = np.asarray(s.get('x_scale', []), dtype=float)
        y   = np.asarray(s.get('y_scale', []), dtype=float)
        if len(x) < 3:
            return

        settings = self.get_settings()
        from src.modules.data_analysis.snip_baseline_manager import SNIPBaselineManager
        mgr      = SNIPBaselineManager()
        baseline = mgr.compute_baseline(y, settings)

        overlay = (self._view_mode.checkedId() == 1)
        self._canvas.plot(x, y, baseline, self._display_label(s['label']), overlay=overlay)
        self._update_nav()

    # ------------------------------------------------------------------ #
    # Settings I/O                                                         #
    # ------------------------------------------------------------------ #

    def _populate_from_settings(self, s):
        if 'n_iter'        in s: self._n_iter_spin.setValue(int(s['n_iter']))
        if 'decreasing'    in s: self._decreasing_cb.setChecked(bool(s['decreasing']))
        if 'transform'     in s: self._transform_cb.setChecked(bool(s['transform']))
        if 'smooth_window' in s: self._smooth_spin.setValue(int(s['smooth_window']))

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
                self, 'Not Available',
                'This dialog was opened without a way to apply changes. '
                'Please reopen it via Parameters.'
            )
            return

        settings = self.get_settings()

        action = ('add the baseline-corrected result as new spectra' if add_as_new
                  else 'replace the selected spectra with their baseline-corrected result')
        confirm = QMessageBox.question(
            self, 'Confirm', f'{action[0].upper() + action[1:]}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(settings, add_as_new, list(self.selected_spectra))
        if success:
            QMessageBox.information(self, 'Done', message)
            self.accept()
        else:
            QMessageBox.warning(self, 'Could Not Apply', message)

    def get_settings(self) -> dict:
        return {
            'n_iter':        self._n_iter_spin.value(),
            'decreasing':    self._decreasing_cb.isChecked(),
            'transform':     self._transform_cb.isChecked(),
            'smooth_window': self._smooth_spin.value(),
        }

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def _show_help(self):
        try:
            from src.help.snip_baseline_help import (
                get_snip_baseline_help_content,
                get_snip_baseline_help_title,
            )
            from src.help.help_window import show_help_window
            show_help_window(self, get_snip_baseline_help_title(),
                             get_snip_baseline_help_content())
        except Exception:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Help',
                                    'Help documentation is not available.')


# ======================================================================
# Preview canvas
# ======================================================================

class _PreviewCanvas(FigureCanvas):

    def __init__(self, parent=None):
        self._fig = Figure(tight_layout=True)
        super().__init__(self._fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fig.patch.set_facecolor('#f0f0f0')

    def plot(self, x, y, baseline, label, overlay=False):
        self._fig.clear()
        corrected = y - baseline

        if overlay:
            ax = self._fig.add_subplot(111)
            ax.set_facecolor('#ffffff')
            ax.plot(x, y,         color='#1565C0', lw=1.0, alpha=0.60,
                    label='Original')
            ax.plot(x, baseline,  color='#E65100', lw=1.5, ls='--',
                    label='Baseline (SNIP)')
            ax.plot(x, corrected, color='#2E7D32', lw=1.2,
                    label='Corrected')
            ax.set_xlabel('x', fontsize=9)
            ax.set_ylabel('Intensity', fontsize=9)
            ax.set_title(f'SNIP baseline — {label}', fontsize=10)
            ax.grid(True, linestyle='--', alpha=0.4)
            ax.legend(fontsize=8, loc='best')
        else:
            ax_top = self._fig.add_subplot(211)
            ax_bot = self._fig.add_subplot(212, sharex=ax_top)
            for ax in (ax_top, ax_bot):
                ax.set_facecolor('#ffffff')
            ax_top.plot(x, y,        color='#1565C0', lw=1.0, label='Original')
            ax_top.plot(x, baseline, color='#E65100', lw=1.5, ls='--',
                        label='Baseline')
            ax_top.set_title(f'Original + baseline — {label}', fontsize=10)
            ax_top.set_ylabel('Intensity', fontsize=9)
            ax_top.legend(fontsize=8, loc='best')
            ax_top.grid(True, linestyle='--', alpha=0.4)

            ax_bot.plot(x, corrected, color='#2E7D32', lw=1.2)
            ax_bot.set_title('Corrected', fontsize=10)
            ax_bot.set_xlabel('x', fontsize=9)
            ax_bot.set_ylabel('Intensity', fontsize=9)
            ax_bot.grid(True, linestyle='--', alpha=0.4)

        self._fig.tight_layout()
        self.draw_idle()
