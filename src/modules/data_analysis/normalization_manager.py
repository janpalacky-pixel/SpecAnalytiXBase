# src/modules/data_analysis/normalization_manager.py

import json
import os
import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match, describe_axis_mismatch
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.progress_utils import notify_progress
try:
    from scipy import integrate
except ImportError:
    pass

logger = get_logger(__name__)

# np.trapz was removed in NumPy 2.0 (renamed to np.trapezoid). Using this
# shim instead of calling either name directly means this module works
# whether the app is running on NumPy 1.x or 2.x, rather than crashing
# with AttributeError the moment anyone upgrades.
_trapz = getattr(np, 'trapezoid', None) or np.trapz


# Presets are stored as JSON in the user's home directory so they persist
# across application restarts, independent of any single dialog session.
_PRESETS_DIR = os.path.join(os.path.expanduser('~'), '.specanalytixbase')
_PRESETS_FILE = os.path.join(_PRESETS_DIR, 'normalization_region_presets.json')


class NormalizationManager:
    """Business logic for normalization operations on spectra."""

    def __init__(self):
        self.normalization_mode = "max_peak"

        # Multiple regions: list of (x_min, x_max) tuples.
        # Legacy single-range attributes kept as properties for backward compat.
        self.x_ranges: list = []          # primary source of truth

        # Include (False) or Exclude (True) mode — mirrors spectral_range_manager logic
        self.is_exclude_mode: bool = False

        # Scatter-correction parameters
        self.reference_spectrum_index = 0
        self.snv_center = True
        self.msc_reference = None
        # MSC's regression (offset + slope vs. the mean spectrum) is fit
        # over the WHOLE spectrum by default — the classical formulation,
        # appropriate when most of the range is scatter-dominated and only
        # a few narrow bands carry real signal. Setting this True instead
        # fits the regression using only the defined normalization region
        # (e.g. a known scatter-only, signal-free window) — a legitimate
        # alternative when you want to exclude real absorption peaks from
        # the fit entirely. Either way, the resulting correction (y - a) / b
        # is always applied to the full spectrum, same as every other
        # region-based method here (factor computed from region, applied
        # to the whole curve).
        self.msc_use_region: bool = False

        # Percentile-based method parameters
        self.percentile_value: float = 95.0   # used by both 'quantile' and 'top_mean'

        # Target value for ratio-based methods (max_peak, unit_area, vector,
        # quantile, top_mean, reference). target_mode selects how the result
        # is scaled:
        #   'standard'      — each spectrum divided by its own factor (result ~1.0). Default.
        #   'mean_relative' — each spectrum divided by (factor / mean(all factors)),
        #                     so spectra are corrected relative to each other while
        #                     the absolute scale stays near the original data's magnitude.
        #   'custom'        — standard result multiplied by target_value.
        self.target_mode: str = 'standard'
        self.target_value: float = 1.0

        # Labels of any spectra skipped on the most recent normalize_spectra()
        # call because they don't share the same x-axis as the spectra
        # they'd otherwise be combined/compared against (MSC, SVD, and
        # Reference modes all require this — see normalize_spectra and
        # _normalize_reference_spectrum).
        self.skipped_labels: list = []

    # Methods for which target_value scaling is meaningful — i.e. methods
    # that divide by a single scalar factor (peak, area, norm, percentile).
    # 'reference' is intentionally excluded: it's a point-wise ratio against
    # another spectrum, not a single-factor division, so "result scaling"
    # has no clean interpretation there.
    RATIO_BASED_MODES = ('max_peak', 'unit_area', 'vector', 'quantile', 'top_mean')

    # ------------------------------------------------------------------
    # Region presets — named (x_min, x_max) region sets saved to disk so
    # they persist across dialog sessions and application restarts.
    # ------------------------------------------------------------------
    @staticmethod
    def list_region_presets() -> dict:
        """Return {preset_name: [(x_min, x_max), ...]} loaded from disk.
        Returns an empty dict if no presets have been saved yet, or if the
        file is missing/corrupted (treated the same as "no presets")."""
        if not os.path.exists(_PRESETS_FILE):
            return {}
        try:
            with open(_PRESETS_FILE, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            # Tuples don't survive JSON round-trip — convert lists back.
            return {name: [tuple(r) for r in regions] for name, regions in data.items()}
        except Exception:
            return {}

    @staticmethod
    def save_region_preset(name: str, regions: list) -> None:
        """Save *regions* (list of (x_min, x_max) tuples) under *name*,
        overwriting any existing preset with the same name."""
        if not name:
            raise ValueError('Preset name cannot be empty')
        os.makedirs(_PRESETS_DIR, exist_ok=True)
        presets = NormalizationManager.list_region_presets()
        presets[name] = [list(r) for r in regions]
        with open(_PRESETS_FILE, 'w', encoding='utf-8') as fh:
            json.dump(presets, fh, indent=2)

    @staticmethod
    def delete_region_preset(name: str) -> None:
        """Remove the preset *name* if it exists; no-op otherwise."""
        presets = NormalizationManager.list_region_presets()
        if name in presets:
            del presets[name]
            os.makedirs(_PRESETS_DIR, exist_ok=True)
            with open(_PRESETS_FILE, 'w', encoding='utf-8') as fh:
                json.dump(presets, fh, indent=2)

    # ------------------------------------------------------------------
    # Backward-compatibility properties so old code using .x_min/.x_max
    # still works without modification.
    # ------------------------------------------------------------------
    @property
    def x_min(self):
        return self.x_ranges[0][0] if self.x_ranges else None

    @x_min.setter
    def x_min(self, value):
        if value is None:
            self.x_ranges = []
        elif self.x_ranges:
            self.x_ranges[0] = (value, self.x_ranges[0][1])
        else:
            self.x_ranges = [(value, value)]   # placeholder until x_max is set

    @property
    def x_max(self):
        return self.x_ranges[0][1] if self.x_ranges else None

    @x_max.setter
    def x_max(self, value):
        if value is None:
            self.x_ranges = []
        elif self.x_ranges:
            self.x_ranges[0] = (self.x_ranges[0][0], value)
        else:
            self.x_ranges = [(value, value)]   # placeholder

    # ------------------------------------------------------------------
    # Range helpers
    # ------------------------------------------------------------------
    def get_default_range(self, spectra):
        """Return (x_min, x_max) covering all provided spectra."""
        if not spectra:
            return None, None
        x_mins, x_maxs = [], []
        for spectrum in spectra:
            x_scale = spectrum.get('original_x_scale', spectrum['x_scale'])
            if len(x_scale) > 0:
                x_mins.append(np.min(x_scale))
                x_maxs.append(np.max(x_scale))
        if not x_mins:
            return None, None
        return min(x_mins), max(x_maxs)

    def _get_range_mask(self, x_scale):
        """Return a boolean mask for the normalization region.

        Include mode (is_exclude_mode=False):
            True inside the UNION of all x_ranges.
        Exclude mode (is_exclude_mode=True):
            True everywhere EXCEPT inside the union of x_ranges
            (full spectrum minus the selected regions).
        If no ranges are defined, returns all-True regardless of mode.
        """
        if not self.x_ranges:
            return np.ones(len(x_scale), dtype=bool)

        union = np.zeros(len(x_scale), dtype=bool)
        for x_min, x_max in self.x_ranges:
            union |= (x_scale >= x_min) & (x_scale <= x_max)

        return ~union if self.is_exclude_mode else union

    # ------------------------------------------------------------------
    # Intensity normalization methods
    # ------------------------------------------------------------------
    def _get_vector_factor(self, y_scale, x_scale):
        """Return the L2-norm factor used by vector normalization."""
        mask = self._get_range_mask(x_scale)
        return np.linalg.norm(y_scale[mask]) if np.any(mask) else np.linalg.norm(y_scale)

    def _normalize_vector(self, y_scale, x_scale):
        """Vector (L2) normalization — divides by Euclidean norm of the
        selected region; result is applied to the full spectrum."""
        norm = self._get_vector_factor(y_scale, x_scale)
        return y_scale / norm if norm != 0 else y_scale.copy()

    def _get_unit_area_factor(self, x_scale, y_scale):
        """Return the integral factor used by area normalization."""
        mask = self._get_range_mask(x_scale)
        if np.any(mask):
            return _trapz(y_scale[mask], x_scale[mask])
        return _trapz(y_scale, x_scale)

    def _normalize_unit_area(self, x_scale, y_scale):
        """Area normalization — divides by the integral over the selected region."""
        area = self._get_unit_area_factor(x_scale, y_scale)
        return y_scale / area if area != 0 else y_scale.copy()

    def _get_max_peak_factor(self, y_scale, x_scale):
        """Return the maximum factor used by peak-intensity normalization."""
        mask = self._get_range_mask(x_scale)
        return np.max(y_scale[mask]) if np.any(mask) else np.max(y_scale)

    def _normalize_max_peak(self, y_scale, x_scale):
        """Peak intensity normalization — divides by the maximum in the selected region."""
        max_val = self._get_max_peak_factor(y_scale, x_scale)
        return y_scale / max_val if max_val != 0 else y_scale.copy()

    def _get_quantile_factor(self, y_scale, x_scale):
        """Return the Nth-percentile factor used by robust-peak normalization."""
        mask = self._get_range_mask(x_scale)
        data = y_scale[mask] if np.any(mask) else y_scale
        return np.percentile(data, self.percentile_value)

    def _normalize_quantile(self, y_scale, x_scale):
        """Robust peak normalization — divides by the Nth percentile of the
        selected region. N is configurable (default 95)."""
        q = self._get_quantile_factor(y_scale, x_scale)
        return y_scale / q if q != 0 else y_scale.copy()

    def _get_top_mean_factor(self, y_scale, x_scale):
        """Return the mean-of-top-N% factor used by top-mean normalization."""
        mask = self._get_range_mask(x_scale)
        data = y_scale[mask] if np.any(mask) else y_scale
        threshold = np.percentile(data, self.percentile_value)
        top_points = data[data >= threshold]
        return np.mean(top_points) if len(top_points) > 0 else threshold

    def _normalize_top_mean(self, y_scale, x_scale):
        """Mean-of-top-N% normalization — divides by the mean of all points
        that lie above the Nth percentile in the selected region.

        This gives a better estimate of the true peak intensity than the
        percentile boundary alone, especially for broad or flat-topped bands:
        instead of picking one threshold value it averages the actual peak-top
        points. N is the same configurable percentile_value parameter."""
        mean_top = self._get_top_mean_factor(y_scale, x_scale)
        return y_scale / mean_top if mean_top != 0 else y_scale.copy()

    def _get_reference_factor(self, y_scale, reference_spectrum, x_scale=None, reference_x_scale=None):
        """Return the mean point-wise ratio factor used by reference normalization
        (only meaningful as a scalar summary for mean_relative scaling)."""
        if len(reference_spectrum) != len(y_scale):
            return 1.0
        if (x_scale is not None and reference_x_scale is not None
                and not axes_match(x_scale, reference_x_scale)):
            return 1.0
        ref = reference_spectrum.copy()
        ref[ref == 0] = 1e-10
        ratio = y_scale / ref
        return np.mean(ratio)

    def _normalize_reference_spectrum(self, y_scale, reference_spectrum, x_scale=None, reference_x_scale=None):
        """Divide by a reference spectrum (element-wise).

        Requires the reference to share the SAME x-axis as the spectrum
        being normalized — this is a point-by-point division, so a
        length match alone doesn't guarantee the two spectra's points
        correspond to the same wavenumbers. Verified directly: two
        same-length spectra with a 50-unit x-offset between them
        previously divided point-by-point without any warning, silently
        comparing unrelated positions. Refuses (returns the spectrum
        unchanged) rather than silently mismatching, same as every other
        "combines/compares spectra" operation in this app.
        """
        if len(reference_spectrum) != len(y_scale):
            return y_scale.copy()
        if (x_scale is not None and reference_x_scale is not None
                and not axes_match(x_scale, reference_x_scale)):
            return y_scale.copy()
        ref = reference_spectrum.copy()
        ref[ref == 0] = 1e-10
        return y_scale / ref

    # ------------------------------------------------------------------
    # Scatter correction methods  (kept in Normalization category)
    # ------------------------------------------------------------------
    def _normalize_snv(self, y_scale, x_scale):
        """Standard Normal Variate — removes multiplicative scatter effects.
        Computed on the selected region, applied to the full spectrum."""
        mask = self._get_range_mask(x_scale)
        data = y_scale[mask] if np.any(mask) else y_scale
        mean_val = np.mean(data)
        std_val = np.std(data)
        centered = y_scale - mean_val
        return centered / std_val if std_val != 0 else centered

    def _normalize_msc(self, spectra_matrix, current_spectrum_idx, fit_mask=None):
        """Multiplicative Scatter Correction — fits each spectrum to the
        mean spectrum using linear regression.

        If fit_mask is given, the regression coefficients (a, b) are
        estimated using only the masked points (e.g. a defined normalization
        region) — but the correction (current - a) / b is still applied to
        the FULL spectrum, same as every other region-based method here.
        If fit_mask is None (default), the regression uses the whole
        spectrum, matching the classical MSC formulation.
        """
        reference = np.mean(spectra_matrix, axis=1) if self.msc_reference is None else self.msc_reference
        current = spectra_matrix[:, current_spectrum_idx]

        if fit_mask is not None:
            fit_reference = reference[fit_mask]
            fit_current = current[fit_mask]
        else:
            fit_reference = reference
            fit_current = current

        A = np.vstack([np.ones(len(fit_reference)), fit_reference]).T
        try:
            a, b = np.linalg.lstsq(A, fit_current, rcond=None)[0]
            return (current - a) / b if b != 0 else current.copy()
        except np.linalg.LinAlgError:
            return current.copy()

    def _normalize_svd_pca(self, spectra_matrix, x_ranges=None):
        """SVD factor normalization — uses first PC loadings as normalization
        factors across the whole set of spectra."""
        if x_ranges is not None:
            working = np.zeros_like(spectra_matrix)
            for i, (x_scale, mask) in enumerate(x_ranges):
                if i < spectra_matrix.shape[1]:
                    working[:, i] = spectra_matrix[:, i] * mask.astype(float) if np.any(mask) else spectra_matrix[:, i]
        else:
            working = spectra_matrix

        U, S, Vt = np.linalg.svd(working, full_matrices=False)
        V = Vt.T
        first_loadings = V[:, 0]
        mean_loading = np.mean(first_loadings)
        norm_factors = np.abs(first_loadings / mean_loading) if abs(mean_loading) > 1e-10 else np.ones(len(first_loadings))

        explained = S ** 2 / np.sum(S ** 2)

        normalized = spectra_matrix.copy()
        for i in range(spectra_matrix.shape[1]):
            if norm_factors[i] > 1e-10:
                normalized[:, i] = spectra_matrix[:, i] / norm_factors[i]
        return normalized, norm_factors, explained

    # ------------------------------------------------------------------
    # Methods moved to Baseline Correction — kept here only so that
    # saved pipelines that reference these mode strings still work.
    # They are no longer shown in the Normalization dialog.
    # ------------------------------------------------------------------
    def _normalize_min_max(self, y_scale, x_scale):
        """Min-max [0, 1] normalisation.

        Computes min and max over the selected region, then applies the same
        linear rescaling to the *full* spectrum so that the region spans [0, 1].
        The transformation is: y_out = (y - min_region) / (max_region - min_region).
        """
        mask = self._get_range_mask(x_scale)
        data = y_scale[mask] if np.any(mask) else y_scale
        min_val = np.min(data)
        max_val = np.max(data)
        rng = max_val - min_val
        return (y_scale - min_val) / rng if rng != 0 else y_scale.copy()

    def _normalize_offset_correction(self, y_scale, x_scale):
        """Offset correction — subtract the mean of the selected region.

        Typical use: define a silent/flat region (e.g. 320–330 nm for CD or
        absorption spectra) and subtract its mean as a constant offset from
        the entire spectrum. Zeros the baseline without any scaling.
        """
        mask = self._get_range_mask(x_scale)
        offset = np.mean(y_scale[mask]) if np.any(mask) else np.mean(y_scale)
        return y_scale - offset

    def _normalize_mean_centering(self, y_scale, x_scale):
        mask = self._get_range_mask(x_scale)
        mean_val = np.mean(y_scale[mask]) if np.any(mask) else np.mean(y_scale)
        return y_scale - mean_val

    def _normalize_z_score(self, y_scale, x_scale):
        mask = self._get_range_mask(x_scale)
        data = y_scale[mask] if np.any(mask) else y_scale
        mean_val, std_val = np.mean(data), np.std(data)
        return (y_scale - mean_val) / std_val if std_val != 0 else y_scale - mean_val

    def _normalize_range_scaling(self, y_scale, x_scale):
        mask = self._get_range_mask(x_scale)
        data = y_scale[mask] if np.any(mask) else y_scale
        min_val, max_val = np.min(data), np.max(data)
        rng = max_val - min_val
        return (y_scale - min_val) / rng if rng != 0 else y_scale.copy()

    def _normalize_robust_scaling(self, y_scale, x_scale):
        mask = self._get_range_mask(x_scale)
        data = y_scale[mask] if np.any(mask) else y_scale
        median_val = np.median(data)
        iqr = np.percentile(data, 75) - np.percentile(data, 25)
        return (y_scale - median_val) / iqr if iqr != 0 else y_scale - median_val

    def _normalize_baseline_correction(self, y_scale, x_scale):
        mask = self._get_range_mask(x_scale)
        baseline = np.min(y_scale[mask]) if np.any(mask) else np.min(y_scale)
        return y_scale - baseline

    # ------------------------------------------------------------------
    # Factor dispatch — used both to apply normalization and to pre-compute
    # the cross-spectrum mean factor for 'mean_relative' target mode.
    # ------------------------------------------------------------------
    def _get_factor(self, mode, y_scale, x_scale, spectra=None, index=None):
        """Return the raw scalar factor for a ratio-based mode, without dividing."""
        if mode == 'vector':
            return self._get_vector_factor(y_scale, x_scale)
        elif mode == 'unit_area':
            return self._get_unit_area_factor(x_scale, y_scale)
        elif mode == 'max_peak':
            return self._get_max_peak_factor(y_scale, x_scale)
        elif mode == 'quantile':
            return self._get_quantile_factor(y_scale, x_scale)
        elif mode == 'top_mean':
            return self._get_top_mean_factor(y_scale, x_scale)
        elif mode == 'reference':
            if spectra is not None and len(spectra) > self.reference_spectrum_index:
                ref_spectrum = spectra[self.reference_spectrum_index]
                return self._get_reference_factor(
                    y_scale, ref_spectrum['y_scale'],
                    x_scale=x_scale, reference_x_scale=ref_spectrum.get('x_scale')
                )
            return 1.0
        return 1.0

    # ------------------------------------------------------------------
    # Main normalization entry point
    # ------------------------------------------------------------------
    def normalize_spectra(self, spectra, settings, progress_callback=None):
        """Apply normalization to a list of spectra dicts.

        progress_callback : optional callable, invoked every 50 spectra
            during the main per-spectrum loop below — see
            src/modules/utils/progress_utils.py's notify_progress for the
            full reasoning; same hook/contract used by every other
            operation's manager in this codebase. None (the default) —
            no change from before. Only hooked into the main output-
            building loop (not the conditional MSC/SVD or ratio-based
            pre-passes above it), matching how every other manager in
            this codebase hooks its one real per-spectrum processing
            loop rather than every internal pre-computation step.
        """
        self.update_settings(settings)

        normalized_spectra = []
        mode = self.normalization_mode

        # Pre-build matrix for methods that need all spectra at once
        spectra_matrix = None
        valid_indices = []
        msc_fit_mask = None   # boolean mask used to restrict MSC's regression fit, if enabled
        self.skipped_labels = []
        if self.normalization_mode in ('msc', 'svd'):
            all_y = []
            shared_x_scale = None
            for i, s in enumerate(spectra):
                x, y = s['x_scale'], s['y_scale']
                if len(x) == 0 or len(y) == 0 or len(x) != len(y):
                    continue
                if shared_x_scale is None:
                    shared_x_scale = x
                    all_y.append(y.copy())
                    valid_indices.append(i)
                elif axes_match(x, shared_x_scale):
                    all_y.append(y.copy())
                    valid_indices.append(i)
                else:
                    logger.warning(
                        "Excluding '%s' from %s: x-axis doesn't match the "
                        "other spectra being combined.\n%s",
                        s.get('label', '?'), self.normalization_mode,
                        describe_axis_mismatch(spectra[valid_indices[0]], s, self.normalization_mode)
                        if valid_indices else ''
                    )
                    self.skipped_labels.append(s.get('label', '?'))
            if all_y:
                spectra_matrix = np.column_stack(all_y)
            if (self.normalization_mode == 'msc' and self.msc_use_region
                    and shared_x_scale is not None):
                mask = self._get_range_mask(shared_x_scale)
                if np.any(mask):
                    msc_fit_mask = mask

        normalized_matrix = None
        norm_factors = None
        explained_variance = None
        if self.normalization_mode == 'svd' and spectra_matrix is not None:
            x_ranges_for_svd = None
            if self.x_ranges:
                x_ranges_for_svd = []
                for i in valid_indices:
                    x_scale = spectra[i]['x_scale'].copy()
                    mask = self._get_range_mask(x_scale)
                    x_ranges_for_svd.append((x_scale, mask))
            normalized_matrix, norm_factors, explained_variance = self._normalize_svd_pca(
                spectra_matrix, x_ranges_for_svd
            )

        # Pre-pass: compute every spectrum's raw factor up front. This serves
        # two purposes:
        #   1. For 'mean_relative' target mode, the mean across all factors is
        #      needed before any spectrum is divided (existing behaviour).
        #   2. Every spectrum's individual factor is now also stored in
        #      normalization_info so the dialog can show a per-spectrum
        #      factor table and flag outliers, regardless of target_mode.
        # Computed from ALL spectra passed in (the full dataset for the
        # operation), not a subset, so results are independent of any
        # display/preview selection elsewhere.
        mean_factor = None
        factors_by_index: dict = {}
        if mode in self.RATIO_BASED_MODES:
            raw_factors = []
            for idx, spectrum in enumerate(spectra):
                x_scale = spectrum['x_scale']
                y_scale = spectrum['y_scale']
                if len(x_scale) == 0 or len(y_scale) == 0 or len(x_scale) != len(y_scale):
                    continue
                f = self._get_factor(mode, y_scale, x_scale, spectra=spectra)
                factors_by_index[idx] = f
                if f != 0:
                    raw_factors.append(f)
            if raw_factors and self.target_mode == 'mean_relative':
                mean_factor = float(np.mean(raw_factors))

        for i, spectrum in enumerate(spectra):
            notify_progress(progress_callback, i)
            norm_s = spectrum.copy()
            x_scale = spectrum['x_scale'].copy()
            y_scale = spectrum['y_scale'].copy()

            if len(x_scale) == 0 or len(y_scale) == 0 or len(x_scale) != len(y_scale):
                normalized_spectra.append(norm_s)
                continue

            if mode == 'vector':
                normalized_y = self._normalize_vector(y_scale, x_scale)
            elif mode == 'unit_area':
                normalized_y = self._normalize_unit_area(x_scale, y_scale)
            elif mode == 'max_peak':
                normalized_y = self._normalize_max_peak(y_scale, x_scale)
            elif mode == 'quantile':
                normalized_y = self._normalize_quantile(y_scale, x_scale)
            elif mode == 'top_mean':
                normalized_y = self._normalize_top_mean(y_scale, x_scale)
            elif mode == 'min_max':
                normalized_y = self._normalize_min_max(y_scale, x_scale)
            elif mode == 'offset_correction':
                normalized_y = self._normalize_offset_correction(y_scale, x_scale)
            elif mode == 'reference':
                if len(spectra) > self.reference_spectrum_index:
                    ref_spectrum = spectra[self.reference_spectrum_index]
                    normalized_y = self._normalize_reference_spectrum(
                        y_scale, ref_spectrum['y_scale'],
                        x_scale=x_scale, reference_x_scale=ref_spectrum.get('x_scale')
                    )
                else:
                    normalized_y = y_scale.copy()
            elif mode == 'snv':
                normalized_y = self._normalize_snv(y_scale, x_scale)
            elif mode == 'msc':
                if spectra_matrix is not None and i in valid_indices:
                    normalized_y = self._normalize_msc(
                        spectra_matrix, valid_indices.index(i), fit_mask=msc_fit_mask
                    )
                else:
                    normalized_y = y_scale.copy()
            elif mode == 'svd':
                if normalized_matrix is not None and i in valid_indices:
                    normalized_y = normalized_matrix[:, valid_indices.index(i)]
                else:
                    normalized_y = y_scale.copy()
            # Legacy / moved-to-baseline methods — still functional for saved pipelines
            elif mode == 'mean_center':
                normalized_y = self._normalize_mean_centering(y_scale, x_scale)
            elif mode == 'z_score':
                normalized_y = self._normalize_z_score(y_scale, x_scale)
            elif mode == 'range_scaling':
                normalized_y = self._normalize_range_scaling(y_scale, x_scale)
            elif mode == 'robust_scaling':
                normalized_y = self._normalize_robust_scaling(y_scale, x_scale)
            elif mode == 'baseline_correction':
                normalized_y = self._normalize_baseline_correction(y_scale, x_scale)
            else:
                normalized_y = y_scale.copy()

            # Scale ratio-based results according to target_mode:
            #   'standard'      — leave as-is (result ~1.0 per spectrum's own factor)
            #   'mean_relative' — normalized_y currently equals y / factor; multiply
            #                     back by mean_factor so the result lands near the
            #                     batch's original scale instead of unity, while
            #                     spectra remain corrected relative to each other.
            #   'custom'        — multiply by the user-specified target_value.
            if mode in self.RATIO_BASED_MODES:
                if self.target_mode == 'mean_relative' and mean_factor is not None:
                    normalized_y = normalized_y * mean_factor
                elif self.target_mode == 'custom' and self.target_value != 1.0:
                    normalized_y = normalized_y * self.target_value

            norm_s['y_scale'] = normalized_y
            norm_s['normalization_info'] = {
                'mode': mode,
                'x_ranges': list(self.x_ranges),
                # legacy keys kept so downstream code that reads x_min/x_max still works
                'x_min': self.x_min,
                'x_max': self.x_max,
            }
            if mode in self.RATIO_BASED_MODES:
                norm_s['normalization_info']['target_mode'] = self.target_mode
                if self.target_mode == 'custom':
                    norm_s['normalization_info']['target_value'] = self.target_value
                elif self.target_mode == 'mean_relative':
                    norm_s['normalization_info']['mean_factor'] = mean_factor
                if i in factors_by_index:
                    norm_s['normalization_info']['factor'] = factors_by_index[i]
            if mode == 'svd' and explained_variance is not None:
                norm_s['normalization_info']['explained_variance'] = explained_variance
                if norm_factors is not None and i in valid_indices:
                    norm_s['normalization_info']['svd_factor'] = norm_factors[valid_indices.index(i)]
            if mode == 'msc':
                norm_s['normalization_info']['msc_use_region'] = self.msc_use_region

            # norm_s = spectrum.copy() above is a SHALLOW copy — norm_s['metadata']
            # would still be the exact same dict object as the source spectrum's
            # metadata unless replaced here, so writing into it directly would
            # silently mutate the original too (same bug found and fixed in
            # BaselineManager.apply_baseline_correction and
            # CosmicRayManager.apply).
            norm_s['metadata'] = dict(norm_s.get('metadata') or {})
            # Shared, chronologically-ordered history across every operation
            # type that records one (SVD Background, Manual Baseline, Cosmic
            # Ray Removal, and this) — see correction_history.py. Kept
            # deliberately compact (mode, region, and the single scalar
            # factor/target info that's actually meaningful for this mode)
            # rather than duplicating everything already in
            # normalization_info, which stays as the fuller, code-facing
            # record.
            history_entry = {'mode': mode, 'x_ranges': list(self.x_ranges)}
            if mode in self.RATIO_BASED_MODES and i in factors_by_index:
                history_entry['factor'] = float(factors_by_index[i])
            if mode == 'reference':
                history_entry['reference_spectrum_index'] = self.reference_spectrum_index
            norm_s['metadata']['correction_history'] = append_correction_history(
                spectrum.get('metadata'), 'Normalization', history_entry
            )

            normalized_spectra.append(norm_s)

        return normalized_spectra

    def get_factor_zscores(self, factors: dict) -> dict:
        """
        Compute how many standard deviations each spectrum's factor is from
        the batch mean.

        Parameters
        ----------
        factors : dict mapping spectrum index -> raw factor (as stored in
                  normalization_info['factor'] by normalize_spectra).

        Returns
        -------
        dict mapping spectrum index -> z-score, for EVERY index in
        *factors* (not just outliers). Empty dict if fewer than 3 factors
        are given (not enough data for a meaningful standard deviation) or
        if the standard deviation is zero (all factors identical) — in
        both cases a z-score isn't meaningful to show at all.
        """
        if len(factors) < 3:
            return {}

        values = np.array(list(factors.values()), dtype=float)
        mean = float(np.mean(values))
        std = float(np.std(values))
        if std == 0:
            return {}

        return {idx: (f - mean) / std for idx, f in factors.items()}

    def get_factor_outliers(self, factors: dict, threshold: float = 3.0) -> dict:
        """
        Flag spectra whose factor deviates from the mean by more than
        *threshold* standard deviations.

        Parameters
        ----------
        factors   : dict mapping spectrum index -> raw factor (as stored in
                    normalization_info['factor'] by normalize_spectra).
        threshold : number of standard deviations considered an outlier.

        Returns
        -------
        dict mapping spectrum index -> z-score, for every index whose
        |z-score| exceeds *threshold*. Empty dict if fewer than 3 factors
        are given (not enough data for a meaningful standard deviation) or
        if the standard deviation is zero (all factors identical).
        """
        zscores = self.get_factor_zscores(factors)
        return {idx: z for idx, z in zscores.items() if abs(z) > threshold}

    def update_settings(self, settings):
        """Update normalization settings from a dict.

        Accepts both the new ``x_ranges`` key (list of tuples) and the legacy
        ``x_min`` / ``x_max`` keys so that old saved pipelines keep working.
        """
        if 'normalization_mode' in settings:
            self.normalization_mode = settings['normalization_mode']

        if 'x_ranges' in settings and settings['x_ranges']:
            self.x_ranges = list(settings['x_ranges'])
        elif 'x_min' in settings and 'x_max' in settings:
            x_min = settings['x_min']
            x_max = settings['x_max']
            if x_min is not None and x_max is not None:
                self.x_ranges = [(x_min, x_max)]
            else:
                self.x_ranges = []

        if 'is_exclude_mode' in settings:
            self.is_exclude_mode = bool(settings['is_exclude_mode'])

        if 'reference_spectrum_index' in settings:
            self.reference_spectrum_index = int(settings['reference_spectrum_index'])
        if 'snv_center' in settings:
            self.snv_center = bool(settings['snv_center'])
        if 'msc_use_region' in settings:
            self.msc_use_region = bool(settings['msc_use_region'])
        if 'percentile_value' in settings:
            self.percentile_value = float(settings['percentile_value'])
        if 'target_value' in settings:
            self.target_value = float(settings['target_value'])
        if 'target_mode' in settings:
            self.target_mode = str(settings['target_mode'])
