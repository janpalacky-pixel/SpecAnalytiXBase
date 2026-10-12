# src/views/dialogs/visualization_analysis/peak_fit_settings_dialog.py
"""Settings for the 2D Map's peak-fit metrics ("Fitted peak position", ...):
peak shape, background, which fits to show, and serial/parallel
processing. See src/modules/visualization_analysis/peak_fit_map.py."""

from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QSpinBox, QVBoxLayout)

from src.modules.utils.parallel_utils import describe_worker_limits, safe_worker_count
from src.modules.visualization_analysis.peak_fit_map import (
    BASELINES, DEFAULT_SETTINGS, SHAPES, normalized_settings)

PREFERENCES_KEY = 'peak_fit_map_settings'

_MODE_TEXT = {'auto': 'Automatic', 'serial': 'Serial (one process)',
              'parallel': 'Parallel (several processes)'}


def load_settings():
    try:
        from src.modules.misc.session_files import Preferences
        stored = Preferences().get(PREFERENCES_KEY, {})
    except Exception:
        stored = {}
    return normalized_settings(stored if isinstance(stored, dict) else {})


def save_settings(settings):
    try:
        from src.modules.misc.session_files import Preferences
        Preferences().set(PREFERENCES_KEY, normalized_settings(settings))
    except Exception:
        pass


class PeakFitSettingsDialog(QDialog):

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Peak-fit settings")
        s = normalized_settings(settings)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "In every pixel, one peak plus a background is fitted to the points in the "
            "Band range (Configure Band…). Choose a range that contains one band and some "
            "background on both sides; exclude ranges can remove a neighbouring band.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(SHAPES)
        self.shape_combo.setCurrentText(s['shape'])
        self.shape_combo.setToolTip(
            "Gaussian: typical for broad bands, solids, inhomogeneous broadening.\n"
            "Lorentzian: typical for narrow Raman bands of liquids/gases.\n"
            "Pseudo-Voigt: a mix of both; the mixing fraction is fitted too\n"
            "(more flexible, a little slower, needs a clear band).")
        form.addRow("Peak shape:", self.shape_combo)

        self.baseline_combo = QComboBox()
        self.baseline_combo.addItems(BASELINES)
        self.baseline_combo.setCurrentText(s['baseline'])
        self.baseline_combo.setToolTip(
            "Background under the band, fitted together with it.\n"
            "Linear (default) handles a sloping background; Constant a flat offset;\n"
            "None only for already baseline-corrected spectra.")
        form.addRow("Background:", self.baseline_combo)

        self.min_r2_spin = QDoubleSpinBox()
        self.min_r2_spin.setRange(0.0, 0.99)
        self.min_r2_spin.setSingleStep(0.05)
        self.min_r2_spin.setDecimals(2)
        self.min_r2_spin.setSpecialValueText("show all fits")
        self.min_r2_spin.setValue(s['min_r2'])
        self.min_r2_spin.setToolTip(
            "Pixels whose fit describes the data worse than this (R², 0–1) are left\n"
            "empty (no value, hatched grey), e.g. where there is no band, only noise. 0 = show all fits.\n"
            "Pixels where the fit failed or its centre ended at the edge of the\n"
            "range, or the band is wider than the range, are always empty.")
        form.addRow("Hide fits with R² below:", self.min_r2_spin)

        self.mode_combo = QComboBox()
        for key in ('auto', 'serial', 'parallel'):
            self.mode_combo.addItem(_MODE_TEXT[key], key)
        self.mode_combo.setCurrentIndex(['auto', 'serial', 'parallel'].index(s['processing_mode']))
        self.mode_combo.setToolTip(
            "Automatic: fits a few pixels first and uses several processes only when\n"
            "the whole map would take more than a few seconds.")
        form.addRow("Processing:", self.mode_combo)

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(0, 61)
        self.workers_spin.setSpecialValueText(f"Auto ({safe_worker_count()})")
        self.workers_spin.setToolTip(
            "Auto: one less than the CPU cores, but fewer when little memory is free\n"
            "(about 200 MB per worker, 1 GB kept free).\n"
            f"Right now on this computer: {describe_worker_limits()}.\n"
            "A number set by hand is used as given (up to the number of cores). If the\n"
            "workers cannot start or run out of memory, the fitting is redone serially.")
        self.workers_spin.setValue(int(s['max_workers'] or 0))
        form.addRow("Parallel workers:", self.workers_spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel
                                   | QDialogButtonBox.RestoreDefaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        layout.addWidget(buttons)

    def _defaults(self):
        d = DEFAULT_SETTINGS
        self.shape_combo.setCurrentText(d['shape'])
        self.baseline_combo.setCurrentText(d['baseline'])
        self.min_r2_spin.setValue(d['min_r2'])
        self.mode_combo.setCurrentIndex(0)
        self.workers_spin.setValue(0)

    def settings(self):
        return normalized_settings({
            'shape': self.shape_combo.currentText(),
            'baseline': self.baseline_combo.currentText(),
            'min_r2': self.min_r2_spin.value(),
            'processing_mode': self.mode_combo.currentData(),
            'max_workers': self.workers_spin.value(),
        })
