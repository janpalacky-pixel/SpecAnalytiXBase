"""Regression test for a real crash the user hit while testing in the GUI:
K-Means (or Hierarchical) with n_clusters set equal to the number of
selected spectra puts every spectrum in its own cluster. That passed
compute_silhouette_analysis()'s old "at least 2 clusters" guard, but
sklearn's silhouette_samples actually requires 2 <= n_labels <=
n_samples - 1 -- so it raised ValueError("Number of labels is N. Valid
values are 2 to n_samples - 1"), which the outer try/except in
compute_clustering() caught and turned into "clustering failed" for the
WHOLE run, even though the cluster labels themselves were computed fine
and silhouette is only a diagnostic on top of them.

A second, independent bug compounded this: the dialog's own
"clustering failed" message box crashed with UnboundLocalError instead
of showing (see cluster_analysis_dialog.py's _on_clustering_computed) --
not covered here since it needs Qt; covered by manual inspection and the
fix removing the shadowing local import.
"""

import numpy as np

from src.modules.visualization_analysis.cluster_analysis_manager import (
    ClusterAnalysisManager)


def _spectra(n, n_points=20):
    rng = np.random.default_rng(0)
    x = np.linspace(0, 10, n_points)
    return [
        {'label': f's{i}', 'x_scale': x, 'y_scale': rng.normal(size=n_points) + i * 5}
        for i in range(n)
    ]


def test_kmeans_n_clusters_equal_to_n_samples_does_not_crash():
    """3 clusters for 3 spectra -> every spectrum its own cluster --
    used to raise inside silhouette and fail the whole run."""
    mgr = ClusterAnalysisManager()
    spectra = _spectra(3)

    success = mgr.compute_clustering(spectra, method='kmeans', n_clusters=3)

    assert success is True
    assert mgr.cluster_labels is not None
    assert len(np.unique(mgr.cluster_labels)) == 3
    # Silhouette is meaningless here (no valid n_labels in [2, n_samples-1]
    # range exists when n_clusters == n_samples) -- skipped gracefully,
    # not crashed.
    assert mgr.get_silhouette_data() is None


def test_kmeans_normal_case_still_computes_silhouette():
    """Sanity check the fix didn't disable silhouette for the normal case
    (fewer clusters than samples)."""
    mgr = ClusterAnalysisManager()
    spectra = _spectra(6)

    success = mgr.compute_clustering(spectra, method='kmeans', n_clusters=2)

    assert success is True
    data = mgr.get_silhouette_data()
    assert data is not None
    assert data['avg_score'] is not None


def test_hierarchical_n_clusters_equal_to_n_samples_does_not_crash():
    mgr = ClusterAnalysisManager()
    spectra = _spectra(4)

    success = mgr.compute_clustering(spectra, method='hierarchical', n_clusters=4)

    assert success is True
    assert mgr.get_silhouette_data() is None
