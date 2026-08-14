# src/modules/data_analysis/peak_fitting_manager.py

import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import find_peaks
from scipy.special import wofz
from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

# NumPy 2.0 renamed trapz -> trapezoid; this keeps working on either.
_trapz = getattr(np, 'trapezoid', None) or np.trapz

# --- Peak Shape Definitions ---
#
# Convention shared by every model here: 'amplitude' is the peak HEIGHT
# (the model's own value at x=center), not an integrated area — verified
# by construction below for each one. This matters because fit_peaks()
# passes the same amplitude/center/width initial guesses and bounds to
# every model uniformly, and get_peak_properties() reports 'height' as
# whatever the fitted amplitude parameter came out to.

def gaussian(x, amplitude, center, sigma):
    """Gaussian peak shape function."""
    return amplitude * np.exp(-(x - center)**2 / (2 * sigma**2))

def lorentzian(x, amplitude, center, gamma):
    """Lorentzian peak shape function."""
    return amplitude * gamma**2 / ((x - center)**2 + gamma**2)

def voigt(x, amplitude, center, sigma, gamma):
    """True Voigt profile: the exact convolution of a Gaussian (width
    sigma) and a Lorentzian (width gamma), evaluated via the Faddeeva
    function (scipy.special.wofz) rather than numerically integrating
    the convolution — the standard, fast, accurate approach used across
    spectroscopy fitting software.

    Height-normalized so that voigt(center, amplitude, center, sigma,
    gamma) == amplitude exactly, matching every other model's
    'amplitude = peak height' convention (the raw Faddeeva-based formula
    is normally AREA-normalized instead, so this divides through by its
    own on-axis value to rescale it).
    """
    sigma = abs(sigma)
    gamma = abs(gamma)
    z = ((x - center) + 1j * gamma) / (sigma * np.sqrt(2))
    profile = np.real(wofz(z))
    peak_value = np.real(wofz(1j * gamma / (sigma * np.sqrt(2))))
    return amplitude * profile / peak_value

def pseudo_voigt(x, amplitude, center, width, eta):
    """Pseudo-Voigt: a linear combination of a Gaussian and a Lorentzian
    that share the SAME full width at half maximum ('width') and the
    same peak height — a fast, widely-used approximation to the true
    Voigt profile (no Faddeeva function needed), at the cost of being a
    slightly less accurate line-shape than true Voigt for intermediate
    mixing ratios. Standard in XRD/Raman peak-fitting software as a
    quicker alternative to true Voigt.

    eta (0-1) sets the mixing fraction: eta=0 is pure Gaussian, eta=1 is
    pure Lorentzian. Height-normalized the same way as every other model
    here (both components individually peak at 1, so their weighted sum
    does too, and amplitude scales that directly).
    """
    fwhm = abs(width)
    sigma_equiv = fwhm / (2 * np.sqrt(2 * np.log(2)))
    gamma_equiv = fwhm / 2.0
    gauss_shape = np.exp(-(x - center)**2 / (2 * sigma_equiv**2))
    lorentz_shape = gamma_equiv**2 / ((x - center)**2 + gamma_equiv**2)
    return amplitude * (eta * lorentz_shape + (1 - eta) * gauss_shape)

class PeakFittingManager:
    """Business logic for peak fitting and deconvolution."""

    def __init__(self):
        self.peak_models = {
            'Gaussian': (gaussian, ['amplitude', 'center', 'sigma']),
            'Lorentzian': (lorentzian, ['amplitude', 'center', 'gamma']),
            'Voigt': (voigt, ['amplitude', 'center', 'sigma', 'gamma']),
            'Pseudo-Voigt': (pseudo_voigt, ['amplitude', 'center', 'width', 'eta']),
        }


    def get_peak_properties(self, model_name, params):
        """Calculate FWHM and Area for a fitted peak."""
        properties = {}
        if model_name == 'Gaussian':
            amplitude, center, sigma = params
            properties['fwhm'] = 2 * np.sqrt(2 * np.log(2)) * abs(sigma)
            properties['area'] = amplitude * abs(sigma) * np.sqrt(2 * np.pi)
            properties['sigma'] = sigma  # --- FIX: Store the sigma value ---
        elif model_name == 'Lorentzian':
            amplitude, center, gamma = params
            properties['fwhm'] = 2 * abs(gamma)
            properties['area'] = np.pi * amplitude * abs(gamma)
            properties['gamma'] = gamma  # --- FIX: Store the gamma value ---
        elif model_name == 'Voigt':
            amplitude, center, sigma, gamma = params
            sigma, gamma = abs(sigma), abs(gamma)
            properties['sigma'] = sigma
            properties['gamma'] = gamma
            # Olivero & Longbothum (1977) approximation relating Voigt FWHM
            # to its Gaussian and Lorentzian component widths — accurate to
            # ~0.02%, the standard approximation used across spectroscopy
            # software rather than solving for the true FWHM numerically.
            fwhm_g = 2 * np.sqrt(2 * np.log(2)) * sigma
            fwhm_l = 2 * gamma
            fwhm = 0.5346 * fwhm_l + np.sqrt(0.2166 * fwhm_l**2 + fwhm_g**2)
            properties['fwhm'] = fwhm
            # No simple closed form for a height-normalized Voigt's area,
            # so integrate numerically over a window wide enough that the
            # tails are negligible on either side.
            half_span = max(50 * fwhm, 20 * (sigma + gamma))
            x_wide = np.linspace(center - half_span, center + half_span, 20001)
            y_wide = voigt(x_wide, amplitude, center, sigma, gamma)
            properties['area'] = float(_trapz(y_wide, x_wide))
        elif model_name == 'Pseudo-Voigt':
            amplitude, center, width, eta = params
            width = abs(width)
            eta = float(np.clip(eta, 0.0, 1.0))
            properties['fwhm'] = width
            properties['eta'] = eta
            # Exact (not approximated): pseudo-Voigt IS defined as exactly
            # this linear combination, so its area is the same combination
            # of the two components' own individual areas at this shared
            # FWHM and height.
            sigma_equiv = width / (2 * np.sqrt(2 * np.log(2)))
            gamma_equiv = width / 2.0
            gauss_area = amplitude * sigma_equiv * np.sqrt(2 * np.pi)
            lorentz_area = amplitude * np.pi * gamma_equiv
            properties['area'] = eta * lorentz_area + (1 - eta) * gauss_area
        else:
            # Not reachable today — every model actually offered by the
            # dialog is registered in self.peak_models above, and this
            # method is only ever called with a model_name that came from
            # there. Kept as a safety net: previously, if model_name ever
            # matched neither branch, amplitude/center were referenced
            # without ever being assigned, raising an opaque NameError
            # instead of a clear message pointing at the cause.
            raise ValueError(f"get_peak_properties: unrecognized model '{model_name}'")
        
        properties['height'] = amplitude
        properties['center'] = center
        return properties

    def multi_peak_model(self, x, *params, model_definitions):
        """
        A model consisting of the sum of multiple peaks.
        
        Args:
            x: The independent variable (x-axis).
            *params: A flat list of all parameters for all peaks.
            model_definitions: A list of tuples, each containing (model_name, num_params).
        """
        y_fit = np.zeros_like(x)
        param_index = 0
        for model_name, num_params in model_definitions:
            peak_params = params[param_index : param_index + num_params]
            model_func, _ = self.peak_models[model_name]
            y_fit += model_func(x, *peak_params)
            param_index += num_params
        return y_fit

    def get_extra_param_defaults(self, model_name, abs_width, peak):
        """Return [(initial_value, lower_bound, upper_bound), ...] for any
        model parameters BEYOND the shared amplitude/center/width triple
        every model has — called by fit_peaks() when a model needs more
        than 3 parameters. Centralizing this here means fit_peaks() itself
        doesn't need to know about each model's own individual shape
        parameters, just how many extra ones a given model needs.

        Uses peak['extra'] as the initial guess when the caller supplied
        one (e.g. the user edited a custom starting gamma/eta in the
        dialog before fitting), falling back to a neutral default
        otherwise.
        """
        user_extra = peak.get('extra')
        if model_name == 'Voigt':
            # gamma (Lorentzian component width) — default to the Gaussian
            # component width (abs_width, reused as sigma) as a neutral
            # guess; the fit finds the actual Gaussian/Lorentzian balance
            # from there.
            initial = abs(user_extra) if user_extra is not None else abs_width
            return [(initial, 1e-6, abs_width * 10)]
        elif model_name == 'Pseudo-Voigt':
            # eta (mixing fraction, 0=Gaussian .. 1=Lorentzian) — 0.5 is a
            # neutral starting guess with no bias either way.
            initial = float(np.clip(user_extra, 0.0, 1.0)) if user_extra is not None else 0.5
            return [(initial, 0.0, 1.0)]
        return []

    def fit_peaks(self, x_data, y_data, initial_peaks, amplitude_constraint='unrestricted'):
        """
        Fit multiple peaks to the provided spectral data with robust bounds and amplitude constraints.

        Args:
            x_data, y_data: The spectral data for the region of interest.
            initial_peaks: A list of dictionaries, each with 'model', 'center', 'amplitude', 'width'.
            amplitude_constraint: 'unrestricted', 'positive', or 'negative'.
        """
        if not initial_peaks:
            return [], None

        initial_params = []
        bounds_lower = []
        bounds_upper = []
        model_definitions = []

        for peak in initial_peaks:
            model_name = peak['model']
            _, param_names = self.peak_models[model_name]
            num_params = len(param_names)
            model_definitions.append((model_name, num_params))

            amplitude, center, width = peak['amplitude'], peak['center'], peak['width']
            abs_width = abs(width)

            # --- NEW: Amplitude Constraint Logic ---
            if amplitude_constraint == 'positive':
                amp_lower, amp_upper = 0, np.inf
                # If initial guess is negative, make it slightly positive
                if amplitude <= 0: amplitude = 1e-6
            elif amplitude_constraint == 'negative':
                amp_lower, amp_upper = -np.inf, 0
                # If initial guess is positive, make it slightly negative
                if amplitude >= 0: amplitude = -1e-6
            else: # 'unrestricted'
                amp_lower, amp_upper = -np.inf, np.inf
            
            center_lower, center_upper = center - abs_width * 2, center + abs_width * 2
            width_lower, width_upper = 1e-6, abs_width * 10

            # Every model shares these first three parameters
            # (amplitude, center, width) — the table's own columns.
            initial_params.extend([amplitude, center, abs_width])
            bounds_lower.extend([amp_lower, center_lower, width_lower])
            bounds_upper.extend([amp_upper, center_upper, width_upper])

            # Models needing MORE than the shared three (Voigt's second
            # width term, Pseudo-Voigt's mixing fraction) get their extra
            # parameters' initial guess and bounds from
            # get_extra_param_defaults(), so this method doesn't need to
            # know about every model's own shape parameters individually
            # — it only needs to know how many of them there are, already
            # tracked by num_params/model_definitions above.
            if num_params > 3:
                for value, lo, hi in self.get_extra_param_defaults(model_name, abs_width, peak):
                    initial_params.append(value)
                    bounds_lower.append(lo)
                    bounds_upper.append(hi)
        
        model_func_for_fit = lambda x, *params: self.multi_peak_model(x, *params, model_definitions=model_definitions)

        try:
            popt, pcov = curve_fit(
                model_func_for_fit, x_data, y_data, p0=initial_params, bounds=(bounds_lower, bounds_upper)
            )
            y_fit = model_func_for_fit(x_data, *popt)

            fitted_peaks = []
            param_index = 0
            for model_name, num_params in model_definitions:
                peak_params = popt[param_index : param_index + num_params]
                peak_properties = self.get_peak_properties(model_name, peak_params)
                fitted_peaks.append({'model': model_name, 'parameters': peak_properties})
                param_index += num_params
            
            return fitted_peaks, y_fit

        except (RuntimeError, ValueError) as e:
            logger.error(f"Peak fitting failed: {e}")
            return None, None

    def auto_detect_peaks(self, y_data, x_data=None):
        """Automatically detect initial peaks, finding both positive and negative, but always returning positive width."""
        # Find both positive and negative peaks separately
        peaks_pos, props_pos = find_peaks(y_data, prominence=(np.max(y_data) - np.min(y_data)) * 0.1, width=3)
        peaks_neg, props_neg = find_peaks(-y_data, prominence=(np.max(y_data) - np.min(y_data)) * 0.1, width=3)

        initial_guesses = []
        
        # Process positive peaks
        for i, peak_idx in enumerate(peaks_pos):
            center = x_data[peak_idx] if x_data is not None else peak_idx
            amplitude = y_data[peak_idx]
            width_in_points = props_pos['widths'][i]
            width_in_x_units = width_in_points * (x_data[1] - x_data[0] if x_data is not None and len(x_data) > 1 else 1)
            
            initial_guesses.append({
                'model': 'Gaussian',
                'center': center,
                'amplitude': amplitude,
                'width': abs(width_in_x_units) # Ensure width is positive
            })

        # Process negative peaks
        for i, peak_idx in enumerate(peaks_neg):
            center = x_data[peak_idx] if x_data is not None else peak_idx
            amplitude = y_data[peak_idx] # Use the original negative amplitude
            width_in_points = props_neg['widths'][i]
            width_in_x_units = width_in_points * (x_data[1] - x_data[0] if x_data is not None and len(x_data) > 1 else 1)
            
            initial_guesses.append({
                'model': 'Gaussian',
                'center': center,
                'amplitude': amplitude,
                'width': abs(width_in_x_units) # Ensure width is positive
            })

        # Sort all found peaks by their center position
        initial_guesses.sort(key=lambda p: p['center'])
        
        return initial_guesses