# tests/test_ground_truth_correctness.py
"""
Correctness tests for NMF and MCR-ALS against the shipped synthetic
benchmark datasets in resources/test_data/synthetic/, which carry a known
true decomposition (Pure_components + Concentrations sheets) precisely so
these two managers' actual recovery accuracy can be checked against ground
truth, not just "did it run without crashing."

This targets a gap the rest of the suite doesn't cover: NMF and MCR-ALS are
the most mathematically complex, most bug-prone managers in the app (see
test_regression_bugs.py's TestMCRALSClosureReferenceScale for a real
example — a bug here silently produced a plausible-looking wrong answer,
not a crash, and went unnoticed until manual testing surfaced it).

A note on which datasets are used and why: NMF and (without Closure)
MCR-ALS have a genuine mathematical property called rotational ambiguity —
multiple different decompositions can fit the data equally well, with no
way for the algorithm to know which one matches physical reality (see
nmf_help.py / mcr_als_help.py's "Test datasets with known ground truth"
section for the full explanation). This is NOT a bug and must not be
"fixed" by loosening these tests indefinitely — it means a handful of the
synthetic families (e.g. 3+ component Raman/UV-Vis without a Closure
constraint or a fixed reference) legitimately recover with mediocre
component-matching scores even when the manager code is completely
correct. Using such a family here would make the test either flaky or
misleadingly strict.

So this file deliberately sticks to the families where correct code
SHOULD recover near-exactly:
  - closed_dna_melting_*: a genuinely closed system (concentrations sum to
    100% per spectrum by construction) — MCR-ALS with Closure ON has no
    rotational freedom left to get wrong, and NMF (whose W/H concentration
    scale is otherwise arbitrary) happens to recover it very well too.
  - uvvis_2comp_clean: only 2 components, where rotational ambiguity
    reduces to little more than an overall scale/sign choice — component
    SHAPE recovery is reliably near-exact even without Closure. Its
    concentration-side numbers are deliberately not asserted as tightly
    (see TestMCRALSGroundTruthCorrectness.
    test_uvvis_2comp_clean_without_closure_recovers_component_shapes for
    why), consistent with everything this app's own help pages say about
    reading concentration RMSE without an anchoring constraint.
"""

import os

import numpy as np
import pandas as pd
import pytest

from src.modules.visualization_analysis.ground_truth_comparison import (
    load_ground_truth, build_recovery_report,
)
from src.modules.visualization_analysis.mcr_als_manager import MCRALSManager
from src.modules.visualization_analysis.nmf_manager import NMFManager


SYNTHETIC_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'resources', 'test_data', 'synthetic'))


def _dataset_path(filename):
    path = os.path.join(SYNTHETIC_DIR, filename)
    if not os.path.isfile(path):
        pytest.skip(f'Synthetic benchmark dataset not found: {filename}')
    return path


def _load_spectra_and_truth(filename):
    """Load a benchmark workbook's 'Spectra' sheet as a list of spectrum
    dicts (labelled with the BARE column header, exactly as the ground
    truth's own Concentrations sheet stores them — see
    align_concentration_rows's docstring for why a normally-imported
    spectrum's label differs from this and needs the suffix-fallback match
    that test_regression_bugs.py covers separately), plus the matching
    GroundTruth."""
    path = _dataset_path(filename)
    df = pd.read_excel(path, sheet_name='Spectra')
    x = df.iloc[:, 0].to_numpy(dtype=float)
    spectra = [
        {'label': str(col), 'x_scale': x.copy(), 'y_scale': df[col].to_numpy(dtype=float)}
        for col in df.columns[1:]
    ]
    truth = load_ground_truth(path)
    return spectra, truth


def _assert_good_recovery(report, min_mean_similarity, min_r, max_rmse_pct):
    assert report['n_conc_rows_matched'] == report['n_conc_rows_total'], (
        f"{report['unmatched_labels']!r} did not match any ground-truth spectrum row")
    assert report['mean_spectral_similarity'] >= min_mean_similarity
    for row in report['rows']:
        assert row['truth_index'] is not None, 'every fitted component should match a truth component'
        assert row['spectral_similarity'] >= min_mean_similarity - 0.02, row
        assert row['conc_correlation'] >= min_r, row
        assert row['conc_rmse_pct'] <= max_rmse_pct, row


# ---------------------------------------------------------------------- #
# NMF                                                                      #
# ---------------------------------------------------------------------- #

class TestNMFGroundTruthCorrectness:

    def test_closed_dna_3comp_clean_recovers_almost_exactly(self):
        spectra, truth = _load_spectra_and_truth('closed_dna_melting_3comp_clean.xlsx')
        mgr = NMFManager()
        assert mgr.compute(spectra, n_components=truth.n_components)
        report = build_recovery_report(mgr.H, mgr.x_axis, mgr.W, mgr.labels, truth)
        _assert_good_recovery(report, min_mean_similarity=0.999, min_r=0.999, max_rmse_pct=3.0)

    def test_closed_dna_3comp_noisy_recovers_well(self):
        spectra, truth = _load_spectra_and_truth('closed_dna_melting_3comp_noisy.xlsx')
        mgr = NMFManager()
        assert mgr.compute(spectra, n_components=truth.n_components)
        report = build_recovery_report(mgr.H, mgr.x_axis, mgr.W, mgr.labels, truth)
        _assert_good_recovery(report, min_mean_similarity=0.995, min_r=0.999, max_rmse_pct=3.0)

    def test_uvvis_2comp_clean_recovers_component_shapes(self):
        """2 components -> rotational ambiguity is minimal, shapes recover
        almost exactly. Concentration RMSE is deliberately given a loose
        bound here (not tightened to match the closed-DNA tests): NMF's
        "Normalize to 100%" is a display-only rescale, not a fitting
        constraint (see nmf_dialog.py's own tooltip for exactly this
        caveat), so an absolute-scale mismatch between fitted and truth
        concentrations is expected without Closure/reference anchoring,
        even though both r and spectral similarity are excellent."""
        spectra, truth = _load_spectra_and_truth('uvvis_2comp_clean.xlsx')
        mgr = NMFManager()
        assert mgr.compute(spectra, n_components=truth.n_components)
        report = build_recovery_report(mgr.H, mgr.x_axis, mgr.W, mgr.labels, truth)
        _assert_good_recovery(report, min_mean_similarity=0.99, min_r=0.999, max_rmse_pct=20.0)


# ---------------------------------------------------------------------- #
# MCR-ALS                                                                  #
# ---------------------------------------------------------------------- #

class TestMCRALSGroundTruthCorrectness:

    def test_closed_dna_3comp_clean_with_closure_recovers_almost_exactly(self):
        spectra, truth = _load_spectra_and_truth('closed_dna_melting_3comp_clean.xlsx')
        mgr = MCRALSManager()
        assert mgr.compute(spectra, n_components=truth.n_components, closure=True)
        assert mgr.lof < 1.0
        report = build_recovery_report(mgr.ST, mgr.x_axis, mgr.C, mgr.labels, truth)
        _assert_good_recovery(report, min_mean_similarity=0.999, min_r=0.999, max_rmse_pct=3.0)

    def test_closed_dna_3comp_noisy_with_closure_recovers_well(self):
        spectra, truth = _load_spectra_and_truth('closed_dna_melting_3comp_noisy.xlsx')
        mgr = MCRALSManager()
        assert mgr.compute(spectra, n_components=truth.n_components, closure=True)
        assert mgr.lof < 10.0
        report = build_recovery_report(mgr.ST, mgr.x_axis, mgr.C, mgr.labels, truth)
        _assert_good_recovery(report, min_mean_similarity=0.995, min_r=0.999, max_rmse_pct=3.0)

    def test_uvvis_2comp_clean_without_closure_recovers_component_shapes(self):
        """Same rationale as the NMF equivalent above, but additionally
        this dataset is NOT a closed system, so Closure is off (using it
        here would be physically wrong, not just unnecessary — see
        mcr_als_help.py's "Closure is only physically valid for genuinely
        closed systems"). Without Closure or a fixed reference there is
        nothing pinning the concentration scale down, so — deliberately —
        only component shape (spectral similarity) is asserted tightly;
        concentration r/RMSE are read but not gated on, since a low RMSE
        here would be luck, not correctness, and a high one would not be a
        bug."""
        spectra, truth = _load_spectra_and_truth('uvvis_2comp_clean.xlsx')
        mgr = MCRALSManager()
        assert mgr.compute(spectra, n_components=truth.n_components, closure=False)
        report = build_recovery_report(mgr.ST, mgr.x_axis, mgr.C, mgr.labels, truth)
        assert report['mean_spectral_similarity'] >= 0.97
        for row in report['rows']:
            assert row['truth_index'] is not None
            assert row['spectral_similarity'] >= 0.95
