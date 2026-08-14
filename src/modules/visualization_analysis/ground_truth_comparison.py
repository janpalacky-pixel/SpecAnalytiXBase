# src/modules/visualization_analysis/ground_truth_comparison.py
"""
Shared, Qt-free logic behind the hidden "Compare with ground truth (testing)"
feature in the NMF and MCR-ALS dialogs.

This exists purely for developing/debugging/teaching this app's own
decomposition tools against the shipped synthetic benchmark datasets (see
resources/test_data/synthetic/README.md) — it has no meaning for real data,
since real spectra never come with a known-true decomposition to check
against. That's why it's not a first-class button anywhere: it's reached via
a right-click context menu inside the NMF/MCR-ALS dialog, not the normal
Settings panel.

Kept independent of PyQt and of NMFDialog/MCRALSDialog on purpose, so the
matching/scoring logic here can be unit-tested without a QApplication and
reused identically by both dialogs.
"""

import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------- #
# Locating and listing the shipped synthetic datasets                     #
# ---------------------------------------------------------------------- #

def synthetic_datasets_dir():
    """Folder holding the shipped synthetic benchmark workbooks:
    <app root>/resources/test_data/synthetic/. Resolved the same way as
    MainController._synthetic_datasets_dir() (source vs. PyInstaller
    _MEIPASS bundle) — duplicated rather than imported from there to avoid
    a views/controllers -> modules layering violation."""
    base = getattr(sys, '_MEIPASS', None)
    if base is None:
        # src/modules/visualization_analysis/<this file> -> up three levels
        base = os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
    return os.path.join(base, 'resources', 'test_data', 'synthetic')


def list_ground_truth_datasets():
    """Every .xlsx in the synthetic folder that actually has both a
    'Pure_components' and a 'Concentrations' sheet — i.e. one this feature
    can use. Content-based rather than a hardcoded filename list on purpose:
    the folder also holds unrelated demo workbooks (Kinetics, Melting Curve,
    PLS, QC/Outlier, plus a couple of stray manual test files), and new
    decomposition benchmark families can be added later without touching
    any code here, as long as they follow the same two-sheet convention.

    Returns a list of (filename, display_label) tuples, sorted by filename.
    Any file that can't be opened (corrupt, locked, mid-write) is silently
    skipped rather than aborting the whole listing.
    """
    import openpyxl

    folder = synthetic_datasets_dir()
    if not os.path.isdir(folder):
        return []

    results = []
    for filename in sorted(os.listdir(folder)):
        if not filename.lower().endswith('.xlsx'):
            continue
        path = os.path.join(folder, filename)
        try:
            wb = openpyxl.load_workbook(path, read_only=True)
            sheets = set(wb.sheetnames)
            wb.close()
        except Exception:
            logger.debug('Skipping unreadable workbook while listing '
                          'ground-truth datasets: %s', filename, exc_info=True)
            continue
        if {'Pure_components', 'Concentrations'}.issubset(sheets):
            label = filename[:-5].replace('_', ' ')
            results.append((filename, label))
    return results


# ---------------------------------------------------------------------- #
# Loading one dataset's ground truth                                      #
# ---------------------------------------------------------------------- #

class GroundTruth:
    """Everything read from one synthetic workbook's Pure_components and
    Concentrations sheets, in plain numpy/list form."""

    def __init__(self, filename, x_axis, components, component_labels,
                 spectrum_labels, concentrations):
        self.filename = filename
        self.x_axis = x_axis                    # (n_wl,)
        self.components = components             # (n_truth_comp, n_wl)
        self.component_labels = component_labels  # len n_truth_comp
        self.spectrum_labels = spectrum_labels    # len n_truth_spec
        self.concentrations = concentrations      # (n_truth_spec, n_truth_comp)

    @property
    def n_components(self):
        return self.components.shape[0]


def load_ground_truth(filepath):
    """Read a synthetic benchmark workbook's Pure_components and
    Concentrations sheets into a GroundTruth. Raises on malformed input
    (missing sheets, empty data) — callers should catch and show the user a
    message rather than let a stray file crash the dialog."""
    pure_df = pd.read_excel(filepath, sheet_name='Pure_components')
    conc_df = pd.read_excel(filepath, sheet_name='Concentrations')

    if pure_df.shape[1] < 2:
        raise ValueError("'Pure_components' sheet has no component columns.")
    x_axis = pure_df.iloc[:, 0].to_numpy(dtype=float)
    component_labels = list(pure_df.columns[1:])
    components = pure_df.iloc[:, 1:].to_numpy(dtype=float).T  # (n_comp, n_wl)

    if 'Spectrum' not in conc_df.columns:
        raise ValueError("'Concentrations' sheet has no 'Spectrum' column.")
    spectrum_labels = conc_df['Spectrum'].astype(str).tolist()
    # Only the plain per-component columns (Component_1, Component_2, ...),
    # never the _pct / SUM_check columns some families add — those are
    # derived from the same raw numbers and would double them up.
    conc_cols = [c for c in component_labels if c in conc_df.columns]
    if not conc_cols:
        raise ValueError(
            "'Concentrations' sheet's columns don't match "
            "'Pure_components' sheet's component names.")
    concentrations = conc_df[conc_cols].to_numpy(dtype=float)

    return GroundTruth(
        filename=os.path.basename(filepath),
        x_axis=x_axis,
        components=components,
        component_labels=component_labels,
        spectrum_labels=spectrum_labels,
        concentrations=concentrations,
    )


# ---------------------------------------------------------------------- #
# Matching fitted components to ground-truth components                   #
# ---------------------------------------------------------------------- #

def _ascending(x, rows):
    """Sort x ascending, carrying 2D `rows` (n_curves, n_wl) along with it —
    np.interp requires ascending x and several imported spectra/benchmarks
    use a descending axis."""
    x = np.asarray(x, dtype=float)
    rows = np.asarray(rows, dtype=float)
    if x.size > 1 and np.any(np.diff(x) < 0):
        order = np.argsort(x, kind='stable')
        return x[order], rows[:, order]
    return x, rows


def _interp_onto(target_x, source_x, source_rows):
    """Interpolate each row of source_rows (n_curves, n_wl_source) onto
    target_x, after sorting both ascending. Values of target_x outside
    source_x's range are held flat at the nearest edge (np.interp's default),
    consistent with how this app already treats out-of-range points when
    aligning spectra to a common grid elsewhere (Data Range, NMF/MCR-ALS
    axis harmonisation)."""
    target_x = np.asarray(target_x, dtype=float)
    tx_sorted, _ = _ascending(target_x, source_rows[:1] if len(source_rows) else np.zeros((1, 1)))
    sx, rows = _ascending(source_x, source_rows)
    out = np.empty((rows.shape[0], target_x.size), dtype=float)
    for i in range(rows.shape[0]):
        out[i] = np.interp(target_x, sx, rows[i])
    return out


def spectral_similarity(a, b):
    """Absolute cosine similarity between two 1D curves — 1.0 for
    identical shape (up to a positive or negative scale factor), 0.0 for
    orthogonal. Absolute value because NMF/MCR-ALS components can come out
    sign-flipped without that being a meaningfully different answer (most
    relevant for signed/CD-style data with ST non-negativity off)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(abs(np.dot(a, b) / (na * nb)))


def match_components(fitted_components, fitted_x, truth):
    """Best one-to-one assignment between fitted components (rows) and
    ground-truth components (rows), maximising total spectral similarity —
    solved exactly via the Hungarian algorithm rather than greedily, so the
    reported similarity numbers don't depend on component processing order.

    truth's components are interpolated onto fitted_x first, since the two
    may come from slightly different (but here, if the right benchmark file
    was chosen, numerically identical) x-axes.

    Returns (assignment, similarity) where assignment[k] is the truth-row
    index matched to fitted component k (or None if truth has fewer
    components than were fitted, so k has no partner), and similarity[k] is
    that pair's spectral_similarity (0.0 if unmatched).
    """
    n_fitted = fitted_components.shape[0]
    truth_on_fitted_x = _interp_onto(fitted_x, truth.x_axis, truth.components)
    n_truth = truth_on_fitted_x.shape[0]

    cost = np.zeros((n_fitted, n_truth))
    for i in range(n_fitted):
        for j in range(n_truth):
            cost[i, j] = 1.0 - spectral_similarity(fitted_components[i], truth_on_fitted_x[j])

    row_idx, col_idx = linear_sum_assignment(cost)
    assignment = [None] * n_fitted
    similarity = [0.0] * n_fitted
    for r, c in zip(row_idx, col_idx):
        assignment[r] = int(c)
        similarity[r] = 1.0 - float(cost[r, c])
    return assignment, similarity


# ---------------------------------------------------------------------- #
# Concentration alignment + comparison                                    #
# ---------------------------------------------------------------------- #

def align_concentration_rows(fitted_labels, truth):
    """Map each fitted spectrum label onto its row in truth.concentrations.
    Returns (row_for_fitted, unmatched_labels): row_for_fitted[i] is the
    truth-row index for fitted spectrum i (or None if that label isn't in
    the ground-truth file — e.g. a reference spectrum that was excluded
    from the fit, or simply the wrong benchmark file), and unmatched_labels
    lists which fitted labels had no match.

    Tries an exact match first, then falls back to matching on the part
    after the LAST " : " in the fitted label. This matters because a
    normally-IMPORTED spectrum is never labelled with the bare column
    header from the workbook — table_data_converter._parse_column_data
    always prefixes it with the workbook's filename
    ("raman_3comp_noisy : raman_01"), and "import several sheets" adds a
    further "[<sheet>]" tag on top of that ("raman_3comp_noisy [Spectra] :
    raman_01"). The ground-truth workbook's own Concentrations sheet, by
    contrast, stores the bare header ("raman_01") — so an exact-match-only
    comparison would silently match nothing for any spectrum that came
    through the normal Import dialog, which is the overwhelmingly common
    case for this feature. Falling back to the suffix keeps the exact match
    as the first attempt so a fitted label that genuinely equals the raw
    header (e.g. spectra built/renamed by hand, or a test harness) still
    matches directly."""
    index_of = {lbl: i for i, lbl in enumerate(truth.spectrum_labels)}
    row_for_fitted = []
    unmatched = []
    for lbl in fitted_labels:
        idx = index_of.get(lbl)
        if idx is None and ' : ' in lbl:
            idx = index_of.get(lbl.rsplit(' : ', 1)[-1])
        row_for_fitted.append(idx)
        if idx is None:
            unmatched.append(lbl)
    return row_for_fitted, unmatched


def interpolate_truth_components(target_x, truth):
    """Public wrapper around the same interpolation match_components() uses
    internally — lets a caller (e.g. a dialog drawing the overlay curves)
    get truth.components resampled onto its own fitted x-axis without
    duplicating the interpolation logic."""
    return _interp_onto(target_x, truth.x_axis, truth.components)


def normalize_rows_to_100(mat):
    """Public name for _normalize_rows_to_100 — see that docstring. Exposed
    separately so callers plotting a concentration overlay can apply the
    exact same normalisation the report table uses, instead of reimplementing
    it or comparing on-scale numbers to normalised ones by mistake."""
    return _normalize_rows_to_100(mat)


def _normalize_rows_to_100(mat):
    """Rescale each row to sum to 100 — the same 'Normalize to 100% per
    spectrum' convention already used on the Concentrations tab, needed
    here because raw concentration scale is arbitrary (a component's
    concentration column and its spectrum can trade a multiplicative factor
    with no change to the fit), so comparing un-normalised numbers to
    ground truth would penalise a perfectly correct decomposition for
    landing on a different, equally valid overall scale."""
    mat = np.asarray(mat, dtype=float)
    row_sums = mat.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    return 100.0 * mat / row_sums


def concentration_correlation(fitted_col, truth_col):
    """Pearson r and RMSE (in percentage points, after normalising both
    columns to sum-100%-per-spectrum jointly across all components) between
    one fitted concentration column and its matched truth column. Returns
    (r, rmse_pct); r is NaN if either column is constant (undefined
    correlation, e.g. a single-spectrum comparison)."""
    fitted_col = np.asarray(fitted_col, dtype=float)
    truth_col = np.asarray(truth_col, dtype=float)
    if fitted_col.size < 2 or np.std(fitted_col) == 0 or np.std(truth_col) == 0:
        r = float('nan')
    else:
        r = float(np.corrcoef(fitted_col, truth_col)[0, 1])
    rmse_pct = float(np.sqrt(np.mean((fitted_col - truth_col) ** 2)))
    return r, rmse_pct


# ---------------------------------------------------------------------- #
# Top-level report                                                        #
# ---------------------------------------------------------------------- #

def build_recovery_report(fitted_components, fitted_x, fitted_concentrations,
                           fitted_labels, truth):
    """Combine component matching + concentration alignment into one report
    structure the dialogs can render directly (table rows + a summary).

    fitted_components : (n_fitted_comp, n_wl)
    fitted_concentrations : (n_spectra, n_fitted_comp) — same component
        order/columns as fitted_components' rows.
    fitted_labels : spectrum labels for the rows of fitted_concentrations.

    Returns a dict:
        rows: list of per-fitted-component dicts (fitted_index,
              truth_index, truth_label, spectral_similarity,
              conc_correlation, conc_rmse_pct)
        mean_spectral_similarity: float
        n_conc_rows_matched / n_conc_rows_total: int
        unmatched_labels: list[str]
        source_filename: str
    """
    assignment, similarity = match_components(fitted_components, fitted_x, truth)
    row_for_fitted, unmatched_labels = align_concentration_rows(fitted_labels, truth)

    truth_norm = _normalize_rows_to_100(truth.concentrations)
    fitted_norm = _normalize_rows_to_100(fitted_concentrations)

    matched_mask = [r is not None for r in row_for_fitted]
    n_matched = sum(matched_mask)

    rows = []
    for k in range(fitted_components.shape[0]):
        truth_idx = assignment[k]
        entry = {
            'fitted_index': k,
            'truth_index': truth_idx,
            'truth_label': truth.component_labels[truth_idx] if truth_idx is not None else None,
            'spectral_similarity': similarity[k],
            'conc_correlation': float('nan'),
            'conc_rmse_pct': float('nan'),
        }
        if truth_idx is not None and n_matched >= 2:
            fitted_vals = np.array([
                fitted_norm[i, k] for i, r in enumerate(row_for_fitted) if r is not None
            ])
            truth_vals = np.array([
                truth_norm[r, truth_idx] for r in row_for_fitted if r is not None
            ])
            r, rmse = concentration_correlation(fitted_vals, truth_vals)
            entry['conc_correlation'] = r
            entry['conc_rmse_pct'] = rmse
        rows.append(entry)

    mean_similarity = float(np.mean(similarity)) if similarity else float('nan')

    return {
        'rows': rows,
        'mean_spectral_similarity': mean_similarity,
        'n_conc_rows_matched': n_matched,
        'n_conc_rows_total': len(fitted_labels),
        'unmatched_labels': unmatched_labels,
        'source_filename': truth.filename,
    }
