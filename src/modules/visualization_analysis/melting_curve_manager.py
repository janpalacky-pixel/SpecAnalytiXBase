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

        if not np.any(low_mask) or not np.any(high_mask):
            return None

        coeffs_low = np.polyfit(x[low_mask], y[low_mask], deg=order)
        coeffs_high = np.polyfit(x[high_mask], y[high_mask], deg=order)

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
            'coeffs_low': coeffs_low,
            'coeffs_high': coeffs_high,
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
