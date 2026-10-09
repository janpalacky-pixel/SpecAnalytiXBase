# src/modules/data_analysis/cosmic_ray_manager.py
"""
Cross-spectrum cosmic ray detection.

Unlike single-spectrum spike removal (which uses the 2nd derivative of
each spectrum independently), this manager compares every spectrum against
its neighbours in the group.  A cosmic ray appears as an intensity outlier
at a specific x-index that is statistically anomalous relative to the same
x-position in all other spectra.

Algorithm
---------
1. Every selected spectrum must already share the same x-axis (refuses
   otherwise — see _build_matrix).
2. For each x-position j, compute the median and MAD across all spectra
   (this cross-spectrum comparison is DETECTION only).
3. A point (i, j) is flagged as a cosmic ray if its modified Z-score
   relative to the group at position j exceeds the threshold:

       Z(i,j) = 0.6745 * (y[i,j] - median_j) / MAD_j

4. Flagged points (optionally widened by replace_window points on each
   side, to also cover a ray's shoulders) are replaced by linear
   interpolation between the nearest CLEAN points in that SAME spectrum's
   own trace — not the group median. Detection is cross-spectrum, but
   replacement is local to each spectrum, so it's never at the mercy of
   the group median being an imperfect reference at any given position.

This approach catches rays that do not look like narrow spikes within a
single spectrum (e.g. broad rays, or rays in spectra with high noise)
but are obvious outliers when compared across replicates.
"""

import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match, describe_axis_mismatch
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.progress_utils import notify_progress

logger = get_logger(__name__)


class AxisMismatchError(ValueError):
    """Raised when the selected spectra don't share a common x-axis. See
    _build_matrix's docstring for why this refuses rather than resamples."""
    pass


class CosmicRayManager:

    def __init__(self):
        self.threshold      = 10.0   # modified Z-score threshold
        self.flagged        = {}     # {label: [x_indices]}
        self.n_replaced     = 0
        # Points on each side of a flagged position ALSO replaced (via
        # local interpolation — see _smooth_replace), in addition to the
        # flagged position itself. The modified Z-score reliably finds
        # the SHARPEST point of a cosmic ray, but a ray's shoulders —
        # adjacent points still visibly elevated, just not anomalous
        # enough to individually cross the threshold — are left
        # completely untouched at 0 (they were never flagged in the
        # first place, so there's nothing for the interpolation fix to
        # smooth), leaving a visible remnant right where the ray was.
        # Default is 1 rather than 0: in practice 0 often still shows
        # that remnant, while 1-2 reliably cleans it up without eating
        # into real spectral features on either side.
        self.replace_window = 1
        # Cached from the most recent _build_matrix() call, so callers
        # (the dialog's heatmap, in particular) can reuse the SAME matrix
        # this manager already built rather than rebuilding it themselves
        # — previously the dialog had its own, independent copy of the
        # "build matrix on a common x-grid" logic, using the same
        # exact-equality np.array_equal comparison this file used to have,
        # meaning the same bug existed in two disconnected places that
        # could silently drift out of sync with each other.
        self._x_ref  = None
        self._matrix = None
        self._labels = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def detect(self, spectra: list, threshold: float = None) -> dict:
        """
        Detect cosmic rays by cross-spectrum comparison.

        Parameters
        ----------
        spectra   : list of spectrum dicts with 'x_scale', 'y_scale', 'label'
        threshold : modified Z-score threshold (default: self.threshold)

        Returns
        -------
        dict {label: list_of_flagged_x_indices}

        Raises
        ------
        AxisMismatchError if the spectra don't share a common x-axis.
        """
        if threshold is not None:
            self.threshold = threshold
        if len(spectra) < 2:
            logger.warning("CosmicRayManager: need ≥2 spectra for cross comparison")
            return {}

        x_ref, matrix, labels = self._build_matrix(spectra)
        self.flagged = self._find_outliers(matrix, labels)
        return dict(self.flagged)

    def apply(self, spectra: list, threshold: float = None, replace_window: int = None,
              progress_callback=None) -> list:
        """
        Detect and replace cosmic rays. Returns new spectrum dicts.

        Replacement value: linear interpolation from this spectrum's own
        nearest clean neighbours (see _smooth_replace).

        progress_callback : optional callable, invoked every 50 spectra
            during the loop below — see
            src/modules/utils/progress_utils.py's notify_progress for the
            full reasoning; same hook/contract used by every other
            operation's manager in this codebase. None (the default) —
            no change from before.

        Raises
        ------
        AxisMismatchError if the spectra don't share a common x-axis.
        """
        eff_threshold = threshold if threshold is not None else self.threshold
        if replace_window is not None:
            self.replace_window = replace_window
        # Skip re-running detect() if it was already run for this exact
        # spectra set and threshold (e.g. the dialog's live preview just
        # computed it, and the user clicked Apply without changing
        # anything since). detect() is a pure function of (spectra,
        # threshold) — re-running it on unchanged input always produces
        # the identical result, so this cache check costs O(n_spectra)
        # (comparing labels) instead of the full O(n_spectra x n_points)
        # matrix rebuild + per-position statistics, which measured at
        # ~1-2 seconds for a 4675-spectrum, 1600-point dataset — a real,
        # if modest, saving. A genuine change (different threshold, or a
        # different/reordered selection) still correctly falls through to
        # a fresh detect() call below.
        if len(spectra) < 2:
            # detect() has nothing to compare against and builds no matrix;
            # without this check the loop below failed with a TypeError.
            raise ValueError(
                "Cosmic ray removal compares each spectrum with the others and "
                "needs at least 2 spectra.")
        cache_valid = (
            self._matrix is not None
            and self._labels == [s['label'] for s in spectra]
            and self.threshold == eff_threshold
        )
        if not cache_valid:
            self.detect(spectra, threshold)
        x_ref, matrix, labels = self._x_ref, self._matrix, self._labels

        result = []
        self.n_replaced = 0
        for i, s in enumerate(spectra):
            notify_progress(progress_callback, i)
            y_new = matrix[i].copy()
            indices = self.flagged.get(s['label'], [])
            replace_pixels = self._expand_window(indices, len(y_new), self.replace_window)
            y_new = self._smooth_replace(y_new, replace_pixels)
            self.n_replaced += len(replace_pixels)

            # No "interpolate back to original x-grid" step needed here —
            # _build_matrix() (called via detect() above) already
            # guarantees every spectrum's x-axis matches x_ref, or it
            # would have raised AxisMismatchError instead of reaching
            # this point. y_new is already on this spectrum's own axis.
            new_s = dict(s)
            new_s['y_scale'] = y_new

            if indices:
                # dict(s) above is a SHALLOW copy — new_s['metadata']
                # would still be the exact same dict object as the
                # original spectrum's metadata unless replaced here.
                # Writing into it directly would silently mutate the
                # ORIGINAL spectrum's metadata too (same bug found and
                # fixed in BaselineManager.apply_baseline_correction).
                new_s['metadata'] = dict(new_s.get('metadata') or {})
                # Shared, chronologically-ordered history across every
                # operation type that records one (SVD Background, Manual
                # Baseline, and this) — see correction_history.py. Only
                # spectra that actually had a point replaced get an
                # entry; a spectrum that was compared but had nothing
                # flagged wasn't corrected, so it gets no record, the same
                # reasoning as the affected-spectra filtering in
                # OperationsController.commit_cosmic_ray_removal.
                new_s['metadata']['correction_history'] = append_correction_history(
                    s.get('metadata'), 'Cosmic Ray Removal',
                    {
                        # Actual pixels replaced (may be wider than the
                        # number of flagged/detected positions if
                        # replace_window > 0) versus how many distinct
                        # cosmic rays were actually detected.
                        'points_replaced': len(replace_pixels),
                        'points_flagged': len(indices),
                        'replace_window': self.replace_window,
                        'threshold': self.threshold,
                        # The x-value at each flagged position is what
                        # actually tells a user WHERE on the spectrum a
                        # cosmic ray was found (e.g. "2815.7 cm-1") — the
                        # raw index alone only makes sense if you also know
                        # the axis. Rounded to a sensible number of
                        # significant figures for display rather than the
                        # raw float; kept alongside the index, not instead
                        # of it, in case anything downstream wants to
                        # re-derive the exact array position.
                        'flagged_x_positions': [round(float(x_ref[idx]), 4) for idx in sorted(indices)],
                        'flagged_x_indices': [int(idx) + 1 for idx in sorted(indices)],
                    }
                )

            result.append(new_s)

        logger.info("CosmicRayManager: replaced %d points across %d spectra",
                    self.n_replaced, len(spectra))
        return result

    def get_summary(self, spectra: list) -> dict:
        flagged_counts = {s['label']: len(self.flagged.get(s['label'], []))
                         for s in spectra}
        return {
            'total_spectra':        len(spectra),
            'spectra_with_rays':    sum(1 for n in flagged_counts.values() if n > 0),
            'total_flagged_points': sum(flagged_counts.values()),
            'details':              flagged_counts,
        }

    def preview_correction(self, label, replace_window=None):
        """Return (x_ref, y_original, y_corrected, flagged_indices) for a
        single already-detected spectrum, without needing a full apply()
        call across every spectrum.

        Lets the dialog show what a correction WOULD look like — using
        whichever replace_window is currently set in the UI — before
        anything is actually applied. Requires detect() to have already
        been run (returns None if not, or if *label* wasn't part of that
        detection).
        """
        if self._matrix is None or label not in self._labels:
            return None
        i = self._labels.index(label)
        y_original = self._matrix[i].copy()
        indices = self.flagged.get(label, [])
        window = self.replace_window if replace_window is None else replace_window
        replace_pixels = self._expand_window(indices, len(y_original), window)
        y_corrected = self._smooth_replace(y_original, replace_pixels)
        return self._x_ref, y_original, y_corrected, indices

    @staticmethod
    def _expand_window(indices, n_wl, window=None):
        """Expand each flagged index into [idx - window, idx + window]
        (clamped to the spectrum's bounds), merging overlapping ranges.
        Shared by apply() and preview_correction() so both always treat
        the replacement window identically."""
        pixels = set()
        for idx in indices:
            lo = max(0, idx - window) if window else idx
            hi = min(n_wl - 1, idx + window) if window else idx
            pixels.update(range(lo, hi + 1))
        return pixels

    @staticmethod
    def _smooth_replace(y, replace_pixels):
        """Replace each pixel in replace_pixels with linear interpolation
        between the nearest CLEAN (non-replaced) neighbours in y's own
        trace — guarantees a smooth continuation of THIS spectrum's own
        local trend. Mirrors SpikeRemovalManager._interpolate_spikes.

        Previously each replaced pixel was set to the cross-spectrum group
        median at that exact x-position instead. Two confirmed problems
        with that: (1) the group median is only a reliable reference where
        a genuine majority of the group is actually clean at that
        position — not guaranteed on a large dataset, where multiple
        spectra can have cosmic rays overlapping the same region; (2) a
        wide cosmic ray's tapering edges can leave isolated points just
        under the detection threshold even while still visibly elevated,
        and widening replace_window doesn't reliably bridge such a gap —
        it only expands around indices that were already flagged. Either
        way, the result was a visible discontinuity right where the
        un-replaced (or median-mismatched) pixels sat among otherwise
        "corrected" neighbours — exactly the deformed/zigzag artifact this
        replaces. Local interpolation depends only on this spectrum's own
        real values on either side of the replaced region, so it can't
        produce that kind of artifact and naturally bridges any gap.
        """
        y_out = y.copy()
        n = len(y_out)
        for px in sorted(replace_pixels):
            lo = px - 1
            while lo >= 0 and lo in replace_pixels:
                lo -= 1
            hi = px + 1
            while hi < n and hi in replace_pixels:
                hi += 1
            if lo < 0 and hi >= n:
                continue   # entire spectrum flagged — nothing to interpolate from
            elif lo < 0:
                y_out[px] = y_out[hi]
            elif hi >= n:
                y_out[px] = y_out[lo]
            else:
                t = (px - lo) / (hi - lo)
                y_out[px] = y_out[lo] * (1 - t) + y_out[hi] * t
        return y_out

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _build_matrix(self, spectra):
        """Build (n_spectra x n_wl) matrix on the shared x-grid.

        Every spectrum must already share the same x-axis (within
        axes_match's tolerance for float round-off) — raises
        AxisMismatchError otherwise, rather than silently resampling.

        This used to silently np.interp() any spectrum whose axis wasn't
        an EXACT bit-for-bit match (np.array_equal) onto the first
        spectrum's grid. Two problems with that, proved directly:
        (1) exact equality is the wrong test — two axes that are
        genuinely the same but differ by float round-off (e.g. one
        rebuilt arithmetically) would be needlessly resampled; (2) far
        more seriously, np.interp() does not extrapolate — for any x
        position outside a spectrum's own measured range, it silently
        holds the nearest edge value flat instead. That fabricated,
        flat-clamped value then went straight into the SAME matrix used
        to compute the group's median and MAD at every x-position — the
        exact statistics this whole algorithm uses to decide what counts
        as a cosmic ray. A spectrum with a genuinely narrower measured
        range didn't just get bad values for itself; it quietly skewed
        the cosmic-ray determination for every OTHER spectrum near those
        edges too, silently, with no indication anything was wrong.

        Cross-spectrum comparison fundamentally requires a real,
        measured value from every spectrum at every compared position —
        there's no valid non-destructive way to compare spectra that
        don't already share an axis, the same reasoning already applied
        to Combine Spectra, 2D Correlation, and every other operation in
        this app that stacks multiple spectra into one comparison.
        """
        first_x = np.asarray(spectra[0]['x_scale'], dtype=float)
        x_ref = first_x[::-1].copy() if first_x[0] > first_x[-1] else first_x.copy()

        rows   = []
        labels = []
        for s in spectra:
            x = np.asarray(s['x_scale'], dtype=float)
            y = np.asarray(s['y_scale'], dtype=float)
            if x[0] > x[-1]:
                x, y = x[::-1], y[::-1]
            if not axes_match(x, x_ref):
                raise AxisMismatchError(
                    "Cosmic ray removal requires every selected spectrum to "
                    "share the same x-axis (it compares each spectrum "
                    "against the others at every x-position).\n\n"
                    + describe_axis_mismatch(spectra[0], s, 'cosmic ray removal')
                )
            rows.append(y)
            labels.append(s['label'])

        matrix = np.array(rows, dtype=float)
        self._x_ref, self._matrix, self._labels = x_ref, matrix, labels
        return x_ref, matrix, labels

    def _find_outliers(self, matrix, labels):
        """
        For each x-position, compute modified Z-score across spectra.
        Return {label: [flagged_x_indices]}.
        """
        n_spec, n_wl = matrix.shape
        med = np.median(matrix, axis=0)      # (n_wl,)
        mad = np.median(np.abs(matrix - med), axis=0)  # (n_wl,)

        # Avoid division by zero at flat positions
        safe_mad = np.where(mad < 1e-12, 1.0, mad)
        Z = 0.6745 * (matrix - med) / safe_mad  # (n_spec × n_wl)

        flagged = {lbl: [] for lbl in labels}
        outlier_mask = np.abs(Z) > self.threshold
        for i, lbl in enumerate(labels):
            flagged[lbl] = list(np.where(outlier_mask[i])[0])

        return flagged
