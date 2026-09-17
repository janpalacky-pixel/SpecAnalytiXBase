# src/modules/visualization_analysis/map2d_manager.py

import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match, describe_axis_mismatch

logger = get_logger(__name__)


class Map2DManager:
    """
    Business logic for the 2-D spectral map feature.

    Responsibilities
    ----------------
    * Validate map dimensions (m × n == N spectra).
    * Compute per-spectrum scalar values via three intensity metrics
      (integral, mean, variance) applied to spectral ranges.
    * Compute per-spectrum SVD coefficients (Vt row k) from the same
      range-filtered spectra and return U[:, k] (subspectrum profile)
      alongside the coefficient map.
    * Same idea for NMF and MCR-ALS: range-filter, hand the result to
      NMFManager / MCRALSManager (the same classes the standalone NMF
      Analysis / MCR-ALS tools use, so this is never a second
      implementation to keep in sync by hand), and reshape one
      component's per-pixel score into a map. get_n_components(),
      get_component_subspectrum(), get_component_coefficients() and
      get_component_explained_variance() accept a `kind` of 'svd',
      'nmf' or 'mcr' and dispatch accordingly, so dialog code that
      wants to work with "whichever decomposition is active" doesn't
      need three separate near-identical call sites.
    * Reshape flat per-spectrum arrays into (n_rows, n_cols) grids ready
      for imshow / contourf.
    """

    # ------------------------------------------------------------------ #
    # Construction                                                         #
    # ------------------------------------------------------------------ #

    def __init__(self):
        self.map_data = None          # 2-D numpy array (n_rows × n_cols)
        self.n_rows = None
        self.n_cols = None
        self.metric = "Integral"      # "Integral" | "Mean" | "Variance"
        self.map_mode = "intensity"   # "intensity" | "svd"
        self.svd_component = 0        # 0-based index of Vt row to display
        self.subspectrum_x = None     # x-axis of the SVD subspectrum profile
        self.subspectrum_y = None     # U[:, k] values

        # SVD internals (populated by compute_svd_map)
        self._U = None
        self._s = None
        self._Vt = None
        self._svd_x_axis = None
        self._explained_variance = None

        # PCA internals (populated by compute_pca_map). PCA here is SVD
        # with mean-centering applied first (see PcaScoresManager /
        # SVDBackgroundManager's mean_center option) — kept as its own
        # separate set of arrays rather than reusing the SVD ones above,
        # for the same reason NMF/MCR-ALS get their own storage below.
        self._pca_U = None
        self._pca_s = None
        self._pca_Vt = None
        self._pca_x_axis = None
        self._pca_explained_variance = None
        self._pca_mean_spectrum = None

        # NMF / MCR-ALS internals (populated by compute_nmf_map /
        # compute_mcr_map). Each holds the actual NMFManager /
        # MCRALSManager instance from the fit — not just the arrays —
        # so get_component_* below can read straight from it, the same
        # way the standalone NMF Analysis / MCR-ALS dialogs do.
        self._nmf_manager = None
        self._mcr_manager = None
        # (n_runs, n_in_near_best_pool, consensus) from the last
        # compute_nmf_map()/compute_mcr_map() call, or None if that
        # call was a plain single fit (n_runs=1) — see _pick_best_of_n.
        self._nmf_run_info = None
        self._mcr_run_info = None

    # ------------------------------------------------------------------ #
    # Dimension validation                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def validate_dimensions(n_spectra: int, n_rows: int, n_cols: int) -> bool:
        """Return True if n_rows * n_cols == n_spectra (and both > 0)."""
        return n_rows > 0 and n_cols > 0 and n_rows * n_cols == n_spectra

    @staticmethod
    def _match_similarity(A, B):
        """Average best-matched absolute correlation between two sets of
        component rows (e.g. two H or ST matrices from two separate
        fits) — used to judge whether two candidate solutions agree with
        each other structurally. Same one-to-one best-matching logic as
        nmf_dialog.py / mcr_als_dialog.py's own "Run N times, keep best".
        """
        n = A.shape[0]
        used = set()
        total = 0.0
        for k in range(n):
            best_j, best_c = None, -2
            for j in range(n):
                if j in used:
                    continue
                length = min(A.shape[1], B.shape[1])
                c = np.corrcoef(A[k, :length], B[j, :length])[0, 1]
                if np.isnan(c):
                    c = 0.0
                if abs(c) > best_c:
                    best_c, best_j = abs(c), j
            used.add(best_j)
            total += best_c
        return total / n

    @classmethod
    def _pick_best_of_n(cls, trials, shape_matrices):
        """Given a list of (lof, mgr) trials, return (best_mgr, consensus, pool).

        Doesn't just keep the single lowest-LOF run: with a genuinely
        noisy fit, the absolute best LOF can belong to a solution that
        fits this particular noise realization marginally better than
        several other, essentially-as-good solutions, while representing
        a different (wrong) rotation of the components. Instead, take the
        pool of near-best runs (within 2% of the best LOF) and keep
        whichever is most representative of that pool (highest average
        structural agreement with the others in it) — same policy as the
        standalone NMF Analysis / MCR-ALS "Run N times, keep best".

        shape_matrices : callable(mgr) -> 2-D array of component rows
            (mgr.H for NMF, mgr.ST for MCR-ALS) used for the agreement check.

        consensus is None when the pool has only one member (nothing to
        compare against).
        """
        best_lof = min(lof for lof, _ in trials)
        near_best_tol = 0.02   # within 2% of the best LOF
        pool = [(lof, mgr) for lof, mgr in trials
                if lof <= best_lof * (1 + near_best_tol)]
        if len(pool) == 1:
            return pool[0][1], None, pool
        agreement = []
        for i, (_, mgr_i) in enumerate(pool):
            scores = [cls._match_similarity(shape_matrices(mgr_i), shape_matrices(mgr_j))
                      for j, (_, mgr_j) in enumerate(pool) if j != i]
            agreement.append(np.mean(scores))
        best_idx = int(np.argmax(agreement))
        return pool[best_idx][1], agreement[best_idx], pool

    @staticmethod
    def factor_pairs(n: int):
        """
        Return all (a, b) pairs with a <= b and a*b == n, sorted by a.
        Useful for suggesting valid dimension combinations to the user.
        """
        pairs = []
        for a in range(1, int(n ** 0.5) + 1):
            if n % a == 0:
                pairs.append((a, n // a))
        return pairs

    # ------------------------------------------------------------------ #
    # Spectral range helpers (mirrors SpectralRangeController logic)      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _apply_range_filter(x, y, x_min, x_max, include_ranges, exclude_ranges):
        """
        Return (x_filtered, y_filtered) after applying the same include/exclude
        logic used by SpectralRangeManager.

        Parameters
        ----------
        x, y          : numpy arrays – spectrum data
        x_min, x_max  : global clip limits (None = no clip)
        include_ranges: list of [start, end] to *keep* (include mode)
        exclude_ranges: list of [start, end] to *remove* (exclude mode)

        The caller may pass either include_ranges OR exclude_ranges (not both);
        the caller decides which list is active based on is_exclude_mode.
        """
        if len(x) == 0:
            return x.copy(), y.copy()

        # Global clip
        if x_min is not None and x_max is not None:
            mask = (x >= x_min) & (x <= x_max)
            x, y = x[mask], y[mask]
            if len(x) == 0:
                return x, y

        # Range mask
        active_ranges = include_ranges or exclude_ranges
        is_exclude = bool(exclude_ranges)

        if active_ranges:
            bit = np.zeros(len(x), dtype=bool)
            for start, end in active_ranges:
                lo, hi = min(start, end), max(start, end)
                bit |= (x >= lo) & (x <= hi)
            if is_exclude:
                bit = ~bit
            x, y = x[bit], y[bit]

        return x, y

    # ------------------------------------------------------------------ #
    # Intensity-metric map                                                 #
    # ------------------------------------------------------------------ #

    def compute_intensity_map(self, spectra, n_rows, n_cols,
                              metric="Integral",
                              x_min=None, x_max=None,
                              include_ranges=None, exclude_ranges=None,
                              x_val=None):
        """
        Compute a 2-D map using a scalar intensity metric.

        Parameters
        ----------
        spectra        : list of spectrum dicts (x_scale, y_scale, label)
        n_rows, n_cols : map dimensions
        metric         : "Integral" | "Mean" | "Variance"
        x_min, x_max   : global spectral clip (None = no clip)
        include_ranges : list of [start, end] to keep (None = no ranges)
        exclude_ranges : list of [start, end] to exclude (None = no ranges)

        Returns
        -------
        numpy.ndarray of shape (n_rows, n_cols), or None on error.
        """
        if not self.validate_dimensions(len(spectra), n_rows, n_cols):
            logger.error("Map2DManager: dimension mismatch %d × %d ≠ %d",
                         n_rows, n_cols, len(spectra))
            return None

        include_ranges = include_ranges or []
        exclude_ranges = exclude_ranges or []

        values = np.empty(len(spectra))
        for i, sp in enumerate(spectra):
            x = np.asarray(sp['x_scale'], dtype=float)
            y = np.asarray(sp['y_scale'], dtype=float)
            xf, yf = self._apply_range_filter(
                x, y, x_min, x_max, include_ranges, exclude_ranges)

            if len(yf) == 0:
                values[i] = np.nan
                continue

            if metric == "Integral":
                values[i] = np.trapz(yf, xf) if len(xf) > 1 else yf[0]
            elif metric == "Mean":
                values[i] = np.mean(yf)
            elif metric == "Variance":
                values[i] = np.var(yf)
            elif metric == "Peak intensity":
                values[i] = np.max(yf)
            elif metric == "Peak position":
                values[i] = float(xf[np.argmax(yf)]) if len(xf) > 0 else np.nan
            elif metric == "FWHM":
                values[i] = self._compute_fwhm(xf, yf)
            elif metric == "Baseline-corrected integral":
                values[i] = self._baseline_corrected_integral(xf, yf)
            elif metric == "Intensity at x":
                # Use the FULL x/y arrays (not range-clipped xf/yf) so that
                # both Band A and Band B always interpolate from identical data.
                # Range clipping is meaningful for integrals but not for point
                # interpolation — using different clips on A and B with the
                # same x_val would give different bracket points and A/B ≠ 1.
                xp = np.asarray(sp.get('original_x_scale', sp['x_scale']), dtype=float)
                yp = np.asarray(sp.get('original_y_scale', sp['y_scale']), dtype=float)
                if x_val is not None and len(xp) >= 2:
                    x_lo, x_hi = min(xp[0], xp[-1]), max(xp[0], xp[-1])
                    if x_lo <= x_val <= x_hi:
                        if xp[0] > xp[-1]:
                            values[i] = float(np.interp(x_val, xp[::-1], yp[::-1]))
                        else:
                            values[i] = float(np.interp(x_val, xp, yp))
                    else:
                        values[i] = np.nan
                elif x_val is not None and len(xp) == 1:
                    values[i] = yp[0]
                else:
                    values[i] = np.nan
            else:
                values[i] = np.mean(yf)

        self.map_data = values.reshape(n_rows, n_cols)
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.metric = metric
        self.map_mode = "intensity"
        self.subspectrum_x = None
        self.subspectrum_y = None
        logger.debug("Map2DManager: intensity map computed (%d×%d, metric=%s)",
                     n_rows, n_cols, metric)
        return self.map_data

    @staticmethod
    def _compute_fwhm(x, y):
        """Full width at half maximum of the dominant peak in (x, y).

        Returns the FWHM in x-axis units, or NaN if it cannot be determined.
        The half-maximum is defined relative to the minimum baseline within
        the range, so the metric is robust to a sloped background.
        """
        if len(y) < 3:
            return np.nan
        y_min  = np.min(y)
        y_max  = np.max(y)
        half   = y_min + (y_max - y_min) / 2.0
        peak_i = int(np.argmax(y))

        # Walk left from peak to find half-max crossing. for-else here
        # deliberately distinguishes "found a real crossing" from "walked
        # all the way to the edge of the data without ever descending to
        # half-max" — the two are NOT the same thing, and conflating them
        # (as this used to) meant a peak sitting close to the edge of the
        # selected range would silently have its own position treated as
        # if it were a genuine crossing, producing a confidently wrong
        # FWHM (verified: a peak with a true FWHM of ~7.06 whose left side
        # was clipped by the range selection came out as ~3.58 — roughly
        # half — instead of correctly reporting "cannot be determined").
        left_i = peak_i
        for k in range(peak_i, -1, -1):
            if y[k] <= half:
                left_i = k
                break
        else:
            return np.nan   # never descended to half-max on the left

        # Walk right from peak
        right_i = peak_i
        for k in range(peak_i, len(y)):
            if y[k] <= half:
                right_i = k
                break
        else:
            return np.nan   # never descended to half-max on the right

        if left_i == right_i:
            return np.nan
        # Linear interpolation for sub-pixel accuracy
        try:
            # Left crossing
            if left_i < peak_i:
                x_left = np.interp(half, [y[left_i], y[left_i + 1]],
                                         [x[left_i], x[left_i + 1]])
            else:
                x_left = x[left_i]
            # Right crossing
            if right_i > peak_i:
                x_right = np.interp(half, [y[right_i], y[right_i - 1]],
                                          [x[right_i], x[right_i - 1]])
            else:
                x_right = x[right_i]
            fwhm = abs(x_right - x_left)
            return fwhm if fwhm > 0 else np.nan
        except Exception:
            return np.nan

    @staticmethod
    def _baseline_corrected_integral(x, y):
        """Integral after subtracting the straight-line baseline connecting
        the first and last points of the filtered range.

        This is equivalent to the area between the spectrum and the chord,
        and is more robust than raw integral when the background level varies
        across the map.
        """
        if len(x) < 2:
            return float(y[0]) if len(y) else np.nan
        # Straight line from (x[0], y[0]) to (x[-1], y[-1])
        baseline = y[0] + (y[-1] - y[0]) * (x - x[0]) / (x[-1] - x[0])
        return np.trapz(y - baseline, x)

    # ------------------------------------------------------------------ #
    # Map arithmetic                                                       #
    # ------------------------------------------------------------------ #

    def compute_arithmetic_map(self, spectra, n_rows, n_cols,
                               metric_a="Integral", metric_b="Integral",
                               x_min_a=None, x_max_a=None,
                               include_ranges_a=None, exclude_ranges_a=None,
                               x_val_a=None,
                               x_min_b=None, x_max_b=None,
                               include_ranges_b=None, exclude_ranges_b=None,
                               x_val_b=None,
                               operation="A / B"):
        """Compute a pixel-wise arithmetic combination of two band maps.

        Parameters
        ----------
        spectra              : list of spectrum dicts
        n_rows, n_cols       : map dimensions
        metric_a / metric_b  : metric string for band A / B
        x_min/x_max_a/b      : global clip for band A / B
        include/exclude_a/b  : range filters for band A / B
        x_val_a/b            : x-value for "Intensity at x" metric
        operation            : "A / B" | "A - B" | "A + B" | "A × B"

        Returns
        -------
        numpy.ndarray of shape (n_rows, n_cols), or None on error.
        """
        if not self.validate_dimensions(len(spectra), n_rows, n_cols):
            logger.error("Map2DManager: arithmetic dimension mismatch")
            return None

        map_a = self.compute_intensity_map(
            spectra, n_rows, n_cols,
            metric=metric_a,
            x_min=x_min_a, x_max=x_max_a,
            include_ranges=include_ranges_a or [],
            exclude_ranges=exclude_ranges_a or [],
            x_val=x_val_a,
        )
        if map_a is None:
            return None

        map_b = self.compute_intensity_map(
            spectra, n_rows, n_cols,
            metric=metric_b,
            x_min=x_min_b, x_max=x_max_b,
            include_ranges=include_ranges_b or [],
            exclude_ranges=exclude_ranges_b or [],
            x_val=x_val_b,
        )
        if map_b is None:
            return None

        with np.errstate(divide='ignore', invalid='ignore'):
            if operation == "A / B":
                result = np.where(map_b != 0, map_a / map_b, np.nan)
            elif operation == "A - B":
                result = map_a - map_b
            elif operation == "A + B":
                result = map_a + map_b
            elif operation == "A × B":
                result = map_a * map_b
            else:
                logger.error("Unknown arithmetic operation: %s", operation)
                return None

        self.map_data  = result
        self.n_rows    = n_rows
        self.n_cols    = n_cols
        self.map_mode  = "arithmetic"
        self.subspectrum_x = None
        self.subspectrum_y = None
        logger.debug("Map2DManager: arithmetic map computed (%s, %d×%d)",
                     operation, n_rows, n_cols)
        return result

    def compute_svd_map(self, spectra, n_rows, n_cols,
                        component_index=0,
                        x_min=None, x_max=None,
                        include_ranges=None, exclude_ranges=None):
        """
        Compute a 2-D map from SVD coefficient V[component_index, :].

        The spectra are first filtered to the selected spectral range, then
        SVD is computed on the resulting data matrix.

        Also stores the corresponding subspectrum (U[:, component_index]) for
        side-by-side display.

        Parameters
        ----------
        spectra         : list of spectrum dicts
        n_rows, n_cols  : map dimensions
        component_index : 0-based SVD component index
        x_min, x_max    : global clip limits
        include_ranges  : include-mode ranges
        exclude_ranges  : exclude-mode ranges

        Returns
        -------
        numpy.ndarray of shape (n_rows, n_cols), or None on error.
        """
        if not self.validate_dimensions(len(spectra), n_rows, n_cols):
            logger.error("Map2DManager: dimension mismatch %d × %d ≠ %d",
                         n_rows, n_cols, len(spectra))
            return None

        include_ranges = include_ranges or []
        exclude_ranges = exclude_ranges or []

        # --- filter spectra to selected ranges -------------------------
        filtered_y = []
        filtered_x = None
        reference_sp = None
        for sp in spectra:
            x = np.asarray(sp['x_scale'], dtype=float)
            y = np.asarray(sp['y_scale'], dtype=float)
            xf, yf = self._apply_range_filter(
                x, y, x_min, x_max, include_ranges, exclude_ranges)
            if filtered_x is None:
                filtered_x = xf
                reference_sp = sp
            elif len(xf) == len(filtered_x) and not axes_match(xf, filtered_x):
                # Same length, but NOT the same x-axis — the length-only
                # check below wouldn't catch this at all. SVD fundamentally
                # requires every spectrum to be on the same x-grid (it's
                # finding components shared ACROSS the whole batch); combining
                # mismatched spectra means comparing unrelated wavenumber
                # positions point-by-point, producing meaningless components
                # with no error or warning. Verified directly with two
                # same-length, x-offset spectra combining silently before
                # this check existed.
                logger.error(
                    "Map2DManager: cannot compute SVD map — spectra don't "
                    "share a common x-axis.\n%s",
                    describe_axis_mismatch(reference_sp, sp, 'SVD map')
                )
                return None
            filtered_y.append(yf)

        if filtered_x is None or len(filtered_x) == 0:
            logger.error("Map2DManager: no data points remain after filtering")
            return None

        # Check consistent lengths
        lengths = [len(y) for y in filtered_y]
        if len(set(lengths)) > 1:
            logger.error("Map2DManager: spectra have different lengths after "
                         "filtering (%s) – linearization required", set(lengths))
            return None

        # Build data matrix (n_wavelengths × n_spectra)
        try:
            data_matrix = np.column_stack(filtered_y)
        except ValueError as exc:
            logger.error("Map2DManager: cannot stack filtered spectra: %s", exc)
            return None

        # --- SVD -------------------------------------------------------
        try:
            U, s, Vt = np.linalg.svd(data_matrix, full_matrices=False)
        except np.linalg.LinAlgError as exc:
            logger.error("Map2DManager: SVD failed: %s", exc)
            return None

        self._U = U
        self._s = s
        self._Vt = Vt
        self._svd_x_axis = filtered_x
        self._explained_variance = (s ** 2) / np.sum(s ** 2) * 100

        n_components = U.shape[1]
        component_index = max(0, min(component_index, n_components - 1))

        # Coefficients for this component (length == n_spectra)
        coefficients = Vt[component_index, :]

        # Store subspectrum for display
        self.subspectrum_x = filtered_x
        self.subspectrum_y = U[:, component_index]

        self.map_data = coefficients.reshape(n_rows, n_cols)
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.svd_component = component_index
        self.map_mode = "svd"

        ev = self._explained_variance[component_index]
        logger.debug("Map2DManager: SVD map computed (%d×%d, component=%d, EV=%.2f%%)",
                     n_rows, n_cols, component_index + 1, ev)
        return self.map_data

    def compute_pca_map(self, spectra, n_rows, n_cols,
                        component_index=0,
                        x_min=None, x_max=None,
                        include_ranges=None, exclude_ranges=None):
        """
        Compute a 2-D map from PCA coefficient V[component_index, :].

        Identical to compute_svd_map() except the data matrix is
        mean-centered (per-wavelength average across the selected
        spectra subtracted) before the SVD — the standard PCA
        convention, matching PcaScoresManager.compute_svd()
        (mean_center=True by default there) and
        SVDBackgroundManager.compute_svd_from_spectra's mean_center
        option. PCA needs no iterative fit settings and has no
        rotational ambiguity (unlike NMF/MCR-ALS), so — like SVD —
        this is a plain, one-shot linear-algebra call with component
        browsing, not a fit-then-browse workflow.

        Kept as its own method (duplicating compute_svd_map's filtering
        logic) rather than adding a mean_center flag to that method —
        compute_svd_map is working, tested code, and every existing SVD
        map call site should keep behaving exactly as before.

        Parameters
        ----------
        spectra         : list of spectrum dicts
        n_rows, n_cols  : map dimensions
        component_index : 0-based PCA component index
        x_min, x_max    : global clip limits
        include_ranges  : include-mode ranges
        exclude_ranges  : exclude-mode ranges

        Returns
        -------
        numpy.ndarray of shape (n_rows, n_cols), or None on error.
        """
        if not self.validate_dimensions(len(spectra), n_rows, n_cols):
            logger.error("Map2DManager: dimension mismatch %d × %d ≠ %d",
                         n_rows, n_cols, len(spectra))
            return None

        include_ranges = include_ranges or []
        exclude_ranges = exclude_ranges or []

        # --- filter spectra to selected ranges -------------------------
        filtered_y = []
        filtered_x = None
        reference_sp = None
        for sp in spectra:
            x = np.asarray(sp['x_scale'], dtype=float)
            y = np.asarray(sp['y_scale'], dtype=float)
            xf, yf = self._apply_range_filter(
                x, y, x_min, x_max, include_ranges, exclude_ranges)
            if filtered_x is None:
                filtered_x = xf
                reference_sp = sp
            elif len(xf) == len(filtered_x) and not axes_match(xf, filtered_x):
                # Same rationale as compute_svd_map's identical check —
                # see its comment for the full explanation.
                logger.error(
                    "Map2DManager: cannot compute PCA map — spectra don't "
                    "share a common x-axis.\n%s",
                    describe_axis_mismatch(reference_sp, sp, 'PCA map')
                )
                return None
            filtered_y.append(yf)

        if filtered_x is None or len(filtered_x) == 0:
            logger.error("Map2DManager: no data points remain after filtering")
            return None

        lengths = [len(y) for y in filtered_y]
        if len(set(lengths)) > 1:
            logger.error("Map2DManager: spectra have different lengths after "
                         "filtering (%s) – linearization required", set(lengths))
            return None

        try:
            data_matrix = np.column_stack(filtered_y)
        except ValueError as exc:
            logger.error("Map2DManager: cannot stack filtered spectra: %s", exc)
            return None

        # --- mean-center (the PCA convention), then SVD -----------------
        mean_spectrum = data_matrix.mean(axis=1)
        data_matrix = data_matrix - mean_spectrum[:, np.newaxis]

        try:
            U, s, Vt = np.linalg.svd(data_matrix, full_matrices=False)
        except np.linalg.LinAlgError as exc:
            logger.error("Map2DManager: PCA (mean-centered SVD) failed: %s", exc)
            return None

        self._pca_U = U
        self._pca_s = s
        self._pca_Vt = Vt
        self._pca_x_axis = filtered_x
        self._pca_mean_spectrum = mean_spectrum
        self._pca_explained_variance = (s ** 2) / np.sum(s ** 2) * 100

        n_components = U.shape[1]
        component_index = max(0, min(component_index, n_components - 1))

        coefficients = Vt[component_index, :]

        # Store subspectrum for display
        self.subspectrum_x = filtered_x
        self.subspectrum_y = U[:, component_index]

        self.map_data = coefficients.reshape(n_rows, n_cols)
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.map_mode = "pca"

        ev = self._pca_explained_variance[component_index]
        logger.debug("Map2DManager: PCA map computed (%d×%d, component=%d, EV=%.2f%%)",
                     n_rows, n_cols, component_index + 1, ev)
        return self.map_data

    # ------------------------------------------------------------------ #
    # NMF / MCR-ALS maps                                                   #
    # ------------------------------------------------------------------ #


    def _filter_spectra_for_decomposition(self, spectra, x_min, x_max,
                                           include_ranges, exclude_ranges):
        """
        Range-filter every spectrum in *spectra*, using the exact same
        per-spectrum filtering (_apply_range_filter) and cross-spectrum
        axis-consistency check compute_svd_map uses — but return a new
        list of spectrum dicts rather than a bare matrix, since that's
        the shape NMFManager.compute() / MCRALSManager.compute() expect
        (both are reused unmodified from the standalone NMF Analysis /
        MCR-ALS tools, not reimplemented here).

        Deliberately separate from compute_svd_map's own inline filtering
        loop rather than a shared refactor of it: compute_svd_map is
        working, tested code, and duplicating a dozen lines here is a
        smaller risk than touching it.

        Returns None (after logging the reason) if the spectra don't
        share a common x-axis after filtering, or nothing remains.
        """
        filtered = []
        filtered_x = None
        reference_sp = None
        for sp in spectra:
            x = np.asarray(sp['x_scale'], dtype=float)
            y = np.asarray(sp['y_scale'], dtype=float)
            xf, yf = self._apply_range_filter(
                x, y, x_min, x_max, include_ranges, exclude_ranges)
            if filtered_x is None:
                filtered_x = xf
                reference_sp = sp
            elif len(xf) == len(filtered_x) and not axes_match(xf, filtered_x):
                logger.error(
                    "Map2DManager: cannot compute map — spectra don't "
                    "share a common x-axis.\n%s",
                    describe_axis_mismatch(reference_sp, sp, 'component map')
                )
                return None
            filtered.append({
                'label': sp.get('label', ''),
                'x_scale': xf,
                'y_scale': yf,
                'metadata': sp.get('metadata', {}),
            })

        if filtered_x is None or len(filtered_x) == 0:
            logger.error("Map2DManager: no data points remain after filtering")
            return None

        lengths = {len(s['y_scale']) for s in filtered}
        if len(lengths) > 1:
            logger.error("Map2DManager: spectra have different lengths after "
                         "filtering (%s) – linearization required", lengths)
            return None

        return filtered

    def compute_nmf_map(self, spectra, n_rows, n_cols, n_components,
                        component_index=0,
                        x_min=None, x_max=None,
                        include_ranges=None, exclude_ranges=None,
                        init='nndsvda', max_iter=500, random_state=42,
                        n_runs=1, references=None, fix_references=False):
        """
        Compute a 2-D map from the NMF score W[:, component_index] — the
        same role Vt[component_index, :] plays in compute_svd_map —
        reshaped to the map's own (n_rows, n_cols) grid.

        The spectra are first filtered to the selected spectral range
        (see _filter_spectra_for_decomposition), then the actual fit is
        delegated to NMFManager — the same class the standalone NMF
        Analysis tool uses — so this mode's math is identical to (and
        stays in sync with) that tool's, rather than a second
        implementation to keep consistent by hand.

        Parameters
        ----------
        spectra         : list of spectrum dicts
        n_rows, n_cols  : map dimensions
        n_components    : number of NMF components to fit
        component_index : 0-based component whose score becomes the map
        x_min, x_max    : global clip limits
        include_ranges  : include-mode ranges
        exclude_ranges  : exclude-mode ranges
        init, max_iter, random_state : passed straight through to
            NMFManager.compute() (ignored when n_runs > 1 — see below)
        n_runs : if > 1, run the fit this many times with init='random'
            and a different seed each time, then keep whichever run is
            most representative of the near-best group — same "Run N
            times, keep best" policy as the standalone NMF Analysis tool.
            get_last_run_info('nmf') reports (n_runs, pool_size, consensus)
            afterward.
        references, fix_references : passed straight through to
            NMFManager.compute() on every trial.

        Returns
        -------
        numpy.ndarray of shape (n_rows, n_cols), or None on error/failure
        (NMFManager.last_error carries the reason for a fit failure).
        """
        if not self.validate_dimensions(len(spectra), n_rows, n_cols):
            logger.error("Map2DManager: dimension mismatch %d × %d ≠ %d",
                         n_rows, n_cols, len(spectra))
            return None

        filtered = self._filter_spectra_for_decomposition(
            spectra, x_min, x_max, include_ranges or [], exclude_ranges or [])
        if filtered is None:
            return None

        from src.modules.visualization_analysis.nmf_manager import NMFManager

        self._nmf_run_info = None
        if n_runs <= 1:
            mgr = NMFManager()
            ok = mgr.compute(filtered, n_components, init=init,
                             max_iter=max_iter, random_state=random_state,
                             references=references or {},
                             fix_references=fix_references)
            if not ok:
                logger.error("Map2DManager: NMF failed: %s", mgr.last_error)
                return None
        else:
            trials = []
            last_error = None
            for i in range(n_runs):
                trial_mgr = NMFManager()
                trial_ok = trial_mgr.compute(
                    filtered, n_components, init='random',
                    max_iter=max_iter, random_state=i,
                    references=references or {},
                    fix_references=fix_references)
                if trial_ok:
                    trials.append((trial_mgr.lof, trial_mgr))
                else:
                    last_error = trial_mgr.last_error
            if not trials:
                logger.error("Map2DManager: all %d NMF trials failed: %s",
                             n_runs, last_error)
                self._nmf_manager = None
                return None
            mgr, consensus, pool = self._pick_best_of_n(
                trials, shape_matrices=lambda m: m.H)
            self._nmf_run_info = (n_runs, len(pool), consensus)

        self._nmf_manager = mgr
        n_actual = mgr.W.shape[1]
        component_index = max(0, min(component_index, n_actual - 1))

        self.map_data = mgr.W[:, component_index].reshape(n_rows, n_cols)
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.map_mode = "nmf"

        logger.debug(
            "Map2DManager: NMF map computed (%d×%d, component=%d, EV=%.2f%%)",
            n_rows, n_cols, component_index + 1,
            mgr.explained_variance[component_index])
        return self.map_data

    def compute_mcr_map(self, spectra, n_rows, n_cols, n_components,
                        component_index=0,
                        x_min=None, x_max=None,
                        include_ranges=None, exclude_ranges=None,
                        init='svd', max_iterations=100, tol=0.01,
                        c_nonneg=True, st_nonneg=True,
                        normalize_spectra=True, closure=False,
                        random_state=42,
                        n_runs=1, references=None, fix_references=False):
        """
        Compute a 2-D map from the MCR-ALS concentration profile
        C[:, component_index] — the same role Vt[component_index, :]
        plays in compute_svd_map — reshaped to the map's own
        (n_rows, n_cols) grid.

        Same pattern as compute_nmf_map: filter to the selected range,
        then delegate the actual fit to MCRALSManager (the class the
        standalone MCR-ALS tool uses) rather than reimplementing it.

        Parameters
        ----------
        spectra         : list of spectrum dicts
        n_rows, n_cols  : map dimensions
        n_components    : number of components to resolve
        component_index : 0-based component whose concentration profile
            becomes the map
        x_min, x_max    : global clip limits
        include_ranges  : include-mode ranges
        exclude_ranges  : exclude-mode ranges
        init, max_iterations, tol, c_nonneg, st_nonneg,
        normalize_spectra, closure, random_state : passed straight
            through to MCRALSManager.compute() (init ignored when
            n_runs > 1 — see below)
        n_runs : if > 1, run the fit this many times with init='random'
            and a different seed each time, then keep whichever run is
            most representative of the near-best group — same "Run N
            times, keep best" policy as the standalone MCR-ALS tool.
            get_last_run_info('mcr') reports (n_runs, pool_size, consensus)
            afterward.
        references, fix_references : passed straight through to
            MCRALSManager.compute() on every trial.

        Returns
        -------
        numpy.ndarray of shape (n_rows, n_cols), or None on error/failure.
        """
        if not self.validate_dimensions(len(spectra), n_rows, n_cols):
            logger.error("Map2DManager: dimension mismatch %d × %d ≠ %d",
                         n_rows, n_cols, len(spectra))
            return None

        filtered = self._filter_spectra_for_decomposition(
            spectra, x_min, x_max, include_ranges or [], exclude_ranges or [])
        if filtered is None:
            return None

        from src.modules.visualization_analysis.mcr_als_manager import MCRALSManager

        self._mcr_run_info = None
        if n_runs <= 1:
            mgr = MCRALSManager()
            ok = mgr.compute(filtered, n_components, init=init,
                             max_iterations=max_iterations, tol=tol,
                             c_nonneg=c_nonneg, st_nonneg=st_nonneg,
                             normalize_spectra=normalize_spectra,
                             closure=closure, random_state=random_state,
                             references=references or {},
                             fix_references=fix_references)
            if not ok:
                logger.error("Map2DManager: MCR-ALS failed")
                return None
        else:
            trials = []
            for i in range(n_runs):
                trial_mgr = MCRALSManager()
                trial_ok = trial_mgr.compute(
                    filtered, n_components, init='random',
                    max_iterations=max_iterations, tol=tol,
                    c_nonneg=c_nonneg, st_nonneg=st_nonneg,
                    normalize_spectra=normalize_spectra,
                    closure=closure, random_state=i,
                    references=references or {},
                    fix_references=fix_references)
                if trial_ok:
                    trials.append((trial_mgr.lof, trial_mgr))
            if not trials:
                logger.error("Map2DManager: all %d MCR-ALS trials failed", n_runs)
                self._mcr_manager = None
                return None
            mgr, consensus, pool = self._pick_best_of_n(
                trials, shape_matrices=lambda m: m.ST)
            self._mcr_run_info = (n_runs, len(pool), consensus)

        self._mcr_manager = mgr
        n_actual = mgr.C.shape[1]
        component_index = max(0, min(component_index, n_actual - 1))

        self.map_data = mgr.C[:, component_index].reshape(n_rows, n_cols)
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.map_mode = "mcr"

        logger.debug(
            "Map2DManager: MCR-ALS map computed (%d×%d, component=%d, EV=%.2f%%)",
            n_rows, n_cols, component_index + 1,
            mgr.explained_variance[component_index])
        return self.map_data

    # ------------------------------------------------------------------ #
    # Accessors                                                            #
    # ------------------------------------------------------------------ #

    def get_explained_variance(self):
        """Return full explained variance array or None."""
        return self._explained_variance

    def invert_component(self, kind, component_index):
        """Flip the sign of one component's subspectrum and per-pixel
        coefficients in place. Meaningful only for SVD/PCA, whose
        components have a genuine sign ambiguity (NMF/MCR-ALS's
        non-negativity constraint rules it out for them). Returns True if
        the flip was applied, False if *kind* doesn't support it or
        *component_index* is out of range / not yet computed.
        """
        if kind == 'svd':
            if self._U is None or component_index >= self._U.shape[1]:
                return False
            self._U[:, component_index]  *= -1
            self._Vt[component_index, :] *= -1
            return True
        if kind == 'pca':
            if self._pca_U is None or component_index >= self._pca_U.shape[1]:
                return False
            self._pca_U[:, component_index]  *= -1
            self._pca_Vt[component_index, :] *= -1
            return True
        return False

    def get_n_svd_components(self):
        """Return number of SVD components available (0 if not computed)."""
        if self._U is None:
            return 0
        return self._U.shape[1]

    def get_subspectrum(self, component_index):
        """
        Return (x_axis, u_column) for the requested SVD component.
        Returns (None, None) if SVD not yet computed.
        """
        if self._U is None:
            return None, None
        ci = max(0, min(component_index, self._U.shape[1] - 1))
        return self._svd_x_axis, self._U[:, ci]

    def get_coefficients(self, component_index):
        """Return Vt[component_index, :] or None."""
        if self._Vt is None:
            return None
        ci = max(0, min(component_index, self._Vt.shape[0] - 1))
        return self._Vt[ci, :]

    # ------------------------------------------------------------------ #
    # Unified accessors — work with 'svd' | 'nmf' | 'mcr'                 #
    # ------------------------------------------------------------------ #
    #
    # Added alongside (not replacing) the SVD-only accessors above, so
    # every existing SVD call site keeps working completely unchanged.
    # New dialog code that wants to handle "whichever decomposition is
    # currently active" uses these instead of three separate,
    # near-identical branches.

    _KNOWN_KINDS = ('svd', 'nmf', 'mcr', 'pca')

    def get_n_components(self, kind):
        """Number of available components for *kind* (0 if not computed)."""
        if kind == 'svd':
            return self.get_n_svd_components()
        if kind == 'nmf':
            mgr = self._nmf_manager
            return 0 if mgr is None or mgr.W is None else mgr.W.shape[1]
        if kind == 'mcr':
            mgr = self._mcr_manager
            return 0 if mgr is None or mgr.C is None else mgr.C.shape[1]
        if kind == 'pca':
            return 0 if self._pca_U is None else self._pca_U.shape[1]
        raise ValueError(f"Unknown decomposition kind: {kind!r}")

    def get_component_subspectrum(self, kind, component_index):
        """
        Return (x_axis, values) for one component's own spectral shape
        — U[:, k] for SVD, H[k, :] for NMF, ST[k, :] for MCR-ALS.
        Returns (None, None) if *kind* hasn't been computed yet.
        """
        if kind == 'svd':
            return self.get_subspectrum(component_index)
        if kind == 'nmf':
            mgr = self._nmf_manager
            if mgr is None or mgr.H is None:
                return None, None
            ci = max(0, min(component_index, mgr.H.shape[0] - 1))
            return mgr.x_axis, mgr.H[ci, :]
        if kind == 'mcr':
            mgr = self._mcr_manager
            if mgr is None or mgr.ST is None:
                return None, None
            ci = max(0, min(component_index, mgr.ST.shape[0] - 1))
            return mgr.x_axis, mgr.ST[ci, :]
        if kind == 'pca':
            if self._pca_U is None:
                return None, None
            ci = max(0, min(component_index, self._pca_U.shape[1] - 1))
            return self._pca_x_axis, self._pca_U[:, ci]
        raise ValueError(f"Unknown decomposition kind: {kind!r}")

    def get_component_coefficients(self, kind, component_index):
        """
        Return the per-pixel score/coefficient row for one component —
        Vt[k, :] for SVD, W[:, k] for NMF, C[:, k] for MCR-ALS — i.e.
        exactly the flat array compute_*_map() reshapes into the map.
        Returns None if *kind* hasn't been computed yet.
        """
        if kind == 'svd':
            return self.get_coefficients(component_index)
        if kind == 'nmf':
            mgr = self._nmf_manager
            if mgr is None or mgr.W is None:
                return None
            ci = max(0, min(component_index, mgr.W.shape[1] - 1))
            return mgr.W[:, ci]
        if kind == 'mcr':
            mgr = self._mcr_manager
            if mgr is None or mgr.C is None:
                return None
            ci = max(0, min(component_index, mgr.C.shape[1] - 1))
            return mgr.C[:, ci]
        if kind == 'pca':
            if self._pca_Vt is None:
                return None
            ci = max(0, min(component_index, self._pca_Vt.shape[0] - 1))
            return self._pca_Vt[ci, :]
        raise ValueError(f"Unknown decomposition kind: {kind!r}")

    def get_component_explained_variance(self, kind):
        """Full explained-variance array for *kind*, or None."""
        if kind == 'svd':
            return self.get_explained_variance()
        if kind == 'nmf':
            return None if self._nmf_manager is None else self._nmf_manager.explained_variance
        if kind == 'mcr':
            return None if self._mcr_manager is None else self._mcr_manager.explained_variance
        if kind == 'pca':
            return self._pca_explained_variance
        raise ValueError(f"Unknown decomposition kind: {kind!r}")

    def get_last_decomp_error(self, kind):
        """
        Specific reason the last compute_nmf_map()/compute_mcr_map() call
        failed, or None. SVD has no equivalent — np.linalg.svd either
        succeeds or raises, there's no separate "why did the fit itself
        refuse" message the way NMF/MCR-ALS have (e.g. mismatched x-axes,
        non-overlapping ranges).
        """
        if kind == 'nmf':
            return None if self._nmf_manager is None else self._nmf_manager.last_error
        if kind == 'mcr':
            return None if self._mcr_manager is None else self._mcr_manager.last_error
        return None

    def get_component_lof(self, kind):
        """Lack-of-fit (%) for the last fit of *kind*, or None. SVD has no
        equivalent (see get_last_decomp_error)."""
        if kind == 'nmf':
            return None if self._nmf_manager is None else self._nmf_manager.lof
        if kind == 'mcr':
            return None if self._mcr_manager is None else self._mcr_manager.lof
        return None

    def get_component_iterations(self, kind):
        """(iterations_used, converged) for the last fit of *kind*, or
        (None, None)."""
        mgr = self._nmf_manager if kind == 'nmf' else (
            self._mcr_manager if kind == 'mcr' else None)
        if mgr is None:
            return None, None
        return getattr(mgr, 'iterations_used', None), getattr(mgr, 'converged', None)

    def get_last_run_info(self, kind):
        """(n_runs, pool_size, consensus) from the last compute_*_map() call
        if it used n_runs > 1 ("Run N times, keep best"), else None — the
        last such call was a single, plain fit."""
        if kind == 'nmf':
            return self._nmf_run_info
        if kind == 'mcr':
            return self._mcr_run_info
        return None
