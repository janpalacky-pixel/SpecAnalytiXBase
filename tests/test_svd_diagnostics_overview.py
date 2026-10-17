"""SVD Analysis -> Diagnostics tab, view mode "Overview (all)": every metric
gets its own panel. (It used a fixed 2 x 3 grid, which crashed with the
seventh metric, Eigenvalue: "num must be an integer with 1 <= num <= 6, not 7".)"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.controllers.visualization_analysis.svd_analysis_controller import SVDAnalysisController  # noqa: E402
from src.views.dialogs.visualization_analysis.svd_analysis_dialog import SVDDiagnosticsDialog  # noqa: E402


class _Main:
    pass


def _spectra(n_spectra=20, n_points=80, seed=3):
    rng = np.random.default_rng(seed)
    x = np.linspace(400.0, 1800.0, n_points)
    bands = np.stack([np.exp(-0.5 * ((x - c) / 30.0) ** 2) for c in (700, 1000, 1450)])
    amounts = rng.random((n_spectra, 3))
    Y = amounts @ bands + rng.normal(scale=0.01, size=(n_spectra, n_points))
    return [{'label': f's{i}', 'x_scale': x.copy(), 'y_scale': Y[i].copy(), 'metadata': {}}
            for i in range(n_spectra)]


def test_overview_shows_every_metric_without_error():
    ctrl = SVDAnalysisController(_Main())
    assert ctrl.compute_svd_analysis(_spectra())
    panel = SVDDiagnosticsDialog(controller=ctrl)
    assert len(panel.METRICS) == 7
    panel.mode_combo.setCurrentText("Overview (all)")      # raised ValueError before
    app.processEvents()
    titled = [ax for ax in panel.fig.axes if ax.get_title()]
    assert len(titled) == len(panel.METRICS)
    # also with "Log scale (overview)" ticked
    panel.overview_log_cb.setChecked(True)
    app.processEvents()
    assert len([ax for ax in panel.fig.axes if ax.get_title()]) == len(panel.METRICS)
