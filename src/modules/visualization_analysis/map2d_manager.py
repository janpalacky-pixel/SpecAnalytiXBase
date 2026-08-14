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

    # ------------------------------------------------------------------ #
    # Dimension validation                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def validate_dimensions(n_spectra: int, n_rows: int, n_cols: int) -> bool:
        """Return True if n_rows * n_cols == n_spectra (and both > 0)."""
        return n_rows > 0 and n_cols > 0 and n_rows * n_cols == n_spectra

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

    # ------------------------------------------------------------------ #
    # Accessors                                                            #
    # ------------------------------------------------------------------ #

    def get_explained_variance(self):
        """Return full explained variance array or None."""
        return self._explained_variance

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
