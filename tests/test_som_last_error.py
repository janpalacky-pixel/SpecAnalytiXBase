"""Regression test for a "generic message, no detail" gap in SOM, the same
class of usability bug just fixed in ClusterAnalysisManager: when
compute_som() returns False, the dialog used to always show the bare text
"SOM training failed." with no indication of WHY, forcing the user to dig
through logs.

SOMManager now sets self.last_error to a specific, human-readable reason on
every path that returns False (empty selection, feature mode with no
feature definitions, feature mode with an uncomputable feature, and a
shape-mode axis mismatch between selected spectra), mirroring
ClusterAnalysisManager.last_error. som_dialog.py's
_on_som_computed() displays that detail instead of the generic string.

Unlike Cluster Analysis's n_clusters-vs-n_samples crash, SOM's own training
loop (_train) has no equivalent degenerate-parameter crash: it already
guards n_samples == 0 with a clear ValueError, and falls back cleanly to
random weight initialisation whenever n_samples < 2 or n_features < 2
(skipping the PCA-based init that needs at least 2 of each) -- confirmed
by inspection, not retested here since it needs no fix.
"""

import numpy as np

from src.modules.visualization_analysis.som_manager import SOMManager


def _spectra(n, n_points=20, x=None):
    rng = np.random.default_rng(0)
    if x is None:
        x = np.linspace(0, 10, n_points)
    return [
        {'label': f's{i}', 'x_scale': x, 'y_scale': rng.normal(size=n_points) + i * 5}
        for i in range(n)
    ]


def test_no_spectra_sets_last_error():
    mgr = SOMManager()
    success = mgr.compute_som([], grid_rows=2, grid_cols=2, n_iterations=10)

    assert success is False
    assert mgr.last_error
    assert 'no spectra' in mgr.last_error.lower() or 'no spectra selected' in mgr.last_error.lower()


def test_feature_mode_without_feature_defs_sets_last_error():
    mgr = SOMManager()
    spectra = _spectra(3)

    success = mgr.compute_som(
        spectra, grid_rows=2, grid_cols=2, n_iterations=10,
        train_mode='feature', feature_defs=None)

    assert success is False
    assert mgr.last_error
    assert 'feature' in mgr.last_error.lower()


def test_axis_mismatch_sets_last_error():
    mgr = SOMManager()
    spectra = _spectra(2, n_points=20)
    # Second spectrum uses a completely different, incompatible x-axis.
    spectra[1]['x_scale'] = np.linspace(100, 200, 20)

    success = mgr.compute_som(spectra, grid_rows=2, grid_cols=2, n_iterations=10)

    assert success is False
    assert mgr.last_error


def test_successful_run_leaves_last_error_none():
    mgr = SOMManager()
    spectra = _spectra(5)

    success = mgr.compute_som(spectra, grid_rows=2, grid_cols=2, n_iterations=10)

    assert success is True
    assert mgr.last_error is None


def test_reset_clears_last_error():
    mgr = SOMManager()
    mgr.compute_som([], grid_rows=2, grid_cols=2, n_iterations=10)
    assert mgr.last_error

    mgr.reset()

    assert mgr.last_error is None
