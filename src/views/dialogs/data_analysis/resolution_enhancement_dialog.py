# src/views/dialogs/data_analysis/resolution_enhancement_dialog.py
"""
Spectral Resolution Enhancement dialog (Wiener deconvolution).

Shows a live preview comparing original and enhanced spectrum.
"""

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QDoubleSpinBox, QSizePolicy,
    QSplitter, QWidget, QComboBox, QCheckBox,
)
from PyQt5.QtCore import Qt, QTimer

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
from src.modules.utils.label_shortening import make_shortened_name_delegate, make_shorten_names_checkbox
logger = get_logger(__name__)


class ResolutionEnhancementDialog(QDialog):

    def __init__(self, parent=None, spectra=None, current_settings=None,
                 controller=None, commit_callback=None):
        super().__init__(parent)
        self.setWindowTitle('Spectral Resolution Enhancement (Wiener deconvolution)')
        self.setMinimumSize(900, 560)
        self.resize(1100, 660)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)

        self.spectra        = list(spectra or [])
        self._settings      = dict(current_settings or {})
        # ResolutionEnhancementController — owns the actual
        # ResolutionEnhancementManager instance, shared with the commit
        # path (OperationsController.commit_resolution_enhancement) so
        # the preview shown here and the enhancement actually applied are
        # provably the same computation. Falls back to a private
        # controller if none is given (e.g. direct/standalone use).
        if controller is not None and hasattr(controller, 'preview'):
            self.controller = controller
        else:
            from src.controllers.data_analysis.resolution_enhancement_controller import (
                ResolutionEnhancementController)
            self.controller = ResolutionEnhancementController(None)
        self._preview_idx   = 0
        # Bound method (OperationsController.commit_resolution_enhancement)
        # passed in by whatever opened this dialog, so Apply / Add as New
        # can commit the result directly, without a separate Run step.
        self.commit_callback = commit_callback

        # Debounce timer
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._refresh_preview)

        self._build_ui()
        self._restore_settings()
        self._refresh_preview()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 800])
        root.addWidget(splitter)

    def _build_left(self):
        w = QWidget()
        w.setFixedWidth(300)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Settings
        grp = QGroupBox('Deconvolution settings')
        gl  = QVBoxLayout(grp)

        # IRF sigma
        r1 = QHBoxLayout()
        r1.addWidget(QLabel('IRF width (σ, x-units):'))
        self._sigma_spin = QDoubleSpinBox()
        self._sigma_spin.setRange(0.1, 100.0)
        self._sigma_spin.setDecimals(2)
        self._sigma_spin.setSingleStep(0.5)
        self._sigma_spin.setValue(float(self._settings.get('irf_sigma', 2.0)))
        self._sigma_spin.setFixedWidth(80)
        self._sigma_spin.setToolTip(
            'Gaussian IRF half-width in x-axis units (e.g. cm⁻¹).\n'
            'Typical values:\n'
            '  High-res Raman: 0.5–2 cm⁻¹\n'
            '  Standard Raman: 2–5 cm⁻¹\n'
            '  Low-res / FTIR: 4–16 cm⁻¹\n\n'
            'Estimate from a known sharp peak (e.g. Si at 520 cm⁻¹):\n'
            'measure its FWHM, then σ = FWHM / 2.355'
        )
        self._sigma_spin.valueChanged.connect(self._schedule)
        r1.addWidget(self._sigma_spin)
        r1.addStretch()
        gl.addLayout(r1)

        # SNR
        r2 = QHBoxLayout()
        r2.addWidget(QLabel('SNR (regularisation):'))
        self._snr_spin = QDoubleSpinBox()
        self._snr_spin.setRange(1.0, 10000.0)
        self._snr_spin.setDecimals(0)
        self._snr_spin.setSingleStep(10.0)
        self._snr_spin.setValue(float(self._settings.get('snr', 100.0)))
        self._snr_spin.setFixedWidth(80)
        self._snr_spin.setToolTip(
            'Signal-to-noise ratio. Controls sharpening aggressiveness.\n'
            'Higher = more sharpening but more noise amplification.\n'
            'Lower  = smoother result.\n\n'
            'Typical range: 10 (noisy) – 1000 (clean spectrum).\n'
            'Start at 100 and adjust based on the preview.'
        )
        self._snr_spin.valueChanged.connect(self._schedule)
        r2.addWidget(self._snr_spin)
        r2.addStretch()
        gl.addLayout(r2)

        # IRF estimation helper
        est_btn = QPushButton('Estimate σ from peak width…')
        est_btn.setToolTip(
            'Enter the FWHM of a known sharp peak.\n'
            'σ will be set to FWHM / 2.355')
        est_btn.clicked.connect(self._estimate_sigma)
        gl.addWidget(est_btn)

        self._sigma_hint = QLabel('')
        self._sigma_hint.setStyleSheet('font-size:8pt; color:#1565C0;')
        self._sigma_hint.setWordWrap(True)
        gl.addWidget(self._sigma_hint)

        layout.addWidget(grp)

        # Preview spectrum selector — listbox uses all vertical space
        prev_grp = QGroupBox('Preview spectrum')
        pl = QVBoxLayout(prev_grp)
        pl.addWidget(QLabel('Click spectrum to preview:'))
        from PyQt5.QtWidgets import QListWidget as _QLW
        self._prev_list = _QLW()
        self._prev_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        for s in self.spectra:
            self._prev_list.addItem(s['label'])
        # Display-only "shorten names" — navigation is positional
        # (currentRowChanged), never by matching displayed text.
        self._prev_list.setItemDelegate(
            make_shortened_name_delegate(self._prev_list, self._shorten_names_enabled)
        )
        if self.spectra:
            self._prev_list.setCurrentRow(0)
        self._prev_list.currentRowChanged.connect(self._on_preview_changed)
        pl.addWidget(self._prev_list)

        self.checkBox_shorten_names = make_shorten_names_checkbox()
        self.checkBox_shorten_names.stateChanged.connect(
            lambda _: self._prev_list.viewport().update()
        )
        pl.addWidget(self.checkBox_shorten_names)

        self._show_diff_cb = QCheckBox('Show residual (original − enhanced)')
        self._show_diff_cb.setChecked(False)
        self._show_diff_cb.stateChanged.connect(self._schedule)
        pl.addWidget(self._show_diff_cb)
        layout.addWidget(prev_grp, stretch=1)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        help_btn = QPushButton('Help')
        help_btn.clicked.connect(self._show_help)
        btn_row.addWidget(help_btn)
        btn_row.addStretch()

        # Apply / Add as New commit directly via commit_callback — there's
        # no separate Run step in the main window for this operation
        # anymore (see OperationsController.commit_resolution_enhancement).
        self.apply_button = QPushButton('Apply')
        self.apply_button.setToolTip(
            'Replace the selected spectra with their resolution-enhanced result.'
        )
        self.apply_button.setStyleSheet(
            'QPushButton { background-color:#2E7D32; color:white; '
            'font-weight:bold; padding:5px 14px; border-radius:4px; }'
            'QPushButton:hover { background-color:#1B5E20; }'
        )
        self.apply_button.clicked.connect(lambda: self._on_commit_clicked(add_as_new=False))
        btn_row.addWidget(self.apply_button)

        self.add_as_new_button = QPushButton('Add as New')
        self.add_as_new_button.setToolTip(
            'Keep the original spectra unchanged and add the resolution-enhanced '
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
        self._canvas = _PlotCanvas(w)
        layout.addWidget(NavigationToolbar(self._canvas, w))
        layout.addWidget(self._canvas)
        return w

    # ------------------------------------------------------------------ #
    # Preview                                                              #
    # ------------------------------------------------------------------ #

    def _schedule(self, *_):
        self._timer.start()

    def _shorten_names_enabled(self):
        return self.checkBox_shorten_names.isChecked()

    def _on_preview_changed(self, row):
        if row >= 0:
            self._preview_idx = row
            self._refresh_preview()

    def _refresh_preview(self):
        if not self.spectra:
            return
        idx = min(self._preview_idx, len(self.spectra) - 1)
        s   = self.spectra[idx]
        x   = np.asarray(s['x_scale'], dtype=float)
        y   = np.asarray(s['y_scale'], dtype=float)

        sigma = self._sigma_spin.value()
        snr   = self._snr_spin.value()

        y_enh  = self.controller.preview(x, y, sigma, snr)

        # Clear figure completely to avoid overlay artifacts
        self._canvas.fig.clear()
        ax = self._canvas.fig.add_subplot(111)
        ax.set_facecolor('#ffffff')
        self._canvas.ax = ax
        ax.plot(x, y,     color='#555', lw=1.0, alpha=0.7,
                label='Original', zorder=2)
        ax.plot(x, y_enh, color='#C62828', lw=1.2,
                label=f'Enhanced (σ={sigma:.1f}, SNR={snr:.0f})', zorder=3)

        if self._show_diff_cb.isChecked():
            ax2 = ax.twinx()
            ax2.plot(x, y - y_enh, color='#1565C0', lw=0.8,
                     alpha=0.6, label='Residual')
            ax2.set_ylabel('Residual', fontsize=8, color='#1565C0')
            ax2.tick_params(axis='y', labelcolor='#1565C0')

        ax.set_xlabel('x', fontsize=10)
        ax.set_ylabel('Intensity', fontsize=10)
        ax.set_title(f'Resolution enhancement — {s["label"][-50:]}', fontsize=10)
        ax.legend(fontsize=8, loc='best', framealpha=0.7)
        ax.grid(True, linestyle='--', alpha=0.35)
        self._canvas.draw_tight()

    # ------------------------------------------------------------------ #
    # Sigma estimation                                                     #
    # ------------------------------------------------------------------ #

    def _estimate_sigma(self):
        from PyQt5.QtWidgets import QInputDialog
        fwhm, ok = QInputDialog.getDouble(
            self, 'Estimate σ from FWHM',
            'Enter the FWHM of a known sharp peak (in x-axis units):',
            value=5.0, min=0.01, max=1000.0, decimals=2)
        if ok:
            sigma = fwhm / 2.3548
            self._sigma_spin.setValue(round(sigma, 2))
            self._sigma_hint.setText(
                f'σ = {sigma:.3f}  (from FWHM = {fwhm:.2f})')

    # ------------------------------------------------------------------ #
    # Settings                                                             #
    # ------------------------------------------------------------------ #

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

        action = ('add the resolution-enhanced result as new spectra' if add_as_new
                  else 'replace the selected spectra with their resolution-enhanced result')
        confirm = QMessageBox.question(
            self, 'Confirm', f'{action[0].upper() + action[1:]}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, message = self.commit_callback(settings, add_as_new, list(self.spectra))
        if success:
            QMessageBox.information(self, 'Done', message)
            self.accept()
        else:
            QMessageBox.warning(self, 'Could Not Apply', message)

    def get_settings(self) -> dict:
        return {
            'irf_sigma': self._sigma_spin.value(),
            'snr':       self._snr_spin.value(),
        }

    def _restore_settings(self):
        if 'irf_sigma' in self._settings:
            self._sigma_spin.setValue(float(self._settings['irf_sigma']))
        if 'snr' in self._settings:
            self._snr_spin.setValue(float(self._settings['snr']))

    # ------------------------------------------------------------------ #
    # Help                                                                 #
    # ------------------------------------------------------------------ #

    def _show_help(self):
        try:
            from src.help.resolution_enhancement_help import (
                get_resolution_help_content, get_resolution_help_title)
            from src.help.help_window import show_help_window
            show_help_window(self, get_resolution_help_title(),
                             get_resolution_help_content())
        except Exception:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Help',
                                    'Help documentation is not available.')


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
