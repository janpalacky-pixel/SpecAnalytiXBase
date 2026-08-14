# src/modules/visualization_analysis/kinetics_manager.py

import numpy as np
from scipy.optimize import curve_fit, least_squares

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

# NumPy 2.0 renamed trapz -> trapezoid; same compatibility shim used
# elsewhere in this codebase (melting_curve_manager.py, peak_fitting_manager.py).
_trapz = getattr(np, 'trapezoid', None) or np.trapz


class KineticsManager:
    """Business logic for time-course kinetics fitting: extraction of a
    kinetic trace from a series of spectra (same pattern as
    MeltingCurveManager.extract_curve_from_spectra, here reading a time-
    axis instead of a temperature-axis), multi-exponential (1-4
    components) fitting at one fixed wavelength, and GLOBAL analysis --
    a single shared set of rate constants fitted across every wavelength
    of the whole spectral series simultaneously, producing per-component
    Decay-Associated Spectra (DAS).

    Model (single wavelength):
        y(t) = y_inf + sum_i A_i * exp(-k_i * t)

    Model (global, one shared k_i set across all wavelengths lambda):
        D(t, lambda) = y_inf(lambda) + sum_i A_i(lambda) * exp(-k_i * t)

    The global model is fitted via variable projection (Golub-Pereyra):
    for any trial set of rate constants k_1..k_n, every A_i(lambda) (and
    y_inf(lambda)) is a LINEAR parameter -- solvable in closed form by
    ordinary least squares for every wavelength at once, given k. Only
    the k_i themselves are nonlinear parameters that need an iterative
    optimizer, and there are only 1-4 of them regardless of how many
    wavelengths or time points are in the data. This is the standard
    approach used by dedicated global/target analysis software (e.g.
    Glotaran, TIMP) for time-resolved spectroscopy, and is far more
    stable and far cheaper than naively throwing every A_i(lambda) into
    one giant simultaneous nonlinear fit alongside the k_i's.
    """

    # ------------------------------------------------------------------ #
    # 1. Curve extraction from a series of spectra                        #
    # ------------------------------------------------------------------ #

    def extract_curve_from_spectra(self, spectra, x_value, window=0.0):
        """Extract one y-value per spectrum at x_value (interpolated),
        returning them in the SAME order as `spectra`. Identical
        approach to MeltingCurveManager.extract_curve_from_spectra --
        see that docstring for the full explanation of the `window`
        parameter; duplicated here rather than imported since every
        manager in this codebase owns its full pipeline independently.

        Returns (y_values, out_of_range_labels).
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
                    y_values.append(float(np.interp(x_value, x, y)))
            else:
                order = np.argsort(x)
                y_values.append(float(np.interp(x_value, x[order], y[order])))

        return np.array(y_values), out_of_range

    def build_data_matrix(self, spectra, times):
        """Build the global-analysis data matrix D[n_times, n_wavelengths]
        from a list of spectra that all already share one common x-axis
        (validate this with spectra_validation.validate_common_x_axis
        BEFORE calling this -- not re-checked here), sorted ascending by
        the given per-spectrum `times` array (same order/length as
        spectra).

        Returns (t_sorted, x_wavelengths, D, sort_order) where
        x_wavelengths is the shared x_scale (taken from the first
        spectrum), D has one row per time point (ascending) and one
        column per wavelength, and sort_order is the index array used to
        sort -- callers that need to map a fitted result back to the
        original spectra list can use it.
        """
        times = np.asarray(times, dtype=float)
        sort_order = np.argsort(times)
        t_sorted = times[sort_order]
        x_wavelengths = np.asarray(spectra[0]['x_scale'], dtype=float)
        D = np.empty((len(spectra), len(x_wavelengths)), dtype=float)
        for row, idx in enumerate(sort_order):
            D[row, :] = np.asarray(spectra[idx]['y_scale'], dtype=float)
        return t_sorted, x_wavelengths, D, sort_order

    # ------------------------------------------------------------------ #
    # 2. Single-wavelength multi-exponential model & fitting              #
    # ------------------------------------------------------------------ #

    def exp_sum_model(self, t, *params, n_components):
        """y_inf + sum_i A_i * exp(-k_i * t).

        Parameter layout (length 1 + 2*n_components):
            params[0]                  -> y_inf (constant offset /
                                           infinite-time asymptote)
            params[1 : n+1]            -> A_1 .. A_n (amplitudes; a
                                           NEGATIVE amplitude with a
                                           positive-going signal is a
                                           perfectly normal "growth"/rise
                                           kinetic, not an error)
            params[n+1 : 2n+1]         -> k_1 .. k_n (rate constants,
                                           1/time units; always
                                           constrained > 0 during fitting
                                           -- see fit_exponential_model)
        """
        n = n_components
        t = np.asarray(t, dtype=float)
        y_inf = params[0]
        amplitudes = params[1:n + 1]
        rates = params[n + 1:2 * n + 1]
        total = np.full_like(t, y_inf)
        for i in range(n):
            total = total + amplitudes[i] * np.exp(-rates[i] * t)
        return total

    def auto_detect_rate_guesses(self, t, n_components):
        """Seed n_components initial rate-constant guesses, log-spaced
        across the timescale actually spanned by the data -- from
        roughly 5/duration (a process that's ~95% done by the last time
        point) down to 1/(5*dt) (a process barely distinguishable from
        instantaneous at the data's own time resolution). Rate constants
        for real multi-step kinetics routinely span 1-3 orders of
        magnitude, which is exactly why a log-spaced (not linear) spread
        is used -- a linear spread would cluster every guess in the slow
        end and leave curve_fit needing to find any fast component from
        nothing.

        Uses the MEDIAN time-point spacing for dt, not the minimum. With
        irregularly-spaced time points (e.g. randomly sampled, or a real
        experiment with a couple of accidentally-close early readings),
        the single smallest gap in the whole series can be orders of
        magnitude tighter than the data's actual typical resolution --
        using it directly sent k_fast into the thousands on data that
        was actually well-resolved on a much slower timescale, seeding a
        fit optimizer with a starting point nowhere near reality. The
        median reflects the sampling rate that actually describes most
        of the series.
        """
        t = np.asarray(t, dtype=float)
        t_sorted = np.sort(t)
        duration = max(t_sorted[-1] - t_sorted[0], 1e-12)
        dt = np.median(np.diff(t_sorted)) if len(t_sorted) > 1 else duration
        dt = max(dt, duration * 1e-6)

        k_fast = 1.0 / (5.0 * dt)
        k_slow = 5.0 / duration
        # Guard against a pathological ratio even after the median fix
        # (e.g. very few, very unevenly spread points) -- an initial
        # spread of more than 4 orders of magnitude is not a realistic
        # "seed near the truth" guess for anything this app fits, and
        # only risks handing the optimizer a diverging starting point.
        k_fast = min(k_fast, k_slow * 1e4)
        if n_components == 1:
            return [k_slow]
        return list(np.geomspace(k_slow, k_fast, n_components))

    def fit_exponential_model(self, t, y, n_components, k_guesses=None,
                              amplitude_guesses=None, offset_guess=None):
        """Fit y_inf + sum of n_components (1-4) exponential decays/
        growths to (t, y) via scipy.optimize.curve_fit with bounds
        (every k_i > 0; a genuinely GROWING signal is still represented
        by exp(-k*t) with a NEGATIVE amplitude, not a negative rate
        constant -- this keeps "how fast" and "which direction" as
        separate, independently interpretable parameters).

        Args:
            t, y: the kinetic trace to fit (time, signal).
            n_components: 1-4.
            k_guesses: optional list of n_components initial rate
                constants (from auto_detect_rate_guesses, or user-edited);
                defaults to auto_detect_rate_guesses(t, n_components).
            amplitude_guesses: optional list of n_components initial
                amplitudes; defaults to splitting the total y-range
                evenly across components.
            offset_guess: optional initial y_inf; defaults to the last
                (latest-time) y value.

        Returns dict with 'params' (flat vector, canonical layout per
        exp_sum_model), 'y_fit', 'components' (see
        get_exponential_components), 'quality' (see
        estimate_fit_quality), 'n_components', or None if the fit failed.
        """
        if n_components not in (1, 2, 3, 4):
            raise ValueError("n_components must be between 1 and 4")

        t = np.asarray(t, dtype=float)
        y = np.asarray(y, dtype=float)
        n = n_components
        y_span = float(np.ptp(y)) if len(y) > 1 else 1.0
        y_span = y_span if y_span > 0 else 1.0

        if k_guesses is None or len(k_guesses) != n:
            k_guesses = self.auto_detect_rate_guesses(t, n)
        if amplitude_guesses is None or len(amplitude_guesses) != n:
            amplitude_guesses = [(y[0] - y[-1]) / n if len(y) > 1 else y_span / n] * n
        if offset_guess is None:
            offset_guess = float(y[-1]) if len(y) > 0 else 0.0

        p0 = [offset_guess] + list(amplitude_guesses) + [max(k, 1e-12) for k in k_guesses]
        lower = [-np.inf] + [-np.inf] * n + [1e-12] * n
        # Rate constants bounded well above the fastest guess so the
        # optimizer can't run away to an arbitrarily large k that fits
        # noise as an instant step -- 1000x the fastest initial guess
        # (or a generous absolute fallback) is loose enough to never
        # constrain a genuine fit, tight enough to keep the search sane.
        k_upper = max(max(k_guesses) * 1000.0, 1e6)
        upper = [np.inf] + [np.inf] * n + [k_upper] * n

        model_func = lambda tt, *params: self.exp_sum_model(tt, *params, n_components=n)

        try:
            popt, pcov = curve_fit(model_func, t, y, p0=p0, bounds=(lower, upper), maxfev=20000)
        except (RuntimeError, ValueError) as e:
            logger.error(f"Kinetics single-wavelength exponential fit failed: {e}")
            return None

        y_fit = self.exp_sum_model(t, *popt, n_components=n)
        components = self.get_exponential_components(t, popt, n, pcov=pcov)
        quality = self.estimate_fit_quality(y, y_fit, popt)

        return {'params': popt, 'y_fit': y_fit, 'components': components,
                'quality': quality, 'n_components': n}

    def get_exponential_components(self, t, params, n_components, pcov=None):
        """Return the individual exponential components (for plotting)
        plus each component's (amplitude, rate, tau=1/rate) and, if pcov
        is given, standard errors -- same role as MeltingCurveManager's
        get_sigmoid_components.

        Always returned sorted by ASCENDING rate constant -- i.e. the
        SLOWEST component (smallest k, longest tau) first, fastest last
        -- regardless of fit convergence order. This is a stable,
        arbitrary-but-consistent convention (like get_sigmoid_components'
        ascending-midpoint sort): what matters is that "component 1"
        means the same physical process every time this is called on
        comparable data, not which specific order was chosen.
        """
        n = n_components
        t = np.asarray(t, dtype=float)
        y_inf = params[0]
        amplitudes = params[1:n + 1]
        rates = params[n + 1:2 * n + 1]

        perr = None
        if pcov is not None:
            with np.errstate(invalid='ignore'):
                diag = np.diag(pcov)
            if np.all(np.isfinite(diag)) and np.all(diag >= 0):
                perr = np.sqrt(diag)

        raw = []
        for i in range(n):
            comp_curve = amplitudes[i] * np.exp(-rates[i] * t)
            comp_params = {'amplitude': float(amplitudes[i]), 'rate': float(rates[i]),
                          'tau': float(1.0 / rates[i]) if rates[i] != 0 else float('inf')}
            if perr is not None:
                comp_params['amplitude_err'] = float(perr[1 + i])
                comp_params['rate_err'] = float(perr[1 + n + i])
                # tau = 1/k  =>  d(tau) = |d(k)| / k^2
                comp_params['tau_err'] = (float(perr[1 + n + i]) / rates[i] ** 2
                                          if rates[i] != 0 else None)
            raw.append({'comp': comp_curve, 'params': comp_params})
        raw.sort(key=lambda r: r['params']['rate'])

        components = [r['comp'] for r in raw]
        component_params = [r['params'] for r in raw]
        y_inf_err = float(perr[0]) if perr is not None else None
        return {'components': components, 'params': component_params,
                'y_inf': float(y_inf), 'y_inf_err': y_inf_err}

    # ------------------------------------------------------------------ #
    # 3. Global analysis (shared rate constants across all wavelengths)   #
    # ------------------------------------------------------------------ #

    def _global_design_matrix(self, t, rates, include_offset):
        """C[n_times, n_components (+1 if include_offset)] -- the basis
        of exp(-k_i * t) columns (plus a constant column of 1's for the
        offset/infinite-time term, if requested) that every wavelength's
        amplitudes are linearly fitted against for a given trial `rates`.
        """
        t = np.asarray(t, dtype=float)
        cols = [np.exp(-k * t) for k in rates]
        if include_offset:
            cols.append(np.ones_like(t))
        return np.column_stack(cols)

    def _global_residuals(self, log_rates, t, D, n_components, include_offset):
        """Residual vector for least_squares, optimizing over log(k) (not
        k itself) -- keeps every trial rate constant automatically
        positive with no explicit bound needed, and matches how rate
        constants are naturally compared (ratios / orders of magnitude,
        not linear differences). For the current trial rates, the linear
        amplitude matrix A is solved by ordinary least squares
        (np.linalg.lstsq) -- this is the "variable projection" step: A
        is NOT a free nonlinear parameter, it's computed exactly, in
        closed form, from whatever k the optimizer is currently trying.
        """
        rates = np.exp(log_rates)
        C = self._global_design_matrix(t, rates, include_offset)
        # lstsq solves C @ A = D for every wavelength column of D at once.
        A, _, _, _ = np.linalg.lstsq(C, D, rcond=None)
        residual = D - C @ A
        return residual.ravel()

    def fit_global_model(self, times, x_wavelengths, D, n_components,
                         k_guesses=None, include_offset=True):
        """Global analysis: fit ONE shared set of n_components (1-4) rate
        constants across the ENTIRE data matrix D[n_times, n_wavelengths]
        simultaneously, via variable projection (see class docstring and
        _global_residuals). Each wavelength gets its own linear
        amplitude for every component (and its own offset, if
        include_offset) -- these amplitude-vs-wavelength curves are the
        Decay-Associated Spectra (DAS).

        Args:
            times: 1D array, ascending, one per row of D (from
                build_data_matrix).
            x_wavelengths: 1D array, one per column of D.
            D: data matrix, D[i, j] = signal at times[i], x_wavelengths[j].
            n_components: 1-4.
            k_guesses: optional list of n_components initial rate
                constants; defaults to auto_detect_rate_guesses(times, n).
            include_offset: if True (default), also fits a per-wavelength
                constant (infinite-time) term -- almost always wanted
                for real kinetics, where the signal doesn't necessarily
                decay all the way to exactly zero. Set False only to
                force every wavelength's curve through zero at t=inf.

        Returns dict with 'rates' (shared k_i, ascending), 'tau'
        (1/rates), 'rates_err' (or None), 'amplitudes' (DAS matrix,
        n_components x n_wavelengths, row order matching 'rates'),
        'offset_spectrum' (1D, per-wavelength y_inf, or None if
        include_offset is False), 'D_fit' (reconstructed data matrix),
        'quality' (whole-matrix R^2/RMSD; see estimate_fit_quality_2d),
        'n_components', 'include_offset', or None if the fit failed.
        """
        if n_components not in (1, 2, 3, 4):
            raise ValueError("n_components must be between 1 and 4")

        times = np.asarray(times, dtype=float)
        x_wavelengths = np.asarray(x_wavelengths, dtype=float)
        D = np.asarray(D, dtype=float)
        n = n_components

        if k_guesses is None or len(k_guesses) != n:
            k_guesses = self.auto_detect_rate_guesses(times, n)
        log_p0 = np.log(np.maximum(k_guesses, 1e-12))

        try:
            result = least_squares(
                self._global_residuals, log_p0,
                args=(times, D, n, include_offset), method='lm', max_nfev=20000)
        except Exception as e:
            logger.error(f"Kinetics global analysis fit failed: {e}")
            return None

        if not result.success and result.status <= 0:
            logger.error(f"Kinetics global analysis did not converge: {result.message}")
            return None

        rates = np.exp(result.x)
        C = self._global_design_matrix(times, rates, include_offset)
        A, _, _, _ = np.linalg.lstsq(C, D, rcond=None)
        D_fit = C @ A

        order = np.argsort(rates)
        rates_sorted = rates[order]
        # A's first n rows are the exponential components' amplitudes
        # (one row per rate constant, in solver order); reorder those
        # rows to match rates_sorted. Row n (if include_offset) is the
        # separate per-wavelength constant/offset term, handled next.
        amplitudes_sorted = A[:n][order]

        offset_spectrum = A[n, :] if include_offset else None

        # Rough standard errors for the rate constants from the
        # Jacobian's covariance approximation (same spirit as curve_fit's
        # own pcov, since least_squares doesn't return one directly) --
        # in log-k space, then propagated to k via d(exp(x)) = exp(x)*dx.
        rates_err = None
        try:
            J = result.jac
            residual_var = float(np.sum(result.fun ** 2) / max(len(result.fun) - len(result.x), 1))
            JTJ = J.T @ J
            cov_log = np.linalg.pinv(JTJ) * residual_var
            diag = np.diag(cov_log)
            if np.all(np.isfinite(diag)) and np.all(diag >= 0):
                err_log = np.sqrt(diag)
                rates_err = (rates * err_log)[order]
        except Exception as e:
            logger.warning(f"fit_global_model: rate-constant error estimation failed ({e}).")

        quality = self.estimate_fit_quality_2d(D, D_fit, n_params=len(result.x) + A.size)

        return {
            'rates': rates_sorted,
            'tau': 1.0 / rates_sorted,
            'rates_err': rates_err,
            'amplitudes': amplitudes_sorted,
            'offset_spectrum': offset_spectrum,
            'D_fit': D_fit,
            'quality': quality,
            'n_components': n,
            'include_offset': bool(include_offset),
            'times': times,
            'x_wavelengths': x_wavelengths,
        }

    # ------------------------------------------------------------------ #
    # 4. Fit-quality statistics                                           #
    # ------------------------------------------------------------------ #

    def estimate_fit_quality(self, y_orig, y_fit, params):
        """R-squared, RMSD, AIC, BIC for a 1D fit -- same formulas as
        MeltingCurveManager.estimate_fit_quality / peak_fitting_manager's
        analogue."""
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

    def estimate_fit_quality_2d(self, D_orig, D_fit, n_params):
        """Whole-matrix R-squared/RMSD/AIC/BIC for a global analysis fit
        -- same formulas as estimate_fit_quality, just summed over every
        (time, wavelength) point in the matrix instead of a single 1D
        trace. n_params should count EVERY fitted number (shared rate
        constants + every per-wavelength linear amplitude/offset), since
        that's what AIC/BIC penalize -- the linear parameters are still
        real fitted degrees of freedom even though they were solved in
        closed form rather than by the nonlinear optimizer directly."""
        D_orig = np.asarray(D_orig, dtype=float)
        D_fit = np.asarray(D_fit, dtype=float)
        n = D_orig.size
        p = n_params
        residuals = D_orig - D_fit
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((D_orig - np.mean(D_orig)) ** 2)
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
