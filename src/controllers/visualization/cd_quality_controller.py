# src/controllers/visualization/cd_quality_controller.py
"""View -> CD data quality: switch the grey "unreliable CD" shading on or
off and change the limits it uses (remembered between sessions).
The rule itself is explained in src/modules/data_io/cd_quality.py."""

from src.views.plot_only_mode import run_beside_plot  # windows beside the main plot
from PyQt5.QtWidgets import (
    QAction, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QMenu, QMessageBox, QVBoxLayout)

from src.modules.data_io.cd_quality import DEFAULT_ABS_LIMIT, DEFAULT_HT_LIMIT_V
from src.modules.misc.session_files import Preferences
from src.modules.utils.app_logger import get_logger
from src.modules.visualization.cd_quality_shading import apply_cd_quality_shading

logger = get_logger(__name__)


class CDQualityLimitsDialog(QDialog):
    def __init__(self, parent, ht_limit, abs_limit):
        super().__init__(parent)
        self.setWindowTitle("CD data quality limits")
        layout = QVBoxLayout(self)
        intro = QLabel(
            "CD is unreliable where the detector receives too little light. "
            "SpecAnalytiXBase judges this by the HT (detector voltage) channel "
            "of the same scan, or, if the file has none, by its absorbance channel.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.ht_spin = QDoubleSpinBox()
        self.ht_spin.setRange(100, 2000)
        self.ht_spin.setDecimals(0)
        self.ht_spin.setSingleStep(10)
        self.ht_spin.setSuffix(" V")
        self.ht_spin.setValue(ht_limit)
        self.ht_spin.setToolTip(f"Usual advice: below 600-700 V (default {DEFAULT_HT_LIMIT_V:.0f} V).")
        self.abs_spin = QDoubleSpinBox()
        self.abs_spin.setRange(0.1, 10)
        self.abs_spin.setDecimals(2)
        self.abs_spin.setSingleStep(0.1)
        self.abs_spin.setValue(abs_limit)
        self.abs_spin.setToolTip(
            f"Textbook ideal: total absorbance below 1. Default {DEFAULT_ABS_LIMIT:g}, because "
            "the absorbance channel recorded by JASCO instruments carries an offset of "
            "about 1 (even pure buffer reads about 0.9 at 320 nm). Lower it to be stricter.")
        form.addRow("HT limit:", self.ht_spin)
        form.addRow("Absorbance limit:", self.abs_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        layout.addWidget(buttons)

    def _defaults(self):
        self.ht_spin.setValue(DEFAULT_HT_LIMIT_V)
        self.abs_spin.setValue(DEFAULT_ABS_LIMIT)

    def values(self):
        return float(self.ht_spin.value()), float(self.abs_spin.value())


class CDQualityController:

    def __init__(self, main_controller, preferences=None):
        self.main = main_controller
        self.preferences = preferences or Preferences()
        self._build_menu()

    # -- state
    def shading_enabled(self):
        return self.preferences.cd_quality_shading()

    def limits(self):
        return self.preferences.cd_quality_limits()

    def set_shading(self, on):
        self.preferences.set('cd_quality_shading', bool(on))
        self.shade_action.setChecked(bool(on))
        self._replot()

    def set_limits(self, ht_limit, abs_limit):
        self.preferences.set('cd_ht_limit_V', float(ht_limit))
        self.preferences.set('cd_abs_limit', float(abs_limit))
        self._replot()

    # -- drawing (called by the main window after every plot)
    def decorate(self, fig, spectra, plot_type):
        if not self.shading_enabled():
            return 0
        try:
            ht_limit, abs_limit = self.limits()
            return apply_cd_quality_shading(fig, spectra, ht_limit, abs_limit, plot_type)
        except Exception:
            # A decoration must never break the plot itself.
            logger.exception("CD data quality shading failed")
            return 0

    def _replot(self):
        if getattr(self.main, 'selected_spectra', None):
            self.main.plot_spectra()

    # -- menu
    def _build_menu(self):
        view_menu = self.main.view.menuView
        self.menu = QMenu("CD data quality", view_menu)
        self.menu.setObjectName("menuCDDataQuality")
        self.shade_action = QAction("Shade unreliable CD regions", self.menu, checkable=True)
        self.shade_action.setChecked(self.shading_enabled())
        self.shade_action.toggled.connect(self.set_shading)
        self.menu.addAction(self.shade_action)
        limits = QAction("Limits…", self.menu)
        limits.triggered.connect(self.edit_limits)
        self.menu.addAction(limits)
        self.menu.addSeparator()
        about = QAction("About CD data quality…", self.menu)
        about.triggered.connect(self.explain)
        self.menu.addAction(about)
        view_menu.addMenu(self.menu)

    def edit_limits(self):
        dialog = CDQualityLimitsDialog(self.main.view, *self.limits())
        if run_beside_plot(dialog) == QDialog.Accepted:
            self.set_limits(*dialog.values())

    def explain(self):
        ht_limit, abs_limit = self.limits()
        QMessageBox.information(
            self.main.view, "CD data quality",
            "Where a sample (with its buffer and cell) absorbs almost all of the "
            "light, the CD detector gets too little light and the CD values become "
            "noise, sometimes looking like real bands.\n\n"
            "When JASCO files (.jws, .jwb) contain an HT (detector voltage) or "
            "absorbance channel, SpecAnalytiXBase uses it to mark those wavelengths "
            "on CD spectra, also if you imported only the CD channel:\n"
            f"   • HT above {ht_limit:.0f} V, or, without an HT channel,\n"
            f"   • absorbance above {abs_limit:g}.\n\n"
            "They are shaded grey in the plot and mentioned after import. Nothing "
            "is removed or changed; you decide what to use (the Data range tool "
            "can cut them off).\n\n"
            "Change the limits in View → CD data quality → Limits.")
