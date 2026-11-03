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

_FWHM_PER_SIGMA = 2.0 * np.sqrt(2.0 * np.log(2.0))     # a Gaussian's FWHM / sigma


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

# --- Background under the peaks ---
#
# Raw spectra often sit on an offset (detector counts, e.g. 669 counts with
# bands only 3-14 counts high) or a slope. The peaks alone cannot make such
# an offset, so the fit can add a background: none, a constant, or a straight
# line. It is kept as {'kind', 'x0', 'x1', 'y0', 'y1'}: its value at the two
# ends of the data (a constant: y0 == y1). Heights and areas of the peaks are
# then measured above it.
#
# 'auto' (Automatic, the default) chooses for each spectrum from its data
# (resolve_background): None where the data come back to zero - a CD or a
# difference spectrum (bands up and down), a baseline-corrected spectrum -,
# Linear where they sit on an offset (raw Raman counts). If the data have no
# background but the fit adds one anyway, the fit is less stable (with CD a
# sloped line and a broad band look alike, so the fit cannot tell which of
# the two the signal belongs to).
BACKGROUNDS = (('auto', "Automatic"), ('none', "None"), ('constant', "Constant"),
               ('linear', "Linear"))
DEFAULT_BACKGROUND = 'auto'
BACKGROUND_NAMES = dict(BACKGROUNDS)


def _edges(x, y):
    """(x, y) sorted by x without NaN, and the medians of the first and of
    the last 5 % of the points (at least 5) - the ends of the spectrum."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    order = np.argsort(x)
    x, y = x[order], y[order]
    if x.size < 2:
        return x, y, None, None
    n = max(5, x.size // 20)
    return x, y, float(np.median(y[:n])), float(np.median(y[-n:]))


def resolve_background(x, y, kind):
    """The background really used for the data (x, y): kind itself, or for
    'auto' 'none' or 'linear':
    - 'none' when the data have clear bands both up and down from zero (CD,
      difference spectra), or when at least one end of the spectrum is at
      zero (within 5 % of the data's range or 3x the noise) - the data come
      back to zero, so zero is their baseline;
    - 'linear' otherwise: both ends away from zero (an offset or a slope)."""
    if kind != 'auto':
        return kind if kind in BACKGROUND_NAMES else 'none'
    x, y, left, right = _edges(x, y)
    if left is None or y.size < 5:
        return 'none'
    span = float(np.ptp(y))
    noise = float(np.median(np.abs(np.diff(y)))) / 0.6745 / np.sqrt(2)
    near = max(0.05 * span, 3.0 * noise)
    if abs(left) <= near or abs(right) <= near:
        return 'none'
    clear = max(0.1 * span, 5.0 * noise)
    if np.percentile(y, 99) > clear and np.percentile(y, 1) < -clear:
        return 'none'                      # bands up and down: CD, difference spectra
    return 'linear'


def background_values(background, x):
    """The background `background` (a dict as above, or None) at x."""
    x = np.asarray(x, dtype=float)
    if not background or background.get('kind', 'none') == 'none':
        return np.zeros_like(x)
    y0, y1 = float(background['y0']), float(background['y1'])
    x0, x1 = float(background['x0']), float(background['x1'])
    if background['kind'] == 'constant' or x1 == x0:
        return np.full_like(x, y0)
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def initial_background(x, y, kind):
    """A first guess of the background from the two ends of the data (the
    median of the first and of the last 5 % of the points, at least 5) -
    the ends are usually free of bands. None for kind 'none' (and for
    'auto' when the data need no background, see resolve_background)."""
    kind = resolve_background(x, y, kind)
    if kind not in ('constant', 'linear'):
        return None
    x, y, left, right = _edges(x, y)
    if left is None:
        return None
    if kind == 'constant':
        level = min(left, right) if np.median(y) >= max(left, right) else (left + right) / 2.0
        left = right = level
    return {'kind': kind, 'x0': float(x[0]), 'x1': float(x[-1]), 'y0': left, 'y1': right}


# --- Fixed and linked values ---
#
# A starting peak can carry peak['constraints'] = {name: spec} for the names
# of PARAM_NAMES (its 1st..4th fit parameter): spec {'kind': 'fixed'} keeps
# the start value (not fitted); {'kind': 'link', 'peak': <id of another
# peak>, 'value': v} ties it to that peak's value: center = the other's
# center + v (a fixed distance), height = the other's height x v (a fixed
# ratio), width / extra = the other's (the same; only between peaks of the
# same model). Peaks are known by peak['id'] (new_peak_id), so a link stays
# right when peaks are added or removed; a link to a peak that is no longer
# there, a link round in a circle or a width link between different models
# counts as free.
PARAM_NAMES = ('height', 'center', 'width', 'extra')
LINK_KINDS = {'center': 'distance', 'height': 'ratio', 'width': 'same', 'extra': 'same'}


def new_peak_id(peaks):
    """An id not used by any of `peaks` (p1, p2, ...)."""
    used = {p.get('id') for p in peaks}
    k = 1
    while f'p{k}' in used:
        k += 1
    return f'p{k}'


def constraint_of(peak, name):
    """The constraint of one value of a starting peak (None = fitted)."""
    spec = (peak.get('constraints') or {}).get(name)
    return spec if isinstance(spec, dict) and spec.get('kind') in ('fixed', 'link') else None


def _constraint_plan(peaks, model_definitions):
    """For every fit parameter of the peaks (in the order of fit_peaks):
    None (fitted), ('fixed',) or ('link', i_target, name, value)."""
    ids = {p.get('id'): k for k, p in enumerate(peaks) if p.get('id')}
    starts, pos = [], 0
    for _, n in model_definitions:
        starts.append(pos)
        pos += n
    plan = [None] * pos
    for k, (peak, (model, n)) in enumerate(zip(peaks, model_definitions)):
        for j, name in enumerate(PARAM_NAMES[:n]):
            spec = constraint_of(peak, name)
            if spec is None:
                continue
            i = starts[k] + j
            if spec['kind'] == 'fixed':
                plan[i] = ('fixed',)
                continue
            t = ids.get(spec.get('peak'))
            if t is None or t == k:
                continue
            if name in ('width', 'extra') and model_definitions[t][0] != model:
                continue                       # a width of another shape means another thing
            if j >= model_definitions[t][1]:
                continue
            plan[i] = ('link', starts[t] + j, name, float(spec.get('value', 0.0 if name == 'center'
                                                                           else 1.0)))
    # links that cannot be resolved (a circle) are fitted freely
    resolved = {i for i, p in enumerate(plan) if p is None or p[0] == 'fixed'}
    changed = True
    while changed:
        changed = False
        for i, p in enumerate(plan):
            if i not in resolved and p[1] in resolved:
                resolved.add(i)
                changed = True
    return [p if i in resolved else None for i, p in enumerate(plan)]


def _expand(plan, full_start, free_index, q):
    """The full parameter vector from the fitted (free) ones q: fixed values
    from full_start, linked ones from their target (in order of need)."""
    full = np.array(full_start, dtype=float)
    full[free_index] = q
    todo = [i for i, p in enumerate(plan) if p is not None and p[0] == 'link']
    done = set(range(len(full))) - set(todo)
    while todo:
        rest = []
        for i in todo:
            _, t, name, v = plan[i]
            if t not in done:
                rest.append(i)
                continue
            full[i] = full[t] + v if name == 'center' else (full[t] * v if name == 'height'
                                                             else full[t])
            done.add(i)
        if len(rest) == len(todo):
            break
        todo = rest
    return full


def _finite_cov(pcov, n):
    """The covariance of curve_fit as an n x n array (inf where the fit
    could not estimate it)."""
    try:
        cov = np.asarray(pcov, dtype=float)
    except (TypeError, ValueError):
        cov = None
    if cov is None or cov.shape != (n, n):
        return np.full((n, n), np.inf)
    return cov


def _sd(cov, i):
    """The standard error of parameter i (None if not estimated)."""
    v = float(cov[i, i])
    return float(np.sqrt(v)) if np.isfinite(v) and v >= 0 else None


def format_error(err):
    """An uncertainty with 2 significant digits, without an exponent:
    4.123 -> '4.1', 0.03214 -> '0.032', 123.4 -> '123'; None -> 'n/a'."""
    if err is None or not np.isfinite(err):
        return "n/a"
    err = abs(float(err))
    if err == 0:
        return "0"
    if err >= 100:
        return f"{err:.0f}"
    decimals = min(8, max(0, 1 - int(np.floor(np.log10(err)))))
    return f"{err:.{decimals}f}"


def format_with_error(value, err):
    """'value \u00b1 error', the value rounded to the error's last digit (as
    usual in science): (3431.5432, 3.123) -> '3431.5 \u00b1 3.1',
    (11.4094, 0.2213) -> '11.41 \u00b1 0.22'; an unknown error: the value with
    4 decimals and '\u00b1 n/a'."""
    text = format_error(err)
    if text == "n/a":
        return f"{float(value):.4f} \u00b1 n/a"
    decimals = len(text.split('.')[1]) if '.' in text else 0
    return f"{float(value):.{decimals}f} \u00b1 {text}"


def _smoothed(y, window):
    from scipy.signal import savgol_filter
    y = np.asarray(y, dtype=float)
    window = int(window) | 1
    if y.size < 21 or window < 5 or window >= y.size:
        return y
    return savgol_filter(y, window, 2)


class PeakFittingManager:
    """Business logic for peak fitting and deconvolution."""

    def __init__(self):
        self.last_background = None          # the background of the last fit (a dict or None)
        self.last_background_kind = 'none'   # and its kind ('auto' resolved)
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
            # Exact: voigt() is the area-normalized Voigt profile V scaled
            # to height `amplitude` at the centre, so its area is
            # amplitude / V(0). (Before, it was integrated numerically over
            # +-50 FWHM, which cut off the slowly decaying Lorentzian tails:
            # up to 0.64 % too small for Lorentzian-like peaks.)
            from scipy.special import voigt_profile
            v0 = float(voigt_profile(0.0, sigma, gamma)) if (sigma > 0 or gamma > 0) else 0.0
            if np.isfinite(v0) and v0 > 0:
                properties['area'] = float(amplitude / v0)
            else:
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

    def peak_errors(self, model_name, params, cov):
        """The standard errors (1 sigma) of every value of
        get_peak_properties (center, height, width, FWHM, area, ...) from the
        covariance `cov` of the peak's fit parameters: by error propagation,
        var(f) = g C g^T with g the derivative of the value by the
        parameters (numerical, central differences). None where it cannot
        be estimated (the fit could not determine a parameter)."""
        params = np.asarray(params, dtype=float)
        cov = np.asarray(cov, dtype=float)
        base = self.get_peak_properties(model_name, params)
        keys = [k for k, v in base.items() if isinstance(v, (int, float, np.floating))]
        grads = {k: np.zeros(params.size) for k in keys}
        for i in range(params.size):
            h = 1e-6 * max(abs(params[i]), 1e-6)
            up, down = params.copy(), params.copy()
            up[i] += h
            down[i] -= h
            if model_name == 'Pseudo-Voigt' and i == 3:     # eta stays within 0..1
                up[i], down[i] = min(up[i], 1.0), max(down[i], 0.0)
            step = up[i] - down[i]
            if step <= 0:
                continue
            p_up = self.get_peak_properties(model_name, up)
            p_down = self.get_peak_properties(model_name, down)
            for k in keys:
                grads[k][i] = (float(p_up[k]) - float(p_down[k])) / step
        out = {}
        for k in keys:
            g = grads[k]
            used = g != 0
            if not np.any(used):
                out[k] = 0.0
                continue
            sub = cov[np.ix_(used, used)]
            if not np.all(np.isfinite(sub)):
                out[k] = None
                continue
            var = float(g[used] @ sub @ g[used])
            out[k] = float(np.sqrt(var)) if var >= 0 and np.isfinite(var) else None
        return out

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

    def fit_peaks(self, x_data, y_data, initial_peaks, amplitude_constraint='unrestricted',
                  background='none'):
        """
        Fit multiple peaks to the provided spectral data with robust bounds and amplitude constraints.

        Args:
            x_data, y_data: The spectral data for the region of interest.
            initial_peaks: A list of dictionaries, each with 'model', 'center', 'amplitude', 'width'.
            amplitude_constraint: 'unrestricted', 'positive', or 'negative'.
            background: 'auto', 'none', 'constant' or 'linear' - fitted together
                with the peaks (see BACKGROUNDS; 'auto' chooses from the data,
                resolve_background - the choice is kept in
                self.last_background_kind); the result is kept in
                self.last_background (None for 'none'), the returned total
                fit includes it, the peaks' heights are above it.
        """
        self.last_background = None
        background = resolve_background(x_data, y_data, background)
        self.last_background_kind = background
        if not initial_peaks:
            return [], None

        initial_params = []
        raw_params = []           # the start values as given (a fixed value stays this)
        bounds_lower = []
        bounds_upper = []
        model_definitions = []
        # Limits from the data themselves, so the fit cannot run away: no
        # peak higher than 3x the data's largest value (two huge peaks of
        # opposite sign cancelling each other were a common failure), no
        # centre outside the data, no width beyond half the x range (a very
        # broad peak - or one centred outside the data - otherwise acts as
        # a baseline).
        x_arr = np.asarray(x_data, dtype=float)
        y_arr = np.asarray(y_data, dtype=float)
        x_lo, x_hi = float(np.nanmin(x_arr)), float(np.nanmax(x_arr))
        bg0 = initial_background(x_arr, y_arr, background)
        if bg0 is not None:
            # with a background the peaks only make the part above it: their
            # height is limited by the data's range, not by the offset
            span = float(np.nanmax(y_arr) - np.nanmin(y_arr)) if y_arr.size else 0.0
            amp_cap = 3.0 * span
        else:
            amp_cap = 3.0 * float(np.nanmax(np.abs(y_arr))) if y_arr.size else np.inf
        if not np.isfinite(amp_cap) or amp_cap <= 0:
            amp_cap = np.inf
        width_cap = (x_hi - x_lo) / 2.0 if x_hi > x_lo else np.inf

        for peak in initial_peaks:
            model_name = peak['model']
            _, param_names = self.peak_models[model_name]
            num_params = len(param_names)
            model_definitions.append((model_name, num_params))

            amplitude, center, width = peak['amplitude'], peak['center'], peak['width']
            abs_width = abs(width)
            raw_params.extend([float(amplitude), float(center), float(abs_width)])
            if bg0 is not None and np.isfinite(amp_cap) and abs(amplitude) > amp_cap / 2.0:
                # a height given from zero (a click or an older guess on data
                # sitting on an offset): the height above the background
                at = float(np.interp(center, np.sort(x_arr), y_arr[np.argsort(x_arr)]))
                amplitude = at - float(background_values(bg0, [center])[0])

            # --- NEW: Amplitude Constraint Logic ---
            if amplitude_constraint == 'positive':
                amp_lower, amp_upper = 0, amp_cap
                # If initial guess is negative, make it slightly positive
                if amplitude <= 0: amplitude = 1e-6
            elif amplitude_constraint == 'negative':
                amp_lower, amp_upper = -amp_cap, 0
                # If initial guess is positive, make it slightly negative
                if amplitude >= 0: amplitude = -1e-6
            else: # 'unrestricted'
                amp_lower, amp_upper = -amp_cap, amp_cap
            amplitude = float(np.clip(amplitude, amp_lower, amp_upper))

            abs_width = min(abs_width, width_cap * 0.999) if abs_width > 0 else abs_width
            center_lower = max(center - abs_width * 2, x_lo)
            center_upper = min(center + abs_width * 2, x_hi)
            if center_lower >= center_upper:            # a peak placed outside the data
                center_lower, center_upper = center - abs_width * 2, center + abs_width * 2
            center = float(np.clip(center, center_lower, center_upper))
            width_lower, width_upper = 1e-6, min(abs_width * 10, width_cap)

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
                    raw_params.append(value)
                    bounds_lower.append(lo)
                    bounds_upper.append(hi)
        
        n_peak_params = len(initial_params)
        # fixed values keep their start; linked ones follow their peak; only
        # the others (and the background) are fitted
        plan = _constraint_plan(initial_peaks, model_definitions)
        for i, p in enumerate(plan):
            if p is not None and p[0] == 'fixed':
                initial_params[i] = raw_params[i]
        if bg0 is not None:
            span = float(np.nanmax(y_arr) - np.nanmin(y_arr)) or 1.0
            lo_b, hi_b = float(np.nanmin(y_arr)) - span, float(np.nanmax(y_arr)) + span
            for v in ([bg0['y0']] if background == 'constant' else [bg0['y0'], bg0['y1']]):
                initial_params.append(float(np.clip(v, lo_b, hi_b)))
                bounds_lower.append(lo_b)
                bounds_upper.append(hi_b)

        def background_of(params):
            if bg0 is None:
                return None
            extra = list(params[n_peak_params:])
            y1 = extra[0] if background == 'constant' else extra[1]
            return dict(bg0, y0=float(extra[0]), y1=float(y1))

        def full_model(x, *params):
            y = self.multi_peak_model(x, *params[:n_peak_params],
                                      model_definitions=model_definitions)
            if bg0 is not None:
                y = y + background_values(background_of(params), x)
            return y

        plan += [None] * (len(initial_params) - n_peak_params)      # the background: fitted
        free = np.array([i for i, p in enumerate(plan) if p is None], dtype=int)
        start_full = _expand(plan, initial_params, free, np.asarray(initial_params)[free])

        def model_func_for_fit(x, *q):
            return full_model(x, *_expand(plan, start_full, free, np.asarray(q)))

        try:
            if free.size:
                q_opt, q_cov = curve_fit(
                    model_func_for_fit, x_data, y_data, p0=start_full[free],
                    bounds=(np.asarray(bounds_lower)[free], np.asarray(bounds_upper)[free]))
            else:                                   # everything fixed: nothing to fit
                q_opt, q_cov = np.zeros(0), np.zeros((0, 0))
            popt = _expand(plan, start_full, free, q_opt)
            y_fit = full_model(x_data, *popt)

            self.last_background = background_of(popt)
            # the covariance of all values: C = J Cq J^T, J = d(all) / d(fitted)
            # (the links are linear, so J is exact with unit steps); a fixed
            # value has no uncertainty
            q_cov = _finite_cov(q_cov, free.size)
            jac = np.zeros((len(popt), free.size))
            for j in range(free.size):
                step = q_opt.copy()
                step[j] += 1.0
                jac[:, j] = _expand(plan, start_full, free, step) - popt
            bad_q = ~np.all(np.isfinite(q_cov), axis=0) if free.size else np.zeros(0, bool)
            cov = jac @ np.where(np.isfinite(q_cov), q_cov, 0.0) @ jac.T
            bad = np.any(jac[:, bad_q] != 0, axis=1) if bad_q.any() else np.zeros(len(popt), bool)
            cov[bad, :] = np.inf                    # depends on a value the fit could not judge
            cov[:, bad] = np.inf
            if self.last_background is not None:
                # the background's own uncertainties (y0, and y1 when linear)
                errs = [_sd(cov, i) for i in range(n_peak_params, len(popt))]
                self.last_background['y0_err'] = errs[0]
                self.last_background['y1_err'] = errs[1] if len(errs) > 1 else errs[0]
            fitted_peaks = []
            param_index = 0
            for model_name, num_params in model_definitions:
                peak_params = popt[param_index : param_index + num_params]
                peak_properties = self.get_peak_properties(model_name, peak_params)
                block = cov[param_index:param_index + num_params,
                            param_index:param_index + num_params]
                fitted_peaks.append({'model': model_name, 'parameters': peak_properties,
                                     'errors': self.peak_errors(model_name, peak_params, block)})
                param_index += num_params
            
            return fitted_peaks, y_fit

        except (RuntimeError, ValueError) as e:
            logger.error(f"Peak fitting failed: {e}")
            return None, None

    def estimate_width(self, x_data, y_data, center):
        """The Gaussian width (sigma) of the band at `center`: its width at
        half height, measured on the data (the highest point within a few
        points of `center`). None when there is no band there."""
        from scipy.signal import peak_widths
        x = np.asarray(x_data, dtype=float)
        y = np.asarray(y_data, dtype=float)
        if x.size < 5 or center is None:
            return None
        # noisy data: a point of noise near the top passes for a very narrow
        # band - then measured again on more and more smoothed data
        step = float(np.median(np.abs(np.diff(x)))) if x.size > 1 else 1.0
        for window in (0, 7, 15, 31, 61):
            ys = y if window == 0 else _smoothed(y, window)
            if window and ys is y:
                break
            sigma = self._width_at(x, ys, center)
            if sigma is not None and sigma * _FWHM_PER_SIGMA >= max(5, window) * step:
                return sigma
            if sigma is None and window == 0 and self._flat(y):
                return None
        return None

    @staticmethod
    def _flat(y):
        """No band at all (only noise): the data's range is within a few
        times its noise."""
        y = np.asarray(y, dtype=float)
        if y.size < 5:
            return True
        noise = float(np.median(np.abs(np.diff(y)))) / 0.6745 / np.sqrt(2)
        return float(np.ptp(y)) <= 6 * noise + 1e-12

    def _width_at(self, x, y, center):
        from scipy.signal import peak_widths
        k = int(np.argmin(np.abs(x - center)))
        lo, hi = max(k - 5, 1), min(k + 6, x.size - 1)
        k = lo + int(np.argmax(y[lo:hi]))
        if not (y[k] >= y[k - 1] and y[k] >= y[k + 1]):
            return None
        try:
            widths = peak_widths(y, [k], rel_height=0.5)[0]
        except ValueError:
            return None
        if not len(widths) or not np.isfinite(widths[0]) or widths[0] <= 0:
            return None
        step = float(np.median(np.abs(np.diff(x))))
        sigma = float(widths[0]) * step / _FWHM_PER_SIGMA
        if sigma <= 0 or sigma > (x.max() - x.min()) / 4:
            return None
        return sigma

    @staticmethod
    def _merge_split(guesses):
        """One band found twice: on noisy data a small dip on the band's top
        splits it into two maxima close together. Two real bands closer than
        one width (sigma) never show two maxima, so such a pair is one band -
        kept once (the higher one, or their middle when equally high)."""
        out = []
        for g in sorted(guesses, key=lambda p: p['center']):
            if out:
                prev = out[-1]
                same_sign = (prev['amplitude'] >= 0) == (g['amplitude'] >= 0)
                near = abs(g['center'] - prev['center']) < max(prev['width'], g['width'])
                if same_sign and near:
                    if abs(g['amplitude']) > abs(prev['amplitude']):
                        out[-1] = g
                    elif abs(g['amplitude']) == abs(prev['amplitude']):
                        prev['center'] = (prev['center'] + g['center']) / 2.0
                    continue
            out.append(g)
        return out

    def auto_detect_peaks(self, y_data, x_data=None, background='none'):
        """Automatically detect initial peaks, finding both positive and negative, but always returning positive width.
        With a background ('constant', 'linear') the heights are measured
        above its first guess (initial_background), not from zero."""
        # Find both positive and negative peaks separately. A peak must stand
        # out by 10 % of the data's range and by 5x the noise; a negative
        # peak must also lie that much BELOW the baseline (the median) - the
        # dip between two neighbouring positive bands is not a peak.
        y_raw = np.asarray(y_data, dtype=float)
        span = float(np.max(y_raw) - np.min(y_raw))
        noise = float(np.median(np.abs(np.diff(y_raw)))) / 0.6745 / np.sqrt(2) if y_raw.size > 2 else 0.0
        threshold = max(span * 0.1, 5.0 * noise)
        baseline = float(np.median(y_raw))
        # found on lightly smoothed data (a short Savitzky-Golay filter): single
        # noisy points no longer pass for narrow peaks, and the heights and
        # widths are those of the band, not of its noisiest point
        y_data = y_raw
        if y_raw.size >= 21:
            from scipy.signal import savgol_filter
            y_data = savgol_filter(y_raw, 7, 2)
        peaks_pos, props_pos = find_peaks(y_data, prominence=threshold, width=3)
        peaks_neg, props_neg = find_peaks(-y_data, prominence=threshold, width=3,
                                          height=-(baseline - threshold))

        initial_guesses = []
        
        # Process positive peaks
        for i, peak_idx in enumerate(peaks_pos):
            center = x_data[peak_idx] if x_data is not None else peak_idx
            amplitude = y_data[peak_idx]
            width_in_points = props_pos['widths'][i]
            width_in_x_units = width_in_points * (x_data[1] - x_data[0] if x_data is not None and len(x_data) > 1 else 1)
            # find_peaks measures the full width at half height (FWHM); the
            # Gaussian's width parameter is sigma = FWHM / 2.355
            width_in_x_units = width_in_x_units / _FWHM_PER_SIGMA
            
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
            # find_peaks measures the full width at half height (FWHM); the
            # Gaussian's width parameter is sigma = FWHM / 2.355
            width_in_x_units = width_in_x_units / _FWHM_PER_SIGMA
            
            initial_guesses.append({
                'model': 'Gaussian',
                'center': center,
                'amplitude': amplitude,
                'width': abs(width_in_x_units) # Ensure width is positive
            })

        initial_guesses = self._merge_split(initial_guesses)
        if x_data is not None and resolve_background(x_data, y_raw, background) != 'none':
            bg = initial_background(x_data, y_raw, background)
            for p in initial_guesses:
                p['amplitude'] = float(p['amplitude']) - float(background_values(bg, [p['center']])[0])
        # Sort all found peaks by their center position
        initial_guesses.sort(key=lambda p: p['center'])
        
        return initial_guesses