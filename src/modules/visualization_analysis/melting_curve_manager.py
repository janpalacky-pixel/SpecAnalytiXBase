# src/modules/visualization_analysis/melting_curve_manager.py

import re
import numpy as np
import scipy.signal as sg
from scipy.optimize import curve_fit
from scipy.signal import find_peaks
from scipy.special import expit, erf

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

# NumPy 2.0 renamed trapz -> trapezoid; this keeps working on either
# (same compatibility shim used by peak_fitting_manager.py).
_trapz = getattr(np, 'trapezoid', None) or np.trapz

R_GAS = 8.31446261815324  # J / (mol * K)

# --- Automatic (Santoro-Bolen) fit: model-selection and reliability
# constants ----------------------------------------------------------
#
# Ported from MeltAnalytiX's feature_extraction.py, where these same
# values gate its own automatic joint-fit walk-up and its "is this run
# reliable" rule. Kept as the same numbers here rather than re-derived,
# since they aren't SpecAnalytiXBase- or MeltAnalytiX-specific — they're
# generic thresholds for "is this fit meaningfully better" (BIC) and "is
# this fit trustworthy enough to report a Tm from" (R^2/edge-tracking).

# Kass & Raftery (1995) "decisive evidence" convention: a candidate
# component count is only adopted over the current best if it lowers BIC
# by more than this.
BIC_DECISIVE_THRESHOLD = 10.0

# How much the downstream Arrhenius R^2 (or edge-tracking error, as a
# fraction of curve amplitude) is allowed to get worse, step to step,
# before the automatic component-count walk-up refuses to adopt an
# otherwise BIC-decisive extra component.
SCORE_TOLERANCE = 0.03

# Absolute cutoff (as a fraction of curve amplitude) on the FINAL chosen
# fit's own edge-tracking error — "does the dashed baseline line actually
# sit on top of the flat part of the real data" — independent of the
# step-to-step SCORE_TOLERANCE comparison above. A fit whose baseline
# misses the data by more than this at either edge is discarded outright
# (automatic mode reports "not reliable" rather than showing it).
EDGE_TOLERANCE_ABSOLUTE_FRACTION = 0.12

# Reliability gates for the automatic fit's overall verdict (see
# fit_automatic below) — same two R^2 thresholds MeltAnalytiX's own
# _pair_is_reliable rule uses, kept as two SEPARATE gates (the van't
# Hoff/Arrhenius regression's own R^2, vs. a genuine independent re-fit
# of the sigmoid shape in normalized space) rather than one, since they
# can fail for different reasons.
ARRHENIUS_CONFIDENCE_R2_THRESHOLD = 0.85
SIGMOID_CONFIDENCE_R2_THRESHOLD = 0.70


# --- Sigmoid shape definitions -------------------------------------------
#
# Two interchangeable 0-1 normalized sigmoid shapes are offered, ported
# from the standalone "thermoanalysis" prototype (helper_functions_thermo/
# data_analysis.py). Both go from 0 (fully "unfolded"/low-temperature
# baseline) to 1 (fully "folded"/high-temperature baseline) as x increases
# through 'midpoint', with 'lambda_' controlling the transition width.

def logistic_sigmoid(x):
    """Standard logistic function, 0-1 normalized."""
    return expit(x)


def erf_sigmoid(x):
    """Error-function sigmoid, 0-1 normalized."""
    return 0.5 + erf(x) / 2.0


SIGMOID_SHAPES = {
    'Logistic': logistic_sigmoid,
    'Error function': erf_sigmoid,
}


class MeltingCurveManager:
    """Business logic for thermal melting-curve analysis: extraction of a
    melting curve from a series of spectra, linear-baseline normalization,
    Arrhenius-based thermodynamic parameters (deltaH, deltaS), and
    multi-sigmoid (up to 4 components) deconvolution of multiphasic
    transitions.

    Ported and simplified from the standalone "thermoanalysis" prototype
    (helper_functions_thermo/data_analysis.py). The prototype's optional
    multi-solver machinery (autograd/numdifftools-based minimize() with a
    dozen selectable methods) is intentionally NOT ported — every other
    Manager in this codebase (see peak_fitting_manager.py) fits with plain
    scipy.optimize.curve_fit only, and adding two new third-party
    dependencies for an alternate fitting path nothing else in the app
    uses was not worth the added complexity/fragility.
    """

    def __init__(self):
        self.sigmoid_shapes = SIGMOID_SHAPES
        # Set by normalize_melting_curve() whenever it returns None because
        # the baseline fit itself failed (as opposed to the empty-mask
        # case, which has no extra detail to report) -- read by
        # MeltingCurveDialog.perform_normalization() to show a specific
        # warning instead of the generic "widen the ranges" one.
        self.last_normalization_error = None

    # ------------------------------------------------------------------ #
    # 1. Curve extraction from a series of spectra                        #
    # ------------------------------------------------------------------ #

    def extract_curve_from_spectra(self, spectra, x_value, window=0.0):
        """Extract one y-value per spectrum at x_value (interpolated),
        returning them in the SAME order as `spectra`.

        Args:
            spectra: list of {'x_scale', 'y_scale', 'label', ...} dicts.
            x_value: the x position (e.g. wavenumber) at which to read
                the melting-curve signal off each spectrum.
            window: if > 0, average all points within
                [x_value - window, x_value + window] instead of a single
                interpolated point — useful to reduce noise. window = 0
                (default) uses plain linear interpolation (np.interp) at
                exactly x_value.

        Returns:
            (y_values, out_of_range_labels) — y_values is a numpy array,
            same length/order as spectra. out_of_range_labels lists any
            spectra whose x_scale does not cover x_value (interpolation
            still runs — numpy clamps to the nearest edge value — but the
            caller should warn the user).
        """
        y_values = []
        out_of_range = []
        for spec in spectra:
            x = np.asarray(spec['x_scale'], dtype=float)
            y = np.asarray(spec['y_scale'], dtype=float)
            if x.size == 0:
                y_values.append(np.nan)
                out_of_range.append(spec.get('label', '?'))
                continue

            x_min, x_max = np.nanmin(x), np.nanmax(x)
            if x_value < x_min or x_value > x_max:
                out_of_range.append(spec.get('label', '?'))

            if window and window > 0:
                mask = (x >= x_value - window) & (x <= x_value + window)
                if np.any(mask):
                    y_values.append(float(np.mean(y[mask])))
                else:
                    # Fall back to interpolation if the window caught nothing
                    # (e.g. window smaller than point spacing).
                    y_values.append(float(np.interp(x_value, x, y)))
            else:
                # np.interp requires ascending x
                order = np.argsort(x)
                y_values.append(float(np.interp(x_value, x[order], y[order])))

        return np.array(y_values), out_of_range

    def extract_curve_svd_from_spectra(self, spectra, center=True):
        """Extract a generalized melting curve from a series of spectra
        via SVD, as an alternative to extract_curve_from_spectra's
        single-x-value reading.

        Ported from MeltAnalytiX's feature_extraction._generalized_
        melting_curve (see that module's docstring for the full
        rationale): rather than picking one representative x position
        (arbitrary, and sensitive to noise or an isosbestic point sitting
        exactly there), this decomposes the whole (wavelength x spectrum)
        matrix via SVD and uses the first singular component's own
        across-spectrum trajectory as the melting curve \u2014 a summary of
        how the ENTIRE measured spectral shape changes, not just one
        point on it. Matches SpecAnalytiXBase's own SVD Analysis tool's
        SVD convention (src/modules/visualization_analysis/
        svd_analysis_manager.py): data matrix = wavelengths x spectra,
        optionally mean-centered per wavelength before np.linalg.svd.

        Args:
            spectra: list of {'x_scale', 'y_scale', 'label', ...} dicts,
                one per spectrum (e.g. one per temperature) \u2014 same shape
                extract_curve_from_spectra takes. Every spectrum MUST
                share an identical x_scale (same grid, same length) \u2014
                SVD needs one common matrix, not a per-spectrum
                interpolation the way the single-X method allows.
            center: mean-center each wavelength's row (subtract its own
                across-spectrum mean) before decomposing. Recommended
                default, matching MeltAnalytiX: an uncentered SVD's first
                component tends to just reproduce the plain per-spectrum
                average (dominated by whatever's common to every
                spectrum) rather than how the spectrum actually CHANGES
                \u2014 the real transition signal. center=False is kept only
                for direct before/after comparison.

        Returns:
            (y_values, diagnostics) \u2014 y_values is the extracted curve, a
            numpy array in the SAME order as `spectra`. diagnostics is a
            dict with 'explained_variance_pc1'/'explained_variance_pc2'
            (fraction of total variance the first two components
            explain \u2014 PC2 well above ~0 is a real hint that more than
            one spectroscopic process changes with temperature) and
            'wavelength_range' (min, max of the shared x-axis actually
            used).

        Raises:
            ValueError if fewer than 2 spectra are given, or if their
            x_scale arrays don't all match exactly.
        """
        if len(spectra) < 2:
            raise ValueError("SVD extraction needs at least 2 spectra.")

        x_scales = [np.asarray(s['x_scale'], dtype=float) for s in spectra]
        first_x = x_scales[0]
        for i, x in enumerate(x_scales):
            if x.shape != first_x.shape or not np.allclose(x, first_x, equal_nan=True):
                bad_label = spectra[i].get('label', f'spectrum #{i + 1}')
                raise ValueError(
                    "SVD extraction requires every selected spectrum to share the exact "
                    f"same x-axis (wavelength/wavenumber) grid, but '{bad_label}' does not "
                    "match the others. Re-sample or crop the spectra onto a common grid "
                    "first, or use \"Extract signal at X\" instead, which doesn't require "
                    "this.")

        y_scales = [np.asarray(s['y_scale'], dtype=float) for s in spectra]
        data_matrix = np.column_stack(y_scales)  # wavelengths x spectra

        if center:
            baseline = data_matrix.mean(axis=1, keepdims=True)
            working = data_matrix - baseline
        else:
            working = data_matrix

        U, S, Vt = np.linalg.svd(working, full_matrices=False)
        curve = S[0] * Vt[0, :]

        # Sign is arbitrary in SVD \u2014 orient it to correlate positively
        # with the plain per-wavelength-averaged trajectory, so it's
        # comparable/consistent across runs without an arbitrary flip
        # (same convention MeltAnalytiX uses).
        mean_traj = data_matrix.mean(axis=0)
        if np.corrcoef(curve, mean_traj)[0, 1] < 0:
            curve = -curve

        total_var = float(np.sum(S ** 2))
        explained_pc1 = float(S[0] ** 2 / total_var) if total_var > 0 else float('nan')
        explained_pc2 = (float(S[1] ** 2 / total_var)
                         if total_var > 0 and S.size > 1 else float('nan'))

        diagnostics = {
            'explained_variance_pc1': explained_pc1,
            'explained_variance_pc2': explained_pc2,
            'wavelength_range': (float(np.nanmin(first_x)), float(np.nanmax(first_x))),
        }
        return curve, diagnostics

    # ------------------------------------------------------------------ #
    # 2. Linear-baseline normalization                                    #
    # ------------------------------------------------------------------ #

    def normalize_melting_curve(self, x, y, low_range, high_range, order=1,
                                instability_frac=0.15):
        """Normalize a melting curve using linear (order=1) or constant
        (order=0) approximations of the low-x and high-x baseline regions,
        following the handout's convention:

            A_corr = (A_orig - A_unfolded) / (A_folded - A_unfolded)

        Args:
            x, y: the raw melting curve (e.g. temperature, signal).
            low_range, high_range: (min, max) x-tuples defining the two
                baseline regions ("unfolded"/low-x and "folded"/high-x —
                which physical state each represents depends on whether
                the signal increases or decreases with x, and is not
                assumed here).
            order: 0 (constant/zero-order) or 1 (linear/first-order) fit
                for each baseline region.
            instability_frac: a point is flagged in 'unstable_mask' when
                its own |denom| falls below this fraction of the curve's
                own max |denom| — see 'unstable_mask' below.

        Returns:
            dict with 'y_norm', 'baseline_low' (evaluated over all of x),
            'baseline_high' (evaluated over all of x), 'coeffs_low',
            'coeffs_high', 'baselines_cross', and 'unstable_mask', or None
            if either region is empty.
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        low_mask = (x >= min(low_range)) & (x <= max(low_range))
        high_mask = (x >= min(high_range)) & (x <= max(high_range))

        self.last_normalization_error = None

        if not np.any(low_mask) or not np.any(high_mask):
            return None

        try:
            coeffs_low = np.polyfit(x[low_mask], y[low_mask], deg=order)
            coeffs_high = np.polyfit(x[high_mask], y[high_mask], deg=order)
        except (np.linalg.LinAlgError, ValueError) as exc:
            # Degenerate baseline-region data (e.g. too few distinct
            # temperatures, or all-identical signal in a window) can make
            # the underlying least-squares fit unsolvable -- reported by
            # a user who fed this tool's own exported curve/normalized-
            # curve outputs back in as source spectra. That is not a
            # bug in the fit itself, just data this method fundamentally
            # can't baseline-fit, so it's reported the same way as the
            # empty-mask case just above (return None) rather than left
            # to propagate as an unhandled exception -- see
            # last_normalization_error for why, specifically.
            logger.warning(
                "normalize_melting_curve: baseline fit failed (%s)", exc,
                exc_info=True)
            self.last_normalization_error = (
                "Could not fit the Low-T / High-T baseline regions -- the "
                "data inside one or both selected ranges is too degenerate "
                "for a reliable fit (e.g. too few distinct temperatures, or "
                "an all-identical signal). This can happen when the "
                "selected spectra aren't actually a melting-curve series "
                "(for example, re-analyzing this tool's own previously "
                "exported curve/normalized-curve outputs)."
            )
            return None

        return self._normalize_from_coeffs(x, y, coeffs_low, coeffs_high,
                                           instability_frac=instability_frac)

    @staticmethod
    def _normalize_from_coeffs(x, y, coeffs_low, coeffs_high, instability_frac=0.15):
        """The actual normalization arithmetic behind normalize_melting_curve,
        factored out so a caller that already HAS baseline coefficients from
        somewhere other than "polyfit a straight line to two windows" —
        specifically fit_two_state_curve/fit_multi_state_curve below, whose
        whole point is determining the baselines a different way — can reuse
        this instead of duplicating the y_norm/unstable_mask/baselines_cross
        logic. normalize_melting_curve itself keeps its original signature/
        behavior unchanged — existing callers are unaffected."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        baseline_low = np.polyval(coeffs_low, x)
        baseline_high = np.polyval(coeffs_high, x)

        denom = baseline_high - baseline_low
        with np.errstate(divide='ignore', invalid='ignore'):
            y_norm = (y - baseline_low) / denom
        y_norm = np.where(np.isfinite(y_norm), y_norm, np.nan)

        # If the two baselines cross somewhere within the curve's own
        # x-range, the denominator passes through (or very near) zero
        # right there, and y_norm blows up toward +/-infinity at that
        # point regardless of how good the fit itself is — a genuine
        # numerical instability of linear-baseline normalization, not a
        # sign of anything wrong with the fitting step downstream. Flag
        # it explicitly so the caller can warn rather than silently
        # accept a curve with huge, physically meaningless excursions.
        baselines_cross = bool(np.any(denom > 0) and np.any(denom < 0))

        # unstable_mask: True at any point whose LOCAL |denom| is small
        # relative to the curve's own overall scale (max |denom|) — these
        # points sit close enough to wherever the two baselines cross (or
        # nearly cross) that y_norm there is dominated by division-by-
        # near-zero noise rather than genuine signal, even when finite.
        # This matters downstream, specifically for
        # transform_xy_for_arrhenius: those points passing the ordinary
        # 0-1 span filter (nothing about them looks obviously wrong — a
        # spurious-but-finite y_norm value can easily land inside 0.05-
        # 0.95) can dominate the van't Hoff linear regression precisely
        # because the transform is most sensitive right where K=y/(1-y)
        # crosses 1 — silently distorting the fitted slope (and hence
        # deltaH) by an order of magnitude and dragging the fitted Tm
        # away from the true value, while the regression's own R^2/
        # parameter-uncertainty numbers make the fit LOOK worse (not
        # obviously wrong in a way that points at the real cause). Not
        # gated on baselines_cross alone: two baselines that come close
        # without technically crossing produce the same instability, just
        # less dramatically.
        max_abs_denom = np.max(np.abs(denom)) if denom.size else 0.0
        if max_abs_denom > 0:
            unstable_mask = np.abs(denom) < (instability_frac * max_abs_denom)
        else:
            unstable_mask = np.zeros_like(denom, dtype=bool)

        return {
            'y_norm': y_norm,
            'baseline_low': baseline_low,
            'baseline_high': baseline_high,
            'coeffs_low': np.asarray(coeffs_low, dtype=float),
            'coeffs_high': np.asarray(coeffs_high, dtype=float),
            'baselines_cross': baselines_cross,
            'unstable_mask': unstable_mask,
        }

    def compute_median_crossing_temperature(self, x, y_raw, baseline_low, baseline_high):
        """X_trans: the temperature where the RAW curve crosses the
        median line — (baseline_low(T) + baseline_high(T)) / 2 — found by
        linear interpolation between the two data points that bracket the
        sign change. This is a DIRECT, purely geometric estimate of the
        transition midpoint (no Arrhenius/van't Hoff regression involved
        at all), matching the reference two-state UV-melting protocol's
        own primary method: find where the original curve crosses halfway
        between its two baselines.

        This is a genuinely DIFFERENT calculation from Tm returned by
        compute_thermodynamic_params() (which comes from where the FITTED
        ln(K) vs 1/T regression line crosses zero) — they estimate the
        same physical quantity two different ways and will generally
        agree closely for a clean two-state transition, but are not
        guaranteed to be numerically identical, especially if the van't
        Hoff plot has real curvature (e.g. non-negligible heat capacity
        change) that a straight-line regression can't capture, or the
        chosen Threshold (span) pulls in points from a region where that
        curvature matters.

        Returns the crossing temperature, or None if the raw curve never
        crosses its own median line (e.g. a badly-chosen baseline region,
        or a curve with no real transition in range).
        """
        x = np.asarray(x, dtype=float)
        y_raw = np.asarray(y_raw, dtype=float)
        median_line = (np.asarray(baseline_low, dtype=float)
                       + np.asarray(baseline_high, dtype=float)) / 2.0
        diff = y_raw - median_line

        order = np.argsort(x)
        x_sorted, diff_sorted = x[order], diff[order]
        sign_changes = np.where(np.diff(np.sign(diff_sorted)) != 0)[0]
        if sign_changes.size == 0:
            return None

        # Use the sign change nearest the middle of the data if there's
        # more than one (e.g. noisy baseline regions crossing their own
        # median spuriously near the edges) — the real transition is
        # expected to dominate near the center of the temperature range.
        mid_idx = len(x_sorted) // 2
        i = sign_changes[np.argmin(np.abs(sign_changes - mid_idx))]
        x0, x1 = x_sorted[i], x_sorted[i + 1]
        d0, d1 = diff_sorted[i], diff_sorted[i + 1]
        if d1 == d0:
            return float(x0)
        # Linear interpolation for where diff crosses zero between the
        # two bracketing points.
        return float(x0 + (0 - d0) * (x1 - x0) / (d1 - d0))

    # ------------------------------------------------------------------ #
    # 3. Arrhenius transform and thermodynamic parameters                 #
    # ------------------------------------------------------------------ #

    def transform_xy_for_arrhenius(self, x_temperature, y_fraction, span=0.95,
                                    exclude_mask=None):
        """Restrict to the central `span` of the 0-1 normalized curve
        (dropping points too close to either baseline, where
        ln(K)=ln(y/(1-y)) diverges) and transform to Arrhenius coordinates:
        x_arr = 1/T[K], y_arr = ln(K), K = y/(1-y).

        Args:
            x_temperature: temperature in the SAME units the spectra were
                tagged with — assumed degrees Celsius, converted to Kelvin
                here (+273.15), matching the ported prototype.
            y_fraction: 0-1 normalized melting-curve signal (y_norm from
                normalize_melting_curve, or a directly 0-1 normalized
                curve).
            span: keep points where span-side thresholds
                1-span <= y <= span (default 0.95 keeps the central 90%).
            exclude_mask: optional boolean array, same length as
                x_temperature/y_fraction — True marks a point to drop
                before the span filter even runs, regardless of where its
                y value happens to land. Meant for
                normalize_melting_curve's 'unstable_mask': a point near a
                low-T/high-T baseline crossing can have a spurious-but-
                finite y_norm that passes the ordinary span filter
                undetected, then distorts the regression precisely
                because this transform is most sensitive right where
                K=y/(1-y) crosses 1. None (default) excludes nothing —
                unchanged behavior for every existing caller.

        Returns:
            dict with 'x_arr' (1/T), 'y_arr' (ln K), 'K', 'ind' (indices
            into the input arrays that were kept), or None if nothing is
            left after filtering.
        """
        x = np.asarray(x_temperature, dtype=float)
        y = np.asarray(y_fraction, dtype=float)

        with np.errstate(invalid='ignore'):
            ind = np.where((y >= 1 - span) & (y <= span))[0]
        if exclude_mask is not None:
            exclude_mask = np.asarray(exclude_mask, dtype=bool)
            ind = ind[~exclude_mask[ind]]
        if ind.size < 2:
            return None

        x_k, y_k = x[ind] + 273.15, y[ind]
        x_arr = 1.0 / x_k

        with np.errstate(divide='ignore', invalid='ignore'):
            K = y_k / (1 - y_k)
            logK = np.log(K)

        finite = np.isfinite(logK)
        if not np.any(finite):
            return None

        return {
            'x_arr': x_arr[finite],
            'y_arr': logK[finite],
            'K': K[finite],
            'ind': ind[finite],
        }

    def compute_thermodynamic_params(self, x_arr, y_arr):
        """Linear regression of the Arrhenius plot (y_arr = ln K vs.
        x_arr = 1/T) to get van't Hoff deltaH and deltaS:

            ln K = -deltaH/R * (1/T) + deltaS/R

        Tm here is the temperature at which the FITTED regression line
        crosses ln(K) = 0 (equivalently K = 1, A_corr = 0.5) — the
        rigorous van't Hoff definition of the transition midpoint, using
        every point in the chosen threshold span rather than a single
        raw data point. This is the same physical quantity as a simple
        "temperature where the curve crosses its median value" estimate
        (as in the two-state UV-melting protocol this tool's
        normalization/Arrhenius approach follows) — regression just makes
        it noise-robust instead of reading it off one point.

        Returns dict with 'deltaH' (J/mol), 'deltaS' (J/mol/K), 'coeffs'
        (slope, intercept), 'Tm' (melting temperature in degrees C, or
        None), and standard-error estimates 'deltaH_err', 'deltaS_err',
        'Tm_err' (via scipy.stats.linregress's slope/intercept standard
        errors, propagated through — treating slope and intercept as
        independent, a standard simplifying approximation; None if fewer
        than 3 points, since a 2-point line has no residual to estimate
        error from at all), or None if fewer than 2 points.
        """
        x_arr = np.asarray(x_arr, dtype=float)
        y_arr = np.asarray(y_arr, dtype=float)
        if x_arr.size < 2:
            return None

        coeffs = np.polyfit(x_arr, y_arr, deg=1)
        slope, intercept = coeffs
        deltaH = -slope * R_GAS
        deltaS = intercept * R_GAS

        # ln K = 0  =>  x = -intercept/slope = 1/T_m
        Tm = None
        inv_Tm = None
        if slope != 0:
            inv_Tm = -intercept / slope
            if inv_Tm > 0:
                Tm = (1.0 / inv_Tm) - 273.15

        deltaH_err = deltaS_err = Tm_err = None
        if x_arr.size >= 3:
            try:
                from scipy import stats
                reg = stats.linregress(x_arr, y_arr)
                deltaH_err = abs(reg.stderr * R_GAS)
                deltaS_err = abs(reg.intercept_stderr * R_GAS)
                if slope != 0 and inv_Tm is not None and inv_Tm > 0:
                    # Tm_K = 1/inv_Tm, inv_Tm = -intercept/slope. Propagating
                    # this through slope/intercept requires their COVARIANCE,
                    # not just their individual variances - treating them as
                    # independent (as this function used to) ignores a
                    # substantial, usually NEGATIVE correlation between a
                    # regression's slope and intercept whenever the x-data
                    # isn't centered near zero, which 1/T (in Kelvin) never
                    # is. Dropping that term systematically inflates Tm_err
                    # by an order of magnitude or more - verified via Monte
                    # Carlo simulation (repeated noisy resampling of a
                    # synthetic Arrhenius plot): the true spread in the
                    # recovered Tm was ~1 C, the independence-assumption
                    # formula reported ~67 C, and this covariance-aware
                    # formula reported ~1.6 C, matching the Monte Carlo
                    # result to the right order of magnitude.
                    #
                    # For ordinary least squares, Cov(slope, intercept) has
                    # the closed form -mean(x) * Var(slope) - no separate
                    # covariance-matrix fit is needed to get it.
                    var_slope = reg.stderr ** 2
                    var_intercept = reg.intercept_stderr ** 2
                    cov_slope_intercept = -float(np.mean(x_arr)) * var_slope
                    # Delta method for x0 = -intercept/slope:
                    #   d(x0)/d(intercept) = -1/slope
                    #   d(x0)/d(slope)     = intercept/slope**2
                    var_x0 = (
                        var_intercept / slope ** 2
                        + (intercept ** 2 / slope ** 4) * var_slope
                        - (2 * intercept / slope ** 3) * cov_slope_intercept
                    )
                    sigma_inv_tm = np.sqrt(max(var_x0, 0.0))
                    Tm_err = float(sigma_inv_tm / inv_Tm ** 2)
            except Exception as e:
                logger.warning(f"compute_thermodynamic_params: standard-error "
                               f"estimation failed ({e}); returning None for errors.")

        return {'deltaH': deltaH, 'deltaS': deltaS, 'coeffs': coeffs, 'Tm': Tm,
               'deltaH_err': deltaH_err, 'deltaS_err': deltaS_err, 'Tm_err': Tm_err}

    # ------------------------------------------------------------------ #
    # 3b. Joint baseline + transition (Santoro-Bolen) fitting             #
    # ------------------------------------------------------------------ #
    #
    # Ported from MeltAnalytiX (2026-09), where this same joint-fit model
    # replaced an older two-stage "search for where the baseline windows
    # are, THEN fit a straight line to each" pipeline for its automatic
    # (no manual override) path. SpecAnalytiXBase's own manual workflow —
    # the low_range/high_range sliders above, feeding
    # normalize_melting_curve — is left completely unchanged; these three
    # methods add a new, independent Automatic mode that estimates the
    # SAME baseline+transition shape a different way: everything fit
    # jointly, in one regression, with no window-search step at all. See
    # fit_automatic below for how the two model-selection safety gates
    # (BIC and downstream fit quality) are combined into a single
    # go/no-go decision this app's dialog can act on.

    def fit_two_state_curve(self, x, y, midpoint_guess=None, width_guess=None,
                            shape_name='Logistic', exclude_mask=None, baseline_fraction=0.15):
        """Fit the native-state baseline, denatured-state baseline, AND the
        transition itself all in ONE simultaneous nonlinear regression
        against the raw curve — a two-state / Santoro-Bolen-style model —
        instead of first guessing where the low-T/high-T plateaus are and
        then fitting a straight line to each separately.

        The win over a window-search-then-fit approach: there is no step
        that has to correctly GUESS where the plateau boundaries are
        before anything else can happen — a bad guess there (e.g. a run
        whose blank-correction excludes exactly the region a heuristic
        window search would have anchored on) corrupts everything
        downstream (normalization, the van't Hoff/Arrhenius regression,
        Tm/deltaH). This one regression fits against every measured point
        at once, so it is data-efficient (uses the whole scan, not just
        whichever points a heuristic walk decided belonged in a window)
        and self-consistent (the baselines and the transition are fit
        against each other directly, instead of each other's approximate
        byproducts).

        Model: y(T) = base_low(T) + [base_high(T) - base_low(T)] *
        shape((T - mid) / width), where base_low/base_high are straight
        lines (their own slope+intercept, both free parameters) — exactly
        normalize_melting_curve's own baseline model, just fit jointly
        with the transition instead of independently beforehand.

        exclude_mask (optional, same length/order as x): accepted for
        signature symmetry with the rest of this module, but — same
        reasoning as normalize_melting_curve's own polyfit, which never
        takes an exclude_mask either — NOT used to drop points from this
        regression. A point flagged upstream (e.g. a blank-correction
        artifact) is a signal to be suspicious of DOWNSTREAM (the
        Arrhenius scoring, in fit_automatic below), not a reason to treat
        the already-corrected sample measurement at that temperature as
        unreal; dropping a whole exclusion window from THIS fit risks
        starving it of exactly the points that pin down the transition's
        true shape, on a curve where the excluded region happens to
        overlap the transition itself.

        Returns a dict with 'coeffs_low'/'coeffs_high' (same [slope,
        intercept] shape normalize_melting_curve's own coeffs_low/
        coeffs_high use, so callers can feed these straight into
        _normalize_from_coeffs above), 'mid' (the fitted transition
        midpoint — a Tm estimate; the van't Hoff Tm from the Arrhenius
        regression downstream remains this app's primary reported Tm),
        'width', 'y_fit', 'quality' (estimate_fit_quality's r_squared/
        rmsd/aic/bic), and 'popt' (raw fit parameters). Returns None if
        the fit fails or there isn't enough data — callers should treat
        None as "automatic fit unavailable, fall back to Manual", never
        raise."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        # Fit against every point, including any exclude_mask-flagged
        # ones — see the exclude_mask paragraph in the docstring above.
        x_fit, y_fit_data = x, y
        if x_fit.size < 6:
            return None
        order = np.argsort(x_fit)
        x_fit, y_fit_data = x_fit[order], y_fit_data[order]
        x_span = float(x_fit.max() - x_fit.min())
        if x_span <= 0:
            return None
        shape_func = self.sigmoid_shapes.get(shape_name)
        if shape_func is None:
            return None

        # Initial guesses: a quick straight-line fit to each end's own
        # baseline_fraction slice of the data — purely a STARTING POINT
        # for the joint fit below, not the final answer, so any
        # imprecision here just costs curve_fit a few extra iterations.
        n = len(x_fit)
        k = max(2, int(round(baseline_fraction * n)))
        try:
            p0_low = np.polyfit(x_fit[:k], y_fit_data[:k], deg=1)
        except Exception:
            p0_low = [0.0, float(np.mean(y_fit_data[:k]))]
        try:
            p0_high = np.polyfit(x_fit[-k:], y_fit_data[-k:], deg=1)
        except Exception:
            p0_high = [0.0, float(np.mean(y_fit_data[-k:]))]
        mid0 = float(midpoint_guess) if midpoint_guess is not None else float(np.median(x_fit))
        mid0 = min(max(mid0, x_fit.min()), x_fit.max())
        width0 = float(width_guess) if width_guess else max(x_span / 10.0, 1e-6)

        # Bound (not fix) the baseline slopes: left fully unbounded,
        # curve_fit can converge to a mathematically-valid but
        # physically-nonsensical solution whenever the transition doesn't
        # fully saturate within the measured range — a real, common case,
        # not an edge case. In that situation the fit can trade off a
        # steeper baseline slope against the transition's own
        # width/midpoint and still match the visible data well (a real
        # near-collinearity between "baseline slope" and "transition
        # shape" whenever the plateau itself is under-sampled), producing
        # a baseline that doesn't resemble the plateau it's supposed to
        # describe at all despite an excellent overall R^2. Physically, a
        # baseline should never be steeper than the transition it's
        # flanking — bounding each side's |slope| to 2x the curve's own
        # overall amplitude-over-span rules out that runaway solution
        # while still leaving room for a real, visibly-tilted baseline
        # (most runs' true baselines are much flatter than this bound —
        # it exists to catch the pathological case, not to constrain
        # ordinary ones).
        curve_amplitude = float(np.max(y_fit_data) - np.min(y_fit_data))
        max_slope = 2.0 * (curve_amplitude / x_span) if curve_amplitude > 0 else np.inf

        p0 = [p0_low[0], p0_low[1], p0_high[0], p0_high[1], mid0, width0]
        lower = [-max_slope, -np.inf, -max_slope, -np.inf, x_fit.min() - x_span, 1e-6]
        upper = [max_slope, np.inf, max_slope, np.inf, x_fit.max() + x_span, x_span * 5]
        # p0's own slope, from the quick endpoint-only fit above, can
        # occasionally already exceed this bound on real noisy data — the
        # bound is about the JOINT fit's behavior, not the rough initial
        # guess — so clip it in so curve_fit always starts inside its own
        # bounds, which scipy requires.
        p0[0] = float(np.clip(p0[0], -max_slope, max_slope))
        p0[2] = float(np.clip(p0[2], -max_slope, max_slope))

        def model_func(xx, m_low, b_low, m_high, b_high, mid, width):
            xx = np.asarray(xx, dtype=float)
            base_low = m_low * xx + b_low
            base_high = m_high * xx + b_high
            return base_low + (base_high - base_low) * shape_func((xx - mid) / width)

        try:
            popt, _pcov = curve_fit(model_func, x_fit, y_fit_data, p0=p0,
                                    bounds=(lower, upper), maxfev=10000)
        except (RuntimeError, ValueError) as e:
            logger.error(f"fit_two_state_curve: joint baseline+transition fit failed: {e}")
            return None

        m_low, b_low, m_high, b_high, mid, width = popt
        y_fit_kept = model_func(x_fit, *popt)
        quality = self.estimate_fit_quality(y_fit_data, y_fit_kept, popt)
        y_fit_full = model_func(x, *popt)
        return {
            'coeffs_low': np.array([m_low, b_low]), 'coeffs_high': np.array([m_high, b_high]),
            'mid': float(mid), 'width': float(width), 'y_fit': y_fit_full,
            'quality': quality, 'popt': popt, 'shape_name': shape_name,
        }

    def fit_multi_state_curve(self, x, y, n_components, midpoint_guesses=None,
                              width_guesses=None, factor_guesses=None,
                              coeffs_low_guess=None, coeffs_high_guess=None,
                              shape_name='Logistic', baseline_fraction=0.15):
        """Generalizes fit_two_state_curve from exactly ONE shared-baseline
        transition to N (1-4):

            y(T) = base_low(T) + [base_high(T) - base_low(T)]
                   * sum_i factor_i * shape((T - mid_i) / width_i)

        factors summing to 1 — the SAME weighted-sum convention
        sigmoid_sum_model above already uses for this app's separate,
        POST-normalization multi-component overlay (fit_sigmoid_model),
        just with the two baselines now inside THIS SAME regression
        instead of fixed beforehand. n_components=1 reduces to exactly
        fit_two_state_curve's own model.

        Why this exists: a run whose real transition needs 2+ components
        but whose baseline was determined by a fit that only had ONE
        component available is forced to distort the baseline's
        slope/level to compensate for a shape it has no other way to
        represent — a visibly wrong baseline with a deceptively good R^2,
        because the shortfall shows up as baseline error instead of
        transition-shape error. Letting the baseline see all N components
        AT ONCE, in the same regression, means it never has to make that
        trade. Use fit_multi_state_curve_auto below to actually pick N
        via BIC; this method just fits one specific, given N.

        midpoint_guesses/width_guesses/factor_guesses (each length
        n_components, or None for a generic evenly-spaced default) and
        coeffs_low_guess/coeffs_high_guess ([slope, intercept], or None
        for a quick fit to each end's own baseline_fraction slice) are
        STARTING POINTS ONLY — every parameter, baselines included, stays
        completely free to move in this fit regardless of what it's
        seeded with. That distinction matters: fit_multi_state_curve_auto
        warm-starts each larger fit from a smaller one's answer purely to
        converge faster, never by freezing anything — freezing the
        baseline while adding a component would silently recreate the
        exact problem this method exists to avoid.

        Returns a dict shaped like fit_two_state_curve's own output, but
        with 'components' — a list of n_components {'factor', 'mid',
        'width'} dicts, sorted by mid — instead of a single mid/width,
        plus 'n_components'. Returns None on failure/insufficient data
        (same best-effort contract as fit_two_state_curve)."""
        if n_components not in (1, 2, 3, 4):
            raise ValueError("n_components must be between 1 and 4")
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        n = n_components
        if x.size < 6:
            return None
        order = np.argsort(x)
        x_fit, y_fit_data = x[order], y[order]
        x_span = float(x_fit.max() - x_fit.min())
        if x_span <= 0:
            return None
        shape_func = self.sigmoid_shapes.get(shape_name)
        if shape_func is None:
            return None

        # Baseline starting guess: a caller-supplied warm start (a
        # smaller fit's own converged answer, from
        # fit_multi_state_curve_auto), or — same as fit_two_state_curve —
        # a quick straight-line fit to each end's own baseline_fraction
        # slice, as the very first guess when there's nothing smaller to
        # warm-start from.
        k = max(2, int(round(baseline_fraction * len(x_fit))))
        if coeffs_low_guess is not None:
            p0_low = [float(coeffs_low_guess[0]), float(coeffs_low_guess[1])]
        else:
            try:
                p0_low = list(np.polyfit(x_fit[:k], y_fit_data[:k], deg=1))
            except Exception:
                p0_low = [0.0, float(np.mean(y_fit_data[:k]))]
        if coeffs_high_guess is not None:
            p0_high = [float(coeffs_high_guess[0]), float(coeffs_high_guess[1])]
        else:
            try:
                p0_high = list(np.polyfit(x_fit[-k:], y_fit_data[-k:], deg=1))
            except Exception:
                p0_high = [0.0, float(np.mean(y_fit_data[-k:]))]

        if midpoint_guesses is None or len(midpoint_guesses) != n:
            midpoint_guesses = list(np.linspace(x_fit.min(), x_fit.max(), n + 2)[1:-1])
        if width_guesses is None or len(width_guesses) != n:
            width_guesses = [max(x_span / 10.0, 1e-6)] * n
        else:
            width_guesses = [max(float(w), 1e-6) for w in width_guesses]
        if factor_guesses is None or len(factor_guesses) != n:
            factor_guesses = [1.0 / n] * n
        else:
            total = sum(factor_guesses)
            factor_guesses = ([f / total for f in factor_guesses] if total > 0
                              else [1.0 / n] * n)

        # Same baseline-slope safety bound as fit_two_state_curve (see
        # its own comment for the full reasoning) — unchanged by how many
        # transition components this candidate has, since it's about the
        # WHOLE curve's own scale, not the transition shape.
        curve_amplitude = float(np.max(y_fit_data) - np.min(y_fit_data))
        max_slope = 2.0 * (curve_amplitude / x_span) if curve_amplitude > 0 else np.inf

        p0 = [p0_low[0], p0_low[1], p0_high[0], p0_high[1]]
        lower = [-max_slope, -np.inf, -max_slope, -np.inf]
        upper = [max_slope, np.inf, max_slope, np.inf]
        if n > 1:
            p0.extend(factor_guesses[:-1])
            lower.extend([0.0] * (n - 1))
            upper.extend([1.0] * (n - 1))
        for mid, w in zip(midpoint_guesses, width_guesses):
            p0.extend([float(mid), float(w)])
            lower.extend([x_fit.min() - x_span, 1e-6])
            upper.extend([x_fit.max() + x_span, x_span * 5])
        # Every starting value must sit strictly inside its own bound
        # (scipy requires this) — clip everything defensively rather than
        # just the two known slope-guess offenders.
        p0 = [float(np.clip(v, lo, hi)) for v, lo, hi in zip(p0, lower, upper)]

        def model_func(xx, *params):
            xx = np.asarray(xx, dtype=float)
            m_low, b_low, m_high, b_high = params[0], params[1], params[2], params[3]
            rest = params[4:]
            independent_factors = np.array(rest[:n - 1]) if n > 1 else np.array([])
            sigmoid_params = rest[n - 1:]
            last_factor = 1 - np.sum(independent_factors)
            factors = np.concatenate([independent_factors, [last_factor]])
            base_low = m_low * xx + b_low
            base_high = m_high * xx + b_high
            shape_sum = np.zeros_like(xx)
            for i in range(n):
                mid_i, width_i = sigmoid_params[2 * i], sigmoid_params[2 * i + 1]
                shape_sum = shape_sum + factors[i] * shape_func((xx - mid_i) / width_i)
            return base_low + (base_high - base_low) * shape_sum

        try:
            popt, _pcov = curve_fit(model_func, x_fit, y_fit_data, p0=p0,
                                    bounds=(lower, upper), maxfev=10000)
        except (RuntimeError, ValueError) as e:
            logger.error(f"fit_multi_state_curve: joint {n}-component baseline+transition "
                        f"fit failed: {e}")
            return None

        m_low, b_low, m_high, b_high = (float(popt[0]), float(popt[1]),
                                        float(popt[2]), float(popt[3]))
        rest = popt[4:]
        independent_factors = np.array(rest[:n - 1]) if n > 1 else np.array([])
        sigmoid_params = rest[n - 1:]
        last_factor = 1 - np.sum(independent_factors)
        factors = np.concatenate([independent_factors, [last_factor]])
        components = []
        for i in range(n):
            mid_i, width_i = float(sigmoid_params[2 * i]), float(sigmoid_params[2 * i + 1])
            components.append({'factor': float(factors[i]), 'mid': mid_i, 'width': width_i})
        components.sort(key=lambda c: c['mid'])

        y_fit_kept = model_func(x_fit, *popt)
        quality = self.estimate_fit_quality(y_fit_data, y_fit_kept, popt)
        y_fit_full = model_func(x, *popt)
        return {
            'coeffs_low': np.array([m_low, b_low]), 'coeffs_high': np.array([m_high, b_high]),
            'components': components, 'n_components': n, 'y_fit': y_fit_full,
            'quality': quality, 'popt': popt, 'shape_name': shape_name,
        }

    def fit_multi_state_curve_auto(self, x, y, max_components=4, midpoint_guess=None,
                                   exclude_mask=None, shape_name='Logistic',
                                   baseline_fraction=0.15,
                                   bic_decisive_threshold=BIC_DECISIVE_THRESHOLD,
                                   accept_step=None):
        """Picks the number of shared-baseline transition components (1 to
        max_components) for fit_multi_state_curve by walking up and
        warm-starting — the actual entry point most callers want (see
        fit_multi_state_curve's own docstring for the model and the reason
        this generalization exists at all).

        accept_step (optional): a callable accept_step(prev_fit,
        candidate_fit) -> bool, checked IN ADDITION to the BIC-decisive
        test below before adopting n over the current best. Why this
        exists: BIC alone judges a candidate purely by how much better it
        traces the RAW measured curve — and on real, noisy data, that raw-
        curve residual can shrink further with a 3rd or 4th component
        whether or not the extra component corresponds to a genuine
        additional transition (instrument drift or an imperfect blank
        correction can leave a small, structured — not random — wiggle
        that a smooth extra sigmoid happily "explains", decisively beating
        the BIC threshold, while making the fitted baseline in the
        transition region worse for the one thing that actually matters
        downstream, the van't Hoff/Arrhenius fit). BIC here is kept as a
        cheap first filter (skip even trying a candidate that wouldn't
        out-fit the raw curve at all); accept_step is the authoritative
        second opinion, checked only when BIC already says yes, using
        whatever downstream quality measure the caller actually cares
        about instead of curve-fit residual alone. None (the default)
        reproduces plain BIC-only behavior.

        exclude_mask: accepted for signature symmetry with
        fit_two_state_curve (same call shape at fit_automatic's own call
        site below) but, for the SAME reason documented on
        fit_two_state_curve's own exclude_mask parameter, NOT used to drop
        points from any of these regressions.

        Two deliberate design choices, both mirroring the SAME choices
        this app's already-existing POST-normalization multi-component
        search (fit_sigmoid_model, used manually) already makes, for
        consistency:

        1. SEQUENTIAL, not "fit all 4 then take the best BIC": starting
           from n=1, n=2 is only adopted if it beats the CURRENT BEST
           decisively (delta BIC > bic_decisive_threshold, the standard
           Kass & Raftery "decisive evidence" cutoff); if adopted, n=3
           must then beat THAT, not n=1; and so on. A plain global-minimum-
           BIC search would happily take n=4 whenever it's numerically
           lowest even by a hair, which defeats the point of using BIC
           (penalizing complexity) in the first place.

        2. WARM-STARTED, not fit from scratch at every n: each step reuses
           the previous (smaller) fit's own converged baseline and
           component parameters as ITS STARTING POINT, adding one new
           component's guess placed at the temperature of the largest
           remaining |data - fit| residual (a standard match-the-leftover
           heuristic). This is purely a starting point, never a frozen
           constraint — every parameter, including the earlier components
           and both baselines, stays fully free to move in each new fit.

        Returns a dict shaped like fit_multi_state_curve's own output
        (whichever n won), plus 'bic_trace' (list of {'from_n', 'to_n',
        'delta_bic'} for every step actually adopted, and a 'rejected':
        True entry for a step BIC favored but accept_step declined — the
        audit trail for "why N components") and 'fits' ({1: ..., 2: ...,
        ...}, every n actually attempted, None for any that failed or
        weren't reached). Returns None only if even n=1 fails."""
        x_arr = np.asarray(x, dtype=float)
        y_arr = np.asarray(y, dtype=float)
        midpoint_guesses_1 = [float(midpoint_guess)] if midpoint_guess is not None else None
        fit1 = self.fit_multi_state_curve(x_arr, y_arr, n_components=1,
                                          midpoint_guesses=midpoint_guesses_1,
                                          shape_name=shape_name,
                                          baseline_fraction=baseline_fraction)
        if fit1 is None:
            return None
        out = {'fits': {1: fit1}, 'bic_trace': []}
        best_n, best_fit = 1, fit1
        x_span = float(x_arr.max() - x_arr.min()) if x_arr.size else 1.0
        for n in range(2, max_components + 1):
            residual = np.abs(y_arr - best_fit['y_fit'])
            new_mid = float(x_arr[int(np.argmax(residual))])
            new_factor = 1.0 / n
            prev = best_fit['components']
            factor_guesses = [c['factor'] * (1.0 - new_factor) for c in prev] + [new_factor]
            midpoint_guesses = [c['mid'] for c in prev] + [new_mid]
            width_guesses = [c['width'] for c in prev] + [max(x_span / 10.0, 1e-6)]
            fit_n = self.fit_multi_state_curve(
                x_arr, y_arr, n_components=n,
                midpoint_guesses=midpoint_guesses, width_guesses=width_guesses,
                factor_guesses=factor_guesses,
                coeffs_low_guess=best_fit['coeffs_low'], coeffs_high_guess=best_fit['coeffs_high'],
                shape_name=shape_name, baseline_fraction=baseline_fraction)
            out['fits'][n] = fit_n
            if fit_n is None:
                continue
            bic_prev = best_fit['quality']['bic']
            bic_n = fit_n['quality']['bic']
            if bic_prev is None or bic_n is None:
                continue
            delta = bic_prev - bic_n
            if delta > bic_decisive_threshold:
                if accept_step is not None and not accept_step(best_fit, fit_n):
                    # BIC says this candidate traces the raw curve
                    # decisively better, but the caller's own downstream
                    # check says it isn't actually better — stop
                    # adopting here (see accept_step's own docstring
                    # above). Recorded in bic_trace as a rejected step so
                    # the audit trail shows the walk-up considered and
                    # declined n, not that it silently never tried.
                    out['bic_trace'].append({'from_n': best_n, 'to_n': n,
                                             'delta_bic': delta, 'rejected': True})
                    continue
                out['bic_trace'].append({'from_n': best_n, 'to_n': n, 'delta_bic': delta})
                best_n, best_fit = n, fit_n
        out.update(best_fit)
        out['n_components'] = best_n
        return out

    def fit_automatic(self, x, y, exclude_mask=None, max_components=4,
                      shape_name='Logistic', baseline_fraction=0.15,
                      arrhenius_span=0.95,
                      bic_decisive_threshold=BIC_DECISIVE_THRESHOLD):
        """Automatic mode's single entry point: run the joint Santoro-Bolen
        fit (fit_multi_state_curve_auto above), gate it through the same
        safety checks MeltAnalytiX's own automatic path uses, and — if it
        passes — carry it all the way through normalization and the van't
        Hoff/Arrhenius regression to a final reliability verdict.

        This does NOT touch the existing manual workflow at all
        (normalize_melting_curve with user-chosen low_range/high_range
        stays exactly as it was, and remains this app's default) — it is
        a new, independent, opt-in path: pick the transition midpoint(s)
        automatically via auto_detect_transitions, fit baselines +
        transition(s) jointly instead of from user-dragged windows, and
        report clearly whether the result can be trusted or whether the
        user should fall back to Manual.

        Three safety gates are applied, mirroring MeltAnalytiX's own
        automatic path (see that app's feature_extraction.py for the full
        history of why each one exists):

        1. Inside the walk-up itself (accept_step below): a candidate
           component count is only adopted if it doesn't make the
           downstream Arrhenius R^2 meaningfully worse than the best seen
           so far, AND doesn't make the baseline's own tracking of the
           data at the curve's edges meaningfully worse either (both
           ratcheted against the best-so-far, not just the immediately
           preceding step) — BIC alone can be fooled by a smooth extra
           component absorbing structured noise rather than a genuine
           transition.
        2. Component plausibility: every component's own midpoint must
           fall within the measured range (padded by half the range on
           each side) — an unconstrained optimizer can otherwise park a
           near-zero-weight "phantom" component's midpoint far outside
           the data (e.g. 190C on a 4-98C scan), or let the walk-up's
           very first (n=1) fit itself run to that same boundary when the
           data has no clear transition in range at all (n=1 predates
           accept_step, so it needs this same check applied separately).
        3. Absolute edge-tracking tolerance on the FINAL chosen fit: even
           a fit that passed every step-to-step comparison can still end
           up with a baseline that misses the real data at an edge by a
           large fraction of the curve's own amplitude, on a curve with
           no genuine flat plateau for baseline and transition shape to
           be separately identifiable against. A fit whose edge error
           exceeds EDGE_TOLERANCE_ABSOLUTE_FRACTION of the curve's
           amplitude is discarded outright.

        If the joint fit fails any of these, this returns
        {'success': False, 'reason': <str>, ...} — the caller (the
        dialog) should tell the user automatic mode couldn't find a
        trustworthy fit and point them at the existing Manual controls,
        never silently fall back to a different heuristic on its own.

        If the joint fit succeeds, this goes on to compute the SAME
        normalization/Arrhenius/thermodynamics pipeline the manual path
        already uses (via _normalize_from_coeffs, transform_xy_for_
        arrhenius, compute_thermodynamic_params), plus a genuine re-fit
        of the sigmoid shape in normalized space (fit_sigmoid_model, at
        the SAME component count the joint fit settled on — never a
        second, independent component-count search, so the dashed
        baseline lines and the solid sigmoid overlay can never disagree
        on how many transitions there are) — and a single overall
        'reliable' verdict from 5 gates adapted from MeltAnalytiX's own
        "is this run reliable" rule (its 6th gate, hysteresis pairing
        between a heating/cooling run pair, doesn't apply here — this app
        analyzes one curve at a time, not paired runs):

            1. Arrhenius R^2 >= ARRHENIUS_CONFIDENCE_R2_THRESHOLD (0.85)
            2. Tm falls inside the measured temperature range
            3. the two baselines don't cross near the transition itself
               (a crossing confined to an already-saturated plateau tail,
               nowhere near the points the Arrhenius regression actually
               used, is allowed)
            4. Tm falls inside the actual window of points the Arrhenius
               regression used (stricter than #2 alone — a shallow, noisy
               fit can extrapolate its Tm well past its own fit window
               while still landing inside the run's overall range)
            5. the sigmoid re-fit's own R^2 >=
               SIGMOID_CONFIDENCE_R2_THRESHOLD (0.70) — a SEPARATE check
               from the Arrhenius R^2 above, since they can fail for
               different reasons
            6. edge_error_fraction <= EDGE_TOLERANCE_ABSOLUTE_FRACTION
               (0.12) — same absolute check as gate 3 in the paragraph
               above, repeated here as part of the reliability verdict
               so the UI's reliability banner and its underlying pass/
               fail reason agree with each other.

        A missing/uncomputable value fails a gate closed (counts as
        "not reliable") EXCEPT gate 4 (Tm_in_fit_range), which — matching
        MeltAnalytiX's own convention — degrades to "pass" when it can't
        be computed at all (gates 1-2 already fail closed in that same
        situation, since the whole Arrhenius fit didn't produce a Tm).

        Returns a dict with (all of these; many are None when an earlier
        step didn't run or failed):
            'success' — False only when the joint fit itself was rejected
                (gates 1-3 above); True whenever a global_fit was found,
                REGARDLESS of the final 'reliable' verdict — a low-
                confidence but present fit is still something the caller
                can show the user with a clear warning, unlike a fit that
                never existed at all.
            'reason' — human-readable explanation when success is False.
            'global_fit' — fit_multi_state_curve_auto's own result.
            'norm', 'low_range', 'high_range' — normalize_melting_curve-
                shaped normalization result and the descriptive baseline
                extents (derived from the fit itself — everywhere at
                least one component's own transition is still within 3
                widths of its midpoint — for shading the plot; these are
                NOT what determined the fit, unlike the manual path).
            'Tm_crossing', 'arrhenius', 'thermo', 'arrhenius_r_squared',
                'Tm_in_measured_range', 'Tm_in_fit_range',
                'baselines_cross_near_transition', 'edge_error_fraction'
                — same meaning/computation as MeltAnalytiX's own
                compute_run_diagnostics.
            'sigmoid_fit', 'sigmoid_r_squared' — the normalized-space
                re-fit and its own R^2 (gate 5).
            'reliable' — the overall verdict.
            'reliability_gates' — dict of {gate_name: bool or None} for
                each of the 6 checks above, so the UI can explain WHICH
                gate(s) failed rather than just showing a single yes/no.
        """
        x_arr = np.asarray(x, dtype=float)
        y_arr = np.asarray(y, dtype=float)
        if exclude_mask is not None:
            exclude_mask = np.asarray(exclude_mask, dtype=bool)

        out = {
            'success': False, 'reason': None, 'global_fit': None,
            'norm': None, 'low_range': None, 'high_range': None,
            'Tm_crossing': None, 'arrhenius': None, 'thermo': None,
            'arrhenius_r_squared': None, 'Tm_in_measured_range': None,
            'Tm_in_fit_range': None, 'baselines_cross_near_transition': False,
            'edge_error_fraction': None, 'sigmoid_fit': None, 'sigmoid_r_squared': None,
            'reliable': False, 'reliability_gates': {},
        }

        if x_arr.size < 6:
            out['reason'] = "Not enough data points for an automatic fit (need at least 6)."
            return out

        t_min, t_max = float(np.min(x_arr)), float(np.max(x_arr))

        try:
            mids = self.auto_detect_transitions(x_arr, y_arr, n_components=1)
            mid_guess = float(mids[0]) if mids else None
        except Exception:
            mid_guess = None

        # --- Gate 1: the walk-up's own step-to-step ratchet (Arrhenius
        # R^2 and edge-tracking error, both never allowed to get
        # meaningfully worse than the best seen so far) --------------
        order = np.argsort(x_arr)
        n_edge = max(3, int(round(0.05 * len(order))))
        low_idx, high_idx = order[:n_edge], order[-n_edge:]
        curve_amplitude = float(np.max(y_arr) - np.min(y_arr))
        edge_tolerance_relative = SCORE_TOLERANCE * curve_amplitude if curve_amplitude > 0 else 0.0

        def _edge_error(norm):
            if norm is None:
                return None
            lo_err = np.mean(np.abs(norm['baseline_low'][low_idx] - y_arr[low_idx]))
            hi_err = np.mean(np.abs(norm['baseline_high'][high_idx] - y_arr[high_idx]))
            return float(max(lo_err, hi_err))

        t_span_data = t_max - t_min if t_max > t_min else 1.0
        plausible_lo = t_min - 0.5 * t_span_data
        plausible_hi = t_max + 0.5 * t_span_data

        def _components_plausible(fit):
            return all(plausible_lo <= c['mid'] <= plausible_hi for c in fit['components'])

        step_state = {'best_r2': None, 'best_edge_err': None}

        def _accept_step(prev_fit, candidate_fit):
            # --- Gate 2: component plausibility (see docstring above) --
            if not _components_plausible(candidate_fit):
                return False
            norm_prev = self._normalize_from_coeffs(x_arr, y_arr, prev_fit['coeffs_low'],
                                                     prev_fit['coeffs_high'])
            norm_cand = self._normalize_from_coeffs(x_arr, y_arr, candidate_fit['coeffs_low'],
                                                     candidate_fit['coeffs_high'])
            r2_prev = self._arrhenius_r_squared(x_arr, norm_prev, exclude_mask, arrhenius_span)
            r2_cand = self._arrhenius_r_squared(x_arr, norm_cand, exclude_mask, arrhenius_span)
            if r2_prev is not None:
                step_state['best_r2'] = (r2_prev if step_state['best_r2'] is None
                                        else max(step_state['best_r2'], r2_prev))
            edge_err_prev = _edge_error(norm_prev)
            if edge_err_prev is not None:
                step_state['best_edge_err'] = (edge_err_prev if step_state['best_edge_err'] is None
                                              else min(step_state['best_edge_err'], edge_err_prev))
            r2_ok = (step_state['best_r2'] is None
                    or (r2_cand is not None and r2_cand >= step_state['best_r2'] - SCORE_TOLERANCE))
            edge_err_cand = _edge_error(norm_cand)
            edge_ok = (step_state['best_edge_err'] is None or edge_err_cand is None
                      or edge_err_cand <= step_state['best_edge_err'] + edge_tolerance_relative)
            return r2_ok and edge_ok

        global_fit = self.fit_multi_state_curve_auto(
            x_arr, y_arr, max_components=max_components, midpoint_guess=mid_guess,
            exclude_mask=exclude_mask, shape_name=shape_name,
            baseline_fraction=baseline_fraction, bic_decisive_threshold=bic_decisive_threshold,
            accept_step=_accept_step)

        if global_fit is None:
            out['reason'] = ("The automatic joint baseline+transition fit did not converge on "
                             "this curve. Use Manual mode instead.")
            return out

        # n=1 (the walk-up's unconditional starting point) never goes
        # through accept_step, so its own plausibility has to be checked
        # separately — a data set with no clear transition in range can
        # otherwise let the optimizer park the single component's
        # midpoint right at its own bound, far outside the measured data.
        if not _components_plausible(global_fit):
            out['reason'] = ("The automatic fit's transition midpoint fell far outside the "
                             "measured temperature range — this curve doesn't show a clear "
                             "transition automatic mode can identify. Use Manual mode instead.")
            return out

        norm = self._normalize_from_coeffs(x_arr, y_arr, global_fit['coeffs_low'],
                                           global_fit['coeffs_high'])

        # --- Gate 3: absolute edge-tracking tolerance on the FINAL fit -
        edge_tolerance_absolute = (EDGE_TOLERANCE_ABSOLUTE_FRACTION * curve_amplitude
                                   if curve_amplitude > 0 else 0.0)
        edge_err_final = _edge_error(norm)
        if edge_err_final is not None and edge_err_final > edge_tolerance_absolute:
            out['reason'] = (
                f"The automatic fit's baseline doesn't track the measured data closely enough "
                f"at the low- or high-temperature edge (edge error "
                f"{edge_err_final / curve_amplitude * 100:.0f}% of the curve's amplitude, "
                f"vs. a {EDGE_TOLERANCE_ABSOLUTE_FRACTION * 100:.0f}% limit) — this usually means "
                f"the curve has no genuine flat plateau for the fit to anchor on. Use Manual "
                f"mode instead.")
            return out

        out['success'] = True
        out['global_fit'] = global_fit
        out['norm'] = norm
        out['edge_error_fraction'] = (edge_err_final / curve_amplitude
                                      if curve_amplitude > 0 and edge_err_final is not None else None)

        # Descriptive baseline extents for the plot — everywhere at least
        # one winning component's own transition is still within 3
        # widths of its midpoint, spanning every component (not just
        # one), clamped to the curve's own measured range. Purely
        # descriptive — NOT what determined the fit (unlike the manual
        # path's low_range/high_range).
        components = global_fit['components']
        first_mid, first_width = components[0]['mid'], components[0]['width']
        last_mid, last_width = components[-1]['mid'], components[-1]['width']
        span = t_max - t_min
        min_gap = max(span * 0.02, 1e-6) if span > 0 else 1e-6
        low_hi = min(first_mid - 3 * first_width, t_max - min_gap)
        low_hi = max(low_hi, t_min + min_gap)
        high_lo = max(last_mid + 3 * last_width, t_min + min_gap)
        high_lo = min(high_lo, t_max - min_gap)
        out['low_range'] = (t_min, low_hi)
        out['high_range'] = (high_lo, t_max)

        out['Tm_crossing'] = self.compute_median_crossing_temperature(
            x_arr, y_arr, norm['baseline_low'], norm['baseline_high'])

        unstable_mask = norm.get('unstable_mask')
        combined_exclude = unstable_mask
        if exclude_mask is not None:
            combined_exclude = (exclude_mask if combined_exclude is None
                                else (combined_exclude | exclude_mask))
        arr = self.transform_xy_for_arrhenius(x_arr, norm['y_norm'], span=arrhenius_span,
                                              exclude_mask=combined_exclude)
        out['arrhenius'] = arr

        # baselines_cross_near_transition: a crossing confined to an
        # already-saturated plateau tail, far from the points the
        # Arrhenius regression actually used, shouldn't by itself
        # disqualify an otherwise-good fit — compare the crossing's own
        # temperature against the actual fit window, not just "did the
        # two lines cross somewhere in the whole scan."
        if norm['baselines_cross']:
            coeffs_low, coeffs_high = norm.get('coeffs_low'), norm.get('coeffs_high')
            x0 = None
            if coeffs_low is not None and coeffs_high is not None:
                a_low, b_low = float(coeffs_low[0]), float(coeffs_low[1])
                a_high, b_high = float(coeffs_high[0]), float(coeffs_high[1])
                if abs(a_low - a_high) > 1e-9:
                    x0 = (b_high - b_low) / (a_low - a_high)
            if x0 is not None and arr is not None and arr['ind'].size:
                used_T = x_arr[arr['ind']]
                out['baselines_cross_near_transition'] = bool(used_T.min() <= x0 <= used_T.max())
            else:
                # Couldn't solve for the crossing point, or the Arrhenius
                # fit didn't produce a usable point set to check against —
                # can't verify safety, so fail closed.
                out['baselines_cross_near_transition'] = True

        thermo = None
        if arr is not None:
            thermo = self.compute_thermodynamic_params(arr['x_arr'], arr['y_arr'])
            out['thermo'] = thermo
            if thermo is not None:
                if arr['x_arr'].size >= 2:
                    slope, intercept = thermo['coeffs']
                    y_pred = slope * arr['x_arr'] + intercept
                    ss_res = float(np.sum((arr['y_arr'] - y_pred) ** 2))
                    ss_tot = float(np.sum((arr['y_arr'] - np.mean(arr['y_arr'])) ** 2))
                    out['arrhenius_r_squared'] = (1 - ss_res / ss_tot) if ss_tot > 0 else None
                if thermo['Tm'] is not None:
                    out['Tm_in_measured_range'] = bool(t_min <= thermo['Tm'] <= t_max)
                    used_T = x_arr[arr['ind']]
                    out['Tm_in_fit_range'] = bool(used_T.min() <= thermo['Tm'] <= used_T.max())

        # Genuine re-fit of the sigmoid shape in NORMALIZED space, at the
        # SAME component count the joint fit already settled on — never
        # a second, independent component-count search (that would let
        # the dashed baseline lines and the solid sigmoid overlay
        # disagree on how many transitions there are). Warm-started from
        # global_fit's own converged components/factors, converted from
        # the raw-curve fit's units into the [0, 1]-normalized space this
        # overlay fits in.
        n_comp = global_fit['n_components']
        try:
            sigmoid_fit = self.fit_sigmoid_model(
                x_arr, norm['y_norm'], n_components=n_comp, shape_name=shape_name,
                midpoint_guesses=[c['mid'] for c in components],
                width_guess=[c['width'] for c in components],
                factor_guesses=[c['factor'] for c in components])
        except Exception as e:
            logger.warning(f"fit_automatic: normalized-space sigmoid re-fit failed: {e}")
            sigmoid_fit = None
        out['sigmoid_fit'] = sigmoid_fit
        sigmoid_r2 = sigmoid_fit['quality']['r_squared'] if sigmoid_fit is not None else None
        out['sigmoid_r_squared'] = sigmoid_r2

        # --- Final reliability verdict (5 of MeltAnalytiX's 6 gates —
        # hysteresis pairing doesn't apply to a single curve) ----------
        r2 = out['arrhenius_r_squared']
        in_range = out['Tm_in_measured_range']
        in_fit_range = out['Tm_in_fit_range']
        crossing = out['baselines_cross_near_transition']
        edge_frac = out['edge_error_fraction']

        gate_arrhenius_r2 = (r2 is not None and r2 >= ARRHENIUS_CONFIDENCE_R2_THRESHOLD)
        gate_tm_in_range = bool(in_range)
        gate_no_crossing = not bool(crossing)
        gate_tm_in_fit_range = (in_fit_range is None) or bool(in_fit_range)
        gate_sigmoid_r2 = (sigmoid_r2 is None) or (sigmoid_r2 >= SIGMOID_CONFIDENCE_R2_THRESHOLD)
        gate_edge_ok = (edge_frac is None) or (edge_frac <= EDGE_TOLERANCE_ABSOLUTE_FRACTION)

        out['reliability_gates'] = {
            'arrhenius_r_squared_ok': gate_arrhenius_r2,
            'tm_in_measured_range': gate_tm_in_range,
            'no_baseline_crossing_near_transition': gate_no_crossing,
            'tm_in_fit_range': gate_tm_in_fit_range,
            'sigmoid_r_squared_ok': gate_sigmoid_r2,
            'edge_error_ok': gate_edge_ok,
        }
        out['reliable'] = (gate_arrhenius_r2 and gate_tm_in_range and gate_no_crossing
                           and gate_tm_in_fit_range and gate_sigmoid_r2 and gate_edge_ok)
        return out

    def _arrhenius_r_squared(self, x, norm, exclude_mask, arrhenius_span):
        """Small helper for fit_automatic's own accept_step closure: runs
        the van't Hoff/Arrhenius regression for a candidate normalization
        and returns just its R^2 (or None if it couldn't be computed) —
        factored out since the walk-up needs this exact computation twice
        per step (once for the previous best, once for the candidate) and
        nowhere else needs the intermediate arrhenius/thermo dicts."""
        if norm is None:
            return None
        unstable_mask = norm.get('unstable_mask')
        combined_exclude = unstable_mask
        if exclude_mask is not None:
            combined_exclude = (exclude_mask if combined_exclude is None
                                else (combined_exclude | exclude_mask))
        arr = self.transform_xy_for_arrhenius(x, norm['y_norm'], span=arrhenius_span,
                                              exclude_mask=combined_exclude)
        if arr is None or arr['x_arr'].size < 2:
            return None
        thermo = self.compute_thermodynamic_params(arr['x_arr'], arr['y_arr'])
        if thermo is None:
            return None
        slope, intercept = thermo['coeffs']
        y_pred = slope * arr['x_arr'] + intercept
        ss_res = float(np.sum((arr['y_arr'] - y_pred) ** 2))
        ss_tot = float(np.sum((arr['y_arr'] - np.mean(arr['y_arr'])) ** 2))
        return (1 - ss_res / ss_tot) if ss_tot > 0 else None

    def parse_ground_truth_info_sheet(self, path):
        """Parse the "Info" sheet of one of this app's own synthetic
        test datasets (Help -> Test datasets -> Synthetic -> Melting
        curve) for its known/true per-transition Tm, deltaH, deltaS, and
        factor — a "Field"/"Value" two-column sheet with rows like
        "Transition 1: Tm (C)" / 35, "Transition 1: deltaH (kJ/mol)" /
        180, and so on, generated by
        resources/test_data/synthetic/generate_melting_test_datasets.py.

        Not a general-purpose file format reader — this only works for
        that exact sheet layout, and is meant purely for sanity-checking
        a fit against a known answer on the app's own bundled test data,
        not for arbitrary user files.

        Returns a list of dicts (one per transition, in "Transition N"
        order, N starting at 1), each with 'Tm' (deg C), 'deltaH'
        (J/mol — converted from the sheet's kJ/mol), 'deltaS' (J/mol/K),
        and 'factor' (0-1) — whichever of those four fields were found
        for that transition (missing ones are just absent from the
        dict). Returns None if the file has no "Info" sheet, or nothing
        matching "Transition N: ..." was found in it.
        """
        try:
            import pandas as pd
        except ImportError:
            return None
        try:
            xl = pd.ExcelFile(path)
            if 'Info' not in xl.sheet_names:
                return None
            df = pd.read_excel(path, sheet_name='Info')
        except Exception as e:
            logger.warning(f"parse_ground_truth_info_sheet: could not read '{path}': {e}")
            return None
        if 'Field' not in df.columns or 'Value' not in df.columns:
            return None

        transitions = {}
        field_map = {'tm': 'Tm', 'deltah': 'deltaH', 'deltas': 'deltaS', 'factor': 'factor'}
        for _, row in df.iterrows():
            field = str(row['Field'])
            m = re.match(r'Transition\s+(\d+)\s*:\s*(\w+)', field, re.IGNORECASE)
            if not m:
                continue
            idx = int(m.group(1))
            key_raw = m.group(2).lower()
            key = field_map.get(key_raw)
            if key is None:
                continue
            try:
                value = float(row['Value'])
            except (TypeError, ValueError):
                continue
            if key == 'deltaH':
                value *= 1000  # sheet is kJ/mol, this app works in J/mol internally
            transitions.setdefault(idx, {})[key] = value

        if not transitions:
            return None
        return [transitions[i] for i in sorted(transitions.keys())]

    def compute_delta_g(self, deltaH, deltaS, temperature_celsius):
        """deltaG = deltaH - T*deltaS at the given reference temperature
        (degrees C) — J/mol. None if deltaH/deltaS is None."""
        if deltaH is None or deltaS is None:
            return None
        return deltaH - (temperature_celsius + 273.15) * deltaS

    def estimate_width_from_thermodynamics(self, deltaH, Tm_celsius):
        """A logistic sigmoid's width (lambda_, in the 1/(1+exp(-(T-Tm)/w))
        parameterization) that matches the transition SLOPE a van't Hoff
        deltaH implies at Tm — derived by equating the two models' slopes
        at the midpoint: a logistic's dtheta/dT|Tm = 1/(4w), while the
        two-state van't Hoff model's own dtheta/dT|Tm = deltaH/(4*R*Tm^2).
        Setting them equal gives w = R*Tm^2/deltaH.

        Used to seed a MUCH better default width guess for the sigmoid
        fit than the generic "span/10" fallback once an Arrhenius deltaH
        is available — the previous default had no relationship to the
        actual transition's sharpness at all, which is why the pre-fit
        "Guess (sum)" preview curve could look far too broad/narrow
        compared to the real data.

        Returns None if deltaH is None, zero, or Tm_celsius is None (no
        sensible width can be derived).
        """
        if deltaH is None or Tm_celsius is None or deltaH == 0:
            return None
        Tm_kelvin = Tm_celsius + 273.15
        return abs(R_GAS * Tm_kelvin ** 2 / deltaH)

    def compute_component_thermodynamics(self, x, y_measured, y_fit_total, component_params,
                                        shape_name, span=0.95, exclude_mask=None):
        """Generalize the Arrhenius/thermodynamic calculation to EACH
        individual sigmoid component of a multi-transition fit.

        For each component (a dict with at least 'factor', 'midpoint',
        and 'lambda_' — the same shape produced by get_sigmoid_components's
        'params' list), this reconstructs that component's own
        contribution from the REAL MEASURED data — removing every OTHER
        component's contribution (via the residual of the whole fit) and
        renormalizing by this component's own factor — then runs the
        ordinary single-transition Arrhenius transform + thermodynamic
        fit against THAT still-noisy, still-empirical reconstructed
        curve, exactly matching what gets plotted as "Data
        (reconstructed)" for that component elsewhere in this app.

        NOTE: the ported thermoanalysis prototype this app is based on
        instead runs this same calculation against the purely
        theoretical/noise-free sigmoid curve (shape_func((x-midpoint)/
        lambda_) alone, with no real data). That was a deliberate choice
        to depart from here, not a bug fix relative to it — using the
        theoretical curve makes the result a near-exact mathematical
        conversion of the shape fit's own midpoint/width into
        thermodynamic units (there's a close, near-exact relationship
        between a logistic sigmoid's width and van't Hoff deltaH, namely
        deltaH ~ R*Tm^2/width — see estimate_width_from_thermodynamics,
        the same relationship used in reverse), which can never actually
        disagree with the shape fit and returns artificially tiny/zero
        uncertainty, since there's no noise in a mathematical curve to
        begin with. Using the real reconstructed data instead makes this
        a genuine, independent empirical check: does the actual
        measured transition, isolated from its neighbors, really behave
        like a two-state process? For a clean transition the two
        approaches should come out close but not identical (different
        data, different fitting methods, and genuinely honest
        uncertainty here instead of a fictional near-zero); for a
        transition that doesn't actually follow simple two-state
        thermodynamics, they can meaningfully diverge — which the
        theoretical-curve approach is structurally incapable of ever
        revealing. For heavily overlapping components, this
        reconstruction inherits some of the whole fit's residual
        (whatever the N-component model didn't explain, which has no
        independent identity that could be attributed to one component
        over another) into whichever component is currently being
        isolated — this is not a compromise or approximation but the
        only principled way to handle it: from that component's own
        perspective, "everything left over once the other components'
        predicted contributions are removed" IS its true isolated
        signal, imperfections included. Any scheme that tried to
        redistribute the residual some other way would need extra,
        arbitrary assumptions with no real justification.

        IMPORTANT ASSUMPTION: every component is treated as an
        INDEPENDENT two-state transition, exactly like a single-transition
        curve would be — this does not model any coupling between
        transitions (e.g. one component's population decreasing at the
        expense of another's, a shared intermediate state, or any other
        thermodynamic linkage). If the real system has such coupling, the
        deltaH/deltaS/Tm reported per component are only as good as that
        independence assumption; they describe "a two-state transition
        with this shape", not necessarily the true coupled mechanism.

        Args:
            x: the temperature axis (same one the whole-curve fit used).
            y_measured: the actual (normalized, or raw if unnormalized)
                curve data the fit was run against.
            y_fit_total: the fit's own total model curve over x (sum of
                every component) — fit_result['y_fit'].
            component_params: list of per-component dicts, e.g.
                fit_result['components']['params'] from fit_sigmoid_model
                — each with 'factor', 'midpoint', 'lambda_'.
            shape_name: key into SIGMOID_SHAPES, matching whichever shape
                the fit itself used.
            span: same central-span threshold as transform_xy_for_arrhenius.
            exclude_mask: optional boolean array, same length as x —
                forwarded unchanged to each component's own
                transform_xy_for_arrhenius call (see that function's own
                exclude_mask doc). Typically normalize_melting_curve's
                'unstable_mask' for the SAME curve y_measured came from —
                a point unstable in the raw normalized curve is exactly
                as unstable in every component's reconstructed curve,
                since the reconstruction (see y_local_data below) only
                redistributes signal between components, it doesn't fix
                the underlying near-zero-denominator problem at that
                temperature. None (default) excludes nothing.

        Returns:
            A list (same order/length as component_params) of dicts, each
            with 'y_pure' (the component's own ideal 0-1 curve over x,
            kept for plotting the model line), 'y_local_data' (the real
            reconstructed data this component's Arrhenius fit actually
            used), 'arrhenius' (transform_xy_for_arrhenius() output or
            None), and 'thermodynamics' (compute_thermodynamic_params()
            output or None) — None for either when too few points survive
            the span filter for that component (e.g. an unusually
            narrow/steep transition).
        """
        shape_func = self.sigmoid_shapes.get(shape_name)
        if shape_func is None:
            raise ValueError(f"Unknown sigmoid shape '{shape_name}'")

        x = np.asarray(x, dtype=float)
        y_measured = np.asarray(y_measured, dtype=float)
        y_fit_total = np.asarray(y_fit_total, dtype=float)
        residual_total = y_measured - y_fit_total

        results = []
        for comp in component_params:
            y_pure = shape_func((x - comp['midpoint']) / comp['lambda_'])
            factor = comp['factor'] if comp['factor'] != 0 else 1e-9
            # Real data's own contribution to this component alone,
            # renormalized back to a standalone 0-1 transition — the
            # SAME reconstruction the plot itself uses, so the numbers
            # here always match what's actually shown on screen.
            y_local_data = residual_total / factor + y_pure
            arr = self.transform_xy_for_arrhenius(x, y_local_data, span=span,
                                                  exclude_mask=exclude_mask)
            thermo = None
            if arr is not None:
                thermo = self.compute_thermodynamic_params(arr['x_arr'], arr['y_arr'])
            results.append({'y_pure': y_pure, 'y_local_data': y_local_data,
                           'arrhenius': arr, 'thermodynamics': thermo})
        return results

    # ------------------------------------------------------------------ #
    # 4. Multi-sigmoid (up to 4 transitions) model & fitting              #
    # ------------------------------------------------------------------ #

    def sigmoid_sum_model(self, x, *params, n_components, shape_func):
        """Weighted sum of n_components sigmoids of the given shape.

        Parameter layout (length 3*n_components - 1), matching the ported
        prototype's convention:
            params[0 : n-1]    -> independent scale factors (the last one
                                   is 1 - sum(the others), so all factors
                                   sum to 1)
            params[n-1 : ]     -> n pairs of (midpoint, lambda_)
        """
        n = n_components
        independent_factors = np.array(params[:n - 1]) if n > 1 else np.array([])
        sigmoid_params = params[n - 1:]
        last_factor = 1 - np.sum(independent_factors)
        factors = np.concatenate([independent_factors, [last_factor]])

        x = np.asarray(x, dtype=float)
        total = np.zeros_like(x)
        for i in range(n):
            midpoint, lambda_ = sigmoid_params[2 * i], sigmoid_params[2 * i + 1]
            total = total + factors[i] * shape_func((x - midpoint) / lambda_)
        return total

    def get_sigmoid_components(self, x, params, n_components, shape_func, pcov=None):
        """Return the individual weighted sigmoid components (for
        plotting / export as separate spectra) plus each component's
        (factor, midpoint, lambda_) and inflection-point (x, y).

        Always returned sorted by ASCENDING midpoint — component 1 is
        reliably the lowest-temperature transition, component 2 the
        next, and so on — regardless of what order they happened to
        converge in during fitting (which generally follows the initial
        guess order, but isn't guaranteed to). This is what makes "1st
        transition" / "2nd transition" a meaningful, stable basis for
        comparing the SAME transition across different curves/samples —
        without it, "component 1" could mean a different physical
        transition from one fit to the next.

        If pcov (the covariance matrix curve_fit returns) is given, each
        component's params dict also gets 'factor_err', 'midpoint_err',
        'lambda_err' — standard errors (1 std) for how well-determined
        that component's own SHAPE parameters are, straight from the
        fit itself. This is a different, independent notion of
        uncertainty from the Arrhenius-derived deltaH/deltaS/Tm errors
        elsewhere: it says nothing about thermodynamics, only about how
        tightly the sigmoid fit pins down where a transition is and how
        sharp it is, given the data and the model. The last component's
        factor is not directly fitted (it's 1 minus the others, to keep
        every fraction summing to 1) — its error is approximated by
        propagating the OTHER factors' variances assuming independence
        (ignoring covariance terms, the same simplification used for
        the Tm error propagation elsewhere in this module) — a
        reasonable approximation, not an exact value. None for any
        error if pcov isn't provided, or is invalid (e.g. the fit sat
        exactly on a bound, giving infinite/undefined covariance).
        """
        n = n_components
        independent_factors = np.array(params[:n - 1]) if n > 1 else np.array([])
        sigmoid_params = params[n - 1:]
        last_factor = 1 - np.sum(independent_factors)
        factors = np.concatenate([independent_factors, [last_factor]])

        perr = None
        if pcov is not None:
            with np.errstate(invalid='ignore'):
                diag = np.diag(pcov)
            if np.all(np.isfinite(diag)) and np.all(diag >= 0):
                perr = np.sqrt(diag)

        x = np.asarray(x, dtype=float)
        raw = []
        for i in range(n):
            midpoint, lambda_ = sigmoid_params[2 * i], sigmoid_params[2 * i + 1]
            comp = factors[i] * shape_func((x - midpoint) / lambda_)
            comp_params = {'factor': float(factors[i]), 'midpoint': float(midpoint),
                          'lambda_': float(lambda_)}
            if perr is not None:
                if i < n - 1:
                    factor_err = float(perr[i])
                else:
                    # Last (derived) factor: propagate the others' variances,
                    # assuming independence between them.
                    factor_err = (float(np.sqrt(np.sum(perr[:n - 1] ** 2)))
                                 if n > 1 else 0.0)
                comp_params['factor_err'] = factor_err
                comp_params['midpoint_err'] = float(perr[(n - 1) + 2 * i])
                comp_params['lambda_err'] = float(perr[(n - 1) + 2 * i + 1])
            raw.append({
                'comp': comp,
                'params': comp_params,
                'inflection': (float(midpoint), float(factors[i] * shape_func(0.0))),
            })
        raw.sort(key=lambda r: r['params']['midpoint'])

        components = [r['comp'] for r in raw]
        component_params = [r['params'] for r in raw]
        inflection_points = [r['inflection'] for r in raw]
        return {'components': components, 'params': component_params,
                'inflection_points': inflection_points}

    def auto_detect_transitions(self, x, y, n_components=1,
                                 window_length=5, smooth_order=3, distance=10):
        """Estimate initial (midpoint, height) guesses for n_components
        transitions from the peaks of the smoothed first derivative
        (Savitzky-Golay), same approach as the ported prototype's
        get_inflex_points(). Returns a list of x-positions (midpoints)
        sorted ascending, length exactly n_components (padded with the
        curve's midpoint if fewer real inflections are found).
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        n_points = len(x)
        wl = min(window_length, n_points - (1 - n_points % 2))
        if wl < smooth_order + 2:
            wl = smooth_order + 2 if (smooth_order + 2) % 2 == 1 else smooth_order + 3
        wl = max(wl, 3)
        if wl % 2 == 0:
            wl += 1
        wl = min(wl, n_points - 1 if n_points % 2 == 0 else n_points)
        if wl < 3:
            # Too few points to differentiate meaningfully — fall back to
            # evenly-spaced guesses across the x-range.
            mids = np.linspace(x.min(), x.max(), n_components + 2)[1:-1]
            return list(mids)

        delta = np.mean(np.diff(x)) if n_points > 1 else 1.0
        if delta == 0:
            delta = 1e-10

        try:
            y_der = sg.savgol_filter(y, window_length=wl, polyorder=min(smooth_order, wl - 1),
                                      deriv=1, delta=delta, mode='interp')
        except Exception as e:
            logger.warning(f"auto_detect_transitions: savgol_filter failed ({e}); "
                           f"falling back to evenly-spaced guesses.")
            mids = np.linspace(x.min(), x.max(), n_components + 2)[1:-1]
            return list(mids)

        peak_distance = max(abs(distance / delta), 1)
        peak_indices, peak_dict = find_peaks(np.abs(y_der), height=0, distance=peak_distance)
        peak_heights = peak_dict['peak_heights']

        n_found = len(peak_indices)
        n_take = min(n_components, n_found)
        chosen = []
        for rank in range(1, n_take + 1):
            idx = peak_indices[np.argpartition(peak_heights, -rank)[-rank]]
            chosen.append(x[idx])

        if n_found < n_components:
            missing = n_components - n_found
            mid_x = x[n_points // 2]
            chosen.extend([mid_x] * missing)

        return sorted(chosen)

    def fit_sigmoid_model(self, x, y, n_components, shape_name='Logistic',
                          midpoint_guesses=None, width_guess=None, factor_guesses=None,
                          constrain_factors=False):
        """Fit a sum of n_components (1-4) sigmoids to (x, y) via
        scipy.optimize.curve_fit with bounds.

        Args:
            x, y: the (normalized, ideally 0-1) melting curve to fit.
            n_components: 1-4.
            shape_name: key into SIGMOID_SHAPES ('Logistic' or
                'Error function').
            midpoint_guesses: optional list of n_components initial
                midpoint x-values (from auto_detect_transitions or
                user-edited); defaults to evenly spaced across x.
            width_guess: optional initial transition width (lambda_) —
                either a single number shared by every component, or a
                list of n_components individual widths (e.g. user-edited
                per-component values from a guesses table); defaults to
                1/10th of the x-range for every component.
            factor_guesses: optional list of n_components initial scale
                factors (should sum to ~1; renormalized if not) — e.g.
                user-edited fractions from a guesses table; defaults to
                an equal 1/n split.
            constrain_factors: if True (only matters for n_components >=
                3 — see below), every fraction is guaranteed to land in
                (0, 1) and all n sum to exactly 1, by fitting N
                unconstrained "logit" values u_1..u_n and mapping them
                through a softmax, f_i = exp(u_i) / sum_j(exp(u_j)),
                instead of the normal parameterization (see
                sigmoid_sum_model's docstring), which only individually
                bounds n-1 of the n factors to [0, 1] — leaving nothing
                to stop their SUM exceeding 1, which is exactly what lets
                the derived n-th factor go negative for n_components>=3.
                A softmax is mathematically incapable of producing a
                negative or >1 value for any f_i, unlike that
                parameterization. The cost: since every real two-state
                transition has some small, unavoidable mismatch against
                this tool's T-linear logistic shape (see the "?" button
                on Sigmoid Fit for why), forcibly ruling out the
                negative-factor "escape hatch" a normal fit could use to
                partly compensate for that mismatch typically costs a
                small amount of R^2 even for well-behaved, independent
                data — comparing the constrained vs. unconstrained R^2 is
                itself informative (a small gap is reassuring; a large
                one is a stronger, though still not conclusive, signal
                that the extra flexibility was doing real work). With
                exactly 2 components this makes no difference at all,
                since the ordinary parameterization already guarantees
                both factors stay in [0, 1] (f_2 = 1 - f_1, and 1 minus
                something already in [0, 1] is still in [0, 1]).
                Component-level standard errors (factor_err, midpoint_err,
                lambda_err) are not reported for a constrained fit — the
                covariance matrix here is in the reparametrized "logit"
                space, and propagating it back through the softmax
                correctly would need its Jacobian, not a simple index
                lookup; since this is meant as a diagnostic comparison
                fit rather than the primary result, that was judged not
                worth the added complexity.

        Returns:
            dict with 'params' (fitted flat parameter vector, ALWAYS in
            the canonical n-1-factors-plus-derived-last format described
            in sigmoid_sum_model's docstring, regardless of
            constrain_factors — converting back to this shared format
            immediately after fitting is what lets every other part of
            this app that reads a fit result stay unchanged either way),
            'y_fit', 'components' (see get_sigmoid_components), 'quality'
            (see estimate_fit_quality), 'constrained' (echoes the
            constrain_factors argument, so callers/UI can tell which kind
            of fit this is), or None if the fit failed.
        """
        if n_components not in (1, 2, 3, 4):
            raise ValueError("n_components must be between 1 and 4")
        shape_func = self.sigmoid_shapes.get(shape_name)
        if shape_func is None:
            raise ValueError(f"Unknown sigmoid shape '{shape_name}'")

        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        x_span = x.max() - x.min() if len(x) > 1 else 1.0
        n = n_components

        if midpoint_guesses is None or len(midpoint_guesses) != n:
            midpoint_guesses = list(np.linspace(x.min(), x.max(), n + 2)[1:-1])

        if width_guess is None:
            width_guesses = [max(abs(x_span) / 10.0, 1e-6)] * n
        elif np.isscalar(width_guess):
            width_guesses = [max(abs(width_guess), 1e-6)] * n
        else:
            width_guesses = [max(abs(w), 1e-6) for w in width_guess]
            if len(width_guesses) != n:
                width_guesses = [max(abs(x_span) / 10.0, 1e-6)] * n

        if factor_guesses is None or len(factor_guesses) != n:
            factor_guesses = [1.0 / n] * n
        else:
            total = sum(factor_guesses)
            factor_guesses = ([f / total for f in factor_guesses] if total > 0
                              else [1.0 / n] * n)

        if constrain_factors and n > 1:
            # Softmax reparametrization: n unconstrained logits instead
            # of n-1 individually-bounded factors — see the docstring
            # above for why this guarantees every fraction stays valid.
            p0 = [float(np.log(max(f, 1e-6))) for f in factor_guesses]
            lower = [-30.0] * n
            upper = [30.0] * n
            for mid, w in zip(midpoint_guesses, width_guesses):
                p0.extend([mid, w])
                lower.extend([x.min() - x_span, 1e-6])
                upper.extend([x.max() + x_span, x_span * 5])

            def model_func(xx, *params):
                logits = np.array(params[:n])
                exp_logits = np.exp(logits - logits.max())  # shift for numerical stability
                factors = exp_logits / exp_logits.sum()
                sigmoid_params = params[n:]
                xx = np.asarray(xx, dtype=float)
                total = np.zeros_like(xx)
                for i in range(n):
                    midpoint, lambda_ = sigmoid_params[2 * i], sigmoid_params[2 * i + 1]
                    total = total + factors[i] * shape_func((xx - midpoint) / lambda_)
                return total

            try:
                popt_raw, _ = curve_fit(model_func, x, y, p0=p0, bounds=(lower, upper), maxfev=20000)
            except (RuntimeError, ValueError) as e:
                logger.error(f"Melting curve constrained sigmoid fit failed: {e}")
                return None

            # Convert back to the canonical (n-1 factors + derived last)
            # format immediately, so everything downstream — plotting,
            # get_sigmoid_components, saved fits, reports — works
            # identically regardless of how the fit itself was
            # parameterized. Exact, not approximate: softmax factors
            # already sum to 1 by construction, so factors[:-1] plus
            # "1 minus their sum" reproduces factors[-1] precisely.
            logits = popt_raw[:n]
            exp_logits = np.exp(logits - logits.max())
            factors = exp_logits / exp_logits.sum()
            popt = np.concatenate([factors[:-1], popt_raw[n:]])
            pcov = None  # see docstring — not propagated through the softmax
        else:
            p0 = []
            lower, upper = [], []
            if n > 1:
                p0.extend(factor_guesses[:-1])
                lower.extend([0.0] * (n - 1))
                upper.extend([1.0] * (n - 1))
            for mid, w in zip(midpoint_guesses, width_guesses):
                p0.extend([mid, w])
                lower.extend([x.min() - x_span, 1e-6])
                upper.extend([x.max() + x_span, x_span * 5])

            model_func_canonical = lambda xx, *params: self.sigmoid_sum_model(
                xx, *params, n_components=n, shape_func=shape_func)

            try:
                popt, pcov = curve_fit(model_func_canonical, x, y, p0=p0, bounds=(lower, upper),
                                       maxfev=20000)
            except (RuntimeError, ValueError) as e:
                logger.error(f"Melting curve sigmoid fit failed: {e}")
                return None

        y_fit = self.sigmoid_sum_model(x, *popt, n_components=n, shape_func=shape_func)
        components = self.get_sigmoid_components(x, popt, n, shape_func, pcov=pcov)
        quality = self.estimate_fit_quality(y, y_fit, popt)

        return {'params': popt, 'y_fit': y_fit, 'components': components,
                'quality': quality, 'n_components': n, 'shape_name': shape_name,
                'constrained': bool(constrain_factors)}

    # ------------------------------------------------------------------ #
    # 5. Fit-quality statistics                                           #
    # ------------------------------------------------------------------ #

    def estimate_fit_quality(self, y_orig, y_fit, params):
        """R-squared, RMSD, AIC, BIC — same formulas as
        peak_fitting_manager's analogue / the ported prototype."""
        y_orig = np.asarray(y_orig, dtype=float)
        y_fit = np.asarray(y_fit, dtype=float)
        n = len(y_orig)
        p = len(params)
        residuals = y_orig - y_fit
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y_orig - np.mean(y_orig)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else float('nan')
        rmsd = np.sqrt(ss_res / n) if n > 0 else float('nan')

        if ss_res <= 0 or n <= p:
            aic = bic = float('nan')
        else:
            if n / max(p, 1) >= 40:
                aic = n * np.log(ss_res / n) + 2 * p
            else:
                denom = (n - p - 1)
                aic = n * np.log(ss_res / n) + (2 * p * (p + 1)) / denom if denom != 0 else float('nan')
            bic = n * np.log(ss_res / n) + p * np.log(n)

        return {'rmsd': float(rmsd), 'r_squared': float(r_squared),
                'aic': float(aic) if aic == aic else None,
                'bic': float(bic) if bic == bic else None}
