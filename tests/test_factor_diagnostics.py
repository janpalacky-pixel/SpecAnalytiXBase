"""How many components: residual error, Malinowski IND (with the SMALLER side
of the table as c), noise limit / clearly above -- factor_diagnostics, its use in SVD
Analysis, PCA and the 2D Map -- and safe_tight_layout (no "Singular matrix"
for a zero-size figure; the 2D Map's Diagnostics window)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from src.modules.visualization_analysis import factor_diagnostics as fd    # noqa: E402


def _mixture(n_sp, n_pts, k=3, noise=0.02, seed=0):
    """n_pts x n_sp table (columns = spectra) made of k Gaussian bands."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 1, n_pts)
    S = np.stack([np.exp(-0.5 * ((x - c) / 0.04) ** 2) for c in np.linspace(0.2, 0.8, k)])
    C = rng.random((n_sp, k))
    return (C @ S).T + rng.normal(scale=noise, size=(n_pts, n_sp)), x


def _old_ind_spectra_as_c(s, n_pts, n_sp):
    """The formula used before: c = number of spectra (always)."""
    lam = s ** 2
    out = np.zeros(len(s) - 1)
    for m in range(len(s) - 1):
        re = np.sqrt(lam[m + 1:].sum() / (n_pts * (n_sp - m)))
        out[m] = re / (n_sp - m) ** 2
    return out


def test_ind_uses_the_smaller_side_for_a_map_shaped_table():
    X, _ = _mixture(n_sp=3000, n_pts=200, k=3)          # more spectra than points
    s = np.linalg.svd(X, compute_uv=False)
    ind = fd.malinowski_ind(s, n_pts=200, n_sp=3000)
    assert fd.ind_minimum(ind) == 3
    # the same whichever way round the sizes are given
    assert fd.ind_minimum(fd.malinowski_ind(s, 3000, 200)) == 3
    # the old formula (c = spectra) runs to the last component
    assert int(np.argmin(_old_ind_spectra_as_c(s, 200, 3000))) + 1 == len(s) - 1


def test_ind_for_few_spectra_of_many_points():
    X, _ = _mixture(n_sp=20, n_pts=500, k=3)
    s = np.linalg.svd(X, compute_uv=False)
    assert fd.ind_minimum(fd.malinowski_ind(s, 500, 20)) == 3


def test_noise_limit_and_clearly_above():
    X, _ = _mixture(n_sp=2000, n_pts=300, k=3)
    s = np.linalg.svd(X, compute_uv=False)
    nl = fd.noise_limit(s)
    assert nl['n'] == 3 and nl['clear'] == 3 and nl['factor'] == 1.15 and nl['clear_factor'] == 2.0
    assert fd.noise_limit(s[:11]) is None                # too few values


def test_svd_analysis_residual_error_uses_the_real_number_of_spectra():
    from src.modules.visualization_analysis.svd_analysis_manager import SVDAnalysisManager
    X, x = _mixture(n_sp=600, n_pts=120, k=3, noise=0.05)
    spectra = [{'label': f's{i}', 'x_scale': x, 'y_scale': X[:, i], 'metadata': {}}
               for i in range(X.shape[1])]
    mgr = SVDAnalysisManager()
    assert mgr.compute_svd_from_spectra(spectra)
    E = mgr.calculate_residual_errors()
    assert np.allclose(E, fd.residual_error(mgr.s, 120, 600))
    # after the 3 real components E is the noise level per point
    assert E[2] == pytest.approx(0.05, rel=0.1)


def test_pca_residual_error_and_ind_do_not_depend_on_components_kept():
    from src.modules.visualization_analysis.pca_scores_manager import PcaScoresManager
    X, x = _mixture(n_sp=40, n_pts=300, k=3)
    spectra = [{'label': f's{i}', 'x_scale': x, 'y_scale': X[:, i], 'metadata': {}}
               for i in range(X.shape[1])]
    a, b = PcaScoresManager(), PcaScoresManager()
    assert a.compute_svd(spectra, 6) and b.compute_svd(spectra, 15)
    assert np.allclose(a.residual_err, b.residual_err[:len(a.residual_err)])
    assert np.allclose(a.malinowski_ind, b.malinowski_ind[:len(a.malinowski_ind)])


def test_safe_tight_layout_skips_a_zero_size_figure():
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from src.modules.visualization.safe_layout import safe_tight_layout
    fig = Figure()
    canvas = FigureCanvasQTAgg(fig)
    fig.add_subplot(111).plot([1, 2])
    canvas.resize(300, 0)
    canvas.show()
    app.processEvents()
    with pytest.raises(np.linalg.LinAlgError):
        fig.tight_layout()                               # what crashed before
    assert safe_tight_layout(fig) is False               # skipped, no error
    canvas.resize(300, 200)
    app.processEvents()
    assert safe_tight_layout(fig) is True


def test_2d_map_diagnostics_opens_in_its_own_window(monkeypatch):
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda t, v, tb: errors.append(v))
    from src.controllers.visualization_analysis.map2d_controller import Map2DController
    from src.views.dialogs.visualization_analysis.map2d_dialog import Map2DDialog
    X, x = _mixture(n_sp=20 * 30, n_pts=150, k=3)
    spectra = [{'label': f'map [r{i // 30:03d}_c{i % 30:03d}]', 'x_scale': x,
                'y_scale': X[:, i], 'metadata': {}} for i in range(X.shape[1])]

    class _Main:
        view = None

    d = Map2DDialog(None, Map2DController(_Main()), spectra)
    d._rows_spin.setValue(20)
    d._cols_spin.setValue(30)
    d.show()
    app.processEvents()
    d._radio_svd.setChecked(True)
    d._on_mode_changed(d._radio_svd)
    d._compute_map()
    d._show_diagnostics()
    app.processEvents()
    win, panel = d._diagnostics_window, d._diagnostics_panel
    assert win.isWindow() and panel.canvas.height() > 100
    for mode in ("Single metric", "Compare two metrics", "Overview (all)"):
        panel.mode_combo.setCurrentText(mode)
        app.processEvents()
    panel._refresh_plot()
    assert not errors
    assert fd.ind_minimum(panel.data['IND']) == 3        # 600 spectra x 150 points
    assert panel.noise is not None and panel.noise['n'] == 3
    assert 'Above the noise:</b> 3' in panel._summary_label.text()
    win.close()
    d.close()
