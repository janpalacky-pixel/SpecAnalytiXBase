# src/views/dialogs/visualization_analysis/peak_fit_settings_dialog.py
"""Settings for the 2D Map's peak-fit metrics ("Fitted peak position", ...):
peak shape, background, which fits to show, and serial/parallel
processing. See src/modules/visualization_analysis/peak_fit_map.py."""

from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QVBoxLayout)

from src.modules.visualization_analysis.peak_fit_map import (
    BASELINES, DEFAULT_SETTINGS, MIN_BAND_POINTS_CHOICES, SHAPES, normalized_settings)
from src.views.dialogs.misc.worker_count_slider import WorkerCountSlider

PREFERENCES_KEY = 'peak_fit_map_settings'

_MODE_TEXT = {'auto': 'Automatic', 'serial': 'Serial (one process)',
              'parallel': 'Parallel (several processes)'}


_SHARED = {'processing_mode': 'parallel_processing_mode', 'max_workers': 'parallel_max_workers'}


def load_settings():
    """The Fit settings; Processing and Workers are the computer-wide
    Parallel processing setting (shared with Automated Baseline, X-axis
    alignment and bootstrap). Values stored here by an earlier version are
    moved there once, if it is not set yet."""
    try:
        from src.modules.misc.session_files import Preferences
        prefs = Preferences()
        stored = prefs.get(PREFERENCES_KEY, {})
        stored = dict(stored) if isinstance(stored, dict) else {}
        for key, shared in _SHARED.items():
            if key in stored:
                old = stored.pop(key)
                if prefs.get(shared) is None and old not in ('auto', 0, None):
                    prefs.set(shared, old)
                prefs.set(PREFERENCES_KEY, stored) if stored else prefs.remove(PREFERENCES_KEY)
    except Exception:
        stored = {}
    from src.modules.utils.parallel_utils import default_parallel_settings
    stored.update(default_parallel_settings())
    return normalized_settings(stored)


def save_settings(settings):
    try:
        from src.modules.misc.session_files import Preferences
        prefs = Preferences()
        s = normalized_settings(settings)
        for key, shared in _SHARED.items():
            value = s.pop(key)
            if value in ('auto', 0):
                prefs.remove(shared)
            else:
                prefs.set(shared, value)
        prefs.set(PREFERENCES_KEY, s)
    except Exception:
        pass


class PeakFitSettingsDialog(QDialog):

    def __init__(self, settings=None, parent=None, intro=None):
        super().__init__(parent)
        self.setWindowTitle("Peak-fit settings")
        s = normalized_settings(settings)
        layout = QVBoxLayout(self)
        intro = QLabel(intro or (
            "In every pixel, one peak plus a background is fitted to the points in the "
            "Band range (Configure Band…). Choose a range that contains one band and some "
            "background on both sides; exclude ranges can remove a neighbouring band."))
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

        self.min_points_combo = QComboBox()
        for n in MIN_BAND_POINTS_CHOICES:
            self.min_points_combo.addItem("off" if n == 0 else f"{n} data points", n)
        self._set_min_points(s['min_band_points'])
        self.min_points_combo.setToolTip(
            "A fitted band narrower than this many data-point spacings (its FWHM) is\n"
            "taken as a single spike -- noise or a cosmic ray -- not a band: the pixel\n"
            "gets no value. Off: such fits are kept. 2 rejects only one-point spikes;\n"
            "3 or 4 also two- or three-point ones. Choose a value smaller than the\n"
            "narrowest real band of your data (in data points).")
        form.addRow("Reject bands narrower than:", self.min_points_combo)

        self.mode_combo = QComboBox()
        for key in ('auto', 'serial', 'parallel'):
            self.mode_combo.addItem(_MODE_TEXT[key], key)
        self.mode_combo.setCurrentIndex(['auto', 'serial', 'parallel'].index(s['processing_mode']))
        shared_note = ("\n\nProcessing and Parallel workers are shared by all tools that can use\n"
                       "several processor cores (Automated Baseline, X-axis alignment, bootstrap):\n"
                       "File \u203a Settings and saved items\u2026 \u203a Parallel processing.")
        self.mode_combo.setToolTip(
            "Automatic: fits a few pixels first and uses several processes only when\n"
            "the whole map would take more than a few seconds." + shared_note)
        form.addRow("Processing:", self.mode_combo)

        self.workers_spin = WorkerCountSlider()
        self.workers_spin.setValue(int(s['max_workers'] or 0))
        self.workers_spin.setToolTip(shared_note.strip())
        form.addRow("Parallel workers:", self.workers_spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel
                                   | QDialogButtonBox.RestoreDefaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        layout.addWidget(buttons)

    def _set_min_points(self, value):
        index = self.min_points_combo.findData(int(value) if float(value).is_integer() else value)
        if index < 0:                         # a value set elsewhere, e.g. 2.5
            self.min_points_combo.addItem(f"{value:g} data points", value)
            index = self.min_points_combo.count() - 1
        self.min_points_combo.setCurrentIndex(index)

    def _defaults(self):
        d = DEFAULT_SETTINGS
        self.shape_combo.setCurrentText(d['shape'])
        self.baseline_combo.setCurrentText(d['baseline'])
        self.min_r2_spin.setValue(d['min_r2'])
        self.mode_combo.setCurrentIndex(0)
        self.workers_spin.setValue(0)
        self._set_min_points(d['min_band_points'])

    def settings(self):
        return normalized_settings({
            'shape': self.shape_combo.currentText(),
            'baseline': self.baseline_combo.currentText(),
            'min_r2': self.min_r2_spin.value(),
            'processing_mode': self.mode_combo.currentData(),
            'max_workers': self.workers_spin.value(),
            'min_band_points': self.min_points_combo.currentData(),
        })
