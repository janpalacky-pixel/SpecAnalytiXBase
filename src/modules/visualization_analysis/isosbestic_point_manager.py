# src/modules/visualization_analysis/isosbestic_point_manager.py
"""
Isosbestic / Isodichroic Point Detection manager.

An isosbestic point (absorption/UV-Vis) or isodichroic point (CD) is a
wavelength (or other x-axis value) where every spectrum in a series
recorded along some interconversion coordinate (titration, temperature,
time, pH, ...) between exactly two species crosses through the same
y-value. It happens where the two species have equal molar absorptivity
(or equal molar CD) at that wavelength, so the observed signal there is
independent of how far the interconversion has progressed.

DETECTION APPROACH: given N spectra sharing one x-axis (stacked into a
matrix), a genuine isosbestic point shows up as a wavelength where the
spectra AGREE tightly with each other, surrounded on both sides by
wavelengths where they visibly fan out. That is exactly a local MINIMUM
of the cross-spectrum standard deviation std(x) = std_i(y_i(x)), and one
that stands out from the surrounding baseline noise level — a true dip,
not just the smallest value in an otherwise flat, noisy curve.

This is found with scipy.signal.find_peaks on the NEGATED std(x) curve
(so "peaks" of -std(x) are exactly the local minima/valleys of std(x)),
using its built-in topographic PROMINENCE metric to reject dips that
aren't clearly distinguished from the noise around them — see
scipy's documentation for the precise definition; in short, a valley's
prominence is how far you'd have to climb back up, on the shallower
side, before reaching a point lower than the valley itself elsewhere in
the signal (or the edge of the search range). A shallow, noise-driven
wiggle has low prominence; a genuine, clean isosbestic point — where the
spectra collapse together tightly compared to how much they disagree
everywhere else — has high prominence.

EMPTY/BASELINE REGIONS — the most important pitfall this manager guards
against: a flat, signal-free stretch of x-axis (no peak from EITHER
species, e.g. the wide gaps between separated Raman bands) also has
std(x) close to zero there, often an even sharper dip than a genuine
crossing, since the baseline sits at exactly the same (near-)zero value
for every spectrum. Confirmed directly against a real multi-peak
dataset: without guarding against this, trivial empty-baseline gaps
dominated the top candidates and crowded out the genuine, physically
meaningful crossing entirely. The fix is min_signal_pct (see
compute_results' docstring): a candidate is only kept if the mean signal
there is a non-trivial fraction of the largest mean signal anywhere in
the searched range — i.e., there must actually be two active,
comparably-sized signals crossing, not simply "nothing happening on
either side." This significance test is applied to the RESULTS of
find_peaks, not baked into the search curve itself — injecting an
artificial sentinel value into std(x) wherever the signal is
insignificant (an earlier version of this fix did exactly that) creates
a hard cliff at the mask boundary, and find_peaks mistakes the last
still-significant point on a decaying peak's shoulder for a genuine
valley bottom. Confirmed directly against a real dataset: that produced
spurious candidates sitting right at the mask edge, nowhere near an
actual pure-component crossing.

CAVEATS (see src/help/isosbestic_point_help.py for the full discussion):
  * Needs at least 3 spectra to be meaningful. With only 2, any two
    non-parallel curves cross SOMEWHERE trivially — that crossing proves
    nothing about a shared two-species equilibrium.
  * Requires all spectra to already share one identical x-axis (use the
    Data Range operation with linearisation first if they don't) — see
    spectra_validation.validate_common_x_axis.
  * Only detects a point common to ALL selected spectra. If some spectra
    in the selection don't belong to the same two-state series (e.g. an
    unrelated control), no consistent crossing will be found, or the
    real isosbestic point of the other spectra may lose prominence.
"""
import numpy as np
from scipy.signal import find_peaks

from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match

logger = get_logger(__name__)

DEFAULT_MIN_PROMINENCE_PCT = 10.0
DEFAULT_MIN_SIGNAL_PCT = 5.0
DEFAULT_MAX_CANDIDATES = 5


class IsosbesticPointManager:
    """Business logic for isosbestic/isodichroic point detection.

    Pure computation — compute_results() never mutates its inputs, never
    touches the UI, and never modifies the spectra list (nothing is
    added, removed, or transformed), same as BandRatioManager. All
    results are handed back for the dialog to display/export.
    """

    def compute_results(self, spectra: list, settings: dict = None) -> dict:
        """Detect candidate isosbestic/isodichroic point(s) across *spectra*.

        Parameters
        ----------
        spectra : list of spectrum dicts — must share one identical
            x-axis (see spectra_validation.axes_match); the caller
            should validate this up front (validate_common_x_axis) so
            the user sees a clear message before this raises.
        settings : dict with optional keys
            x_range             : (x_min, x_max) or None — restrict the
                                   search to this sub-range.
            min_prominence_pct  : float, 0-100 (default 10.0) — minimum
                                   prominence, as a percentage of the
                                   full std(x) variation range within the
                                   searched window, for a local minimum
                                   to be reported as a candidate.
            min_signal_pct      : float, 0-100 (default 5.0) — a
                                   candidate is only kept if the mean
                                   signal there (|mean_y|) is at least
                                   this percentage of the largest mean
                                   signal anywhere in the searched range.
                                   See the module docstring's "EMPTY
                                   REGIONS" note for why this matters.
            max_candidates      : int (default 5) — cap on how many
                                   candidates are returned, strongest
                                   (highest prominence) first.

        Returns
        -------
        dict with keys:
            x, mean_curve, std_curve  : arrays over the searched x-range
            candidates                : list of dicts, sorted by
                                         prominence descending, each with
                                         x, mean_y, std, prominence,
                                         relative_tightness
            n_spectra                 : int, number of spectra used
            warning                   : str or None — e.g. "only 2
                                         spectra: not statistically
                                         meaningful" or "no candidates
                                         found at this sensitivity"

        Raises
        ------
        ValueError — fewer than 2 spectra, spectra don't share an
        x-axis, or the x_range leaves too few points to search.
        """
        settings = settings or {}
        x_range = settings.get('x_range')
        min_prominence_pct = float(settings.get('min_prominence_pct', DEFAULT_MIN_PROMINENCE_PCT))
        min_signal_pct = float(settings.get('min_signal_pct', DEFAULT_MIN_SIGNAL_PCT))
        max_candidates = int(settings.get('max_candidates', DEFAULT_MAX_CANDIDATES))

        if len(spectra) < 2:
            raise ValueError("Select at least 2 spectra (3 or more recommended — see Help).")

        x_ref = np.asarray(spectra[0]['x_scale'], dtype=float)
        rows = []
        for s in spectra:
            x = np.asarray(s.get('x_scale', []), dtype=float)
            if not axes_match(x_ref, x):
                raise ValueError(
                    f"Spectrum '{s.get('label', '?')}' does not share the same "
                    "x-axis as the others. Use the Data Range operation with "
                    "linearisation to bring all spectra onto a common x-axis first."
                )
            rows.append(np.asarray(s.get('y_scale', []), dtype=float))
        y_matrix = np.vstack(rows)

        # Restrict to the requested x-range, if any.
        if x_range is not None:
            lo, hi = min(x_range), max(x_range)
            mask = (x_ref >= lo) & (x_ref <= hi)
            x = x_ref[mask]
            y_matrix = y_matrix[:, mask]
        else:
            x = x_ref

        if len(x) < 5:
            raise ValueError(
                "Too few points in the searched x-range to detect a crossing "
                "point (need at least 5). Widen the x-range."
            )

        n_spectra = y_matrix.shape[0]
        std_curve = np.std(y_matrix, axis=0, ddof=1 if n_spectra > 1 else 0)
        mean_curve = np.mean(y_matrix, axis=0)

        warning = None
        if n_spectra == 2:
            warning = (
                "Only 2 spectra selected — any two non-parallel curves cross "
                "somewhere trivially, so this alone doesn't confirm a genuine "
                "isosbestic/isodichroic point. Select 3 or more spectra from "
                "the series for a statistically meaningful result."
            )

        variation_range = float(np.max(std_curve) - np.min(std_curve))
        if variation_range <= 0:
            return {
                'x': x, 'mean_curve': mean_curve, 'std_curve': std_curve,
                'candidates': [], 'n_spectra': n_spectra,
                'warning': (warning or '') + (
                    ' All selected spectra are numerically identical everywhere '
                    'in this range — nothing to detect.'
                ),
            }

        # EMPTY/BASELINE REGIONS: a genuine isosbestic point is where two
        # ACTIVE signals happen to be equal — not where every spectrum
        # simply has no signal at all. But a flat baseline stretch (no
        # peak from either component) also produces a std(x) of ~0, often
        # an even SHARPER, more "prominent" dip than the real crossing
        # (since it drops to exactly zero on both sides too). Confirmed
        # directly against a real dataset with several separated peaks:
        # without this filter, trivial empty-baseline gaps between peaks
        # dominated the top-N results and crowded out the genuine
        # crossing entirely. The fix: only report candidates where the
        # mean signal itself is non-trivial — at least min_signal_pct of
        # the largest mean signal anywhere in the searched range.
        #
        # IMPORTANT: this filter is applied to the RESULTS of peak-finding,
        # never to the search curve itself. An earlier version injected an
        # artificial sentinel value into std_curve wherever the signal was
        # insignificant before calling find_peaks — but that creates a
        # hard artificial cliff at the mask boundary, and find_peaks then
        # mistakes the last still-significant point on the shoulder of a
        # decaying peak tail (where std is already small and still
        # trending down) for a genuine valley bottom, since the very next
        # point jumps straight to the sentinel. Confirmed directly against
        # a real dataset: this produced spurious candidates sitting right
        # at the edge of the significance mask, nowhere near an actual
        # pure-component crossing. Running find_peaks on the untouched
        # curve and filtering the resulting candidate list afterward finds
        # exactly the same genuine local minima without this artifact.
        max_abs_signal = float(np.max(np.abs(mean_curve)))
        if max_abs_signal > 0:
            significant = np.abs(mean_curve) >= (min_signal_pct / 100.0) * max_abs_signal
        else:
            significant = np.ones_like(mean_curve, dtype=bool)

        # "Typical" disagreement for the relative-tightness metric is
        # also computed only over the significant region — the median
        # across the WHOLE range (including long flat, signal-free
        # stretches common in real spectra) would be dominated by
        # trivial near-zero baseline and make every real candidate look
        # artificially "loose" by comparison, which is exactly backwards.
        significant_std = std_curve[significant]
        typical_std = float(np.median(significant_std)) if significant_std.size else 0.0

        min_prominence = (min_prominence_pct / 100.0) * variation_range
        peak_indices, properties = find_peaks(-std_curve, prominence=min_prominence)

        candidates = []
        for idx, prom in zip(peak_indices, properties['prominences']):
            if not significant[idx]:
                continue
            x_refined = self._refine_x(x, std_curve, idx)
            std_val = float(std_curve[idx])
            relative_tightness = (std_val / typical_std) if typical_std > 0 else 0.0
            candidates.append({
                'x': x_refined,
                'mean_y': float(mean_curve[idx]),
                'std': std_val,
                'prominence': float(prom),
                'relative_tightness': relative_tightness,
            })

        candidates.sort(key=lambda c: c['prominence'], reverse=True)
        candidates = candidates[:max_candidates]

        if not candidates and warning is None:
            warning = (
                "No candidate points found at this sensitivity. Try lowering "
                "the minimum prominence or the minimum signal level, or "
                "widening the searched x-range."
            )

        return {
            'x': x, 'mean_curve': mean_curve, 'std_curve': std_curve,
            'candidates': candidates, 'n_spectra': n_spectra, 'warning': warning,
        }

    @staticmethod
    def _refine_x(x, std_curve, idx):
        """Sub-grid refinement of a local minimum's x-location via a
        parabola fit through the minimum and its two neighbours — done
        in FRACTIONAL INDEX space (robust to non-uniform x-spacing) and
        then mapped back to x by linear interpolation between the
        neighbouring grid points, rather than assuming a fixed step
        size. Falls back to the plain grid point at the edges of the
        array (no neighbour on one side) or if the parabola is
        degenerate (denominator would be zero, i.e. the three points are
        collinear)."""
        n = len(std_curve)
        if idx <= 0 or idx >= n - 1:
            return float(x[idx])

        y_left, y_mid, y_right = std_curve[idx - 1], std_curve[idx], std_curve[idx + 1]
        denom = y_left - 2 * y_mid + y_right
        if denom == 0:
            return float(x[idx])

        # Vertex offset in fractional-index units, in [-0.5, 0.5] for a
        # genuine local minimum bracketed by its neighbours.
        delta = 0.5 * (y_left - y_right) / denom
        delta = max(-0.5, min(0.5, delta))

        if delta >= 0:
            return float(x[idx] + delta * (x[idx + 1] - x[idx]))
        else:
            return float(x[idx] + delta * (x[idx] - x[idx - 1]))
